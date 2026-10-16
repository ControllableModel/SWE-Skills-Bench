"""
Test for 'pydicom-dicom-parsing' skill (variant ext3).

Variant task
------------
Implement a grayscale windowing normalizer:
    src/pydicom/util/window.py  ->  window_to_uint8(arr, ds)

`arr` is a 2-D numpy array of intensities; `ds` is a pydicom Dataset that
may carry WindowCenter (c) and WindowWidth (w >= 1). The function returns a
NEW numpy.uint8 array of the same shape, never mutating `arr`.

Mapping contract (windowed, when both c and w present):
    v <= c - 0.5 - (w-1)/2          -> 0
    v >  c - 0.5 + (w-1)/2          -> 255
    else round(((v-(c-0.5))/(w-1) + 0.5) * 255), clipped to [0,255]
WindowCenter / WindowWidth may be multi-valued; the FIRST value of each is used.

Fallback (no WindowCenter or no WindowWidth): linear min-max scaling of `arr`
(min -> 0, max -> 255); a constant array yields all zeros.

Verification strategy
---------------------
L1 confirms the deliverable files exist and the module is importable with the
exact public name `window_to_uint8`.

L2 drives the *real* behaviour by writing self-contained driver scripts under
REPO_DIR and running them with the repo's own Python (PYTHONPATH=<REPO_DIR>/src).
Each driver builds numpy arrays + pydicom Datasets, calls the agent's
window_to_uint8(), and prints machine-readable JSON this test deep-validates
against values computed independently here. A naive implementation (ignores the
window elements, returns a non-uint8 array, mutates the input, or skips the
min-max fallback / constant-array case) fails these tests. The final L2 case
runs the agent's own native suite via:
    python -m pytest tests/test_util_window.py -q
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
WINDOW_PATH = os.path.join(SRC_DIR, "pydicom", "util", "window.py")
NATIVE_TEST = os.path.join(REPO_DIR, "tests", "test_util_window.py")


def _run_driver(body, timeout=300):
    """Write `body` as a python script under REPO_DIR and run it.

    Returns the parsed JSON dict printed on the last line tagged RESULT::.
    The script must import window_to_uint8 from pydicom.util.window and print
    exactly one line `RESULT::{json}`.
    """
    header = textwrap.dedent(
        """
        import json
        import numpy as np
        from pydicom.dataset import Dataset
        from pydicom.util.window import window_to_uint8
        """
    )
    script = header + textwrap.dedent(body)

    tmpdir = tempfile.mkdtemp(prefix="window_drv_", dir=REPO_DIR)
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


# --- independent reference implementation (NOT shared with the agent) -------

def _ref_window(v, c, w):
    lo = c - 0.5 - (w - 1) / 2
    hi = c - 0.5 + (w - 1) / 2
    if v <= lo:
        return 0
    if v > hi:
        return 255
    val = round(((v - (c - 0.5)) / (w - 1) + 0.5) * 255)
    return int(min(255, max(0, val)))


def _ref_minmax(values):
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return [0 for _ in values]
    return [int(round((v - lo) / (hi - lo) * 255)) for v in values]


class TestPydicomDicomParsing:
    """Grayscale windowing normalizer behavioural tests."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverables exist / importable
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/pydicom/util/window.py must exist."""
        assert os.path.isfile(WINDOW_PATH), f"missing {WINDOW_PATH}"

    def test_test_file_exists(self):
        """tests/test_util_window.py must exist."""
        assert os.path.isfile(NATIVE_TEST), f"missing {NATIVE_TEST}"

    def test_importable_and_callable(self):
        """window_to_uint8 must import and be a callable accepting (arr, ds)."""
        result = _run_driver(
            """
            import inspect
            sig = inspect.signature(window_to_uint8)
            names = list(sig.parameters.keys())
            out = {"callable": callable(window_to_uint8), "names": names}
            print("RESULT::" + json.dumps(out))
            """
        )
        assert result["callable"] is True
        assert len(result["names"]) >= 2, "must accept (arr, ds)"

    # ------------------------------------------------------------------
    # L2 — dtype / shape invariants
    # ------------------------------------------------------------------

    def test_returns_uint8_and_shape(self):
        """Result dtype is exactly numpy.uint8 and shape matches input."""
        result = _run_driver(
            """
            arr = np.array([[0, 50, 100], [10, 20, 30]], dtype=np.int16)
            ds = Dataset()
            ds.WindowCenter = 50
            ds.WindowWidth = 100
            out = window_to_uint8(arr, ds)
            res = {
                "dtype": str(out.dtype),
                "shape": list(out.shape),
                "max": int(out.max()),
                "min": int(out.min()),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["dtype"] == "uint8", "output dtype must be numpy.uint8"
        assert result["shape"] == [2, 3], "output shape must match input"
        assert 0 <= result["min"] <= result["max"] <= 255

    # ------------------------------------------------------------------
    # L2 — windowed mapping (low / centre / high)
    # ------------------------------------------------------------------

    def test_windowed_mapping_low_centre_high(self):
        """[[0,50,100]] with c=50,w=100 maps to the exact contract values."""
        c, w = 50, 100
        expected = [_ref_window(v, c, w) for v in (0, 50, 100)]
        result = _run_driver(
            """
            arr = np.array([[0, 50, 100]], dtype=np.int32)
            ds = Dataset()
            ds.WindowCenter = 50
            ds.WindowWidth = 100
            out = window_to_uint8(arr, ds)
            print("RESULT::" + json.dumps({"row": [int(x) for x in out[0]]}))
            """
        )
        assert result["row"] == expected, (
            f"windowed mapping wrong: got {result['row']} expected {expected}"
        )
        # guard the exact boundary semantics independently
        assert expected[0] == 0
        assert expected[2] == 255
        assert 120 <= expected[1] <= 135

    def test_windowed_below_and_above_window_clip(self):
        """Values below the window -> 0; strictly above -> 255."""
        c, w = 1000, 200
        lo_v, hi_v = 800, 1500   # 800 <= c-0.5-(w-1)/2 ; 1500 > c-0.5+(w-1)/2
        expected = [_ref_window(lo_v, c, w), _ref_window(hi_v, c, w)]
        result = _run_driver(
            """
            arr = np.array([[800, 1500]], dtype=np.int32)
            ds = Dataset()
            ds.WindowCenter = 1000
            ds.WindowWidth = 200
            out = window_to_uint8(arr, ds)
            print("RESULT::" + json.dumps({"row": [int(x) for x in out[0]]}))
            """
        )
        assert result["row"] == expected
        assert expected == [0, 255], "below->0 / above->255 clipping broken"

    def test_windowed_negative_hounsfield(self):
        """Negative CT Hounsfield inputs map correctly under windowing."""
        c, w = 40, 400
        vals = [-1000, -200, 40, 240, 1000]
        expected = [_ref_window(v, c, w) for v in vals]
        result = _run_driver(
            """
            arr = np.array([[-1000, -200, 40, 240, 1000]], dtype=np.int32)
            ds = Dataset()
            ds.WindowCenter = 40
            ds.WindowWidth = 400
            out = window_to_uint8(arr, ds)
            print("RESULT::" + json.dumps({"row": [int(x) for x in out[0]]}))
            """
        )
        assert result["row"] == expected, (
            f"negative-input mapping wrong: {result['row']} != {expected}"
        )
        # monotone non-decreasing across increasing intensity
        assert result["row"] == sorted(result["row"])

    # ------------------------------------------------------------------
    # L2 — multi-valued window elements
    # ------------------------------------------------------------------

    def test_multivalued_window_uses_first(self):
        """Multi-valued WindowCenter/Width must use the first value of each."""
        c, w = 50, 100   # first values; the trailing junk must be ignored
        expected = [_ref_window(v, c, w) for v in (0, 50, 100)]
        result = _run_driver(
            """
            arr = np.array([[0, 50, 100]], dtype=np.int32)
            ds = Dataset()
            ds.WindowCenter = [50, 9999]
            ds.WindowWidth = [100, 1]
            out = window_to_uint8(arr, ds)
            print("RESULT::" + json.dumps({"row": [int(x) for x in out[0]]}))
            """
        )
        assert result["row"] == expected, (
            "multi-valued window elements must use the first value of each; "
            f"got {result['row']} expected {expected}"
        )

    # ------------------------------------------------------------------
    # L2 — min-max fallback when window elements absent
    # ------------------------------------------------------------------

    def test_minmax_fallback_no_window(self):
        """No window elements -> linear min-max: 100->0, 900->255, mid->128."""
        vals = [100, 500, 900]
        expected = _ref_minmax(vals)
        result = _run_driver(
            """
            arr = np.array([[100, 500, 900]], dtype=np.int32)
            ds = Dataset()  # no WindowCenter / WindowWidth
            out = window_to_uint8(arr, ds)
            print("RESULT::" + json.dumps({"row": [int(x) for x in out[0]]}))
            """
        )
        assert result["row"] == expected, (
            f"min-max fallback wrong: {result['row']} != {expected}"
        )
        assert result["row"][0] == 0 and result["row"][-1] == 255

    def test_minmax_fallback_partial_window_elements(self):
        """Only one of WindowCenter/WindowWidth present -> min-max fallback."""
        vals = [0, 64, 255]
        expected = _ref_minmax(vals)
        result = _run_driver(
            """
            arr = np.array([[0, 64, 255]], dtype=np.int32)
            ds = Dataset()
            ds.WindowCenter = 100   # WindowWidth deliberately absent
            out = window_to_uint8(arr, ds)
            print("RESULT::" + json.dumps({"row": [int(x) for x in out[0]]}))
            """
        )
        assert result["row"] == expected, (
            "missing WindowWidth must trigger min-max fallback, not windowing"
        )

    def test_constant_array_fallback_all_zero(self):
        """Constant array with no window elements -> all-zero result."""
        result = _run_driver(
            """
            arr = np.full((2, 3), 700, dtype=np.int32)
            ds = Dataset()
            out = window_to_uint8(arr, ds)
            res = {
                "dtype": str(out.dtype),
                "shape": list(out.shape),
                "all_zero": bool((out == 0).all()),
                "sum": int(out.sum()),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["dtype"] == "uint8"
        assert result["shape"] == [2, 3]
        assert result["all_zero"] is True, "constant array must map to all zeros"
        assert result["sum"] == 0

    # ------------------------------------------------------------------
    # L2 — non-mutation contract
    # ------------------------------------------------------------------

    def test_input_not_mutated(self):
        """The input array must be unchanged and a new object returned."""
        result = _run_driver(
            """
            arr = np.array([[0, 50, 100]], dtype=np.int32)
            before = arr.copy()
            ds = Dataset()
            ds.WindowCenter = 50
            ds.WindowWidth = 100
            out = window_to_uint8(arr, ds)
            res = {
                "unchanged": bool((arr == before).all()),
                "dtype_in": str(arr.dtype),
                "is_same_obj": out is arr,
                "shares_mem": bool(np.shares_memory(out, arr)),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["unchanged"] is True, "input array was mutated"
        assert result["dtype_in"] == "int32", "input dtype changed in place"
        assert result["is_same_obj"] is False, "must return a new array"
        assert result["shares_mem"] is False, "output must not alias input memory"

    def test_minmax_input_not_mutated(self):
        """Min-max fallback path also leaves the input untouched."""
        result = _run_driver(
            """
            arr = np.array([[100, 500, 900]], dtype=np.int32)
            before = arr.copy()
            ds = Dataset()
            out = window_to_uint8(arr, ds)
            res = {"unchanged": bool((arr == before).all()),
                   "out_dtype": str(out.dtype)}
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["unchanged"] is True, "input mutated on fallback path"
        assert result["out_dtype"] == "uint8"

    # ------------------------------------------------------------------
    # L2 — native test suite must pass
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The agent's own tests/test_util_window.py must pass via pytest."""
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC_DIR
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_util_window.py", "-q"],
            cwd=REPO_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "native window test suite failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "passed" in proc.stdout, f"no tests passed: {proc.stdout}"
