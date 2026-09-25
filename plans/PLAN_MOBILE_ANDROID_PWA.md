# Mobile plan: installable Android PWA over a trusted LAN backend, phase by phase

**Branch:** `feature/android-pwa`
**Depends on:** `plans/PLAN_SECURITY_NETWORK_HARDENING.md` (already merged) -
reuses `BACKEND_PAIRING_TOKEN` and the single-household LAN threat model
as-is, no changes needed there.
**Touches:** `backend/static/*` (new manifest, service worker, icons),
`backend/scripts/` (new cert + QR-pairing scripts), `backend/.env.example`,
`README.md`, `DESIGN.md`, `STATUS.md`, `plans/ROADMAP.md`. Phase 9 (stretch,
deferred by default) also touches `backend/app/main.py` and
`backend/requirements.txt`.
**Related:** `plans/ROADMAP.md`'s "Mobile implementation" section - this
plan makes its "PWA first, cheapest next step" bullet concrete. iOS is
explicitly out of scope (see "Android first, iOS later" below); a future
`PLAN_MOBILE_IOS.md` would build on whatever this plan proves works.

Each phase below is self-contained: what to build and why, a ready-to-paste
prompt, and a suggested commit message. Feed one phase's prompt at a time to
the LLM, review the diff, commit yourself (the LLM should never run `git
commit`), then move to the next phase.

---

## Why PWA, not native - and why Android before iOS

`DESIGN.md` #1 already made this call for the MVP: a browser gives camera,
mic, speech synthesis, vibration, and a wake-lock API for free, with no app
store, no build pipeline, and no code signing. Nothing about "make it feel
like a real installed app" changes that calculus - it just means going one
step further than a browser tab: a **manifest** (so Chrome offers "Install
app" and it gets a home-screen icon, a splash screen, and a standalone
window with no address bar) and a **service worker** (so the static shell
survives a flaky connection instead of failing to load at all).

`plans/ROADMAP.md` already recommended this ordering explicitly: "PWA
first, cheapest next step... before considering a native rewrite," and
flagged a native (or React Native) rewrite as "only worth it once the PWA
path has proven the product, not before." This plan is that first step.

**Android before iOS** is a deliberate ordering, not an oversight: Chrome on
Android has had mature support for installable PWAs, the `beforeinstallprompt`
banner, and Web Push notifications for years. Safari on iOS only gained
reliable Web Push for home-screen-installed apps in iOS 16.4 (March 2023),
and historically has stricter/different rules around storage eviction and
background execution for home-screen web apps. Proving the PWA model on
Android first means the harder platform's gaps (see Phase 9) are understood
before iOS-specific workarounds get designed on top.

---

## Architecture: how the frontend talks to the backend, in every shape this app now supports

Nothing about `backend/static/js/api.js` changes for any of this.
`requestJson()` already calls relative paths (`/analyze`, `/recipes`, ...),
so whichever origin the page was loaded from is where it calls back to -
there is no "web build" vs "Android build," it is the same static files in
every case:

| Shape | How the phone reaches the backend | Cert needed? | Status |
|---|---|---|---|
| `adb reverse` over USB (dev) | Tablet's browser sees the backend as `localhost:8000` | No | Already works (`DESIGN.md` #10) |
| Browser tab over LAN HTTPS | Phone and backend on the same WiFi, self-signed cert, click through the browser warning each time | Self-signed, untrusted | Already works today, just nags |
| **Installed Android PWA over LAN HTTPS** | Same as above, but the cert is trusted (Phase 1) so there's no warning to click through, and Chrome offers a real "Install app" prompt | Self-signed, **locally trusted via a local CA** | **This plan** |
| iOS, later | Safari's Add to Home Screen, different Web Push story | TBD | Out of scope here |

