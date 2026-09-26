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
    // "Hey chef" however the recognizer spells it.
    ["Χέι σεφ επόμενο", true, "επόμενο"],
    ["Χέι Σεφ, θέλω να φτιάξω ροσμπίφ", true, "θέλω να φτιάξω ροσμπίφ"],
    ["έι σεφ", true, ""],
    ["εϊ σεφ πόση ώρα μένει", true, "πόση ώρα μένει"],
    ["okay so hey chef repeat", true, "repeat"],
    ["heychef stop", true, "stop"],
    ["hey there", false, ""],
    // The name, said to the app, is the wake word - measured: Chrome's Greek recognizer drops the
    // "Χέι" ("Χέι σεφ, επόμενο βήμα" -> "chef επόμενο βήμα") but writes "γεια σου σεφ" whole.
    ["chef επόμενο βήμα", true, "επόμενο βήμα"],
    ["σεφ, επόμενο βήμα", true, "επόμενο βήμα"],
    ["Σεφ", true, ""],
    ["Γεια σου σεφ", true, ""],
    ["γεια σου σεφ επόμενο βήμα", true, "επόμενο βήμα"],
    ["για σου σεφ πόση ώρα μένει", true, "πόση ώρα μένει"], // "γεια" and "για" sound the same
    ["πόση ώρα μένει σεφ", true, ""], // the name last: waits for the command
    ["ok chef next", true, "next"],
    // Talk *about* a chef - the TV, the table - doesn't wake it.
    ["the chef said it's done", false, ""],
    ["ο σεφ είπε ότι είναι έτοιμο", false, ""],
    ["μαγειρεύει σαν σεφ", false, ""],
    ["ρώτα τον σεφ", false, ""],
    ["my chef friend", false, ""],
    // Heard on a real microphone (feature/detection-db's list): "ε σεφ", "he chef".
    ["ε σεφ επόμενο", true, "επόμενο"],
    ["he chef next step", true, "next step"],
    // Chrome's Greek recognizer drops the φ once a command follows - after a clear "hey" only.
    ["χέι σε επόμενο βήμα", true, "επόμενο βήμα"],
    ["hey σε επόμενο", true, "επόμενο"],
    ["χέι σε", false, ""],
    ["ε σε λίγο θα είναι έτοιμο", false, ""], // "eh, in a moment it'll be ready" - everyday Greek
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
