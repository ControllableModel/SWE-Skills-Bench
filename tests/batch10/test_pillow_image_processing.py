"""
Test for 'pillow-image-processing' skill (variant ext10) — Watermark Compositor.

Verifies the Agent's new module ``src/PIL/Watermark.py`` inside the Pillow repo,
a deterministic alpha compositor that stamps a semi-transparent mark onto a base
image at a chosen corner (with margin) without mutating its inputs:

  * ``apply_watermark(base, mark, *, position, margin, opacity)``
        -> a new RGBA image, mark alpha-composited over base at the requested
           corner/centre, mark alpha scaled by ``opacity``.
  * ``text_watermark(base, text, *, position, margin, opacity, fill)``
        -> renders ``text`` with Pillow's built-in default font into a
           transparent mark and composites it onto base via ``apply_watermark``.

The module under test is loaded DIRECTLY from REPO_DIR/src/PIL/Watermark.py
(not from any installed PIL.Watermark), so the Agent's actual file is exercised.
Fixture images use the installed ``PIL``. An independent verification harness
re-derives expected compositing math rather than trusting the agent's tests.

Discriminative intent: a stub that ignores ``position``/``margin``/``opacity``,
mutates its inputs, skips alpha compositing, or hardcodes output MUST fail.

Native command verified by Acceptance Criteria:
    python -m pytest Tests/test_watermark.py -q
"""

import importlib.util
import os
import subprocess
import sys

import pytest

# The installed Pillow is used only to build/inspect fixture images.
from PIL import Image


REPO_DIR = "/workspace/Pillow"
MODULE_PATH = os.path.join(REPO_DIR, "src", "PIL", "Watermark.py")


