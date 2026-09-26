// Words -> action, on the device, for the commands a cook says most: "next", "yes", "start the
// timer", "check it". Exact whole-utterance matches only - anything else goes to the server
// (/voice/text), which understands free speech. Matching here is instant, costs nothing and
// works with no API key at all, so the core of a recipe never waits on the network.
//
// The same shape as the server's VoiceResponse, so app.js runs both the same way. Two extra
// local-only actions: "start" and "done" mean different things before and during the steps.

// Casefold, strip accents (Greek tonos/dialytika too), final sigma -> sigma, punctuation -> space.
export function fold(text) {
  return (text || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/ς/g, "σ")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

// --- the wake phrase: "Hey chef" / "Γεια σου σεφ" ---

// A Greek recognizer may write "Hey chef" in Latin letters or in Greek ("χέι σεφ", "έι σεφ").
const GREETINGS = [["hey"], ["hi"], ["hei"], ["χει"], ["χαι"], ["ει"], ["γεια", "σου"], ["γεια"], ["γειασου"], ["ok"], ["okay"], ["οκ"]];
const NAMES = new Set(["chef", "shef", "sef", "chief", "σεφ", "τσεφ"]);
const JOINED = new Set(["heychef", "heyshef", "χεισεφ", "γειασουσεφ"]);

function words(text) {
  return (text || "").split(/[^\p{L}\p{N}]+/u).filter(Boolean);
}

// { woke, rest }: whether the wake phrase is anywhere in `text`, and the original words after it
// (so "Hey chef, I want to make roast beef" acts at once, without a second round).
export function splitWake(text) {
  const original = words(text);
  const folded = original.map(fold);
  for (let i = 0; i < folded.length; i++) {
    if (JOINED.has(folded[i])) return { woke: true, rest: original.slice(i + 1).join(" ") };
    for (const greeting of GREETINGS) {
      const n = greeting.length;
      if (greeting.every((w, k) => folded[i + k] === w) && NAMES.has(folded[i + n])) {
        return { woke: true, rest: original.slice(i + n + 1).join(" ") };
      }
    }
  }
  return { woke: false, rest: "" };
}

// --- local commands ---

const PHRASES = {
  next_step: ["next", "next step", "go on", "continue", "επομενο", "επομενο βημα", "παμε", "παμε παρακατω", "παρακατω", "συνεχεια", "συνεχισε"],
  previous_step: ["previous", "previous step", "back", "go back", "προηγουμενο", "προηγουμενο βημα", "πισω", "γυρνα πισω"],
  repeat_step: ["repeat", "again", "say again", "say that again", "repeat that", "επαναλαβε", "ξανα", "πες ξανα", "πες το ξανα", "τι ειπες"],
  start: ["start", "begin", "lets start", "ξεκινα", "ξεκιναμε", "αρχισε", "παμε να ξεκινησουμε"],
  done: ["done", "finished", "im done", "i am done", "i m done", "i finished", "ready", "εγινε", "τελειωσα", "τελειωσε", "ετοιμο", "ετοιμος", "ετοιμη", "το εκανα"],
  start_timer: ["start timer", "start the timer", "timer", "set timer", "set the timer", "χρονομετρο", "ξεκινα χρονομετρο", "ξεκινα το χρονομετρο", "βαλε χρονομετρο", "βαλε το χρονομετρο"],
  stop_timer: ["stop timer", "stop the timer", "cancel timer", "cancel the timer", "σταματα χρονομετρο", "σταματα το χρονομετρο", "ακυρωσε το χρονομετρο", "κλεισε το χρονομετρο"],
  check_doneness: ["check", "check it", "check this", "is it ready", "is it done", "evaluate", "evaluate it", "how does it look", "look", "take a look", "ελεγξε", "ελεγξε το", "ελεγχος", "ειναι ετοιμο", "κοιτα", "κοιτα το", "κοιταξε", "αξιολογησε", "αξιολογησε το", "τσεκαρε", "τσεκαρε το", "ριξε μια ματια"],
  check_ingredients: ["check ingredients", "check my ingredients", "check the ingredients", "look at my ingredients", "ελεγξε τα υλικα", "κοιτα τα υλικα", "τσεκαρε τα υλικα", "δες τα υλικα"],
  list_ingredients: ["ingredients", "what do i need", "read the ingredients", "list ingredients", "list the ingredients", "υλικα", "τα υλικα", "συστατικα", "τι χρειαζομαι", "πες τα υλικα", "πες μου τα υλικα", "διαβασε τα υλικα", "ποια υλικα"],
  identify: ["what is this", "whats this", "what s this", "what is that", "τι ειναι αυτο", "τι ειναι αυτο εδω", "τι ειναι"],
  list_recipes: ["recipes", "list recipes", "show recipes", "συνταγες", "δειξε συνταγες", "πες συνταγες"],
  stop_recipe: ["stop recipe", "stop the recipe", "end recipe", "end the recipe", "quit recipe", "σταματα τη συνταγη", "τελος συνταγης", "κλεισε τη συνταγη", "ακυρωσε τη συνταγη"],
  hush: ["stop", "quiet", "silence", "shh", "shush", "σταματα", "σιωπη", "ησυχια", "σουτ", "σκασμος"],
  yes: ["yes", "yeah", "yep", "yes please", "ok", "okay", "sure", "go ahead", "do it", "ναι", "ναι ναι", "ναι παρακαλω", "ενταξει", "οκ", "οκει", "βεβαια", "σωστα", "φυσικα", "κανε το"],
  no: ["no", "nope", "not yet", "no thanks", "οχι", "οχι ακομα", "οχι ακομη", "οχι ευχαριστω", "μη", "οχι τωρα"],
};

const DONENESS = {
  rare: ["rare", "σενιαν", "σενιον"],
  medium_rare: ["medium rare", "μετρια προς σενιαν", "μετρια σενιαν", "μισοψημενο"],
  medium: ["medium", "μετρια", "μετριο", "μετρια ψημενο"],
  medium_well: ["medium well", "μετρια προς καλοψημενο", "μετρια καλοψημενο"],
  well_done: ["well done", "καλοψημενο", "καλα ψημενο", "πολυ ψημενο"],
};

const NUMBERS = {
  1: ["1", "one", "first", "the first", "the first one", "number one", "ενα", "πρωτο", "το πρωτο", "πρωτη", "την πρωτη", "νουμερο ενα", "1ο", "1η"],
  2: ["2", "two", "second", "the second", "the second one", "number two", "δυο", "δευτερο", "το δευτερο", "δευτερη", "τη δευτερη", "την δευτερη", "νουμερο δυο", "2ο", "2η"],
  3: ["3", "three", "third", "the third", "the third one", "number three", "τρια", "τριτο", "το τριτο", "τριτη", "την τριτη", "νουμερο τρια", "3ο", "3η"],
  4: ["4", "four", "fourth", "the fourth", "the fourth one", "τεσσερα", "τεταρτο", "το τεταρτο", "τεταρτη", "την τεταρτη", "4ο", "4η"],
  5: ["5", "five", "fifth", "the fifth", "the fifth one", "πεντε", "πεμπτο", "το πεμπτο", "πεμπτη", "την πεμπτη", "5ο", "5η"],
};

// Politeness and address around a command don't change it: "chef, next step please".
const FILLER = /^(?:(?:please|παρακαλω|σε παρακαλω|chef|σεφ|ok|οκ|and|και|now|τωρα)\s+)+|(?:\s+(?:please|παρακαλω|σε παρακαλω|chef|σεφ|now|τωρα))+$/g;

const TABLE = new Map();
function add(phrases, result) {
  for (const p of phrases) TABLE.set(fold(p), result);
}
for (const [action, phrases] of Object.entries(PHRASES)) add(phrases, { action });
for (const [doneness, phrases] of Object.entries(DONENESS)) add(phrases, { action: "set_doneness", doneness });
for (const [n, phrases] of Object.entries(NUMBERS)) add(phrases, { action: "choose_recipe", choice: Number(n) });

// Returns a VoiceResponse-shaped action, or null when the server should decide.
export function matchLocal(text) {
  let key = fold(text);
  for (let i = 0; i < 3; i++) {
    const stripped = key.replace(FILLER, "").trim();
    if (stripped === key || !stripped) break;
    key = stripped;
  }
  const hit = TABLE.get(key);
  return hit ? { heard: text, spoken_response: "", ...hit, local: true } : null;
}
