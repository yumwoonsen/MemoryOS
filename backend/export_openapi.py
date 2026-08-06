"""Write the canonical FastAPI OpenAPI document for frontend type generation."""

from __future__ import annotations

import json
from pathlib import Path

from backend.main import app


def main() -> None:
    output = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"
    output.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
