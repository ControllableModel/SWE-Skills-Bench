"""
Test for 'pydicom-dicom-parsing' skill (variant ext7).

Variant task
------------
Implement a Tag and Keyword Resolver at ``src/pydicom/util/tagref.py`` exposing
exactly two public functions:

    resolve(name_or_tag)  -> int   (normalized 32-bit combined group/element tag)
    describe(name_or_tag) -> dict  (tag/group/element/keyword/vr/name)

`name_or_tag` may be a keyword ``str`` (e.g. "PatientName"), a ``(group, element)``
tuple of ints, or an ``int`` tag value. All three input forms for the same element
must resolve to the same ``int``. ``resolve`` raises ``ValueError`` on an unknown
keyword string; ``describe`` raises ``ValueError`` on an unknown keyword string but
tolerates unknown numeric/tuple tags (keyword -> "").

Verification strategy
---------------------
L1 checks the deliverable files exist and the module is importable with exactly
the two specified public functions.

L2 drives the *real* behaviour by writing small self-contained driver scripts under
REPO_DIR and running them with the repo's own Python (PYTHONPATH=<REPO_DIR>/src).
Each driver imports ``resolve``/``describe`` from ``pydicom.util.tagref``, exercises
concrete inputs, and prints one machine-readable ``RESULT::{json}`` line that this
test deep-validates against values read from the real DICOM data dictionary
(PatientName=0x00100010 VR=PN, Modality=0x00080060, PatientID=0x00100020 VR=LO).

A naive implementation that hardcodes a single tag, ignores one input form, breaks
the tag == group<<16|element consistency, fails to raise on an unknown keyword, or
raises on an unknown numeric tag MUST fail these tests. The agent's own native
test suite (tests/test_util_tagref.py) is also run via the doc's acceptance command.
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
TAGREF_PATH = os.path.join(SRC_DIR, "pydicom", "util", "tagref.py")
NATIVE_TEST = os.path.join(REPO_DIR, "tests", "test_util_tagref.py")


def _run_driver(body, timeout=300):
    """Write `body` as a python script under REPO_DIR and run it.

    The script imports resolve/describe from pydicom.util.tagref and must print
    exactly one line ``RESULT::{json}``. Returns the parsed dict.
    """
    header = textwrap.dedent(
        """
        import json
        from pydicom.util.tagref import resolve, describe
        """
    )
    script = header + textwrap.dedent(body)

    tmpdir = tempfile.mkdtemp(prefix="tagref_drv_", dir=REPO_DIR)
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
    """Tag/keyword resolver behavioural tests."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverables exist / importable / correct public API
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/pydicom/util/tagref.py must exist."""
        assert os.path.isfile(TAGREF_PATH), f"missing {TAGREF_PATH}"

    def test_test_file_exists(self):
        """tests/test_util_tagref.py must exist."""
        assert os.path.isfile(NATIVE_TEST), f"missing {NATIVE_TEST}"

    def test_public_api_importable(self):
        """resolve and describe must be importable callables."""
        result = _run_driver(
            """
            out = {
                "resolve_callable": callable(resolve),
                "describe_callable": callable(describe),
            }
            print("RESULT::" + json.dumps(out))
            """
        )
        assert result["resolve_callable"] is True, "resolve must be callable"
        assert result["describe_callable"] is True, "describe must be callable"

    # ------------------------------------------------------------------
    # L2 — resolve: keyword / tuple / int equivalence
    # ------------------------------------------------------------------

    def test_resolve_keyword_returns_int_tag(self):
        """resolve('PatientName') returns the int tag 0x00100010."""
        result = _run_driver(
            """
            t = resolve("PatientName")
            out = {"tag": t, "is_int": isinstance(t, int) and not isinstance(t, bool)}
            print("RESULT::" + json.dumps(out))
            """
        )
        assert result["is_int"] is True, "resolve must return a plain int"
        assert result["tag"] == 0x00100010, "PatientName tag must be 0x00100010"

    def test_resolve_cross_form_equivalence(self):
        """resolve of keyword, tuple, and int forms all yield the same int."""
        result = _run_driver(
            """
            a = resolve("PatientName")
            b = resolve((0x0010, 0x0010))
            c = resolve(0x00100010)
            out = {"a": a, "b": b, "c": c}
            print("RESULT::" + json.dumps(out))
            """
        )
        assert result["a"] == 0x00100010
        assert result["b"] == 0x00100010
        assert result["c"] == 0x00100010
        assert result["a"] == result["b"] == result["c"], (
            "keyword/tuple/int forms must resolve to the same int "
            "(naive form-ignoring impl fails here)"
        )

    def test_resolve_modality_keyword_equals_tuple(self):
        """resolve('Modality') == resolve((0x0008, 0x0060)) == 0x00080060."""
        result = _run_driver(
            """
            kw = resolve("Modality")
            tup = resolve((0x0008, 0x0060))
            iv = resolve(0x00080060)
            out = {"kw": kw, "tup": tup, "iv": iv}
            print("RESULT::" + json.dumps(out))
            """
        )
        assert result["kw"] == 0x00080060
        assert result["tup"] == 0x00080060
        assert result["iv"] == 0x00080060
        assert result["kw"] == result["tup"] == result["iv"]

    def test_resolve_distinct_tags_distinct(self):
        """Different elements must resolve to different ints (no hardcoding)."""
        result = _run_driver(
            """
            out = {
                "name": resolve("PatientName"),
                "pid": resolve("PatientID"),
                "modality": resolve("Modality"),
            }
            print("RESULT::" + json.dumps(out))
            """
        )
        assert result["name"] == 0x00100010
        assert result["pid"] == 0x00100020
        assert result["modality"] == 0x00080060
        # A naive impl that hardcodes one tag would collapse these.
        assert len({result["name"], result["pid"], result["modality"]}) == 3, (
            "distinct keywords must map to distinct tags"
        )

    def test_resolve_unknown_keyword_raises_valueerror(self):
        """resolve on an unknown keyword string raises ValueError."""
        result = _run_driver(
            """
            raised = None
            try:
                resolve("NotAKeyword")
                raised = "none"
            except ValueError:
                raised = "ValueError"
            except Exception as e:
                raised = type(e).__name__
            print("RESULT::" + json.dumps({"raised": raised}))
            """
        )
        assert result["raised"] == "ValueError", (
            "resolve('NotAKeyword') must raise ValueError, got %r" % result["raised"]
        )

    # ------------------------------------------------------------------
    # L2 — describe: full output for a known tag
    # ------------------------------------------------------------------

    def test_describe_known_keyword_full(self):
        """describe('PatientName') returns the complete, correct dict."""
        result = _run_driver(
            """
            d = describe("PatientName")
            print("RESULT::" + json.dumps(d))
            """
        )
        assert result["tag"] == 0x00100010, "tag must be combined int 0x00100010"
        assert result["group"] == 0x0010, "group must be 0x0010"
        assert result["element"] == 0x0010, "element must be 0x0010"
        assert result["keyword"] == "PatientName"
        assert result["vr"] == "PN", "VR must come from the data dictionary (PN)"
        assert result["name"] == "Patient's Name", (
            "name must be the dictionary descriptive name"
        )

    def test_describe_tag_group_element_consistency(self):
        """tag == (group << 16) | element for several described elements."""
        result = _run_driver(
            """
            res = {}
            for kw in ["PatientName", "PatientID", "Modality"]:
                d = describe(kw)
                res[kw] = [d["tag"], d["group"], d["element"]]
            print("RESULT::" + json.dumps(res))
            """
        )
        for kw, (tag, group, element) in result.items():
            assert tag == (group << 16) | element, (
                f"{kw}: tag 0x{tag:08X} != group<<16|element "
                f"(0x{group:04X},0x{element:04X})"
            )
        # Concrete spot checks.
        assert result["Modality"][0] == 0x00080060
        assert result["Modality"][1] == 0x0008
        assert result["Modality"][2] == 0x0060

    def test_describe_from_tuple_matches_keyword(self):
        """describe((0x0010,0x0010)) yields the same dict as describe('PatientName')."""
        result = _run_driver(
            """
            a = describe("PatientName")
            b = describe((0x0010, 0x0010))
            c = describe(0x00100010)
            out = {"a": a, "b": b, "c": c}
            print("RESULT::" + json.dumps(out))
            """
        )
        for key in ("tag", "group", "element", "keyword", "vr", "name"):
            assert result["a"][key] == result["b"][key] == result["c"][key], (
                f"describe disagrees across input forms on {key!r}: "
                f"{result['a'][key]!r} / {result['b'][key]!r} / {result['c'][key]!r}"
            )
        assert result["a"]["keyword"] == "PatientName"
        assert result["a"]["vr"] == "PN"

    # ------------------------------------------------------------------
    # L2 — describe: unknown numeric/tuple tag tolerance
    # ------------------------------------------------------------------

    def test_describe_unknown_tuple_does_not_raise(self):
        """describe on an unknown numeric/tuple tag is tolerated; keyword is ''."""
        result = _run_driver(
            """
            raised = None
            d = None
            try:
                d = describe((0x0011, 0x0011))
                raised = "none"
            except Exception as e:
                raised = type(e).__name__
            out = {"raised": raised, "desc": d}
            print("RESULT::" + json.dumps(out))
            """
        )
        assert result["raised"] == "none", (
            "describe on an unknown numeric tag must NOT raise, got %r"
            % result["raised"]
        )
        d = result["desc"]
        assert d is not None
        assert d["tag"] == 0x00110011, "tag must reflect the input numeric tag"
        assert d["group"] == 0x0011
        assert d["element"] == 0x0011
        assert d["keyword"] == "", "unknown tag keyword must be empty string"
        assert (d["group"] << 16) | d["element"] == d["tag"], "consistency must hold"

    def test_describe_unknown_int_does_not_raise(self):
        """describe(0x00110011) (int form of an unknown tag) is tolerated."""
        result = _run_driver(
            """
            raised = None
            d = None
            try:
                d = describe(0x00110011)
                raised = "none"
            except Exception as e:
                raised = type(e).__name__
            print("RESULT::" + json.dumps({"raised": raised, "desc": d}))
            """
        )
        assert result["raised"] == "none"
        assert result["desc"]["tag"] == 0x00110011
        assert result["desc"]["keyword"] == ""

    def test_describe_unknown_keyword_raises_valueerror(self):
        """describe on an unknown keyword *string* raises ValueError."""
        result = _run_driver(
            """
            raised = None
            try:
                describe("NotAKeyword")
                raised = "none"
            except ValueError:
                raised = "ValueError"
            except Exception as e:
                raised = type(e).__name__
            print("RESULT::" + json.dumps({"raised": raised}))
            """
        )
        assert result["raised"] == "ValueError", (
            "describe('NotAKeyword') must raise ValueError, got %r" % result["raised"]
        )

    # ------------------------------------------------------------------
    # L2 — native acceptance command
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The agent's own tests/test_util_tagref.py must pass via pytest -q."""
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC_DIR
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_util_tagref.py", "-q"],
            cwd=REPO_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "native tagref test suite failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "passed" in proc.stdout, f"no tests passed: {proc.stdout}"
