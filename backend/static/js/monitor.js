import { extractFeatures, resetFeatures, TRACKED } from "./features.js";

const FPS = 2;
const CALIBRATE_MS = 3000;
const K = 3.5;
const HYSTERESIS = [5, 6]; // [fire threshold, vote window size]
const REBASE_Z = 9;
const MOTION_Z = 4;
const MAX_ERRORS = 3;

// A perfectly still scene gives sigma ~ 0, which would fire on quantization
// noise alone - every tracked feature needs a floor below which sigma isn't trusted.
const FLOORS = {
  brownRB: 0.012,
  brownRG: 0.012,
  Yratio: 0.02,
  satC: 0.012,
  specC: 0.012,
  E: 0.0006,
  Acentre: 0.002,
  boil: 0.002,
};

function stats(rows, key) {
  const n = rows.length;
  const mean = rows.reduce((sum, r) => sum + r[key], 0) / n;
  const variance = rows.reduce((sum, r) => sum + (r[key] - mean) ** 2, 0) / n;
  return { mean, sd: Math.sqrt(variance) };
}

export function createMonitor({ video, onChange, onTick, onDisabled }) {
  let phase = "idle";
  let calStart = 0;
  let calRows = [];
  let baseline = null;
  let sampleWindow = [];
  let votes = [];
  let errors = 0;
  let lastFired = 0;
  let timer = null;

  function reset() {
    phase = "calibrating";
    calStart = Date.now();
    calRows = [];
    baseline = null;
    sampleWindow = [];
    votes = [];
    resetFeatures();
  }

  function setBaseline(rows) {
    baseline = {};
    for (const key of TRACKED) {
      baseline[key] = stats(rows, key);
    }
    phase = "watching";
    votes = [];
  }

  function z(row, key) {
    const floor = FLOORS[key] ?? 0.01;
    return Math.abs(row[key] - baseline[key].mean) / Math.max(baseline[key].sd, floor);
  }

  function tick() {
    let row;
    try {
      row = extractFeatures(video);
    } catch (err) {
      errors++;
      if (errors >= MAX_ERRORS) {
        stop();
        onDisabled?.(err);
      }
      return;
    }
    errors = 0;

    if (row === null) return;
    if (row.veiled) return;

    if (phase === "calibrating") {
      calRows.push(row);
      const elapsed = Date.now() - calStart;
      onTick?.({ phase, progress: Math.min(1, elapsed / CALIBRATE_MS) });
      if (elapsed >= CALIBRATE_MS && calRows.length >= 4) {
        setBaseline(calRows);
      }
      return;
    }

    if (phase === "watching") {
      const [FIRE_THRESHOLD, VOTE_WINDOW] = HYSTERESIS;

      // Hand/spatula/tablet-knock: the whole frame churns, not just the food.
      const moving =
        z(row, "Acentre") > MOTION_Z &&
        row.Aannulus > baseline.Acentre.mean + MOTION_Z * Math.max(baseline.Acentre.sd, FLOORS.Acentre);
      if (moving) {
        onTick?.({ moving: true });
        return;
      }

      sampleWindow.push(row);
      if (sampleWindow.length > VOTE_WINDOW) sampleWindow.shift();

      let maxZ = 0;
      for (const key of TRACKED) {
        maxZ = Math.max(maxZ, z(row, key));
      }

      // A huge jump that then sits still at a new level is a scene change, not doneness -
      // ingredient added, pan moved, flip happened. Without this a flip reads as instant doneness.
      if (maxZ > REBASE_Z && sampleWindow.length === VOTE_WINDOW) {
        const settled = TRACKED.every((key) => {
          const sd = stats(sampleWindow, key).sd;
          return sd <= Math.max(FLOORS[key], baseline[key].sd * 2);
        });
        if (settled) {
          setBaseline(sampleWindow);
          onTick?.({ rebaselined: true });
          return;
        }
      }

      const changed = ["brownRB", "Yratio", "boil", "E"].some((key) => z(row, key) > K);
      votes.push(changed);
      if (votes.length > VOTE_WINDOW) votes.shift();
      const agree = votes.filter(Boolean).length;

      onTick?.(row, { phase, maxZ, agree, changed });

      const now = Date.now();
      if (votes.length === VOTE_WINDOW && agree >= FIRE_THRESHOLD && now - lastFired > 20000) {
        lastFired = now;
        votes = [];

        let driver = TRACKED[0];
        let driverZ = z(row, driver);
        for (const key of TRACKED) {
          const zk = z(row, key);
          if (zk > driverZ) {
            driver = key;
            driverZ = zk;
          }
        }
        onChange?.({ driver, z: driverZ, row });
      }
    }
  }

  function start() {
    stop();
    errors = 0;
    reset();
    timer = setInterval(tick, 1000 / FPS);
  }

  function stop() {
    clearInterval(timer);
    timer = null;
    phase = "idle";
  }

  return {
    start,
    stop,
    isRunning: () => timer !== null,
    getPhase: () => phase,
  };
}
