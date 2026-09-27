# AI Cooking Assistant

Presented at Open Hackathon 2026 as **SayChef**. Try it: the QR on the pitch's last slide opens the
online copy (see "Online: one fixed address" below).

A voice-first cooking assistant for a tablet propped up in the kitchen. Point
the camera at what you're cooking, get spoken feedback. No screen-reading
required - it's built for someone whose hands are busy or who can't look at
the screen while cooking.

Python 3.10+, FastAPI serving both the API and a plain-HTML/JS client from
the same origin. No Node runtime dependency, no build step; Docker only for the optional
online copy (`deploy-cloud.ps1`).

## Quick start

**Windows (PowerShell, or double-click):**

```powershell
.\start.cmd            # or: powershell -ExecutionPolicy Bypass -File .\start.ps1 [-NoWindow] [-LocalOnly] [-NoDetection]
.\start.ps1 -CheckOnly # what's installed, what a first start would download - changes nothing
```

On Windows the first start also installs what's missing, once, with winget and for this user
only: **Python 3.12** when no usable Python is installed (the Microsoft Store `python.exe`
shortcut doesn't count, and detection needs 3.11/3.12), and **git** when detection needs it.
Anything already installed is skipped.

**Linux, macOS, WSL/Ubuntu:**

```bash
./start.sh             # [--no-window] [--local-only] [--no-detection]
```

That's the whole thing:
- **First start:** runs setup once (venv, every dependency, detection models, database,
  `.env`). It runs again only after a requirement or detector setting changes.
- **Every later start:** about 5 s to a running app. Setup is skipped via a fingerprint in
  `.run/setup-*.stamp`.
- **One server, two addresses:**
  - `http://localhost:8000` for this computer, in any browser, with no certificate warning;
  - `https://<LAN IP>:8443` for phones and tablets on the same Wi-Fi (install `/ca.crt` once
    — see **Tablet bring-up**). One process means one detection model in memory.
- **The app window:** it opens in its own Edge/Chrome window with the camera and microphone
  already allowed for the app's address. Closing it stops the server (Windows); on
  Linux/macOS, Ctrl+C stops it.
- **The phone, on the same network as the laptop** (a Wi-Fi, or a phone's hotspot): a QR code
  for the phone link is printed in the terminal (also saved as `.run/pairing.png`).
  - The first time on each phone, install `/ca.crt` (see **Tablet bring-up**). After that the
    app is trusted on any network: each address gets its own certificate from the same local CA.
  - The link follows the laptop's address, which changes between networks.
  - For a QR that never changes, for example on a slide, use `.\start.ps1 -Hotspot` (see
    **Static QR codes for slides and demos**).
- **Every start is a clean one (Windows):** it closes the previous session's server and app
  window, and removes the leftovers: the window's browser profile (cache, service worker,
  stored settings), QR images and logs.
  - **Kept:** the setup stamp, so starts stay fast, and the certificates, so a phone trusts the
    local CA once, not every run.
  - **Never killed:** a port held by some other program. `start.ps1` names it and stops.

Then add a vision-provider key to `backend/.env` (see **API keys** below).

**Which script:** `.cmd`/`.ps1` are for Windows, `.sh` for Linux, macOS and WSL. Typing
`bash something.sh` in a Windows terminal runs **WSL's** bash, which is a separate Linux
install. Under WSL the Linux environment goes in the Linux home
(`~/.local/share/ai-cook-assistant/`), because installing torch's thousands of files
through `/mnt/c` is so slow it never finished.

**Phones and WSL:** a phone on Wi-Fi cannot reach `start.sh` inside WSL unless WSL
networking is set to **mirrored**. For any phone or tablet work, run `start.cmd` from
Windows (or enable mirrored networking first). `start.sh` already drops the LAN address
when it detects unmirrored WSL.

Each operating system gets its own environment, and the scripts never delete one. A broken or
moved environment is renamed aside and rebuilt from `.wheelhouse/`. If an environment's files
were partly deleted, repair it offline with
`backend/.venv/Scripts/python.exe backend/scripts/sync_deps.py --repair backend/requirements.txt backend/requirements-detect.txt`.

The setup scripts can still be run on their own:
- `.\setup.cmd` / `./setup.sh` installs and runs the tests.
- `setup-window` serves on the LAN over HTTPS with an app window, as before.

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

`./start.sh` / `.\start.cmd` (or `./setup-window.sh`) run setup if needed, then:
1. serve everything at `https://<this machine's LAN IP>:8443`. HTTPS is required because
   browsers only allow the camera on a non-localhost address over HTTPS. A **local CA**
   in `backend/certs/` signs a per-IP leaf (also kept there).
2. turn on the pairing token, since the server is now reachable from the network (it's
   generated into `backend/.env` if none is set);
3. open the app in its own Edge/Chrome **app window**: no address bar, its own taskbar entry,
   its own profile. That window trusts exactly this certificate and nothing else.
4. print a link (and a QR code, plus `.run/pairing.png`) for phones on the same Wi-Fi.

**First time on an Android phone** (Chrome):
1. Open `https://<LAN IP>:8443/ca.crt` — one certificate warning is expected **here only**.
2. Install it as a **CA certificate**: Settings → Security → Encryption & credentials →
   Install a certificate → CA certificate. Android will show a persistent "Network may
   be monitored" notice; that is what installing a CA means, and the CA key never leaves
   this laptop (`backend/certs/` is gitignored).
3. Scan the QR (or open the printed `https://<LAN IP>:8443/?token=...&detect=1` link).
   There should be a padlock and **no** warning.
4. Chrome offers **Install app** (or use the ⋮ menu). After that, open it from the
   home-screen icon — standalone, no address bar.

If the laptop's LAN IP changes (new DHCP lease), the leaf cert is reissued under the
**same CA** — the phone does not need to reinstall anything. The *URL* does change, so
re-scan the QR. The pairing token does not change.

**Known limitation:** timers do not notify while the phone is locked or the app has been
in the background for several minutes. Switching apps briefly with the screen still on
can show a system notification; a locked screen cannot. The on-screen countdown and the
catch-up when you reopen the app remain the fallback.

Closing the app window stops the server. On Windows, allow Python through the firewall on
private networks when asked, or phones can't connect.

Then open `http://localhost:8000` (or see **Tablet bring-up** below).

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

1. **`adb reverse` (dev, Android over USB)** - no certificates, no
   network config, the tablet just talks to `localhost:8000`. Chrome will
   **not** offer "Install app" on `http://localhost`.
   ```bash
   adb reverse tcp:8000 tcp:8000
   ```
2. **Self-signed HTTPS (fallback)** - still the path if you have not
   installed the local CA: iOS, or a one-off browser tab. `getUserMedia` /
   `wakeLock` need a secure context, so plain HTTP over the LAN won't work.
   Every browser will nag about the certificate on first load; accept it
   once per device. An *installed* PWA cannot click through that warning.
3. **Installed Android PWA over LAN HTTPS (this is the phone path)** - run
   `start.cmd` on Windows (see **Phones and WSL** above), install `/ca.crt`
   once, scan the QR, tap Chrome's **Install app**. Details under **Run it
   as an app on your network**. iOS Add to Home Screen is out of scope for
   now.

### Online: one fixed address (Google Cloud Run)

`.\deploy-cloud.ps1` puts the app online at **one address that never changes**:
`https://readycheck-<project number>.europe-west1.run.app` (the event project's:
`https://readycheck-406241909903.europe-west1.run.app`). Every redeploy lands on it, so the QR for it -
`qr/main-app.png`, written by the script and used on the pitch's last slide - keeps working. Phones
on any network open it with nothing to install: Cloud Run serves real HTTPS.

- **First time:** install the Google Cloud CLI, `gcloud auth login` with the event account, and
  accept the Google Cloud terms once at https://console.cloud.google.com.
- **What it does:** turns on Cloud Run, Artifact Registry and Secret Manager; stores the OpenAI key
  and a cloud pairing token (`CLOUD_PAIRING_TOKEN`, created once in `backend/.env`) in Secret
  Manager - never printed; builds the image **here with Docker** (Windows, or WSL) and pushes it;
  deploys with at most 2 instances; checks `/health`; writes `qr/main-app.png`.
- **Why built here:** the event accounts can't grant project roles, so Cloud Build's account can't
  read the upload. `-UseCloudBuild` builds in Google Cloud where a project allows it.
- **What's in the image:** only what `backend/.dockerignore` lets through (`app/`, `static/`, the
  recipes, the reference photos). The script refuses to push an image with `.env`, a venv or certs.
