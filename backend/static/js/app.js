import { boot, caps, earcon, buzz } from "./boot.js";
import { speak, isSpeaking, fireSafetyInterrupt } from "./tts.js";
import { t } from "./strings.js";
import { captureFrame } from "./capture.js";
import * as api from "./api.js";
import { createMonitor } from "./monitor.js";
import { createAimer, guideUntilFramed } from "./aim.js";
import { createSession } from "./session.js";

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
};

let lang = "el";
let busy = false;
let lastCheck = null; // context for the one clarification round

const DEBUG = new URLSearchParams(window.location.search).get("debug") === "1";

// Present only when an operator is pairing this device for the first time - captured
// once into localStorage, then api.js attaches it as a header on every call after.
const PAIRING_TOKEN_PARAM = new URLSearchParams(window.location.search).get("token");
if (PAIRING_TOKEN_PARAM) {
  api.setPairingToken(PAIRING_TOKEN_PARAM);
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
    say(res.safety_flag.reason, "checkin");
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
  el.recipeList.appendChild(backBtn);

  el.recipeList.hidden = false;
  el.controls.hidden = true;

  say(recipes.map((r) => r.name[lang] || r.name.en).join(", "), "command");
}

async function startRecipe(id) {
  const recipe = await api.getRecipe(id);
  session.setRecipe(recipe);
  el.recipeList.hidden = true;
  el.controls.hidden = true;
  el.stepper.hidden = false;
  announceStep();
}

function announceStep() {
  el.clarify.hidden = true;
  const step = session.currentStep();
  if (!step) return;

  say(step.instruction[lang] || step.instruction.en, "command");

  const checkBtn = el.stepper.querySelector('[data-action="check"]');
  if (checkBtn) checkBtn.hidden = !step.checkable;

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

function stopRecipe() {
  aimer.stop();
  monitor.stop();
  session.clearTimer();
  el.stepper.hidden = true;
  el.clarify.hidden = true;
  el.controls.hidden = false;
  el.timer.textContent = "";
}

const ACTIONS = {
  identify: () => identify(),
  recipes: () => openRecipes(),
  "close-recipes": () => {
    el.recipeList.hidden = true;
    el.controls.hidden = false;
  },
  "open-recipe": (btn) => startRecipe(btn.dataset.recipeId),
  check: () => checkDoneness(),
  repeat: () => announceStep(),
  next: () => nextStep(),
  stop: () => stopRecipe(),
  "answer-yes": () => checkDoneness(lang === "el" ? "Ναι" : "yes"),
  "answer-no": () => checkDoneness(lang === "el" ? "Όχι" : "no"),
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
  } catch (err) {
    el.start.disabled = false;
    el.gateError.hidden = false;
    el.gateError.textContent = (err && err.message) || String(err);
  }
});
