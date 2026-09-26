# AI Cooking Assistant: project overview

A short tour for someone new to the project. The details live in **README.md** (how to run
and use it), **DESIGN.md** (why it's built this way, decisions #1-#32) and **STATUS.md** (what
is verified, and what isn't yet).

## 1. What it is

A voice-first cooking assistant for a phone or tablet propped up in the kitchen. It's made for
blind and low-vision cooks, and it also works fully without sound for deaf cooks who don't
speak. Greek by default, English when the device has no Greek voice.

- **Point the camera** at food or a package, and it says what it sees.
- **Recipes step by step, read aloud:**
  - needs and preferences come first;
  - then the ingredients and tools, as checklists;
  - timers start when the cook says so, several at a time;
  - "is it ready?" checks from a photo, with food-safety rules. Meat is never judged done by
    looks; the cook gets the thermometer target instead.
- **Live object and hand detection** on the laptop: utensils, cookware, ingredients and hands,
  plus which hand touches what. On screen only, since the camera has no depth.

## 2. Architecture

| Part | What |
|---|---|
| Server | FastAPI + Uvicorn (Python 3.12). One process serves `http://localhost:8000` and `https://<LAN IP>:8443` (`scripts/serve.py`) |
| Client | Plain HTML/CSS/JS, no build step; an installable Android PWA with a service worker (`static/sw.js`) |
| Recipes | SQLite (`backend/data/cook.db`), seeded from `backend/data/recipes.json` (16 bilingual recipes). Imported recipes stay *staged* until a person curates their safety fields |
| Vision answers | "What is this?" / "Is it ready?": one provider of Anthropic, OpenAI or Gemini (`VISION_PROVIDER`) |
| Detection | Pretrained YOLOE-26s at 480 px, OpenVINO on the CPU, letterboxed to the frame's own shape, plus MediaPipe hands in parallel. About 6 FPS on a 15 W laptop CPU |
| Voice | Browser speech recognition for "Γεια σου σεφ" / "Hey chef" (Chrome, Edge, Safari). Common commands are matched on the device; free speech goes to `POST /voice/text`. Browsers without a recognizer (Firefox) record and transcribe on the server (`gpt-4o-mini-transcribe`) |
| Phones | The network the laptop is on, with a local CA installed once per phone (trusted on any network). `-Hotspot`: the laptop's own hotspot at the fixed `192.168.137.1`, with static QR codes for slides in `qr/` |

Safety and security:
- a pairing token, skipped only for the laptop itself;
- rate limits and size caps;
- an output guard against prompt injection in model answers;
- voice actions from a closed list, checked in code;
- audio and transcripts never stored.

## 3. Running it

- **Windows:** `.\start.cmd` or `.\start.ps1`.
  - Setup runs once; later starts take about 5 s.
  - Every start closes the previous session.
  - It prints the phone QR in the terminal; `-Hotspot` uses the laptop's own hotspot and writes the static slide QR codes.
- **Linux, macOS, WSL:** `./start.sh`.
- **API keys** go in `backend/.env`, never in `.env.example`.

## 4. How it was built

- **`feature/detection-db`:** detection, the recipe database, the any-URL importer, speaking
  buttons, voice commands, per-browser camera help, and the instant launchers.
- **`feature/hands-free-chef` (ckagias):** hands-free wake phrase, the recipe flow, short-term
  memory, the deaf-friendly UI, 16 curated recipes.
- **`dev` (Fanis):** Android PWA, service worker, local CA for phones, QR pairing, timer
  notifications.
- **`integration`:** all three merged, with the fixes found while testing them together
  (DESIGN #31-#32). It is now `main`.

## 5. Known limits

- Hands-free needs a browser with speech recognition. On a PC use Chrome; Edge's recognizer
  missed the Greek wake phrase in testing. Firefox uses tap-to-talk.
- Recognition can mishear dish names ("ροσμπίφ" came back as "προς πεις" once). The app says
  which recipe it opened and shows what it heard, so a wrong pick is easy to notice and undo.
- Detection runs on the laptop's CPU. Its speed depends on the machine and on thermal
  throttling; it is capped at ~6 FPS to leave headroom.
- Recipes imported from websites are for personal or demo use. Their text stays in the local
  database, not in git.
