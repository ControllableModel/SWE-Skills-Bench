"""Benchmark test for skill: sqlalchemy-orm-patterns (variant ext10).

Task: Add a `Dashboard.drafts_by_user(user)` classmethod to redash's ORM model
(`redash/models/__init__.py`) that returns the given user's *unpublished* (draft),
*non-archived* dashboards, ordered by ascending dashboard `id`.

Selection rules derived from the variant requirement doc:
  * Only dashboards owned by the given ``user`` may appear.
  * Only dashboards with ``is_draft`` true may appear (published ones excluded).
  * Archived dashboards are excluded even when they are drafts of the user.
  * Results are ordered by ascending ``id`` (deterministic).
  * Empty result (``list(...)`` empty) when the user has no draft dashboards.
  * Each qualifying dashboard appears exactly once; the call is read-only.

Verification strategy
---------------------
L1 checks confirm the deliverable model file exists, that ``drafts_by_user`` is
defined on the ``Dashboard`` class as a ``@classmethod`` taking exactly
``(cls, user)`` (verified by AST, not substring grep), and that the modified
module imports cleanly.

L2 checks DYNAMICALLY EXERCISE real behavior. Rather than trusting any test the
agent may have written, we drop our OWN focused pytest driver modules into the
repo's ``tests/models/`` directory (so they pick up the real DB-backed
``BaseTestCase`` + factory), seed ``Dashboard`` rows directly via the ORM, call
``Dashboard.drafts_by_user(...)``, and assert on the concrete returned rows.
Each driver runs under the repo's native ``pytest`` and we assert on
returncode + behavior.

A naive solution fails these tests, e.g. one that:
  * returns ``Dashboard.by_user`` unchanged (includes published dashboards),
  * forgets the archived filter,
  * leaks dashboards owned by other users,
  * returns rows in nondeterministic / wrong order,
  * hardcodes a fixed list, or returns a non-empty value when there are no drafts.

Finally one L2 case drives the task's native acceptance command directly:
``pytest tests/models/test_dashboards.py -k drafts_by_user``.
"""

import ast
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/redash"
MODELS_FILE = os.path.join(REPO_DIR, "redash", "models", "__init__.py")
MODELS_TESTS_DIR = os.path.join(REPO_DIR, "tests", "models")
DASHBOARDS_TEST_FILE = os.path.join(MODELS_TESTS_DIR, "test_dashboards.py")

# Files we inject into the repo so we can clean them up afterwards.
_INJECTED = []


def _write_driver(name, body):
    """Write a pytest driver module into tests/models/ and remember it."""
    path = os.path.join(MODELS_TESTS_DIR, name)
    with open(path, "w") as fh:
        fh.write(body)
    _INJECTED.append(path)
    return path


def _run_pytest(target, timeout=600, extra=None):
    """Run the repo's native pytest against `target` (path relative to REPO_DIR)."""
    cmd = ["python", "-m", "pytest", target, "-v", "--tb=short", "-p", "no:cacheprovider"]
    if extra:
        cmd.extend(extra)
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
            if "drafts_driver" in f:
                try:
                    os.remove(os.path.join(pycache, f))
                except OSError:
                    pass


# Shared driver preamble: seed helpers used by several scenarios.  The factory's
# create_dashboard accepts user=, is_draft=, is_archived=.  Note that the factory
# default for is_draft is False (published), so drafts must be requested
# explicitly.  We flush after creation so ids are assigned deterministically.
_PREAMBLE = '''\
from redash.models import Dashboard, db
from tests import BaseTestCase


class _DraftsBase(BaseTestCase):
    def make_dashboard(self, user=None, is_draft=True, is_archived=False, name="d"):
        d = self.factory.create_dashboard(
            user=user or self.factory.user,
            is_draft=is_draft,
            is_archived=is_archived,
            name=name,
        )
        db.session.flush()
        return d

    def result(self, user):
        return list(Dashboard.drafts_by_user(user))
'''


