// Push-to-talk: records only while the talk button (or the V key) is held - never an always-on
// microphone, so a TV or a visitor can't issue commands the rest of the time.

const PREFERRED_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];

export const MIN_MS = 300; // shorter than this is an accidental tap, not a command
export const MAX_MS = 15000; // a held button stops itself

export function pickMimeType(Recorder) {
  if (!Recorder || typeof Recorder.isTypeSupported !== "function") return "";
  return PREFERRED_TYPES.find((t) => Recorder.isTypeSupported(t)) || "";
}

// Tap-to-talk without browser speech recognition (Firefox): record until the cook stops talking.
// Levels are RMS of the microphone signal (0-1). The first CALIBRATE_MS set the room's noise
// floor, so a humming extractor fan isn't mistaken for speech.
export const CALIBRATE_MS = 250;
export const SPEECH_MIN_MS = 150; // this long above the threshold = someone is talking
export const SILENCE_MS = 1200; // this long below it after speech = they've finished
export const NO_SPEECH_MS = 6000; // nothing said at all

export function createSilenceDetector({ now = () => Date.now(), minThreshold = 0.015, factor = 2.5 } = {}) {
  const startedAt = now();
  let floorSum = 0;
  let floorCount = 0;
  let threshold = minThreshold;
  let loudSince = null;
  let quietSince = null;
  let heard = false;

  // -> "calibrating" | "waiting" | "speaking" | "done" | "no_speech"
  return function feed(level) {
    const t = now();
    if (t - startedAt < CALIBRATE_MS) {
      floorSum += level;
      floorCount += 1;
      threshold = Math.max(minThreshold, (floorSum / floorCount) * factor);
      return "calibrating";
    }
    if (level >= threshold) {
      quietSince = null;
      if (loudSince === null) loudSince = t;
      if (t - loudSince >= SPEECH_MIN_MS) heard = true;
    } else {
      loudSince = null;
      if (quietSince === null) quietSince = t;
    }
    if (heard) return quietSince !== null && t - quietSince >= SILENCE_MS ? "done" : "speaking";
    return t - startedAt >= NO_SPEECH_MS ? "no_speech" : "waiting";
  };
}

export function createPushToTalk({
  getStream, // async () => MediaStream (microphone)
  send, // async (blob, mimeType) => server response
  onState = () => {}, // "listening" | "thinking" | "idle"
  onResult = () => {}, // (response) or (null, "too_short")
  onError = () => {},
  Recorder = globalThis.MediaRecorder,
  // (stream) => { read() -> RMS level, close() } - only needed for autoStop()
  meter = null,
  setTimer = (fn, ms) => setTimeout(fn, ms),
  clearTimer = (id) => clearTimeout(id),
  now = () => Date.now(),
}) {
  let recorder = null;
  let chunks = [];
  let startedAt = 0;
  let stopTimer = null;
  let busy = false;
  let starting = null;
  let stopRequested = false;
  let discard = false;
  let stream = null;
  let watch = null; // { timer, gauge } while autoStop() listens for the end of speech
  let noSpeech = false;

  function endWatch() {
    if (!watch) return;
    clearTimer(watch.timer);
    try {
      watch.gauge.close();
    } catch {
      // already closed
    }
    watch = null;
  }

  async function finish(rec) {
    endWatch();
    const duration = now() - startedAt;
    const type = (rec.mimeType || pickMimeType(Recorder) || "audio/webm").split(";")[0];
    if (discard) {
      discard = false;
      onState("idle");
      if (noSpeech) {
        noSpeech = false;
        onResult(null, "no_speech");
      }
      return;
    }
    if (duration < MIN_MS || chunks.length === 0) {
      onState("idle");
      onResult(null, "too_short");
      return;
    }
    busy = true;
    onState("thinking");
    try {
      onResult(await send(new Blob(chunks, { type }), type));
    } catch (err) {
      onError(err);
    } finally {
      busy = false;
      onState("idle");
    }
  }

  async function start() {
    if (recorder || busy || starting) return;
    stopRequested = false;
    discard = false;
    noSpeech = false;
    starting = (async () => {
      stream = await getStream();
      const mimeType = pickMimeType(Recorder);
      const rec = new Recorder(stream, mimeType ? { mimeType } : undefined);
      chunks = [];
      rec.ondataavailable = (e) => {
        if (e.data && e.data.size) chunks.push(e.data);
      };
      rec.onstop = () => finish(rec);
      recorder = rec;
      startedAt = now();
      rec.start();
      stopTimer = setTimer(stop, MAX_MS);
      onState("listening");
    })();
    try {
      await starting;
    } catch (err) {
      recorder = null;
      onState("idle");
      onError(err);
    } finally {
      starting = null;
    }
    if (stopRequested) stop(); // released before the microphone was even ready
  }

  function stop() {
    if (!recorder) {
      if (starting) stopRequested = true;
      return;
    }
    clearTimer(stopTimer);
    const rec = recorder;
    recorder = null;
    rec.stop(); // -> onstop -> finish()
  }

  // Stop without sending anything.
  function cancel() {
    if (!recorder && !starting) return;
    discard = true;
    stop();
  }

  // A tap instead of a hold: keep recording until the cook has spoken and gone quiet.
  async function autoStop() {
    if (!meter) {
      stop();
      return;
    }
    if (starting) await starting.catch(() => {});
    if (!recorder || watch) return;
    const gauge = meter(stream);
    const feed = createSilenceDetector({ now });
    watch = { gauge, timer: null };
    const poll = () => {
      if (!watch || !recorder) return;
      const verdict = feed(gauge.read());
      if (verdict === "done") {
        stop();
      } else if (verdict === "no_speech") {
        noSpeech = true;
        cancel();
      } else {
        watch.timer = setTimer(poll, 50);
      }
    };
    poll();
  }

  return {
    start,
    stop,
    cancel,
    autoStop,
    isRecording: () => recorder !== null,
    isBusy: () => busy,
  };
}
