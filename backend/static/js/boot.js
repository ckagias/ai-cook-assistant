import { probeVoices, registerAcousticGate } from "./tts.js";

export const caps = {
  video: false,
  audioIn: false,
  wakeLock: false,
  vibrate: false,
  audioCtx: null,
  stream: null,
  micStream: null,
  lang: "el",
};

let wakeLockSentinel = null;

async function acquireWakeLock() {
  if (!("wakeLock" in navigator)) return false;
  try {
    wakeLockSentinel = await navigator.wakeLock.request("screen");
    return true;
  } catch (err) {
    return false;
  }
}

function registerWakeLockReacquire() {
  // A wake lock is released automatically whenever the page hides - a one-shot
  // request silently stops working the moment a notification steals focus.
  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState === "visible") {
      caps.wakeLock = await acquireWakeLock();
    }
  });
}

export async function boot(preferredLang = "el") {
  const warnings = [];

  if (!window.isSecureContext || !navigator.mediaDevices) {
    throw new Error("Insecure context or no media device support - camera/mic access needs HTTPS.");
  }

  // Audio out. Warn, don't throw, if resume() fails.
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  caps.audioCtx = new AudioContextCtor();
  try {
    await caps.audioCtx.resume();
  } catch (err) {
    warnings.push("Could not start the audio output context.");
  }

  // Camera. "ideal", never "exact" - exact throws OverconstrainedError on a
  // front-camera-only device. Fatal if this fails, since there is no app without it.
  try {
    caps.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 } },
    });
    caps.video = true;
    const videoTrack = caps.stream.getVideoTracks()[0];
    const settings = videoTrack ? videoTrack.getSettings() : {};
    if (settings.facingMode && settings.facingMode !== "environment") {
      warnings.push("Could not confirm the rear camera is in use.");
    }
  } catch (err) {
    throw new Error("Camera access failed: " + err.name);
  }

  // Mic. All three constraints OFF or AGC drifts the noise-floor threshold and
  // noise suppression removes sizzle. Not fatal if refused.
  try {
    caps.micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
    });
    caps.audioIn = true;
    const audioTrack = caps.micStream.getAudioTracks()[0];
    const audioSettings = audioTrack ? audioTrack.getSettings() : {};
    if (audioSettings.noiseSuppression || audioSettings.autoGainControl) {
      warnings.push("Microphone processing could not be fully disabled - sizzle detection may be unreliable.");
    }
  } catch (err) {
    warnings.push("Microphone access was not granted.");
  }

  // Wake lock.
  caps.wakeLock = await acquireWakeLock();
  registerWakeLockReacquire();

  // Vibration - claim it inside this gesture, same as iOS needs for audio/mic/camera.
  if (navigator.vibrate) {
    caps.vibrate = navigator.vibrate(1);
  }

  // Voice.
  caps.lang = await probeVoices(preferredLang);
  if (caps.lang !== preferredLang) {
    warnings.push("No Greek voice was found - falling back to English speech.");
  }

  // Registered explicitly, even as a no-op - see the note in tts.js.
  registerAcousticGate(() => {});

  return warnings;
}

export function earcon(kind = "ok") {
  if (!caps.audioCtx) return;
  const freqs = { ok: 880, done: 1320, error: 220, wait: 560 };
  const freq = freqs[kind] ?? freqs.ok;

  const osc = caps.audioCtx.createOscillator();
  const gain = caps.audioCtx.createGain();
  osc.frequency.value = freq;
  osc.connect(gain);
  gain.connect(caps.audioCtx.destination);

  const now = caps.audioCtx.currentTime;
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(0.25, now + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.22);

  osc.start(now);
  osc.stop(now + 0.24);
}

export function buzz(pattern = 40) {
  if (caps.vibrate) {
    navigator.vibrate(pattern);
  }
}
