"""
Test for 'pillow-image-processing' skill (variant ext5) — Bounded Thumbnail
Generator.

Verifies the Agent's new module ``src/PIL/ThumbOps.py`` inside the Pillow repo,
providing a non-mutating, predictable thumbnail helper built on ``PIL.Image``:

  * ``make_thumbnail(image, size)``            — fit inside a size x size square,
    preserve aspect ratio, longer side == size, never upscale, ValueError on
    non-positive size, source image never mutated.
  * ``make_thumbnail_box(image, width, height)`` — fit inside a width x height
    rectangle, preserve aspect ratio, never upscale, ValueError on non-positive
    bounds.

The module under test is loaded DIRECTLY from REPO_DIR/src/PIL/ThumbOps.py
(not from any installed PIL.ThumbOps), so the Agent's actual file is what is
exercised. Fixture images and result inspection use the installed ``PIL``.

Verification strategy:
  * L1 — deliverables exist (module + native test file) and expose the two
    public callables.
  * L2 — dynamic behavioural checks of every Acceptance Criterion using
    in-memory images: exact output sizes, aspect-ratio preservation, the
    rounding/floor-of-1 rule, the no-upscale rule, ValueError on bad bounds,
    non-mutation of the source, and an objective high-quality-resampling check
    (smoother adjacent-pixel diff than NEAREST). A naive/stub implementation
    (returns input unchanged, ignores `size`, hardcodes a size, upscales, or
    uses NEAREST) fails at least one case.
  * L2 — the Agent's own native suite must pass:
        python -m pytest Tests/test_thumbops.py -q

Native command verified by Acceptance Criteria:
    python -m pytest Tests/test_thumbops.py -q
"""

import importlib.util
import math
import os
import subprocess
import sys

import pytest

# The installed Pillow is used only to build/inspect fixture images.
from PIL import Image


REPO_DIR = "/workspace/Pillow"
MODULE_PATH = os.path.join(REPO_DIR, "src", "PIL", "ThumbOps.py")


def _load_thumbops():
    """Import the Agent's ThumbOps.py straight from the repo source tree."""
    assert os.path.isfile(MODULE_PATH), f"ThumbOps.py not found at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("_agent_thumbops", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    # The module's own `from PIL import Image` resolves to installed Pillow.
    spec.loader.exec_module(mod)
    return mod


def _gradient(width, height):
    """A horizontal grayscale gradient (px value == x) returned as RGB."""
    grad = Image.new("L", (width, height))
    px = grad.load()
    for x in range(width):
        for y in range(height):
            px[x, y] = x % 256
    return grad.convert("RGB")


def _mean_abs_adjacent_diff(im):
    """Mean absolute difference between horizontally-adjacent grayscale pixels."""
    g = im.convert("L")
    w, h = g.size
    px = g.load()
    total = 0
    count = 0
    for y in range(h):
        for x in range(1, w):
            total += abs(px[x, y] - px[x - 1, y])
            count += 1
    return total / count if count else 0.0


