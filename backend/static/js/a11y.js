import { speak } from "./tts.js";
import { t } from "./strings.js";

// Say and show what a button does before it's pressed:
//   touch/pen: long-press (~0.5 s) speaks and does NOT activate; a normal tap still activates
//   mouse:     hovering ~1/4 s speaks (PC demo)
//   keyboard:  focusing a button (Tab, Bluetooth remote) speaks
// The same words appear in a bubble by the button, for cooks who can't hear them - also when
// speaking them is turned off. Browsers only allow speech after the page has had one real tap,
// so the spoken part starts working once the Start button has been pressed.

export const LONG_PRESS_MS = 500;
export const MOVE_TOLERANCE_PX = 10;
export const HOVER_DWELL_MS = 250;
const REPEAT_GUARD_MS = 1500;
const CLICK_SUPPRESS_WINDOW_MS = 1000;
export const TOUCH_TIP_MS = 3500; // a long-press bubble stays this long after the finger lifts
const STORAGE_KEY = "speakButtons";

// The bubble: one element, placed above the button (below it when there's no room), inside the
// screen. aria-hidden: screen readers already have the button's name and hear the description.
let tipEl = null;
function showTipOnScreen(button, text) {
  const doc = globalThis.document;
  if (!doc || !doc.body || !button.getBoundingClientRect) return;
  if (!tipEl) {
    tipEl = doc.createElement("div");
    tipEl.className = "tip";
    tipEl.setAttribute("aria-hidden", "true");
    doc.body.appendChild(tipEl);
  }
  tipEl.textContent = text;
  tipEl.hidden = false;
  const r = button.getBoundingClientRect();
  const width = doc.documentElement.clientWidth;
  const gap = 8;
  const left = Math.min(Math.max(gap, r.left + r.width / 2 - tipEl.offsetWidth / 2), width - tipEl.offsetWidth - gap);
  let top = r.top - tipEl.offsetHeight - gap;
  if (top < gap) top = r.bottom + gap;
  tipEl.style.left = `${Math.max(gap, left)}px`;
  tipEl.style.top = `${top}px`;
}
function hideTipOnScreen() {
  if (tipEl) tipEl.hidden = true;
}

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
  showTip = showTipOnScreen,
  hideTip = hideTipOnScreen,
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
  let tipFor = null; // the button whose bubble is showing
  let tipTimer = null;

  const buttonFrom = (target) => (target && target.closest ? target.closest("button") : null);

  function tip(button, text) {
    if (tipTimer !== null) clearTimer(tipTimer);
    tipTimer = null;
    tipFor = button;
    showTip(button, text);
  }

  function untip(button = tipFor) {
    if (!tipFor || button !== tipFor) return;
    if (tipTimer !== null) clearTimer(tipTimer);
    tipTimer = null;
    tipFor = null;
    hideTip();
  }

  // Shown always; spoken unless this device turned speaking off. `speakIt` false: shown only.
  function announce(button, { speakIt = true } = {}) {
    const lang = getLang();
    const text = describe(button, lang);
    if (!text) return false;
    tip(button, text);
    if (!speakIt || !speakButtonsEnabled()) return false;
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
      const button = press.button;
      announce(button);
      suppressClickOn = button; // the finger lifting must not also press it
      press = null;
      tipTimer = setTimer(() => untip(button), TOUCH_TIP_MS); // time to read it
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
        // Back on it right away: the bubble again, the voice not again.
        announce(button, { speakIt: !(lastSpoken.button === button && now() - lastSpoken.at < REPEAT_GUARD_MS) });
      }, HOVER_DWELL_MS),
    };
  });
  root.addEventListener("pointerout", (e) => {
    if (e.pointerType !== "mouse") return;
    const leftFor = buttonFrom(e.relatedTarget);
    if (!hover || leftFor !== hover.button) clearHover();
    if (leftFor !== tipFor) untip();
  });

  // --- keyboard focus ---
  root.addEventListener("focusin", (e) => {
    const button = buttonFrom(e.target);
    // :focus-visible is true for keyboard focus only - a tap or click focusing the
    // button must not double up with the long-press/hover speech.
    if (button && button.matches && button.matches(":focus-visible")) announce(button);
  });
  root.addEventListener("focusout", (e) => untip(buttonFrom(e.target)));
}
