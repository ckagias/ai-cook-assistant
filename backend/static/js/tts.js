let speaking = false;
let gateListener = null;
let greekVoice = null;
let voiceProbeDone = false;
let forcedLang = null;
let keepAlive = null;

// Higher rank wins. "hint" is a button description (long-press / hover) - it must never cut
// off real speech. A "command" must never cut off a playing "safety" alert.
export const PRIORITY_RANK = { hint: 0, checkin: 1, command: 2, safety: 3 };
let current = null; // the utterance actually playing, so a late onend from a cancelled one is ignored
let currentRank = -1;

export function registerAcousticGate(fn) {
  gateListener = fn;
}

export function isSpeaking() {
  return speaking;
}

function setAcousticMonitor(enabled) {
  // The gate must be registered explicitly, even as a no-op - a gate that's
  // never wired up was a real bug once, and this guard makes that silent again.
  if (gateListener) {
    gateListener(enabled);
  }
}

export function didFallBackToEnglish() {
  return forcedLang === "en";
}

export function effectiveLang(requested) {
  return forcedLang || requested;
}

export function probeVoices(preferredLang) {
  return new Promise((resolve) => {
    if (voiceProbeDone) {
      resolve(effectiveLang(preferredLang));
      return;
    }

    let settled = false;

    function finish() {
      if (settled) return;
      settled = true;
      voiceProbeDone = true;
      window.speechSynthesis.removeEventListener("voiceschanged", onVoicesChanged);

      const voices = window.speechSynthesis.getVoices() || [];
      greekVoice = voices.find((v) => v.lang && v.lang.toLowerCase().startsWith("el")) || null;
      if (!greekVoice) {
        forcedLang = "en";
      }
      resolve(effectiveLang(preferredLang));
    }

    function onVoicesChanged() {
      finish();
    }

    // Safari may populate synchronously and never fire "voiceschanged".
    const initial = window.speechSynthesis.getVoices();
    if (initial && initial.length > 0) {
      finish();
      return;
    }

    // Chrome returns [] on first call and fires the event later - listen for
    // both that AND a 2000ms fallback in case neither ever arrives.
    window.speechSynthesis.addEventListener("voiceschanged", onVoicesChanged);
    setTimeout(finish, 2000);
  });
}

function buildUtterance(text, lang) {
  const u = new SpeechSynthesisUtterance(text);
  const effective = effectiveLang(lang);
  u.lang = effective === "el" ? "el-GR" : "en-US";
  // Setting .lang alone is unreliable in Chrome, which often ignores the tag.
  if (effective === "el" && greekVoice) {
    u.voice = greekVoice;
  }

  u.onstart = () => {
    speaking = true;
    setAcousticMonitor(false);
    clearInterval(keepAlive);
    // Chrome cuts speech off after ~15s of silence from the tab; a pause/resume
    // keepalive every 10s prevents that.
    keepAlive = setInterval(() => {
      if (!window.speechSynthesis.speaking) {
        clearInterval(keepAlive);
        return;
      }
      window.speechSynthesis.pause();
      window.speechSynthesis.resume();
    }, 10000);
  };

  const onDone = () => {
    // cancel() fires the cancelled utterance's end/error asynchronously - possibly after the
    // next one was queued. Only the most recently queued utterance may clear the state.
    if (current !== u) return;
    current = null;
    currentRank = -1;
    speaking = false;
    clearInterval(keepAlive);
    keepAlive = null;
    setAcousticMonitor(true);
  };
  u.onend = onDone;
  u.onerror = onDone;

  return u;
}

// Returns false when the text was dropped (a hint while something more important plays).
export function speak(text, { priority = "checkin", lang = "el" } = {}) {
  if (!text) return false;
  const rank = PRIORITY_RANK[priority] ?? PRIORITY_RANK.checkin;
  const synth = window.speechSynthesis;
  const busy = speaking || synth.speaking || synth.pending;

  if (priority === "hint") {
    // Only ever replaces another hint; never cancels queued or playing real speech.
    if (busy && (currentRank > PRIORITY_RANK.hint || synth.pending)) return false;
    if (busy) synth.cancel();
    currentRank = rank;
  } else if (priority === "safety" || (priority === "command" && currentRank < PRIORITY_RANK.safety)) {
    synth.cancel();
    speaking = false;
    setAcousticMonitor(false);
    currentRank = rank;
  } else {
    // Queued behind whatever is playing (a checkin, or a command during a safety alert):
    // the queue keeps the highest rank it holds until it drains.
    currentRank = Math.max(currentRank, rank);
  }
  const u = buildUtterance(text, lang);
  current = u;
  synth.speak(u);
  return true;
}

export function fireSafetyInterrupt(message, lang) {
  speak(message, { priority: "safety", lang });
}

// The cook pressed talk: stop talking over them - unless a safety alert is playing, which
// nothing may cut off. Returns false when it was left alone.
export function hush() {
  const synth = window.speechSynthesis;
  if (currentRank >= PRIORITY_RANK.safety && (speaking || synth.speaking || synth.pending)) return false;
  stopAll();
  return true;
}

export function stopAll() {
  window.speechSynthesis.cancel();
  current = null;
  currentRank = -1;
  speaking = false;
  clearInterval(keepAlive);
  keepAlive = null;
  setAcousticMonitor(true);
}
