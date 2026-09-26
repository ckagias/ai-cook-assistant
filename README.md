# AI Cooking Assistant

A voice-first cooking assistant for a tablet propped up in the kitchen. Point
the camera at what you're cooking, get spoken feedback. No screen-reading
required - it's built for someone whose hands are busy or who can't look at
the screen while cooking.

Python 3.10+, FastAPI serving both the API and a plain-HTML/JS client from
the same origin. No Docker, no Node runtime dependency, no build step.

## Quick start

```bash
./setup.sh          # venv + every dependency + detection models + database + .env, then tests
# edit backend/.env and add a provider API key
./setup-window.sh   # runs everything on your network and opens it as an app window
```

On Windows without Git Bash, use PowerShell. The `.cmd` files can also just be double-clicked;
they get past PowerShell's default script policy for that one run:

```powershell
.\setup.cmd           # or: powershell -ExecutionPolicy Bypass -File .\setup.ps1 [-NoDetection] [-SkipTests] [-Run]
.\setup-window.cmd    # or: powershell -ExecutionPolicy Bypass -File .\setup-window.ps1 [-NoDetection]
```

Typing `bash setup-window.sh` in a Windows terminal usually runs **WSL's** bash. The script
detects that and hands over to `setup-window.ps1`, because the camera, the app window and the
network card phones can reach are all Windows'. Each operating system gets its own
environment (`backend/.venv` for Windows, `backend/.venv-linux` for WSL/Linux), and the setup
scripts never delete one. A broken or moved environment is renamed aside and rebuilt from
`.wheelhouse/`. If an environment's files were partly deleted, repair it offline with
`backend/.venv/Scripts/python.exe backend/scripts/sync_deps.py --repair backend/requirements.txt backend/requirements-detect.txt`.

**API keys:** exactly one vision-provider key is needed, for "What is this?" and "Is it
ready?". Anthropic, OpenAI or Gemini all work; pick one with `VISION_PROVIDER` in
`backend/.env`, e.g. `VISION_PROVIDER=openai` plus `OPENAI_API_KEY=...`. Detection, the
recipe importer and the speaking buttons need no key. `backend/.env` is gitignored; keys go
there, never in `.env.example`.

`setup.sh` is safe to re-run:
- Anything already installed at the required version is **not downloaded again** (a re-run
  with nothing to do takes seconds).
- When a required version changes, only that package is fetched. The version it replaces is
  kept as a wheel in `.wheelhouse/`; files there are never deleted, so an older version can be
  reinstalled offline with `pip install --no-index --find-links .wheelhouse <name>==<version>`.
- Model files under `backend/models/` are only ever added.

Flags: `--no-detection` (skip the ~1 GB detection stack), `--skip-tests`, `--run` (start the
server on localhost afterwards). Detection needs Python 3.11 or 3.12 (MediaPipe has no 3.13
wheels yet); setup prefers those and otherwise installs the base app only.

### Run it as an app on your network

`./setup-window.sh` runs setup (without tests), then:
1. serves everything at `https://<this machine's LAN IP>:8443`. HTTPS is required because
   browsers only allow the camera on a non-localhost address over HTTPS. The self-signed
   certificate is generated for that IP and kept in `backend/certs/`.
2. turns on the pairing token, since the server is now reachable from the network (it's
   generated into `backend/.env` if none is set);
3. opens the app in its own Edge/Chrome **app window**: no address bar, its own taskbar entry,
   its own profile. That window trusts exactly this certificate and nothing else.
4. prints a link for phones and tablets on the same Wi-Fi. They show a certificate warning
   once; accept it.

Closing the app window stops the server. On Windows, allow Python through the firewall on
private networks when asked, or phones can't connect.

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

## Object and hand detection (optional)

A pretrained detector (nothing is trained) finds cutlery, cookware, appliances, ingredients
and some dishes, and MediaPipe finds hands, so the app knows what a hand is **touching**,
hovering **over**, or **near**. It runs on the laptop, not in the cloud: frames never leave
the machine, and there's no per-call cost.

1. `./setup.sh --with-detection` (or `pip install -r backend/requirements-detect.txt`).
2. Pick the model by measurement on *your* machine:
   ```bash
   python backend/scripts/fetch_eval_set.py          # ~1,000 Open Images photos, ~150 MB
   python backend/scripts/benchmark_detectors.py     # ~1 h on a laptop CPU
   python backend/scripts/benchmark_detectors.py --retime-finalists 4
   ```
   It prints the `DETECTOR_*` / `HANDS_BACKEND` lines for `backend/.env`; the reasoning is in
   `backend/data/benchmarks/detector_report.md`.
3. Set `DETECTION_ENABLED=true` and start the server. Open `http://localhost:8000/?detect=1`
   (or tap **Ανίχνευση** / **Detection**): boxes with confidence appear over the camera
   preview, colored by group, with a table underneath showing each object's position (x, y
   in the sent frame), size, and which hand touches it.

The vocabulary (`backend/app/detection/vocabulary.json`) is one list shared by the detector,
the preview and the recipe importer. With a recipe open, detection narrows to that recipe's
ingredients and equipment plus hands, core cookware and hazards.

Limits, stated plainly:
- The camera has no depth. "Touching" means overlapping in the image, and hand relations are
  shown visually only. They are never spoken as a safety guarantee.
- The cooking-state classes (boiling water, fried egg, ...) are experimental. Doneness is still
  judged by `/analyze`.
- Ultralytics code and weights are **AGPL-3.0**: offering the app to others over a network
  means publishing its source (or buying an Ultralytics license).

## Recipe database and importing recipes

Recipes live in a local SQLite file (`backend/data/cook.db`, gitignored). It's created and
seeded from `backend/data/recipes.json` on first start. No database server is needed.

```bash
# any site that publishes schema.org recipe data (most recipe sites do)
python backend/scripts/import_recipes.py url --urls https://example.com/some-recipe
python backend/scripts/import_recipes.py url --sitemap https://example.com/sitemap.xml --pattern /recipe/ --limit 20

python backend/scripts/curate_recipe.py --list          # staged, not yet reviewed
python backend/scripts/curate_recipe.py s-1a2b3c4d5e     # review and publish one
python backend/scripts/curate_recipe.py --export        # write published recipes back to recipes.json
```

The importer stores steps, ingredients (with parsed quantity/unit), equipment (listed or
inferred from the steps), times, servings, nutrition, author and source URL. Imported recipes
are **staged**: the app never serves them until a human has curated the safety-relevant fields
(which steps are checkable, which contain raw protein) with `curate_recipe.py`. The importer
also:
- honours `robots.txt`;
- identifies itself honestly (the browser User-Agent is opt-in);
- won't re-fetch a page within 7 days;
- never overwrites a recipe that has already been published.

Scraped text and photos belong to their authors. Attribution is stored, but this is for
personal or demo use; republishing needs the site's permission.

## Speaking buttons

Every big button says what it does before you press it:
- **Long-press** (phone/tablet): it speaks and does *not* activate. A normal tap still works.
- **Mouse hover** (PC demo): it speaks after about a quarter of a second.
- **Keyboard focus** (Tab, Bluetooth remote): it speaks when the button is focused.

Screen-reader (TalkBack) users can turn this off per device with `?speakButtons=0`.

## API surface

```
GET  /health                              -> {"status": "ok", "demo_mode": bool}
POST /analyze                             -> AnalyzeResponse
POST /detect[?recipe_id=...]              -> DetectResponse (raw image/jpeg body, <= 2 MB); 503 if detection is off
GET  /recipes                             -> [{"id", "name"}]   (published recipes only)
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
