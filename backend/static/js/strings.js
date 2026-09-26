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
  speak_talk: {
    en: "Talk. Hold it down and say what you need, then let go. For example: next step, set a timer for five minutes, or I want to make pasta.",
    el: "Μίλα. Κράτα το πατημένο, πες τι θέλεις και άφησέ το. Για παράδειγμα: επόμενο βήμα, βάλε χρονόμετρο πέντε λεπτά, ή θέλω να φτιάξω ζυμαρικά.",
  },
  speak_detect_toggle: {
    en: "Detection. Turns the on-screen object detection preview on or off.",
    el: "Ανίχνευση. Ανοίγει ή κλείνει την προβολή ανίχνευσης αντικειμένων στην οθόνη.",
  },

  // --- camera didn't start: what to do, per browser (camera_help.js picks the key) ---
  cam_blocked: {
    en: "The camera is blocked for this page. Click the icon to the left of the address (a lock or sliders), set Camera and Microphone to Allow, then press Start again.",
    el: "Η κάμερα είναι μπλοκαρισμένη για αυτή τη σελίδα. Πάτησε το εικονίδιο αριστερά της διεύθυνσης (κλειδαριά ή ρυθμίσεις), βάλε την Κάμερα και το Μικρόφωνο σε «Να επιτρέπεται» και πάτησε ξανά ΞΕΚΙΝΑ.",
  },
  cam_blocked_firefox: {
    en: "Firefox blocked the camera. If the address bar shows a crossed-out camera, click it and remove the block. Otherwise open Settings, Privacy & Security, Permissions, Camera, Settings, and untick \"Block new requests asking to access your camera\". Then press Start again.",
    el: "Ο Firefox μπλόκαρε την κάμερα. Αν στη γραμμή διεύθυνσης φαίνεται διαγραμμένη κάμερα, πάτησέ τη και αφαίρεσε τον αποκλεισμό. Αλλιώς: Ρυθμίσεις, Απόρρητο και ασφάλεια, Άδειες, Κάμερα, Ρυθμίσεις, και ξετσέκαρε το «Φραγή νέων αιτημάτων πρόσβασης στην κάμερα». Μετά πάτησε ξανά ΞΕΚΙΝΑ.",
  },
  cam_blocked_ios: {
    en: "The camera is blocked. On iPhone or iPad: tap \"aA\" in the address bar, Website Settings, Camera and Microphone, Allow - or Settings, Apps, Safari, Camera. Then reload the page.",
    el: "Η κάμερα είναι μπλοκαρισμένη. Σε iPhone ή iPad: πάτησε «aA» στη γραμμή διεύθυνσης, Ρυθμίσεις ιστότοπου, Κάμερα και Μικρόφωνο, Να επιτρέπεται - ή Ρυθμίσεις, Εφαρμογές, Safari, Κάμερα. Μετά ανανέωσε τη σελίδα.",
  },
  cam_blocked_safari: {
    en: "Safari blocked the camera. Open Safari, Settings, Websites, Camera and Microphone, set this site to Allow, then reload the page.",
    el: "Το Safari μπλόκαρε την κάμερα. Άνοιξε Safari, Ρυθμίσεις, Ιστότοποι, Κάμερα και Μικρόφωνο, βάλε αυτόν τον ιστότοπο σε «Να επιτρέπεται» και ανανέωσε τη σελίδα.",
  },
  cam_blocked_android: {
    en: "The camera is blocked. Tap the icon to the left of the address, Permissions, and allow Camera and Microphone. If they're greyed out: Android Settings, Apps, your browser, Permissions. Then press Start again.",
    el: "Η κάμερα είναι μπλοκαρισμένη. Πάτησε το εικονίδιο αριστερά της διεύθυνσης, Άδειες, και επίτρεψε Κάμερα και Μικρόφωνο. Αν είναι γκρι: Ρυθμίσεις Android, Εφαρμογές, ο browser σου, Άδειες. Μετά πάτησε ξανά ΞΕΚΙΝΑ.",
  },
  cam_blocked_system: {
    en: "The computer itself is blocking the camera. Windows: Settings, Privacy & security, Camera - turn on camera access and \"Let desktop apps access your camera\". Mac: System Settings, Privacy & Security, Camera - allow your browser. Then press Start again.",
    el: "Ο ίδιος ο υπολογιστής μπλοκάρει την κάμερα. Windows: Ρυθμίσεις, Απόρρητο και ασφάλεια, Κάμερα - άνοιξε την πρόσβαση και το «Να επιτρέπεται στις εφαρμογές υπολογιστή». Mac: Ρυθμίσεις συστήματος, Απόρρητο και ασφάλεια, Κάμερα - επίτρεψε τον browser. Μετά πάτησε ξανά ΞΕΚΙΝΑ.",
  },
  cam_embedded: {
    en: "This preview window can't use the camera. Open the page in a browser - Chrome, Edge, Firefox or Safari.",
    el: "Αυτό το παράθυρο προεπισκόπησης δεν μπορεί να χρησιμοποιήσει την κάμερα. Άνοιξε τη σελίδα σε browser - Chrome, Edge, Firefox ή Safari.",
  },
  cam_busy: {
    en: "Another app is using the camera (Teams, Zoom, the Camera app). Close it, then press Start again.",
    el: "Άλλη εφαρμογή χρησιμοποιεί την κάμερα (Teams, Zoom, Κάμερα). Κλείσ' την και πάτησε ξανά ΞΕΚΙΝΑ.",
  },
  cam_missing: {
    en: "No camera was found. Connect one, then press Start again.",
    el: "Δεν βρέθηκε κάμερα. Σύνδεσε μία και πάτησε ξανά ΞΕΚΙΝΑ.",
  },
  cam_insecure: {
    en: "The camera needs a secure address. On this computer open http://localhost:8000; on a phone use the https:// link that setup-window prints.",
    el: "Η κάμερα θέλει ασφαλή διεύθυνση. Σε αυτόν τον υπολογιστή άνοιξε http://localhost:8000· σε κινητό τον σύνδεσμο https:// που τυπώνει το setup-window.",
  },
  cam_failed: {
    en: "The camera didn't start. Press Start to try again.",
    el: "Η κάμερα δεν ξεκίνησε. Πάτησε ξανά ΞΕΚΙΝΑ.",
  },

  // --- push-to-talk voice commands, see voice.js ---
  talk: { en: "Talk", el: "Μίλα" },
  listening: { en: "Listening…", el: "Σε ακούω…" },
  thinking: { en: "One moment…", el: "Μια στιγμή…" },
  hold_to_talk: {
    en: "Hold the button down while you speak.",
    el: "Κράτα το κουμπί πατημένο όσο μιλάς.",
  },
  no_mic: {
    en: "I can't use the microphone. Allow it in the browser settings and start again.",
    el: "Δεν έχω πρόσβαση στο μικρόφωνο. Επίτρεψέ το στις ρυθμίσεις του browser και ξεκίνα ξανά.",
  },
  voice_unavailable: {
    en: "Voice commands aren't set up on the server. The buttons still work.",
    el: "Οι φωνητικές εντολές δεν είναι ρυθμισμένες στον διακομιστή. Τα κουμπιά λειτουργούν κανονικά.",
  },
  no_previous: { en: "This is the first step.", el: "Αυτό είναι το πρώτο βήμα." },
  timer_stopped: { en: "Timer stopped.", el: "Το χρονόμετρο σταμάτησε." },

  // --- detection preview (visual panel) ---
  detect_toggle: { en: "Detection", el: "Ανίχνευση" },
  detect_error: { en: "Detection unavailable - is the server running with DETECTION_ENABLED=true?", el: "Η ανίχνευση δεν είναι διαθέσιμη." },
  detect_loading: { en: "Loading the detection model…", el: "Φόρτωση μοντέλου ανίχνευσης…" },
  detect_slow: { en: "Detection is slow to answer - retrying…", el: "Η ανίχνευση αργεί - ξαναδοκιμάζω…" },
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
