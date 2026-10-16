"""
Test for 'pydicom-dicom-parsing' skill (variant ext6).

Variant task
------------
The agent implements a self-contained multi-frame *frame selector* utility:
``src/pydicom/util/frames.py`` exposing exactly

    def get_frame(arr, ds, index)

`arr` is a ``numpy.ndarray`` of stacked frames, `ds` a ``pydicom.dataset.Dataset``
optionally defining ``NumberOfFrames``/``Rows``/``Columns``, and `index` the
frame to return as a 2-D ``(Rows, Columns)`` array. The selection contract:
multi-frame indexing (incl. negative indices), single-frame handling (only
index 0 valid), frame-count derived from ``ds.NumberOfFrames`` (default 1, NOT
from ``arr.shape``), ``IndexError`` on out-of-range, returned-frame shape equal
to ``(Rows, Columns)``, and result independence (mutating the result must not
alter `arr`).

Verification strategy
---------------------
L1 confirms the deliverable files exist and that ``get_frame`` is importable
with the exact 3-positional signature ``(arr, ds, index)``.

L2 drives the *real* behaviour by writing small self-contained driver scripts
into a temp dir under REPO_DIR and executing them with the repo's own Python
(``PYTHONPATH=<REPO_DIR>/src``). Each driver builds numpy arrays + pydicom
Datasets, calls the agent's ``get_frame``, and prints a single machine-readable
``RESULT::{json}`` line this test parses and deep-validates.

Discriminative power: a naive implementation that always indexes ``arr``
without consulting ``NumberOfFrames``, that never raises on out-of-range, that
returns a memory-shared view enabling side-effects, or that ignores the
single-frame contract, MUST fail these tests. The variant's native acceptance
command (``python -m pytest tests/test_util_frames.py -q``) is also executed.
"""

import os
import sys
import json
import subprocess
import tempfile
import textwrap

import pytest


REPO_DIR = "/workspace/pydicom"
SRC_DIR = os.path.join(REPO_DIR, "src")
FRAMES_PATH = os.path.join(SRC_DIR, "pydicom", "util", "frames.py")
NATIVE_TEST = os.path.join(REPO_DIR, "tests", "test_util_frames.py")


