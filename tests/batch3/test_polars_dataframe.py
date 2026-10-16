"""Tests for the `polars-dataframe` skill task (ext3 variant): a Deferred Log-Query Engine.

Verifies the deliverable `examples/log_query/engine.py` inside the polars
repository (REPO_DIR=/workspace/polars). The three public functions
(`slow_error_endpoints`, `endpoint_latency_stats`, `total_bytes_after`) are
exercised dynamically: a focused driver script is written into REPO_DIR, imports
the agent's module + polars, writes small controlled CSV access logs to a
temporary directory, calls the functions on those CSV paths, and emits JSON that
is deep-validated here.

L1 cases check the deliverable files exist and the public functions are
importable/callable. L2 cases drive real polars behavior over CSVs:
  * slow_error_endpoints: combined status>=500 AND latency>=min filtering,
    per-endpoint counts, (error_count desc, endpoint asc) ordering, empty shape,
    and proof that the `ts`/`bytes` columns never influence the result.
  * endpoint_latency_stats: count/max/mean latency per endpoint, status-agnostic,
    sorted by endpoint ascending.
  * total_bytes_after: strict ts > after_ts sum returning a plain Python int,
    0 when nothing qualifies, and proof other columns are irrelevant.

A naive/hardcoded implementation (ignoring a filter condition, summing all bytes,
letting ts/bytes leak into the error aggregation, or mis-ordering) fails these
cases. The variant's native acceptance command
`python -m pytest examples/log_query/test_engine.py -q` is also driven directly.
"""

import json
import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/polars"
PKG_DIR = os.path.join(REPO_DIR, "examples", "log_query")
ENGINE_PY = os.path.join(PKG_DIR, "engine.py")


# ---------------------------------------------------------------------------
# Driver harness: run a python snippet from REPO_DIR with the agent's module
# importable, capturing a single JSON object printed on the LAST stdout line.
# A scratch temp dir is created for CSVs and removed afterward.
# ---------------------------------------------------------------------------

_PREAMBLE = textwrap.dedent(
    """
    import json, sys, os, tempfile, shutil
    import polars as pl
    sys.path.insert(0, os.path.join(os.getcwd(), "examples"))
    from log_query import engine as E

    _SCRATCH = tempfile.mkdtemp(prefix="logq_")

    def _write_csv(name, header, rows):
        path = os.path.join(_SCRATCH, name)
        with open(path, "w") as fh:
            fh.write(",".join(header) + "\\n")
            for r in rows:
                fh.write(",".join(str(x) for x in r) + "\\n")
        return path

    _HEADER = ["ts", "endpoint", "status", "latency_ms", "bytes"]

    def _df_to_records(df):
        cols = list(df.columns)
        dtypes = [str(df.schema[c]) for c in cols]
        out = []
        for r in df.rows():
            rec = {}
            for c, v in zip(cols, r):
                if isinstance(v, float) and v != v:  # NaN
                    rec[c] = "__NAN__"
                else:
                    rec[c] = v
            out.append(rec)
        return {"columns": cols, "dtypes": dtypes, "rows": out}
    """
)

_EPILOGUE = textwrap.dedent(
    """
    shutil.rmtree(_SCRATCH, ignore_errors=True)
    """
)


