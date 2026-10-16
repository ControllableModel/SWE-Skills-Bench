"""
Test for the 'vitest-unit-testing' skill (variant ext3).

Task: add an exported factory `createMonotonicClock(): { now: () => number }`
to packages/vite/src/node/utils.ts plus a dedicated vitest spec at
packages/vite/src/node/__tests__/createMonotonicClock.spec.ts.

The factory returns an independent object whose now() guarantees a strictly
increasing sequence of integers: it reads Date.now(); if that fresh value is
strictly greater than the last value this clock returned it returns (and
remembers) the fresh value, otherwise it returns previous+1. Separate
createMonotonicClock() calls keep fully independent internal state.

Verification strategy:
- L1: the deliverable source/spec files exist and minimally well-formed
  (the factory is exported as a function, the spec imports it from ../utils
  and restores the clock between tests).
- L2: DYNAMIC EXECUTION via the repo's native toolchain (vitest, run with
  `pnpm exec vitest run ...`). To avoid trusting the agent's own spec, we drop
  INDEPENDENT driver spec files into the repo's __tests__ directory. Each
  driver imports `createMonotonicClock` from `../utils` and drives Date.now()
  to deterministic values via vi.spyOn so no assertion depends on real elapsed
  time. The drivers pin every documented behavior: strictly-increasing values
  within a frozen instant (T, T+1, T+2), large forward jumps returning the new
  wall value, backward clock motion still strictly increasing, and full
  independence of two instances. A naive implementation (returning Date.now()
  directly, sharing global state across instances, or returning a constant)
  fails at least one driver. We also run the agent's delivered spec.
"""

