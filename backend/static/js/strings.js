export const STRINGS = {
  greeting: {
    en: "Ready. Point the camera at what you're cooking.",
    el: "Έτοιμο. Δείξε την κάμερα σε αυτό που μαγειρεύεις.",
  },
  analyzing: {
    en: "Let me take a look.",
    el: "Για να δω.",
  },
  network_trouble: {
    en: "I'm having trouble reaching the server. Please try again.",
    el: "Έχω πρόβλημα σύνδεσης με τον διακομιστή. Δοκίμασε ξανά.",
  },
  // Deliberately identical in both slots: it fires precisely when no Greek voice
  // exists, so a Greek rendering of it could never be heard.
  no_greek_voice: {
    en: "No Greek voice was found on this device, so I'll speak in English instead.",
    el: "No Greek voice was found on this device, so I'll speak in English instead.",
  },
  timer_done: {
    en: "Time's up.",
    el: "Ο χρόνος τελείωσε.",
  },
};

export function t(key, lang = "el") {
  const entry = STRINGS[key];
  if (!entry) return "";
  return entry[lang] ?? entry.en;
}
