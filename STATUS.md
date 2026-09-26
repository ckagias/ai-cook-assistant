# Status

Where this rebuild actually stands today, and what to test next. This file
reflects real state as of this writing, not the plan's projections.

## Update: Greek hands-free fix, preferences first, short-term memory, detection-db features (uncommitted, 2026-09-26)

See DESIGN.md #27-#30. **Built and verified:**
- **Why "Γεια σου σεφ" didn't work on a real microphone:**
  - Chrome's Greek recognizer never marks results final. This was measured with the real Web
    Speech API on synthesized speech.
  - Fixed with a 1 s "words settled" stop. The real recognizer then drove this app end to end
    with no errors ("recipes", "1", "start", "next step"...).
- **The new recipe flow:** needs and preferences, then the ingredients and tools, then the steps.
  Each step has its own buttons and one-tap questions, and a per-recipe short-term memory is kept.
- **From feature/detection-db:**
  - 16 recipes, all with bilingual tools;
  - stemmed search;
  - no-cache page files;
  - the local pairing-token skip, now with a Host check;
  - detection on by default, stopping cleanly when the server has none;
  - "ready" said once;
  - two more wake spellings.
- **Every button has a spoken form**, in Greek and English (τι βλέπω, συνταγές, σκεύη, βοήθεια,
  τι κάναμε, πόση ώρα μένει, ανίχνευση).
- **Fixed along the way:**
  - camera feedback answered in English to a Greek cook - seen live, now flagged;
  - an exhausted AI quota was reported as "can't reach the server";
  - a button's hover description could cut off a command mid-sentence.
- **Tests:** 331 passing (Python + Node).
- **End to end in headless Edge**, against the live server (Gemini), with a recognizer that
  behaves like Chrome's Greek one: every step passed, from "Γεια σου σεφ θέλω να φτιάξω ροσμπίφ"
  through preferences, the tip, tools, doneness, the steps, a one-tap question, the recap and
  help, to stop/reopen/continue-from-step-3.

**Not verified yet:**
- A real microphone in a real kitchen. The Greek fix was measured with synthesized speech
  through Chrome's fake microphone.
- The Gemini free tier (5 requests/minute per model) ran out several times during testing. The
  app now says "the assistant is busy", and simple commands keep working on the device.
- Fanis's `origin/dev` (PWA) is not integrated. This branch already sends the timer notification
  it expects. On merge, add `wake.js`, `commands.js`, `timers.js` and `memory.js` to `sw.js`'s
  `SHELL_FILES`.

## Update: hands-free "Hey chef", recipe flow, deaf-friendly UI (branch `feature/hands-free-chef`, 2026-09-26)

See DESIGN.md #21-#26 for the why. **Built and verified:**
- **Wake phrase "Γεια σου σεφ" / "Hey chef"** (`static/js/wake.js`), with the talk button as a
  tap-to-listen. Common commands are matched on the device (`static/js/commands.js`), and free
  speech or typed text goes to the new `POST /voice/text`.
- **Voice text understood with any one key.** Measured live with the Gemini key on this machine
  (text only, no audio):
  - 8 of 8 real Greek/English requests got the right action:
    - "θέλω να φτιάξω ροσμπίφ" opened roast beef directly;
    - "πόσο λάδι βάζω;" was answered from the recipe;
    - "τελείωσα με το κόψιμο" became a check;
    - "βάλε δύο λεπτά ακόμα" added 120 s;
    - "το θέλω μέτρια ψημένο" set medium, target 60°C;
    - "yeah go ahead" became yes to the pending question;
  - 3-11 s each - mostly Gemini's 503s and the free tier's 5 requests/minute per model. That
    is why simple commands never leave the device.
- **Recipe flow:**
  - an overview with an ingredient checklist (tap, camera check via the new `check_ingredients`
    mode, or live detection);
  - a doneness choice for meat, with curated thermometer targets;
  - steps whose timers start only when the cook says so, several at once;
  - check -> "shall we move on?" / "add 5 minutes?" - never advances on its own;
  - cut and prep steps judged on the work.
- **Deaf / non-speaking use:** a text box for every command and question, a conversation log,
  the step and timers shown large, and alerts that stay with a flash until dismissed.
