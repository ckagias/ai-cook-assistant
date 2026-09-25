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

## 9. Per-model latency: not yet measured here

The plan for this rebuild called for recording measured per-provider
latency once real providers were tested. That hasn't happened in this
environment - no real API key for any provider has been available here, so
every live network call made during this rebuild deliberately used an
invalid key to verify error handling (`check_providers.py` correctly
reporting `FAIL` on a real 401, in ~3-5s, which is HTTP round-trip and
auth-rejection time, not inference time). Whoever runs this with a real key
should record real `check_doneness` timings here.

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
