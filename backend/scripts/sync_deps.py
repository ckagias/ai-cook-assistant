#!/usr/bin/env python3
"""Install requirement files without re-downloading what's already there.

Usage (run with the venv's python): python scripts/sync_deps.py requirements.txt [requirements-detect.txt ...]
       python scripts/sync_deps.py --repair requirements.txt [...]   # see repair() below

1. Ask pip for a dry run: which packages are missing or at a different version than required.
   Nothing to do -> exit immediately, no network.
2. For each package that would change: if a *different* version is installed now, save that old
   version's wheel into ../.wheelhouse first, then fetch the new one there too. The wheelhouse only
   ever grows - older versions stay available offline:
       pip install --no-index --find-links .wheelhouse "torch==<old version>"
3. Install from the wheelhouse (pip falls back to the index only for what isn't there).

A virtual environment holds one version of a package at a time, so the *installed* copy is
replaced on an upgrade - the wheelhouse is where old versions are kept.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
WHEELHOUSE = Path(os.getenv("WHEELHOUSE") or BACKEND_DIR.parent / ".wheelhouse")


def pip(*args: str, quiet: bool = True) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "pip", *args]
    if quiet:
        cmd.append("-q")
    return subprocess.run(cmd, capture_output=quiet, text=True)


def planned_changes(req_files: list[str]) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.json"
        args = ["install", "--dry-run", "--report", str(report), "--find-links", str(WHEELHOUSE)]
        for req in req_files:
            args += ["-r", req]
        result = pip(*args)
        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            raise SystemExit(f"pip could not resolve {', '.join(req_files)} (see above)")
        return json.loads(report.read_text(encoding="utf-8")).get("install", [])


def installed_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def keep(specs: list[str]) -> set[str]:
    """Put exact versions' wheels into the wheelhouse (files already there are skipped).
    One pip process for the whole batch; only if that fails, retry one by one to find which
    spec can't be fetched. Returns the specs that could not be kept."""
    if not specs:
        return set()
    base = ["download", "--no-deps", "--find-links", str(WHEELHOUSE), "-d", str(WHEELHOUSE)]
    if pip(*base, *specs).returncode == 0:
        return set()
    return {s for s in specs if pip(*base, s).returncode != 0}


def main(req_files: list[str]) -> int:
    WHEELHOUSE.mkdir(exist_ok=True)
    changes = planned_changes(req_files)
    if not changes:
        print(f"  {', '.join(req_files)}: everything already installed at the required versions.")
        return 0

    added, upgraded, old_specs, new_specs = [], [], [], []
    for item in changes:
        name, version = item["metadata"]["name"], item["metadata"]["version"]
        old = installed_version(name)
        if item.get("is_direct"):  # e.g. a git URL - pip builds it during install
            added.append(f"{name} (from {item['download_info']['url']})")
            continue
        if old and old != version:
            old_specs.append(f"{name}=={old}")
            upgraded.append((name, old, version))
        else:
            added.append(f"{name} {version}")
        new_specs.append(f"{name}=={version}")

    print(f"  {len(new_specs)} package(s) to fetch into .wheelhouse/ ({len(upgraded)} version change(s))...")
    lost = keep(old_specs)  # the versions about to be replaced, so they stay available offline
    keep(new_specs)
    for line in added:
        print(f"  + {line}")
    for name, old, version in upgraded:
        kept = "old wheel kept in .wheelhouse/" if f"{name}=={old}" not in lost else "old version not downloadable to keep"
        print(f"  ~ {name} {old} -> {version}  ({kept})")

    reqs = [a for req in req_files for a in ("-r", req)]
    # Everything that changes is in the wheelhouse now - install strictly from it, so nothing is
    # fetched twice. Only something that can't be a plain wheel (a git URL) needs the index.
    result = pip("install", "--no-index", "--find-links", str(WHEELHOUSE), *reqs)
    if result.returncode != 0:
        result = pip("install", "--find-links", str(WHEELHOUSE), *reqs, quiet=False)
    return result.returncode


def _wheel_name(name: str) -> str:
    return name.lower().replace("-", "_").replace(".", "_")


def repair(req_files: list[str]) -> int:
    """Reinstall every installed package from its wheel in the wheelhouse, offline, without
    re-resolving anything. For an environment whose files were partly deleted (e.g. an
    interrupted `rm -rf`): pip's own check only reads package metadata, so a package can look
    installed while files it needs are gone."""
    wheels = {}
    for wheel in WHEELHOUSE.glob("*.whl"):
        parts = wheel.name.split("-")
        wheels[(_wheel_name(parts[0]), parts[1])] = wheel
    targets, unmatched = [], []
    for dist in metadata.distributions():
        name, version = dist.metadata["Name"], dist.version
        if _wheel_name(name) in ("pip", "setuptools", "wheel"):
            continue
        wheel = wheels.get((_wheel_name(name), version))
        (targets if wheel else unmatched).append(wheel or f"{name}=={version}")
    print(f"  repairing {len(targets)} package(s) from .wheelhouse/ (offline)...")
    result = pip("install", "--force-reinstall", "--no-deps", "--no-index", *map(str, targets), quiet=False)
    if unmatched:
        print(f"  not in the wheelhouse, left as installed: {', '.join(map(str, unmatched))}")
    if result.returncode != 0:
        return result.returncode
    return main(req_files)  # anything missing entirely is (re)installed the normal way


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args == ["--repair"]:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    if args[0] == "--repair":
        sys.exit(repair(args[1:]))
    sys.exit(main(args))