- **10 curated bilingual seed recipes** (roast beef, steak, Greek salad, lemon potatoes, oven
  chicken, tomato pasta, tzatziki + the original 3). They reach existing databases
  automatically when `recipes.json` changes.
- **End to end in headless Edge 153 against the real server (Gemini):**
  - real `app.js`, a fake camera, and scripted stand-ins for the recognizer and the speech voice;
  - 13 scenarios passed, no page errors. Among them:
    - nothing happens without the wake phrase;
    - "Hey chef, I want to make roast beef" -> overview in 4.4-13.2 s;
    - "medium", "start", "timer" and "next" are handled locally;
    - timer +1 min; the app's own voice is ignored;
    - "done" on the garlic step -> a camera check in 10-13 s, not moved on;
    - a typed reminder question gets "2 tbsp";
    - a 3-second timer -> an alert stays on screen;
    - "stop the recipe" asks first;
    - hands-free off -> the talk button still works.
- Fixed along the way:
  - **a Gemini `504 DEADLINE_EXCEEDED` ended the model fallback chain** instead of trying the
    next model (seen live; affected `/analyze` too);
  - **the seed file was hashed from one path and seeded from another** (a default argument
    bound at import time);
  - **silent recordings echoing the transcription hint** (the "Known, not fixed yet" item
    below) now count as "not heard".
- Test suite: 307 passing (Python + Node). New: `test_hands_free.py`, `/voice/text` tests in
  `test_voice.py`, `commands.test.mjs`, `wake.test.mjs`, `timers.test.mjs`, and tap-to-talk
  tests in `voice.test.mjs`.

**Not verified yet:**
- **A real microphone with real browser recognition.** Everything above used a scripted
  `SpeechRecognition`. Not yet measured:
  - how reliably Chrome/Edge's `el-GR` recognizer writes "Γεια σου σεφ" or "Hey chef" (the
    matcher accepts the Latin and Greek spellings seen in `commands.test.mjs`);
  - false wakes from a TV;
  - kitchen noise.
- **Android Chrome** beeps each time continuous recognition restarts, and it restarts often.
  Test on the tablet before relying on hands-free there.
- **On-device recognition (`processLocally`)** is used when the browser reports it available.
  No browser here did, so every run was cloud mode.
- **Firefox tap-to-talk** (records until silence) is unit-tested only, and needs `OPENAI_API_KEY`.
- **The Anthropic voice path** has never been called live (no key here).
- **The new recipes are hand-written, not cooked.** Times and temperatures follow standard
  guidance; a person should read them through like any curated recipe. The ingredient camera
  check has only seen the fake camera's pasta pot.
- **Imported recipes (Akis Petretzikis, any-URL) are still `staged`** until curated with
  `scripts/curate_recipe.py`, so hands-free search can't find them yet. That is on purpose
  (DESIGN #18): their safety fields need a human.

## Update: instant start, camera in any browser, voice commands (2026-09-26)

**Built and verified:**
- **`start.cmd` / `start.ps1`** (Windows) and **`start.sh`** (Linux, macOS, WSL):
  - setup runs only on first use or after a change (the `.run/setup-*.stamp` fingerprint);
  - one process serves both `http://localhost:8000` and `https://<LAN IP>:8443`;
  - the app window opens with the camera and microphone pre-allowed.

  Measured on this laptop: first start with the setup check took 35.9 s, a later start 5.7 s.
  Both addresses answered `/health` from one process.
- **Camera in any browser**: a refused camera gets per-browser instructions (Greek and
  English, spoken) and Start retries. Verified in real browsers:
  - Firefox with "block new requests" set (as on this machine) shows the Firefox steps;
  - Edge with the camera denied shows the site-permission steps;
  - with the laptop's real webcam, Edge ran at 1280x720 / 4.3 FPS detection and Firefox also
    started (its first camera open takes ~9 s).
- **Detection end to end in both browsers** (hand holding a knife):
  - Edge: 5.5 FPS, "Χέρι 71%, μαχαίρι 40%, ακουμπά";
  - Firefox: 4.2 FPS, same detections.
- **Push-to-talk voice commands** (`app/voice.py`, `static/js/voice.js`), verified end to end in
  headless Edge with recorded Greek speech: find recipe, pick "the first one", set a 5-minute
  timer, repeat without resetting the timer, next step, a cooking question, and an accidental
  tap. About 3.4-5.4 s per command, including a ~3 s hold.
- WSL: `setup.sh` never finished on `/mnt/c`, because unpacking torch through the Windows
  drive is too slow. The Linux venv now lives in `~/.local/share/ai-cook-assistant/`. The old
  partial `backend/.venv-linux` is left in place and can be deleted by hand.

- **Detection speed.** Under the app's continuous load this laptop throttled (the same
  inference went from ~90 ms to 385 ms). Three changes, measured together under load, took a
  frame from 318 ms to 195 ms with identical detections: letterboxing to the frame's shape
  (`DETECTOR_RECT`), hands in parallel with the detector, and a ~6 FPS cap. See DESIGN.md #17.

