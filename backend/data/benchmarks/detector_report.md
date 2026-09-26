# Detector benchmark

Generated 2026-09-25T19:24:59 UTC by `scripts/benchmark_detectors.py` on AMD64 Family 23 Model 96 Stepping 1, AuthenticAMD (6 cores, 7.4 GB RAM, Windows-11-10.0.26200-SP0). ultralytics 8.4.163, torch 2.14.0+cpu, onnxruntime 1.30.0, openvino 2026.4.0-22959-99c81491cc3-releases/2026/4, mediapipe 1.0.1.

Eval set: 1011 images from the Open Images V7 validation split (`scripts/fetch_eval_set.py`). Budget: detector + hands p50 <= 170 ms (~4.5 FPS end to end). Operating confidence 0.25. No model was trained or fine-tuned.

## Recommendation

**yoloe-26s-seg at 480px, openvino** - weighted AP50 0.446, 102 ms p50 with hands.

```
DETECTOR_MODEL=yoloe-26s-seg
DETECTOR_IMGSZ=480
DETECTOR_FORMAT=openvino
HANDS_BACKEND=hybrid
```

## Finalists, re-timed interleaved

The most accurate configs, timed round-robin over the same 100 frames so thermal throttling affects all equally (hands p50 18.7 ms). This table decides the recommendation.

| model | imgsz | format | weighted AP50 | p50 ms | p95 ms | +hands p50 | fits |
|---|---|---|---|---|---|---|---|
| yoloe-26s-seg | 480 | openvino | 0.446 | 84 | 120 | 102 | yes |
| yoloe-26s-seg | 480 | torch | 0.446 | 115 | 167 | 134 | yes |
| yoloe-26s-seg | 320 | openvino | 0.443 | 42 | 59 | 61 | yes |
| yoloe-26s-seg | 320 | torch | 0.443 | 70 | 107 | 88 | yes |
| yoloe-26m-seg | 320 | openvino | 0.442 | 119 | 166 | 138 | yes |
| yoloe-26m-seg | 320 | torch | 0.442 | 142 | 185 | 161 | yes |
| yoloe-26n-seg | 640 | openvino | 0.392 | 72 | 99 | 91 | yes |
| yoloe-26n-seg | 640 | torch | 0.392 | 92 | 154 | 111 | yes |

## Hands (MediaPipe Hand Landmarker)

p50 15.9 ms, p95 27.2 ms. Hand AP50 0.356 (recall 0.36, precision 0.97 at 0.5) over 84 hand boxes.

Hand sources compared on the recommended detector (operating point 0.25). MediaPipe needs most of the hand in frame; the detector also finds hands cut off at the edge or seen edge-on, but without fingertips. `hybrid` = MediaPipe plus the detector's hands MediaPipe missed.

| HANDS_BACKEND | hand AP50 | recall | precision |
|---|---|---|---|
| mediapipe | 0.356 | 0.36 | 0.97 |
| detector | 0.135 | 0.07 | 0.60 |
| hybrid **(recommended)** | 0.448 | 0.42 | 0.88 |

## Latency sweep (detector only, then + hands)

Measured sequentially over a long run on a laptop, so later rows may be slowed by thermal throttling - treat small differences as noise; the finalist table above is the fair comparison.

