# Status

Where this rebuild actually stands today, and what to test next. This file
reflects real state as of this writing, not the plan's projections.

## What's built and verified

All 23 phases of the rebuild plan are implemented:

- **Backend**: FastAPI app, recipe schema/knowledge base, demo fixture cache,
  Open Food Facts barcode proxy, the three-provider vision seam, `/analyze`
  with both backend-enforced safety rules, full route set.
- **Client**: static markup/styling, one-gesture unlock + four-level audio
  priority stack, frame capture + HTTP client, illumination-invariant
  feature extraction, local sigma-based progress monitor, audible
  camera-aiming assist, recipe-stepping session with absolute-deadline
  timers, and `app.js` wiring all of it together.
- **Diagnostics**: `probe.html` (dynamically imports the real
  `features.js`/`aim.js`, not a reimplementation), client-JS checks run
  from pytest.
- **Tooling**: `setup.sh`, `check_providers.py`,
  `record_fixture.py`/`add_reference.py`, `fetch_reference_candidates.py`,
  `check_dependencies.py` (`pip-audit` wrapper - currently zero findings
  against `requirements.txt`).
- **Security**: opt-in pairing-token auth, per-IP rate limiting and request
  size caps on `/analyze`/`/barcode`, and a heuristic output-injection guard
  on every vision response (`backend/SECURITY_THREAT_MODEL_network.md`,
  `backend/SECURITY_THREAT_MODEL_vision.md`, `DESIGN.md` #13 and #15).
- **Data**: 3 of 5 reference photos installed from Wikimedia Commons (see
  `backend/data/reference_images/SOURCES.md` for the 2 that are still
  missing and why).
- **Docs**: this file, `README.md`, `DESIGN.md`.
- **Stretch**: standalone cutlery detection utility, not wired in.

Test suite: 46 backend pytest tests passing (safety rules, routes, demo
mode, vision failure paths, the real per-SDK schema normalizer regression
test). 2 client-side `.test.mjs` suites passing with real measured numbers
(see `DESIGN.md` #6 for the `features.test.mjs` figures).
`test_client_js.py` skips cleanly when `node` isn't on `PATH` and passes
fully when it is - both paths verified directly (this dev environment
didn't have Node preinstalled).

`app.js`'s wiring was verified with a throwaway integration harness (shimmed
DOM/browser surface, real sibling modules) rather than a committed test, per
the plan; it caught and fixed a real bug in the harness itself, not the app
code.

## Real bugs found and fixed during this rebuild

Worth listing because they're exactly the kind of cross-file consistency
issue that's easy to miss when phases are built one file at a time:

- `features.js` computed `Aannulus` but never attached it to the returned
  object, even though `monitor.js`'s motion-veto logic (written one phase
  later) reads `row.Aannulus`. Fixed by exposing it alongside `Acentre`.
- `test_smoke.py` imported via `from backend.app import ...`, which only
  resolves when pytest is invoked from the repo root - but `setup.sh`
  (correctly) `cd`s into `backend/` first, so `backend` isn't importable
  from there, only `app` is (the convention every other file already
  follows). `setup.sh`'s own first real run caught this.
- `fetch_reference_candidates.py`'s license filter checked for the literal
  substring `"cc-by"`, but Wikimedia's actual `LicenseShortName` values use
  a space (`"CC BY-SA 4.0"`), not a hyphen - every genuinely reusable CC-BY
  file was being silently rejected. Also extracted a candidate's file
  extension from the raw URL including its query string, producing garbage
  filenames like `candidate_1.org&utm_campaign=...` (and an `&` in a
  filename that then breaks the exact copy-pasteable `add_reference.py`
  command the script prints). Both fixed and re-verified against the real
  Commons API with actual downloads eye-checked.

## What hasn't been tested here

- **Anthropic and OpenAI still have no successful live call.** Both have
  only been exercised far enough to confirm error handling - a deliberately
  invalid key correctly surfaced as a real 401, reported as `FAIL` by
  `check_providers.py` without crashing the run.
- **Gemini now does.** With a real `GEMINI_API_KEY`, `check_providers.py`
  completed a genuine `check_doneness` round-trip against the pancake
  reference step in 14.3s, and a full `/analyze` request through the
  running backend (with pairing-token auth enabled) returned a correct,
  honest low-confidence response for a synthetic test image. That run also
  exercised the `GEMINI_MODEL` fallback chain for real: the first two
  models hit a transient 503 before the third succeeded. See `DESIGN.md`
  #9 for the timing and fallback detail.
- **No demo fixtures recorded.** `record_fixture.py` is implemented and its
  validation logic (rejects a non-schema-valid response, rejects an empty
  `spoken_response`, correct `{mode}__{recipe}__{step}.json` /
  `{mode}.json` naming) is unit-tested by monkeypatching
  `vision.analyze_frame`, but no fixture recorded from a real provider
  response exists in `backend/data/demo_fixtures/` yet.
- **No real device testing.** Camera aiming, the acoustic gate, wake lock
  re-acquisition on `visibilitychange`, and the monitor's calibration
  against real kitchen lighting have all been verified against synthetic
  painted-canvas shims in Node, never a physical camera or a real stove.
  `probe.html` exists specifically to close this gap on an actual tablet.
- **`cutlery_detection/detect.py` has not been run.** `ultralytics`/`torch`
  weren't installed (deliberately - see its README), so only a syntax
  check has been done on it.

## What to test next, in order

1. ~~Configure one real provider API key and run `check_providers.py` for
   real~~ - done for Gemini (see above). Do the same for Anthropic and
   OpenAI once a key for either is available.
2. Record real demo fixtures with `record_fixture.py`, at minimum
   `identify.json` and a `check_doneness` fixture for `scrambled_eggs`/1.
3. Shoot or fetch the two missing pancake reference photos.
4. `adb reverse tcp:8000 tcp:8000` to a real Android tablet, open
   `/probe.html` first, run every section, then open the main app and walk
   through a full recipe start-to-finish with the camera pointed at a real
   stove.
5. Commit whatever real-hardware bugs that surfaces as their own `fix:`
   commits - that part isn't scriptable in advance.
