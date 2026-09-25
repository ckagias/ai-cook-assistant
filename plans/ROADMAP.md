# Roadmap

Forward-looking, not a phase-by-phase implementation plan like the
`PLAN_*.md` files - this is a short list of what's next once the MVP is
stable, grouped by theme.

## Security: prompt injection and hardening - done

The vision pipeline speaks a model's output directly to a user who often
can't verify it against what's actually in front of them - that's a
real, specific attack surface this app has that a typical chat app
doesn't. `PLAN_SECURITY_PROMPT_INJECTION.md` and
`PLAN_SECURITY_NETWORK_HARDENING.md` implemented everything below; see
`DESIGN.md` #13 and #15 and `backend/SECURITY_THREAT_MODEL_vision.md` /
`backend/SECURITY_THREAT_MODEL_network.md` for the full writeups.

- ~~**Image-borne prompt injection.**~~ `backend/app/output_guard.py` now
  scans `spoken_response`/`evidence`/`clarifying_question` for
  meta-instruction markers (replacing a hit with the standard fallback) and
  downgrades implausibly confident/reassuring responses - defense-in-depth,
  not a guarantee; see `DESIGN.md` #13 for the stated residual risk.
- ~~**No auth on the backend at all.**~~ Opt-in `BACKEND_PAIRING_TOKEN`
  (`backend/app/auth.py`), off by default so the existing `adb reverse`/dev
  flow is unchanged. Gates `/analyze`, `/barcode`, `/recipes`, and
  `/reference` behind an `X-Pairing-Token` header; `/health` and the static
  mount stay open.
- ~~**No request size/rate limits on `/analyze`.**~~ Per-IP rate limiting
  (`backend/app/rate_limit.py`: 20/hr on `/analyze`, 60/hr on `/barcode`,
  `429` + `Retry-After`) and two size-cap layers on `/analyze` (a
  `Content-Length` check before the body is read, and a post-decode byte
  check before any vision-provider call).
- ~~**Dependency and secret hygiene as the codebase grows.**~~
  `backend/scripts/check_dependencies.py` wraps `pip-audit` against
  `requirements.txt` (currently zero findings). Not wired into CI yet -
  there is no CI pipeline in this repo - so it's a periodic manual run.
- **General pass, still open**: the `security-review` gate for when the
  import/combine features land is in place (a callout was added to both
  `PLAN_IMPORT_AKIS.md` and `PLAN_COMBINE_RECIPES.md`), but the actual
  review can't happen until that branch exists.

## Mobile implementation

The MVP deliberately chose a browser + `adb reverse` over a native app
(see `DESIGN.md` #1) - that was the right call for a hackathon demo, not
necessarily the final answer.

- **PWA first, cheapest next step.** Add a manifest + service worker to
  the existing static client so it's installable ("Add to Home Screen")
  and can cache its own static assets for a faster/offline-tolerant
  launch. Same backend, same code, no new platform to maintain - this is
  the natural next step before considering a native rewrite.
- **Background timers are the real gap a browser can't close.** The
  step timer (`session.js`) and the local monitor (`monitor.js`) both stop
  running the moment the tab is truly backgrounded on mobile OSes, not
  just throttled - `visibilitychange` catches up a *missed* deadline on
  resume, but can't fire a notification while the phone is in a pocket.
  A native (or PWA + push notifications) implementation would need a real
  OS-level timer/notification for "your pasta is ready" to work with the
  screen off.
- **Native app (React Native or platform-native), if it's ever worth it.**
  Would mean re-implementing the camera/mic/audio-priority stack
  (`boot.js`, `tts.js`, `aim.js`) against native APIs instead of Web APIs,
  in exchange for real background execution, push notifications, and app
  store distribution. Significant lift - only worth it once the PWA path
  has proven the product, not before.
- **Real hosting**, once this leaves a laptop-as-backend model: a
  deployed HTTPS endpoint instead of `adb reverse`/self-signed certs, plus
  whatever the auth work above ends up requiring.
