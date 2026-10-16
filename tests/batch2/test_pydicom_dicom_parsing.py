"""
Test for 'pydicom-dicom-parsing' skill (variant ext2).

Variant task
------------
The agent builds a structured metadata summary extractor at
``src/pydicom/util/summary.py`` exposing::

    def summarize(ds, *, include_missing=False)

which distils a ``pydicom.dataset.Dataset`` into a flat ``dict`` with the
exact keys ``patient_name, patient_id, modality, study_date, rows, columns,
num_elements`` derived from the matching DICOM elements. Missing elements are
omitted (default) or set to ``None`` (``include_missing=True``).
``patient_name`` must be a plain ``str``; ``rows``/``columns``/``num_elements``
must be Python ``int``; ``num_elements`` counts the dataset's own top-level
elements only; the function must not mutate ``ds`` and must never raise on
missing elements.

Verification strategy
---------------------
L1 checks the deliverable files exist and that ``summarize`` is importable
with the exact public signature ``(ds, *, include_missing=False)``.

L2 drives the *real* behaviour by writing small self-contained driver scripts
into a temp dir under REPO_DIR and executing them with the repo's own Python
(``PYTHONPATH=<REPO_DIR>/src``). Each driver builds pydicom Datasets, calls the
agent's ``summarize()``, and prints a machine-readable ``RESULT::{json}`` line
that this test parses and deep-validates. A naive implementation that returns
``PersonName``/non-``int`` types, always includes missing keys, omits
``num_elements``, or mutates the source must fail. The agent's own native test
file is also driven through ``python -m pytest tests/test_util_summary.py -q``.
"""

import os
import sys
import json
import subprocess
import tempfile
import textwrap


REPO_DIR = "/workspace/pydicom"
SRC_DIR = os.path.join(REPO_DIR, "src")
SUMMARY_PATH = os.path.join(SRC_DIR, "pydicom", "util", "summary.py")
NATIVE_TEST = os.path.join(REPO_DIR, "tests", "test_util_summary.py")


