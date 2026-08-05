"""Focused tests for the bounded OpenAI Responses API adapter."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest
from pydantic import BaseModel

import backend.services.openai_client as adapter


class ExampleOutput(BaseModel):
    message: str


class FakeResponses:
    def __init__(self, *, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakeClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses


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


def test_structured_request_is_bounded_and_not_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    expected = ExampleOutput(message="grounded result")
    responses = FakeResponses(result=SimpleNamespace(output_parsed=expected, output=[]))
    constructor_options = install_fake_client(monkeypatch, responses)

    generator = adapter.OpenAIStructuredGenerator()
    result = generator.generate(
        prompt_name="memory_prompt.txt",
        payload={"event_ids": ["event-1"]},
        response_model=ExampleOutput,
        stage="memory_discovery",
    )

    assert result is expected
    assert generator.model_name == "gpt-5.6-luna"
    assert constructor_options == {"timeout": 30.0, "max_retries": 2}
    assert len(responses.calls) == 1
    request = responses.calls[0]
    assert request["model"] == "gpt-5.6-luna"
    assert request["text_format"] is ExampleOutput
    assert request["reasoning"] == {"effort": "low"}
    assert request["store"] is False
    assert request["max_output_tokens"] == 2_000
    assert json.loads(request["input"][1]["content"]) == {"event_ids": ["event-1"]}


def test_missing_key_raises_safe_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(adapter.OpenAIProviderError) as raised:
        adapter.OpenAIStructuredGenerator()

    assert raised.value.as_dict() == {
        "stage": "configuration",
        "code": "missing_api_key",
        "retryable": False,
    }
    assert "OPENAI_API_KEY" not in str(raised.value)


@pytest.mark.parametrize(
    ("sdk_error", "expected_code", "retryable"),
    [
        (
            openai.APITimeoutError(httpx.Request("POST", "https://api.openai.com/v1/responses")),
            "provider_timeout",
            True,
        ),
        (
            openai.RateLimitError(
                "sensitive provider detail",
                response=httpx.Response(
                    429,
                    request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                ),
                body={"detail": "sensitive provider detail"},
            ),
            "provider_rate_limited",
            True,
        ),
        (
            openai.RateLimitError(
                "sensitive provider detail",
                response=httpx.Response(
                    429,
                    request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                ),
                body={"code": "insufficient_quota"},
            ),
            "provider_quota_exhausted",
            False,
        ),
        (
            openai.AuthenticationError(
                "sensitive provider detail",
                response=httpx.Response(
                    401,
                    request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                ),
                body={"detail": "sensitive provider detail"},
            ),
            "provider_authentication_failed",
            False,
        ),
        (
            openai.InternalServerError(
                "sensitive provider detail",
                response=httpx.Response(
                    500,
                    request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                ),
                body={"detail": "sensitive provider detail"},
            ),
            "provider_unavailable",
            True,
        ),
    ],
)
def test_sdk_errors_are_translated_without_provider_details(
    monkeypatch: pytest.MonkeyPatch,
    sdk_error: Exception,
    expected_code: str,
    retryable: bool,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    responses = FakeResponses(error=sdk_error)
    install_fake_client(monkeypatch, responses)
    generator = adapter.OpenAIStructuredGenerator()

    with pytest.raises(adapter.OpenAIProviderError) as raised:
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


def test_refusal_is_reported_without_refusal_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    refusal = SimpleNamespace(type="refusal", refusal="sensitive refusal text")
    response = SimpleNamespace(
        output_parsed=None,
        output=[SimpleNamespace(content=[refusal])],
    )
    install_fake_client(monkeypatch, FakeResponses(result=response))
    generator = adapter.OpenAIStructuredGenerator()

    with pytest.raises(adapter.OpenAIProviderError) as raised:
        generator.generate(
            prompt_name="memory_prompt.txt",
            payload={"event_ids": ["event-1"]},
            response_model=ExampleOutput,
            stage="memory_discovery",
        )

    assert raised.value.code == "provider_refusal"
    assert raised.value.retryable is False
    assert "sensitive refusal text" not in str(raised.value)


def test_missing_output_parsed_is_reported_as_safe_no_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    response = SimpleNamespace(output=[])
    install_fake_client(monkeypatch, FakeResponses(result=response))
    generator = adapter.OpenAIStructuredGenerator()

    with pytest.raises(adapter.OpenAIProviderError) as raised:
        generator.generate(
            prompt_name="memory_prompt.txt",
            payload={"event_ids": ["event-1"]},
            response_model=ExampleOutput,
            stage="memory_discovery",
        )

    assert raised.value.as_dict() == {
        "stage": "memory_discovery",
        "code": "provider_no_output",
        "retryable": False,
    }


def test_wrong_parsed_model_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")

    class WrongOutput(BaseModel):
        value: int

    response = SimpleNamespace(output_parsed=WrongOutput(value=1), output=[])
    install_fake_client(monkeypatch, FakeResponses(result=response))
    generator = adapter.OpenAIStructuredGenerator()

    with pytest.raises(adapter.OpenAIProviderError) as raised:
        generator.generate(
            prompt_name="memory_prompt.txt",
            payload={"event_ids": ["event-1"]},
            response_model=ExampleOutput,
            stage="memory_discovery",
        )

    assert raised.value.code == "provider_invalid_response"
    assert raised.value.retryable is False
