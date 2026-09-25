const TIMEOUT_MS = 25000; // above the worst observed real latency - lower silently aborts calls about to succeed.

export class HttpError extends Error {
  constructor(status, path) {
    super(`HTTP ${status} for ${path}`);
    this.name = "HttpError";
    this.status = status;
    this.path = path;
  }
}

async function requestJson(path, init = {}, timeoutMs = TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(path, { ...init, signal: controller.signal });
    if (!res.ok) {
      throw new HttpError(res.status, path);
    }
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

async function withOneRetry(fn) {
  try {
    return await fn();
  } catch (err) {
    // Never retry a timeout into a second full timeout - that's double the wait on a dead backend.
    if (err.name === "AbortError") {
      throw err;
    }
    // A 400 must never be sent twice.
    if (err instanceof HttpError && err.status < 500) {
      throw err;
    }
    return await fn();
  }
}

export function analyze(req) {
  return withOneRetry(() =>
    requestJson("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    })
  );
}

export const health = () => requestJson("/health", {}, 4000);
export const listRecipes = () => requestJson("/recipes");
export const getRecipe = (id) => requestJson("/recipes/" + encodeURIComponent(id));
export const getBarcode = (code) => requestJson("/barcode/" + encodeURIComponent(code));
export const referenceImageUrl = (id, step) => "/reference/" + encodeURIComponent(id) + "/" + step;
