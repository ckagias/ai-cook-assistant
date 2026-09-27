# Status

What works today, how it was verified, and what hasn't been tried yet. The reasons behind each
part are in `DESIGN.md` (decisions #1-#35); how to run and use it is in `README.md`.

Last updated: 2026-09-27, `main` = `integration`.

## Tests

**355 passing** (Python + the Node `.test.mjs` suites, run through `test_client_js.py`). GitHub
Actions runs both on every push to `main` and every pull request (`.github/workflows/tests.yml`).

## What works

**Talking to it** (`static/js/wake.js`, `commands.js`, `echo.js`, `app/voice.py`)
- **Hold Μίλα / Talk** (or the V key) while speaking, let go to send. Pauses don't cut the cook off.
- **The mic lock** (the mic button beside Talk): commands one after another, no wake phrase, until
  it's tapped again.
- **"Hey chef" / «Χέι σεφ»** with hands-free on. It wakes on the name said *to* the app, so
  «σεφ, …» and «γεια σου σεφ» work too, and "ο σεφ είπε…" doesn't.
- **It interrupts at any moment**, even while the app talks. The recipe, the step, the timers and
  an open question stay. After an aside the app carries on from the sentence it was in; after
  "next step" it doesn't. Fire warnings always play to the end.
- **The app's own voice** is never taken for a command: its words from the last 15 s are removed
  from what the mic heard, and while it talks only the wake phrase counts.
- **Common commands are understood on the device** (instant, no key needed). Free speech and
  typed text go to `POST /voice/text`, where the model picks from a closed list of actions and
  code checks the result.
- **Firefox** (no recognizer): hold Talk, or the mic lock, which records until each pause; the
  server transcribes it.

**Cooking a recipe**
- Needs and preferences first (an allergy, less salt, for children), then the ingredients and
  tools as checklists, then the steps.
- **Checklists tick** by tap, by showing them to the camera, from the live detection, or **by
  voice**: "έχω τα αυγά και το γάλα, δεν έχω βούτυρο" ticks two and suggests a substitute for
  the butter. Only what is said changes; with everything ticked it asks "Ξεκινάμε;".
  "Τα έχω όλα, μπορούμε να ξεκινήσουμε" starts the steps.
- Timers start only when the cook asks, several at once. "Is it ready?" checks judge colour and
  the timer together, or the work for cutting and mixing; meat is never judged done by looks
  (the cook gets the thermometer target). The app asks before moving on.
- Needs and allergies said at any point are kept for the whole recipe and checked in answers.
  A short-term memory per recipe answers "τι κάναμε;" and offers to continue the same day.
- **16 curated bilingual recipes** in SQLite (`backend/data/cook.db`, seeded from
  `recipes.json`). Recipes imported from any URL stay *staged* until a person curates them.

**Seeing**
- **"Τι είναι αυτό; / What is this?"** is always in the bottom bar.
- **Live object and hand detection** (YOLOE-26s at 480 px on OpenVINO, MediaPipe hands in
  parallel): boxes, labels and "which hand touches what", about 6 FPS on this 15 W laptop CPU.

**Without hearing, without sight**
- Every button says what it does (long-press, hover, keyboard focus) and shows the same words in
  a bubble.
- Everything said is also on screen (status line, conversation log); alerts stay up with a flash
  and a buzz; the step and timers are large; a large-text switch ("Aa").
- Greek speech by default. A Greek voice that Android lists late still switches the app to
  Greek; with none, the app says where to install one.

**Running it**
- `start.ps1` / `start.cmd` (Windows), `start.sh` (Linux, macOS, WSL). Setup runs only when
  something changed; a later start takes about 5 s, and every start closes the previous session.
- One process serves `http://localhost:8000` and `https://<LAN IP>:8443`. Phones join the
  network the laptop is on by scanning the QR printed in the terminal, and trust the local CA
  after one install. `-Hotspot` uses the laptop's own hotspot at a fixed address and writes
  static QR codes for slides.
- Installable on Android as a PWA; the service worker keeps the app shell offline.

**Security**: a pairing token (skipped only for the laptop itself), rate limits and size caps,
an output guard on every model answer, voice actions from a closed list, and audio, transcripts
and typed text never stored.

## Verified live

- **On this laptop, by the user:** hands-free, hold to talk, the mic lock and the voice checklist
  work. "Hey chef" works but is still a bit hard to land with a Greek accent.
- **OpenAI** (the key configured here) runs voice understanding and vision. Checked on
  2026-09-27: 7 of 7 checklist and start phrases got the right action and the right boxes.
- **Earlier, with Gemini:** a full recipe end to end in headless Edge, and `check_doneness`
  against a reference photo (see DESIGN #9 for timings).
- **Chrome's Greek recognizer on a real microphone** (a phrase played through the speakers):
  woke and opened a recipe. Edge's recognizer missed the wake phrase 3 of 3 times.
- **Detection** in Edge and Firefox with a fake camera and the laptop webcam: 4-7 FPS.
- **Barge-in and resume** in the real page against the real server, with a scripted recognizer.
- **`start.ps1`**, the default network and `-Hotspot`: `/health` over HTTPS, the certificate for
  the address, and every QR code decoded back to the right text.

## Not verified yet

- **A real Android phone:** the microphone, hands-free, hold to talk, the mic lock, the installed
  PWA, and joining from the phone's side. Phone speakers and echo cancellation differ from the
  laptop's, so the app's-own-voice removal needs a check there.
- **Edge as a hands-free browser**: use Chrome on a PC.
- **Anthropic** has never been called with a real key. Gemini isn't configured on this laptop now.
- **A live import from a recipe site**: the importer is tested on hand-written HTML only.
- **Detection in a real kitchen**: so far photos, a fake camera and a desk.
- **The recipes are hand-written, not cooked.** Times and temperatures follow standard guidance.
- **`start.sh`** has neither the clean start nor `-Hotspot`.
- **Demo fixtures** (`DEMO_MODE`) have never been recorded from a real provider.
- **Two of five reference photos are missing** (see `backend/data/reference_images/SOURCES.md`);
  checks skip the comparison when a photo is missing.

## Known quirks

- **The manifest test rewrites the three app icons** (`backend/static/icons/`) on every run, so
  they show as modified in git afterwards. Leave them out of commits.
- Speech recognition can mishear dish names ("ροσμπίφ" once came back as "προς πεις"). The app
  says which recipe it opened and shows what it heard.
- The Gemini free tier (5 requests a minute per model) runs out quickly; the app then says the
  assistant is busy, and on-device commands keep working.

## What to test next

1. A real Android phone on the same network: scan the QR, install the CA, then hands-free, hold
   to talk, the mic lock and a whole recipe.
2. The app's own voice through a phone speaker: talk over it, and check that its words don't end
   up in commands.
3. Import a few Greek recipes from `backend/data/greek_demo_urls.txt`, curate them, and cook one.
