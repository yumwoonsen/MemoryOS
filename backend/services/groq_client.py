"""Groq Chat Completions adapter for GPT-OSS strict structured generation."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import openai
from openai import OpenAI
from openai.lib._pydantic import to_strict_json_schema
from pydantic import ValidationError

from backend.services.openai_client import (
    OpenAIProviderError,
    _sdk_error_code,
    _translate_sdk_error,
)
from backend.services.prompt_loader import load_prompt
from backend.services.provider_observability import ProviderObservability
from backend.services.structured_generator import ModelT

DEFAULT_MODEL = "openai/gpt-oss-20b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MAX_OUTPUT_TOKENS = 2_000
# GPT-OSS reasoning tokens share this completion budget.  The v2.1 decision now
# includes four player perspectives plus a complete multi-objective mission, so
# the former 2k ceiling could terminate strict JSON before the closing fields.
V2_INTERPRETATION_MAX_OUTPUT_TOKENS = 4_000
REQUEST_TIMEOUT_SECONDS = 30.0
SDK_MAX_RETRIES = 2
logger = logging.getLogger(__name__)


class GroqProviderError(OpenAIProviderError):
    """Safe Groq failure compatible with the API's provider-error boundary."""


class GroqStructuredGenerator:
    """Run every model-capable pipeline stage through Groq GPT-OSS 20B."""

    provider_name = "groq"
    semantic_retry_limit = 1
    narrative_fallback_enabled = True

    def __init__(self, model_name: str | None = None) -> None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key or not api_key.strip():
            raise GroqProviderError(
                stage="configuration",
                code="missing_api_key",
                retryable=False,
            )
        self.model_name = model_name or os.getenv("GROQ_MODEL") or DEFAULT_MODEL
        self._client = OpenAI(
            api_key=api_key.strip(),
            base_url=GROQ_BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            max_retries=SDK_MAX_RETRIES,
        )
        self._observability = ProviderObservability(
            provider=self.provider_name,
            model=self.model_name,
            mode="live_ai",
            configured_max_retries=SDK_MAX_RETRIES,
        )

    @property
    def usage_totals(self) -> dict[str, int]:
        """Return aggregate token counts without retaining request content."""

        return self._observability.usage_totals

    @property
    def observability(self) -> dict[str, object]:
        """Return safe per-stage latency and token metrics."""

        return self._observability.snapshot()

    def generate(
        self,
        *,
        prompt_name: str,
        payload: dict[str, Any],
        response_model: type[ModelT],
        stage: str,
    ) -> ModelT:
        started = time.perf_counter()
        safe_error: GroqProviderError | None = None
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": load_prompt(prompt_name)},
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_model.__name__,
                        "strict": True,
                        "schema": to_strict_json_schema(response_model),
                    },
                },
                reasoning_effort="low",
                temperature=0,
                max_completion_tokens=(
                    V2_INTERPRETATION_MAX_OUTPUT_TOKENS
                    if stage.startswith("memory_interpretation")
                    else MAX_OUTPUT_TOKENS
                ),
            )
        except openai.OpenAIError as error:
            # Groq reports strict-schema generation failures as a 400 with the
            # stable json_validate_failed code.  Treat that one response as a
            # repairable malformed model output; never retain its body because
            # it can contain the rejected generation.
            if (
                isinstance(error, openai.BadRequestError)
                and _sdk_error_code(error) == "json_validate_failed"
            ):
                safe_error = GroqProviderError(
                    stage=stage,
                    code="provider_invalid_response",
                    retryable=False,
                )
            else:
                safe_error = _translate_sdk_error(
                    stage,
                    error,
                    error_type=GroqProviderError,
                )
        except (ValidationError, ValueError, TypeError):
            safe_error = GroqProviderError(
                stage=stage,
                code="provider_invalid_response",
                retryable=False,
            )
        except Exception:
            safe_error = GroqProviderError(
                stage=stage,
                code="provider_unexpected_error",
                retryable=False,
            )

        # Raise outside the handler so no SDK exception or provider-authored
        # request detail is retained on the public exception context.
        if safe_error is not None:
            self._record_failure(
                stage=stage,
                code=safe_error.code,
                retryable=safe_error.retryable,
                started=started,
            )
            raise safe_error

        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

        choices = getattr(response, "choices", None) or []
        message = getattr(choices[0], "message", None) if choices else None
        refusal = getattr(message, "refusal", None) if message is not None else None
        finish_reason = getattr(choices[0], "finish_reason", None) if choices else None
        content = getattr(message, "content", None) if message is not None else None
        if refusal or finish_reason == "content_filter":
            self._record_failure(
                stage=stage,
                code="provider_refusal",
                retryable=False,
                started=started,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            raise GroqProviderError(stage=stage, code="provider_refusal", retryable=False)
        if finish_reason == "length":
            self._record_failure(
                stage=stage,
                code="provider_output_limit",
                retryable=False,
                started=started,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            raise GroqProviderError(
                stage=stage,
                code="provider_output_limit",
                retryable=False,
            )
        if not isinstance(content, str) or not content.strip():
            self._record_failure(
                stage=stage,
                code="provider_no_output",
                retryable=False,
                started=started,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            raise GroqProviderError(
                stage=stage,
                code="provider_no_output",
                retryable=False,
            )
        parsed_error: GroqProviderError | None = None
        parsed: ModelT | None = None
        try:
            parsed = response_model.model_validate_json(content)
        except (ValidationError, ValueError, TypeError):
            parsed_error = GroqProviderError(
                stage=stage,
                code="provider_invalid_response",
                retryable=False,
            )
        if parsed_error is not None or parsed is None:
            self._record_failure(
                stage=stage,
                code="provider_invalid_response",
                retryable=False,
                started=started,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            raise parsed_error or GroqProviderError(
                stage=stage,
                code="provider_invalid_response",
                retryable=False,
            )

        latency_ms = (time.perf_counter() - started) * 1000
        self._observability.record(
            stage=stage,
            status="succeeded",
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        logger.info(
            "provider_call_complete provider=%s model=%s stage=%s input_tokens=%d "
            "output_tokens=%d latency_ms=%.2f",
            self.provider_name,
            self.model_name,
            stage,
            input_tokens,
            output_tokens,
            latency_ms,
        )
        return parsed

    def _record_failure(
        self,
        *,
        stage: str,
        code: str,
        retryable: bool,
        started: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        latency_ms = (time.perf_counter() - started) * 1000
        self._observability.record(
            stage=stage,
            status="failed",
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        logger.warning(
            "provider_call_failed provider=%s model=%s stage=%s code=%s "
            "retryable=%s latency_ms=%.2f",
            self.provider_name,
            self.model_name,
            stage,
            code,
            retryable,
            latency_ms,
        )
