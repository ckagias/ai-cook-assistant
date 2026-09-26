// wake.js against a fake SpeechRecognition: the wake phrase with and without a command in the
// same breath, nothing acted on without it, the app's own speech ignored, restarts after the
// browser ends a session, a blocked microphone, and the talk button's one-shot listening.

const { createWakeListener, ARM_MS } = await import("../static/js/wake.js");

function assert(cond, message) {
  if (!cond) throw new Error("assertion failed: " + message);
}
const tick = () => new Promise((r) => setTimeout(r, 0));

class FakeRecognition {
  static instances = [];
  constructor() {
    this.started = 0;
    this.aborted = 0;
    this.active = false;
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

async function setup() {
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
    probeLocal: async () => false,
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
  s.rec().hear("Γεια σου σεφ επόμενο", false);
  assert(s.log.woke === 1 && s.log.commands.length === 0, "woke on the interim result, waits for the final one");
  s.rec().hear("Γεια σου σεφ επόμενο βήμα", true);
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
  s.listener.setGate(false); // the app starts speaking
  assert(s.rec().aborted === 1 && !s.rec().active, "recognition stops while the app talks");
  s.rec().hear("Πες γεια σου σεφ επόμενο", true); // a late result of the app's own voice
  assert(s.log.woke === 0 && s.log.commands.length === 0, "the app's own voice is dropped");
  s.fire(); // no restart while closed
  assert(!s.rec().active, "stays stopped until speech ends");
  s.listener.setGate(true);
  assert(s.rec().active && s.rec().started === 2, "listening again after the app finishes");
  console.log("test f (the app's own speech is ignored) OK");
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
await tick();

console.log("all passed");
