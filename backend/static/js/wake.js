// Hands-free listening: the browser's own speech recognition runs continuously, and nothing is
// acted on until the wake phrase ("Hey chef", in any language) - or a tap on the talk button,
// which arms it the same way. Words after the wake phrase in the same breath are the command
// ("Hey chef, next step"); a wake phrase on its own waits ARM_MS for the command.
//
// "Hey chef" works while the app itself is talking too (setSpeaking): the cook can cut in with a
// question, a need or something urgent at any moment. While the app talks nothing but the wake
// phrase counts - the recognizer hears the app's own voice as well, and that is never a command.
// Only a sentence that itself says "Hey chef" (the greeting, help) closes the gate while it plays
// (setGate(false) aborts the recognizer and throws its audio away), or it would wake itself.
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
// 1.8 s, not 1 s: a cook thinking mid-sentence ("I have the eggs... and the milk") was cut off and
// half a sentence was acted on. Holding the talk button never cuts off at all (hold()).
export const SETTLE_MS = 1800;
// Released the talk button: how long to wait for the recognizer's final words before acting on
// what was heard so far.
export const RELEASE_FINAL_MS = 1200;

// Of the recognizer's alternatives, the one that woke with a command after it, else any that woke:
// "χέρι σεφ" / "χέι σεφ επανάλαβε" -> the second.
function bestWake(alternatives) {
  const woke = alternatives.map(splitWake).filter((w) => w.woke);
  return woke.find((w) => w.rest.trim()) || woke[0] || null;
}

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
  cleanEcho = (text) => text, // takes the app's own words out of what was heard (echo.js)
} = {}) {
  let rec = null;
  let enabled = false;
  let gateOpen = true;
  let appSpeaking = false; // the app is talking: only the wake phrase counts
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
  // The talk button, held: listen until it's let go - no wake word, no cut-off on a pause.
  let held = false;
  let releasing = false; // let go: waiting for the recognizer's last words
  let releaseTimer = null;
  let heldWords = []; // final results while held
  let heldInterim = ""; // the words still being recognized
  // The lock: commands without the wake word, one after another, until it's unlocked.
  let locked = false;
  let lockTurnedOn = false; // the lock started the recognizer (hands-free was off)

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
    if (!text || held || releasing) return; // held: the cook decides when it's over
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
    armTimer = null;
    // Held or locked, nothing times out: the cook decides.
    if (!held && !releasing && !locked) {
      armTimer = setTimer(() => {
        armTimer = null;
        if (!armed) return;
        armed = false;
        report("idle", mode);
        endOneShot();
        onTimeout();
      }, ARM_MS);
    }
    report(locked ? "locked" : "armed", mode);
  }

  function endOneShot() {
    if (!oneShot) return;
    oneShot = false;
    enabled = false;
    if (rec && (running || starting)) rec.abort();
    report("off");
  }

  function fire(text) {
    if (locked) {
      // Locked: act on it and keep listening for the next one.
      unsettle();
      wokeOn = -1;
      onCommand(text);
      return;
    }
    disarm();
    wokeOn = -1;
    report("idle", mode);
    endOneShot();
    onCommand(text);
  }

  // Let go of the talk button: everything said while it was held, once the last words are in.
  function finishRelease() {
    if (!releasing) return;
    releasing = false;
    if (releaseTimer !== null) clearTimer(releaseTimer);
    releaseTimer = null;
    const text = [...heldWords, heldInterim].join(" ").trim();
    heldWords = [];
    heldInterim = "";
    if (text) {
      fire(text);
      return;
    }
    disarm();
    wokeOn = -1;
    report(locked ? "locked" : "idle", mode);
    endOneShot();
    onTimeout(); // held, nothing said
  }

  function onResult(event) {
    failures = 0;
    if (!gateOpen) return; // the app's own voice, or whatever was said over it
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      const alternatives = Array.from({ length: result.length }, (_, k) => (result[k] && result[k].transcript) || "");
      if (!armed) {
        const hit = bestWake(alternatives);
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
      const heard = bestWake(alternatives);
      // Still talking (a safety alert plays on): what's heard now is the app's own voice.
      if (appSpeaking && !heard) continue;
      const text = cleanEcho((heard ? heard.rest : alternatives[0]).trim());
      if (held || releasing) {
        // Held: gather everything until release - a pause is not the end.
        if (result.isFinal) {
          if (text) heldWords.push(text);
          heldInterim = "";
          if (releasing) finishRelease();
        } else {
          heldInterim = text;
          if (text) onInterim([...heldWords, text].join(" "));
        }
        continue;
      }
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
      lockTurnedOn = false; // ...and so does listening the lock started: unlocking won't stop it
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
      held = false;
      releasing = false;
      locked = false;
      lockTurnedOn = false;
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
    // The talk button pressed (or V held): listening from now until release() - no wake word
    // needed, and a pause doesn't end it. Works with hands-free off too (one command, then off).
    hold() {
      if (!Recognition) return false;
      if (!enabled) {
        enabled = true;
        oneShot = !locked;
      }
      gateOpen = true;
      held = true;
      releasing = false;
      heldWords = [];
      heldInterim = "";
      wokeOn = -1;
      arm();
      ensureRunning();
      return true;
    },
    // Let go: whatever was said while held is acted on, after the recognizer's last words.
    release() {
      if (!held) return;
      held = false;
      releasing = true;
      if (rec && running) rec.stop(); // hands over the final words
      releaseTimer = setTimer(finishRelease, RELEASE_FINAL_MS);
    },
    // The lock: listen for commands without the wake word, one after another, until unlocked.
    setLocked(on) {
      if (Boolean(on) === locked || !Recognition) return;
      locked = Boolean(on);
      if (locked) {
        if (!enabled) {
          enabled = true;
          lockTurnedOn = true;
        }
        oneShot = false;
        gateOpen = true;
        wokeOn = -1;
        arm();
        ensureRunning();
        return;
      }
      disarm();
      if (lockTurnedOn) {
        lockTurnedOn = false;
        enabled = false;
        if (rec && (running || starting)) rec.abort();
        report("off");
      } else {
        report("idle", mode);
      }
    },
    isLocked: () => locked,
    isHeld: () => held,
    // Closed: nothing is heard at all (the recognizer is aborted). Opening restarts it.
    setGate,
    // The app started or stopped talking. Listening goes on - "Hey chef" can interrupt - unless
    // the sentence being said itself says "Hey chef": then the gate is closed until it's over.
    setSpeaking(on, { saysWake = false } = {}) {
      appSpeaking = Boolean(on);
      setGate(!(on && saysWake));
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
    isAppSpeaking: () => appSpeaking,
    mode: () => mode,
  };

  function setGate(open) {
    if (open === gateOpen) return;
    gateOpen = open;
    if (!open) {
      unsettle();
      if (rec && (running || starting)) rec.abort();
    } else {
      ensureRunning();
    }
  }
}