def _run_driver(body, timeout=180):
    """Write `body` (which must `print(json.dumps(result))`) and run it.

    Returns the parsed JSON from the last non-empty stdout line.
    """
    script = _PREAMBLE + "\n" + textwrap.dedent(body) + "\n" + _EPILOGUE
    driver_path = os.path.join(REPO_DIR, "_skilltest_driver_ext3.py")
    with open(driver_path, "w") as fh:
        fh.write(script)
    try:
        proc = subprocess.run(
            ["python", "_skilltest_driver_ext3.py"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    finally:
        try:
            os.remove(driver_path)
        except OSError:
            pass
    if proc.returncode != 0:
        raise AssertionError(
            "driver failed (rc=%s)\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.returncode, proc.stdout[-3000:], proc.stderr[-3000:])
        )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, "driver produced no stdout\nSTDERR:\n%s" % proc.stderr[-2000:]
    return json.loads(lines[-1])


class TestPolarsDataframe:
    REPO_DIR = "/workspace/polars"

    # ------------------------------------------------------------------ L1

    def test_package_marker_exists(self):
        """L1: the package marker __init__.py is present."""
        assert os.path.isfile(
            os.path.join(PKG_DIR, "__init__.py")
        ), "examples/log_query/__init__.py missing"

    def test_engine_module_exists(self):
        """L1: engine.py deliverable exists and is non-trivial."""
        assert os.path.isfile(ENGINE_PY), "examples/log_query/engine.py missing"
        assert os.path.getsize(ENGINE_PY) > 200, "engine.py is suspiciously small"

    def test_public_functions_importable(self):
        """L1: the three public functions are importable and callable."""
        result = _run_driver(
            """
            names = ["slow_error_endpoints", "endpoint_latency_stats",
                     "total_bytes_after"]
            out = {n: callable(getattr(E, n, None)) for n in names}
            print(json.dumps(out))
            """
        )
        for name, ok in result.items():
            assert ok, "%s missing or not callable in engine.py" % name

    # -------------------------------------------------- L2 slow_error_endpoints

    def test_slow_error_columns_and_dtypes(self):
        """L2: slow_error_endpoints returns exactly [endpoint, error_count] in order."""
        result = _run_driver(
            """
            path = _write_csv("a.csv", _HEADER, [
                (100, "/a", 500, 300, 10),
                (101, "/a", 500, 250, 20),
                (102, "/b", 502, 500, 30),
            ])
            df = E.slow_error_endpoints(path, 100)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == ["endpoint", "error_count"], (
            "unexpected columns/order: %s" % result["columns"]
        )
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["endpoint"].lower().startswith("str"), (
            "endpoint must be String, got %s" % dtype_map["endpoint"]
        )
        assert dtype_map["error_count"].lower().startswith(("int", "uint")), (
            "error_count must be an integer type, got %s" % dtype_map["error_count"]
        )

    def test_slow_error_combined_status_and_latency_filter(self):
        """L2: only rows with status>=500 AND latency_ms>=min_latency are counted."""
        result = _run_driver(
            """
            path = _write_csv("b.csv", _HEADER, [
                (1, "/a", 500, 300, 10),   # qualifies
                (2, "/a", 200, 900, 20),   # status too low -> excluded
                (3, "/a", 503, 50, 30),    # latency below min -> excluded
                (4, "/b", 500, 100, 40),   # exactly at min -> qualifies (>=)
                (5, "/b", 499, 999, 50),   # status 499 -> excluded
                (6, "/c", 500, 99, 60),    # latency 99 < 100 -> excluded
            ])
            df = E.slow_error_endpoints(path, 100)
            print(json.dumps(_df_to_records(df)))
            """
        )
        counts = {r["endpoint"]: r["error_count"] for r in result["rows"]}
        assert counts.get("/a") == 1, "only the status500/lat300 /a row qualifies"
        assert counts.get("/b") == 1, "the latency==min /b row must count (>=)"
        assert "/c" not in counts, "/c row (latency 99 < 100) must not appear"
        assert set(counts) == {"/a", "/b"}, "unexpected endpoints: %s" % set(counts)

    def test_slow_error_ts_and_bytes_do_not_influence(self):
        """L2: ts/bytes columns must never affect slow_error_endpoints results.

        Two CSVs share identical status/latency/endpoint but differ wildly in
        ts and bytes; the function must produce identical output. A naive impl
        that accidentally filters/aggregates on ts or bytes fails.
        """
        result = _run_driver(
            """
            base = [
                ("/a", 500, 300),
                ("/a", 501, 400),
                ("/b", 500, 200),
            ]
            rows1 = [(ts, ep, st, lat, byt)
                     for ts, byt, (ep, st, lat) in
                     zip([10, 11, 12], [1, 2, 3], base)]
            rows2 = [(ts, ep, st, lat, byt)
                     for ts, byt, (ep, st, lat) in
                     zip([99999, 88888, 77777], [9999, 8888, 7777], base)]
            p1 = _write_csv("v1.csv", _HEADER, rows1)
            p2 = _write_csv("v2.csv", _HEADER, rows2)
            d1 = _df_to_records(E.slow_error_endpoints(p1, 100))
            d2 = _df_to_records(E.slow_error_endpoints(p2, 100))
            print(json.dumps({"d1": d1, "d2": d2}))
            """
        )
        assert result["d1"]["rows"] == result["d2"]["rows"], (
            "ts/bytes changed the result -> they leaked into the aggregation"
        )
        counts = {r["endpoint"]: r["error_count"] for r in result["d1"]["rows"]}
        assert counts == {"/a": 2, "/b": 1}, "unexpected counts: %s" % counts

    def test_slow_error_ordering(self):
        """L2: output sorted by error_count desc, then endpoint asc."""
        result = _run_driver(
            """
            rows = []
            # /z: 3 errors ; /a: 3 errors ; /m: 1 error ; /b: 2 errors
            for ep, n in [("/z", 3), ("/a", 3), ("/m", 1), ("/b", 2)]:
                for i in range(n):
                    rows.append((i, ep, 500, 200, 5))
            path = _write_csv("ord.csv", _HEADER, rows)
            df = E.slow_error_endpoints(path, 100)
            print(json.dumps(_df_to_records(df)))
            """
        )
        ordered = [(r["endpoint"], r["error_count"]) for r in result["rows"]]
        # count desc, then endpoint asc: /a(3),/z(3),/b(2),/m(1)
        assert ordered == [("/a", 3), ("/z", 3), ("/b", 2), ("/m", 1)], (
            "wrong ordering: %s" % ordered
        )

    def test_slow_error_empty_shape(self):
        """L2: when nothing qualifies, return empty DF with the two columns."""
        result = _run_driver(
            """
            path = _write_csv("empty.csv", _HEADER, [
                (1, "/a", 200, 999, 10),   # status too low
                (2, "/b", 500, 1, 20),     # latency below min
            ])
            df = E.slow_error_endpoints(path, 100)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["rows"] == [], "expected no surviving rows"
        assert result["columns"] == ["endpoint", "error_count"], (
            "empty result must still carry [endpoint, error_count]: %s"
            % result["columns"]
        )

    # ------------------------------------------------ L2 endpoint_latency_stats

    def test_latency_stats_columns_and_order(self):
        """L2: endpoint_latency_stats returns the exact 4 columns in order."""
        result = _run_driver(
            """
            path = _write_csv("ls.csv", _HEADER, [
                (1, "/b", 200, 100, 10),
                (2, "/a", 500, 300, 20),
                (3, "/a", 200, 100, 30),
            ])
            df = E.endpoint_latency_stats(path)
            assert isinstance(df, pl.DataFrame)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert result["columns"] == [
            "endpoint",
            "requests",
            "p_max_latency",
            "avg_latency",
        ], "unexpected columns/order: %s" % result["columns"]
        eps = [r["endpoint"] for r in result["rows"]]
        assert eps == sorted(eps), "rows must be sorted by endpoint ascending"
        assert eps == ["/a", "/b"]
        dtype_map = dict(zip(result["columns"], result["dtypes"]))
        assert dtype_map["avg_latency"].lower().startswith("float"), (
            "avg_latency must be Float64, got %s" % dtype_map["avg_latency"]
        )

    def test_latency_stats_values_status_agnostic(self):
        """L2: requests/max/mean computed over ALL rows per endpoint, ignoring status."""
        result = _run_driver(
            """
            path = _write_csv("lsv.csv", _HEADER, [
                (1, "/a", 200, 100, 10),
                (2, "/a", 500, 400, 20),
                (3, "/a", 503, 250, 30),
                (4, "/b", 200, 80, 40),
            ])
            df = E.endpoint_latency_stats(path).sort("endpoint")
            print(json.dumps(_df_to_records(df)))
            """
        )
        by = {r["endpoint"]: r for r in result["rows"]}
        a = by["/a"]
        # /a latencies 100,400,250 regardless of status -> count 3, max 400, mean 250
        assert a["requests"] == 3, "requests must count all rows regardless of status"
        assert a["p_max_latency"] == 400
        assert a["avg_latency"] == pytest.approx((100 + 400 + 250) / 3.0)
        b = by["/b"]
        assert b["requests"] == 1
        assert b["p_max_latency"] == 80
        assert b["avg_latency"] == pytest.approx(80.0)

    def test_latency_stats_single_endpoint_mean(self):
        """L2: a non-integer mean is returned as a float (not truncated)."""
        result = _run_driver(
            """
            path = _write_csv("mean.csv", _HEADER, [
                (1, "/x", 200, 10, 1),
                (2, "/x", 200, 11, 1),
            ])
            df = E.endpoint_latency_stats(path)
            print(json.dumps(_df_to_records(df)))
            """
        )
        assert len(result["rows"]) == 1
        row = result["rows"][0]
        assert row["endpoint"] == "/x"
        assert row["requests"] == 2
        assert row["p_max_latency"] == 11
        assert row["avg_latency"] == pytest.approx(10.5), (
            "mean must be a true float 10.5, got %r (truncation/int-cast bug?)"
            % row["avg_latency"]
        )

    # --------------------------------------------------- L2 total_bytes_after

    def test_total_bytes_after_strict_and_int(self):
        """L2: total_bytes_after sums bytes for ts strictly > after_ts, returns int."""
        result = _run_driver(
            """
            path = _write_csv("tb.csv", _HEADER, [
                (10, "/a", 200, 5, 100),
                (20, "/a", 200, 5, 200),
                (30, "/b", 500, 5, 400),
            ])
            v = E.total_bytes_after(path, 20)   # strictly > 20 -> only ts=30
            out = {"value": v, "type": type(v).__name__}
            print(json.dumps(out))
            """
        )
        assert result["type"] == "int", (
            "must return a plain Python int, got %s" % result["type"]
        )
        assert result["value"] == 400, (
            "strict ts>20 must select only the bytes=400 row, got %s"
            % result["value"]
        )

    def test_total_bytes_after_boundary_excluded(self):
        """L2: a row with ts exactly == after_ts is excluded (strict >)."""
        result = _run_driver(
            """
            path = _write_csv("bd.csv", _HEADER, [
                (50, "/a", 200, 5, 1000),   # ts == after_ts -> excluded
                (51, "/a", 200, 5, 7),      # ts > after_ts -> included
            ])
            v = E.total_bytes_after(path, 50)
            print(json.dumps({"value": v, "type": type(v).__name__}))
            """
        )
        assert result["value"] == 7, (
            "boundary ts==after_ts must be excluded; expected 7, got %s"
            % result["value"]
        )

    def test_total_bytes_after_zero_when_none_qualify(self):
        """L2: returns 0 (int) when no row has ts > after_ts."""
        result = _run_driver(
            """
            path = _write_csv("zero.csv", _HEADER, [
                (1, "/a", 200, 5, 100),
                (2, "/a", 200, 5, 200),
            ])
            v = E.total_bytes_after(path, 999)
            print(json.dumps({"value": v, "type": type(v).__name__}))
            """
        )
        assert result["type"] == "int", "must return a plain Python int"
        assert result["value"] == 0, "no qualifying row must yield 0, got %s" % result["value"]

    def test_total_bytes_after_ignores_other_columns(self):
        """L2: only ts and bytes matter; status/latency/endpoint are irrelevant.

        Same ts/bytes but different status/latency/endpoint must give the same
        sum. A naive impl that filters on status or sums latency fails.
        """
        result = _run_driver(
            """
            rows1 = [(10, "/a", 200, 5, 100), (30, "/b", 200, 5, 300)]
            rows2 = [(10, "/zzz", 599, 9999, 100), (30, "/qqq", 500, 1, 300)]
            p1 = _write_csv("o1.csv", _HEADER, rows1)
            p2 = _write_csv("o2.csv", _HEADER, rows2)
            v1 = E.total_bytes_after(p1, 5)
            v2 = E.total_bytes_after(p2, 5)
            print(json.dumps({"v1": v1, "v2": v2}))
            """
        )
        assert result["v1"] == result["v2"] == 400, (
            "ts/bytes-only sum must equal 400 regardless of other columns: %s"
            % result
        )

    # ----------------------------------------------------- L2 native acceptance

    def test_native_pytest_suite_passes(self):
        """L2: the agent's own pytest suite for the module passes (acceptance command)."""
        proc = subprocess.run(
            ["python", "-m", "pytest", "examples/log_query/test_engine.py", "-q"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=420,
        )
        assert proc.returncode == 0, (
            "native pytest suite failed (rc=%s)\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.returncode, proc.stdout[-3000:], proc.stderr[-2000:])
        )
