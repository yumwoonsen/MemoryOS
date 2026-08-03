"""Read version-controlled prompts from the backend prompt directory."""

from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


def load_prompt(prompt_name: str) -> str:
    prompt_path = (PROMPT_DIR / prompt_name).resolve()
    if prompt_path.parent != PROMPT_DIR.resolve():
        raise ValueError("prompt_name must refer to a file in backend/prompts")
    return prompt_path.read_text(encoding="utf-8")
