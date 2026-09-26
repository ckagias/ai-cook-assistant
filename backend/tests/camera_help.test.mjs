// camera_help.js: the browser's refusal -> the instructions for *that* browser. Error names and
// messages below are the ones each browser really produces.

const { cameraProblem } = await import("../static/js/camera_help.js");
const { t } = await import("../static/js/strings.js");

function assert(cond, message) {
  if (!cond) throw new Error("assertion failed: " + message);
}

const UA = {
  firefox: "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0",
  edge: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
  chrome: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
  android: "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36",
  iphone: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1",
  iphoneChrome: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/140.0 Mobile/15E148 Safari/604.1",
  macSafari: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15",
};

const denied = (detail = "Permission denied") => ({ mediaError: "NotAllowedError", detail });

// Firefox with "Block new requests asking to access your camera" - rejects without a prompt.
assert(cameraProblem(denied("The request is not allowed by the user agent or the platform in the current context."),
  { userAgent: UA.firefox }) === "cam_blocked_firefox", "Firefox block -> Firefox's settings path");
assert(cameraProblem(denied(), { userAgent: UA.edge }) === "cam_blocked", "Edge site block -> address-bar icon");
assert(cameraProblem(denied(), { userAgent: UA.chrome }) === "cam_blocked", "Chrome site block");
assert(cameraProblem(denied("Permission denied by system"), { userAgent: UA.edge }) === "cam_blocked_system",
  "Windows privacy switch off -> the OS settings");
assert(cameraProblem(denied(), { userAgent: UA.android }) === "cam_blocked_android", "Android");
assert(cameraProblem(denied(), { userAgent: UA.iphone }) === "cam_blocked_ios", "iPhone Safari");
assert(cameraProblem(denied(), { userAgent: UA.iphoneChrome }) === "cam_blocked_ios", "every iOS browser is Safari inside");
assert(cameraProblem(denied(), { userAgent: UA.macSafari }) === "cam_blocked_safari", "Mac Safari");
assert(cameraProblem(denied(), { userAgent: UA.edge, embedded: true }) === "cam_embedded", "iframe/preview pane");
assert(cameraProblem({ mediaError: "insecure" }, { userAgent: UA.chrome }) === "cam_insecure", "http on a LAN address");
assert(cameraProblem(denied(), { userAgent: UA.chrome, secure: false }) === "cam_insecure", "insecure wins");
assert(cameraProblem({ name: "NotReadableError" }, { userAgent: UA.chrome }) === "cam_busy", "camera in use (plain DOMException)");
assert(cameraProblem({ mediaError: "NotFoundError" }, { userAgent: UA.firefox }) === "cam_missing", "no camera");
assert(cameraProblem({ mediaError: "Weird" }, {}) === "cam_failed", "unknown -> generic retry");
assert(cameraProblem(null, {}) === "cam_failed", "no error object");

// Every key it can return has both languages.
for (const key of ["cam_blocked", "cam_blocked_firefox", "cam_blocked_ios", "cam_blocked_safari", "cam_blocked_android",
  "cam_blocked_system", "cam_embedded", "cam_busy", "cam_missing", "cam_insecure", "cam_failed"]) {
  assert(t(key, "el") && t(key, "en") && t(key, "el") !== t(key, "en"), `${key} has Greek and English`);
}

console.log("all passed");
