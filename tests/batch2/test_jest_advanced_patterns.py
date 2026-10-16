"""Benchmark verification for skill: jest-advanced-patterns (variant ext2).

Task: Add a synchronous publish/subscribe event bus to the React monorepo's
``shared`` package (``packages/shared/createEventBus.js``) plus a deterministic
Jest suite (``packages/shared/__tests__/createEventBus-test.js``).

The bus is a zero-argument ``export default`` factory returning an object with
exactly these methods:

  * ``on(eventName, listener) -> unsubscribe``
  * ``once(eventName, listener) -> unsubscribe``
  * ``emit(eventName, payload) -> number``
  * ``listenerCount(eventName) -> number``
  * ``removeAll(eventName?) -> void``

Strategy
--------
L1 cases assert the two deliverable files exist, are non-empty, that the bus
module exposes a default export, and that it ``import``/``require``s no other
module (a hard constraint from the requirement doc).

L2 cases independently EXERCISE the real bus behavior. Rather than trusting the
agent's own test file, each L2 method writes ITS OWN focused Jest probe spec
into ``packages/shared/__tests__/`` and runs that single spec through the repo's
native Jest CLI (``yarn test <path>`` -> ``node scripts/jest/jest-cli.js
<path>``, which forwards the path as a testPathPattern). Every probe drives the
bus with ``jest.fn()`` mock listeners (no timers, network, or randomness) and
deep-validates exactly ONE behavior from the requirement doc:

  * multi-listener emit: both invoked once, with the payload, in order; returns 2
  * the same listener registered twice fires twice per emit
  * ``once`` fires at most once across repeated emits
  * ``once`` unsubscribe before first fire cancels it
  * ``on`` unsubscribe removes that listener and is idempotent (no-op on 2nd call)
  * ``emit`` with zero listeners returns 0 and does nothing
  * mid-emit mutation safety: a listener that unsubscribes another mid-emit does
    not skip/double-invoke listeners snapshotted at emit start, but the change
    takes effect on the NEXT emit
  * ``listenerCount`` reflects on/once/unsubscribe and once-fire decrement
  * ``removeAll(eventName)`` clears one event only
  * ``removeAll()`` clears every event
  * ``on`` throws ``TypeError`` for a non-function listener

Because each behavior is its own probe spec and its own pytest method, a
partial / buggy solution (e.g. one that ignores registration order, mishandles
mid-emit mutation, lets ``once`` fire twice, or returns a fixed emit count)
fails the SPECIFIC behavior it got wrong. We also confirm the agent's own suite
runs green via the exact Acceptance-Criteria command and that it contains
several independent passing cases.

Module resolution note: this repo resolves ``shared/<name>`` via Jest haste
(``roots: ['<rootDir>/packages', ...]``), so the probe ``require``s
``'shared/createEventBus'`` exactly like the repo's own shared tests.
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

SRC_REL = "packages/shared/createEventBus.js"
AGENT_TEST_REL = "packages/shared/__tests__/createEventBus-test.js"

# Each probe is written under __tests__ (so the repo's testRegex matches it) and
# is removed after the run. Unique names avoid cross-test collisions.
PROBE_DIR_REL = "packages/shared/__tests__"
PROBE_PREFIX = "createEventBus-probe-"


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


# Shared JS preamble: a deterministic helper to load the bus factory. No timers,
# network, or randomness; listeners are jest mock functions in each probe.
_PREAMBLE = """\
'use strict';

