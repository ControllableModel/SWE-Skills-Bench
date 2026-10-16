# Task: Implement a Favicon / Icon Set Generator

## Background

Shipping a logo for the web means deriving a set of square icon assets at standard sizes (e.g. 16, 32, 180, 512) from a single source, with surrounding whitespace removed first and a square, centred canvas around the content. This task adds `src/PIL/IconSet.py`.

## Files to Create/Modify

- `src/PIL/IconSet.py` (new) — the icon-set generator described below.
- `Tests/test_iconset.py` (new) — deterministic unit tests for the module.

The module must depend only on Pillow (`from PIL import Image`) and the standard library. The test must write files under a temporary directory (`tmp_path`); no network.

## Requirements

### `square_canvas(image)`

Return a **new** `RGBA` image that is a square whose side equals the longer side of the input, with the original content centred and the surrounding area fully transparent. The input must not be mutated.

- A 40×20 input → an 40×40 square with the content vertically centred (10px transparent margin top and bottom) and a transparent background.
- An already-square input → same-size square copy.

### `generate(image, dst_dir, sizes, *, trim=True, name="icon")`

Produce one square PNG per requested size and return a dict mapping each size to the written file path.

- When `trim` is true, surrounding uniform / transparent border pixels are removed from the source before squaring (alpha-aware, as for an auto-crop).
- After trimming (if any), the content is placed on a centred square canvas, then scaled to `size`×`size` using a high-quality resampling filter.
- Each output is a `size`×`size` PNG saved as `{name}-{size}.png` in `dst_dir` (created if missing).
- `sizes` must be a non-empty iterable of positive integers; an empty `sizes` or any non-positive size raises `ValueError`.
- Every written PNG must preserve transparency in its margin (it is saved in a mode that supports alpha).

### Expected Functionality

- `square_canvas` on a 60×30 image → a 60×60 `RGBA` image with transparent top/bottom margins of 15px each.
- `generate(logo, dst, [16, 32, 512])` → three PNG files of sizes 16×16, 32×32, 512×512.
- With `trim=True`, a logo padded with a transparent border produces icons whose content fills the square (the border is gone).

## Acceptance Criteria

All checks write real files under `tmp_path`.

1. `square_canvas` returns a square `RGBA` image whose side equals the longer input side, with the content centred and transparent margins, without mutating the input.
2. `generate` writes exactly one `size`×`size` PNG per requested size with the expected filenames, each in an alpha-capable mode.
3. With `trim=True`, a transparently-bordered source yields icons whose opaque content reaches the square edges (border removed); with `trim=False`, the border is retained.
4. An empty `sizes` or any non-positive size raises `ValueError`, and `dst_dir` is created when missing.
5. Reopening a generated PNG confirms its declared size and that transparency is preserved in the margin.

The added test file must pass:

```
python -m pytest Tests/test_iconset.py -q
```
