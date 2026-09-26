// Exercises a11y.js (long-press / hover / focus speech) and tts.js's priority rules against a
// fake speechSynthesis that models the real queue - including cancel() firing the cancelled
// utterances' end events asynchronously, which is where the ordering bugs hide.

const store = {};
globalThis.localStorage = {
  getItem: (k) => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
};

const synth = {
  playing: null,
  queue: [],
  log: [],
  get speaking() { return this.playing !== null; },
  get pending() { return this.queue.length > 0; },
  speak(u) {
    this.log.push("speak:" + u.text);
    if (this.playing) this.queue.push(u);
    else this._start(u);
  },
  _start(u) { this.playing = u; u.onstart && u.onstart(); },
  finish() {
    const u = this.playing;
    this.playing = null;
    u && u.onend && u.onend();
    const next = this.queue.shift();
    if (next) this._start(next);
  },
  cancel() {
    const dropped = [this.playing, ...this.queue].filter(Boolean);
    this.playing = null;
    this.queue = [];
    this.log.push("cancel");
    for (const u of dropped) setTimeout(() => u.onend && u.onend(), 0);
  },
  getVoices: () => [],
  addEventListener() {},
  removeEventListener() {},
  pause() {},
  resume() {},
};
globalThis.window = { speechSynthesis: synth };
globalThis.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };

const tts = await import("../static/js/tts.js");
const a11y = await import("../static/js/a11y.js");

function assert(cond, message) {
  if (!cond) throw new Error("assertion failed: " + message);
}
const tick = () => new Promise((r) => setTimeout(r, 0));

function reset() {
  tts.stopAll();
  synth.playing = null;
  synth.queue = [];
  synth.log = [];
}

// ---------------------------------------------------------------- tts priorities

async function testHintNeverInterruptsRealSpeech() {
  reset();
  tts.speak("step one", { priority: "command", lang: "en" });
  const before = synth.log.length; // the command itself cancels whatever was there first
  const accepted = tts.speak("hint text", { priority: "hint", lang: "en" });
  assert(accepted === false, "hint during a command is dropped");
  assert(synth.log.length === before && synth.playing.text === "step one", `command not cancelled: ${synth.log}`);
  synth.finish();
  await tick();
  assert(tts.speak("hint text", { priority: "hint", lang: "en" }) === true, "hint plays once idle");
  assert(tts.speak("another hint", { priority: "hint", lang: "en" }) === true, "a hint replaces a hint");
  assert(synth.log.at(-2) === "cancel", `second hint cancelled the first: ${synth.log}`);
  console.log("test a (hints never interrupt real speech) OK");
}

async function testCommandQueuesBehindSafety() {
  reset();
  tts.speak("filler", { priority: "hint", lang: "en" });
  tts.speak("FIRE - turn off the burner", { priority: "safety", lang: "en" });
  await tick(); // the cancelled hint's late onend arrives now - must not clear the safety state
  const cancelsBefore = synth.log.filter((x) => x === "cancel").length;
  tts.speak("Let me take a look.", { priority: "command", lang: "en" });
  assert(synth.playing.text === "FIRE - turn off the burner", "safety still playing");
  assert(synth.queue.length === 1 && synth.queue[0].text === "Let me take a look.", "command queued behind it");
  assert(synth.log.filter((x) => x === "cancel").length === cancelsBefore, `the command cancelled nothing: ${synth.log}`);
  console.log("test b (a command queues behind a safety alert) OK");
}

async function testHushSparesSafety() {
  reset();
  tts.speak("step one", { priority: "command", lang: "en" });
  assert(tts.hush() === true && synth.playing === null, "talk silences a command");
  await tick();
  tts.speak("FIRE - turn off the burner", { priority: "safety", lang: "en" });
  assert(tts.hush() === false && synth.playing.text === "FIRE - turn off the burner", "talk never silences safety");
  synth.finish();
  await tick();
  assert(tts.hush() === true, "once the alert is over, hush works again");
  console.log("test j (hush spares a safety alert) OK");
}

async function testCommandStillInterruptsCommand() {
  reset();
  tts.speak("old instruction", { priority: "command", lang: "en" });
  tts.speak("new instruction", { priority: "command", lang: "en" });
  assert(synth.playing.text === "new instruction", "newer command wins");
  console.log("test c (a command still interrupts a command) OK");
}

// ---------------------------------------------------------------- a11y gestures

function makeRoot() {
  const listeners = {};
  return {
    addEventListener(type, fn) { (listeners[type] ||= []).push(fn); },
    dispatch(type, ev) {
      for (const fn of listeners[type] || []) {
        fn(ev);
        if (ev.stopped) break;
      }
      return ev;
    },
  };
}

function makeButton(speakKey, text, { focusVisible = false } = {}) {
  const b = {
    dataset: speakKey ? { speak: speakKey } : {},
    disabled: false,
    textContent: text,
    getAttribute: () => null,
    matches: (q) => q === ":focus-visible" && focusVisible,
  };
  b.closest = () => b;
  return b;
}

function ev(target, extra = {}) {
  return {
    target,
    pointerType: "touch",
    clientX: 100,
    clientY: 100,
    relatedTarget: null,
    defaultPrevented: false,
    stopped: false,
    preventDefault() { this.defaultPrevented = true; },
    stopImmediatePropagation() { this.stopped = true; },
    ...extra,
  };
}

