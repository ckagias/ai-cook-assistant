import { boot, caps, earcon, buzz } from "./boot.js";
import { speak, isSpeaking, fireSafetyInterrupt, hush, probeVoices, registerAcousticGate } from "./tts.js";
import { cameraProblem } from "./camera_help.js";
import { t, tf, humanDuration } from "./strings.js";
import { captureFrame } from "./capture.js";
import * as api from "./api.js";
import { createMonitor } from "./monitor.js";
import { createAimer, guideUntilFramed } from "./aim.js";
import { createSession } from "./session.js";
import { createTimers, formatClock } from "./timers.js";
import { createDetector } from "./detect.js";
import { installSpeakOnPress, setSpeakButtons } from "./a11y.js";
import { createPushToTalk } from "./voice.js";
import { createWakeListener, getRecognition } from "./wake.js";
import { matchLocal } from "./commands.js";

// Three ways in, two ways out, for everything the app does:
//   in:  voice ("Hey chef" or the talk button), the buttons, and typing
//   out: speech, and the same words on screen (status line, conversation log, alerts that stay)
// so a blind cook never needs the screen, and a deaf cook who doesn't speak never needs sound.

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
  overview: document.getElementById("overview"),
  overviewTitle: document.getElementById("overview-title"),
  overviewMeta: document.getElementById("overview-meta"),
  doneness: document.getElementById("doneness"),
  donenessOptions: document.getElementById("doneness-options"),
  ingredientList: document.getElementById("ingredient-list"),
  stepper: document.getElementById("stepper"),
  stepCount: document.getElementById("step-count"),
  stepText: document.getElementById("step-text"),
  timers: document.getElementById("timers"),
  startTimer: document.getElementById("start-timer"),
  question: document.getElementById("question"),
  questionText: document.getElementById("question-text"),
  alert: document.getElementById("alert"),
  alertText: document.getElementById("alert-text"),
  flash: document.getElementById("flash"),
  ask: document.getElementById("ask"),
  askInput: document.getElementById("ask-input"),
  log: document.getElementById("log"),
  wakeToggle: document.getElementById("wake-toggle"),
  wakeStatus: document.getElementById("wake-status"),
  interim: document.getElementById("interim"),
  timer: document.getElementById("timer"),
  debug: document.getElementById("debug"),
  overlay: document.getElementById("overlay"),
  detectToggle: document.getElementById("detect-toggle"),
  detectStats: document.getElementById("detect-stats"),
  detectTable: document.getElementById("detect-table"),
};

const params = new URLSearchParams(window.location.search);
const DEBUG = params.get("debug") === "1";
// Demo convenience: start the detection preview as soon as the camera is up.
const DETECT_ON_START = params.get("detect") === "1";
// The language the cook speaks. Replies follow the voice the device has (lang below), but a
// Greek cook on a device without a Greek voice still speaks Greek.
const LISTEN_LANG = params.get("listen") === "en" ? "en" : "el";
const LOG_MAX = 40;
const TAP_MS = 300; // talk button released sooner = a tap: keep listening until they stop talking

let lang = "el";
let busy = false;
let lastCheck = null; // context for the one clarification round
let offered = []; // recipe ids last listed to the cook, so "the second one" can be resolved
let pending = null; // the yes/no question the app is waiting on: { type, sec? }
let ticked = new Set(); // ingredient positions the cook has (tapped, said, or the camera saw)
const finished = new Map(); // timer key -> { totalMs, endedAt }, for "how long has it been" after the alarm

// Per-device conveniences - nothing here is needed for the app to work.
function loadPref(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function savePref(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // private browsing - the choice just isn't remembered
  }
}
let doneness = loadPref("doneness");

// ?speakButtons=0 / =1 persists the per-device choice (0 for screen-reader users).
const SPEAK_BUTTONS_PARAM = params.get("speakButtons");
if (SPEAK_BUTTONS_PARAM === "0" || SPEAK_BUTTONS_PARAM === "1") {
  setSpeakButtons(SPEAK_BUTTONS_PARAM === "1");
}
installSpeakOnPress({ getLang: () => lang });

// Present only when an operator is pairing this device for the first time - captured
// once into localStorage, then api.js attaches it as a header on every call after.
const PAIRING_TOKEN_PARAM = params.get("token");
if (PAIRING_TOKEN_PARAM) {
  api.setPairingToken(PAIRING_TOKEN_PARAM);
  // Stored now - take it out of the address bar and history so it isn't shown or shared.
  const clean = new URL(window.location.href);
  clean.searchParams.delete("token");
  window.history.replaceState(null, "", clean.pathname + clean.search + clean.hash);
}

// --- output: speech + text, always both ---

function logLine(who, text) {
  if (!text) return;
  const line = document.createElement("p");
  line.className = "log-" + who;
  const name = document.createElement("b");
  name.textContent = t(who === "you" ? "log_you" : "log_chef", lang) + ": ";
  line.append(name, text); // text node - never HTML, some of it comes from the server
  el.log.append(line);
  while (el.log.childElementCount > LOG_MAX) el.log.firstElementChild.remove();
  el.log.scrollTop = el.log.scrollHeight;
}

