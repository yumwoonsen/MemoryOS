"""Gemini structured-output adapter and observability tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest
from pydantic import BaseModel, Field

import backend.services.gemini_client as adapter
from backend.models.v2_provider_schemas import ProviderInterpretationDecisionV2
from backend.models.v2_schemas import RawTelemetryBatchV2
from backend.services.v2_interpreter import MemoryInterpreterV2
from backend.services.v2_preparation import TelemetryPreparerV2
from backend.v2_pipeline import MemoryInterpretationPipelineV2, build_v2_pipeline

DATA_DIR = Path(__file__).resolve().parents[1] / "backend" / "data"


class ExampleOutput(BaseModel):
    message: str = Field(min_length=1, max_length=80)


class FakeResponses:
    def __init__(self, *, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakeClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.chat = SimpleNamespace(completions=responses)


def chat_response(
    output: BaseModel | str | None,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    refusal: str | None = None,
    finish_reason: str = "stop",
) -> SimpleNamespace:
    content = output.model_dump_json() if isinstance(output, BaseModel) else output
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, refusal=refusal),
                finish_reason=finish_reason,
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        ),
    )


def install_fake_client(
    monkeypatch: pytest.MonkeyPatch,
    responses: FakeResponses,
) -> dict[str, Any]:
    constructor_options: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> FakeClient:
        constructor_options.update(kwargs)
        return FakeClient(responses)

    monkeypatch.setattr(adapter, "OpenAI", fake_openai)
    return constructor_options


def test_gemini_request_is_backend_keyed_structured_and_observable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-only-key")
    monkeypatch.setenv("GROQ_API_KEY", "must-not-be-used")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    response = chat_response(
        ExampleOutput(message="grounded result"),
        input_tokens=14,
        output_tokens=9,
    )
    responses = FakeResponses(result=response)
    constructor_options = install_fake_client(monkeypatch, responses)

    generator = adapter.GeminiStructuredGenerator()
    result = generator.generate(
        prompt_name="memory_prompt.txt",
        payload={"event_ids": ["event-1"]},
        response_model=ExampleOutput,
        stage="memory_discovery",
    )

    assert result == ExampleOutput(message="grounded result")
    assert generator.provider_name == "gemini"
    assert generator.model_name == "gemini-3.6-flash"
    assert constructor_options == {
        "api_key": "gemini-test-only-key",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "timeout": 60.0,
        "max_retries": 0,
    }
    request = responses.calls[0]
    assert request["model"] == "gemini-3.6-flash"
    assert request["reasoning_effort"] == "low"
    assert "temperature" not in request
    assert request["max_completion_tokens"] == 2_000
    assert json.loads(request["messages"][1]["content"]) == {"event_ids": ["event-1"]}
    response_format = request["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "ExampleOutput"
    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert "minLength" not in schema["properties"]["message"]
    assert "maxLength" not in schema["properties"]["message"]

    metrics = generator.observability
    assert metrics["provider"] == "gemini"
    assert metrics["model"] == "gemini-3.6-flash"
    assert metrics["mode"] == "live_ai"
    assert metrics["totals"]["request_count"] == 1
    assert metrics["totals"]["input_tokens"] == 14
    assert metrics["totals"]["output_tokens"] == 9
    assert metrics["stages"][0]["status"] == "succeeded"


def test_missing_gemini_key_fails_safely_without_using_other_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", "must-not-be-used")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")

    with pytest.raises(adapter.GeminiProviderError) as raised:
        adapter.GeminiStructuredGenerator()

    assert raised.value.as_dict() == {
        "stage": "configuration",
        "code": "missing_api_key",
        "retryable": False,
    }
    assert "must-not-be-used" not in str(raised.value)


def test_v2_pipeline_routes_normalized_gemini_provider() -> None:
    pipeline = build_v2_pipeline("  GeMiNi  ")

    assert pipeline.provider_name == "gemini"
    assert pipeline.model_name == "gemini-3.6-flash"
    assert pipeline.execution_mode == "live_ai"
    assert pipeline.interpreter.observability["totals"]["configured_max_retries"] == 0


def test_full_provider_v2_contract_passes_through_gemini_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = RawTelemetryBatchV2.model_validate_json(
        (DATA_DIR / "raw_telemetry_v2.json").read_text(encoding="utf-8")
    )
    prepared = TelemetryPreparerV2().prepare(batch)
    decision = MemoryInterpreterV2().demo_provider_decision(prepared)
    responses = FakeResponses(result=chat_response(decision, input_tokens=1200, output_tokens=900))
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-only-key")
    install_fake_client(monkeypatch, responses)

    result = MemoryInterpretationPipelineV2(adapter.GeminiStructuredGenerator()).interpret_delivery(
        batch
    )

    assert result.status == "pending_player_decision"
    assert len(result.player_perspectives) == 4
    assert result.next_chapter is not None
    assert result.next_chapter.family == "role_reversal"
    assert len(result.next_chapter.objectives) == 5
    assert sum(not objective.required for objective in result.next_chapter.objectives) == 1
    assert responses.calls[0]["response_format"]["json_schema"]["name"] == (
        ProviderInterpretationDecisionV2.__name__
    )


@pytest.mark.parametrize(
    ("sdk_error", "expected_code", "retryable"),
    [
        (
            openai.APITimeoutError(
                httpx.Request(
                    "POST",
                    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                )
            ),
            "provider_timeout",
            True,
        ),
        (
            openai.RateLimitError(
                "sensitive provider detail",
                response=httpx.Response(
                    429,
                    request=httpx.Request(
                        "POST",
                        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                    ),
                ),
                body={"error": {"status": "RESOURCE_EXHAUSTED"}},
            ),
            "provider_rate_limited",
            True,
        ),
        (
            openai.AuthenticationError(
                "sensitive provider detail",
                response=httpx.Response(
                    401,
                    request=httpx.Request(
                        "POST",
                        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                    ),
                ),
                body={"detail": "sensitive provider detail"},
            ),
            "provider_authentication_failed",
            False,
        ),
    ],
)
def test_gemini_sdk_errors_map_to_safe_stable_codes(
    monkeypatch: pytest.MonkeyPatch,
    sdk_error: Exception,
    expected_code: str,
    retryable: bool,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-only-key")
    install_fake_client(monkeypatch, FakeResponses(error=sdk_error))
    generator = adapter.GeminiStructuredGenerator()

    with pytest.raises(adapter.GeminiProviderError) as raised:
        generator.generate(
            prompt_name="memory_prompt.txt",
            payload={"event_ids": ["event-1"]},
            response_model=ExampleOutput,
            stage="memory_discovery",
        )

    assert raised.value.as_dict() == {
        "stage": "memory_discovery",
        "code": expected_code,
        "retryable": retryable,
    }
    assert "sensitive provider detail" not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    assert generator.observability["stages"][0]["status"] == "failed"


@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        (chat_response("not valid json"), "provider_invalid_response"),
        (chat_response(None), "provider_no_output"),
        (chat_response(None, refusal="cannot comply"), "provider_refusal"),
        (chat_response("{}", finish_reason="length"), "provider_output_limit"),
    ],
)
def test_gemini_output_failures_are_safe_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    response: SimpleNamespace,
    expected_code: str,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-only-key")
    install_fake_client(monkeypatch, FakeResponses(result=response))
    generator = adapter.GeminiStructuredGenerator()

    with pytest.raises(adapter.GeminiProviderError) as raised:
        generator.generate(
            prompt_name="memory_prompt.txt",
            payload={"event_ids": ["event-1"]},
            response_model=ExampleOutput,
            stage="memory_discovery",
        )

    assert raised.value.code == expected_code
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_v2_output_budget_is_bounded_and_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-only-key")
    monkeypatch.setenv("GEMINI_V2_MAX_OUTPUT_TOKENS", "5000")
    responses = FakeResponses(result=chat_response(ExampleOutput(message="ok")))
    install_fake_client(monkeypatch, responses)
    generator = adapter.GeminiStructuredGenerator()

    generator.generate(
        prompt_name="memory_prompt.txt",
        payload={"event_ids": ["event-1"]},
        response_model=ExampleOutput,
        stage="memory_interpretation",
    )

    assert responses.calls[0]["max_completion_tokens"] == 5_000


@pytest.mark.parametrize("value", ["999", "16001", "not-a-number"])
def test_invalid_v2_output_budget_fails_configuration(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-only-key")
    monkeypatch.setenv("GEMINI_V2_MAX_OUTPUT_TOKENS", value)

    with pytest.raises(adapter.GeminiProviderError) as raised:
        adapter.GeminiStructuredGenerator()

    assert raised.value.code == "invalid_output_token_limit"
