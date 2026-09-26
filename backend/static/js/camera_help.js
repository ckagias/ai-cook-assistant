// Why the camera didn't start, and where the fix is - that place differs per browser and OS, so a
// bare "NotAllowedError" helps nobody. Returns a strings.js key.
//
// A page can't override a browser that refuses: Firefox's "Block new requests asking to access
// your camera" and a remembered "Block" both reject at once, without a prompt. All it can do is
// say exactly where to switch it back on, and let Start try again.

const BLOCKED = new Set(["NotAllowedError", "PermissionDeniedError", "SecurityError"]);
const BUSY = new Set(["NotReadableError", "TrackStartError", "AbortError"]);
const MISSING = new Set(["NotFoundError", "DevicesNotFoundError", "OverconstrainedError"]);

export function cameraProblem(err, { userAgent = "", embedded = false, secure = true } = {}) {
  const name = (err && (err.mediaError || err.name)) || "";
  if (!secure || name === "insecure") return "cam_insecure";
  if (BLOCKED.has(name)) {
    // An editor's preview pane or any iframe without allow="camera": no prompt can ever show.
    if (embedded) return "cam_embedded";
    // Chrome/Edge say "Permission denied by system" when the OS privacy switch is off.
    if (/by system/i.test((err && (err.detail || err.message)) || "")) return "cam_blocked_system";
    if (/Firefox\//.test(userAgent)) return "cam_blocked_firefox";
    if (/iPhone|iPad|iPod/.test(userAgent)) return "cam_blocked_ios";
    if (/Safari\//.test(userAgent) && !/Chrome|Chromium|Edg\//.test(userAgent)) return "cam_blocked_safari";
    if (/Android/.test(userAgent)) return "cam_blocked_android";
    return "cam_blocked";
  }
  if (BUSY.has(name)) return "cam_busy";
  if (MISSING.has(name)) return "cam_missing";
  return "cam_failed";
}
