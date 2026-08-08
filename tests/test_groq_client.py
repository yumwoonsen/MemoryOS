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
from backend.models.v2_schemas import (
    CompactInterpretationDecisionV2,
    CompactMemoryProposalV2,
    MemoryProposalV2,
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

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakeClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.chat = SimpleNamespace(completions=responses)


class SequenceResponses(FakeResponses):
    def __init__(self, results: list[Any]) -> None:
        super().__init__()
        self.results = list(results)

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.results.pop(0)


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


def test_groq_request_is_backend_keyed_bounded_and_observable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-only-key")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    expected = ExampleOutput(message="grounded result")
    response = chat_response(expected, input_tokens=12, output_tokens=7)
    responses = FakeResponses(result=response)
    constructor_options = install_fake_client(monkeypatch, responses)

    generator = adapter.GroqStructuredGenerator()
    result = generator.generate(
        prompt_name="memory_prompt.txt",
        payload={"event_ids": ["event-1"]},
        response_model=ExampleOutput,
        stage="memory_discovery",
    )

    assert result == expected
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
    assert request["reasoning_effort"] == "low"
    assert request["temperature"] == 0
    assert "store" not in request
    assert request["max_completion_tokens"] == 2_000
    assert json.loads(request["messages"][1]["content"]) == {"event_ids": ["event-1"]}
    response_format = request["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "ExampleOutput"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == to_strict_json_schema(ExampleOutput)

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
            chat_response(baseline.memory, input_tokens=10, output_tokens=5),
            chat_response(
                PerspectiveSet(perspectives=baseline.player_perspectives),
                input_tokens=20,
                output_tokens=8,
            ),
            chat_response(baseline.next_chapter, input_tokens=30, output_tokens=12),
        ]
    )
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-only-key")
    install_fake_client(monkeypatch, responses)
    pipeline = MemoryPipeline(adapter.GroqStructuredGenerator())

    result = pipeline.generate(pack)

    assert result.status == PipelineStatusV11.READY
    assert [call["response_format"]["json_schema"]["name"] for call in responses.calls] == [
        "MemoryRecord",
        "PerspectiveSet",
        "NextChapter",
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
                httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
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
                        "POST", "https://api.groq.com/openai/v1/chat/completions"
                    ),
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
        (
            openai.APIStatusError(
                "sensitive provider detail",
                response=httpx.Response(
                    413,
                    request=httpx.Request(
                        "POST", "https://api.groq.com/openai/v1/chat/completions"
                    ),
                ),
                body={"error": {"code": "rate_limit_exceeded"}},
            ),
            "provider_rate_limited",
            True,
        ),
        (
            openai.BadRequestError(
                "sensitive provider detail",
                response=httpx.Response(
                    400,
                    request=httpx.Request(
                        "POST", "https://api.groq.com/openai/v1/chat/completions"
                    ),
                ),
                body={"detail": "sensitive provider detail"},
            ),
            "provider_request_rejected",
            False,
        ),
        (
            openai.BadRequestError(
                "sensitive provider detail",
                response=httpx.Response(
                    400,
                    request=httpx.Request(
                        "POST", "https://api.groq.com/openai/v1/chat/completions"
                    ),
                ),
                body={
                    "error": {
                        "code": "json_validate_failed",
                        "message": "failed_generation containing rejected private prose",
                    }
                },
            ),
            "provider_invalid_response",
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


@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        (chat_response("not valid json"), "provider_invalid_response"),
        (chat_response(None), "provider_no_output"),
        (chat_response(None, refusal="cannot comply"), "provider_refusal"),
        (chat_response("{}", finish_reason="length"), "provider_output_limit"),
    ],
)
def test_groq_chat_output_failures_are_safe_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    response: SimpleNamespace,
    expected_code: str,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-only-key")
    install_fake_client(monkeypatch, FakeResponses(result=response))
    generator = adapter.GroqStructuredGenerator()

    with pytest.raises(adapter.GroqProviderError) as raised:
        generator.generate(
            prompt_name="memory_prompt.txt",
            payload={"event_ids": ["event-1"]},
            response_model=ExampleOutput,
            stage="memory_discovery",
        )

    assert raised.value.code == expected_code
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_v2_interpretation_uses_compact_bounded_chat_output_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-only-key")
    responses = FakeResponses(result=chat_response(ExampleOutput(message="ok")))
    install_fake_client(monkeypatch, responses)
    generator = adapter.GroqStructuredGenerator()

    generator.generate(
        prompt_name="memory_prompt.txt",
        payload={"event_ids": ["event-1"]},
        response_model=ExampleOutput,
        stage="memory_interpretation",
    )

    assert responses.calls[0]["max_completion_tokens"] == 4_000


@pytest.mark.parametrize(
    "response_model", [MemoryRecord, PerspectiveSet, NextChapter, CompactMemoryProposalV2]
)
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


def test_quest_target_schema_does_not_overlap_integer_and_number() -> None:
    schema = to_strict_json_schema(NextChapter)
    target_options = schema["$defs"]["VerificationRule"]["properties"]["target"]["anyOf"]
    target_types = {option["type"] for option in target_options}

    assert target_types == {"string", "integer", "boolean", "array"}


def test_backend_derived_claim_schema_supports_integer_and_decimal_values() -> None:
    schema = to_strict_json_schema(MemoryProposalV2)
    options = schema["$defs"]["GroundedClaim"]["properties"]["value"]["anyOf"]
    value_types = {option["type"] for option in options}

    assert value_types == {"string", "integer", "number", "boolean", "array", "null"}


def test_compact_ai_schema_omits_backend_authoritative_fields() -> None:
    schema = to_strict_json_schema(CompactMemoryProposalV2)
    properties = schema["properties"]

    assert "selected_window_id" in properties
    assert {
        "selected_match_id",
        "selected_event_ids",
        "recipe",
        "verification",
        "assigned_player_id",
        "media_id",
    }.isdisjoint(properties)
    assert set(schema["$defs"]["CompactPerspectiveV2"]["properties"]) == {
        "player_id",
        "message",
        "evidence_ids",
    }
    assert set(schema["$defs"]["CompactSectionDraftV2"]["properties"]) == {
        "text",
        "evidence_ids",
    }
    assert "CompactClaimV2" not in schema["$defs"]
    assert "GroundedClaim" not in schema["$defs"]
    assert len(json.dumps(schema, separators=(",", ":")).encode("utf-8")) < 4_500


def test_v2_1_decision_schema_requires_generate_or_abstain_payload() -> None:
    schema = to_strict_json_schema(CompactInterpretationDecisionV2)

    assert set(schema["properties"]) == {
        "decision",
        "abstention_reason_code",
        "proposal",
    }
    assert set(schema["required"]) == set(schema["properties"])


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
