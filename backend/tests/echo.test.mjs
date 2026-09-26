// echo.js: the app's own voice taken out of what the microphone heard, the cook's words kept.

const { stripEcho } = await import("../static/js/echo.js");

function assert(cond, message) {
  if (!cond) throw new Error("assertion failed: " + message);
}

const said = ["Χρειάζεσαι: 200 γρ. αλεύρι, 2 αυγά, 300 ml γάλα, 30 γρ. βούτυρο."];

// Seen live: the tail of the ingredient list, then the cook.
assert(stripEcho("2 αυγά Okay έχω συλλέξει τα πάντα", said) === "Okay έχω συλλέξει τα πάντα",
  `the echo at the start goes: ${stripEcho("2 αυγά Okay έχω συλλέξει τα πάντα", said)}`);
// A long run of the app's words anywhere goes too.
assert(stripEcho("ναι 300 ml γάλα 30 γρ βούτυρο έχω", said) === "ναι έχω",
  `a long run goes: ${stripEcho("ναι 300 ml γάλα 30 γρ βούτυρο έχω", said)}`);
// But the cook repeating a short part of it is the cook: "I have the 2 eggs".
assert(stripEcho("έχω τα 2 αυγά", said) === "έχω τα 2 αυγά", "a short match after the cook's own words stays");
// A command the app suggested is still a command.
const hint = ["Πες «ξεκίνα» όταν είσαι έτοιμος, ή «επόμενο βήμα»."];
assert(stripEcho("ξεκίνα", hint) === "ξεκίνα", "one word the app said stays");
assert(stripEcho("θέλω επόμενο βήμα", hint) === "θέλω επόμενο βήμα", "a short match mid-sentence stays");
// Case and accents don't hide an echo; nothing said recently, nothing removed.
assert(stripEcho("ΑΛΕΥΡΙ 2 αυγα και ξεκινάμε", said) === "και ξεκινάμε", `folded: ${stripEcho("ΑΛΕΥΡΙ 2 αυγα και ξεκινάμε", said)}`);
assert(stripEcho("2 αυγά Okay", []) === "2 αυγά Okay", "no recent speech: untouched");
assert(stripEcho("", said) === "", "empty stays empty");
// Everything was the app: nothing left to act on.
assert(stripEcho("300 ml γάλα 30 γρ βούτυρο", said) === "", "all echo -> empty");

console.log("all passed");
