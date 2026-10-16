"""
Test for 'pydicom-dicom-parsing' skill (variant ext4).

Variant task: implement a DICOM *series slice sorter*.
    src/pydicom/util/series.py  ->  sort_slices(datasets)

`sort_slices` takes an iterable of pydicom Datasets and returns a NEW list of
the same dataset objects ordered by:
  - primary key: third component of ImagePositionPatient (patient z), ascending
    as float;
  - fallback: InstanceNumber, ascending as int, when ImagePositionPatient
    is absent;
  - datasets with neither key go LAST, preserving their original relative
    order;
  - the sort is stable (equal keys keep original order);
  - input is never mutated, object identity is preserved, empty input -> [],
    and a generator input is accepted.

Verification strategy
---------------------
L1 checks the deliverable files exist and that sort_slices is importable with
the exact public signature.

L2 drives the *real* behaviour by writing small, self-contained driver scripts
into a temp dir under REPO_DIR and executing them with the repo's own Python
(PYTHONPATH=<REPO_DIR>/src). Each driver constructs pydicom Datasets, calls the
agent's sort_slices(), and prints machine-readable results that this test
parses and deep-validates against concrete expected orderings.  A naive
implementation (crashes on missing elements, ignores the position/instance
precedence, is unstable, mutates the input, copies the datasets, or mishandles
generators / empty input) fails these tests.  The native acceptance command
(`python -m pytest tests/test_util_series.py -q`) is also driven directly.
"""

import os
import sys
import json
import subprocess
import tempfile
import textwrap


REPO_DIR = "/workspace/pydicom"
SRC_DIR = os.path.join(REPO_DIR, "src")
SERIES_PATH = os.path.join(SRC_DIR, "pydicom", "util", "series.py")
NATIVE_TEST = os.path.join(REPO_DIR, "tests", "test_util_series.py")


