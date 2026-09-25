// Shims document.createElement("canvas") the same way features.test.mjs does:
// getImageData returns a synthetically painted buffer matching aim.js's own
// region geometry (inner-40% centre box, outer-20% edge ring).

const W = 64;
const H = 48;

function regionOf(x, y, w, h) {
  const fx = x / w;
  const fy = y / h;
  if (fx >= 0.3 && fx < 0.7 && fy >= 0.3 && fy < 0.7) return "centre";
  if (fx < 0.2 || fx >= 0.8 || fy < 0.2 || fy >= 0.8) return "edge";
  return "mid";
}

function clampByte(v) {
  return Math.max(0, Math.min(255, Math.round(v)));
}

let paint = () => 128;
function setPaint(fn) {
  paint = fn;
}

function makeFakeCanvas() {
  const canvas = { width: 0, height: 0 };
  canvas.getContext = () => ({
    drawImage() {},
    getImageData(x, y, w, h) {
      const data = new Uint8ClampedArray(w * h * 4);
      for (let yy = 0; yy < h; yy++) {
        for (let xx = 0; xx < w; xx++) {
          const reg = regionOf(xx, yy, w, h);
          const lum = clampByte(paint(xx, yy, w, h, reg));
          const i = (yy * w + xx) * 4;
          data[i] = lum;
          data[i + 1] = lum;
          data[i + 2] = lum;
          data[i + 3] = 255;
        }
      }
      return { data, width: w, height: h };
    },
  });
  return canvas;
}

globalThis.document = {
  createElement: (tag) => {
    if (tag === "canvas") return makeFakeCanvas();
    throw new Error("unsupported tag: " + tag);
  },
};

const aim = await import("../static/js/aim.js");

const FAKE_VIDEO = { videoWidth: 100, videoHeight: 100 };

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

function withPaint(fn, video = FAKE_VIDEO) {
  setPaint(fn);
  return aim.aimScore(video);
}

// --- a uniform near-black frame scores <0.1 and reports "too dark" ---
{
  const r = withPaint(() => 8);
  assert(r.score < 0.1, `expected score <0.1, got ${r.score}`);
  assert(r.reason === "too dark", `expected "too dark", got "${r.reason}"`);
  console.log("test 1 (near-black -> too dark) OK, score=" + r.score.toFixed(4));
}

// --- a uniform near-white frame scores <0.1 and reports "too bright" ---
{
  const r = withPaint(() => 250);
  assert(r.score < 0.1, `expected score <0.1, got ${r.score}`);
  assert(r.reason === "too bright", `expected "too bright", got "${r.reason}"`);
  console.log("test 2 (near-white -> too bright) OK, score=" + r.score.toFixed(4));
}

// --- a uniform mid-grey speckle-free frame scores <0.1 and reports "no detail, move back" ---
{
  const r = withPaint(() => 115); // ~0.45 normalized, dead-centre exposure
  assert(r.score < 0.1, `expected score <0.1, got ${r.score}`);
  assert(r.reason === "no detail, move back", `expected "no detail, move back", got "${r.reason}"`);
  console.log("test 3 (uniform mid-grey -> no detail) OK, score=" + r.score.toFixed(4));
}

function speckle(x, y, amplitude) {
  return ((((x * 13 + y * 7) % 23) / 22) * 2 - 1) * amplitude;
}

// A centred, lit, speckled subject against a darker speckled background,
// tuned so the whole-frame mean lands near the 0.45 mid-tone sweet spot.
function goodScene(x, y, w, h, reg) {
  if (reg === "centre") return 195 + speckle(x, y, 45);
  if (reg === "edge") return 55 + speckle(x, y, 30);
  return 120 + speckle(x, y, 25);
}

// --- a centred, lit, speckled subject against a darker speckled background scores >=GOOD_ENOUGH and reports "ok" ---
{
  const r = withPaint(goodScene);
  assert(r.score >= aim.GOOD_ENOUGH, `expected score >=${aim.GOOD_ENOUGH}, got ${r.score}`);
  assert(r.reason === "ok", `expected "ok", got "${r.reason}"`);
  console.log("test 4 (well-framed speckled subject -> ok) OK, score=" + r.score.toFixed(4));
}

// --- the identical scene under-exposed scores strictly lower ---
{
  const wellExposed = withPaint(goodScene);
  const underExposed = withPaint((x, y, w, h, reg) => goodScene(x, y, w, h, reg) * 0.35);
  assert(
    underExposed.score < wellExposed.score,
    `expected under-exposed score (${underExposed.score}) < well-exposed score (${wellExposed.score})`
  );
  console.log(
    `test 5 (under-exposed scores lower) OK, well=${wellExposed.score.toFixed(4)} under=${underExposed.score.toFixed(4)}`
  );
}

// --- aimScore handles {videoWidth:0} and null without throwing ---
{
  const r1 = aim.aimScore({ videoWidth: 0 });
  assert(r1.score === 0 && r1.reason === "no camera", `expected {score:0, reason:"no camera"}, got ${JSON.stringify(r1)}`);

  const r2 = aim.aimScore(null);
  assert(r2.score === 0 && r2.reason === "no camera", `expected {score:0, reason:"no camera"}, got ${JSON.stringify(r2)}`);
  console.log("test 6 (handles videoWidth:0 and null without throwing) OK");
}

// --- createAimer(...).start() with audioCtx: null runs without throwing, isRunning() reflects start/stop ---
{
  setPaint(() => 128);
  const scores = [];
  const aimer = aim.createAimer({
    video: FAKE_VIDEO,
    audioCtx: null,
    isSpeaking: () => false,
    onScore: (score, reason) => scores.push([score, reason]),
  });

  assert(aimer.isRunning() === false, "expected isRunning() false before start()");
  aimer.start();
  assert(aimer.isRunning() === true, "expected isRunning() true after start()");
  assert(scores.length === 1, `expected one synchronous onScore call from start(), got ${scores.length}`);
  aimer.stop();
  assert(aimer.isRunning() === false, "expected isRunning() false after stop()");
  console.log("test 7 (createAimer with audioCtx:null, start/stop) OK");
}

console.log("all passed");
process.exit(0);
