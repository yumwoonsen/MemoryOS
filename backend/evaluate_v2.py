"""Opt-in v2.1 mission-affordance and abstention benchmark.

Deterministic evaluation is the default. Live provider calls require both an explicit
provider and ``--allow-live-api`` so importing this module or running the test suite cannot incur
API usage. Reports contain aggregate provider counters only; credentials, prompts, payloads, and
generated prose are never emitted.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from backend.models.schemas import StrictModel
from backend.models.v2_schemas import (
    InterpretDeliveryResultV2,
    InterpretDeliveryStatusV2,
    MissionFamilyV2,
    RawTelemetryBatchV2,
)
from backend.services.v2_evaluation import V2OfflineEvaluationCase, summarize_v2_evaluation
from backend.v2_pipeline import build_v2_pipeline

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_MANIFEST = DATA_DIR / "v2_evaluation" / "manifest.json"
ProviderName = Literal["deterministic", "groq", "openai", "gemini"]


class V2BenchmarkManifestCase(StrictModel):
    case_id: str = Field(min_length=1, max_length=128)
    fixture: str = Field(min_length=1, max_length=500)
    expected_status: InterpretDeliveryStatusV2
    expected_mission_family: MissionFamilyV2 | None = None
    forbidden_offered_mission_families: list[MissionFamilyV2] = Field(
        default_factory=list,
        max_length=3,
    )
    mission_variation_group: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def labels_are_consistent(self) -> V2BenchmarkManifestCase:
        if (
            self.expected_mission_family is not None
            and self.expected_status != InterpretDeliveryStatusV2.PENDING_PLAYER_DECISION
        ):
            raise ValueError("expected_mission_family requires pending_player_decision")
        if len(self.forbidden_offered_mission_families) != len(
            set(self.forbidden_offered_mission_families)
        ):
            raise ValueError("forbidden offered mission families must be unique")
        if self.mission_variation_group is not None and self.expected_mission_family is None:
            raise ValueError("mission_variation_group requires expected_mission_family")
        return self


class V2BenchmarkManifest(StrictModel):
    schema_version: Literal["2.1"] = "2.1"
    cases: list[V2BenchmarkManifestCase] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_cases(self) -> V2BenchmarkManifest:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("benchmark case_id values must be unique")
        return self


class BenchmarkConfigurationError(ValueError):
    """A safe, user-actionable CLI configuration failure."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the MemoryOS v2.1 pipeline.")
    parser.add_argument(
        "--provider",
        choices=("deterministic", "groq", "openai", "gemini"),
        default="deterministic",
        help="Live providers are disabled unless --allow-live-api is also supplied.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Labelled v2.1 fixture manifest.",
    )
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Repeat for a controlled model comparison. Omit for the provider default.",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Run every identical labelled case this many times (1-10).",
    )
    parser.add_argument(
        "--allow-live-api",
        action="store_true",
        help="Explicitly permit live provider calls, which may incur usage.",
    )
    return parser.parse_args(argv)


def load_manifest(path: Path) -> V2BenchmarkManifest:
    return V2BenchmarkManifest.model_validate_json(path.read_text(encoding="utf-8"))


def run_benchmark(
    *,
    provider: ProviderName,
    manifest_path: Path = DEFAULT_MANIFEST,
    models: Sequence[str] | None = None,
    repeats: int = 1,
    allow_live_api: bool = False,
) -> dict[str, Any]:
    """Run labelled cases without retaining telemetry or generated text in the report."""

    if repeats < 1 or repeats > 10:
        raise BenchmarkConfigurationError("repeats must be between 1 and 10")
    if provider != "deterministic" and not allow_live_api:
        raise BenchmarkConfigurationError(
            "live providers require the explicit --allow-live-api flag"
        )
    if (
        provider == "gemini"
        and allow_live_api
        and manifest_path.resolve() != DEFAULT_MANIFEST.resolve()
    ):
        raise BenchmarkConfigurationError(
            "Gemini live evaluation is restricted to the committed synthetic demo manifest"
        )
    requested_models = list(models or [None])
    if provider == "deterministic" and any(model is not None for model in requested_models):
        raise BenchmarkConfigurationError("deterministic evaluation does not accept --model")
    if any(model is not None and not model.strip() for model in requested_models):
        raise BenchmarkConfigurationError("model names cannot be empty")

    manifest = load_manifest(manifest_path)
    benchmark_started = time.perf_counter()
    model_reports = [
        _run_model(
            provider=provider,
            requested_model=requested_model,
            manifest=manifest,
            manifest_path=manifest_path,
            repeats=repeats,
        )
        for requested_model in requested_models
    ]
    return {
        "schema_version": "2.1",
        "provider": provider,
        "manifest": str(manifest_path),
        "repeats": repeats,
        "live_api_enabled": provider != "deterministic",
        "models": model_reports,
        "benchmark_latency_ms": round((time.perf_counter() - benchmark_started) * 1000, 2),
    }


