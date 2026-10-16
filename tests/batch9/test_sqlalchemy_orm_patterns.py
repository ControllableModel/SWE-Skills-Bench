"""Benchmark test for skill: sqlalchemy-orm-patterns (variant ext9).

Task: Add a `Group.enabled_member_count(group_id)` classmethod to redash's ORM
model (`redash/models/users.py`) returning the number of *enabled* users whose
`group_ids` array contains `group_id`. Disabled users are excluded; a group with
no enabled members returns the integer `0`; users in several groups are counted
once per group they belong to. A test module `tests/models/test_groups.py` is
also added by the agent.

Verification strategy
---------------------
L1 checks confirm the deliverable file (`redash/models/users.py`) exists, that
`enabled_member_count` is defined on the `Group` class as a `@classmethod` with
the exact `(cls, group_id)` signature (verified via AST, not substring grep),
and that the modified module imports cleanly.

L2 checks DYNAMICALLY EXERCISE the real behavior. Rather than trusting any test
the agent wrote, we inject our OWN focused pytest driver modules into the repo's
`tests/models/` directory (so they bind to the real DB-backed `BaseTestCase` and
`self.factory`), seed `User`/`Group` rows directly through the ORM, call
`Group.enabled_member_count(...)`, and assert on the concrete integer returned.
Each driver runs under the repo's native `pytest`; we assert on returncode and
behavior.

A naive solution fails these tests, e.g. one that:
  * returns `Group.members(group_id).count()` (ignores disabled users),
  * hardcodes a constant / returns the query object instead of an int,
  * returns 0 always, or returns a non-zero value for an empty group,
  * leaks members of other groups, or double-counts multi-group users.

Native acceptance command (from the task's Acceptance Criteria):
    pytest tests/models/test_groups.py
"""

import ast
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/redash"
USERS_FILE = os.path.join(REPO_DIR, "redash", "models", "users.py")
MODELS_TESTS_DIR = os.path.join(REPO_DIR, "tests", "models")

# Driver modules we inject so we can clean them up afterwards.
_INJECTED = []


def _write_driver(name, body):
    """Write a pytest driver module into tests/models/ and remember it."""
    path = os.path.join(MODELS_TESTS_DIR, name)
    with open(path, "w") as fh:
        fh.write(body)
    _INJECTED.append(path)
    return path


def _run_pytest(target, timeout=600):
    """Run the repo's native pytest against `target` (relative to REPO_DIR)."""
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
            if "emc_driver" in f:
                try:
                    os.remove(os.path.join(pycache, f))
                except OSError:
                    pass


# Shared driver preamble: helpers to seed groups and (enabled/disabled) members.
_PREAMBLE = '''\
from redash.models import db
from redash.models.users import Group, User
from tests import BaseTestCase


class _EMCBase(BaseTestCase):
    def make_group(self, name="G"):
        g = self.factory.create_group(name=name)
        db.session.add(g)
        db.session.flush()
        return g

    def make_member(self, groups, disabled=False):
        """Create a user belonging to the given Group objects."""
        kwargs = {"group_ids": [g.id for g in groups]}
        u = self.factory.create_user(**kwargs)
        if disabled:
            u.disabled_at = db.func.now()
            db.session.add(u)
        db.session.flush()
        return u

    def count(self, group):
        return Group.enabled_member_count(group.id)
'''


