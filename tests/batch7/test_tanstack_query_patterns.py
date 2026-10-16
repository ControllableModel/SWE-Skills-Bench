"""
Test for 'tanstack-query-patterns' skill (variant ext7) — Retry-and-Backoff Planner.

The agent must add a pure, self-contained `planRetry(input): { shouldRetry, delayMs }`
utility to `@tanstack/query-core` (packages/query-core/src/retryPlan.ts), re-export
`planRetry` and the `RetryPlanInput` type from the package entry point
(packages/query-core/src/index.ts), and add a vitest suite
(packages/query-core/src/__tests__/retryPlan.test.tsx).

Planning semantics under test (from the requirement doc):
  * `retry`:
      - number n  -> shouldRetry while failureCount <= n (default n = 3 when omitted)
      - true      -> always retry; false -> never retry
      - function  -> called (failureCount, error); boolean return decides
  * `retryDelay` (only evaluated when retrying):
      - number    -> used directly
      - function  -> called (failureCount, error); numeric return used
      - omitted   -> exponential backoff Math.min(1000 * 2 ** (failureCount - 1), 30000)
  * When shouldRetry === false: delayMs MUST be 0 and retryDelay MUST NOT be evaluated.
  * Pure: no input mutation, no QueryClient/cache/timers/network; callbacks invoked at most once.

Strategy: rather than trusting the agent's own test file, this suite injects its
OWN focused vitest probe specs into packages/query-core/src/__tests__/ (where the
package's vitest config picks them up: test.dir === './src') and runs them with the
repo's native vitest — the SAME command family the Acceptance Criteria specifies
(`pnpm --filter @tanstack/query-core exec vitest run src/__tests__/<probe>`). Each
probe imports `planRetry` from the package index (`..`) and asserts concrete
{ shouldRetry, delayMs } values plus callback-invocation counts, so a stub /
hardcoded / always-retry / ignores-default-backoff implementation fails.
"""

import os
import subprocess

import pytest


REPO_DIR = "/workspace/query"
CORE_DIR = os.path.join(REPO_DIR, "packages", "query-core")
SRC_DIR = os.path.join(CORE_DIR, "src")
TESTS_SUBDIR = os.path.join(SRC_DIR, "__tests__")

# Probe specs we inject live under src/__tests__ so the package's vitest
# config (test.dir === './src') picks them up. Distinct name to avoid clobber.
PROBE_BASENAME = "zzRetryPlanProbe.gen.test.tsx"
PROBE_PATH = os.path.join(TESTS_SUBDIR, PROBE_BASENAME)

INSTALL_TIMEOUT = 1800
VITEST_TIMEOUT = 600


def _pnpm_env():
    env = dict(os.environ)
    env.setdefault("CI", "")
    env.setdefault("npm_config_yes", "true")
    return env


