// wake.js against a fake SpeechRecognition: the wake phrase with and without a command in the
// same breath, nothing acted on without it, the app's own speech ignored, restarts after the
// browser ends a session, a blocked microphone, and the talk button's one-shot listening.

const { createWakeListener, ARM_MS, SETTLE_MS, RELEASE_FINAL_MS, MAX_ALTERNATIVES } = await import("../static/js/wake.js");

function assert(cond, message) {
  if (!cond) throw new Error("assertion failed: " + message);
}
const tick = () => new Promise((r) => setTimeout(r, 0));

class FakeRecognition {
  static instances = [];
  constructor() {
    this.started = 0;
    this.aborted = 0;
    this.stopped = 0;
    this.active = false;
    this.phrases = null; // newer Chrome has the property; a list is set only for on-device recognition
    FakeRecognition.instances.push(this);
  }
  start() {
    if (this.active) throw new Error("InvalidStateError");
    this.active = true;
    this.started += 1;
    this.onstart && this.onstart();
  }
  abort() {
    this.aborted += 1;
    this.end();
  }
  stop() {
    this.stopped += 1; // a real one hands over its final result, then ends
  }
  end() {
    if (!this.active) return;
    this.active = false;
    this.onend && this.onend();
  }
  // One recognition result; `alternatives` is a string or a list of them.
  hear(alternatives, isFinal = true, index = 0) {
    const alts = [].concat(alternatives).map((transcript) => ({ transcript }));
    const result = Object.assign(alts, { isFinal });
    const results = [];
    results[index] = result;
    this.onresult && this.onresult({ resultIndex: index, results });
  }
  fail(error) {
    this.onerror && this.onerror({ error });
    this.end();
  }
}

async function setup({ cleanEcho, local = false, onHeard, phrases, tuning = {} } = {}) {
  FakeRecognition.instances = [];
  const log = { woke: 0, commands: [], interim: [], timeouts: 0, states: [] };
  const timers = [];
  const listener = createWakeListener({
    Recognition: FakeRecognition,
    lang: "el-GR",
    onWake: () => (log.woke += 1),
    onCommand: (text) => log.commands.push(text),
    onInterim: (text) => log.interim.push(text),
    onTimeout: () => (log.timeouts += 1),
    onState: (state, detail) => log.states.push(detail ? `${state}:${detail}` : state),
    setTimer: (fn, ms) => {
      timers.push({ fn, ms, live: true });
      return timers.length - 1;
    },
    clearTimer: (id) => {
      if (timers[id]) timers[id].live = false;
    },
    probeLocal: async () => local,
    ...(cleanEcho ? { cleanEcho } : {}),
    ...(onHeard ? { onHeard } : {}),
    ...(phrases ? { phrases } : {}),
    ...tuning,
  });
  const fire = (ms) => {
    for (const t of timers.splice(0)) if (t.live && (ms === undefined || t.ms === ms)) t.fn();
  };
  return { listener, log, timers, fire, rec: () => FakeRecognition.instances[0] };
}

async function testWakeAndCommandInOneBreath() {
  const s = await setup();
  await s.listener.start();
  assert(s.rec().started === 1 && s.rec().continuous && s.rec().lang === "el-GR", "listening continuously in Greek");
  assert(s.log.states.includes("idle:cloud"), `reports cloud mode: ${s.log.states}`);
  s.rec().hear("Χέι σεφ επόμενο", false);
  assert(s.log.woke === 1 && s.log.commands.length === 0, "woke on the interim result, waits for the final one");
  s.rec().hear("Χέι σεφ επόμενο βήμα", true);
  assert(s.log.woke === 1, "one wake per utterance");
  assert(s.log.commands[0] === "επόμενο βήμα", `command: ${s.log.commands}`);
  assert(!s.listener.isArmed(), "back to waiting for the wake phrase");
  console.log("test a (wake phrase + command in one breath) OK");
}

