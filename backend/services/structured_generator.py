"""Provider-neutral interface for schema-constrained model calls."""

from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


class StructuredGenerator(Protocol):
    provider_name: str
    model_name: str

    def generate(
        self,
        *,
        prompt_name: str,
        payload: dict[str, Any],
        response_model: type[ModelT],
    ) -> ModelT:
        """Return a model response already parsed into the requested contract."""

        ...
