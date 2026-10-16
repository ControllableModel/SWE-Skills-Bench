"""Benchmark test for skill: sqlalchemy-orm-patterns (variant ext3).

Task
----
Add a classmethod ``User.pending_in_org(cls, org)`` to redash's ORM model
(``redash/models/users.py``) that returns the organization's *enabled* users
whose invitation is still pending, ordered by ascending ``id``.

Selection rules (from the variant requirement doc):
  * only users whose ``is_invitation_pending`` JSON-derived value is true qualify
    (false OR absent => excluded),
  * only users belonging to the given ``org`` may appear (no cross-org leakage),
  * disabled users (``disabled_at`` not NULL) are excluded,
  * results are ordered by ascending user ``id``,
  * empty result when no user qualifies; ``len(list(...))`` reflects the count;
  * the call must not mutate the database and takes exactly one arg beyond cls.

Verification strategy
---------------------
L1 checks confirm the deliverable file exists, ``pending_in_org`` is defined on
the ``User`` class as a ``@classmethod`` with the exact signature ``(cls, org)``
(verified via AST, not substring grep), and the modified module imports cleanly.

L2 checks DYNAMICALLY EXERCISE the real behavior. Rather than trusting any test
the agent may have written, we drop our OWN focused pytest driver modules into
the repo's ``tests/models/`` directory (so they pick up the real DB-backed
``BaseTestCase`` + ``self.factory``), seed ``User`` rows directly via the ORM
with explicit invitation/disabled/org states, call ``User.pending_in_org(org)``,
and assert on the concrete returned rows / ordering / counts.

A naive solution fails these tests, including: returning all org users, ignoring
the pending flag, ignoring the disabled flag, leaking other-org users, returning
an unordered/reverse-ordered iterable, hardcoding a fixed list, or mutating the
DB.

The final L2 method drives the variant's native acceptance command verbatim:
``pytest tests/models/test_users.py -k pending_in_org`` (and asserts the full
file still passes), validating the agent's own added tests.
"""

import ast
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/redash"
USERS_FILE = os.path.join(REPO_DIR, "redash", "models", "users.py")
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
    pycache = os.path.join(MODELS_TESTS_DIR, "__pycache__")
    if os.path.isdir(pycache):
        for f in os.listdir(pycache):
            if "pending_driver" in f:
                try:
                    os.remove(os.path.join(pycache, f))
                except OSError:
                    pass


# Shared driver preamble: seed helpers used by several scenarios.
# `make_user` seeds a User scoped to a given org with explicit invitation and
# disabled state by writing the JSON `details` column directly, mirroring how
# `is_invitation_pending` (a json_cast_property over details) is stored.
_PREAMBLE = '''\
from redash.models import User, db
from tests import BaseTestCase


class _PendingBase(BaseTestCase):
    _seq = 0

    def make_user(self, org=None, pending=False, disabled=False, set_flag=True):
        org = org or self.factory.org
        _PendingBase._seq += 1
        email = "pend{}@example.com".format(_PendingBase._seq)
        details = {}
        if set_flag:
            details["is_invitation_pending"] = bool(pending)
        # else: leave the key absent entirely (tests the "absent" case).
        u = self.factory.create_user(org=org, email=email, details=details)
        if disabled:
            u.disabled_at = db.func.now()
        db.session.add(u)
        db.session.flush()
        return u

    def result(self, org):
        return list(User.pending_in_org(org))

    def ids(self, org):
        return [u.id for u in User.pending_in_org(org)]
'''


