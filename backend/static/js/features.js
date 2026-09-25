const COLOR_W = 64;
const COLOR_H = 48;
const TEX_W = 128;
const TEX_H = 96;
const CLIP = 245; // R=G=B=255 is "no data" (blown highlight), not "white food"
const DARK = 12; // below the sRGB toe, ratios go unstable
const EPS = 1e-6;

// Two OWN canvases (not shared with capture.js or aim.js).
const colorCanvas = document.createElement("canvas");
colorCanvas.width = COLOR_W;
colorCanvas.height = COLOR_H;
const colorCtx = colorCanvas.getContext("2d");

const texCanvas = document.createElement("canvas");
texCanvas.width = TEX_W;
texCanvas.height = TEX_H;
const texCtx = texCanvas.getContext("2d");

let prevLuma = null;

function region(x, y, w, h) {
  const fx = x / w;
  const fy = y / h;
  if (fx >= 0.3 && fx < 0.7 && fy >= 0.3 && fy < 0.7) {
    return "centre";
  }
  if (fx < 0.25 || fx >= 0.75 || fy < 0.25 || fy >= 0.75) {
    return "annulus";
  }
  return null; // the ring between centre and annulus is deliberately ignored
}

export function resetFeatures() {
  prevLuma = null;
}

export function extractFeatures(video) {
  if (!video.videoWidth) return null;

  // --- colour, over COLOR_W x COLOR_H ---
  colorCtx.drawImage(video, 0, 0, COLOR_W, COLOR_H);
  const colorData = colorCtx.getImageData(0, 0, COLOR_W, COLOR_H).data;

  let cR = 0,
    cG = 0,
    cB = 0,
    cN = 0;
  let aR = 0,
    aG = 0,
    aB = 0,
    aN = 0;
  let cSat = 0;
  let cClip = 0,
    cTotal = 0;

  for (let y = 0; y < COLOR_H; y++) {
    for (let x = 0; x < COLOR_W; x++) {
      const reg = region(x, y, COLOR_W, COLOR_H);
      if (reg === null) continue;

      const i = (y * COLOR_W + x) * 4;
      const r = colorData[i];
      const g = colorData[i + 1];
      const b = colorData[i + 2];
      const maxc = Math.max(r, g, b);
      const minc = Math.min(r, g, b);

      if (reg === "centre") {
        cTotal++;
        if (maxc > CLIP) {
          cClip++;
          continue;
        }
        if (maxc < DARK) continue;
        cR += r;
        cG += g;
        cB += b;
        cN++;
        cSat += (maxc - minc) / (maxc + 1);
      } else {
        if (maxc > CLIP || maxc < DARK) continue;
        aR += r;
        aG += g;
        aB += b;
        aN++;
      }
    }
  }

  if (cN < 20 || aN < 20) return null;

  const Rc = cR / cN,
    Gc = cG / cN,
    Bc = cB / cN;
  const Ra = aR / aN,
    Ga = aG / aN,
    Ba = aB / aN;

  const annulusLuma = 0.299 * Ra + 0.587 * Ga + 0.114 * Ba;
  const referenceOk = annulusLuma > 25; // a matte-black hob carries no reference

  const Rn = Rc / (Ra + 1);
  const Gn = Gc / (Ga + 1);
  const Bn = Bc / (Ba + 1);

  const centreLuma = 0.299 * Rc + 0.587 * Gc + 0.114 * Bc;

  const features = {
    brownRB: (Rn - Bn) / (Rn + Bn + EPS), // monotonic pale -> golden -> brown; Yratio covers char (Rn≈Bn)
    brownRG: (Rn - Gn) / (Rn + Gn + EPS),
    Yratio: centreLuma / (annulusLuma + EPS),
    satC: cSat / cN,
    specC: cTotal ? cClip / cTotal : 0,
    referenceOk,
  };

  // --- texture + activity, over TEX_W x TEX_H ---
  texCtx.drawImage(video, 0, 0, TEX_W, TEX_H);
  const texData = texCtx.getImageData(0, 0, TEX_W, TEX_H).data;
  const n = TEX_W * TEX_H;
  const luma = new Float64Array(n);
  let sumY = 0;
  for (let p = 0; p < n; p++) {
    const i = p * 4;
    const y = 0.299 * texData[i] + 0.587 * texData[i + 1] + 0.114 * texData[i + 2];
    luma[p] = y;
    sumY += y;
  }
  const meanY = sumY / n;

  // Edge energy over the CENTRE only, measured on the downsample deliberately -
  // a 3px defocus blur at full res is sub-pixel here, so autofocus hunting
  // doesn't read as bubbles.
  let eSum = 0,
    eCount = 0;
  for (let y = 0; y < TEX_H; y++) {
    for (let x = 0; x < TEX_W; x++) {
      if (region(x, y, TEX_W, TEX_H) !== "centre") continue;
      if (x + 1 >= TEX_W || y + 1 >= TEX_H) continue;
      const p = y * TEX_W + x;
      const dx = luma[p] - luma[p + 1];
      const dy = luma[p] - luma[p + TEX_W];
      eSum += dx * dx + dy * dy;
      eCount++;
    }
  }
  features.E = eCount ? eSum / eCount / (meanY * meanY + EPS) : 0;

  if (!prevLuma) {
    prevLuma = luma;
    return null; // needs 2 frames
  }

  const diff = new Float64Array(n);
  let diffSum = 0;
  for (let p = 0; p < n; p++) {
    diff[p] = luma[p] - prevLuma[p];
    diffSum += diff[p];
  }
  const dMean = diffSum / n; // subtract exactly this so a uniform AE brightness step isn't read as boiling

  let centreAbsSum = 0,
    centreCount = 0;
  let annulusAbsSum = 0,
    annulusCount = 0;
  for (let y = 0; y < TEX_H; y++) {
    for (let x = 0; x < TEX_W; x++) {
      const reg = region(x, y, TEX_W, TEX_H);
      if (reg === null) continue;
      const p = y * TEX_W + x;
      const val = Math.abs(diff[p] - dMean);
      if (reg === "centre") {
        centreAbsSum += val;
        centreCount++;
      } else {
        annulusAbsSum += val;
        annulusCount++;
      }
    }
  }

  const Acentre = centreCount ? centreAbsSum / centreCount / (meanY + EPS) : 0;
  const Aannulus = annulusCount ? annulusAbsSum / annulusCount / (meanY + EPS) : 0;

  features.Acentre = Acentre;
  features.Aannulus = Aannulus; // consumed by monitor.js's motion veto, not itself sigma-tracked
  // Separates "food is doing something" from "someone nudged the pan/tablet" (which churns both regions equally).
  features.boil = Acentre - Aannulus;
  features.veiled = features.Yratio > 1.4 && features.satC < 0.12 && features.E < 0.005; // steam signature

  prevLuma = luma;
  return features;
}

export const TRACKED = ["brownRB", "brownRG", "Yratio", "satC", "specC", "E", "Acentre", "boil"];
