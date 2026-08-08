"""Safe CLI coverage for the opt-in v2.1 benchmark."""

from __future__ import annotations

from pathlib import Path

import pytest

import backend.evaluate_v2 as evaluate_v2_module
from backend.evaluate_v2 import (
    DEFAULT_MANIFEST,
    BenchmarkConfigurationError,
    load_manifest,
    parse_args,
    run_benchmark,
)
from backend.v2_pipeline import MemoryInterpretationPipelineV2


def test_default_cli_is_deterministic_and_live_calls_require_opt_in() -> None:
    args = parse_args([])

    assert args.provider == "deterministic"
    assert args.allow_live_api is False
    with pytest.raises(BenchmarkConfigurationError, match="explicit --allow-live-api"):
        run_benchmark(provider="groq", manifest_path=DEFAULT_MANIFEST)


def test_manifest_contains_labelled_counterfactual_and_abstention() -> None:
    manifest = load_manifest(DEFAULT_MANIFEST)
    cases = {case.case_id: case for case in manifest.cases}

    assert cases["rescue-role-reversal"].expected_mission_family == "role_reversal"
    counterfactual = cases["rescue-counterfactual-no-revive"]
    assert counterfactual.expected_mission_family == "reunion"
    assert counterfactual.forbidden_offered_mission_families == ["role_reversal"]
    assert cases["repeated-near-miss"].expected_mission_family == "redemption"
    assert cases["ordinary-sparse-telemetry"].expected_status == "not_generated"


def test_deterministic_benchmark_reports_safe_per_run_fields() -> None:
    report = run_benchmark(
        provider="deterministic",
        manifest_path=Path(DEFAULT_MANIFEST),
        repeats=1,
    )

    assert report["provider"] == "deterministic"
    assert report["live_api_enabled"] is False
    assert len(report["models"]) == 1
    model_report = report["models"][0]
    assert len(model_report["runs"]) == 4
    by_case = {run["case_id"]: run for run in model_report["runs"]}
    assert by_case["rescue-role-reversal"]["selected_family"] == "role_reversal"
    assert "role_reversal" not in by_case["rescue-counterfactual-no-revive"]["offered_families"]
    assert by_case["repeated-near-miss"]["selected_family"] == "redemption"
    assert by_case["ordinary-sparse-telemetry"]["labels_passed"] is False
    summary = model_report["summary"]
    assert summary["mission_family_labels_evaluated"] == 3
    assert summary["mission_family_accuracy"] == 1
    assert summary["cross_fixture_family_variation_rate"] == 1
    assert summary["typed_abstention_accuracy"] == 0
    for run in model_report["runs"]:
        assert set(run) == {
            "case_id",
            "repeat",
            "status",
            "offered_families",
            "selected_family",
            "correction_attempted",
            "validation_passed",
            "validation_issue_codes",
            "latency_ms",
            "provider_usage",
            "labels_passed",
        }
        assert set(run["provider_usage"]) == {
            "request_count",
            "input_tokens",
            "output_tokens",
            "provider_latency_ms",
        }


def test_repeated_model_matrix_can_be_exercised_without_network(monkeypatch) -> None:
    class NoNetworkPipeline(MemoryInterpretationPipelineV2):
        @property
        def model_name(self) -> str:
            return evaluate_v2_module.os.environ["GROQ_MODEL"]

        def validate_provider_configuration(self) -> None:
            return None

    monkeypatch.setattr(
        evaluate_v2_module,
        "build_v2_pipeline",
        lambda _provider: NoNetworkPipeline(),
    )

    report = run_benchmark(
        provider="groq",
        manifest_path=DEFAULT_MANIFEST,
        models=["model-a", "model-b"],
        repeats=2,
        allow_live_api=True,
    )

    assert [item["model"] for item in report["models"]] == ["model-a", "model-b"]
    assert all(len(item["runs"]) == 8 for item in report["models"])
