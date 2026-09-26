import { boot, caps, earcon, buzz } from "./boot.js";
import { speak, isSpeaking, fireSafetyInterrupt, hush, probeVoices } from "./tts.js";
import { cameraProblem } from "./camera_help.js";
import { t } from "./strings.js";
import { captureFrame } from "./capture.js";
import * as api from "./api.js";
import { createMonitor } from "./monitor.js";
import { createAimer, guideUntilFramed } from "./aim.js";
import { createSession } from "./session.js";
import { createDetector } from "./detect.js";
import { installSpeakOnPress, setSpeakButtons } from "./a11y.js";
import { createPushToTalk } from "./voice.js";

const el = {
  gate: document.getElementById("gate"),
  start: document.getElementById("start"),
  gateError: document.getElementById("gate-error"),
  app: document.getElementById("app"),
  video: document.getElementById("video"),
  busy: document.getElementById("busy"),
  status: document.getElementById("status"),
  controls: document.getElementById("controls"),
  recipeList: document.getElementById("recipe-list"),
  stepper: document.getElementById("stepper"),
  clarify: document.getElementById("clarify"),
  timer: document.getElementById("timer"),
  debug: document.getElementById("debug"),
  overlay: document.getElementById("overlay"),
  detectToggle: document.getElementById("detect-toggle"),
  detectStats: document.getElementById("detect-stats"),
  detectTable: document.getElementById("detect-table"),
};

let lang = "el";
let busy = false;
let lastCheck = null; // context for the one clarification round
let offered = []; // recipe ids last listed to the cook, so "the second one" can be resolved

