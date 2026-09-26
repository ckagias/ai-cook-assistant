import { captureJpegBlob } from "./capture.js";
import * as defaultApi from "./api.js";
import { t } from "./strings.js";

// Okabe-Ito palette: stays distinguishable for the common colour-vision deficiencies.
export const GROUP_COLORS = {
  hand: "#CC79A7",
  utensil: "#56B4E9",
  cookware: "#E69F00",
  appliance: "#F0E442",
  ingredient: "#009E73",
  food: "#0072B2",
  hazard: "#D55E00",
};

const TABLE_INTERVAL_MS = 250; // the table is for reading, not animation - <=4 updates/s
const MAX_ROWS = 20;

// #video uses object-fit: cover, so the frame is scaled to fill the element and the overflow
// cropped equally on both sides. Normalized frame coordinates must go through the same
// transform or every box drifts off its object.
export function coverTransform(viewW, viewH, videoW, videoH) {
  const s = Math.max(viewW / videoW, viewH / videoH);
  return { s, dx: (viewW - videoW * s) / 2, dy: (viewH - videoH * s) / 2, videoW, videoH };
}

export function toViewRect(box, tr) {
  const x = tr.dx + box.x1 * tr.videoW * tr.s;
  const y = tr.dy + box.y1 * tr.videoH * tr.s;
  return {
    x,
    y,
    w: (box.x2 - box.x1) * tr.videoW * tr.s,
    h: (box.y2 - box.y1) * tr.videoH * tr.s,
  };
}

export function toViewPoint(pt, tr) {
  return { x: tr.dx + pt.x * tr.videoW * tr.s, y: tr.dy + pt.y * tr.videoH * tr.s };
}

function hash(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) | 0;
  return Math.abs(h);
}

// Group colour, nudged lighter/darker per class so two classes of one group still differ.
export function classColor(group, classId) {
  const base = GROUP_COLORS[group] || "#FFFFFF";
  const amount = [-0.25, 0, 0.25][hash(classId) % 3];
  const channels = [1, 3, 5].map((i) => parseInt(base.slice(i, i + 2), 16));
  const mixed = channels.map((c) => Math.round(amount < 0 ? c * (1 + amount) : c + (255 - c) * amount));
  return "#" + mixed.map((c) => c.toString(16).padStart(2, "0")).join("");
}

export function handLabel(hand, lang) {
  const side = { Left: t("hand_left", lang), Right: t("hand_right", lang) }[hand.handedness];
  return side || t("hand", lang);
}

// Plain rows for the table: pixel coordinates are in the frame that was sent (e.g. 640x480).
export function buildRows(res, lang) {
  const byObject = new Map();
  for (const rel of res.relations) {
    const hand = res.hands[rel.hand];
    if (!hand) continue;
    const text = `${handLabel(hand, lang)}: ${t("rel_" + rel.kind, lang)}`;
    byObject.set(rel.object, [...(byObject.get(rel.object) || []), text]);
  }
  const px = (v, size) => Math.round(v * size);
  const row = (label, group, colorKey, conf, box, relation) => ({
    label,
    group,
    color: classColor(group, colorKey),
    confidence: Math.round(conf * 100),
    x: px((box.x1 + box.x2) / 2, res.width),
    y: px((box.y1 + box.y2) / 2, res.height),
    w: px(box.x2 - box.x1, res.width),
    h: px(box.y2 - box.y1, res.height),
    relation,
  });

  const rows = res.hands.map((h, i) => row(handLabel(h, lang), "hand", "hand" + i, h.confidence, h.box, ""));
  res.detections.forEach((d, i) => {
    rows.push(row(lang === "el" ? d.label_el : d.label_en, d.group, d.class_id, d.confidence, d.box, (byObject.get(i) || []).join(", ")));
  });
  return rows.slice(0, MAX_ROWS);
}

