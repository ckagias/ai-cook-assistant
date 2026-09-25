const W = 64;
const H = 48; // own canvas

const aimCanvas = document.createElement("canvas");
aimCanvas.width = W;
aimCanvas.height = H;
const aimCtx = aimCanvas.getContext("2d", { willReadFrequently: true });

function clamp01(v) {
  return Math.max(0, Math.min(1, v));
}

export function aimScore(video) {
  if (!video || !video.videoWidth) return { score: 0, reason: "no camera" };

  aimCtx.drawImage(video, 0, 0, W, H);
  const { data } = aimCtx.getImageData(0, 0, W, H);

  const n = W * H;
  const lumas = new Float64Array(n);
  let sum = 0;
  let centreSum = 0,
    centreN = 0;
  let edgeSum = 0,
    edgeN = 0;

  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const p = y * W + x;
      const i = p * 4;
      const luma = (0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]) / 255;
      lumas[p] = luma;
      sum += luma;

      const fx = x / W;
      const fy = y / H;
      if (fx >= 0.3 && fx < 0.7 && fy >= 0.3 && fy < 0.7) {
        centreSum += luma;
        centreN++;
      }
      if (fx < 0.2 || fx >= 0.8 || fy < 0.2 || fy >= 0.8) {
        edgeSum += luma;
        edgeN++;
      }
    }
  }

  const mean = sum / n;
  let varSum = 0;
  for (let p = 0; p < n; p++) {
    const d = lumas[p] - mean;
    varSum += d * d;
  }
  const variance = varSum / n;

  const centre = centreN ? centreSum / centreN : mean;
  const edge = edgeN ? edgeSum / edgeN : mean;

  const exposure = clamp01(1 - Math.abs(mean - 0.45) / 0.42); // peaks at mid-tone 0.45
  const detail = clamp01(Math.sqrt(variance) / 0.13); // flat frame = lens on pan or blank wall
  const subject = clamp01(Math.abs(centre - edge) / 0.1); // something distinct in the middle

  // MULTIPLIED, not averaged - any one term failing means the frame is
  // unusable; averaging would let good detail hide a black frame.
  const score = exposure * detail * (0.35 + 0.65 * subject);

  let reason;
  if (exposure < 0.4) {
    reason = mean < 0.45 ? "too dark" : "too bright";
  } else if (detail < 0.4) {
    reason = "no detail, move back";
  } else if (subject < 0.3) {
    reason = "nothing in the middle";
  } else {
    reason = "ok";
  }

  return { score: clamp01(score), reason, mean, variance, centre, edge };
}

export function createAimer({ video, audioCtx, isSpeaking, onScore }) {
  let ctx = audioCtx;
  let timer = null;
  let running = false;
  let best = 0;

  function pulse(score) {
    if (!ctx || ctx.state !== "running") return;

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 440 + 440 * score;
    osc.connect(gain);
    gain.connect(ctx.destination);

    const speaking = Boolean(isSpeaking && isSpeaking());
    // Ducks near-silent during speech but not to true silence.
    const peak = (speaking ? 0.03 : 0.16) * (0.4 + 0.6 * score);

    const now = ctx.currentTime;
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(peak, now + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.075);

    osc.start(now);
    osc.stop(now + 0.09);
  }

  function tick() {
    if (!running) return;
    const { score, reason } = aimScore(video);
    best = Math.max(best, score);
    if (onScore) onScore(score, reason);
    pulse(score);

    // Rescheduled every pulse so rate tracks the tablet moving live.
    const hz = 1.5 + 6.5 * score; // 1.5/s hopeless, 8/s framed
    timer = setTimeout(tick, 1000 / hz);
  }

  return {
    setAudioContext(newCtx) {
      ctx = newCtx;
    },
    start() {
      if (running) return;
      running = true;
      best = 0;
      tick();
    },
    stop() {
      running = false;
      clearTimeout(timer);
      timer = null;
    },
    isRunning: () => running,
    bestSeen: () => best,
  };
}

export const GOOD_ENOUGH = 0.45;

export function guideUntilFramed(aimer, video, maxMs = 3000) {
  return new Promise((resolve) => {
    const initial = aimScore(video);
    if (initial.score >= GOOD_ENOUGH) {
      resolve({ guided: false, score: initial.score });
      return;
    }

    aimer.start();
    const startedAt = Date.now();

    function poll() {
      const { score } = aimScore(video);
      const elapsed = Date.now() - startedAt;
      if (score >= GOOD_ENOUGH || elapsed >= maxMs) {
        aimer.stop();
        // Always resolves, never rejects - refusing to take a photo is worse
        // than taking a mediocre one; camera_feedback handles a bad shot.
        resolve({ guided: true, score, timedOut: score < GOOD_ENOUGH });
        return;
      }
      setTimeout(poll, 120);
    }

    setTimeout(poll, 120);
  });
}