**Known, not fixed yet:**
- ~~**Silent recordings echo the prompt.**~~ Fixed on `feature/hands-free-chef`: a transcript
  that is mostly the hint's own words now counts as "not heard" (`voice._echoes_hint`).
- **Voice in Firefox isn't verified.** Headless Firefox recorded silence from the test's fake
  microphone.
- **`start.sh` hasn't been run end to end on WSL.** It's only syntax-checked, because a full
  Linux install needs a large download.

## Update: detection, recipe database, any-URL import, speaking buttons (branch `feature/detection-db`)

**Built and verified:**
- **Object + hand detection** (`backend/app/detection/`, `POST /detect`): pretrained models only.
  The model was chosen by `scripts/benchmark_detectors.py` on this laptop (Ryzen 5 4500U, no
  CUDA). See `backend/data/benchmarks/detector_report.md` for the numbers and caveats.
  Verified live: a real photo through the running server, and the full client in headless Edge
  with a fake camera fed from that photo. Boxes land on the object in both the desktop and
  phone layouts, and the table fills with pixel positions.
- **Detection preview** (`static/js/detect.js`): overlay colored by group, "label NN%", a table
  under the preview, FPS and latency shown. Measured about 8 FPS end to end while the benchmark
  was competing for the CPU.
- **Speaking buttons** (`static/js/a11y.js`): long-press speaks without activating, a short tap
  activates, and mouse hover speaks. Verified in headless Edge with real touch events and by
  recording what reached `speechSynthesis`.
- **SQLite recipe database** (`app/db.py`, `app/recipes.py`): seeded from `recipes.json`. The
  seed recipes round-trip exactly, and staged recipes are never served.
- **Any-URL importer** (`app/importers/generic.py`): schema.org via `recipe-scrapers`; honours
  robots.txt; idempotent; never overwrites published recipes. Tested with hand-written HTML
  fixtures only, *not yet run against a live site*.
- Fixed along the way:
  - `main` had been red (8 failing tests);
  - the importer crashed on any recipe with ingredients, and its `source_id` could escape the
    staging folder;
  - curation defaulted Greek instructions to English text and could silently overwrite a
    curated recipe;
  - a TTS command could cut off a safety alert;
  - `#video`'s height never resolved in the portrait layout, which left a black band.
- Test suite: 220 passing (Python + Node), with and without the detection dependencies.
- **Setup scripts** (`setup.sh`, `setup.ps1`, `setup-window.sh`, `setup-window.ps1`, `.cmd`
  wrappers), all run for real:
  - a re-run with nothing to do takes seconds and downloads nothing;
  - a version change keeps the old wheel in `.wheelhouse/`;
  - `setup-window` serves on the LAN over HTTPS and opens an Edge app window; closing the
    window stops the server;
  - `bash setup-window.sh` from WSL hands over to the Windows launcher;
  - a venv partly deleted by an interrupted WSL run was repaired offline with
    `sync_deps.py --repair`.

**Not verified yet:**
- A live import from a real recipe site (the fixtures cover the parser, not any site's markup).
- Detection on a **physical tablet camera in a real kitchen**: everything so far is photos and
  a fake camera. The Open Images eval set is not your kitchen; add an in-house labeled set with
  `benchmark_detectors.py --extra-dir`.
- Hand relations are 2D ("touching" = overlapping in the image) and shown visually only. Spoken
  hand alerts were deliberately left for after real-footage false-alarm rates are measured.

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
