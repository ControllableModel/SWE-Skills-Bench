# Task: Implement a One-Step Web Optimise Pipeline

## Background

Preparing a hero or photo asset for production usually means resizing to a maximum width and re-encoding with a compression-friendly format in a single pass. This task adds `src/PIL/OptimizeOps.py`, a small pipeline that caps an image's width and writes a compressed result.

## Files to Create/Modify

- `src/PIL/OptimizeOps.py` (new) — the optimise pipeline described below.
- `Tests/test_optimizeops.py` (new) — deterministic unit tests for the module.

The module must depend only on Pillow (`from PIL import Image`) and the standard library.

## Requirements

### `optimize(image, path, *, max_width=1920, quality=85)`

Resize (if needed) and save `image` to `path` in one call. Return the path written.

### Resize stage

- If the image's width exceeds `max_width`, it is downscaled so its width equals `max_width`, with the height scaled proportionally (aspect ratio preserved, derived height rounded to nearest integer, floor `1`). A high-quality resampling filter must be used.
- If the image's width is already `<= max_width`, it is left at its original size (no upscaling).
- The original image object must not be mutated.

### Save stage

- The destination format is derived from the file extension (case-insensitive): `.webp`, `.jpg`/`.jpeg`, and `.png` are supported; any other extension raises `ValueError`.
- For lossy formats (`webp`, `jpg`/`jpeg`) the `quality` argument is forwarded to the encoder.
- For JPEG output, an image carrying an alpha channel is flattened onto an **opaque white** background using its alpha as the mask before saving (a fully transparent source pixel reopens as white).
- For `.png`, lossless optimisation is enabled and `quality` is ignored without raising.
- Missing parent directories of `path` are created.

### `optimize_bytes(image, fmt, *, max_width=1920, quality=85)`

Same resize+encode behaviour but returns the encoded image as a `bytes` object instead of writing to disk. `fmt` is one of `"webp"`, `"jpeg"`, `"png"` (case-insensitive); an unknown value raises `ValueError`.

### Expected Functionality

- `optimize(img, "out.webp", max_width=800)` on a 1600×900 image → written file reopens at width `800`, height `450`.
- `optimize(img, "out.webp", max_width=4000)` on a 1600×900 image → reopens at the original `1600×900`.
- `optimize_bytes(img, "jpeg")` returns non-empty `bytes` that reopen as a JPEG.

## Acceptance Criteria

All checks run with in-memory images.

1. An image wider than `max_width` is downscaled to exactly `max_width` with proportional height; one already within the cap is unchanged in size.
2. A lower `quality` yields a strictly smaller lossy output (file or bytes) than a higher `quality` for the same source.
3. JPEG output flattens alpha onto white (a transparent source pixel reopens as `(255, 255, 255)`).
4. An unsupported extension / format raises `ValueError`, missing directories are created, and the source image is unmodified.
5. `optimize_bytes` returns valid encoded bytes that Pillow can reopen in the requested format.

The added test file must pass:

```
python -m pytest Tests/test_optimizeops.py -q
```
