// Exercises api.js's retry/backoff behavior against a mocked global fetch - no real
// network calls, no DOM. localStorage is shimmed as an in-memory map since api.js
// reads the pairing token from it on every request.

globalThis.localStorage = {
  _data: {},
  getItem(key) {
    return Object.prototype.hasOwnProperty.call(this._data, key) ? this._data[key] : null;
  },
  setItem(key, value) {
    this._data[key] = String(value);
  },
};

function fakeResponse(status) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => ({}),
  };
}

let fetchCalls;
let fetchStatuses;

globalThis.fetch = async (path, init) => {
  fetchCalls.push({ path, init });
  const status = fetchStatuses.shift();
  return fakeResponse(status);
};

const api = await import("../static/js/api.js");

function assert(cond, message) {
  if (!cond) {
    throw new Error("assertion failed: " + message);
  }
}

async function testAnalyzeRequest() {
  fetchCalls = [];
  fetchStatuses = [200];
  const result = await api.analyze({ mode: "identify", image_base64: "x" });
  assert(fetchCalls.length === 1, `expected 1 fetch call, got ${fetchCalls.length}`);
  assert(fetchCalls[0].path === "/analyze", `expected /analyze, got ${fetchCalls[0].path}`);
  assert(JSON.stringify(result) === "{}", "expected the mocked JSON body back");
  console.log("test a (successful analyze makes exactly one call) OK");
}

async function test429NeverRetried() {
  fetchCalls = [];
  fetchStatuses = [429];
  let threw = null;
  try {
    await api.analyze({ mode: "identify", image_base64: "x" });
  } catch (err) {
    threw = err;
  }
  assert(threw !== null, "expected analyze() to throw on a 429");
  assert(threw.status === 429, `expected HttpError.status===429, got ${threw.status}`);
  assert(fetchCalls.length === 1, `expected a 429 to never be retried, got ${fetchCalls.length} calls`);
  console.log("test b (429 is never retried) OK");
}

async function test500IsRetriedOnce() {
  fetchCalls = [];
  fetchStatuses = [500, 200];
  const result = await api.analyze({ mode: "identify", image_base64: "x" });
  assert(fetchCalls.length === 2, `expected a 500 to be retried once, got ${fetchCalls.length} calls`);
  assert(JSON.stringify(result) === "{}", "expected the retry's successful body back");
  console.log("test c (500 is retried exactly once) OK");
}

async function test400NeverRetried() {
  fetchCalls = [];
  fetchStatuses = [400];
  let threw = null;
  try {
    await api.analyze({ mode: "identify", image_base64: "x" });
  } catch (err) {
    threw = err;
  }
  assert(threw !== null && threw.status === 400, "expected a 400 to throw HttpError");
  assert(fetchCalls.length === 1, `expected a 400 to never be retried, got ${fetchCalls.length} calls`);
  console.log("test d (400 is never retried) OK");
}

async function testPairingTokenHeaderAttached() {
  fetchCalls = [];
  fetchStatuses = [200];
  api.setPairingToken("abc123");
  await api.health();
  const headers = fetchCalls[0].init.headers;
  assert(headers["X-Pairing-Token"] === "abc123", `expected pairing token header, got ${JSON.stringify(headers)}`);
  console.log("test e (pairing token header attached from localStorage) OK");
}

await testAnalyzeRequest();
await test429NeverRetried();
await test500IsRetriedOnce();
await test400NeverRetried();
await testPairingTokenHeaderAttached();

console.log("all passed");
