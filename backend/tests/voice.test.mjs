// Exercises voice.js's push-to-talk state machine against a fake MediaRecorder: hold/release,
// an accidental tap, releasing before the microphone is ready, the 15 s cap, and no second
// recording while the first is still being understood.

const { createPushToTalk, pickMimeType, createSilenceDetector, MIN_MS, MAX_MS, CALIBRATE_MS, SILENCE_MS, NO_SPEECH_MS } =
  await import("../static/js/voice.js");

function assert(cond, message) {
  if (!cond) throw new Error("assertion failed: " + message);
}
const tick = () => new Promise((r) => setTimeout(r, 0));

class FakeRecorder {
  static supported = ["audio/webm;codecs=opus", "audio/webm"];
  static instances = [];
  static isTypeSupported(t) {
    return FakeRecorder.supported.includes(t);
  }
  constructor(stream, options) {
    this.stream = stream;
    this.mimeType = (options && options.mimeType) || "";
    this.state = "inactive";
    FakeRecorder.instances.push(this);
  }
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    // Like the real one: the last chunk arrives, then stop fires - both asynchronously.
    setTimeout(() => {
      this.ondataavailable && this.ondataavailable({ data: { size: 1200 } });
      this.onstop && this.onstop();
    }, 0);
  }
}
globalThis.Blob = class {
  constructor(parts, { type }) {
    this.parts = parts;
    this.type = type;
  }
};

function setup({ send, getStream, meter } = {}) {
  let clock = 0;
  const timers = [];
  const states = [];
  const results = [];
  const errors = [];
  const sent = [];
  FakeRecorder.instances = [];
  const ptt = createPushToTalk({
    getStream: getStream || (async () => ({ id: "mic" })),
    send: send || (async (blob, type) => {
      sent.push({ blob, type });
      return { action: "next_step", spoken_response: "" };
    }),
    onState: (s) => states.push(s),
    onResult: (res, reason) => results.push(res || reason),
    onError: (err) => errors.push(err),
    Recorder: FakeRecorder,
    meter,
    setTimer: (fn, ms) => { timers.push({ fn, ms, live: true }); return timers.length - 1; },
    clearTimer: (id) => { if (timers[id]) timers[id].live = false; },
    now: () => clock,
  });
  const runTimers = () => {
    for (const t of timers.splice(0)) if (t.live) t.fn();
  };
  return { ptt, states, results, errors, sent, timers, runTimers, advance: (ms) => (clock += ms) };
}

async function testHoldAndReleaseSendsTheRecording() {
  const s = setup();
  await s.ptt.start();
  assert(s.ptt.isRecording() && s.states[0] === "listening", "recording while held");
  assert(FakeRecorder.instances[0].mimeType === "audio/webm;codecs=opus", "best supported type");
  s.advance(1500);
  s.ptt.stop();
  await tick();
  await tick();
  assert(s.sent.length === 1 && s.sent[0].type === "audio/webm", `sent once, bare type: ${JSON.stringify(s.sent)}`);
  assert(s.results[0].action === "next_step", "result delivered");
  assert(s.states.join(",") === "listening,thinking,idle", `states: ${s.states}`);
  console.log("test a (hold, release, send) OK");
}

async function testAccidentalTapIsNotSent() {
  const s = setup();
  await s.ptt.start();
  s.advance(MIN_MS - 50);
  s.ptt.stop();
  await tick();
  assert(s.sent.length === 0, "a tap sends nothing");
  assert(s.results[0] === "too_short", `told why: ${s.results}`);
  console.log("test b (an accidental tap is not sent) OK");
}

async function testReleaseBeforeTheMicIsReady() {
  let grant;
  const s = setup({ getStream: () => new Promise((r) => (grant = r)) });
  const starting = s.ptt.start();
  s.ptt.stop(); // lifted before getUserMedia resolved
  grant({ id: "mic" });
  await starting;
  await tick();
  assert(!s.ptt.isRecording(), "not left recording with nobody holding the button");
  assert(s.sent.length === 0 && s.results[0] === "too_short", "and nothing sent");
  console.log("test c (released before the microphone was ready) OK");
}

async function testHeldTooLongStopsItself() {
  const s = setup();
  await s.ptt.start();
  const cap = s.timers.find((t) => t.live);
  assert(cap && cap.ms === MAX_MS, "a cap timer is armed");
  s.advance(MAX_MS);
  s.runTimers();
  await tick();
  await tick();
  assert(!s.ptt.isRecording() && s.sent.length === 1, "stopped itself and sent");
  console.log("test d (held too long stops itself) OK");
}

async function testNoSecondRecordingWhileThinking() {
  let answer;
  const s = setup({ send: () => new Promise((r) => (answer = r)) });
  await s.ptt.start();
  s.advance(1000);
  s.ptt.stop();
  await tick();
  assert(s.ptt.isBusy(), "waiting on the server");
  await s.ptt.start();
  assert(!s.ptt.isRecording() && FakeRecorder.instances.length === 1, "a second press is ignored while thinking");
  answer({ action: "repeat_step" });
  await tick();
  assert(!s.ptt.isBusy() && s.results[0].action === "repeat_step", "then idle again");
  console.log("test e (no second recording while thinking) OK");
}

