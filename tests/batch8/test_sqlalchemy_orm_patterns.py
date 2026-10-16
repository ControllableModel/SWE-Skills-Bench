"""Benchmark test for skill: sqlalchemy-orm-patterns (variant ext8).

Task under test
---------------
Add a `QueryResult.counts_by_data_source(org)` classmethod to redash's ORM model
(`redash/models/__init__.py`). It must return an iterable of two-element rows
`(data_source_id, result_count)`:

  * only `QueryResult` rows belonging to the given ``org`` are counted;
  * rows are grouped by ``data_source_id``;
  * a data source with zero stored results does NOT appear;
  * rows are ordered by ascending ``data_source_id`` (deterministic);
  * the method is read-only and takes exactly one argument beyond ``cls``.

Verification strategy
---------------------
L1 checks confirm the deliverable model file exists, the classmethod is defined
on the `QueryResult` class with the exact signature ``(cls, org)`` (via AST, not
substring grep), and the modified module imports cleanly.

L2 checks DYNAMICALLY EXERCISE the real behavior. Rather than trusting any test
the agent may have written, we drop our OWN focused pytest driver modules into
the repo's `tests/models/` directory (so they pick up the real DB-backed
`BaseTestCase` + `Factory`), seed `QueryResult`/`DataSource` rows directly via
the ORM, call `QueryResult.counts_by_data_source(org)`, and assert on the exact
returned rows. Each driver is run with the repo's native `pytest` and we assert
on returncode + collected behavior.

A naive solution fails these tests: e.g. one that hardcodes a list, returns all
data sources regardless of stored results, ignores the ``org`` filter (leaking
cross-org rows), counts queries instead of query_results, fails to group, or
returns rows in a non-deterministic / wrong order.
"""

import ast
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/redash"
MODELS_FILE = os.path.join(REPO_DIR, "redash", "models", "__init__.py")
MODELS_TESTS_DIR = os.path.join(REPO_DIR, "tests", "models")
TARGET_TEST_FILE = os.path.join(MODELS_TESTS_DIR, "test_query_results.py")

# Files we inject into the repo so we can clean them up afterwards.
_INJECTED = []


def _write_driver(name, body):
    """Write a pytest driver module into tests/models/ and remember it."""
    path = os.path.join(MODELS_TESTS_DIR, name)
    with open(path, "w") as fh:
        fh.write(body)
    _INJECTED.append(path)
    return path


def _run_pytest(target, extra=None, timeout=600):
    """Run the repo's native pytest against `target` (path relative to REPO_DIR)."""
    cmd = ["python", "-m", "pytest", target, "-v", "--tb=short", "-p", "no:cacheprovider"]
    if extra:
        cmd.extend(extra)
    env = dict(os.environ)
    # Ensure the repo itself is importable regardless of how we were invoked.
    env["PYTHONPATH"] = REPO_DIR
    return subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


@pytest.fixture(scope="module", autouse=True)
def _cleanup_injected():
    """Remove any driver modules we injected once the module's tests finish."""
    yield
    for path in _INJECTED:
        try:
            os.remove(path)
        except OSError:
            pass
    # Drop any __pycache__ entries we may have created.
    pycache = os.path.join(MODELS_TESTS_DIR, "__pycache__")
    if os.path.isdir(pycache):
        for f in os.listdir(pycache):
            if "cbds_driver" in f:
                try:
                    os.remove(os.path.join(pycache, f))
                except OSError:
                    pass


# Shared driver preamble: seed helpers used by several scenarios. We use the
# real Factory + ORM so that org/data_source/query_result wiring matches prod.
_PREAMBLE = '''\
from redash.models import QueryResult, DataSource, db
from tests import BaseTestCase


class _CountsBase(BaseTestCase):
    def new_data_source(self, org=None):
        org = org or self.factory.org
        ds = self.factory.create_data_source(org=org)
        db.session.flush()
        return ds

    def add_results(self, data_source, n, org=None):
        """Create n QueryResult rows for data_source within org."""
        org = org or data_source.org
        for _ in range(n):
            self.factory.create_query_result(data_source=data_source, org=org)
        db.session.flush()

    def counts(self, org=None):
        org = org or self.factory.org
        return list(QueryResult.counts_by_data_source(org))
'''


