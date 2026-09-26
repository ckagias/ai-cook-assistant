#!/usr/bin/env python3
"""Pick the detector setup by measurement: which pretrained model, input size and runtime
format gives the best kitchen accuracy while still running live on *this* machine.

Usage:
  python scripts/benchmark_detectors.py                 # full sweep (~30-60 min on a laptop CPU)
  python scripts/benchmark_detectors.py --smoke         # 20 images, 2 configs - checks the plumbing
  python scripts/benchmark_detectors.py --include-large # also measure l/x models (accuracy ceiling)
  python scripts/benchmark_detectors.py --extra-dir path/to/yolo_set  # add an in-house labeled set

Stages:
  1. MediaPipe hands: latency + hand AP (hands come from MediaPipe at runtime - fingertips).
  2. Latency sweep over model x imgsz x format on real eval frames (10 warm-up, N timed).
  3. Accuracy for every (model, imgsz) that fits the budget with at least one format.
  4. Selection: among configs whose detector + hands p50 <= --budget-ms, the highest
     group-weighted AP50. Writes data/benchmarks/detector_report.md (+ .json) and prints .env lines.

Needs requirements-detect.txt and data from scripts/fetch_eval_set.py.
"""
from __future__ import annotations

import argparse
import gc
import json
import platform
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import cv2  # noqa: E402
import psutil  # noqa: E402

from app.detection import detector as det_mod  # noqa: E402
from app.detection.hands import HandTracker  # noqa: E402
from app.detection.metrics import ClassScore, GroundTruth, ImageSample, Prediction, evaluate, weighted_mean_ap  # noqa: E402
from app.detection.vocabulary import load_vocabulary  # noqa: E402

EVAL_DIR = BACKEND_DIR / "data" / "detection_eval" / "openimages"
REPORT_DIR = BACKEND_DIR / "data" / "benchmarks"

DEFAULT_MODELS = ["yolov8n-oiv7", "yolov8s-oiv7", "yolov8m-oiv7", "yoloe-26n-seg", "yoloe-26s-seg", "yoloe-26m-seg"]
LARGE_MODELS = ["yolov8l-oiv7", "yolov8x-oiv7", "yoloe-26l-seg", "yoloe-26x-seg"]
GROUP_WEIGHTS = {"hand": 2.0, "utensil": 2.0, "cookware": 2.0, "appliance": 1.0, "ingredient": 1.0, "food": 0.5, "hazard": 1.0}
MIN_GT_FOR_RANKING = 10  # classes with fewer boxes are reported but don't move the score
FRAME_MAX_EDGE = 640  # what the client sends (capture.js captureJpegBlob)
AP_CONF = 0.05  # low threshold so AP sees the whole precision/recall curve


# ---------------------------------------------------------------- data


def load_openimages(eval_dir: Path, limit: int | None) -> tuple[dict[str, ImageSample], dict[str, Path]]:
    manifest = json.loads((eval_dir / "manifest.json").read_text(encoding="utf-8"))
    samples, files = {}, {}
    for entry in manifest["images"][:limit]:
        gts = [GroundTruth(b["class_id"], tuple(b["box"]), b["group_of"]) for b in entry["boxes"]]
        samples[entry["id"]] = ImageSample(gts, set(entry["evaluable"]))
        files[entry["id"]] = eval_dir / entry["file"]
    return samples, files


def load_yolo_dir(root: Path, class_ids: list[str]) -> tuple[dict[str, ImageSample], dict[str, Path]]:
    """In-house set: images/*.jpg + labels/*.txt ("<class_index> cx cy w h", normalized, indices in
    vocabulary order). Treated as exhaustively labeled - every class is evaluable on every image."""
    samples, files = {}, {}
    everything = set(class_ids)
    for img in sorted((root / "images").glob("*.jpg")):
        gts = []
        label = root / "labels" / f"{img.stem}.txt"
        if label.exists():
            for line in label.read_text().split("\n"):
                parts = line.split()
                if len(parts) != 5:
                    continue
                idx, cx, cy, w, h = int(parts[0]), *map(float, parts[1:])
                gts.append(GroundTruth(class_ids[idx], (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)))
        key = f"extra/{img.stem}"
        samples[key] = ImageSample(gts, everything)
        files[key] = img
    return samples, files


def read_frame(path: Path):
    img = cv2.imread(str(path))
    h, w = img.shape[:2]
    scale = FRAME_MAX_EDGE / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    return img


