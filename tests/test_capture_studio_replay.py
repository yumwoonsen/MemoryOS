"""Pure replay-capture validation and atomic manifest tests (no network/provider)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest

import backend.capture_studio_replay as capture_module
from backend.capture_studio_replay import (
    ReplayCaptureError,
    ReplayCaptureProviderFailure,
    StudioReplayEnvelopeV1,
    StudioReplayManifestV1,
    build_replay_envelope,
    load_manifest,
    select_catalog_scenario,
    update_manifest,
    validate_interpretation_for_capture,
    write_manifest_atomically,
)
from backend.models.v2_schemas import (
    CompactInterpretationDecisionV2,
    InterpretationAbstentionReasonV2,
    InterpretationDecisionKindV2,
)
from backend.models.v2_studio_schemas import StudioScenarioInterpretationV2
from backend.services.v2_interpreter import MemoryInterpreterV2
from backend.services.v2_preparation import TelemetryPreparerV2
from backend.services.v2_studio_scenarios import studio_scenario_registry_v2
from backend.v2_pipeline import MemoryInterpretationPipelineV2

CAPTURED_AT = datetime(2026, 8, 9, 4, 5, 6, tzinfo=UTC)


class _DecisionGenerator:
    provider_name = "test-live"
    model_name = "typed-v2.1"

    def __init__(self, decision: CompactInterpretationDecisionV2) -> None:
        self.decision = decision

    @property
    def observability(self) -> dict[str, object]:
        return {"not_copied_to_replay": True}

    def generate(self, **_: object) -> CompactInterpretationDecisionV2:
        return self.decision


def _interpretation(scenario_id: str) -> StudioScenarioInterpretationV2:
    registered = studio_scenario_registry_v2.get(scenario_id)
    if registered.descriptor.expected_status == "not_generated":
        decision = CompactInterpretationDecisionV2(
            decision=InterpretationDecisionKindV2.ABSTAIN,
            abstention_reason_code=(InterpretationAbstentionReasonV2.NO_MEANINGFUL_EPISODE),
            proposal=None,
        )
    else:
        prepared = TelemetryPreparerV2().prepare(registered.telemetry)
        compact = MemoryInterpreterV2().demo_compact_proposal(prepared)
        decision = CompactInterpretationDecisionV2(
            decision=InterpretationDecisionKindV2.GENERATE,
            abstention_reason_code=None,
            proposal=compact,
        )
    result = MemoryInterpretationPipelineV2(_DecisionGenerator(decision)).interpret_delivery(
        registered.telemetry
    )
    return StudioScenarioInterpretationV2(
        scenario=registered.descriptor,
        result=result,
    )


def _replay(scenario_id: str) -> StudioReplayEnvelopeV1:
    interpretation = _interpretation(scenario_id)
    return build_replay_envelope(
        interpretation.scenario,
        interpretation,
        captured_at=CAPTURED_AT,
    )


def test_pending_capture_replaces_live_authorization_and_strips_runtime_metadata() -> None:
    interpretation = _interpretation("rescue-role-reversal")
    original_delivery_id = interpretation.result.delivery_id

    replay = build_replay_envelope(
        interpretation.scenario,
        interpretation,
        captured_at=CAPTURED_AT,
    )

    assert replay.replay_schema_version == "1.0"
    assert replay.provenance.provider == "test-live"
    assert replay.provenance.model == "typed-v2.1"
    assert replay.provenance.result_schema_version == "2.1"
    assert replay.provenance.captured_at == "2026-08-09T04:05:06Z"
    assert replay.result.delivery_id == (
        "replay-only:non-authorizing:rescue-role-reversal:"
        f"{interpretation.scenario.fixture_sha256[:12]}"
    )
    assert replay.result.delivery_id != original_delivery_id
    assert interpretation.result.delivery_id == original_delivery_id
    assert replay.result.metadata == {
        "provider": "test-live",
        "model": "typed-v2.1",
        "mode": "saved_replay",
        "prompt_version": interpretation.result.metadata["prompt_version"],
        "content_origin": "saved_live_replay",
        "grounded_render": False,
        "narrative_fallback": False,
    }


def test_not_generated_capture_keeps_no_player_content_provenance() -> None:
    replay = _replay("ordinary-sparse-telemetry")

    assert replay.result.status == "not_generated"
    assert replay.result.delivery_id is None
    assert replay.result.memory is None
    assert replay.result.next_chapter is None
    assert replay.result.metadata["mode"] == "saved_replay"
    assert replay.result.metadata["content_origin"] == "no_player_content"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("descriptor", "scenario_descriptor_mismatch"),
        ("status", "unexpected_result_status"),
        ("family", "unexpected_mission_family"),
        ("origin", "invalid_content_origin"),
        ("mode", "result_not_live_ai"),
    ],
)
def test_capture_rejects_mismatched_or_non_live_results(
    mutation: str,
    expected_code: str,
) -> None:
    interpretation = _interpretation("rescue-role-reversal")
    descriptor = interpretation.scenario

    if mutation == "descriptor":
        replacement = studio_scenario_registry_v2.get("repeated-near-miss").descriptor
        interpretation = interpretation.model_copy(update={"scenario": replacement})
    elif mutation == "status":
        descriptor = descriptor.model_copy(update={"expected_status": "not_generated"})
        interpretation = interpretation.model_copy(update={"scenario": descriptor})
    elif mutation == "family":
        descriptor = descriptor.model_copy(update={"expected_mission_family": "redemption"})
        interpretation = interpretation.model_copy(update={"scenario": descriptor})
    else:
        metadata = dict(interpretation.result.metadata)
        metadata[mutation if mutation == "mode" else "content_origin"] = (
            "deterministic" if mutation == "mode" else "deterministic_studio_sample"
        )
        result = interpretation.result.model_copy(update={"metadata": metadata})
        interpretation = interpretation.model_copy(update={"result": result})

    with pytest.raises(ReplayCaptureError) as captured:
        validate_interpretation_for_capture(descriptor, interpretation)
    assert captured.value.code == expected_code


def test_catalog_selection_fails_safely_for_unknown_id() -> None:
    catalog = studio_scenario_registry_v2.catalog()

    with pytest.raises(ReplayCaptureError) as captured:
        select_catalog_scenario(catalog, "not-registered")

    assert captured.value.code == "unknown_scenario"


def test_manifest_replaces_one_entry_and_writes_canonical_order(tmp_path: Path) -> None:
    rescue = _replay("rescue-role-reversal")
    near_miss = _replay("repeated-near-miss")
    ordinary = _replay("ordinary-sparse-telemetry")
    old_rescue = rescue.model_copy(
        update={
            "provenance": rescue.provenance.model_copy(
                update={"captured_at": "2026-08-08T01:02:03Z"}
            )
        }
    )
    shuffled = StudioReplayManifestV1(replays=[ordinary, old_rescue, near_miss])

    updated = update_manifest(shuffled, rescue)

    assert [item.scenario.scenario_id.value for item in updated.replays] == [
        "rescue-role-reversal",
        "repeated-near-miss",
        "ordinary-sparse-telemetry",
    ]
    assert updated.replays[0] == rescue
    assert updated.replays[1] == near_miss
    assert updated.replays[2] == ordinary

    manifest_path = tmp_path / "manifest.json"
    write_manifest_atomically(manifest_path, updated)
    loaded = load_manifest(manifest_path)
    assert loaded == updated
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["schema_version"] == "1.0"
    assert list(tmp_path.glob(".manifest.json.*.tmp")) == []


def test_invalid_existing_manifest_fails_closed(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text('{"schema_version":"1.0","replays":[{}]}', encoding="utf-8")

    with pytest.raises(ReplayCaptureError) as captured:
        load_manifest(manifest_path)

    assert captured.value.code == "invalid_existing_manifest"


class _BytesResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> _BytesResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, _: int) -> bytes:
        return self.payload


def _provider_http_error(payload: dict[str, object]) -> HTTPError:
    return HTTPError(
        url="http://127.0.0.1:8000/v2/studio/scenarios/rescue-role-reversal/interpret",
        code=503,
        msg="Service Unavailable",
        hdrs=None,
        fp=BytesIO(json.dumps(payload).encode("utf-8")),
    )


def test_cli_reports_only_validated_provider_failure_and_never_retries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "SENSITIVE_SENTINEL_MUST_NOT_APPEAR"
    catalog_bytes = studio_scenario_registry_v2.catalog().model_dump_json().encode("utf-8")
    requests: list[str] = []

    def fake_urlopen(request: object, **_: object) -> _BytesResponse:
        requests.append(str(getattr(request, "full_url", "")))
        if len(requests) == 1:
            return _BytesResponse(catalog_bytes)
        raise _provider_http_error(
            {
                "stage": "memory_interpretation_correction",
                "code": "provider_rate_limited",
                "retryable": True,
                "message": f"Provider raw prose containing {secret}",
            }
        )

    monkeypatch.setattr(capture_module, "urlopen", fake_urlopen)
    manifest_path = tmp_path / "manifest.json"

    exit_code = capture_module.main(
        [
            "--scenario",
            "rescue-role-reversal",
            "--manifest",
            str(manifest_path),
        ]
    )

    output = capsys.readouterr()
    assert exit_code == 1
    assert output.out == ""
    assert output.err == (
        "scenario=rescue-role-reversal status=capture_failed http_status=503 "
        "stage=memory_interpretation_correction code=provider_rate_limited "
        "retryable=true\n"
    )
    assert secret not in output.err
    assert len(requests) == 2
    assert not manifest_path.exists()


@pytest.mark.parametrize(
    "provider_body",
    [
        {
            "stage": "memory_interpretation",
            "code": "AQ.secret-key-in-code",
            "retryable": False,
            "message": "raw provider prose",
        },
        {
            "stage": "memory_interpretation",
            "code": "provider_rate_limited",
            "retryable": False,
            "message": "retryability mismatch",
        },
    ],
)
def test_cli_reduces_unvalidated_provider_body_to_internal_error_code(
    provider_body: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    catalog_bytes = studio_scenario_registry_v2.catalog().model_dump_json().encode("utf-8")
    request_count = 0

    def fake_urlopen(_: object, **__: object) -> _BytesResponse:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return _BytesResponse(catalog_bytes)
        raise _provider_http_error(provider_body)

    monkeypatch.setattr(capture_module, "urlopen", fake_urlopen)

    exit_code = capture_module.main(
        [
            "--scenario",
            "rescue-role-reversal",
            "--manifest",
            str(tmp_path / "manifest.json"),
        ]
    )

    output = capsys.readouterr()
    assert exit_code == 1
    assert output.out == ""
    assert output.err == (
        "scenario=rescue-role-reversal status=capture_failed "
        "error_code=invalid_provider_error_response\n"
    )
    assert "secret" not in output.err
    assert "raw provider prose" not in output.err
    assert request_count == 2


def test_cli_unexpected_failure_never_prints_exception_or_user_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "AQ.secret-in-exception"

    def fail_capture(*_: object, **__: object) -> StudioReplayEnvelopeV1:
        raise RuntimeError(secret)

    monkeypatch.setattr(capture_module, "capture_one_scenario", fail_capture)
    manifest_path = tmp_path / f"{secret}.json"

    exit_code = capture_module.main(
        [
            "--scenario",
            "rescue-role-reversal",
            "--manifest",
            str(manifest_path),
        ]
    )

    output = capsys.readouterr()
    assert exit_code == 1
    assert output.out == ""
    assert output.err == (
        "scenario=rescue-role-reversal status=capture_failed error_code=unexpected_capture_error\n"
    )
    assert secret not in output.err
    assert str(manifest_path) not in output.err


def test_provider_failure_type_is_not_constructed_from_unvalidated_fields() -> None:
    with pytest.raises(ReplayCaptureError) as captured:
        capture_module._validated_provider_failure(
            http_status=503,
            payload=json.dumps(
                {
                    "stage": "memory_interpretation",
                    "code": "provider_timeout",
                    "retryable": False,
                    "message": "wrong retryability",
                }
            ).encode("utf-8"),
        )

    assert captured.value.code == "invalid_provider_error_response"

    failure = capture_module._validated_provider_failure(
        http_status=503,
        payload=json.dumps(
            {
                "stage": "memory_interpretation",
                "code": "provider_timeout",
                "retryable": True,
                "message": "safe typed provider failure",
            }
        ).encode("utf-8"),
    )
    assert isinstance(failure, ReplayCaptureProviderFailure)
    assert failure.http_status == 503
    assert failure.stage == "memory_interpretation"
    assert failure.code == "provider_timeout"
    assert failure.retryable is True
