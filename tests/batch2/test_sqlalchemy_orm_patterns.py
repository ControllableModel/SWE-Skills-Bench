"""Benchmark test for skill: sqlalchemy-orm-patterns (variant ext2).

Task: Add a `Dashboard.owned_tags(user)` classmethod to redash's ORM model
(`redash/models/__init__.py`) that returns per-tag usage counts restricted to
the dashboards the given user has actually authored (owns), excluding archived
dashboards and dashboards owned by other users, ordered alphabetically by tag.

This is a DIFFERENT task from ext1 (which targeted `Query.favorite_tags` and a
Favorite-based query). Here the deliverable is `Dashboard.owned_tags`, scoped by
ownership (`Dashboard.user_id == user.id`) and excluding archived dashboards.

Verification strategy
---------------------
L1 checks confirm the deliverable file exists, the classmethod is defined on the
`Dashboard` class with the exact required signature `(cls, user)`, and the
modified source still imports cleanly (no syntax/import error) -- all verified via
AST and subprocess import, not substring grep.

L2 checks DYNAMICALLY EXERCISE the real behavior. Rather than trusting any test
the agent may have written, we drop our OWN focused pytest driver modules into the
repo's `tests/models/` directory (so they pick up the real DB-backed
`BaseTestCase` + `Factory`), seed Dashboard rows directly via the ORM (with
specific owners, tags, and archived flags), call `Dashboard.owned_tags(...)`, and
assert on the concrete returned rows. Each driver is run with the repo's native
`pytest` and we assert on returncode + behavior.

A naive solution (hardcoded list, keyword-matched stub, counting ALL visible
dashboards instead of only the user's own -- e.g. mirroring `all_tags` --, leaking
another user's dashboards, including archived dashboards, wrong ordering, or
mishandling null/empty tags) fails these tests.
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
            if "owned_tags_driver" in f or "ownedtags_driver" in f:
                try:
                    os.remove(os.path.join(pycache, f))
                except OSError:
                    pass


# Shared driver preamble: seed helpers used by several scenarios.
#
# Notes on seeding semantics:
# * Dashboards are owned via `user=` (sets user_id). The factory default owner is
#   `self.factory.user`, so we pass `user=` explicitly when ownership matters.
# * Archiving is done by setting `is_archived = True` on the row, mirroring the
#   model's own `archive()` behavior, then flushing.
_PREAMBLE = '''\
from redash.models import Dashboard, db
from tests import BaseTestCase


class _OwnedTagsBase(BaseTestCase):
    def make_dashboard(self, tags, user=None, archived=False):
        owner = user if user is not None else self.factory.user
        dash = self.factory.create_dashboard(tags=tags, user=owner)
        if archived:
            dash.is_archived = True
        db.session.add(dash)
        db.session.flush()
        return dash

    def result(self, user):
        return list(Dashboard.owned_tags(user))
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
            os.path.join(MODELS_TESTS_DIR, "test_dashboards.py")
        ), "tests/models/test_dashboards.py must exist"

    def test_owned_tags_classmethod_signature(self):
        """L1: `owned_tags` is defined on the Dashboard class as a classmethod
        taking exactly (cls, user) -- verified via AST, not substring grep."""
        with open(MODELS_FILE) as fh:
            tree = ast.parse(fh.read())

        dashboard_cls = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "Dashboard":
                dashboard_cls = node
                break
        assert dashboard_cls is not None, "class Dashboard not found in models"

        method = None
        for item in dashboard_cls.body:
            if isinstance(item, ast.FunctionDef) and item.name == "owned_tags":
                method = item
                break
        assert method is not None, "Dashboard.owned_tags method not defined"

        decorators = {
            d.id for d in method.decorator_list if isinstance(d, ast.Name)
        }
        assert "classmethod" in decorators, "owned_tags must be a @classmethod"

        argnames = [a.arg for a in method.args.args]
        assert argnames == ["cls", "user"], (
            f"owned_tags signature must be (cls, user); got {argnames}"
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
        """L2: two owned dashboards -> alphabetically ordered (tag, count) rows.

        A: ['alpha','beta'], B: ['beta'] -> [('alpha',1),('beta',2)]."""
        driver = _PREAMBLE + textwrap.dedent('''
            class OwnedTagsBasic(_OwnedTagsBase):
                def test_basic(self):
                    user = self.factory.user
                    self.make_dashboard(tags=["alpha", "beta"], user=user)
                    self.make_dashboard(tags=["beta"], user=user)
                    res = self.result(user)
                    assert res == [("alpha", 1), ("beta", 2)], res
        ''')
        _write_driver("test_owned_tags_driver_basic.py", driver)
        proc = _run_pytest("tests/models/test_owned_tags_driver_basic.py")
        assert proc.returncode == 0, (
            "basic counts/ordering failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_returns_tuples_and_is_iterable(self):
        """L2: list(owned_tags(user)) yields 2-tuples of (str, int)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class OwnedTagsShape(_OwnedTagsBase):
                def test_shape(self):
                    user = self.factory.user
                    self.make_dashboard(tags=["gamma", "delta"], user=user)
                    res = self.result(user)
                    assert isinstance(res, list)
                    assert len(res) == 2, res
                    for row in res:
                        assert len(row) == 2, row
                        tag, count = row
                        assert isinstance(tag, str), type(tag)
                        assert isinstance(count, int), type(count)
                    assert res == [("delta", 1), ("gamma", 1)], res
        ''')
        _write_driver("test_owned_tags_driver_shape.py", driver)
        proc = _run_pytest("tests/models/test_owned_tags_driver_shape.py")
        assert proc.returncode == 0, (
            "shape/iterability failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_only_owned_dashboards_counted(self):
        """L2: a dashboard owned by a DIFFERENT user must not affect this user,
        even when both carry the same tag.

        Discriminates a solution that counts all *visible* dashboards rather than
        only the user's own (i.e. one that mirrors `all_tags`)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class OwnedTagsOtherUser(_OwnedTagsBase):
                def test_other_user(self):
                    user = self.factory.user
                    other = self.factory.create_user()
                    db.session.flush()
                    self.make_dashboard(tags=["zeta"], user=user)
                    self.make_dashboard(tags=["zeta"], user=other)
                    # First user sees only their own dashboard's tag.
                    assert self.result(user) == [("zeta", 1)], self.result(user)
                    # The other user sees their own single dashboard.
                    assert self.result(other) == [("zeta", 1)], self.result(other)
        ''')
        _write_driver("test_owned_tags_driver_otheruser.py", driver)
        proc = _run_pytest("tests/models/test_owned_tags_driver_otheruser.py")
        assert proc.returncode == 0, (
            "ownership isolation failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_other_users_dashboard_does_not_leak_extra_tags(self):
        """L2: a tag that exists ONLY on another user's dashboard must not appear
        in this user's result at all.

        Strongly discriminates an `all_tags`-style implementation that ignores
        ownership: such an impl would surface 'foreign' here."""
        driver = _PREAMBLE + textwrap.dedent('''
            class OwnedTagsNoLeak(_OwnedTagsBase):
                def test_no_leak(self):
                    user = self.factory.user
                    other = self.factory.create_user()
                    db.session.flush()
                    self.make_dashboard(tags=["mine"], user=user)
                    # 'foreign' exists only on the other user's dashboard.
                    self.make_dashboard(tags=["foreign"], user=other)
                    res = self.result(user)
                    tags = [t for (t, _c) in res]
                    assert "foreign" not in tags, res
                    assert res == [("mine", 1)], res
        ''')
        _write_driver("test_owned_tags_driver_noleak.py", driver)
        proc = _run_pytest("tests/models/test_owned_tags_driver_noleak.py")
        assert proc.returncode == 0, (
            "foreign tag leaked into result:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_archived_dashboards_excluded(self):
        """L2: archived dashboards owned by the user must contribute nothing."""
        driver = _PREAMBLE + textwrap.dedent('''
            class OwnedTagsArchived(_OwnedTagsBase):
                def test_archived_only(self):
                    user = self.factory.user
                    self.make_dashboard(tags=["gone"], user=user, archived=True)
                    assert self.result(user) == [], self.result(user)

                def test_archived_plus_active(self):
                    user = self.factory.user
                    self.make_dashboard(tags=["keep"], user=user)
                    self.make_dashboard(tags=["gone"], user=user, archived=True)
                    # Archived 'gone' excluded; only active 'keep' remains.
                    assert self.result(user) == [("keep", 1)], self.result(user)

                def test_archived_same_tag_not_counted(self):
                    user = self.factory.user
                    self.make_dashboard(tags=["shared"], user=user)
                    self.make_dashboard(tags=["shared"], user=user, archived=True)
                    # Only the one active dashboard counts -> count of 1, not 2.
                    assert self.result(user) == [("shared", 1)], self.result(user)
        ''')
        _write_driver("test_owned_tags_driver_archived.py", driver)
        proc = _run_pytest("tests/models/test_owned_tags_driver_archived.py")
        assert proc.returncode == 0, (
            "archived dashboards not excluded:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_empty_when_no_owned_tagged_dashboards(self):
        """L2: a user who owns no tagged dashboards -> empty list (no rows, no error)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class OwnedTagsEmpty(_OwnedTagsBase):
                def test_no_dashboards(self):
                    user = self.factory.create_user()
                    db.session.flush()
                    # This user owns nothing at all.
                    assert self.result(user) == [], self.result(user)

                def test_only_other_users_dashboards(self):
                    user = self.factory.create_user()
                    other = self.factory.create_user()
                    db.session.flush()
                    self.make_dashboard(tags=["x", "y"], user=other)
                    # `user` owns nothing -> empty even though tags exist elsewhere.
                    assert self.result(user) == [], self.result(user)
        ''')
        _write_driver("test_owned_tags_driver_empty.py", driver)
        proc = _run_pytest("tests/models/test_owned_tags_driver_empty.py")
        assert proc.returncode == 0, (
            "empty result case failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_empty_and_null_tags_produce_no_rows(self):
        """L2: an owned dashboard with empty `[]` or NULL tags yields no rows and
        must not raise."""
        driver = _PREAMBLE + textwrap.dedent('''
            class OwnedTagsNullTags(_OwnedTagsBase):
                def test_empty_list_tags(self):
                    user = self.factory.user
                    self.make_dashboard(tags=[], user=user)
                    assert self.result(user) == [], self.result(user)

                def test_null_tags(self):
                    user = self.factory.user
                    self.make_dashboard(tags=None, user=user)
                    assert self.result(user) == [], self.result(user)

                def test_mix_null_and_real(self):
                    user = self.factory.user
                    self.make_dashboard(tags=None, user=user)
                    self.make_dashboard(tags=["real"], user=user)
                    assert self.result(user) == [("real", 1)], self.result(user)
        ''')
        _write_driver("test_owned_tags_driver_nulltags.py", driver)
        proc = _run_pytest("tests/models/test_owned_tags_driver_nulltags.py")
        assert proc.returncode == 0, (
            "empty/null tags handling failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_case_sensitivity_and_aggregation(self):
        """L2: tags are case-sensitive ('prod' != 'PROD'); per-tag counts aggregate
        across multiple owned dashboards; each distinct tag counted once/dashboard."""
        driver = _PREAMBLE + textwrap.dedent('''
            class OwnedTagsCase(_OwnedTagsBase):
                def test_case_and_aggregate(self):
                    user = self.factory.user
                    # 'PROD' appears in d1; 'prod' appears in d2 and d3 -> distinct.
                    self.make_dashboard(tags=["PROD", "etl"], user=user)
                    self.make_dashboard(tags=["prod", "etl"], user=user)
                    self.make_dashboard(tags=["prod"], user=user)
                    res = self.result(user)
                    # Ordered alphabetically; uppercase sorts before lowercase.
                    expected = [("PROD", 1), ("etl", 2), ("prod", 2)]
                    assert res == expected, res

                def test_same_tag_two_dashboards_counts_two(self):
                    user = self.factory.user
                    self.make_dashboard(tags=["dup"], user=user)
                    self.make_dashboard(tags=["dup"], user=user)
                    assert self.result(user) == [("dup", 2)], self.result(user)
        ''')
        _write_driver("test_owned_tags_driver_case.py", driver)
        proc = _run_pytest("tests/models/test_owned_tags_driver_case.py")
        assert proc.returncode == 0, (
            "case-sensitivity/aggregation failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_three_tags_single_dashboard(self):
        """L2: one owned dashboard with three tags contributes to three tag rows,
        each with count 1, ordered alphabetically."""
        driver = _PREAMBLE + textwrap.dedent('''
            class OwnedTagsThree(_OwnedTagsBase):
                def test_three(self):
                    user = self.factory.user
                    self.make_dashboard(tags=["mango", "apple", "lemon"], user=user)
                    assert self.result(user) == [("apple", 1), ("lemon", 1), ("mango", 1)], \
                        self.result(user)
        ''')
        _write_driver("test_owned_tags_driver_three.py", driver)
        proc = _run_pytest("tests/models/test_owned_tags_driver_three.py")
        assert proc.returncode == 0, (
            "three-tags-single-dashboard failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_combined_scenario_owner_archive_other(self):
        """L2: an end-to-end scenario combining ownership, archiving and a foreign
        user -- the toughest discriminator against naive impls."""
        driver = _PREAMBLE + textwrap.dedent('''
            class OwnedTagsCombined(_OwnedTagsBase):
                def test_combined(self):
                    user = self.factory.user
                    other = self.factory.create_user()
                    db.session.flush()
                    # Owned + active: contributes.
                    self.make_dashboard(tags=["alpha", "beta"], user=user)
                    self.make_dashboard(tags=["beta"], user=user)
                    # Owned but archived: excluded.
                    self.make_dashboard(tags=["alpha", "gamma"], user=user, archived=True)
                    # Other user's dashboards (active + archived): excluded entirely.
                    self.make_dashboard(tags=["alpha", "delta"], user=other)
                    self.make_dashboard(tags=["beta"], user=other, archived=True)
                    res = self.result(user)
                    # Only the two owned-active dashboards count:
                    #   alpha:1 (one active owned), beta:2.
                    assert res == [("alpha", 1), ("beta", 2)], res
        ''')
        _write_driver("test_owned_tags_driver_combined.py", driver)
        proc = _run_pytest("tests/models/test_owned_tags_driver_combined.py")
        assert proc.returncode == 0, (
            "combined ownership/archive/foreign scenario failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_does_not_mutate_db(self):
        """L2: calling owned_tags repeatedly is read-only -- it neither changes
        results nor alters the underlying dashboard rows."""
        driver = _PREAMBLE + textwrap.dedent('''
            class OwnedTagsReadOnly(_OwnedTagsBase):
                def test_read_only(self):
                    user = self.factory.user
                    self.make_dashboard(tags=["alpha", "beta"], user=user)
                    self.make_dashboard(tags=["beta"], user=user)
                    before = Dashboard.query.count()
                    r1 = self.result(user)
                    r2 = self.result(user)
                    r3 = self.result(user)
                    assert r1 == r2 == r3 == [("alpha", 1), ("beta", 2)], (r1, r2, r3)
                    assert Dashboard.query.count() == before
        ''')
        _write_driver("test_owned_tags_driver_readonly.py", driver)
        proc = _run_pytest("tests/models/test_owned_tags_driver_readonly.py")
        assert proc.returncode == 0, (
            "read-only / idempotence check failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_agent_test_file_passes_owned_tags_selection(self):
        """L2: the agent's own additions to tests/models/test_dashboards.py for
        owned_tags must pass under the native command from the task's
        Acceptance Criteria (`pytest tests/models/test_dashboards.py -k owned_tags`).

        We require at least one matching test to have been collected & passed."""
        cmd = [
            "python", "-m", "pytest", "tests/models/test_dashboards.py",
            "-k", "owned_tags", "-v", "--tb=short", "-p", "no:cacheprovider",
        ]
        proc = subprocess.run(
            cmd, cwd=REPO_DIR, capture_output=True, text=True, timeout=600,
            env={**os.environ, "PYTHONPATH": REPO_DIR},
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "agent's owned_tags tests did not pass:\n" + out[-4000:]
        )
        # Ensure tests were actually collected (no rubber-stamp "no tests ran").
        assert "no tests ran" not in out.lower(), (
            "no owned_tags test was collected:\n" + out[-2000:]
        )
        assert " passed" in out, "expected at least one passing owned_tags test:\n" + out[-2000:]