def _run_model(
    *,
    provider: ProviderName,
    requested_model: str | None,
    manifest: V2BenchmarkManifest,
    manifest_path: Path,
    repeats: int,
) -> dict[str, Any]:
    with _temporary_model(provider, requested_model):
        pipeline = build_v2_pipeline(provider)
        if provider != "deterministic":
            try:
                pipeline.validate_provider_configuration()
            except Exception as error:
                raise BenchmarkConfigurationError(
                    f"provider configuration failed: {_safe_error_code(error)}"
                ) from None
        model_name = pipeline.model_name
        runs: list[dict[str, Any]] = []
        evaluation_cases: list[V2OfflineEvaluationCase] = []
        for repeat_index in range(1, repeats + 1):
            for manifest_case in manifest.cases:
                batch = _load_fixture(manifest_path.parent, manifest_case.fixture)
                before = _provider_totals(pipeline.interpreter.observability)
                started = time.perf_counter()
                try:
                    result = pipeline.interpret_delivery(batch)
                except Exception as error:  # Provider SDK errors differ but reports stay redacted.
                    runs.append(
                        {
                            "case_id": manifest_case.case_id,
                            "repeat": repeat_index,
                            "status": "provider_error",
                            "error_code": _safe_error_code(error),
                            "offered_families": [],
                            "selected_family": None,
                            "correction_attempted": False,
                            "validation_passed": False,
                            "validation_issue_codes": [],
                            "latency_ms": round(
                                (time.perf_counter() - started) * 1000,
                                2,
                            ),
                            "provider_usage": _usage_delta(
                                before,
                                _provider_totals(pipeline.interpreter.observability),
                            ),
                            "labels_passed": False,
                        }
                    )
                    continue
                elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
                after = _provider_totals(pipeline.interpreter.observability)
                evaluation_cases.append(
                    V2OfflineEvaluationCase(
                        case_id=f"{model_name}:{repeat_index}:{manifest_case.case_id}",
                        result=result,
                        expected_status=manifest_case.expected_status,
                        expected_mission_family=manifest_case.expected_mission_family,
                        forbidden_offered_mission_families=(
                            manifest_case.forbidden_offered_mission_families
                        ),
                        mission_variation_group=(
                            f"{model_name}:{repeat_index}:{manifest_case.mission_variation_group}"
                            if manifest_case.mission_variation_group
                            else None
                        ),
                    )
                )
                runs.append(
                    _run_report(
                        manifest_case,
                        result,
                        repeat_index=repeat_index,
                        latency_ms=elapsed_ms,
                        usage=_usage_delta(before, after),
                    )
                )

    return {
        "model": model_name,
        "prompt_version": pipeline.interpreter.prompt_version,
        "runs": runs,
        "summary": (
            summarize_v2_evaluation(evaluation_cases).model_dump(mode="json")
            if evaluation_cases
            else None
        ),
    }


def _load_fixture(base_dir: Path, fixture: str) -> RawTelemetryBatchV2:
    path = (base_dir / fixture).resolve()
    return RawTelemetryBatchV2.model_validate_json(path.read_text(encoding="utf-8"))


def _run_report(
    manifest_case: V2BenchmarkManifestCase,
    result: InterpretDeliveryResultV2,
    *,
    repeat_index: int,
    latency_ms: float,
    usage: dict[str, int | float],
) -> dict[str, Any]:
    offered_families = sorted(
        {item.family.value for item in result.studio_trace.mission_affordances}
    )
    selection = result.studio_trace.mission_selection
    selected_family = selection.selected_family.value if selection is not None else None
    forbidden = {family.value for family in manifest_case.forbidden_offered_mission_families}
    family_matches = (
        manifest_case.expected_mission_family is None
        or selected_family == manifest_case.expected_mission_family.value
    )
    return {
        "case_id": manifest_case.case_id,
        "repeat": repeat_index,
        "status": result.status.value,
        "offered_families": offered_families,
        "selected_family": selected_family,
        "correction_attempted": result.validation.correction_attempted,
        "validation_passed": result.validation.passed,
        "validation_issue_codes": [issue.code for issue in result.validation.issues],
        "latency_ms": latency_ms,
        "provider_usage": usage,
        "labels_passed": (
            result.status == manifest_case.expected_status
            and family_matches
            and not forbidden.intersection(offered_families)
        ),
    }


def _provider_totals(observability: object) -> dict[str, int | float]:
    if not isinstance(observability, dict):
        return _empty_usage()
    totals = observability.get("totals")
    if not isinstance(totals, dict):
        return _empty_usage()
    return {
        "request_count": _non_negative_number(totals.get("request_count"), integer=True),
        "input_tokens": _non_negative_number(totals.get("input_tokens"), integer=True),
        "output_tokens": _non_negative_number(totals.get("output_tokens"), integer=True),
        "provider_latency_ms": _non_negative_number(totals.get("latency_ms"), integer=False),
    }


def _usage_delta(
    before: dict[str, int | float],
    after: dict[str, int | float],
) -> dict[str, int | float]:
    return {
        key: round(max(0, after[key] - before[key]), 2)
        if key == "provider_latency_ms"
        else int(max(0, after[key] - before[key]))
        for key in _empty_usage()
    }


def _empty_usage() -> dict[str, int | float]:
    return {
        "request_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "provider_latency_ms": 0.0,
    }


def _non_negative_number(value: object, *, integer: bool) -> int | float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        return 0 if integer else 0.0
    return int(value) if integer else float(value)


def _safe_error_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and code and len(code) <= 100:
        return code
    return type(error).__name__


@contextmanager
def _temporary_model(provider: ProviderName, model: str | None) -> Iterator[None]:
    environment_key = {
        "groq": "GROQ_MODEL",
        "openai": "OPENAI_MODEL",
        "gemini": "GEMINI_MODEL",
    }.get(provider)
    if environment_key is None or model is None:
        yield
        return
    original = os.environ.get(environment_key)
    os.environ[environment_key] = model
    try:
        yield
    finally:
        if original is None:
            os.environ.pop(environment_key, None)
        else:
            os.environ[environment_key] = original


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run_benchmark(
            provider=args.provider,
            manifest_path=args.manifest,
            models=args.models,
            repeats=args.repeats,
            allow_live_api=args.allow_live_api,
        )
    except BenchmarkConfigurationError as error:
        print(json.dumps({"status": "configuration_error", "code": str(error)}))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