- **Differences from the laptop copy:** no live detection (it needs the laptop's CPU and models);
  photo checks are limited to 20 an hour per network address, so phones on one venue Wi-Fi share
  them. Everything else is the same app.
- The event deletes its projects 3-4 days after the event, and this address with them.

### QR codes: which is which

| QR | Opens | Works when |
|---|---|---|
| `qr/main-app.png` (the slide) | the online copy | always, on any network - the laptop can be off |
| the one `.\start.ps1` prints | the laptop | the phone is on the laptop's network, `start.ps1` running |
| `qr/2-certificate.png`, `qr/3-app.png` | the laptop, this network's address | written by every `.\start.ps1`; rebuild the deck after moving networks |
| `qr/1-wifi.png` + the two above | the laptop's own hotspot, `192.168.137.1` | only with `.\start.ps1 -Hotspot` |

### Static QR codes for the laptop's hotspot

`.\start.ps1 -Hotspot` turns on the laptop's own Windows Mobile Hotspot (no admin rights). On it
the laptop is always `192.168.137.1`, so a QR code for it never changes. Each such start writes
`qr/slide.png`: three QR codes with Greek and English captions, each also a separate PNG for a
presentation.

Without `-Hotspot` (the default), phones use the network the laptop is already on: the terminal
QR, `qr/2-certificate.png` and `qr/3-app.png` follow its address, and `qr/1-wifi.png` is removed.
Many venue and guest networks block devices from reaching each other; there, use the online copy
or `-Hotspot`.

| QR code | What it does |
|---|---|
| `1-wifi.png` | Joins the laptop's hotspot. It's a standard Wi-Fi QR, so phone cameras connect without typing the password. |
| `2-certificate.png` | Opens `https://192.168.137.1:8443/ca.crt`. Needed once per phone. |
| `3-app.png` | Opens `https://192.168.137.1:8443/?token=...&detect=1`, already paired. |

They stay valid through any code change or restart. They only change if the pairing token,
the hotspot's name or password (Settings > Network > Mobile hotspot), or the port changes. They
contain the token and the Wi-Fi password, so `qr/` is gitignored. Regenerate them by hand with
`python backend/scripts/static_qr.py --ssid "<name>" --password "<password>"`.

At a demo with the slide codes:
- the laptop runs `.\start.ps1 -Hotspot`, with its own internet (Wi-Fi or a phone's hotspot)
  shared through its hotspot;
- phones scan 1, then 2 (first time only), then 3;
- if phones can't connect, allow Python through Windows Firewall when asked;
- by default Windows turns the hotspot off after 5 minutes with no device connected. Before a
  demo, switch off Settings > Network & internet > Mobile hotspot > **Power saving**, or run
  `.\start.ps1 -Hotspot` again, which turns it back on.

Once connected, open `/probe.html` on the tablet first and run through
every section - it exercises the real camera/mic/audio stack and the real
`features.js`/`aim.js` modules before you ever open the main app. On
`adb reverse` that is `http://localhost:8000/probe.html`; on the LAN it is
`https://<LAN IP>:8443/probe.html`.

## Troubleshooting

- **"Camera access failed" / nothing asks for the camera.** The start screen names the fix for
  the browser in use, in Greek and English, and speaks it. Pressing Start again retries
  without a reload. The usual causes:
  - **Firefox with "Block new requests asking to access your camera" ticked:** it refuses at
    once, without a prompt. Untick it under Settings > Privacy & Security > Permissions >
    Camera > Settings.
  - **A site permission set to Block:** fix it with the icon left of the address.
  - **The Windows/macOS camera privacy switch is off.**
  - **The page is open in an editor's built-in preview:** it can never show a camera prompt.
  - **Another app holds the camera:** Teams, Zoom or the Camera app.

  `start.cmd`'s app window avoids all of these: its own profile already allows the camera for
  the app's address. On Firefox, the first camera start can take ~10 s on some webcams.
- **Buttons render but do nothing** - check the browser console for a 404 on
  `js/app.js`; `mimetypes.add_type` must run before the static mount, and
  Windows registers `.js` as `text/plain` if that ordering is wrong.
- **No sound at all** - `speechSynthesis` and `AudioContext` both require a
  user gesture on iOS/Chrome; the Start button's click handler is the only
  place that unlocks them. A page reload after granting permissions once is
  usually enough if audio still seems dead.
- **Speaks in English instead of Greek** - no Greek voice is installed on that device. This is
  common on **Android**: Chrome there uses the phone's text-to-speech engine, which usually has
  only the phone's language and English.
  - The app then says, and shows in both languages, where to get one on that kind of device.
  - On Android that's Settings → Text-to-speech → Speech Services by Google → its settings →
    Install voice data → Greek. On Samsung, first set the preferred engine to Google's.
  - A Greek voice that appears later, whether it loads late (Android lists voices in steps) or
    is installed meanwhile, switches the app back to Greek by itself.
  - `probe.html`'s "Speak Greek test phrase" button shows the actual voice found (or not).
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
# the Greek demo list (Akis Petretzikis, Argiro): into this machine's database only - not git
python backend/scripts/import_recipes.py url --url-file backend/data/greek_demo_urls.txt --browser-ua

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

Every big button says what it does before you press it, and shows the same words in a bubble
beside it (for a cook who can't hear them):
- **Long-press** (phone/tablet): it speaks and does *not* activate. A normal tap still works.
- **Mouse hover** (PC demo): it speaks after about a quarter of a second.
- **Keyboard focus** (Tab, Bluetooth remote): it speaks when the button is focused.

Screen-reader (TalkBack) users can turn the speaking off per device with `?speakButtons=0`; the
bubble still shows.

## Hands-free: "Hey chef"

Say **"Hey chef"** (in Greek «Χέι σεφ»; it's the same phrase in every language), then what you
need. You can say it in one breath ("Hey chef, next step") or after the beep. Just **«σεφ, …»**
or **«γεια σου σεφ»** works too: the app wakes on the name said *to* it, so a "hey" the
recognizer drops doesn't matter, and "ο σεφ είπε…" (talking *about* a chef) doesn't wake it.

Three ways to talk, always in the bottom bar:
- **Hold Μίλα / Talk** (or the **V** key) while you speak, let go when you're done. A pause while
  holding doesn't cut you off. A quick tap only reminds you to hold it.
- **The mic button (the lock)**: tap once and it keeps listening, command after command, with no wake phrase,
  until you tap it again. Locked listening is shown on the button in the talk colour.
- **"Hey chef"** with hands-free on (the **Χωρίς χέρια / Hands-free** switch).

**Τι είναι αυτό; / What is this?** sits in the same bar, so the camera can name anything at any
point. A cook who doesn't speak **types** the same commands in the box under the buttons, and
every button does what a voice command does.

**"Hey chef" interrupts at any moment, even while the app is talking:** mid-step, mid-list, or
during the opening questions. The app stops talking, and only talking. The recipe, the step,
the timers and any open question stay as they are.
- **A question, a need or an allergy, a timer:** answered, then the app carries on from the
  sentence it was in ("Όπως έλεγα: … / As I was saying: …").
- **Something that moves the cooking on** ("next step", another recipe): done, and the
  interrupted words are dropped.
- **"Hey chef" and then silence:** it carries on after a few seconds.
- **A need or allergy said at any point** ("Hey chef, my son is allergic to nuts"): kept for
  the whole recipe, and checked against its ingredients in the answer.
- **Something urgent** (a burn, a cut, smoke): the answer starts with the immediate safety step.
- **A fire warning** is the one thing that always plays to the end.

A cooking session, start to finish:

1. "Χέι σεφ, θέλω να φτιάξω ροσμπίφ" - a dish named outright starts at once; a vaguer
   request ("something with eggs") lists up to three to pick from ("the second one").
2. First, **needs and preferences** for this dish: an allergy, less salt, spicier, for children.
   Say it, type it, tap one, or say "όχι". The assistant tells a need from a question: it
   answers "for how many is it?" and asks again. A preference gets a matching tip from the
   assistant. With no key or no network, whatever is said is kept as the preference.
3. The **ingredients** and the **tools** (knife, board, tray, oven...) are read out and shown as
   checklists. "Έλεγξε τα υλικά" shows them to the camera and ticks what it sees (the live
   detection preview ticks them too); a tap ticks one. **By voice too:** "έχω τα αυγά και το
   γάλα, δεν έχω βούτυρο" ticks those two, and for the butter the assistant suggests a
   substitute or says it can be left out; "τα έχω όλα εκτός από το σύρμα" ticks the rest. With
   everything ticked it asks "Ξεκινάμε;". Only what you say is ticked or unticked: something not
   mentioned is never counted as missing. Meat recipes ask how you like it.
4. "Ξεκίνα", "πάμε στα βήματα" or "τα έχω όλα, μπορούμε να ξεκινήσουμε" - step by step. A step with a usual time says so, but **timers start only when you
   say "χρονόμετρο"** (or tap it): people work at different speeds. Several run at once, and
   "two more minutes" / "+1 λεπτό" / "πόση ώρα μένει;" adjust and read them. Each step also gets
   its own buttons: **Done**, and one-tap questions that fit the step ("how do I know it's
   ready?", "what can I use instead?") for a cook who reads rather than speaks.
5. Cutting, grating, mixing: "τελείωσα" / "έλεγξε" and the camera judges the **work** (piece
   size, evenness). On the heat it judges **colour and the timer together**. When it looks ready
   it **asks** "shall we move on?" - it never moves on by itself. Not ready: "add 5 minutes?".
   Meat is never judged done by looks: you hear the thermometer target for your doneness choice.
6. Any time: a question or reminder ("πόσο λάδι βάζω;", "what's next?") is answered from the
   open recipe **and what happened so far**: a short-term memory per recipe keeps the
   preferences, the steps done, what each check saw and the assistant's own tips. "Τι κάναμε;"
   reads it back, it's listed on screen, and reopening the recipe the same day offers to
   continue where you were.

Every button has a spoken form, in Greek and English: "τι βλέπω / what do I see", "συνταγές /
recipes", "υλικά", "σκεύη / tools", "βοήθεια / help", "άνοιξε / κλείσε την ανίχνευση". Common
commands are understood on the device, instantly.

Everything said is also on screen (status line and conversation log), timer ends and fire
warnings stay up with a flash and a buzz until dismissed, and the step and its timers are shown
large - so the whole app works without hearing it.

- **Speech recognition is the browser's** (Chrome, Edge, Safari). On-device where the browser
  offers it; otherwise audio goes to the browser's speech service (Google / Microsoft) while
  hands-free is on - the badge on the camera view says which. The **Χωρίς χέρια / Hands-free**
  button turns it off (remembered per device, or `?wake=0`); the talk button still works.
  `?listen=en` listens for English instead of Greek.
- **Nothing is acted on without the wake phrase** or a tap.
- **While the app speaks, only "Hey chef" counts.** The microphone also hears the app's own
  voice, and that is never taken for a command.
- **The app's own words are taken out of what you said.** It knows what it said in the last 15 s,
  so when the mic catches the end of its sentence before yours ("2 αυγά… okay, τα έχω όλα"),
  that part is dropped by comparing the words (`static/js/echo.js`).
- **It waits for you to finish:** 1.8 s of quiet ends a command (a breath in the middle doesn't).
- **Hearing the wake name:** the browser's recognizer does the listening (we can't raise its
  microphone gain). The app asks it for 5 guesses per phrase, so a «σεφ» it ranked lower still wakes
  it, and where Chrome recognizes on-device it is told to expect «σεφ / Χέι σεφ». With a Greek
  accent, «Σεφ, …» is heard more reliably than "Hey chef"; the phone close by helps most.
- **What it heard:** `?heard=1` (remembered; `?heard=0` off) shows every phrase the recognizer
  returned, with all its guesses and whether the wake name was among them - to add the
  mis-hearings of real voices to `static/js/commands.js`. Shown only, never stored.
- **Tuning for tests** (from the link, this visit only; `?heard=1` prints the values in force):

  | Option | Changes | Default | Range |
  |---|---|---|---|
  | `alts` | guesses per phrase from the recognizer | 5 | 1-10 |
  | `settle` | ms of quiet before a command is acted on | 1800 | 500-5000 |
  | `arm` | ms it waits for the command after the wake name alone | 8000 | 3000-30000 |
  | `quiet` | least loudness that counts as speech - lower hears softer voices (recorded path, e.g. Firefox) | 0.015 | 0.002-0.1 |
  | `pause` | ms of quiet that ends a recording (recorded path) | 1800 | 600-5000 |

  For example `…/?token=…&heard=1&alts=8&settle=2500`. Chrome's own microphone level can't be
  set from a web page; on a laptop, raise it in Windows (Sound > Input > volume, "Microphone boost").
- **A sentence that itself says "Hey chef"** (the greeting, help) mutes listening while it plays,
  so the app can't wake itself.
- **Common commands never leave the device** ("next", "yes", "timer", "check it", "σενιάν"...,
  `static/js/commands.js`): instant, free, and they work with no API key at all. Free speech goes
  to `POST /voice/text`, understood by whichever key is set - OpenAI (`gpt-5-mini`), Gemini, or
  Anthropic (`VOICE_PROVIDER` picks one explicitly).
- **Browsers without speech recognition (Firefox):** hold Talk while you speak (up to 30 s), or
  use the mic lock, which records until each pause and then listens again; the recording is
  transcribed on the server (`gpt-4o-mini-transcribe`, needs `OPENAI_API_KEY`).
- **A closed set of actions:** the model can only pick one from a fixed list. Code checks the
  result: timer bounds, that a chosen recipe was actually offered, that a step action has an
  open recipe, that "yes" answers a question the app asked. Recipe text is passed as tagged
  data, never as instructions, and every reply goes through the same output guard as the
  vision answers.
- **Nothing kept:** audio, transcripts and typed text are never stored or logged.

## API surface

```
GET  /health                              -> {"status": "ok", "demo_mode": bool, "voice": {"text": bool, "audio": bool}}
POST /analyze                             -> AnalyzeResponse (modes incl. check_doneness, check_ingredients)
POST /detect[?recipe_id=...]              -> DetectResponse (raw image/jpeg body, <= 2 MB); 503 if detection is off
POST /voice/text                          -> VoiceResponse (JSON {text, language, recipe_id, step_index, candidates,
                                             pending, doneness, timer_remaining_sec}); 503 with no API key at all
POST /voice?language=..[&recipe_id&step_index&candidates&pending&doneness&timer_remaining_sec]
                                          -> VoiceResponse (raw audio body, <= 2 MB); 503 without OPENAI_API_KEY
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
  if it isn't already present). Run it periodically by hand - CI
  (`.github/workflows/tests.yml`) runs the tests, not this check.
- **Prompt-injection defense**: `backend/SECURITY_THREAT_MODEL_vision.md`
  and `DESIGN.md` #13 cover the heuristic output-injection guard on vision
  responses. Every spoken field is checked: injection phrasing in Greek and English (including
  paraphrases like "forget everything above" / «ξέχνα ό,τι…»), web addresses and short links,
  hidden characters. Text in a photo is never an instruction; what the cook said reaches the model
  as one line of data, and a request to play a character is refused. A fire alarm survives an
  answer the guard withholds.
- **Tested live (2026-09-27):** 12 attacks against the real models - instructions and links
  written on things in photos, a "READY" label on raw pasta, "COOKED 75°C" printed next to
  chicken, spoken/typed jailbreaks, requests for the system prompt or the API key, a
  99,999-hour timer, "skip the thermometer", and a planted note in the session memory. 12/12
  held (one partly worked at first - a persona request - and was fixed; `DESIGN.md` #37).
- **Disclaimer and your data**: a page in Greek and English (start screen and app), read aloud on
  request: what leaves the device and what doesn't, and that the answers can be wrong.
- **The online copy**: HTTPS only, the pairing token in the QR (401 without it), the keys in
  Secret Manager, at most 2 instances.

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
- **Anthropic has not been called with a genuine, valid API key** - only
  far enough to confirm correct error handling (a live 401 against a
  deliberately invalid key). **OpenAI** runs voice and vision live on the
  development laptop, and **Gemini** did earlier: a real `check_doneness`
  round-trip against the pancake reference step in 14.3s (see `DESIGN.md`
  #9), including the `GEMINI_MODEL` fallback chain.
- **Not yet tried on a real Android phone** end to end - see `STATUS.md`
  for everything verified so far and what to test next.
- **Cutlery detection (`cutlery_detection/`) is a standalone script**, not
  wired into `scene_description` mode - see its README for why and the
  ~30-minute follow-up if it's ever needed.
