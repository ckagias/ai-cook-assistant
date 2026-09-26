const TIMEOUT_MS = 25000; // above the worst observed real latency - lower silently aborts calls about to succeed.
const PAIRING_TOKEN_KEY = "pairingToken";

export class HttpError extends Error {
  constructor(status, path, detail = "") {
    super(`HTTP ${status} for ${path}${detail ? ": " + detail : ""}`);
    this.name = "HttpError";
    this.status = status;
    this.path = path;
    this.detail = detail; // the server's reason, e.g. "warming up - the detection model is loading"
  }
}

export function setPairingToken(token) {
  try {
    localStorage.setItem(PAIRING_TOKEN_KEY, token);
  } catch {
    // Private browsing / disabled storage - the token just won't persist across reloads.
  }
}

function getPairingToken() {
  try {
    return localStorage.getItem(PAIRING_TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

async function requestJson(path, init = {}, timeoutMs = TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    // Sent on every call whether a token is set or not - an empty header is harmless
    // when the backend has BACKEND_PAIRING_TOKEN unset.
    const headers = { ...(init.headers || {}), "X-Pairing-Token": getPairingToken() };
    const res = await fetch(path, { ...init, headers, signal: controller.signal });
    if (!res.ok) {
      let detail = "";
      try {
        detail = (await res.json()).detail || "";
      } catch {
        // not JSON - the status alone will do
      }
      throw new HttpError(res.status, path, typeof detail === "string" ? detail : "");
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

// Live preview frames: short timeout and never retried - the next frame is a better retry.
export function detectFrame(blob, recipeId) {
  const query = recipeId ? "?recipe_id=" + encodeURIComponent(recipeId) : "";
  return requestJson(
    "/detect" + query,
    { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: blob },
    3000
  );
}

// Push-to-talk: the recording plus what the server needs to understand it. Never retried -
// a second transcription of the same audio would just cost twice.
export function voiceCommand(blob, mimeType, ctx = {}) {
  const params = new URLSearchParams({ language: ctx.language || "el" });
  if (ctx.recipeId) params.set("recipe_id", ctx.recipeId);
  if (ctx.stepIndex !== undefined && ctx.stepIndex !== null) params.set("step_index", String(ctx.stepIndex));
  if (ctx.candidates && ctx.candidates.length) params.set("candidates", ctx.candidates.join(","));
  if (ctx.pending) params.set("pending", ctx.pending);
  if (ctx.doneness) params.set("doneness", ctx.doneness);
  if (ctx.timerRemainingSec !== undefined && ctx.timerRemainingSec !== null) {
    params.set("timer_remaining_sec", String(ctx.timerRemainingSec));
  }
  return requestJson(
    "/voice?" + params.toString(),
    { method: "POST", headers: { "Content-Type": mimeType || "audio/webm" }, body: blob },
    30000
  );
}

// Words the browser recognized (hands-free / talk button) or the cook typed. Same context as
// voiceCommand; never retried - a second call would just answer the same words twice.
export function voiceText(text, ctx = {}) {
  const body = { text, language: ctx.language || "el", candidates: (ctx.candidates || []).slice(0, 5) };
  if (ctx.recipeId) body.recipe_id = ctx.recipeId;
  if (ctx.stepIndex !== undefined && ctx.stepIndex !== null) body.step_index = ctx.stepIndex;
  if (ctx.pending) body.pending = ctx.pending;
  if (ctx.doneness) body.doneness = ctx.doneness;
  if (ctx.timerRemainingSec !== undefined && ctx.timerRemainingSec !== null) body.timer_remaining_sec = ctx.timerRemainingSec;
  if (ctx.memory) body.memory = String(ctx.memory).slice(0, 2000); // the recipe so far (memory.js)
  return requestJson(
    "/voice/text",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    30000
  );
}

export const health = () => requestJson("/health", {}, 4000);
export const listRecipes = () => requestJson("/recipes");
export const getRecipe = (id) => requestJson("/recipes/" + encodeURIComponent(id));
export const getBarcode = (code) => requestJson("/barcode/" + encodeURIComponent(code));
export const referenceImageUrl = (id, step) => "/reference/" + encodeURIComponent(id) + "/" + step;
