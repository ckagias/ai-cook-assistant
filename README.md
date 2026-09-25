# AI Cooking Assistant

A voice-first cooking assistant for a tablet propped up in the kitchen. Point
the camera at what you're cooking, get spoken feedback. No screen-reading
required - it's built for someone whose hands are busy or who can't look at
the screen while cooking.

Python 3.10+, FastAPI serving both the API and a plain-HTML/JS client from
the same origin. No Docker, no Node runtime dependency, no build step.

## Quick start

```bash
./setup.sh          # creates backend/.venv, installs deps, prepares .env, runs tests
# edit backend/.env and add a provider API key
./setup.sh --run    # starts uvicorn in the foreground
```

Then open `http://localhost:8000` (or see **Tablet bring-up** below to reach
it from an actual tablet).

## Provider table

| Provider  | Env var(s)                              | Default model(s) |
|-----------|------------------------------------------|-------------------|
| Anthropic | `ANTHROPIC_API_KEY`                      | `claude-sonnet-5` (`ANTHROPIC_MODEL`) |
| OpenAI    | `OPENAI_API_KEY`                         | `gpt-5` (`OPENAI_MODEL`), reasoning effort via `OPENAI_REASONING_EFFORT` |
| Gemini    | `GEMINI_API_KEY` or `GOOGLE_API_KEY`     | comma-separated fallback chain via `GEMINI_MODEL` (default `gemini-3.7-flash,gemini-3.8-flash,gemini-3.6-flash`), retried in order on transient errors |

Select the active one with `VISION_PROVIDER=anthropic|openai|gemini`. Verify
a configured provider actually works (real model listing + a real
`check_doneness` call) with:

```bash
backend/.venv/bin/python backend/scripts/check_providers.py [photo.jpg]
```

## Tablet bring-up

1. **`adb reverse` (preferred, Android over USB)** - no certificates, no
   network config, the tablet just talks to `localhost:8000`:
   ```bash
   adb reverse tcp:8000 tcp:8000
   ```
2. **Self-signed HTTPS (fallback)** - needed for iOS, or any tablet not on
   USB. `getUserMedia`/`wakeLock` both require a secure context, so plain
   HTTP over the LAN won't work. Every browser will nag about the
   certificate on first load; accept it once per device.

Once connected, open `http://localhost:8000/probe.html` on the tablet first
and run through every section - it exercises the real camera/mic/audio
stack and the real `features.js`/`aim.js` modules before you ever open the
main app.

## Troubleshooting

- **Buttons render but do nothing** - check the browser console for a 404 on
  `js/app.js`; `mimetypes.add_type` must run before the static mount, and
  Windows registers `.js` as `text/plain` if that ordering is wrong.
- **No sound at all** - `speechSynthesis` and `AudioContext` both require a
  user gesture on iOS/Chrome; the Start button's click handler is the only
  place that unlocks them. A page reload after granting permissions once is
  usually enough if audio still seems dead.
- **Speaks in English instead of Greek** - no Greek voice is installed on
  that device/OS. `probe.html`'s "Speak Greek test phrase" button confirms
  this directly by pinning the actual voice object it found (or didn't).
- **Reference image silently never shows up** - `GET /reference/<recipe>/<step>`
  distinguishes "not declared in recipes.json" from "declared but missing on
  disk" in its 404 detail message; a typo in `reference_image` looks
  identical to the feature not working otherwise.
- **"Something changed, should I check?" never fires** - the local monitor
  needs ~3s of calibration at the *start of the current step* before it
  trusts any signal; walking away immediately after `announceStep()` runs
  skips that window.
- **Demo hangs waiting on a network call** - set `DEMO_STRICT=true`, not
  just `DEMO_MODE=true`; the latter still falls through to a live call on a
  fixture miss.

## API surface

```
GET  /health                              -> {"status": "ok", "demo_mode": bool}
POST /analyze                             -> AnalyzeResponse
GET  /recipes                             -> [{"id", "name"}]
GET  /recipes/{recipe_id}                 -> full Recipe, 404 if unknown
GET  /barcode/{code}                      -> Open Food Facts proxy, 404 if not found
GET  /reference/{recipe_id}/{step_index}  -> reference JPEG, 404 if none/missing
```

## Security

- **Pairing token**: unauthenticated by default, matching the `adb reverse`
  bring-up path. If the backend is reachable from more than the USB-tethered
  tablet (self-signed HTTPS on a LAN), set `BACKEND_PAIRING_TOKEN` in `.env`
  - see the comment above it in `.env.example` for how to generate one. See
  `backend/SECURITY_THREAT_MODEL_network.md` for the full trust-boundary
  writeup.
- **Rate limits and size caps**: `/analyze` and `/barcode` are rate-limited
  per client IP, and `/analyze` rejects oversized request bodies before and
  after base64 decoding. None of this requires configuration.
- **Dependency vulnerability check**: `python backend/scripts/check_dependencies.py`
  wraps `pip-audit` against `backend/requirements.txt` and exits non-zero on
  any known vulnerability (installs `pip-audit` into the current environment
  if it isn't already present). Run it periodically by hand - there is no CI
  pipeline in this repo to run it automatically yet.
- **Prompt-injection defense**: `backend/SECURITY_THREAT_MODEL_vision.md`
  and `DESIGN.md` #13 cover the heuristic output-injection guard on vision
  responses.

## What's still incomplete

- **Two of five reference photos are missing**: `pancake_ready_to_flip.jpg`
  and `pancake_done.jpg`. `scripts/fetch_reference_candidates.py` found no
  freely-licensed mid-cook action shot for either on Wikimedia Commons - see
  `backend/data/reference_images/SOURCES.md`. `vision.py` skips the
  reference-image comparison silently when a file is missing, so this
  degrades gracefully rather than breaking anything.
- **No demo fixtures are recorded** (`backend/data/demo_fixtures/` is
  empty). `scripts/record_fixture.py` is implemented and tested, but has
  never actually been run against a real provider response -
  `check_providers.py` has (see below), `record_fixture.py` hasn't.
  `DEMO_MODE`/`DEMO_STRICT` therefore still haven't been exercised against
  real recorded content, only against fixtures the automated test suite
  builds itself at test time.
- **Anthropic and OpenAI have not been called with a genuine, valid API
  key** in this environment - only far enough to confirm correct error
  handling (a live 401 against a deliberately invalid key). **Gemini has**:
  a real `check_doneness` round-trip against the pancake reference step
  succeeded in 14.3s (see `DESIGN.md` #9), including a real exercise of the
  `GEMINI_MODEL` fallback chain (two models returned a transient 503 before
  the third succeeded).
- **Cutlery detection (`cutlery_detection/`) is a standalone script**, not
  wired into `scene_description` mode - see its README for why and the
  ~30-minute follow-up if it's ever needed.
