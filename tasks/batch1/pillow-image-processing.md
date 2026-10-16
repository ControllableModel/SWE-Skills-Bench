# Task: Add a Web Asset Preparation Helper Module

## Background

Pillow ships a number of high-level convenience helpers in `src/PIL/ImageOps.py`, but it has no single entry point for the common chore of preparing a raster asset for delivery on the web. This task adds a small new module, `src/PIL/WebImageOps.py`, that wraps the existing core API (`Image`) into a few task-oriented helpers and saves the result with sensible, format-appropriate parameters.

## Files to Create/Modify

- `src/PIL/WebImageOps.py` (new) — the helper module described below.
- `Tests/test_webimageops.py` (new) — deterministic unit tests for the module.

The module must depend only on Pillow itself (`from PIL import Image`, plus standard library). Do not add new third-party dependencies and do not invoke external binaries.

## Requirements

### `scale_to(image, *, width=None, height=None)`

Return a new resized image. The original image must not be mutated.

- When **both** `width` and `height` are given, the returned image has exactly those dimensions.
- When **only `width`** is given, the height is derived so the original aspect ratio is preserved; symmetrically when only `height` is given.
- The derived dimension must be computed from the original ratio and rounded to the nearest integer, with a floor of `1` pixel (a target that would round to `0` becomes `1`).
- When neither `width` nor `height` is given, raise `ValueError`.
- Downscaling must use high-quality resampling (the result of downscaling a smooth gradient must be visibly smoother than nearest-neighbour — see Acceptance Criteria for the objective check).

### `trim(image, *, padding=0)`

Return a new image with surrounding uniform border pixels removed (auto-crop), based on the image content.

- Detection of the content region must take any alpha channel into account: a fully transparent border must be trimmed even if its RGB values are not uniform.
- `padding` (a non-negative integer) re-adds that many pixels of margin on every side **after** trimming. The padding region must be transparent (alpha 0) — the returned image therefore always carries an alpha channel.
- If the image has **no** trimmable border (content already fills the frame) and `padding == 0`, the returned image has the same pixel dimensions as the input.
- If the entire image is empty/transparent (no content at all), return a copy of the original unchanged.
- A negative `padding` raises `ValueError`.

### `fit_thumbnail(image, size)`

Return a new image that fits inside a `size x size` square while preserving aspect ratio. `size` is a positive integer.

- The longer side of the result equals `size`; the shorter side is scaled proportionally. Neither side ever exceeds `size`.
- If the image is already smaller than `size` in both dimensions, it is returned unchanged in size (no upscaling).
- The original image must not be mutated.

### `save_web(image, path, *, quality=None)`

Persist `image` to `path`, choosing save parameters from the destination file extension (case-insensitive). Create any missing parent directories.

- `.png` → lossless save with size optimisation enabled.
- `.jpg` / `.jpeg` → lossy save. JPEG cannot store transparency, so an image carrying an alpha channel must first be flattened onto an **opaque white** background using its alpha as the compositing mask; fully transparent input pixels therefore become white in the output.
- `.webp` → lossy save honouring `quality`.
- A default quality must be applied for the lossy formats when `quality` is `None`; an explicit `quality` overrides it.
- An unsupported extension raises `ValueError`.
- The function returns the path it wrote to.

### Expected Functionality

- `scale_to(img, width=100)` on a 400x200 image → `(100, 50)`.
- `scale_to(img, width=3)` on a 400x200 image → `(3, 2)` (3*200/400 = 1.5 → rounds to 2).
- `trim` on a 100x100 opaque-white image containing a 20x20 red square at offset (40,40) → a 20x20 image; with `padding=5` → 30x30 with a transparent margin.
- `fit_thumbnail` on a 400x200 image with `size=100` → `(100, 50)`.
- `save_web` of an RGBA image with a fully transparent pixel to a `.jpg` path → reopened pixel reads white `(255, 255, 255)`.

## Acceptance Criteria

All checks are objectively verifiable with in-process, in-memory images (no network, no fixtures required):

1. `scale_to` honours both the both-dimensions and single-dimension (aspect-preserving, rounded, min-1) cases above, leaves the source image unmodified, and raises `ValueError` when given neither dimension.
2. `trim` removes a uniform opaque border, trims a fully transparent border regardless of underlying RGB, adds a transparent `padding` margin of the requested width, returns same-size output when there is nothing to trim, returns the original when the image is entirely empty, and raises `ValueError` on negative padding.
3. `fit_thumbnail` produces a result whose longer side equals `size`, never upscales, and preserves aspect ratio.
4. `save_web` writes PNG/JPEG (and, when WebP support is present, WebP), creates missing parent directories, flattens alpha onto white for JPEG so a transparent source pixel reopens as `(255, 255, 255)`, applies and overrides default quality, and raises `ValueError` for an unknown extension.
5. Quality of downscaling: downscaling a horizontal 256-wide gradient to width 64 with `scale_to` yields strictly smaller mean absolute difference between adjacent pixels than the same downscale done with `Image.Resampling.NEAREST`, confirming a high-quality resampling filter is used.

The added test file must pass:

```
python -m pytest Tests/test_webimageops.py -q
```
