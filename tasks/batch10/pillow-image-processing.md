# Task: Implement a Watermark Compositor

## Background

Distributing imagery for the web often requires stamping a semi-transparent watermark (a logo or text-rendered mark) onto a base image at a chosen corner with a margin, without altering the original asset on disk. This task adds `src/PIL/Watermark.py`, a deterministic alpha compositor.

## Files to Create/Modify

- `src/PIL/Watermark.py` (new) — the watermark compositor described below.
- `Tests/test_watermark.py` (new) — deterministic unit tests for the module.

The module must depend only on Pillow (`from PIL import Image`) and the standard library. Any text rendering must use Pillow's built-in default font so the test does not depend on a system font.

## Requirements

### `apply_watermark(base, mark, *, position="bottom-right", margin=10, opacity=1.0)`

Return a **new** `RGBA` image with `mark` composited over `base`. Neither input may be mutated.

### Positioning

- `position` is one of `"top-left"`, `"top-right"`, `"bottom-left"`, `"bottom-right"`, `"center"`. Any other value raises `ValueError`.
- `margin` (non-negative int) is the gap in pixels from the relevant edges; for `"center"` the mark is centred and `margin` is ignored.
- The mark is composited using its own alpha channel over the base (alpha compositing), so transparent regions of the mark do not obscure the base.

### Opacity

- `opacity` is a float in `0.0..1.0` (inclusive); a value outside that range raises `ValueError`.
- The mark's existing alpha is scaled by `opacity` before compositing, so `opacity=0.0` leaves the base visually unchanged and `opacity=1.0` uses the mark's native alpha.

### `text_watermark(base, text, *, position="bottom-right", margin=10, opacity=0.5, fill=(255, 255, 255))`

Render `text` with the default font into a transparent mark and composite it onto `base` via `apply_watermark`. Return the resulting `RGBA` image.

- An empty `text` raises `ValueError`.
- The rendered text region is brighter than the same region of the un-watermarked base when `fill` is light and `opacity > 0`.

### Determinism

- Identical arguments produce byte-identical output; no randomness or timestamps.

### Expected Functionality

- `apply_watermark(base, mark, position="bottom-right", margin=10)` places the mark's bottom-right corner `10` pixels from the base's bottom-right corner.
- `apply_watermark(base, mark, opacity=0.0)` returns an image whose pixels equal the base (converted to RGBA).
- `text_watermark(base, "DRAFT")` produces a visibly altered region where the text sits.

## Acceptance Criteria

All checks run with in-memory images and Pillow's default font.

1. The mark is placed at the correct corner/centre for each valid `position`, offset by `margin`, verified by inspecting which region of the output differs from the base.
2. `opacity=0.0` yields output equal to the base (in RGBA); higher opacity produces a larger pixel difference in the mark region.
3. Alpha compositing is used: a transparent area of the mark leaves the corresponding base pixels unchanged.
4. Invalid `position`, out-of-range `opacity`, and empty `text` each raise `ValueError`; neither input image is mutated.
5. Identical arguments produce byte-identical output (deterministic).

The added test file must pass:

```
python -m pytest Tests/test_watermark.py -q
```
