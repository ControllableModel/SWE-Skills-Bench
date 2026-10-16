"""
Test for the 'vitest-unit-testing' skill (variant ext8).

Task: add an exported promise-timeout helper

    export function withTimeout<T>(
      promise: Promise<T>,
      ms: number,
      message?: string,
    ): Promise<T>

to packages/vite/src/node/utils.ts, plus a dedicated vitest spec at
packages/vite/src/node/__tests__/withTimeout.spec.ts that drives time
deterministically with fake timers.

Behavior under test (from the requirement doc):
- promise settles before `ms`  -> returned promise settles identically.
- `ms` elapses first           -> rejects with Error(message) or
                                  "Timed out after {ms}ms" if message omitted.
- the internal timer is cleared once the race settles (no dangling setTimeout).
- a pre-deadline rejection propagates the ORIGINAL error, not a timeout error.

Verification strategy:
- L1: deliverable source/spec files exist and the export / signature / import
  / fake-timer usage are minimally well-formed.
- L2: DYNAMIC EXECUTION via the repo's native toolchain (vitest, run with
  `pnpm exec vitest run ...`). To avoid trusting the agent's own spec, we drop
  INDEPENDENT driver spec files into the repo __tests__ dir that import
  `withTimeout` from '../utils' and exercise the exact required behaviors under
  vitest fake timers. A naive implementation (never clearing the timer,
  ignoring the custom message, swallowing a real rejection into a timeout
  error, or always resolving) makes at least one driver spec fail. We also run
  the agent's own delivered spec.
"""

import os
import re
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/vite"
TESTS_DIR = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "__tests__")
UTILS_TS = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "utils.ts")
AGENT_SPEC = os.path.join(TESTS_DIR, "withTimeout.spec.ts")

