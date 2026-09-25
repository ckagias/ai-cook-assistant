export function createSession({ onTick, onExpired } = {}) {
  let recipe = null;
  let stepIndex = 0;
  // Absolute end timestamp, never a decrementing counter - a backgrounded tab
  // throttles to 1 tick/s then 1/min, and a locked screen can freeze JS
  // outright; only an absolute deadline survives that.
  let endsAt = null;
  let firedFor = null;

  function recompute() {
    if (endsAt === null) {
      if (onTick) onTick(0, stepIndex);
      return;
    }
    const remaining = Math.max(0, endsAt - Date.now());
    if (onTick) onTick(remaining, stepIndex);
    if (remaining === 0 && firedFor !== stepIndex) {
      firedFor = stepIndex;
      endsAt = null;
      if (onExpired) onExpired(stepIndex);
    }
  }

  setInterval(recompute, 1000);
  // A deadline that passed while backgrounded still fires on resume instead of being lost.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      recompute();
    }
  });

  function setRecipe(newRecipe) {
    recipe = newRecipe;
    stepIndex = 0;
    endsAt = null;
    firedFor = null;
  }

  function getRecipe() {
    return recipe;
  }

  function getStepIndex() {
    return stepIndex;
  }

  function currentStep() {
    if (!recipe) return null;
    return recipe.steps[stepIndex] ?? null;
  }

  function goTo(index) {
    if (!recipe) return;
    if (index < 0 || index >= recipe.steps.length) return;
    stepIndex = index;
  }

  function next() {
    if (!recipe) return false;
    if (stepIndex + 1 >= recipe.steps.length) return false;
    stepIndex += 1;
    return true;
  }

  function startTimer(durationSec) {
    endsAt = Date.now() + durationSec * 1000;
    firedFor = null;
  }

  function clearTimer() {
    endsAt = null;
  }

  function remainingMs() {
    if (endsAt === null) return 0;
    return Math.max(0, endsAt - Date.now());
  }

  return {
    setRecipe,
    getRecipe,
    getStepIndex,
    currentStep,
    goTo,
    next,
    startTimer,
    clearTimer,
    remainingMs,
  };
}
