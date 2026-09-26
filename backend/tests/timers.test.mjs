// timers.js and session.js: timers the cook starts, several at once, deadlines that survive a
// hidden tab; and the overview -> steps flow.

const { createTimers, formatClock } = await import("../static/js/timers.js");
const { createSession } = await import("../static/js/session.js");

function assert(cond, message) {
  if (!cond) throw new Error("assertion failed: " + message);
}

function setup() {
  let clock = 1_000_000;
  let ticker = null;
  const expired = [];
  const ticks = [];
  const listeners = {};
  const doc = {
    visibilityState: "visible",
    addEventListener: (name, fn) => (listeners[name] = fn),
  };
  const timers = createTimers({
    now: () => clock,
    every: (fn) => (ticker = fn),
    doc,
    onExpired: (tm) => expired.push(tm),
    onTick: (list) => ticks.push(list),
  });
  return {
    timers,
    expired,
    ticks,
    advance(ms) {
      clock += ms;
      ticker();
    },
    wake(ms) {
      clock += ms; // the tab was hidden - no ticks at all
      listeners.visibilitychange();
    },
  };
}

function testSeveralTimersAtOnce() {
  const s = setup();
  s.timers.start("sauce", 20 * 60, { label: "step 4", stepIndex: 3 });
  s.timers.start("pasta", 10 * 60, { label: "step 6", stepIndex: 5 });
  assert(s.timers.list().map((t) => t.key).join() === "pasta,sauce", "soonest first");
  s.advance(10 * 60 * 1000);
  assert(s.expired.length === 1 && s.expired[0].key === "pasta" && s.expired[0].label === "step 6", "pasta rang");
  assert(s.timers.get("sauce").remainingMs === 10 * 60 * 1000, "the sauce keeps going");
  s.advance(1000);
  assert(s.expired.length === 1, "rings once");
  console.log("test a (several timers at once) OK");
}

function testAddAndTakeOffTime() {
  const s = setup();
  s.timers.start("t", 300);
  s.advance(100 * 1000);
  const more = s.timers.add("t", 120);
  assert(more.remainingMs === 320 * 1000 && more.totalMs === 420 * 1000, `more: ${JSON.stringify(more)}`);
  assert(more.elapsedMs === 100 * 1000, "elapsed is unchanged by adding time");
  s.timers.add("t", -60);
  assert(s.timers.get("t").remainingMs === 260 * 1000, "less");
  assert(s.timers.add("t", -9999) === null && s.expired.length === 1, "taking off more than is left ends it now");
  assert(s.timers.add("nope", 60) === null, "unknown timer");
  console.log("test b (more and less time) OK");
}

function testDeadlineSurvivesAHiddenTab() {
  const s = setup();
  s.timers.start("oven", 60);
  s.wake(5 * 60 * 1000);
  assert(s.expired.length === 1, "a deadline that passed while hidden fires on return");
  console.log("test c (deadline survives a hidden tab) OK");
}

function testStopAndClear() {
  const s = setup();
  s.timers.start("a", 60);
  s.timers.start("b", 60);
  assert(s.timers.stop("a") && !s.timers.stop("a"), "stop once");
  s.timers.clear();
  assert(s.timers.list().length === 0 && s.ticks.at(-1).length === 0, "cleared and redrawn");
  s.advance(120 * 1000);
  assert(s.expired.length === 0, "a stopped timer never rings");
  console.log("test d (stop and clear) OK");
}

function testFormatClock() {
  assert(formatClock(0) === "0:00" && formatClock(61_000) === "1:01", "minutes");
  assert(formatClock(59_001) === "1:00", "rounds up - never shows 0:00 while time is left");
  assert(formatClock(3_725_000) === "1:02:05", "hours");
  console.log("test e (clock format) OK");
}

function testSessionOverviewThenSteps() {
  const session = createSession();
  const recipe = { id: "r", steps: [{ index: 0 }, { index: 1 }] };
  session.setRecipe(recipe);
  assert(session.getPhase() === "overview" && session.currentStep() === null, "opens at the ingredients");
  assert(session.next() && session.getPhase() === "steps" && session.currentStep().index === 0, "next starts the steps");
  assert(!session.isLastStep() && session.next() && session.isLastStep(), "last step");
  assert(!session.next(), "no step after the last");
  assert(session.goTo(0) && session.currentStep().index === 0 && !session.goTo(5), "goTo bounds");
  session.setRecipe(null);
  assert(session.getPhase() === null && session.currentStep() === null, "closed");
  console.log("test f (session: overview, then steps) OK");
}

testSeveralTimersAtOnce();
testAddAndTakeOffTime();
testDeadlineSurvivesAHiddenTab();
testStopAndClear();
testFormatClock();
testSessionOverviewThenSteps();

console.log("all passed");
