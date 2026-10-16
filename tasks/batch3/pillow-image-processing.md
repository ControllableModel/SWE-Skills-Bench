# Task: Implement an Aspect-Ratio Resize Helper

## Background

Pillow's `Image.resize` takes an explicit `(width, height)` and does no aspect-ratio bookkeeping. This task adds a new module `src/PIL/ResizeOps.py` that resizes by a single constraining dimension (or a max bounding box) while preserving the original proportions, using a high-quality downscaling filter.

## Files to Create/Modify

- `src/PIL/ResizeOps.py` (new) — the resize helpers described below.
- `Tests/test_resizeops.py` (new) — deterministic unit tests for the module.

The module must depend only on Pillow (`from PIL import Image`) and the standard library.

## Requirements

### `resize_to(image, *, width=None, height=None)`

Return a **new** image (the input must not be mutated).

- When both `width` and `height` are given, the result has exactly those dimensions.
- When only `width` is given, the height is derived from the original aspect ratio; symmetrically when only `height` is given.
- The derived dimension is computed from the original ratio and rounded to the nearest integer, with a floor of `1` pixel.
- When neither dimension is given, raise `ValueError`.
- A `width` or `height` of `0` or negative raises `ValueError`.

### `fit_within(image, max_width, max_height)`

Return a **new** image scaled so it fits entirely inside the `max_width` × `max_height` box while preserving aspect ratio.

- The result must not exceed either bound on any side.
- At least one side of the result equals its corresponding bound when the image had to be shrunk (the image is scaled by the single most-constraining ratio).
- If the image already fits inside the box, it is returned unchanged in size (no upscaling).

### Downscaling quality

Downscaling must use a high-quality resampling filter (not nearest-neighbour). The objective check is in the Acceptance Criteria.

### Expected Functionality

- `resize_to(img, width=100)` on a 400×200 image → `(100, 50)`.
- `resize_to(img, width=3)` on a 400×200 image → `(3, 2)` (3·200/400 = 1.5 → 2).
- `fit_within(img, 100, 100)` on a 400×200 image → `(100, 50)`.
- `fit_within(img, 1000, 1000)` on a 400×200 image → `(400, 200)` (no upscale).

## Acceptance Criteria

All checks run with in-memory images.

1. `resize_to` honours both-dimensions, width-only, and height-only cases with correct aspect-preserving, rounded, min-1 results, and raises `ValueError` for the no-dimension and non-positive cases.
2. `fit_within` never exceeds either bound, touches a bound when shrinking, and never upscales an already-fitting image.
3. Neither helper mutates the source image (its size is unchanged after the call).
4. Downscaling a horizontal 256-wide smooth gradient to width 64 via `resize_to` yields a strictly smaller mean absolute difference between adjacent pixels than the same downscale performed with `Image.Resampling.NEAREST`, confirming a high-quality filter is used.

The added test file must pass:

```
python -m pytest Tests/test_resizeops.py -q
```
