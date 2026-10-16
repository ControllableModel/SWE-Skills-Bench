# Task: Implement a Bounded Thumbnail Generator

## Background

Generating a thumbnail that fits inside a square box while preserving aspect ratio and never upscaling is a recurring need when preparing gallery and preview assets. Pillow's `Image.thumbnail` mutates the image in place and has subtle rounding behaviour. This task adds `src/PIL/ThumbOps.py` with a non-mutating, predictable thumbnail helper.

## Files to Create/Modify

- `src/PIL/ThumbOps.py` (new) — the thumbnail helper described below.
- `Tests/test_thumbops.py` (new) — deterministic unit tests for the module.

The module must depend only on Pillow (`from PIL import Image`) and the standard library.

## Requirements

### `make_thumbnail(image, size)`

Return a **new** image that fits inside a `size` × `size` square while preserving aspect ratio. `size` is a positive integer; a non-positive `size` raises `ValueError`. The input image must not be mutated.

- The **longer** side of the result equals `size`; the shorter side is scaled proportionally and rounded to the nearest integer, with a floor of `1`.
- Neither side of the result ever exceeds `size`.
- If the image is already smaller than `size` in **both** dimensions, it is returned unchanged in size (no upscaling).
- A square input produces a `size` × `size` result.

### `make_thumbnail_box(image, width, height)`

Return a **new** image that fits inside a `width` × `height` rectangle, preserving aspect ratio and never upscaling.

- The result fits entirely within the box; when the image had to shrink, at least one side equals its corresponding bound.
- `width` and `height` must be positive; otherwise raise `ValueError`.

### Resampling

Downscaling must use a high-quality resampling filter (objective check below).

### Expected Functionality

- `make_thumbnail(img, 100)` on a 400×200 image → `(100, 50)`.
- `make_thumbnail(img, 100)` on a 200×400 image → `(50, 100)`.
- `make_thumbnail(img, 500)` on a 400×200 image → `(400, 200)` (no upscale).
- `make_thumbnail_box(img, 100, 100)` on a 400×200 image → `(100, 50)`.

## Acceptance Criteria

All checks run with in-memory images.

1. `make_thumbnail` makes the longer side exactly `size`, keeps both sides `<= size`, preserves aspect ratio, and never upscales an already-small image.
2. `make_thumbnail` raises `ValueError` for non-positive `size` and leaves the source image's size unchanged.
3. `make_thumbnail_box` fits within the rectangle, never upscales, and raises `ValueError` for non-positive bounds.
4. Downscaling a 256-wide gradient with `make_thumbnail` to a longer-side of 64 yields strictly smaller adjacent-pixel mean absolute difference than the same operation with `Image.Resampling.NEAREST`.

The added test file must pass:

```
python -m pytest Tests/test_thumbops.py -q
```
