"""
Test for 'pillow-image-processing' skill (variant ext2) — Format-Aware Web Save Helper.

Verifies the Agent's new module ``src/PIL/WebSave.py`` inside the Pillow repo.
The module exposes a single entry point::

    save(image, path, *, quality=None, optimize=True)

that derives save behaviour from the destination file extension
(case-insensitive):

  * ``.png``        — lossless; PNG ``optimize`` flag honoured.
  * ``.webp``       — lossy WebP; ``quality`` forwarded (default 80–90).
  * ``.jpg/.jpeg``  — JPEG; transparency flattened onto an OPAQUE WHITE canvas
                      using the source alpha as paste mask; ``quality`` forwarded.
  * anything else   — ``ValueError`` whose message contains the offending ext.

Additional contract: missing parent dirs are created; bare-filename paths work;
the input image is never mutated; the written path string is returned.

The module under test is loaded DIRECTLY from REPO_DIR/src/PIL/WebSave.py (not
from any installed PIL.WebSave), so the Agent's actual file is exercised.
Fixture images and result re-opening use the installed ``PIL``.

Verification strategy: load the Agent's module from source, drive the real
Pillow encoders through ``save``, then reopen the written files with installed
Pillow to assert concrete format identifiers, pixel values, file-size ordering,
directory creation, immutability and error behaviour. A naive stub (fixed
output, ignored quality, no alpha flatten, no dir creation, no ValueError) fails.
Finally the Agent's own native suite is executed:

    python -m pytest Tests/test_websave.py -q
"""

import importlib.util
import os
import subprocess
import sys

import pytest

# The installed Pillow is used only to build/inspect fixture images.
from PIL import Image, features


REPO_DIR = "/workspace/Pillow"
MODULE_PATH = os.path.join(REPO_DIR, "src", "PIL", "WebSave.py")


