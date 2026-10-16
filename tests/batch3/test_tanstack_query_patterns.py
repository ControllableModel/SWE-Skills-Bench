"""
Test for 'tanstack-query-patterns' skill — Freshness Classifier (ext3 variant).

Verifies the agent added a pure `classifyFreshness(input): { status, msUntilStale }`
utility to `@tanstack/query-core` (packages/query-core/src/freshness.ts), re-exported
it (and the `Freshness` type) from the package entry point, and that the freshness
semantics match the requirement doc exactly:

  - 'fresh' while now < updatedAt + staleTime; 'stale' once now >= that boundary
    (boundary is inclusive-stale).
  - msUntilStale is the non-negative ms remaining until stale; exactly 0 once stale.
  - missing/0 staleTime => stale at/after updatedAt (fresh only when now < updatedAt).
  - staleTime === Infinity => always fresh with msUntilStale === Infinity.
  - negative staleTime treated as 0.
  - clock-skew (now < updatedAt) still yields non-negative msUntilStale.
  - pure: no real-clock read, no input mutation, no QueryClient/cache/timers/network.

Strategy: rather than trusting the agent's own test file, this suite writes its own
vitest probe specs into packages/query-core/src/__tests__/ and runs them with the
repo's native vitest (the SAME command family the Acceptance Criteria specifies):

    pnpm --filter @tanstack/query-core exec vitest run src/__tests__/<probe>

Each probe imports `classifyFreshness` (and the `Freshness` type) from the package
index (`..`) and asserts concrete numeric/string values, so a stub / hardcoded /
sign-flipped / clock-reading implementation fails. A separate probe verifies the
function never reads the real clock by stubbing Date.now to throw.
"""

import json
import os
import subprocess

import pytest


REPO_DIR = "/workspace/query"
CORE_DIR = os.path.join(REPO_DIR, "packages", "query-core")
SRC_DIR = os.path.join(CORE_DIR, "src")
TESTS_SUBDIR = os.path.join(SRC_DIR, "__tests__")

# Probe specs we inject live under src/__tests__ so the package's vitest
# config (test.dir === './src') picks them up. Distinct name to avoid clobber.
PROBE_BASENAME = "zzFreshnessProbe.gen.test.tsx"
PROBE_PATH = os.path.join(TESTS_SUBDIR, PROBE_BASENAME)

INSTALL_TIMEOUT = 1800
VITEST_TIMEOUT = 600


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


# A shared header importing the function under test from the package index.
_HEADER = (
    "import { describe, expect, it } from 'vitest'\n"
    "import { classifyFreshness } from '..'\n"
)


