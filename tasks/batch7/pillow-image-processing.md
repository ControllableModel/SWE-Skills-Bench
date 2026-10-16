# Task: Implement an OG Card Composer

## Background

Social-share (Open Graph) card images are a fixed 1200×630 canvas with a title and subtitle drawn over a background, darkened for legibility. This task adds `src/PIL/OgCard.py`, a deterministic composer that builds such a card from a solid colour or background image plus centred text.

## Files to Create/Modify

- `src/PIL/OgCard.py` (new) — the card composer described below.
- `Tests/test_ogcard.py` (new) — deterministic unit tests for the module.

The module must depend only on Pillow (`from PIL import Image, ImageDraw, ImageFont`) and the standard library. The renderer must use Pillow's built-in default font so the test does not depend on any system font being installed.

## Requirements

### `render_card(*, title, subtitle=None, background=None, bg_color="#1a1a2e", overlay_alpha=128)`

Return a new `RGB` image of size exactly `1200 × 630`.

### Background

- When `background` is a Pillow `Image`, it is resized to fill the 1200×630 canvas (aspect ratio need not be preserved — it fills the frame).
- When `background` is `None`, the canvas is filled with the solid `bg_color`.

### Darkening overlay

- A semi-transparent black overlay with alpha `overlay_alpha` (0–255) is composited over the background before text is drawn, so the mean brightness of the background region is reduced relative to the un-darkened background.
- `overlay_alpha == 0` leaves the background unchanged; `overlay_alpha == 255` produces a fully black background region behind text.
- An `overlay_alpha` outside `0..255` raises `ValueError`.

### Text

- `title` is required (empty string raises `ValueError`); `subtitle` is optional.
- Title and subtitle are horizontally centred on the canvas. The drawn title's horizontal extent must be centred to within a small tolerance (its left and right margins differ by at most 2 pixels).
- The subtitle, when present, is drawn below the title and is also horizontally centred.
- Text is rendered in a light colour so the title region is brighter than the darkened background behind it.

### Determinism

- Calling `render_card` twice with identical arguments must produce byte-identical pixel data (no randomness, no timestamps).

## Acceptance Criteria

All checks run with in-memory images and Pillow's default font; no system fonts or network required.

1. The result is always an `RGB` image of size `1200 × 630`.
2. With `background=None` and a known `bg_color`, increasing `overlay_alpha` strictly decreases the mean brightness of a background sample region (a corner away from the text).
3. The horizontal centre of the drawn title is within 2 pixels of the canvas centre (left/right margins approximately equal).
4. A required-but-empty `title` and an out-of-range `overlay_alpha` each raise `ValueError`.
5. Two calls with identical arguments yield byte-identical output (deterministic).
6. The text region behind the title is brighter than a darkened background-only region, confirming text was actually drawn.

The added test file must pass:

```
python -m pytest Tests/test_ogcard.py -q
```
