"""
Test for 'pillow-image-processing' skill — Web Asset Preparation Helper Module.

Verifies the Agent's new module ``src/PIL/WebImageOps.py`` inside the Pillow
repo, providing task-oriented web-asset helpers built on top of ``PIL.Image``:

  * ``scale_to``       — aspect-preserving / explicit resize, high-quality filter
  * ``trim``           — alpha-aware auto-crop with optional transparent padding
  * ``fit_thumbnail``  — fit-inside-square without upscaling
  * ``save_web``       — extension-driven save (PNG/JPEG/WebP), alpha flatten

The module under test is loaded DIRECTLY from REPO_DIR/src/PIL/WebImageOps.py
(not from any installed PIL.WebImageOps), so the Agent's actual file is what is
exercised. Fixture images and result re-opening use the installed ``PIL``.

Native command verified by Acceptance Criteria:
    python -m pytest Tests/test_webimageops.py -q
"""

import importlib.util
import os
import subprocess
import sys

import pytest

# The installed Pillow is used only to build/inspect fixture images.
from PIL import Image, features


REPO_DIR = "/workspace/Pillow"
MODULE_PATH = os.path.join(REPO_DIR, "src", "PIL", "WebImageOps.py")


def _load_webimageops():
    """Import the Agent's WebImageOps.py straight from the repo source tree."""
    assert os.path.isfile(MODULE_PATH), f"WebImageOps.py not found at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("_agent_webimageops", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    # Make the module's own `from PIL import Image` resolve to installed Pillow.
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