| model | imgsz | format | p50 ms | p95 ms | +hands p50 | RSS MB | fits |
|---|---|---|---|---|---|---|---|
| yolov8n-oiv7 | 320 | torch | 28 | 36 | 44 | 572 | yes |
| yolov8n-oiv7 | 320 | onnx | 62 | 91 | 78 | 569 | yes |
| yolov8n-oiv7 | 320 | openvino | 21 | 24 | 37 | 698 | yes |
| yolov8n-oiv7 | 480 | torch | 48 | 65 | 64 | 705 | yes |
| yolov8n-oiv7 | 480 | onnx | 112 | 338 | 128 | 823 | yes |
| yolov8n-oiv7 | 480 | openvino | 45 | 56 | 61 | 783 | yes |
| yolov8n-oiv7 | 640 | torch | 71 | 100 | 87 | 795 | yes |
| yolov8n-oiv7 | 640 | onnx | 120 | 339 | 135 | 928 | yes |
| yolov8n-oiv7 | 640 | openvino | 74 | 90 | 90 | 842 | yes |
| yolov8s-oiv7 | 320 | torch | 50 | 61 | 66 | 835 | yes |
| yolov8s-oiv7 | 320 | onnx | 75 | 108 | 91 | 853 | yes |
| yolov8s-oiv7 | 320 | openvino | 38 | 47 | 54 | 831 | yes |
| yolov8s-oiv7 | 480 | torch | 88 | 133 | 104 | 743 | yes |
| yolov8s-oiv7 | 480 | onnx | 107 | 191 | 123 | 977 | yes |
| yolov8s-oiv7 | 480 | openvino | 83 | 113 | 99 | 850 | yes |
| yolov8s-oiv7 | 640 | torch | 138 | 193 | 154 | 777 | yes |
| yolov8s-oiv7 | 640 | onnx | 200 | 284 | 216 | 1056 | no |
| yolov8s-oiv7 | 640 | openvino | 197 | 321 | 213 | 841 | no |
| yolov8m-oiv7 | 320 | torch | 165 | 406 | 181 | 463 | no |
| yolov8m-oiv7 | 320 | onnx | 106 | 229 | 122 | 1039 | yes |
| yolov8m-oiv7 | 320 | openvino | 107 | 349 | 123 | 950 | yes |
| yolov8m-oiv7 | 480 | torch | 214 | 300 | 229 | 811 | no |
| yolov8m-oiv7 | 480 | onnx | 313 | 417 | 329 | 1174 | no |
| yolov8m-oiv7 | 480 | openvino | 218 | 299 | 234 | 1064 | no |
| yolov8m-oiv7 | 640 | torch | 301 | 410 | 317 | 847 | no |
| yolov8m-oiv7 | 640 | onnx | 475 | 931 | 491 | 1371 | no |
| yolov8m-oiv7 | 640 | openvino | 393 | 452 | 409 | 1182 | no |
| yoloe-26n-seg | 320 | torch | 38 | 69 | 54 | 831 | yes |
| yoloe-26n-seg | 320 | onnx | 77 | 144 | 93 | 806 | yes |
| yoloe-26n-seg | 320 | openvino | 24 | 27 | 40 | 961 | yes |
| yoloe-26n-seg | 480 | torch | 67 | 114 | 83 | 759 | yes |
| yoloe-26n-seg | 480 | onnx | 124 | 203 | 140 | 988 | yes |
| yoloe-26n-seg | 480 | openvino | 44 | 52 | 60 | 774 | yes |
| yoloe-26n-seg | 640 | torch | 90 | 149 | 106 | 801 | yes |
| yoloe-26n-seg | 640 | onnx | 180 | 290 | 196 | 887 | no |
| yoloe-26n-seg | 640 | openvino | 66 | 98 | 82 | 810 | yes |
| yoloe-26s-seg | 320 | torch | 69 | 86 | 85 | 830 | yes |
| yoloe-26s-seg | 320 | onnx | 101 | 234 | 117 | 797 | yes |
| yoloe-26s-seg | 320 | openvino | 44 | 61 | 60 | 892 | yes |
| yoloe-26s-seg | 480 | torch | 118 | 153 | 134 | 861 | yes |
| yoloe-26s-seg | 480 | onnx | 255 | 317 | 271 | 1158 | no |
| yoloe-26s-seg | 480 | openvino | 95 | 134 | 111 | 1023 | yes |
| yoloe-26s-seg | 640 | torch | 177 | 242 | 193 | 938 | no |
| yoloe-26s-seg | 640 | onnx | 258 | 456 | 274 | 1267 | no |
| yoloe-26s-seg | 640 | openvino | 198 | 247 | 213 | 1032 | no |
| yoloe-26m-seg | 320 | torch | 142 | 177 | 158 | 1109 | yes |
| yoloe-26m-seg | 320 | onnx | 233 | 340 | 249 | 1620 | no |
| yoloe-26m-seg | 320 | openvino | 162 | 203 | 178 | 1293 | no |
| yoloe-26m-seg | 480 | torch | 307 | 477 | 323 | 1214 | no |
| yoloe-26m-seg | 480 | onnx | 435 | 533 | 451 | 1170 | no |
| yoloe-26m-seg | 480 | openvino | 300 | 375 | 316 | 1080 | no |
| yoloe-26m-seg | 640 | torch | 467 | 651 | 483 | 1038 | no |
| yoloe-26m-seg | 640 | onnx | 709 | 930 | 725 | 1795 | no |
| yoloe-26m-seg | 640 | openvino | 640 | 693 | 656 | 1199 | no |

