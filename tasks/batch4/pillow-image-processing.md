# Task: Implement an Auto-Trim Helper with Padding

## Background

Logos and icons supplied for the web often arrive surrounded by a flat border (solid colour or transparency) that should be cropped away before use. Pillow exposes `Image.getbbox` and `Image.crop` but no convenience that combines them with alpha awareness and an optional re-added margin. This task adds `src/PIL/TrimOps.py`.

## Files to Create/Modify

- `src/PIL/TrimOps.py` (new) — the trim helper described below.
- `Tests/test_trimops.py` (new) — deterministic unit tests for the module.

The module must depend only on Pillow (`from PIL import Image`) and the standard library.

## Requirements

### `trim(image, *, padding=0, border_color=None)`

Return a **new** image with the surrounding uniform border removed (auto-crop). The input must not be mutated.

### Detection rules

- When `border_color` is `None`, the border colour to remove is inferred from the image's top-left corner pixel.
- Detection must take any alpha channel into account: a fully transparent border must be trimmed even when its underlying RGB values are not uniform.
- When `border_color` is given as an RGB(A) tuple, that exact colour is what gets trimmed from the edges.

### Padding rules

- `padding` is a non-negative integer; it re-adds that many pixels of margin on every side **after** trimming.
- The re-added margin must be transparent (alpha 0), so the returned image always carries an alpha channel when `padding > 0`.
- A negative `padding` raises `ValueError`.

### Edge cases

- If the image content already fills the frame (nothing to trim) and `padding == 0`, the returned image has the same pixel dimensions as the input.
- If the entire image is a single uniform colour / fully transparent (no content to keep), return a copy of the original unchanged.

### Expected Functionality

- `trim` on a 100×100 opaque-white image containing a 20×20 red square at offset (40, 40) → a 20×20 image.
- The same input with `padding=5` → a 30×30 image whose 5-pixel border ring is transparent.
- A 50×50 image whose border is fully transparent but whose transparent pixels have varying RGB → still trimmed to the opaque content bounds.

## Acceptance Criteria

All checks run with in-memory images.

1. `trim` removes a uniform opaque border down to the content bounding box.
2. `trim` removes a fully transparent border regardless of the RGB values beneath it.
3. `padding=N` enlarges each side by exactly `N` pixels of fully transparent margin.
4. An image with no trimmable border and `padding == 0` returns same-size output.
5. A wholly uniform / empty image returns an unchanged-size copy.
6. Negative padding raises `ValueError`, and the source image is unchanged after every call.

The added test file must pass:

```
python -m pytest Tests/test_trimops.py -q
```
