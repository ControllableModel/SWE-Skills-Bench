"""
Test for 'tanstack-query-patterns' skill (variant ext4) — Cache Eviction
Scheduler Helper.

Verifies the agent added a pure `planEviction(input): EvictionSchedule`
utility to `@tanstack/query-core`
(packages/query-core/src/evictionSchedule.ts), re-exported it (and the
`EvictionSchedule` type) from the package entry point, and that the
scheduling semantics match the requirement doc EXACTLY:

  - effectiveGcTime == max of all defined, non-negative requested windows,
  - an `undefined` requested window contributes the environment default
    (5 * 60 * 1000 ms in the browser, Infinity when isServer),
  - empty requestedGcTimes -> environment default,
  - negative windows clamped to 0 before being considered,
  - a single explicit 0 does NOT lower the maximum,
  - evictAt == lastActiveAt + effectiveGcTime (Infinity -> Infinity),
  - the function is pure (no clock/env read, no input mutation).

Strategy: rather than trusting the agent's own test file, this suite writes
its OWN vitest probe specs into packages/query-core/src/__tests__/ and runs
them with the repo's native vitest (the SAME command family the Acceptance
Criteria specifies:
  pnpm --filter @tanstack/query-core exec vitest run src/__tests__/<spec>).
Each probe imports `planEviction` / `EvictionSchedule` from the package
index (`..`) and asserts concrete numeric values, so a stub / hardcoded /
input-ignoring implementation fails. Infinity is JSON-serialized as a raw
`Infinity` literal inside the generated TS (not via JSON.parse) so the probes
exercise real IEEE Infinity arithmetic.
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
PROBE_BASENAME = "zzEvictionScheduleProbe.gen.test.tsx"
PROBE_PATH = os.path.join(TESTS_SUBDIR, PROBE_BASENAME)

INSTALL_TIMEOUT = 1800
VITEST_TIMEOUT = 600

DEFAULT_GC = 5 * 60 * 1000  # 300000, the documented browser default


def _pnpm_env():
    env = dict(os.environ)
    # Keep installs/output deterministic and offline-friendly where possible.
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
            # Fall back to a non-frozen install (lockfile drift tolerant).
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
    # Clean up the injected probe so we don't pollute the repo.
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
    # Vitest reports passing files; guard against "No test files found".
    lowered = combined.lower()
    assert "no test files found" not in lowered, (
        "vitest collected no tests:\n" + combined[-3000:]
    )


# A tiny TS prelude reused by probes: imports planEviction from the package
# index. Using `..` matches how the package's own __tests__ import internals.
_IMPORT = (
    "import { describe, expect, it } from 'vitest'\n"
    "import { planEviction } from '..'\n"
)


class TestTanstackQueryPatterns:
    """Verify the planEviction cache-eviction scheduler utility."""

    REPO_DIR = "/workspace/query"

    # ------------------------------------------------------------------
    # L1: deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_eviction_source_file_exists(self):
        """packages/query-core/src/evictionSchedule.ts must exist, export
        planEviction, and not be a trivial stub."""
        path = os.path.join(SRC_DIR, "evictionSchedule.ts")
        assert os.path.isfile(path), "evictionSchedule.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "planEviction" in content, (
            "planEviction not defined in evictionSchedule.ts"
        )
        assert len(content.strip()) > 80, "evictionSchedule.ts looks empty/stub"

    def test_index_reexports_planeviction(self):
        """index.ts must re-export planEviction and the EvictionSchedule type."""
        path = os.path.join(SRC_DIR, "index.ts")
        assert os.path.isfile(path), "index.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "planEviction" in content, (
            "index.ts does not re-export planEviction"
        )
        assert "EvictionSchedule" in content, (
            "index.ts does not re-export the EvictionSchedule type"
        )

    def test_agent_test_suite_exists(self):
        """The required vitest suite file must exist."""
        path = os.path.join(TESTS_SUBDIR, "evictionSchedule.test.tsx")
        assert os.path.isfile(path), "evictionSchedule.test.tsx not found"

    # ------------------------------------------------------------------
    # L2: dynamic execution via the repo's native vitest toolchain.
    # Each method injects its own focused probe importing planEviction
    # from the package index, so the agent's own test file is not trusted.
    # ------------------------------------------------------------------

    def test_documented_examples(self):
        """All five documented Expected-Functionality examples produce the exact
        effectiveGcTime / evictAt numbers from the requirement doc."""
        probe = (
            _IMPORT
            + "describe('planEviction documented', () => {\n"
            "  it('matches the requirement examples', () => {\n"
            "    expect(planEviction({ requestedGcTimes: [1000, 5000, 2000], lastActiveAt: 100 }))"
            ".toEqual({ effectiveGcTime: 5000, evictAt: 5100 })\n"
            "    expect(planEviction({ requestedGcTimes: [1000, undefined], lastActiveAt: 0 }).effectiveGcTime)"
            f".toBe({DEFAULT_GC})\n"
            "    expect(planEviction({ requestedGcTimes: [], lastActiveAt: 0 }).effectiveGcTime)"
            f".toBe({DEFAULT_GC})\n"
            "    expect(planEviction({ requestedGcTimes: [undefined], lastActiveAt: 0, isServer: true }))"
            ".toEqual({ effectiveGcTime: Infinity, evictAt: Infinity })\n"
            "    expect(planEviction({ requestedGcTimes: [-5, 1000], lastActiveAt: 10 }))"
            ".toEqual({ effectiveGcTime: 1000, evictAt: 1010 })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_max_window_wins(self):
        """effectiveGcTime is the maximum of the defined windows regardless of
        ordering, and evictAt = lastActiveAt + that max."""
        probe = (
            _IMPORT
            + "describe('planEviction max', () => {\n"
            "  it('takes the maximum defined window', () => {\n"
            "    expect(planEviction({ requestedGcTimes: [10, 9999, 42], lastActiveAt: 1 }))"
            ".toEqual({ effectiveGcTime: 9999, evictAt: 10000 })\n"
            "    expect(planEviction({ requestedGcTimes: [9999, 10, 42], lastActiveAt: 1 }))"
            ".toEqual({ effectiveGcTime: 9999, evictAt: 10000 })\n"
            "    expect(planEviction({ requestedGcTimes: [7000], lastActiveAt: 3000 }))"
            ".toEqual({ effectiveGcTime: 7000, evictAt: 10000 })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_undefined_contributes_browser_default(self):
        """An `undefined` observer contributes the 5-minute browser default, and
        that default participates in the max alongside defined windows."""
        probe = (
            _IMPORT
            + "describe('planEviction default contribution', () => {\n"
            "  it('undefined contributes the browser default', () => {\n"
            "    // default (300000) beats the small defined window\n"
            "    expect(planEviction({ requestedGcTimes: [1000, undefined], lastActiveAt: 0 }))"
            f".toEqual({{ effectiveGcTime: {DEFAULT_GC}, evictAt: {DEFAULT_GC} }})\n"
            "    // a larger defined window beats the default\n"
            f"    expect(planEviction({{ requestedGcTimes: [{DEFAULT_GC + 1000}, undefined], lastActiveAt: 0 }}).effectiveGcTime)"
            f".toBe({DEFAULT_GC + 1000})\n"
            "    // multiple undefineds still cap at one default in the browser\n"
            "    expect(planEviction({ requestedGcTimes: [undefined, undefined], lastActiveAt: 7 }))"
            f".toEqual({{ effectiveGcTime: {DEFAULT_GC}, evictAt: {DEFAULT_GC + 7} }})\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_empty_uses_environment_default(self):
        """Empty requestedGcTimes resolves to the environment default: the
        browser default by default, Infinity on the server."""
        probe = (
            _IMPORT
            + "describe('planEviction empty', () => {\n"
            "  it('empty -> environment default', () => {\n"
            "    expect(planEviction({ requestedGcTimes: [], lastActiveAt: 50 }))"
            f".toEqual({{ effectiveGcTime: {DEFAULT_GC}, evictAt: {DEFAULT_GC + 50} }})\n"
            "    expect(planEviction({ requestedGcTimes: [], lastActiveAt: 50, isServer: false }).effectiveGcTime)"
            f".toBe({DEFAULT_GC})\n"
            "    expect(planEviction({ requestedGcTimes: [], lastActiveAt: 50, isServer: true }))"
            ".toEqual({ effectiveGcTime: Infinity, evictAt: Infinity })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_server_default_is_infinity(self):
        """On the server an `undefined` window contributes Infinity, which
        dominates the max and forces an Infinity evictAt; defined finite windows
        alongside it are still dominated by Infinity."""
        probe = (
            _IMPORT
            + "describe('planEviction server', () => {\n"
            "  it('server undefined contributes Infinity', () => {\n"
            "    expect(planEviction({ requestedGcTimes: [undefined], lastActiveAt: 0, isServer: true }))"
            ".toEqual({ effectiveGcTime: Infinity, evictAt: Infinity })\n"
            "    // a finite defined window does not lower Infinity from an undefined observer\n"
            "    expect(planEviction({ requestedGcTimes: [1000, undefined], lastActiveAt: 0, isServer: true }))"
            ".toEqual({ effectiveGcTime: Infinity, evictAt: Infinity })\n"
            "    // but on the server with only finite defined windows, the max is finite\n"
            "    expect(planEviction({ requestedGcTimes: [1000, 2000], lastActiveAt: 5, isServer: true }))"
            ".toEqual({ effectiveGcTime: 2000, evictAt: 2005 })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_negative_clamped_to_zero(self):
        """A negative requested window is clamped to 0 before being considered;
        it never lowers the maximum and never produces a negative evictAt."""
        probe = (
            _IMPORT
            + "describe('planEviction clamp', () => {\n"
            "  it('clamps negatives to 0', () => {\n"
            "    expect(planEviction({ requestedGcTimes: [-5, 1000], lastActiveAt: 10 }))"
            ".toEqual({ effectiveGcTime: 1000, evictAt: 1010 })\n"
            "    // a lone negative clamps to 0, so the max of [0] is 0\n"
            "    expect(planEviction({ requestedGcTimes: [-9999], lastActiveAt: 100 }))"
            ".toEqual({ effectiveGcTime: 0, evictAt: 100 })\n"
            "    // multiple negatives all clamp to 0\n"
            "    expect(planEviction({ requestedGcTimes: [-1, -2, -3], lastActiveAt: 0 }))"
            ".toEqual({ effectiveGcTime: 0, evictAt: 0 })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_explicit_zero_does_not_lower_max(self):
        """A single explicit 0 among larger defined windows does NOT lower the
        maximum (catches a naive Math.min / last-wins implementation)."""
        probe = (
            _IMPORT
            + "describe('planEviction zero', () => {\n"
            "  it('explicit 0 does not lower the max', () => {\n"
            "    expect(planEviction({ requestedGcTimes: [0, 1000], lastActiveAt: 0 }))"
            ".toEqual({ effectiveGcTime: 1000, evictAt: 1000 })\n"
            "    expect(planEviction({ requestedGcTimes: [1000, 0], lastActiveAt: 0 }))"
            ".toEqual({ effectiveGcTime: 1000, evictAt: 1000 })\n"
            "    expect(planEviction({ requestedGcTimes: [0, 0, 0], lastActiveAt: 5 }))"
            ".toEqual({ effectiveGcTime: 0, evictAt: 5 })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_mixed_defined_and_undefined_browser(self):
        """Mixing defined values and `undefined` in the browser: the effective
        window is the max across both the defined values and the contributed
        default, so a single undefined forces at least the 5-minute floor only
        when no larger defined value exists."""
        probe = (
            _IMPORT
            + "describe('planEviction mixed', () => {\n"
            "  it('max across defined values and the default', () => {\n"
            "    // undefined floor wins over small defined values\n"
            "    expect(planEviction({ requestedGcTimes: [10, 20, undefined], lastActiveAt: 0 }).effectiveGcTime)"
            f".toBe({DEFAULT_GC})\n"
            "    // a defined value larger than the floor wins\n"
            f"    expect(planEviction({{ requestedGcTimes: [10, {DEFAULT_GC * 2}, undefined], lastActiveAt: 0 }}).effectiveGcTime)"
            f".toBe({DEFAULT_GC * 2})\n"
            "    // negative + undefined in the browser -> default floor\n"
            "    expect(planEviction({ requestedGcTimes: [-100, undefined], lastActiveAt: 1 }))"
            f".toEqual({{ effectiveGcTime: {DEFAULT_GC}, evictAt: {DEFAULT_GC + 1} }})\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_evict_at_relationship(self):
        """evictAt is always exactly lastActiveAt + effectiveGcTime across a grid
        of inputs (finite cases), establishing the structural invariant rather
        than checking only point values."""
        probe = (
            _IMPORT
            + "const requested = [\n"
            "  [1000], [0, 2000], [-5, 1000], [42, 43, 44], [undefined, 1000],\n"
            "  [500, 500, 500], [1],\n"
            "]\n"
            "const stamps = [0, 1, 100, 123456, 999999]\n"
            "describe('planEviction invariant', () => {\n"
            "  it('evictAt === lastActiveAt + effectiveGcTime (finite)', () => {\n"
            "    for (const r of requested) {\n"
            "      for (const t of stamps) {\n"
            "        const out = planEviction({ requestedGcTimes: r, lastActiveAt: t })\n"
            "        expect(Number.isFinite(out.effectiveGcTime)).toBe(true)\n"
            "        expect(out.effectiveGcTime).toBeGreaterThanOrEqual(0)\n"
            "        expect(out.evictAt).toBe(t + out.effectiveGcTime)\n"
            "      }\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_infinity_evict_at_is_infinity(self):
        """Whenever effectiveGcTime is Infinity (server default or empty server),
        evictAt MUST be Infinity regardless of lastActiveAt (no NaN, no finite
        arithmetic leak)."""
        probe = (
            _IMPORT
            + "const stamps = [0, 1, 100, 123456]\n"
            "describe('planEviction infinity', () => {\n"
            "  it('Infinity window -> Infinity evictAt', () => {\n"
            "    for (const t of stamps) {\n"
            "      const a = planEviction({ requestedGcTimes: [undefined], lastActiveAt: t, isServer: true })\n"
            "      expect(a.effectiveGcTime).toBe(Infinity)\n"
            "      expect(a.evictAt).toBe(Infinity)\n"
            "      const b = planEviction({ requestedGcTimes: [], lastActiveAt: t, isServer: true })\n"
            "      expect(b.effectiveGcTime).toBe(Infinity)\n"
            "      expect(b.evictAt).toBe(Infinity)\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_purity_no_mutation(self):
        """planEviction MUST NOT mutate its input array/object (snapshot via
        JSON.stringify before/after, plus a frozen-input call that must not
        throw)."""
        probe = (
            _IMPORT
            + "describe('planEviction purity', () => {\n"
            "  it('does not mutate input', () => {\n"
            "    const arr = [1000, undefined, -5, 2000]\n"
            "    const input = { requestedGcTimes: arr, lastActiveAt: 10, isServer: false }\n"
            "    const snapArr = JSON.stringify(arr)\n"
            "    const snapInput = JSON.stringify(input)\n"
            "    planEviction(input)\n"
            "    expect(JSON.stringify(arr)).toBe(snapArr)\n"
            "    expect(JSON.stringify(input)).toBe(snapInput)\n"
            "    expect(arr.length).toBe(4)\n"
            "    // a deeply frozen input must not be mutated -> no throw\n"
            "    const frozenArr = Object.freeze([1000, 2000])\n"
            "    const frozenInput = Object.freeze({ requestedGcTimes: frozenArr, lastActiveAt: 5 })\n"
            "    expect(() => planEviction(frozenInput)).not.toThrow()\n"
            "    expect(planEviction(frozenInput)).toEqual({ effectiveGcTime: 2000, evictAt: 2005 })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_determinism_no_clock_read(self):
        """The function MUST be deterministic and not read the real clock: two
        calls with identical inputs return identical results, and the result does
        not depend on Date.now (lastActiveAt is the only time source)."""
        probe = (
            _IMPORT
            + "describe('planEviction determinism', () => {\n"
            "  it('deterministic and clock-independent', () => {\n"
            "    const input = { requestedGcTimes: [1000, 5000, 2000], lastActiveAt: 100 }\n"
            "    const a = planEviction(input)\n"
            "    const b = planEviction(input)\n"
            "    expect(a).toEqual(b)\n"
            "    expect(a).toEqual({ effectiveGcTime: 5000, evictAt: 5100 })\n"
            "    // mutating the real clock must not change the result\n"
            "    const realNow = Date.now\n"
            "    try {\n"
            "      Date.now = () => 999999999\n"
            "      const c = planEviction(input)\n"
            "      expect(c).toEqual({ effectiveGcTime: 5000, evictAt: 5100 })\n"
            "    } finally {\n"
            "      Date.now = realNow\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)