async function testWakeThenCommand() {
  const s = await setup();
  await s.listener.start();
  s.rec().hear(["hey chef"], true, 0);
  assert(s.log.woke === 1 && s.listener.isArmed(), "armed after the wake phrase alone");
  s.rec().hear("θέλω να φτιάξω", false, 1);
  assert(s.log.interim[0] === "θέλω να φτιάξω", "live caption while armed");
  s.rec().hear("θέλω να φτιάξω ροσμπίφ", true, 1);
  assert(s.log.commands[0] === "θέλω να φτιάξω ροσμπίφ", `command: ${s.log.commands}`);
  console.log("test b (wake phrase, then the command) OK");
}

async function testNothingWithoutTheWakePhrase() {
  const s = await setup();
  await s.listener.start();
  s.rec().hear("επόμενο βήμα", true);
  s.rec().hear("the chef on TV says next step", true, 1);
  assert(s.log.woke === 0 && s.log.commands.length === 0, "a TV or a conversation doesn't command the app");
  console.log("test c (nothing without the wake phrase) OK");
}

async function testAlternativeCanCarryTheWakePhrase() {
  const s = await setup();
  await s.listener.start();
  s.rec().hear(["χέρι σεφ", "χέι σεφ επανάλαβε"], true);
  assert(s.log.woke === 1 && s.log.commands[0] === "επανάλαβε", `second-best transcript counts: ${s.log.commands}`);
  console.log("test d (a lower-ranked alternative can carry the wake phrase) OK");
}

async function testArmedTimesOut() {
  const s = await setup();
  await s.listener.start();
  s.rec().hear("hey chef", true);
  s.fire(ARM_MS);
  assert(s.log.timeouts === 1 && !s.listener.isArmed(), "gave up waiting");
  s.rec().hear("next step", true, 1);
  assert(s.log.commands.length === 0, "and later words need the wake phrase again");
  console.log("test e (armed, nothing said: times out) OK");
}

async function testOwnSpeechIsIgnored() {
  const s = await setup();
  await s.listener.start();
  s.listener.setSpeaking(true, { saysWake: true }); // the app says "Say hey chef..." (the greeting)
  assert(s.rec().aborted === 1 && !s.rec().active, "recognition stops while the app says the wake phrase");
  s.rec().hear("Πες χέι σεφ επόμενο", true); // a late result of the app's own voice
  assert(s.log.woke === 0 && s.log.commands.length === 0, "the app's own voice is dropped");
  s.fire(); // no restart while closed
  assert(!s.rec().active, "stays stopped until that sentence ends");
  s.listener.setSpeaking(false);
  assert(s.rec().active && s.rec().started === 2, "listening again after the app finishes");
  console.log("test f (a sentence that says the wake phrase can't wake the app) OK");
}

async function testRestartsWhenTheBrowserEndsTheSession() {
  const s = await setup();
  await s.listener.start();
  s.rec().end(); // Chrome ends continuous sessions on its own
  s.fire();
  assert(s.rec().active && s.rec().started === 2, "restarted");
  s.rec().fail("network");
  const retry = s.timers.find((t) => t.live);
  assert(retry && retry.ms > 250, `backs off after a network error: ${retry && retry.ms}`);
  console.log("test g (restarts after the browser ends a session) OK");
}

async function testBlockedMicrophoneTurnsItOff() {
  const s = await setup();
  await s.listener.start();
  s.rec().fail("not-allowed");
  s.fire();
  assert(!s.rec().active && !s.listener.isOn(), "not restarted into a refusal loop");
  assert(s.log.states.at(-1) === "error:not-allowed", `reported: ${s.log.states}`);
  console.log("test h (a blocked microphone turns hands-free off) OK");
}

async function testTalkButtonWithHandsFreeOff() {
  const s = await setup();
  assert(s.listener.listenNow() && s.listener.isArmed(), "the talk button arms it without a wake phrase");
  assert(s.rec().active, "recognizer running just for this");
  s.rec().hear("πόσο λάδι βάζω", true);
  assert(s.log.commands[0] === "πόσο λάδι βάζω", "the command, no wake phrase needed");
  assert(!s.listener.isOn() && !s.rec().active, "then it stops listening again");
  assert(s.log.states.at(-1) === "off", `state: ${s.log.states}`);
  console.log("test i (talk button with hands-free off) OK");
}

