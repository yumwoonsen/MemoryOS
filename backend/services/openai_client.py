"""OpenAI Responses API adapter with Pydantic Structured Outputs."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI
from pydantic import BaseModel

from backend.services.prompt_loader import load_prompt
from backend.services.structured_generator import ModelT


class OpenAIStructuredGenerator:
    """Generate one pipeline stage while preserving a strict Pydantic contract."""

    provider_name = "openai"

    def __init__(self, model_name: str | None = None) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY is required when MEMORYOS_PROVIDER=openai. "
                "Use deterministic mode for the credential-free local demo."
            )
        self.model_name = model_name or os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
        self._client = OpenAI()

    def generate(
        self,
        *,
        prompt_name: str,
        payload: dict[str, Any],
        response_model: type[ModelT],
    ) -> ModelT:
        response = self._client.responses.parse(
            model=self.model_name,
            input=[
                {"role": "system", "content": load_prompt(prompt_name)},
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                },
            ],
            text_format=response_model,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise RuntimeError("The model returned no parsed output for the requested schema.")
        if not isinstance(parsed, BaseModel):
            raise RuntimeError("The model response was not parsed into a Pydantic model.")
        return parsed
