// Classic script (not a module): sw.test.mjs evaluates this with a shimmed self.
const SHELL_CACHE = "cook-assist-shell-v1";
const SHELL_FILES = [
  "/",
  "/app.css",
  "/manifest.webmanifest",
  "/js/app.js",
  "/js/boot.js",
  "/js/tts.js",
  "/js/strings.js",
  "/js/capture.js",
  "/js/api.js",
  "/js/monitor.js",
  "/js/aim.js",
  "/js/session.js",
  "/js/features.js",
  "/js/detect.js",
  "/js/a11y.js",
  "/js/voice.js",
  "/js/camera_help.js",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-512-maskable.png",
];
const SHELL_SET = new Set(SHELL_FILES);

// Exposed for sw.test.mjs. A navigation to "/?token=...&detect=1" is still the shell:
// the query string is dropped for the cache key, never stored.
function shellPath(request, origin) {
  if (request.method !== "GET") return null;
  const url = new URL(request.url);
  if (url.origin !== origin) return null;
  if (request.mode === "navigate") return "/";
  return SHELL_SET.has(url.pathname) ? url.pathname : null;
}

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((c) => c.addAll(SHELL_FILES)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL_CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const client of windows) {
        if (typeof client.focus === "function") return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow("/");
    })
  );
});

self.addEventListener("fetch", (event) => {
  const path = shellPath(event.request, self.location.origin);
  if (path === null) return; // API, POST, probe.html, /ca.crt, cross-origin: untouched
  event.respondWith(
    fetch(event.request)
      .then((res) => {
        if (res.ok) caches.open(SHELL_CACHE).then((c) => c.put(path, res.clone()));
        return res;
      })
      .catch(() => caches.match(path))
  );
});
