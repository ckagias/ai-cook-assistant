// Cooking timers. The cook starts each one ("start the timer" / the timer button) - a step being
// read out never starts one, because people work at different speeds. Several can run at once
// (the sauce simmers while the pasta water boils), so each is keyed, normally by its step.
//
// Absolute end timestamps, never decrementing counters: a backgrounded tab throttles to one tick
// per second, then per minute, and a locked screen can freeze JS outright; only an absolute
// deadline survives that - and a deadline that passed while hidden still fires on return.

export function createTimers({
  onTick = () => {}, // (list) every second while any timer runs, and on every change
  onExpired = () => {}, // (timer) once, when it reaches zero
  now = () => Date.now(),
  every = (fn, ms) => setInterval(fn, ms),
  doc = globalThis.document,
} = {}) {
  const timers = new Map(); // key -> { key, label, stepIndex, endsAt, totalMs }

  function view(tm) {
    const remainingMs = Math.max(0, tm.endsAt - now());
    return {
      key: tm.key,
      label: tm.label,
      stepIndex: tm.stepIndex,
      remainingMs,
      totalMs: tm.totalMs,
      elapsedMs: Math.max(0, tm.totalMs - remainingMs),
    };
  }

  function list() {
    return [...timers.values()].map(view).sort((a, b) => a.remainingMs - b.remainingMs);
  }

  function tick() {
    const t = now();
    for (const tm of [...timers.values()]) {
      if (tm.endsAt <= t) {
        timers.delete(tm.key);
        onExpired(view(tm));
      }
    }
    onTick(list());
  }

  every(tick, 1000);
  if (doc && typeof doc.addEventListener === "function") {
    doc.addEventListener("visibilitychange", () => {
      if (doc.visibilityState === "visible") tick();
    });
  }

  return {
    start(key, seconds, { label = "", stepIndex = null } = {}) {
      const totalMs = Math.max(1, Math.round(seconds)) * 1000;
      timers.set(key, { key, label, stepIndex, endsAt: now() + totalMs, totalMs });
      onTick(list());
      return view(timers.get(key));
    },
    // More (positive) or less (negative) time. Taking off more than is left ends it now.
    add(key, seconds) {
      const tm = timers.get(key);
      if (!tm) return null;
      const deltaMs = Math.round(seconds) * 1000;
      tm.endsAt = Math.max(now(), tm.endsAt + deltaMs);
      tm.totalMs = Math.max(0, tm.totalMs + deltaMs);
      tick();
      return timers.has(key) ? view(tm) : null;
    },
    stop(key) {
      const had = timers.delete(key);
      onTick(list());
      return had;
    },
    clear() {
      timers.clear();
      onTick(list());
    },
    get(key) {
      const tm = timers.get(key);
      return tm ? view(tm) : null;
    },
    list,
    soonest: () => list()[0] || null,
    tick,
  };
}

export function formatClock(ms) {
  const totalSec = Math.ceil(Math.max(0, ms) / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  const mm = h ? String(m).padStart(2, "0") : String(m);
  return `${h ? h + ":" : ""}${mm}:${String(s).padStart(2, "0")}`;
}