async function testStopEndsEverything() {
  const s = await setup();
  await s.listener.start();
  s.rec().hear("hey chef", true);
  s.listener.stop();
  s.fire();
  assert(!s.rec().active && !s.listener.isArmed() && s.log.states.at(-1) === "off", "stopped and not restarted");
  console.log("test j (stop) OK");
}

async function testUnsupportedBrowser() {
  const states = [];
  const listener = createWakeListener({ Recognition: null, onState: (s, d) => states.push(`${s}:${d}`) });
  assert((await listener.start()) === false && states[0] === "error:unsupported", "reports unsupported");
  assert(listener.listenNow() === false, "the talk button falls back to recording");
  console.log("test k (a browser without speech recognition) OK");
}

// Measured with Chrome's real recognizer: el-GR never marks a result final in continuous mode.
async function testGreekInterimSettles() {
  const s = await setup();
  await s.listener.start();
  s.rec().hear("χέι σεφ", false);
  s.rec().hear("χέι σεφ επόμενο βήμα", false);
  assert(s.log.woke === 1 && s.log.commands.length === 0, "woke, waiting");
  s.fire(SETTLE_MS);
  assert(s.rec().stopped === 1, "words stopped changing: asked the recognizer for its final result");
  s.rec().hear(["χέι σε επόμενο βήμα", "χέι σε επομένω βήμα"], true); // the φ dropped, as measured
  assert(s.log.commands[0] === "επόμενο βήμα", `command: ${s.log.commands}`);
  s.rec().end();
  s.fire();
  assert(s.rec().active && s.rec().started === 2, "a fresh session afterwards");
  console.log("test l (Greek: no final result -> stop() once the words settle) OK");
  const t = await setup();
  await t.listener.start();
  t.rec().hear("χέι σεφ", false);
  t.fire(SETTLE_MS);
  assert(t.rec().stopped === 0 && t.listener.isArmed(), "the wake phrase alone doesn't cut the session short");
  console.log("test l2 (the wake phrase alone waits for the command) OK");
}

async function testArmedAlternativeStripsTheWakePhrase() {
  const s = await setup();
  await s.listener.start();
  s.rec().hear("hey chef", false);
  s.rec().hear(["patient I want to make roast beef", "hey chef I want to make roast beef"], true);
  assert(s.log.commands[0] === "I want to make roast beef", `command: ${s.log.commands}`);
  console.log("test m (armed: the wake phrase is stripped from whichever alternative has it) OK");
}

// "Hey chef" cuts in while the app is talking (a long step, the opening questions): the recognizer
// keeps running, the app's own words never count, and the wake phrase does.
async function testWakeWhileTheAppTalks() {
  const s = await setup();
  await s.listener.start();
  s.listener.setSpeaking(true); // reading a step - no wake phrase in it
  assert(s.rec().active && s.rec().aborted === 0, "still listening while the app talks");
  s.rec().hear("Σπάστε τα αυγά σε ένα μπολ", true);
  assert(s.log.woke === 0 && s.log.commands.length === 0, "the app's own voice is no command");
  s.rec().hear("και χτυπήστε τα χέι σεφ είμαι αλλεργικός", false, 1);
  assert(s.log.woke === 1, "woke mid-sentence");
  s.listener.setSpeaking(false); // the app stops talking at once (interrupt)
  s.rec().hear("και χτυπήστε τα χέι σεφ είμαι αλλεργικός στα καρύδια", true, 1);
  assert(s.log.commands[0] === "είμαι αλλεργικός στα καρύδια", `command: ${s.log.commands}`);
  console.log("test n (Hey chef interrupts the app while it talks) OK");
}

