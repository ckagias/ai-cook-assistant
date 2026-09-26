#!/usr/bin/env python3
"""Open the app in its own browser window: Edge/Chrome app mode, with a profile of its own in
which the camera and microphone are already allowed for the app's address.

Why: a camera prompt can't appear everywhere. VS Code's built-in preview never shows one, and a
browser set to block camera requests (a Firefox privacy option) refuses without asking - both
end in "Camera access failed: NotAllowedError". This window sidesteps both, and never touches
the user's everyday browser profile.

  python scripts/app_window.py grant --profile DIR --origin https://192.168.1.15:8443
  python scripts/app_window.py open  --profile DIR --url http://localhost:8000/?token=... \
                                     [--wait http://127.0.0.1:8000/health] [--spki HASH]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

MEDIA_SETTINGS = ("media_stream_camera", "media_stream_mic")
ALLOW = 1
WINDOWS_TO_UNIX_EPOCH_S = 11644473600  # Chromium stores times as microseconds since 1601


def is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def find_browser() -> str | None:
    if os.getenv("APP_BROWSER"):
        return os.environ["APP_BROWSER"]
    if sys.platform == "win32":
        bases = [os.getenv("ProgramFiles(x86)"), os.getenv("ProgramFiles"), os.getenv("LOCALAPPDATA")]
        rel = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
        candidates = [str(Path(b) / r) for r in rel for b in bases if b]
    elif sys.platform == "darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                      "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    else:
        candidates = [shutil.which(n) or "" for n in
                      ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge")]
        if is_wsl():  # the Windows browser; WSL forwards localhost to it
            candidates += ["/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
                           "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"]
    return next((c for c in candidates if c and Path(c).exists()), None)


def origin_pattern(url: str) -> str:
    """Chromium's content-setting key for one origin, e.g. "http://localhost:8000,*"."""
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return f"{parts.scheme}://{parts.hostname}:{port},*"


def browser_running(profile: Path) -> bool:
    """A running browser rewrites Preferences on exit - editing it underneath would be lost."""
    lock = profile / "lockfile"  # Windows: held open exclusively while the browser runs
    if lock.exists():
        try:
            with open(lock, "a"):
                pass
        except PermissionError:
            return True
    singleton = profile / "SingletonLock"  # Linux/macOS: a symlink to "host-pid"
    if singleton.is_symlink():
        try:
            os.kill(int(os.readlink(singleton).rsplit("-", 1)[1]), 0)
            return True
        except (ValueError, OSError):
            return False
    return False


def grant(profile: Path, origin: str) -> str:
    if browser_running(profile):
        return "app window already open - its own camera prompt applies"
    prefs_path = profile / "Default" / "Preferences"
    prefs = {}
    if prefs_path.exists():
        try:
            prefs = json.loads(prefs_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return "profile preferences unreadable - left alone, the browser will ask instead"
    exceptions = prefs.setdefault("profile", {}).setdefault("content_settings", {}).setdefault("exceptions", {})
    key = origin_pattern(origin)
    stamp = str(int((time.time() + WINDOWS_TO_UNIX_EPOCH_S) * 1_000_000))
    changed = False
    for setting in MEDIA_SETTINGS:
        entries = exceptions.setdefault(setting, {})
        if (entries.get(key) or {}).get("setting") != ALLOW:
            entries[key] = {"last_modified": stamp, "setting": ALLOW}
            changed = True
    if not changed:
        return f"camera and microphone already allowed for {key[:-2]}"
    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = prefs_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(prefs), encoding="utf-8")
    os.replace(tmp, prefs_path)
    return f"camera and microphone allowed for {key[:-2]} in the app window"


def wait_until_up(url: str, seconds: float = 90.0) -> bool:
    context = ssl._create_unverified_context()  # our own self-signed LAN certificate
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2, context=context):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def native_path(path: Path, browser: str) -> str:
    if is_wsl() and browser.startswith("/mnt/"):
        return subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True).stdout.strip()
    return str(path)


def open_window(url: str, profile: Path, wait: str | None, spki: str | None) -> int:
    browser = find_browser()
    if not browser:
        print(f"No Edge/Chrome found for the app window - open {url} in a browser (not an editor's preview).")
        return 1
    if wait and not wait_until_up(wait):
        print(f"The server didn't come up at {wait} - not opening the app window.")
        return 1
    print(grant(profile, url))
    args = [browser, f"--app={url}", f"--user-data-dir={native_path(profile, browser)}",
            "--no-first-run", "--no-default-browser-check", "--window-size=1280,860"]
    if spki:
        # --test-type hides the "unsupported command-line flag" bar the SPKI flag causes.
        args += [f"--ignore-certificate-errors-spki-list={spki}", "--test-type"]
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=sys.platform != "win32")
    print("Opened the app window.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grant", help="allow camera + microphone for an origin in the app profile")
    g.add_argument("--profile", required=True, type=Path)
    g.add_argument("--origin", required=True)
    o = sub.add_parser("open", help="(wait for the server, grant, then) open the app window")
    o.add_argument("--profile", required=True, type=Path)
    o.add_argument("--url", required=True)
    o.add_argument("--wait", default=None, help="health URL to wait for first")
    o.add_argument("--spki", default=None, help="trust exactly this certificate (LAN HTTPS)")
    args = ap.parse_args()
    if args.cmd == "grant":
        print(grant(args.profile, args.origin))
        return 0
    return open_window(args.url, args.profile, args.wait, args.spki)


if __name__ == "__main__":
    sys.exit(main())
