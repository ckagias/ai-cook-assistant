// Where the cook is in the open recipe. Timers live in timers.js: the cook starts them, and one
// may keep running while the cook moves on to the next step.
//
// phase "overview": the recipe is open at its ingredients, no step started yet.
// phase "steps":    working through recipe.steps[stepIndex].
export function createSession() {
  let recipe = null;
  let stepIndex = 0;
  let phase = null;

  return {
    setRecipe(newRecipe) {
      recipe = newRecipe;
      stepIndex = 0;
      phase = newRecipe ? "overview" : null;
    },
    getRecipe: () => recipe,
    getPhase: () => phase,
    getStepIndex: () => stepIndex,
    // null during the overview, so nothing step-shaped happens before the cook starts.
    currentStep() {
      if (!recipe || phase !== "steps") return null;
      return recipe.steps[stepIndex] ?? null;
    },
    beginSteps() {
      if (!recipe || !recipe.steps.length) return false;
      phase = "steps";
      stepIndex = 0;
      return true;
    },
    goTo(index) {
      if (!recipe || index < 0 || index >= recipe.steps.length) return false;
      phase = "steps";
      stepIndex = index;
      return true;
    },
    next() {
      if (phase === "overview") return this.beginSteps();
      return this.goTo(stepIndex + 1);
    },
    isLastStep: () => Boolean(recipe) && phase === "steps" && stepIndex === recipe.steps.length - 1,
  };
}
