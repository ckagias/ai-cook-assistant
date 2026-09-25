# Security plan: network hardening and access control, phase by phase

**Branch:** `feature/security-network-hardening`
**Owner:** Developer B
**Depends on:** nothing else in this repo. Touches `backend/app/main.py`,
`backend/static/js/api.js`/`app.js`, `backend/.env.example`.
**Related:** `plans/PLAN_SECURITY_PROMPT_INJECTION.md` (Developer A) - that
plan covers what happens to a legitimate call's output; this plan covers
who's allowed to make the call at all. Independent work, no shared files.

Each phase below is self-contained: what to build and why, a ready-to-paste
prompt, and a suggested commit message. Feed one phase's prompt at a time to
the LLM, review the diff, commit yourself (the LLM should never run `git
commit`), then move to the next phase.

---

## Trust boundary as it stands today

`backend/app/main.py` has **no authentication anywhere**, **no rate
limiting**, and **no request size cap** on `/analyze`. That's a reasonable
default for the MVP's actual deployment model - same-origin, reached via
`adb reverse` (traffic never leaves the USB link) or a self-signed cert on
a trusted home LAN (README's "Tablet bring-up" section). It stops being
reasonable the moment that self-signed-HTTPS path is reachable from a
network with anyone untrusted on it: **anyone who can reach the backend can
burn API credits via `/analyze`, or use `/barcode/{code}` as an open,
unauthenticated proxy to Open Food Facts.**

This plan's job: make "who can call this" an explicit, opt-in decision
(off by default, so the existing demo/dev workflow is untouched unless
someone turns it on), not an accident of network topology.

---

## Phase 1 — Threat model doc

**Files:** `backend/SECURITY_THREAT_MODEL_network.md`.

Write down, concretely:

- The two deployment shapes this app actually has today (`adb reverse` /
  same-origin-on-localhost vs. self-signed HTTPS on a LAN) and what's
  actually exposed to whom in each.
- What each unauthenticated route costs an attacker nothing to abuse and
  what it costs the operator: `/analyze` (real API spend per call, and a
  captured recipe context could be used to probe the safety-override
  behavior), `/barcode/{code}` (a free open proxy to a third party's API -
  abuse of *that* could get the whole app's IP rate-limited or blocked by
  Open Food Facts, a problem for every user, not just the attacker),
  `/recipes`/`/reference/*` (low sensitivity - no cost, no secrets, just
  recipe text and images already meant to be shown).
- Explicitly **not** in scope: this plan does not attempt full
  multi-tenant user accounts, OAuth, or anything sized for a public SaaS -
  this is a single-household device-pairing model, matching how the rest
  of the app is designed (one backend, one or a few tablets on the same
  network).

**Prompt:**
> Write `backend/SECURITY_THREAT_MODEL_network.md` covering the points
> above: the two real deployment shapes, what each route costs to leave
> open, and an explicit statement that this plan targets device-pairing
> for a single household, not multi-tenant auth. Do not commit - stop for
> review.

**Suggested commit message:** `docs: network threat model and trust-boundary notes`

---

## Phase 2 — Opt-in pairing-token auth

**Files:** `backend/app/auth.py`, `backend/app/main.py` (wire in),
`backend/.env.example` (new var), `backend/static/js/api.js`,
`backend/static/js/app.js`.

**Off by default**, same pattern as `DEMO_MODE`/`DEMO_STRICT` - a blank env
var means the existing behavior (no auth) is unchanged, so nobody's local
setup breaks silently on an upgrade.

```python
# backend/app/auth.py
import os
from fastapi import Header, HTTPException


def pairing_token_enabled() -> bool:
    return bool(os.getenv("BACKEND_PAIRING_TOKEN"))


async def require_pairing_token(x_pairing_token: str | None = Header(default=None)) -> None:
    if not pairing_token_enabled():
        return
    expected = os.getenv("BACKEND_PAIRING_TOKEN")
    if x_pairing_token != expected:
        raise HTTPException(status_code=401, detail="invalid or missing pairing token")
```

Apply as a FastAPI dependency (`Depends(require_pairing_token)`) on
`/analyze`, `/barcode/{code}`, `/recipes`, `/recipes/{recipe_id}`,
`/reference/{recipe_id}/{step_index}` - **not** on `/health` (a health
check shouldn't need a secret) and **not** on the static file mount
(serving inert HTML/JS/CSS to an unauthenticated request costs nothing and
reveals nothing sensitive - gating routes with real cost/data, not the
shell that loads them, matches the threat model from Phase 1).

**Client side**: the token has to get from the operator's head into the
browser once. `app.js`'s boot flow reads a `?token=` query-string param on
first load (present only when the operator is setting the device up),
stores it in `localStorage` (a per-viewer convenience, never sent anywhere
but this backend), and `api.js`'s `requestJson()` attaches it as the
`X-Pairing-Token` header on every call from then on, token or not (an
empty header is harmless when the backend has the feature disabled). If a
call comes back `401`, `app.js` shows a clear message ("this device isn't
paired - open the link with `?token=...` once to set it up") rather than
the generic network-trouble fallback.

`.env.example`: add `BACKEND_PAIRING_TOKEN=` (blank) with a comment
explaining it's opt-in and how to generate one (e.g. `python -c "import
secrets; print(secrets.token_urlsafe(24))"`).

**Prompt:**
> Implement `backend/app/auth.py` exactly as described, wire
> `Depends(require_pairing_token)` onto the routes listed above (not
> `/health`, not the static mount), and add `BACKEND_PAIRING_TOKEN=` to
> `.env.example` with a comment on how to generate one. On the client,
> update `api.js`'s `requestJson()` to attach an `X-Pairing-Token` header
> read from `localStorage`, and `app.js`'s boot flow to capture a `?token=`
> query param into `localStorage` on first load and show a clear
> re-pairing message on a 401 instead of the generic network-trouble
> fallback. Write backend tests covering: with the env var unset, every
> route works with no header at all (unchanged existing behavior); with it
> set, a missing/wrong header gets 401 on the protected routes and
> `/health` still works with no header. Do not commit - stop for review.

**Suggested commit message:** `feat: opt-in pairing-token auth for the backend API`

---

## Phase 3 — Rate limiting on `/analyze` and `/barcode`

**Files:** `backend/app/rate_limit.py`, `backend/app/main.py` (wire in).

No new dependency - this is a single-process backend, an in-memory sliding
window is enough and keeps the "no Docker, no build step" simplicity this
project has held to throughout.

```python
# backend/app/rate_limit.py
import time
from collections import defaultdict, deque

_WINDOWS: dict[str, deque] = defaultdict(deque)


def check_rate_limit(key: str, *, max_requests: int, window_sec: float) -> bool:
    """Returns True if the call is allowed (and records it), False if the
    caller is over the limit for this key within the window. Prunes
    timestamps older than window_sec on every call - no separate cleanup
    task needed for a single-process deployment."""
```

Apply per-client-IP (`request.client.host`) with separate, named limits:
`/analyze` (the expensive one - something like 20 requests/hour is
generous for real cooking use and stops runaway abuse) and `/barcode`
(cheaper but still a third-party proxy - something like 60/hour). On
rejection, return `429` with a `Retry-After` header. Client side: confirm
(don't change) that `api.js`'s existing retry logic already treats a 429
correctly - `withOneRetry` only retries `HttpError` with `status >= 500`,
so a 429 is correctly **not** retried today; write a test proving that
stays true rather than assuming it.

**Prompt:**
> Implement `backend/app/rate_limit.py` exactly as described, and wire it
> into `/analyze` and `/barcode/{code}` in `main.py` with the limits given
> above, returning 429 + Retry-After on rejection. Write backend tests
> covering: requests under the limit succeed, the request that crosses the
> limit gets 429, and the window actually slides (advance a mocked clock
> and confirm an old request drops out of the count). Add or confirm a
> client-side test in the existing api.js test suite proving a 429 is
> never retried. Do not commit - stop for review.

**Suggested commit message:** `feat: per-IP rate limiting on /analyze and /barcode`

---

## Phase 4 — Request size caps on `/analyze`

**Files:** `backend/app/main.py`.

Two layers, since a huge `Content-Length` shouldn't even get read into
memory to find out it's garbage:

1. A small ASGI middleware rejecting any request to `/analyze` with a
   `Content-Length` header above a generous ceiling (e.g. 15MB - base64
   overhead plus a large photo, well above `capture.js`'s own
   `MAX_EDGE`/`QUALITY`-constrained output) with `413 Payload Too Large`,
   before FastAPI parses the body at all.
2. After `base64.standard_b64decode()` succeeds in the existing `/analyze`
   handler, an explicit check on the **decoded** byte length (a
   pathological base64 string could still slip past a Content-Length
   check depending on how it's encoded) - reject over some ceiling (e.g.
   10MB decoded) with `413` before the bytes are ever handed to
   `vision.analyze_frame()`, so a paid API call is never made against an
   oversized or garbage payload.

**Prompt:**
> Add the two size-cap layers described above to `backend/app/main.py`:
> an ASGI middleware checking Content-Length before body parsing, and a
> post-decode byte-length check before calling `vision.analyze_frame()`.
> Both return 413 with a clear detail message. Write tests covering: a
> request under both limits proceeds normally, a request with an
> oversized Content-Length header is rejected before the body is read
> (assert the vision layer was never called), and a request whose decoded
> image exceeds the post-decode ceiling is rejected with 413. Do not
> commit - stop for review.

**Suggested commit message:** `feat: request and payload size caps on /analyze`

---

## Phase 5 — Dependency and secret hygiene

**Files:** `backend/scripts/check_dependencies.py`, `README.md` (new
section).

This project has no Node dependency tree at all (`PLAN.md`'s original
intro: "no build step" - the client is vanilla JS with no `package.json`),
so this is entirely a Python-side concern: `backend/requirements.txt`
against known CVEs.

```python
#!/usr/bin/env python3
"""Wrapper around `pip-audit` so the command to run is documented and
consistent, not something every developer has to remember the flags for.

Usage: python scripts/check_dependencies.py
"""
# Installs pip-audit into the current venv if missing (same "the tool
# installs what it needs" pattern as the rest of backend/scripts/), runs
# it against backend/requirements.txt, and exits non-zero on any finding
# at "high" severity or above (never silently ignore a real CVE, but don't
# fail the whole workflow on a low-severity advisory nobody's triaged yet).
```

Add a short **Security** section to `README.md`: how to run this script,
and a note to run it periodically (there's no CI pipeline in this repo to
hook it into automatically yet - be honest about that rather than implying
it's automated when it isn't).

**Prompt:**
> Implement `backend/scripts/check_dependencies.py` exactly as described
> (wraps pip-audit, installs it if missing, fails on high+ severity
> findings) and add a Security section to `README.md` documenting how and
> how often to run it, noting honestly that it isn't wired into CI yet
> because this repo doesn't have one. Run it for real against
> `backend/requirements.txt` and report what it finds - fix anything it
> flags as high+ severity if a safe version bump is available, otherwise
> just report it. Do not commit - stop for review.

**Suggested commit message:** `chore: dependency vulnerability check script`

---

## Phase 6 — Security-review checkpoint for the import/combine features

**Files:** `plans/PLAN_IMPORT_AKIS.md`, `plans/PLAN_COMBINE_RECIPES.md`
(append a note to each), `README.md` (or `DESIGN.md` - wherever the repo's
review-checklist notes belong).

`plans/PLAN_IMPORT_AKIS.md` and `plans/PLAN_COMBINE_RECIPES.md` introduce
the first untrusted external content this codebase has ever had to parse
(scraped HTML/JSON from a third-party site) - that's a qualitatively
different risk than anything else in this repo (recipes.json today is
100% hand-authored). This phase doesn't re-review those plans' code (they
may not exist yet, or may be on branches this plan doesn't touch) - it
adds an explicit, impossible-to-miss gate so that review happens before
either branch merges.

Append to both `PLAN_IMPORT_AKIS.md` and `PLAN_COMBINE_RECIPES.md`, near
the top: a short callout that this repo's `security-review` skill (or an
equivalent manual pass) must run against the branch before merging,
specifically checking: HTML/JSON parsing doesn't `eval`/exec anything from
the response, no SSRF-shaped fetches (the importer only ever talks to the
one documented host), and no path-traversal risk in how staged filenames
are derived from source data (`source_id` used directly in a file path -
confirm it's validated as safe, e.g. digits-only, before ever touching the
filesystem).

**Prompt:**
> Append a short "Security review required before merge" callout near the
> top of `plans/PLAN_IMPORT_AKIS.md` and `plans/PLAN_COMBINE_RECIPES.md`,
> naming the specific checks above (no eval/exec of parsed content, no
> SSRF-shaped requests beyond the documented host, `source_id`/filename
> path-traversal safety). Do not commit - stop for review.

**Suggested commit message:** `docs: require a security-review pass before merging the import/combine plans`

---

## Phase 7 — Full regression pass and design-log entry

**Files:** `DESIGN.md` (append a new numbered decision).

Run the complete backend test suite, confirm `pairing_token_enabled()`
being false (the default) leaves every existing test and the app's actual
runtime behavior completely unchanged - this phase is the proof that
"opt-in, off by default" was actually honored, not just intended. Append a
`DESIGN.md` decision documenting the pairing-token model and why it's
sized for a household, not a SaaS.

**Prompt:**
> Run `pytest backend/tests -q` and confirm it's fully green with
> `BACKEND_PAIRING_TOKEN` unset (the default). Start the backend with it
> unset and confirm the existing static client still works exactly as
> before with no changes needed on the client side. Then set
> `BACKEND_PAIRING_TOKEN` and confirm a request without the header is
> rejected and one with the correct header succeeds. Append a decision to
> `DESIGN.md` documenting the pairing-token auth model, the rate limits,
> and the size caps, explicit that this is sized for a single household's
> devices, not a multi-tenant service. Report what you found. Do not
> commit - stop for review.

**Suggested commit message:** `docs: document network hardening decisions`
