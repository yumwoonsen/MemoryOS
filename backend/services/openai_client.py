"""OpenAI Responses API adapter with Pydantic Structured Outputs."""

from __future__ import annotations

import json
import os
from typing import Any

import openai
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from backend.services.prompt_loader import load_prompt
from backend.services.structured_generator import ModelT

DEFAULT_MODEL = "gpt-5.6-luna"
MAX_OUTPUT_TOKENS = 2_000
REQUEST_TIMEOUT_SECONDS = 30.0
SDK_MAX_RETRIES = 2


class OpenAIProviderError(RuntimeError):
    """A safe, serializable failure raised at the provider boundary.

    The original SDK exception is deliberately not retained in public fields or
    included in the message because provider errors can contain request data.
    """

    def __init__(self, *, stage: str, code: str, retryable: bool) -> None:
        self.stage = stage
        self.code = code
        self.retryable = retryable
        super().__init__("The OpenAI provider could not complete the requested stage.")

    def as_dict(self) -> dict[str, str | bool]:
        """Return the fields an API layer may safely expose to clients."""

        return {
            "stage": self.stage,
            "code": self.code,
            "retryable": self.retryable,
        }


def _translate_sdk_error(stage: str, error: openai.OpenAIError) -> OpenAIProviderError:
    """Map SDK-specific failures to the stable MemoryOS provider contract."""

    if isinstance(error, openai.APITimeoutError):
        return OpenAIProviderError(stage=stage, code="provider_timeout", retryable=True)
    if isinstance(error, openai.RateLimitError):
        if _sdk_error_code(error) == "insufficient_quota":
            return OpenAIProviderError(
                stage=stage,
                code="provider_quota_exhausted",
                retryable=False,
            )
        return OpenAIProviderError(stage=stage, code="provider_rate_limited", retryable=True)
    if isinstance(error, openai.APIConnectionError):
        return OpenAIProviderError(stage=stage, code="provider_connection_error", retryable=True)
    if isinstance(error, openai.APIResponseValidationError):
        return OpenAIProviderError(stage=stage, code="provider_invalid_response", retryable=False)
    if isinstance(error, openai.ContentFilterFinishReasonError):
        return OpenAIProviderError(stage=stage, code="provider_refusal", retryable=False)
    if isinstance(error, openai.LengthFinishReasonError):
        return OpenAIProviderError(stage=stage, code="provider_output_limit", retryable=False)
    if isinstance(error, openai.APIStatusError):
        if error.status_code == 401:
            code, retryable = "provider_authentication_failed", False
        elif error.status_code == 403:
            code, retryable = "provider_permission_denied", False
        elif error.status_code in {408, 409} or error.status_code >= 500:
            code, retryable = "provider_unavailable", True
        else:
            code, retryable = "provider_request_rejected", False
        return OpenAIProviderError(stage=stage, code=code, retryable=retryable)
    return OpenAIProviderError(stage=stage, code="provider_error", retryable=False)


def _sdk_error_code(error: openai.OpenAIError) -> str | None:
    direct = getattr(error, "code", None)
    if isinstance(direct, str):
        return direct
    body = getattr(error, "body", None)
    if not isinstance(body, dict):
        return None
    nested = body.get("error") if isinstance(body.get("error"), dict) else body
    for key in ("code", "type"):
        value = nested.get(key)
        if isinstance(value, str):
            return value
    return None


class OpenAIStructuredGenerator:
    """Generate one pipeline stage while preserving a strict Pydantic contract."""

    provider_name = "openai"

    def __init__(self, model_name: str | None = None) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            raise OpenAIProviderError(
                stage="configuration",
                code="missing_api_key",
                retryable=False,
            )
        self.model_name = model_name or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
        self._client = OpenAI(
            timeout=REQUEST_TIMEOUT_SECONDS,
            max_retries=SDK_MAX_RETRIES,
        )
        self._usage_totals = {"input_tokens": 0, "output_tokens": 0}

    @property
    def usage_totals(self) -> dict[str, int]:
        """Return aggregate non-secret usage for evaluation and observability."""

        return dict(self._usage_totals)

    def generate(
        self,
        *,
        prompt_name: str,
        payload: dict[str, Any],
        response_model: type[ModelT],
        stage: str,
    ) -> ModelT:
        safe_error: OpenAIProviderError | None = None
        try:
            response = self._client.responses.parse(
                model=self.model_name,
                input=[
                    {"role": "system", "content": load_prompt(prompt_name)},
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    },
                ],
                text_format=response_model,
                reasoning={"effort": "low"},
                store=False,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )
        except openai.OpenAIError as error:
            safe_error = _translate_sdk_error(stage, error)
        except (ValidationError, ValueError, TypeError):
            safe_error = OpenAIProviderError(
                stage=stage,
                code="provider_invalid_response",
                retryable=False,
            )
        except Exception:
            safe_error = OpenAIProviderError(
                stage=stage,
                code="provider_unexpected_error",
                retryable=False,
            )

        # Raise outside the handler so the SDK exception is not retained as
        # ``__context__`` on the safe public exception.
        if safe_error is not None:
            raise safe_error

        usage = getattr(response, "usage", None)
        if usage is not None:
            self._usage_totals["input_tokens"] += int(getattr(usage, "input_tokens", 0) or 0)
            self._usage_totals["output_tokens"] += int(getattr(usage, "output_tokens", 0) or 0)

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            code = "provider_refusal" if _contains_refusal(response) else "provider_no_output"
            raise OpenAIProviderError(stage=stage, code=code, retryable=False)
        if not isinstance(parsed, BaseModel) or not isinstance(parsed, response_model):
            raise OpenAIProviderError(
                stage=stage,
                code="provider_invalid_response",
                retryable=False,
            )
        return parsed


def _contains_refusal(response: Any) -> bool:
    """Detect a refusal without copying provider-authored text into an exception."""

    for item in getattr(response, "output", ()) or ():
        for content in getattr(item, "content", ()) or ():
            if getattr(content, "type", None) == "refusal":
                return True
    return False
