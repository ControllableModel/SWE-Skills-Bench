"""
Test for 'pillow-image-processing' skill (variant ext4) — Auto-Trim Helper.

This variant is DISTINCT from ext1. The Agent must add a single new module
``src/PIL/TrimOps.py`` exposing one public function::

    trim(image, *, padding=0, border_color=None)

that auto-crops a uniform / alpha-transparent border off an image (built on
``Image.getbbox`` + ``Image.crop``), optionally re-adding a fully transparent
margin, with the following contract (from the variant requirement doc):

  * border colour inferred from the top-left corner when ``border_color`` is
    ``None``; an explicit RGB(A) tuple trims exactly that colour;
  * detection is alpha-aware — a fully transparent border is trimmed even when
    the underlying RGB is non-uniform;
  * ``padding`` re-adds N transparent pixels per side AFTER trimming, so the
    result gains an alpha channel when ``padding > 0``;
  * negative ``padding`` raises ``ValueError``;
  * content that fills the frame with ``padding == 0`` returns same-size output;
  * a wholly uniform / empty image returns an unchanged-size copy;
  * the source image is never mutated.

The module under test is loaded DIRECTLY from REPO_DIR/src/PIL/TrimOps.py so the
Agent's actual file is exercised (not any installed PIL.TrimOps). Fixture images
are built with the installed ``PIL``.

Verification strategy: load the Agent module by path and drive concrete
in-memory pixel cases (discriminative — a stub that returns the input unchanged,
ignores alpha, ignores padding, or mutates the source must FAIL), then run the
Agent's own native acceptance command as the final gate.

Native command verified by Acceptance Criteria:
    python -m pytest Tests/test_trimops.py -q
"""

import importlib.util
import os
import subprocess
import sys

import pytest

# The installed Pillow is used only to build/inspect fixture images.
from PIL import Image


REPO_DIR = "/workspace/Pillow"
MODULE_PATH = os.path.join(REPO_DIR, "src", "PIL", "TrimOps.py")


def _load_trimops():
    """Import the Agent's TrimOps.py straight from the repo source tree."""
    assert os.path.isfile(MODULE_PATH), f"TrimOps.py not found at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("_agent_trimops", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _white_canvas_with_red_square():
    """100x100 opaque white with a 20x20 red square at (40,40)."""
    src = Image.new("RGB", (100, 100), (255, 255, 255))
    src.paste(Image.new("RGB", (20, 20), (255, 0, 0)), (40, 40))
    return src