class TestPillowImageProcessing:
    """Verify the WebImageOps web-asset preparation helpers."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/PIL/WebImageOps.py must exist."""
        assert os.path.isfile(MODULE_PATH), "WebImageOps.py was not created"

    def test_module_imports_and_exposes_api(self):
        """The module imports cleanly and exposes the four public callables."""
        mod = _load_webimageops()
        for name in ("scale_to", "trim", "fit_thumbnail", "save_web"):
            assert hasattr(mod, name), f"WebImageOps.{name} is missing"
            assert callable(getattr(mod, name)), f"WebImageOps.{name} is not callable"

    def test_native_test_file_exists(self):
        """Tests/test_webimageops.py (the Agent's own test) must exist."""
        tpath = os.path.join(self.REPO_DIR, "Tests", "test_webimageops.py")
        assert os.path.isfile(tpath), "Tests/test_webimageops.py was not created"

    # ------------------------------------------------------------------
    # L2: scale_to behaviour
    # ------------------------------------------------------------------

    def test_scale_to_both_dimensions_exact(self):
        """Both width and height given -> exactly those dimensions; source intact."""
        mod = _load_webimageops()
        src = Image.new("RGB", (400, 200), (120, 30, 200))
        out = mod.scale_to(src, width=64, height=128)
        assert out.size == (64, 128), f"expected (64,128) got {out.size}"
        assert src.size == (400, 200), "scale_to must not mutate the source image"

    def test_scale_to_width_only_preserves_ratio(self):
        """Width only -> height derived from aspect ratio (400x200, w=100 -> 50)."""
        mod = _load_webimageops()
        src = Image.new("RGB", (400, 200), (10, 10, 10))
        out = mod.scale_to(src, width=100)
        assert out.size == (100, 50), f"expected (100,50) got {out.size}"

    def test_scale_to_height_only_preserves_ratio(self):
        """Height only -> width derived from aspect ratio (400x200, h=50 -> 100)."""
        mod = _load_webimageops()
        src = Image.new("RGB", (400, 200), (10, 10, 10))
        out = mod.scale_to(src, height=50)
        assert out.size == (100, 50), f"expected (100,50) got {out.size}"

    def test_scale_to_rounding_and_min_one(self):
        """Derived dim rounds to nearest int with floor 1 (400x200 w=3 -> (3,2))."""
        mod = _load_webimageops()
        src = Image.new("RGB", (400, 200), (10, 10, 10))
        # 3 * 200/400 = 1.5 -> rounds to 2
        out = mod.scale_to(src, width=3)
        assert out.size == (3, 2), f"expected (3,2) got {out.size}"
        # A target that would round to 0 must become 1.
        # 1000 wide, 1 tall -> width=2 gives height 2*1/1000=0.002 -> floor 1.
        tall = Image.new("RGB", (1000, 1), (10, 10, 10))
        out2 = mod.scale_to(tall, width=2)
        assert out2.size[1] == 1, f"min-1 floor violated: {out2.size}"

    def test_scale_to_requires_a_dimension(self):
        """Neither width nor height -> ValueError."""
        mod = _load_webimageops()
        src = Image.new("RGB", (40, 20), (10, 10, 10))
        with pytest.raises(ValueError):
            mod.scale_to(src)

    def test_scale_to_high_quality_downscale(self):
        """Downscaling a gradient is smoother than NEAREST (high-quality filter)."""
        mod = _load_webimageops()
        # 256-wide horizontal gradient.
        grad = Image.new("L", (256, 16))
        px = grad.load()
        for x in range(256):
            for y in range(16):
                px[x, y] = x
        grad = grad.convert("RGB")

        out = mod.scale_to(grad, width=64)
        assert out.size[0] == 64, f"expected width 64 got {out.size}"

        nearest = grad.resize((64, out.size[1]), Image.Resampling.NEAREST)
        smooth_diff = _mean_abs_adjacent_diff(out)
        nearest_diff = _mean_abs_adjacent_diff(nearest)
        assert smooth_diff < nearest_diff, (
            "downscale not smoother than NEAREST: "
            f"helper={smooth_diff:.4f} nearest={nearest_diff:.4f}"
        )

    # ------------------------------------------------------------------
    # L2: trim behaviour
    # ------------------------------------------------------------------

    def test_trim_uniform_opaque_border(self):
        """Trim a white border around a 20x20 red square -> 20x20 result."""
        mod = _load_webimageops()
        src = Image.new("RGB", (100, 100), (255, 255, 255))
        square = Image.new("RGB", (20, 20), (255, 0, 0))
        src.paste(square, (40, 40))
        out = mod.trim(src)
        assert out.size == (20, 20), f"expected (20,20) got {out.size}"

    def test_trim_with_transparent_padding(self):
        """padding=5 re-adds a 5px transparent margin on each side -> 30x30."""
        mod = _load_webimageops()
        src = Image.new("RGB", (100, 100), (255, 255, 255))
        src.paste(Image.new("RGB", (20, 20), (255, 0, 0)), (40, 40))
        out = mod.trim(src, padding=5)
        assert out.size == (30, 30), f"expected (30,30) got {out.size}"
        assert "A" in out.getbands(), "padded result must carry an alpha channel"
        a = out.getchannel("A")
        # corner is padding -> transparent; center is content -> opaque.
        assert a.getpixel((0, 0)) == 0, "padding pixel must be transparent (alpha 0)"
        assert a.getpixel((15, 15)) == 255, "content pixel must be opaque"

    def test_trim_alpha_aware_transparent_border(self):
        """A fully transparent border is trimmed even with non-uniform RGB."""
        mod = _load_webimageops()
        src = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
        # Scribble random opaque-but-transparent RGB into the border region.
        bpx = src.load()
        for x in range(60):
            bpx[x, 0] = (123, 45, 67, 0)
            bpx[x, 59] = (9, 200, 14, 0)
        # Opaque content block in the middle: 24x24 at (18,18)..(41,41).
        content = Image.new("RGBA", (24, 24), (10, 220, 30, 255))
        src.paste(content, (18, 18))
        out = mod.trim(src)
        assert out.size == (24, 24), (
            f"alpha-aware trim should yield (24,24) got {out.size}"
        )

    def test_trim_no_border_same_size(self):
        """Content fills the frame and padding=0 -> dimensions unchanged."""
        mod = _load_webimageops()
        # Distinct corners so there is genuinely no uniform border to remove.
        src = Image.new("RGB", (30, 30), (10, 10, 10))
        src.putpixel((0, 0), (255, 0, 0))
        src.putpixel((29, 29), (0, 0, 255))
        out = mod.trim(src)
        assert out.size == (30, 30), f"expected unchanged (30,30) got {out.size}"

    def test_trim_empty_image_returns_copy(self):
        """A fully transparent image (no content) is returned unchanged in size."""
        mod = _load_webimageops()
        src = Image.new("RGBA", (40, 25), (0, 0, 0, 0))
        out = mod.trim(src)
        assert out.size == (40, 25), f"empty image should be unchanged got {out.size}"

    def test_trim_negative_padding_raises(self):
        """Negative padding -> ValueError."""
        mod = _load_webimageops()
        src = Image.new("RGB", (20, 20), (255, 255, 255))
        src.paste(Image.new("RGB", (4, 4), (1, 2, 3)), (8, 8))
        with pytest.raises(ValueError):
            mod.trim(src, padding=-1)

    # ------------------------------------------------------------------
    # L2: fit_thumbnail behaviour
    # ------------------------------------------------------------------

    def test_fit_thumbnail_longer_side_equals_size(self):
        """400x200 fit into size=100 -> (100,50); longer side == size."""
        mod = _load_webimageops()
        src = Image.new("RGB", (400, 200), (50, 60, 70))
        out = mod.fit_thumbnail(src, 100)
        assert out.size == (100, 50), f"expected (100,50) got {out.size}"
        assert max(out.size) == 100, "longer side must equal size"
        assert src.size == (400, 200), "fit_thumbnail must not mutate the source"

    def test_fit_thumbnail_portrait_orientation(self):
        """200x400 fit into size=100 -> (50,100); shorter side scaled, no overflow."""
        mod = _load_webimageops()
        src = Image.new("RGB", (200, 400), (50, 60, 70))
        out = mod.fit_thumbnail(src, 100)
        assert out.size == (50, 100), f"expected (50,100) got {out.size}"
        assert max(out.size) == 100 and min(out.size) <= 100

    def test_fit_thumbnail_no_upscale(self):
        """Image already smaller than size in both dims -> size unchanged."""
        mod = _load_webimageops()
        src = Image.new("RGB", (40, 25), (50, 60, 70))
        out = mod.fit_thumbnail(src, 100)
        assert out.size == (40, 25), f"must not upscale; got {out.size}"

    # ------------------------------------------------------------------
    # L2: save_web behaviour
    # ------------------------------------------------------------------

    def test_save_web_png_lossless_and_returns_path(self, tmp_path):
        """PNG save is lossless, creates missing dirs, and returns the path."""
        mod = _load_webimageops()
        src = Image.new("RGBA", (16, 12), (200, 50, 25, 255))
        src.putpixel((1, 1), (3, 7, 11, 128))
        out_path = os.path.join(str(tmp_path), "nested", "deep", "asset.png")
        ret = mod.save_web(src, out_path)
        assert os.path.isfile(out_path), "PNG file was not written"
        assert ret == out_path, f"save_web must return its path; got {ret!r}"
        with Image.open(out_path) as re:
            re.load()
            assert re.format == "PNG", f"expected PNG format got {re.format}"
            assert re.size == (16, 12)
            # Lossless: exact pixel preserved.
            assert re.convert("RGBA").getpixel((0, 0)) == (200, 50, 25, 255)

    def test_save_web_jpeg_flattens_alpha_to_white(self, tmp_path):
        """A fully transparent RGBA pixel reopens as white (255,255,255) in JPEG."""
        mod = _load_webimageops()
        # Opaque red image with a large fully-transparent block in the corner.
        # A large block avoids JPEG chroma-subsampling bleed from neighbours so
        # the flatten-to-white behaviour is what is actually measured.
        src = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        for x in range(16):
            for y in range(16):
                src.putpixel((x, y), (10, 20, 30, 0))  # transparent, dark RGB
        out_path = os.path.join(str(tmp_path), "out.jpg")
        ret = mod.save_web(src, out_path)
        assert ret == out_path
        with Image.open(out_path) as re:
            re.load()
            assert re.format == "JPEG", f"expected JPEG format got {re.format}"
            # Sample well inside the transparent region (away from the edge).
            px = re.convert("RGB").getpixel((4, 4))
            # JPEG is lossy; allow a tiny tolerance but it must be (near) white.
            assert all(c >= 248 for c in px), (
                f"transparent pixel should flatten to white; got {px}"
            )

    def test_save_web_quality_default_and_override(self, tmp_path):
        """Default quality applies; explicit quality overrides (smaller != bigger)."""
        mod = _load_webimageops()
        # Noisy image so JPEG quality meaningfully changes file size.
        import random

        random.seed(1234)
        noisy = Image.new("RGB", (96, 96))
        npx = noisy.load()
        for x in range(96):
            for y in range(96):
                npx[x, y] = (
                    random.randint(0, 255),
                    random.randint(0, 255),
                    random.randint(0, 255),
                )
        low_path = os.path.join(str(tmp_path), "low.jpg")
        high_path = os.path.join(str(tmp_path), "high.jpg")
        default_path = os.path.join(str(tmp_path), "default.jpg")
        mod.save_web(noisy, low_path, quality=10)
        mod.save_web(noisy, high_path, quality=95)
        mod.save_web(noisy, default_path)
        low = os.path.getsize(low_path)
        high = os.path.getsize(high_path)
        default = os.path.getsize(default_path)
        assert low < high, (
            f"explicit quality must change output: q10={low} q95={high}"
        )
        # The default produces a valid, non-trivial file (default quality applied).
        assert default > 0
        assert low <= default, (
            "default quality should not be lower than q=10 "
            f"(default={default}, q10={low})"
        )

    def test_save_web_unknown_extension_raises(self, tmp_path):
        """An unsupported extension -> ValueError."""
        mod = _load_webimageops()
        src = Image.new("RGB", (8, 8), (1, 2, 3))
        with pytest.raises(ValueError):
            mod.save_web(src, os.path.join(str(tmp_path), "asset.tiffx"))

    def test_save_web_extension_case_insensitive(self, tmp_path):
        """Extension matching is case-insensitive (.JPG behaves like .jpg)."""
        mod = _load_webimageops()
        src = Image.new("RGB", (10, 10), (40, 80, 120))
        out_path = os.path.join(str(tmp_path), "UPPER.JPG")
        mod.save_web(src, out_path)
        assert os.path.isfile(out_path)
        with Image.open(out_path) as re:
            re.load()
            assert re.format == "JPEG", f"expected JPEG for .JPG got {re.format}"

    @pytest.mark.skipif(
        not features.check("webp"), reason="WebP support not built into Pillow"
    )
    def test_save_web_webp(self, tmp_path):
        """WebP save writes a readable WebP honouring quality."""
        mod = _load_webimageops()
        src = Image.new("RGB", (24, 24), (90, 160, 30))
        out_path = os.path.join(str(tmp_path), "asset.webp")
        ret = mod.save_web(src, out_path, quality=80)
        assert ret == out_path
        with Image.open(out_path) as re:
            re.load()
            assert re.format == "WEBP", f"expected WEBP got {re.format}"
            assert re.size == (24, 24)

    # ------------------------------------------------------------------
    # L2: the Agent's own native test suite must pass.
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """`python -m pytest Tests/test_webimageops.py -q` exits cleanly."""
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "Tests/test_webimageops.py", "-q"],
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
