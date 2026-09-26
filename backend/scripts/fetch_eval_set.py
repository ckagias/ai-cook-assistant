#!/usr/bin/env python3
"""Download a kitchen-relevant slice of the Open Images V7 *validation* split, for scoring
pretrained detectors in scripts/benchmark_detectors.py. Nothing here is used for training.

Usage: python scripts/fetch_eval_set.py [--per-class 30] [--workers 4] [--seed 0]

Writes backend/data/detection_eval/openimages/ (gitignored):
  manifest.json      - per image: boxes mapped to vocabulary ids, group-of flags, and the set
                       of classes a human verified present/absent (needed for a fair score -
                       Open Images labels are not exhaustive)
  images/<id>.jpg    - resized to fit 1024px, the rest of the pipeline never needs more
  _meta/*.csv        - the official annotation files, cached

Open Images annotations are CC BY 4.0 and the images are individually licensed (mostly
CC BY 2.0) - fine for local evaluation, never commit them.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.detection.vocabulary import load_vocabulary  # noqa: E402

OUT_DIR = BACKEND_DIR / "data" / "detection_eval" / "openimages"
META = {
    "boxes": "https://storage.googleapis.com/openimages/v5/validation-annotations-bbox.csv",
    "labels": "https://storage.googleapis.com/openimages/v5/validation-annotations-human-imagelabels-boxable.csv",
    "classes": "https://storage.googleapis.com/openimages/v7/oidv7-class-descriptions-boxable.csv",
}
IMAGE_URL = "https://open-images-dataset.s3.amazonaws.com/validation/{image_id}.jpg"
MAX_EDGE = 1024


def download(client: httpx.Client, url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with client.stream("GET", url) as resp:
        resp.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in resp.iter_bytes(1 << 16):
                fh.write(chunk)
    tmp.replace(dest)
    return dest


def fetch_image(client: httpx.Client, image_id: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    resp = client.get(IMAGE_URL.format(image_id=image_id))
    if resp.status_code != 200:
        return False
    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="JPEG", quality=90)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--per-class", type=int, default=30, help="max images sampled per vocabulary class")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    vocab = load_vocabulary()
    name_to_id = vocab.oiv7_to_id()

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        meta = {key: download(client, url, args.out / "_meta" / Path(url).name) for key, url in META.items()}

        mid_to_id: dict[str, str] = {}
        resolved: set[str] = set()
        with meta["classes"].open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row["DisplayName"] in name_to_id:
                    mid_to_id[row["LabelName"]] = name_to_id[row["DisplayName"]]
                    resolved.add(row["DisplayName"])
        if resolved != set(name_to_id):
            print(f"WARNING: Open Images names not found in the class list: {sorted(set(name_to_id) - resolved)}")

        boxes: dict[str, list[dict]] = defaultdict(list)
        with meta["boxes"].open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                class_id = mid_to_id.get(row["LabelName"])
                if class_id is None:
                    continue
                boxes[row["ImageID"]].append({
                    "class_id": class_id,
                    "box": [float(row["XMin"]), float(row["YMin"]), float(row["XMax"]), float(row["YMax"])],
                    "group_of": row["IsGroupOf"] == "1",
                })

        evaluable: dict[str, set[str]] = defaultdict(set)
        with meta["labels"].open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                class_id = mid_to_id.get(row["LabelName"])
                if class_id is not None:
                    evaluable[row["ImageID"]].add(class_id)  # verified present (1) or absent (0)

        by_class: dict[str, list[str]] = defaultdict(list)
        for image_id, image_boxes in boxes.items():
            for class_id in {b["class_id"] for b in image_boxes}:
                by_class[class_id].append(image_id)

        rng = random.Random(args.seed)
        selected: set[str] = set()
        for class_id in sorted(by_class):
            candidates = sorted(by_class[class_id])
            rng.shuffle(candidates)
            selected.update(candidates[: args.per_class])

        images_dir = args.out / "images"
        ordered = sorted(selected)
        print(f"Downloading {len(ordered)} images ({args.workers} parallel, resumable)...")
        ok: set[str] = set()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(fetch_image, client, i, images_dir / f"{i}.jpg"): i for i in ordered}
            for done, future in enumerate(as_completed(futures), start=1):
                image_id = futures[future]
                try:
                    if future.result():
                        ok.add(image_id)
                except Exception as exc:  # one bad download must not sink the whole set
                    print(f"  failed {image_id}: {exc}")
                if done % 100 == 0:
                    print(f"  {done}/{len(ordered)}")

    manifest = {
        "source": "Open Images V7 validation split",
        "license": "annotations CC BY 4.0; images individually licensed (mostly CC BY 2.0)",
        "vocabulary_version": vocab.version,
        "images": [
            {
                "id": image_id,
                "file": f"images/{image_id}.jpg",
                "boxes": boxes[image_id],
                "evaluable": sorted(evaluable[image_id] | {b["class_id"] for b in boxes[image_id]}),
            }
            for image_id in ordered
            if image_id in ok
        ],
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    counts = defaultdict(int)
    for entry in manifest["images"]:
        for b in entry["boxes"]:
            counts[b["class_id"]] += 1
    print(f"\nWrote {len(manifest['images'])} images to {args.out}")
    print("Ground-truth boxes per class:")
    for class_id in vocab.ids():
        if class_id in counts:
            print(f"  {class_id:<16} {counts[class_id]}")
    unscored = [c.id for c in vocab.classes if c.id not in counts]
    print(f"No Open Images ground truth (cannot be scored here): {', '.join(unscored)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