# ---------------------------------------------------------------- measurement


def time_calls(fn, frames, warmup: int) -> dict:
    for f in frames[:warmup]:
        fn(f)
    times = []
    for f in frames:
        t = time.perf_counter()
        fn(f)
        times.append((time.perf_counter() - t) * 1000)
    times.sort()
    return {"p50_ms": statistics.median(times), "p95_ms": times[int(0.95 * (len(times) - 1))], "n": len(times)}


def rss_mb() -> float:
    return psutil.Process().memory_info().rss / 2**20


def score_predictions(samples, predictions, vocab, conf) -> dict[str, ClassScore]:
    return evaluate(samples, predictions, conf_thr=conf)


def group_summary(scores: dict[str, ClassScore], vocab) -> dict:
    ranked = {c: s for c, s in scores.items() if s.n_gt >= MIN_GT_FOR_RANKING}
    weights = {c: GROUP_WEIGHTS[vocab.by_id(c).group] for c in ranked}
    by_group = defaultdict(list)
    for c, s in ranked.items():
        by_group[vocab.by_id(c).group].append(s.ap50)
    return {
        "weighted_ap50": weighted_mean_ap(ranked, weights),
        "groups": {g: statistics.mean(v) for g, v in by_group.items()},
        "ranked_classes": len(ranked),
    }