class TestSqlalchemyOrmPatterns:
    REPO_DIR = "/workspace/redash"

    # ------------------------------------------------------------------ L1

    def test_models_file_exists(self):
        """L1: the model module to be modified exists."""
        assert os.path.isfile(MODELS_FILE), f"missing {MODELS_FILE}"

    def test_models_dir_and_test_file_present(self):
        """L1: tests/models dir and the target test file exist (for native run)."""
        assert os.path.isdir(MODELS_TESTS_DIR), f"missing {MODELS_TESTS_DIR}"
        assert os.path.isfile(DASHBOARDS_TEST_FILE), (
            "tests/models/test_dashboards.py must exist"
        )

    def test_drafts_by_user_classmethod_signature(self):
        """L1: `drafts_by_user` is defined on the Dashboard class as a classmethod
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
            if isinstance(item, ast.FunctionDef) and item.name == "drafts_by_user":
                method = item
                break
        assert method is not None, "Dashboard.drafts_by_user method not defined"

        decorators = {
            d.id for d in method.decorator_list if isinstance(d, ast.Name)
        }
        assert "classmethod" in decorators, "drafts_by_user must be a @classmethod"

        argnames = [a.arg for a in method.args.args]
        assert argnames == ["cls", "user"], (
            f"drafts_by_user signature must be (cls, user); got {argnames}"
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

    def test_draft_excludes_published(self):
        """L2: user authors draft A and published B -> only A appears.

        Discriminates a stub that simply returns ``Dashboard.by_user`` (which
        would also include the published dashboard)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class DraftsExcludePublished(_DraftsBase):
                def test_only_draft(self):
                    user = self.factory.user
                    a = self.make_dashboard(user=user, is_draft=True, name="A")
                    b = self.make_dashboard(user=user, is_draft=False, name="B")
                    res = self.result(user)
                    assert a in res, ("draft A missing", [d.id for d in res])
                    assert b not in res, ("published B leaked", [d.id for d in res])
                    assert len(res) == 1, [d.id for d in res]
        ''')
        _write_driver("test_drafts_driver_published.py", driver)
        proc = _run_pytest("tests/models/test_drafts_driver_published.py")
        assert proc.returncode == 0, (
            "published-exclusion failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_ordering_by_ascending_id(self):
        """L2: drafts A then C (in id order) -> result is exactly [A, C]."""
        driver = _PREAMBLE + textwrap.dedent('''
            class DraftsOrdering(_DraftsBase):
                def test_ascending_id(self):
                    user = self.factory.user
                    a = self.make_dashboard(user=user, is_draft=True, name="A")
                    c = self.make_dashboard(user=user, is_draft=True, name="C")
                    # Sanity: ids assigned in creation order.
                    assert a.id < c.id, (a.id, c.id)
                    res = self.result(user)
                    assert res == [a, c], [d.id for d in res]
                    assert [d.id for d in res] == sorted(d.id for d in res)
        ''')
        _write_driver("test_drafts_driver_order.py", driver)
        proc = _run_pytest("tests/models/test_drafts_driver_order.py")
        assert proc.returncode == 0, (
            "ordering-by-id failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_archived_drafts_excluded(self):
        """L2: a draft authored by the user that is archived must NOT appear.

        Discriminates a solution that filters on is_draft but forgets the
        is_archived filter."""
        driver = _PREAMBLE + textwrap.dedent('''
            class DraftsArchived(_DraftsBase):
                def test_archived_excluded(self):
                    user = self.factory.user
                    live = self.make_dashboard(user=user, is_draft=True,
                                               is_archived=False, name="live")
                    arch = self.make_dashboard(user=user, is_draft=True,
                                               is_archived=True, name="arch")
                    res = self.result(user)
                    assert live in res, [d.id for d in res]
                    assert arch not in res, ("archived draft leaked", [d.id for d in res])
                    assert len(res) == 1, [d.id for d in res]
        ''')
        _write_driver("test_drafts_driver_archived.py", driver)
        proc = _run_pytest("tests/models/test_drafts_driver_archived.py")
        assert proc.returncode == 0, (
            "archived-exclusion failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_other_users_drafts_excluded(self):
        """L2: a draft authored by a DIFFERENT user must not appear in this
        user's result, and the other user sees only their own draft."""
        driver = _PREAMBLE + textwrap.dedent('''
            class DraftsOtherUser(_DraftsBase):
                def test_cross_user(self):
                    user = self.factory.user
                    other = self.factory.create_user()
                    db.session.flush()
                    mine = self.make_dashboard(user=user, is_draft=True, name="mine")
                    theirs = self.make_dashboard(user=other, is_draft=True, name="theirs")
                    mine_res = self.result(user)
                    assert mine in mine_res, [d.id for d in mine_res]
                    assert theirs not in mine_res, ("other user's draft leaked",
                                                    [d.id for d in mine_res])
                    other_res = self.result(other)
                    assert theirs in other_res, [d.id for d in other_res]
                    assert mine not in other_res, [d.id for d in other_res]
        ''')
        _write_driver("test_drafts_driver_otheruser.py", driver)
        proc = _run_pytest("tests/models/test_drafts_driver_otheruser.py")
        assert proc.returncode == 0, (
            "cross-user isolation failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_empty_when_no_drafts(self):
        """L2: a user whose only dashboards are published/archived -> empty list.

        Discriminates a hardcoded non-empty return."""
        driver = _PREAMBLE + textwrap.dedent('''
            class DraftsEmpty(_DraftsBase):
                def test_no_drafts(self):
                    user = self.factory.user
                    # Published (not a draft).
                    self.make_dashboard(user=user, is_draft=False, name="pub")
                    # Archived draft (excluded).
                    self.make_dashboard(user=user, is_draft=True,
                                        is_archived=True, name="arch")
                    res = self.result(user)
                    assert res == [], [d.id for d in res]

                def test_user_with_nothing(self):
                    other = self.factory.create_user()
                    db.session.flush()
                    assert self.result(other) == []
        ''')
        _write_driver("test_drafts_driver_empty.py", driver)
        proc = _run_pytest("tests/models/test_drafts_driver_empty.py")
        assert proc.returncode == 0, (
            "empty-when-no-drafts failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_each_qualifying_dashboard_appears_once(self):
        """L2: every qualifying draft appears exactly once (no duplicate rows
        introduced by joins), in ascending id order, alongside excluded ones."""
        driver = _PREAMBLE + textwrap.dedent('''
            class DraftsUnique(_DraftsBase):
                def test_no_duplicates(self):
                    user = self.factory.user
                    other = self.factory.create_user()
                    db.session.flush()
                    a = self.make_dashboard(user=user, is_draft=True, name="A")
                    # noise: published, archived-draft, other user's draft
                    self.make_dashboard(user=user, is_draft=False, name="pub")
                    self.make_dashboard(user=user, is_draft=True,
                                        is_archived=True, name="arch")
                    self.make_dashboard(user=other, is_draft=True, name="other")
                    b = self.make_dashboard(user=user, is_draft=True, name="B")
                    res = self.result(user)
                    ids = [d.id for d in res]
                    assert ids == sorted(ids), ids
                    assert len(ids) == len(set(ids)), ("duplicate rows", ids)
                    assert res == [a, b], ids
        ''')
        _write_driver("test_drafts_driver_unique.py", driver)
        proc = _run_pytest("tests/models/test_drafts_driver_unique.py")
        assert proc.returncode == 0, (
            "uniqueness/ordering with noise failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_returns_dashboard_instances_and_is_iterable(self):
        """L2: list(drafts_by_user(user)) yields actual Dashboard instances whose
        attributes confirm they are the user's non-archived drafts."""
        driver = _PREAMBLE + textwrap.dedent('''
            class DraftsShape(_DraftsBase):
                def test_shape(self):
                    user = self.factory.user
                    self.make_dashboard(user=user, is_draft=True, name="A")
                    self.make_dashboard(user=user, is_draft=True, name="B")
                    res = self.result(user)
                    assert isinstance(res, list)
                    assert len(res) == 2, [d.id for d in res]
                    for d in res:
                        assert isinstance(d, Dashboard), type(d)
                        assert d.is_draft is True, d.is_draft
                        assert d.is_archived is False, d.is_archived
                        assert d.user_id == user.id, (d.user_id, user.id)
        ''')
        _write_driver("test_drafts_driver_shape.py", driver)
        proc = _run_pytest("tests/models/test_drafts_driver_shape.py")
        assert proc.returncode == 0, (
            "shape/iterability failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_does_not_mutate_db(self):
        """L2: repeated calls are read-only -- results stable and the underlying
        dashboard row count is unchanged."""
        driver = _PREAMBLE + textwrap.dedent('''
            class DraftsReadOnly(_DraftsBase):
                def test_read_only(self):
                    user = self.factory.user
                    a = self.make_dashboard(user=user, is_draft=True, name="A")
                    b = self.make_dashboard(user=user, is_draft=True, name="B")
                    self.make_dashboard(user=user, is_draft=False, name="pub")
                    before = Dashboard.query.count()
                    r1 = self.result(user)
                    r2 = self.result(user)
                    r3 = self.result(user)
                    assert r1 == r2 == r3 == [a, b], (
                        [d.id for d in r1], [d.id for d in r2], [d.id for d in r3]
                    )
                    assert Dashboard.query.count() == before
        ''')
        _write_driver("test_drafts_driver_readonly.py", driver)
        proc = _run_pytest("tests/models/test_drafts_driver_readonly.py")
        assert proc.returncode == 0, (
            "read-only / idempotence check failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_published_and_archived_combined_filter(self):
        """L2: only the live draft survives a mix of published, archived-published,
        and archived-draft dashboards owned by the same user."""
        driver = _PREAMBLE + textwrap.dedent('''
            class DraftsCombined(_DraftsBase):
                def test_combined(self):
                    user = self.factory.user
                    live_draft = self.make_dashboard(user=user, is_draft=True,
                                                     is_archived=False, name="live")
                    self.make_dashboard(user=user, is_draft=False,
                                        is_archived=False, name="pub")
                    self.make_dashboard(user=user, is_draft=False,
                                        is_archived=True, name="pub_arch")
                    self.make_dashboard(user=user, is_draft=True,
                                        is_archived=True, name="draft_arch")
                    res = self.result(user)
                    assert res == [live_draft], [d.id for d in res]
        ''')
        _write_driver("test_drafts_driver_combined.py", driver)
        proc = _run_pytest("tests/models/test_drafts_driver_combined.py")
        assert proc.returncode == 0, (
            "combined-filter failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_agent_test_file_passes_native_command(self):
        """L2: the agent's own additions to tests/models/test_dashboards.py for
        drafts_by_user must pass under the task's native acceptance command
        (`pytest tests/models/test_dashboards.py -k drafts_by_user`), and the
        full file must still pass.

        We require at least one matching test to have been collected & passed."""
        proc = _run_pytest(
            "tests/models/test_dashboards.py",
            timeout=600,
            extra=["-k", "drafts_by_user"],
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "agent's drafts_by_user tests did not pass:\n" + out[-4000:]
        )
        assert "no tests ran" not in out.lower(), (
            "no drafts_by_user test was collected:\n" + out[-2000:]
        )
        assert " passed" in out, (
            "expected at least one passing drafts_by_user test:\n" + out[-2000:]
        )

    def test_full_dashboards_test_file_still_passes(self):
        """L2: the entire tests/models/test_dashboards.py file must continue to
        pass, guarding against regressions introduced by the agent's edits."""
        proc = _run_pytest("tests/models/test_dashboards.py", timeout=900)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "full test_dashboards.py did not pass:\n" + out[-4000:]
        )
        assert " passed" in out, (
            "expected passing tests in test_dashboards.py:\n" + out[-2000:]
        )
