"""Benchmark test for skill: sqlalchemy-orm-patterns (variant ext5).

Task: Add an `Alert.in_state(state, group_ids)` classmethod to redash's ORM
model (`redash/models/__init__.py`). It must return an iterable of `Alert` rows
that (a) are in the requested `state` and (b) are reachable from at least one of
the supplied `group_ids` -- reachability being defined exactly as the existing
`Alert.all` behavior (an alert is reachable if its query's data source belongs
to a group in `group_ids`, via the `DataSourceGroup` join). Each matching alert
must appear at most once even when its data source belongs to several supplied
groups.

Verification strategy
---------------------
L1 checks confirm the deliverable file exists, the classmethod is defined on the
`Alert` class with the EXACT required signature `(cls, state, group_ids)` (via
AST, not substring grep), and that `redash.models` imports cleanly.

L2 checks DYNAMICALLY EXERCISE the real behavior. Rather than trusting whatever
test the agent wrote, we inject our OWN focused pytest driver modules into the
repo's `tests/models/` directory (so they pick up the real DB-backed
`BaseTestCase` + `factory`), seed Alert/Query/DataSource/Group rows directly via
the ORM, call `Alert.in_state(...)`, and assert on the concrete returned rows.
Each driver runs under the repo's native `pytest`; we assert on returncode AND
that tests were actually collected.

A naive solution fails these tests if it: ignores the `state` argument (returns
all reachable alerts), ignores `group_ids` (returns all alerts in that state),
hardcodes a state, mirrors `Alert.all` verbatim, duplicates an alert reachable
via multiple groups, or mutates the database.
"""

import ast
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/redash"
MODELS_FILE = os.path.join(REPO_DIR, "redash", "models", "__init__.py")
MODELS_TESTS_DIR = os.path.join(REPO_DIR, "tests", "models")
ALERTS_TEST_FILE = os.path.join(MODELS_TESTS_DIR, "test_alerts.py")

# Driver modules we inject into the repo so we can clean them up afterwards.
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
            if "in_state_driver" in f:
                try:
                    os.remove(os.path.join(pycache, f))
                except OSError:
                    pass