function say(text, priority = "checkin") {
  if (!text) return;
  el.status.textContent = text;
  logLine("chef", text);
  speak(text, { priority, lang });
}

// Stays until dismissed, with a flash and a buzz: a cook who can't hear the alarm still sees it.
function showAlert(text, kind) {
  el.alertText.textContent = text;
  el.alert.dataset.kind = kind;
  el.alert.hidden = false;
  el.flash.dataset.kind = kind;
  el.flash.hidden = false;
  el.flash.classList.remove("go");
  void el.flash.offsetWidth; // restart the animation
  el.flash.classList.add("go");
  setTimeout(() => (el.flash.hidden = true), 3000);
}

function setBusy(on) {
  busy = on;
  el.busy.hidden = !on;
  // Talking, typing and dismissing an alert stay possible while the camera call runs.
  document.querySelectorAll("[data-action]").forEach((btn) => {
    if (!["talk", "wake-toggle", "alert-ok", "tick"].includes(btn.dataset.action)) btn.disabled = on;
  });
}

function localize() {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-label]").forEach((node) => {
    const text = t(node.dataset.label, lang);
    if (text) node.textContent = text;
  });
  el.askInput.placeholder = t("ask_placeholder", lang);
}

// --- the yes/no question the app is waiting on ---

function askQuestion(type, text, extra = {}) {
  pending = { type, ...extra };
  el.questionText.textContent = text;
  el.question.hidden = false;
  say(text, "checkin"); // queued behind whatever answer came before it
}

function clearPending() {
  pending = null;
  el.question.hidden = true;
}

function answer(yes) {
  const question = pending;
  clearPending();
  if (!question) {
    say(t("ok", lang), "command");
    return;
  }
  switch (question.type) {
    case "advance":
      if (yes) nextStep();
      else say(t("ok_wait", lang), "command");
      break;
    case "add_time":
      if (yes) addTime(question.sec);
      else say(t("ok_wait", lang), "command");
      break;
    case "clarify":
      checkDoneness(yes ? (lang === "el" ? "Ναι" : "yes") : lang === "el" ? "Όχι" : "no");
      break;
    case "check_offer":
      if (yes) checkDoneness();
      else say(t("ok", lang), "command");
      break;
    case "stop_recipe":
      if (yes) {
        stopRecipe();
        say(t("recipe_stopped", lang), "command");
      } else {
        say(t("ok", lang), "command");
      }
      break;
  }
}

// --- timers: started by the cook, several at once ---

function stepKey(step) {
  return `step-${session.getRecipe()?.id}-${step.index}`;
}

function stepLabel(step) {
  const words = (step.instruction[lang] || step.instruction.en || "").split(/\s+/);
  const short = words.slice(0, 5).join(" ") + (words.length > 5 ? "…" : "");
  return `${tf("timer_label_step", lang, { n: step.index + 1 })} (${short})`;
}

function effectiveDoneness(recipe = session.getRecipe()) {
  if (!recipe || !doneness) return null;
  return recipe.steps.some((s) => s.by_doneness && s.by_doneness[doneness]) ? doneness : null;
}

function stepSeconds(step) {
  if (!step) return null;
  const target = step.by_doneness && effectiveDoneness() && step.by_doneness[effectiveDoneness()];
  return (target && target.duration_sec) || step.expected_duration_sec || null;
}

// The timer a command like "add a minute" means: this step's, else the one ending soonest.
function targetTimer() {
  const step = session.currentStep();
  return (step && timers.get(stepKey(step))) || timers.soonest();
}

const timerRows = new Map(); // key -> { row, clock }

function renderTimers(list) {
  const keys = new Set(list.map((tm) => tm.key));
  for (const [key, row] of timerRows) {
    if (!keys.has(key)) {
      row.row.remove();
      timerRows.delete(key);
    }
  }
  for (const tm of list) {
    let row = timerRows.get(tm.key);
    if (!row) {
      // Built once per timer and only its clock updated after, so a finger on +1 isn't lost.
      const node = document.createElement("div");
      node.className = "timer-row";
      const label = document.createElement("span");
      label.className = "timer-label";
      label.textContent = tm.label;
      const clock = document.createElement("span");
      clock.className = "timer-clock";
      node.append(label, clock);
      for (const [action, key] of [["timer-add", "add_minute"], ["timer-sub", "sub_minute"], ["timer-stop", "stop_timer"]]) {
        const btn = document.createElement("button");
        btn.dataset.action = action;
        btn.dataset.timer = tm.key;
        btn.dataset.speak = key;
        btn.textContent = t(key, lang);
        node.append(btn);
      }
      el.timers.append(node);
      row = { row: node, clock };
      timerRows.set(tm.key, row);
    }
    row.clock.textContent = formatClock(tm.remainingMs);
  }
  const soonest = list[0];
  el.timer.textContent = soonest ? `⏱ ${formatClock(soonest.remainingMs)} · ${soonest.label}` : "";
  updateStepButtons();
}

