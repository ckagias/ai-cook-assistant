import shutil
import subprocess
from pathlib import Path

import pytest

STATIC_JS_DIR = Path(__file__).resolve().parent.parent / "static" / "js"
TESTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TESTS_DIR.parent

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node not found on PATH")


def _js_files():
    return sorted(STATIC_JS_DIR.glob("*.js"))


def _mjs_test_files():
    return sorted(TESTS_DIR.glob("*.test.mjs"))


@pytest.mark.parametrize("path", _js_files(), ids=lambda p: p.name)
def test_js_module_syntax(path):
    # Piping the source into stdin with --input-type=module is deliberate:
    # `node --check <file>` returns exit code 0 even on a file with an
    # outright syntax error, which would make this check worthless.
    source = path.read_text(encoding="utf-8")
    result = subprocess.run(
        [NODE, "--input-type=module", "--check"],
        input=source,
        capture_output=True,
        text=True,
        encoding="utf-8",  # Windows would otherwise encode the Greek source as cp1252 and crash
        timeout=30,
    )
    assert result.returncode == 0, f"{path.name} failed to parse:\n{result.stderr}"


@pytest.mark.parametrize("path", _mjs_test_files(), ids=lambda p: p.name)
def test_mjs_suite_passes(path):
    result = subprocess.run(
        [NODE, str(path.relative_to(BACKEND_DIR))],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, f"{path.name} exited {result.returncode}:\n{result.stdout}\n{result.stderr}"
    assert "all passed" in result.stdout, f"{path.name} did not print 'all passed':\n{result.stdout}"