class TestPillowImageProcessing:
    """Verify the ThumbOps bounded-thumbnail helpers."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/PIL/ThumbOps.py must exist."""
        assert os.path.isfile(MODULE_PATH), "ThumbOps.py was not created"

    def test_module_imports_and_exposes_api(self):
        """The module imports cleanly and exposes the two public callables."""
        mod = _load_thumbops()
        for name in ("make_thumbnail", "make_thumbnail_box"):
            assert hasattr(mod, name), f"ThumbOps.{name} is missing"
            assert callable(getattr(mod, name)), f"ThumbOps.{name} is not callable"

    def test_native_test_file_exists(self):
        """Tests/test_thumbops.py (the Agent's own test) must exist."""
        tpath = os.path.join(self.REPO_DIR, "Tests", "test_thumbops.py")
        assert os.path.isfile(tpath), "Tests/test_thumbops.py was not created"

    # ------------------------------------------------------------------
    # L2: make_thumbnail core sizing behaviour.
    # ------------------------------------------------------------------

    def test_make_thumbnail_landscape(self):
        """400x200, size=100 -> (100, 50); longer side == size, source intact."""
        mod = _load_thumbops()
        src = Image.new("RGB", (400, 200), (50, 60, 70))
        out = mod.make_thumbnail(src, 100)
        assert out.size == (100, 50), f"expected (100,50) got {out.size}"
        assert max(out.size) == 100, "longer side must equal size"
        assert max(out.size) <= 100 and min(out.size) <= 100, "no side may exceed size"
        assert src.size == (400, 200), "make_thumbnail must not mutate the source"
        assert out is not src, "make_thumbnail must return a new image"

    def test_make_thumbnail_portrait(self):
        """200x400, size=100 -> (50, 100); shorter side scaled, no overflow."""
        mod = _load_thumbops()
        src = Image.new("RGB", (200, 400), (50, 60, 70))
        out = mod.make_thumbnail(src, 100)
        assert out.size == (50, 100), f"expected (50,100) got {out.size}"
        assert max(out.size) == 100
        assert out.size[0] <= 100 and out.size[1] <= 100

    def test_make_thumbnail_square(self):
        """A square input produces an exact size x size result."""
        mod = _load_thumbops()
        src = Image.new("RGB", (300, 300), (10, 20, 30))
        out = mod.make_thumbnail(src, 128)
        assert out.size == (128, 128), f"expected (128,128) got {out.size}"

    def test_make_thumbnail_no_upscale(self):
        """Image smaller than size in both dims -> returned unchanged in size."""
        mod = _load_thumbops()
        src = Image.new("RGB", (400, 200), (50, 60, 70))
        out = mod.make_thumbnail(src, 500)
        assert out.size == (400, 200), f"must not upscale; got {out.size}"

    def test_make_thumbnail_rounding_and_min_one(self):
        """Shorter side rounds to nearest int with a floor of 1."""
        mod = _load_thumbops()
        # 400x200, size=3 -> longer side 3, shorter 3 * 200/400 = 1.5 -> 2.
        src = Image.new("RGB", (400, 200), (10, 10, 10))
        out = mod.make_thumbnail(src, 3)
        assert max(out.size) == 3, f"longer side must equal size; got {out.size}"
        assert out.size == (3, 2), f"expected (3,2) got {out.size}"
        # 1000x1, size=2 -> shorter side 2 * 1/1000 = 0.002 -> floored to 1.
        tall = Image.new("RGB", (1000, 1), (10, 10, 10))
        out2 = mod.make_thumbnail(tall, 2)
        assert out2.size[1] >= 1, f"min-1 floor violated: {out2.size}"
        assert max(out2.size) == 2, f"longer side must equal size; got {out2.size}"

    def test_make_thumbnail_preserves_aspect_ratio(self):
        """The output aspect ratio matches the input within rounding tolerance."""
        mod = _load_thumbops()
        src = Image.new("RGB", (640, 360), (1, 2, 3))  # 16:9
        out = mod.make_thumbnail(src, 200)
        assert max(out.size) == 200, f"longer side must be 200; got {out.size}"
        src_ratio = 640 / 360
        out_ratio = out.size[0] / out.size[1]
        assert math.isclose(src_ratio, out_ratio, rel_tol=0.02), (
            f"aspect ratio not preserved: src={src_ratio:.4f} out={out_ratio:.4f}"
        )

    def test_make_thumbnail_invalid_size_raises_and_no_mutation(self):
        """Non-positive size -> ValueError; source size unchanged afterwards."""
        mod = _load_thumbops()
        src = Image.new("RGB", (400, 200), (50, 60, 70))
        for bad in (0, -1, -100):
            with pytest.raises(ValueError):
                mod.make_thumbnail(src, bad)
        assert src.size == (400, 200), "source image must be unchanged after error"

    def test_make_thumbnail_high_quality_downscale(self):
        """Downscaling a 256-wide gradient to longer-side 64 is smoother than NEAREST.

        Objective Acceptance Criterion: adjacent-pixel mean-absolute-difference
        of the helper output must be strictly smaller than a NEAREST resize of
        the same gradient to the same dimensions. A NEAREST-based stub fails.
        """
        mod = _load_thumbops()
        grad = _gradient(256, 16)  # 256x16 landscape
        out = mod.make_thumbnail(grad, 64)
        assert out.size[0] == 64, f"expected width 64; got {out.size}"

        nearest = grad.resize((64, out.size[1]), Image.Resampling.NEAREST)
        smooth_diff = _mean_abs_adjacent_diff(out)
        nearest_diff = _mean_abs_adjacent_diff(nearest)
        assert smooth_diff < nearest_diff, (
            "downscale not smoother than NEAREST: "
            f"helper={smooth_diff:.4f} nearest={nearest_diff:.4f}"
        )

    # ------------------------------------------------------------------
    # L2: make_thumbnail_box behaviour.
    # ------------------------------------------------------------------

    def test_make_thumbnail_box_landscape_fits(self):
        """400x200 into 100x100 box -> (100,50); fits, longer side bound met."""
        mod = _load_thumbops()
        src = Image.new("RGB", (400, 200), (50, 60, 70))
        out = mod.make_thumbnail_box(src, 100, 100)
        assert out.size == (100, 50), f"expected (100,50) got {out.size}"
        assert out.size[0] <= 100 and out.size[1] <= 100, "result must fit the box"
        assert src.size == (400, 200), "must not mutate the source"

    def test_make_thumbnail_box_non_square_box(self):
        """A non-square box constrains by the binding dimension; result fits inside.

        400x200 into a 300x60 box: height is the binding constraint
        (200 -> 60, scale 0.3) -> width 400*0.3 = 120 -> (120, 60). At least one
        side equals its bound and neither exceeds the box.
        """
        mod = _load_thumbops()
        src = Image.new("RGB", (400, 200), (50, 60, 70))
        out = mod.make_thumbnail_box(src, 300, 60)
        assert out.size[0] <= 300 and out.size[1] <= 60, (
            f"result must fit within 300x60; got {out.size}"
        )
        assert out.size == (120, 60), f"expected (120,60) got {out.size}"
        assert out.size[0] == 300 or out.size[1] == 60, (
            f"at least one side must touch its bound; got {out.size}"
        )

    def test_make_thumbnail_box_no_upscale(self):
        """Image smaller than the box in both dims -> size unchanged."""
        mod = _load_thumbops()
        src = Image.new("RGB", (80, 40), (50, 60, 70))
        out = mod.make_thumbnail_box(src, 200, 200)
        assert out.size == (80, 40), f"must not upscale; got {out.size}"

    def test_make_thumbnail_box_invalid_bounds_raise(self):
        """Non-positive width or height -> ValueError."""
        mod = _load_thumbops()
        src = Image.new("RGB", (400, 200), (50, 60, 70))
        for w, h in ((0, 100), (100, 0), (-1, 100), (100, -5)):
            with pytest.raises(ValueError):
                mod.make_thumbnail_box(src, w, h)
        assert src.size == (400, 200), "source must be unchanged after error"

    # ------------------------------------------------------------------
    # L2: the Agent's own native test suite must pass.
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """`python -m pytest Tests/test_thumbops.py -q` exits cleanly."""
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "Tests/test_thumbops.py", "-q"],
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