class TestSqlalchemyOrmPatterns:
    REPO_DIR = "/workspace/redash"

    # ------------------------------------------------------------------ L1

    def test_users_file_exists(self):
        """L1: the model module to be modified exists."""
        assert os.path.isfile(USERS_FILE), f"missing {USERS_FILE}"

    def test_models_tests_dir_and_test_file_present(self):
        """L1: tests/models exists and the agent's new test_groups.py is there."""
        assert os.path.isdir(MODELS_TESTS_DIR), f"missing {MODELS_TESTS_DIR}"
        assert os.path.isfile(
            os.path.join(MODELS_TESTS_DIR, "test_groups.py")
        ), "tests/models/test_groups.py must be created by the agent"

    def test_enabled_member_count_classmethod_signature(self):
        """L1: `enabled_member_count` is defined on the Group class as a
        classmethod taking exactly (cls, group_id) -- verified via AST."""
        with open(USERS_FILE) as fh:
            tree = ast.parse(fh.read())

        group_cls = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "Group":
                group_cls = node
                break
        assert group_cls is not None, "class Group not found in redash/models/users.py"

        method = None
        for item in group_cls.body:
            if isinstance(item, ast.FunctionDef) and item.name == "enabled_member_count":
                method = item
                break
        assert method is not None, "Group.enabled_member_count method not defined"

        decorators = {d.id for d in method.decorator_list if isinstance(d, ast.Name)}
        assert "classmethod" in decorators, "enabled_member_count must be a @classmethod"

        argnames = [a.arg for a in method.args.args]
        assert argnames == ["cls", "group_id"], (
            f"signature must be (cls, group_id); got {argnames}"
        )

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

    def test_returns_plain_int(self):
        """L2: the return value is a plain `int` (not a query/row) and is usable
        directly in arithmetic and equality. A stub returning a query fails."""
        driver = _PREAMBLE + textwrap.dedent('''
            class EMCIntType(_EMCBase):
                def test_is_int(self):
                    g = self.make_group("type-check")
                    self.make_member([g])
                    self.make_member([g])
                    res = self.count(g)
                    assert type(res) is int, type(res)
                    # Usable directly in arithmetic / equality.
                    assert res == 2, res
                    assert res + 1 == 3
        ''')
        _write_driver("test_emc_driver_inttype.py", driver)
        proc = _run_pytest("tests/models/test_emc_driver_inttype.py")
        assert proc.returncode == 0, (
            "return-type/int check failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_three_enabled_members(self):
        """L2: a group with three enabled members returns 3."""
        driver = _PREAMBLE + textwrap.dedent('''
            class EMCThree(_EMCBase):
                def test_three(self):
                    g = self.make_group("three")
                    self.make_member([g])
                    self.make_member([g])
                    self.make_member([g])
                    assert self.count(g) == 3, self.count(g)
        ''')
        _write_driver("test_emc_driver_three.py", driver)
        proc = _run_pytest("tests/models/test_emc_driver_three.py")
        assert proc.returncode == 0, (
            "three-enabled-members failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_disabled_member_excluded(self):
        """L2: disabling one of three members drops the count to 2.

        This is the key discriminator vs `Group.members(group_id).count()`,
        which would still return 3."""
        driver = _PREAMBLE + textwrap.dedent('''
            class EMCDisabled(_EMCBase):
                def test_disabled_excluded(self):
                    g = self.make_group("disabled")
                    self.make_member([g])
                    self.make_member([g])
                    self.make_member([g], disabled=True)
                    assert self.count(g) == 2, self.count(g)

                def test_all_disabled(self):
                    g = self.make_group("all-disabled")
                    self.make_member([g], disabled=True)
                    self.make_member([g], disabled=True)
                    assert self.count(g) == 0, self.count(g)
        ''')
        _write_driver("test_emc_driver_disabled.py", driver)
        proc = _run_pytest("tests/models/test_emc_driver_disabled.py")
        assert proc.returncode == 0, (
            "disabled-member exclusion failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_empty_group_returns_zero(self):
        """L2: a group nobody belongs to returns the integer 0 (no error)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class EMCEmpty(_EMCBase):
                def test_empty(self):
                    g = self.make_group("empty")
                    # Seed an unrelated populated group to ensure isolation.
                    other = self.make_group("other-populated")
                    self.make_member([other])
                    res = self.count(g)
                    assert type(res) is int, type(res)
                    assert res == 0, res
        ''')
        _write_driver("test_emc_driver_empty.py", driver)
        proc = _run_pytest("tests/models/test_emc_driver_empty.py")
        assert proc.returncode == 0, (
            "empty-group-zero failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_other_groups_not_leaked(self):
        """L2: members of a DIFFERENT group must not be counted for this group.

        Discriminates a stub that counts all enabled users org-wide."""
        driver = _PREAMBLE + textwrap.dedent('''
            class EMCIsolation(_EMCBase):
                def test_isolation(self):
                    g1 = self.make_group("g1")
                    g2 = self.make_group("g2")
                    # Two members in g1, three in g2.
                    self.make_member([g1])
                    self.make_member([g1])
                    self.make_member([g2])
                    self.make_member([g2])
                    self.make_member([g2])
                    assert self.count(g1) == 2, self.count(g1)
                    assert self.count(g2) == 3, self.count(g2)
        ''')
        _write_driver("test_emc_driver_isolation.py", driver)
        proc = _run_pytest("tests/models/test_emc_driver_isolation.py")
        assert proc.returncode == 0, (
            "cross-group isolation failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_multi_group_member_counts_in_each(self):
        """L2: a user in both G1 and G2 contributes 1 to each group's count."""
        driver = _PREAMBLE + textwrap.dedent('''
            class EMCMulti(_EMCBase):
                def test_multi_group(self):
                    g1 = self.make_group("multi-g1")
                    g2 = self.make_group("multi-g2")
                    # One shared member in both groups.
                    self.make_member([g1, g2])
                    # One member only in g1.
                    self.make_member([g1])
                    assert self.count(g1) == 2, self.count(g1)
                    assert self.count(g2) == 1, self.count(g2)

                def test_multi_with_disabled_shared(self):
                    g1 = self.make_group("md-g1")
                    g2 = self.make_group("md-g2")
                    # Shared member is disabled -> excluded from BOTH.
                    self.make_member([g1, g2], disabled=True)
                    self.make_member([g1])
                    assert self.count(g1) == 1, self.count(g1)
                    assert self.count(g2) == 0, self.count(g2)
        ''')
        _write_driver("test_emc_driver_multi.py", driver)
        proc = _run_pytest("tests/models/test_emc_driver_multi.py")
        assert proc.returncode == 0, (
            "multi-group membership failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_does_not_mutate_db(self):
        """L2: calling enabled_member_count is read-only and idempotent --
        repeated calls give the same value and do not change row counts."""
        driver = _PREAMBLE + textwrap.dedent('''
            class EMCReadOnly(_EMCBase):
                def test_read_only(self):
                    g = self.make_group("readonly")
                    self.make_member([g])
                    self.make_member([g])
                    self.make_member([g], disabled=True)
                    before_users = User.query.count()
                    r1 = self.count(g)
                    r2 = self.count(g)
                    r3 = self.count(g)
                    assert r1 == r2 == r3 == 2, (r1, r2, r3)
                    assert User.query.count() == before_users
        ''')
        _write_driver("test_emc_driver_readonly.py", driver)
        proc = _run_pytest("tests/models/test_emc_driver_readonly.py")
        assert proc.returncode == 0, (
            "read-only / idempotence check failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_re_enabling_member_increments(self):
        """L2: disabling then re-enabling a member is reflected in the count,
        proving the method reads live `disabled_at` state rather than membership
        alone."""
        driver = _PREAMBLE + textwrap.dedent('''
            class EMCReEnable(_EMCBase):
                def test_disable_then_enable(self):
                    g = self.make_group("toggle")
                    self.make_member([g])
                    u = self.make_member([g])
                    assert self.count(g) == 2, self.count(g)
                    u.disable()
                    db.session.add(u)
                    db.session.flush()
                    assert self.count(g) == 1, self.count(g)
                    u.enable()
                    db.session.add(u)
                    db.session.flush()
                    assert self.count(g) == 2, self.count(g)
        ''')
        _write_driver("test_emc_driver_reenable.py", driver)
        proc = _run_pytest("tests/models/test_emc_driver_reenable.py")
        assert proc.returncode == 0, (
            "re-enable toggle failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_agent_test_groups_passes(self):
        """L2: the agent's own new tests/models/test_groups.py must pass under the
        native command from the Acceptance Criteria:

            pytest tests/models/test_groups.py

        We also require at least one test to have actually been collected."""
        proc = _run_pytest("tests/models/test_groups.py", timeout=600)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "agent's tests/models/test_groups.py did not pass:\n" + out[-4000:]
        )
        assert "no tests ran" not in out.lower(), (
            "no test was collected in test_groups.py:\n" + out[-2000:]
        )
        assert " passed" in out, (
            "expected at least one passing test in test_groups.py:\n" + out[-2000:]
        )
