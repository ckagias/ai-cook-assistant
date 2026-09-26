// Exercises voice.js's push-to-talk state machine against a fake MediaRecorder: hold/release,
// an accidental tap, releasing before the microphone is ready, the 15 s cap, and no second
// recording while the first is still being understood.

const { createPushToTalk, pickMimeType, MIN_MS, MAX_MS } = await import("../static/js/voice.js");

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

function setup({ send, getStream } = {}) {
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

console.log("all passed");
