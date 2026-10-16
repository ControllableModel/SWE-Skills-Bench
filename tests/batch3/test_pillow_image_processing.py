"""
Test for 'pillow-image-processing' skill (variant ext3) —
Aspect-Ratio Resize Helper Module.

The Agent must create a new module ``src/PIL/ResizeOps.py`` inside the Pillow
repo that resizes by a single constraining dimension (or a bounding box) while
preserving aspect ratio, using a high-quality downscaling filter, plus a
deterministic unit-test file ``Tests/test_resizeops.py``.

Two public helpers are exercised:

  * ``resize_to(image, *, width=None, height=None)`` — explicit / single-axis
    aspect-preserving resize; derived dimension rounded to nearest int, floored
    to 1 px; ValueError for no-dimension and non-positive inputs; never mutates
    the source.
  * ``fit_within(image, max_width, max_height)`` — scale to fit entirely inside
    the box, touching a bound when shrinking, never upscaling.

Verification strategy:
  - The module under test is loaded DIRECTLY from REPO_DIR/src/PIL/ResizeOps.py
    (via importlib from the file path), so the Agent's actual file is what is
    exercised, regardless of any installed PIL.ResizeOps.
  - Fixture images are built with the installed ``PIL``; assertions check
    concrete result sizes, boundary/error cases, source immutability, and an
    objective high-quality-filter check (adjacent-pixel smoothness vs NEAREST).
  - A naive implementation (ignoring an input, hardcoding sizes, skipping the
    rounding/min-1/no-upscale rules, or using NEAREST) MUST fail these tests.
  - Finally the Agent's own native suite is driven exactly as the doc requires.

Native command verified by Acceptance Criteria:
    python -m pytest Tests/test_resizeops.py -q
"""

import importlib.util
import os
import subprocess
import sys

import pytest

# The installed Pillow is used only to build/inspect fixture images.
from PIL import Image


REPO_DIR = "/workspace/Pillow"
MODULE_PATH = os.path.join(REPO_DIR, "src", "PIL", "ResizeOps.py")


def _load_resizeops():
    """Import the Agent's ResizeOps.py straight from the repo source tree."""
    assert os.path.isfile(MODULE_PATH), f"ResizeOps.py not found at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("_agent_resizeops", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def _gradient(width, height):
    """A horizontal smooth gradient image (pixel value == x), as RGB."""
    grad = Image.new("L", (width, height))
    px = grad.load()
    for x in range(width):
        for y in range(height):
            px[x, y] = x % 256
    return grad.convert("RGB")