## Accuracy (AP50; classes with >= 10 boxes are ranked)

| model | imgsz | weighted AP50 | hand | utensil | cookware | appliance | ingredient | food | hazard | detector's own hand AP50 |
|---|---|---|---|---|---|---|---|---|---|---|
| yoloe-26s-seg | 480 | 0.446 | 0.36 | 0.44 | 0.53 | 0.49 | 0.37 | 0.55 | - | 0.13 |
| yoloe-26s-seg | 320 | 0.443 | 0.36 | 0.46 | 0.52 | 0.50 | 0.36 | 0.56 | - | 0.15 |
| yoloe-26m-seg | 320 | 0.442 | 0.36 | 0.46 | 0.50 | 0.49 | 0.39 | 0.50 | - | 0.21 |
| yoloe-26n-seg | 640 | 0.392 | 0.36 | 0.29 | 0.46 | 0.45 | 0.35 | 0.52 | - | 0.17 |
| yoloe-26n-seg | 480 | 0.391 | 0.36 | 0.26 | 0.48 | 0.45 | 0.35 | 0.52 | - | 0.14 |
| yoloe-26n-seg | 320 | 0.377 | 0.36 | 0.26 | 0.45 | 0.45 | 0.33 | 0.52 | - | 0.09 |
| yolov8m-oiv7 | 320 | 0.351 | 0.36 | 0.37 | 0.38 | 0.28 | 0.33 | 0.50 | - | 0.15 |
| yolov8s-oiv7 | 640 | 0.331 | 0.36 | 0.34 | 0.36 | 0.27 | 0.31 | 0.48 | - | 0.15 |
| yolov8s-oiv7 | 480 | 0.305 | 0.36 | 0.29 | 0.33 | 0.22 | 0.30 | 0.46 | - | 0.14 |
| yolov8s-oiv7 | 320 | 0.269 | 0.36 | 0.25 | 0.31 | 0.18 | 0.25 | 0.41 | - | 0.08 |
| yolov8n-oiv7 | 640 | 0.225 | 0.36 | 0.16 | 0.27 | 0.20 | 0.21 | 0.31 | - | 0.07 |
| yolov8n-oiv7 | 480 | 0.213 | 0.36 | 0.15 | 0.27 | 0.16 | 0.19 | 0.32 | - | 0.06 |
| yolov8n-oiv7 | 320 | 0.157 | 0.36 | 0.10 | 0.23 | 0.09 | 0.13 | 0.23 | - | 0.08 |

## Per-class, recommended config