const timers = createTimers({
  onTick: renderTimers,
  onExpired: (tm) => {
    finished.set(tm.key, { totalMs: tm.totalMs, endedAt: Date.now() });
    earcon("wait");
    setTimeout(() => earcon("wait"), 350);
    buzz([300, 120, 300, 120, 300]);
    const text = tf("timer_done_label", lang, { label: tm.label });
    showAlert(text, "timer");
    const step = session.currentStep();
    const suggest = step && step.index === tm.stepIndex && step.checkable ? " " + t("timer_done_check", lang) : "";
    say(text + suggest, "checkin"); // queued, not interrupting
  },
});

function startTimer(seconds, spoken) {
  const step = session.currentStep();
  const secs = seconds || stepSeconds(step);
  if (!secs) {
    say(t("how_long", lang), "command");
    return;
  }
  const key = step ? stepKey(step) : "custom";
  finished.delete(key);
  timers.start(key, secs, {
    label: step ? stepLabel(step) : t("timer_label_custom", lang),
    stepIndex: step ? step.index : null,
  });
  earcon("ok");
  say(spoken || tf("timer_started", lang, { human: humanDuration(secs, lang) }), "command");
}

function addTime(seconds, spoken) {
  if (!seconds) return;
  const tm = targetTimer();
  if (!tm) {
    if (seconds > 0) startTimer(seconds);
    else say(t("no_timer", lang), "command");
    return;
  }
  timers.add(tm.key, seconds);
  earcon("ok");
  const human = humanDuration(seconds, lang);
  say(spoken || tf(seconds > 0 ? "timer_added" : "timer_removed", lang, { human }), "command");
}

function stopTimer(key) {
  const tm = key ? timers.get(key) : targetTimer();
  if (!tm) {
    say(t("no_timer", lang), "command");
    return;
  }
  timers.stop(tm.key);
  say(t("timer_stopped", lang), "command");
}

// How far along this step's timer is (or was, when it already rang) - part of judging "ready".
function timerProgress(step) {
  const key = stepKey(step);
  const tm = timers.get(key);
  if (tm) return { timer_elapsed_sec: Math.round(tm.elapsedMs / 1000), timer_total_sec: Math.round(tm.totalMs / 1000) };
  const done = finished.get(key);
  if (done) {
    const elapsed = done.totalMs + (Date.now() - done.endedAt);
    return { timer_elapsed_sec: Math.round(elapsed / 1000), timer_total_sec: Math.round(done.totalMs / 1000) };
  }
  return {};
}

// --- recipe session, monitor, aiming, detection ---

const session = createSession();

