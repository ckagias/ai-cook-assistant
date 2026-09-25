# Reference image sources

None of these are original photos - all three installed reference images were
found via `scripts/fetch_reference_candidates.py` (Wikimedia Commons) and
installed with `scripts/add_reference.py`, which bakes in EXIF rotation,
downsizes to fit 1024x1024, and re-encodes as JPEG under 200KB.

## pasta_boiling.jpg (pasta, step 0)

- Source: https://commons.wikimedia.org/wiki/File:2008-07-05_Water_boiling_in_cooking_pot.jpg
- Author: Ildar Sagdejev (Specious)
- Licence: CC BY-SA 4.0

## pasta_cooked.jpg (pasta, step 1)

- Source: https://commons.wikimedia.org/wiki/File:Spaghetti_boiling.jpg
- Author: Bodhi Peace
- Licence: CC BY-SA 4.0

## eggs_done.jpg (scrambled_eggs, step 1)

- Source: https://commons.wikimedia.org/wiki/File:Scrambled_eggs.png
- Author: not credited on the Commons file page
- Licence: CC BY-SA 3.0

## Empty slots

- **pancake_ready_to_flip.jpg** (pancakes, step 2) - empty.
  `fetch_reference_candidates.py` found no raster image with a reusable
  licence for "pancake batter cooking on griddle bubbles". Commons has
  plenty of finished-pancake photos, but very few mid-cook action shots
  that are actually freely licensed. `vision.py` skips the reference-image
  comparison silently when the file is missing, so this is a quality gap,
  not a bug.
- **pancake_done.jpg** (pancakes, step 3) - empty, same reason as above for
  "pancake flipping in frying pan".

Re-run `python scripts/fetch_reference_candidates.py pancakes` periodically -
Commons' inventory changes over time, or shoot these two directly in a real
kitchen and install with `add_reference.py`.