class TestSqlalchemyOrmPatterns:
    REPO_DIR = "/workspace/redash"

    # ------------------------------------------------------------------ L1

    def test_users_model_file_exists(self):
        """L1: the model module to be modified exists."""
        assert os.path.isfile(USERS_FILE), f"missing {USERS_FILE}"

    def test_models_dir_and_test_file_present(self):
        """L1: the tests/models dir and the target test file exist (for native run)."""
        assert os.path.isdir(MODELS_TESTS_DIR), f"missing {MODELS_TESTS_DIR}"
        assert os.path.isfile(
            os.path.join(MODELS_TESTS_DIR, "test_users.py")
        ), "tests/models/test_users.py must exist"

    def test_pending_in_org_classmethod_signature(self):
        """L1: `pending_in_org` is defined on the User class as a @classmethod
        taking exactly (cls, org) -- verified via AST, not substring grep."""
        with open(USERS_FILE) as fh:
            tree = ast.parse(fh.read())

        user_cls = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "User":
                user_cls = node
                break
        assert user_cls is not None, "class User not found in users.py"

        method = None
        for item in user_cls.body:
            if isinstance(item, ast.FunctionDef) and item.name == "pending_in_org":
                method = item
                break
        assert method is not None, "User.pending_in_org method not defined"

        decorators = {
            d.id for d in method.decorator_list if isinstance(d, ast.Name)
        }
        assert "classmethod" in decorators, "pending_in_org must be a @classmethod"

        argnames = [a.arg for a in method.args.args]
        assert argnames == ["cls", "org"], (
            f"pending_in_org signature must be (cls, org); got {argnames}"
        )
        # Exactly one argument beyond cls (no extra positional params).
        assert method.args.vararg is None, "pending_in_org must not take *args"
        assert not method.args.kwonlyargs, "pending_in_org must not take kw-only args"

    def test_models_module_imports(self):
        """L1: the modified models module imports cleanly (no syntax/import error)."""
        proc = subprocess.run(
            ["python", "-c", "import redash.models.users"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "PYTHONPATH": REPO_DIR},
        )
        assert proc.returncode == 0, (
            "importing redash.models.users failed:\n" + proc.stdout + proc.stderr
        )

    # ------------------------------------------------------------------ L2

    def test_pending_selected_nonpending_excluded(self):
        """L2: a pending user X is returned; a non-pending user Y is excluded."""
        driver = _PREAMBLE + textwrap.dedent('''
            class PendingBasic(_PendingBase):
                def test_basic(self):
                    org = self.factory.org
                    x = self.make_user(org=org, pending=True)
                    y = self.make_user(org=org, pending=False)
                    res = self.result(org)
                    res_ids = [u.id for u in res]
                    assert x.id in res_ids, res_ids
                    assert y.id not in res_ids, res_ids
                    # Every returned user is genuinely pending and in this org.
                    for u in res:
                        assert u.org_id == org.id
                        assert u.is_invitation_pending is True
        ''')
        _write_driver("test_pending_driver_basic.py", driver)
        proc = _run_pytest("tests/models/test_pending_driver_basic.py")
        assert proc.returncode == 0, (
            "pending-selected/non-pending-excluded failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_absent_flag_excluded(self):
        """L2: a user with NO is_invitation_pending key at all is excluded
        (the doc treats 'absent' the same as false)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class PendingAbsent(_PendingBase):
                def test_absent(self):
                    org = self.factory.org
                    pend = self.make_user(org=org, pending=True)
                    absent = self.make_user(org=org, set_flag=False)
                    res_ids = self.ids(org)
                    assert pend.id in res_ids, res_ids
                    assert absent.id not in res_ids, res_ids
        ''')
        _write_driver("test_pending_driver_absent.py", driver)
        proc = _run_pytest("tests/models/test_pending_driver_absent.py")
        assert proc.returncode == 0, (
            "absent-flag-excluded failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_ordering_by_ascending_id(self):
        """L2: two pending users P then Q (created in that id order) come back as
        [P, Q] -- exact ascending-id ordering, discriminating reverse/unordered."""
        driver = _PREAMBLE + textwrap.dedent('''
            class PendingOrder(_PendingBase):
                def test_order(self):
                    org = self.factory.org
                    p = self.make_user(org=org, pending=True)
                    q = self.make_user(org=org, pending=True)
                    assert p.id < q.id, (p.id, q.id)
                    res_ids = self.ids(org)
                    assert res_ids == sorted(res_ids), res_ids
                    # P must come before Q in the result.
                    assert res_ids.index(p.id) < res_ids.index(q.id), res_ids
                    assert res_ids == [p.id, q.id], res_ids
        ''')
        _write_driver("test_pending_driver_order.py", driver)
        proc = _run_pytest("tests/models/test_pending_driver_order.py")
        assert proc.returncode == 0, (
            "ascending-id ordering failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_disabled_pending_user_excluded(self):
        """L2: a pending user who is DISABLED must not appear in the result."""
        driver = _PREAMBLE + textwrap.dedent('''
            class PendingDisabled(_PendingBase):
                def test_disabled_excluded(self):
                    org = self.factory.org
                    active = self.make_user(org=org, pending=True)
                    dead = self.make_user(org=org, pending=True, disabled=True)
                    res_ids = self.ids(org)
                    assert active.id in res_ids, res_ids
                    assert dead.id not in res_ids, res_ids
                    for u in self.result(org):
                        assert u.disabled_at is None, u.disabled_at
        ''')
        _write_driver("test_pending_driver_disabled.py", driver)
        proc = _run_pytest("tests/models/test_pending_driver_disabled.py")
        assert proc.returncode == 0, (
            "disabled-pending-user-excluded failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_cross_org_isolation(self):
        """L2: a pending user in a DIFFERENT org must never appear in this org's
        result, and vice-versa."""
        driver = _PREAMBLE + textwrap.dedent('''
            class PendingCrossOrg(_PendingBase):
                def test_cross_org(self):
                    org_a = self.factory.org
                    org_b = self.factory.create_org()
                    a = self.make_user(org=org_a, pending=True)
                    b = self.make_user(org=org_b, pending=True)
                    a_ids = self.ids(org_a)
                    b_ids = self.ids(org_b)
                    assert a.id in a_ids, a_ids
                    assert b.id not in a_ids, a_ids
                    assert b.id in b_ids, b_ids
                    assert a.id not in b_ids, b_ids
                    for u in self.result(org_a):
                        assert u.org_id == org_a.id
        ''')
        _write_driver("test_pending_driver_crossorg.py", driver)
        proc = _run_pytest("tests/models/test_pending_driver_crossorg.py")
        assert proc.returncode == 0, (
            "cross-org isolation failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_empty_when_none_qualify(self):
        """L2: an org with users present but none pending -> list(...) is empty."""
        driver = _PREAMBLE + textwrap.dedent('''
            class PendingEmpty(_PendingBase):
                def test_empty(self):
                    org = self.factory.org
                    self.make_user(org=org, pending=False)
                    self.make_user(org=org, set_flag=False)
                    self.make_user(org=org, pending=True, disabled=True)
                    res = self.result(org)
                    assert res == [], res
                    assert len(res) == 0, res
        ''')
        _write_driver("test_pending_driver_empty.py", driver)
        proc = _run_pytest("tests/models/test_pending_driver_empty.py")
        assert proc.returncode == 0, (
            "empty-when-none-qualify failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_count_reflects_qualifying_users(self):
        """L2: len(list(...)) equals the exact number of qualifying users amid a
        mix of pending/non-pending/disabled/other-org noise."""
        driver = _PREAMBLE + textwrap.dedent('''
            class PendingCount(_PendingBase):
                def test_count(self):
                    org = self.factory.org
                    other = self.factory.create_org()
                    # 3 qualifying
                    q1 = self.make_user(org=org, pending=True)
                    q2 = self.make_user(org=org, pending=True)
                    q3 = self.make_user(org=org, pending=True)
                    # noise: must all be excluded
                    self.make_user(org=org, pending=False)
                    self.make_user(org=org, set_flag=False)
                    self.make_user(org=org, pending=True, disabled=True)
                    self.make_user(org=other, pending=True)
                    res_ids = self.ids(org)
                    assert len(res_ids) == 3, res_ids
                    assert set(res_ids) == {q1.id, q2.id, q3.id}, res_ids
                    # still ascending order
                    assert res_ids == sorted(res_ids), res_ids
        ''')
        _write_driver("test_pending_driver_count.py", driver)
        proc = _run_pytest("tests/models/test_pending_driver_count.py")
        assert proc.returncode == 0, (
            "count-reflects-qualifying-users failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_returns_user_objects(self):
        """L2: the result yields real User ORM instances (not ids/dicts/tuples),
        each carrying the queried org_id and a true pending flag."""
        driver = _PREAMBLE + textwrap.dedent('''
            from redash.models import User as _U

            class PendingShape(_PendingBase):
                def test_shape(self):
                    org = self.factory.org
                    self.make_user(org=org, pending=True)
                    self.make_user(org=org, pending=True)
                    res = self.result(org)
                    assert len(res) == 2, res
                    for u in res:
                        assert isinstance(u, _U), type(u)
                        assert u.org_id == org.id
                        assert u.is_invitation_pending is True
                        assert u.disabled_at is None
        ''')
        _write_driver("test_pending_driver_shape.py", driver)
        proc = _run_pytest("tests/models/test_pending_driver_shape.py")
        assert proc.returncode == 0, (
            "returns-user-objects failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_read_only_and_idempotent(self):
        """L2: calling pending_in_org repeatedly is read-only -- stable results and
        no change to the underlying User row count."""
        driver = _PREAMBLE + textwrap.dedent('''
            class PendingReadOnly(_PendingBase):
                def test_read_only(self):
                    org = self.factory.org
                    self.make_user(org=org, pending=True)
                    self.make_user(org=org, pending=True)
                    self.make_user(org=org, pending=False)
                    before = User.query.count()
                    r1 = self.ids(org)
                    r2 = self.ids(org)
                    r3 = self.ids(org)
                    assert r1 == r2 == r3, (r1, r2, r3)
                    assert len(r1) == 2, r1
                    assert User.query.count() == before, User.query.count()
        ''')
        _write_driver("test_pending_driver_readonly.py", driver)
        proc = _run_pytest("tests/models/test_pending_driver_readonly.py")
        assert proc.returncode == 0, (
            "read-only/idempotence check failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_combined_matrix(self):
        """L2: a full matrix across two orgs exercising every rule at once.

        Discriminates any solution that drops one of the four filters (pending,
        enabled, org-scope, ordering)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class PendingMatrix(_PendingBase):
                def test_matrix(self):
                    org = self.factory.org
                    other = self.factory.create_org()
                    p1 = self.make_user(org=org, pending=True)        # keep
                    np = self.make_user(org=org, pending=False)       # drop: not pending
                    ab = self.make_user(org=org, set_flag=False)      # drop: absent
                    dis = self.make_user(org=org, pending=True, disabled=True)  # drop: disabled
                    p2 = self.make_user(org=org, pending=True)        # keep
                    xo = self.make_user(org=other, pending=True)      # drop: other org
                    res_ids = self.ids(org)
                    assert res_ids == [p1.id, p2.id], res_ids
                    for bad in (np.id, ab.id, dis.id, xo.id):
                        assert bad not in res_ids, (bad, res_ids)
        ''')
        _write_driver("test_pending_driver_matrix.py", driver)
        proc = _run_pytest("tests/models/test_pending_driver_matrix.py")
        assert proc.returncode == 0, (
            "combined-matrix failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_native_acceptance_command(self):
        """L2: the agent's own additions to tests/models/test_users.py for
        pending_in_org must pass under the variant's native acceptance command:
        `pytest tests/models/test_users.py -k pending_in_org`. We require at
        least one matching test to have been collected & passed, and the full
        file must also pass."""
        # 1) Targeted native command from the Acceptance Criteria.
        proc = _run_pytest(
            "tests/models/test_users.py", extra=["-k", "pending_in_org"], timeout=600
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "agent's pending_in_org tests did not pass:\n" + out[-4000:]
        )
        assert "no tests ran" not in out.lower(), (
            "no pending_in_org test was collected:\n" + out[-2000:]
        )
        assert " passed" in out, (
            "expected at least one passing pending_in_org test:\n" + out[-2000:]
        )

        # 2) The whole file must also continue to pass (no regressions).
        full = _run_pytest("tests/models/test_users.py", timeout=900)
        full_out = full.stdout + full.stderr
        assert full.returncode == 0, (
            "full tests/models/test_users.py did not pass:\n" + full_out[-4000:]
        )
