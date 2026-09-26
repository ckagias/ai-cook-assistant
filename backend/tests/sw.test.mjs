// Evaluates sw.js as a classic worker script against a shimmed self/caches.
// No browser, no network: shellPath allow-list + notificationclick registration.

import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const ORIGIN = "https://192.168.1.15:8443";
const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../static/sw.js"), "utf8");

const listeners = {};
const self = {
  location: { origin: ORIGIN },
  addEventListener(type, fn) {
    (listeners[type] ||= []).push(fn);
  },
  skipWaiting() {},
  clients: { claim() {} },
};
const context = vm.createContext({
  self,
  caches: {},
  fetch() {},
  URL,
  Set,
  Promise,
});
vm.runInContext(source, context);
const { shellPath } = context;

function assert(cond, message) {
  if (!cond) throw new Error("assertion failed: " + message);
}

function req(method, url, { mode = "cors", origin = ORIGIN } = {}) {
  const absolute = url.startsWith("http") ? url : origin + url;
  return { method, url: absolute, mode };
}

assert(typeof shellPath === "function", "shellPath should be defined on the worker global");

assert(shellPath(req("POST", "/analyze"), ORIGIN) === null, "POST /analyze");
assert(shellPath(req("POST", "/detect"), ORIGIN) === null, "POST /detect");
assert(shellPath(req("POST", "/voice"), ORIGIN) === null, "POST /voice");

assert(shellPath(req("GET", "/recipes"), ORIGIN) === null, "GET /recipes");
assert(shellPath(req("GET", "/health"), ORIGIN) === null, "GET /health");
assert(shellPath(req("GET", "/ca.crt"), ORIGIN) === null, "GET /ca.crt");
assert(shellPath(req("GET", "/probe.html"), ORIGIN) === null, "GET /probe.html");

assert(shellPath(req("GET", "https://evil.example/js/app.js"), ORIGIN) === null, "cross-origin GET");

assert(
  shellPath(req("GET", "/?token=abc&detect=1", { mode: "navigate" }), ORIGIN) === "/",
  "navigation with pairing query still caches as /"
);
assert(shellPath(req("GET", "/js/app.js"), ORIGIN) === "/js/app.js", "GET /js/app.js");

// Every module the app can import is in the offline shell - a missing one breaks an installed app
// opened without a connection (app.js's imports fail). New modules must be added to SHELL_FILES.
for (const file of readdirSync(join(dirname(fileURLToPath(import.meta.url)), "../static/js")).filter((f) => f.endsWith(".js"))) {
  assert(shellPath(req("GET", "/js/" + file), ORIGIN) === "/js/" + file, `/js/${file} is in sw.js SHELL_FILES`);
}

assert(
  (listeners.notificationclick || []).length > 0,
  "notificationclick handler should be registered"
);

// fetch: the copy for the cache is cloned before the page reads the body. Cloning later, inside
// the caches.open() callback, threw "Response body is already used" on every shell file.
{
  let bodyUsed = false;
  const res = {
    ok: true,
    clone() {
      if (bodyUsed) throw new TypeError("Failed to execute 'clone' on 'Response': Response body is already used");
      return { copy: true };
    },
  };
  let openCache;
  const puts = [];
  context.fetch = () => Promise.resolve(res);
  context.caches = { open: () => new Promise((resolve) => (openCache = resolve)), match: async () => undefined };
  let responded;
  const waits = [];
  const event = { request: req("GET", "/js/app.js"), respondWith: (p) => (responded = p), waitUntil: (p) => waits.push(p) };
  for (const fn of listeners.fetch) fn(event);
  const served = await responded;
  bodyUsed = true; // the page consumes the response
  openCache({ put: (path, copy) => puts.push([path, copy]) });
  await Promise.all(waits);
  assert(served === res, "the page gets the network response itself");
  assert(puts.length === 1 && puts[0][0] === "/js/app.js" && puts[0][1].copy, "the cache got a clone taken in time");
}

console.log("all passed");
