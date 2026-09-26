# Mobile plan: installable Android PWA over the existing LAN launcher, phase by phase

**Branch:** `feature/android-pwa`
**Depends on (all already merged as of `ce30c07`):**
- `plans/PLAN_SECURITY_NETWORK_HARDENING.md` - `BACKEND_PAIRING_TOKEN`,
  `?token=` -> `localStorage` -> `X-Pairing-Token` pairing flow, rate limits,
  the single-household LAN threat model. Reused as-is.
- The `start.sh` / `start.ps1` launcher + `backend/scripts/serve.py` +
  `backend/scripts/lan.py`. These already generate the pairing token, detect
  the LAN IP, generate a per-IP self-signed cert into `backend/certs/`, and
  serve `http://localhost:8000` and `https://<LAN IP>:8443` from one process.
  **This plan plugs into that launcher; it does not build a second one.**

**Touches:** `backend/scripts/lan.py` (local CA), `backend/app/main.py` (one
mimetype line, one `/ca.crt` route, one `detect` flag persistence),
`backend/static/*` (manifest, icons, service worker, notification wiring),
`backend/scripts/pairing_qr.py` (new), `start.sh` / `start.ps1` (call the QR
script, change the "accept the warning" line), `backend/requirements.txt`
(`qrcode`), `backend/.env.example`, `README.md`, `DESIGN.md`, `STATUS.md`,
`plans/ROADMAP.md`. Phase 9 (stretch, deferred) would touch more.

**Related:** `plans/ROADMAP.md` "Mobile implementation" - this plan makes its
"PWA first, cheapest next step" bullet concrete. iOS is out of scope (see
below); a future `PLAN_MOBILE_IOS.md` builds on what this proves.

Each phase below is self-contained: what to build and why, a ready-to-paste
prompt, and a suggested commit message. Feed one phase's prompt at a time to
the LLM, review the diff, commit yourself (the LLM never runs `git commit`),
then move on.

---

## What already works today, and the five gaps this plan closes

Run `./start.sh` (or `start.cmd` on Windows) and you get:

- token generated once into `backend/.env` (`lan.py token`)
- LAN IP detected (`lan.py ip`), a self-signed cert for that IP (`lan.py cert`)
- one uvicorn process on `127.0.0.1:8000` (HTTP) and `0.0.0.0:8443` (HTTPS)
- a printed phone link `https://<LAN IP>:8443/?token=...&detect=1` with the
  note "(accept the certificate warning once)"
- `app.js` stores the token, strips it from the URL, and speaks "not paired"
  on a 401

A phone can open that link **as a browser tab** today. The gaps:

1. **The cert is self-signed, not trusted.** A tab can click through the
   warning. An *installed* PWA in standalone mode has no address bar and no
   "Advanced > proceed" link - an untrusted cert is a blank screen. Chrome
   also won't offer "Install app" for an origin with a cert error.
2. **No manifest**, so Chrome never offers install and there is no
   home-screen icon, splash, or standalone window.
3. **No service worker**, so there is no install prompt (Chrome requires
   one) and a flaky connection fails the shell outright.
4. **Timer completion is silent when another app is in front.**
5. **Pairing means typing a LAN IP + 32-char token** on a phone keyboard.

Plus one environment fact that isn't a gap in the code but will bite on
this machine: **`start.sh` inside WSL is unreachable from a phone** unless
WSL networking is `mirrored` - `start.sh` already detects this and drops the
LAN address. For every phone test in this plan, run `start.cmd` from Windows
or switch WSL to mirrored networking. Phase 7 repeats this.

---

## Why PWA, not native - and why Android before iOS

`DESIGN.md` #1 made this call for the MVP: a browser gives camera, mic,
speech synthesis, `MediaRecorder` (push-to-talk), vibration, and a wake lock
for free. "Make it feel installed" is one step further - a **manifest** and a
**service worker** - not a different platform.

`plans/ROADMAP.md` already recommended this ordering: PWA first, native only
once the PWA path has proven the product.