import os
import re
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/vite"
TESTS_DIR = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "__tests__")
UTILS_TS = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "utils.ts")
AGENT_SPEC = os.path.join(TESTS_DIR, "createMonotonicClock.spec.ts")

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
    """Verify the createMonotonicClock factory and its vitest coverage."""

    REPO_DIR = "/workspace/vite"

    # ------------------------------------------------------------------
    # L1 — deliverables exist / minimally well-formed
    # ------------------------------------------------------------------

    def test_utils_file_exists(self):
        """utils.ts (the modify target) must exist."""
        assert os.path.isfile(UTILS_TS), f"missing {UTILS_TS}"

    def test_create_monotonic_clock_is_exported(self):
        """utils.ts must export a function named createMonotonicClock."""
        with open(UTILS_TS) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+createMonotonicClock\b", src
        ), "createMonotonicClock not exported as a function from utils.ts"

    def test_agent_spec_file_exists(self):
        """The dedicated spec file must be delivered."""
        assert os.path.isfile(AGENT_SPEC), f"missing {AGENT_SPEC}"

    def test_agent_spec_imports_and_restores_clock(self):
        """Spec must import from ../utils and restore the clock between tests."""
        with open(AGENT_SPEC) as f:
            spec = f.read()
        assert "createMonotonicClock" in spec, (
            "spec does not reference createMonotonicClock"
        )
        assert re.search(
            r"from\s+['\"]\.\./utils['\"]", spec
        ), "spec must import from '../utils'"
        # The doc requires the clock be restored after each test so order does not
        # matter: a fake-timer / Date.now spy must be torn down. Accept the common
        # vitest restoration idioms.
        restored = any(
            tok in spec
            for tok in (
                "useRealTimers",
                "restoreAllMocks",
                "mockRestore",
                "afterEach",
                "resetAllMocks",
            )
        )
        assert restored, (
            "spec must restore the clock between tests "
            "(useRealTimers/restoreAllMocks/afterEach)"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic execution against INDEPENDENT driver specs.
    # Each driver imports the real implementation and drives Date.now()
    # deterministically via vi.spyOn, then restores it.
    # ------------------------------------------------------------------

    def test_frozen_instant_strictly_increasing(self):
        """Clock frozen at T: three calls return T, T+1, T+2 (no repeats)."""
        rel = _write_spec(
            "zz_driver_frozen",
            """
            import { afterEach, expect, test, vi } from 'vitest'
            import { createMonotonicClock } from '../utils'

            afterEach(() => vi.restoreAllMocks())

            test('frozen instant yields T, T+1, T+2', () => {
              const T = 1_000_000
              const spy = vi.spyOn(Date, 'now').mockReturnValue(T)
              const clock = createMonotonicClock()
              const a = clock.now()
              const b = clock.now()
              const c = clock.now()
              expect(a).toBe(T)
              expect(b).toBe(T + 1)
              expect(c).toBe(T + 2)
              // strictly increasing, no repeats
              expect(b).toBeGreaterThan(a)
              expect(c).toBeGreaterThan(b)
              expect(new Set([a, b, c]).size).toBe(3)
              spy.mockRestore()
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "frozen-instant sequence wrong (a naive impl returning Date.now() "
            f"directly returns T,T,T and fails)\nSTDOUT:\n{res.stdout}\n"
            f"STDERR:\n{res.stderr}"
        )

    def test_first_call_returns_wall_clock(self):
        """The very first now() returns the current Date.now() value verbatim."""
        rel = _write_spec(
            "zz_driver_first",
            """
            import { afterEach, expect, test, vi } from 'vitest'
            import { createMonotonicClock } from '../utils'

            afterEach(() => vi.restoreAllMocks())

            test('first call equals wall clock', () => {
              const T = 42_000
              vi.spyOn(Date, 'now').mockReturnValue(T)
              const clock = createMonotonicClock()
              expect(clock.now()).toBe(T)
            })

            test('first call equals a different wall clock', () => {
              const T = 9_999_999
              vi.spyOn(Date, 'now').mockReturnValue(T)
              const clock = createMonotonicClock()
              // brand new clock: first read is exactly the wall value, not +1
              expect(clock.now()).toBe(T)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "first now() must equal the wall clock value\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_large_forward_jump_takes_wall_value(self):
        """A big forward jump returns the new wall value, not merely previous+1."""
        rel = _write_spec(
            "zz_driver_jump",
            """
            import { afterEach, expect, test, vi } from 'vitest'
            import { createMonotonicClock } from '../utils'

            afterEach(() => vi.restoreAllMocks())

            test('forward jump returns new wall value', () => {
              const T = 1_000
              const spy = vi.spyOn(Date, 'now').mockReturnValue(T)
              const clock = createMonotonicClock()
              expect(clock.now()).toBe(T)       // first read
              // wall clock jumps far forward
              spy.mockReturnValue(T + 1000)
              const after = clock.now()
              expect(after).toBe(T + 1000)      // exact wall value, NOT T+1
              expect(after).not.toBe(T + 1)
              spy.mockRestore()
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "large forward jump must return the new wall value (T+1000), not "
            f"previous+1\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_backward_clock_still_increasing(self):
        """If the wall clock goes backward, now() still returns previous+1."""
        rel = _write_spec(
            "zz_driver_backward",
            """
            import { afterEach, expect, test, vi } from 'vitest'
            import { createMonotonicClock } from '../utils'

            afterEach(() => vi.restoreAllMocks())

            test('backward wall clock stays strictly increasing', () => {
              const spy = vi.spyOn(Date, 'now').mockReturnValue(5_000)
              const clock = createMonotonicClock()
              const first = clock.now()
              expect(first).toBe(5_000)
              // wall clock moves BACKWARD by a large amount
              spy.mockReturnValue(1)
              const second = clock.now()
              expect(second).toBe(5_001)            // previous + 1
              expect(second).toBeGreaterThan(first)
              // still backward
              const third = clock.now()
              expect(third).toBe(5_002)
              expect(third).toBeGreaterThan(second)
              spy.mockRestore()
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "backward clock motion must still yield strictly increasing values\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_jump_then_freeze_resumes_increment(self):
        """After taking a wall jump, a re-freeze resumes +1 incrementing."""
        rel = _write_spec(
            "zz_driver_jumpfreeze",
            """
            import { afterEach, expect, test, vi } from 'vitest'
            import { createMonotonicClock } from '../utils'

            afterEach(() => vi.restoreAllMocks())

            test('jump then freeze increments from the jumped value', () => {
              const spy = vi.spyOn(Date, 'now').mockReturnValue(100)
              const clock = createMonotonicClock()
              expect(clock.now()).toBe(100)
              spy.mockReturnValue(100_000)
              expect(clock.now()).toBe(100_000)     // took the jump
              // now frozen at the jumped instant -> +1 each time
              expect(clock.now()).toBe(100_001)
              expect(clock.now()).toBe(100_002)
              spy.mockRestore()
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "after a jump the clock must resume +1 incrementing from the new base\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_two_instances_independent(self):
        """Two clocks keep fully independent state; advancing one not the other."""
        rel = _write_spec(
            "zz_driver_independent",
            """
            import { afterEach, expect, test, vi } from 'vitest'
            import { createMonotonicClock } from '../utils'

            afterEach(() => vi.restoreAllMocks())

            test('independent instances at a frozen instant', () => {
              const T = 7_000
              vi.spyOn(Date, 'now').mockReturnValue(T)
              const a = createMonotonicClock()
              const b = createMonotonicClock()
              // each fresh clock returns the wall value on its FIRST call
              expect(a.now()).toBe(T)
              expect(b.now()).toBe(T)
              // advance only a
              expect(a.now()).toBe(T + 1)
              expect(a.now()).toBe(T + 2)
              // b is untouched: its next call is only its 2nd, so T+1
              expect(b.now()).toBe(T + 1)
              // and a continues from where IT left off
              expect(a.now()).toBe(T + 3)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "instances are NOT independent (shared global state). A naive impl "
            "reusing a module-level counter fails here\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_independent_different_bases(self):
        """Clocks created at different wall instants track separate bases."""
        rel = _write_spec(
            "zz_driver_diffbase",
            """
            import { afterEach, expect, test, vi } from 'vitest'
            import { createMonotonicClock } from '../utils'

            afterEach(() => vi.restoreAllMocks())

            test('clocks created at different instants are independent', () => {
              const spy = vi.spyOn(Date, 'now').mockReturnValue(1_000)
              const a = createMonotonicClock()
              expect(a.now()).toBe(1_000)
              // create the second clock at a later instant
              spy.mockReturnValue(50_000)
              const b = createMonotonicClock()
              expect(b.now()).toBe(50_000)      // b's first read = current wall
              // a is still frozen-ish: its next reads ignore b entirely
              spy.mockReturnValue(50_000)
              expect(a.now()).toBe(50_000)      // a now also sees the wall jump
              expect(a.now()).toBe(50_001)
              // b keeps its own counter
              expect(b.now()).toBe(50_001)
              expect(b.now()).toBe(50_002)
              spy.mockRestore()
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "clocks with different creation instants are not independent\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_returns_integers_and_object_shape(self):
        """now() returns integers and the factory yields { now } objects."""
        rel = _write_spec(
            "zz_driver_shape",
            """
            import { afterEach, expect, test, vi } from 'vitest'
            import { createMonotonicClock } from '../utils'

            afterEach(() => vi.restoreAllMocks())

            test('object shape and integer results', () => {
              vi.spyOn(Date, 'now').mockReturnValue(123_456)
              const clock = createMonotonicClock()
              expect(typeof clock).toBe('object')
              expect(typeof clock.now).toBe('function')
              const v1 = clock.now()
              const v2 = clock.now()
              expect(Number.isInteger(v1)).toBe(true)
              expect(Number.isInteger(v2)).toBe(true)
              expect(v1).toBe(123_456)
              expect(v2).toBe(123_457)
              // two separate factory calls produce distinct objects
              const other = createMonotonicClock()
              expect(other).not.toBe(clock)
              expect(other.now).not.toBe(clock.now)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "factory shape or integer guarantee wrong\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_long_run_strictly_monotonic(self):
        """A long frozen run yields a strictly increasing, contiguous sequence."""
        rel = _write_spec(
            "zz_driver_longrun",
            """
            import { afterEach, expect, test, vi } from 'vitest'
            import { createMonotonicClock } from '../utils'

            afterEach(() => vi.restoreAllMocks())

            test('1000 calls within one frozen instant are strictly increasing', () => {
              const T = 2_000_000
              vi.spyOn(Date, 'now').mockReturnValue(T)
              const clock = createMonotonicClock()
              const vals: number[] = []
              for (let i = 0; i < 1000; i++) vals.push(clock.now())
              expect(vals[0]).toBe(T)
              expect(vals[vals.length - 1]).toBe(T + 999)
              for (let i = 1; i < vals.length; i++) {
                expect(vals[i]).toBe(vals[i - 1] + 1)
              }
              // no duplicates at all
              expect(new Set(vals).size).toBe(vals.length)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "long frozen run is not strictly monotonic / contiguous\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_agent_delivered_spec_passes(self):
        """The agent's own delivered spec must pass under native vitest."""
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        rel = os.path.relpath(AGENT_SPEC, REPO_DIR)
        res = _vitest(rel)
        assert res.returncode == 0, (
            "agent's createMonotonicClock.spec.ts does not pass\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
        combined = (res.stdout + res.stderr).lower()
        assert "no test" not in combined, "agent spec contains no tests"