def _load_watermark():
    """Import the Agent's Watermark.py straight from the repo source tree."""
    assert os.path.isfile(MODULE_PATH), f"Watermark.py not found at {MODULE_PATH}"
    spec = importlib.util.spec_from_file_location("_agent_watermark", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _solid_base(w=80, h=60, color=(20, 40, 60)):
    """An opaque RGB base; returned as RGB so we also exercise RGBA conversion."""
    return Image.new("RGB", (w, h), color)


def _opaque_mark(w=16, h=12, color=(255, 0, 0, 255)):
    """A fully-opaque RGBA mark."""
    return Image.new("RGBA", (w, h), color)


def _half_transparent_mark(w=16, h=12, rgb=(0, 255, 0)):
    """A mark whose left half is opaque and right half fully transparent."""
    m = Image.new("RGBA", (w, h), (rgb[0], rgb[1], rgb[2], 255))
    px = m.load()
    for x in range(w // 2, w):
        for y in range(h):
            px[x, y] = (rgb[0], rgb[1], rgb[2], 0)
    return m


def _diff_mask(out, base_rgba):
    """Set of (x,y) where the composited output differs from the base (RGBA)."""
    assert out.size == base_rgba.size
    op = out.convert("RGBA").load()
    bp = base_rgba.load()
    changed = set()
    for y in range(out.size[1]):
        for x in range(out.size[0]):
            if op[x, y] != bp[x, y]:
                changed.add((x, y))
    return changed


def _bbox_of(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


class TestPillowImageProcessing:
    """Verify the Watermark alpha compositor."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/PIL/Watermark.py must exist."""
        assert os.path.isfile(MODULE_PATH), "Watermark.py was not created"

    def test_module_imports_and_exposes_api(self):
        """The module imports cleanly and exposes the two public callables."""
        mod = _load_watermark()
        for name in ("apply_watermark", "text_watermark"):
            assert hasattr(mod, name), f"Watermark.{name} is missing"
            assert callable(getattr(mod, name)), f"Watermark.{name} is not callable"

    def test_native_test_file_exists(self):
        """Tests/test_watermark.py (the Agent's own test) must exist."""
        tpath = os.path.join(self.REPO_DIR, "Tests", "test_watermark.py")
        assert os.path.isfile(tpath), "Tests/test_watermark.py was not created"

    # ------------------------------------------------------------------
    # L2: apply_watermark — return type, non-mutation, default position.
    # ------------------------------------------------------------------

    def test_returns_new_rgba_without_mutating_inputs(self):
        """Output is a new RGBA image; neither base nor mark is mutated."""
        mod = _load_watermark()
        base = _solid_base(80, 60, (30, 30, 30))
        mark = _opaque_mark(16, 12, (200, 10, 10, 255))
        base_before = base.tobytes()
        mark_before = mark.tobytes()
        base_size = base.size

        out = mod.apply_watermark(base, mark, position="bottom-right", margin=10)

        assert isinstance(out, Image.Image), "apply_watermark must return an Image"
        assert out.mode == "RGBA", f"output must be RGBA, got {out.mode}"
        assert out.size == base_size, f"output size must match base; got {out.size}"
        # Must be a distinct object from base.
        assert out is not base, "output must not be the base object itself"
        # Inputs unchanged.
        assert base.tobytes() == base_before, "base image was mutated"
        assert mark.tobytes() == mark_before, "mark image was mutated"

    def test_bottom_right_corner_placement_with_margin(self):
        """bottom-right + margin=10: changed region's bottom-right corner sits
        exactly 10px from the base's bottom-right corner."""
        mod = _load_watermark()
        W, H, mw, mh, margin = 80, 60, 16, 12, 10
        base = _solid_base(W, H, (0, 0, 0))
        mark = _opaque_mark(mw, mh, (255, 255, 255, 255))
        out = mod.apply_watermark(base, mark, position="bottom-right", margin=margin)

        changed = _diff_mask(out, base.convert("RGBA"))
        assert changed, "watermark produced no visible change"
        x0, y0, x1, y1 = _bbox_of(changed)
        # The mark occupies [x0..x1],[y0..y1]; its right/bottom edge is margin
        # pixels from the base edge. Last changed pixel index == W-1-margin.
        assert x1 == W - 1 - margin, f"right edge: got x1={x1}, expected {W - 1 - margin}"
        assert y1 == H - 1 - margin, f"bottom edge: got y1={y1}, expected {H - 1 - margin}"
        # And the mark spans its own width/height.
        assert x1 - x0 + 1 == mw, f"mark width region wrong: {x1 - x0 + 1} != {mw}"
        assert y1 - y0 + 1 == mh, f"mark height region wrong: {y1 - y0 + 1} != {mh}"

    def test_top_left_corner_placement_with_margin(self):
        """top-left + margin=5: changed region's top-left corner sits exactly
        5px from the base's origin."""
        mod = _load_watermark()
        mw, mh, margin = 16, 12, 5
        base = _solid_base(80, 60, (0, 0, 0))
        mark = _opaque_mark(mw, mh, (255, 255, 255, 255))
        out = mod.apply_watermark(base, mark, position="top-left", margin=margin)

        changed = _diff_mask(out, base.convert("RGBA"))
        x0, y0, x1, y1 = _bbox_of(changed)
        assert x0 == margin, f"left edge: got x0={x0}, expected {margin}"
        assert y0 == margin, f"top edge: got y0={y0}, expected {margin}"
        assert x1 - x0 + 1 == mw and y1 - y0 + 1 == mh, "mark region size wrong"

    def test_each_corner_distinct_and_correct(self):
        """top-right and bottom-left land at the correct, distinct corners.

        A stub that ignores ``position`` (always same corner) fails here.
        """
        mod = _load_watermark()
        W, H, mw, mh, margin = 80, 60, 16, 12, 4
        base = _solid_base(W, H, (0, 0, 0))
        mark = _opaque_mark(mw, mh, (255, 255, 255, 255))

        tr = mod.apply_watermark(base, mark, position="top-right", margin=margin)
        bl = mod.apply_watermark(base, mark, position="bottom-left", margin=margin)

        trc = _bbox_of(_diff_mask(tr, base.convert("RGBA")))
        blc = _bbox_of(_diff_mask(bl, base.convert("RGBA")))

        # top-right: top edge at margin, right edge at W-1-margin
        assert trc[1] == margin, f"top-right top edge wrong: {trc}"
        assert trc[2] == W - 1 - margin, f"top-right right edge wrong: {trc}"
        # bottom-left: left edge at margin, bottom edge at H-1-margin
        assert blc[0] == margin, f"bottom-left left edge wrong: {blc}"
        assert blc[3] == H - 1 - margin, f"bottom-left bottom edge wrong: {blc}"
        assert trc != blc, "different positions must yield different placements"

    def test_center_placement_ignores_margin(self):
        """center centres the mark and ignores margin; even W-mw => symmetric."""
        mod = _load_watermark()
        W, H, mw, mh = 80, 60, 16, 12
        base = _solid_base(W, H, (0, 0, 0))
        mark = _opaque_mark(mw, mh, (255, 255, 255, 255))
        out = mod.apply_watermark(base, mark, position="center", margin=999)
        x0, y0, x1, y1 = _bbox_of(_diff_mask(out, base.convert("RGBA")))
        # Centred: left margin == right margin (within 1px for integer centring).
        left_gap = x0
        right_gap = (W - 1) - x1
        top_gap = y0
        bottom_gap = (H - 1) - y1
        assert abs(left_gap - right_gap) <= 1, (
            f"not horizontally centred: left={left_gap} right={right_gap}"
        )
        assert abs(top_gap - bottom_gap) <= 1, (
            f"not vertically centred: top={top_gap} bottom={bottom_gap}"
        )
        assert x1 - x0 + 1 == mw and y1 - y0 + 1 == mh

    # ------------------------------------------------------------------
    # L2: alpha compositing semantics.
    # ------------------------------------------------------------------

    def test_alpha_compositing_transparent_region_unchanged(self):
        """A fully transparent half of the mark leaves the base pixels intact.

        A stub that pastes opaquely (ignoring the mark's alpha) fails here.
        """
        mod = _load_watermark()
        W, H = 80, 60
        base = _solid_base(W, H, (10, 20, 30))
        mark = _half_transparent_mark(16, 12, (250, 0, 0))  # right half alpha 0
        out = mod.apply_watermark(base, mark, position="top-left", margin=0)

        base_rgba = base.convert("RGBA")
        changed = _diff_mask(out, base_rgba)
        # Only the opaque LEFT half (x in 0..7) should differ.
        for (x, y) in changed:
            assert x < 8, (
                f"transparent mark area altered base at {(x, y)} "
                "(alpha compositing not applied)"
            )
        # The left half should actually have changed (non-trivial composite).
        assert any(x < 8 for (x, y) in changed), "opaque mark half had no effect"

    def test_opacity_zero_equals_base(self):
        """opacity=0.0 yields output byte-equal to the base converted to RGBA.

        A stub that ignores ``opacity`` fails here.
        """
        mod = _load_watermark()
        base = _solid_base(48, 32, (77, 88, 99))
        mark = _opaque_mark(16, 12, (255, 255, 255, 255))
        out = mod.apply_watermark(base, mark, position="center", opacity=0.0)
        assert out.convert("RGBA").tobytes() == base.convert("RGBA").tobytes(), (
            "opacity=0.0 must leave the base visually unchanged"
        )

    def test_higher_opacity_larger_difference(self):
        """A larger opacity produces a larger composited pixel difference.

        Uses a mark whose own alpha is partially transparent so scaling matters.
        """
        mod = _load_watermark()
        base = _solid_base(48, 32, (0, 0, 0))
        # Mark with mid alpha so opacity scaling produces graded results.
        mark = Image.new("RGBA", (16, 12), (255, 255, 255, 200))

        def total_abs_diff(opacity):
            out = mod.apply_watermark(
                base, mark, position="center", opacity=opacity
            )
            op = out.convert("RGBA").load()
            bp = base.convert("RGBA").load()
            tot = 0
            for y in range(out.size[1]):
                for x in range(out.size[0]):
                    a, b = op[x, y], bp[x, y]
                    tot += sum(abs(a[i] - b[i]) for i in range(3))
            return tot

        d_low = total_abs_diff(0.25)
        d_high = total_abs_diff(1.0)
        assert d_high > d_low > 0, (
            f"opacity must scale effect: d0.25={d_low} d1.0={d_high}"
        )

    def test_opacity_one_matches_independent_alpha_composite(self):
        """opacity=1.0 over a base equals an independent Image.alpha_composite.

        Independent verification harness: we recompute the expected pixel for
        the mark region using Pillow's own alpha_composite and compare.
        """
        mod = _load_watermark()
        W, H, mw, mh, margin = 60, 40, 16, 12, 3
        base = _solid_base(W, H, (40, 10, 90))
        # Mark with varied alpha across columns to exercise true compositing.
        mark = Image.new("RGBA", (mw, mh), (255, 255, 0, 0))
        mpx = mark.load()
        for x in range(mw):
            for y in range(mh):
                mpx[x, y] = (255, 255, 0, int(255 * (x + 1) / mw))

        out = mod.apply_watermark(
            base, mark, position="top-left", margin=margin, opacity=1.0
        ).convert("RGBA")

        # Independent expectation: composite mark onto a base-sized transparent
        # canvas at (margin, margin), then alpha_composite over base.
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        layer.paste(mark, (margin, margin))
        expected = Image.alpha_composite(base.convert("RGBA"), layer)

        ep = expected.load()
        op = out.load()
        max_diff = 0
        for y in range(margin, margin + mh):
            for x in range(margin, margin + mw):
                for i in range(4):
                    max_diff = max(max_diff, abs(ep[x, y][i] - op[x, y][i]))
        assert max_diff <= 1, (
            f"compositing differs from Image.alpha_composite (max_diff={max_diff})"
        )

    # ------------------------------------------------------------------
    # L2: validation / error handling.
    # ------------------------------------------------------------------

    def test_invalid_position_raises(self):
        """An unknown position string raises ValueError."""
        mod = _load_watermark()
        base = _solid_base(40, 30)
        mark = _opaque_mark()
        with pytest.raises(ValueError):
            mod.apply_watermark(base, mark, position="middle-left")

    def test_out_of_range_opacity_raises(self):
        """opacity outside 0.0..1.0 raises ValueError (both ends)."""
        mod = _load_watermark()
        base = _solid_base(40, 30)
        mark = _opaque_mark()
        with pytest.raises(ValueError):
            mod.apply_watermark(base, mark, opacity=1.5)
        with pytest.raises(ValueError):
            mod.apply_watermark(base, mark, opacity=-0.1)

    # ------------------------------------------------------------------
    # L2: text_watermark behaviour.
    # ------------------------------------------------------------------

    def test_text_watermark_alters_region(self):
        """text_watermark renders text into the base; output differs from base
        and is RGBA, without mutating the base."""
        mod = _load_watermark()
        base = _solid_base(120, 50, (0, 0, 0))
        base_before = base.tobytes()
        out = mod.text_watermark(
            base, "DRAFT", position="center", opacity=0.8, fill=(255, 255, 255)
        )
        assert out.mode == "RGBA", f"text_watermark must return RGBA, got {out.mode}"
        assert out.size == base.size
        changed = _diff_mask(out, base.convert("RGBA"))
        assert changed, "text watermark produced no visible change"
        # Light fill on a black base must brighten the text region.
        op = out.convert("L").load()
        bp = base.convert("L").load()
        brighter = sum(
            1 for (x, y) in changed if op[x, y] > bp[x, y]
        )
        assert brighter > 0, "light text on dark base must brighten pixels"
        assert base.tobytes() == base_before, "base was mutated by text_watermark"

    def test_text_watermark_empty_raises(self):
        """Empty text raises ValueError."""
        mod = _load_watermark()
        base = _solid_base(40, 30)
        with pytest.raises(ValueError):
            mod.text_watermark(base, "")

    # ------------------------------------------------------------------
    # L2: determinism.
    # ------------------------------------------------------------------

    def test_deterministic_byte_identical(self):
        """Identical arguments produce byte-identical output (no randomness)."""
        mod = _load_watermark()
        base = _solid_base(64, 48, (12, 34, 56))
        mark = _opaque_mark(20, 16, (10, 200, 50, 180))
        a = mod.apply_watermark(base, mark, position="bottom-right", margin=7,
                                opacity=0.6)
        b = mod.apply_watermark(base, mark, position="bottom-right", margin=7,
                                opacity=0.6)
        assert a.convert("RGBA").tobytes() == b.convert("RGBA").tobytes(), (
            "apply_watermark is not deterministic"
        )
        t1 = mod.text_watermark(base, "HELLO", position="top-left")
        t2 = mod.text_watermark(base, "HELLO", position="top-left")
        assert t1.convert("RGBA").tobytes() == t2.convert("RGBA").tobytes(), (
            "text_watermark is not deterministic"
        )

    # ------------------------------------------------------------------
    # L2: the Agent's own native test suite must pass.
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """`python -m pytest Tests/test_watermark.py -q` exits cleanly."""
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "Tests/test_watermark.py", "-q"],
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
