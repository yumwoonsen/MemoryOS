"""Capture one exact, reviewed live Developer Studio result as a safe replay.

The command deliberately performs one catalog request and one interpretation
request, without retries.  Its pure validation and manifest functions are kept
separate so safety behavior can be tested without a network or AI provider.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from pydantic import Field, ValidationError, model_validator

from backend.models.schemas import ProviderErrorBody, StrictModel
from backend.models.v2_schemas import (
    InterpretDeliveryResultV2,
    InterpretDeliveryStatusV2,
    MissionFamilyV2,
)
from backend.models.v2_studio_schemas import (
    StudioScenarioCatalogV2,
    StudioScenarioDescriptorV2,
    StudioScenarioIdV2,
    StudioScenarioInterpretationV2,
)

REPLAY_SCHEMA_VERSION = "1.0"
SAVED_REPLAY_MODE = "saved_replay"
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1] / "frontend" / "data" / "studio-replays" / "manifest.json"
)
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 150.0
_CANONICAL_SCENARIO_ORDER = {
    scenario_id: index for index, scenario_id in enumerate(StudioScenarioIdV2)
}
_SAFE_CAPTURE_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_PROVIDER_FAILURE_STAGES = frozenset(
    {
        "configuration",
        "memory_interpretation",
        "memory_interpretation_correction",
    }
)
_PROVIDER_FAILURE_RETRYABILITY = {
    "invalid_output_token_limit": False,
    "invalid_provider": False,
    "live_ai_required": False,
    "missing_api_key": False,
    "provider_authentication_failed": False,
    "provider_connection_error": True,
    "provider_error": False,
    "provider_invalid_response": False,
    "provider_no_output": False,
    "provider_output_limit": False,
    "provider_permission_denied": False,
    "provider_quota_exhausted": False,
    "provider_rate_limited": True,
    "provider_refusal": False,
    "provider_request_rejected": False,
    "provider_timeout": True,
    "provider_unavailable": True,
    "provider_unexpected_error": False,
}


class ReplayCaptureError(RuntimeError):
    """A fail-closed capture error with a non-sensitive stable code."""

    def __init__(self, code: str) -> None:
        safe_code = (
            code if _SAFE_CAPTURE_ERROR_CODE.fullmatch(code) else "invalid_capture_error_code"
        )
        super().__init__(safe_code)
        self.code = safe_code


class ReplayCaptureProviderFailure(RuntimeError):
    """A validated provider failure containing only allowlisted public fields."""

    def __init__(self, *, http_status: int, stage: str, code: str, retryable: bool) -> None:
        self.http_status = http_status
        self.stage = stage
        self.code = code
        self.retryable = retryable
        super().__init__("The live provider request failed safely.")


class StudioReplayScenarioRefV1(StrictModel):
    scenario_id: StudioScenarioIdV2
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fixture_revision: str = Field(pattern=r"^2\.1:[0-9a-f]{12}$")


class StudioReplayProvenanceV1(StrictModel):
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=160)
    prompt_version: str = Field(min_length=1, max_length=160)
    result_schema_version: Literal["2.1"] = "2.1"
    captured_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")


class StudioReplayEnvelopeV1(StrictModel):
    replay_schema_version: Literal["1.0"] = "1.0"
    scenario: StudioReplayScenarioRefV1
    provenance: StudioReplayProvenanceV1
    result: InterpretDeliveryResultV2


class StudioReplayManifestV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    replays: list[StudioReplayEnvelopeV1] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def scenario_entries_are_unique(self) -> StudioReplayManifestV1:
        scenario_ids = [replay.scenario.scenario_id for replay in self.replays]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("replay manifest scenario IDs must be unique")
        return self


def select_catalog_scenario(
    catalog: StudioScenarioCatalogV2,
    scenario_id: str | StudioScenarioIdV2,
) -> StudioScenarioDescriptorV2:
    """Return the exact catalog descriptor or fail without accepting arbitrary input."""

    try:
        typed_id = StudioScenarioIdV2(scenario_id)
    except ValueError as error:
        raise ReplayCaptureError("unknown_scenario") from error
    descriptor = next(
        (item for item in catalog.scenarios if item.scenario_id == typed_id),
        None,
    )
    if descriptor is None:
        raise ReplayCaptureError("scenario_missing_from_catalog")
    return descriptor


def _actual_family(result: InterpretDeliveryResultV2) -> MissionFamilyV2 | None:
    if result.status != InterpretDeliveryStatusV2.PENDING_PLAYER_DECISION:
        return None
    if result.next_chapter is None:  # Defensive; the result model already requires it.
        raise ReplayCaptureError("pending_result_missing_chapter")
    return result.next_chapter.family


def _safe_metadata_label(metadata: dict[str, object], key: str, max_length: int) -> str:
    value = metadata.get(key)
    if (
        not isinstance(value, str)
        or not value
        or len(value) > max_length
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ReplayCaptureError(f"invalid_{key}")
    return value


def validate_interpretation_for_capture(
    descriptor: StudioScenarioDescriptorV2,
    interpretation: StudioScenarioInterpretationV2,
) -> None:
    """Require exact fixture binding, offline expectation agreement, and live provenance."""

    if interpretation.scenario != descriptor:
        raise ReplayCaptureError("scenario_descriptor_mismatch")

    result = interpretation.result
    if result.status != descriptor.expected_status:
        raise ReplayCaptureError("unexpected_result_status")
    if _actual_family(result) != descriptor.expected_mission_family:
        raise ReplayCaptureError("unexpected_mission_family")

    metadata = result.metadata
    if metadata.get("mode") != "live_ai":
        raise ReplayCaptureError("result_not_live_ai")
    expected_origin = (
        "live_ai_validated"
        if result.status == InterpretDeliveryStatusV2.PENDING_PLAYER_DECISION
        else "no_player_content"
    )
    if metadata.get("content_origin") != expected_origin:
        raise ReplayCaptureError("invalid_content_origin")
    if metadata.get("grounded_render") is not False:
        raise ReplayCaptureError("grounded_render_not_disabled")
    if metadata.get("narrative_fallback") is not False:
        raise ReplayCaptureError("narrative_fallback_not_disabled")

    _safe_metadata_label(metadata, "provider", 80)
    _safe_metadata_label(metadata, "model", 160)
    _safe_metadata_label(metadata, "prompt_version", 160)


def _captured_at_string(captured_at: datetime) -> str:
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ReplayCaptureError("captured_at_requires_timezone")
    return captured_at.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sanitized_result(
    descriptor: StudioScenarioDescriptorV2,
    result: InterpretDeliveryResultV2,
) -> InterpretDeliveryResultV2:
    """Remove live authorization and arbitrary runtime metadata from a replay result."""

    metadata = result.metadata
    payload = result.model_dump(mode="json")
    payload["metadata"] = {
        "provider": _safe_metadata_label(metadata, "provider", 80),
        "model": _safe_metadata_label(metadata, "model", 160),
        "mode": SAVED_REPLAY_MODE,
        "prompt_version": _safe_metadata_label(metadata, "prompt_version", 160),
        "content_origin": (
            "saved_live_replay"
            if result.status == InterpretDeliveryStatusV2.PENDING_PLAYER_DECISION
            else "no_player_content"
        ),
        "grounded_render": False,
        "narrative_fallback": False,
    }
    if result.status == InterpretDeliveryStatusV2.PENDING_PLAYER_DECISION:
        payload["delivery_id"] = (
            "replay-only:non-authorizing:"
            f"{descriptor.scenario_id.value}:{descriptor.fixture_sha256[:12]}"
        )
    return InterpretDeliveryResultV2.model_validate(payload)


def build_replay_envelope(
    descriptor: StudioScenarioDescriptorV2,
    interpretation: StudioScenarioInterpretationV2,
    *,
    captured_at: datetime,
) -> StudioReplayEnvelopeV1:
    """Build one version-bound, non-authorizing replay envelope."""

    validate_interpretation_for_capture(descriptor, interpretation)
    metadata = interpretation.result.metadata
    return StudioReplayEnvelopeV1(
        scenario=StudioReplayScenarioRefV1(
            scenario_id=descriptor.scenario_id,
            fixture_sha256=descriptor.fixture_sha256,
            fixture_revision=descriptor.fixture_revision,
        ),
        provenance=StudioReplayProvenanceV1(
            provider=_safe_metadata_label(metadata, "provider", 80),
            model=_safe_metadata_label(metadata, "model", 160),
            prompt_version=_safe_metadata_label(metadata, "prompt_version", 160),
            result_schema_version=interpretation.result.schema_version,
            captured_at=_captured_at_string(captured_at),
        ),
        result=_sanitized_result(descriptor, interpretation.result),
    )


def update_manifest(
    manifest: StudioReplayManifestV1,
    replay: StudioReplayEnvelopeV1,
) -> StudioReplayManifestV1:
    """Replace only the selected scenario and return canonical scenario order."""

    retained = [
        item
        for item in manifest.replays
        if item.scenario.scenario_id != replay.scenario.scenario_id
    ]
    ordered = sorted(
        [*retained, replay],
        key=lambda item: _CANONICAL_SCENARIO_ORDER[item.scenario.scenario_id],
    )
    return StudioReplayManifestV1(replays=ordered)


def load_manifest(path: Path) -> StudioReplayManifestV1:
    """Strictly load an existing manifest, or initialize a missing one."""

    if not path.exists():
        return StudioReplayManifestV1()
    try:
        return StudioReplayManifestV1.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as error:
        raise ReplayCaptureError("invalid_existing_manifest") from error


def write_manifest_atomically(path: Path, manifest: StudioReplayManifestV1) -> None:
    """Atomically replace a manifest in its existing parent directory."""

    if not path.parent.is_dir():
        raise ReplayCaptureError("manifest_parent_missing")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(manifest.model_dump(mode="json"), handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except OSError as error:
        raise ReplayCaptureError("manifest_write_failed") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass


def _validated_base_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    if (
        parts.scheme not in {"http", "https"}
        or parts.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or parts.path not in {"", "/"}
    ):
        raise ReplayCaptureError("backend_url_must_be_local")
    return urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")


def _validated_provider_failure(
    *,
    http_status: int,
    payload: bytes,
) -> ReplayCaptureProviderFailure:
    """Reduce a typed 503 body to a small, allowlisted provider failure."""

    if http_status != 503:
        raise ReplayCaptureError(f"backend_http_{http_status}")
    try:
        body = ProviderErrorBody.model_validate_json(payload)
    except ValidationError as error:
        raise ReplayCaptureError("invalid_provider_error_response") from error
    expected_retryable = _PROVIDER_FAILURE_RETRYABILITY.get(body.code)
    if (
        body.stage not in _PROVIDER_FAILURE_STAGES
        or expected_retryable is None
        or body.retryable is not expected_retryable
    ):
        raise ReplayCaptureError("invalid_provider_error_response")
    return ReplayCaptureProviderFailure(
        http_status=http_status,
        stage=body.stage,
        code=body.code,
        retryable=body.retryable,
    )


def _read_response(
    request: Request,
    *,
    timeout_seconds: float,
    accept_provider_failure: bool = False,
) -> bytes:
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        try:
            payload = error.read(MAX_RESPONSE_BYTES + 1)
        except OSError as read_error:
            raise ReplayCaptureError("backend_http_error_unreadable") from read_error
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ReplayCaptureError("backend_error_response_too_large") from error
        if accept_provider_failure:
            raise _validated_provider_failure(
                http_status=error.code,
                payload=payload,
            ) from error
        raise ReplayCaptureError(f"backend_http_{error.code}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise ReplayCaptureError("backend_request_failed") from error
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ReplayCaptureError("backend_response_too_large")
    return payload


def _request_headers() -> dict[str, str]:
    headers = {"Accept": "application/json", "Cache-Control": "no-store"}
    proxy_token = os.getenv("MEMORYOS_PROXY_TOKEN", "")
    if proxy_token:
        headers["X-MemoryOS-Proxy-Token"] = proxy_token
    return headers


def capture_one_scenario(
    scenario_id: str | StudioScenarioIdV2,
    *,
    base_url: str = DEFAULT_BACKEND_URL,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    captured_at: datetime | None = None,
) -> StudioReplayEnvelopeV1:
    """Make exactly two body-safe local requests and atomically save one scenario."""

    if timeout_seconds <= 0:
        raise ReplayCaptureError("invalid_timeout")
    typed_id = StudioScenarioIdV2(scenario_id)
    local_url = _validated_base_url(base_url)
    headers = _request_headers()

    catalog_bytes = _read_response(
        Request(f"{local_url}/v2/studio/scenarios", headers=headers, method="GET"),
        timeout_seconds=timeout_seconds,
    )
    try:
        catalog = StudioScenarioCatalogV2.model_validate_json(catalog_bytes)
    except ValidationError as error:
        raise ReplayCaptureError("invalid_catalog_response") from error
    descriptor = select_catalog_scenario(catalog, typed_id)

    interpretation_bytes = _read_response(
        Request(
            f"{local_url}/v2/studio/scenarios/{quote(typed_id.value, safe='')}/interpret",
            headers=headers,
            method="POST",
        ),
        timeout_seconds=timeout_seconds,
        accept_provider_failure=True,
    )
    try:
        interpretation = StudioScenarioInterpretationV2.model_validate_json(interpretation_bytes)
    except ValidationError as error:
        raise ReplayCaptureError("invalid_interpretation_response") from error

    replay = build_replay_envelope(
        descriptor,
        interpretation,
        captured_at=captured_at or datetime.now(UTC),
    )
    manifest = update_manifest(load_manifest(manifest_path), replay)
    write_manifest_atomically(manifest_path, manifest)
    return replay


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture one exact live Developer Studio scenario replay.",
    )
    parser.add_argument(
        "--scenario",
        required=True,
        choices=[scenario_id.value for scenario_id in StudioScenarioIdV2],
    )
    parser.add_argument("--base-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        replay = capture_one_scenario(
            args.scenario,
            base_url=args.base_url,
            manifest_path=args.manifest,
            timeout_seconds=args.timeout_seconds,
        )
    except ReplayCaptureProviderFailure as error:
        print(
            f"scenario={args.scenario} status=capture_failed "
            f"http_status={error.http_status} stage={error.stage} code={error.code} "
            f"retryable={str(error.retryable).lower()}",
            file=sys.stderr,
        )
        return 1
    except ReplayCaptureError as error:
        print(
            f"scenario={args.scenario} status=capture_failed error_code={error.code}",
            file=sys.stderr,
        )
        return 1
    except Exception:  # Keep unexpected exception text and raw response data private.
        print(
            f"scenario={args.scenario} status=capture_failed error_code=unexpected_capture_error",
            file=sys.stderr,
        )
        return 1
    print(
        f"scenario={replay.scenario.scenario_id.value} "
        f"status={replay.result.status.value} path={args.manifest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