def _run_driver(body, timeout=300):
    """Write `body` as a python script under REPO_DIR and run it.

    Returns the parsed JSON dict printed on the last line tagged RESULT::.
    The script must import sort_slices from pydicom.util.series and print
    exactly one line `RESULT::{json}`.
    """
    header = textwrap.dedent(
        """
        import json
        from pydicom.dataset import Dataset
        from pydicom.util.series import sort_slices

        def mk(pos=None, inst=None, tag=None, extra=None):
            d = Dataset()
            if tag is not None:
                d.StudyDescription = str(tag)
            if pos is not None:
                d.ImagePositionPatient = list(pos)
            if inst is not None:
                d.InstanceNumber = int(inst)
            if extra is not None:
                d.Modality = str(extra)
            return d
        """
    )
    script = header + textwrap.dedent(body)

    tmpdir = tempfile.mkdtemp(prefix="series_drv_", dir=REPO_DIR)
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
    """Series slice-sorter behavioural tests."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverables exist / importable / correct signature
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/pydicom/util/series.py must exist."""
        assert os.path.isfile(SERIES_PATH), f"missing {SERIES_PATH}"

    def test_test_file_exists(self):
        """tests/test_util_series.py must exist."""
        assert os.path.isfile(NATIVE_TEST), f"missing {NATIVE_TEST}"

    def test_signature_and_importable(self):
        """sort_slices must be importable with a single positional param."""
        result = _run_driver(
            """
            import inspect
            sig = inspect.signature(sort_slices)
            params = list(sig.parameters.items())
            names = [n for n, _ in params]
            kinds = [str(p.kind) for _, p in params]
            out = {"names": names, "kinds": kinds}
            print("RESULT::" + json.dumps(out))
            """
        )
        assert len(result["names"]) == 1, (
            "sort_slices must take exactly one parameter, got %r" % result["names"]
        )
        # the lone parameter must accept a positional iterable
        assert result["kinds"][0] in (
            "POSITIONAL_OR_KEYWORD",
            "POSITIONAL_ONLY",
        ), "sole parameter must be positionally callable"

    # ------------------------------------------------------------------
    # L2 — position-based ordering (primary key, float compare)
    # ------------------------------------------------------------------

    def test_position_sort_basic(self):
        """Three datasets ordered by z = third ImagePositionPatient component."""
        result = _run_driver(
            """
            a = mk(pos=[0.0, 0.0, 2.0], tag="a")
            b = mk(pos=[0.0, 0.0, 0.0], tag="b")
            c = mk(pos=[0.0, 0.0, 1.0], tag="c")
            out = sort_slices([a, b, c])
            res = {
                "tags": [str(d.StudyDescription) for d in out],
                "zs": [float(d.ImagePositionPatient[2]) for d in out],
                "len": len(out),
                "is_list": isinstance(out, list),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["is_list"] is True, "sort_slices must return a list"
        assert result["len"] == 3
        assert result["zs"] == [0.0, 1.0, 2.0], "must sort ascending by z"
        assert result["tags"] == ["b", "c", "a"]

    def test_position_sort_float_not_lexicographic(self):
        """z must be compared as float, not as string ('10.0' > '9.0')."""
        result = _run_driver(
            """
            a = mk(pos=[0, 0, 10.0], tag="ten")
            b = mk(pos=[0, 0, 9.0], tag="nine")
            c = mk(pos=[0, 0, 100.0], tag="hundred")
            out = sort_slices([a, b, c])
            res = {"tags": [str(d.StudyDescription) for d in out],
                   "zs": [float(d.ImagePositionPatient[2]) for d in out]}
            print("RESULT::" + json.dumps(res))
            """
        )
        # lexicographic ordering of the stringified z would give
        # ['10.0','100.0','9.0']; numeric ordering is the only correct one.
        assert result["zs"] == [9.0, 10.0, 100.0], (
            "z must be compared numerically (float), got %r" % result["zs"]
        )
        assert result["tags"] == ["nine", "ten", "hundred"]

    def test_position_sort_negative_z(self):
        """Negative z-coordinates sort correctly below positives."""
        result = _run_driver(
            """
            out = sort_slices([
                mk(pos=[0, 0, 1.5], tag="p"),
                mk(pos=[0, 0, -3.0], tag="n"),
                mk(pos=[0, 0, 0.0], tag="z"),
            ])
            res = {"tags": [str(d.StudyDescription) for d in out],
                   "zs": [float(d.ImagePositionPatient[2]) for d in out]}
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["zs"] == [-3.0, 0.0, 1.5]
        assert result["tags"] == ["n", "z", "p"]

    # ------------------------------------------------------------------
    # L2 — InstanceNumber fallback
    # ------------------------------------------------------------------

    def test_instance_number_fallback(self):
        """Datasets lacking position order by InstanceNumber ascending (int)."""
        result = _run_driver(
            """
            out = sort_slices([
                mk(inst=3, tag="three"),
                mk(inst=1, tag="one"),
                mk(inst=2, tag="two"),
            ])
            res = {"tags": [str(d.StudyDescription) for d in out],
                   "inst": [int(d.InstanceNumber) for d in out]}
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["inst"] == [1, 2, 3], "must sort by InstanceNumber ascending"
        assert result["tags"] == ["one", "two", "three"]

    def test_instance_number_int_not_lexicographic(self):
        """InstanceNumber must compare as int (10 > 2, not '10' < '2')."""
        result = _run_driver(
            """
            out = sort_slices([
                mk(inst=10, tag="ten"),
                mk(inst=2, tag="two"),
                mk(inst=1, tag="one"),
            ])
            res = {"inst": [int(d.InstanceNumber) for d in out]}
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["inst"] == [1, 2, 10], (
            "InstanceNumber must compare numerically, got %r" % result["inst"]
        )

    # ------------------------------------------------------------------
    # L2 — elementless datasets go last (preserving relative order)
    # ------------------------------------------------------------------

    def test_elementless_placed_last(self):
        """Datasets with neither key are placed after all keyed datasets."""
        result = _run_driver(
            """
            keyed_pos = mk(pos=[0, 0, 5.0], tag="pos")
            keyed_inst = mk(inst=7, tag="inst")
            none1 = mk(tag="none1", extra="CT")
            none2 = mk(tag="none2", extra="MR")
            out = sort_slices([none1, keyed_pos, none2, keyed_inst])
            tags = [str(d.StudyDescription) for d in out]
            # the two elementless datasets must be the final two, in original
            # relative order (none1 before none2).
            res = {
                "tags": tags,
                "tail": tags[-2:],
                "keyed_before_none": (
                    tags.index("pos") < tags.index("none1")
                    and tags.index("inst") < tags.index("none1")
                ),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["tail"] == ["none1", "none2"], (
            "elementless datasets must come last, in original order; got tail %r"
            % result["tail"]
        )
        assert result["keyed_before_none"] is True, (
            "every keyed dataset must precede every elementless one"
        )

    # ------------------------------------------------------------------
    # L2 — stability
    # ------------------------------------------------------------------

    def test_stability_equal_keys(self):
        """Datasets with equal z keep their original relative order."""
        result = _run_driver(
            """
            out = sort_slices([
                mk(pos=[0, 0, 1.0], tag="first"),
                mk(pos=[0, 0, 0.0], tag="low"),
                mk(pos=[0, 0, 1.0], tag="second"),
                mk(pos=[0, 0, 1.0], tag="third"),
            ])
            tags = [str(d.StudyDescription) for d in out]
            res = {"tags": tags}
            print("RESULT::" + json.dumps(res))
            """
        )
        # 'low' (z=0) comes first; the three z=1.0 entries must keep the
        # original first/second/third order.
        assert result["tags"] == ["low", "first", "second", "third"], (
            "sort must be stable for equal keys, got %r" % result["tags"]
        )

    def test_stability_elementless_relative_order(self):
        """Multiple elementless datasets preserve their input relative order."""
        result = _run_driver(
            """
            out = sort_slices([
                mk(tag="x", extra="CT"),
                mk(pos=[0, 0, 0.0], tag="k"),
                mk(tag="y", extra="MR"),
                mk(tag="z", extra="US"),
            ])
            tags = [str(d.StudyDescription) for d in out]
            res = {"tail": tags[-3:], "head": tags[0]}
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["head"] == "k", "keyed dataset must come first"
        assert result["tail"] == ["x", "y", "z"], (
            "elementless datasets must preserve input order, got %r"
            % result["tail"]
        )

    # ------------------------------------------------------------------
    # L2 — position vs instance precedence
    # ------------------------------------------------------------------

    def test_position_precedes_instance_only(self):
        """Position-bearing datasets order among themselves; instance-only too."""
        result = _run_driver(
            """
            out = sort_slices([
                mk(inst=2, tag="i2"),
                mk(pos=[0, 0, 9.0], tag="p9"),
                mk(inst=1, tag="i1"),
                mk(pos=[0, 0, 1.0], tag="p1"),
            ])
            tags = [str(d.StudyDescription) for d in out]
            res = {"tags": tags}
            print("RESULT::" + json.dumps(res))
            """
        )
        tags = result["tags"]
        # position-bearing datasets ordered by z among themselves
        assert tags.index("p1") < tags.index("p9"), "position datasets ordered by z"
        # instance-only datasets ordered by instance number among themselves
        assert tags.index("i1") < tags.index("i2"), (
            "instance-only datasets ordered by InstanceNumber"
        )
        # both position datasets must precede both instance-only datasets
        assert max(tags.index("p1"), tags.index("p9")) < min(
            tags.index("i1"), tags.index("i2")
        ), "position-bearing datasets are ordered before instance-only ones"

    # ------------------------------------------------------------------
    # L2 — identity / non-mutation / empty / generator
    # ------------------------------------------------------------------

    def test_identity_preserved_no_copy(self):
        """Returned list holds the SAME object references, not copies."""
        result = _run_driver(
            """
            a = mk(pos=[0, 0, 2.0], tag="a")
            b = mk(pos=[0, 0, 1.0], tag="b")
            src = [a, b]
            out = sort_slices(src)
            res = {
                "same_objects": out[0] is b and out[1] is a,
                "all_from_src": all(any(o is s for s in src) for o in out),
                "not_same_list": out is not src,
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["same_objects"] is True, "must return same object refs (no copies)"
        assert result["all_from_src"] is True
        assert result["not_same_list"] is True, "must return a NEW list"

    def test_input_not_mutated(self):
        """The input list's ordering and datasets must be unchanged."""
        result = _run_driver(
            """
            a = mk(pos=[0, 0, 2.0], tag="a")
            b = mk(pos=[0, 0, 0.0], tag="b")
            c = mk(pos=[0, 0, 1.0], tag="c")
            src = [a, b, c]
            before = [str(d.StudyDescription) for d in src]
            out = sort_slices(src)
            after = [str(d.StudyDescription) for d in src]
            res = {
                "before": before,
                "after": after,
                "datasets_intact": [float(d.ImagePositionPatient[2]) for d in src],
                "out_order": [str(d.StudyDescription) for d in out],
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["before"] == ["a", "b", "c"]
        assert result["after"] == ["a", "b", "c"], (
            "input list ordering was mutated: %r" % result["after"]
        )
        assert result["datasets_intact"] == [2.0, 0.0, 1.0], "datasets were mutated"
        assert result["out_order"] == ["b", "c", "a"], "sorted output incorrect"

    def test_empty_input_returns_empty_list(self):
        """Passing an empty iterable returns an empty list."""
        result = _run_driver(
            """
            out = sort_slices([])
            res = {"is_list": isinstance(out, list), "len": len(out)}
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["is_list"] is True
        assert result["len"] == 0

    def test_generator_input_accepted(self):
        """A generator input must be consumed and sorted correctly."""
        result = _run_driver(
            """
            def gen():
                yield mk(pos=[0, 0, 3.0], tag="g3")
                yield mk(pos=[0, 0, 1.0], tag="g1")
                yield mk(pos=[0, 0, 2.0], tag="g2")
            out = sort_slices(gen())
            res = {
                "is_list": isinstance(out, list),
                "tags": [str(d.StudyDescription) for d in out],
                "zs": [float(d.ImagePositionPatient[2]) for d in out],
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["is_list"] is True, "generator input must yield a list"
        assert result["zs"] == [1.0, 2.0, 3.0]
        assert result["tags"] == ["g1", "g2", "g3"]

    def test_single_element(self):
        """A single-dataset input returns a one-element list with same object."""
        result = _run_driver(
            """
            a = mk(pos=[0, 0, 5.0], tag="solo")
            out = sort_slices([a])
            res = {"len": len(out), "same": out[0] is a}
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["len"] == 1
        assert result["same"] is True

    # ------------------------------------------------------------------
    # L2 — native test suite must pass
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The agent's own tests/test_util_series.py must pass via pytest."""
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC_DIR
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_util_series.py", "-q"],
            cwd=REPO_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "native series test suite failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "passed" in proc.stdout, f"no tests passed: {proc.stdout}"
