const MAX_EDGE = 1024;
const QUALITY = 0.8;

const uploadCanvas = document.createElement("canvas"); // resized every call
const probeCanvas = document.createElement("canvas"); // hoisted, reused

export function captureFrame(video) {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) {
    throw new Error("camera not ready");
  }

  const scale = Math.min(1, MAX_EDGE / Math.max(vw, vh));
  const w = Math.round(vw * scale);
  const h = Math.round(vh * scale);

  uploadCanvas.width = w;
  uploadCanvas.height = h;
  const ctx = uploadCanvas.getContext("2d");
  ctx.drawImage(video, 0, 0, w, h);

  // Strip the "data:image/jpeg;base64," prefix - the backend calls
  // base64.standard_b64decode and 400s on it if left in.
  return uploadCanvas.toDataURL("image/jpeg", QUALITY).split(",")[1];
}

export function frameQuality(video) {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) return null;

  const w = 64;
  const h = Math.max(1, Math.round((vh / vw) * w));

  probeCanvas.width = w;
  probeCanvas.height = h;
  const ctx = probeCanvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(video, 0, 0, w, h);

  const { data } = ctx.getImageData(0, 0, w, h);
  const n = w * h;
  const lumas = new Float64Array(n);
  let sum = 0;
  for (let i = 0; i < n; i++) {
    const luma = 0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2];
    lumas[i] = luma;
    sum += luma;
  }
  const mean = sum / n;

  let variance = 0;
  for (let i = 0; i < n; i++) {
    const d = lumas[i] - mean;
    variance += d * d;
  }
  variance /= n;

  return { mean, variance };
}
