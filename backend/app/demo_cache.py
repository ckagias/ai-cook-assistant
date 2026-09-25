import json
import os
from pathlib import Path
from typing import Optional

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "demo_fixtures"


def demo_mode_enabled() -> bool:
    return os.getenv("DEMO_MODE", "false").lower() == "true"


def demo_strict_enabled() -> bool:
    return os.getenv("DEMO_STRICT", "false").lower() == "true"


def load_fixture(mode: str, recipe_id: Optional[str], step_index: Optional[int]) -> Optional[dict]:
    candidates = []
    if recipe_id is not None and step_index is not None:
        candidates.append(f"{mode}__{recipe_id}__{step_index}.json")
    candidates.append(f"{mode}.json")

    for name in candidates:
        path = FIXTURES_DIR / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return None
