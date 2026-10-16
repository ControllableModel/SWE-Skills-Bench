"""
Test for 'pillow-image-processing' skill (variant ext6) — One-Step Web
Optimise Pipeline.

Verifies the Agent's new module ``src/PIL/OptimizeOps.py`` inside the Pillow
repo. The module caps an image's width and re-encodes it with a
compression-friendly format in a single pass, exposing:

  * ``optimize(image, path, *, max_width=1920, quality=85)``
        — resize (cap width, preserve ratio, no upscale, no mutation) and save
          to ``path`` with the format derived from the extension; returns the
          written path. JPEG flattens alpha onto opaque white; PNG is lossless
          and ignores ``quality``; unsupported extensions raise ``ValueError``;
          missing parent directories are created.
  * ``optimize_bytes(image, fmt, *, max_width=1920, quality=85)``
        — same resize+encode behaviour but returns encoded ``bytes``; ``fmt`` is
          one of ``webp``/``jpeg``/``png`` (case-insensitive); unknown -> ValueError.

The module under test is loaded DIRECTLY from REPO_DIR/src/PIL/OptimizeOps.py
(not from an installed PIL.OptimizeOps), so the Agent's actual file is what is
exercised. Fixture images and result re-opening use the installed ``PIL``.

The assertions independently re-derive the doc's Acceptance Criteria rather than
trusting the Agent's own tests; a stub that ignores ``max_width``, ignores
``quality``, hardcodes a format, skips alpha flatten, or mutates the source must
fail. The Agent's own native suite is also driven last:

Native command verified by Acceptance Criteria:
    python -m pytest Tests/test_optimizeops.py -q
"""

import importlib.util
import io
import os
import subprocess
import sys

import pytest

# The installed Pillow is used only to build/inspect fixture images.
from PIL import Image, features


REPO_DIR = "/workspace/Pillow"
MODULE_PATH = os.path.join(REPO_DIR, "src", "PIL", "OptimizeOps.py")


def _load_optimizeops():
    """Import the Agent's OptimizeOps.py straight from the repo source tree."""
    assert os.path.isfile(MODULE_PATH), f"OptimizeOps.py not found at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("_agent_optimizeops", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _gradient_rgb(w, h):
    """A horizontal gradient RGB image (deterministic, compresses non-trivially)."""
    g = Image.new("L", (w, h))
    px = g.load()
    for x in range(w):
        col = (x * 255) // max(w - 1, 1)
        for y in range(h):
            px[x, y] = col
    return g.convert("RGB")


def _noise_rgb(w, h, seed=20240611):
    """A deterministic pseudo-random RGB image (high entropy for size tests)."""
    import random

    r = random.Random(seed)
    im = Image.new("RGB", (w, h))
    px = im.load()
    for x in range(w):
        for y in range(h):
            px[x, y] = (r.randint(0, 255), r.randint(0, 255), r.randint(0, 255))
    return im


