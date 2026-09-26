# Design decisions

A numbered log of the decisions that shaped this rebuild and why, in
roughly the order they came up while building.

## 1. Web app, not a native app (React Native, etc.)

A tablet's browser already has camera, mic, speech synthesis, vibration and
a wake lock API - all reachable from plain JS with no app store, no build
pipeline, no code signing. `adb reverse` gets a browser talking to a laptop
backend over USB in one command. A native app buys nothing here that the
browser doesn't already give for free, at a much higher setup cost for a
demo.

## 2. No speech-to-text

The interaction surface is deliberately small: point-and-ask, yes/no,
check/repeat/next/stop, all reachable by touch or a Bluetooth shutter
remote acting as a keyboard. Free-form voice input would need a
wake-word, a much larger vocabulary, and failure modes (misheard word while
a pan is sizzling) that are worse than just tapping a big button with wet
hands.

## 3. One Pydantic schema, not three hand-written JSON Schemas

`AnalyzeResponse` is defined once in `schemas.py` and each provider SDK
builds its own strict JSON Schema from it. A hand-written schema using
`{"type": ["string", "null"]}` union syntax fails Anthropic's schema
normalizer outright - `test_smoke.py`'s `TestProviderSeam` class is the
regression test for exactly that, running the real internal normalizer from
each of the three SDKs (`anthropic.lib._parse._transform.transform_schema`,
`openai.lib._pydantic.to_strict_json_schema`,
`google.genai._transformers.t_schema`) against the one schema and asserting
none of them raise.

## 4. Safety rules live in the backend, not the system prompt

`_apply_protein_safety` and `_apply_safety_flag` in `main.py` run on every
response, from both the fixture branch and the live branch - `DEMO_MODE`
must never be a way to skip a safety rule, and a prompt instruction is
something a model can drift on across a provider update; a small, tested
Python function can't. The recipe-curated tri-state
(`step_contains_raw_protein` returning `True`/`False`/`None`) beating a
model's own raw-protein guess is the concrete case this exists for: the
pancake batter genuinely contains raw egg, and a model that (correctly)
flags that would otherwise trigger "use a meat thermometer on a pancake" -
useless advice that the recipe's own curation vetoes.

## 5. The client never sends a reference image

Only `recipe_id`/`step_index` cross the wire; the backend resolves the
actual reference file from disk. This means a reference photo can be
replaced without touching the client at all, and the client never needs to
know a reference exists for a given step - `AnalyzeRequest` deliberately has
no `reference_image` field.

## 6. Ratio-based monitoring, not absolute thresholds

Auto-exposure and auto-white-balance are servos whose entire job is to
cancel exactly the signal a naive brightness/color reading would measure -
browning lowers reflectance, the camera raises gain to compensate, and raw
luma sits flat while the food visibly darkens. A ratio between two regions
of the *same* frame (centre food vs. annulus background) cancels a uniform
per-channel gain shift algebraically, and survives gamma too. Numbers
actually measured by `features.test.mjs` while building this (all far
inside the bounds the test asserts):

- `brownRB` drift under a simulated **+40%/-30% uniform AE gain**: `0.00000`
  in both directions - the ratio genuinely doesn't move.
- `brownRB` drift under a simulated **warm/cool white-balance shift**
  (asymmetric per-channel gain): `0.00081` (warm) / `0.00454` (cool).
- `brownRB` **rise from a pale-to-golden-brown colour shift**: `0.5166`.
- That signal is **113.7x** the worst artefact drift measured above - not
  just bigger, an order of magnitude bigger.
- Browning plus a *simultaneous* AE compensation still reads within
  `0.00000` of browning alone.
- A near-black annulus (matte hob, no usable reference) correctly flags
  `referenceOk: false`.

`monitor.js`'s thresholds (`K`, `MOTION_Z`, `REBASE_Z`) are all expressed in
sigma measured from *this kitchen* during the first 3 seconds of the
current step, never as absolute constants - the lighting in one kitchen is
not the lighting in another.

## 7. No model training