function setup() {
  const root = makeRoot();
  const said = [];
  const vibrations = [];
  const timers = [];
  let clock = 0;
  a11y.installSpeakOnPress({
    root,
    getLang: () => "el",
    say: (text) => said.push(text),
    vibrate: (ms) => vibrations.push(ms),
    setTimer: (fn, ms) => { timers.push({ fn, ms, live: true }); return timers.length - 1; },
    clearTimer: (id) => { if (timers[id]) timers[id].live = false; },
    now: () => clock,
  });
  const appClicks = [];
  root.addEventListener("click", (e) => appClicks.push(e.target)); // app.js's delegated handler, registered after
  const runTimers = () => {
    for (const t of timers.splice(0)) if (t.live) t.fn();
  };
  return { root, said, vibrations, appClicks, runTimers, advance: (ms) => (clock += ms) };
}

function testLongPressSpeaksAndSwallowsTheClick() {
  const s = setup();
  const check = makeButton("check", "Έλεγξε");
  s.root.dispatch("pointerdown", ev(check));
  s.runTimers();
  assert(s.said.length === 1 && s.said[0].startsWith("Έλεγξε. Βγάζει"), `spoke the Greek description: ${s.said}`);
  assert(s.vibrations[0] === 20, "short haptic tick");
  s.root.dispatch("pointerup", ev(check));
  const click = s.root.dispatch("click", ev(check));
  assert(s.appClicks.length === 0 && click.defaultPrevented, "the action did NOT fire");
  console.log("test d (long-press speaks, action suppressed) OK");
}

function testShortTapActivatesSilently() {
  const s = setup();
  const next = makeButton("next", "Επόμενο");
  s.root.dispatch("pointerdown", ev(next));
  s.root.dispatch("pointerup", ev(next)); // released before 500 ms: the timer is cleared
  s.runTimers();
  s.root.dispatch("click", ev(next));
  assert(s.said.length === 0, "nothing spoken");
  assert(s.appClicks.length === 1, "action fired");
  console.log("test e (short tap activates, no speech) OK");
}

function testDragCancelsAndStaleSuppressionExpires() {
  const s = setup();
  const b = makeButton("repeat", "Επανάλαβε");
  s.root.dispatch("pointerdown", ev(b));
  s.root.dispatch("pointermove", ev(b, { clientX: 140 }));
  s.runTimers();
  assert(s.said.length === 0, "a drag is not a long-press");

  s.root.dispatch("pointerdown", ev(b));
  s.runTimers(); // long-press fires
  s.root.dispatch("pointerup", ev(b));
  s.runTimers(); // browser never sent a click; the suppression window lapses
  s.root.dispatch("click", ev(b));
  assert(s.appClicks.length === 1, "the next genuine tap is not swallowed");
  console.log("test f (drag cancels, stale suppression expires) OK");
}

function testHoverSpeaksOnceAndFocusOnlyWhenKeyboard() {
  const s = setup();
  const b = makeButton("identify", "Τι είναι αυτό;");
  s.root.dispatch("pointerover", ev(b, { pointerType: "mouse" }));
  s.root.dispatch("pointerover", ev(b, { pointerType: "mouse" })); // moving within the button
  s.runTimers();
  assert(s.said.length === 1, `hover spoke once, got ${s.said.length}`);
  s.root.dispatch("pointerout", ev(b, { pointerType: "mouse" }));
  s.root.dispatch("pointerover", ev(b, { pointerType: "mouse" }));
  s.advance(500);
  s.runTimers();
  assert(s.said.length === 1, "re-entering within 1.5 s doesn't repeat");

  s.root.dispatch("focusin", ev(makeButton("stop", "Διακοπή", { focusVisible: false })));
  assert(s.said.length === 1, "pointer focus is silent");
  s.root.dispatch("focusin", ev(makeButton("stop", "Διακοπή", { focusVisible: true })));
  assert(s.said.length === 2 && s.said[1].startsWith("Διακοπή."), "keyboard focus speaks");
  console.log("test g (hover once, focus only for keyboard) OK");
}

function testHoldToTalkIsNeverALongPress() {
  const s = setup();
  const talk = makeButton("talk", "Μίλα");
  talk.dataset.hold = "1";
  s.root.dispatch("pointerdown", ev(talk));
  s.runTimers();
  assert(s.said.length === 0 && s.vibrations.length === 0, "holding the talk button stays silent");
  s.root.dispatch("pointerover", ev(talk, { pointerType: "mouse" }));
  s.runTimers();
  assert(s.said.length === 1 && s.said[0].startsWith("Μίλα."), `hover still describes it: ${s.said}`);
  console.log("test i (hold-to-talk is never a long-press) OK");
}

function testOptOut() {
  const s = setup();
  a11y.setSpeakButtons(false);
  s.root.dispatch("pointerdown", ev(makeButton("check", "x")));
  s.runTimers();
  assert(s.said.length === 0, "opted out: silent");
  a11y.setSpeakButtons(true);
  console.log("test h (per-device opt-out) OK");
}

await testHintNeverInterruptsRealSpeech();
await testCommandQueuesBehindSafety();
await testCommandStillInterruptsCommand();
await testHushSparesSafety();
testLongPressSpeaksAndSwallowsTheClick();
testShortTapActivatesSilently();
testDragCancelsAndStaleSuppressionExpires();
testHoverSpeaksOnceAndFocusOnlyWhenKeyboard();
testHoldToTalkIsNeverALongPress();
testOptOut();
tts.stopAll();

console.log("all passed");