class TestPillowImageProcessing:
    """Verify the OptimizeOps one-step web-optimise pipeline."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/PIL/OptimizeOps.py must exist."""
        assert os.path.isfile(MODULE_PATH), "OptimizeOps.py was not created"

    def test_module_imports_and_exposes_api(self):
        """The module imports cleanly and exposes optimize + optimize_bytes."""
        mod = _load_optimizeops()
        for name in ("optimize", "optimize_bytes"):
            assert hasattr(mod, name), f"OptimizeOps.{name} is missing"
            assert callable(getattr(mod, name)), f"OptimizeOps.{name} is not callable"

    def test_native_test_file_exists(self):
        """Tests/test_optimizeops.py (the Agent's own test) must exist."""
        tpath = os.path.join(self.REPO_DIR, "Tests", "test_optimizeops.py")
        assert os.path.isfile(tpath), "Tests/test_optimizeops.py was not created"

    # ------------------------------------------------------------------
    # L2: resize stage of optimize()
    # ------------------------------------------------------------------

    def test_optimize_downscales_wide_image(self, tmp_path):
        """1600x900, max_width=800 -> reopens at exactly 800x450 (proportional)."""
        mod = _load_optimizeops()
        src = Image.new("RGB", (1600, 900), (30, 120, 200))
        out_path = os.path.join(str(tmp_path), "wide.webp")
        ret = mod.optimize(src, out_path, max_width=800)
        assert ret == out_path, f"optimize must return its path; got {ret!r}"
        with Image.open(out_path) as re:
            re.load()
            assert re.size == (800, 450), (
                f"expected downscale to (800,450) got {re.size}"
            )

    def test_optimize_no_upscale_when_within_cap(self, tmp_path):
        """1600x900, max_width=4000 -> left unchanged at original 1600x900."""
        mod = _load_optimizeops()
        src = Image.new("RGB", (1600, 900), (30, 120, 200))
        out_path = os.path.join(str(tmp_path), "keep.webp")
        mod.optimize(src, out_path, max_width=4000)
        with Image.open(out_path) as re:
            re.load()
            assert re.size == (1600, 900), (
                f"must not upscale; expected (1600,900) got {re.size}"
            )

    def test_optimize_proportional_rounding(self, tmp_path):
        """Derived height rounds to nearest integer (1000x333, w=100 -> h=33)."""
        mod = _load_optimizeops()
        # 100 * 333/1000 = 33.3 -> rounds to 33.
        src = Image.new("RGB", (1000, 333), (10, 10, 10))
        out_path = os.path.join(str(tmp_path), "round.png")
        mod.optimize(src, out_path, max_width=100)
        with Image.open(out_path) as re:
            re.load()
            assert re.size == (100, 33), f"expected (100,33) got {re.size}"

    def test_optimize_min_height_floor_one(self, tmp_path):
        """A target that would round the height to 0 is floored to 1."""
        mod = _load_optimizeops()
        # 4000 wide, 1 tall. max_width=2 -> height 2*1/4000 -> floor to 1.
        src = Image.new("RGB", (4000, 1), (10, 10, 10))
        out_path = os.path.join(str(tmp_path), "thin.png")
        mod.optimize(src, out_path, max_width=2)
        with Image.open(out_path) as re:
            re.load()
            assert re.size[0] == 2, f"width should be capped at 2 got {re.size}"
            assert re.size[1] == 1, f"height floor-1 violated got {re.size}"

    def test_optimize_does_not_mutate_source(self, tmp_path):
        """The original image object must not be resized/mutated."""
        mod = _load_optimizeops()
        src = Image.new("RGB", (1600, 900), (5, 6, 7))
        out_path = os.path.join(str(tmp_path), "src_intact.jpg")
        mod.optimize(src, out_path, max_width=400)
        assert src.size == (1600, 900), "optimize must not mutate the source image"

    def test_optimize_uses_high_quality_resampling(self, tmp_path):
        """Downscaling a gradient is smoother than NEAREST (HQ filter used)."""
        mod = _load_optimizeops()
        grad = _gradient_rgb(512, 16)
        out_path = os.path.join(str(tmp_path), "grad.png")  # PNG => lossless, exact
        mod.optimize(grad, out_path, max_width=64)
        with Image.open(out_path) as re:
            re.load()
            assert re.size[0] == 64, f"expected width 64 got {re.size}"
            got = re.convert("L")
            nearest = grad.resize(re.size, Image.Resampling.NEAREST).convert("L")

        def adj_diff(im):
            w, h = im.size
            px = im.load()
            tot = cnt = 0
            for y in range(h):
                for x in range(1, w):
                    tot += abs(px[x, y] - px[x - 1, y])
                    cnt += 1
            return tot / cnt if cnt else 0.0

        smooth = adj_diff(got)
        coarse = adj_diff(nearest)
        assert smooth < coarse, (
            f"downscale not smoother than NEAREST: helper={smooth:.4f} "
            f"nearest={coarse:.4f}"
        )

    # ------------------------------------------------------------------
    # L2: save stage / format derivation
    # ------------------------------------------------------------------

    def test_optimize_format_from_extension(self, tmp_path):
        """Format is derived from extension: .png->PNG, .jpg->JPEG."""
        mod = _load_optimizeops()
        src = Image.new("RGB", (40, 30), (90, 90, 90))
        png_path = os.path.join(str(tmp_path), "a.png")
        jpg_path = os.path.join(str(tmp_path), "b.jpg")
        mod.optimize(src, png_path)
        mod.optimize(src, jpg_path)
        with Image.open(png_path) as p:
            p.load()
            assert p.format == "PNG", f"expected PNG got {p.format}"
        with Image.open(jpg_path) as j:
            j.load()
            assert j.format == "JPEG", f"expected JPEG got {j.format}"

    def test_optimize_extension_case_insensitive(self, tmp_path):
        """Extension matching is case-insensitive (.JPEG behaves like .jpeg)."""
        mod = _load_optimizeops()
        src = Image.new("RGB", (12, 12), (40, 80, 120))
        out_path = os.path.join(str(tmp_path), "UPPER.JPEG")
        mod.optimize(src, out_path)
        assert os.path.isfile(out_path)
        with Image.open(out_path) as re:
            re.load()
            assert re.format == "JPEG", f"expected JPEG for .JPEG got {re.format}"

    def test_optimize_jpeg_flattens_alpha_to_white(self, tmp_path):
        """A fully transparent RGBA region reopens as white (255,255,255) in JPEG."""
        mod = _load_optimizeops()
        # Opaque red base with a large fully-transparent dark block in a corner.
        # A large block avoids JPEG chroma-subsampling bleed from neighbours.
        src = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
        for x in range(32):
            for y in range(32):
                src.putpixel((x, y), (10, 20, 30, 0))  # transparent, dark RGB
        out_path = os.path.join(str(tmp_path), "flat.jpg")
        mod.optimize(src, out_path, max_width=4000)  # no resize
        with Image.open(out_path) as re:
            re.load()
            assert re.format == "JPEG"
            px = re.convert("RGB").getpixel((6, 6))  # well inside transparent region
            assert all(c >= 248 for c in px), (
                f"transparent pixel should flatten to white; got {px}"
            )

    def test_optimize_quality_affects_lossy_size(self, tmp_path):
        """Lower quality yields a strictly smaller lossy file than higher quality."""
        mod = _load_optimizeops()
        noisy = _noise_rgb(128, 128)
        low_path = os.path.join(str(tmp_path), "low.jpg")
        high_path = os.path.join(str(tmp_path), "high.jpg")
        mod.optimize(noisy, low_path, max_width=4000, quality=10)
        mod.optimize(noisy, high_path, max_width=4000, quality=95)
        low = os.path.getsize(low_path)
        high = os.path.getsize(high_path)
        assert low < high, (
            f"lower quality must yield a strictly smaller file: q10={low} q95={high}"
        )

    def test_optimize_png_lossless_and_ignores_quality(self, tmp_path):
        """PNG is lossless (exact pixels) and accepts quality without raising."""
        mod = _load_optimizeops()
        src = Image.new("RGB", (20, 16), (200, 50, 25))
        src.putpixel((3, 4), (3, 7, 11))
        out_path = os.path.join(str(tmp_path), "loss.png")
        # quality should be ignored for PNG, not raise.
        mod.optimize(src, out_path, max_width=4000, quality=10)
        with Image.open(out_path) as re:
            re.load()
            assert re.format == "PNG"
            assert re.size == (20, 16)
            assert re.convert("RGB").getpixel((3, 4)) == (3, 7, 11), (
                "PNG must be lossless (exact pixel preserved)"
            )
            assert re.convert("RGB").getpixel((0, 0)) == (200, 50, 25)

    def test_optimize_creates_missing_parent_dirs(self, tmp_path):
        """Missing parent directories of the destination path are created."""
        mod = _load_optimizeops()
        src = Image.new("RGB", (8, 8), (1, 2, 3))
        out_path = os.path.join(str(tmp_path), "nested", "deep", "asset.png")
        ret = mod.optimize(src, out_path)
        assert os.path.isfile(out_path), "nested output file was not written"
        assert ret == out_path

    def test_optimize_unsupported_extension_raises(self, tmp_path):
        """An unsupported extension -> ValueError."""
        mod = _load_optimizeops()
        src = Image.new("RGB", (8, 8), (1, 2, 3))
        with pytest.raises(ValueError):
            mod.optimize(src, os.path.join(str(tmp_path), "asset.gifx"))

    # ------------------------------------------------------------------
    # L2: optimize_bytes behaviour
    # ------------------------------------------------------------------

    def test_optimize_bytes_returns_reopenable_jpeg(self):
        """optimize_bytes(img, 'jpeg') -> non-empty bytes reopening as JPEG."""
        mod = _load_optimizeops()
        src = Image.new("RGB", (100, 60), (120, 30, 200))
        data = mod.optimize_bytes(src, "jpeg")
        assert isinstance(data, (bytes, bytearray)), f"expected bytes got {type(data)}"
        assert len(data) > 0, "encoded bytes are empty"
        with Image.open(io.BytesIO(bytes(data))) as re:
            re.load()
            assert re.format == "JPEG", f"expected JPEG got {re.format}"
            assert re.size == (100, 60)

    def test_optimize_bytes_resizes_and_is_case_insensitive(self):
        """optimize_bytes honours max_width and a case-insensitive fmt ('PNG')."""
        mod = _load_optimizeops()
        src = Image.new("RGB", (1600, 800), (10, 200, 30))
        data = mod.optimize_bytes(src, "PNG", max_width=400)
        with Image.open(io.BytesIO(bytes(data))) as re:
            re.load()
            assert re.format == "PNG", f"expected PNG got {re.format}"
            assert re.size == (400, 200), f"expected (400,200) got {re.size}"

    def test_optimize_bytes_quality_affects_size(self):
        """Lower quality yields strictly smaller bytes than higher quality."""
        mod = _load_optimizeops()
        noisy = _noise_rgb(128, 128, seed=777)
        low = mod.optimize_bytes(noisy, "jpeg", max_width=4000, quality=10)
        high = mod.optimize_bytes(noisy, "jpeg", max_width=4000, quality=95)
        assert len(low) < len(high), (
            f"lower quality must yield strictly smaller bytes: q10={len(low)} "
            f"q95={len(high)}"
        )

    def test_optimize_bytes_unknown_format_raises(self):
        """An unknown fmt value -> ValueError."""
        mod = _load_optimizeops()
        src = Image.new("RGB", (8, 8), (1, 2, 3))
        with pytest.raises(ValueError):
            mod.optimize_bytes(src, "tiff")

    @pytest.mark.skipif(
        not features.check("webp"), reason="WebP support not built into Pillow"
    )
    def test_optimize_webp_roundtrip(self, tmp_path):
        """WebP save (file) writes a readable WebP at the capped size."""
        mod = _load_optimizeops()
        src = Image.new("RGB", (1600, 900), (90, 160, 30))
        out_path = os.path.join(str(tmp_path), "asset.webp")
        mod.optimize(src, out_path, max_width=800, quality=80)
        with Image.open(out_path) as re:
            re.load()
            assert re.format == "WEBP", f"expected WEBP got {re.format}"
            assert re.size == (800, 450)

    # ------------------------------------------------------------------
    # L2: the Agent's own native test suite must pass.
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """`python -m pytest Tests/test_optimizeops.py -q` exits cleanly."""
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "Tests/test_optimizeops.py", "-q"],
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
