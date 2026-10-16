"""
Test for 'pillow-image-processing' skill (variant ext7) — OG Card Composer.

The Agent adds ``src/PIL/OgCard.py`` to the Pillow repo: a deterministic
Open Graph social-card composer exposing::

    render_card(*, title, subtitle=None, background=None,
                bg_color="#1a1a2e", overlay_alpha=128) -> RGB Image (1200x630)

Verification strategy
---------------------
The module under test is loaded DIRECTLY from REPO_DIR/src/PIL/OgCard.py
(not from any installed ``PIL.OgCard``), so the Agent's actual file is what
is exercised. Fixture images are built with the installed ``PIL``.

L1 checks assert the deliverable files exist and expose the public API.
L2 checks exercise *behaviour* with in-memory images and Pillow's default
font, encoding every acceptance criterion as a concrete numeric/structural
assertion so that a naive stub (fixed size, ignored overlay_alpha, no text,
non-deterministic output, no validation) FAILS:

  * result is always RGB and exactly 1200x630
  * higher ``overlay_alpha`` strictly darkens a background-only corner sample
  * ``overlay_alpha == 0`` leaves the solid background untouched
  * the drawn title is horizontally centred (left/right margins ~equal)
  * empty title and out-of-range overlay_alpha raise ValueError
  * two identical calls are byte-identical (deterministic)
  * the title region is brighter than a darkened background-only region
  * a supplied ``background`` image actually fills/affects the canvas

The Agent's own native suite is finally driven exactly as the doc's
Acceptance Criteria requires::

    python -m pytest Tests/test_ogcard.py -q
"""

import importlib.util
import os
import subprocess
import sys

import pytest

# Installed Pillow is used only to build/inspect fixture images.
from PIL import Image


REPO_DIR = "/workspace/Pillow"
MODULE_PATH = os.path.join(REPO_DIR, "src", "PIL", "OgCard.py")

CANVAS_W = 1200
CANVAS_H = 630


def _load_ogcard():
    """Import the Agent's OgCard.py straight from the repo source tree."""
    assert os.path.isfile(MODULE_PATH), f"OgCard.py not found at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("_agent_ogcard", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mean_brightness(im, box):
    """Mean grayscale brightness over ``box`` = (left, top, right, bottom)."""
    region = im.convert("L").crop(box)
    px = list(region.getdata())
    return sum(px) / len(px) if px else 0.0


