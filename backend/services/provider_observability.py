"""Safe, payload-free observability for structured provider calls."""

from __future__ import annotations

from typing import Literal

StageStatus = Literal["succeeded", "failed"]


class ProviderObservability:
    """Collect aggregate and per-stage metrics without retaining prompts or outputs."""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        mode: Literal["deterministic", "live_ai"],
        configured_max_retries: int,
    ) -> None:
        self.provider = provider
        self.model = model
        self.mode = mode
        self.configured_max_retries = configured_max_retries
        self._stages: list[dict[str, str | int | float]] = []

    def record(
        self,
        *,
        stage: str,
        status: StageStatus,
        latency_ms: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Record one logical call; SDK-internal retry counts are intentionally not guessed."""

        self._stages.append(
            {
                "stage": stage,
                "status": status,
                "request_count": 1,
                "input_tokens": max(0, input_tokens),
                "output_tokens": max(0, output_tokens),
                "latency_ms": round(max(0.0, latency_ms), 2),
                "configured_max_retries": self.configured_max_retries,
            }
        )

    @property
    def usage_totals(self) -> dict[str, int]:
        return {
            "input_tokens": sum(int(item["input_tokens"]) for item in self._stages),
            "output_tokens": sum(int(item["output_tokens"]) for item in self._stages),
        }

    def snapshot(self) -> dict[str, object]:
        usage = self.usage_totals
        return {
            "provider": self.provider,
            "model": self.model,
            "mode": self.mode,
            "totals": {
                "request_count": len(self._stages),
                **usage,
                "latency_ms": round(
                    sum(float(item["latency_ms"]) for item in self._stages),
                    2,
                ),
                "configured_max_retries": self.configured_max_retries,
            },
            "stages": [dict(item) for item in self._stages],
        }


def empty_observability(
    *,
    provider: str,
    model: str,
    mode: Literal["deterministic", "live_ai"],
    configured_max_retries: int = 0,
) -> dict[str, object]:
    """Return the same stable shape before any live provider stage has run."""

    return ProviderObservability(
        provider=provider,
        model=model,
        mode=mode,
        configured_max_retries=configured_max_retries,
    ).snapshot()
