// Exercises detect.js: the object-fit:cover coordinate mapping, colour assignment, table rows,
// and the one-request-in-flight loop - against fake canvas/table/api objects, no real DOM.

function fakeCtx() {
  return {
    calls: [],
    setTransform() {},
    clearRect() {},
    strokeRect(...a) { this.calls.push(["strokeRect", ...a]); },
    fillRect() {},
    fillText() {},
    measureText: (s) => ({ width: s.length * 7 }),
    beginPath() {}, arc() {}, fill() {}, moveTo() {}, lineTo() {}, stroke() {}, setLineDash() {},
  };
}

function fakeElement(tag) {
  return {
    tag,
    children: [],
    style: {},
    textContent: "",
    appendChild(c) { this.children.push(c); return c; },
    replaceChildren(...c) { this.children = c; },
  };
}

globalThis.document = {
  hidden: false,
  createElement: (tag) => {
    if (tag === "canvas") return { getContext: () => fakeCtx(), toBlob() {} };
    return fakeElement(tag);
  },
};
globalThis.localStorage = { getItem: () => null, setItem() {} };

const detect = await import("../static/js/detect.js");

function assert(cond, message) {
  if (!cond) throw new Error("assertion failed: " + message);
}

const near = (a, b) => Math.abs(a - b) < 1e-6;

function testCoverTransformCropsWiderVideo() {
  // 1280x720 video in a 400x400 element: scaled to height (s = 400/720), sides cropped.
  const tr = detect.coverTransform(400, 400, 1280, 720);
  assert(near(tr.s, 400 / 720), `scale ${tr.s}`);
  assert(tr.dx < 0 && near(tr.dy, 0), `offsets ${tr.dx},${tr.dy}`);
  // The frame centre must land on the element centre, whatever the crop.
  const p = detect.toViewPoint({ x: 0.5, y: 0.5 }, tr);
  assert(near(p.x, 200) && near(p.y, 200), `centre mapped to ${p.x},${p.y}`);
  // A full-frame box spans wider than the element (the cropped parts are off-screen).
  const r = detect.toViewRect({ x1: 0, y1: 0, x2: 1, y2: 1 }, tr);
  assert(r.w > 400 && near(r.h, 400), `full box ${r.w}x${r.h}`);
  console.log("test a (object-fit: cover mapping) OK");
}

