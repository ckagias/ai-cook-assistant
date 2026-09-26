// Evaluates sw.js as a classic worker script against a shimmed self/caches.
// No browser, no network: only shellPath's allow-list.

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const ORIGIN = "https://192.168.1.15:8443";
const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../static/sw.js"), "utf8");

const self = {
  location: { origin: ORIGIN },
  addEventListener() {},
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

console.log("all passed");