const monitor = createMonitor({
  video: el.video,
  onChange: () => {
    if (busy || pending || !session.currentStep()) return;
    earcon("wait");
    buzz(50);
    askQuestion("check_offer", t("changed", lang));
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
  onResult: tickFromDetections,
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

// --- camera checks (/analyze) ---

function render(res, kind) {
  // Order matters: safety preempts, framing blocks, then the answer, then hedging, then the question.
  if (res.safety_flag && res.safety_flag.severity === "alarm") {
    earcon("error");
    buzz([120, 60, 120, 60, 120]);
    fireSafetyInterrupt(res.spoken_response, lang);
    el.status.textContent = res.spoken_response;
    logLine("chef", res.spoken_response);
    showAlert(res.spoken_response, "safety");
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

  if (kind === "ingredients") {
    for (const n of res.ingredients_seen || []) ticked.add(n - 1);
    renderIngredients();
    sayMissingIngredients();
  } else if (kind === "check") {
    const step = session.currentStep();
    if (res.verdict === "ready") {
      // Proposed, never done for them: the cook agrees before the app moves on.
      earcon("done");
      askQuestion("advance", t(session.isLastStep() ? "ask_finish" : "ask_advance", lang));
    } else if (res.verdict === "not_ready" && res.suggested_extra_sec) {
      const human = humanDuration(res.suggested_extra_sec, lang);
      const running = step && timers.get(stepKey(step));
      askQuestion("add_time", tf(running ? "ask_add_time" : "ask_set_timer", lang, { human }), { sec: res.suggested_extra_sec });
    } else if (res.needs_clarification && res.clarifying_question && lastCheck) {
      askQuestion("clarify", res.clarifying_question);
    }
  } else if (res.confidence === "high") {
    earcon("done");
  }

  updateDebug(res);
}

function updateDebug(res) {
  if (DEBUG) return; // DEBUG mode's live feature/aim stream owns the footer instead
  el.debug.textContent = res.doneness_stage ? `${res.confidence} / ${res.doneness_stage}` : res.confidence;
}

async function analyze(buildPayload, kind, ackKey = "analyzing") {
  if (busy) {
    say(t("still_busy", lang), "checkin");
    return;
  }
  clearPending();
  setBusy(true);

  const aim = await guideUntilFramed(aimer, el.video);
  if (aim.guided && !aim.timedOut) earcon("done");
  earcon("ok");
  buzz(30);
  say(t(ackKey, lang), "command"); // the call runs 8-11s - say something NOW

  try {
    const res = await api.analyze({ language: lang, ...buildPayload() });
    render(res, kind);
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
  lastCheck = null;
  analyze(() => ({ mode: "identify", image_base64: captureFrame(el.video) }), "identify");
}

function checkDoneness(followup) {
  const recipe = session.getRecipe();
  if (!recipe) {
    say(t("no_recipe_open", lang), "command");
    return;
  }
  const step = session.currentStep();
  if (!step) {
    checkIngredients(); // "check it" before the first step: the ingredients are what's in front of me
    return;
  }
  lastCheck = { recipe_id: recipe.id, step_index: step.index };
  analyze(() => {
    const payload = {
      mode: "check_doneness",
      image_base64: captureFrame(el.video),
      recipe_id: recipe.id,
      step_index: step.index,
      ...timerProgress(step),
    };
    if (effectiveDoneness()) payload.doneness_preference = effectiveDoneness();
    if (followup) payload.user_followup = followup;
    return payload;
  }, "check");
}

function checkIngredients() {
  const recipe = session.getRecipe();
  if (!recipe) {
    say(t("no_recipe_open", lang), "command");
    return;
  }
  lastCheck = null;
  analyze(() => ({ mode: "check_ingredients", image_base64: captureFrame(el.video), recipe_id: recipe.id }), "ingredients");
}

// --- recipes: list, overview with ingredients, steps ---

function showPanel(name) {
  el.controls.hidden = name !== "home";
  el.recipeList.hidden = name !== "list";
  el.overview.hidden = name !== "overview";
  el.stepper.hidden = name !== "steps";
}

async function openRecipes() {
  try {
    const recipes = await api.listRecipes();
    showRecipeButtons(recipes);
    say(recipes.map((r) => r.name[lang] || r.name.en).join(", "), "command");
  } catch {
    say(t("network_trouble", lang), "command");
  }
}

// The same buttons for the full list and for voice search results, so a sighted helper sees
// what the cook heard - and the cook can pick by voice ("the second one") or by tapping.
function showRecipeButtons(recipes) {
  offered = recipes.slice(0, 5).map((r) => r.id);
  el.recipeList.innerHTML = "";
  recipes.forEach((r, i) => {
    const btn = document.createElement("button");
    btn.textContent = i < 5 ? `${i + 1}. ${r.name[lang] || r.name.en}` : r.name[lang] || r.name.en;
    btn.dataset.action = "open-recipe";
    btn.dataset.recipeId = r.id;
    el.recipeList.appendChild(btn);
  });
  const backBtn = document.createElement("button");
  backBtn.textContent = t("back", lang);
  backBtn.dataset.action = "close-recipes";
  backBtn.dataset.speak = "back";
  el.recipeList.appendChild(backBtn);
  showPanel("list");
}

function ingredientLines(recipe) {
  if (recipe.ingredient_details && recipe.ingredient_details.length) {
    return recipe.ingredient_details.map((d) => (d.text && (d.text[lang] || d.text.en)) || d.raw_text);
  }
  return recipe.ingredients;
}

function donenessOptions(recipe) {
  const order = ["rare", "medium_rare", "medium", "medium_well", "well_done"];
  const offeredKeys = new Set(recipe.steps.flatMap((s) => Object.keys(s.by_doneness || {})));
  return order.filter((k) => offeredKeys.has(k));
}

function renderIngredients() {
  const recipe = session.getRecipe();
  el.ingredientList.innerHTML = "";
  if (!recipe) return;
  ingredientLines(recipe).forEach((text, i) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.dataset.action = "tick"; // no data-speak: long-press reads the ingredient itself
    btn.dataset.index = String(i);
    btn.setAttribute("aria-pressed", String(ticked.has(i)));
    btn.textContent = text;
    li.appendChild(btn);
    el.ingredientList.appendChild(li);
  });
}

function renderDoneness() {
  const recipe = session.getRecipe();
  const options = recipe ? donenessOptions(recipe) : [];
  el.doneness.hidden = options.length === 0;
  el.donenessOptions.innerHTML = "";
  for (const key of options) {
    const btn = document.createElement("button");
    btn.dataset.action = "doneness"; // no data-speak: long-press reads "medium-rare" etc.
    btn.dataset.doneness = key;
    btn.setAttribute("aria-pressed", String(effectiveDoneness() === key));
    btn.textContent = t("done_" + key, lang);
    el.donenessOptions.appendChild(btn);
  }
}

function overviewSpeech(recipe, { withName = true } = {}) {
  const parts = withName ? [(recipe.name[lang] || recipe.name.en) + "."] : [];
  if (recipe.servings) parts.push(tf("overview_serves", lang, { n: recipe.servings }));
  if (recipe.times && recipe.times.total_min) parts.push(tf("overview_time", lang, { minutes: recipe.times.total_min }));
  const lines = ingredientLines(recipe);
  parts.push(tf("overview_ingredients", lang, { count: lines.length, list: lines.join(", ") }));
  const options = donenessOptions(recipe);
  if (options.length && !effectiveDoneness(recipe)) {
    const names = options.map((k) => t("done_" + k, lang));
    const spoken = names.slice(0, -1).join(", ") + ` ${t("or", lang)} ` + names[names.length - 1];
    parts.push(tf("overview_doneness", lang, { options: spoken }));
  }
  parts.push(t("overview_next", lang));
  return parts.join(" ");
}

async function startRecipe(id, intro = "") {
  let recipe;
  try {
    recipe = await api.getRecipe(id);
  } catch {
    say(t("network_trouble", lang), "command");
    return;
  }
  timers.clear();
  finished.clear();
  session.setRecipe(recipe);
  offered = [];
  ticked = new Set();
  lastCheck = null;
  clearPending();
  monitor.stop();

  el.overviewTitle.textContent = recipe.name[lang] || recipe.name.en;
  const meta = [];
  if (recipe.servings) meta.push(tf("overview_serves", lang, { n: recipe.servings }));
  if (recipe.times && recipe.times.total_min) meta.push(tf("overview_time", lang, { minutes: recipe.times.total_min }));
  el.overviewMeta.textContent = meta.join(" ");
  renderDoneness();
  renderIngredients();
  showPanel("overview");

  // One utterance: two "command"s in a row would cut the first one off. The server's
  // "Starting: Roast Beef." already names it.
  const speech = overviewSpeech(recipe, { withName: !intro });
  say(intro ? `${intro} ${speech}` : speech, "command");
}

function readIngredients() {
  const recipe = session.getRecipe();
  if (!recipe) {
    say(t("no_recipe_open", lang), "command");
    return;
  }
  say(tf("ingredients_list", lang, { list: ingredientLines(recipe).join(", ") }), "command");
}

function sayMissingIngredients() {
  const recipe = session.getRecipe();
  if (!recipe) return;
  const missing = ingredientLines(recipe).filter((_, i) => !ticked.has(i));
  say(missing.length ? tf("ingredients_missing", lang, { list: missing.join(", ") }) : t("ingredients_all", lang), "checkin");
}

// The live detection preview ticks what it sees, silently apart from a click - a spoken
// announcement per ingredient would talk over everything else.
function tickFromDetections(res) {
  const recipe = session.getRecipe();
  if (!recipe || session.getPhase() !== "overview" || !recipe.ingredient_details) return;
  let changed = false;
  for (const d of res.detections || []) {
    if (d.confidence < 0.4) continue;
    recipe.ingredient_details.forEach((line, i) => {
      if (line.vocab_id && line.vocab_id === d.class_id && !ticked.has(i)) {
        ticked.add(i);
        changed = true;
      }
    });
  }
  if (changed) {
    earcon("ok");
    renderIngredients();
  }
}

function setDoneness(key, spoken) {
  doneness = key;
  savePref("doneness", key);
  renderDoneness();
  const step = session.currentStep();
  const target = step && step.by_doneness && step.by_doneness[key];
  let text = spoken || tf("doneness_set", lang, { name: t("done_" + key, lang) });
  if (!spoken && target) text += " " + tf("step_target", lang, { pref: t("done_" + key, lang), temp: target.temp_c });
  say(text, "command");
}

function beginSteps() {
  if (!session.beginSteps()) return;
  showPanel("steps");
  announceStep();
}

function stepSpeech(step) {
  const recipe = session.getRecipe();
  const parts = [
    tf("step_n_of", lang, { n: step.index + 1, total: recipe.steps.length }),
    step.instruction[lang] || step.instruction.en,
  ];
  const pref = effectiveDoneness();
  const target = pref && step.by_doneness && step.by_doneness[pref];
  if (target) parts.push(tf("step_target", lang, { pref: t("done_" + pref, lang), temp: target.temp_c }));
  const secs = stepSeconds(step);
  if (secs && !timers.get(stepKey(step))) parts.push(tf("step_timer_hint", lang, { human: humanDuration(secs, lang) }));
  if (step.checkable) parts.push(t(step.kind === "prep" ? "step_check_prep" : "step_check_cook", lang));
  return parts.join(" ");
}

function updateStepButtons() {
  const step = session.currentStep();
  if (!step) return;
  const checkBtn = el.stepper.querySelector('[data-action="check"]');
  if (checkBtn) checkBtn.hidden = !step.checkable; // "check it" by voice still works anywhere
  const secs = stepSeconds(step);
  const running = timers.get(stepKey(step));
  el.startTimer.hidden = !secs || Boolean(running);
  if (secs) el.startTimer.textContent = tf("start_timer", lang, { time: formatClock(secs * 1000) });
}

// repeat: says the step again and leaves the change monitor alone. Timers never change on a
// step change - the cook started them, the cook stops them.
function announceStep({ repeat = false, intro = "" } = {}) {
  clearPending();
  const step = session.currentStep();
  if (!step) return;

  el.stepCount.textContent = tf("step_n_of", lang, { n: step.index + 1, total: session.getRecipe().steps.length });
  el.stepText.textContent = step.instruction[lang] || step.instruction.en;
  updateStepButtons();

  const speech = stepSpeech(step);
  say(intro ? `${intro} ${speech}` : speech, "command");

  if (repeat) return;
  lastCheck = null;
  // Baselines against the scene as it currently is - must go at the end of the
  // announcement, not at recipe start.
  monitor.stop();
  if (step.checkable) {
    monitor.start();
  }
}

function nextStep() {
  if (!session.getRecipe()) {
    say(t("no_recipe_open", lang), "command");
    return;
  }
  if (session.getPhase() === "overview") {
    beginSteps();
    return;
  }
  if (session.next()) {
    announceStep();
  } else {
    stopRecipe();
    say(t("recipe_done", lang), "command");
  }
}

function previousStep() {
  if (session.getPhase() === "steps" && session.goTo(session.getStepIndex() - 1)) {
    announceStep();
  } else {
    say(t("no_previous", lang), "command");
  }
}

function repeat() {
  const recipe = session.getRecipe();
  if (session.currentStep()) announceStep({ repeat: true });
  else if (recipe) say(overviewSpeech(recipe), "command");
  else say(el.status.textContent || t("greeting", lang), "command");
}

function stopRecipe() {
  aimer.stop();
  monitor.stop();
  timers.clear();
  finished.clear();
  session.setRecipe(null);
  clearPending();
  lastCheck = null;
  ticked = new Set();
  offered = [];
  showPanel("home");
}

// --- understanding what the cook said or typed ---

function voiceContext() {
  const step = session.currentStep();
  const tm = targetTimer();
  return {
    language: lang,
    recipeId: session.getRecipe()?.id,
    stepIndex: step ? step.index : null,
    candidates: offered,
    pending: pending ? pending.type : null,
    // With a recipe open, only a choice that recipe offers; before one, the saved preference.
    doneness: session.getRecipe() ? effectiveDoneness() : doneness,
    timerRemainingSec: tm ? Math.round(tm.remainingMs / 1000) : null,
  };
}

// Whether a locally matched command makes sense right now; otherwise the server decides.
function localApplies(cmd) {
  if (cmd.action === "choose_recipe") return cmd.choice <= offered.length;
  if (cmd.action === "set_doneness") {
    const recipe = session.getRecipe();
    return !recipe || donenessOptions(recipe).includes(cmd.doneness);
  }
  return true;
}

function heard(text) {
  const words = (text || "").trim();
  if (!words) return;
  logLine("you", words);
  el.interim.textContent = "";
  const local = matchLocal(words);
  if (local && localApplies(local)) {
    runAction(local);
    return;
  }
  askServer(words);
}

let thinking = false;
async function askServer(text) {
  if (thinking) return;
  thinking = true;
  el.status.textContent = t("thinking", lang);
  el.busy.hidden = false;
  try {
    runAction(await api.voiceText(text, voiceContext()));
  } catch (err) {
    voiceError(err);
  } finally {
    thinking = false;
    el.busy.hidden = !busy;
  }
}

function voiceError(err) {
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
}

const NEEDS_RECIPE = new Set(["next_step", "previous_step", "check_ingredients", "list_ingredients", "stop_recipe", "done"]);

function runAction(res) {
  const action = res.action;
  const reply = () => say(res.spoken_response, "command");
  const serverWords = res.local ? null : res.spoken_response;

  // Answering the clarifying question in your own words ("it smells a bit burnt") - that's the
  // follow-up for the second look, not a new request.
  if (pending && pending.type === "clarify" && (action === "answer" || action === "unclear") && res.heard) {
    clearPending();
    checkDoneness(res.heard);
    return;
  }
  // Doing anything else is also an answer to a pending question: it's dropped.
  if (pending && !["yes", "no", "hush"].includes(action)) clearPending();

  if (NEEDS_RECIPE.has(action) && !session.getRecipe()) {
    say(t("no_recipe_open", lang), "command");
    return;
  }

  switch (action) {
    case "hush":
      hush();
      break;
    case "yes":
    case "no":
      answer(action === "yes");
      break;
    case "start":
      if (session.getPhase() === "overview") beginSteps();
      else if (session.currentStep()) startTimer();
      else openRecipes();
      break;
    case "done": {
      const step = session.currentStep();
      if (!step) beginSteps();
      else if (step.checkable) checkDoneness(); // "done cutting" -> let me see before moving on
      else nextStep();
      break;
    }
    case "next_step":
      nextStep();
      break;
    case "previous_step":
      previousStep();
      break;
    case "repeat_step":
      repeat();
      break;
    case "start_timer":
      startTimer(res.timer_seconds, serverWords);
      break;
    case "add_time":
      addTime(res.timer_seconds, serverWords);
      break;
    case "stop_timer":
      stopTimer();
      break;
    case "check_doneness":
      checkDoneness();
      break;
    case "check_ingredients":
      checkIngredients();
      break;
    case "list_ingredients":
      readIngredients();
      break;
    case "identify":
      identify();
      break;
    case "list_recipes":
      openRecipes();
      break;
    case "find_recipe":
      if (res.candidates && res.candidates.length) showRecipeButtons(res.candidates);
      reply();
      break;
    case "choose_recipe": {
      const id = res.local ? offered[res.choice - 1] : res.recipe_id;
      if (id) startRecipe(id, serverWords || "");
      else reply();
      break;
    }
    case "set_doneness":
      if (res.doneness) setDoneness(res.doneness, serverWords);
      else reply();
      break;
    case "stop_recipe":
      askQuestion("stop_recipe", t("ask_stop", lang));
      break;
    default: // answer, unclear
      reply();
  }
}

// --- hands-free: "Hey chef" ---

const Recognition = getRecognition();
const recognitionLang = () => (LISTEN_LANG === "el" ? "el-GR" : "en-US");

function setListening(on) {
  document.querySelectorAll('[data-action="talk"]').forEach((b) => b.setAttribute("aria-pressed", String(on)));
  if (on) el.status.textContent = t("listening", lang);
  else el.interim.textContent = "";
}

function renderWakeState(state, detail) {
  el.wakeStatus.dataset.state = state;
  let text;
  if (state === "idle") text = `${t("wake_idle", lang)} · ${t(detail === "local" ? "wake_local" : "wake_cloud", lang)}`;
  else if (state === "armed") text = t("wake_armed", lang);
  else if (state === "error") text = t(detail === "unsupported" ? "wake_unsupported" : "wake_blocked", lang);
  else text = Recognition ? t("wake_off", lang) : t("wake_unsupported", lang);
  el.wakeStatus.textContent = text;
  el.wakeToggle.setAttribute("aria-pressed", String(state === "idle" || state === "armed"));
  if (state !== "armed") setListening(false);
}

const wake = createWakeListener({
  lang: recognitionLang(),
  onWake: () => {
    hush(); // don't talk over the cook - except a safety alert
    earcon("ok");
    buzz(20);
    setListening(true);
  },
  onCommand: (text) => {
    setListening(false);
    heard(text);
  },
  onInterim: (text) => {
    el.interim.textContent = text;
  },
  onTimeout: () => {
    setListening(false);
    el.status.textContent = t("wake_timeout", lang);
  },
  onState: renderWakeState,
});

async function setHandsFree(on, { announce = true } = {}) {
  if (!Recognition) {
    renderWakeState("error", "unsupported");
    if (announce) say(t("wake_unsupported", lang), "command");
    return;
  }
  savePref("wake", on ? "1" : "0");
  if (on) {
    await wake.start();
    if (announce) say(t("wake_on_said", lang), "command");
  } else {
    wake.stop();
    if (announce) say(t("wake_off_said", lang), "command");
  }
}

// --- the talk button: the browser's recognizer when there is one, else record + server ---

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

// RMS level of a stream, for the recorder's end-of-speech detection.
function levelMeter(stream) {
  const source = caps.audioCtx.createMediaStreamSource(stream);
  const analyser = caps.audioCtx.createAnalyser();
  analyser.fftSize = 1024;
  source.connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  return {
    read() {
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += v * v;
      return Math.sqrt(sum / buf.length);
    },
    close() {
      source.disconnect();
    },
  };
}

function setRecordState(state) {
  setListening(state === "listening");
  if (state === "listening") {
    earcon("ok");
    buzz(20);
  } else if (state === "thinking") {
    el.status.textContent = t("thinking", lang);
  }
  el.busy.hidden = !(busy || state === "thinking");
}

const talk = createPushToTalk({
  getStream: getVoiceStream,
  meter: (stream) => levelMeter(stream),
  send: (blob, type) => api.voiceCommand(blob, type, voiceContext()),
  onState: setRecordState,
  onResult: (res, reason) => {
    if (!res) {
      if (reason === "too_short") say(t("hold_to_talk", lang), "command");
      else if (reason === "no_speech") say(t("no_speech", lang), "command");
      return;
    }
    if (res.heard) logLine("you", res.heard);
    runAction(res);
  },
  onError: voiceError,
});

let pressedAt = 0;

function talkPressed() {
  if (el.app.hidden) return;
  pressedAt = Date.now();
  hush(); // don't talk over the cook - except a safety alert
  if (Recognition) {
    wake.listenNow();
    earcon("ok");
    buzz(20);
    setListening(true);
  } else {
    talk.start();
  }
}

function talkReleased() {
  if (Recognition) return; // the recognizer hears when they've finished on its own
  if (Date.now() - pressedAt < TAP_MS) talk.autoStop();
  else talk.stop();
}

// pointerdown starts; lifting (anywhere - the pointer is captured) ends a hold.
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
  talkPressed();
});
const endTalkPointer = (e) => {
  if (e.pointerId !== talkPointer) return;
  talkPointer = null;
  talkReleased();
};
document.addEventListener("pointerup", endTalkPointer);
document.addEventListener("pointercancel", endTalkPointer);
// Focus leaving the window mid-hold would otherwise leave the V key "held" until MAX_MS.
window.addEventListener("blur", () => {
  if (!Recognition) talk.stop();
});

// --- buttons, keys, typing ---

const ACTIONS = {
  identify: () => identify(),
  recipes: () => openRecipes(),
  "close-recipes": () => {
    offered = [];
    showPanel("home");
  },
  "open-recipe": (btn) => startRecipe(btn.dataset.recipeId),
  "start-cooking": () => beginSteps(),
  "read-ingredients": () => readIngredients(),
  "check-ingredients": () => checkIngredients(),
  tick: (btn) => {
    const i = Number(btn.dataset.index);
    if (ticked.has(i)) ticked.delete(i);
    else ticked.add(i);
    btn.setAttribute("aria-pressed", String(ticked.has(i)));
  },
  doneness: (btn) => setDoneness(btn.dataset.doneness),
  check: () => checkDoneness(),
  "start-timer": () => startTimer(),
  "timer-add": (btn) => {
    timers.add(btn.dataset.timer, 60);
    earcon("ok");
  },
  "timer-sub": (btn) => {
    timers.add(btn.dataset.timer, -60);
    earcon("ok");
  },
  "timer-stop": (btn) => stopTimer(btn.dataset.timer),
  repeat: () => repeat(),
  next: () => nextStep(),
  previous: () => previousStep(),
  stop: () => askQuestion("stop_recipe", t("ask_stop", lang)),
  "answer-yes": () => answer(true),
  "answer-no": () => answer(false),
  "alert-ok": () => {
    el.alert.hidden = true;
  },
  "wake-toggle": () => setHandsFree(!wake.isOn()),
  "detect-toggle": () => setDetection(!detector.isRunning()),
};

// No per-button onclick - delegate from a single document-level click listener.
document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-action]");
  if (!btn) return;
  const action = btn.dataset.action;
  if (action === "start" || action === "talk") return; // handled by their own listeners
  const handler = ACTIONS[action];
  if (handler) handler(btn);
});

