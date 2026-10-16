"""Benchmark test for skill: sqlalchemy-orm-patterns.

Task: Add a `Query.favorite_tags(user)` classmethod to redash's ORM model
(`redash/models/__init__.py`) that returns per-tag usage counts restricted to
the requesting user's favorited queries, ordered alphabetically by tag.

Verification strategy
---------------------
L1 checks confirm the deliverable file exists, the classmethod is defined with
the exact required signature, and the source is importable / syntactically sound.

L2 checks DYNAMICALLY EXERCISE the real behavior. Rather than trusting any test
the agent may have written, we drop our OWN focused pytest driver modules into
the repo's `tests/models/` directory (so they pick up the real DB-backed
`BaseTestCase`), seed Favorite/Query rows directly via the ORM, call
`Query.favorite_tags(...)`, and assert on the concrete returned rows. Each driver
is run with the repo's native `pytest` and we assert on returncode + behavior.

A naive solution (hardcoded list, keyword-matched stub, counting all queries
instead of only favorites, wrong ordering, mishandling of null/empty tags, or
cross-user leakage) fails these tests.
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
            if "fav_tags_driver" in f or "favtags_driver" in f:
                try:
                    os.remove(os.path.join(pycache, f))
                except OSError:
                    pass


# Shared driver preamble: seed helpers used by several scenarios.
_PREAMBLE = '''\
from redash.models import Query, Favorite, db
from tests import BaseTestCase


class _FavTagsBase(BaseTestCase):
    def make_query(self, tags, user=None, data_source=None):
        if data_source is None:
            data_source = self.factory.create_data_source(group=self.factory.default_group)
        q = self.factory.create_query(data_source=data_source, tags=tags, user=user or self.factory.user)
        db.session.flush()
        return q

    def favorite(self, obj, user):
        fav = Favorite(org_id=self.factory.org.id, object=obj, user=user)
        db.session.add(fav)
        db.session.flush()
        return fav

    def result(self, user):
        return list(Query.favorite_tags(user))
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

    def test_favorite_tags_classmethod_signature(self):
        """L1: `favorite_tags` is defined on the Query class as a classmethod
        taking exactly (cls, user) -- verified via AST, not substring grep."""
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
            if isinstance(item, ast.FunctionDef) and item.name == "favorite_tags":
                method = item
                break
        assert method is not None, "Query.favorite_tags method not defined"

        decorators = {
            d.id for d in method.decorator_list if isinstance(d, ast.Name)
        }
        assert "classmethod" in decorators, "favorite_tags must be a @classmethod"

        argnames = [a.arg for a in method.args.args]
        assert argnames == ["cls", "user"], (
            f"favorite_tags signature must be (cls, user); got {argnames}"
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
        """L2: two favorited queries -> alphabetically ordered (tag, count) rows.

        A: ['alpha','beta'], B: ['beta'] -> [('alpha',1),('beta',2)]."""
        driver = _PREAMBLE + textwrap.dedent('''
            class FavTagsBasic(_FavTagsBase):
                def test_basic(self):
                    qa = self.make_query(tags=["alpha", "beta"])
                    qb = self.make_query(tags=["beta"])
                    self.favorite(qa, self.factory.user)
                    self.favorite(qb, self.factory.user)
                    res = self.result(self.factory.user)
                    assert res == [("alpha", 1), ("beta", 2)], res
        ''')
        _write_driver("test_fav_tags_driver_basic.py", driver)
        proc = _run_pytest("tests/models/test_fav_tags_driver_basic.py")
        assert proc.returncode == 0, (
            "basic counts/ordering failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_returns_tuples_and_is_iterable(self):
        """L2: list(favorite_tags(user)) yields 2-tuples of (str, int)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class FavTagsShape(_FavTagsBase):
                def test_shape(self):
                    qa = self.make_query(tags=["gamma", "delta"])
                    self.favorite(qa, self.factory.user)
                    res = self.result(self.factory.user)
                    assert isinstance(res, list)
                    assert len(res) == 2, res
                    for row in res:
                        assert len(row) == 2, row
                        tag, count = row
                        assert isinstance(tag, str), type(tag)
                        assert isinstance(count, int), type(count)
                    assert res == [("delta", 1), ("gamma", 1)], res
        ''')
        _write_driver("test_fav_tags_driver_shape.py", driver)
        proc = _run_pytest("tests/models/test_fav_tags_driver_shape.py")
        assert proc.returncode == 0, (
            "shape/iterability failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_only_owners_favorites_counted(self):
        """L2: a query favorited by a DIFFERENT user must not affect this user."""
        driver = _PREAMBLE + textwrap.dedent('''
            class FavTagsOtherUser(_FavTagsBase):
                def test_other_user(self):
                    user = self.factory.user
                    other = self.factory.create_user()
                    db.session.flush()
                    qa = self.make_query(tags=["zeta"])
                    qc = self.make_query(tags=["zeta"])
                    self.favorite(qa, user)
                    self.favorite(qc, other)
                    assert self.result(user) == [("zeta", 1)], self.result(user)
                    # The other user sees their own single favorite.
                    assert self.result(other) == [("zeta", 1)], self.result(other)
        ''')
        _write_driver("test_fav_tags_driver_otheruser.py", driver)
        proc = _run_pytest("tests/models/test_fav_tags_driver_otheruser.py")
        assert proc.returncode == 0, (
            "cross-user isolation failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_non_query_favorites_ignored(self):
        """L2: a favorited DASHBOARD (non-Query object) must not produce rows."""
        driver = _PREAMBLE + textwrap.dedent('''
            class FavTagsDashboard(_FavTagsBase):
                def test_dashboard_only(self):
                    user = self.factory.user
                    dash = self.factory.create_dashboard()
                    db.session.flush()
                    self.favorite(dash, user)
                    assert self.result(user) == [], self.result(user)

                def test_dashboard_plus_query(self):
                    user = self.factory.user
                    dash = self.factory.create_dashboard()
                    qa = self.make_query(tags=["x"])
                    db.session.flush()
                    self.favorite(dash, user)
                    self.favorite(qa, user)
                    assert self.result(user) == [("x", 1)], self.result(user)
        ''')
        _write_driver("test_fav_tags_driver_dash.py", driver)
        proc = _run_pytest("tests/models/test_fav_tags_driver_dash.py")
        assert proc.returncode == 0, (
            "non-query favorites not ignored:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_non_favorited_queries_excluded(self):
        """L2: queries the user can see but has NOT favorited must not be counted.

        Discriminates a solution that mistakenly mirrors `all_tags`."""
        driver = _PREAMBLE + textwrap.dedent('''
            class FavTagsNonFav(_FavTagsBase):
                def test_non_fav_excluded(self):
                    user = self.factory.user
                    fav_q = self.make_query(tags=["kept"])
                    # Several non-favorited queries owned by the user, same group.
                    self.make_query(tags=["dropped", "kept"])
                    self.make_query(tags=["dropped"])
                    self.make_query(tags=["other"])
                    self.favorite(fav_q, user)
                    # Only the favorited query contributes -> just ("kept", 1).
                    assert self.result(user) == [("kept", 1)], self.result(user)
        ''')
        _write_driver("test_fav_tags_driver_nonfav.py", driver)
        proc = _run_pytest("tests/models/test_fav_tags_driver_nonfav.py")
        assert proc.returncode == 0, (
            "non-favorited queries leaked into result:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_empty_when_no_favorites(self):
        """L2: a user with no favorited queries -> empty list (no rows, no error)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class FavTagsEmpty(_FavTagsBase):
                def test_no_favorites(self):
                    user = self.factory.user
                    # Create queries but favorite none of them.
                    self.make_query(tags=["a", "b"])
                    self.make_query(tags=["c"])
                    assert self.result(user) == [], self.result(user)
        ''')
        _write_driver("test_fav_tags_driver_empty.py", driver)
        proc = _run_pytest("tests/models/test_fav_tags_driver_empty.py")
        assert proc.returncode == 0, (
            "empty-favorites case failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_empty_and_null_tags_produce_no_rows(self):
        """L2: a favorited query with empty `[]` or NULL tags yields no rows and
        must not raise."""
        driver = _PREAMBLE + textwrap.dedent('''
            class FavTagsNullTags(_FavTagsBase):
                def test_empty_list_tags(self):
                    user = self.factory.user
                    q = self.make_query(tags=[])
                    self.favorite(q, user)
                    assert self.result(user) == [], self.result(user)

                def test_null_tags(self):
                    user = self.factory.user
                    q = self.make_query(tags=None)
                    self.favorite(q, user)
                    assert self.result(user) == [], self.result(user)

                def test_mix_null_and_real(self):
                    user = self.factory.user
                    q_null = self.make_query(tags=None)
                    q_real = self.make_query(tags=["real"])
                    self.favorite(q_null, user)
                    self.favorite(q_real, user)
                    assert self.result(user) == [("real", 1)], self.result(user)
        ''')
        _write_driver("test_fav_tags_driver_nulltags.py", driver)
        proc = _run_pytest("tests/models/test_fav_tags_driver_nulltags.py")
        assert proc.returncode == 0, (
            "empty/null tags handling failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_case_sensitivity_and_aggregation(self):
        """L2: tags are case-sensitive ('sql' != 'SQL'); per-tag counts aggregate
        across multiple favorited queries; each distinct tag counted once/query."""
        driver = _PREAMBLE + textwrap.dedent('''
            class FavTagsCase(_FavTagsBase):
                def test_case_and_aggregate(self):
                    user = self.factory.user
                    # SQL appears in q1; sql appears in q2 and q3 -> distinct tags.
                    q1 = self.make_query(tags=["SQL", "etl"])
                    q2 = self.make_query(tags=["sql", "etl"])
                    q3 = self.make_query(tags=["sql"])
                    for q in (q1, q2, q3):
                        self.favorite(q, user)
                    res = self.result(user)
                    expected = [("SQL", 1), ("etl", 2), ("sql", 2)]
                    assert res == expected, res

                def test_duplicate_tag_one_query_counts_once(self):
                    # Even if a tag is listed twice in a single query's list,
                    # the query contributes per its distinct presence; the
                    # important invariant is that aggregation is by tag value.
                    user = self.factory.user
                    qa = self.make_query(tags=["dup"])
                    qb = self.make_query(tags=["dup"])
                    self.favorite(qa, user)
                    self.favorite(qb, user)
                    assert self.result(user) == [("dup", 1 + 1)], self.result(user)
        ''')
        _write_driver("test_fav_tags_driver_case.py", driver)
        proc = _run_pytest("tests/models/test_fav_tags_driver_case.py")
        assert proc.returncode == 0, (
            "case-sensitivity/aggregation failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_three_tags_single_query(self):
        """L2: one favorited query with three tags contributes to three tag rows,
        each with count 1, ordered alphabetically."""
        driver = _PREAMBLE + textwrap.dedent('''
            class FavTagsThree(_FavTagsBase):
                def test_three(self):
                    user = self.factory.user
                    q = self.make_query(tags=["mango", "apple", "lemon"])
                    self.favorite(q, user)
                    assert self.result(user) == [("apple", 1), ("lemon", 1), ("mango", 1)], \
                        self.result(user)
        ''')
        _write_driver("test_fav_tags_driver_three.py", driver)
        proc = _run_pytest("tests/models/test_fav_tags_driver_three.py")
        assert proc.returncode == 0, (
            "three-tags-single-query failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_does_not_mutate_db(self):
        """L2: calling favorite_tags repeatedly is read-only -- it neither changes
        results nor alters the underlying favorite/query rows."""
        driver = _PREAMBLE + textwrap.dedent('''
            class FavTagsReadOnly(_FavTagsBase):
                def test_read_only(self):
                    user = self.factory.user
                    qa = self.make_query(tags=["alpha", "beta"])
                    qb = self.make_query(tags=["beta"])
                    self.favorite(qa, user)
                    self.favorite(qb, user)
                    before_queries = Query.query.count()
                    before_favs = Favorite.query.count()
                    r1 = self.result(user)
                    r2 = self.result(user)
                    r3 = self.result(user)
                    assert r1 == r2 == r3 == [("alpha", 1), ("beta", 2)], (r1, r2, r3)
                    assert Query.query.count() == before_queries
                    assert Favorite.query.count() == before_favs
        ''')
        _write_driver("test_fav_tags_driver_readonly.py", driver)
        proc = _run_pytest("tests/models/test_fav_tags_driver_readonly.py")
        assert proc.returncode == 0, (
            "read-only / idempotence check failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_agent_test_file_passes_favorite_tags_selection(self):
        """L2: the agent's own additions to tests/models/test_queries.py for
        favorite_tags must pass under the native command from the task's
        Acceptance Criteria (`pytest tests/models/test_queries.py -k favorite_tags`).

        We require at least one matching test to have been collected & passed."""
        cmd = [
            "python", "-m", "pytest", "tests/models/test_queries.py",
            "-k", "favorite_tags", "-v", "--tb=short", "-p", "no:cacheprovider",
        ]
        proc = subprocess.run(
            cmd, cwd=REPO_DIR, capture_output=True, text=True, timeout=600,
            env={**os.environ, "PYTHONPATH": REPO_DIR},
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "agent's favorite_tags tests did not pass:\n" + out[-4000:]
        )
        # Ensure tests were actually collected (no rubber-stamp "no tests ran").
        assert "no tests ran" not in out.lower(), (
            "no favorite_tags test was collected:\n" + out[-2000:]
        )
        assert " passed" in out, "expected at least one passing favorite_tags test:\n" + out[-2000:]
