"""
Test for 'pydicom-dicom-parsing' skill (variant ext10).

Variant task
------------
Implement a Modality LUT Rescale Applier in
``src/pydicom/util/rescale.py`` exposing exactly::

    def apply_rescale(arr, ds)

``arr`` is a ``numpy.ndarray`` of stored pixel values and ``ds`` is a
``pydicom.dataset.Dataset`` that may carry the DICOM **DS** elements
``RescaleSlope`` (m) and ``RescaleIntercept`` (b). The function returns a new
``numpy.ndarray`` and must NOT mutate ``arr``:

- both present                 -> ``arr * m + b`` as ``numpy.float64``
- only slope present           -> intercept defaults to 0
- only intercept present       -> slope defaults to 1
- neither present              -> values returned unchanged
- DS values parsed numerically (e.g. "1", "-1024", "0.5")
- whenever a rescale is applied the output dtype is ``numpy.float64``

Verification strategy
----------------------
L1 confirms the deliverable files exist and the module imports with the exact
public signature ``apply_rescale(arr, ds)``.

L2 drives the *real* behaviour by writing small self-contained driver scripts
into a temp dir under REPO_DIR and executing them with the repo's own Python
(PYTHONPATH=<REPO_DIR>/src). Each driver builds a numpy array + a pydicom
Dataset, calls the agent's ``apply_rescale``, and prints machine-readable JSON
this test deep-validates (exact numeric outputs, dtype, non-mutation, identity
defaults, fractional slope). A naive implementation that ignores the intercept,
leaves an integer dtype, hardcodes a passthrough, or mutates the input fails.

Finally the agent's own ``tests/test_util_rescale.py`` is executed with the
native acceptance command ``python -m pytest tests/test_util_rescale.py -q``.
"""

import os
import sys
import json
import subprocess
import tempfile
import textwrap


REPO_DIR = "/workspace/pydicom"
SRC_DIR = os.path.join(REPO_DIR, "src")
RESCALE_PATH = os.path.join(SRC_DIR, "pydicom", "util", "rescale.py")
NATIVE_TEST = os.path.join(REPO_DIR, "tests", "test_util_rescale.py")


