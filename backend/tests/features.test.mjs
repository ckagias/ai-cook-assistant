// Shims document.createElement("canvas") to return a fake context whose
// getImageData returns a synthetically painted buffer matching the region
// geometry in features.js (centre box, annulus, ignored ring). No npm
// dependency - pixels are painted directly into a Uint8ClampedArray.

const COLOR_W = 64;
const COLOR_H = 48;
const TEX_W = 128;
const TEX_H = 96;

function regionOf(x, y, w, h) {
  const fx = x / w;
  const fy = y / h;
  if (fx >= 0.3 && fx < 0.7 && fy >= 0.3 && fy < 0.7) return "centre";
  if (fx < 0.25 || fx >= 0.75 || fy < 0.25 || fy >= 0.75) return "annulus";
  return "ring";
}

let scene = {
  colorPaint: () => [128, 128, 128],
  texPaint: () => 128,
};

function setScene(next) {
  scene = { ...scene, ...next };
}

function makeFakeCanvas() {
  const canvas = { width: 0, height: 0 };
  canvas.getContext = () => ({
    drawImage() {}, // no-op: pixels come from `scene`, not a real decoded video frame
    getImageData(x, y, w, h) {
      const data = new Uint8ClampedArray(w * h * 4);
      const isColor = w === COLOR_W && h === COLOR_H;
      for (let yy = 0; yy < h; yy++) {
        for (let xx = 0; xx < w; xx++) {
          const reg = regionOf(xx, yy, w, h);
          const i = (yy * w + xx) * 4;
          if (isColor) {
            const [r, g, b] = scene.colorPaint(xx, yy, w, h, reg);
            data[i] = r;
            data[i + 1] = g;
            data[i + 2] = b;
          } else {
            const lum = scene.texPaint(xx, yy, w, h, reg);
            data[i] = lum;
            data[i + 1] = lum;
            data[i + 2] = lum;
          }
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

const features = await import("../static/js/features.js");

const FAKE_VIDEO = { videoWidth: 100, videoHeight: 100 };
const NEUTRAL_ANNULUS = [90, 90, 90];
const CONST_TEX = () => 130;

function clampChannel(v) {
  return Math.max(0, Math.min(255, Math.round(v)));
}

function gainColor([r, g, b], gR, gG = gR, gB = gR) {
  return [clampChannel(r * gR), clampChannel(g * gG), clampChannel(b * gB)];
}

// Returns a stable features object for a given (centre, annulus) colour pair.
// The first extractFeatures() call after a reset always returns null (needs
// two frames), so this primes prevLuma with a constant texture frame and
// returns the second call's result.
function featuresForScene(centreColor, annulusColor = NEUTRAL_ANNULUS) {
  features.resetFeatures();
  setScene({
    colorPaint: (x, y, w, h, reg) => (reg === "centre" ? centreColor : annulusColor),
    texPaint: CONST_TEX,
  });
  features.extractFeatures(FAKE_VIDEO);
  const result = features.extractFeatures(FAKE_VIDEO);
  if (result === null) throw new Error("expected a non-null features object on the second call");
  return result;
}

function assert(cond, message) {
  if (!cond) throw new Error(message);
}

// A representative golden/tan food colour against a neutral hob/counter background.
const BASE_CENTRE = [140, 110, 70];
const baseline = featuresForScene(BASE_CENTRE);
console.log("baseline brownRB:", baseline.brownRB.toFixed(4));

let worstArtefactDrift = 0;

// --- a) brownRB drift < 0.01 under simulated +40%/-30% uniform per-channel AE gain ---
{
  for (const gain of [1.4, 0.7]) {
    const centre = gainColor(BASE_CENTRE, gain);
    const annulus = gainColor(NEUTRAL_ANNULUS, gain);
    const f = featuresForScene(centre, annulus);
    const drift = Math.abs(f.brownRB - baseline.brownRB);
    worstArtefactDrift = Math.max(worstArtefactDrift, drift);
    assert(drift < 0.01, `AE gain ${gain}: expected drift < 0.01, got ${drift}`);
    console.log(`test a (AE gain ${gain}x) OK, drift=${drift.toFixed(5)}`);
  }
}

// --- b) brownRB drift < 0.02 under a warm/cool white-balance shift (asymmetric per-channel gains) ---
{
  const shifts = [
    { name: "warm", g: [1.2, 1.0, 0.85] },
    { name: "cool", g: [0.85, 1.0, 1.2] },
  ];
  for (const { name, g } of shifts) {
    const centre = gainColor(BASE_CENTRE, ...g);
    const annulus = gainColor(NEUTRAL_ANNULUS, ...g);
    const f = featuresForScene(centre, annulus);
    const drift = Math.abs(f.brownRB - baseline.brownRB);
    worstArtefactDrift = Math.max(worstArtefactDrift, drift);
    assert(drift < 0.02, `${name} WB shift: expected drift < 0.02, got ${drift}`);
    console.log(`test b (${name} white balance) OK, drift=${drift.toFixed(5)}`);
  }
}

// --- c) brownRB rises by > 0.15 when the centre colour actually shifts pale -> golden-brown ---
const PALE_CENTRE = [200, 195, 185];
const BROWN_CENTRE = [140, 90, 40];
let browningDelta;
{
  const pale = featuresForScene(PALE_CENTRE);
  const brown = featuresForScene(BROWN_CENTRE);
  browningDelta = brown.brownRB - pale.brownRB;
  assert(browningDelta > 0.15, `expected browning to raise brownRB by >0.15, got ${browningDelta}`);
  console.log(`test c (pale -> golden-brown) OK, delta=${browningDelta.toFixed(4)}`);
}

// --- d) that signal is > 20x the worst artefact drift measured above ---
{
  const ratio = browningDelta / worstArtefactDrift;
  assert(ratio > 20, `expected browning signal to be >20x worst artefact drift, got ${ratio}x`);
  console.log(`test d (signal/drift ratio) OK, ratio=${ratio.toFixed(1)}x`);
}

// --- e) browning plus simultaneous AE compensation still reads within 0.02 of browning alone ---
{
  const brownAlone = featuresForScene(BROWN_CENTRE);
  const brownWithAE = featuresForScene(gainColor(BROWN_CENTRE, 1.3), gainColor(NEUTRAL_ANNULUS, 1.3));
  const diff = Math.abs(brownWithAE.brownRB - brownAlone.brownRB);
  assert(diff < 0.02, `expected browning+AE to read within 0.02 of browning alone, got ${diff}`);
  console.log(`test e (browning + simultaneous AE) OK, diff=${diff.toFixed(5)}`);
}

// --- f) a near-black annulus (luma ~18) flags referenceOk === false ---
{
  const nearBlackAnnulus = [18, 18, 18]; // luma = 18*(0.299+0.587+0.114) = 18
  const f = featuresForScene([120, 100, 80], nearBlackAnnulus);
  assert(f.referenceOk === false, `expected referenceOk === false for a near-black annulus, got ${f.referenceOk}`);
  console.log("test f (near-black annulus -> referenceOk false) OK");

  const litAnnulus = [90, 90, 90];
  const f2 = featuresForScene([120, 100, 80], litAnnulus);
  assert(f2.referenceOk === true, `expected referenceOk === true for a normally-lit annulus, got ${f2.referenceOk}`);
  console.log("test f (normally-lit annulus -> referenceOk true) OK");
}

// --- g) adding per-pixel jitter between two consecutive frames raises Acentre above a small floor ---
{
  features.resetFeatures();
  setScene({
    colorPaint: (x, y, w, h, reg) => (reg === "centre" ? [120, 100, 80] : NEUTRAL_ANNULUS),
    texPaint: () => 130,
  });
  features.extractFeatures(FAKE_VIDEO); // primes prevLuma, returns null
  const still = features.extractFeatures(FAKE_VIDEO); // identical second frame -> ~no activity
  assert(still.Acentre < 0.001, `expected near-zero Acentre with no jitter, got ${still.Acentre}`);
  console.log("test g (no jitter -> near-zero Acentre) OK, Acentre=" + still.Acentre.toFixed(6));

  features.resetFeatures();
  setScene({
    colorPaint: (x, y, w, h, reg) => (reg === "centre" ? [120, 100, 80] : NEUTRAL_ANNULUS),
    texPaint: () => 130,
  });
  features.extractFeatures(FAKE_VIDEO); // primes prevLuma with the stable frame
  setScene({
    colorPaint: (x, y, w, h, reg) => (reg === "centre" ? [120, 100, 80] : NEUTRAL_ANNULUS),
    texPaint: (x, y) => 130 + (((x * 7 + y * 13) % 11) - 5), // deterministic per-pixel jitter, [-5, 5]
  });
  const jittered = features.extractFeatures(FAKE_VIDEO);
  assert(jittered.Acentre > 0.001, `expected jitter to raise Acentre above a small floor, got ${jittered.Acentre}`);
  console.log("test g (jitter raises Acentre) OK, Acentre=" + jittered.Acentre.toFixed(6));
}

console.log("all passed");