# ---------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--include-large", action="store_true")
    ap.add_argument("--sizes", default="320,480,640")
    ap.add_argument("--formats", default="torch,onnx,openvino")
    ap.add_argument("--latency-frames", type=int, default=100)
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--budget-ms", type=float, default=170.0, help="detector + hands p50 budget (~4.5 FPS end to end)")
    ap.add_argument("--conf", type=float, default=0.25, help="operating confidence for precision/recall")
    ap.add_argument("--max-images", type=int, default=None)
    ap.add_argument("--extra-dir", type=Path, default=None)
    ap.add_argument("--accuracy-all", action="store_true", help="score accuracy even for configs over budget")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--retime-finalists", type=int, default=0, metavar="K",
                    help="after a full run: re-time the K most accurate configs interleaved, then re-pick")
    args = ap.parse_args()

    if args.retime_finalists:
        return retime_finalists(args, load_vocabulary())

    if args.smoke:
        args.models, args.sizes, args.formats = "yolov8n-oiv7,yoloe-26s-seg", "320", "torch,onnx"
        args.max_images, args.latency_frames, args.warmup = 20, 10, 2

    vocab = load_vocabulary()
    models = [m for m in args.models.split(",") if m] + (LARGE_MODELS if args.include_large else [])
    sizes = [int(s) for s in args.sizes.split(",")]
    formats = [f for f in args.formats.split(",") if f]

    samples, files = load_openimages(EVAL_DIR, args.max_images)
    if args.extra_dir:
        extra_samples, extra_files = load_yolo_dir(args.extra_dir, vocab.ids())
        samples.update(extra_samples)
        files.update(extra_files)
    image_ids = sorted(samples)
    timing_frames = [read_frame(files[i]) for i in image_ids[: args.latency_frames]]
    print(f"{len(image_ids)} eval images, {len(timing_frames)} timing frames, budget {args.budget_ms} ms")

    report: dict = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "machine": {
            "cpu": platform.processor(),
            "cores": psutil.cpu_count(logical=False),
            "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
            "os": platform.platform(),
        },
        "versions": {},
        "budget_ms": args.budget_ms,
        "conf": args.conf,
        "images": len(image_ids),
    }
    for pkg in ("ultralytics", "torch", "onnxruntime", "openvino", "mediapipe"):
        try:
            report["versions"][pkg] = __import__(pkg).__version__
        except Exception:
            report["versions"][pkg] = "n/a"

    # 1. hands --------------------------------------------------------------
    print("\n[hands] MediaPipe Hand Landmarker")
    tracker = HandTracker()
    hands_latency = time_calls(tracker.detect, timing_frames, args.warmup)
    hand_preds = {}
    for image_id in image_ids:
        hand_preds[image_id] = [Prediction("hand", h.box, h.confidence) for h in tracker.detect(read_frame(files[image_id]))]
    tracker.close()
    hand_samples = {i: ImageSample([g for g in s.ground_truth if g.class_id == "hand"], s.evaluable & {"hand"}) for i, s in samples.items()}
    mp_hand = score_predictions(hand_samples, hand_preds, vocab, 0.5).get("hand")
    report["hands"] = {"latency": hands_latency, "ap50": mp_hand.ap50 if mp_hand else None,
                       "recall": mp_hand.recall if mp_hand else None, "precision": mp_hand.precision if mp_hand else None,
                       "n_gt": mp_hand.n_gt if mp_hand else 0}
    print(f"  p50 {hands_latency['p50_ms']:.1f} ms | hand AP50 {report['hands']['ap50']}")

    # 2. latency sweep ------------------------------------------------------
    latency_rows = []
    for model_name in models:
        for imgsz in sizes:
            for fmt in formats:
                label = f"{model_name}@{imgsz}/{fmt}"
                try:
                    t0 = time.perf_counter()
                    detector = det_mod.load_detector(model_name, imgsz, fmt, vocab)
                    load_s = time.perf_counter() - t0
                    lat = time_calls(lambda f: detector.detect(f, args.conf), timing_frames, args.warmup)
                    row = {"model": model_name, "imgsz": imgsz, "format": fmt, **lat, "load_s": round(load_s, 1), "rss_mb": round(rss_mb())}
                    row["total_p50_ms"] = row["p50_ms"] + hands_latency["p50_ms"]
                    row["fits"] = row["total_p50_ms"] <= args.budget_ms
                    print(f"[latency] {label:<34} p50 {row['p50_ms']:7.1f} ms  p95 {row['p95_ms']:7.1f}  +hands {row['total_p50_ms']:7.1f}  {'OK' if row['fits'] else 'over'}")
                except Exception as exc:  # one broken export must not end the sweep
                    row = {"model": model_name, "imgsz": imgsz, "format": fmt, "error": f"{type(exc).__name__}: {exc}"[:300], "fits": False}
                    print(f"[latency] {label:<34} FAILED {row['error']}")
                latency_rows.append(row)
                detector = None
                gc.collect()
    report["latency"] = latency_rows

    # 3. accuracy -----------------------------------------------------------
    fastest: dict[tuple[str, int], dict] = {}
    for row in latency_rows:
        if "error" in row or not (row["fits"] or args.accuracy_all):
            continue
        key = (row["model"], row["imgsz"])
        if key not in fastest or row["p50_ms"] < fastest[key]["p50_ms"]:
            fastest[key] = row

    accuracy_rows = []
    for (model_name, imgsz), row in sorted(fastest.items()):
        label = f"{model_name}@{imgsz}/{row['format']}"
        print(f"[accuracy] {label} over {len(image_ids)} images...")
        detector = det_mod.load_detector(model_name, imgsz, row["format"], vocab)
        preds = {}
        detector_hand = {}
        for image_id in image_ids:
            dets = detector.detect(read_frame(files[image_id]), AP_CONF)
            detector_hand[image_id] = [Prediction("hand", d.box, d.confidence) for d in dets if d.class_id == "hand"]
            # At runtime hands come from MediaPipe (fingertips); score the same way.
            preds[image_id] = [Prediction(d.class_id, d.box, d.confidence) for d in dets if d.class_id != "hand"] + hand_preds[image_id]
        scores = score_predictions(samples, preds, vocab, args.conf)
        own_hand = score_predictions(hand_samples, detector_hand, vocab, args.conf).get("hand")
        summary = group_summary(scores, vocab)
        accuracy_rows.append({
            "model": model_name, "imgsz": imgsz, "format": row["format"], "p50_ms": row["p50_ms"],
            "total_p50_ms": row["total_p50_ms"], "fits": row["fits"], **summary,
            "detector_hand_ap50": own_hand.ap50 if own_hand else None,
            "classes": {c: vars(s) for c, s in sorted(scores.items())},
        })
        print(f"  weighted AP50 {summary['weighted_ap50']:.3f} | groups " + ", ".join(f"{g} {v:.2f}" for g, v in sorted(summary["groups"].items())))
        detector = None
        gc.collect()
    report["accuracy"] = accuracy_rows

    # 4. selection ----------------------------------------------------------
    feasible = [r for r in accuracy_rows if r["fits"]]
    winner = max(feasible, key=lambda r: r["weighted_ap50"]) if feasible else None
    report["winner"] = {k: winner[k] for k in ("model", "imgsz", "format", "weighted_ap50", "total_p50_ms")} if winner else None
    report["unscored_classes"] = [c.id for c in vocab.classes if not any(c.id in r["classes"] for r in accuracy_rows)]

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stem = "detector_report_smoke" if args.smoke else "detector_report"
    (REPORT_DIR / f"{stem}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (REPORT_DIR / f"{stem}.md").write_text(render_markdown(report, vocab), encoding="utf-8")
    print(f"\nReport: {REPORT_DIR / (stem + '.md')}")
    if winner:
        print("\nRecommended backend/.env lines:")
        print(env_lines(winner))
    else:
        print("\nNo configuration met the budget - see the latency table; consider --budget-ms or smaller sizes.")
    return 0


def retime_finalists(args, vocab) -> int:
    """Re-time the most accurate candidates *interleaved*, frame by frame, so laptop thermal
    throttling drifting over a long sweep hits every candidate equally, then re-pick the winner.
    Reads and rewrites the report produced by a full run."""
    json_path = REPORT_DIR / "detector_report.json"
    report = json.loads(json_path.read_text(encoding="utf-8"))
    ranked = sorted(report["accuracy"], key=lambda r: -r["weighted_ap50"])[: args.retime_finalists]
    formats = [f for f in args.formats.split(",") if f]
    samples, files = load_openimages(EVAL_DIR, None)
    frames = [read_frame(files[i]) for i in sorted(samples)[: args.latency_frames]]

    loaded = []
    for row in ranked:
        for fmt in formats:
            try:
                loaded.append((row, fmt, det_mod.load_detector(row["model"], row["imgsz"], fmt, vocab)))
            except Exception as exc:
                print(f"[finalists] skip {row['model']}@{row['imgsz']}/{fmt}: {exc}")
    tracker = HandTracker()
    runners = [("hands", None, lambda f: tracker.detect(f))] + [
        (f"{r['model']}@{r['imgsz']}/{fmt}", (r, fmt), (lambda d: lambda f: d.detect(f, args.conf))(d)) for r, fmt, d in loaded
    ]
    for f in frames[: args.warmup]:
        for _, _, fn in runners:
            fn(f)
    times: dict[str, list[float]] = defaultdict(list)
    for i, f in enumerate(frames):
        order = runners[i % len(runners):] + runners[: i % len(runners)]  # rotate who goes first
        for label, _, fn in order:
            t = time.perf_counter()
            fn(f)
            times[label].append((time.perf_counter() - t) * 1000)
    tracker.close()

    hands_p50 = statistics.median(times["hands"])
    finalists = []
    for label, meta, _ in runners[1:]:
        row, fmt = meta
        ordered = sorted(times[label])
        p50 = statistics.median(ordered)
        finalists.append({
            "model": row["model"], "imgsz": row["imgsz"], "format": fmt, "weighted_ap50": row["weighted_ap50"],
            "p50_ms": p50, "p95_ms": ordered[int(0.95 * (len(ordered) - 1))], "total_p50_ms": p50 + hands_p50,
            "fits": p50 + hands_p50 <= args.budget_ms,
        })
        print(f"[finalists] {label:<34} p50 {p50:7.1f}  +hands {p50 + hands_p50:7.1f}  AP {row['weighted_ap50']:.3f}  {'OK' if finalists[-1]['fits'] else 'over'}")

    fitting = [f for f in finalists if f["fits"]]
    winner = max(fitting, key=lambda f: (f["weighted_ap50"], -f["total_p50_ms"])) if fitting else None
    report["finalists"] = {"hands_p50_ms": hands_p50, "frames": len(frames), "rows": finalists}
    report["winner"] = {k: winner[k] for k in ("model", "imgsz", "format", "weighted_ap50", "total_p50_ms")} if winner else None
    for _, _, d in loaded:
        del d
    loaded = []
    gc.collect()

    if winner:
        print(f"[hands] comparing hand backends on {winner['model']}@{winner['imgsz']}/{winner['format']}...")
        report["hand_backends"] = compare_hand_backends(winner, vocab, samples, files)
        report["winner"]["hands"] = max(
            report["hand_backends"],
            # A near-tie goes to MediaPipe: its fingertips are what make "touching" meaningful.
            key=lambda name: report["hand_backends"][name]["ap50"] + (0.01 if name == "mediapipe" else 0),
        )
        for name, s in report["hand_backends"].items():
            print(f"  {name:<10} hand AP50 {s['ap50']:.3f}  recall {s['recall']:.2f}  precision {s['precision']:.2f}")
    json_path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    (REPORT_DIR / "detector_report.md").write_text(render_markdown(report, vocab), encoding="utf-8")
    if report["winner"]:
        # report["winner"] carries the hand-backend choice; the finalist row doesn't.
        print("\nRecommended backend/.env lines:\n" + env_lines(report["winner"]))
    return 0


def compare_hand_backends(winner: dict, vocab, samples, files) -> dict:
    """Hand AP for the three hand sources on the chosen detector: MediaPipe alone, the detector's
    own hand boxes alone, and the hybrid (MediaPipe + detector hands MediaPipe missed)."""
    from app.detection.hands import merge_hands

    detector = det_mod.load_detector(winner["model"], winner["imgsz"], winner["format"], vocab)
    tracker = HandTracker()
    preds: dict[str, dict] = {"mediapipe": {}, "detector": {}, "hybrid": {}}
    for image_id in sorted(samples):
        frame = read_frame(files[image_id])
        mp_hands = tracker.detect(frame)
        det_hands = [(d.box, d.confidence) for d in detector.detect(frame, AP_CONF) if d.class_id == "hand"]
        preds["mediapipe"][image_id] = [Prediction("hand", h.box, h.confidence) for h in mp_hands]
        preds["detector"][image_id] = [Prediction("hand", b, c) for b, c in det_hands]
        preds["hybrid"][image_id] = [Prediction("hand", h.box, h.confidence) for h in merge_hands(mp_hands, det_hands)]
    tracker.close()
    hand_samples = {i: ImageSample([g for g in s.ground_truth if g.class_id == "hand"], s.evaluable & {"hand"}) for i, s in samples.items()}
    out = {}
    for name, p in preds.items():
        s = evaluate(hand_samples, p, conf_thr=0.25).get("hand")
        out[name] = {"ap50": s.ap50, "recall": s.recall, "precision": s.precision, "n_gt": s.n_gt} if s else {"ap50": 0.0, "recall": 0.0, "precision": 0.0, "n_gt": 0}
    return out


def env_lines(w: dict) -> str:
    return (
        f"DETECTOR_MODEL={w['model']}\nDETECTOR_IMGSZ={w['imgsz']}\nDETECTOR_FORMAT={w['format']}\n"
        f"HANDS_BACKEND={w.get('hands', 'mediapipe')}"
    )


def render_markdown(r: dict, vocab) -> str:
    m = r["machine"]
    out = [
        "# Detector benchmark",
        "",
        f"Generated {r['created_at'][:19]} UTC by `scripts/benchmark_detectors.py` on {m['cpu']} "
        f"({m['cores']} cores, {m['ram_gb']} GB RAM, {m['os']}). "
        + ", ".join(f"{k} {v}" for k, v in r["versions"].items()) + ".",
        "",
        f"Eval set: {r['images']} images from the Open Images V7 validation split (`scripts/fetch_eval_set.py`). "
        f"Budget: detector + hands p50 <= {r['budget_ms']:.0f} ms (~4.5 FPS end to end). "
        f"Operating confidence {r['conf']}. No model was trained or fine-tuned.",
        "",
    ]
    w = r.get("winner")
    if w:
        out += ["## Recommendation", "", f"**{w['model']} at {w['imgsz']}px, {w['format']}** - weighted AP50 "
                f"{w['weighted_ap50']:.3f}, {w['total_p50_ms']:.0f} ms p50 with hands.", "", "```", env_lines(w), "```", ""]
    else:
        out += ["## Recommendation", "", "No configuration met the budget.", ""]

    fin = r.get("finalists")
    if fin:
        out += ["## Finalists, re-timed interleaved", "",
                f"The most accurate configs, timed round-robin over the same {fin['frames']} frames so thermal "
                f"throttling affects all equally (hands p50 {fin['hands_p50_ms']:.1f} ms). This table decides the recommendation.", "",
                "| model | imgsz | format | weighted AP50 | p50 ms | p95 ms | +hands p50 | fits |", "|---|---|---|---|---|---|---|---|"]
        for row in sorted(fin["rows"], key=lambda x: (-x["weighted_ap50"], x["p50_ms"])):
            out.append(f"| {row['model']} | {row['imgsz']} | {row['format']} | {row['weighted_ap50']:.3f} | {row['p50_ms']:.0f} | "
                       f"{row['p95_ms']:.0f} | {row['total_p50_ms']:.0f} | {'yes' if row['fits'] else 'no'} |")
        out.append("")

    h = r["hands"]
    out += ["## Hands (MediaPipe Hand Landmarker)", "",
            f"p50 {h['latency']['p50_ms']:.1f} ms, p95 {h['latency']['p95_ms']:.1f} ms. Hand AP50 "
            f"{(h['ap50'] or 0):.3f} (recall {(h['recall'] or 0):.2f}, precision {(h['precision'] or 0):.2f} at 0.5) "
            f"over {h['n_gt']} hand boxes.", ""]
    hb = r.get("hand_backends")
    if hb:
        out += ["Hand sources compared on the recommended detector (operating point 0.25). MediaPipe needs most "
                "of the hand in frame; the detector also finds hands cut off at the edge or seen edge-on, but "
                "without fingertips. `hybrid` = MediaPipe plus the detector's hands MediaPipe missed.", "",
                "| HANDS_BACKEND | hand AP50 | recall | precision |", "|---|---|---|---|"]
        for name, s in hb.items():
            chosen = " **(recommended)**" if w and w.get("hands") == name else ""
            out.append(f"| {name}{chosen} | {s['ap50']:.3f} | {s['recall']:.2f} | {s['precision']:.2f} |")
        out.append("")

    out += ["## Latency sweep (detector only, then + hands)", "",
            "Measured sequentially over a long run on a laptop, so later rows may be slowed by thermal throttling - "
            "treat small differences as noise; the finalist table above is the fair comparison.", "", "| model | imgsz | format | p50 ms | p95 ms | +hands p50 | RSS MB | fits |", "|---|---|---|---|---|---|---|---|"]
    for row in r["latency"]:
        if "error" in row:
            out.append(f"| {row['model']} | {row['imgsz']} | {row['format']} | - | - | - | - | error: {row['error'][:80]} |")
        else:
            out.append(f"| {row['model']} | {row['imgsz']} | {row['format']} | {row['p50_ms']:.0f} | {row['p95_ms']:.0f} | "
                       f"{row['total_p50_ms']:.0f} | {row['rss_mb']} | {'yes' if row['fits'] else 'no'} |")
    out.append("")

    groups = vocab.groups
    out += ["## Accuracy (AP50; classes with >= 10 boxes are ranked)", "",
            "| model | imgsz | weighted AP50 | " + " | ".join(groups) + " | detector's own hand AP50 |",
            "|---|---|---|" + "---|" * len(groups) + "---|"]
    for row in sorted(r["accuracy"], key=lambda x: -x["weighted_ap50"]):
        cells = " | ".join(f"{row['groups'][g]:.2f}" if g in row["groups"] else "-" for g in groups)
        dh = f"{row['detector_hand_ap50']:.2f}" if row["detector_hand_ap50"] is not None else "-"
        out.append(f"| {row['model']} | {row['imgsz']} | {row['weighted_ap50']:.3f} | {cells} | {dh} |")
    out.append("")

    if w:
        best = next(a for a in r["accuracy"] if a["model"] == w["model"] and a["imgsz"] == w["imgsz"])
        out += ["## Per-class, recommended config", "", "| class | group | boxes | AP50 | precision | recall |", "|---|---|---|---|---|---|"]
        for cid, s in sorted(best["classes"].items(), key=lambda kv: -kv[1]["ap50"]):
            flag = "" if s["n_gt"] >= MIN_GT_FOR_RANKING else " (few boxes)"
            out.append(f"| {cid}{flag} | {vocab.by_id(cid).group} | {s['n_gt']} | {s['ap50']:.2f} | {s['precision']:.2f} | {s['recall']:.2f} |")
        out.append("")

    out += ["## Caveats", "",
            "- Open Images is what the `oiv7` models were trained on (different split), so this set favors them. "
            "Classes with no Open Images boxes cannot be scored here at all and are only reachable by YOLOE: "
            + ", ".join(r["unscored_classes"]) + ".",
            "- Cooking-state classes (boiling water, fried egg, ...) are experimental and unscored; doneness stays with `/analyze`.",
            "- FP32 only. INT8 quantization needs a calibration set and was not attempted.",
            "- Ultralytics code and weights are AGPL-3.0.",
            "- Add an in-house labeled kitchen set with `--extra-dir` to measure the real deployment domain.", ""]
    return "\n".join(out)


if __name__ == "__main__":
    sys.exit(main())
