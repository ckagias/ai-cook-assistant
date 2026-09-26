export const STRINGS = {
  greeting: {
    en: "Ready. Say “Hey chef” or tap Talk, then tell me what you'd like to cook.",
    el: "Έτοιμο. Πες «Γεια σου σεφ» ή πάτα Μίλα, και πες μου τι θέλεις να μαγειρέψεις.",
  },
  greeting_no_wake: {
    en: "Ready. Tap Talk, or type below what you'd like to cook.",
    el: "Έτοιμο. Πάτα Μίλα, ή γράψε από κάτω τι θέλεις να μαγειρέψεις.",
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
    en: "Check it. Takes a photo and tells you whether this step looks done - a cut, a mix, or the food cooking.",
    el: "Έλεγξε. Βγάζει φωτογραφία και σου λέει αν το βήμα φαίνεται έτοιμο - κόψιμο, ανάμειξη ή μαγείρεμα.",
  },
  speak_repeat: { en: "Repeat. Says the current step again.", el: "Επανάλαβε. Λέει ξανά το τρέχον βήμα." },
  speak_next: { en: "Next. Moves on to the next step.", el: "Επόμενο. Πηγαίνει στο επόμενο βήμα." },
  speak_stop: { en: "Stop. Ends the recipe.", el: "Διακοπή. Σταματά τη συνταγή." },
  speak_answer_yes: { en: "Yes. Answers yes to my question.", el: "Ναι. Απαντά ναι στην ερώτησή μου." },
  speak_answer_no: { en: "No. Answers no to my question.", el: "Όχι. Απαντά όχι στην ερώτησή μου." },
  speak_back: { en: "Back. Returns to the main buttons.", el: "Πίσω. Επιστρέφει στα κύρια κουμπιά." },
  speak_talk: {
    en: "Talk. Tap it, then say what you need. For example: I want to make roast beef, next step, start the timer, or check it.",
    el: "Μίλα. Πάτα το και πες τι θέλεις. Για παράδειγμα: θέλω να φτιάξω ροσμπίφ, επόμενο βήμα, χρονόμετρο, ή έλεγξε.",
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
  no_speech: { en: "I didn't hear anything.", el: "Δεν άκουσα τίποτα." },

  // --- hands-free: "Hey chef" (wake.js) ---
  wake_toggle: { en: "Hands-free", el: "Χωρίς χέρια" },
  wake_idle: { en: "Say “Hey chef”", el: "Πες «Γεια σου σεφ»" },
  wake_armed: { en: "Listening…", el: "Σε ακούω…" },
  wake_off: { en: "Hands-free is off - tap Talk", el: "Χωρίς χέρια: ανενεργό - πάτα Μίλα" },
  wake_unsupported: {
    en: "This browser can't listen hands-free - tap Talk (Chrome, Edge or Safari can)",
    el: "Αυτός ο browser δεν ακούει χωρίς χέρια - πάτα Μίλα (μπορούν Chrome, Edge, Safari)",
  },
  wake_blocked: { en: "The microphone is blocked - hands-free is off", el: "Το μικρόφωνο είναι μπλοκαρισμένο - χωρίς χέρια ανενεργό" },
  wake_local: { en: "on this device", el: "στη συσκευή" },
  wake_cloud: { en: "via the browser's speech service", el: "μέσω της υπηρεσίας ομιλίας του browser" },
  wake_on_said: { en: "Hands-free on. Say “Hey chef”.", el: "Χωρίς χέρια: ενεργό. Πες «Γεια σου σεφ»." },
  wake_off_said: { en: "Hands-free off. Tap Talk when you need me.", el: "Χωρίς χέρια: ανενεργό. Πάτα Μίλα όταν με χρειαστείς." },
  wake_timeout: { en: "I'm here when you need me.", el: "Είμαι εδώ όταν με χρειαστείς." },
  still_busy: { en: "One moment, I'm still looking.", el: "Μια στιγμή, ακόμα κοιτάζω." },
  no_recipe_open: {
    en: "No recipe is open. Say, for example, “I want to make pasta”.",
    el: "Δεν υπάρχει ανοιχτή συνταγή. Πες για παράδειγμα «θέλω να φτιάξω ζυμαρικά».",
  },
  no_question: { en: "I didn't ask anything. What would you like to do?", el: "Δεν σε ρώτησα κάτι. Τι θέλεις να κάνω;" },
  ok: { en: "OK.", el: "Εντάξει." },
  changed: { en: "Something changed. Shall I check?", el: "Κάτι άλλαξε. Να ελέγξω;" },

  // --- recipe overview: ingredients before the first step ---
  overview_serves: { en: "Serves {n}.", el: "Για {n} άτομα." },
  overview_time: { en: "About {minutes} minutes.", el: "Περίπου {minutes} λεπτά." },
  overview_ingredients: { en: "You need {count} ingredients: {list}.", el: "Χρειάζεσαι {count} υλικά: {list}." },
  overview_doneness: { en: "How do you like it cooked: {options}?", el: "Πώς σου αρέσει το ψήσιμο: {options};" },
  overview_next: {
    en: "Say “check ingredients” to show them to the camera, or “start” when you're ready.",
    el: "Πες «έλεγξε τα υλικά» για να τα δω με την κάμερα, ή «ξεκίνα» όταν είσαι έτοιμος.",
  },
  ingredients_list: { en: "You need: {list}.", el: "Χρειάζεσαι: {list}." },
  ingredients_missing: { en: "Not ticked yet: {list}.", el: "Δεν έχουν σημειωθεί ακόμα: {list}." },
  ingredients_all: { en: "Everything's ticked. Say “start” when you're ready.", el: "Όλα σημειωμένα. Πες «ξεκίνα» όταν είσαι έτοιμος." },
  or: { en: "or", el: "ή" },

  // --- steps ---
  step_n_of: { en: "Step {n} of {total}.", el: "Βήμα {n} από {total}." },
  step_timer_hint: {
    en: "It takes about {human}. Say “start timer” when you begin.",
    el: "Θέλει περίπου {human}. Πες «χρονόμετρο» όταν ξεκινήσεις.",
  },
  step_check_prep: { en: "When you're done, say “check it” and I'll take a look.", el: "Όταν τελειώσεις, πες «έλεγξε» να ρίξω μια ματιά." },
  step_check_cook: { en: "Say “check it” whenever you want me to look.", el: "Πες «έλεγξε» όποτε θέλεις να ρίξω μια ματιά." },
  step_target: { en: "For {pref}, aim for {temp}°C inside.", el: "Για {pref}, στόχος {temp}°C στο εσωτερικό." },
  recipe_done: { en: "That's the last step - enjoy your meal!", el: "Αυτό ήταν το τελευταίο βήμα - καλή όρεξη!" },
  recipe_stopped: { en: "Recipe stopped.", el: "Η συνταγή σταμάτησε." },

  // --- questions the cook answers yes/no ---
  ask_advance: { en: "Shall we move on to the next step?", el: "Να πάμε στο επόμενο βήμα;" },
  ask_finish: { en: "That was the last step. Shall I finish the recipe?", el: "Ήταν το τελευταίο βήμα. Να κλείσω τη συνταγή;" },
  ask_add_time: { en: "Shall I add {human} to the timer?", el: "Να προσθέσω {human} στο χρονόμετρο;" },
  ask_set_timer: { en: "Shall I set a timer for {human}?", el: "Να βάλω χρονόμετρο για {human};" },
  ask_stop: { en: "Stop the recipe?", el: "Να σταματήσω τη συνταγή;" },
  ok_wait: {
    en: "OK. Say “check it” when you want me to look again.",
    el: "Εντάξει. Πες «έλεγξε» όταν θες να ξανακοιτάξω.",
  },

  // --- timers ---
  timer_started: { en: "Timer: {human}.", el: "Χρονόμετρο: {human}." },
  timer_added: { en: "Added {human}.", el: "Πρόσθεσα {human}." },
  timer_removed: { en: "Took off {human}.", el: "Αφαίρεσα {human}." },
  timer_done_label: { en: "Time's up: {label}.", el: "Τέλος χρόνου: {label}." },
  timer_done_check: { en: "Say “check it” and I'll look.", el: "Πες «έλεγξε» να ρίξω μια ματιά." },
  timer_label_step: { en: "step {n}", el: "βήμα {n}" },
  timer_label_custom: { en: "timer", el: "χρονόμετρο" },
  timer_left: { en: "{time} left on {label}.", el: "Απομένουν {time} για {label}." },
  no_timer: { en: "No timer is running.", el: "Δεν τρέχει χρονόμετρο." },
  how_long: {
    en: "For how long? Say, for example, “timer five minutes”.",
    el: "Για πόση ώρα; Πες για παράδειγμα «χρονόμετρο πέντε λεπτά».",
  },
  unit_h: { en: ["hour", "hours"], el: ["ώρα", "ώρες"] },
  unit_m: { en: ["minute", "minutes"], el: ["λεπτό", "λεπτά"] },
  unit_s: { en: ["second", "seconds"], el: ["δευτερόλεπτο", "δευτερόλεπτα"] },

  // --- doneness (meat) ---
  done_rare: { en: "rare", el: "σενιάν" },
  done_medium_rare: { en: "medium-rare", el: "μέτρια προς σενιάν" },
  done_medium: { en: "medium", el: "μέτρια" },
  done_medium_well: { en: "medium-well", el: "μέτρια προς καλοψημένο" },
  done_well_done: { en: "well done", el: "καλοψημένο" },
  doneness_set: { en: "Got it: {name}.", el: "Εντάξει, {name}." },

  // --- on-screen labels (data-label in index.html) ---
  identify: { en: "What is this?", el: "Τι είναι αυτό;" },
  recipes: { en: "Recipes", el: "Συνταγές" },
  check: { en: "Check it", el: "Έλεγξε" },
  repeat: { en: "Repeat", el: "Επανάλαβε" },
  next: { en: "Next", el: "Επόμενο" },
  previous: { en: "Previous", el: "Προηγούμενο" },
  stop: { en: "Stop", el: "Διακοπή" },
  back: { en: "Back", el: "Πίσω" },
  answer_yes: { en: "Yes", el: "Ναι" },
  answer_no: { en: "No", el: "Όχι" },
  ingredients: { en: "Ingredients", el: "Υλικά" },
  read_ingredients: { en: "Read ingredients", el: "Πες τα υλικά" },
  check_ingredients: { en: "Check with camera", el: "Έλεγχος με κάμερα" },
  start_cooking: { en: "Start cooking", el: "Ξεκίνα" },
  start_timer: { en: "Timer {time}", el: "Χρονόμετρο {time}" },
  add_minute: { en: "+1 min", el: "+1 λεπτό" },
  sub_minute: { en: "−1 min", el: "−1 λεπτό" },
  stop_timer: { en: "Stop timer", el: "Σταμάτα" },
  send: { en: "Send", el: "Στείλε" },
  ask_placeholder: { en: "Type a command or a question…", el: "Γράψε εντολή ή ερώτηση…" },
  ask_label: { en: "Type instead of speaking", el: "Γράψε αντί να μιλήσεις" },
  log_you: { en: "You", el: "Εσύ" },
  log_chef: { en: "Chef", el: "Σεφ" },
  log_title: { en: "Conversation", el: "Συνομιλία" },
  alert_ok: { en: "OK", el: "Εντάξει" },
  doneness_title: { en: "Doneness", el: "Ψήσιμο" },

  // --- spoken descriptions of the new buttons ---
  speak_wake_toggle: {
    en: "Hands-free. When it's on, say “Hey chef” and then what you need - no need to touch anything.",
    el: "Χωρίς χέρια. Όταν είναι ενεργό, πες «Γεια σου σεφ» και μετά τι θέλεις - χωρίς να αγγίξεις τίποτα.",
  },
  speak_previous: { en: "Previous. Goes back one step.", el: "Προηγούμενο. Πηγαίνει ένα βήμα πίσω." },
  speak_ingredients: { en: "Ingredients. Reads the ingredients again.", el: "Υλικά. Λέει ξανά τα υλικά." },
  speak_read_ingredients: { en: "Read ingredients. Reads the list out loud.", el: "Πες τα υλικά. Διαβάζει δυνατά τη λίστα." },
  speak_check_ingredients: {
    en: "Check with camera. Show me your ingredients and I'll tick the ones I can see.",
    el: "Έλεγχος με κάμερα. Δείξε μου τα υλικά σου και θα σημειώσω όσα βλέπω.",
  },
  speak_start_cooking: { en: "Start cooking. Goes to the first step.", el: "Ξεκίνα. Πηγαίνει στο πρώτο βήμα." },
  speak_start_timer: { en: "Timer. Starts this step's timer.", el: "Χρονόμετρο. Ξεκινά το χρονόμετρο του βήματος." },
  speak_add_minute: { en: "Adds one minute to the timer.", el: "Προσθέτει ένα λεπτό στο χρονόμετρο." },
  speak_sub_minute: { en: "Takes one minute off the timer.", el: "Αφαιρεί ένα λεπτό από το χρονόμετρο." },
  speak_stop_timer: { en: "Stops this timer.", el: "Σταματά αυτό το χρονόμετρο." },
  speak_send: { en: "Send. Sends what you typed.", el: "Στείλε. Στέλνει αυτό που έγραψες." },
  speak_alert_ok: { en: "OK. Closes the alert.", el: "Εντάξει. Κλείνει την ειδοποίηση." },

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

// t() with {placeholders} filled in; an unknown placeholder is left as written.
export function tf(key, lang, vars = {}) {
  return t(key, lang).replace(/\{(\w+)\}/g, (match, name) => (name in vars ? String(vars[name]) : match));
}

// "1 hour 5 minutes" / "40 λεπτά" - for speech, where "40:00" reads badly.
export function humanDuration(seconds, lang = "el") {
  const total = Math.round(Math.abs(seconds));
  const parts = [
    [Math.floor(total / 3600), "unit_h"],
    [Math.floor((total % 3600) / 60), "unit_m"],
    [total % 60, "unit_s"],
  ]
    .filter(([n]) => n)
    .map(([n, key]) => `${n} ${t(key, lang)[n === 1 ? 0 : 1]}`);
  return parts.join(" ") || `0 ${t("unit_s", lang)[1]}`;
}
