#!/usr/bin/env python3
"""Check backend/requirements.txt for known CVEs via pip-audit.

Usage: python scripts/check_dependencies.py

Note: pip-audit's JSON output does not include a normalized severity field
(its OSV-backed report is id/fix_versions/aliases/description only), so this
cannot selectively fail on "high severity" as one might expect - it exits
non-zero on ANY known vulnerability instead. That errs toward never silently
ignoring a real CVE; triaging severity is left to whoever reads the output.
"""
import json
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REQUIREMENTS = BACKEND_DIR / "requirements.txt"


def ensure_pip_audit_installed() -> None:
    try:
        import pip_audit  # noqa: F401
    except ImportError:
        print("pip-audit not found, installing into the current environment...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pip-audit"], check=True)


def run_pip_audit() -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "pip_audit", "-r", str(REQUIREMENTS), "-f", "json"],
        capture_output=True,
        text=True,
    )
    if not result.stdout.strip():
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("pip-audit produced no output")
    return json.loads(result.stdout)


def main() -> int:
    ensure_pip_audit_installed()
    report = run_pip_audit()

    findings = [(dep["name"], dep["version"], vuln) for dep in report.get("dependencies", []) for vuln in dep.get("vulns", [])]

    if not findings:
        print("pip-audit: no known vulnerabilities found in requirements.txt")
        return 0

    print(f"pip-audit: {len(findings)} known vulnerability record(s) found:\n")
    for name, version, vuln in findings:
        aliases = ", ".join(vuln.get("aliases", [])) or vuln["id"]
        fix_versions = ", ".join(vuln.get("fix_versions", [])) or "no fix published yet"
        print(f"  {name} {version}: {aliases}")
        print(f"    fix: {fix_versions}\n")

    return 1


if __name__ == "__main__":
    sys.exit(main())
