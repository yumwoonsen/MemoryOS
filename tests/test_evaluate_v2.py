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
    with pytest.raises(BenchmarkConfigurationError, match="explicit --allow-live-api"):
        run_benchmark(provider="gemini", manifest_path=DEFAULT_MANIFEST)


def test_gemini_live_benchmark_rejects_a_non_demo_manifest(tmp_path: Path) -> None:
    external_manifest = tmp_path / "manifest.json"

    with pytest.raises(BenchmarkConfigurationError, match="committed synthetic demo manifest"):
        run_benchmark(
            provider="gemini",
            manifest_path=external_manifest,
            allow_live_api=True,
        )


def test_manifest_contains_labelled_counterfactual_and_abstention() -> None:
    manifest = load_manifest(DEFAULT_MANIFEST)
    cases = {case.case_id: case for case in manifest.cases}

    assert cases["rescue-role-reversal"].expected_mission_family == "role_reversal"
    counterfactual = cases["rescue-counterfactual-no-revive"]
    assert counterfactual.expected_mission_family == "reunion"
    assert counterfactual.forbidden_offered_mission_families == ["role_reversal"]
    assert cases["landing-rendezvous"].expected_mission_family == "landing_rendezvous"
    assert cases["duo-assist"].expected_mission_family == "duo_assist"
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
    assert len(model_report["runs"]) == 6
    by_case = {run["case_id"]: run for run in model_report["runs"]}
    assert by_case["rescue-role-reversal"]["selected_family"] == "role_reversal"
    assert "role_reversal" not in by_case["rescue-counterfactual-no-revive"]["offered_families"]
    assert by_case["landing-rendezvous"]["selected_family"] == "landing_rendezvous"
    assert by_case["duo-assist"]["selected_family"] == "duo_assist"
    assert by_case["repeated-near-miss"]["selected_family"] == "redemption"
    ordinary = by_case["ordinary-sparse-telemetry"]
    assert ordinary["status"] == "not_generated"
    assert ordinary["selected_family"] is None
    assert ordinary["labels_passed"] is True
    summary = model_report["summary"]
    assert summary["mission_family_labels_evaluated"] == 5
    assert summary["mission_family_accuracy"] == 1
    assert summary["cross_fixture_family_variation_rate"] == 1
    assert summary["status_accuracy"] == 1
    assert summary["typed_abstention_accuracy"] == 1
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


@pytest.mark.parametrize(("labels_passed", "expected_exit_code"), [(True, 0), (False, 1)])
def test_cli_exit_code_reflects_label_results(
    labels_passed: bool,
    expected_exit_code: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evaluate_v2_module,
        "run_benchmark",
        lambda **_kwargs: {
            "models": [{"runs": [{"labels_passed": labels_passed}]}],
        },
    )

    assert evaluate_v2_module.main([]) == expected_exit_code


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
    assert all(len(item["runs"]) == 12 for item in report["models"])


def test_gemini_model_override_is_scoped_without_network(monkeypatch) -> None:
    class NoNetworkPipeline(MemoryInterpretationPipelineV2):
        @property
        def model_name(self) -> str:
            return evaluate_v2_module.os.environ["GEMINI_MODEL"]

        def validate_provider_configuration(self) -> None:
            return None

    monkeypatch.setattr(
        evaluate_v2_module,
        "build_v2_pipeline",
        lambda _provider: NoNetworkPipeline(),
    )
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    report = run_benchmark(
        provider="gemini",
        manifest_path=DEFAULT_MANIFEST,
        models=["gemini-test-model"],
        allow_live_api=True,
    )

    assert report["models"][0]["model"] == "gemini-test-model"
    assert "GEMINI_MODEL" not in evaluate_v2_module.os.environ
