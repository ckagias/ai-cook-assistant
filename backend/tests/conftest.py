import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(autouse=True, scope="session")
def _test_database(tmp_path_factory):
    """Every test session gets its own SQLite file seeded from data/recipes.json - the real
    backend/data/cook.db is never touched. Tests that write recipes point DB_PATH at their own
    file instead (see test_db.py)."""
    import os

    path = tmp_path_factory.mktemp("db") / "test.db"
    previous = os.environ.get("DB_PATH")
    os.environ["DB_PATH"] = str(path)
    yield path
    if previous is None:
        os.environ.pop("DB_PATH", None)
    else:
        os.environ["DB_PATH"] = previous
