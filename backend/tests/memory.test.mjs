// memory.js: one recipe's short-term memory - kept per recipe, picked up again the same day,
// forgotten after that, and summarized for the assistant without ever dropping the cook's
// needs and preferences.

const { createMemory, MEMORY_TTL_MS, MAX_CHARS } = await import("../static/js/memory.js");

function assert(cond, message) {
  if (!cond) throw new Error("assertion failed: " + message);
}

function setup() {
  const store = new Map();
  let clock = 1_000_000;
  const storage = { get: (k) => store.get(k) ?? null, set: (k, v) => store.set(k, v), remove: (k) => store.delete(k) };
  return { store, advance: (ms) => (clock += ms), make: () => createMemory({ storage, now: () => clock }) };
}

function testRecordsAndSummarizes() {
  const s = setup();
  const m = s.make();
  assert(m.open("roast_beef") === false, "a first visit is not a resume");
  m.addPreference("λιγότερο αλάτι");
  m.addPreference("λιγότερο αλάτι"); // said twice, kept once
  m.setDoneness("medium_rare");
  m.note("step", "Βήμα 5: Χαμήλωσε τον φούρνο", { step: 4 });
  s.advance(10 * 60 * 1000);
  m.note("check", "Έλεγχος, βήμα 5: όχι ακόμα. ανοιχτό καφέ - χρειάζεται 10 λεπτά", { step: 4 });
  const text = m.summary();
  assert(text.startsWith("Cook's needs and preferences: λιγότερο αλάτι."), `prefs first: ${text}`);
  assert(text.includes("Doneness chosen: medium rare") && text.includes("Furthest step reached: 5."), text);
  assert(text.includes("[10 min ago] step: Βήμα 5") && text.includes("[0 min ago] check: Έλεγχος"), text);
  console.log("test a (records and summarizes) OK");
}

function testPickedUpTheSameDayForgottenAfter() {
  const s = setup();
  const first = s.make();
  first.open("tzatziki");
  first.note("step", "Βήμα 2", { step: 1 });
  first.close();
  s.advance(3 * 3600 * 1000);
  const later = s.make(); // a page reload
  assert(later.open("tzatziki") === true && later.lastStep() === 1, "picked up where it was left");
  assert(later.open("pasta") === false && later.events().length === 0, "another recipe has its own memory");
  s.advance(MEMORY_TTL_MS + 1);
  assert(s.make().open("tzatziki") === false, "forgotten after a day");
  console.log("test b (picked up the same day, forgotten after) OK");
}

function testSummaryKeepsPrefsAndTheNewestEventsWithinTheCap() {
  const s = setup();
  const m = s.make();
  m.open("briam");
  m.addPreference("αλλεργία σε ξηρούς καρπούς");
  for (let i = 0; i < 80; i++) m.note("answer", `ερώτηση ${i} → ${"απάντηση ".repeat(20)}`);
  const text = m.summary();
  assert(text.length <= MAX_CHARS, `capped: ${text.length}`);
  assert(text.includes("αλλεργία σε ξηρούς καρπούς"), "an allergy is never dropped to make room");
  assert(text.includes("ερώτηση 79") && !text.includes("ερώτηση 10 "), "the newest events win");
  assert(m.events().length === 60, "the event list itself is bounded");
  console.log("test c (prefs always kept, newest events within the cap) OK");
}

function testResetAndNoRecipe() {
  const s = setup();
  const m = s.make();
  assert(m.summary() === "" && m.prefs().length === 0, "nothing open: empty");
  m.note("step", "ignored"); // no recipe open - no crash, nothing stored
  m.open("pasta");
  m.note("step", "Βήμα 1", { step: 0 });
  m.reset();
  assert(m.events().length === 0 && m.lastStep() === null, "reset starts the recipe over");
  assert(s.make().open("pasta") === false, "and the stored copy is fresh too");
  console.log("test d (reset; nothing open) OK");
}

testRecordsAndSummarizes();
testPickedUpTheSameDayForgottenAfter();
testSummaryKeepsPrefsAndTheNewestEventsWithinTheCap();
testResetAndNoRecipe();

console.log("all passed");
