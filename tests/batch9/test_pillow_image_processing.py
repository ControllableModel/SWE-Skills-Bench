"""
Test for 'pillow-image-processing' skill (variant ext9) — Favicon / Icon Set
Generator module.

Verifies the Agent's new module ``src/PIL/IconSet.py`` inside the Pillow repo,
which derives a set of square icon assets from a single source image:

  * ``square_canvas(image)``
        Return a NEW RGBA square whose side equals the longer input side, with
        the original content centred and the surrounding area fully transparent.
        The input must not be mutated.

  * ``generate(image, dst_dir, sizes, *, trim=True, name="icon")``
        Produce one square PNG per requested size and return a dict mapping each
        size -> written path. When ``trim`` is true, uniform/transparent border
        pixels are removed before squaring; content is centred on a square
        canvas, then scaled to ``size``x``size`` with a high-quality filter and
        saved as ``{name}-{size}.png`` in ``dst_dir`` (created if missing).
        Empty ``sizes`` or any non-positive size raises ``ValueError``. Outputs
        are saved in an alpha-capable mode preserving margin transparency.

The module under test is loaded DIRECTLY from REPO_DIR/src/PIL/IconSet.py (not
from any installed PIL.IconSet), so the Agent's actual file is what is exercised.
Fixture images and result re-opening use the installed ``PIL``.

Discriminative intent: a naive stub (returns a fixed-size image, ignores the
source aspect ratio, hardcodes one output, drops the alpha channel, skips
trimming, or never writes files) MUST fail.

Native command verified by Acceptance Criteria:
    python -m pytest Tests/test_iconset.py -q
"""

import importlib.util
import os
import subprocess
import sys

import pytest

# The installed Pillow is used only to build / inspect fixture images.
from PIL import Image


REPO_DIR = "/workspace/Pillow"
MODULE_PATH = os.path.join(REPO_DIR, "src", "PIL", "IconSet.py")


def _load_iconset():
    """Import the Agent's IconSet.py straight from the repo source tree."""
    assert os.path.isfile(MODULE_PATH), f"IconSet.py not found at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("_agent_iconset", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _padded_logo(content=(10, 220, 30, 255), border=20, size=24):
    """An RGBA logo: an opaque content block surrounded by a transparent border."""
    total = size + 2 * border
    im = Image.new("RGBA", (total, total), (0, 0, 0, 0))
    im.paste(Image.new("RGBA", (size, size), content), (border, border))
    return im


