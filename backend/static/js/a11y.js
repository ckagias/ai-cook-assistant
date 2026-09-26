import { speak } from "./tts.js";
import { t } from "./strings.js";

// Speak what a button does before it's pressed:
//   touch/pen: long-press (~0.5 s) speaks and does NOT activate; a normal tap still activates
//   mouse:     hovering ~1/4 s speaks (PC demo)
//   keyboard:  focusing a button (Tab, Bluetooth remote) speaks
// Browsers only allow speech after the page has had one real tap, so this starts working
// once the Start button has been pressed.

export const LONG_PRESS_MS = 500;
export const MOVE_TOLERANCE_PX = 10;
export const HOVER_DWELL_MS = 250;
const REPEAT_GUARD_MS = 1500;
const CLICK_SUPPRESS_WINDOW_MS = 1000;
const STORAGE_KEY = "speakButtons";

// Per-viewer opt-out, e.g. for TalkBack users who'd otherwise hear every label twice.
export function speakButtonsEnabled() {
  try {
    return localStorage.getItem(STORAGE_KEY) !== "0";
  } catch {
    return true;
  }
}

export function setSpeakButtons(on) {
  try {
    localStorage.setItem(STORAGE_KEY, on ? "1" : "0");
  } catch {
    // storage unavailable - the default (on) applies
  }
}

export function describe(button, lang) {
  const key = button.dataset && button.dataset.speak;
  const text = key ? t("speak_" + key, lang) : "";
  return (text || button.getAttribute("aria-label") || button.textContent || "").trim();
}

export function installSpeakOnPress({
  root = document,
  getLang = () => "el",
  say = (text, lang) => speak(text, { priority: "hint", lang }),
  vibrate = (ms) => globalThis.navigator?.vibrate?.(ms),
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
  now = () => Date.now(),
} = {}) {
  let press = null; // { button, x, y, timer }
  let suppressClickOn = null;
  let suppressTimer = null;
  let hover = null; // { button, timer }
  let lastSpoken = { button: null, at: -Infinity };

  const buttonFrom = (target) => (target && target.closest ? target.closest("button") : null);

  function announce(button) {
    if (!speakButtonsEnabled()) return false;
    const lang = getLang();
    const text = describe(button, lang);
    if (!text) return false;
    say(text, lang);
    lastSpoken = { button, at: now() };
    return true;
  }

  function cancelPress() {
    if (press) clearTimer(press.timer);
    press = null;
  }

  function clearHover() {
    if (hover) clearTimer(hover.timer);
    hover = null;
  }

  // --- touch / pen long-press ---
  root.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse") return;
    suppressClickOn = null; // a fresh press never inherits a stale suppression
    const button = buttonFrom(e.target);
    cancelPress();
    // A hold-to-talk button is *meant* to be held - a long-press description would talk over
    // the user. Hover and keyboard focus still describe it.
    if (!button || button.disabled || (button.dataset && button.dataset.hold)) return;
    press = { button, x: e.clientX, y: e.clientY, timer: null };
    press.timer = setTimer(() => {
      if (!press) return;
      vibrate(20);
      announce(press.button);
      suppressClickOn = press.button; // the finger lifting must not also press it
      press = null;
    }, LONG_PRESS_MS);
  });

  root.addEventListener("pointermove", (e) => {
    if (press && Math.hypot(e.clientX - press.x, e.clientY - press.y) > MOVE_TOLERANCE_PX) cancelPress();
  });
  root.addEventListener("pointercancel", cancelPress);
  root.addEventListener("pointerup", () => {
    cancelPress();
    if (suppressClickOn) {
      // Some browsers never send the click after a long press - don't let the suppression
      // linger and swallow the next genuine tap.
      clearTimer(suppressTimer);
      suppressTimer = setTimer(() => (suppressClickOn = null), CLICK_SUPPRESS_WINDOW_MS);
    }
  });

  // Capture phase on the root: runs before app.js's delegated handler and before a
  // button's own listener, so a long-press never also triggers the action.
  root.addEventListener(
    "click",
    (e) => {
      if (suppressClickOn && buttonFrom(e.target) === suppressClickOn) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
      suppressClickOn = null;
    },
    true
  );

  // Android's long-press context menu / text selection would fight the gesture.
  root.addEventListener("contextmenu", (e) => {
    if (buttonFrom(e.target)) e.preventDefault();
  });

  // --- mouse hover (PC demo) ---
  root.addEventListener("pointerover", (e) => {
    if (e.pointerType !== "mouse") return;
    const button = buttonFrom(e.target);
    if (hover && hover.button === button) return;
    clearHover();
    if (!button) return;
    hover = {
      button,
      timer: setTimer(() => {
        if (lastSpoken.button === button && now() - lastSpoken.at < REPEAT_GUARD_MS) return;
        announce(button);
      }, HOVER_DWELL_MS),
    };
  });
  root.addEventListener("pointerout", (e) => {
    if (e.pointerType !== "mouse") return;
    if (!hover || buttonFrom(e.relatedTarget) !== hover.button) clearHover();
  });

  // --- keyboard focus ---
  root.addEventListener("focusin", (e) => {
    const button = buttonFrom(e.target);
    // :focus-visible is true for keyboard focus only - a tap or click focusing the
    // button must not double up with the long-press/hover speech.
    if (button && button.matches && button.matches(":focus-visible")) announce(button);
  });
}
