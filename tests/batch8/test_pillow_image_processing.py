"""
Test for 'pillow-image-processing' skill (variant ext8) — Batch Directory Processor.

Verifies the Agent's new module ``src/PIL/BatchOps.py`` inside the Pillow repo,
exposing a deterministic batch directory processor:

    process_dir(src_dir, dst_dir, *, action, **params) -> list[str]

Behaviour under test (per the ext8 requirement doc):
  * Processes only supported image extensions (.png/.jpg/.jpeg/.webp/.bmp,
    case-insensitive) directly inside ``src_dir``; ignores other files and
    does NOT recurse into subdirectories.
  * ``action="convert"`` with ``format=`` re-encodes (new extension; JPEG
    flattens alpha onto opaque white).
  * ``action="resize"`` with ``width=`` resizes preserving aspect ratio
    (rounded, floor 1); output keeps original filename + format.
  * ``action="thumbnail"`` with ``size=`` fits inside a size×size box without
    upscaling; output keeps original filename + format.
  * Missing ``src_dir`` -> FileNotFoundError; empty-but-existing -> ``[]`` and
    ``dst_dir`` still created.
  * Unknown action or missing required param -> ValueError.
  * Returned path list is sorted by input filename (deterministic).

The module under test is loaded DIRECTLY from REPO_DIR/src/PIL/BatchOps.py so
the Agent's actual file is exercised. Fixture images and result re-opening use
the installed ``PIL``. The Agent's own native test file is also driven via the
documented acceptance command.

Native command verified by Acceptance Criteria:
    python -m pytest Tests/test_batchops.py -q

A naive/stub implementation — one that returns a fixed list, ignores the
``action``/``width``/``size``/``format`` params, hardcodes output names, skips
writing files, or fails to filter extensions / sort / raise — MUST fail these
tests.
"""

import importlib.util
import os
import subprocess
import sys

import pytest

# The installed Pillow is used only to build/inspect fixture images.
from PIL import Image, features


REPO_DIR = "/workspace/Pillow"
MODULE_PATH = os.path.join(REPO_DIR, "src", "PIL", "BatchOps.py")

SUPPORTED_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def _load_batchops():
    """Import the Agent's BatchOps.py straight from the repo source tree."""
    assert os.path.isfile(MODULE_PATH), f"BatchOps.py not found at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("_agent_batchops", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_png(path, size, color):
    """Write a solid-color PNG fixture and return its path."""
    Image.new("RGB", size, color).save(path, "PNG")
    return path


def _names(paths):
    """Basenames of a returned path list (preserving order)."""
    return [os.path.basename(p) for p in paths]