async function testErrorsReachTheApp() {
  const denied = Object.assign(new Error("denied"), { name: "NotAllowedError" });
  const s = setup({ getStream: async () => { throw denied; } });
  await s.ptt.start();
  assert(s.errors[0] === denied && !s.ptt.isRecording(), "microphone refusal reported");
  assert(s.states.at(-1) === "idle", "back to idle");

  const s2 = setup({ send: async () => { throw new Error("HTTP 503"); } });
  await s2.ptt.start();
  s2.advance(1000);
  s2.ptt.stop();
  await tick();
  await tick();
  assert(s2.errors.length === 1 && s2.states.at(-1) === "idle", "server failure reported, idle again");
  console.log("test f (errors reach the app) OK");
}

function testPickMimeType() {
  assert(pickMimeType(FakeRecorder) === "audio/webm;codecs=opus", "webm/opus first");
  assert(pickMimeType({ isTypeSupported: (t) => t === "audio/mp4" }) === "audio/mp4", "Safari: mp4");
  assert(pickMimeType(undefined) === "", "no MediaRecorder: empty");
  console.log("test g (mime type choice) OK");
}

await testHoldAndReleaseSendsTheRecording();
await testAccidentalTapIsNotSent();
await testReleaseBeforeTheMicIsReady();
await testHeldTooLongStopsItself();
await testNoSecondRecordingWhileThinking();
await testErrorsReachTheApp();
testPickMimeType();

// --- tap to talk (no browser speech recognition): record until the cook stops talking ---

function testSilenceDetector() {
  let clock = 0;
  const feed = createSilenceDetector({ now: () => clock });
  const run = (level, ms) => {
    let out;
    for (let t = 0; t < ms; t += 50) {
      clock += 50;
      out = feed(level);
    }
    return out;
  };
  assert(feed(0.02) === "calibrating", "calibrates on the room first");
  run(0.02, CALIBRATE_MS); // a humming fan: the floor
  assert(run(0.03, 400) === "waiting", "the fan a bit louder is not speech (2.5x the floor)");
  assert(run(0.2, 400) === "speaking", "speech");
  assert(run(0.02, SILENCE_MS - 100) === "speaking", "a pause mid-sentence is not the end");
  assert(run(0.02, 300) === "done", "quiet after speech: done");

  clock = 0;
  const idle = createSilenceDetector({ now: () => clock });
  let out;
  for (let t = 0; t <= NO_SPEECH_MS; t += 50) {
    clock = t;
    out = idle(0.001);
  }
  assert(out === "no_speech", "nobody said anything");
  console.log("test h (silence detector) OK");
}

function fakeMeter(levels) {
  const gauge = { closed: false, read: () => levels.shift() ?? 0.001, close() { gauge.closed = true; } };
  return { gauge, meter: () => gauge };
}

async function testTapRecordsUntilTheCookStopsTalking() {
  const levels = [...Array(6).fill(0.01), ...Array(10).fill(0.3), ...Array(40).fill(0.01)];
  const { gauge, meter } = fakeMeter(levels);
  const s = setup({ meter });
  await s.ptt.start();
  s.advance(100);
  await s.ptt.autoStop(); // released quickly: a tap
  s.timers.forEach((t) => { if (t.ms === MAX_MS) t.live = false; }); // runTimers ignores time - keep the 15 s cap out
  assert(s.ptt.isRecording(), "a tap keeps recording");
  for (let i = 0; i < 60 && s.ptt.isRecording(); i++) {
    s.advance(50);
    s.runTimers();
  }
  await tick();
  await tick();
  assert(!s.ptt.isRecording() && s.sent.length === 1, "stopped after the speech ended, and sent");
  assert(gauge.closed, "the level meter is released");
  console.log("test i (tap to talk stops on silence) OK");
}

async function testTapWithNothingSaidSendsNothing() {
  const { meter } = fakeMeter([]);
  const s = setup({ meter });
  await s.ptt.start();
  await s.ptt.autoStop();
  s.timers.forEach((t) => { if (t.ms === MAX_MS) t.live = false; }); // the no-speech path must end it, not the cap
  for (let i = 0; i < 200 && s.ptt.isRecording(); i++) {
    s.advance(50);
    s.runTimers();
  }
  await tick();
  assert(!s.ptt.isRecording() && s.sent.length === 0, "nothing sent");
  assert(s.results[0] === "no_speech", `told why: ${s.results}`);
  console.log("test j (a tap with nothing said) OK");
}

async function testCancelDiscards() {
  const s = setup();
  await s.ptt.start();
  s.advance(2000);
  s.ptt.cancel();
  await tick();
  assert(!s.ptt.isRecording() && s.sent.length === 0 && s.results.length === 0, "cancelled silently");
  console.log("test k (cancel discards) OK");
}

testSilenceDetector();
await testTapRecordsUntilTheCookStopsTalking();
await testTapWithNothingSaidSendsNothing();
await testCancelDiscards();

console.log("all passed");
