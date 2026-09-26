// commands.js: the wake phrase in every form a Greek or English recognizer writes it, and the
// on-device commands - exact matches only, so free speech still reaches the server.

const { fold, splitWake, matchLocal } = await import("../static/js/commands.js");

function assert(cond, message) {
  if (!cond) throw new Error("assertion failed: " + message);
}

function testFold() {
  assert(fold("Έλεγξέ το!") === "ελεγξε το", "accents and punctuation");
  assert(fold("ΣΕΦ") === "σεφ" && fold("σεφς").endsWith("σ"), "case and final sigma");
  console.log("test a (fold) OK");
}

function testWakePhrase() {
  const cases = [
    ["Hey chef", true, ""],
    ["hey chef, next step", true, "next step"],
    ["Hey Chef I want to make roast beef", true, "I want to make roast beef"],
    ["Γεια σου σεφ", true, ""],
    ["Γειά σου Σεφ, θέλω να φτιάξω ροσμπίφ", true, "θέλω να φτιάξω ροσμπίφ"],
    ["Χέι σεφ επόμενο", true, "επόμενο"],
    ["έι σεφ", true, ""],
    ["okay so hey chef repeat", true, "repeat"],
    ["heychef stop", true, "stop"],
    ["the chef said it's done", false, ""],
    ["hey there", false, ""],
    ["σεφ", false, ""],
    // Heard on a real microphone (feature/detection-db's list): "ε σεφ", "he chef".
    ["ε σεφ επόμενο", true, "επόμενο"],
    ["he chef next step", true, "next step"],
    // Chrome's Greek recognizer, measured: the φ drops once a command follows.
    ["γεια σου σε επόμενο βήμα", true, "επόμενο βήμα"],
    ["γεια σου σε", false, ""],
  ];
  for (const [text, woke, rest] of cases) {
    const got = splitWake(text);
    assert(got.woke === woke && got.rest === rest, `${JSON.stringify(text)} -> ${JSON.stringify(got)}`);
  }
  console.log("test b (wake phrase) OK");
}

function testLocalCommands() {
  const cases = [
    ["next", "next_step"],
    ["Επόμενο βήμα.", "next_step"],
    ["chef, next step please", "next_step"],
    ["Ναι", "yes"],
    ["όχι ακόμα", "no"],
    ["εντάξει", "yes"],
    ["έλεγξέ το", "check_doneness"],
    ["Is it ready?", "check_doneness"],
    ["τελείωσα", "done"],
    ["ξεκίνα", "start"],
    ["βάλε χρονόμετρο", "start_timer"],
    ["σταμάτα το χρονόμετρο", "stop_timer"],
    ["σταμάτα", "hush"],
    ["τι χρειάζομαι", "list_ingredients"],
    ["Τι σκεύη χρειάζομαι;", "list_equipment"],
    ["σκεύη", "list_equipment"],
    ["what tools do I need", "list_equipment"],
    ["έλεγξε τα υλικά", "check_ingredients"],
    ["τι είναι αυτό;", "identify"],
    ["σταμάτα τη συνταγή", "stop_recipe"],
    // Every button has a spoken form, in both languages.
    ["Τι βλέπω;", "identify"],
    ["what do I see", "identify"],
    ["συνταγές", "list_recipes"],
    ["what recipes do you have", "list_recipes"],
    ["βοήθεια", "help"],
    ["what can I say", "help"],
    ["τι κάναμε;", "recap"],
    ["what have we done", "recap"],
    ["πόση ώρα μένει;", "time_left"],
    ["how much time is left", "time_left"],
    ["άνοιξε την ανίχνευση", "detect_on"],
    ["detection off", "detect_off"],
  ];
  for (const [text, action] of cases) {
    const got = matchLocal(text);
    assert(got && got.action === action && got.local && got.heard === text, `${text} -> ${JSON.stringify(got)}`);
  }
  assert(matchLocal("σενιάν").doneness === "rare", "doneness in Greek");
  assert(matchLocal("medium rare").doneness === "medium_rare", "doneness in English");
  assert(matchLocal("το δεύτερο").choice === 2 && matchLocal("3").choice === 3, "recipe numbers");
  console.log("test c (local commands) OK");
}

function testFreeSpeechGoesToTheServer() {
  for (const text of ["θέλω να φτιάξω ροσμπίφ", "set a timer for five minutes", "πόσο λάδι βάζω;", "next time use less salt"]) {
    assert(matchLocal(text) === null, `${text} is not a local command`);
  }
  assert(matchLocal("") === null && matchLocal("   ") === null, "nothing said");
  console.log("test d (free speech is not matched locally) OK");
}

testFold();
testWakePhrase();
testLocalCommands();
testFreeSpeechGoesToTheServer();

console.log("all passed");