el.ask.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = el.askInput.value.trim();
  if (!text) return;
  el.askInput.value = "";
  heard(text);
});

// A Bluetooth shutter remote pairs as a keyboard, so this covers both the real
// remote and a laptop operator pressing space. A touch-only tablet never emits
// keydown, so this stays a convenience, not the main path.
document.addEventListener("keydown", (e) => {
  if (el.app.hidden) return;
  const tag = e.target && e.target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || (e.target && e.target.isContentEditable)) return; // typing
  // V held = the talk button (PC demo). e.code, not e.key: on a Greek layout V types "ω".
  if (e.code === "KeyV" && !e.ctrlKey && !e.altKey && !e.metaKey) {
    e.preventDefault();
    if (!e.repeat) talkPressed();
    return;
  }
  if (e.key === " " || e.key === "Enter") {
    if (e.target && e.target.closest && e.target.closest("button")) return; // the button's own click
    e.preventDefault();
    if (session.getRecipe()) {
      checkDoneness();
    } else {
      identify();
    }
  } else if (e.key === "ArrowRight") {
    if (session.getRecipe()) {
      nextStep();
    }
  }
});

document.addEventListener("keyup", (e) => {
  if (e.code === "KeyV") talkReleased();
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
    localize();

    el.debug.textContent = warnings.length ? warnings.join(" | ") : "";

    // The recognizer never hears the app itself: it's paused for as long as speech plays.
    registerAcousticGate((open) => wake.setGate(open));
    // Some browsers occasionally never fire the end of an utterance; don't stay deaf because of it.
    setInterval(() => {
      const synth = window.speechSynthesis;
      if (!wake.isGateOpen() && !isSpeaking() && !synth.speaking && !synth.pending) wake.setGate(true);
    }, 3000);

    const handsFree = Recognition && params.get("wake") !== "0" && (params.get("wake") === "1" || loadPref("wake") !== "0");
    if (handsFree) {
      await setHandsFree(true, { announce: false });
    } else {
      renderWakeState(Recognition ? "off" : "error", Recognition ? undefined : "unsupported");
    }

    say(t(handsFree ? "greeting" : "greeting_no_wake", lang), "command");
    if (warnings.some((w) => /greek/i.test(w))) {
      speak(t("no_greek_voice", "en"), { priority: "checkin", lang: "en" });
    }

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
