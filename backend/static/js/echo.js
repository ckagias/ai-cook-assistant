// The microphone hears the app's own voice as well as the cook's, so a transcript can start with the
// tail of what the app was saying: "2 αυγά Okay έχω συλλέξει τα πάντα" - "2 αυγά" was the app
// reading the ingredient list. The app knows exactly what it said, so its words are taken out
// by comparing texts, and the cook's words are kept.
//
// Only two kinds of match are removed, so a cook who repeats a command the app just suggested
// ("say «next step»" -> "next step") still gets it:
//   - the app's words at the START of what was heard (where the echo sits: the recognizer was
//     still hearing the app when the cook began), two words or more;
//   - a run of MIN_LONG_RUN words or more anywhere - too long to be a coincidence.

import { fold } from "./commands.js";

export const MIN_START_RUN = 2;
export const MIN_LONG_RUN = 3;

function tokens(text) {
  return fold(text).split(" ").filter(Boolean);
}

// How many words from `heard[i]` on appear, in order and contiguous, in one of `said`.
function runAt(heard, i, saidTexts) {
  let best = 0;
  for (const said of saidTexts) {
    for (let s = 0; s < said.length; s++) {
      let n = 0;
      while (i + n < heard.length && s + n < said.length && heard[i + n] === said[s + n]) n += 1;
      if (n > best) best = n;
    }
  }
  return best;
}

// heard: the transcript. said: texts the app spoke recently (tts.recentSpeech()).
export function stripEcho(heard, said = []) {
  const original = (heard || "").split(/\s+/).filter(Boolean);
  if (!original.length || !said.length) return (heard || "").trim();
  // Word by word, keeping the original spelling for what stays.
  const words = original.map((w) => ({ w, t: tokens(w).join(" ") })).filter((x) => x.t);
  const heardTokens = words.map((x) => x.t);
  const saidTokens = said.map(tokens).filter((t) => t.length);
  const keep = new Array(words.length).fill(true);
  let i = 0;
  while (i < words.length) {
    const n = runAt(heardTokens, i, saidTokens);
    const atStart = keep.slice(0, i).every((k) => !k); // nothing of the cook's before it yet
    if ((atStart && n >= MIN_START_RUN) || n >= MIN_LONG_RUN) {
      for (let k = i; k < i + n; k++) keep[k] = false;
      i += n;
    } else {
      i += 1;
    }
  }
  return words.filter((_, k) => keep[k]).map((x) => x.w).join(" ").trim();
}