function factory() {
  return require('shared/createEventBus').default;
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
    def test_bus_source_exists(self):
        """L1: the event-bus module file exists and is non-empty."""
        path = _src_path()
        assert os.path.isfile(path), f"missing deliverable: {SRC_REL}"
        assert os.path.getsize(path) > 0, "event-bus source is empty"

    def test_agent_test_file_exists(self):
        """L1: the agent's Jest test suite file exists and is non-empty."""
        path = _agent_test_path()
        assert os.path.isfile(path), f"missing deliverable: {AGENT_TEST_REL}"
        assert os.path.getsize(path) > 0, "agent test file is empty"

    def test_bus_has_default_export(self):
        """L1: the bus module exposes a default export (the factory)."""
        src = _read_src()
        assert "export default" in src or "module.exports" in src, (
            "bus must export the factory by default"
        )

    def test_bus_imports_no_other_module(self):
        """L1: hard constraint — the module imports/requires no other module."""
        src = _read_src()
        no_block = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
        no_line = re.sub(r"//[^\n]*", "", no_block)
        assert not re.search(r"^\s*import\s", no_line, flags=re.MULTILINE), (
            "bus must contain no `import` statement"
        )
        assert not re.search(r"\brequire\s*\(", no_line), (
            "bus must not `require` any other module"
        )

    # -----------------------------------------------------------------------
    # L2 — each behavior gets its OWN independent probe spec run via Jest.
    # -----------------------------------------------------------------------
    def test_emit_invokes_all_listeners_in_order_with_payload(self):
        """L2: emit calls every listener once, in registration order, with payload.

        Two listeners on the same event must each be invoked exactly once with
        the emitted payload; the invocation order must follow registration
        order; emit must return the count (2). A stub that returns a fixed count
        or drops a listener fails here.
        """
        result = _run_probe(
            "emit-order",
            """
            it('emit invokes all listeners in order, with payload; returns count', () => {
              const bus = factory()();
              const order = [];
              const a = jest.fn(() => order.push('a'));
              const b = jest.fn(() => order.push('b'));
              bus.on('data', a);
              bus.on('data', b);
              const n = bus.emit('data', 5);
              expect(n).toBe(2);
              expect(a).toHaveBeenCalledTimes(1);
              expect(b).toHaveBeenCalledTimes(1);
              expect(a).toHaveBeenCalledWith(5);
              expect(b).toHaveBeenCalledWith(5);
              expect(order).toEqual(['a', 'b']);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"emit-order probe failed:\n{out[-4000:]}"

    def test_same_listener_registered_twice_fires_twice(self):
        """L2: registering the same function twice yields two independent firings.

        The doc requires each registration to be independent; emit must invoke
        the function twice and return 2.
        """
        result = _run_probe(
            "dup-listener",
            """
            it('same listener registered twice fires twice per emit', () => {
              const bus = factory()();
              const fn = jest.fn();
              bus.on('e', fn);
              bus.on('e', fn);
              expect(bus.listenerCount('e')).toBe(2);
              const n = bus.emit('e', 'p');
              expect(n).toBe(2);
              expect(fn).toHaveBeenCalledTimes(2);
              expect(fn).toHaveBeenNthCalledWith(1, 'p');
              expect(fn).toHaveBeenNthCalledWith(2, 'p');
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"dup-listener probe failed:\n{out[-4000:]}"

    def test_once_fires_at_most_once(self):
        """L2: a once listener fires exactly once across repeated emits.

        After two emits of the same event, a once listener must have been
        invoked exactly once. A naive impl that treats once like on fails.
        """
        result = _run_probe(
            "once-fire",
            """
            it('once fires at most once across repeated emits', () => {
              const bus = factory()();
              const fn = jest.fn();
              bus.once('ping', fn);
              expect(bus.listenerCount('ping')).toBe(1);
              const n1 = bus.emit('ping', 1);
              const n2 = bus.emit('ping', 2);
              expect(n1).toBe(1);
              expect(n2).toBe(0);
              expect(fn).toHaveBeenCalledTimes(1);
              expect(fn).toHaveBeenCalledWith(1);
              expect(bus.listenerCount('ping')).toBe(0);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"once-fire probe failed:\n{out[-4000:]}"

    def test_once_unsubscribe_before_fire_cancels(self):
        """L2: once's returned unsubscribe cancels the pending listener.

        Calling the once-unsubscribe before any emit must prevent the listener
        from ever firing and drop the listenerCount to 0.
        """
        result = _run_probe(
            "once-cancel",
            """
            it('once unsubscribe before fire cancels the pending listener', () => {
              const bus = factory()();
              const fn = jest.fn();
              const off = bus.once('ping', fn);
              expect(bus.listenerCount('ping')).toBe(1);
              off();
              expect(bus.listenerCount('ping')).toBe(0);
              const n = bus.emit('ping', 1);
              expect(n).toBe(0);
              expect(fn).not.toHaveBeenCalled();
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"once-cancel probe failed:\n{out[-4000:]}"

    def test_unsubscribe_removes_listener_and_is_idempotent(self):
        """L2: on's unsubscribe removes exactly that listener and is idempotent.

        After unsubscribe the listener no longer fires and the count drops; a
        second unsubscribe call must be a no-op (not remove an unrelated
        listener and not throw).
        """
        result = _run_probe(
            "unsub-idempotent",
            """
            it('on unsubscribe removes that listener and is idempotent', () => {
              const bus = factory()();
              const a = jest.fn();
              const b = jest.fn();
              const offA = bus.on('e', a);
              bus.on('e', b);
              expect(bus.listenerCount('e')).toBe(2);
              offA();
              expect(bus.listenerCount('e')).toBe(1);
              // Idempotent: second call must NOT remove b and must not throw.
              expect(() => offA()).not.toThrow();
              expect(bus.listenerCount('e')).toBe(1);
              const n = bus.emit('e', 'x');
              expect(n).toBe(1);
              expect(a).not.toHaveBeenCalled();
              expect(b).toHaveBeenCalledTimes(1);
              expect(b).toHaveBeenCalledWith('x');
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"unsub-idempotent probe failed:\n{out[-4000:]}"

    def test_emit_with_no_listeners_returns_zero(self):
        """L2: emitting an event with zero listeners returns 0 and does nothing.

        An event that was never subscribed must yield emit() === 0 without
        throwing.
        """
        result = _run_probe(
            "emit-empty",
            """
            it('emit with no listeners returns 0', () => {
              const bus = factory()();
              expect(bus.emit('nobody', 123)).toBe(0);
              expect(bus.listenerCount('nobody')).toBe(0);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"emit-empty probe failed:\n{out[-4000:]}"

    def test_mid_emit_unsubscribe_does_not_skip_current_emit(self):
        """L2: mutating listeners during emit must not skip/double-invoke.

        A listener that unsubscribes a later listener during an in-progress emit
        must NOT prevent that later listener from running for the snapshot taken
        when emit began; but on the NEXT emit the unsubscribed listener is gone.
        An impl iterating the live array fails this.
        """
        result = _run_probe(
            "mid-emit",
            """
            it('mid-emit unsubscribe affects next emit, not the in-flight one', () => {
              const bus = factory()();
              const second = jest.fn();
              let offSecond;
              const first = jest.fn(() => { offSecond(); });
              bus.on('e', first);
              offSecond = bus.on('e', second);
              // First emit: 'first' unsubscribes 'second' mid-emit, but the
              // snapshot already included 'second', so it still runs now.
              const n1 = bus.emit('e', 'a');
              expect(n1).toBe(2);
              expect(first).toHaveBeenCalledTimes(1);
              expect(second).toHaveBeenCalledTimes(1);
              expect(second).toHaveBeenCalledWith('a');
              // Second emit: 'second' is gone now.
              expect(bus.listenerCount('e')).toBe(1);
              const n2 = bus.emit('e', 'b');
              expect(n2).toBe(1);
              expect(first).toHaveBeenCalledTimes(2);
              expect(second).toHaveBeenCalledTimes(1);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"mid-emit probe failed:\n{out[-4000:]}"

    def test_listener_count_tracks_on_once_and_unsubscribe(self):
        """L2: listenerCount reflects on/once additions, unsubscribe, once-fire.

        Counts must rise with on/once, fall on unsubscribe, and drop when a once
        listener fires. Per-event isolation is checked too.
        """
        result = _run_probe(
            "count-tracking",
            """
            it('listenerCount tracks on/once/unsubscribe and once-fire decrement', () => {
              const bus = factory()();
              expect(bus.listenerCount('e')).toBe(0);
              const off1 = bus.on('e', jest.fn());
              bus.once('e', jest.fn());
              expect(bus.listenerCount('e')).toBe(2);
              expect(bus.listenerCount('other')).toBe(0);
              off1();
              expect(bus.listenerCount('e')).toBe(1);
              bus.emit('e', null);   // once fires and is removed
              expect(bus.listenerCount('e')).toBe(0);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"count-tracking probe failed:\n{out[-4000:]}"

    def test_remove_all_with_event_clears_only_that_event(self):
        """L2: removeAll(eventName) clears one event and leaves others intact.

        After removeAll('a'), event 'a' has no listeners but event 'b' still
        fires its listener.
        """
        result = _run_probe(
            "removeall-one",
            """
            it('removeAll(eventName) clears only that event', () => {
              const bus = factory()();
              const a = jest.fn();
              const b = jest.fn();
              bus.on('a', a);
              bus.on('b', b);
              bus.removeAll('a');
              expect(bus.listenerCount('a')).toBe(0);
              expect(bus.listenerCount('b')).toBe(1);
              expect(bus.emit('a', 1)).toBe(0);
              expect(a).not.toHaveBeenCalled();
              expect(bus.emit('b', 2)).toBe(1);
              expect(b).toHaveBeenCalledWith(2);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"removeall-one probe failed:\n{out[-4000:]}"

    def test_remove_all_without_argument_clears_every_event(self):
        """L2: removeAll() with no argument removes listeners for every event.

        After a bare removeAll(), all events have zero listeners and none fire.
        """
        result = _run_probe(
            "removeall-all",
            """
            it('removeAll() clears every event', () => {
              const bus = factory()();
              const a = jest.fn();
              const b = jest.fn();
              bus.on('a', a);
              bus.on('b', b);
              bus.removeAll();
              expect(bus.listenerCount('a')).toBe(0);
              expect(bus.listenerCount('b')).toBe(0);
              expect(bus.emit('a', 1)).toBe(0);
              expect(bus.emit('b', 2)).toBe(0);
              expect(a).not.toHaveBeenCalled();
              expect(b).not.toHaveBeenCalled();
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"removeall-all probe failed:\n{out[-4000:]}"

    def test_on_throws_typeerror_for_non_function_listener(self):
        """L2: on throws a TypeError when the listener is not a function.

        undefined, a number, and an object must each cause on() to throw a
        TypeError; the bad registration must not leave a phantom listener.
        """
        result = _run_probe(
            "typeerror",
            """
            it('on throws TypeError for a non-function listener', () => {
              const bus = factory()();
              expect(() => bus.on('e', undefined)).toThrow(TypeError);
              expect(() => bus.on('e', 123)).toThrow(TypeError);
              expect(() => bus.on('e', {})).toThrow(TypeError);
              expect(bus.listenerCount('e')).toBe(0);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"TypeError-guard probe failed:\n{out[-4000:]}"

    # -----------------------------------------------------------------------
    # L2 — the agent's own suite must pass via the spec'd command.
    # -----------------------------------------------------------------------
    def test_agent_suite_passes(self):
        """L2: the agent's own Jest suite passes via the Acceptance command.

        Mirrors the Acceptance Criteria command exactly:
        ``yarn test packages/shared/__tests__/createEventBus-test.js``.
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