def _run_driver(body, timeout=300):
    """Write `body` as a python script under REPO_DIR and run it.

    Returns the parsed JSON dict printed on the last line tagged RESULT::.
    The script may use the pre-imported `summarize`, `Dataset`, `json`.
    """
    header = textwrap.dedent(
        """
        import json, copy
        from pydicom.dataset import Dataset
        from pydicom.util.summary import summarize
        """
    )
    script = header + textwrap.dedent(body)

    tmpdir = tempfile.mkdtemp(prefix="summary_drv_", dir=REPO_DIR)
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
    """Metadata summary extractor behavioural tests."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverables exist / importable / correct signature
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/pydicom/util/summary.py must exist."""
        assert os.path.isfile(SUMMARY_PATH), f"missing {SUMMARY_PATH}"

    def test_test_file_exists(self):
        """tests/test_util_summary.py must exist."""
        assert os.path.isfile(NATIVE_TEST), f"missing {NATIVE_TEST}"

    def test_signature_and_importable(self):
        """summarize must be importable with signature (ds, *, include_missing=False)."""
        result = _run_driver(
            """
            import inspect
            sig = inspect.signature(summarize)
            names = list(sig.parameters.keys())
            inc = sig.parameters.get("include_missing")
            out = {
                "names": names,
                "first": names[0] if names else None,
                "inc_default": None if inc is None else inc.default,
                "inc_kwonly": None if inc is None
                    else (inc.kind == inspect.Parameter.KEYWORD_ONLY),
            }
            print("RESULT::" + json.dumps(out))
            """
        )
        assert result["first"] == "ds", "first param must be 'ds'"
        assert "include_missing" in result["names"], "missing 'include_missing' param"
        assert result["inc_default"] is False, "include_missing must default to False"
        assert result["inc_kwonly"] is True, "include_missing must be keyword-only"

    # ------------------------------------------------------------------
    # L2 — full present dataset: exact keys, values, and types
    # ------------------------------------------------------------------

    def test_full_dataset_keys_and_values(self):
        """A fully-populated dataset yields all keys with correct values."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.PatientID = "ID7"
            ds.Modality = "MR"
            ds.StudyDate = "20200101"
            ds.Rows = 64
            ds.Columns = 32
            out = summarize(ds)
            res = {
                "keys": sorted(out.keys()),
                "patient_name": out.get("patient_name"),
                "patient_id": out.get("patient_id"),
                "modality": out.get("modality"),
                "study_date": out.get("study_date"),
                "rows": out.get("rows"),
                "columns": out.get("columns"),
                "num_elements": out.get("num_elements"),
                "is_dict": isinstance(out, dict),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["is_dict"] is True, "summarize must return a plain dict"
        assert result["keys"] == sorted([
            "patient_name", "patient_id", "modality", "study_date",
            "rows", "columns", "num_elements",
        ]), f"unexpected key set: {result['keys']}"
        assert result["patient_name"] == "Doe^John"
        assert result["patient_id"] == "ID7"
        assert result["modality"] == "MR"
        assert result["study_date"] == "20200101"
        assert result["rows"] == 64
        assert result["columns"] == 32
        assert result["num_elements"] == 6, "six top-level elements were set"

    def test_patient_name_is_plain_str(self):
        """patient_name must be a plain str, not a PersonName subclass."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            out = summarize(ds)
            val = out.get("patient_name")
            res = {
                "type_is_str": type(val) is str,
                "value": str(val),
                "json_ok": True,
            }
            # round-trip JSON to confirm serializability
            json.dumps(out)
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["type_is_str"] is True, (
            "patient_name must be exactly type str (not PersonName)"
        )
        assert result["value"] == "Doe^John"

    def test_numeric_fields_are_python_int(self):
        """rows/columns/num_elements must be exactly type int."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.Rows = 8
            ds.Columns = 12
            ds.Modality = "CT"
            out = summarize(ds)
            res = {
                "rows_is_int": type(out.get("rows")) is int,
                "cols_is_int": type(out.get("columns")) is int,
                "num_is_int": type(out.get("num_elements")) is int,
                "rows": out.get("rows"),
                "cols": out.get("columns"),
                "num": out.get("num_elements"),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["rows_is_int"] is True, "rows must be exactly type int"
        assert result["cols_is_int"] is True, "columns must be exactly type int"
        assert result["num_is_int"] is True, "num_elements must be exactly type int"
        assert result["rows"] == 8
        assert result["cols"] == 12
        assert result["num"] == 3

    # ------------------------------------------------------------------
    # L2 — missing-element handling under both flag values
    # ------------------------------------------------------------------

    def test_missing_omitted_by_default(self):
        """include_missing=False omits keys for absent elements entirely."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.PatientID = "ID7"
            ds.Modality = "MR"
            ds.Rows = 64
            ds.Columns = 64
            # no StudyDate
            out = summarize(ds)
            res = {
                "keys": sorted(out.keys()),
                "has_study_date": "study_date" in out,
                "num_elements": out.get("num_elements"),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["has_study_date"] is False, (
            "study_date must be omitted when absent and include_missing=False"
        )
        assert result["keys"] == sorted([
            "patient_name", "patient_id", "modality",
            "rows", "columns", "num_elements",
        ]), f"unexpected keys: {result['keys']}"
        assert result["num_elements"] == 5

    def test_missing_present_as_none_when_flag_set(self):
        """include_missing=True includes absent keys with value None."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.PatientID = "ID7"
            ds.Modality = "MR"
            ds.Rows = 64
            ds.Columns = 64
            # no StudyDate
            out = summarize(ds, include_missing=True)
            res = {
                "keys": sorted(out.keys()),
                "study_date": out.get("study_date"),
                "study_date_present": "study_date" in out,
                "num_elements": out.get("num_elements"),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["study_date_present"] is True, (
            "study_date key must be present when include_missing=True"
        )
        assert result["study_date"] is None, "absent study_date must map to None"
        assert result["keys"] == sorted([
            "patient_name", "patient_id", "modality", "study_date",
            "rows", "columns", "num_elements",
        ]), f"with include_missing=True all keys must be present: {result['keys']}"

    def test_all_missing_empty_dataset(self):
        """An empty dataset: default omits everything but num_elements=0."""
        result = _run_driver(
            """
            empty = Dataset()
            default = summarize(empty)
            full = summarize(empty, include_missing=True)
            res = {
                "default_keys": sorted(default.keys()),
                "default_num": default.get("num_elements"),
                "full_keys": sorted(full.keys()),
                "full_num": full.get("num_elements"),
                "full_name": full.get("patient_name"),
                "full_rows": full.get("rows"),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        # default: every data-key omitted, but num_elements always present
        assert result["default_keys"] == ["num_elements"], (
            f"empty dataset default keys should be only num_elements: "
            f"{result['default_keys']}"
        )
        assert result["default_num"] == 0, "empty dataset has zero elements"
        # include_missing=True: all keys present, all data fields None
        assert result["full_keys"] == sorted([
            "patient_name", "patient_id", "modality", "study_date",
            "rows", "columns", "num_elements",
        ])
        assert result["full_num"] == 0
        assert result["full_name"] is None, "absent patient_name must be None"
        assert result["full_rows"] is None, "absent rows must be None"

    # ------------------------------------------------------------------
    # L2 — num_elements counting semantics
    # ------------------------------------------------------------------

    def test_num_elements_counts_only_dataset_elements(self):
        """num_elements counts top-level data elements only, not summary keys."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.PatientID = "ID7"
            ds.Modality = "MR"
            # also add an element NOT mapped into the summary
            ds.StudyInstanceUID = "1.2.3.4.5"
            ds.SeriesInstanceUID = "1.2.3.4.6"
            out = summarize(ds)
            res = {
                "num_elements": out.get("num_elements"),
                "summary_key_count": len(out),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        # 5 elements were set on the dataset
        assert result["num_elements"] == 5, (
            "num_elements must count ALL top-level elements (incl. unmapped ones)"
        )
        # summary dict has patient_name, patient_id, modality, num_elements = 4
        assert result["summary_key_count"] == 4, (
            "summary must not include unmapped elements as keys"
        )

    def test_num_elements_independent_of_flag(self):
        """num_elements is identical regardless of include_missing."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.Modality = "CT"
            ds.Rows = 16
            # missing PatientID, StudyDate, Columns
            a = summarize(ds)["num_elements"]
            b = summarize(ds, include_missing=True)["num_elements"]
            res = {"a": a, "b": b}
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["a"] == 3, "three elements were set"
        assert result["b"] == 3
        assert result["a"] == result["b"], (
            "num_elements must not depend on include_missing"
        )

    # ------------------------------------------------------------------
    # L2 — non-mutation and determinism
    # ------------------------------------------------------------------

    def test_does_not_mutate_dataset(self):
        """summarize must not add/remove/change elements of the source dataset."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.PatientID = "ID7"
            ds.Modality = "MR"
            before_len = len(ds)
            before_name = str(ds.PatientName)
            # run with both flag values
            summarize(ds)
            summarize(ds, include_missing=True)
            after_len = len(ds)
            res = {
                "before_len": before_len,
                "after_len": after_len,
                "name_same": str(ds.PatientName) == before_name,
                "no_study_date": "StudyDate" not in ds,
                "no_rows": "Rows" not in ds,
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["before_len"] == 3
        assert result["after_len"] == 3, "summarize must not change element count"
        assert result["name_same"] is True, "PatientName value must be unchanged"
        assert result["no_study_date"] is True, (
            "summarize must not add absent elements to the dataset"
        )
        assert result["no_rows"] is True

    def test_determinism_repeated_calls_equal(self):
        """Calling summarize twice on the same dataset yields equal dicts."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.PatientID = "ID7"
            ds.Modality = "MR"
            ds.Rows = 64
            ds.Columns = 64
            first = summarize(ds)
            second = summarize(ds)
            res = {
                "equal": first == second,
                "first": first,
                "second": second,
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["equal"] is True, (
            "repeated summarize calls must return equal dicts: "
            f"{result['first']} != {result['second']}"
        )

    def test_never_raises_on_partial_dataset(self):
        """summarize must not raise when only some elements are present."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.Modality = "US"   # only one mapped element present
            ok = True
            err = ""
            try:
                a = summarize(ds)
                b = summarize(ds, include_missing=True)
            except Exception as e:
                ok = False
                err = repr(e)
            res = {
                "ok": ok,
                "err": err,
                "default_modality": a.get("modality") if ok else None,
                "default_has_rows": ("rows" in a) if ok else None,
                "full_rows_none": (b.get("rows") is None) if ok else None,
                "num": a.get("num_elements") if ok else None,
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["ok"] is True, f"summarize raised: {result['err']}"
        assert result["default_modality"] == "US"
        assert result["default_has_rows"] is False, (
            "absent rows omitted by default"
        )
        assert result["full_rows_none"] is True
        assert result["num"] == 1

    # ------------------------------------------------------------------
    # L2 — native test suite must pass
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The agent's own tests/test_util_summary.py must pass via pytest."""
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC_DIR
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_util_summary.py", "-q"],
            cwd=REPO_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "native summary test suite failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "passed" in proc.stdout, f"no tests passed: {proc.stdout}"