| class | group | boxes | AP50 | precision | recall |
|---|---|---|---|---|---|
| scissors (few boxes) | utensil | 1 | 1.00 | 1.00 | 1.00 |
| toaster (few boxes) | appliance | 1 | 1.00 | 0.50 | 1.00 |
| pizza | food | 35 | 0.99 | 0.90 | 1.00 |
| refrigerator | appliance | 26 | 0.96 | 0.91 | 0.81 |
| bottle | ingredient | 71 | 0.83 | 0.86 | 0.83 |
| french_fries | food | 40 | 0.76 | 0.82 | 0.78 |
| cup | cookware | 79 | 0.72 | 0.76 | 0.73 |
| sandwich | food | 69 | 0.67 | 0.85 | 0.68 |
| strawberry | ingredient | 175 | 0.66 | 0.80 | 0.51 |
| plate | cookware | 110 | 0.65 | 0.81 | 0.65 |
| blender | appliance | 19 | 0.63 | 0.76 | 0.68 |
| bowl | cookware | 73 | 0.58 | 0.78 | 0.59 |
| broccoli | ingredient | 50 | 0.54 | 0.52 | 0.60 |
| pasta | ingredient | 35 | 0.53 | 0.89 | 0.46 |
| apple | ingredient | 82 | 0.53 | 0.57 | 0.59 |
| bread | ingredient | 97 | 0.52 | 0.66 | 0.40 |
| salad | food | 91 | 0.50 | 0.83 | 0.42 |
| fork | utensil | 46 | 0.50 | 0.58 | 0.48 |
| banana | ingredient | 26 | 0.47 | 0.52 | 0.46 |
| microwave | appliance | 30 | 0.45 | 0.78 | 0.47 |
| sink | appliance | 40 | 0.45 | 0.75 | 0.15 |
| carrot | ingredient | 107 | 0.44 | 0.75 | 0.36 |
| spoon | utensil | 59 | 0.44 | 0.68 | 0.46 |
| cutting_board | cookware | 10 | 0.40 | 1.00 | 0.30 |
| oven | appliance | 34 | 0.38 | 0.55 | 0.47 |
| potato | ingredient | 62 | 0.37 | 0.65 | 0.24 |
| knife | utensil | 68 | 0.37 | 0.79 | 0.34 |
| hand | hand | 84 | 0.36 | 0.97 | 0.36 |
| tomato | ingredient | 212 | 0.34 | 0.60 | 0.28 |
| kettle | appliance | 35 | 0.33 | 1.00 | 0.20 |
| frying_pan | cookware | 44 | 0.33 | 0.75 | 0.27 |
| cucumber | ingredient | 86 | 0.31 | 0.86 | 0.21 |
| cabbage | ingredient | 32 | 0.29 | 0.64 | 0.28 |
| bell_pepper | ingredient | 84 | 0.27 | 0.94 | 0.19 |
| pancake | food | 45 | 0.21 | 0.90 | 0.20 |
| stove | appliance | 23 | 0.21 | 0.31 | 0.39 |
| dessert | food | 276 | 0.20 | 0.67 | 0.18 |
| zucchini | ingredient | 66 | 0.19 | 0.58 | 0.11 |
| milk | ingredient | 20 | 0.15 | 1.00 | 0.15 |
| mushroom | ingredient | 56 | 0.13 | 0.33 | 0.02 |
| seafood | ingredient | 100 | 0.10 | 0.41 | 0.11 |
| cheese | ingredient | 147 | 0.05 | 0.83 | 0.03 |
| ladle (few boxes) | utensil | 2 | 0.00 | 0.00 | 0.00 |
| pressure_cooker (few boxes) | cookware | 3 | 0.00 | 0.00 | 0.00 |
| salt_pepper (few boxes) | ingredient | 4 | 0.00 | 0.00 | 0.00 |
| spatula (few boxes) | utensil | 4 | 0.00 | 0.00 | 0.00 |

## Caveats

- Open Images is what the `oiv7` models were trained on (different split), so this set favors them. Classes with no Open Images boxes cannot be scored here at all and are only reachable by YOLOE: whisk, tongs, peeler, grater, measuring_cup, pot, baking_tray, colander, egg, onion, garlic, lemon, orange, raw_meat, chicken, butter, rice, flour, boiling_water, fried_egg, scrambled_eggs, cooked_meat, soup, flame, smoke.
- Cooking-state classes (boiling water, fried egg, ...) are experimental and unscored; doneness stays with `/analyze`.
- FP32 only. INT8 quantization needs a calibration set and was not attempted.
- Ultralytics code and weights are AGPL-3.0.
- Add an in-house labeled kitchen set with `--extra-dir` to measure the real deployment domain.
