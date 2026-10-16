"""
Test for the 'vitest-unit-testing' skill (variant ext9).

Task: add a minimal, dependency-free typed `EventEmitter` class at
packages/vite/src/node/eventEmitter.ts (with on/once/off/emit/listenerCount)
plus a dedicated vitest spec at
packages/vite/src/node/__tests__/eventEmitter.spec.ts.

NOTE: this is a DIFFERENT task from ext1 (which added a parseRequestQuery
URL-query helper). Here the deliverable is an event-emitter primitive whose
listener-dispatch semantics must be exact.

Verification strategy:
- L1: the deliverable source/spec files exist, the `EventEmitter` class is
  exported, and the agent's spec imports it from '../eventEmitter' and contains
  real mock-based assertions.
- L2: DYNAMIC EXECUTION via the repo's native toolchain (vitest, run with
  `pnpm exec vitest run ...`). To avoid trusting the agent's own spec, we write
  INDEPENDENT driver spec files into the repo __tests__ dir that import
  `EventEmitter` from '../eventEmitter' and exercise the exact required
  semantics: registration-order dispatch, once-fires-once, unsubscribe removes
  exactly one listener, snapshot-iteration during emit (mutation while emitting
  does not affect the in-flight dispatch), event isolation, listenerCount, and
  double-unsubscribe safety. A naive implementation (mutating the live listener
  array during dispatch, `once` firing twice, unsubscribe affecting the wrong
  listener, or shared listener storage across events) makes at least one of
  these driver specs fail. We also run the agent's delivered spec.
"""

import os
import re
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/vite"
TESTS_DIR = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "__tests__")
EMITTER_TS = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "eventEmitter.ts")
AGENT_SPEC = os.path.join(TESTS_DIR, "eventEmitter.spec.ts")

# abs paths of driver specs we drop in; filled by _write_spec, removed at teardown.
_DRIVER_FILES = []


def _vitest(rel_spec_path, timeout=600):
    """Run a single spec file via the repo's native vitest from repo root."""
    cmd = ["pnpm", "exec", "vitest", "run", rel_spec_path]
    return subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _write_spec(name, body):
    """Write a driver spec into the repo __tests__ dir; return its repo-rel path."""
    assert os.path.isdir(TESTS_DIR), f"tests dir missing: {TESTS_DIR}"
    fname = name if name.endswith(".spec.ts") else name + ".spec.ts"
    abspath = os.path.join(TESTS_DIR, fname)
    with open(abspath, "w") as f:
        f.write(textwrap.dedent(body).lstrip("\n"))
    rel = os.path.relpath(abspath, REPO_DIR)
    _DRIVER_FILES.append(abspath)
    return rel


@pytest.fixture(scope="module", autouse=True)
def _cleanup_driver_specs():
    """Remove any driver specs we created so we leave the repo clean."""
    yield
    for p in _DRIVER_FILES:
        try:
            os.remove(p)
        except OSError:
            pass