**Android before iOS**: Chrome on Android has had installable PWAs,
`beforeinstallprompt`, `ServiceWorkerRegistration.showNotification()`, and
Web Push for years. iOS Safari's story for home-screen apps (Web Push since
16.4, `navigator.vibrate` absent entirely, stricter storage eviction) is
different enough to deserve its own plan once Android is proven.

---

## Architecture: how the phone reaches the backend, in every shape

Nothing about `backend/static/js/api.js` changes. It calls relative paths
(`/analyze`, `/detect`, `/voice`, `/recipes`, ...), so whichever origin
served the page is the backend. Same static files in every row:

| Shape | How the client reaches the backend | Cert | Status |
|---|---|---|---|
| `adb reverse` over USB (dev) | tablet sees `localhost:8000` | none | works (`DESIGN.md` #10) |
| App window on this computer (`start.sh`) | `http://localhost:8000`, own Chrome profile, SPKI-pinned | none needed on localhost | works |
| Browser tab on a phone over LAN | `https://<LAN IP>:8443`, click through the warning | self-signed leaf | works today, nags |
| **Installed Android PWA over LAN** | same origin, cert chains to a **local CA installed once on the phone** | CA-signed leaf | **this plan** |
| iOS, later | Add to Home Screen | TBD | out of scope |

Phases 2-3 touch zero Android-specific code: a manifest and a service worker
make the desktop app window better too (installable there as well).

---

## Phase 1 - Local CA in `lan.py`, so the phone trusts the cert once and forever

**Files:** `backend/scripts/lan.py`, `backend/app/main.py` (one route),
`backend/.env.example`, `start.sh` / `start.ps1` (one printed line each),
`backend/tests/test_launch_scripts.py` (or a new `test_lan_ca.py`).

**Why not mkcert:** the earlier draft of this plan reached for
[`mkcert`](https://github.com/FiloSottile/mkcert). It's a Go binary that
can't be `pip install`ed, it would sit beside `lan.py`'s existing cert code
rather than replace it, and it isn't needed: `lan.py` already depends on
`cryptography` and already generates X.509 certs. Generating our own root CA
with the same library is ~40 lines and keeps `start.sh` as the single
launcher.

**Why a CA at all, not just "install the self-signed leaf":** Android's
"Install a certificate > CA certificate" needs a cert with
`basicConstraints CA:TRUE`. More importantly, a leaf is bound to **one IP**.
When DHCP hands the laptop a new address, `lan.py` already issues a new leaf
for it - if the phone trusts the *CA*, that new leaf is trusted with no
action on the phone. If the phone had trusted the leaf, the installed PWA
would silently fail on the next IP change. The CA is what makes this robust.

**What `lan.py` gains:**

```python
CA_CERT = CERT_DIR / "ca-cert.pem"
CA_KEY = CERT_DIR / "ca-key.pem"
CA_CRT = CERT_DIR / "ca-cert.crt"   # same PEM bytes; Android's file picker wants .crt

def ensure_ca() -> tuple[Path, Path]:
    # Once per machine. CN "Cooking Assistant Local CA (<hostname>)", 10 years,
    # basicConstraints CA:TRUE (critical), keyUsage keyCertSign+cRLSign.
    # Also writes CA_CRT (a copy of CA_CERT with the .crt extension).

def ensure_cert(ip: str) -> tuple[Path, Path, str]:
    # Unchanged signature and return (cert, key, spki) - app_window.py's SPKI pinning
    # and start.sh's `lan.py all` parsing keep working untouched.
    # Now: issuer = CA, signed by CA_KEY, SAN {ip, 127.0.0.1, localhost},
    # extendedKeyUsage serverAuth, validity <= 825 days (Chrome/Apple ceiling).
    # If an existing lan-<ip>-cert.pem is self-signed (issuer == subject, the pre-CA
    # format), regenerate it under the CA once.
```

`lan.py all` output stays the same six fields; `start.sh`/`start.ps1` need no
parsing change. Their printed line `(accept the certificate warning once)`
becomes `(first time on a phone: open https://<ip>:8443/ca.crt, install it,
then no warning)`.

**`main.py`**: `GET /ca.crt` -> `FileResponse(backend/certs/ca-cert.crt,
media_type="application/x-x509-ca-cert")`, 404 if the file doesn't exist.
**Not** behind the pairing token - a root cert is public by definition, and
the phone doesn't have the token yet at this point. Chrome on Android
downloads it and Android offers to install it. This makes the one manual
step a single tap instead of "email yourself a file".

**`.env.example`**: add `BACKEND_HTTPS_PORT=8443` (already read by
`start.sh` but undocumented) with a comment. `BACKEND_SSL_CERTFILE`/`KEYFILE`
are **not** needed - `serve.py --cert/--key` already exists and `start.sh`
already passes them.

**Android facts to write into the README in Phase 6, verified in Phase 7:**
Chrome on Android trusts user-installed CAs (Settings > Security >
Encryption & credentials > Install a certificate > CA certificate). Android
then shows a persistent "Network may be monitored" notification - expected,
that is what installing a CA means, and it's the reason the CA key stays on
this one machine and `backend/certs/` stays gitignored (it already is).

**Prompt:**
> In `backend/scripts/lan.py`, add `ensure_ca()` that creates a local root
> CA once (`certs/ca-cert.pem`, `certs/ca-key.pem`, plus a `.crt` copy of the
> cert; CN "Cooking Assistant Local CA (<hostname>)", 10-year validity,
> critical basicConstraints CA:TRUE, keyUsage keyCertSign+cRLSign). Change
> `ensure_cert(ip)` to sign the per-IP leaf with that CA (issuer = CA name,
> SAN unchanged: the IP, 127.0.0.1, localhost; add extendedKeyUsage
> serverAuth; validity 825 days) while keeping its signature and its
> `(cert, key, spki)` return unchanged so `lan.py all`, `start.sh`,
> `start.ps1`, and `app_window.py` keep working. If an existing
> `lan-<ip>-cert.pem` is self-signed (issuer == subject), regenerate it under
> the CA. In `main.py`, add `GET /ca.crt` serving `backend/certs/ca-cert.crt`
> with media type `application/x-x509-ca-cert`, 404 if absent, **not**
> behind `require_pairing_token`. Add `BACKEND_HTTPS_PORT=8443` to
> `.env.example` with a comment. Change the "(accept the certificate warning
> once)" line in `start.sh` and `start.ps1` to point at `/ca.crt` instead.
> Add tests: the CA has CA:TRUE, the leaf's issuer is the CA and the chain
> verifies with `cryptography`, the leaf's SAN contains the IP, a pre-existing
> self-signed leaf gets regenerated under the CA, and `/ca.crt` returns 200
> with the right content type when the file exists and 404 when not (use
> `tmp_path` and monkeypatch `CERT_DIR`). Run nothing against a real network.
> Do not commit - stop for review.

**Suggested commit message:** `feat: local root CA in lan.py so phones trust the LAN cert once`

---

## Phase 2 - PWA manifest + icons

**Files:** `backend/static/manifest.webmanifest`, `backend/static/icons/`
(new PNGs), `backend/scripts/generate_pwa_icons.py`,
`backend/static/index.html` (head tags), `backend/app/main.py` (one mimetype
line), `backend/static/js/app.js` (persist the `detect` flag).

A manifest is what turns "a website" into "something Chrome offers to
install". No design asset exists in this repo, so icons are generated with
Pillow (already in `requirements.txt`) - a **placeholder**, flagged honestly
the same way the missing pancake reference photos are.

```json
{
  "id": "/",
  "name": "Βοηθός Μαγειρικής",
  "short_name": "Βοηθός",
  "lang": "el",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#111111",
  "theme_color": "#111111",
  "icons": [
    {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
    {"src": "/icons/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
  ]
}
```

Deliberate choices, each of which the earlier draft got wrong:

- **No `orientation` field.** `app.css` has a landscape grid for tablets
  (`@media (min-width: 720px) and (orientation: landscape)`). Locking
  `portrait` would disable it in the installed app. Let the OS decide.
- **Colors match `app.css`'s `--bg: #111`**, not an invented `#161616`.
- **`start_url` is `/`, with no query string.** The launcher's link carries
  `?token=...&detect=1`. The token already persists in `localStorage`. The
  `detect=1` flag does not - `app.js` reads `DETECT_ON_START` from the URL
  on every load, so the installed app would lose it. Persist it the same way
  `?speakButtons=` already persists a per-device choice: `?detect=1` writes
  `localStorage`, `?detect=0` clears it, and `DETECT_ON_START` reads the URL
  first and storage second.

`index.html` head: `<link rel="manifest">`, `<meta name="theme-color">`,
replace the `data:,` favicon with the 192px icon, and an `apple-touch-icon`
(harmless on Android, saves a step for the iOS plan).

`main.py`: `mimetypes.add_type("application/manifest+json", ".webmanifest")`
next to the existing `.js`/`.css` lines - the same Windows-registers-it-wrong
issue the comment there already documents. Chrome silently ignores a
manifest served as `text/plain`.

**Prompt:**
> Implement `backend/scripts/generate_pwa_icons.py` (Pillow; writes
> `icon-192.png`, `icon-512.png`, and `icon-512-maskable.png` with the
> maskable safe zone respected, into `backend/static/icons/`, from a simple
> programmatic design - a placeholder, say so in the docstring) and run it
> once so the PNGs exist. Add `backend/static/manifest.webmanifest` exactly
> as specified above (no `orientation`, colors `#111111`). In `index.html`
> add the manifest link, `theme-color` meta, `apple-touch-icon`, and point
> the favicon at `/icons/icon-192.png`. In `main.py` register
> `application/manifest+json` for `.webmanifest`. In `app.js`, make
> `?detect=1` persist to `localStorage` (and `?detect=0` clear it), with
> `DETECT_ON_START` reading URL first then storage - mirror how
> `speakButtons` is handled. Add a test that `GET /manifest.webmanifest`
> returns `application/manifest+json` and parses as JSON with the three icon
> entries present on disk. Do not commit - stop for review.

**Suggested commit message:** `feat: PWA manifest, generated placeholder icons, persistent detect flag`

---

## Phase 3 - Service worker: shell only, GET only, never the API

**Files:** `backend/static/sw.js`, `backend/static/js/app.js` (registration),
`backend/tests/sw.test.mjs`.

Chrome requires a registered service worker before it offers "Install app",
and Phase 4's `showNotification()` needs one too. It also makes the static
shell survive a flaky connection.

It must **never** touch an API route. Caching a `/analyze` answer would be a
safety problem (stale doneness advice), and `/detect` and `/voice` are live
frames and live audio. The safe rule is narrow: **handle only same-origin
GET requests for files in the fixed shell list; pass everything else
through untouched.** That rules out POSTs (the Cache API rejects them
anyway), every API path, `probe.html`, `/ca.crt`, and anything with a query
string the app doesn't know about.

**Network-first for the shell, cache as fallback.** There is no build step
and no content-hashed filenames, so cache-first would serve stale JS for as
long as the cache lived. Network-first means an online reload always gets
the current code; the cache is only used when the network genuinely fails.
An accepted limitation, written down in Phase 8.

```js
// backend/static/sw.js
const SHELL_CACHE = "cook-assist-shell-v1";
const SHELL_FILES = [
  "/", "/app.css", "/manifest.webmanifest",
  "/js/app.js", "/js/boot.js", "/js/tts.js", "/js/strings.js", "/js/capture.js",
  "/js/api.js", "/js/monitor.js", "/js/aim.js", "/js/session.js", "/js/features.js",
  "/js/detect.js", "/js/a11y.js", "/js/voice.js", "/js/camera_help.js",
  "/icons/icon-192.png", "/icons/icon-512.png", "/icons/icon-512-maskable.png",
];
const SHELL_SET = new Set(SHELL_FILES);

// Exposed for sw.test.mjs. A navigation to "/?token=...&detect=1" is still the shell:
// the query string is dropped for the cache key, never stored.
function shellPath(request, origin) {
  if (request.method !== "GET") return null;
  const url = new URL(request.url);
  if (url.origin !== origin) return null;
  if (request.mode === "navigate") return "/";
  return SHELL_SET.has(url.pathname) ? url.pathname : null;
}

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((c) => c.addAll(SHELL_FILES)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL_CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const path = shellPath(event.request, self.location.origin);
  if (path === null) return; // API, POST, probe.html, /ca.crt, cross-origin: untouched
  event.respondWith(
    fetch(event.request)
      .then((res) => {
        if (res.ok) caches.open(SHELL_CACHE).then((c) => c.put(path, res.clone()));
        return res;
      })
      .catch(() => caches.match(path))
  );
});
```

Note `caches.addAll` fails the whole install if any one path 404s - the
icon paths from Phase 2 must be exact, and Phase 7 checks the worker reached
`activated`.

Registration: a few lines at the top of `app.js`, on page load, **not**
inside `boot()` (registration needs no user gesture), best-effort with a
caught rejection. Because `shellPath` is a plain function and `sw.js` is a
classic script, `sw.test.mjs` can read the file, evaluate it with a shimmed
`self` (`addEventListener`, `location`, `skipWaiting`, `clients`) and
`caches`, and call `shellPath` directly.

**Prompt:**
> Implement `backend/static/sw.js` as sketched above: a fixed `SHELL_FILES`
> list (verify it against what `index.html` and the `js/` modules actually
> import - add anything missing), `shellPath()` that returns a cache key only
> for same-origin GETs that are either navigations or listed shell files and
> `null` otherwise, network-first with `res.ok` gating before `cache.put`,
> versioned cache with old-version cleanup on activate, `skipWaiting` +
> `clients.claim`. Register it from `app.js` on load, outside `boot()`,
> best-effort. Write `backend/tests/sw.test.mjs` (same style as the existing
> `*.test.mjs` files, discovered by `test_client_js.py`) that evaluates
> `sw.js` with a shimmed `self`/`caches` and asserts: POST to `/analyze`,
> `/detect`, `/voice` -> null; GET `/recipes`, `/health`, `/ca.crt`,
> `/probe.html` -> null; cross-origin GET -> null; navigation to
> `/?token=abc&detect=1` -> `/`; GET `/js/app.js` -> `/js/app.js`. Do not
> commit - stop for review.

**Suggested commit message:** `feat: service worker for an offline-tolerant static shell (GET-only, API untouched)`

---

## Phase 4 - Timer notification when another app is in front

**Files:** `backend/static/js/boot.js`, `backend/static/js/app.js`,
`backend/static/sw.js` (a `notificationclick` handler),
`backend/static/js/strings.js` if a string is needed.

`session.js`'s `onExpired` already fires `earcon("wait")`, `buzz(...)`,
`say(t("timer_done"))`. This adds an OS notification **only when
`document.hidden`**, so a user looking at the app isn't double-alerted.

**The one thing that would have broken on the phone:** the earlier draft
called `new Notification(...)`. Chrome on Android does not implement the
page-level constructor - it throws `Illegal constructor` and requires
`ServiceWorkerRegistration.showNotification()`. That works on desktop too,
so it's the only call to use, and it's why this phase depends on Phase 3.

```js
// app.js, inside onExpired, after the existing earcon/buzz/say
if (document.hidden && "Notification" in window && Notification.permission === "granted") {
  navigator.serviceWorker.ready
    .then((reg) => reg.showNotification(t("timer_done", lang), { tag: "timer", renotify: true }))
    .catch(() => {});
}
```

`tag: "timer"` means a second expiry replaces the first instead of stacking.
In `sw.js`, `notificationclick` closes the notification and focuses (or
opens) the app window - otherwise the tap does nothing.

Permission is requested inside `boot()`'s single gesture, next to the
camera/mic/wake-lock claims `DESIGN.md` #11 consolidates there. Best-effort:
unsupported or denied degrades to today's behavior.

**Be honest about what this buys.** Android Chrome throttles a hidden tab's
timers to about once a minute and can freeze the tab entirely after ~5
minutes hidden. `session.js` uses an absolute deadline, so the *time* stays
correct, but the check that notices it passed may run up to a minute late,
or not until the app is foregrounded again. This phase improves "switched
apps for a moment"; it does not deliver "phone in a pocket". That needs
Web Push (Phase 9), which this plan defers.

**Prompt:**
> In `boot.js`'s `boot()`, request `Notification` permission best-effort
> inside the same gesture (guard on `"Notification" in window`; never let a
> rejection break boot; add a warning string only if permission is denied).
> In `app.js`'s `onExpired`, after the existing calls, if `document.hidden`
> and permission is granted, call `showNotification` via
> `navigator.serviceWorker.ready` as sketched above - never `new
> Notification()`. In `sw.js`, add a `notificationclick` handler that closes
> the notification and focuses an existing client or opens `/`. Extend
> `sw.test.mjs` to assert the handler is registered. Do not commit - stop
> for review.

**Suggested commit message:** `feat: system notification for timer completion while backgrounded (SW showNotification)`

---

## Phase 5 - QR code in the launcher output

**Files:** `backend/scripts/pairing_qr.py` (new), `start.sh`, `start.ps1`,
`backend/requirements.txt` (`qrcode`).

`start.sh` already prints `https://<LAN IP>:8443/?token=...&detect=1`. The
phone has to type it. This phase prints the same URL as an ASCII QR right
under it, and saves `.run/pairing.png` for terminals that render ASCII QR
badly (Windows consoles often do).

Not a second URL-builder: the script takes the URL as an argument
(`pairing_qr.py --url "$PHONE_URL" --png .run/pairing.png`), so `start.sh`
and `start.ps1` remain the only place the URL is assembled. Standalone use
(`python scripts/pairing_qr.py` with no args) rebuilds it from `lan.py all`
+ `BACKEND_HTTPS_PORT`, omitting `?token=` with a printed note if the token
is unset - it must never invent one.

`qrcode` is pure Python; Pillow is already present for the PNG. If `qrcode`
isn't importable (an older venv), the launcher skips the QR and prints one
line saying so - never a stack trace in the happy-path output.

**Prompt:**
> Implement `backend/scripts/pairing_qr.py`: `--url` and `--png` arguments;
> with no `--url`, rebuild it from `scripts/lan.py all` output and
> `BACKEND_HTTPS_PORT` (default 8443), omitting `?token=` with a note if the
> token is blank. Print the QR via `qrcode`'s `print_ascii(invert=True)` and
> save the PNG. Add `qrcode` to `requirements.txt`. In `start.sh` and
> `start.ps1`, right after the phone link is printed (only when a LAN IP
> exists), call the script with that exact URL and `.run/pairing.png`,
> tolerating a missing `qrcode` module with a one-line message. Add a unit
> test for the URL-building path with the token unset and set (mock `lan.py`
> output). Do not commit - stop for review.

**Suggested commit message:** `feat: QR code for phone pairing in the launcher output`

---

## Phase 6 - README: the phone path, end to end

**Files:** `README.md`.

The README already has "Quick start", "Run it as an app on your network",
"Tablet bring-up" (adb reverse / self-signed), and a WSL note. Update, don't
duplicate:

- **"Run it as an app on your network"**: step 4 currently says phones "show
  a certificate warning". Replace with the real flow: open `/ca.crt` once,
  install it as a CA certificate (Settings path spelled out), expect
  Android's "Network may be monitored" notice, then scan the QR / open the
  link, tap Chrome's "Install app" (or the 3-dot menu), use the icon from
  then on.
- **"Tablet bring-up"**: add the installed-PWA path as option 3, keep
  `adb reverse` as the no-cert dev path.
- **WSL callout**, promoted: phones can't reach `start.sh` inside WSL
  unless networking is mirrored - use `start.cmd` for phone work.
- **What happens when the laptop's IP changes**: the leaf cert is reissued
  automatically under the same CA (no phone action), but the *URL* changes -
  re-scan the QR. The token does not change.
- **Known limitation**: timers don't notify while the phone is locked or the
  app has been in the background for several minutes; on-screen countdown
  and the catch-up on resume remain the fallback. Same wording as
  `plans/ROADMAP.md`.

**Prompt:**
> Update `README.md` as described: rewrite the phone steps in "Run it as an
> app on your network" around `/ca.crt` + install + QR + "Install app", add
> the installed-PWA path as a third "Tablet bring-up" option, promote the WSL
> note, add the IP-change paragraph, and the backgrounded-timer limitation.
> Keep everything else. Do not commit - stop for review.

**Suggested commit message:** `docs: Android PWA bring-up path in README`

---

## Phase 7 - Manual Android verification checklist

No code for an LLM. Whoever holds the phone runs this in order, on a machine
whose LAN address the phone can reach (**Windows `start.cmd`, not WSL
`start.sh`, unless WSL is mirrored**):

1. Delete `backend/certs/` once so Phase 1's CA path is exercised from
   scratch, then `start.cmd`. Confirm the console prints the `/ca.crt` hint
   and the QR.
2. On the phone, open `https://<LAN IP>:8443/ca.crt` in Chrome (one warning
   click-through is expected here and only here). Install it as a CA
   certificate. Confirm the "Network may be monitored" notice appears.
3. Scan the QR. Confirm **no** certificate warning and a padlock. Open
   DevTools remote debugging or `chrome://inspect` from the laptop if
   anything is off.
4. Confirm Chrome offers "Install app" (or install from the 3-dot menu).
   Open from the icon; confirm standalone (no address bar). In DevTools >
   Application, confirm the service worker is `activated` and the shell
   cache holds every `SHELL_FILES` entry.
5. Golden path from the installed icon: Start (one-gesture unlock, incl. the
   new notification prompt), identify a scene, toggle detection, open a
   recipe, step through, check doneness, **hold the talk button** for a
   voice command (touch-hold, not click), trigger a timer.
6. Start a timer, switch to another app, screen on. Confirm a notification
   arrives and note how late (throttling). Tap it; confirm the app comes to
   front.
7. Start a timer, lock the screen. Confirm - as expected - no notification;
   confirm the remaining time is correct on unlock via `visibilitychange`.
8. Airplane mode after one full load, then relaunch from the icon: shell
   renders; `/analyze` fails with the spoken network message, not a hang.
9. Clear the app's site data, relaunch: confirm the spoken "not paired" on
   the first API call, re-scan the QR, confirm recovery.
10. Change the laptop's IP (toggle Wi-Fi, or force a new DHCP lease),
    `start.cmd` again: confirm a new leaf was issued, the phone trusts it
    without any phone-side action, and only the URL/QR changed.

Record real-device bugs as their own `fix:` commits.

---

## Phase 8 - Document the decision

**Files:** `DESIGN.md`, `STATUS.md`, `plans/ROADMAP.md`.

Append a `DESIGN.md` decision: PWA over native (ref #1); a local CA in
`lan.py` over mkcert or a public cert (no public domain for a LAN IP; the
`cryptography` dependency already exists; CA-trust survives IP changes, leaf
trust wouldn't); GET-only, allow-list, network-first service worker and why
(no build step, safety of never caching API answers);
`showNotification()` over `new Notification()` (Android); and the explicit
scope boundary - locked-screen timer notification is Phase 9 or never.
Update `STATUS.md`'s "no real device testing" bullet with Phase 7's real
findings. Mark `plans/ROADMAP.md`'s "PWA first" bullet done, pointing here.

**Prompt:**
> Append a numbered decision to `DESIGN.md` covering the points above.
> Update `STATUS.md` with Phase 7's actual findings (ask for them if not
> provided - do not invent results) and mark the "PWA first" roadmap bullet
> done with a link to this plan. Do not commit - stop for review.

**Suggested commit message:** `docs: document the Android PWA decision and update status`

---

## Stretch, deferred by default - Phase 9: Web Push for locked-screen timers

**Not part of the core plan.** Only if Phase 7 shows the locked-screen gap
matters in real use.

What it takes: VAPID keys (`pywebpush`), `POST /push/subscribe` and
`POST /push/cancel` behind the pairing token, a single in-process
`asyncio` scheduler holding pending deadlines (same "one process is enough"
reasoning `rate_limit.py` used), `webpush()` on expiry, and a `push` handler
in `sw.js` calling `showNotification`. Deserves its own phase-by-phase
document if picked up - not an addendum here.
