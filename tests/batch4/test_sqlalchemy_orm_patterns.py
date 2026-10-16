"""Benchmark test for skill: sqlalchemy-orm-patterns (variant ext4).

Task
----
Add a `Query.archived_counts_by_data_source(cls, org)` classmethod to redash's
ORM model (`redash/models/__init__.py`). For the given organization it must
return an iterable of two-element rows `(data_source_id, archived_count)` where:

  * only queries belonging to `org` are counted (other orgs excluded),
  * only archived queries (`is_archived` true) are counted,
  * rows are grouped by `data_source_id`,
  * data sources with zero archived queries are omitted entirely,
  * rows are ordered by ascending `data_source_id` (deterministic output),
  * the method is read-only (does not mutate the DB) and takes exactly one
    argument beyond `cls`.

Verification strategy
---------------------
L1 checks confirm the deliverable file exists, the classmethod is defined with
the EXACT required signature `(cls, org)` and the `@classmethod` decorator (via
AST, not substring grep), and that the modified module imports cleanly.

L2 checks DYNAMICALLY EXERCISE the real behavior. Rather than trusting tests the
agent may have written, we drop our OWN focused pytest driver modules into the
repo's `tests/models/` directory (so they pick up the real DB-backed
`BaseTestCase`), seed `Query`/`DataSource` rows directly via the ORM factory,
call `Query.archived_counts_by_data_source(...)`, and assert on the concrete
returned rows. Each driver is run with the repo's native `pytest`; we assert on
returncode + behavior.

A naive solution (hardcoded list, counting all queries regardless of
`is_archived`, ignoring the `org` filter, including zero-count data sources,
wrong ordering, or cross-org leakage) fails these tests.
"""

import ast
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/redash"
MODELS_FILE = os.path.join(REPO_DIR, "redash", "models", "__init__.py")
MODELS_TESTS_DIR = os.path.join(REPO_DIR, "tests", "models")

# Files we inject into the repo so we can clean them up afterwards.
_INJECTED = []


def _write_driver(name, body):
    """Write a pytest driver module into tests/models/ and remember it."""
    path = os.path.join(MODELS_TESTS_DIR, name)
    with open(path, "w") as fh:
        fh.write(body)
    _INJECTED.append(path)
    return path


def _run_pytest(target, timeout=600):
    """Run the repo's native pytest against `target` (path relative to REPO_DIR)."""
    cmd = ["python", "-m", "pytest", target, "-v", "--tb=short", "-p", "no:cacheprovider"]
    env = dict(os.environ)
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
    pycache = os.path.join(MODELS_TESTS_DIR, "__pycache__")
    if os.path.isdir(pycache):
        for f in os.listdir(pycache):
            if "arch_counts_driver" in f:
                try:
                    os.remove(os.path.join(pycache, f))
                except OSError:
                    pass


# Shared driver preamble: seed helpers used by several scenarios.
_PREAMBLE = '''\
from redash.models import Query, DataSource, db
from tests import BaseTestCase


class _ArchCountsBase(BaseTestCase):
    def make_data_source(self, org=None, group=None):
        org = org or self.factory.org
        group = group or self.factory.default_group
        ds = self.factory.create_data_source(group=group, org=org)
        db.session.flush()
        return ds

    def make_query(self, data_source, archived, org=None, user=None):
        org = org or self.factory.org
        user = user or self.factory.user
        q = self.factory.create_query(
            data_source=data_source,
            org=org,
            user=user,
            is_archived=archived,
        )
        db.session.flush()
        return q

    def result(self, org=None):
        org = org or self.factory.org
        return list(Query.archived_counts_by_data_source(org))
'''


