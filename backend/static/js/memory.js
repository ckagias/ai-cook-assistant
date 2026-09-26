// Short-term memory for one recipe: what the cook asked for (needs, preferences, doneness), which
// steps were done and when, what each camera check saw (colour, doneness, "needs 5 more
// minutes"), timers, and the assistant's own suggestions. It is sent with every question and
// camera check, so "what did we do?", "is it browner than before?" and "remember I'm allergic
// to nuts" all work - and it is shown on screen for a cook who reads rather than listens.
//
// Kept on this device only (localStorage, per recipe) and forgotten after MEMORY_TTL_MS, so
// coming back to the same recipe within the day picks up where it was left.

export const MEMORY_TTL_MS = 12 * 3600 * 1000;
export const MAX_EVENTS = 60;
export const MAX_CHARS = 1800; // the server accepts 2000

function defaultStorage() {
  return {
    get(key) {
      try {
        return globalThis.localStorage.getItem(key);
      } catch {
        return null;
      }
    },
    set(key, value) {
      try {
        globalThis.localStorage.setItem(key, value);
      } catch {
        // private browsing / full - memory still works for this page
      }
    },
    remove(key) {
      try {
        globalThis.localStorage.removeItem(key);
      } catch {
        // ignore
      }
    },
  };
}

const clip = (text, n) => {
  const s = String(text || "").replace(/\s+/g, " ").trim();
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
};

export function createMemory({ storage = defaultStorage(), now = () => Date.now() } = {}) {
  let state = null; // { recipeId, startedAt, updatedAt, prefs: [], doneness, lastStep, events: [] }

  const keyFor = (id) => "memory:" + id;

  function save() {
    if (!state) return;
    state.updatedAt = now();
    storage.set(keyFor(state.recipeId), JSON.stringify(state));
  }

  function load(recipeId) {
    try {
      const saved = JSON.parse(storage.get(keyFor(recipeId)) || "null");
      if (saved && saved.recipeId === recipeId && now() - (saved.updatedAt || 0) < MEMORY_TTL_MS) return saved;
    } catch {
      // unreadable - start over
    }
    return null;
  }

  return {
    // -> true when an earlier session of this recipe (same day) was picked up.
    open(recipeId) {
      const saved = load(recipeId);
      state = saved || { recipeId, startedAt: now(), updatedAt: now(), prefs: [], doneness: null, lastStep: null, events: [] };
      if (!saved) save();
      return Boolean(saved && (saved.events.length || saved.prefs.length));
    },
    // Start this recipe over: forget the earlier session.
    reset() {
      if (!state) return;
      const { recipeId } = state;
      state = { recipeId, startedAt: now(), updatedAt: now(), prefs: [], doneness: null, lastStep: null, events: [] };
      save();
    },
    close() {
      state = null;
    },
    isOpen: () => Boolean(state),
    prefs: () => (state ? state.prefs.slice() : []),
    lastStep: () => (state ? state.lastStep : null),
    events: () => (state ? state.events.slice() : []),

    addPreference(text) {
      const value = clip(text, 200);
      if (!state || !value) return;
      if (!state.prefs.includes(value)) state.prefs.push(value);
      save();
    },
    removePreference(text) {
      if (!state) return;
      state.prefs = state.prefs.filter((p) => p !== text);
      save();
    },
    setDoneness(value) {
      if (!state) return;
      state.doneness = value;
      save();
    },
    // type: "step" | "check" | "timer" | "answer" | "advice" | "ingredients" | "note" | "done"
    note(type, text, { step = null } = {}) {
      if (!state || !text) return;
      if (type === "step" && step !== null) state.lastStep = step;
      state.events.push({ at: now(), type, step, text: clip(text, 240) });
      if (state.events.length > MAX_EVENTS) state.events.splice(0, state.events.length - MAX_EVENTS);
      save();
    },

    // What the assistant is given: preferences first (they must never be dropped), then as many
    // of the latest events as fit, oldest first, with how long ago each happened.
    summary() {
      if (!state) return "";
      const head = [];
      if (state.prefs.length) head.push(`Cook's needs and preferences: ${state.prefs.join("; ")}.`);
      if (state.doneness) head.push(`Doneness chosen: ${state.doneness.replace("_", " ")}.`);
      if (state.lastStep !== null) head.push(`Furthest step reached: ${state.lastStep + 1}.`);
      let text = head.join(" ");
      const lines = [];
      let budget = MAX_CHARS - text.length - 20;
      for (let i = state.events.length - 1; i >= 0 && budget > 0; i--) {
        const e = state.events[i];
        const mins = Math.max(0, Math.round((now() - e.at) / 60000));
        const line = `[${mins} min ago] ${e.type}: ${e.text}`;
        if (line.length + 1 > budget) break;
        lines.unshift(line);
        budget -= line.length + 1;
      }
      if (lines.length) text += (text ? "\n" : "") + lines.join("\n");
      return text.slice(0, MAX_CHARS);
    },
  };
}