class TestPillowImageProcessing:
    """Verify the ResizeOps aspect-ratio resize helpers."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/PIL/ResizeOps.py must exist."""
        assert os.path.isfile(MODULE_PATH), "ResizeOps.py was not created"

    def test_module_imports_and_exposes_api(self):
        """The module imports cleanly and exposes the two public callables."""
        mod = _load_resizeops()
        for name in ("resize_to", "fit_within"):
            assert hasattr(mod, name), f"ResizeOps.{name} is missing"
            assert callable(getattr(mod, name)), f"ResizeOps.{name} is not callable"

    def test_native_test_file_exists(self):
        """Tests/test_resizeops.py (the Agent's own test) must exist."""
        tpath = os.path.join(self.REPO_DIR, "Tests", "test_resizeops.py")
        assert os.path.isfile(tpath), "Tests/test_resizeops.py was not created"

    # ------------------------------------------------------------------
    # L2: resize_to behaviour
    # ------------------------------------------------------------------

    def test_resize_to_both_dimensions_exact(self):
        """Both width and height given -> exactly those dimensions; source intact."""
        mod = _load_resizeops()
        src = Image.new("RGB", (400, 200), (120, 30, 200))
        out = mod.resize_to(src, width=64, height=128)
        assert out.size == (64, 128), f"expected (64,128) got {out.size}"
        assert src.size == (400, 200), "resize_to must not mutate the source image"
        # Must be a NEW image object, not the same instance.
        assert out is not src, "resize_to must return a new image"

    def test_resize_to_width_only_preserves_ratio(self):
        """Width only -> height derived from aspect ratio (400x200, w=100 -> 50)."""
        mod = _load_resizeops()
        src = Image.new("RGB", (400, 200), (10, 10, 10))
        out = mod.resize_to(src, width=100)
        assert out.size == (100, 50), f"expected (100,50) got {out.size}"
        assert src.size == (400, 200), "source must be unchanged"

    def test_resize_to_height_only_preserves_ratio(self):
        """Height only -> width derived from aspect ratio (400x200, h=50 -> 100)."""
        mod = _load_resizeops()
        src = Image.new("RGB", (400, 200), (10, 10, 10))
        out = mod.resize_to(src, height=50)
        assert out.size == (100, 50), f"expected (100,50) got {out.size}"

    def test_resize_to_rounding_nearest(self):
        """Derived dim rounds to NEAREST int (400x200 w=3 -> (3,2); 1.5 -> 2)."""
        mod = _load_resizeops()
        src = Image.new("RGB", (400, 200), (10, 10, 10))
        # 3 * 200/400 = 1.5 -> rounds to 2 (not truncated to 1).
        out = mod.resize_to(src, width=3)
        assert out.size == (3, 2), f"expected (3,2) got {out.size}"
        # 5 * 200/400 = 2.5 -> rounds to 2 (round-half logic still yields >=2).
        out2 = mod.resize_to(src, width=5)
        assert out2.size[0] == 5
        assert out2.size[1] in (2, 3), (
            f"5*200/400=2.5 should round to 2 or 3, got {out2.size[1]}"
        )

    def test_resize_to_min_one_floor(self):
        """A derived dimension that would round to 0 is floored to 1 pixel."""
        mod = _load_resizeops()
        # 1000 wide, 1 tall -> width=2 gives height 2*1/1000 = 0.002 -> floor 1.
        tall = Image.new("RGB", (1000, 1), (10, 10, 10))
        out = mod.resize_to(tall, width=2)
        assert out.size == (2, 1), f"min-1 floor violated: {out.size}"

    def test_resize_to_requires_a_dimension(self):
        """Neither width nor height -> ValueError."""
        mod = _load_resizeops()
        src = Image.new("RGB", (40, 20), (10, 10, 10))
        with pytest.raises(ValueError):
            mod.resize_to(src)

    def test_resize_to_non_positive_raises(self):
        """A width or height of 0 or negative -> ValueError."""
        mod = _load_resizeops()
        src = Image.new("RGB", (40, 20), (10, 10, 10))
        with pytest.raises(ValueError):
            mod.resize_to(src, width=0)
        with pytest.raises(ValueError):
            mod.resize_to(src, height=-5)
        with pytest.raises(ValueError):
            mod.resize_to(src, width=10, height=0)

    def test_resize_to_high_quality_downscale(self):
        """Downscaling a gradient is smoother than NEAREST (high-quality filter)."""
        mod = _load_resizeops()
        grad = _gradient(256, 16)

        out = mod.resize_to(grad, width=64)
        assert out.size[0] == 64, f"expected width 64 got {out.size}"

        nearest = grad.resize((64, out.size[1]), Image.Resampling.NEAREST)
        smooth_diff = _mean_abs_adjacent_diff(out)
        nearest_diff = _mean_abs_adjacent_diff(nearest)
        assert smooth_diff < nearest_diff, (
            "downscale not smoother than NEAREST: "
            f"helper={smooth_diff:.4f} nearest={nearest_diff:.4f}"
        )

    # ------------------------------------------------------------------
    # L2: fit_within behaviour
    # ------------------------------------------------------------------

    def test_fit_within_landscape_constrained_by_width(self):
        """400x200 into 100x100 box -> (100,50); width is the constraining side."""
        mod = _load_resizeops()
        src = Image.new("RGB", (400, 200), (50, 60, 70))
        out = mod.fit_within(src, 100, 100)
        assert out.size == (100, 50), f"expected (100,50) got {out.size}"
        # Touches a bound when shrinking.
        assert out.size[0] == 100, "constraining side must equal its bound"
        # Never exceeds either bound.
        assert out.size[0] <= 100 and out.size[1] <= 100, "result overflowed box"
        assert src.size == (400, 200), "fit_within must not mutate the source"
        assert out is not src, "fit_within must return a new image"

    def test_fit_within_portrait_constrained_by_height(self):
        """200x400 into 100x100 box -> (50,100); height is the constraining side."""
        mod = _load_resizeops()
        src = Image.new("RGB", (200, 400), (50, 60, 70))
        out = mod.fit_within(src, 100, 100)
        assert out.size == (50, 100), f"expected (50,100) got {out.size}"
        assert out.size[1] == 100, "constraining side must equal its bound"
        assert out.size[0] <= 100 and out.size[1] <= 100, "result overflowed box"

    def test_fit_within_asymmetric_box_picks_most_constraining(self):
        """400x200 into a 300x300 box: width-ratio 0.75 < height-ratio 1.5 -> (300,150)."""
        mod = _load_resizeops()
        src = Image.new("RGB", (400, 200), (50, 60, 70))
        out = mod.fit_within(src, 300, 300)
        # min(300/400, 300/200) = min(0.75, 1.5) = 0.75 -> (300, 150).
        assert out.size == (300, 150), f"expected (300,150) got {out.size}"
        assert out.size[0] <= 300 and out.size[1] <= 300

    def test_fit_within_no_upscale_when_already_fits(self):
        """Image already inside the box -> returned unchanged in size (no upscale)."""
        mod = _load_resizeops()
        src = Image.new("RGB", (400, 200), (50, 60, 70))
        out = mod.fit_within(src, 1000, 1000)
        assert out.size == (400, 200), f"must not upscale; got {out.size}"

    def test_fit_within_never_exceeds_either_bound(self):
        """Across several box sizes the result fits inside and preserves ratio."""
        mod = _load_resizeops()
        src = Image.new("RGB", (640, 480), (10, 20, 30))
        for mw, mh in ((100, 100), (320, 200), (50, 400), (700, 100)):
            out = mod.fit_within(src, mw, mh)
            assert out.size[0] <= mw, f"width {out.size[0]} > {mw}"
            assert out.size[1] <= mh, f"height {out.size[1]} > {mh}"
            # Aspect ratio preserved within rounding tolerance (4:3 source).
            ratio = out.size[0] / out.size[1]
            assert abs(ratio - (640 / 480)) < 0.05, (
                f"aspect ratio not preserved: {out.size} ratio={ratio:.3f}"
            )

    # ------------------------------------------------------------------
    # L2: the Agent's own native test suite must pass.
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """`python -m pytest Tests/test_resizeops.py -q` exits cleanly."""
        tpath = os.path.join(self.REPO_DIR, "Tests", "test_resizeops.py")
        assert os.path.isfile(tpath), "Tests/test_resizeops.py was not created"
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "Tests/test_resizeops.py", "-q"],
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