class TestVitestUnitTesting:
    """Verify the EventEmitter primitive and its vitest coverage."""

    REPO_DIR = "/workspace/vite"

    # ------------------------------------------------------------------
    # L1 — deliverables exist / minimally well-formed
    # ------------------------------------------------------------------

    def test_emitter_file_exists(self):
        """eventEmitter.ts (the new source target) must exist."""
        assert os.path.isfile(EMITTER_TS), f"missing {EMITTER_TS}"

    def test_emitter_class_is_exported(self):
        """eventEmitter.ts must export a class named EventEmitter."""
        with open(EMITTER_TS) as f:
            src = f.read()
        assert re.search(
            r"export\s+class\s+EventEmitter\b", src
        ), "EventEmitter not exported as a class from eventEmitter.ts"

    def test_emitter_has_required_methods(self):
        """The class source must declare on/once/off/emit/listenerCount methods."""
        with open(EMITTER_TS) as f:
            src = f.read()
        for method in ("on", "once", "off", "emit", "listenerCount"):
            assert re.search(
                rf"\b{method}\s*<", src
            ) or re.search(rf"\b{method}\s*\(", src), (
                f"method '{method}' not declared in EventEmitter"
            )

    def test_agent_spec_file_exists(self):
        """The dedicated spec file must be delivered."""
        assert os.path.isfile(AGENT_SPEC), f"missing {AGENT_SPEC}"

    def test_agent_spec_imports_from_emitter(self):
        """The spec must import EventEmitter from ../eventEmitter (not redefine it)."""
        with open(AGENT_SPEC) as f:
            spec = f.read()
        assert "EventEmitter" in spec, "spec does not reference EventEmitter"
        assert re.search(
            r"from\s+['\"]\.\./eventEmitter['\"]", spec
        ), "spec must import from '../eventEmitter'"

    def test_agent_spec_uses_mocks(self):
        """The spec must use vitest mock listeners (vi.fn) per the requirement."""
        with open(AGENT_SPEC) as f:
            spec = f.read()
        assert "vi.fn" in spec, (
            "spec must use mock listener functions (vi.fn) to assert exact "
            "call counts/arguments per the acceptance criteria"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic execution against INDEPENDENT driver specs.
    # Each test drops a focused spec that imports the real implementation
    # and asserts the precise required behavior via native vitest.
    # ------------------------------------------------------------------

    def test_emit_order_and_payload(self):
        """Two `on` listeners both fire once, in registration order, with payload."""
        rel = _write_spec(
            "zz_driver_order",
            """
            import { expect, test, vi } from 'vitest'
            import { EventEmitter } from '../eventEmitter'

            test('registration order + payload', () => {
              type E = { tick: number }
              const ee = new EventEmitter<E>()
              const calls: string[] = []
              const a = vi.fn(() => calls.push('a'))
              const b = vi.fn(() => calls.push('b'))
              ee.on('tick', a)
              ee.on('tick', b)
              ee.emit('tick', 42)
              expect(a).toHaveBeenCalledTimes(1)
              expect(b).toHaveBeenCalledTimes(1)
              expect(a).toHaveBeenCalledWith(42)
              expect(b).toHaveBeenCalledWith(42)
              expect(calls).toEqual(['a', 'b'])  // registration order
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "emit order/payload wrong\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_once_fires_exactly_once(self):
        """A `once` listener is invoked at most once across multiple emits."""
        rel = _write_spec(
            "zz_driver_once",
            """
            import { expect, test, vi } from 'vitest'
            import { EventEmitter } from '../eventEmitter'

            test('once fires once', () => {
              type E = { go: string }
              const ee = new EventEmitter<E>()
              const f = vi.fn()
              ee.once('go', f)
              ee.emit('go', 'x')
              ee.emit('go', 'y')
              ee.emit('go', 'z')
              expect(f).toHaveBeenCalledTimes(1)
              expect(f).toHaveBeenCalledWith('x')
              // a naive impl that leaves the once-listener registered fails above
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "once did not fire exactly once\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_unsubscribe_removes_exactly_that_listener(self):
        """`on` returns an unsubscribe that removes exactly its own listener."""
        rel = _write_spec(
            "zz_driver_unsub",
            """
            import { expect, test, vi } from 'vitest'
            import { EventEmitter } from '../eventEmitter'

            test('unsubscribe removes one listener', () => {
              type E = { ev: number }
              const ee = new EventEmitter<E>()
              const keep = vi.fn()
              const drop = vi.fn()
              ee.on('ev', keep)
              const off = ee.on('ev', drop)
              off()
              ee.emit('ev', 1)
              expect(drop).toHaveBeenCalledTimes(0)
              expect(keep).toHaveBeenCalledTimes(1)
              expect(keep).toHaveBeenCalledWith(1)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "unsubscribe affected the wrong listener\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_double_unsubscribe_is_safe(self):
        """Calling the unsubscribe function twice is a no-op (no throw/double-remove)."""
        rel = _write_spec(
            "zz_driver_double_unsub",
            """
            import { expect, test, vi } from 'vitest'
            import { EventEmitter } from '../eventEmitter'

            test('double unsubscribe safe', () => {
              type E = { ev: number }
              const ee = new EventEmitter<E>()
              const a = vi.fn()
              const b = vi.fn()
              const offA = ee.on('ev', a)
              ee.on('ev', b)
              offA()
              expect(() => offA()).not.toThrow()  // second call no-op
              ee.emit('ev', 7)
              expect(a).toHaveBeenCalledTimes(0)
              expect(b).toHaveBeenCalledTimes(1)  // not removed by stray 2nd unsub
              expect(ee.listenerCount('ev')).toBe(1)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "double unsubscribe not safe / removed an extra listener\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_off_removes_one_registration_at_a_time(self):
        """Same fn registered twice fires twice; `off` removes one registration."""
        rel = _write_spec(
            "zz_driver_off_dup",
            """
            import { expect, test, vi } from 'vitest'
            import { EventEmitter } from '../eventEmitter'

            test('off removes one of duplicate registrations', () => {
              type E = { ev: number }
              const ee = new EventEmitter<E>()
              const f = vi.fn()
              ee.on('ev', f)
              ee.on('ev', f)            // same fn twice
              expect(ee.listenerCount('ev')).toBe(2)
              ee.emit('ev', 1)
              expect(f).toHaveBeenCalledTimes(2)  // both registrations fire
              ee.off('ev', f)           // remove just ONE registration
              expect(ee.listenerCount('ev')).toBe(1)
              ee.emit('ev', 2)
              expect(f).toHaveBeenCalledTimes(3)  // one remained -> +1
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "duplicate registration / single-removal semantics wrong\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_off_unregistered_is_noop(self):
        """Removing a listener that was never registered is a harmless no-op."""
        rel = _write_spec(
            "zz_driver_off_noop",
            """
            import { expect, test, vi } from 'vitest'
            import { EventEmitter } from '../eventEmitter'

            test('off unknown is no-op', () => {
              type E = { ev: number }
              const ee = new EventEmitter<E>()
              const a = vi.fn()
              const never = vi.fn()
              ee.on('ev', a)
              expect(() => ee.off('ev', never)).not.toThrow()
              expect(() => ee.off('nope' as any, never)).not.toThrow()
              expect(ee.listenerCount('ev')).toBe(1)
              ee.emit('ev', 1)
              expect(a).toHaveBeenCalledTimes(1)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "off of unregistered listener was not a no-op\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_emit_no_listeners_is_noop(self):
        """Emitting an event with no listeners must not throw."""
        rel = _write_spec(
            "zz_driver_empty_emit",
            """
            import { expect, test } from 'vitest'
            import { EventEmitter } from '../eventEmitter'

            test('emit with no listeners', () => {
              type E = { a: number; b: string }
              const ee = new EventEmitter<E>()
              expect(() => ee.emit('a', 1)).not.toThrow()
              expect(ee.listenerCount('a')).toBe(0)
              expect(ee.listenerCount('b')).toBe(0)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "emit with no listeners threw / wrong count\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_listener_count_tracks_on_once_off(self):
        """listenerCount reflects on/once additions and drops after a once fires."""
        rel = _write_spec(
            "zz_driver_count",
            """
            import { expect, test, vi } from 'vitest'
            import { EventEmitter } from '../eventEmitter'

            test('listenerCount lifecycle', () => {
              type E = { ev: number }
              const ee = new EventEmitter<E>()
              expect(ee.listenerCount('ev')).toBe(0)
              ee.on('ev', vi.fn())
              expect(ee.listenerCount('ev')).toBe(1)
              ee.once('ev', vi.fn())     // a pending once still counts
              expect(ee.listenerCount('ev')).toBe(2)
              ee.emit('ev', 1)           // once fires + is removed
              expect(ee.listenerCount('ev')).toBe(1)
              ee.emit('ev', 2)           // stable now
              expect(ee.listenerCount('ev')).toBe(1)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "listenerCount lifecycle wrong\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_event_isolation(self):
        """Listeners for different events are isolated; emit 'a' never calls 'b'."""
        rel = _write_spec(
            "zz_driver_isolation",
            """
            import { expect, test, vi } from 'vitest'
            import { EventEmitter } from '../eventEmitter'

            test('event isolation', () => {
              type E = { a: number; b: number }
              const ee = new EventEmitter<E>()
              const fa = vi.fn()
              const fb = vi.fn()
              ee.on('a', fa)
              ee.on('b', fb)
              ee.emit('a', 1)
              expect(fa).toHaveBeenCalledTimes(1)
              expect(fa).toHaveBeenCalledWith(1)
              expect(fb).toHaveBeenCalledTimes(0)  // b never called by emit('a')
              ee.emit('b', 2)
              expect(fb).toHaveBeenCalledTimes(1)
              expect(fb).toHaveBeenCalledWith(2)
              expect(fa).toHaveBeenCalledTimes(1)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "events are not isolated (shared listener storage?)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_dispatch_iterates_over_snapshot(self):
        """Adding/removing listeners DURING emit must not affect the in-flight dispatch."""
        rel = _write_spec(
            "zz_driver_snapshot",
            """
            import { expect, test, vi } from 'vitest'
            import { EventEmitter } from '../eventEmitter'

            test('emit iterates a snapshot', () => {
              type E = { ev: number }
              const ee = new EventEmitter<E>()
              const added = vi.fn()
              const second = vi.fn()
              // first listener adds a NEW listener mid-dispatch; it must NOT be
              // called by this same emit (snapshot semantics).
              const first = vi.fn(() => {
                ee.on('ev', added)
              })
              ee.on('ev', first)
              ee.on('ev', second)
              ee.emit('ev', 1)
              expect(first).toHaveBeenCalledTimes(1)
              expect(second).toHaveBeenCalledTimes(1)  // already-snapshotted still fires
              expect(added).toHaveBeenCalledTimes(0)    // added mid-emit -> not this round
              // but it IS registered for the next emit
              ee.emit('ev', 2)
              expect(added).toHaveBeenCalledTimes(1)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "dispatch does not iterate over a snapshot (mutating live array)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_remove_during_emit_keeps_snapshot(self):
        """Removing a not-yet-notified listener during emit still notifies it this round."""
        rel = _write_spec(
            "zz_driver_remove_snapshot",
            """
            import { expect, test, vi } from 'vitest'
            import { EventEmitter } from '../eventEmitter'

            test('remove during emit honors snapshot', () => {
              type E = { ev: number }
              const ee = new EventEmitter<E>()
              const victim = vi.fn()
              // first listener unsubscribes the (later) victim mid-dispatch.
              const first = vi.fn(() => offVictim())
              ee.on('ev', first)
              const offVictim = ee.on('ev', victim)
              ee.emit('ev', 1)
              // victim was part of the snapshot -> still called THIS round
              expect(victim).toHaveBeenCalledTimes(1)
              // but removed for subsequent emits
              ee.emit('ev', 2)
              expect(victim).toHaveBeenCalledTimes(1)
              expect(first).toHaveBeenCalledTimes(2)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "removal during emit corrupted the in-flight snapshot\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_agent_delivered_spec_passes(self):
        """The agent's own delivered spec must pass under native vitest."""
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        rel = os.path.relpath(AGENT_SPEC, REPO_DIR)
        res = _vitest(rel)
        assert res.returncode == 0, (
            "agent's eventEmitter.spec.ts does not pass\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
        combined = (res.stdout + res.stderr).lower()
        assert "no test" not in combined, "agent spec contains no tests"