class TestSqlalchemyOrmPatterns:
    REPO_DIR = "/workspace/redash"

    # ------------------------------------------------------------------ L1

    def test_models_file_exists(self):
        """L1: the model module to be modified exists."""
        assert os.path.isfile(MODELS_FILE), f"missing {MODELS_FILE}"

    def test_models_dir_and_test_file_present(self):
        """L1: the tests/models dir and target test file exist (for native run)."""
        assert os.path.isdir(MODELS_TESTS_DIR), f"missing {MODELS_TESTS_DIR}"
        assert os.path.isfile(
            os.path.join(MODELS_TESTS_DIR, "test_queries.py")
        ), "tests/models/test_queries.py must exist"

    def test_classmethod_signature(self):
        """L1: `archived_counts_by_data_source` is defined on the Query class as a
        classmethod taking exactly (cls, org) -- verified via AST, not substring grep."""
        with open(MODELS_FILE) as fh:
            tree = ast.parse(fh.read())

        query_cls = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "Query":
                query_cls = node
                break
        assert query_cls is not None, "class Query not found in models"

        method = None
        for item in query_cls.body:
            if (
                isinstance(item, ast.FunctionDef)
                and item.name == "archived_counts_by_data_source"
            ):
                method = item
                break
        assert method is not None, (
            "Query.archived_counts_by_data_source method not defined"
        )

        decorators = {
            d.id for d in method.decorator_list if isinstance(d, ast.Name)
        }
        assert "classmethod" in decorators, (
            "archived_counts_by_data_source must be a @classmethod"
        )

        argnames = [a.arg for a in method.args.args]
        assert argnames == ["cls", "org"], (
            f"signature must be (cls, org); got {argnames}"
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
        """L2: D1 has 2 archived + 1 active, D2 has 1 archived ->
        [(D1.id, 2), (D2.id, 1)] ordered by ascending data_source_id.

        This is the canonical scenario from the task's Expected Functionality."""
        driver = _PREAMBLE + textwrap.dedent('''
            class ArchBasic(_ArchCountsBase):
                def test_basic(self):
                    d1 = self.make_data_source()
                    d2 = self.make_data_source()
                    # Ensure ordering assertion is meaningful.
                    lo, hi = sorted([d1, d2], key=lambda d: d.id)
                    # lo gets 2 archived + 1 active, hi gets 1 archived.
                    self.make_query(lo, archived=True)
                    self.make_query(lo, archived=True)
                    self.make_query(lo, archived=False)
                    self.make_query(hi, archived=True)
                    res = self.result()
                    assert res == [(lo.id, 2), (hi.id, 1)], res
        ''')
        _write_driver("test_arch_counts_driver_basic.py", driver)
        proc = _run_pytest("tests/models/test_arch_counts_driver_basic.py")
        assert proc.returncode == 0, (
            "basic counts/ordering failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_returns_tuples_and_iterable(self):
        """L2: list(...) yields 2-element rows of (int data_source_id, int count)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class ArchShape(_ArchCountsBase):
                def test_shape(self):
                    d1 = self.make_data_source()
                    self.make_query(d1, archived=True)
                    self.make_query(d1, archived=True)
                    res = self.result()
                    assert isinstance(res, list)
                    assert len(res) == 1, res
                    row = res[0]
                    assert len(row) == 2, row
                    ds_id, count = row
                    assert isinstance(ds_id, int), type(ds_id)
                    assert isinstance(count, int), type(count)
                    assert (ds_id, count) == (d1.id, 2), res
        ''')
        _write_driver("test_arch_counts_driver_shape.py", driver)
        proc = _run_pytest("tests/models/test_arch_counts_driver_shape.py")
        assert proc.returncode == 0, (
            "shape/iterability failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_non_archived_excluded(self):
        """L2: a data source whose queries are ALL non-archived must not appear.

        Discriminates a solution that counts all queries regardless of is_archived."""
        driver = _PREAMBLE + textwrap.dedent('''
            class ArchNonArchived(_ArchCountsBase):
                def test_all_active(self):
                    d1 = self.make_data_source()
                    self.make_query(d1, archived=False)
                    self.make_query(d1, archived=False)
                    self.make_query(d1, archived=False)
                    assert self.result() == [], self.result()

                def test_mix_only_archived_counted(self):
                    d1 = self.make_data_source()
                    self.make_query(d1, archived=True)
                    self.make_query(d1, archived=False)
                    self.make_query(d1, archived=False)
                    assert self.result() == [(d1.id, 1)], self.result()
        ''')
        _write_driver("test_arch_counts_driver_nonarchived.py", driver)
        proc = _run_pytest("tests/models/test_arch_counts_driver_nonarchived.py")
        assert proc.returncode == 0, (
            "non-archived queries leaked into result:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_zero_archived_data_source_omitted(self):
        """L2: a data source with zero archived queries must not appear as a row,
        even when another data source in the org does have archived queries."""
        driver = _PREAMBLE + textwrap.dedent('''
            class ArchOmitZero(_ArchCountsBase):
                def test_omit_zero(self):
                    d_with = self.make_data_source()
                    d_without = self.make_data_source()
                    self.make_query(d_with, archived=True)
                    # d_without only has active queries.
                    self.make_query(d_without, archived=False)
                    res = self.result()
                    assert res == [(d_with.id, 1)], res
                    ids = [r[0] for r in res]
                    assert d_without.id not in ids, res
        ''')
        _write_driver("test_arch_counts_driver_omitzero.py", driver)
        proc = _run_pytest("tests/models/test_arch_counts_driver_omitzero.py")
        assert proc.returncode == 0, (
            "zero-archived data source not omitted:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_empty_when_no_archived(self):
        """L2: an org with no archived queries -> empty list (no rows, no error)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class ArchEmpty(_ArchCountsBase):
                def test_no_archived(self):
                    d1 = self.make_data_source()
                    d2 = self.make_data_source()
                    self.make_query(d1, archived=False)
                    self.make_query(d2, archived=False)
                    assert self.result() == [], self.result()

                def test_no_queries_at_all(self):
                    self.make_data_source()
                    assert self.result() == [], self.result()
        ''')
        _write_driver("test_arch_counts_driver_empty.py", driver)
        proc = _run_pytest("tests/models/test_arch_counts_driver_empty.py")
        assert proc.returncode == 0, (
            "empty/no-archived case failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_cross_org_isolation(self):
        """L2: archived queries belonging to a DIFFERENT org's data source must not
        contribute to this org's result.

        Discriminates a solution that ignores the org filter."""
        driver = _PREAMBLE + textwrap.dedent('''
            class ArchCrossOrg(_ArchCountsBase):
                def test_other_org_excluded(self):
                    org = self.factory.org
                    other_org = self.factory.create_org()
                    other_group = self.factory.create_group(org=other_org)
                    other_user = self.factory.create_user(org=other_org)
                    db.session.add(other_group)
                    db.session.flush()

                    d_mine = self.make_data_source(org=org)
                    d_other = self.make_data_source(org=other_org, group=other_group)

                    self.make_query(d_mine, archived=True, org=org)
                    # Archived query in the OTHER org must never contribute.
                    self.make_query(d_other, archived=True, org=other_org, user=other_user)
                    self.make_query(d_other, archived=True, org=other_org, user=other_user)

                    res = self.result(org)
                    assert res == [(d_mine.id, 1)], res
                    ids = [r[0] for r in res]
                    assert d_other.id not in ids, res

                    # And the other org sees only its own two.
                    other_res = self.result(other_org)
                    assert other_res == [(d_other.id, 2)], other_res
        ''')
        _write_driver("test_arch_counts_driver_crossorg.py", driver)
        proc = _run_pytest("tests/models/test_arch_counts_driver_crossorg.py")
        assert proc.returncode == 0, (
            "cross-org isolation failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_multiple_data_sources_ordered(self):
        """L2: with three data sources each having a distinct number of archived
        queries, rows must be ordered by ascending data_source_id with correct counts."""
        driver = _PREAMBLE + textwrap.dedent('''
            class ArchMulti(_ArchCountsBase):
                def test_three_sources(self):
                    sources = [self.make_data_source() for _ in range(3)]
                    sources.sort(key=lambda d: d.id)
                    a, b, c = sources
                    # a:3 archived, b:1 archived (+1 active), c:2 archived
                    for _ in range(3):
                        self.make_query(a, archived=True)
                    self.make_query(b, archived=True)
                    self.make_query(b, archived=False)
                    for _ in range(2):
                        self.make_query(c, archived=True)
                    res = self.result()
                    assert res == [(a.id, 3), (b.id, 1), (c.id, 2)], res
                    # Strictly ascending by data_source_id.
                    ids = [r[0] for r in res]
                    assert ids == sorted(ids), ids
        ''')
        _write_driver("test_arch_counts_driver_multi.py", driver)
        proc = _run_pytest("tests/models/test_arch_counts_driver_multi.py")
        assert proc.returncode == 0, (
            "multi-source ordering/counts failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_counts_are_exact_not_rubber_stamped(self):
        """L2: the count value must equal the exact number of archived queries for a
        data source -- not 1, not the total number of queries.

        Discriminates a stub that emits a constant or counts every query."""
        driver = _PREAMBLE + textwrap.dedent('''
            class ArchExact(_ArchCountsBase):
                def test_exact_count(self):
                    d1 = self.make_data_source()
                    # 5 archived + 4 active on the same data source.
                    for _ in range(5):
                        self.make_query(d1, archived=True)
                    for _ in range(4):
                        self.make_query(d1, archived=False)
                    res = self.result()
                    assert res == [(d1.id, 5)], res
                    # Must not be the total (9) and must not be a constant 1.
                    assert res[0][1] == 5, res
        ''')
        _write_driver("test_arch_counts_driver_exact.py", driver)
        proc = _run_pytest("tests/models/test_arch_counts_driver_exact.py")
        assert proc.returncode == 0, (
            "exact-count check failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_read_only_and_idempotent(self):
        """L2: calling the method repeatedly is read-only -- it neither changes
        results nor alters the underlying query rows; arity is exactly (cls, org)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class ArchReadOnly(_ArchCountsBase):
                def test_read_only(self):
                    d1 = self.make_data_source()
                    d2 = self.make_data_source()
                    lo, hi = sorted([d1, d2], key=lambda d: d.id)
                    self.make_query(lo, archived=True)
                    self.make_query(lo, archived=True)
                    self.make_query(hi, archived=True)
                    before_queries = Query.query.count()
                    r1 = self.result()
                    r2 = self.result()
                    r3 = self.result()
                    assert r1 == r2 == r3 == [(lo.id, 2), (hi.id, 1)], (r1, r2, r3)
                    assert Query.query.count() == before_queries

                def test_arity(self):
                    import inspect
                    sig = inspect.signature(Query.archived_counts_by_data_source)
                    # `cls` is bound; only `org` remains visible on the bound method.
                    assert list(sig.parameters) == ["org"], list(sig.parameters)
        ''')
        _write_driver("test_arch_counts_driver_readonly.py", driver)
        proc = _run_pytest("tests/models/test_arch_counts_driver_readonly.py")
        assert proc.returncode == 0, (
            "read-only / idempotence / arity check failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_agent_test_file_passes_archived_counts_selection(self):
        """L2: the agent's own additions to tests/models/test_queries.py for
        archived_counts must pass under the native command from the task's
        Acceptance Criteria (`pytest tests/models/test_queries.py -k archived_counts`).

        We require at least one matching test to have been collected & passed."""
        cmd = [
            "python", "-m", "pytest", "tests/models/test_queries.py",
            "-k", "archived_counts", "-v", "--tb=short", "-p", "no:cacheprovider",
        ]
        proc = subprocess.run(
            cmd, cwd=REPO_DIR, capture_output=True, text=True, timeout=600,
            env={**os.environ, "PYTHONPATH": REPO_DIR},
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "agent's archived_counts tests did not pass:\n" + out[-4000:]
        )
        assert "no tests ran" not in out.lower(), (
            "no archived_counts test was collected:\n" + out[-2000:]
        )
        assert " passed" in out, (
            "expected at least one passing archived_counts test:\n" + out[-2000:]
        )
