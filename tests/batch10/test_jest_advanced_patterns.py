"""Benchmark verification for skill: jest-advanced-patterns (variant ext10).

Task: Add a small observable value store to the React monorepo's ``shared``
package (``packages/shared/createObservableValue.js``) plus a deterministic Jest
suite (``packages/shared/__tests__/createObservableValue-test.js``).

The store is a factory ``createObservableValue(initialValue)`` returning an
object with exactly:
  * ``get() -> value``
  * ``set(nextValue) -> boolean``  (true iff the value changed under Object.is)
  * ``subscribe(listener) -> unsubscribe``
  * ``subscriberCount() -> number``
``set`` notifies every subscriber, in subscription order, with
``(nextValue, previousValue)`` ONLY when the value changes under ``Object.is``
semantics (NaN==NaN is no change; +0 vs -0 IS a change). The module must import
no other module.

Strategy
--------
L1 cases assert the two deliverable files exist, expose a default export, and
that the implementation imports/requires no other module (a hard constraint of
the requirement doc).

L2 cases independently EXERCISE the real store behavior. Rather than trusting
the agent's own test file, each L2 method writes ITS OWN focused Jest probe spec
into ``packages/shared/__tests__/`` and runs that single spec through the repo's
native Jest CLI (``yarn test <path>`` -> ``node scripts/jest/jest-cli.js
<path>``, which forwards the path as a testPathPattern). Every probe drives the
store with mock listeners (``jest.fn()``) and deep-validates exactly ONE
behavior from the requirement doc:

  * change notifies all subscribers once, in order, with (next, prev); set->true
  * equivalent value suppresses notification; set->false
  * Object.is NaN: set(NaN) over NaN is no change
  * Object.is signed zero: set(-0) over +0 IS a change
  * (next, prev) argument pair is exact
  * unsubscribe stops notifications and drops subscriberCount
  * unsubscribe is idempotent (calling twice is a safe no-op)
  * a late subscriber only sees subsequent changes
  * subscriberCount reflects active subscribers
  * subscribe(non-function) throws TypeError
  * the store relies only on its args (no timers/network needed; deterministic)

Because each behavior is its own probe spec and its own pytest method, a partial
or naive implementation (e.g. one that always notifies, ignores Object.is,
returns a fixed boolean, or never decrements subscriberCount) fails the SPECIFIC
behavior it got wrong instead of one monolithic probe. We also confirm the
agent's own suite runs green via the exact Acceptance-Criteria command.

Module resolution note: this repo resolves ``shared/<name>`` via Jest haste
(``roots: ['<rootDir>/packages', ...]``), so the probe ``require``s
``'shared/createObservableValue'`` exactly like the repo's own shared tests.
"""

import os
import re
import subprocess
import textwrap

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies  # noqa: F401
except Exception:  # pragma: no cover - utils may be absent locally
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/react"

SRC_REL = "packages/shared/createObservableValue.js"
AGENT_TEST_REL = "packages/shared/__tests__/createObservableValue-test.js"

# Each probe is written under __tests__ (so the repo's testRegex matches it) and
# is removed after the run. Unique names avoid cross-test collisions.
PROBE_DIR_REL = "packages/shared/__tests__"
PROBE_PREFIX = "createObservableValue-probe-"


def _src_path():
    return os.path.join(REPO_DIR, SRC_REL)


def _agent_test_path():
    return os.path.join(REPO_DIR, AGENT_TEST_REL)


def _probe_rel(name):
    return os.path.join(PROBE_DIR_REL, PROBE_PREFIX + name + ".bench-test.js")


def _probe_abs(name):
    return os.path.join(REPO_DIR, _probe_rel(name))


def _read_src():
    with open(_src_path()) as fh:
        return fh.read()


