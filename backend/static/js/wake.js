// Hands-free listening: the browser's own speech recognition runs continuously, and nothing is
// acted on until the wake phrase ("Hey chef" / "Γεια σου σεφ") - or a tap on the talk button,
// which arms it the same way. Words after the wake phrase in the same breath are the command
// ("Hey chef, next step"); a wake phrase on its own waits ARM_MS for the command.
//
// Everything heard while the app itself is speaking is dropped (setGate(false) aborts the
// recognizer and throws its audio away): the app must never take its own voice for a command,
// and "Say “Hey chef”" in a spoken hint must not wake it.
//
// Privacy: where the browser offers on-device recognition (processLocally) it is used; otherwise
// the browser streams microphone audio to its speech service (Google for Chrome, Microsoft for
// Edge) for as long as hands-free is on. The toggle turns it off; the talk button still works.

import { splitWake } from "./commands.js";

export const ARM_MS = 8000; // wake phrase alone: how long to wait for the command
export const RESTART_MS = 250;
export const MAX_BACKOFF_MS = 15000;
// Chrome's cloud recognizer never marks a Greek (el-GR) result final in continuous mode - the
// words only grow, even across long pauses (measured: nothing final in 30 s of "Γεια σου σεφ,
// επόμενο βήμα" on a loop). English finalizes on its own within ~0.5 s. So once the wake phrase
// is heard and the words stop changing for SETTLE_MS, stop() the session: that hands over the
// final result at once (measured ~0.1 s later), and onend starts a fresh session.
export const SETTLE_MS = 1000;

export function getRecognition(g = globalThis) {
  return g.SpeechRecognition || g.webkitSpeechRecognition || null;
}

// "available" -> the browser can recognize this language on the device.
async function localAvailable(Recognition, lang) {
  if (!Recognition || typeof Recognition.available !== "function") return false;
  try {
    const answer = await Promise.race([
      Recognition.available({ langs: [lang], processLocally: true }),
      new Promise((resolve) => setTimeout(() => resolve("timeout"), 1500)),
    ]);
    return answer === "available";
  } catch {
    return false;
  }
}

