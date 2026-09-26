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
// What is still to be said, in order: the utterance playing, then the queue behind it. Kept so an
// interruption ("Hey chef") can pick up where it stopped - see interrupt().
let unsaid = []; // [{ text, priority, lang, u, spokenTo }]

export function registerAcousticGate(fn) {
  gateListener = fn;
}

export function isSpeaking() {
  return speaking;
}

// enabled = the app is quiet. While it speaks, the listener also gets the words being said, so
// it can tell a sentence that itself says "Hey chef" (the greeting, help) from any other.
function setAcousticMonitor(enabled, text = "") {
  // The gate must be registered explicitly, even as a no-op - a gate that's
  // never wired up was a real bug once, and this guard makes that silent again.
  if (gateListener) {
    gateListener(enabled, text);
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

function buildUtterance(text, lang, entry) {
  const u = new SpeechSynthesisUtterance(text);
  const effective = effectiveLang(lang);
  u.lang = effective === "el" ? "el-GR" : "en-US";
  // Setting .lang alone is unreliable in Chrome, which often ignores the tag.
  if (effective === "el" && greekVoice) {
    u.voice = greekVoice;
  }
  // Where the voice has got to (not every voice reports it; then a resume repeats the sentence).
  u.onboundary = (e) => {
    if (typeof e.charIndex === "number") entry.spokenTo = e.charIndex;
  };

  u.onstart = () => {
    speaking = true;
    setAcousticMonitor(false, text);
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
    unsaid = unsaid.filter((x) => x.u !== u); // said (or cancelled): nothing left of it to resume
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
    if (busy) {
      synth.cancel();
      unsaid = [];
    }
    currentRank = rank;
  } else if (priority === "safety" || (priority === "command" && currentRank < PRIORITY_RANK.safety)) {
    synth.cancel();
    unsaid = [];
    speaking = false;
    setAcousticMonitor(false);
    currentRank = rank;
  } else {
    // Queued behind whatever is playing (a checkin, or a command during a safety alert):
    // the queue keeps the highest rank it holds until it drains.
    currentRank = Math.max(currentRank, rank);
  }
  const entry = { text, priority, lang, u: null, spokenTo: 0 };
  const u = buildUtterance(text, lang, entry);
  entry.u = u;
  unsaid.push(entry);
  current = u;
  synth.speak(u);
  return true;
}

// The unsaid rest of `text`, from the start of the sentence the voice was in at `spokenTo`:
// resuming mid-sentence is hard to follow, so the sentence is said again whole.
export function remainder(text, spokenTo = 0) {
  if (!spokenTo || spokenTo <= 0) return text.trim();
  const before = text.slice(0, spokenTo);
  // ". ! ? ; ·" - ";" is also the Greek question mark, "·" the Greek semicolon.
  const ends = [...before.matchAll(/[.!?;·:](\s+)/g)];
  if (!ends.length) return text.trim();
  const last = ends[ends.length - 1];
  return text.slice(last.index + last[0].length).trim();
}

// "Hey chef" while the app talks: stop now and hand back what wasn't said yet - the sentence it
// stopped in, and everything queued behind it - so the app can say it after answering the cook.
// A safety alert is never cut off: null means nothing was interrupted, and the alert plays on.
// Button descriptions (hints) aren't worth resuming.
export function interrupt() {
  const synth = window.speechSynthesis;
  if (!(speaking || synth.speaking || synth.pending)) {
    unsaid = [];
    return [];
  }
  if (currentRank >= PRIORITY_RANK.safety) return null;
  const left = unsaid
    .filter((x) => x.priority !== "hint")
    .map((x, i) => ({ text: i === 0 ? remainder(x.text, x.spokenTo) : x.text, priority: x.priority, lang: x.lang }))
    .filter((x) => x.text);
  stopAll();
  return left;
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
  unsaid = [];
  current = null;
  currentRank = -1;
  speaking = false;
  clearInterval(keepAlive);
  keepAlive = null;
  setAcousticMonitor(true);
}