// A safety alert is never cut off, so the app can still be talking once armed: its words wait.
async function testArmedWhileAnAlertPlaysOn() {
  const s = await setup();
  await s.listener.start();
  s.listener.setSpeaking(true);
  s.rec().hear("hey chef", true);
  assert(s.listener.isArmed(), "armed");
  s.rec().hear("Φωτιά κλείσε το μάτι", true, 1); // the alert, still playing
  assert(s.log.commands.length === 0 && s.listener.isArmed(), "the alert's words are not the command");
  s.listener.setSpeaking(false);
  s.rec().hear("τι να κάνω", true, 2);
  assert(s.log.commands[0] === "τι να κάνω", `command after the alert: ${s.log.commands}`);
  console.log("test o (armed while a safety alert plays on) OK");
}

// Held talk button: a pause is not the end ("I have the eggs... and the milk"), letting go is.
async function testHeldListensUntilRelease() {
  const s = await setup();
  assert(s.listener.hold() && s.listener.isHeld(), "listening while held, no wake word");
  s.rec().hear("έχω τα αυγά", false, 1);
  s.fire(SETTLE_MS);
  assert(s.rec().stopped === 0 && s.log.commands.length === 0, "a pause while held doesn't cut it off");
  s.rec().hear("έχω τα αυγά και το γάλα", false, 1);
  assert(s.log.interim.at(-1) === "έχω τα αυγά και το γάλα", "live caption while held");
  s.listener.release();
  assert(s.rec().stopped === 1, "let go: asked the recognizer for its last words");
  s.rec().hear("έχω τα αυγά και το γάλα", true, 1);
  assert(s.log.commands[0] === "έχω τα αυγά και το γάλα", `command at release: ${s.log.commands}`);
  assert(!s.listener.isOn(), "hands-free was off: back off after the one command");
  console.log("test p (held: no cut-off on a pause, the command on release) OK");

  const t = await setup();
  t.listener.hold();
  t.rec().hear("πόσο αλάτι", false, 1);
  t.listener.release();
  t.fire(RELEASE_FINAL_MS); // Greek never finalizes: act on the words heard so far
  assert(t.log.commands[0] === "πόσο αλάτι", `no final result: the interim words count: ${t.log.commands}`);
  const u = await setup();
  u.listener.hold();
  u.listener.release();
  u.fire(RELEASE_FINAL_MS);
  assert(u.log.commands.length === 0 && u.log.timeouts === 1, "held, nothing said: nothing acted on");
  console.log("test p2 (released: the last words, or nothing) OK");
}

// The lock: commands one after another without the wake word, until unlocked.
async function testLockedTakesCommandsWithoutTheWakeWord() {
  const s = await setup();
  s.listener.setLocked(true);
  assert(s.listener.isLocked() && s.rec().active && s.listener.isArmed(), "listening, no wake word needed");
  s.rec().hear("επόμενο βήμα", true, 1);
  assert(s.log.commands[0] === "επόμενο βήμα" && s.listener.isArmed(), "acted on, and still listening");
  s.fire(ARM_MS);
  assert(s.log.timeouts === 0 && s.listener.isArmed(), "a lock doesn't time out");
  s.listener.setSpeaking(true); // the app answers
  s.rec().hear("Βήμα 2 από 8 προθέρμανε τον φούρνο", true, 2);
  assert(s.log.commands.length === 1, "the app's own answer is no command");
  s.listener.setSpeaking(false);
  s.rec().hear("πόση ώρα μένει", true, 3);
  assert(s.log.commands[1] === "πόση ώρα μένει", `next command: ${s.log.commands}`);
  s.listener.setLocked(false);
  assert(!s.listener.isOn() && !s.rec().active, "unlocked: hands-free was off, so listening stops");

  const h = await setup();
  h.listener.setLocked(true);
  await h.listener.start(); // hands-free switched on while locked
  h.listener.setLocked(false);
  assert(h.listener.isOn() && !h.listener.isArmed(), "unlocked: hands-free stays on, waiting for the wake word");
  console.log("test q (locked: commands without the wake word until unlocked) OK");
}

