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
  not_paired: {
    en: "This device isn't paired. Open the link with ?token=... once to set it up.",
    el: "Αυτή η συσκευή δεν είναι συνδεδεμένη. Άνοιξε τον σύνδεσμο με ?token=... μία φορά για να τη ρυθμίσεις.",
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
  caution: {
    en: "Careful: something near the heat needs attention.",
    el: "Πρόσεξε: κάτι κοντά στη φωτιά θέλει προσοχή.",
  },

  // --- spoken button descriptions (long-press / hover / keyboard focus), see a11y.js ---
  speak_start: {
    en: "Start. Turns on the camera, microphone and voice.",
    el: "Ξεκίνα. Ανοίγει την κάμερα, το μικρόφωνο και τη φωνή.",
  },
  speak_identify: {
    en: "What is this? Takes a photo and tells you what the camera sees.",
    el: "Τι είναι αυτό; Βγάζει φωτογραφία και σου λέει τι βλέπει η κάμερα.",
  },
  speak_recipes: {
    en: "Recipes. Lists the recipes you can cook step by step.",
    el: "Συνταγές. Σου λέει τις συνταγές που μπορείς να μαγειρέψεις βήμα βήμα.",
  },
  speak_check: {
    en: "Is it ready? Takes a photo and checks how the food is doing.",
    el: "Είναι έτοιμο; Βγάζει φωτογραφία και ελέγχει πώς πάει το φαγητό.",
  },
  speak_repeat: { en: "Repeat. Says the current step again.", el: "Επανάλαβε. Λέει ξανά το τρέχον βήμα." },
  speak_next: { en: "Next. Moves on to the next step.", el: "Επόμενο. Πηγαίνει στο επόμενο βήμα." },
  speak_stop: { en: "Stop. Ends the recipe.", el: "Διακοπή. Σταματά τη συνταγή." },
  speak_answer_yes: { en: "Yes. Answers yes to my question.", el: "Ναι. Απαντά ναι στην ερώτησή μου." },
  speak_answer_no: { en: "No. Answers no to my question.", el: "Όχι. Απαντά όχι στην ερώτησή μου." },
  speak_back: { en: "Back. Returns to the main buttons.", el: "Πίσω. Επιστρέφει στα κύρια κουμπιά." },
  speak_detect_toggle: {
    en: "Detection. Turns the on-screen object detection preview on or off.",
    el: "Ανίχνευση. Ανοίγει ή κλείνει την προβολή ανίχνευσης αντικειμένων στην οθόνη.",
  },

  // --- detection preview (visual panel) ---
  detect_toggle: { en: "Detection", el: "Ανίχνευση" },
  detect_error: { en: "Detection unavailable - is the server running with DETECTION_ENABLED=true?", el: "Η ανίχνευση δεν είναι διαθέσιμη." },
  detect_backend: { en: "server", el: "διακομιστής" },
  col_object: { en: "Object", el: "Αντικείμενο" },
  col_group: { en: "Group", el: "Ομάδα" },
  col_confidence: { en: "Confidence", el: "Βεβαιότητα" },
  col_size: { en: "Size", el: "Μέγεθος" },
  col_hand: { en: "Hand", el: "Χέρι" },
  hand: { en: "Hand", el: "Χέρι" },
  hand_left: { en: "Left hand", el: "Αριστερό χέρι" },
  hand_right: { en: "Right hand", el: "Δεξί χέρι" },
  rel_touching: { en: "touching", el: "ακουμπά" },
  rel_over: { en: "over", el: "από πάνω" },
  rel_near: { en: "near", el: "κοντά" },
  group_hand: { en: "hand", el: "χέρι" },
  group_utensil: { en: "utensil", el: "σκεύος" },
  group_cookware: { en: "cookware", el: "μαγειρικό σκεύος" },
  group_appliance: { en: "appliance", el: "συσκευή" },
  group_ingredient: { en: "ingredient", el: "υλικό" },
  group_food: { en: "food", el: "φαγητό" },
  group_hazard: { en: "hazard", el: "κίνδυνος" },
};

export function t(key, lang = "el") {
  const entry = STRINGS[key];
  if (!entry) return "";
  return entry[lang] ?? entry.en;
}