# absolute paths of driver specs we drop in; filled by _write_spec.
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
    """Verify the withTimeout helper and its vitest coverage (ext8)."""

    REPO_DIR = "/workspace/vite"

    # ------------------------------------------------------------------
    # L1 — deliverables exist / minimally well-formed
    # ------------------------------------------------------------------

    def test_utils_file_exists(self):
        """utils.ts (the modify target) must exist."""
        assert os.path.isfile(UTILS_TS), f"missing {UTILS_TS}"

    def test_with_timeout_is_exported(self):
        """utils.ts must export a function named withTimeout."""
        with open(UTILS_TS) as f:
            src = f.read()
        assert re.search(
            r"export\s+(?:async\s+)?function\s+withTimeout\b", src
        ), "withTimeout not exported as a function from utils.ts"

    def test_with_timeout_signature_shape(self):
        """The export must take a promise, a numeric ms, and an optional message."""
        with open(UTILS_TS) as f:
            src = f.read()
        # locate the declaration and grab its parameter list (may span lines).
        m = re.search(
            r"export\s+(?:async\s+)?function\s+withTimeout\s*<[^>]*>?\s*\(",
            src,
        )
        # fall back to a non-generic signature if the agent omitted <T>.
        if not m:
            m = re.search(r"export\s+(?:async\s+)?function\s+withTimeout\s*\(", src)
        assert m, "could not locate withTimeout declaration"
        tail = src[m.end():]
        depth = 1
        params = []
        for ch in tail:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            params.append(ch)
        params = "".join(params)
        assert "promise" in params.lower(), f"no promise param: {params!r}"
        assert re.search(r"\bms\b", params), f"no ms param: {params!r}"
        assert "message" in params.lower(), f"no message param: {params!r}"
        assert "?" in params, f"message should be optional (?): {params!r}"

    def test_agent_spec_file_exists(self):
        """The dedicated withTimeout spec file must be delivered."""
        assert os.path.isfile(AGENT_SPEC), f"missing {AGENT_SPEC}"

    def test_agent_spec_imports_from_utils(self):
        """The spec must import withTimeout from ../utils (not redefine it)."""
        with open(AGENT_SPEC) as f:
            spec = f.read()
        assert "withTimeout" in spec, "spec does not reference withTimeout"
        assert re.search(
            r"from\s+['\"]\.\./utils['\"]", spec
        ), "spec must import from '../utils'"

    def test_agent_spec_controls_time_deterministically(self):
        """The spec must drive a controlled clock (no real elapsed-time waits)."""
        with open(AGENT_SPEC) as f:
            spec = f.read()
        assert re.search(r"useFakeTimers\s*\(", spec), (
            "spec must call vi.useFakeTimers() so no test waits on real time"
        )
        # must restore the timer environment so test order does not matter.
        assert re.search(r"useRealTimers\s*\(|restoreAllMocks\s*\(", spec), (
            "spec must restore the timer environment after each test "
            "(vi.useRealTimers()/vi.restoreAllMocks())"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic execution against INDEPENDENT driver specs.
    # Each test drops a focused spec that imports the real implementation
    # and asserts the precise required behavior via vitest fake timers.
    # ------------------------------------------------------------------

    def test_pre_deadline_resolution_passes_through(self):
        """A promise that resolves before `ms` settles the result, no timeout."""
        rel = _write_spec(
            "zz_driver_resolve",
            """
            import { afterEach, beforeEach, expect, test, vi } from 'vitest'
            import { withTimeout } from '../utils'

            beforeEach(() => vi.useFakeTimers())
            afterEach(() => vi.useRealTimers())

            test('resolves before the deadline', async () => {
              let resolveInner!: (v: number) => void
              const inner = new Promise<number>((r) => { resolveInner = r })
              const raced = withTimeout(inner, 100)

              // settle the inner promise strictly before the timer would fire.
              resolveInner(42)
              await vi.advanceTimersByTimeAsync(50)

              await expect(raced).resolves.toBe(42)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "pre-deadline resolution did not pass through (a stub that always "
            "times out or ignores the inner value fails here)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_default_timeout_message(self):
        """When the deadline fires and no message given -> 'Timed out after {ms}ms'."""
        rel = _write_spec(
            "zz_driver_default_msg",
            """
            import { afterEach, beforeEach, expect, test, vi } from 'vitest'
            import { withTimeout } from '../utils'

            beforeEach(() => vi.useFakeTimers())
            afterEach(() => vi.useRealTimers())

            test('default timeout message', async () => {
              const never = new Promise<number>(() => {})
              const raced = withTimeout(never, 100)
              const assertion = expect(raced).rejects.toThrow('Timed out after 100ms')
              await vi.advanceTimersByTimeAsync(100)
              await assertion
            })

            test('default message exact for a different ms', async () => {
              const never = new Promise<number>(() => {})
              const raced = withTimeout(never, 250)
              const assertion = expect(raced).rejects.toThrowError(
                new Error('Timed out after 250ms'),
              )
              await vi.advanceTimersByTimeAsync(250)
              await assertion
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "default timeout message wrong (must be exactly "
            "'Timed out after {ms}ms')\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_custom_timeout_message(self):
        """A provided custom message must be used verbatim, not the default."""
        rel = _write_spec(
            "zz_driver_custom_msg",
            """
            import { afterEach, beforeEach, expect, test, vi } from 'vitest'
            import { withTimeout } from '../utils'

            beforeEach(() => vi.useFakeTimers())
            afterEach(() => vi.useRealTimers())

            test('custom timeout message', async () => {
              const never = new Promise<number>(() => {})
              const raced = withTimeout(never, 100, 'resolve hung')
              const assertion = expect(raced).rejects.toThrow('resolve hung')
              await vi.advanceTimersByTimeAsync(100)
              await assertion
            })

            test('custom message is NOT the default fallback', async () => {
              const never = new Promise<number>(() => {})
              const raced = withTimeout(never, 100, 'resolve hung')
              const err = await raced.catch((e) => e as Error)
              expect(err).toBeInstanceOf(Error)
              expect(err.message).toBe('resolve hung')
              expect(err.message).not.toBe('Timed out after 100ms')
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "custom message ignored (a naive impl that always uses the default "
            "timeout text fails here)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_pre_deadline_rejection_propagates_original(self):
        """A rejection before the deadline propagates the ORIGINAL error."""
        rel = _write_spec(
            "zz_driver_reject",
            """
            import { afterEach, beforeEach, expect, test, vi } from 'vitest'
            import { withTimeout } from '../utils'

            beforeEach(() => vi.useFakeTimers())
            afterEach(() => vi.useRealTimers())

            test('original rejection propagates, not a timeout error', async () => {
              const original = new Error('boom-original')
              let rejectInner!: (e: unknown) => void
              const inner = new Promise<number>((_r, rej) => { rejectInner = rej })
              const raced = withTimeout(inner, 100, 'should-not-see-this')

              rejectInner(original)
              await vi.advanceTimersByTimeAsync(10)

              const err = await raced.catch((e) => e as Error)
              expect(err).toBe(original)
              expect(err.message).toBe('boom-original')
              expect(err.message).not.toBe('should-not-see-this')
              expect(err.message).not.toContain('Timed out')
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "pre-deadline rejection not propagated as the original error (a naive "
            "impl that converts every failure to a timeout error fails here)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_timer_is_cleared_after_resolution(self):
        """After the inner promise wins, no setTimeout may remain pending."""
        rel = _write_spec(
            "zz_driver_clear",
            """
            import { afterEach, beforeEach, expect, test, vi } from 'vitest'
            import { withTimeout } from '../utils'

            beforeEach(() => vi.useFakeTimers())
            afterEach(() => vi.useRealTimers())

            test('timer cleared once the inner promise resolves', async () => {
              let resolveInner!: (v: number) => void
              const inner = new Promise<number>((r) => { resolveInner = r })
              const raced = withTimeout(inner, 100)

              resolveInner(7)
              await expect(raced).resolves.toBe(7)

              // the race has settled; a correct impl cleared its timeout, so no
              // timer should remain queued.
              expect(vi.getTimerCount()).toBe(0)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "internal timer not cleared after the inner promise resolved "
            "(dangling setTimeout)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_late_inner_settlement_after_timeout_is_safe(self):
        """After a timeout fires, a late inner settlement must not throw or flip."""
        rel = _write_spec(
            "zz_driver_late",
            """
            import { afterEach, beforeEach, expect, test, vi } from 'vitest'
            import { withTimeout } from '../utils'

            beforeEach(() => vi.useFakeTimers())
            afterEach(() => vi.useRealTimers())

            test('late inner settlement does not alter the timeout result', async () => {
              let resolveInner!: (v: number) => void
              const inner = new Promise<number>((r) => { resolveInner = r })
              const raced = withTimeout(inner, 100)

              const assertion = expect(raced).rejects.toThrow('Timed out after 100ms')
              await vi.advanceTimersByTimeAsync(100)
              await assertion

              // inner settles AFTER the timeout already won; must stay rejected
              // and must not introduce a new pending timer or unhandled state.
              resolveInner(999)
              await vi.advanceTimersByTimeAsync(50)
              await expect(raced).rejects.toThrow('Timed out after 100ms')
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "late inner settlement after timeout altered the result or threw\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_already_resolved_wins_with_zero_ms(self):
        """ms=0: an already-resolved promise still settles before the timer tick."""
        rel = _write_spec(
            "zz_driver_zero",
            """
            import { afterEach, beforeEach, expect, test, vi } from 'vitest'
            import { withTimeout } from '../utils'

            beforeEach(() => vi.useFakeTimers())
            afterEach(() => vi.useRealTimers())

            test('already-resolved wins even with ms=0', async () => {
              const raced = withTimeout(Promise.resolve('ready'), 0)
              // microtasks settle the resolved promise before any timer tick.
              await expect(raced).resolves.toBe('ready')
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "ms=0 with an already-resolved promise did not resolve to the value\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_returns_a_real_promise(self):
        """withTimeout must return a thenable Promise instance."""
        rel = _write_spec(
            "zz_driver_thenable",
            """
            import { afterEach, beforeEach, expect, test, vi } from 'vitest'
            import { withTimeout } from '../utils'

            beforeEach(() => vi.useFakeTimers())
            afterEach(() => vi.useRealTimers())

            test('returns a Promise', async () => {
              const r = withTimeout(Promise.resolve(1), 100)
              expect(typeof (r as any).then).toBe('function')
              expect(r).toBeInstanceOf(Promise)
              await vi.advanceTimersByTimeAsync(0)
              await expect(r).resolves.toBe(1)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "withTimeout did not return a real Promise\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_timeout_rejects_with_error_instance(self):
        """The timeout rejection must be an actual Error (with a .message)."""
        rel = _write_spec(
            "zz_driver_error_instance",
            """
            import { afterEach, beforeEach, expect, test, vi } from 'vitest'
            import { withTimeout } from '../utils'

            beforeEach(() => vi.useFakeTimers())
            afterEach(() => vi.useRealTimers())

            test('timeout rejection is an Error instance', async () => {
              const never = new Promise<number>(() => {})
              const raced = withTimeout(never, 100)
              const p = raced.catch((e) => e)
              await vi.advanceTimersByTimeAsync(100)
              const err = await p
              expect(err).toBeInstanceOf(Error)
              expect((err as Error).message).toBe('Timed out after 100ms')
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "timeout did not reject with an Error instance carrying the message\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_agent_delivered_spec_passes(self):
        """The agent's own delivered withTimeout.spec.ts must pass under vitest."""
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        rel = os.path.relpath(AGENT_SPEC, REPO_DIR)
        res = _vitest(rel)
        assert res.returncode == 0, (
            "agent's withTimeout.spec.ts does not pass\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
        combined = (res.stdout + res.stderr).lower()
        assert "no test" not in combined, "agent spec contains no tests"
