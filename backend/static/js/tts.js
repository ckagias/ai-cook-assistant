let speaking = false;
let gateListener = null;
let greekVoice = null;
let voiceProbeDone = false;
let forcedLang = null;
let keepAlive = null;

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
      window.speechSynthesis.pause();
      window.speechSynthesis.resume();
    }, 10000);
  };

  const onDone = () => {
    speaking = false;
    clearInterval(keepAlive);
    keepAlive = null;
    setAcousticMonitor(true);
  };
  u.onend = onDone;
  u.onerror = onDone;

  return u;
}

export function speak(text, { priority = "checkin", lang = "el" } = {}) {
  if (priority === "safety" || priority === "command") {
    window.speechSynthesis.cancel();
    speaking = false;
    setAcousticMonitor(false);
  }
  window.speechSynthesis.speak(buildUtterance(text, lang));
}

export function fireSafetyInterrupt(message, lang) {
  speak(message, { priority: "safety", lang });
}

export function stopAll() {
  window.speechSynthesis.cancel();
  speaking = false;
  clearInterval(keepAlive);
  keepAlive = null;
  setAcousticMonitor(true);
}