The only genuinely new code path is optional-capability detection (Notification
permission, later a Push subscription) - all of it is feature-detected and
no-ops harmlessly in a desktop browser or when denied, exactly the same way
`boot.js` already treats a missing Greek TTS voice as a warning, not a
hard failure (`DESIGN.md` #11). Phases 1-3 below touch zero
Android-specific branching at all: a manifest and a service worker make the
*desktop* browser experience better too (installable there as well), they
just matter more on a phone.

---

## Phase 1 - Trusted local HTTPS cert for the LAN (mkcert)

**Files:** `backend/scripts/generate_lan_cert.sh`, `.gitignore` (add
`backend/certs/`), `backend/.env.example` (document the uvicorn TLS flags).

Today's self-signed HTTPS (README's "Tablet bring-up" §2) means clicking
through a certificate warning on every load - tolerable in a browser tab,
but a real problem for an **installed** PWA: standalone display mode has no
address bar to type `thisisunsafe` into or an "Advanced > Proceed anyway"
link to click, so an untrusted cert can mean a silent failure to load
instead of a dismissible warning. The fix is a **locally-trusted** cert,
not a "real" CA-signed one (there's no public domain for a LAN IP anyway):
[`mkcert`](https://github.com/FiloSottile/mkcert) generates a cert signed
by a local root CA, and installing that one root CA on both the dev
machine and the phone makes every cert it issues show a real green padlock
with no warning, offline, for free.

```bash
#!/usr/bin/env bash
# backend/scripts/generate_lan_cert.sh
# Generates a locally-trusted HTTPS cert for this backend's LAN IP via mkcert.
# 1. Installs mkcert's local CA into this machine's trust store (`mkcert -install`).
# 2. Detects this machine's LAN IP.
# 3. Writes backend/certs/lan-cert.pem + lan-key.pem for that IP + localhost + 127.0.0.1.
# 4. Prints where mkcert's root CA lives (`mkcert -CAROOT`) and how to install it
#    on an Android phone (Settings > Security > Encryption & credentials > Install
#    a certificate > CA certificate), which is the one manual step this can't automate.
```

`backend/certs/` is gitignored (private keys never committed, same
discipline as `.env`). `.env.example` gets two new blank/optional vars,
`BACKEND_SSL_CERTFILE`/`BACKEND_SSL_KEYFILE`, documented as feeding
directly into uvicorn's own `--ssl-certfile`/`--ssl-keyfile` flags - no
application code changes needed, this is purely a launch-command concern.
If `mkcert` isn't installed, the script detects that and prints the
OS-specific install command (`brew install mkcert`, `choco install mkcert`,
or the Linux binary-download instructions) rather than trying to install a
system package itself - `pip install`-installing a Python tool the way
`check_dependencies.py` does with `pip-audit` doesn't apply to a Go binary.

**Prompt:**
> Implement `backend/scripts/generate_lan_cert.sh` exactly as described:
> checks for `mkcert` on PATH and prints OS-specific install instructions
> if missing (don't attempt to install it), otherwise runs `mkcert -install`,
> auto-detects this machine's LAN IP (a zero-traffic UDP-socket trick -
> `socket.connect(("8.8.8.8", 80))` then read `getsockname()[0]`, wrapped so
> a machine with no network interface fails with a clear message instead of
> a stack trace - a small Python one-liner invoked from the bash script is
> fine), generates `backend/certs/lan-cert.pem`/`lan-key.pem` for that IP
> plus `localhost`/`127.0.0.1`, and prints the `mkcert -CAROOT` path with
> instructions for installing that root CA on an Android phone. Add
> `backend/certs/` to `.gitignore`. Add `BACKEND_SSL_CERTFILE=`/
> `BACKEND_SSL_KEYFILE=` (blank) to `.env.example` with a comment explaining
> they feed uvicorn's `--ssl-certfile`/`--ssl-keyfile` flags. Do not commit -
> stop for review.

**Suggested commit message:** `feat: mkcert-based trusted local HTTPS cert for LAN bring-up`

---

## Phase 2 - PWA manifest + icons

**Files:** `backend/static/manifest.webmanifest`, `backend/static/icons/`
(new PNGs), `backend/scripts/generate_pwa_icons.py`, `backend/static/index.html`
(link tags), `backend/app/main.py` (one new mimetype registration).

A manifest is what turns "a website" into "something Chrome offers to
install": name, icons, `display: "standalone"` (no address bar), theme
colors, and a `start_url`. There's no design asset in this repo yet, so
icons are generated programmatically with Pillow - the same "synthesize a
placeholder rather than block on an asset that doesn't exist" approach
`check_providers.py` already uses for its test photo. **This is explicitly
a placeholder**, flagged the same honest way the two missing pancake
reference photos are in `README.md` - swap in real branding whenever it
exists.

```json
{
  "name": "Βοηθός Μαγειρικής",
  "short_name": "CookAssist",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "orientation": "portrait",
  "background_color": "#161616",
  "theme_color": "#161616",
  "icons": [
    {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
    {"src": "/icons/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
  ]
}
```

`main.py` needs one more line next to its existing `.js`/`.css`
`mimetypes.add_type` calls: `.webmanifest` -> `application/manifest+json`
(same Windows-registers-it-wrong problem the existing comment already
documents for `.js`).

**Prompt:**
> Implement `backend/scripts/generate_pwa_icons.py` (Pillow, generates
> `icon-192.png`, `icon-512.png`, and a maskable `icon-512-maskable.png`
> with proper safe-zone padding into `backend/static/icons/` from a simple
> programmatic design - a placeholder, not final branding), add
> `backend/static/manifest.webmanifest` as specified above, link it plus a
> `theme-color` meta tag and an `apple-touch-icon` link from
> `backend/static/index.html`'s `<head>`, and register the
> `application/manifest+json` mimetype for `.webmanifest` in `main.py`
> alongside the existing `.js`/`.css` registrations. Do not commit - stop
> for review.

**Suggested commit message:** `feat: PWA manifest and generated placeholder icons`

---

## Phase 3 - Service worker: shell caching only, never the API

**Files:** `backend/static/sw.js`, `backend/static/js/app.js` (registration).

Chrome requires a registered service worker for the "Install app" prompt to
appear at all, and it's also what makes the static shell (HTML/CSS/JS)
survive a flaky connection instead of failing to load outright - the
"offline-tolerant launch" `plans/ROADMAP.md` asked for. It must **never**
touch `/analyze`, `/recipes`, `/barcode`, `/reference`, or `/health` -
caching a vision analysis response would be actively wrong (stale doneness
advice is a safety problem, not a UX one), so those paths are explicitly
passed straight to the network, untouched by the service worker at all.

For the shell files themselves: **network-first, cache as a fallback**, not
cache-first. This repo has no build step and therefore no
content-hashed filenames to bust a stale cache automatically
(`DESIGN.md`-style honesty: this is a real, accepted limitation, not
solved here) - network-first means an online reload always gets the latest
JS/CSS, and the cache only ever gets used when the network genuinely fails,
which is exactly the "still loads on a bad connection" goal without risking
silently serving stale code indefinitely.

```js
// backend/static/sw.js
const SHELL_CACHE = "cook-assist-shell-v1";
const NEVER_INTERCEPT = ["/analyze", "/recipes", "/barcode", "/reference", "/health"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_FILES)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== SHELL_CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (NEVER_INTERCEPT.some((p) => url.pathname.startsWith(p))) return;
  event.respondWith(
    fetch(event.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(SHELL_CACHE).then((cache) => cache.put(event.request, copy));
        return res;
      })
      .catch(() => caches.match(event.request))
  );
});
```

Registered as early as possible (not gated behind the one-gesture unlock -
registration itself needs no user activation): a few lines near the top of
`app.js`, best-effort, never blocking `boot()` if it fails.

**Prompt:**
> Implement `backend/static/sw.js` exactly as sketched above (network-first
> for the shell, explicit passthrough for `/analyze`/`/recipes`/`/barcode`/
> `/reference`/`/health`, cache versioned as `cook-assist-shell-v1`,
> `SHELL_FILES` listing every static file `index.html` actually loads:
> `/`, `/app.css`, every module under `/js/`, `/manifest.webmanifest`, and
> the icon files from Phase 2). Register it from `app.js` on page load
> (not inside `boot()`), best-effort with a caught rejection. Do not commit
> - stop for review.

**Suggested commit message:** `feat: service worker for offline-tolerant static shell`

---

## Phase 4 - Foreground/background-tab-alive timer notifications

**Files:** `backend/static/js/boot.js`, `backend/static/js/app.js`,
`backend/static/js/strings.js` (if a new string is needed).

`session.js`'s timer already has an `onExpired` callback
(`app.js`'s `onExpired: () => { earcon("wait"); buzz(...); say(...) }`) -
this phase adds a real OS-level `Notification` alongside it, but **only**
when the tab isn't focused (`document.hidden`), so a user actively looking
at the app doesn't get a redundant system notification on top of the
in-page status text and spoken alert. This closes part of the gap
`plans/ROADMAP.md` flagged ("background timers are the real gap a browser
can't close") - specifically the "switched to another app briefly, phone
screen still on" case. It does **not** close the "phone locked, screen off"
case - that needs Web Push (Phase 9, stretch), which this phase explicitly
does not attempt, and the on-screen countdown plus `visibilitychange`
catch-up on resume remain the only guarantee for that case, same as today.

Notification permission is requested inside `boot()`'s single user gesture,
alongside the audio/camera/wake-lock unlock `DESIGN.md` #11 already
consolidates there - best-effort, a denial degrades to exactly today's
behavior (earcon/buzz/speak only), never a hard failure.

**Prompt:**
> In `boot.js`'s `boot()`, add a best-effort
> `Notification.requestPermission()` call alongside the existing
> permission/unlock requests (never let a rejection or an unsupported
> `Notification` API break boot). In `app.js`'s `session.js` `onExpired`
> callback, after the existing `earcon`/`buzz`/`say` calls, if
> `document.hidden` is true and `Notification.permission === "granted"`,
> fire `new Notification(t("timer_done", lang))`. Do not commit - stop for
> review.

**Suggested commit message:** `feat: system notification for timer completion while backgrounded`

---

## Phase 5 - QR-code pairing for one-scan Android setup

**Files:** `backend/scripts/print_pairing_qr.py`, `backend/requirements.txt`
(add `qrcode[pil]`).

`PLAN_SECURITY_NETWORK_HARDENING.md` Phase 2 already built the pairing
mechanism (`?token=...` captured into `localStorage` on first load) - this
phase just makes getting that URL onto the phone a camera scan instead of
manually typing a LAN IP and a 32-character token. Same LAN-IP
auto-detection as Phase 1's cert script.

```python
#!/usr/bin/env python3
"""Print a QR code encoding this backend's pairing URL, for one-scan Android setup.

Usage: python scripts/print_pairing_qr.py [--port 8000]
"""
```

Builds `https://<lan-ip>:<port>/?token=<BACKEND_PAIRING_TOKEN>`
(loaded via `python-dotenv`, same pattern as `check_providers.py`), prints
an ASCII QR to the terminal (`qrcode`'s own `print_ascii()`) and also
saves a PNG for a terminal that can't render ASCII QR legibly. If
`BACKEND_PAIRING_TOKEN` is unset, prints the plain URL with no token param
and a note that pairing is disabled - it must not silently invent a token.

**Prompt:**
> Implement `backend/scripts/print_pairing_qr.py` exactly as described:
> auto-detects the LAN IP the same way Phase 1's `generate_lan_cert.sh`
> does, reads `BACKEND_PORT`/`BACKEND_PAIRING_TOKEN` via `python-dotenv`,
> builds the pairing URL (omitting `?token=` and printing a note if the
> pairing token is unset), prints an ASCII QR via `qrcode.print_ascii()`
> and also saves a PNG. Add `qrcode[pil]` to `requirements.txt`. Do not
> commit - stop for review.

**Suggested commit message:** `feat: QR-code pairing script for Android setup`

---

## Phase 6 - README rewrite for the Android PWA bring-up path

**Files:** `README.md`.

Adds a third path to "Tablet bring-up," alongside the existing `adb reverse`
and plain self-signed-HTTPS ones: run `generate_lan_cert.sh` once, launch
uvicorn with `--ssl-certfile`/`--ssl-keyfile` pointed at `backend/certs/`,
run `print_pairing_qr.py`, scan it with the phone's camera, tap through
Chrome's "Install app" prompt (or the 3-dot menu's "Install app" if the
banner doesn't appear), then use the home-screen icon from then on. Keeps
`adb reverse` documented as the no-cert-hassle path for active development.
Adds one explicit "known limitation" callout: timers don't notify while the
phone is fully locked/backgrounded (Phase 4 covers "switched apps briefly,"
not "screen off") - the on-screen countdown remains the fallback, same
wording as `plans/ROADMAP.md` already uses.

**Prompt:**
> Rewrite README.md's "Tablet bring-up" section to add the Android-PWA path
> described above as a third option, numbered and complete (cert
> generation, launching uvicorn with TLS flags, QR pairing, installing from
> Chrome), keep the existing two paths, and add the "known limitation"
> callout about backgrounded timers. Do not commit - stop for review.

**Suggested commit message:** `docs: document the Android PWA bring-up path`

---

## Phase 7 - Manual Android verification checklist

This phase has no code for an LLM to write - it's a checklist for whoever
has a physical Android device, the same spirit as `STATUS.md`'s "what to
test next" for the original rebuild. Run through, in order:

1. `generate_lan_cert.sh`, then launch uvicorn with the TLS flags.
2. `print_pairing_qr.py`, scan with the phone, confirm **no** certificate
   warning appears (proves the local CA is actually trusted, not just
   clicked through).
3. Confirm Chrome offers "Install app" (or install manually via the 3-dot
   menu), install it, confirm it opens standalone (no address bar).
4. From the installed icon (not a browser tab), walk the full golden path:
   Start button (one-gesture unlock), identify a scene, open a recipe, step
   through it, check doneness, trigger a timer.
5. Start a timer, switch to another app (don't lock the screen), confirm a
   system notification appears when it completes (Phase 4).
6. Start a timer, lock the screen, confirm - as expected - no notification
   fires, and that reopening the app shows the correct elapsed/remaining
   time via the existing `visibilitychange` catch-up.
7. Toggle airplane mode after the app has loaded once, reload: confirm the
   shell (buttons, layout) still renders from the service worker cache,
   and that an `/analyze` call fails/hedges cleanly instead of hanging or
   crashing.
8. Uninstall and reinstall once, to confirm the pairing token in
   `localStorage` survives an app-level reinstall or not (per-origin
   storage in Chrome typically does survive a reinstall unless site data
   was explicitly cleared - worth confirming rather than assuming).

Record whatever real-device bugs this surfaces as their own `fix:` commits
- that part isn't scriptable in advance, same as `STATUS.md` already notes
for the original hardware-testing gap.

---

## Phase 8 - Document the decision

**Files:** `DESIGN.md` (append a new numbered decision), `STATUS.md`,
`plans/ROADMAP.md`.

Append a `DESIGN.md` decision entry documenting the Android-PWA approach:
why PWA over native (referencing #1), why a local CA over a real one
(no public domain for a LAN IP), the network-first service-worker caching
choice and why (no build step, no content hashing), and the explicit,
honest scope boundary - backgrounded/locked-screen timer notifications are
not solved here, only Phase 9 (if ever built) would close that. Update
`STATUS.md`'s "no real device testing" bullet once Phase 7 has actually
happened, with real findings. Update `plans/ROADMAP.md`'s "PWA first"
bullet to done, pointing at this plan, the same way the network-hardening
work already struck through its own roadmap bullets.

**Prompt:**
> Append a new numbered decision to `DESIGN.md` documenting the Android PWA
> approach as described above, explicit about the backgrounded-timer scope
> boundary. Update `STATUS.md` and `plans/ROADMAP.md` to reflect Phase 7's
> real findings and mark the "PWA first" roadmap bullet done, pointing at
> this plan. Do not commit - stop for review.

**Suggested commit message:** `docs: document the Android PWA decision and update project status`

---

## Stretch, deferred by default - Phase 9: Web Push for real background timer completion

**Not part of the core plan above** - a separate, materially bigger
feature with its own new dependency, new stateful backend component, and
own security surface. Only build this if backgrounded/locked-screen timer
notifications turn out to matter enough in real use (Phase 7) to justify
it; otherwise the on-screen countdown + `visibilitychange` catch-up is an
honest, working fallback, documented as such in Phase 8.

**Files:** `backend/app/push.py` (new), `backend/app/main.py` (two new
routes), `backend/static/sw.js` (a `push` event handler), `backend/static/js/*`
(subscribe flow), `backend/requirements.txt` (`pywebpush`).

What it would take: VAPID key generation (one-time, via `pywebpush`'s own
key-gen helper), a `POST /push/subscribe` endpoint (behind the existing
pairing-token auth, same as every other data route) storing a browser's
push subscription plus a step's deadline, an in-process scheduler (a
single background `asyncio` task holding a min-heap of pending deadlines -
same "no new infra, single-process is enough" reasoning
`backend/app/rate_limit.py` already used for its sliding window) that fires
`webpush(subscription, ...)` when a deadline elapses, and a `push` event
handler in `sw.js` calling `registration.showNotification(...)` - this is
the one piece of this whole plan whose service worker code *is*
Android-specific in practice, since Web Push on iOS Safari has a
meaningfully different (and historically less reliable) story. A
`POST /push/cancel` endpoint is needed too, for when a step is skipped or
the timer is stopped manually before it would have fired, so a stale push
never arrives after the fact.

This phase is intentionally left unexpanded into sub-phase prompts here -
if it's ever picked up, it deserves its own phase-by-phase plan document
the same weight as the two security plans, not a rushed addendum to this
one.