export function createDetector({
  video,
  canvas,
  table,
  stats,
  getLang = () => "el",
  getRecipeId = () => null,
  isPaused = () => false,
  capture = captureJpegBlob,
  api = defaultApi,
  schedule = (fn, ms) => setTimeout(fn, ms),
  cancel = (id) => clearTimeout(id),
  now = () => performance.now(),
}) {
  let running = false;
  let timer = null;
  let inFlight = false;
  let errors = 0;
  let lastResult = null;
  let lastTableAt = -Infinity;
  let fps = 0;
  let lastFrameAt = null;

  function viewTransform() {
    const rect = canvas.getBoundingClientRect();
    // Map through the video element's own box, then shift into canvas coordinates, so boxes
    // stay on their objects even if layout ever makes the two elements differ in size.
    const vr = typeof video.getBoundingClientRect === "function" ? video.getBoundingClientRect() : rect;
    const tr = coverTransform(vr.width, vr.height, video.videoWidth || 1, video.videoHeight || 1);
    tr.dx += vr.left - rect.left || 0;
    tr.dy += vr.top - rect.top || 0;
    return { rect, tr };
  }

  function clear() {
    const ctx = canvas.getContext("2d");
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  function draw(res) {
    const { rect, tr } = viewTransform();
    const dpr = globalThis.devicePixelRatio || 1;
    if (canvas.width !== Math.round(rect.width * dpr) || canvas.height !== Math.round(rect.height * dpr)) {
      canvas.width = Math.round(rect.width * dpr);
      canvas.height = Math.round(rect.height * dpr);
    }
    clear();
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.font = "bold 14px system-ui, sans-serif";
    ctx.textBaseline = "top";
    const lang = getLang();

    const label = (text, color, x, y) => {
      const w = ctx.measureText(text).width + 8;
      // Cover-cropping can push a box edge off-screen; keep its label readable.
      x = Math.min(Math.max(0, x), Math.max(0, rect.width - w));
      const top = Math.max(0, y - 20);
      ctx.fillStyle = color;
      ctx.fillRect(x, top, w, 20);
      ctx.fillStyle = "#111";
      ctx.fillText(text, x + 4, top + 3);
    };

    res.detections.forEach((d) => {
      const r = toViewRect(d.box, tr);
      const color = classColor(d.group, d.class_id);
      ctx.strokeStyle = color;
      ctx.lineWidth = d.hazard ? 4 : 3;
      ctx.strokeRect(r.x, r.y, r.w, r.h);
      label(`${lang === "el" ? d.label_el : d.label_en} ${Math.round(d.confidence * 100)}%`, color, r.x, r.y);
    });

    res.hands.forEach((h, i) => {
      const r = toViewRect(h.box, tr);
      const color = GROUP_COLORS.hand;
      ctx.strokeStyle = color;
      ctx.lineWidth = 3;
      ctx.setLineDash([]);
      ctx.strokeRect(r.x, r.y, r.w, r.h);
      label(`${handLabel(h, lang)} ${Math.round(h.confidence * 100)}%`, color, r.x, r.y);
      ctx.fillStyle = color;
      for (const tip of h.fingertips) {
        const p = toViewPoint(tip, tr);
        ctx.beginPath();
        ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
        ctx.fill();
      }
      // Dashed line from the hand to every object it relates to.
      ctx.setLineDash([6, 5]);
      ctx.lineWidth = 2;
      for (const rel of res.relations.filter((x) => x.hand === i)) {
        const obj = res.detections[rel.object];
        if (!obj) continue;
        const a = toViewPoint({ x: (h.box.x1 + h.box.x2) / 2, y: (h.box.y1 + h.box.y2) / 2 }, tr);
        const b = toViewPoint(obj.center, tr);
        ctx.strokeStyle = rel.kind === "near" ? "#FFFFFF" : color;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }
      ctx.setLineDash([]);
    });
  }

  function renderTable(res) {
    const lang = getLang();
    const rows = buildRows(res, lang);
    const head = ["", t("col_object", lang), t("col_group", lang), t("col_confidence", lang), "x, y", t("col_size", lang), t("col_hand", lang)];
    const doc = table.ownerDocument;
    const tbody = doc.createElement("tbody");
    for (const r of rows) {
      const tr = doc.createElement("tr");
      const swatch = doc.createElement("td");
      const chip = doc.createElement("span");
      chip.className = "swatch";
      chip.style.background = r.color;
      swatch.appendChild(chip);
      tr.appendChild(swatch);
      for (const text of [r.label, t("group_" + r.group, lang), `${r.confidence}%`, `${r.x}, ${r.y}`, `${r.w}×${r.h}`, r.relation]) {
        const td = doc.createElement("td");
        td.textContent = text; // never innerHTML - labels come from the server
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    const thead = doc.createElement("thead");
    const headRow = doc.createElement("tr");
    for (const text of head) {
      const th = doc.createElement("th");
      th.textContent = text;
      headRow.appendChild(th);
    }
    thead.appendChild(headRow);
    table.replaceChildren(thead, tbody);
  }

  function renderStats(res, frameMs) {
    if (!stats) return;
    const lang = getLang();
    if (!res) {
      stats.textContent = t("detect_error", lang);
      return;
    }
    stats.textContent = `${fps.toFixed(1)} FPS · ${t("detect_backend", lang)} ${Math.round(res.latency_ms.total)} ms · ${Math.round(frameMs)} ms · ${res.model}`;
  }

  async function tick() {
    timer = null;
    if (!running) return;
    if (isPaused() || globalThis.document?.hidden || !video.videoWidth) {
      timer = schedule(tick, 250);
      return;
    }
    inFlight = true;
    const started = now();
    let delay = 0;
    try {
      const { blob } = await capture(video);
      const res = await api.detectFrame(blob, getRecipeId());
      if (!running) return;
      errors = 0;
      lastResult = res;
      const finished = now();
      if (lastFrameAt !== null) {
        const instant = 1000 / Math.max(1, finished - lastFrameAt);
        fps = fps ? fps * 0.8 + instant * 0.2 : instant;
      }
      lastFrameAt = finished;
      draw(res);
      if (finished - lastTableAt >= TABLE_INTERVAL_MS) {
        lastTableAt = finished;
        renderTable(res);
        renderStats(res, finished - started);
      }
    } catch (err) {
      errors += 1;
      delay = Math.min(2000, 250 * errors); // a dead backend shouldn't be hammered
      renderStats(null, 0);
    } finally {
      inFlight = false;
    }
    if (running) timer = schedule(tick, delay);
  }

  return {
    start() {
      if (running) return;
      running = true;
      errors = 0;
      fps = 0;
      lastFrameAt = null;
      tick();
    },
    stop() {
      running = false;
      if (timer !== null) cancel(timer);
      timer = null;
      lastResult = null;
      clear();
      table.replaceChildren();
      if (stats) stats.textContent = "";
    },
    redraw() {
      if (lastResult) draw(lastResult);
    },
    isRunning: () => running,
    isInFlight: () => inFlight,
    lastResult: () => lastResult,
  };
}
