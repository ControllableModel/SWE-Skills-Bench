"""
Test for 'pydicom-dicom-parsing' skill.

Verifies the agent's recursive dataset de-identification utility
(src/pydicom/util/deident.py -> deidentify(ds, *, in_place=False)).

Strategy
--------
L1 checks the deliverable files exist and the module is importable with the
exact public signature.

L2 drives the *real* behaviour by writing small, self-contained driver
scripts into a temp dir under REPO_DIR and executing them with the repo's
own Python (PYTHONPATH=<REPO_DIR>/src). Each driver constructs pydicom
Datasets, calls the agent's deidentify(), and prints machine-readable
results that this test parses and deep-validates. A naive implementation
(ignores nested sequences, mutates the input, adds absent elements, or
touches unaffected elements) fails these tests.
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
DEIDENT_PATH = os.path.join(SRC_DIR, "pydicom", "util", "deident.py")
NATIVE_TEST = os.path.join(REPO_DIR, "tests", "test_util_deident.py")


def _run_driver(body, timeout=300):
    """Write `body` as a python script under REPO_DIR and run it.

    Returns the parsed JSON dict printed on the last line tagged RESULT::.
    The script must import deidentify from pydicom.util.deident and print
    exactly one line `RESULT::{json}`.
    """
    header = textwrap.dedent(
        """
        import json, copy
        from pydicom.dataset import Dataset
        from pydicom.sequence import Sequence
        from pydicom.util.deident import deidentify
        """
    )
    script = header + textwrap.dedent(body)

    tmpdir = tempfile.mkdtemp(prefix="deident_drv_", dir=REPO_DIR)
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
    """De-identification utility behavioural tests."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverables exist / importable / correct signature
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/pydicom/util/deident.py must exist."""
        assert os.path.isfile(DEIDENT_PATH), f"missing {DEIDENT_PATH}"

    def test_test_file_exists(self):
        """tests/test_util_deident.py must exist."""
        assert os.path.isfile(NATIVE_TEST), f"missing {NATIVE_TEST}"

    def test_signature_and_importable(self):
        """deidentify must be importable with signature (ds, *, in_place=False)."""
        result = _run_driver(
            """
            import inspect
            sig = inspect.signature(deidentify)
            params = list(sig.parameters.items())
            names = [n for n, _ in params]
            in_place = sig.parameters.get("in_place")
            out = {
                "names": names,
                "in_place_default": None if in_place is None else in_place.default,
                "in_place_kwonly": None if in_place is None
                    else (in_place.kind == inspect.Parameter.KEYWORD_ONLY),
            }
            print("RESULT::" + json.dumps(out))
            """
        )
        assert result["names"][0] == "ds", "first param must be 'ds'"
        assert "in_place" in result["names"], "missing 'in_place' parameter"
        assert result["in_place_default"] is False, "in_place must default to False"
        assert result["in_place_kwonly"] is True, "in_place must be keyword-only"

    # ------------------------------------------------------------------
    # L2 — top level replace / remove policy
    # ------------------------------------------------------------------

    def test_top_level_replace_values(self):
        """PatientName/PatientID/PatientBirthDate replaced with fixed placeholders."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.PatientID = "ID-42"
            ds.PatientBirthDate = "19850102"
            out = deidentify(ds)
            res = {
                "name": str(out.PatientName),
                "pid": str(out.PatientID),
                "bd": str(out.PatientBirthDate),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["name"] == "ANONYMOUS"
        assert result["pid"] == "ANONYMOUS"
        assert result["bd"] == "19000101"

    def test_top_level_remove_elements(self):
        """All 'removed' keywords must be deleted from the result."""
        removed = [
            "PatientAddress",
            "PatientTelephoneNumbers",
            "InstitutionName",
            "InstitutionAddress",
            "ReferringPhysicianName",
            "PerformingPhysicianName",
            "OperatorsName",
        ]
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientAddress = "1 Main St"
            ds.PatientTelephoneNumbers = "555-0100"
            ds.InstitutionName = "General Hospital"
            ds.InstitutionAddress = "5 Hospital Rd"
            ds.ReferringPhysicianName = "Ref^Doc"
            ds.PerformingPhysicianName = "Perf^Doc"
            ds.OperatorsName = "Op^Tech"
            out = deidentify(ds)
            present = {kw: (kw in out) for kw in %r}
            print("RESULT::" + json.dumps(present))
            """
            % removed
        )
        for kw in removed:
            assert result[kw] is False, f"{kw} should have been removed"

    def test_unaffected_elements_unchanged(self):
        """Geometry/UID/modality/pixel data must be untouched."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.Modality = "CT"
            ds.Rows = 4
            ds.Columns = 6
            ds.StudyInstanceUID = "1.2.3.4.5"
            ds.PixelData = b"\\x01\\x02\\x03\\x04"
            out = deidentify(ds)
            res = {
                "modality": str(out.Modality),
                "rows": int(out.Rows),
                "cols": int(out.Columns),
                "uid": str(out.StudyInstanceUID),
                "pixel": list(out.PixelData),
                "has_name": "PatientName" in out,
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["modality"] == "CT"
        assert result["rows"] == 4
        assert result["cols"] == 6
        assert result["uid"] == "1.2.3.4.5"
        assert result["pixel"] == [1, 2, 3, 4]
        assert result["has_name"] is True, "PatientName present -> must be replaced not removed"

    # ------------------------------------------------------------------
    # L2 — absent-element idempotent handling
    # ------------------------------------------------------------------

    def test_absent_replaced_not_added(self):
        """Absent 'replaced' keywords must NOT be added to the dataset."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.Modality = "MR"   # no patient identifiers at all
            out = deidentify(ds)
            res = {
                "name": "PatientName" in out,
                "pid": "PatientID" in out,
                "bd": "PatientBirthDate" in out,
                "modality": str(out.Modality),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["name"] is False, "absent PatientName must not be added"
        assert result["pid"] is False, "absent PatientID must not be added"
        assert result["bd"] is False, "absent PatientBirthDate must not be added"
        assert result["modality"] == "MR"

    def test_partial_presence_only_existing_replaced(self):
        """Only present 'replaced' keywords get placeholders; others stay absent."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientID = "ID-99"   # only one of the three present
            out = deidentify(ds)
            res = {
                "pid": str(out.PatientID),
                "name_present": "PatientName" in out,
                "bd_present": "PatientBirthDate" in out,
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["pid"] == "ANONYMOUS"
        assert result["name_present"] is False
        assert result["bd_present"] is False

    def test_remove_absent_is_noop(self):
        """Removing an absent element must not raise and must leave dataset valid."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.Modality = "US"   # none of the removed keywords present
            out = deidentify(ds)
            res = {"ok": True, "modality": str(out.Modality),
                   "len": len(list(out))}
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["ok"] is True
        assert result["modality"] == "US"
        assert result["len"] == 1, "no spurious elements should be added"

    # ------------------------------------------------------------------
    # L2 — nested sequences at depth
    # ------------------------------------------------------------------

    def test_nested_sequence_replace_and_remove(self):
        """Policy applies inside a one-level nested sequence item."""
        result = _run_driver(
            """
            ds = Dataset()
            item = Dataset()
            item.PatientID = "NESTED"
            item.InstitutionAddress = "deep addr"
            item.Modality = "CT"
            ds.OtherPatientIDsSequence = Sequence([item])
            out = deidentify(ds)
            nested = out.OtherPatientIDsSequence[0]
            res = {
                "pid": str(nested.PatientID),
                "addr_present": "InstitutionAddress" in nested,
                "modality": str(nested.Modality),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["pid"] == "ANONYMOUS", "nested PatientID must be replaced"
        assert result["addr_present"] is False, "nested InstitutionAddress must be removed"
        assert result["modality"] == "CT", "nested unaffected element must be untouched"

    def test_deeply_nested_sequence(self):
        """Policy must apply at arbitrary nesting depth (3 levels deep)."""
        result = _run_driver(
            """
            deep = Dataset()
            deep.PatientName = "Deep^Patient"
            deep.OperatorsName = "Deep^Op"
            deep.Modality = "PT"
            mid = Dataset()
            mid.ReferringPhysicianSequence = Sequence([deep])
            top = Dataset()
            top.PatientName = "Top^Patient"
            top.OtherPatientIDsSequence = Sequence([mid])
            out = deidentify(top)
            d = out.OtherPatientIDsSequence[0].ReferringPhysicianSequence[0]
            res = {
                "top_name": str(out.PatientName),
                "deep_name": str(d.PatientName),
                "deep_op_present": "OperatorsName" in d,
                "deep_modality": str(d.Modality),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["top_name"] == "ANONYMOUS"
        assert result["deep_name"] == "ANONYMOUS", "depth-3 PatientName must be replaced"
        assert result["deep_op_present"] is False, "depth-3 OperatorsName must be removed"
        assert result["deep_modality"] == "PT", "depth-3 unaffected element untouched"

    def test_multiple_items_in_sequence(self):
        """Every item of a multi-item sequence is processed independently."""
        result = _run_driver(
            """
            a = Dataset(); a.PatientID = "A"; a.InstitutionName = "Hosp A"
            b = Dataset(); b.PatientID = "B"; b.Modality = "XA"
            ds = Dataset()
            ds.OtherPatientIDsSequence = Sequence([a, b])
            out = deidentify(ds)
            i0, i1 = out.OtherPatientIDsSequence
            res = {
                "p0": str(i0.PatientID),
                "p1": str(i1.PatientID),
                "inst0": "InstitutionName" in i0,
                "mod1": str(i1.Modality),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["p0"] == "ANONYMOUS"
        assert result["p1"] == "ANONYMOUS"
        assert result["inst0"] is False
        assert result["mod1"] == "XA"

    # ------------------------------------------------------------------
    # L2 — non-mutation / in-place contracts
    # ------------------------------------------------------------------

    def test_non_mutation_top_level(self):
        """in_place=False must not mutate the source dataset."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.PatientID = "ID-42"
            ds.InstitutionName = "General Hospital"
            out = deidentify(ds, in_place=False)
            # mutate the returned object
            out.PatientID = "MUTATED"
            res = {
                "src_name": str(ds.PatientName),
                "src_pid": str(ds.PatientID),
                "src_inst_present": "InstitutionName" in ds,
                "out_is_src": out is ds,
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["src_name"] == "Doe^John", "source PatientName mutated!"
        assert result["src_pid"] == "ID-42", "source PatientID mutated!"
        assert result["src_inst_present"] is True, "source InstitutionName removed!"
        assert result["out_is_src"] is False, "in_place=False must return a new object"

    def test_non_mutation_nested(self):
        """in_place=False must not mutate nested sequence items of the source."""
        result = _run_driver(
            """
            item = Dataset()
            item.PatientID = "NESTED"
            item.InstitutionAddress = "deep addr"
            ds = Dataset()
            ds.OtherPatientIDsSequence = Sequence([item])
            out = deidentify(ds, in_place=False)
            # mutate returned nested item
            out.OtherPatientIDsSequence[0].PatientID = "CHANGED"
            src_item = ds.OtherPatientIDsSequence[0]
            res = {
                "src_pid": str(src_item.PatientID),
                "src_addr_present": "InstitutionAddress" in src_item,
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["src_pid"] == "NESTED", "source nested PatientID mutated!"
        assert result["src_addr_present"] is True, "source nested element removed!"

    def test_in_place_true_mutates_and_returns_same(self):
        """in_place=True must mutate and return the same object."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.InstitutionName = "General Hospital"
            out = deidentify(ds, in_place=True)
            res = {
                "is_same": out is ds,
                "ds_name": str(ds.PatientName),
                "ds_inst_present": "InstitutionName" in ds,
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["is_same"] is True, "in_place=True must return the same object"
        assert result["ds_name"] == "ANONYMOUS", "in_place=True must mutate source"
        assert result["ds_inst_present"] is False, "in_place=True must remove on source"

    # ------------------------------------------------------------------
    # L2 — idempotence
    # ------------------------------------------------------------------

    def test_idempotence(self):
        """Running deidentify twice yields the same result as once."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.PatientID = "ID-42"
            ds.PatientBirthDate = "19850102"
            ds.InstitutionName = "General Hospital"
            item = Dataset()
            item.PatientID = "NESTED"
            item.OperatorsName = "Op^Tech"
            ds.OtherPatientIDsSequence = Sequence([item])
            once = deidentify(ds)
            twice = deidentify(once)
            n = twice.OtherPatientIDsSequence[0]
            res = {
                "name": str(twice.PatientName),
                "pid": str(twice.PatientID),
                "bd": str(twice.PatientBirthDate),
                "inst_present": "InstitutionName" in twice,
                "nested_pid": str(n.PatientID),
                "nested_op_present": "OperatorsName" in n,
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["name"] == "ANONYMOUS"
        assert result["pid"] == "ANONYMOUS"
        assert result["bd"] == "19000101"
        assert result["inst_present"] is False
        assert result["nested_pid"] == "ANONYMOUS"
        assert result["nested_op_present"] is False

    # ------------------------------------------------------------------
    # L2 — native test suite must pass
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The agent's own tests/test_util_deident.py must pass via pytest."""
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC_DIR
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_util_deident.py", "-q"],
            cwd=REPO_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "native deident test suite failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "passed" in proc.stdout, f"no tests passed: {proc.stdout}"
