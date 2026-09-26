// Push-to-talk: records only while the talk button (or the V key) is held - never an always-on
// microphone, so a TV or a visitor can't issue commands the rest of the time.

const PREFERRED_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];

export const MIN_MS = 300; // shorter than this is an accidental tap, not a command
export const MAX_MS = 15000; // a held button stops itself

export function pickMimeType(Recorder) {
  if (!Recorder || typeof Recorder.isTypeSupported !== "function") return "";
  return PREFERRED_TYPES.find((t) => Recorder.isTypeSupported(t)) || "";
}

export function createPushToTalk({
  getStream, // async () => MediaStream (microphone)
  send, // async (blob, mimeType) => server response
  onState = () => {}, // "listening" | "thinking" | "idle"
  onResult = () => {}, // (response) or (null, "too_short")
  onError = () => {},
  Recorder = globalThis.MediaRecorder,
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

  async function finish(rec) {
    const duration = now() - startedAt;
    const type = (rec.mimeType || pickMimeType(Recorder) || "audio/webm").split(";")[0];
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
    starting = (async () => {
      const stream = await getStream();
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

  return {
    start,
    stop,
    isRecording: () => recorder !== null,
    isBusy: () => busy,
  };
}