def _yarn_test(path_rel, timeout=300):
    """Run the repo's native Jest CLI scoped to a single test file.

    ``yarn test <path>`` invokes ``node ./scripts/jest/jest-cli.js <path>``;
    the trailing path is forwarded to Jest as a testPathPattern so only that
    one spec executes.
    """
    return subprocess.run(
        ["yarn", "test", path_rel],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _jest_passed(result):
    """Require real test execution plus an explicit green summary."""
    out = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.returncode != 0:
        return False, out
    if re.search(r"No tests found", out):
        return False, out
    if re.search(r"Tests:\s+.*\bfailed", out):
        return False, out
    if not re.search(r"Tests:\s+\d+ passed", out) and not re.search(r"PASS\b", out):
        return False, out
    return True, out


# Shared JS preamble: a deterministic loader for the store factory. No timers,
# network, globals, or randomness are involved; probes use jest.fn() mock
# listeners to assert call counts and argument pairs. Injected verbatim.
_PREAMBLE = """\
'use strict';

function load() {
  return require('shared/createObservableValue').default;
}
"""


def _make_probe(body):
    """Wrap a single-behavior ``it(...)`` body in the shared preamble."""
    return _PREAMBLE + "\n" + textwrap.dedent(body) + "\n"


def _run_probe(name, body, timeout=300):
    """Write a one-behavior probe spec, run it via native Jest, clean up."""
    rel = _probe_rel(name)
    abs_path = _probe_abs(name)
    with open(abs_path, "w") as fh:
        fh.write(_make_probe(body))
    try:
        result = _yarn_test(rel, timeout=timeout)
    finally:
        try:
            os.remove(abs_path)
        except OSError:
            pass
    return result


@pytest.fixture(scope="module", autouse=True)
def _deps():
    """Ensure JS toolchain deps are present, and sweep stray probe files."""
    node_modules = os.path.join(REPO_DIR, "node_modules")
    jest_marker = os.path.join(node_modules, "chalk")
    if not os.path.isdir(jest_marker):
        try:
            subprocess.run(
                ["yarn", "install", "--frozen-lockfile"],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=1800,
            )
        except Exception:
            pass
        if not os.path.isdir(jest_marker) and ensure_npm_dependencies is not None:
            try:
                ensure_npm_dependencies(REPO_DIR)
            except Exception:
                pass
    yield
    probe_dir = os.path.join(REPO_DIR, PROBE_DIR_REL)
    try:
        for fname in os.listdir(probe_dir):
            if fname.startswith(PROBE_PREFIX):
                try:
                    os.remove(os.path.join(probe_dir, fname))
                except OSError:
                    pass
    except OSError:
        pass


class TestJestAdvancedPatterns:
    REPO_DIR = REPO_DIR

    # -----------------------------------------------------------------------
    # L1 — deliverables exist and respect the structural constraints.
    # -----------------------------------------------------------------------
    def test_store_source_exists(self):
        """L1: the observable-value module file exists and is non-empty."""
        path = _src_path()
        assert os.path.isfile(path), f"missing deliverable: {SRC_REL}"
        assert os.path.getsize(path) > 0, "store source is empty"

    def test_agent_test_file_exists(self):
        """L1: the agent's Jest test suite file exists and is non-empty."""
        path = _agent_test_path()
        assert os.path.isfile(path), f"missing deliverable: {AGENT_TEST_REL}"
        assert os.path.getsize(path) > 0, "agent test file is empty"

    def test_store_has_default_export(self):
        """L1: the module exposes a default export (the factory)."""
        src = _read_src()
        assert "export default" in src or "module.exports" in src, (
            "store must export the factory by default"
        )

    def test_store_imports_no_other_module(self):
        """L1: hard constraint — the module imports/requires no other module."""
        src = _read_src()
        no_block = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
        no_line = re.sub(r"//[^\n]*", "", no_block)
        assert not re.search(r"^\s*import\s", no_line, flags=re.MULTILINE), (
            "store must contain no `import` statement"
        )
        assert not re.search(r"\brequire\s*\(", no_line), (
            "store must not `require` any other module"
        )

    # -----------------------------------------------------------------------
    # L2 — each behavior gets its OWN independent probe spec run via Jest.
    # -----------------------------------------------------------------------
    def test_get_returns_initial_then_updated_value(self):
        """L2: get() returns the initial value, then the value after a change.

        A naive store that ignores set() or returns a fixed value fails: get()
        must reflect both the initial and the updated value.
        """
        result = _run_probe(
            "get-value",
            """
            it('get returns initial then updated value', () => {
              const store = load()(1);
              expect(store.get()).toBe(1);
              const changed = store.set(2);
              expect(changed).toBe(true);
              expect(store.get()).toBe(2);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"get-value probe failed:\n{out[-4000:]}"

    def test_change_notifies_all_subscribers_in_order(self):
        """L2: a real change calls every subscriber once, in subscription order.

        Two mock listeners must each be called exactly once on a change; the
        first-subscribed listener must be invoked before the second.
        """
        result = _run_probe(
            "notify-order",
            """
            it('change notifies all subscribers once, in subscription order', () => {
              const store = load()('a');
              const calls = [];
              const l1 = jest.fn(() => calls.push('l1'));
              const l2 = jest.fn(() => calls.push('l2'));
              store.subscribe(l1);
              store.subscribe(l2);
              const changed = store.set('b');
              expect(changed).toBe(true);
              expect(l1).toHaveBeenCalledTimes(1);
              expect(l2).toHaveBeenCalledTimes(1);
              expect(calls).toEqual(['l1', 'l2']);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"notify-order probe failed:\n{out[-4000:]}"

    def test_listener_receives_next_and_prev(self):
        """L2: on change, listeners are called with exactly (next, previous).

        The mock listener must receive (nextValue, previousValue) — a store
        that passes only the new value, or swaps the order, fails.
        """
        result = _run_probe(
            "next-prev",
            """
            it('listener is called with (next, prev)', () => {
              const store = load()(10);
              const l = jest.fn();
              store.subscribe(l);
              const changed = store.set(20);
              expect(changed).toBe(true);
              expect(l).toHaveBeenCalledTimes(1);
              expect(l).toHaveBeenCalledWith(20, 10);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"next-prev probe failed:\n{out[-4000:]}"

    def test_equivalent_value_suppresses_notification(self):
        """L2: set to an equivalent value notifies nobody and returns false.

        set(5) when already 5 must NOT call any subscriber and must return
        false. A store that always notifies (ignoring equality) fails here.
        """
        result = _run_probe(
            "suppress-equal",
            """
            it('set to the same value suppresses notification, returns false', () => {
              const store = load()(5);
              const l = jest.fn();
              store.subscribe(l);
              const changed = store.set(5);
              expect(changed).toBe(false);
              expect(l).not.toHaveBeenCalled();
              expect(store.get()).toBe(5);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"suppress-equal probe failed:\n{out[-4000:]}"

    def test_object_is_nan_is_not_a_change(self):
        """L2: Object.is semantics — set(NaN) over NaN is NOT a change.

        With current value NaN, set(NaN) must return false and notify nobody.
        A store using === for equality would (wrongly) treat NaN!==NaN as a
        change and fail.
        """
        result = _run_probe(
            "object-is-nan",
            """
            it('set(NaN) over NaN is not a change', () => {
              const store = load()(NaN);
              const l = jest.fn();
              store.subscribe(l);
              const changed = store.set(NaN);
              expect(changed).toBe(false);
              expect(l).not.toHaveBeenCalled();
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"object-is-nan probe failed:\n{out[-4000:]}"

    def test_object_is_signed_zero_is_a_change(self):
        """L2: Object.is semantics — set(-0) over +0 IS a change.

        With current value +0, set(-0) must return true and notify with
        (next, prev) where 1/next is -Infinity and 1/prev is +Infinity. A store
        using === (which treats +0 === -0) would wrongly suppress and fail.
        """
        result = _run_probe(
            "object-is-zero",
            """
            it('set(-0) over +0 is a change and notifies', () => {
              const store = load()(0);
              const l = jest.fn();
              store.subscribe(l);
              const changed = store.set(-0);
              expect(changed).toBe(true);
              expect(l).toHaveBeenCalledTimes(1);
              const [next, prev] = l.mock.calls[0];
              expect(Object.is(next, -0)).toBe(true);
              expect(Object.is(prev, 0)).toBe(true);
              expect(1 / store.get()).toBe(-Infinity);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"object-is-zero probe failed:\n{out[-4000:]}"

    def test_unsubscribe_stops_notifications_and_drops_count(self):
        """L2: after unsubscribe, that listener is no longer notified.

        subscriberCount drops by one and the removed listener is not called on a
        later change, while a still-active listener is.
        """
        result = _run_probe(
            "unsubscribe",
            """
            it('unsubscribe stops notifications and drops subscriberCount', () => {
              const store = load()('a');
              const gone = jest.fn();
              const stay = jest.fn();
              const unsub = store.subscribe(gone);
              store.subscribe(stay);
              expect(store.subscriberCount()).toBe(2);
              unsub();
              expect(store.subscriberCount()).toBe(1);
              const changed = store.set('b');
              expect(changed).toBe(true);
              expect(gone).not.toHaveBeenCalled();
              expect(stay).toHaveBeenCalledTimes(1);
              expect(stay).toHaveBeenCalledWith('b', 'a');
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"unsubscribe probe failed:\n{out[-4000:]}"

    def test_unsubscribe_is_idempotent(self):
        """L2: calling unsubscribe twice is a safe no-op.

        A second unsubscribe must not throw and must not remove an unrelated
        subscriber (subscriberCount stays correct).
        """
        result = _run_probe(
            "unsub-idempotent",
            """
            it('unsubscribe twice is a safe no-op', () => {
              const store = load()(0);
              const a = jest.fn();
              const b = jest.fn();
              const unsubA = store.subscribe(a);
              store.subscribe(b);
              expect(store.subscriberCount()).toBe(2);
              unsubA();
              expect(store.subscriberCount()).toBe(1);
              expect(() => unsubA()).not.toThrow();
              expect(store.subscriberCount()).toBe(1);
              store.set(1);
              expect(a).not.toHaveBeenCalled();
              expect(b).toHaveBeenCalledTimes(1);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"unsub-idempotent probe failed:\n{out[-4000:]}"

    def test_late_subscriber_only_sees_subsequent_changes(self):
        """L2: a listener registered after some sets only sees later changes.

        Subscribing after an initial change must not back-fill missed
        notifications; the late listener is called only on the next change, with
        the correct (next, prev) pair.
        """
        result = _run_probe(
            "late-subscriber",
            """
            it('late subscriber only sees subsequent changes', () => {
              const store = load()(1);
              store.set(2);
              const late = jest.fn();
              store.subscribe(late);
              expect(late).not.toHaveBeenCalled();
              const changed = store.set(3);
              expect(changed).toBe(true);
              expect(late).toHaveBeenCalledTimes(1);
              expect(late).toHaveBeenCalledWith(3, 2);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"late-subscriber probe failed:\n{out[-4000:]}"

    def test_subscriber_count_tracks_active_subscribers(self):
        """L2: subscriberCount reflects the number of active subscribers.

        Starts at 0, increases per subscribe, decreases per unsubscribe.
        """
        result = _run_probe(
            "subscriber-count",
            """
            it('subscriberCount tracks active subscribers', () => {
              const store = load()(0);
              expect(store.subscriberCount()).toBe(0);
              const u1 = store.subscribe(jest.fn());
              const u2 = store.subscribe(jest.fn());
              const u3 = store.subscribe(jest.fn());
              expect(store.subscriberCount()).toBe(3);
              u2();
              expect(store.subscriberCount()).toBe(2);
              u1();
              u3();
              expect(store.subscriberCount()).toBe(0);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"subscriber-count probe failed:\n{out[-4000:]}"

    def test_subscribe_throws_typeerror_for_non_function(self):
        """L2: subscribe with a non-function listener throws a TypeError.

        undefined, a number, and an object must each cause subscribe to throw a
        TypeError; subscriberCount must remain 0 afterward.
        """
        result = _run_probe(
            "typeerror",
            """
            it('subscribe throws TypeError for a non-function listener', () => {
              const store = load()(0);
              expect(() => store.subscribe(undefined)).toThrow(TypeError);
              expect(() => store.subscribe(123)).toThrow(TypeError);
              expect(() => store.subscribe({})).toThrow(TypeError);
              expect(store.subscriberCount()).toBe(0);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"typeerror probe failed:\n{out[-4000:]}"

    # -----------------------------------------------------------------------
    # L2 — the agent's own suite must pass via the spec'd command.
    # -----------------------------------------------------------------------
    def test_agent_suite_passes(self):
        """L2: the agent's own Jest suite passes via the Acceptance command.

        Mirrors the Acceptance Criteria command exactly:
        ``yarn test packages/shared/__tests__/createObservableValue-test.js``.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        ok, out = _jest_passed(result)
        assert ok, f"agent suite did not pass green:\n{out[-4000:]}"

    def test_agent_suite_has_multiple_independent_cases(self):
        """L2: the agent suite must contain several independent passing cases.

        The requirement mandates per-behavior independent cases, so a single
        trivial test would not satisfy it; require a multi-case green run.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        out = (result.stdout or "") + "\n" + (result.stderr or "")
        assert result.returncode == 0, f"agent suite nonzero rc:\n{out[-3000:]}"
        m = re.search(r"Tests:\s+(\d+) passed", out)
        assert m is not None, f"no passing summary in agent run:\n{out[-3000:]}"
        assert int(m.group(1)) >= 5, (
            f"agent suite should have multiple cases, saw {m.group(1)}"
        )