# Shared driver preamble: seed helpers used by several scenarios. Mirrors the
# conventions in the repo's own tests/models/test_alerts.py (factory + flush).
_PREAMBLE = '''\
from redash.models import Alert, db
from tests import BaseTestCase


class _InStateBase(BaseTestCase):
    def make_alert(self, state, data_source=None):
        """Create an alert whose query lives on `data_source`, in `state`."""
        if data_source is None:
            data_source = self.factory.data_source
        query = self.factory.create_query(data_source=data_source)
        alert = self.factory.create_alert(query_rel=query, state=state)
        db.session.flush()
        return alert

    def result(self, state, group_ids):
        return list(Alert.in_state(state, group_ids))
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
        assert os.path.isfile(ALERTS_TEST_FILE), (
            "tests/models/test_alerts.py must exist"
        )

    def test_in_state_classmethod_signature(self):
        """L1: `in_state` is defined on the Alert class as a classmethod taking
        EXACTLY (cls, state, group_ids) -- verified via AST, not substring grep."""
        with open(MODELS_FILE) as fh:
            tree = ast.parse(fh.read())

        alert_cls = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "Alert":
                alert_cls = node
                break
        assert alert_cls is not None, "class Alert not found in models"

        method = None
        for item in alert_cls.body:
            if isinstance(item, ast.FunctionDef) and item.name == "in_state":
                method = item
                break
        assert method is not None, "Alert.in_state method not defined"

        decorators = {
            d.id for d in method.decorator_list if isinstance(d, ast.Name)
        }
        assert "classmethod" in decorators, "in_state must be a @classmethod"

        argnames = [a.arg for a in method.args.args]
        assert argnames == ["cls", "state", "group_ids"], (
            f"in_state signature must be (cls, state, group_ids); got {argnames}"
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

    def test_filters_by_state(self):
        """L2: only alerts whose state == requested state appear; alerts in any
        other state on the SAME reachable data source are excluded.

        Discriminates a stub that ignores `state` (would return both)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class InStateFilter(_InStateBase):
                def test_state_filter(self):
                    g = self.factory.default_group
                    a_trig = self.make_alert(Alert.TRIGGERED_STATE)
                    a_ok = self.make_alert(Alert.OK_STATE)
                    res = self.result(Alert.TRIGGERED_STATE, [g.id])
                    assert a_trig in res, res
                    assert a_ok not in res, res
                    # And symmetrically for the other state.
                    res_ok = self.result(Alert.OK_STATE, [g.id])
                    assert a_ok in res_ok, res_ok
                    assert a_trig not in res_ok, res_ok
        ''')
        _write_driver("test_in_state_driver_filter.py", driver)
        proc = _run_pytest("tests/models/test_in_state_driver_filter.py")
        assert proc.returncode == 0, (
            "state filtering failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_filters_by_group_reachability(self):
        """L2: alerts reachable only through a group NOT in group_ids are excluded,
        even when they match the requested state.

        Discriminates a stub that ignores `group_ids` (returns all triggered)."""
        driver = _PREAMBLE + textwrap.dedent('''
            class InStateReach(_InStateBase):
                def test_group_reach(self):
                    default = self.factory.default_group
                    other_group = self.factory.create_group()
                    ds_default = self.factory.data_source
                    ds_other = self.factory.create_data_source(group=other_group)
                    db.session.flush()

                    a_default = self.make_alert(Alert.TRIGGERED_STATE, data_source=ds_default)
                    a_other = self.make_alert(Alert.TRIGGERED_STATE, data_source=ds_other)

                    # Only the default group is supplied.
                    res = self.result(Alert.TRIGGERED_STATE, [default.id])
                    assert a_default in res, res
                    assert a_other not in res, res

                    # Only the other group is supplied.
                    res2 = self.result(Alert.TRIGGERED_STATE, [other_group.id])
                    assert a_other in res2, res2
                    assert a_default not in res2, res2

                    # Both groups supplied -> both alerts reachable.
                    res_both = self.result(Alert.TRIGGERED_STATE, [default.id, other_group.id])
                    assert a_default in res_both, res_both
                    assert a_other in res_both, res_both
        ''')
        _write_driver("test_in_state_driver_reach.py", driver)
        proc = _run_pytest("tests/models/test_in_state_driver_reach.py")
        assert proc.returncode == 0, (
            "group reachability failed:\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_combined_state_and_group(self):
        """L2: both filters apply together -- an alert must match state AND be
        reachable. A triggered alert behind a non-supplied group, and an ok alert
        behind a supplied group, are both excluded from in_state('triggered', [G])."""
        driver = _PREAMBLE + textwrap.dedent('''
            class InStateCombined(_InStateBase):
                def test_combined(self):
                    default = self.factory.default_group
                    other_group = self.factory.create_group()
                    ds_default = self.factory.data_source
                    ds_other = self.factory.create_data_source(group=other_group)
                    db.session.flush()

                    want = self.make_alert(Alert.TRIGGERED_STATE, data_source=ds_default)
                    wrong_state = self.make_alert(Alert.OK_STATE, data_source=ds_default)
                    wrong_group = self.make_alert(Alert.TRIGGERED_STATE, data_source=ds_other)

                    res = self.result(Alert.TRIGGERED_STATE, [default.id])
                    assert want in res, res
                    assert wrong_state not in res, res
                    assert wrong_group not in res, res
                    assert list(res) == [want], [a.id for a in res]
        ''')
        _write_driver("test_in_state_driver_combined.py", driver)
        proc = _run_pytest("tests/models/test_in_state_driver_combined.py")
        assert proc.returncode == 0, (
            "combined state+group filtering failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_dedup_across_multiple_groups(self):
        """L2: a data source belonging to two groups, both supplied, must yield its
        matching alert exactly once -- not duplicated by the join.

        Mirrors the repo's `test_return_each_alert_only_once` invariant."""
        driver = _PREAMBLE + textwrap.dedent('''
            class InStateDedup(_InStateBase):
                def test_dedup(self):
                    default = self.factory.default_group
                    extra_group = self.factory.create_group()
                    # Default data source now belongs to BOTH groups.
                    self.factory.data_source.add_group(extra_group)
                    db.session.flush()

                    alert = self.make_alert(Alert.TRIGGERED_STATE)

                    res = self.result(Alert.TRIGGERED_STATE, [default.id, extra_group.id])
                    matching = [a for a in res if a.id == alert.id]
                    assert len(matching) == 1, [a.id for a in res]
                    assert alert in res, res
        ''')
        _write_driver("test_in_state_driver_dedup.py", driver)
        proc = _run_pytest("tests/models/test_in_state_driver_dedup.py")
        assert proc.returncode == 0, (
            "deduplication across groups failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_empty_when_no_match(self):
        """L2: when nothing matches both state and reachability, list(...) is empty
        (no rows, no error). Covers the no-match edge case from the doc."""
        driver = _PREAMBLE + textwrap.dedent('''
            class InStateEmpty(_InStateBase):
                def test_no_matching_state(self):
                    g = self.factory.default_group
                    # Only OK alerts exist; ask for triggered.
                    self.make_alert(Alert.OK_STATE)
                    self.make_alert(Alert.OK_STATE)
                    assert self.result(Alert.TRIGGERED_STATE, [g.id]) == []

                def test_no_alerts_at_all(self):
                    g = self.factory.default_group
                    assert self.result(Alert.TRIGGERED_STATE, [g.id]) == []

                def test_empty_group_ids(self):
                    self.make_alert(Alert.TRIGGERED_STATE)
                    assert self.result(Alert.TRIGGERED_STATE, []) == []
        ''')
        _write_driver("test_in_state_driver_empty.py", driver)
        proc = _run_pytest("tests/models/test_in_state_driver_empty.py")
        assert proc.returncode == 0, (
            "empty/no-match handling failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_returns_alert_objects(self):
        """L2: results are real Alert instances in the requested state -- not ids,
        not query rows -- and every returned alert satisfies the state filter."""
        driver = _PREAMBLE + textwrap.dedent('''
            class InStateShape(_InStateBase):
                def test_shape(self):
                    g = self.factory.default_group
                    a1 = self.make_alert(Alert.TRIGGERED_STATE)
                    a2 = self.make_alert(Alert.TRIGGERED_STATE)
                    self.make_alert(Alert.OK_STATE)
                    res = self.result(Alert.TRIGGERED_STATE, [g.id])
                    assert len(res) == 2, [type(x) for x in res]
                    for a in res:
                        assert isinstance(a, Alert), type(a)
                        assert a.state == Alert.TRIGGERED_STATE, a.state
                    assert {a1.id, a2.id} == {a.id for a in res}
        ''')
        _write_driver("test_in_state_driver_shape.py", driver)
        proc = _run_pytest("tests/models/test_in_state_driver_shape.py")
        assert proc.returncode == 0, (
            "result shape/type check failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_arbitrary_state_value(self):
        """L2: the method respects the state ARGUMENT (not a hardcoded constant).
        Using a non-standard custom state string must still filter correctly.

        Discriminates a stub that hardcodes `state == 'triggered'`."""
        driver = _PREAMBLE + textwrap.dedent('''
            class InStateArbitrary(_InStateBase):
                def test_custom_state(self):
                    g = self.factory.default_group
                    a_custom = self.make_alert("custom_state")
                    a_trig = self.make_alert(Alert.TRIGGERED_STATE)
                    res = self.result("custom_state", [g.id])
                    assert a_custom in res, res
                    assert a_trig not in res, res
                    assert all(a.state == "custom_state" for a in res), \
                        [a.state for a in res]
        ''')
        _write_driver("test_in_state_driver_custom.py", driver)
        proc = _run_pytest("tests/models/test_in_state_driver_custom.py")
        assert proc.returncode == 0, (
            "arbitrary state value handling failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_does_not_mutate_db(self):
        """L2: calling in_state repeatedly is read-only -- stable results and no
        change to the underlying alert row count."""
        driver = _PREAMBLE + textwrap.dedent('''
            class InStateReadOnly(_InStateBase):
                def test_read_only(self):
                    g = self.factory.default_group
                    a1 = self.make_alert(Alert.TRIGGERED_STATE)
                    a2 = self.make_alert(Alert.TRIGGERED_STATE)
                    self.make_alert(Alert.OK_STATE)
                    before = Alert.query.count()
                    r1 = {a.id for a in self.result(Alert.TRIGGERED_STATE, [g.id])}
                    r2 = {a.id for a in self.result(Alert.TRIGGERED_STATE, [g.id])}
                    r3 = {a.id for a in self.result(Alert.TRIGGERED_STATE, [g.id])}
                    assert r1 == r2 == r3 == {a1.id, a2.id}, (r1, r2, r3)
                    assert Alert.query.count() == before
        ''')
        _write_driver("test_in_state_driver_readonly.py", driver)
        proc = _run_pytest("tests/models/test_in_state_driver_readonly.py")
        assert proc.returncode == 0, (
            "read-only / idempotence check failed:\n"
            + proc.stdout[-4000:] + proc.stderr[-2000:]
        )

    def test_agent_test_file_passes_in_state_selection(self):
        """L2: the agent's own additions to tests/models/test_alerts.py for
        in_state must pass under the native command from the task's Acceptance
        Criteria (`pytest tests/models/test_alerts.py -k in_state`), and at least
        one matching test must actually have been collected."""
        proc = _run_pytest("tests/models/test_alerts.py", extra=["-k", "in_state"], timeout=600)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "agent's in_state tests did not pass:\n" + out[-4000:]
        )
        assert "no tests ran" not in out.lower(), (
            "no in_state test was collected:\n" + out[-2000:]
        )
        assert " passed" in out, (
            "expected at least one passing in_state test:\n" + out[-2000:]
        )

    def test_full_alerts_test_file_still_passes(self):
        """L2: the full tests/models/test_alerts.py must continue to pass, ensuring
        the agent's model change did not break existing Alert behavior."""
        proc = _run_pytest("tests/models/test_alerts.py", timeout=900)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "tests/models/test_alerts.py regressed:\n" + out[-4000:]
        )
        assert "no tests ran" not in out.lower(), (
            "test_alerts.py collected no tests:\n" + out[-2000:]
        )