export function createWakeListener({
  Recognition = getRecognition(),
  lang = "el-GR",
  onWake = () => {}, // the wake phrase was heard (or the talk button pressed): give feedback now
  onCommand = () => {}, // (text) the words to act on
  onInterim = () => {}, // (text) live caption while armed
  onTimeout = () => {}, // armed, but nothing followed
  onState = () => {}, // ("idle" | "armed" | "off" | "error", detail)
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
  probeLocal = localAvailable,
} = {}) {
  let rec = null;
  let enabled = false;
  let gateOpen = true;
  let running = false;
  let starting = false;
  let armed = false;
  let armTimer = null;
  let settleTimer = null;
  let restartTimer = null;
  let failures = 0;
  let wokeOn = -1; // result index whose wake phrase already fired onWake
  let mode = "cloud";
  let oneShot = false; // listenNow() with hands-free off: stop again after this one command

  function report(state, detail) {
    onState(state, detail);
  }

  function build() {
    const r = new Recognition();
    r.lang = lang;
    r.continuous = true;
    r.interimResults = true;
    r.maxAlternatives = 3;
    if (mode === "local") r.processLocally = true;
    r.onstart = () => {
      starting = false;
      running = true;
    };
    r.onresult = onResult;
    r.onerror = onError;
    r.onend = onEnd;
    return r;
  }

  function unsettle() {
    if (settleTimer !== null) clearTimer(settleTimer);
    settleTimer = null;
  }

  // Words are still coming in after the wake phrase: once they stop changing, ask for the final.
  // Only when there are words to act on - the wake phrase alone keeps listening (a stop() then
  // would restart the session just as the cook starts the command).
  function settleLater(text) {
    unsettle();
    if (!text) return;
    settleTimer = setTimer(() => {
      settleTimer = null;
      if (rec && running && (armed || wokeOn !== -1)) rec.stop();
    }, SETTLE_MS);
  }

  function disarm() {
    unsettle();
    armed = false;
    if (armTimer !== null) clearTimer(armTimer);
    armTimer = null;
  }

  function arm() {
    armed = true;
    if (armTimer !== null) clearTimer(armTimer);
    armTimer = setTimer(() => {
      armTimer = null;
      if (!armed) return;
      armed = false;
      report("idle", mode);
      endOneShot();
      onTimeout();
    }, ARM_MS);
    report("armed", mode);
  }

  function endOneShot() {
    if (!oneShot) return;
    oneShot = false;
    enabled = false;
    if (rec && (running || starting)) rec.abort();
    report("off");
  }

  function fire(text) {
    disarm();
    wokeOn = -1;
    report("idle", mode);
    endOneShot();
    onCommand(text);
  }

  function onResult(event) {
    failures = 0;
    if (!gateOpen) return; // the app's own voice, or whatever was said over it
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      const alternatives = Array.from({ length: result.length }, (_, k) => (result[k] && result[k].transcript) || "");
      if (!armed) {
        const hit = alternatives.map(splitWake).find((w) => w.woke);
        if (!hit) continue;
        if (wokeOn !== i) {
          wokeOn = i;
          arm();
          onWake();
        }
        if (!result.isFinal) settleLater(hit.rest.trim());
        if (result.isFinal) {
          if (hit.rest.trim()) fire(hit.rest.trim());
          else wokeOn = -1; // the wake phrase alone: stay armed for the next result
        }
        continue;
      }
      // Armed: the command, possibly repeating the wake phrase in front.
      const heard = alternatives.map(splitWake).find((w) => w.woke);
      const text = (heard ? heard.rest : alternatives[0]).trim();
      if (!result.isFinal) {
        if (text) {
          onInterim(text);
          arm(); // still talking - keep waiting
        }
        settleLater(text);
      } else if (text) {
        fire(text);
      }
    }
  }

  function onError(event) {
    const code = event && event.error;
    if (code === "not-allowed" || code === "service-not-allowed" || code === "audio-capture" || code === "language-not-supported") {
      enabled = false;
      disarm();
      report("error", code);
    } else if (code === "network") {
      failures += 1;
    }
    // "no-speech" and "aborted" are routine: onend follows and restarts.
  }

  function onEnd() {
    running = false;
    starting = false;
    scheduleRestart();
  }

  function scheduleRestart() {
    if (!enabled || !gateOpen || restartTimer !== null) return;
    // Chrome ends a continuous session every minute or so, and on network trouble; back off
    // when it keeps ending straight away so a dead connection isn't hammered.
    const delay = Math.min(MAX_BACKOFF_MS, RESTART_MS * 2 ** failures);
    restartTimer = setTimer(() => {
      restartTimer = null;
      ensureRunning();
    }, delay);
  }

  function ensureRunning() {
    if (!enabled || !gateOpen || running || starting) return;
    if (!rec) rec = build();
    starting = true;
    try {
      rec.start();
    } catch {
      // InvalidStateError: already started - onstart/onend will settle the flags
      starting = false;
    }
  }

  return {
    supported: () => Boolean(Recognition),
    async start() {
      if (!Recognition) {
        report("error", "unsupported");
        return false;
      }
      oneShot = false; // a running one-shot becomes the real thing
      if (enabled && rec) return true;
      enabled = true;
      failures = 0;
      mode = (await probeLocal(Recognition, lang)) ? "local" : "cloud";
      if (!enabled) return false; // stopped while probing
      report("idle", mode);
      ensureRunning();
      return true;
    },
    stop() {
      enabled = false;
      oneShot = false;
      disarm();
      if (restartTimer !== null) clearTimer(restartTimer);
      restartTimer = null;
      if (rec && (running || starting)) rec.abort();
      report("off");
    },
    // The talk button: listen for a command right now, no wake phrase needed. Works even when
    // hands-free is off - then the recognizer runs just for this one command.
    listenNow() {
      if (!Recognition) return false;
      if (!enabled) {
        enabled = true;
        oneShot = true;
      }
      gateOpen = true;
      wokeOn = -1;
      arm();
      ensureRunning();
      return true;
    },
    // Closed while the app speaks. Opening again restarts recognition.
    setGate(open) {
      if (open === gateOpen) return;
      gateOpen = open;
      if (!open) {
        unsettle();
        if (rec && (running || starting)) rec.abort();
      } else {
        ensureRunning();
      }
    },
    setLang(next) {
      lang = next;
      if (rec) {
        rec.lang = next;
        if (running) rec.abort(); // onend restarts it with the new language
      }
    },
    isOn: () => enabled,
    isArmed: () => armed,
    isGateOpen: () => gateOpen,
    mode: () => mode,
  };
}