function testColoursStablePerClassAndDistinctPerGroup() {
  const a = detect.classColor("utensil", "knife");
  assert(a === detect.classColor("utensil", "knife"), "same class, same colour");
  assert(/^#[0-9a-f]{6}$/.test(a), `hex colour, got ${a}`);
  assert(detect.classColor("hand", "hand0") !== detect.classColor("ingredient", "hand0"), "groups differ");
  console.log("test b (colour stability) OK");
}

const RESULT = {
  model: "fake",
  width: 640,
  height: 480,
  latency_ms: { decode: 1, detect: 2, hands: 3, total: 6 },
  detections: [{
    class_id: "knife", label_en: "knife", label_el: "μαχαίρι", group: "utensil", hazard: true,
    confidence: 0.87, box: { x1: 0.1, y1: 0.2, x2: 0.3, y2: 0.4 }, center: { x: 0.2, y: 0.3 },
  }],
  hands: [{ handedness: "Right", confidence: 0.95, box: { x1: 0.25, y1: 0.25, x2: 0.5, y2: 0.6 }, fingertips: [{ x: 0.28, y: 0.3 }] }],
  relations: [{ hand: 0, object: 0, kind: "touching", distance: 0 }],
};

function testRowsCarryPixelCentresAndRelations() {
  const rows = detect.buildRows(RESULT, "en");
  assert(rows.length === 2, `hand + knife rows, got ${rows.length}`);
  assert(rows[0].label === "Right hand", `hand row first, got ${rows[0].label}`);
  const knife = rows[1];
  assert(knife.confidence === 87, `confidence % ${knife.confidence}`);
  assert(knife.x === 128 && knife.y === 144, `pixel centre ${knife.x},${knife.y}`);
  assert(knife.w === 128 && knife.h === 96, `pixel size ${knife.w}x${knife.h}`);
  assert(knife.relation === "Right hand: touching", `relation text "${knife.relation}"`);
  const el = detect.buildRows(RESULT, "el");
  assert(el[1].label === "μαχαίρι" && el[1].relation === "Δεξί χέρι: ακουμπά", `greek row ${JSON.stringify(el[1])}`);
  console.log("test c (table rows) OK");
}

async function testLoopKeepsOneRequestInFlight() {
  const canvas = { width: 0, height: 0, getContext: () => fakeCtx(), getBoundingClientRect: () => ({ width: 400, height: 300 }) };
  const table = fakeElement("table");
  table.ownerDocument = globalThis.document;
  const stats = { textContent: "" };
  const pending = [];
  let concurrent = 0;
  let maxConcurrent = 0;
  const scheduled = [];
  const api = {
    detectFrame: () => {
      concurrent++;
      maxConcurrent = Math.max(maxConcurrent, concurrent);
      return new Promise((resolve) => pending.push(() => { concurrent--; resolve(RESULT); }));
    },
  };
  let clock = 0;
  const d = detect.createDetector({
    video: { videoWidth: 640, videoHeight: 480 },
    canvas, table, stats,
    getLang: () => "en",
    capture: async () => ({ blob: "jpeg", width: 640, height: 480 }),
    api,
    schedule: (fn) => { scheduled.push(fn); return scheduled.length; },
    cancel: () => {},
    now: () => (clock += 100),
  });

  d.start();
  d.start(); // idempotent
  await new Promise((r) => setTimeout(r, 0));
  assert(pending.length === 1, `one request after start, got ${pending.length}`);
  assert(scheduled.length === 0, "nothing scheduled while the request is in flight");

  pending.shift()();
  await new Promise((r) => setTimeout(r, 0));
  assert(scheduled.length === 1, `next frame scheduled only after the reply, got ${scheduled.length}`);
  assert(table.children.length === 2, "table rendered (thead + tbody)");
  assert(stats.textContent.includes("FPS") || stats.textContent === "", `stats text "${stats.textContent}"`);

  scheduled.shift()();
  await new Promise((r) => setTimeout(r, 0));
  assert(pending.length === 1 && maxConcurrent === 1, `never more than one in flight (max ${maxConcurrent})`);

  d.stop();
  pending.shift()();
  await new Promise((r) => setTimeout(r, 0));
  assert(scheduled.length === 0, "a reply arriving after stop() schedules nothing");
  assert(table.children.length === 0, "stop() clears the table");
  console.log("test d (one request in flight, stop is clean) OK");
}

async function testErrorsBackOff() {
  const delays = [];
  const d = detect.createDetector({
    video: { videoWidth: 640, videoHeight: 480 },
    canvas: { getContext: () => fakeCtx(), getBoundingClientRect: () => ({ width: 1, height: 1 }) },
    table: Object.assign(fakeElement("table"), { ownerDocument: globalThis.document }),
    stats: { textContent: "" },
    capture: async () => ({ blob: "jpeg" }),
    api: { detectFrame: async () => { throw new Error("503"); } },
    schedule: (fn, ms) => { delays.push(ms); return 1; },
    cancel: () => {},
  });
  d.start();
  await new Promise((r) => setTimeout(r, 0));
  assert(delays[0] === 250, `first retry after 250ms, got ${delays[0]}`);
  d.stop();
  console.log("test e (errors back off) OK");
}


async function testWarmingUpShowsLoadingAndRetriesWithoutBackoff() {
  const delays = [];
  const stats = { textContent: "" };
  const warming = Object.assign(new Error("HTTP 503"), { status: 503, detail: "warming up - the detection model is loading" });
  const d = detect.createDetector({
    video: { videoWidth: 640, videoHeight: 480 },
    canvas: { getContext: () => fakeCtx(), getBoundingClientRect: () => ({ width: 1, height: 1 }) },
    table: Object.assign(fakeElement("table"), { ownerDocument: globalThis.document }),
    stats,
    getLang: () => "en",
    capture: async () => ({ blob: "jpeg" }),
    api: { detectFrame: async () => { throw warming; } },
    schedule: (fn, ms) => { delays.push(ms); return 1; },
    cancel: () => {},
  });
  d.start();
  await new Promise((r) => setTimeout(r, 0));
  assert(delays[0] === 1000, `retry after 1 s while loading, got ${delays[0]}`);
  assert(stats.textContent.startsWith("Loading"), `loading message, got "${stats.textContent}"`);
  assert(detect.errorReason({ status: 401 }) === "not_paired", "401 -> not paired");
  assert(detect.errorReason(new TypeError("Failed to fetch")) === "network_trouble", "fetch failure -> network");
  d.stop();
  console.log("test f (warming up: loading message, no backoff) OK");
}

testCoverTransformCropsWiderVideo();
testColoursStablePerClassAndDistinctPerGroup();
testRowsCarryPixelCentresAndRelations();
await testLoopKeepsOneRequestInFlight();
await testErrorsBackOff();
await testWarmingUpShowsLoadingAndRetriesWithoutBackoff();

console.log("all passed");