class TestPillowImageProcessing:
    """Verify the BatchOps deterministic directory batch processor."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/PIL/BatchOps.py must exist."""
        assert os.path.isfile(MODULE_PATH), "BatchOps.py was not created"

    def test_module_imports_and_exposes_api(self):
        """The module imports cleanly and exposes a callable ``process_dir``."""
        mod = _load_batchops()
        assert hasattr(mod, "process_dir"), "BatchOps.process_dir is missing"
        assert callable(mod.process_dir), "BatchOps.process_dir is not callable"

    def test_native_test_file_exists(self):
        """Tests/test_batchops.py (the Agent's own test) must exist."""
        tpath = os.path.join(self.REPO_DIR, "Tests", "test_batchops.py")
        assert os.path.isfile(tpath), "Tests/test_batchops.py was not created"

    # ------------------------------------------------------------------
    # L2: input selection / filtering / non-recursion.
    # ------------------------------------------------------------------

    def test_processes_only_supported_extensions(self, tmp_path):
        """Only supported image extensions are processed; other files ignored."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        _write_png(str(src / "a.png"), (40, 20), (200, 10, 10))
        _write_png(str(src / "b.png"), (20, 40), (10, 200, 10))
        # Non-image files that must be ignored.
        (src / "notes.txt").write_text("ignore me")
        (src / "data.json").write_text("{}")
        # A file with an image-like name but unsupported extension.
        (src / "weird.gif").write_bytes(b"GIF89a")

        out = mod.process_dir(str(src), str(dst), action="resize", width=10)
        assert len(out) == 2, f"only the two PNGs should be processed; got {out}"
        for p in out:
            assert os.path.isfile(p), f"declared output not on disk: {p}"
        produced = {os.path.basename(p) for p in out}
        assert produced == {"a.png", "b.png"}, produced
        # The ignored files must NOT have been copied/processed into dst.
        dst_names = set(os.listdir(str(dst)))
        assert "notes.txt" not in dst_names
        assert "data.json" not in dst_names
        assert "weird.gif" not in dst_names

    def test_does_not_recurse_into_subdirectories(self, tmp_path):
        """Images inside subdirectories of src_dir are NOT processed."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        sub = src / "nested"
        sub.mkdir(parents=True)
        _write_png(str(src / "top.png"), (30, 30), (1, 2, 3))
        _write_png(str(sub / "deep.png"), (30, 30), (4, 5, 6))

        out = mod.process_dir(str(src), str(dst), action="resize", width=10)
        names = _names(out)
        assert names == ["top.png"], f"must not recurse; got {names}"
        # The nested image must not have leaked into dst at top level.
        assert "deep.png" not in os.listdir(str(dst))

    def test_extension_filter_case_insensitive(self, tmp_path):
        """Uppercase supported extensions are still processed."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        # Save as PNG content but with an uppercase extension.
        Image.new("RGB", (20, 10), (9, 9, 9)).save(str(src / "PIC.PNG"), "PNG")
        out = mod.process_dir(str(src), str(dst), action="resize", width=10)
        assert len(out) == 1, f"uppercase .PNG should be processed; got {out}"

    # ------------------------------------------------------------------
    # L2: return value contract — sorting & determinism.
    # ------------------------------------------------------------------

    def test_returns_sorted_path_list(self, tmp_path):
        """Returned paths are sorted by input filename regardless of creation order."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        # Create in deliberately non-sorted order.
        for name in ("m.png", "a.png", "z.png", "c.png"):
            _write_png(str(src / name), (12, 12), (5, 5, 5))
        out = mod.process_dir(str(src), str(dst), action="resize", width=6)
        stems = [os.path.splitext(os.path.basename(p))[0] for p in out]
        assert stems == sorted(stems), f"output list not sorted: {stems}"
        assert stems == ["a", "c", "m", "z"], stems

    def test_empty_existing_src_returns_empty_and_creates_dst(self, tmp_path):
        """Existing-but-empty src returns [] and still creates dst_dir."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        assert not dst.exists()
        out = mod.process_dir(str(src), str(dst), action="resize", width=10)
        assert out == [], f"empty src should return []; got {out}"
        assert dst.is_dir(), "dst_dir must be created even when there is no work"

    def test_missing_src_raises_filenotfound(self, tmp_path):
        """A non-existent src_dir raises FileNotFoundError."""
        mod = _load_batchops()
        missing = tmp_path / "nope"
        dst = tmp_path / "dst"
        with pytest.raises(FileNotFoundError):
            mod.process_dir(str(missing), str(dst), action="resize", width=10)

    # ------------------------------------------------------------------
    # L2: resize action.
    # ------------------------------------------------------------------

    def test_resize_preserves_aspect_ratio(self, tmp_path):
        """resize width=100: 400x200 -> 100x50 and 200x400 -> 100x200."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        _write_png(str(src / "a.png"), (400, 200), (200, 0, 0))
        _write_png(str(src / "b.png"), (200, 400), (0, 0, 200))
        out = mod.process_dir(str(src), str(dst), action="resize", width=100)
        by_name = {os.path.basename(p): p for p in out}
        assert set(by_name) == {"a.png", "b.png"}, by_name
        with Image.open(by_name["a.png"]) as im:
            assert im.size == (100, 50), f"a.png expected (100,50) got {im.size}"
        with Image.open(by_name["b.png"]) as im:
            assert im.size == (100, 200), f"b.png expected (100,200) got {im.size}"

    def test_resize_keeps_filename_and_format(self, tmp_path):
        """resize output keeps the original filename and format (PNG stays PNG)."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        _write_png(str(src / "logo.png"), (300, 100), (10, 20, 30))
        out = mod.process_dir(str(src), str(dst), action="resize", width=30)
        assert _names(out) == ["logo.png"], _names(out)
        with Image.open(out[0]) as im:
            assert im.format == "PNG", f"expected PNG got {im.format}"
            assert im.size == (30, 10), f"expected (30,10) got {im.size}"

    def test_resize_height_floor_one(self, tmp_path):
        """A derived height that would round below 1 is floored to 1."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        # 1000 wide, 1 tall -> width=2 gives height 2*1/1000 -> floor 1.
        _write_png(str(src / "wide.png"), (1000, 1), (7, 7, 7))
        out = mod.process_dir(str(src), str(dst), action="resize", width=2)
        with Image.open(out[0]) as im:
            assert im.size[0] == 2, f"width must be honoured: {im.size}"
            assert im.size[1] == 1, f"height floor-1 violated: {im.size}"

    def test_resize_missing_width_raises(self, tmp_path):
        """resize without the required width= raises ValueError."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        _write_png(str(src / "a.png"), (40, 20), (1, 2, 3))
        with pytest.raises(ValueError):
            mod.process_dir(str(src), str(dst), action="resize")

    # ------------------------------------------------------------------
    # L2: convert action.
    # ------------------------------------------------------------------

    def test_convert_changes_extension_and_format(self, tmp_path):
        """convert format=webp: a.png -> a.webp with WEBP format, stem preserved."""
        mod = _load_batchops()
        if not features.check("webp"):
            pytest.skip("WebP support not built into Pillow")
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        _write_png(str(src / "a.png"), (40, 20), (90, 160, 30))
        _write_png(str(src / "b.png"), (20, 40), (30, 90, 160))
        out = mod.process_dir(str(src), str(dst), action="convert", format="webp")
        names = sorted(_names(out))
        assert names == ["a.webp", "b.webp"], names
        for p in out:
            assert os.path.isfile(p), f"output missing: {p}"
            with Image.open(p) as im:
                assert im.format == "WEBP", f"expected WEBP got {im.format}"

    def test_convert_to_png(self, tmp_path):
        """convert format=png re-encodes a BMP source to a real PNG file."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        Image.new("RGB", (24, 16), (12, 34, 56)).save(str(src / "raw.bmp"), "BMP")
        out = mod.process_dir(str(src), str(dst), action="convert", format="png")
        assert _names(out) == ["raw.png"], _names(out)
        with Image.open(out[0]) as im:
            assert im.format == "PNG", f"expected PNG got {im.format}"
            assert im.size == (24, 16)

    def test_convert_jpeg_flattens_alpha_to_white(self, tmp_path):
        """convert format=jpeg flattens a transparent region onto opaque white."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        # Opaque red with a large fully-transparent dark block in a corner.
        rgba = Image.new("RGBA", (32, 32), (255, 0, 0, 255))
        for x in range(16):
            for y in range(16):
                rgba.putpixel((x, y), (10, 20, 30, 0))
        rgba.save(str(src / "logo.png"), "PNG")
        out = mod.process_dir(str(src), str(dst), action="convert", format="jpeg")
        assert _names(out) == ["logo.jpeg"], _names(out)
        with Image.open(out[0]) as im:
            im.load()
            assert im.format == "JPEG", f"expected JPEG got {im.format}"
            # Sample well inside the transparent region (away from the edge).
            px = im.convert("RGB").getpixel((4, 4))
            assert all(c >= 248 for c in px), (
                f"transparent region must flatten to white; got {px}"
            )

    def test_convert_missing_format_raises(self, tmp_path):
        """convert without the required format= raises ValueError."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        _write_png(str(src / "a.png"), (10, 10), (1, 2, 3))
        with pytest.raises(ValueError):
            mod.process_dir(str(src), str(dst), action="convert")

    # ------------------------------------------------------------------
    # L2: thumbnail action.
    # ------------------------------------------------------------------

    def test_thumbnail_fits_box_longer_side(self, tmp_path):
        """thumbnail size=100: 400x200 -> (100,50); longer side equals size."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        _write_png(str(src / "land.png"), (400, 200), (40, 50, 60))
        _write_png(str(src / "port.png"), (200, 400), (60, 50, 40))
        out = mod.process_dir(str(src), str(dst), action="thumbnail", size=100)
        by_name = {os.path.basename(p): p for p in out}
        with Image.open(by_name["land.png"]) as im:
            assert im.size == (100, 50), f"landscape expected (100,50) got {im.size}"
        with Image.open(by_name["port.png"]) as im:
            assert im.size == (50, 100), f"portrait expected (50,100) got {im.size}"

    def test_thumbnail_no_upscale(self, tmp_path):
        """thumbnail does not upscale an image already smaller than the box."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        _write_png(str(src / "tiny.png"), (40, 25), (5, 6, 7))
        out = mod.process_dir(str(src), str(dst), action="thumbnail", size=100)
        with Image.open(out[0]) as im:
            assert im.size == (40, 25), f"must not upscale; got {im.size}"

    def test_thumbnail_missing_size_raises(self, tmp_path):
        """thumbnail without the required size= raises ValueError."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        _write_png(str(src / "a.png"), (40, 20), (1, 2, 3))
        with pytest.raises(ValueError):
            mod.process_dir(str(src), str(dst), action="thumbnail")

    # ------------------------------------------------------------------
    # L2: unknown action / determinism across runs.
    # ------------------------------------------------------------------

    def test_unknown_action_raises(self, tmp_path):
        """An unknown action raises ValueError."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        _write_png(str(src / "a.png"), (10, 10), (1, 2, 3))
        with pytest.raises(ValueError):
            mod.process_dir(str(src), str(dst), action="frobnicate", width=5)

    def test_deterministic_same_inputs_same_bytes(self, tmp_path):
        """Same content + same action produces byte-identical outputs across runs."""
        mod = _load_batchops()
        src = tmp_path / "src"
        dst1 = tmp_path / "dst1"
        dst2 = tmp_path / "dst2"
        src.mkdir()
        _write_png(str(src / "a.png"), (200, 120), (33, 99, 200))
        out1 = mod.process_dir(str(src), str(dst1), action="resize", width=50)
        out2 = mod.process_dir(str(src), str(dst2), action="resize", width=50)
        assert _names(out1) == _names(out2) == ["a.png"]
        with open(out1[0], "rb") as f1, open(out2[0], "rb") as f2:
            assert f1.read() == f2.read(), "resize output is not deterministic"

    # ------------------------------------------------------------------
    # L2: the Agent's own native test suite must pass.
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """`python -m pytest Tests/test_batchops.py -q` exits cleanly."""
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "Tests/test_batchops.py", "-q"],
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