class TestPillowImageProcessing:
    """Verify the TrimOps auto-trim helper (variant ext4)."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/PIL/TrimOps.py must exist."""
        assert os.path.isfile(MODULE_PATH), "TrimOps.py was not created"

    def test_module_imports_and_exposes_trim(self):
        """The module imports cleanly and exposes a callable ``trim``."""
        mod = _load_trimops()
        assert hasattr(mod, "trim"), "TrimOps.trim is missing"
        assert callable(mod.trim), "TrimOps.trim is not callable"

    def test_native_test_file_exists(self):
        """Tests/test_trimops.py (the Agent's own test) must exist."""
        tpath = os.path.join(self.REPO_DIR, "Tests", "test_trimops.py")
        assert os.path.isfile(tpath), "Tests/test_trimops.py was not created"

    # ------------------------------------------------------------------
    # L2: core trim behaviour — uniform opaque border.
    # ------------------------------------------------------------------

    def test_trim_uniform_opaque_border_to_content(self):
        """White border around a 20x20 red square -> exactly 20x20 result.

        A stub returning the input unchanged (100x100) fails this.
        """
        mod = _load_trimops()
        out = mod.trim(_white_canvas_with_red_square())
        assert out.size == (20, 20), f"expected (20,20) got {out.size}"

    def test_trim_returns_new_image_source_unmutated(self):
        """trim must return a NEW image and leave the source untouched."""
        mod = _load_trimops()
        src = _white_canvas_with_red_square()
        # Snapshot a few source pixels before the call.
        before_corner = src.getpixel((0, 0))
        before_center = src.getpixel((50, 50))
        out = mod.trim(src)
        assert out is not src, "trim must return a new image, not the same object"
        assert src.size == (100, 100), "trim must not resize the source"
        assert src.getpixel((0, 0)) == before_corner, "source corner mutated"
        assert src.getpixel((50, 50)) == before_center, "source content mutated"

    def test_trim_preserves_content_pixels(self):
        """The cropped result must contain the actual content, not blank fill.

        Guards against a stub that returns a correctly-sized but empty image.
        """
        mod = _load_trimops()
        out = mod.trim(_white_canvas_with_red_square()).convert("RGB")
        assert out.size == (20, 20)
        # Every pixel of the cropped square should be red.
        assert out.getpixel((0, 0)) == (255, 0, 0), "content not preserved"
        assert out.getpixel((10, 10)) == (255, 0, 0), "content not preserved"
        assert out.getpixel((19, 19)) == (255, 0, 0), "content not preserved"

    def test_trim_offset_content_bounds(self):
        """Asymmetric content bounds are computed correctly (not hardcoded).

        A 12x7 block at offset (33,9) on a 80x60 white canvas -> 12x7.
        """
        mod = _load_trimops()
        src = Image.new("RGB", (80, 60), (255, 255, 255))
        src.paste(Image.new("RGB", (12, 7), (0, 128, 64)), (33, 9))
        out = mod.trim(src).convert("RGB")
        assert out.size == (12, 7), f"expected (12,7) got {out.size}"
        assert out.getpixel((0, 0)) == (0, 128, 64), "wrong crop origin"

    # ------------------------------------------------------------------
    # L2: padding behaviour.
    # ------------------------------------------------------------------

    def test_trim_padding_enlarges_and_is_transparent(self):
        """padding=5 -> 30x30; the re-added ring is fully transparent."""
        mod = _load_trimops()
        out = mod.trim(_white_canvas_with_red_square(), padding=5)
        assert out.size == (30, 30), f"expected (30,30) got {out.size}"
        assert "A" in out.getbands(), "padded result must carry an alpha channel"
        a = out.getchannel("A")
        # Outer ring (padding) transparent on all four sides.
        assert a.getpixel((0, 0)) == 0, "top-left padding must be alpha 0"
        assert a.getpixel((29, 0)) == 0, "top-right padding must be alpha 0"
        assert a.getpixel((0, 29)) == 0, "bottom-left padding must be alpha 0"
        assert a.getpixel((29, 29)) == 0, "bottom-right padding must be alpha 0"
        # Interior (former content) must be opaque.
        assert a.getpixel((15, 15)) == 255, "content pixel must be opaque"
        # And the content colour survives under the padding offset.
        assert out.convert("RGB").getpixel((15, 15)) == (255, 0, 0)

    def test_trim_padding_amount_exact(self):
        """A different padding (3) shifts content by exactly that many pixels."""
        mod = _load_trimops()
        out = mod.trim(_white_canvas_with_red_square(), padding=3)
        # 20x20 content + 3 each side = 26x26.
        assert out.size == (26, 26), f"expected (26,26) got {out.size}"
        a = out.getchannel("A")
        # Pixel at (2,2) still in the padding ring (transparent),
        # pixel at (3,3) is the first content pixel (opaque).
        assert a.getpixel((2, 2)) == 0, "pixel inside 3px ring must be transparent"
        assert a.getpixel((3, 3)) == 255, "first content pixel must be opaque"

    def test_trim_negative_padding_raises(self):
        """Negative padding -> ValueError; source unchanged after the failed call."""
        mod = _load_trimops()
        src = _white_canvas_with_red_square()
        with pytest.raises(ValueError):
            mod.trim(src, padding=-1)
        assert src.size == (100, 100), "source must be intact after ValueError"

    # ------------------------------------------------------------------
    # L2: alpha-aware detection.
    # ------------------------------------------------------------------

    def test_trim_alpha_transparent_border_nonuniform_rgb(self):
        """A fully transparent border is trimmed even with non-uniform RGB.

        This is the key alpha-awareness case: a naive RGB-only implementation
        that infers the border colour from corner RGB would NOT trim, because
        the transparent border pixels have differing RGB values.
        """
        mod = _load_trimops()
        src = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
        bpx = src.load()
        # Scribble varied opaque-looking RGB into the (transparent) border ring.
        for x in range(50):
            bpx[x, 0] = (123, 45, 67, 0)
            bpx[x, 49] = (9, 200, 14, 0)
        for y in range(50):
            bpx[0, y] = (200, 10, 250, 0)
            bpx[49, y] = (5, 5, 5, 0)
        # Opaque content block: 22x22 at (14,14)..(35,35).
        src.paste(Image.new("RGBA", (22, 22), (10, 220, 30, 255)), (14, 14))
        out = mod.trim(src)
        assert out.size == (22, 22), (
            f"alpha-aware trim should yield (22,22) got {out.size}"
        )
        assert out.convert("RGBA").getpixel((0, 0)) == (10, 220, 30, 255), (
            "content not preserved after alpha-aware trim"
        )

    def test_trim_explicit_border_color(self):
        """An explicit border_color trims exactly that colour from the edges.

        Corner is NOT the border colour, so an implementation that infers from
        the corner would trim the wrong colour (or nothing).
        """
        mod = _load_trimops()
        # Background = blue border to remove; corner pixel deliberately differs.
        src = Image.new("RGB", (40, 40), (0, 0, 255))
        src.paste(Image.new("RGB", (10, 10), (255, 255, 0)), (15, 15))
        out = mod.trim(src, border_color=(0, 0, 255)).convert("RGB")
        assert out.size == (10, 10), f"expected (10,10) got {out.size}"
        assert out.getpixel((0, 0)) == (255, 255, 0), "wrong content after trim"

    # ------------------------------------------------------------------
    # L2: edge cases.
    # ------------------------------------------------------------------

    def test_trim_no_border_same_size(self):
        """Content fills the frame and padding=0 -> dimensions unchanged."""
        mod = _load_trimops()
        # Distinct corners so there is genuinely no uniform border to remove.
        src = Image.new("RGB", (30, 30), (10, 10, 10))
        src.putpixel((0, 0), (255, 0, 0))
        src.putpixel((29, 29), (0, 0, 255))
        out = mod.trim(src)
        assert out.size == (30, 30), f"expected unchanged (30,30) got {out.size}"

    def test_trim_empty_image_returns_copy_same_size(self):
        """A wholly uniform / fully transparent image is returned unchanged in size."""
        mod = _load_trimops()
        src = Image.new("RGBA", (40, 25), (0, 0, 0, 0))
        out = mod.trim(src)
        assert out is not src, "should return a copy, not the same object"
        assert out.size == (40, 25), f"empty image should be unchanged got {out.size}"

    def test_trim_uniform_opaque_image_returns_copy_same_size(self):
        """A single solid opaque colour (no content) returns an unchanged-size copy."""
        mod = _load_trimops()
        src = Image.new("RGB", (33, 21), (77, 77, 77))
        out = mod.trim(src)
        assert out.size == (33, 21), (
            f"uniform image should be unchanged got {out.size}"
        )

    # ------------------------------------------------------------------
    # L2: the Agent's own native test suite must pass (final gate).
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """`python -m pytest Tests/test_trimops.py -q` exits cleanly."""
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "Tests/test_trimops.py", "-q"],
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