class TestPillowImageProcessing:
    """Verify the IconSet favicon / icon-set generator helpers."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/PIL/IconSet.py must exist."""
        assert os.path.isfile(MODULE_PATH), "IconSet.py was not created"

    def test_module_imports_and_exposes_api(self):
        """The module imports cleanly and exposes square_canvas + generate."""
        mod = _load_iconset()
        for name in ("square_canvas", "generate"):
            assert hasattr(mod, name), f"IconSet.{name} is missing"
            assert callable(getattr(mod, name)), f"IconSet.{name} is not callable"

    def test_native_test_file_exists(self):
        """Tests/test_iconset.py (the Agent's own test) must exist."""
        tpath = os.path.join(self.REPO_DIR, "Tests", "test_iconset.py")
        assert os.path.isfile(tpath), "Tests/test_iconset.py was not created"

    # ------------------------------------------------------------------
    # L2: square_canvas behaviour
    # ------------------------------------------------------------------

    def test_square_canvas_landscape_centres_content(self):
        """40x20 -> 40x40 RGBA, content vertically centred with transparent margins."""
        mod = _load_iconset()
        src = Image.new("RGBA", (40, 20), (200, 30, 30, 255))
        out = mod.square_canvas(src)
        assert out.size == (40, 40), f"expected (40,40) got {out.size}"
        assert out.mode == "RGBA", f"expected RGBA got {out.mode}"
        a = out.getchannel("A")
        # 10px transparent margin top and bottom.
        assert a.getpixel((20, 0)) == 0, "top margin must be transparent"
        assert a.getpixel((20, 39)) == 0, "bottom margin must be transparent"
        # Content band (rows 10..29) is opaque.
        assert a.getpixel((20, 10)) == 255, "content top edge must be opaque"
        assert a.getpixel((20, 29)) == 255, "content bottom edge must be opaque"
        assert a.getpixel((20, 20)) == 255, "content centre must be opaque"

    def test_square_canvas_does_not_mutate_input(self):
        """The input image must not be modified by square_canvas."""
        mod = _load_iconset()
        src = Image.new("RGBA", (40, 20), (200, 30, 30, 255))
        before = src.tobytes()
        _ = mod.square_canvas(src)
        assert src.size == (40, 20), "input size was mutated"
        assert src.tobytes() == before, "input pixels were mutated"

    def test_square_canvas_portrait_centres_horizontally(self):
        """60x30 portrait-by-width -> side 60; here 30x60 -> 60x60 with side margins."""
        mod = _load_iconset()
        # 30 wide x 60 tall: longer side = 60, content centred horizontally.
        src = Image.new("RGBA", (30, 60), (20, 40, 200, 255))
        out = mod.square_canvas(src)
        assert out.size == (60, 60), f"expected (60,60) got {out.size}"
        a = out.getchannel("A")
        # 15px transparent margin on left and right.
        assert a.getpixel((0, 30)) == 0, "left margin must be transparent"
        assert a.getpixel((59, 30)) == 0, "right margin must be transparent"
        assert a.getpixel((15, 30)) == 255, "content left edge must be opaque"
        assert a.getpixel((44, 30)) == 255, "content right edge must be opaque"

    def test_square_canvas_already_square_same_size(self):
        """An already-square input yields a same-size square copy (no growth)."""
        mod = _load_iconset()
        src = Image.new("RGBA", (50, 50), (90, 160, 30, 255))
        out = mod.square_canvas(src)
        assert out.size == (50, 50), f"expected (50,50) got {out.size}"
        # Distinct object: mutating output must not touch the source.
        assert out is not src, "square_canvas must return a new image"

    # ------------------------------------------------------------------
    # L2: generate — sizing, filenames, return value
    # ------------------------------------------------------------------

    def test_generate_writes_one_png_per_size(self, tmp_path):
        """generate(logo, dst, [16,32,512]) -> three square PNGs of those sizes."""
        mod = _load_iconset()
        logo = _padded_logo()
        dst = os.path.join(str(tmp_path), "icons")
        result = mod.generate(logo, dst, [16, 32, 512])
        assert isinstance(result, dict), f"generate must return a dict, got {type(result)}"
        assert set(result.keys()) == {16, 32, 512}, f"unexpected keys: {result.keys()}"
        for size in (16, 32, 512):
            path = result[size]
            assert os.path.isfile(path), f"missing output for size {size}: {path}"
            with Image.open(path) as re:
                re.load()
                assert re.format == "PNG", f"size {size}: expected PNG got {re.format}"
                assert re.size == (size, size), (
                    f"size {size}: expected ({size},{size}) got {re.size}"
                )

    def test_generate_default_filenames_and_name_override(self, tmp_path):
        """Filenames are {name}-{size}.png; default name is 'icon'."""
        mod = _load_iconset()
        logo = _padded_logo()
        # Default name.
        dst1 = os.path.join(str(tmp_path), "default")
        res1 = mod.generate(logo, dst1, [16, 32])
        assert os.path.basename(res1[16]) == "icon-16.png", res1[16]
        assert os.path.basename(res1[32]) == "icon-32.png", res1[32]
        # Custom name.
        dst2 = os.path.join(str(tmp_path), "named")
        res2 = mod.generate(logo, dst2, [48], name="favicon")
        assert os.path.basename(res2[48]) == "favicon-48.png", res2[48]

    def test_generate_creates_missing_dst_dir(self, tmp_path):
        """dst_dir is created when missing (nested path)."""
        mod = _load_iconset()
        logo = _padded_logo()
        dst = os.path.join(str(tmp_path), "a", "b", "c")
        assert not os.path.isdir(dst)
        res = mod.generate(logo, dst, [16])
        assert os.path.isdir(dst), "dst_dir was not created"
        assert os.path.isfile(res[16])

    def test_generate_output_preserves_margin_transparency(self, tmp_path):
        """Each output is alpha-capable; margin around centred content is transparent."""
        mod = _load_iconset()
        # Landscape so squaring introduces transparent top/bottom margins.
        logo = Image.new("RGBA", (40, 10), (200, 30, 30, 255))
        dst = os.path.join(str(tmp_path), "icons")
        res = mod.generate(logo, dst, [40], trim=False)
        with Image.open(res[40]) as re:
            re.load()
            assert "A" in re.getbands(), "output must carry an alpha channel"
            a = re.convert("RGBA").getchannel("A")
            # With trim=False, 40x10 squares to 40x40: 15px margin top/bottom.
            assert a.getpixel((20, 0)) == 0, "top margin pixel must be transparent"
            assert a.getpixel((20, 39)) == 0, "bottom margin pixel must be transparent"
            assert a.getpixel((20, 20)) == 255, "content centre must be opaque"

    # ------------------------------------------------------------------
    # L2: trim behaviour (the discriminative core)
    # ------------------------------------------------------------------

    def test_generate_trim_removes_transparent_border(self, tmp_path):
        """trim=True: opaque content reaches the icon edges (border removed)."""
        mod = _load_iconset()
        # 24x24 opaque content centred in a 64x64 fully transparent frame.
        logo = _padded_logo(border=20, size=24)  # 64x64 total
        dst = os.path.join(str(tmp_path), "trimmed")
        res = mod.generate(logo, dst, [24], trim=True)
        with Image.open(res[24]) as re:
            re.load()
            a = re.convert("RGBA").getchannel("A")
            # After trimming the transparent border, the 24x24 content fills the
            # 24x24 square -> every edge pixel must be opaque.
            for x in range(24):
                assert a.getpixel((x, 0)) == 255, f"top edge x={x} not opaque after trim"
                assert a.getpixel((x, 23)) == 255, f"bottom edge x={x} not opaque after trim"
            for y in range(24):
                assert a.getpixel((0, y)) == 255, f"left edge y={y} not opaque after trim"
                assert a.getpixel((23, y)) == 255, f"right edge y={y} not opaque after trim"

    def test_generate_no_trim_retains_border(self, tmp_path):
        """trim=False: the transparent border survives, so edges stay transparent."""
        mod = _load_iconset()
        logo = _padded_logo(border=20, size=24)  # 64x64, transparent border
        dst = os.path.join(str(tmp_path), "untrimmed")
        # Output at the source square size so we can read the margin directly.
        res = mod.generate(logo, dst, [64], trim=False)
        with Image.open(res[64]) as re:
            re.load()
            a = re.convert("RGBA").getchannel("A")
            # The 20px transparent border must remain -> corners transparent.
            assert a.getpixel((0, 0)) == 0, "corner must remain transparent without trim"
            assert a.getpixel((63, 63)) == 0, "corner must remain transparent without trim"
            # Centre is still the opaque content.
            assert a.getpixel((32, 32)) == 255, "content centre must be opaque"

    def test_generate_high_quality_downscale(self, tmp_path):
        """Downscaling uses a high-quality filter, not NEAREST (gradient stays smooth)."""
        mod = _load_iconset()
        # 128-wide horizontal gradient, opaque, already square (128x128).
        grad = Image.new("RGBA", (128, 128))
        gpx = grad.load()
        for x in range(128):
            for y in range(128):
                gpx[x, y] = (x * 2, x * 2, x * 2, 255)
        dst = os.path.join(str(tmp_path), "grad")
        res = mod.generate(grad, dst, [32], trim=False)
        with Image.open(res[32]) as re:
            re.load()
            g = re.convert("L")
            # NEAREST reference from the same source.
            nearest = grad.convert("L").resize((32, 32), Image.Resampling.NEAREST)

            def mean_adj_diff(im):
                px = im.load()
                w, h = im.size
                tot = cnt = 0
                for yy in range(h):
                    for xx in range(1, w):
                        tot += abs(px[xx, yy] - px[xx - 1, yy])
                        cnt += 1
                return tot / cnt if cnt else 0.0

            smooth = mean_adj_diff(g)
            near = mean_adj_diff(nearest)
            assert smooth < near, (
                f"downscale not smoother than NEAREST: helper={smooth:.4f} nearest={near:.4f}"
            )

    # ------------------------------------------------------------------
    # L2: validation / error handling
    # ------------------------------------------------------------------

    def test_generate_empty_sizes_raises(self, tmp_path):
        """Empty sizes -> ValueError."""
        mod = _load_iconset()
        logo = _padded_logo()
        with pytest.raises(ValueError):
            mod.generate(logo, os.path.join(str(tmp_path), "x"), [])

    def test_generate_non_positive_size_raises(self, tmp_path):
        """Any non-positive size -> ValueError."""
        mod = _load_iconset()
        logo = _padded_logo()
        with pytest.raises(ValueError):
            mod.generate(logo, os.path.join(str(tmp_path), "y"), [16, 0, 32])
        with pytest.raises(ValueError):
            mod.generate(logo, os.path.join(str(tmp_path), "z"), [16, -8])

    # ------------------------------------------------------------------
    # L2: the Agent's own native test suite must pass.
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """`python -m pytest Tests/test_iconset.py -q` exits cleanly."""
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "Tests/test_iconset.py", "-q"],
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