class TestSqlalchemyOrmPatterns:
    REPO_DIR = "/workspace/redash"

    # ------------------------------------------------------------------ L1

    def test_models_file_exists(self):
        """L1: the model module to be modified exists."""
        assert os.path.isfile(MODELS_FILE), f"missing {MODELS_FILE}"

    def test_models_dir_and_test_file_present(self):
        """L1: the tests/models dir and the target test file exist (for native run)."""
        assert os.path.isdir(MODELS_TESTS_DIR), f"missing {MODELS_TESTS_DIR}"
        assert os.path.isfile(TARGET_TEST_FILE), (
            "tests/models/test_query_results.py must exist"
        )

    def test_counts_classmethod_signature(self):
        """L1: `counts_by_data_source` is defined on the QueryResult class as a
        classmethod taking exactly (cls, org) -- verified via AST, not grep."""
        with open(MODELS_FILE) as fh:
            tree = ast.parse(fh.read())

        qr_cls = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "QueryResult":
                qr_cls = node
                break
        assert qr_cls is not None, "class QueryResult not found in models"

        method = None
        for item in qr_cls.body:
            if isinstance(item, ast.FunctionDef) and item.name == "counts_by_data_source":
                method = item
                break
        assert method is not None, "QueryResult.counts_by_data_source method not defined"

        decorators = {
            d.id for d in method.decorator_list if isinstance(d, ast.Name)
        }
        assert "classmethod" in decorators, (
            "counts_by_data_source must be a @classmethod"
        )

        argnames = [a.arg for a in method.args.args]
        assert argnames == ["cls", "org"], (
            f"counts_by_data_source signature must be (cls, org); got {argnames}"
        )

    def test_models_module_imports(self):
        """L1: the modified models module imports cleanly (no syntax/import error)."""
        proc = subprocess.run(
            ["python", "-c", "import redash.models"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "PYTHONPATH": REPO_DIR},
        )
        assert proc.returncode == 0, (
            "importing redash.models failed:\n" + proc.stdout + proc.stderr
        )

    # ------------------------------------------------------------------ L2

    def test_basic_counts_and_ordering(self):
        """L2: D1 has 3 results, D2 has 1 -> [(D1.id, 3), (D2.id, 1)] ordered by id.

        A stub returning a fixed list, or counting all results without grouping,
        fails here."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsBasic(_CountsBase):
                def test_basic(self):
                    d1 = self.new_data_source()
                    d2 = self.new_data_source()
                    # Guarantee ascending-id expectation regardless of creation order.
                    lo, hi = sorted([d1, d2], key=lambda d: d.id)
                    self.add_results(lo, 3)
                    self.add_results(hi, 1)
                    res = self.counts()
                    assert res == [(lo.id, 3), (hi.id, 1)], res
        ''')
        _write_driver("test_cbds_driver_basic.py", driver)
        proc = _run_pytest("tests/models/test_cbds_driver_basic.py")
        assert proc.returncode == 0, (
            "basic counts/ordering failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_returns_tuples_and_is_iterable(self):
        """L2: list(counts_by_data_source(org)) yields 2-tuples of (int, int)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsShape(_CountsBase):
                def test_shape(self):
                    d1 = self.new_data_source()
                    d2 = self.new_data_source()
                    self.add_results(d1, 2)
                    self.add_results(d2, 5)
                    res = self.counts()
                    assert isinstance(res, list)
                    assert len(res) == 2, res
                    seen = {}
                    for row in res:
                        assert len(row) == 2, row
                        ds_id, count = row
                        assert isinstance(ds_id, int), type(ds_id)
                        assert isinstance(count, int), type(count)
                        seen[ds_id] = count
                    assert seen == {d1.id: 2, d2.id: 5}, seen
        ''')
        _write_driver("test_cbds_driver_shape.py", driver)
        proc = _run_pytest("tests/models/test_cbds_driver_shape.py")
        assert proc.returncode == 0, (
            "shape/iterability failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_ascending_data_source_ordering(self):
        """L2: with several data sources, rows come back strictly ascending by
        data_source_id -- discriminates an implementation that omits ORDER BY."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsOrder(_CountsBase):
                def test_order(self):
                    sources = [self.new_data_source() for _ in range(4)]
                    # Add a distinct, non-monotonic number of results per source so
                    # ordering can't accidentally come from the count column.
                    counts_map = {}
                    for ds, n in zip(sources, [2, 1, 4, 3]):
                        self.add_results(ds, n)
                        counts_map[ds.id] = n
                    res = self.counts()
                    ids = [row[0] for row in res]
                    assert ids == sorted(ids), ids
                    assert dict(res) == counts_map, (res, counts_map)
        ''')
        _write_driver("test_cbds_driver_order.py", driver)
        proc = _run_pytest("tests/models/test_cbds_driver_order.py")
        assert proc.returncode == 0, (
            "ascending ordering failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_zero_result_source_omitted(self):
        """L2: a data source with NO stored results must not appear as a row.

        Discriminates a solution that lists every DataSource (LEFT JOIN with 0)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsOmitEmpty(_CountsBase):
                def test_omit_empty(self):
                    d_with = self.new_data_source()
                    d_empty = self.new_data_source()  # created but never seeded
                    self.add_results(d_with, 2)
                    res = self.counts()
                    assert res == [(d_with.id, 2)], res
                    ids = [row[0] for row in res]
                    assert d_empty.id not in ids, (d_empty.id, res)
        ''')
        _write_driver("test_cbds_driver_omit.py", driver)
        proc = _run_pytest("tests/models/test_cbds_driver_omit.py")
        assert proc.returncode == 0, (
            "zero-result source not omitted:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_empty_when_no_results(self):
        """L2: an org with no stored results -> empty list (no rows, no error)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsEmpty(_CountsBase):
                def test_no_results(self):
                    # Create data sources but store no QueryResult rows at all.
                    self.new_data_source()
                    self.new_data_source()
                    assert self.counts() == [], self.counts()
        ''')
        _write_driver("test_cbds_driver_empty.py", driver)
        proc = _run_pytest("tests/models/test_cbds_driver_empty.py")
        assert proc.returncode == 0, (
            "empty-org case failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_cross_org_isolation(self):
        """L2: results stored in a DIFFERENT org must never contribute, and the
        method respects the org argument it is given.

        Discriminates a solution that ignores `org` (counts globally)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsOrgIsolation(_CountsBase):
                def test_other_org_excluded(self):
                    org1 = self.factory.org
                    org2 = self.factory.create_org()
                    db.session.flush()

                    d1 = self.new_data_source(org=org1)
                    d2 = self.new_data_source(org=org2)
                    self.add_results(d1, 3, org=org1)
                    self.add_results(d2, 5, org=org2)

                    # org1 only sees its own data source / counts.
                    res1 = self.counts(org1)
                    assert res1 == [(d1.id, 3)], res1

                    # org2 only sees its own.
                    res2 = self.counts(org2)
                    assert res2 == [(d2.id, 5)], res2

                    # Cross-check: org2's data source id is absent from org1's rows.
                    assert d2.id not in [r[0] for r in res1], (d2.id, res1)
        ''')
        _write_driver("test_cbds_driver_org.py", driver)
        proc = _run_pytest("tests/models/test_cbds_driver_org.py")
        assert proc.returncode == 0, (
            "cross-org isolation failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_counts_results_not_data_sources_or_queries(self):
        """L2: the count is the number of QueryResult rows per data source, and a
        single data source with many results aggregates into ONE row.

        Discriminates a solution that returns count==1 per source (presence) or
        that counts queries/data-sources instead of stored results."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsAggregate(_CountsBase):
                def test_aggregate(self):
                    d1 = self.new_data_source()
                    self.add_results(d1, 7)
                    res = self.counts()
                    assert res == [(d1.id, 7)], res
                    # Exactly one row for the single data source.
                    assert len(res) == 1, res
                    assert res[0][1] == 7, res
        ''')
        _write_driver("test_cbds_driver_aggregate.py", driver)
        proc = _run_pytest("tests/models/test_cbds_driver_aggregate.py")
        assert proc.returncode == 0, (
            "aggregation-by-data-source failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_old_results_still_counted(self):
        """L2: every stored result counts regardless of how old retrieved_at is.

        Discriminates a solution that (mis)applies the `unused` age threshold."""
        driver = _PREAMBLE + textwrap.dedent('''
            import datetime
            from redash.utils import utcnow

            class CountsOldResults(_CountsBase):
                def test_old_counted(self):
                    d1 = self.new_data_source()
                    very_old = utcnow() - datetime.timedelta(days=3650)
                    recent = utcnow()
                    self.factory.create_query_result(data_source=d1, org=d1.org,
                                                      retrieved_at=very_old)
                    self.factory.create_query_result(data_source=d1, org=d1.org,
                                                      retrieved_at=recent)
                    db.session.flush()
                    res = self.counts()
                    assert res == [(d1.id, 2)], res
        ''')
        _write_driver("test_cbds_driver_old.py", driver)
        proc = _run_pytest("tests/models/test_cbds_driver_old.py")
        assert proc.returncode == 0, (
            "old-results counting failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_multiple_sources_mixed_counts(self):
        """L2: a richer scenario -- three populated sources plus one empty one,
        verifying both grouping, omission of the empty source, and ordering."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsMixed(_CountsBase):
                def test_mixed(self):
                    ds = [self.new_data_source() for _ in range(4)]
                    # ds[0]:1, ds[1]:0 (omitted), ds[2]:3, ds[3]:2
                    self.add_results(ds[0], 1)
                    self.add_results(ds[2], 3)
                    self.add_results(ds[3], 2)
                    expected = sorted(
                        [(ds[0].id, 1), (ds[2].id, 3), (ds[3].id, 2)],
                        key=lambda r: r[0],
                    )
                    res = self.counts()
                    assert res == expected, (res, expected)
                    assert ds[1].id not in [r[0] for r in res], (ds[1].id, res)
        ''')
        _write_driver("test_cbds_driver_mixed.py", driver)
        proc = _run_pytest("tests/models/test_cbds_driver_mixed.py")
        assert proc.returncode == 0, (
            "mixed multi-source scenario failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_does_not_mutate_db(self):
        """L2: calling counts_by_data_source repeatedly is read-only -- it neither
        changes its result nor alters the underlying QueryResult/DataSource rows."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsReadOnly(_CountsBase):
                def test_read_only(self):
                    d1 = self.new_data_source()
                    d2 = self.new_data_source()
                    self.add_results(d1, 2)
                    self.add_results(d2, 1)
                    before_results = QueryResult.query.count()
                    before_sources = DataSource.query.count()
                    r1 = self.counts()
                    r2 = self.counts()
                    r3 = self.counts()
                    assert r1 == r2 == r3, (r1, r2, r3)
                    assert dict(r1) == {d1.id: 2, d2.id: 1}, r1
                    assert QueryResult.query.count() == before_results
                    assert DataSource.query.count() == before_sources
        ''')
        _write_driver("test_cbds_driver_readonly.py", driver)
        proc = _run_pytest("tests/models/test_cbds_driver_readonly.py")
        assert proc.returncode == 0, (
            "read-only / idempotence check failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_agent_test_file_passes_counts_selection(self):
        """L2: the agent's own additions to tests/models/test_query_results.py for
        counts_by_data_source must pass under the native command from the task's
        Acceptance Criteria:

            pytest tests/models/test_query_results.py -k counts_by_data_source

        We require at least one matching test to have been collected & passed."""
        proc = _run_pytest(
            "tests/models/test_query_results.py",
            extra=["-k", "counts_by_data_source"],
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "agent's counts_by_data_source tests did not pass:\n" + out[-4000:]
        )
        # Ensure tests were actually collected (no rubber-stamp "no tests ran").
        assert "no tests ran" not in out.lower(), (
            "no counts_by_data_source test was collected:\n" + out[-2000:]
        )
        assert " passed" in out, (
            "expected at least one passing counts_by_data_source test:\n" + out[-2000:]
        )

    def test_full_query_results_file_still_passes(self):
        """L2: the full target test file must continue to pass (no regressions to
        the existing QueryResult tests), per the Acceptance Criteria."""
        proc = _run_pytest("tests/models/test_query_results.py", timeout=900)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "tests/models/test_query_results.py regressed:\n" + out[-4000:]
        )
        assert " passed" in out, (
            "expected passing tests in test_query_results.py:\n" + out[-2000:]
        )
