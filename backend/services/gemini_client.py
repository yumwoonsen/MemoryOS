"""Gemini OpenAI-compatible adapter for schema-constrained generation."""

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

from backend.services.openai_client import OpenAIProviderError, _translate_sdk_error
from backend.services.prompt_loader import load_prompt
from backend.services.provider_observability import ProviderObservability
from backend.services.structured_generator import ModelT

DEFAULT_MODEL = "gemini-3.6-flash"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MAX_OUTPUT_TOKENS = 2_000
DEFAULT_V2_INTERPRETATION_MAX_OUTPUT_TOKENS = 4_000
MIN_V2_INTERPRETATION_MAX_OUTPUT_TOKENS = 1_000
MAX_V2_INTERPRETATION_MAX_OUTPUT_TOKENS = 16_000
REQUEST_TIMEOUT_SECONDS = 60.0
# Do not let hidden transport retries outlive the same-origin proxy. MemoryOS
# already owns one explicit, observable semantic correction attempt.
SDK_MAX_RETRIES = 0
logger = logging.getLogger(__name__)

# Gemini supports a documented subset of JSON Schema. Pydantic constraints remain
# authoritative after generation, so provider-unsupported hints can be removed from
# the wire schema without weakening MemoryOS validation.
UNSUPPORTED_SCHEMA_KEYS = {
    "const",
    "default",
    "examples",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "maxLength",
    "minLength",
    "multipleOf",
    "pattern",
    "uniqueItems",
}


class GeminiProviderError(OpenAIProviderError):
    """Safe Gemini failure compatible with the shared provider-error boundary."""


class GeminiStructuredGenerator:
    """Run MemoryOS stages through Gemini with a strict structured response."""

    provider_name = "gemini"
    semantic_retry_limit = 1

    def __init__(self, model_name: str | None = None) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or not api_key.strip():
            raise GeminiProviderError(
                stage="configuration",
                code="missing_api_key",
                retryable=False,
            )
        self.model_name = model_name or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
        self._v2_interpretation_max_output_tokens = self._configured_v2_output_tokens()
        self._client = OpenAI(
            api_key=api_key.strip(),
            base_url=GEMINI_BASE_URL,
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
        safe_error: GeminiProviderError | None = None
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
                        "schema": _gemini_json_schema(response_model),
                    },
                },
                reasoning_effort="low",
                max_completion_tokens=(
                    self._v2_interpretation_max_output_tokens
                    if stage.startswith("memory_interpretation")
                    else MAX_OUTPUT_TOKENS
                ),
            )
        except openai.OpenAIError as error:
            safe_error = _translate_sdk_error(
                stage,
                error,
                error_type=GeminiProviderError,
            )
        except (ValidationError, ValueError, TypeError):
            safe_error = GeminiProviderError(
                stage=stage,
                code="provider_invalid_response",
                retryable=False,
            )
        except Exception as error:
            # Keep provider-authored details private while retaining enough
            # diagnostic signal to distinguish SDK compatibility failures.
            logger.warning(
                "provider_call_exception provider=%s model=%s stage=%s exception_type=%s",
                self.provider_name,
                self.model_name,
                stage,
                type(error).__name__,
            )
            safe_error = GeminiProviderError(
                stage=stage,
                code="provider_unexpected_error",
                retryable=False,
            )

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
        finish_reason = getattr(choices[0], "finish_reason", None) if choices else None
        refusal = getattr(message, "refusal", None) if message is not None else None
        content = getattr(message, "content", None) if message is not None else None

        if refusal or finish_reason in {"content_filter", "safety"}:
            self._fail_output(
                stage=stage,
                code="provider_refusal",
                started=started,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        if finish_reason in {"length", "max_tokens"}:
            self._fail_output(
                stage=stage,
                code="provider_output_limit",
                started=started,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        if not isinstance(content, str) or not content.strip():
            self._fail_output(
                stage=stage,
                code="provider_no_output",
                started=started,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        parsed: ModelT | None = None
        parsed_invalid = False
        try:
            parsed = response_model.model_validate_json(content)
        except (ValidationError, ValueError, TypeError):
            # Leave the handler before raising so Pydantic/provider-authored
            # details cannot survive as exception context on the safe error.
            parsed_invalid = True
        if parsed_invalid or parsed is None:
            self._fail_output(
                stage=stage,
                code="provider_invalid_response",
                started=started,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
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

    @staticmethod
    def _configured_v2_output_tokens() -> int:
        raw_value = os.getenv("GEMINI_V2_MAX_OUTPUT_TOKENS")
        if raw_value is None or not raw_value.strip():
            return DEFAULT_V2_INTERPRETATION_MAX_OUTPUT_TOKENS
        try:
            value = int(raw_value)
        except ValueError:
            raise GeminiProviderError(
                stage="configuration",
                code="invalid_output_token_limit",
                retryable=False,
            ) from None
        if not (
            MIN_V2_INTERPRETATION_MAX_OUTPUT_TOKENS
            <= value
            <= MAX_V2_INTERPRETATION_MAX_OUTPUT_TOKENS
        ):
            raise GeminiProviderError(
                stage="configuration",
                code="invalid_output_token_limit",
                retryable=False,
            )
        return value

    def _fail_output(
        self,
        *,
        stage: str,
        code: str,
        started: float,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        self._record_failure(
            stage=stage,
            code=code,
            retryable=False,
            started=started,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        raise GeminiProviderError(stage=stage, code=code, retryable=False)

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


def _gemini_json_schema(response_model: type[ModelT]) -> dict[str, Any]:
    """Return the strict schema minus keywords unsupported by Gemini."""

    schema = to_strict_json_schema(response_model)

    def sanitize(node: object) -> None:
        if isinstance(node, dict):
            for key in UNSUPPORTED_SCHEMA_KEYS:
                node.pop(key, None)
            for value in node.values():
                sanitize(value)
        elif isinstance(node, list):
            for value in node:
                sanitize(value)

    sanitize(schema)
    return schema
