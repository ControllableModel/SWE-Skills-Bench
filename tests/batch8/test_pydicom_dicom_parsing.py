"""
Test for 'pydicom-dicom-parsing' skill (variant ext8).

Variant task
------------
Implement DICOM date/time normalizers in a new self-contained module
``src/pydicom/util/datetimefmt.py`` exposing exactly four functions:

    parse_da(value)   # DICOM DA "YYYYMMDD" -> datetime.date  (None/"" -> None)
    parse_tm(value)   # DICOM TM            -> datetime.time  (None/"" -> None)
    format_da(d)      # datetime.date       -> "YYYYMMDD"
    format_tm(t)      # datetime.time       -> "HHMMSS" or "HHMMSS.FFFFFF"

The agent also writes ``tests/test_util_datetimefmt.py`` (>=10 cases).

Verification strategy
---------------------
L1 confirms the deliverable files exist and the module is importable with the
exact public function names.

L2 drives the *real* behaviour by writing small, self-contained driver scripts
into a temp dir under REPO_DIR and executing them with the repo's own Python
(PYTHONPATH=<REPO_DIR>/src). Each driver imports the agent's module, exercises
parse/format on concrete inputs (full / partial / fractional TM forms,
DA round-trips, microsecond scaling, None/"" handling, malformed-date
ValueError) and prints a machine-readable RESULT line that this test parses and
deep-validates against exact expected values.

A naive implementation -- one that ignores partial/fractional TM forms,
hardcodes outputs, skips microsecond scaling, or does not raise on malformed
dates -- fails these tests. Finally the agent's own native test suite is driven
exactly as the doc's acceptance command requires:

    python -m pytest tests/test_util_datetimefmt.py -q
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
MODULE_PATH = os.path.join(SRC_DIR, "pydicom", "util", "datetimefmt.py")
NATIVE_TEST = os.path.join(REPO_DIR, "tests", "test_util_datetimefmt.py")


def _run_driver(body, timeout=300):
    """Write `body` as a python script under REPO_DIR and run it.

    Returns the parsed JSON dict printed on the last line tagged RESULT::.
    The script body may import the agent's module via:
        from pydicom.util.datetimefmt import parse_da, parse_tm, format_da, format_tm
    and must print exactly one line ``RESULT::{json}``.
    """
    header = textwrap.dedent(
        """
        import json
        import datetime
        from datetime import date, time
        from pydicom.util.datetimefmt import (
            parse_da, parse_tm, format_da, format_tm,
        )
        """
    )
    script = header + textwrap.dedent(body)

    tmpdir = tempfile.mkdtemp(prefix="dtfmt_drv_", dir=REPO_DIR)
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
    """DICOM date/time normalizer behavioural tests."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 -- deliverables exist / importable / correct public API
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """src/pydicom/util/datetimefmt.py must exist."""
        assert os.path.isfile(MODULE_PATH), f"missing {MODULE_PATH}"

    def test_native_test_file_exists(self):
        """tests/test_util_datetimefmt.py must exist."""
        assert os.path.isfile(NATIVE_TEST), f"missing {NATIVE_TEST}"

    def test_public_api_present_and_callable(self):
        """All four functions must be importable and callable."""
        result = _run_driver(
            """
            names = {}
            for n, fn in [
                ("parse_da", parse_da), ("parse_tm", parse_tm),
                ("format_da", format_da), ("format_tm", format_tm),
            ]:
                names[n] = callable(fn)
            print("RESULT::" + json.dumps(names))
            """
        )
        for n in ("parse_da", "parse_tm", "format_da", "format_tm"):
            assert result.get(n) is True, f"{n} missing or not callable"

    # ------------------------------------------------------------------
    # L2 -- DA parsing / formatting
    # ------------------------------------------------------------------

    def test_parse_da_basic(self):
        """parse_da('20230115') must return date(2023, 1, 15)."""
        result = _run_driver(
            """
            d = parse_da("20230115")
            res = {
                "type": type(d).__name__,
                "y": d.year, "m": d.month, "dd": d.day,
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["type"] == "date"
        assert (result["y"], result["m"], result["dd"]) == (2023, 1, 15)

    def test_format_da_basic(self):
        """format_da(date(2023,1,15)) must return '20230115' (zero-padded)."""
        result = _run_driver(
            """
            res = {
                "a": format_da(date(2023, 1, 15)),
                "b": format_da(date(2007, 3, 9)),   # zero-pad month+day
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["a"] == "20230115"
        assert result["b"] == "20070309", "format_da must zero-pad to YYYYMMDD"

    def test_da_round_trip(self):
        """parse_da(format_da(d)) == d for several dates."""
        result = _run_driver(
            """
            samples = [date(2023, 1, 15), date(1999, 12, 31),
                       date(2000, 2, 29), date(2024, 7, 4)]
            ok = all(parse_da(format_da(d)) == d for d in samples)
            print("RESULT::" + json.dumps({"ok": ok}))
            """
        )
        assert result["ok"] is True, "DA round-trip failed"

    def test_parse_da_malformed_raises(self):
        """Malformed DA strings must raise ValueError, not return junk."""
        result = _run_driver(
            """
            cases = {
                "dashed": "2023-01-15",
                "short": "202301",
                "alpha": "abcdefgh",
                "month13": "20231301",
            }
            res = {}
            for k, v in cases.items():
                try:
                    parse_da(v)
                    res[k] = "no-raise"
                except ValueError:
                    res[k] = "ValueError"
                except Exception as e:
                    res[k] = type(e).__name__
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["dashed"] == "ValueError", "'2023-01-15' must raise ValueError"
        assert result["short"] == "ValueError", "wrong-length DA must raise ValueError"
        assert result["alpha"] == "ValueError", "non-numeric DA must raise ValueError"
        assert result["month13"] == "ValueError", "invalid calendar date must raise ValueError"

    # ------------------------------------------------------------------
    # L2 -- TM parsing: full / partial / fractional forms
    # ------------------------------------------------------------------

    def test_parse_tm_fractional_full(self):
        """parse_tm('131005.500000') -> time(13,10,5,500000)."""
        result = _run_driver(
            """
            t = parse_tm("131005.500000")
            res = {
                "type": type(t).__name__,
                "h": t.hour, "m": t.minute, "s": t.second, "us": t.microsecond,
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["type"] == "time"
        assert (result["h"], result["m"], result["s"], result["us"]) == (13, 10, 5, 500000)

    def test_parse_tm_partial_forms(self):
        """parse_tm must accept HHMMSS, HHMM, and HH partial forms."""
        result = _run_driver(
            """
            t_hms = parse_tm("131005")
            t_hm = parse_tm("1310")
            t_h = parse_tm("13")
            res = {
                "hms": [t_hms.hour, t_hms.minute, t_hms.second, t_hms.microsecond],
                "hm": [t_hm.hour, t_hm.minute, t_hm.second, t_hm.microsecond],
                "h": [t_h.hour, t_h.minute, t_h.second, t_h.microsecond],
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["hms"] == [13, 10, 5, 0], "HHMMSS form misparsed"
        assert result["hm"] == [13, 10, 0, 0], "HHMM partial form misparsed"
        assert result["h"] == [13, 0, 0, 0], "HH partial form misparsed"

    def test_parse_tm_fraction_scaling(self):
        """'.5'-style fractions scale to 6-digit microseconds: '131005.5' -> 500000."""
        result = _run_driver(
            """
            cases = {
                "half": parse_tm("131005.5").microsecond,        # -> 500000
                "quarter": parse_tm("090000.25").microsecond,    # -> 250000
                "milli": parse_tm("000000.001").microsecond,     # -> 1000
                "tenth": parse_tm("120000.1").microsecond,       # -> 100000
            }
            print("RESULT::" + json.dumps(cases))
            """
        )
        assert result["half"] == 500000, "'.5' fraction must scale to 500000 us"
        assert result["quarter"] == 250000, "'.25' fraction must scale to 250000 us"
        assert result["milli"] == 1000, "'.001' fraction must scale to 1000 us"
        assert result["tenth"] == 100000, "'.1' fraction must scale to 100000 us"

    # ------------------------------------------------------------------
    # L2 -- TM formatting with / without microseconds
    # ------------------------------------------------------------------

    def test_format_tm_with_and_without_micros(self):
        """format_tm emits HHMMSS without micros, HHMMSS.FFFFFF with micros."""
        result = _run_driver(
            """
            res = {
                "plain": format_tm(time(9, 0, 0)),
                "padded": format_tm(time(1, 2, 3)),
                "frac": format_tm(time(9, 0, 0, 250000)),
                "frac2": format_tm(time(13, 10, 5, 500000)),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["plain"] == "090000", "zero-micros time must emit HHMMSS"
        assert result["padded"] == "010203", "format_tm must zero-pad HHMMSS"
        assert result["frac"] == "090000.250000", "nonzero micros must emit 6-digit fraction"
        assert result["frac2"] == "131005.500000"

    def test_tm_round_trip(self):
        """parse_tm(format_tm(t)) == t for DICOM-expressible times."""
        result = _run_driver(
            """
            samples = [
                time(13, 10, 5, 500000),
                time(9, 0, 0),
                time(0, 0, 0, 1000),
                time(23, 59, 59, 999999),
                time(1, 2, 3, 250000),
            ]
            pairs = []
            for t in samples:
                back = parse_tm(format_tm(t))
                pairs.append([
                    [t.hour, t.minute, t.second, t.microsecond],
                    [back.hour, back.minute, back.second, back.microsecond],
                ])
            ok = all(a == b for a, b in pairs)
            print("RESULT::" + json.dumps({"ok": ok, "pairs": pairs}))
            """
        )
        assert result["ok"] is True, f"TM round-trip failed: {result['pairs']}"

    # ------------------------------------------------------------------
    # L2 -- None / empty handling (parsers return None, no exception)
    # ------------------------------------------------------------------

    def test_none_and_empty_inputs_return_none(self):
        """None/'' inputs to parse_da/parse_tm return None (no exception)."""
        result = _run_driver(
            """
            res = {
                "da_none": parse_da(None),
                "da_empty": parse_da(""),
                "tm_none": parse_tm(None),
                "tm_empty": parse_tm(""),
            }
            print("RESULT::" + json.dumps(res))
            """
        )
        assert result["da_none"] is None, "parse_da(None) must be None"
        assert result["da_empty"] is None, "parse_da('') must be None"
        assert result["tm_none"] is None, "parse_tm(None) must be None"
        assert result["tm_empty"] is None, "parse_tm('') must be None"

    # ------------------------------------------------------------------
    # L2 -- native acceptance command must pass
    # ------------------------------------------------------------------

    def test_native_pytest_suite_passes(self):
        """The agent's own tests/test_util_datetimefmt.py must pass via pytest.

        Drives exactly the doc's native acceptance command:
            python -m pytest tests/test_util_datetimefmt.py -q
        """
        env = dict(os.environ)
        env["PYTHONPATH"] = SRC_DIR
        proc = subprocess.run(
            [sys.executable, "-m", "pytest",
             "tests/test_util_datetimefmt.py", "-q"],
            cwd=REPO_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "native datetimefmt test suite failed:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr)
        )
        assert "passed" in proc.stdout, f"no tests passed: {proc.stdout}"