// What the app itself said is taken out of the command before it's acted on (echo.js).
async function testEchoIsTakenOut() {
  const s = await setup({ cleanEcho: (text) => text.replace(/^2 αυγά\s*/, "") });
  await s.listener.start();
  s.rec().hear("σεφ", true, 0);
  s.rec().hear("2 αυγά έχω συλλέξει τα πάντα", true, 1);
  assert(s.log.commands[0] === "έχω συλλέξει τα πάντα", `the app's words gone: ${s.log.commands}`);
  console.log("test r (the app's own words are taken out of the command) OK");
}

await testGreekInterimSettles();
await testArmedAlternativeStripsTheWakePhrase();
await testWakeWhileTheAppTalks();
await testArmedWhileAnAlertPlaysOn();
await testHeldListensUntilRelease();
await testLockedTakesCommandsWithoutTheWakeWord();
await testEchoIsTakenOut();
await testWakeAndCommandInOneBreath();
await testWakeThenCommand();
await testNothingWithoutTheWakePhrase();
await testAlternativeCanCarryTheWakePhrase();
await testArmedTimesOut();
await testOwnSpeechIsIgnored();
await testRestartsWhenTheBrowserEndsTheSession();
await testBlockedMicrophoneTurnsItOff();
await testTalkButtonWithHandsFreeOff();
await testStopEndsEverything();
await testUnsupportedBrowser();

// Sensitivity: more guesses per result, the wake name as a hint where the browser takes one, and
// every raw result reported for the "what I heard" view.
async function testMoreGuessesHintsAndWhatWasHeard() {
  const heard = [];
  const s = await setup({ onHeard: (h) => heard.push(h) });
  await s.listener.start();
  assert(s.rec().maxAlternatives === MAX_ALTERNATIVES && MAX_ALTERNATIVES === 5, "five guesses per result");
  assert(s.rec().phrases === null, "cloud recognition: no phrase list (on-device only)");
  s.rec().hear(["χέρι σε φ", "κερί", "τι κάνεις", "σεφ πόση ώρα", "σε"], false, 0);
  assert(s.log.woke === 1, "the wake name in the fourth guess still wakes it");
  assert(heard[0].alternatives.length === 5 && heard[0].woke && heard[0].isFinal === false && heard[0].id === "1:0",
    `raw result reported: ${JSON.stringify(heard[0])}`);
  console.log("test s (five guesses; what was heard is reported) OK");

  const t = await setup({ local: true, phrases: () => ["σεφ", "χέι σεφ"] });
  await t.listener.start();
  assert(t.log.states.includes("idle:local"), "on-device recognition");
  assert(JSON.stringify(t.rec().phrases) === '["σεφ","χέι σεφ"]', `hints set on-device: ${t.rec().phrases}`);
  t.rec().fail("phrases-not-supported");
  t.fire(); // the restart after a session ends
  await tick();
  const next = FakeRecognition.instances.at(-1);
  assert(next !== t.rec() && next.phrases === null && next.active, "refused: listening again, without hints");
  assert(!t.log.states.some((x) => x.startsWith("error")), "not an error for the cook");
  console.log("test t (wake-name hints on-device, dropped if refused) OK");
}
await testMoreGuessesHintsAndWhatWasHeard();

// Tuning from the link (?alts= ?settle= ?arm=): each takes effect; undefined keeps the default.
async function testTuning() {
  const s = await setup({ tuning: { alternatives: 8, settleMs: 900, armMs: 4000 } });
  await s.listener.start();
  assert(s.rec().maxAlternatives === 8, "alts");
  s.rec().hear("σεφ", true, 0); // the wake name alone: armed, waiting armMs for the command
  assert(s.timers.some((t) => t.live && t.ms === 4000) && !s.timers.some((t) => t.live && t.ms === ARM_MS), "arm");
  s.rec().hear("πόση ώρα μένει", false, 1);
  assert(s.timers.some((t) => t.live && t.ms === 900), "settle");
  const d = await setup({ tuning: { alternatives: undefined, settleMs: undefined, armMs: undefined } });
  await d.listener.start();
  assert(d.rec().maxAlternatives === MAX_ALTERNATIVES, "undefined -> the default");
  console.log("test u (tuning: alts, settle, arm; defaults when not given) OK");
}
await testTuning();
await tick();

console.log("all passed");