@pytest.fixture(scope="module", autouse=True)
def _ensure_repo_dependencies():
    """Install workspace deps once so native vitest can run."""
    assert os.path.isdir(REPO_DIR), f"repo not found: {REPO_DIR}"
    assert os.path.isdir(CORE_DIR), f"query-core package not found: {CORE_DIR}"
    node_modules = os.path.join(REPO_DIR, "node_modules")
    if not os.path.isdir(node_modules):
        result = subprocess.run(
            ["pnpm", "install", "--frozen-lockfile", "--prefer-offline"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT,
            env=_pnpm_env(),
        )
        if result.returncode != 0:
            result = subprocess.run(
                ["pnpm", "install", "--prefer-offline"],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=INSTALL_TIMEOUT,
                env=_pnpm_env(),
            )
        assert result.returncode == 0, (
            "pnpm install failed:\n"
            f"stdout={result.stdout[-3000:]}\nstderr={result.stderr[-3000:]}"
        )
    yield
    try:
        if os.path.isfile(PROBE_PATH):
            os.remove(PROBE_PATH)
    except OSError:
        pass


def _run_vitest_on_probe(probe_source):
    """Write `probe_source` into src/__tests__, run native vitest on just that
    file, and return (CompletedProcess, combined_output)."""
    os.makedirs(TESTS_SUBDIR, exist_ok=True)
    with open(PROBE_PATH, "w", encoding="utf-8") as fh:
        fh.write(probe_source)
    try:
        result = subprocess.run(
            [
                "pnpm",
                "--filter",
                "@tanstack/query-core",
                "exec",
                "vitest",
                "run",
                f"src/__tests__/{PROBE_BASENAME}",
            ],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=VITEST_TIMEOUT,
            env=_pnpm_env(),
        )
    finally:
        try:
            os.remove(PROBE_PATH)
        except OSError:
            pass
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    return result, combined


def _assert_vitest_passed(result, combined):
    assert result.returncode == 0, (
        "native vitest run did not pass:\n"
        f"stdout={result.stdout[-4000:]}\nstderr={result.stderr[-4000:]}"
    )
    lowered = combined.lower()
    assert "no test files found" not in lowered, (
        "vitest collected no tests:\n" + combined[-3000:]
    )


# Reusable probe header: import planRetry from the package index.
_HEADER = (
    "import { describe, expect, it, vi } from 'vitest'\n"
    "import { planRetry } from '..'\n"
)


class TestTanstackQueryPatterns:
    """Verify the planRetry retry-and-backoff planner utility."""

    REPO_DIR = "/workspace/query"

    # ------------------------------------------------------------------
    # L1: deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_retryplan_source_file_exists(self):
        """packages/query-core/src/retryPlan.ts must exist and define planRetry."""
        path = os.path.join(SRC_DIR, "retryPlan.ts")
        assert os.path.isfile(path), "retryPlan.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "planRetry" in content, "planRetry not defined in retryPlan.ts"
        assert "RetryPlanInput" in content, "RetryPlanInput type not in retryPlan.ts"
        assert len(content.strip()) > 120, "retryPlan.ts looks empty/stub"

    def test_index_reexports_planretry(self):
        """index.ts must re-export planRetry and the RetryPlanInput type."""
        path = os.path.join(SRC_DIR, "index.ts")
        assert os.path.isfile(path), "index.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "planRetry" in content, "index.ts does not re-export planRetry"
        assert "RetryPlanInput" in content, "index.ts does not re-export RetryPlanInput"

    def test_agent_test_suite_exists(self):
        """The required vitest suite file must exist."""
        path = os.path.join(TESTS_SUBDIR, "retryPlan.test.tsx")
        assert os.path.isfile(path), "retryPlan.test.tsx not found"

    # ------------------------------------------------------------------
    # L2: dynamic execution via the repo's native vitest toolchain.
    # Each method injects its own focused probe importing planRetry from
    # the package index, so the agent's own test file is not trusted.
    # ------------------------------------------------------------------

    def test_documented_expected_functionality(self):
        """The six worked examples in the doc's Expected Functionality resolve to
        the exact { shouldRetry, delayMs } pairs specified."""
        probe = _HEADER + (
            "describe('planRetry documented', () => {\n"
            "  it('matches every worked example', () => {\n"
            "    expect(planRetry({ failureCount: 1, error: new Error('x') }))"
            ".toEqual({ shouldRetry: true, delayMs: 1000 })\n"
            "    expect(planRetry({ failureCount: 4, error: new Error('x') }))"
            ".toEqual({ shouldRetry: false, delayMs: 0 })\n"
            "    const e = new Error('e')\n"
            "    expect(planRetry({ failureCount: 1, error: e, retry: false }))"
            ".toEqual({ shouldRetry: false, delayMs: 0 })\n"
            "    expect(planRetry({ failureCount: 2, error: e, retry: true, retryDelay: 250 }))"
            ".toEqual({ shouldRetry: true, delayMs: 250 })\n"
            "    expect(planRetry({ failureCount: 5, error: e, retry: (c) => c < 6, retryDelay: (c) => c * 100 }))"
            ".toEqual({ shouldRetry: true, delayMs: 500 })\n"
            "    expect(planRetry({ failureCount: 20, error: e }))"
            ".toEqual({ shouldRetry: true, delayMs: 30000 })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_default_retry_count_boundary(self):
        """With default retry (omitted -> 3): failureCount 1,2,3 retry; 4 (and
        beyond) do not. A stub that always retries or uses '<' off-by-one fails."""
        probe = _HEADER + (
            "describe('planRetry default count', () => {\n"
            "  it('retries up to 3 inclusive then stops', () => {\n"
            "    const e = new Error('x')\n"
            "    for (const c of [1, 2, 3]) {\n"
            "      expect(planRetry({ failureCount: c, error: e }).shouldRetry).toBe(true)\n"
            "    }\n"
            "    for (const c of [4, 5, 10]) {\n"
            "      const r = planRetry({ failureCount: c, error: e })\n"
            "      expect(r.shouldRetry).toBe(false)\n"
            "      expect(r.delayMs).toBe(0)\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_numeric_retry_count_boundary(self):
        """A numeric retry n means retry while failureCount <= n. Probe several n
        values and assert the exact crossover, so hardcoding 3 fails."""
        probe = _HEADER + (
            "describe('planRetry numeric retry', () => {\n"
            "  it('honors arbitrary numeric retry limits', () => {\n"
            "    const e = new Error('x')\n"
            "    // retry: 0 -> never retry\n"
            "    expect(planRetry({ failureCount: 1, error: e, retry: 0 }).shouldRetry).toBe(false)\n"
            "    // retry: 1 -> only failureCount 1\n"
            "    expect(planRetry({ failureCount: 1, error: e, retry: 1 }).shouldRetry).toBe(true)\n"
            "    expect(planRetry({ failureCount: 2, error: e, retry: 1 }).shouldRetry).toBe(false)\n"
            "    // retry: 5 -> failureCount 5 still retries, 6 stops\n"
            "    expect(planRetry({ failureCount: 5, error: e, retry: 5 }).shouldRetry).toBe(true)\n"
            "    expect(planRetry({ failureCount: 6, error: e, retry: 5 }).shouldRetry).toBe(false)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_boolean_retry_modes(self):
        """retry: true always retries (even at large failureCount); retry: false
        never retries and forces delayMs 0."""
        probe = _HEADER + (
            "describe('planRetry boolean retry', () => {\n"
            "  it('true always retries, false never', () => {\n"
            "    const e = new Error('x')\n"
            "    for (const c of [1, 50, 999]) {\n"
            "      expect(planRetry({ failureCount: c, error: e, retry: true }).shouldRetry).toBe(true)\n"
            "      const f = planRetry({ failureCount: c, error: e, retry: false })\n"
            "      expect(f.shouldRetry).toBe(false)\n"
            "      expect(f.delayMs).toBe(0)\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_function_retry_receives_args_and_decides(self):
        """A function retry is called with (failureCount, error) exactly once and
        its boolean return decides shouldRetry."""
        probe = _HEADER + (
            "describe('planRetry function retry', () => {\n"
            "  it('passes (failureCount, error) and uses the boolean result', () => {\n"
            "    const err = new Error('boom')\n"
            "    const spyTrue = vi.fn((c: number, e: unknown) => true)\n"
            "    const r1 = planRetry({ failureCount: 7, error: err, retry: spyTrue })\n"
            "    expect(r1.shouldRetry).toBe(true)\n"
            "    expect(spyTrue).toHaveBeenCalledTimes(1)\n"
            "    expect(spyTrue).toHaveBeenCalledWith(7, err)\n"
            "    const spyFalse = vi.fn(() => false)\n"
            "    const r2 = planRetry({ failureCount: 2, error: err, retry: spyFalse })\n"
            "    expect(r2.shouldRetry).toBe(false)\n"
            "    expect(r2.delayMs).toBe(0)\n"
            "    expect(spyFalse).toHaveBeenCalledTimes(1)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_default_exponential_backoff_curve(self):
        """Default backoff is Math.min(1000 * 2 ** (failureCount - 1), 30000) and
        caps at 30000. Assert the exact curve and cap; a fixed/linear delay fails."""
        probe = _HEADER + (
            "describe('planRetry default backoff', () => {\n"
            "  it('exponential doubling capped at 30000', () => {\n"
            "    const e = new Error('x')\n"
            "    const expected: Array<[number, number]> = [\n"
            "      [1, 1000], [2, 2000], [3, 4000], [4, 8000], [5, 16000],\n"
            "      [6, 30000], [7, 30000], [20, 30000],\n"
            "    ]\n"
            "    for (const [c, d] of expected) {\n"
            "      // force retry so backoff is evaluated even past the default count\n"
            "      expect(planRetry({ failureCount: c, error: e, retry: true }).delayMs).toBe(d)\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_numeric_and_function_retry_delay(self):
        """A numeric retryDelay is used verbatim; a function retryDelay is called
        with (failureCount, error) once and its numeric return is used."""
        probe = _HEADER + (
            "describe('planRetry retryDelay', () => {\n"
            "  it('numeric verbatim and function-computed delays', () => {\n"
            "    const err = new Error('x')\n"
            "    expect(planRetry({ failureCount: 3, error: err, retry: true, retryDelay: 1234 }).delayMs).toBe(1234)\n"
            "    expect(planRetry({ failureCount: 1, error: err, retry: true, retryDelay: 0 }).delayMs).toBe(0)\n"
            "    const spy = vi.fn((c: number, e: unknown) => c * 100)\n"
            "    const r = planRetry({ failureCount: 4, error: err, retry: true, retryDelay: spy })\n"
            "    expect(r.delayMs).toBe(400)\n"
            "    expect(spy).toHaveBeenCalledTimes(1)\n"
            "    expect(spy).toHaveBeenCalledWith(4, err)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_retry_delay_not_evaluated_when_not_retrying(self):
        """When shouldRetry is false, delayMs MUST be 0 and the retryDelay callback
        MUST NOT be invoked — guarding lazy evaluation, not just the returned value."""
        probe = _HEADER + (
            "describe('planRetry lazy delay', () => {\n"
            "  it('skips retryDelay entirely when not retrying', () => {\n"
            "    const err = new Error('x')\n"
            "    const delaySpy = vi.fn(() => 999)\n"
            "    // not retrying via numeric exhaustion\n"
            "    const r1 = planRetry({ failureCount: 4, error: err, retryDelay: delaySpy })\n"
            "    expect(r1.shouldRetry).toBe(false)\n"
            "    expect(r1.delayMs).toBe(0)\n"
            "    expect(delaySpy).not.toHaveBeenCalled()\n"
            "    // not retrying via retry: false\n"
            "    const delaySpy2 = vi.fn(() => 999)\n"
            "    const r2 = planRetry({ failureCount: 1, error: err, retry: false, retryDelay: delaySpy2 })\n"
            "    expect(r2.shouldRetry).toBe(false)\n"
            "    expect(r2.delayMs).toBe(0)\n"
            "    expect(delaySpy2).not.toHaveBeenCalled()\n"
            "    // not retrying via retry function returning false\n"
            "    const delaySpy3 = vi.fn(() => 999)\n"
            "    const r3 = planRetry({ failureCount: 2, error: err, retry: () => false, retryDelay: delaySpy3 })\n"
            "    expect(r3.shouldRetry).toBe(false)\n"
            "    expect(delaySpy3).not.toHaveBeenCalled()\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_callbacks_invoked_at_most_once_each(self):
        """Per call, the retry callback and (when retrying) the retryDelay callback
        are each evaluated at most once, both receiving the same args."""
        probe = _HEADER + (
            "describe('planRetry callback arity', () => {\n"
            "  it('evaluates each callback at most once', () => {\n"
            "    const err = new Error('z')\n"
            "    const retrySpy = vi.fn((c: number, e: unknown) => c <= 9)\n"
            "    const delaySpy = vi.fn((c: number, e: unknown) => c + 1)\n"
            "    const r = planRetry({ failureCount: 8, error: err, retry: retrySpy, retryDelay: delaySpy })\n"
            "    expect(r).toEqual({ shouldRetry: true, delayMs: 9 })\n"
            "    expect(retrySpy).toHaveBeenCalledTimes(1)\n"
            "    expect(delaySpy).toHaveBeenCalledTimes(1)\n"
            "    expect(retrySpy).toHaveBeenCalledWith(8, err)\n"
            "    expect(delaySpy).toHaveBeenCalledWith(8, err)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_purity_no_input_mutation(self):
        """planRetry MUST NOT mutate its input object (snapshot via stable
        stringify of enumerable fields before/after across several calls)."""
        probe = _HEADER + (
            "describe('planRetry purity', () => {\n"
            "  it('does not mutate the input', () => {\n"
            "    const err = new Error('x')\n"
            "    const input = { failureCount: 2, error: err, retry: 3, retryDelay: 250 }\n"
            "    const snap = JSON.stringify({ fc: input.failureCount, retry: input.retry, rd: input.retryDelay })\n"
            "    planRetry(input)\n"
            "    planRetry(input)\n"
            "    expect(input.failureCount).toBe(2)\n"
            "    expect(input.retry).toBe(3)\n"
            "    expect(input.retryDelay).toBe(250)\n"
            "    expect(JSON.stringify({ fc: input.failureCount, retry: input.retry, rd: input.retryDelay })).toBe(snap)\n"
            "    expect(input.error).toBe(err)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_return_shape_is_complete_across_grid(self):
        """Across a representative input grid the result is always an object with
        exactly { shouldRetry: boolean, delayMs: number >= 0 }, and delayMs is 0
        precisely when shouldRetry is false."""
        probe = _HEADER + (
            "describe('planRetry shape', () => {\n"
            "  it('always returns a well-formed result with the false=>0 invariant', () => {\n"
            "    const e = new Error('x')\n"
            "    const inputs = [\n"
            "      { failureCount: 1, error: e },\n"
            "      { failureCount: 4, error: e },\n"
            "      { failureCount: 1, error: e, retry: false },\n"
            "      { failureCount: 3, error: e, retry: true },\n"
            "      { failureCount: 2, error: e, retry: 2, retryDelay: 50 },\n"
            "      { failureCount: 9, error: e, retry: (c: number) => c < 5 },\n"
            "      { failureCount: 6, error: e, retry: true, retryDelay: (c: number) => c },\n"
            "      { failureCount: 20, error: e, retry: true },\n"
            "    ]\n"
            "    for (const inp of inputs) {\n"
            "      const r = planRetry(inp as any)\n"
            "      expect(Object.keys(r).sort()).toEqual(['delayMs', 'shouldRetry'])\n"
            "      expect(typeof r.shouldRetry).toBe('boolean')\n"
            "      expect(typeof r.delayMs).toBe('number')\n"
            "      expect(Number.isFinite(r.delayMs)).toBe(true)\n"
            "      expect(r.delayMs).toBeGreaterThanOrEqual(0)\n"
            "      if (!r.shouldRetry) expect(r.delayMs).toBe(0)\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)