const DEBUG = new URLSearchParams(window.location.search).get("debug") === "1";
// ?detect=1 / =0 persists so the installed PWA (start_url is "/") still auto-starts detection.
const DETECT_STORAGE_KEY = "detectOnStart";
const DETECT_PARAM = new URLSearchParams(window.location.search).get("detect");
if (DETECT_PARAM === "1") {
  try {
    localStorage.setItem(DETECT_STORAGE_KEY, "1");
  } catch {
    // private browsing - the URL flag still applies for this load
  }
} else if (DETECT_PARAM === "0") {
  try {
    localStorage.removeItem(DETECT_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
const DETECT_ON_START =
  DETECT_PARAM === "1" ||
  (DETECT_PARAM !== "0" &&
    (() => {
      try {
        return localStorage.getItem(DETECT_STORAGE_KEY) === "1";
      } catch {
        return false;
      }
    })());

// ?speakButtons=0 / =1 persists the per-device choice (0 for screen-reader users).
const SPEAK_BUTTONS_PARAM = new URLSearchParams(window.location.search).get("speakButtons");
if (SPEAK_BUTTONS_PARAM === "0" || SPEAK_BUTTONS_PARAM === "1") {
  setSpeakButtons(SPEAK_BUTTONS_PARAM === "1");
}
installSpeakOnPress({ getLang: () => lang });

// Present only when an operator is pairing this device for the first time - captured
// once into localStorage, then api.js attaches it as a header on every call after.
const PAIRING_TOKEN_PARAM = new URLSearchParams(window.location.search).get("token");
if (PAIRING_TOKEN_PARAM) {
  api.setPairingToken(PAIRING_TOKEN_PARAM);
  // Stored now - take it out of the address bar and history so it isn't shown or shared.
  const clean = new URL(window.location.href);
  clean.searchParams.delete("token");
  window.history.replaceState(null, "", clean.pathname + clean.search + clean.hash);
}

function formatTime(ms) {
  const totalSec = Math.ceil(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function say(text, priority = "checkin") {
  el.status.textContent = text;
  speak(text, { priority, lang });
}

function setBusy(on) {
  busy = on;
  el.busy.hidden = !on;
  document.querySelectorAll("[data-action]").forEach((btn) => {
    btn.disabled = on;
  });
}

const session = createSession({
  onTick: (remainingMs) => {
    el.timer.textContent = remainingMs > 0 ? formatTime(remainingMs) : "";
  },
  onExpired: () => {
    earcon("wait");
    buzz([80, 60, 80]);
    say(t("timer_done", lang), "checkin"); // queued, not interrupting
  },
});

const monitor = createMonitor({
  video: el.video,
  onChange: () => {
    if (busy || !session.currentStep()) return;
    earcon("wait");
    buzz(50);
    say("Κάτι άλλαξε. Να ελέγξω;", "checkin");
  },
  onTick: (a, b) => {
    if (!DEBUG) return;
    if (b) {
      el.debug.textContent = `brownRB=${a.brownRB.toFixed(3)} Yratio=${a.Yratio.toFixed(3)} maxZ=${b.maxZ.toFixed(2)} agree=${b.agree}`;
    } else if (a.phase === "calibrating") {
      el.debug.textContent = `calibrating ${Math.round((a.progress || 0) * 100)}%`;
    } else if (a.moving) {
      el.debug.textContent = "monitor: motion detected";
    } else if (a.rebaselined) {
      el.debug.textContent = "monitor: rebaselined";
    }
  },
  onDisabled: (err) => {
    if (DEBUG) el.debug.textContent = `monitor disabled: ${err && err.message}`;
  },
});

const aimer = createAimer({
  video: el.video,
  audioCtx: null, // filled in later via aimer.setAudioContext(caps.audioCtx)
  isSpeaking,
  onScore: (score, reason) => {
    if (!DEBUG) return;
    el.debug.textContent = `aim: ${score.toFixed(2)} (${reason})`;
  },
});

const detector = createDetector({
  video: el.video,
  canvas: el.overlay,
  table: el.detectTable,
  stats: el.detectStats,
  getLang: () => lang,
  getRecipeId: () => session.getRecipe()?.id ?? null,
  // A vision-LLM call is running: don't compete with it for the camera frame or the CPU.
  isPaused: () => busy,
});

function setDetection(on) {
  if (on) {
    detector.start();
  } else {
    detector.stop();
  }
  el.detectToggle.setAttribute("aria-pressed", String(on));
}

window.addEventListener("resize", () => detector.redraw());

function render(res) {
  // Order matters: safety preempts, framing blocks, then the answer, then hedging, then the question.
  if (res.safety_flag && res.safety_flag.severity === "alarm") {
    earcon("error");
    buzz([120, 60, 120, 60, 120]);
    fireSafetyInterrupt(res.spoken_response, lang);
    el.status.textContent = res.spoken_response;
    updateDebug(res);
    return;
  }

  if (res.camera_feedback) {
    earcon("error");
    say(res.camera_feedback, "command");
    updateDebug(res);
    return;
  }

  say(res.spoken_response, "command");

  if (res.confidence !== "high" && res.evidence && res.evidence.length) {
    say(res.evidence.join(". "), "checkin");
  }

  if (res.safety_flag && res.safety_flag.severity === "caution") {
    // The reason is always English (it's for the backend); read in Greek it would be gibberish.
    say(lang === "en" ? res.safety_flag.reason : t("caution", lang), "checkin");
  }

  if (res.needs_clarification && res.clarifying_question && lastCheck) {
    say(res.clarifying_question, "checkin");
    el.clarify.hidden = false;
  } else {
    el.clarify.hidden = true;
    if (res.confidence === "high") {
      earcon("done");
    }
  }

  updateDebug(res);
}

function updateDebug(res) {
  if (DEBUG) return; // DEBUG mode's live feature/aim stream owns the footer instead
  el.debug.textContent = res.doneness_stage ? `${res.confidence} / ${res.doneness_stage}` : res.confidence;
}

async function analyze(buildPayload, ackKey = "analyzing") {
  if (busy) return;
  setBusy(true);

  const aim = await guideUntilFramed(aimer, el.video);
  if (aim.guided && !aim.timedOut) earcon("done");
  earcon("ok");
  buzz(30);
  say(t(ackKey, lang), "command"); // the call runs 8-11s - say something NOW

  try {
    const res = await api.analyze({ language: lang, ...buildPayload() });
    render(res);
  } catch (err) {
    earcon("error");
    if (err instanceof api.HttpError && err.status === 401) {
      say(t("not_paired", lang), "command");
    } else {
      say(t("network_trouble", lang), "command");
    }
  } finally {
    setBusy(false);
  }
}

function identify() {
  el.clarify.hidden = true;
  lastCheck = null;
  analyze(() => ({
    mode: "identify",
    image_base64: captureFrame(el.video),
  }));
}

function checkDoneness(followup) {
  const step = session.currentStep();
  const recipe = session.getRecipe();
  if (!step || !recipe) return;

  lastCheck = { recipe_id: recipe.id, step_index: step.index };

  analyze(() => {
    const payload = {
      mode: "check_doneness",
      image_base64: captureFrame(el.video),
      recipe_id: recipe.id,
      step_index: step.index,
    };
    if (followup) payload.user_followup = followup;
    return payload;
  });
}

async function openRecipes() {
  const recipes = await api.listRecipes();
  showRecipeButtons(recipes);
  say(recipes.map((r) => r.name[lang] || r.name.en).join(", "), "command");
}

// The same buttons for the full list and for voice search results, so a sighted helper sees
// what the cook heard - and the cook can pick by voice ("the second one") or by tapping.
function showRecipeButtons(recipes) {
  offered = recipes.slice(0, 5).map((r) => r.id);
  el.recipeList.innerHTML = "";
  for (const r of recipes) {
    const btn = document.createElement("button");
    btn.textContent = r.name[lang] || r.name.en;
    btn.dataset.action = "open-recipe";
    btn.dataset.recipeId = r.id;
    el.recipeList.appendChild(btn);
  }
  const backBtn = document.createElement("button");
  backBtn.textContent = lang === "el" ? "Πίσω" : "Back";
  backBtn.dataset.action = "close-recipes";
  backBtn.dataset.speak = "back";
  el.recipeList.appendChild(backBtn);

  el.recipeList.hidden = false;
  el.controls.hidden = true;
}

async function startRecipe(id, intro = "") {
  const recipe = await api.getRecipe(id);
  session.setRecipe(recipe);
  offered = [];
  el.recipeList.hidden = true;
  el.controls.hidden = true;
  el.stepper.hidden = false;
  announceStep({ intro });
}

// repeat: says the step again and leaves its timer and the change monitor alone - hearing a
// step twice must not reset a countdown that's already running.
function announceStep({ repeat = false, intro = "" } = {}) {
  el.clarify.hidden = true;
  const step = session.currentStep();
  if (!step) return;

  // One utterance: two "command"s in a row would cut the first one off.
  const text = step.instruction[lang] || step.instruction.en;
  say(intro ? intro + " " + text : text, "command");

  const checkBtn = el.stepper.querySelector('[data-action="check"]');
  if (checkBtn) checkBtn.hidden = !step.checkable;

  if (repeat) return;

  session.clearTimer();
  el.timer.textContent = "";
  if (step.expected_duration_sec) {
    session.startTimer(step.expected_duration_sec);
  }

  // Baselines against the scene as it currently is - must go at the end of the
  // announcement, not at recipe start.
  monitor.stop();
  if (step.checkable) {
    monitor.start();
  }
}

function nextStep() {
  const advanced = session.next();
  if (advanced) {
    announceStep();
  } else {
    stopRecipe();
    say(lang === "el" ? "Η συνταγή ολοκληρώθηκε." : "Recipe complete.", "command");
  }
}

function previousStep() {
  if (session.goTo(session.getStepIndex() - 1)) {
    announceStep();
  } else {
    say(t("no_previous", lang), "command");
  }
}

function stopRecipe() {
  aimer.stop();
  monitor.stop();
  session.clearTimer();
  el.stepper.hidden = true;
  el.clarify.hidden = true;
  el.controls.hidden = false;
  el.timer.textContent = "";
}

// --- push-to-talk ---

let voiceStream = null;

// Its own microphone stream with the browser's speech processing ON: the boot stream has it
// OFF on purpose (sizzle detection needs the raw sound), which is the wrong input for words.
async function getVoiceStream() {
  if (voiceStream && voiceStream.getAudioTracks().some((tr) => tr.readyState === "live")) return voiceStream;
  try {
    voiceStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (err) {
    if (!caps.micStream) throw err;
    voiceStream = caps.micStream; // better unprocessed than nothing
  }
  return voiceStream;
}

function setTalkState(state) {
  const listening = state === "listening";
  document.querySelectorAll('[data-action="talk"]').forEach((b) => b.setAttribute("aria-pressed", String(listening)));
  if (listening) {
    earcon("ok");
    buzz(20);
    el.status.textContent = t("listening", lang);
  } else if (state === "thinking") {
    el.status.textContent = t("thinking", lang);
  }
  el.busy.hidden = !(busy || state === "thinking");
}

function runVoiceCommand(res) {
  const reply = () => say(res.spoken_response, "command");
  switch (res.action) {
    case "next_step":
      nextStep();
      break;
    case "previous_step":
      previousStep();
      break;
    case "repeat_step":
      announceStep({ repeat: true });
      break;
    case "start_timer":
      session.startTimer(res.timer_seconds);
      reply();
      break;
    case "stop_timer":
      session.clearTimer();
      el.timer.textContent = "";
      say(t("timer_stopped", lang), "command");
      break;
    case "check_doneness":
      checkDoneness();
      break;
    case "identify":
      identify();
      break;
    case "find_recipe":
      if (res.candidates && res.candidates.length) showRecipeButtons(res.candidates);
      reply();
      break;
    case "choose_recipe":
      if (res.recipe_id) {
        el.status.textContent = res.spoken_response;
        startRecipe(res.recipe_id, res.spoken_response).catch(() => say(t("network_trouble", lang), "command"));
      } else {
        reply();
      }
      break;
    default: // answer, unclear
      reply();
  }
}

const talk = createPushToTalk({
  getStream: getVoiceStream,
  send: (blob, type) => {
    const step = session.currentStep();
    return api.voiceCommand(blob, type, {
      language: lang,
      recipeId: session.getRecipe()?.id,
      stepIndex: step ? step.index : null,
      candidates: offered,
    });
  },
  onState: setTalkState,
  onResult: (res, reason) => {
    if (!res) {
      if (reason === "too_short") say(t("hold_to_talk", lang), "command");
      return;
    }
    runVoiceCommand(res);
  },
  onError: (err) => {
    earcon("error");
    if (err instanceof api.HttpError && err.status === 503) {
      say(t("voice_unavailable", lang), "command");
    } else if (err instanceof api.HttpError && err.status === 401) {
      say(t("not_paired", lang), "command");
    } else if (err && (err.name === "NotAllowedError" || err.name === "NotFoundError" || err.name === "NotReadableError")) {
      say(t("no_mic", lang), "command");
    } else {
      say(t("network_trouble", lang), "command");
    }
  },
});

function startTalking() {
  if (busy || el.app.hidden) return;
  hush(); // don't talk over the cook - except a safety alert
  talk.start();
}

// Held, not clicked: pointerdown starts, lifting (anywhere - the pointer is captured) stops.
let talkPointer = null;
document.addEventListener("pointerdown", (e) => {
  const btn = e.target.closest('[data-action="talk"]');
  if (!btn || btn.disabled || (e.pointerType === "mouse" && e.button !== 0)) return;
  e.preventDefault();
  try {
    btn.setPointerCapture(e.pointerId);
  } catch {
    // not capturable (synthetic event) - pointerup still reaches the document
  }
  talkPointer = e.pointerId;
  startTalking();
});
const stopTalking = (e) => {
  if (e.pointerId !== talkPointer) return;
  talkPointer = null;
  talk.stop();
};
document.addEventListener("pointerup", stopTalking);
document.addEventListener("pointercancel", stopTalking);
// Focus leaving the window mid-hold would otherwise leave the V key "held" until MAX_MS.
window.addEventListener("blur", () => talk.stop());

const ACTIONS = {
  identify: () => identify(),
  recipes: () => openRecipes(),
  "close-recipes": () => {
    el.recipeList.hidden = true;
    el.controls.hidden = false;
    offered = [];
  },
  "open-recipe": (btn) => startRecipe(btn.dataset.recipeId),
  check: () => checkDoneness(),
  repeat: () => announceStep({ repeat: true }),
  next: () => nextStep(),
  stop: () => stopRecipe(),
  "answer-yes": () => checkDoneness(lang === "el" ? "Ναι" : "yes"),
  "answer-no": () => checkDoneness(lang === "el" ? "Όχι" : "no"),
  "detect-toggle": () => setDetection(!detector.isRunning()),
};

// No per-button onclick - delegate from a single document-level click listener.
document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-action]");
  if (!btn) return;
  const action = btn.dataset.action;
  if (action === "start") return; // handled by its own dedicated listener below
  const handler = ACTIONS[action];
  if (handler) handler(btn);
});

// A Bluetooth shutter remote pairs as a keyboard, so this covers both the real
// remote and a laptop operator pressing space. A touch-only tablet never emits
// keydown, so this stays a convenience, not the main path.
document.addEventListener("keydown", (e) => {
  if (el.app.hidden) return;
  // V held = the talk button held (PC demo). e.code, not e.key: on a Greek layout V types "ω".
  if (e.code === "KeyV" && !e.ctrlKey && !e.altKey && !e.metaKey) {
    e.preventDefault();
    if (!e.repeat) startTalking();
    return;
  }
  if (e.key === " " || e.key === "Enter") {
    e.preventDefault();
    if (session.currentStep()) {
      checkDoneness();
    } else {
      identify();
    }
  } else if (e.key === "ArrowRight") {
    if (session.currentStep()) {
      nextStep();
    }
  }
});

document.addEventListener("keyup", (e) => {
  if (e.code === "KeyV") talk.stop();
});

el.start.addEventListener("click", async () => {
  el.start.disabled = true;
  try {
    const warnings = await boot("el");
    lang = caps.lang;
    el.video.srcObject = caps.stream;
    aimer.setAudioContext(caps.audioCtx);

    el.gate.hidden = true;
    el.app.hidden = false;

    el.debug.textContent = warnings.length ? warnings.join(" | ") : "";

    say(t("greeting", lang), "command");
    if (warnings.some((w) => /greek/i.test(w))) {
      speak(t("no_greek_voice", "en"), { priority: "checkin", lang: "en" });
    }

    el.detectToggle.textContent = t("detect_toggle", lang);
    document.querySelectorAll('[data-action="talk"]').forEach((b) => (b.textContent = t("talk", lang)));
    if (DETECT_ON_START) setDetection(true);
  } catch (err) {
    el.start.disabled = false; // fix the setting, press Start again - no reload needed
    const key = cameraProblem(err, {
      userAgent: navigator.userAgent,
      embedded: window.self !== window.top,
      secure: window.isSecureContext,
    });
    // Both languages on screen so whoever is helping can follow it; the browser's own words last.
    el.gateError.textContent = `${t(key, "el")}\n\n${t(key, "en")}\n\n(${(err && err.message) || err})`;
    el.gateError.hidden = false;
    // Spoken as well - the Start tap already unlocked speech. English when there's no Greek voice.
    try {
      const spokenLang = await probeVoices("el");
      speak(t(key, spokenLang), { priority: "command", lang: spokenLang });
    } catch {
      // no speech synthesis at all - the text above stands
    }
  }
});
