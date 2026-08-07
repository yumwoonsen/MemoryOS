"""Groq GPT-OSS adapter, schema, and observability tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel

import backend.services.groq_client as adapter
from backend.models.schemas import (
    MemoryPackV11,
    MemoryRecord,
    NextChapter,
    PerspectiveSet,
    PipelineStatusV11,
)
from backend.pipeline import MemoryPipeline

DATA_DIR = Path(__file__).resolve().parents[1] / "backend" / "data"


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


class SequenceResponses(FakeResponses):
    def __init__(self, results: list[Any]) -> None:
        super().__init__()
        self.results = list(results)

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.results.pop(0)


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


def test_groq_request_is_backend_keyed_bounded_and_observable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-only-key")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    expected = ExampleOutput(message="grounded result")
    response = SimpleNamespace(
        output_parsed=expected,
        output=[],
        usage=SimpleNamespace(input_tokens=12, output_tokens=7),
    )
    responses = FakeResponses(result=response)
    constructor_options = install_fake_client(monkeypatch, responses)

    generator = adapter.GroqStructuredGenerator()
    result = generator.generate(
        prompt_name="memory_prompt.txt",
        payload={"event_ids": ["event-1"]},
        response_model=ExampleOutput,
        stage="memory_discovery",
    )

    assert result is expected
    assert generator.provider_name == "groq"
    assert generator.model_name == "openai/gpt-oss-20b"
    assert constructor_options == {
        "api_key": "groq-test-only-key",
        "base_url": "https://api.groq.com/openai/v1",
        "timeout": 30.0,
        "max_retries": 2,
    }
    request = responses.calls[0]
    assert request["model"] == "openai/gpt-oss-20b"
    assert request["text_format"] is ExampleOutput
    assert request["reasoning"] == {"effort": "low"}
    assert "store" not in request  # Groq Responses explicitly does not support this field.
    assert request["max_output_tokens"] == 2_000
    assert json.loads(request["input"][1]["content"]) == {"event_ids": ["event-1"]}

    metrics = generator.observability
    assert metrics["provider"] == "groq"
    assert metrics["model"] == "openai/gpt-oss-20b"
    assert metrics["mode"] == "live_ai"
    assert metrics["totals"]["request_count"] == 1
    assert metrics["totals"]["input_tokens"] == 12
    assert metrics["totals"]["output_tokens"] == 7
    assert metrics["totals"]["configured_max_retries"] == 2
    assert metrics["stages"][0]["stage"] == "memory_discovery"
    assert metrics["stages"][0]["status"] == "succeeded"
    assert metrics["stages"][0]["latency_ms"] >= 0
    assert "retry_count" not in metrics["stages"][0]


def test_missing_groq_key_fails_safely_without_using_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")

    with pytest.raises(adapter.GroqProviderError) as raised:
        adapter.GroqStructuredGenerator()

    assert raised.value.as_dict() == {
        "stage": "configuration",
        "code": "missing_api_key",
        "retryable": False,
    }
    assert "OPENAI_API_KEY" not in str(raised.value)
    assert "must-not-be-used" not in str(raised.value)


def test_one_groq_generator_drives_all_three_model_capable_agents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.loads((DATA_DIR / "historical_memory_packs.json").read_text(encoding="utf-8"))[0]
    pack = MemoryPackV11.model_validate(payload)
    baseline = MemoryPipeline().generate(pack)
    assert baseline.memory is not None
    assert baseline.next_chapter is not None
    responses = SequenceResponses(
        [
            SimpleNamespace(
                output_parsed=baseline.memory,
                output=[],
                usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            ),
            SimpleNamespace(
                output_parsed=PerspectiveSet(perspectives=baseline.player_perspectives),
                output=[],
                usage=SimpleNamespace(input_tokens=20, output_tokens=8),
            ),
            SimpleNamespace(
                output_parsed=baseline.next_chapter,
                output=[],
                usage=SimpleNamespace(input_tokens=30, output_tokens=12),
            ),
        ]
    )
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-only-key")
    install_fake_client(monkeypatch, responses)
    pipeline = MemoryPipeline(adapter.GroqStructuredGenerator())

    result = pipeline.generate(pack)

    assert result.status == PipelineStatusV11.READY
    assert [call["text_format"] for call in responses.calls] == [
        MemoryRecord,
        PerspectiveSet,
        NextChapter,
    ]
    assert [item["stage"] for item in result.metadata["observability"]["stages"]] == [
        "memory_discovery",
        "perspectives",
        "quest_generation",
    ]
    assert result.metadata["usage"] == {"input_tokens": 60, "output_tokens": 25}


@pytest.mark.parametrize(
    ("sdk_error", "expected_code", "retryable"),
    [
        (
            openai.APITimeoutError(
                httpx.Request("POST", "https://api.groq.com/openai/v1/responses")
            ),
            "provider_timeout",
            True,
        ),
        (
            openai.RateLimitError(
                "sensitive provider detail",
                response=httpx.Response(
                    429,
                    request=httpx.Request("POST", "https://api.groq.com/openai/v1/responses"),
                ),
                body={"detail": "sensitive provider detail"},
            ),
            "provider_rate_limited",
            True,
        ),
        (
            openai.AuthenticationError(
                "sensitive provider detail",
                response=httpx.Response(
                    401,
                    request=httpx.Request("POST", "https://api.groq.com/openai/v1/responses"),
                ),
                body={"detail": "sensitive provider detail"},
            ),
            "provider_authentication_failed",
            False,
        ),
    ],
)
def test_groq_sdk_errors_map_to_safe_stable_codes(
    monkeypatch: pytest.MonkeyPatch,
    sdk_error: Exception,
    expected_code: str,
    retryable: bool,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-only-key")
    install_fake_client(monkeypatch, FakeResponses(error=sdk_error))
    generator = adapter.GroqStructuredGenerator()

    with pytest.raises(adapter.GroqProviderError) as raised:
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


@pytest.mark.parametrize("response_model", [MemoryRecord, PerspectiveSet, NextChapter])
def test_all_agent_contracts_convert_to_groq_compatible_strict_schema(
    response_model: type[BaseModel],
) -> None:
    schema = to_strict_json_schema(response_model)

    def assert_strict(node: object) -> None:
        if isinstance(node, dict):
            assert "default" not in node
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                properties = node.get("properties", {})
                assert set(node.get("required", [])) == set(properties)
            for value in node.values():
                assert_strict(value)
        elif isinstance(node, list):
            for value in node:
                assert_strict(value)

    assert_strict(schema)


@pytest.mark.skipif(
    os.getenv("MEMORYOS_RUN_GROQ_LIVE") != "1" or not os.getenv("GROQ_API_KEY"),
    reason="set MEMORYOS_RUN_GROQ_LIVE=1 and GROQ_API_KEY for the opt-in live smoke",
)
def test_live_groq_pipeline_parses_all_three_agent_contracts() -> None:
    payload = json.loads((DATA_DIR / "historical_memory_packs.json").read_text(encoding="utf-8"))[0]
    pack = MemoryPackV11.model_validate(payload)
    pipeline = MemoryPipeline(adapter.GroqStructuredGenerator())

    result = pipeline.generate(pack)

    assert result.status == PipelineStatusV11.READY
    assert [item["stage"] for item in pipeline.observability["stages"]] == [
        "memory_discovery",
        "perspectives",
        "quest_generation",
    ]