def _load_websave():
    """Import the Agent's WebSave.py straight from the repo source tree."""
    assert os.path.isfile(MODULE_PATH), f"WebSave.py not found at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("_agent_websave", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPillowImageProcessing:
    """Verify the WebSave format-aware save helper."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/PIL/WebSave.py must exist."""
        assert os.path.isfile(MODULE_PATH), "WebSave.py was not created"

    def test_module_imports_and_exposes_save(self):
        """The module imports cleanly and exposes a callable ``save``."""
        mod = _load_websave()
        assert hasattr(mod, "save"), "WebSave.save is missing"
        assert callable(mod.save), "WebSave.save is not callable"

    def test_native_test_file_exists(self):
        """Tests/test_websave.py (the Agent's own test) must exist."""
        tpath = os.path.join(self.REPO_DIR, "Tests", "test_websave.py")
        assert os.path.isfile(tpath), "Tests/test_websave.py was not created"

    # ------------------------------------------------------------------
    # L2: per-format save produces the correct reopened format identifier.
    # ------------------------------------------------------------------

    def test_png_format_and_returns_path(self, tmp_path):
        """PNG save reopens as PNG and returns the written path string."""
        mod = _load_websave()
        src = Image.new("RGB", (20, 14), (40, 120, 200))
        out_path = os.path.join(str(tmp_path), "asset.png")
        ret = mod.save(src, out_path)
        assert os.path.isfile(out_path), "PNG file was not written"
        assert ret == out_path, f"save must return its path; got {ret!r}"
        with Image.open(out_path) as re:
            re.load()
            assert re.format == "PNG", f"expected PNG got {re.format}"
            assert re.size == (20, 14)
            # PNG is lossless: exact pixel preserved.
            assert re.convert("RGB").getpixel((0, 0)) == (40, 120, 200)

    def test_jpeg_format(self, tmp_path):
        """A .jpg path reopens with format identifier 'JPEG'."""
        mod = _load_websave()
        src = Image.new("RGB", (24, 24), (200, 100, 50))
        out_path = os.path.join(str(tmp_path), "asset.jpg")
        ret = mod.save(src, out_path)
        assert ret == out_path
        with Image.open(out_path) as re:
            re.load()
            assert re.format == "JPEG", f"expected JPEG got {re.format}"
            assert re.size == (24, 24)

    def test_jpeg_alias_jpeg_extension(self, tmp_path):
        """The .jpeg alias also writes a JPEG."""
        mod = _load_websave()
        src = Image.new("RGB", (12, 12), (10, 220, 30))
        out_path = os.path.join(str(tmp_path), "asset.jpeg")
        mod.save(src, out_path)
        with Image.open(out_path) as re:
            re.load()
            assert re.format == "JPEG", f"expected JPEG for .jpeg got {re.format}"

    def test_extension_case_insensitive(self, tmp_path):
        """Extension matching is case-insensitive (.PNG behaves like .png)."""
        mod = _load_websave()
        src = Image.new("RGB", (10, 10), (40, 80, 120))
        out_path = os.path.join(str(tmp_path), "UPPER.PNG")
        mod.save(src, out_path)
        assert os.path.isfile(out_path)
        with Image.open(out_path) as re:
            re.load()
            assert re.format == "PNG", f"expected PNG for .PNG got {re.format}"

    # ------------------------------------------------------------------
    # L2: JPEG transparency is flattened onto opaque white.
    # ------------------------------------------------------------------

    def test_jpeg_flattens_alpha_to_white(self, tmp_path):
        """A fully transparent RGBA pixel reopens as white (255,255,255) in JPEG."""
        mod = _load_websave()
        # Opaque red background with a large fully-transparent dark block so JPEG
        # chroma-subsampling from neighbours cannot mask the flatten-to-white.
        src = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        for x in range(16):
            for y in range(16):
                src.putpixel((x, y), (10, 20, 30, 0))  # transparent, dark RGB
        out_path = os.path.join(str(tmp_path), "flat.jpg")
        mod.save(src, out_path)
        with Image.open(out_path) as re:
            re.load()
            assert re.format == "JPEG", f"expected JPEG got {re.format}"
            px = re.convert("RGB").getpixel((4, 4))
            assert all(c >= 248 for c in px), (
                f"transparent pixel should flatten to white; got {px}"
            )

    def test_jpeg_flattens_la_mode_alpha(self, tmp_path):
        """An LA image with a transparent region also flattens to white."""
        mod = _load_websave()
        src = Image.new("LA", (32, 32), (30, 255))  # opaque mid-gray
        for x in range(16):
            for y in range(16):
                src.putpixel((x, y), (30, 0))  # transparent dark
        out_path = os.path.join(str(tmp_path), "la.jpg")
        mod.save(src, out_path)
        with Image.open(out_path) as re:
            re.load()
            assert re.format == "JPEG"
            px = re.convert("RGB").getpixel((4, 4))
            assert all(c >= 248 for c in px), (
                f"transparent LA pixel should flatten to white; got {px}"
            )

    def test_jpeg_opaque_pixel_preserved_after_flatten(self, tmp_path):
        """Opaque (alpha=255) content survives the flatten unchanged in hue."""
        mod = _load_websave()
        src = Image.new("RGBA", (32, 32), (0, 0, 0, 0))  # transparent base
        # Large opaque blue block in the lower-right quadrant.
        for x in range(16, 32):
            for y in range(16, 32):
                src.putpixel((x, y), (20, 40, 220, 255))
        out_path = os.path.join(str(tmp_path), "mixed.jpg")
        mod.save(src, out_path)
        with Image.open(out_path) as re:
            re.load()
            r, g, b = re.convert("RGB").getpixel((24, 24))
            # Blue dominant, clearly not flattened to white.
            assert b > 150 and b > r and b > g, (
                f"opaque content not preserved through flatten; got {(r, g, b)}"
            )

    # ------------------------------------------------------------------
    # L2: quality handling.
    # ------------------------------------------------------------------

    def test_quality_explicit_changes_file_size(self, tmp_path):
        """Explicit low quality yields a strictly smaller JPEG than high quality."""
        mod = _load_websave()
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
        mod.save(noisy, low_path, quality=10)
        mod.save(noisy, high_path, quality=95)
        low = os.path.getsize(low_path)
        high = os.path.getsize(high_path)
        assert low < high, (
            f"explicit quality must be forwarded: q10={low} q95={high}"
        )

    def test_quality_default_applied(self, tmp_path):
        """Omitting quality uses a default (80–90) without error; sane file size."""
        mod = _load_websave()
        import random

        random.seed(99)
        noisy = Image.new("RGB", (96, 96))
        npx = noisy.load()
        for x in range(96):
            for y in range(96):
                npx[x, y] = (
                    random.randint(0, 255),
                    random.randint(0, 255),
                    random.randint(0, 255),
                )
        low_path = os.path.join(str(tmp_path), "q10.jpg")
        high_path = os.path.join(str(tmp_path), "q95.jpg")
        default_path = os.path.join(str(tmp_path), "default.jpg")
        mod.save(noisy, low_path, quality=10)
        mod.save(noisy, high_path, quality=95)
        mod.save(noisy, default_path)  # default
        low = os.path.getsize(low_path)
        high = os.path.getsize(high_path)
        default = os.path.getsize(default_path)
        assert default > 0
        # Default must sit at/above q=10 and at/below q=95 (i.e. in the 80–90 band).
        assert low <= default <= high, (
            f"default quality out of band: q10={low} default={default} q95={high}"
        )

    def test_png_ignores_quality(self, tmp_path):
        """Passing quality to a PNG path must not raise and stays lossless."""
        mod = _load_websave()
        src = Image.new("RGB", (16, 16), (123, 45, 67))
        out_path = os.path.join(str(tmp_path), "q.png")
        # Should not raise despite quality being irrelevant for PNG.
        mod.save(src, out_path, quality=10)
        with Image.open(out_path) as re:
            re.load()
            assert re.format == "PNG"
            assert re.convert("RGB").getpixel((0, 0)) == (123, 45, 67), (
                "PNG must stay lossless regardless of quality"
            )

    # ------------------------------------------------------------------
    # L2: path / directory handling.
    # ------------------------------------------------------------------

    def test_creates_missing_parent_directories(self, tmp_path):
        """A path whose parent dirs do not exist gets them created."""
        mod = _load_websave()
        src = Image.new("RGB", (8, 8), (5, 5, 5))
        out_path = os.path.join(str(tmp_path), "a", "b", "c", "deep.png")
        assert not os.path.isdir(os.path.dirname(out_path))
        ret = mod.save(src, out_path)
        assert os.path.isfile(out_path), "nested file was not written"
        assert ret == out_path

    def test_bare_filename_no_directory_component(self, tmp_path, monkeypatch):
        """A bare filename (no dir part) saves without erroring on dir creation."""
        mod = _load_websave()
        monkeypatch.chdir(str(tmp_path))
        src = Image.new("RGB", (8, 8), (5, 5, 5))
        ret = mod.save(src, "bare.png")
        assert os.path.isfile(os.path.join(str(tmp_path), "bare.png")), (
            "bare-filename save did not produce a file"
        )
        assert ret == "bare.png"

    # ------------------------------------------------------------------
    # L2: error and immutability contracts.
    # ------------------------------------------------------------------

    def test_unknown_extension_raises_with_ext_in_message(self, tmp_path):
        """An unsupported extension raises ValueError naming the extension."""
        mod = _load_websave()
        src = Image.new("RGB", (8, 8), (1, 2, 3))
        out_path = os.path.join(str(tmp_path), "asset.gif")
        with pytest.raises(ValueError) as exc:
            mod.save(src, out_path)
        assert "gif" in str(exc.value).lower(), (
            f"ValueError message must contain the offending extension; got {exc.value!r}"
        )

    def test_source_image_not_mutated(self, tmp_path):
        """Saving (incl. JPEG alpha flatten) must not mutate the source image."""
        mod = _load_websave()
        src = Image.new("RGBA", (24, 24), (200, 50, 25, 255))
        for x in range(8):
            for y in range(8):
                src.putpixel((x, y), (1, 2, 3, 0))  # transparent block
        before_mode = src.mode
        before_size = src.size
        before_bytes = src.tobytes()
        mod.save(src, os.path.join(str(tmp_path), "m.jpg"))
        assert src.mode == before_mode, "source mode changed"
        assert src.size == before_size, "source size changed"
        assert src.tobytes() == before_bytes, "source pixel data was mutated"

    @pytest.mark.skipif(
        not features.check("webp"), reason="WebP support not built into Pillow"
    )
    def test_webp_format_and_quality(self, tmp_path):
        """A .webp path writes a readable WebP and forwards quality."""
        mod = _load_websave()
        import random

        random.seed(7)
        noisy = Image.new("RGB", (64, 64))
        npx = noisy.load()
        for x in range(64):
            for y in range(64):
                npx[x, y] = (
                    random.randint(0, 255),
                    random.randint(0, 255),
                    random.randint(0, 255),
                )
        out_path = os.path.join(str(tmp_path), "asset.webp")
        low_path = os.path.join(str(tmp_path), "low.webp")
        ret = mod.save(noisy, out_path, quality=90)
        mod.save(noisy, low_path, quality=10)
        assert ret == out_path
        with Image.open(out_path) as re:
            re.load()
            assert re.format == "WEBP", f"expected WEBP got {re.format}"
            assert re.size == (64, 64)
        # Lossy quality must influence size for a noisy source.
        assert os.path.getsize(low_path) < os.path.getsize(out_path), (
            "webp quality was not forwarded to the encoder"
        )

    # ------------------------------------------------------------------
    # L2: the Agent's own native test suite must pass.
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """`python -m pytest Tests/test_websave.py -q` exits cleanly."""
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "Tests/test_websave.py", "-q"],
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
