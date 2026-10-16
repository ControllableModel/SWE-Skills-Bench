"""
Test for 'pydicom-dicom-parsing' skill (variant ext5).

Variant task
------------
Implement a *Transfer Syntax Inspector* utility:

    src/pydicom/util/syntax.py  ->  describe_transfer_syntax(ds)

Given a ``pydicom.dataset.Dataset`` that may carry a File Meta Information
``TransferSyntaxUID``, the function returns a ``dict`` describing the
encoding properties of that syntax:

  * when a TransferSyntaxUID is present it returns the keys
    ``uid`` (str), ``name`` (registered human-readable name, str),
    ``is_compressed`` (bool), ``is_little_endian`` (bool),
    ``is_implicit_vr`` (bool);
  * when ``ds`` has no ``file_meta`` OR ``file_meta`` has no
    ``TransferSyntaxUID`` it returns *exactly* ``{"uid": None}``;
  * it must not mutate ``ds`` and must not raise on the absent cases.

Verification strategy
---------------------
L1 confirms the deliverable files exist and the module is importable with
the exact public symbol ``describe_transfer_syntax``.

L2 drives the *real* behaviour by writing small, self-contained driver
scripts under REPO_DIR and executing them with the repo's own Python
(PYTHONPATH=<REPO_DIR>/src). Each driver constructs Datasets with known
TransferSyntaxUIDs, calls the agent's function, and prints a machine
readable JSON line that this test deep-validates against the ground truth
taken from ``pydicom.uid`` (Explicit/Implicit VR Little Endian, Explicit VR
Big Endian, RLE Lossless, Deflated). A naive implementation that hardcodes
``is_compressed=False``, omits ``name`` resolution, returns the raw UID
digits as the name, ignores endianness / VR-encoding, fails on the absent
cases, mutates the input, or returns extra keys for the absent case MUST
fail these tests.

Finally L2 runs the agent's own native pytest target:
    python -m pytest tests/test_util_syntax.py -q
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
SYNTAX_PATH = os.path.join(SRC_DIR, "pydicom", "util", "syntax.py")
NATIVE_TEST = os.path.join(REPO_DIR, "tests", "test_util_syntax.py")


def _run_driver(body, timeout=300):
    """Write ``body`` as a python script under REPO_DIR and run it.

    The script gets a fixed header that imports the agent's
    ``describe_transfer_syntax`` plus the canonical UIDs from pydicom.uid so
    drivers can reference ground-truth constants. Each driver must print
    exactly one line ``RESULT::{json}`` which is parsed and returned.
    """
    header = textwrap.dedent(
        """
        import json, copy
        from pydicom.dataset import Dataset, FileMetaDataset
        from pydicom.uid import (
            ExplicitVRLittleEndian,
            ImplicitVRLittleEndian,
            ExplicitVRBigEndian,
            DeflatedExplicitVRLittleEndian,
            RLELossless,
        )
        from pydicom.util.syntax import describe_transfer_syntax
        """
    )
    script = header + textwrap.dedent(body)

    tmpdir = tempfile.mkdtemp(prefix="syntax_drv_", dir=REPO_DIR)
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
    """Transfer-syntax inspector behavioural tests."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverables exist / importable / correct public symbol
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/pydicom/util/syntax.py must exist."""
        assert os.path.isfile(SYNTAX_PATH), f"missing {SYNTAX_PATH}"

    def test_native_test_file_exists(self):
        """tests/test_util_syntax.py must exist."""
        assert os.path.isfile(NATIVE_TEST), f"missing {NATIVE_TEST}"

    def test_importable_and_signature(self):
        """describe_transfer_syntax must import and accept a single ds arg."""
        result = _run_driver(
            """
            import inspect
            sig = inspect.signature(describe_transfer_syntax)
            params = list(sig.parameters.values())
            # first positional parameter must accept the dataset
            first = params[0] if params else None
            out = {
                "callable": callable(describe_transfer_syntax),
                "first_name": None if first is None else first.name,
                "n_required": sum(
                    1 for p in params
                    if p.default is inspect.Parameter.empty
                    and p.kind in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ),
            }
            print("RESULT::" + json.dumps(out))
            """
        )
        assert result["callable"] is True
        assert result["first_name"] is not None
        assert result["n_required"] == 1, (
            "function must take exactly one required positional argument (ds)"
        )

    # ------------------------------------------------------------------
    # L2 — Explicit VR Little Endian: uncompressed / little-endian / explicit
    # ------------------------------------------------------------------

    def test_explicit_vr_little_endian(self):
        """ExplicitVRLittleEndian => not compressed, little-endian, explicit VR."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.file_meta = FileMetaDataset()
            ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
            r = describe_transfer_syntax(ds)
            print("RESULT::" + json.dumps(r))
            """
        )
        assert result["uid"] == "1.2.840.10008.1.2.1"
        assert result["name"] == "Explicit VR Little Endian"
        assert result["is_compressed"] is False
        assert result["is_little_endian"] is True
        assert result["is_implicit_vr"] is False
        # exactly the five documented keys, no extras / omissions
        assert set(result.keys()) == {
            "uid", "name", "is_compressed", "is_little_endian", "is_implicit_vr"
        }, f"unexpected key set: {sorted(result.keys())}"

    # ------------------------------------------------------------------
    # L2 — Implicit VR Little Endian: implicit VR flag must be True
    # ------------------------------------------------------------------

    def test_implicit_vr_little_endian(self):
        """ImplicitVRLittleEndian => implicit VR True, uncompressed, little-endian."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.file_meta = FileMetaDataset()
            ds.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
            r = describe_transfer_syntax(ds)
            print("RESULT::" + json.dumps(r))
            """
        )
        assert result["uid"] == "1.2.840.10008.1.2"
        assert result["name"] == "Implicit VR Little Endian"
        assert result["is_compressed"] is False
        assert result["is_little_endian"] is True
        assert result["is_implicit_vr"] is True, (
            "Implicit VR Little Endian must report is_implicit_vr=True; "
            "a stub hardcoding False fails here"
        )

    # ------------------------------------------------------------------
    # L2 — RLE Lossless: compressed flag must be True
    # ------------------------------------------------------------------

    def test_rle_lossless_is_compressed(self):
        """RLELossless => is_compressed True (defeats a hardcoded False stub)."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.file_meta = FileMetaDataset()
            ds.file_meta.TransferSyntaxUID = RLELossless
            r = describe_transfer_syntax(ds)
            print("RESULT::" + json.dumps(r))
            """
        )
        assert result["uid"] == "1.2.840.10008.1.2.5"
        assert result["name"] == "RLE Lossless"
        assert result["is_compressed"] is True, (
            "RLE Lossless is an encapsulated syntax -> is_compressed must be True"
        )
        assert result["is_implicit_vr"] is False

    # ------------------------------------------------------------------
    # L2 — Explicit VR Big Endian: endianness must be detected
    # ------------------------------------------------------------------

    def test_explicit_vr_big_endian(self):
        """ExplicitVRBigEndian => is_little_endian False (defeats a hardcoded True)."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.file_meta = FileMetaDataset()
            ds.file_meta.TransferSyntaxUID = ExplicitVRBigEndian
            r = describe_transfer_syntax(ds)
            print("RESULT::" + json.dumps(r))
            """
        )
        assert result["uid"] == "1.2.840.10008.1.2.2"
        assert result["name"] == "Explicit VR Big Endian"
        assert result["is_compressed"] is False
        assert result["is_little_endian"] is False, (
            "Explicit VR Big Endian must report is_little_endian=False"
        )
        assert result["is_implicit_vr"] is False

    # ------------------------------------------------------------------
    # L2 — Deflated Explicit VR Little Endian: uncompressed but deflated
    # ------------------------------------------------------------------

    def test_deflated_explicit_vr_little_endian(self):
        """Deflated Explicit VR LE => not encapsulated/compressed, little-endian."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.file_meta = FileMetaDataset()
            ds.file_meta.TransferSyntaxUID = DeflatedExplicitVRLittleEndian
            r = describe_transfer_syntax(ds)
            print("RESULT::" + json.dumps(r))
            """
        )
        assert result["uid"] == "1.2.840.10008.1.2.1.99"
        assert result["name"] == "Deflated Explicit VR Little Endian"
        # Deflated is NOT an encapsulated/compressed syntax per UID semantics.
        assert result["is_compressed"] is False
        assert result["is_little_endian"] is True
        assert result["is_implicit_vr"] is False

    # ------------------------------------------------------------------
    # L2 — name resolution must be the registered name, not raw digits
    # ------------------------------------------------------------------

    def test_name_is_registered_not_raw_uid(self):
        """'name' must be the human-readable registered name, never the UID digits."""
        result = _run_driver(
            """
            res = {}
            for label, u in [
                ("evrle", ExplicitVRLittleEndian),
                ("ivrle", ImplicitVRLittleEndian),
                ("rle", RLELossless),
            ]:
                ds = Dataset()
                ds.file_meta = FileMetaDataset()
                ds.file_meta.TransferSyntaxUID = u
                r = describe_transfer_syntax(ds)
                res[label] = {"uid": r.get("uid"), "name": r.get("name")}
            print("RESULT::" + json.dumps(res))
            """
        )
        # name must differ from the raw uid string and match the registered text
        assert result["evrle"]["name"] == "Explicit VR Little Endian"
        assert result["evrle"]["name"] != result["evrle"]["uid"]
        assert result["ivrle"]["name"] == "Implicit VR Little Endian"
        assert result["ivrle"]["name"] != result["ivrle"]["uid"]
        assert result["rle"]["name"] == "RLE Lossless"
        assert result["rle"]["name"] != result["rle"]["uid"]
        # name must be a non-empty string with letters (not all digits/dots)
        for label in ("evrle", "ivrle", "rle"):
            nm = result[label]["name"]
            assert isinstance(nm, str) and nm.strip(), f"{label} name empty"
            assert any(ch.isalpha() for ch in nm), f"{label} name looks like raw UID"

    # ------------------------------------------------------------------
    # L2 — uid field is a plain str equal to the canonical digits
    # ------------------------------------------------------------------

    def test_uid_field_is_string(self):
        """'uid' must be a (json) string equal to the canonical UID digits."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.file_meta = FileMetaDataset()
            ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
            r = describe_transfer_syntax(ds)
            out = {
                "uid": r.get("uid"),
                "uid_is_str": isinstance(r.get("uid"), str),
                "name_is_str": isinstance(r.get("name"), str),
                "comp_is_bool": isinstance(r.get("is_compressed"), bool),
                "le_is_bool": isinstance(r.get("is_little_endian"), bool),
                "impl_is_bool": isinstance(r.get("is_implicit_vr"), bool),
            }
            print("RESULT::" + json.dumps(out))
            """
        )
        assert result["uid_is_str"] is True
        assert result["uid"] == "1.2.840.10008.1.2.1"
        assert result["name_is_str"] is True
        assert result["comp_is_bool"] is True
        assert result["le_is_bool"] is True
        assert result["impl_is_bool"] is True

    # ------------------------------------------------------------------
    # L2 — absent file_meta => exactly {"uid": None}
    # ------------------------------------------------------------------

    def test_absent_file_meta_returns_exact_dict(self):
        """No file_meta => returns EXACTLY {'uid': None}, no extra keys, no raise."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"   # ordinary element, but no file_meta
            r = describe_transfer_syntax(ds)
            print("RESULT::" + json.dumps({
                "keys": sorted(r.keys()),
                "uid": r.get("uid", "MISSING"),
                "n": len(r),
            }))
            """
        )
        assert result["n"] == 1, "absent case must return exactly one key"
        assert result["keys"] == ["uid"], (
            f"absent case must be {{'uid': None}} only, got keys {result['keys']}"
        )
        assert result["uid"] is None

    # ------------------------------------------------------------------
    # L2 — file_meta present but no TransferSyntaxUID => {"uid": None}
    # ------------------------------------------------------------------

    def test_file_meta_without_transfer_syntax(self):
        """file_meta present but missing TransferSyntaxUID => exactly {'uid': None}."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.file_meta = FileMetaDataset()
            ds.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.7"
            # deliberately NO TransferSyntaxUID
            r = describe_transfer_syntax(ds)
            print("RESULT::" + json.dumps({
                "keys": sorted(r.keys()),
                "uid": r.get("uid", "MISSING"),
                "n": len(r),
            }))
            """
        )
        assert result["n"] == 1
        assert result["keys"] == ["uid"]
        assert result["uid"] is None

    # ------------------------------------------------------------------
    # L2 — non-mutation contract
    # ------------------------------------------------------------------

    def test_does_not_mutate_dataset(self):
        """describe_transfer_syntax must not mutate ds (present-TS case)."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.PatientName = "Doe^John"
            ds.Modality = "CT"
            ds.file_meta = FileMetaDataset()
            ds.file_meta.TransferSyntaxUID = RLELossless
            before_top = sorted(e.keyword for e in ds)
            before_fm = sorted(e.keyword for e in ds.file_meta)
            before_ts = str(ds.file_meta.TransferSyntaxUID)
            r = describe_transfer_syntax(ds)
            after_top = sorted(e.keyword for e in ds)
            after_fm = sorted(e.keyword for e in ds.file_meta)
            after_ts = str(ds.file_meta.TransferSyntaxUID)
            print("RESULT::" + json.dumps({
                "top_same": before_top == after_top,
                "fm_same": before_fm == after_fm,
                "ts_same": before_ts == after_ts,
                "returned_dict": isinstance(r, dict),
            }))
            """
        )
        assert result["top_same"] is True, "top-level elements changed"
        assert result["fm_same"] is True, "file_meta elements changed"
        assert result["ts_same"] is True, "TransferSyntaxUID value changed"
        assert result["returned_dict"] is True

    def test_does_not_mutate_absent_case(self):
        """Absent-file_meta call must not add a file_meta to ds."""
        result = _run_driver(
            """
            ds = Dataset()
            ds.Modality = "MR"
            had_fm_before = "file_meta" in ds.__dict__ and ds.__dict__["file_meta"] is not None
            r = describe_transfer_syntax(ds)
            # after call, ds should still have no populated file_meta with a TS
            fm = getattr(ds, "file_meta", None)
            ts_added = bool(fm) and ("TransferSyntaxUID" in fm)
            print("RESULT::" + json.dumps({
                "had_fm_before": had_fm_before,
                "ts_added": ts_added,
                "modality": str(ds.Modality),
            }))
            """
        )
        assert result["had_fm_before"] is False
        assert result["ts_added"] is False, "absent case must not inject a TransferSyntaxUID"
        assert result["modality"] == "MR"

    # ------------------------------------------------------------------
    # L2 — cross-syntax differentiation in a single run
    # ------------------------------------------------------------------

    def test_distinguishes_all_syntaxes(self):
        """Booleans differ across syntaxes (defeats any constant-return stub)."""
        result = _run_driver(
            """
            cases = {
                "evrle": ExplicitVRLittleEndian,
                "ivrle": ImplicitVRLittleEndian,
                "evrbe": ExplicitVRBigEndian,
                "rle": RLELossless,
                "deflate": DeflatedExplicitVRLittleEndian,
            }
            out = {}
            for k, u in cases.items():
                ds = Dataset()
                ds.file_meta = FileMetaDataset()
                ds.file_meta.TransferSyntaxUID = u
                r = describe_transfer_syntax(ds)
                out[k] = [
                    r.get("is_compressed"),
                    r.get("is_little_endian"),
                    r.get("is_implicit_vr"),
                ]
            print("RESULT::" + json.dumps(out))
            """
        )
        # ground-truth triples [compressed, little_endian, implicit_vr]
        assert result["evrle"] == [False, True, False]
        assert result["ivrle"] == [False, True, True]
        assert result["evrbe"] == [False, False, False]
        assert result["rle"] == [True, True, False]
        assert result["deflate"] == [False, True, False]
        # ensure the three boolean columns are not all-constant across syntaxes
        comp = {tuple(v)[0] for v in result.values()}
        le = {tuple(v)[1] for v in result.values()}
        impl = {tuple(v)[2] for v in result.values()}
        assert comp == {True, False}, "is_compressed never varies -> hardcoded"
        assert le == {True, False}, "is_little_endian never varies -> hardcoded"
        assert impl == {True, False}, "is_implicit_vr never varies -> hardcoded"

    # ------------------------------------------------------------------
    # L2 — native test suite must pass
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The agent's own tests/test_util_syntax.py must pass via pytest."""
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC_DIR
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_util_syntax.py", "-q"],
            cwd=REPO_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "native syntax test suite failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "passed" in proc.stdout, f"no tests passed: {proc.stdout}"
