"""
Test for 'pydicom-dicom-parsing' skill (variant ext9).

Variant task
------------
Implement a *nested sequence flattener* utility at
``src/pydicom/util/flatten.py`` exposing a single public function::

    def flatten(ds) -> dict

It walks a ``pydicom.dataset.Dataset`` and returns a flat ``dict`` mapping a
dotted, item-indexed *path* string to each leaf (non-sequence) element's
``.value``.  Path rules:

  * top-level non-sequence element -> ``"PatientName"``;
  * element inside item ``i`` of sequence ``Seq`` ->
    ``"Seq.<i>.<keyword>"``;
  * nesting continues to arbitrary depth, prefixing each level's keyword +
    item index;
  * sequence containers are NOT themselves keyed (only their leaf
    descendants appear);
  * ``PersonName`` values are stored as ``str``; empty values are kept;
  * empty sequences contribute no keys; ``ds`` is never mutated.

Verification strategy
---------------------
L1 checks the two deliverable files exist and that ``flatten`` is importable
with the exact single-parameter public signature.

L2 drives the *real* behaviour by writing small self-contained driver scripts
under REPO_DIR and executing them with the repo's own Python
(PYTHONPATH=<REPO_DIR>/src). Each driver builds Datasets, calls the agent's
``flatten()`` and prints a machine-readable ``RESULT::{json}`` line which this
test deep-validates against exact expected keys/values.

A naive implementation that only handles top-level elements, omits item
indices, keys the sequence container itself, mutates the input, or drops empty
values MUST fail these tests.

Finally the agent's own native test file is run via the doc's native command
``python -m pytest tests/test_util_flatten.py -q``.
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
FLATTEN_PATH = os.path.join(SRC_DIR, "pydicom", "util", "flatten.py")
NATIVE_TEST = os.path.join(REPO_DIR, "tests", "test_util_flatten.py")


def _run_driver(body, timeout=300):
    """Write `body` as a python script under REPO_DIR and run it.

    Returns the parsed JSON dict printed on the last line tagged RESULT::.
    The script must import flatten from pydicom.util.flatten and print
    exactly one line `RESULT::{json}`.
    """
    header = textwrap.dedent(
        """
        import json
        from pydicom.dataset import Dataset
        from pydicom.sequence import Sequence
        from pydicom.util.flatten import flatten
        """
    )
    script = header + textwrap.dedent(body)

    tmpdir = tempfile.mkdtemp(prefix="flatten_drv_", dir=REPO_DIR)
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
    """Nested-sequence flattener behavioural tests."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverables exist / importable / correct signature
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/pydicom/util/flatten.py must exist."""
        assert os.path.isfile(FLATTEN_PATH), f"missing {FLATTEN_PATH}"

    def test_native_test_file_exists(self):
        """tests/test_util_flatten.py must exist."""
        assert os.path.isfile(NATIVE_TEST), f"missing {NATIVE_TEST}"

    def test_signature_and_importable(self):
        """flatten must be importable and take a single positional param 'ds'."""
        result = _run_driver(
            """
            import inspect
            sig = inspect.signature(flatten)
            params = list(sig.parameters.items())
            names = [n for n, _ in params]
            first_kind = None
            if params:
                first_kind = str(params[0][1].kind)
            out = {"names": names, "first_kind": first_kind,
                   "n_required": sum(
                       1 for _, p in params
                       if p.default is inspect.Parameter.empty
                       and p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                                      inspect.Parameter.POSITIONAL_OR_KEYWORD))}
            print("RESULT::" + json.dumps(out))
            """
        )
        assert result["names"][0] == "ds", "first param must be 'ds'"
        assert result["n_required"] == 1, "flatten must take exactly one required param"

    def test_returns_dict(self):
        """flatten must return a dict instance."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            out = flatten(ds)
            print("RESULT::" + json.dumps({"is_dict": isinstance(out, dict),
                                            "type": type(out).__name__}))
            """
        )
        assert result["is_dict"] is True, f"flatten returned {result['type']}, not dict"

    # ------------------------------------------------------------------
    # L2 — top-level only
    # ------------------------------------------------------------------

    def test_top_level_only(self):
        """A dataset with no sequences flattens to keyword->value with no dots."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.Modality = "CT"
            out = flatten(ds)
            res = {
                "keys": sorted(out.keys()),
                "name": out.get("PatientName"),
                "modality": out.get("Modality"),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["keys"] == ["Modality", "PatientName"], result["keys"]
        assert result["name"] == "Doe^John", "PersonName must be stored as str"
        assert result["modality"] == "CT"

    def test_personname_stringified(self):
        """A PersonName value must be stored as a plain str, not a PersonName object."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Smith^Jane^A"
            out = flatten(ds)
            v = out["PatientName"]
            res = {"value": v, "is_str": isinstance(v, str)}
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["is_str"] is True, "PatientName value must be a str"
        assert result["value"] == "Smith^Jane^A"

    def test_empty_value_included(self):
        """An empty (zero-length) value is still present in the mapping."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.PatientComments = ""   # empty LT value
            out = flatten(ds)
            res = {
                "has_comments": "PatientComments" in out,
                "comments": out.get("PatientComments"),
                "name": out.get("PatientName"),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["has_comments"] is True, "empty-valued element must be included"
        assert result["comments"] == "", "empty value must be preserved"
        assert result["name"] == "Doe^John"

    # ------------------------------------------------------------------
    # L2 — single-level sequence
    # ------------------------------------------------------------------

    def test_single_level_sequence(self):
        """An element inside item 0 of a sequence gets a dotted, indexed key."""
        result = _run_driver(
            """
            item = Dataset()
            item.ReferencedSOPInstanceUID = "1.2.3"
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.ReferencedStudySequence = Sequence([item])
            out = flatten(ds)
            res = {
                "keys": sorted(out.keys()),
                "nested": out.get("ReferencedStudySequence.0.ReferencedSOPInstanceUID"),
                "container_keyed": "ReferencedStudySequence" in out,
                "top_name": out.get("PatientName"),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert (
            result["nested"] == "1.2.3"
        ), "nested element must be keyed 'ReferencedStudySequence.0.ReferencedSOPInstanceUID'"
        assert result["top_name"] == "Doe^John"
        assert (
            result["container_keyed"] is False
        ), "the sequence container itself must NOT be a key"
        assert "ReferencedStudySequence.0.ReferencedSOPInstanceUID" in result["keys"]

    def test_multi_item_sequence_distinct_keys(self):
        """Two items in the same sequence yield distinct keys via their indices."""
        result = _run_driver(
            """
            a = Dataset(); a.ReferencedSOPInstanceUID = "1.1"
            b = Dataset(); b.ReferencedSOPInstanceUID = "2.2"
            ds = Dataset()
            ds.ReferencedStudySequence = Sequence([a, b])
            out = flatten(ds)
            res = {
                "k0": out.get("ReferencedStudySequence.0.ReferencedSOPInstanceUID"),
                "k1": out.get("ReferencedStudySequence.1.ReferencedSOPInstanceUID"),
                "n_keys": len(out),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["k0"] == "1.1", "item 0 must use index .0."
        assert result["k1"] == "2.2", "item 1 must use index .1."
        assert result["n_keys"] == 2, "each item must produce its own distinct key"

    # ------------------------------------------------------------------
    # L2 — multi-level nesting
    # ------------------------------------------------------------------

    def test_two_level_nesting(self):
        """A two-level nested sequence yields a key with two '.<index>.' segments."""
        result = _run_driver(
            """
            inner = Dataset()
            inner.ReferencedSOPInstanceUID = "9.9.9"
            mid = Dataset()
            mid.ReferencedSeriesSequence = Sequence([inner])
            top = Dataset()
            top.ReferencedStudySequence = Sequence([mid])
            out = flatten(top)
            key = "ReferencedStudySequence.0.ReferencedSeriesSequence.0.ReferencedSOPInstanceUID"
            res = {
                "keys": sorted(out.keys()),
                "deep": out.get(key),
                "key": key,
                # count of '.<digit>.' index segments in the deepest key
                "n_index_segments": sum(
                    1 for part in key.split(".") if part.isdigit()
                ),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["deep"] == "9.9.9", f"missing deep key {result['key']}; got {result['keys']}"
        assert result["n_index_segments"] == 2, "key must carry two item-index segments"
        assert result["keys"] == [result["key"]], "no spurious or container keys expected"

    def test_top_and_nested_coexist(self):
        """Top-level and nested leaves coexist; only leaves are keyed."""
        result = _run_driver(
            """
            item = Dataset()
            item.ReferencedSOPInstanceUID = "7.7"
            item.PatientID = "NESTED-ID"
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.Modality = "CT"
            ds.ReferencedStudySequence = Sequence([item])
            out = flatten(ds)
            res = {
                "keys": sorted(out.keys()),
                "name": out.get("PatientName"),
                "modality": out.get("Modality"),
                "nested_uid": out.get("ReferencedStudySequence.0.ReferencedSOPInstanceUID"),
                "nested_id": out.get("ReferencedStudySequence.0.PatientID"),
                "container_keyed": "ReferencedStudySequence" in out,
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["name"] == "Doe^John"
        assert result["modality"] == "CT"
        assert result["nested_uid"] == "7.7"
        assert result["nested_id"] == "NESTED-ID"
        assert result["container_keyed"] is False
        assert result["keys"] == sorted([
            "PatientName",
            "Modality",
            "ReferencedStudySequence.0.ReferencedSOPInstanceUID",
            "ReferencedStudySequence.0.PatientID",
        ])

    # ------------------------------------------------------------------
    # L2 — edge cases & invariants
    # ------------------------------------------------------------------

    def test_empty_sequence_contributes_nothing(self):
        """An empty sequence yields no keys (and no container key)."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.ReferencedStudySequence = Sequence([])
            out = flatten(ds)
            res = {
                "keys": sorted(out.keys()),
                "container_keyed": "ReferencedStudySequence" in out,
                "any_seq_prefixed": any(
                    k.startswith("ReferencedStudySequence") for k in out
                ),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["keys"] == ["PatientName"], "empty sequence must contribute nothing"
        assert result["container_keyed"] is False
        assert result["any_seq_prefixed"] is False

    def test_does_not_mutate_input(self):
        """flatten must not mutate the source dataset (top-level or nested)."""
        result = _run_driver(
            """
            item = Dataset()
            item.ReferencedSOPInstanceUID = "1.2.3"
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.Modality = "CT"
            ds.ReferencedStudySequence = Sequence([item])
            before_top = sorted(e.keyword for e in ds)
            before_nested = sorted(e.keyword for e in ds.ReferencedStudySequence[0])
            out = flatten(ds)
            # mutate the returned dict; source must be unaffected
            out["PatientName"] = "MUTATED"
            after_top = sorted(e.keyword for e in ds)
            after_nested = sorted(e.keyword for e in ds.ReferencedStudySequence[0])
            res = {
                "before_top": before_top,
                "after_top": after_top,
                "before_nested": before_nested,
                "after_nested": after_nested,
                "src_name": str(ds.PatientName),
                "src_n_items": len(ds.ReferencedStudySequence),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["before_top"] == result["after_top"], "source top-level elements changed"
        assert result["before_nested"] == result["after_nested"], "source nested elements changed"
        assert result["src_name"] == "Doe^John", "source PatientName mutated"
        assert result["src_n_items"] == 1, "source sequence item count changed"

    def test_no_sequences_does_not_raise(self):
        """A dataset of only top-level elements must flatten cleanly without raising."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.Rows = 4
            ds.Columns = 6
            ds.StudyInstanceUID = "1.2.3.4.5"
            out = flatten(ds)
            res = {
                "rows": out.get("Rows"),
                "cols": out.get("Columns"),
                "uid": out.get("StudyInstanceUID"),
                "keys": sorted(out.keys()),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["rows"] == 4
        assert result["cols"] == 6
        assert result["uid"] == "1.2.3.4.5"
        assert result["keys"] == ["Columns", "Rows", "StudyInstanceUID"]

    # ------------------------------------------------------------------
    # L2 — native test suite must pass
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The agent's own tests/test_util_flatten.py must pass via pytest."""
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC_DIR
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_util_flatten.py", "-q"],
            cwd=REPO_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "native flatten test suite failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "passed" in proc.stdout, f"no tests passed: {proc.stdout}"