Every "is it done" judgment is either a general-purpose vision model call or
a local sigma-based change detector over hand-derived, illumination-invariant
ratios - not a trained classifier. There's no labeled dataset, no training
pipeline, and nothing that needs retraining if the camera or lighting
changes; the ratio design (#6) is what makes that tractable without one.

## 8. Two-switch demo mode

`DEMO_MODE` alone still falls through to a live call on a fixture miss, so
a rehearsal run doesn't dead-end mid-demo if a fixture wasn't recorded for
some path. `DEMO_STRICT` is the second, stricter switch that returns a
canned response on a miss instead - required for a genuinely offline run
(a venue with no reliable network). Splitting these into two flags instead
of one means "mostly-live but backstopped" and "fully offline" are both
reachable without a code change.

## 9. Per-model latency: partially measured now

The plan for this rebuild called for recording measured per-provider
latency once real providers were tested. For most of this rebuild that
hadn't happened - no real API key for any provider had been available, so
every live network call deliberately used an invalid key to verify error
handling (`check_providers.py` correctly reporting `FAIL` on a real 401, in
~3-5s, which is HTTP round-trip and auth-rejection time, not inference
time).

**Gemini, now measured**: with a real `GEMINI_API_KEY`,
`scripts/check_providers.py`'s real `check_doneness` call against the
pancake reference step completed in **14.3s**. That run also exercised the
`GEMINI_MODEL` fallback chain (#8/DESIGN's provider-seam design) for real:
the first two models (`gemini-3.7-flash`, `gemini-3.8-flash`) both returned
a transient `503 UNAVAILABLE`, and the third (`gemini-3.6-flash`) succeeded
- confirming the fallback logic in `vision._call_gemini` behaves correctly
under a real transient-error condition, not just in tests. Anthropic and
OpenAI timings are still unmeasured - whoever runs this with a real key for
either should record it here.

## 10. USB (`adb reverse`) over self-signed HTTPS as the default bring-up path

`getUserMedia`/`wakeLock` require a secure context, so *some* form of HTTPS
or `localhost` is unavoidable. `adb reverse tcp:8000 tcp:8000` makes the
tablet's browser see the backend as `localhost` over USB - no certificate,
no network configuration, no "this connection is not private" warning to
click through in front of an audience. Self-signed HTTPS is kept as a
fallback for iOS (no USB debugging equivalent) or a tablet not physically
tethered, accepting the one-time certificate warning as the cost.

## 11. One-gesture unlock

`AudioContext.resume()`, the first `speechSynthesis.speak()`,
`getUserMedia`, `wakeLock.request()`, and `navigator.vibrate` all need a
user activation, and on iOS they need the *same* one - `boot()` is called
only from the Start button's click handler, never on page load, and claims
every one of these inside that single gesture.

## 12. Aiming as sound, not as a viewfinder overlay

The person using this can't necessarily look at the screen while aiming a
phone/tablet at a pan - that's the whole premise of the app. `aim.js` turns
framing quality into a pitch/rate-modulated tone (`440 + 440*score` Hz,
firing at `1.5 + 6.5*score` Hz) instead of an on-screen box, so "am I
pointed at the right thing" is answerable without looking.

## 13. Output-injection guard as a second, model-independent check

The vision input is a photo, and the model's free-text output
(`spoken_response`, `evidence`, `clarifying_question`) is spoken directly to
a user who often can't look at the screen to cross-check it. A printed
card, phone screen, or sticker in frame could try to steer the model into
saying something other than what's in the pan. `_apply_protein_safety`/
`_apply_safety_flag` already run over structured fields the model
self-reports (#4), but nothing checked the free-text fields before this.

`backend/app/output_guard.py` adds two passes, run on every `/analyze`
response (fixture and live), before the existing safety rules:

1. `scan_for_injection`/`sanitize_response`: a short, reviewed list of
   meta-instruction markers ("ignore previous", "you are now", ...). A hit
   replaces the whole response with the same schema-valid fallback a failed
   API call already produces, rather than trying to salvage individual
   fields.
2. `check_confidence_plausibility`/`apply_plausibility_check`: a softer
   pass that downgrades (never discards) a response claiming
   `confidence: "high"` with no evidence, or reassurance language
   ("safe", "no flame") paired with a doneness claim and no safety flag -
   the shape of a false-safety-claim injection, and the highest-severity
   case since a blind user trusts "it's done" without a way to verify it.

Flagged/downgraded events are logged (`log_flagged_response`) with
investigative context (mode/recipe_id/step_index/language) but never the
image bytes, so they're visible after the fact without becoming a size or
privacy liability.

**Residual risk, stated plainly**: these are heuristic checks, not a
guarantee. A sufficiently novel injection that avoids the marker list and
produces plausible-looking confidence/evidence will not be caught. See
`backend/SECURITY_THREAT_MODEL_vision.md` for the threat categories this
targets. A genuinely stronger defense would be a second model call
specifically to classify the first model's output for injection/false
claims, at roughly 2x the cost and latency per analysis - noted here as a
future option, not built in this pass.

## 15. Opt-in pairing-token auth, sized for a household, not a SaaS

`main.py` has no authentication, no rate limiting, and no request size cap
by default - a reasonable default for this app's actual deployment shapes
(`adb reverse`/USB, where traffic never leaves the cable, or `localhost`).
It stops being reasonable the moment the self-signed-HTTPS-on-a-LAN
fallback (#10) is reachable by anyone untrusted on that network: they could
burn API credits via `/analyze` or use `/barcode/{code}` as an open,
unauthenticated proxy to Open Food Facts. See
`backend/SECURITY_THREAT_MODEL_network.md` for the full trust-boundary
writeup.

**`BACKEND_PAIRING_TOKEN`** (`backend/app/auth.py`) is off by default -
blank/unset leaves every route working exactly as before, same "opt-in,
never breaks the existing demo/dev flow" shape as `DEMO_MODE` (#8). When
set, `Depends(require_pairing_token)` gates `/analyze`, `/barcode/{code}`,
`/recipes`, `/recipes/{recipe_id}`, and `/reference/{recipe_id}/{step_index}`
behind an `X-Pairing-Token` header matching the configured secret -
deliberately **not** `/health` (a health check shouldn't need a secret) and
**not** the static file mount (inert HTML/JS/CSS costs nothing to serve
unauthenticated). The client (`api.js`/`app.js`) captures a `?token=` query
param into `localStorage` once, during device pairing, then attaches it as
a header on every call after.

**Rate limiting** (`backend/app/rate_limit.py`, an in-memory per-key
sliding window - no new dependency, matches this project's "no Docker, no
build step" simplicity) caps `/analyze` at 20 requests/hour and
`/barcode` at 60 requests/hour, per client IP, returning `429` +
`Retry-After` on rejection.

**Size caps** on `/analyze` reject an oversized `Content-Length` before the
body is even read (ASGI middleware, 15MB ceiling) and an oversized decoded
image after base64 decoding (10MB ceiling), so a paid vision-provider call
is never made against a garbage or oversized payload.

**Explicitly sized for one household's devices, not multi-tenant SaaS**:
one shared secret, not per-user accounts, OAuth, or anything else that
would need an identity system. Confirmed the whole `pytest backend/tests`
suite (104 passed) and a live `uvicorn` run stay green/unchanged with
`BACKEND_PAIRING_TOKEN` unset, and that setting it correctly rejects a
missing/wrong header while `/health` and the static mount stay
unauthenticated either way.

## 16. Pretrained detection, chosen by measurement - "cut down" without training

The ask was a big YOLO model "cut down" to kitchen classes and hands, without training one.
You can't prune a network's architecture without retraining it, so "cut down" here means:
- restrict the **vocabulary**;
- pick the **smallest model and input size** that holds the frame-rate target;
- export to the **fastest runtime** on the actual machine.

Two pretrained families compete in `scripts/benchmark_detectors.py`:

- `yolov8*-oiv7`: closed vocabulary, trained on Open Images V7. It already knows Human hand,
  Kitchen knife, Frying pan, Cutting board, Spatula, Whisk and so on; cutting down is class
  filtering.
- `yoloe-26*`: open vocabulary. `set_classes(prompts)` gives any list (pot, onion, raw meat,
  boiling water...), and export bakes it into the weights. The ~254 MB text encoder is then
  only needed at export time.

`app/detection/vocabulary.json` is the single class list both map onto. The preview, the
per-recipe narrowing and the importer's ingredient linking all use the same ids.

Hands come from MediaPipe Hand Landmarker rather than a box class, because its 21 landmarks
give fingertips. That is what makes "touching" answerable instead of just "near".

The selection rule is written down, not tuned by eye. Among configurations whose detector +
hands median latency fits 170 ms (about 4.5 FPS end to end on the target laptop), the winner
is the one with the highest group-weighted AP50. Hands, utensils and cookware weigh double;
the experimental cooking-state classes weigh half. The finalists are then re-timed
*interleaved*, frame by frame, because a long sequential sweep on a laptop is skewed by
thermal throttling. See `data/benchmarks/detector_report.md` for the measured result and its
caveats (Open Images favors the oiv7 family; the classes only YOLOE knows can't be scored there).

**Result on the reference laptop** (Ryzen 5 4500U, no CUDA, 1,011 Open Images photos):
**YOLOE-26s at 480 px on OpenVINO**, weighted AP50 **0.446** at 102 ms per frame with hands.
- The open-vocabulary model beat every Open-Images-trained one on Open Images' own photos.
  The best oiv7 model that fit, `yolov8m` at 320 px, scored 0.351.
- YOLOE-26s at 320 px is nearly as accurate (0.443) at 61 ms. It's the pick if frame rate
  matters more.
- Larger variants and 640 px inputs didn't fit the budget.
- OpenVINO beat ONNX Runtime and PyTorch on this AMD CPU every time; ONNX Runtime was often
  the *slowest*.

Hands use **hybrid** mode: MediaPipe alone had precision 0.97 but recall only 0.36, because
it needs most of the hand in frame. Adding the detector's hand boxes that MediaPipe missed
raised hand AP50 from 0.356 to 0.448. Those extra hands are box-only (no fingertips).

A known confusion: YOLOE sometimes calls a kitchen knife "scissors".

## 17. Detection runs on the laptop, per frame over HTTP

`POST /detect` takes a raw JPEG (no base64), and the client keeps exactly one request in
flight. That gives natural backpressure: a slow frame delays the next one instead of queueing
them. Local inference means frames never leave the machine and cost nothing, unlike `/analyze`.

The endpoint reads its own body with a running byte cap *after* the auth and rate-limit
dependencies run. So an unauthenticated or chunked upload can't make the server buffer
anything; the older Content-Length middleware can't stop a chunked body.

**Speed on a 15 W laptop CPU.** The benchmark measured each frame alone. In the app it's
continuous load, and that behaves differently: sending the next frame the instant a reply
landed kept the CPU at 100%, and within ~30 s the chip hit its power limit (the same inference
went from ~90 ms to 385 ms median, 808 ms peak). Three changes, measured together under load,
took a frame from 318 ms to 195 ms (−39%) with the same detections:
- **Letterbox to the frame's own shape** (`DETECTOR_RECT=true`, a dynamic-shape export of the
  same model). A 16:9 webcam frame becomes 480×288 instead of 480×480 with padding, 24–42%
  less work at the same resolution. Dropping to 320 px was faster still but missed the knife
  on real frames, although the Open Images scores for 320 and 480 were nearly equal.
- **MediaPipe hands run alongside the detector** on their own thread. Both release the GIL,
  so a frame costs max(detector, hands), not the sum.
- **At most ~6 frames/s** (`MIN_FRAME_MS` in `detect.js`, above the 4–5 FPS goal), which
  leaves the CPU headroom so it doesn't throttle.

The camera has no depth, so relations are "touching" (overlap in the image), "over" (inside a
much larger object's box, e.g. a stove) and "near". They are shown visually only. Speaking
them as reassurance ("your hand is clear of the knife") would be a safety claim a 2D detector
can't back.

## 18. SQLite, with imported recipes staged until a human curates them

A single stdlib-sqlite3 file keeps the no-Docker, no-server setup (#1). `recipes.py` kept its
read API, so `/analyze`, `/recipes` and `vision.py` didn't change.

Every row has a status. The importer only ever writes `staged`, and only `published` recipes
are served or used by the safety rules. So DESIGN #4's premise (safety fields are a human
decision) survives importing thousands of recipes.

`data/recipes.json` stays the version-controlled seed, and `curate_recipe.py --export` writes
curated recipes back to it.

## 19. Any-URL import via schema.org, not per-site scrapers

Most recipe sites publish schema.org `Recipe` data because search engines reward it. The
MIT-licensed `recipe-scrapers` library reads it: 725 site-specific scrapers plus a generic
fallback. That covers "any recipe website" with one code path, where the Akis importer needed
a scraper per site.

Fetching stays in `importers/http.py`. The importer is polite by default:
- `robots.txt` is honoured;
- the User-Agent is honest (the browser one is opt-in);
- a page fetched in the last 7 days isn't fetched again.

Staged ids come from a hash of the URL, never from page content, so no remote text reaches
anything id- or path-shaped (the importer path-traversal finding). Step durations, ingredient
quantities and equipment are parsed as *suggestions* that the curator confirms.

## 20. Buttons speak on long-press / hover, below every other voice

Long-press on a touch screen speaks the button's description and swallows the click that
would follow. Mouse hover (PC demo) and keyboard focus speak too.

These "hints" are the lowest TTS priority: a hint never interrupts real speech, and only
replaces another hint. The same change fixed an older ordering bug: a routine command
("Let me take a look") could cut off a safety alert mid-sentence. It now queues behind it.