def _run_driver(body, timeout=300):
    """Write `body` as a python script under REPO_DIR and run it.

    Returns the parsed JSON dict printed on the last line tagged RESULT::.
    The script must import get_frame from pydicom.util.frames and print
    exactly one line `RESULT::{json}`.
    """
    header = textwrap.dedent(
        """
        import json
        import numpy as np
        from pydicom.dataset import Dataset
        from pydicom.util.frames import get_frame
        """
    )
    script = header + textwrap.dedent(body)

    tmpdir = tempfile.mkdtemp(prefix="frames_drv_", dir=REPO_DIR)
    drv = os.path.join(tmpdir, "driver.py")
    with open(drv, "w") as fh:
        fh.write(script)

    env = dict(os.environ)
    env["PYTHONPATH"] = SRC_DIR

    try:
        proc = subprocess.run(
            [sys.executable, drv],
            cwd=REPO_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    finally:
        try:
            os.remove(drv)
            os.rmdir(tmpdir)
        except OSError:
            pass

    assert proc.returncode == 0, (
        "driver script failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
        % (proc.stdout, proc.stderr)
    )

    result_line = None
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT::"):
            result_line = line[len("RESULT::"):]
    assert result_line is not None, (
        "driver produced no RESULT line.\nSTDOUT:\n%s\nSTDERR:\n%s"
        % (proc.stdout, proc.stderr)
    )
    return json.loads(result_line)


class TestPydicomDicomParsing:
    """Multi-frame frame selector behavioural tests."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverables exist / importable / correct signature
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/pydicom/util/frames.py must exist."""
        assert os.path.isfile(FRAMES_PATH), f"missing {FRAMES_PATH}"

    def test_native_test_file_exists(self):
        """tests/test_util_frames.py must exist."""
        assert os.path.isfile(NATIVE_TEST), f"missing {NATIVE_TEST}"

    def test_signature_and_importable(self):
        """get_frame must import with exactly 3 positional params (arr, ds, index)."""
        result = _run_driver(
            """
            import inspect
            sig = inspect.signature(get_frame)
            params = list(sig.parameters.items())
            names = [n for n, _ in params]
            kinds = [p.kind.name for _, p in params]
            print("RESULT::" + json.dumps({"names": names, "kinds": kinds}))
            """
        )
        assert result["names"] == ["arr", "ds", "index"], (
            "signature must be get_frame(arr, ds, index); got %r" % result["names"]
        )
        for kind in result["kinds"]:
            assert kind in ("POSITIONAL_OR_KEYWORD", "POSITIONAL_ONLY"), (
                "all params must be positional; got %r" % result["kinds"]
            )

    # ------------------------------------------------------------------
    # L2 — multi-frame positive indexing
    # ------------------------------------------------------------------

    def test_multiframe_positive_index_values(self):
        """Frame `index` is the correct slice along the leading axis, shape (R,C)."""
        result = _run_driver(
            """
            arr = np.arange(5 * 4 * 4).reshape(5, 4, 4)
            ds = Dataset()
            ds.NumberOfFrames = 5
            ds.Rows = 4
            ds.Columns = 4
            frame = get_frame(arr, ds, 2)
            print("RESULT::" + json.dumps({
                "shape": list(frame.shape),
                "values": frame.tolist(),
                "expected": arr[2].tolist(),
            }))
            """
        )
        assert result["shape"] == [4, 4], "returned frame must be 2-D (Rows, Columns)"
        assert result["values"] == result["expected"], (
            "frame index=2 must equal arr[2]"
        )

    def test_multiframe_first_and_middle_distinct(self):
        """Different indices return different, correct frames (not a hardcoded one)."""
        result = _run_driver(
            """
            arr = np.arange(5 * 4 * 4).reshape(5, 4, 4)
            ds = Dataset()
            ds.NumberOfFrames = 5
            ds.Rows = 4
            ds.Columns = 4
            f0 = get_frame(arr, ds, 0)
            f3 = get_frame(arr, ds, 3)
            print("RESULT::" + json.dumps({
                "f0": f0.tolist(),
                "f3": f3.tolist(),
                "exp0": arr[0].tolist(),
                "exp3": arr[3].tolist(),
            }))
            """
        )
        assert result["f0"] == result["exp0"], "index=0 must equal arr[0]"
        assert result["f3"] == result["exp3"], "index=3 must equal arr[3]"
        assert result["f0"] != result["f3"], (
            "distinct indices must return distinct frames (no hardcoding)"
        )

    # ------------------------------------------------------------------
    # L2 — negative indexing
    # ------------------------------------------------------------------

    def test_negative_index_last_frame(self):
        """index=-1 returns the last frame (Python-style negative indexing)."""
        result = _run_driver(
            """
            arr = np.arange(5 * 4 * 4).reshape(5, 4, 4)
            ds = Dataset()
            ds.NumberOfFrames = 5
            ds.Rows = 4
            ds.Columns = 4
            last = get_frame(arr, ds, -1)
            print("RESULT::" + json.dumps({
                "last": last.tolist(),
                "expected": arr[4].tolist(),
            }))
            """
        )
        assert result["last"] == result["expected"], "index=-1 must equal arr[4]"

    def test_negative_index_interior(self):
        """index=-2 returns the second-to-last frame."""
        result = _run_driver(
            """
            arr = np.arange(5 * 3 * 2).reshape(5, 3, 2)
            ds = Dataset()
            ds.NumberOfFrames = 5
            ds.Rows = 3
            ds.Columns = 2
            f = get_frame(arr, ds, -2)
            print("RESULT::" + json.dumps({
                "f": f.tolist(),
                "expected": arr[3].tolist(),
                "shape": list(f.shape),
            }))
            """
        )
        assert result["f"] == result["expected"], "index=-2 must equal arr[3]"
        assert result["shape"] == [3, 2]

    # ------------------------------------------------------------------
    # L2 — out-of-range -> IndexError
    # ------------------------------------------------------------------

    def test_out_of_range_positive_raises(self):
        """index == NumberOfFrames (and beyond) must raise IndexError."""
        result = _run_driver(
            """
            arr = np.arange(5 * 4 * 4).reshape(5, 4, 4)
            ds = Dataset()
            ds.NumberOfFrames = 5
            ds.Rows = 4
            ds.Columns = 4
            outcomes = {}
            for idx in (5, 6, 100):
                try:
                    get_frame(arr, ds, idx)
                    outcomes[str(idx)] = "no-raise"
                except IndexError:
                    outcomes[str(idx)] = "IndexError"
                except Exception as exc:
                    outcomes[str(idx)] = type(exc).__name__
            print("RESULT::" + json.dumps(outcomes))
            """
        )
        for idx in ("5", "6", "100"):
            assert result[idx] == "IndexError", (
                "index=%s must raise IndexError, got %s" % (idx, result[idx])
            )

    def test_out_of_range_negative_raises(self):
        """index beyond the negative end must raise IndexError."""
        result = _run_driver(
            """
            arr = np.arange(5 * 4 * 4).reshape(5, 4, 4)
            ds = Dataset()
            ds.NumberOfFrames = 5
            ds.Rows = 4
            ds.Columns = 4
            outcomes = {}
            for idx in (-6, -7, -50):
                try:
                    get_frame(arr, ds, idx)
                    outcomes[str(idx)] = "no-raise"
                except IndexError:
                    outcomes[str(idx)] = "IndexError"
                except Exception as exc:
                    outcomes[str(idx)] = type(exc).__name__
            print("RESULT::" + json.dumps(outcomes))
            """
        )
        for idx in ("-6", "-7", "-50"):
            assert result[idx] == "IndexError", (
                "index=%s must raise IndexError, got %s" % (idx, result[idx])
            )

    # ------------------------------------------------------------------
    # L2 — single-frame handling
    # ------------------------------------------------------------------

    def test_single_frame_index_zero_returns_image(self):
        """Single-frame (NumberOfFrames absent): index 0 returns the whole 2-D image."""
        result = _run_driver(
            """
            arr = np.arange(4 * 4).reshape(4, 4)
            ds = Dataset()
            ds.Rows = 4
            ds.Columns = 4
            # NumberOfFrames intentionally absent -> defaults to 1
            f = get_frame(arr, ds, 0)
            print("RESULT::" + json.dumps({
                "shape": list(f.shape),
                "values": f.tolist(),
                "expected": arr.tolist(),
            }))
            """
        )
        assert result["shape"] == [4, 4], "single-frame result must be (Rows, Columns)"
        assert result["values"] == result["expected"], (
            "single-frame index=0 must return the full image"
        )

    def test_single_frame_index_one_raises(self):
        """Single-frame: only index 0 is valid; index 1 (and -2) must raise IndexError."""
        result = _run_driver(
            """
            arr = np.arange(4 * 4).reshape(4, 4)
            ds = Dataset()
            ds.Rows = 4
            ds.Columns = 4
            outcomes = {}
            for idx in (1, 2, -2):
                try:
                    get_frame(arr, ds, idx)
                    outcomes[str(idx)] = "no-raise"
                except IndexError:
                    outcomes[str(idx)] = "IndexError"
                except Exception as exc:
                    outcomes[str(idx)] = type(exc).__name__
            # index 0 and -1 must both work and return the image
            f0 = get_frame(arr, ds, 0)
            fm1 = get_frame(arr, ds, -1)
            outcomes["zero_ok"] = (f0.tolist() == arr.tolist())
            outcomes["neg1_ok"] = (fm1.tolist() == arr.tolist())
            print("RESULT::" + json.dumps(outcomes))
            """
        )
        assert result["1"] == "IndexError", "single-frame index=1 must raise IndexError"
        assert result["2"] == "IndexError", "single-frame index=2 must raise IndexError"
        assert result["-2"] == "IndexError", "single-frame index=-2 must raise IndexError"
        assert result["zero_ok"] is True, "single-frame index=0 must return the image"
        assert result["neg1_ok"] is True, "single-frame index=-1 must return the image"

    def test_number_of_frames_one_explicit(self):
        """NumberOfFrames == 1 behaves like single-frame even with a (1,R,C) array."""
        result = _run_driver(
            """
            arr = np.arange(1 * 3 * 2).reshape(1, 3, 2)
            ds = Dataset()
            ds.NumberOfFrames = 1
            ds.Rows = 3
            ds.Columns = 2
            f = get_frame(arr, ds, 0)
            raised = None
            try:
                get_frame(arr, ds, 1)
                raised = "no-raise"
            except IndexError:
                raised = "IndexError"
            except Exception as exc:
                raised = type(exc).__name__
            print("RESULT::" + json.dumps({
                "shape": list(f.shape),
                "raised": raised,
            }))
            """
        )
        assert result["shape"] == [3, 2], "NumberOfFrames=1 result must be (Rows, Columns)"
        assert result["raised"] == "IndexError", (
            "NumberOfFrames=1 with index=1 must raise IndexError"
        )

    # ------------------------------------------------------------------
    # L2 — frame count derived from metadata, not arr.shape
    # ------------------------------------------------------------------

    def test_frame_count_from_metadata_not_shape(self):
        """Available-frame count comes from ds.NumberOfFrames, not arr.shape[0].

        arr physically holds 5 frames but NumberOfFrames=3, so indices 3 and 4
        (valid against arr.shape but not against metadata) must raise. A naive
        impl that consults only arr.shape would NOT raise -> it fails here.
        """
        result = _run_driver(
            """
            arr = np.arange(5 * 4 * 4).reshape(5, 4, 4)
            ds = Dataset()
            ds.NumberOfFrames = 3   # metadata says 3 even though arr has 5
            ds.Rows = 4
            ds.Columns = 4
            outcomes = {}
            for idx in (3, 4):
                try:
                    get_frame(arr, ds, idx)
                    outcomes[str(idx)] = "no-raise"
                except IndexError:
                    outcomes[str(idx)] = "IndexError"
                except Exception as exc:
                    outcomes[str(idx)] = type(exc).__name__
            # -1 must map to frame index 2 (last per metadata), not 4
            last = get_frame(arr, ds, -1)
            outcomes["neg1_is_frame2"] = (last.tolist() == arr[2].tolist())
            outcomes["neg1_is_frame4"] = (last.tolist() == arr[4].tolist())
            print("RESULT::" + json.dumps(outcomes))
            """
        )
        assert result["3"] == "IndexError", (
            "index=3 invalid per NumberOfFrames=3 -> must raise (frame count must "
            "derive from metadata, not arr.shape)"
        )
        assert result["4"] == "IndexError", "index=4 must raise per metadata count"
        assert result["neg1_is_frame2"] is True, (
            "with NumberOfFrames=3, index=-1 must be frame 2"
        )
        assert result["neg1_is_frame4"] is False, (
            "index=-1 must NOT map to arr's physical last frame"
        )

    # ------------------------------------------------------------------
    # L2 — returned shape equals (Rows, Columns)
    # ------------------------------------------------------------------

    def test_returned_shape_matches_rows_columns(self):
        """Returned frame shape must equal (ds.Rows, ds.Columns)."""
        result = _run_driver(
            """
            arr = np.arange(4 * 6 * 5).reshape(4, 6, 5)
            ds = Dataset()
            ds.NumberOfFrames = 4
            ds.Rows = 6
            ds.Columns = 5
            f = get_frame(arr, ds, 1)
            print("RESULT::" + json.dumps({"shape": list(f.shape)}))
            """
        )
        assert result["shape"] == [6, 5], (
            "frame shape must equal (Rows, Columns) = (6, 5), got %r" % result["shape"]
        )

    # ------------------------------------------------------------------
    # L2 — result independence (no shared-memory side-effects)
    # ------------------------------------------------------------------

    def test_mutating_result_does_not_alter_arr(self):
        """Mutating the returned frame must not change the original arr."""
        result = _run_driver(
            """
            arr = np.arange(5 * 4 * 4).reshape(5, 4, 4).copy()
            ds = Dataset()
            ds.NumberOfFrames = 5
            ds.Rows = 4
            ds.Columns = 4
            before = arr[2].tolist()
            frame = get_frame(arr, ds, 2)
            frame[:] = -999
            after = arr[2].tolist()
            print("RESULT::" + json.dumps({
                "before": before,
                "after": after,
                "frame_mutated": (frame.tolist() != before),
            }))
            """
        )
        assert result["frame_mutated"] is True, "sanity: the result was actually mutated"
        assert result["before"] == result["after"], (
            "mutating the returned frame must NOT alter arr[2] "
            "(result must be independent of arr's memory)"
        )

    # ------------------------------------------------------------------
    # L2 — native acceptance command
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The agent's own tests/test_util_frames.py must pass via the native command."""
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC_DIR
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_util_frames.py", "-q"],
            cwd=REPO_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "native frames test suite failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "passed" in proc.stdout, f"no tests passed: {proc.stdout}"
