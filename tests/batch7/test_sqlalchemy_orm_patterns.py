"""Benchmark test for skill: sqlalchemy-orm-patterns (variant ext7).

Task under test
---------------
Add a `Favorite.counts_by_type(user)` classmethod to redash's ORM model
(`redash/models/__init__.py`). For a given user it must return an iterable of
two-element `(object_type, count)` rows where:

* only favorites belonging to that user are counted (cross-user leakage is a
  bug);
* rows are grouped by `Favorite.object_type`;
* object types for which the user has no favorites are omitted;
* rows are ordered alphabetically (ascending) by `object_type`;
* a user with no favorites yields an empty `list(...)`.

The deliverable also includes a NEW test module `tests/models/test_favorites.py`
exercising the classmethod, runnable via the doc's native command:

    pytest tests/models/test_favorites.py

Verification strategy
---------------------
L1 checks confirm the deliverable files exist, that `counts_by_type` is defined
on the `Favorite` class as a `@classmethod` with the exact `(cls, user)`
signature (via AST, not substring grep), and that the modified module imports
cleanly.

L2 checks DYNAMICALLY EXERCISE behavior. Rather than trusting the agent's own
tests, we drop our OWN focused pytest driver modules into the repo's
`tests/models/` directory (so they inherit the real DB-backed `BaseTestCase`),
seed `Favorite` rows directly via the ORM (favoriting real `Query` and
`Dashboard` objects), call `Favorite.counts_by_type(...)`, and assert on the
concrete returned rows. Each driver runs under the repo's native `pytest`; we
assert on returncode + behavior.

A naive solution (hardcoded list, counting all favorites regardless of owner,
counting all object types globally, wrong/absent ordering, including empty
types, or returning a non-grouped result) fails these tests. A final L2 case
runs the doc's native acceptance command against the agent's own
`tests/models/test_favorites.py`.
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
            if "counts_driver" in f or "cbt_driver" in f:
                try:
                    os.remove(os.path.join(pycache, f))
                except OSError:
                    pass


# Shared driver preamble: seed helpers used by several scenarios.
#
# We favorite objects exactly the way redash's own handlers do
# (`Favorite(org_id=..., object=<obj>, user=<user>)`), which populates
# object_type from the object's class name. `result()` normalizes whatever the
# classmethod returns into a list of plain (str, int) tuples so assertions are
# robust to Row/tuple result shapes.
_PREAMBLE = '''\
from redash.models import Query, Dashboard, Favorite, db
from tests import BaseTestCase


class _CountsBase(BaseTestCase):
    def make_query(self, user=None):
        ds = self.factory.create_data_source(group=self.factory.default_group)
        q = self.factory.create_query(data_source=ds, user=user or self.factory.user)
        db.session.flush()
        return q

    def make_dashboard(self, user=None):
        d = self.factory.create_dashboard(user=user or self.factory.user)
        db.session.flush()
        return d

    def favorite(self, obj, user):
        fav = Favorite(org_id=self.factory.org.id, object=obj, user=user)
        db.session.add(fav)
        db.session.flush()
        return fav

    def result(self, user):
        rows = list(Favorite.counts_by_type(user))
        norm = []
        for row in rows:
            object_type, count = row[0], row[1]
            norm.append((object_type, int(count)))
        return norm
'''


class TestSqlalchemyOrmPatterns:
    REPO_DIR = "/workspace/redash"

    # ------------------------------------------------------------------ L1

    def test_models_file_exists(self):
        """L1: the model module to be modified exists."""
        assert os.path.isfile(MODELS_FILE), f"missing {MODELS_FILE}"

    def test_models_dir_present(self):
        """L1: the tests/models dir exists (needed for native run + drivers)."""
        assert os.path.isdir(MODELS_TESTS_DIR), f"missing {MODELS_TESTS_DIR}"

    def test_new_test_file_present(self):
        """L1: the new deliverable test module tests/models/test_favorites.py exists."""
        path = os.path.join(MODELS_TESTS_DIR, "test_favorites.py")
        assert os.path.isfile(path), "tests/models/test_favorites.py must be created"

    def test_counts_by_type_classmethod_signature(self):
        """L1: `counts_by_type` is defined on the `Favorite` class as a
        @classmethod taking exactly (cls, user) -- verified via AST, not grep."""
        with open(MODELS_FILE) as fh:
            tree = ast.parse(fh.read())

        fav_cls = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "Favorite":
                fav_cls = node
                break
        assert fav_cls is not None, "class Favorite not found in models"

        method = None
        for item in fav_cls.body:
            if isinstance(item, ast.FunctionDef) and item.name == "counts_by_type":
                method = item
                break
        assert method is not None, "Favorite.counts_by_type method not defined"

        decorators = {
            d.id for d in method.decorator_list if isinstance(d, ast.Name)
        }
        assert "classmethod" in decorators, "counts_by_type must be a @classmethod"

        argnames = [a.arg for a in method.args.args]
        assert argnames == ["cls", "user"], (
            f"counts_by_type signature must be (cls, user); got {argnames}"
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
        """L2: two favorited queries + one favorited dashboard ->
        [('Dashboard', 1), ('Query', 2)] (grouped, counted, alphabetical)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsBasic(_CountsBase):
                def test_basic(self):
                    user = self.factory.user
                    q1 = self.make_query()
                    q2 = self.make_query()
                    d1 = self.make_dashboard()
                    self.favorite(q1, user)
                    self.favorite(q2, user)
                    self.favorite(d1, user)
                    assert self.result(user) == [("Dashboard", 1), ("Query", 2)], \\
                        self.result(user)
        ''')
        _write_driver("test_cbt_driver_basic.py", driver)
        proc = _run_pytest("tests/models/test_cbt_driver_basic.py")
        assert proc.returncode == 0, (
            "basic counts/ordering failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_returns_tuples_and_is_iterable(self):
        """L2: list(counts_by_type(user)) yields 2-element rows of (str, int)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsShape(_CountsBase):
                def test_shape(self):
                    user = self.factory.user
                    self.favorite(self.make_query(), user)
                    self.favorite(self.make_dashboard(), user)
                    rows = list(Favorite.counts_by_type(user))
                    assert len(rows) == 2, rows
                    for row in rows:
                        object_type, count = row[0], row[1]
                        assert isinstance(object_type, str), type(object_type)
                        assert isinstance(count, int), type(count)
                    norm = [(r[0], int(r[1])) for r in rows]
                    assert norm == [("Dashboard", 1), ("Query", 1)], norm
        ''')
        _write_driver("test_cbt_driver_shape.py", driver)
        proc = _run_pytest("tests/models/test_cbt_driver_shape.py")
        assert proc.returncode == 0, (
            "shape/iterability failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_only_owners_favorites_counted(self):
        """L2: favorites owned by a DIFFERENT user must not affect this user's
        counts; discriminates a global (non-user-filtered) implementation."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsOtherUser(_CountsBase):
                def test_other_user(self):
                    user = self.factory.user
                    other = self.factory.create_user()
                    db.session.flush()
                    # user favorites one query; other favorites three queries.
                    self.favorite(self.make_query(), user)
                    for _ in range(3):
                        self.favorite(self.make_query(), other)
                    assert self.result(user) == [("Query", 1)], self.result(user)
                    assert self.result(other) == [("Query", 3)], self.result(other)
        ''')
        _write_driver("test_cbt_driver_otheruser.py", driver)
        proc = _run_pytest("tests/models/test_cbt_driver_otheruser.py")
        assert proc.returncode == 0, (
            "cross-user isolation failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_empty_types_omitted(self):
        """L2: an object type the user has NO favorites of must not appear as a
        row (e.g. only-dashboards user -> no 'Query' row)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsOmit(_CountsBase):
                def test_only_dashboards(self):
                    user = self.factory.user
                    self.favorite(self.make_dashboard(), user)
                    self.favorite(self.make_dashboard(), user)
                    assert self.result(user) == [("Dashboard", 2)], self.result(user)

                def test_only_queries(self):
                    user = self.factory.user
                    self.favorite(self.make_query(), user)
                    assert self.result(user) == [("Query", 1)], self.result(user)
        ''')
        _write_driver("test_cbt_driver_omit.py", driver)
        proc = _run_pytest("tests/models/test_cbt_driver_omit.py")
        assert proc.returncode == 0, (
            "empty types not omitted:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_empty_when_no_favorites(self):
        """L2: a user with no favorites -> empty list (no rows, no error).

        Discriminates a hardcoded/stub implementation that returns fixed rows."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsEmpty(_CountsBase):
                def test_no_favorites(self):
                    user = self.factory.user
                    # Create objects but favorite NONE of them.
                    self.make_query()
                    self.make_dashboard()
                    assert self.result(user) == [], self.result(user)
        ''')
        _write_driver("test_cbt_driver_empty.py", driver)
        proc = _run_pytest("tests/models/test_cbt_driver_empty.py")
        assert proc.returncode == 0, (
            "empty-favorites case failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_alphabetical_ordering_is_enforced(self):
        """L2: rows are ordered alphabetically by object_type ascending.

        'Dashboard' must precede 'Query' regardless of insertion order; this
        discriminates an unordered / insertion-ordered implementation."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsOrder(_CountsBase):
                def test_query_inserted_first(self):
                    user = self.factory.user
                    # Favorite a Query BEFORE any Dashboard.
                    self.favorite(self.make_query(), user)
                    self.favorite(self.make_dashboard(), user)
                    rows = self.result(user)
                    types = [r[0] for r in rows]
                    assert types == sorted(types), types
                    assert types == ["Dashboard", "Query"], types
        ''')
        _write_driver("test_cbt_driver_order.py", driver)
        proc = _run_pytest("tests/models/test_cbt_driver_order.py")
        assert proc.returncode == 0, (
            "alphabetical ordering not enforced:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_counts_aggregate_correctly(self):
        """L2: counts equal the number of the user's favorites of each type,
        across many rows; discriminates a count-of-distinct-types stub."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsAggregate(_CountsBase):
                def test_aggregate(self):
                    user = self.factory.user
                    for _ in range(4):
                        self.favorite(self.make_query(), user)
                    for _ in range(2):
                        self.favorite(self.make_dashboard(), user)
                    assert self.result(user) == [("Dashboard", 2), ("Query", 4)], \\
                        self.result(user)
        ''')
        _write_driver("test_cbt_driver_aggregate.py", driver)
        proc = _run_pytest("tests/models/test_cbt_driver_aggregate.py")
        assert proc.returncode == 0, (
            "aggregation failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_two_users_same_object_independent(self):
        """L2: two users favoriting the SAME object are counted independently;
        one user's favorite never inflates the other's counts."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsShared(_CountsBase):
                def test_shared_object(self):
                    user = self.factory.user
                    other = self.factory.create_user()
                    db.session.flush()
                    q = self.make_query()
                    self.favorite(q, user)
                    self.favorite(q, other)
                    assert self.result(user) == [("Query", 1)], self.result(user)
                    assert self.result(other) == [("Query", 1)], self.result(other)
        ''')
        _write_driver("test_cbt_driver_shared.py", driver)
        proc = _run_pytest("tests/models/test_cbt_driver_shared.py")
        assert proc.returncode == 0, (
            "shared-object independence failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_does_not_mutate_db(self):
        """L2: calling counts_by_type repeatedly is read-only -- stable results,
        and the underlying favorite/query/dashboard rows are unchanged."""
        driver = _PREAMBLE + textwrap.dedent('''
            class CountsReadOnly(_CountsBase):
                def test_read_only(self):
                    user = self.factory.user
                    self.favorite(self.make_query(), user)
                    self.favorite(self.make_query(), user)
                    self.favorite(self.make_dashboard(), user)
                    before_favs = Favorite.query.count()
                    before_queries = Query.query.count()
                    r1 = self.result(user)
                    r2 = self.result(user)
                    r3 = self.result(user)
                    expected = [("Dashboard", 1), ("Query", 2)]
                    assert r1 == r2 == r3 == expected, (r1, r2, r3)
                    assert Favorite.query.count() == before_favs
                    assert Query.query.count() == before_queries
        ''')
        _write_driver("test_cbt_driver_readonly.py", driver)
        proc = _run_pytest("tests/models/test_cbt_driver_readonly.py")
        assert proc.returncode == 0, (
            "read-only / idempotence check failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_single_argument_only(self):
        """L2: counts_by_type accepts exactly one argument beyond cls; calling it
        with an extra positional argument must raise TypeError."""
        driver = _PREAMBLE + textwrap.dedent('''
            import pytest

            class CountsArity(_CountsBase):
                def test_arity(self):
                    user = self.factory.user
                    self.favorite(self.make_query(), user)
                    # Exactly one arg works.
                    assert self.result(user) == [("Query", 1)], self.result(user)
                    # An extra positional arg is rejected.
                    with pytest.raises(TypeError):
                        Favorite.counts_by_type(user, user)
        ''')
        _write_driver("test_cbt_driver_arity.py", driver)
        proc = _run_pytest("tests/models/test_cbt_driver_arity.py")
        assert proc.returncode == 0, (
            "argument-arity check failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_agent_test_file_passes_native_command(self):
        """L2: the agent's deliverable tests/models/test_favorites.py must pass
        under the doc's native acceptance command:

            pytest tests/models/test_favorites.py

        We require tests to actually have been collected and passed (no
        rubber-stamp 'no tests ran')."""
        cmd = [
            "python", "-m", "pytest", "tests/models/test_favorites.py",
            "-v", "--tb=short", "-p", "no:cacheprovider",
        ]
        proc = subprocess.run(
            cmd, cwd=REPO_DIR, capture_output=True, text=True, timeout=600,
            env={**os.environ, "PYTHONPATH": REPO_DIR},
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "agent's test_favorites.py did not pass:\n" + out[-4000:]
        )
        assert "no tests ran" not in out.lower(), (
            "no test was collected in test_favorites.py:\n" + out[-2000:]
        )
        assert " passed" in out, (
            "expected at least one passing test in test_favorites.py:\n" + out[-2000:]
        )