# A corner sample well away from any centred text -> pure (darkened) background.
_CORNER_BOX = (0, 0, 120, 120)
# A horizontal band across the vertical centre where the title is drawn.
_TITLE_BAND = (0, CANVAS_H // 2 - 40, CANVAS_W, CANVAS_H // 2 + 40)


class TestPillowImageProcessing:
    """Verify the OgCard deterministic Open Graph card composer."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/PIL/OgCard.py must exist."""
        assert os.path.isfile(MODULE_PATH), "OgCard.py was not created"

    def test_module_imports_and_exposes_api(self):
        """The module imports cleanly and exposes a callable render_card."""
        mod = _load_ogcard()
        assert hasattr(mod, "render_card"), "OgCard.render_card is missing"
        assert callable(mod.render_card), "OgCard.render_card is not callable"

    def test_native_test_file_exists(self):
        """Tests/test_ogcard.py (the Agent's own test) must exist."""
        tpath = os.path.join(self.REPO_DIR, "Tests", "test_ogcard.py")
        assert os.path.isfile(tpath), "Tests/test_ogcard.py was not created"

    # ------------------------------------------------------------------
    # L2: canvas contract.
    # ------------------------------------------------------------------

    def test_result_is_rgb_1200x630(self):
        """Result is always an RGB image of size exactly 1200x630."""
        mod = _load_ogcard()
        out = mod.render_card(title="Hello World")
        assert out.size == (CANVAS_W, CANVAS_H), (
            f"expected ({CANVAS_W},{CANVAS_H}) got {out.size}"
        )
        assert out.mode == "RGB", f"expected RGB mode got {out.mode!r}"

    def test_size_ignores_background_image_size(self):
        """A differently-sized background is filled to the 1200x630 canvas."""
        mod = _load_ogcard()
        bg = Image.new("RGB", (300, 900), (40, 90, 160))
        out = mod.render_card(title="Resize Me", background=bg)
        assert out.size == (CANVAS_W, CANVAS_H), (
            f"background must be resized to fill canvas; got {out.size}"
        )
        assert out.mode == "RGB"

    # ------------------------------------------------------------------
    # L2: darkening overlay behaviour (the core discriminator).
    # ------------------------------------------------------------------

    def test_overlay_alpha_strictly_darkens_background(self):
        """Increasing overlay_alpha strictly decreases corner brightness."""
        mod = _load_ogcard()
        color = "#3060c0"  # a mid-bright blue so darkening is measurable
        b0 = _mean_brightness(
            mod.render_card(title="T", bg_color=color, overlay_alpha=0),
            _CORNER_BOX,
        )
        b1 = _mean_brightness(
            mod.render_card(title="T", bg_color=color, overlay_alpha=96),
            _CORNER_BOX,
        )
        b2 = _mean_brightness(
            mod.render_card(title="T", bg_color=color, overlay_alpha=200),
            _CORNER_BOX,
        )
        assert b0 > b1 > b2, (
            "overlay_alpha must strictly darken background: "
            f"a0={b0:.2f} a96={b1:.2f} a200={b2:.2f}"
        )

    def test_overlay_alpha_zero_leaves_background_unchanged(self):
        """overlay_alpha == 0 leaves the solid background at its true colour."""
        mod = _load_ogcard()
        # Pure red background, sampled at a corner (no text there).
        out = mod.render_card(title="X", bg_color="#ff0000", overlay_alpha=0)
        px = out.convert("RGB").getpixel((5, 5))
        assert px == (255, 0, 0), (
            f"overlay_alpha=0 must leave background unchanged; corner={px}"
        )

    def test_overlay_alpha_full_blacks_background(self):
        """overlay_alpha == 255 produces a (near) fully black background corner."""
        mod = _load_ogcard()
        out = mod.render_card(title="X", bg_color="#ffffff", overlay_alpha=255)
        corner = _mean_brightness(out, _CORNER_BOX)
        assert corner < 5.0, (
            f"overlay_alpha=255 should fully blacken background; corner={corner:.2f}"
        )

    def test_overlay_alpha_out_of_range_raises(self):
        """overlay_alpha outside 0..255 raises ValueError (both ends)."""
        mod = _load_ogcard()
        with pytest.raises(ValueError):
            mod.render_card(title="X", overlay_alpha=-1)
        with pytest.raises(ValueError):
            mod.render_card(title="X", overlay_alpha=256)

    # ------------------------------------------------------------------
    # L2: text presence + centering.
    # ------------------------------------------------------------------

    def test_title_region_brighter_than_background(self):
        """The title band is brighter than a darkened background-only corner."""
        mod = _load_ogcard()
        out = mod.render_card(
            title="BRIGHT TITLE TEXT", bg_color="#101018", overlay_alpha=160
        )
        title_band = _mean_brightness(out, _TITLE_BAND)
        bg_corner = _mean_brightness(out, _CORNER_BOX)
        assert title_band > bg_corner, (
            "light title text must brighten the title region over the "
            f"darkened background: title={title_band:.2f} bg={bg_corner:.2f}"
        )

    def test_title_horizontally_centered(self):
        """The drawn title is horizontally centred (left/right margins ~equal)."""
        mod = _load_ogcard()
        # Solid dark background, no overlay, so any bright column is text ink.
        out = mod.render_card(
            title="CENTER", bg_color="#000000", overlay_alpha=0
        )
        g = out.convert("L")
        w, h = g.size
        px = g.load()
        # Columns that contain any non-trivially-bright (text) pixel.
        threshold = 64
        ink_cols = [
            x
            for x in range(w)
            if any(px[x, y] > threshold for y in range(h))
        ]
        assert ink_cols, "no title text was drawn (no bright columns found)"
        left_margin = ink_cols[0]
        right_margin = (w - 1) - ink_cols[-1]
        assert abs(left_margin - right_margin) <= 2, (
            "title not horizontally centred: "
            f"left_margin={left_margin} right_margin={right_margin}"
        )

    def test_subtitle_drawn_below_title(self):
        """A subtitle adds bright ink strictly below the title's ink rows."""
        mod = _load_ogcard()
        base = mod.render_card(
            title="MAINLINE", bg_color="#000000", overlay_alpha=0
        )
        withsub = mod.render_card(
            title="MAINLINE",
            subtitle="the secondary line",
            bg_color="#000000",
            overlay_alpha=0,
        )

        def ink_rows(im):
            g = im.convert("L")
            w, h = g.size
            px = g.load()
            return [
                y for y in range(h) if any(px[x, y] > 64 for x in range(w))
            ]

        base_rows = ink_rows(base)
        sub_rows = ink_rows(withsub)
        assert base_rows, "title produced no ink"
        assert sub_rows, "title+subtitle produced no ink"
        # The subtitle must extend the inked region further down the canvas.
        assert max(sub_rows) > max(base_rows), (
            "subtitle should add ink below the title: "
            f"title_bottom={max(base_rows)} subtitle_bottom={max(sub_rows)}"
        )

    # ------------------------------------------------------------------
    # L2: validation + determinism.
    # ------------------------------------------------------------------

    def test_empty_title_raises(self):
        """A required-but-empty title raises ValueError."""
        mod = _load_ogcard()
        with pytest.raises(ValueError):
            mod.render_card(title="")

    def test_deterministic_byte_identical(self):
        """Two calls with identical arguments yield byte-identical pixels."""
        mod = _load_ogcard()
        kwargs = dict(
            title="Deterministic",
            subtitle="same every time",
            bg_color="#224466",
            overlay_alpha=140,
        )
        a = mod.render_card(**kwargs)
        b = mod.render_card(**kwargs)
        assert a.tobytes() == b.tobytes(), (
            "render_card must be deterministic (byte-identical pixel data)"
        )

    def test_background_image_affects_output(self):
        """A supplied background image changes the result vs the solid colour."""
        mod = _load_ogcard()
        # Distinct, vivid background image so it cannot match bg_color by chance.
        bg = Image.new("RGB", (CANVAS_W, CANVAS_H), (0, 200, 50))
        with_bg = mod.render_card(
            title="BG", background=bg, bg_color="#000000", overlay_alpha=0
        )
        solid = mod.render_card(
            title="BG", background=None, bg_color="#000000", overlay_alpha=0
        )
        # Corner sample: background image green vs solid black -> must differ.
        cb = with_bg.convert("RGB").getpixel((5, 5))
        cs = solid.convert("RGB").getpixel((5, 5))
        assert cb != cs, (
            f"background image must affect output; bg_corner={cb} solid_corner={cs}"
        )
        # And the background-derived corner must carry the green channel.
        assert cb[1] > cb[0] and cb[1] > cb[2], (
            f"background image green should dominate the corner; got {cb}"
        )

    # ------------------------------------------------------------------
    # L2: the Agent's own native test suite must pass.
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """`python -m pytest Tests/test_ogcard.py -q` exits cleanly."""
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "Tests/test_ogcard.py", "-q"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            "native test suite failed:\n"
            f"STDOUT:\n{proc.stdout[-3000:]}\n\nSTDERR:\n{proc.stderr[-2000:]}"
        )