def _run_driver(body, timeout=300):
    """Write `body` as a python script under REPO_DIR and run it.

    Returns the parsed JSON dict printed on the last line tagged RESULT::.
    The script may assume numpy (np), Dataset and apply_rescale are imported.
    It must print exactly one line ``RESULT::{json}``.
    """
    header = textwrap.dedent(
        """
        import json
        import numpy as np
        from pydicom.dataset import Dataset
        from pydicom.util.rescale import apply_rescale
        """
    )
    script = header + textwrap.dedent(body)

    tmpdir = tempfile.mkdtemp(prefix="rescale_drv_", dir=REPO_DIR)
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
    """Modality LUT rescale applier behavioural tests."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverables exist / importable / correct signature
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/pydicom/util/rescale.py must exist."""
        assert os.path.isfile(RESCALE_PATH), f"missing {RESCALE_PATH}"

    def test_test_file_exists(self):
        """tests/test_util_rescale.py must exist."""
        assert os.path.isfile(NATIVE_TEST), f"missing {NATIVE_TEST}"

    def test_signature_and_importable(self):
        """apply_rescale must import with positional params (arr, ds)."""
        result = _run_driver(
            """
            import inspect
            sig = inspect.signature(apply_rescale)
            params = list(sig.parameters.items())
            names = [n for n, _ in params]
            kinds = [str(p.kind) for _, p in params]
            print("RESULT::" + json.dumps({"names": names, "kinds": kinds}))
            """
        )
        names = result["names"]
        assert len(names) == 2, f"apply_rescale must take 2 params, got {names}"
        assert names[0] == "arr", "first param must be 'arr'"
        assert names[1] == "ds", "second param must be 'ds'"

    # ------------------------------------------------------------------
    # L2 — full slope + intercept linear mapping
    # ------------------------------------------------------------------

    def test_full_slope_and_intercept(self):
        """RescaleSlope='1', RescaleIntercept='-1024' -> arr*1 + -1024."""
        result = _run_driver(
            """
            arr = np.array([[0, 1000, 2000]], dtype=np.int16)
            ds = Dataset()
            ds.RescaleSlope = "1"
            ds.RescaleIntercept = "-1024"
            out = apply_rescale(arr, ds)
            print("RESULT::" + json.dumps({
                "values": out.tolist(),
                "dtype": str(out.dtype),
            }))
            """
        )
        assert result["values"] == [[-1024.0, -24.0, 976.0]]
        assert result["dtype"] == "float64", "rescaled output must be float64"

    def test_fractional_slope(self):
        """A non-unity slope (0.5) must scale values; output float64."""
        result = _run_driver(
            """
            arr = np.array([[10, 20]], dtype=np.int16)
            ds = Dataset()
            ds.RescaleSlope = "0.5"
            out = apply_rescale(arr, ds)
            print("RESULT::" + json.dumps({
                "values": out.tolist(),
                "dtype": str(out.dtype),
            }))
            """
        )
        # slope-only: intercept defaults to 0  -> [10*0.5, 20*0.5]
        assert result["values"] == [[5.0, 10.0]]
        assert result["dtype"] == "float64"

    def test_slope_intercept_combination(self):
        """slope=2.5, intercept=3 applied element-wise as floats."""
        result = _run_driver(
            """
            arr = np.array([0, 2, 4, 6], dtype=np.int16)
            ds = Dataset()
            ds.RescaleSlope = "2.5"
            ds.RescaleIntercept = "3"
            out = apply_rescale(arr, ds)
            print("RESULT::" + json.dumps({
                "values": out.tolist(),
                "dtype": str(out.dtype),
            }))
            """
        )
        assert result["values"] == [3.0, 8.0, 13.0, 18.0]
        assert result["dtype"] == "float64"

    # ------------------------------------------------------------------
    # L2 — identity defaults for a single missing element
    # ------------------------------------------------------------------

    def test_intercept_only_slope_defaults_to_one(self):
        """Only RescaleIntercept present -> slope defaults to 1."""
        result = _run_driver(
            """
            arr = np.array([100, 200, 300], dtype=np.int16)
            ds = Dataset()
            ds.RescaleIntercept = "-50"
            out = apply_rescale(arr, ds)
            print("RESULT::" + json.dumps({
                "values": out.tolist(),
                "dtype": str(out.dtype),
            }))
            """
        )
        # slope default 1: arr*1 + -50
        assert result["values"] == [50.0, 150.0, 250.0]
        assert result["dtype"] == "float64"

    def test_slope_only_intercept_defaults_to_zero(self):
        """Only RescaleSlope present -> intercept defaults to 0."""
        result = _run_driver(
            """
            arr = np.array([4, 8, 12], dtype=np.int16)
            ds = Dataset()
            ds.RescaleSlope = "3"
            out = apply_rescale(arr, ds)
            print("RESULT::" + json.dumps({
                "values": out.tolist(),
                "dtype": str(out.dtype),
            }))
            """
        )
        assert result["values"] == [12.0, 24.0, 36.0]
        assert result["dtype"] == "float64"

    # ------------------------------------------------------------------
    # L2 — no-rescale passthrough (values unchanged)
    # ------------------------------------------------------------------

    def test_no_rescale_passthrough_values(self):
        """Neither element present -> returned values equal input values."""
        result = _run_driver(
            """
            arr = np.array([[5, 9], [13, 17]], dtype=np.int16)
            ds = Dataset()  # no rescale elements at all
            out = apply_rescale(arr, ds)
            print("RESULT::" + json.dumps({
                "values": out.tolist(),
                "input": arr.tolist(),
            }))
            """
        )
        assert result["values"] == result["input"]
        assert result["values"] == [[5, 9], [13, 17]]

    def test_no_rescale_does_not_force_intercept(self):
        """Passthrough must not silently add a -1024 / nonzero offset."""
        result = _run_driver(
            """
            arr = np.array([0, 0, 0], dtype=np.int16)
            ds = Dataset()
            out = apply_rescale(arr, ds)
            print("RESULT::" + json.dumps({"values": out.tolist()}))
            """
        )
        # A stub that hardcodes intercept=-1024 would fail here.
        assert result["values"] == [0, 0, 0]

    # ------------------------------------------------------------------
    # L2 — DS values parsed numerically (not string-concatenated)
    # ------------------------------------------------------------------

    def test_ds_values_parsed_numerically(self):
        """DS strings must be interpreted as numbers, not concatenated text."""
        result = _run_driver(
            """
            arr = np.array([2, 4], dtype=np.int16)
            ds = Dataset()
            ds.RescaleSlope = "0.25"
            ds.RescaleIntercept = "1.5"
            out = apply_rescale(arr, ds)
            print("RESULT::" + json.dumps({
                "values": out.tolist(),
                "dtype": str(out.dtype),
            }))
            """
        )
        # 2*0.25+1.5=2.0 ; 4*0.25+1.5=2.5
        assert result["values"] == [2.0, 2.5]
        assert result["dtype"] == "float64"

    # ------------------------------------------------------------------
    # L2 — non-mutation contract
    # ------------------------------------------------------------------

    def test_input_array_not_mutated(self):
        """apply_rescale must not mutate the input array (rescale case)."""
        result = _run_driver(
            """
            arr = np.array([0, 1000, 2000], dtype=np.int16)
            before = arr.copy()
            ds = Dataset()
            ds.RescaleSlope = "1"
            ds.RescaleIntercept = "-1024"
            out = apply_rescale(arr, ds)
            print("RESULT::" + json.dumps({
                "input_after": arr.tolist(),
                "input_before": before.tolist(),
                "input_dtype": str(arr.dtype),
                "out_is_input": out is arr,
                "out_values": out.tolist(),
            }))
            """
        )
        assert result["input_after"] == result["input_before"], \
            "input array was mutated!"
        assert result["input_after"] == [0, 1000, 2000]
        assert result["input_dtype"] == "int16", "input dtype changed (mutated)!"
        assert result["out_is_input"] is False, "must return a new array"
        assert result["out_values"] == [-1024.0, -24.0, 976.0]

    def test_input_not_mutated_passthrough(self):
        """Passthrough must also leave the input array untouched."""
        result = _run_driver(
            """
            arr = np.array([7, 8, 9], dtype=np.int16)
            before = arr.copy()
            ds = Dataset()
            out = apply_rescale(arr, ds)
            out_changed = out.copy()
            # mutating the returned array must not affect the source
            try:
                out_changed[0] = 999
            except Exception:
                pass
            print("RESULT::" + json.dumps({
                "input_after": arr.tolist(),
                "input_before": before.tolist(),
            }))
            """
        )
        assert result["input_after"] == result["input_before"] == [7, 8, 9]

    # ------------------------------------------------------------------
    # L2 — return type contract
    # ------------------------------------------------------------------

    def test_returns_ndarray(self):
        """Return value must be a numpy.ndarray in every branch."""
        result = _run_driver(
            """
            ds_full = Dataset(); ds_full.RescaleSlope = "1"; ds_full.RescaleIntercept = "-1024"
            ds_none = Dataset()
            a = apply_rescale(np.array([1, 2, 3], dtype=np.int16), ds_full)
            b = apply_rescale(np.array([1, 2, 3], dtype=np.int16), ds_none)
            print("RESULT::" + json.dumps({
                "a_is_ndarray": isinstance(a, np.ndarray),
                "b_is_ndarray": isinstance(b, np.ndarray),
                "a_shape": list(a.shape),
                "b_shape": list(b.shape),
            }))
            """
        )
        assert result["a_is_ndarray"] is True, "rescale branch must return ndarray"
        assert result["b_is_ndarray"] is True, "passthrough branch must return ndarray"
        assert result["a_shape"] == [3]
        assert result["b_shape"] == [3]

    # ------------------------------------------------------------------
    # L2 — native test suite must pass
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The agent's own tests/test_util_rescale.py must pass via pytest."""
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC_DIR
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_util_rescale.py", "-q"],
            cwd=REPO_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "native rescale test suite failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "passed" in proc.stdout, f"no tests passed: {proc.stdout}"