class TestTanstackQueryPatterns:
    """Verify the classifyFreshness freshness-classifier utility."""

    REPO_DIR = "/workspace/query"

    # ------------------------------------------------------------------
    # L1: deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_freshness_source_file_exists(self):
        """packages/query-core/src/freshness.ts must exist and be non-trivial."""
        path = os.path.join(SRC_DIR, "freshness.ts")
        assert os.path.isfile(path), "freshness.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "classifyFreshness" in content, (
            "classifyFreshness not defined in freshness.ts"
        )
        assert len(content.strip()) > 80, "freshness.ts looks empty/stub"

    def test_index_reexports_classify_freshness(self):
        """index.ts must re-export classifyFreshness and the Freshness type."""
        path = os.path.join(SRC_DIR, "index.ts")
        assert os.path.isfile(path), "index.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "classifyFreshness" in content, (
            "index.ts does not re-export classifyFreshness"
        )
        assert "Freshness" in content, "index.ts does not re-export the Freshness type"

    def test_agent_test_suite_exists(self):
        """The required vitest suite file must exist."""
        path = os.path.join(TESTS_SUBDIR, "freshness.test.tsx")
        assert os.path.isfile(path), "freshness.test.tsx not found"

    # ------------------------------------------------------------------
    # L2: dynamic execution via the repo's native vitest toolchain.
    # Each method injects its own focused probe importing classifyFreshness
    # from the package index, so the agent's own test file is not trusted.
    # ------------------------------------------------------------------

    def test_documented_examples_exact_values(self):
        """All Expected-Functionality examples from the doc resolve to the exact
        {status, msUntilStale} the requirement specifies."""
        probe = (
            _HEADER
            + "describe('classifyFreshness examples', () => {\n"
            "  it('matches documented examples', () => {\n"
            "    expect(classifyFreshness({ updatedAt: 1000, staleTime: 5000, now: 3000 }))\n"
            "      .toEqual({ status: 'fresh', msUntilStale: 3000 })\n"
            "    expect(classifyFreshness({ updatedAt: 1000, staleTime: 5000, now: 6000 }))\n"
            "      .toEqual({ status: 'stale', msUntilStale: 0 })\n"
            "    expect(classifyFreshness({ updatedAt: 1000, now: 500 }))\n"
            "      .toEqual({ status: 'fresh', msUntilStale: 500 })\n"
            "    expect(classifyFreshness({ updatedAt: 1000, staleTime: Infinity, now: 9999999 }))\n"
            "      .toEqual({ status: 'fresh', msUntilStale: Infinity })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_fresh_window_and_countdown(self):
        """While now < updatedAt + staleTime the status is 'fresh' and
        msUntilStale === updatedAt + staleTime - now exactly (a stub returning a
        constant or ignoring `now` fails)."""
        # (updatedAt, staleTime, now, expectedMs)
        cases = [
            (0, 10000, 0, 10000),
            (0, 10000, 1, 9999),
            (0, 10000, 9999, 1),
            (1000, 5000, 1000, 5000),
            (1000, 5000, 4999, 1001),
            (2_000_000, 250000, 2_100_000, 150000),
        ]
        body = "\n".join(
            "    {{ const r = classifyFreshness({{ updatedAt: {u}, staleTime: {s}, now: {n} }});\n"
            "      expect(r.status).toBe('fresh'); expect(r.msUntilStale).toBe({e}); }}".format(
                u=u, s=s, n=n, e=e
            )
            for (u, s, n, e) in cases
        )
        probe = (
            _HEADER
            + "describe('classifyFreshness fresh window', () => {\n"
            "  it('counts down within the fresh window', () => {\n"
            f"{body}\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_boundary_is_inclusive_stale(self):
        """Exactly at now === updatedAt + staleTime the entry is 'stale' with
        msUntilStale === 0; one ms earlier it is still 'fresh' with msUntilStale 1."""
        probe = (
            _HEADER
            + "describe('classifyFreshness boundary', () => {\n"
            "  it('boundary is inclusive-stale', () => {\n"
            "    const at = classifyFreshness({ updatedAt: 1000, staleTime: 5000, now: 6000 })\n"
            "    expect(at).toEqual({ status: 'stale', msUntilStale: 0 })\n"
            "    const before = classifyFreshness({ updatedAt: 1000, staleTime: 5000, now: 5999 })\n"
            "    expect(before).toEqual({ status: 'fresh', msUntilStale: 1 })\n"
            "    const after = classifyFreshness({ updatedAt: 1000, staleTime: 5000, now: 6001 })\n"
            "    expect(after).toEqual({ status: 'stale', msUntilStale: 0 })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_ms_until_stale_never_negative(self):
        """Once stale, msUntilStale MUST be exactly 0 (never negative) regardless
        of how far past the boundary `now` is."""
        # Deep past the boundary in each case.
        cases = [
            (1000, 5000, 6000),
            (1000, 5000, 7000),
            (1000, 5000, 1_000_000),
            (0, 1, 1),
            (0, 1, 1_000_000),
        ]
        body = "\n".join(
            "    {{ const r = classifyFreshness({{ updatedAt: {u}, staleTime: {s}, now: {n} }});\n"
            "      expect(r.status).toBe('stale'); expect(r.msUntilStale).toBe(0);\n"
            "      expect(r.msUntilStale).toBeGreaterThanOrEqual(0); }}".format(
                u=u, s=s, n=n
            )
            for (u, s, n) in cases
        )
        probe = (
            _HEADER
            + "describe('classifyFreshness non-negative', () => {\n"
            "  it('msUntilStale is exactly 0 when stale', () => {\n"
            f"{body}\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_missing_or_zero_stale_time_default_behavior(self):
        """With staleTime omitted (or 0) an entry is 'fresh' only when
        now < updatedAt; at/after updatedAt it is immediately 'stale' with
        msUntilStale 0."""
        probe = (
            _HEADER
            + "describe('classifyFreshness default stale', () => {\n"
            "  it('omitted/zero staleTime => stale at/after updatedAt', () => {\n"
            "    // omitted, now before updatedAt -> fresh, counts down to updatedAt\n"
            "    expect(classifyFreshness({ updatedAt: 1000, now: 500 }))\n"
            "      .toEqual({ status: 'fresh', msUntilStale: 500 })\n"
            "    // omitted, exactly at updatedAt -> stale\n"
            "    expect(classifyFreshness({ updatedAt: 1000, now: 1000 }))\n"
            "      .toEqual({ status: 'stale', msUntilStale: 0 })\n"
            "    // omitted, after updatedAt -> stale\n"
            "    expect(classifyFreshness({ updatedAt: 1000, now: 5000 }))\n"
            "      .toEqual({ status: 'stale', msUntilStale: 0 })\n"
            "    // explicit zero behaves identically\n"
            "    expect(classifyFreshness({ updatedAt: 1000, staleTime: 0, now: 999 }))\n"
            "      .toEqual({ status: 'fresh', msUntilStale: 1 })\n"
            "    expect(classifyFreshness({ updatedAt: 1000, staleTime: 0, now: 1000 }))\n"
            "      .toEqual({ status: 'stale', msUntilStale: 0 })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_infinite_stale_time_always_fresh(self):
        """staleTime === Infinity => always 'fresh' with msUntilStale === Infinity,
        even for `now` far in the future or before updatedAt."""
        probe = (
            _HEADER
            + "describe('classifyFreshness infinite', () => {\n"
            "  it('Infinity staleTime is always fresh', () => {\n"
            "    for (const now of [0, 500, 1000, 9999999, Number.MAX_SAFE_INTEGER]) {\n"
            "      const r = classifyFreshness({ updatedAt: 1000, staleTime: Infinity, now })\n"
            "      expect(r.status).toBe('fresh')\n"
            "      expect(r.msUntilStale).toBe(Infinity)\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_negative_stale_time_treated_as_zero(self):
        """A negative staleTime MUST be treated as 0 (no fresh window): fresh only
        when now < updatedAt, stale at/after updatedAt with msUntilStale 0."""
        probe = (
            _HEADER
            + "describe('classifyFreshness negative stale', () => {\n"
            "  it('negative staleTime == 0', () => {\n"
            "    // Same as the omitted/zero case.\n"
            "    expect(classifyFreshness({ updatedAt: 1000, staleTime: -5000, now: 1000 }))\n"
            "      .toEqual({ status: 'stale', msUntilStale: 0 })\n"
            "    expect(classifyFreshness({ updatedAt: 1000, staleTime: -5000, now: 3000 }))\n"
            "      .toEqual({ status: 'stale', msUntilStale: 0 })\n"
            "    // before updatedAt is still fresh (window is 0, not negative)\n"
            "    expect(classifyFreshness({ updatedAt: 1000, staleTime: -5000, now: 700 }))\n"
            "      .toEqual({ status: 'fresh', msUntilStale: 300 })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_clock_skew_now_before_updated_at(self):
        """now earlier than updatedAt (clock skew) MUST yield a non-negative
        msUntilStale consistent with the fresh window: updatedAt + staleTime - now,
        and status 'fresh'."""
        # (updatedAt, staleTime, now, expectedMs) all with now < updatedAt.
        cases = [
            (1000, 5000, 500, 5500),
            (1000, 5000, 0, 6000),
            (10000, 1000, 5000, 6000),
            (1000, 0, 500, 500),  # zero window but now before updatedAt
        ]
        body = "\n".join(
            "    {{ const r = classifyFreshness({{ updatedAt: {u}, staleTime: {s}, now: {n} }});\n"
            "      expect(r.status).toBe('fresh'); expect(r.msUntilStale).toBe({e});\n"
            "      expect(r.msUntilStale).toBeGreaterThanOrEqual(0); }}".format(
                u=u, s=s, n=n, e=e
            )
            for (u, s, n, e) in cases
        )
        probe = (
            _HEADER
            + "describe('classifyFreshness clock skew', () => {\n"
            "  it('now before updatedAt stays fresh and non-negative', () => {\n"
            f"{body}\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_purity_no_input_mutation(self):
        """classifyFreshness MUST NOT mutate its input object (snapshot the JSON
        before/after for both finite and Infinity staleTime)."""
        probe = (
            _HEADER
            + "describe('classifyFreshness purity', () => {\n"
            "  it('does not mutate its input', () => {\n"
            "    const a = { updatedAt: 1000, staleTime: 5000, now: 3000 }\n"
            "    const sa = JSON.stringify(a)\n"
            "    classifyFreshness(a)\n"
            "    expect(JSON.stringify(a)).toBe(sa)\n"
            "    expect(Object.keys(a).sort()).toEqual(['now', 'staleTime', 'updatedAt'])\n"
            "    // omitted staleTime must NOT be injected onto the input\n"
            "    const b = { updatedAt: 1000, now: 500 }\n"
            "    classifyFreshness(b)\n"
            "    expect(Object.keys(b).sort()).toEqual(['now', 'updatedAt'])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_does_not_read_real_clock(self):
        """The function MUST be pure with respect to the real clock: it uses the
        provided `now`. Stub Date.now / performance.now to throw and confirm the
        function still returns the correct value derived purely from `now`."""
        probe = (
            _HEADER
            + "describe('classifyFreshness no real clock', () => {\n"
            "  it('never reads Date.now or performance.now', () => {\n"
            "    const realDateNow = Date.now\n"
            "    const realPerfNow = performance.now\n"
            "    Date.now = () => { throw new Error('classifyFreshness read Date.now') }\n"
            "    performance.now = () => { throw new Error('classifyFreshness read performance.now') }\n"
            "    try {\n"
            "      expect(classifyFreshness({ updatedAt: 1000, staleTime: 5000, now: 3000 }))\n"
            "        .toEqual({ status: 'fresh', msUntilStale: 3000 })\n"
            "      expect(classifyFreshness({ updatedAt: 1000, staleTime: 5000, now: 6000 }))\n"
            "        .toEqual({ status: 'stale', msUntilStale: 0 })\n"
            "    } finally {\n"
            "      Date.now = realDateNow\n"
            "      performance.now = realPerfNow\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_status_only_fresh_or_stale_over_grid(self):
        """Over a broad input grid `status` is only ever one of the two documented
        literals and msUntilStale is always a non-negative number (or Infinity),
        with status agreeing with the now-vs-boundary comparison."""
        grid = {
            "updatedAt": [0, 1000, 2_000_000, -500],
            "staleTime": [0, 1, 5000, -100, "Infinity"],
            "now": [-1000, 0, 999, 1000, 1001, 6000, 9_999_999],
        }
        probe = (
            _HEADER
            + "const updated = "
            + json.dumps(grid["updatedAt"])
            + "\n"
            "const stales = [0, 1, 5000, -100, Infinity]\n"
            "const nows = " + json.dumps(grid["now"]) + "\n"
            "describe('classifyFreshness grid', () => {\n"
            "  it('status is fresh|stale and msUntilStale non-negative', () => {\n"
            "    for (const updatedAt of updated) {\n"
            "      for (const staleTime of stales) {\n"
            "        for (const now of nows) {\n"
            "          const r = classifyFreshness({ updatedAt, staleTime, now })\n"
            "          expect(['fresh', 'stale']).toContain(r.status)\n"
            "          expect(typeof r.msUntilStale).toBe('number')\n"
            "          expect(r.msUntilStale).toBeGreaterThanOrEqual(0)\n"
            "          if (staleTime === Infinity) {\n"
            "            expect(r.status).toBe('fresh')\n"
            "            expect(r.msUntilStale).toBe(Infinity)\n"
            "          } else {\n"
            "            const window = staleTime > 0 ? staleTime : 0\n"
            "            const boundary = updatedAt + window\n"
            "            expect(r.status).toBe(now < boundary ? 'fresh' : 'stale')\n"
            "            if (r.status === 'fresh') expect(r.msUntilStale).toBe(boundary - now)\n"
            "            else expect(r.msUntilStale).toBe(0)\n"
            "          }\n"
            "        }\n"
            "      }\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)
