"""
Test for 'tanstack-query-patterns' skill (variant ext10) — Bounded Page Window
Manager for Infinite Queries.

Verifies the agent added a pure `pushBounded(input): Array<TItem>` utility to
`@tanstack/query-core` (packages/query-core/src/pageWindow.ts), re-exported it
(and the `FetchDirection` type) from the package entry point, and that the
bounded-window semantics match the requirement doc exactly:

  - direction 'forward'  -> append item to END; if length > maxPages drop the
    FIRST element so result length == maxPages.
  - direction 'backward' -> prepend item to START; if length > maxPages drop
    the LAST element so result length == maxPages.
  - maxPages of 0 / undefined / any value <= 0 means "no limit": add, no trim.
  - empty list returns a one-element list regardless of maxPages.
  - below maxPages: no trimming.
  - MUST return a NEW array and MUST NOT mutate `items`.

Strategy: rather than trusting the agent's own test file, this suite writes its
own vitest probe spec into packages/query-core/src/__tests__/ and runs it with
the repo's native vitest — the SAME command family the Acceptance Criteria
specifies:

    pnpm --filter @tanstack/query-core exec vitest run src/__tests__/<probe>

Each probe imports `pushBounded` / `FetchDirection` from the package index
(`..`) and asserts concrete array values, so a stub / hardcoded / mutating /
wrong-end implementation fails. A naive implementation that ignores `direction`,
ignores `maxPages`, trims from the wrong end, mutates `items`, or returns the
same array reference MUST fail these probes.
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
PROBE_BASENAME = "zzPageWindowProbe.gen.test.tsx"
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


# Header reused by every probe: import the utility from the package index.
_PROBE_HEADER = (
    "import { describe, expect, it } from 'vitest'\n"
    "import { pushBounded } from '..'\n"
)


def _probe(name, body):
    """Assemble a single-it vitest probe from a JS body."""
    return (
        f"{_PROBE_HEADER}"
        f"describe('pushBounded {name}', () => {{\n"
        f"  it('{name}', () => {{\n"
        f"{body}\n"
        "  })\n"
        "})\n"
    )


class TestTanstackQueryPatterns:
    """Verify the pushBounded bounded page-window utility."""

    REPO_DIR = "/workspace/query"

    # ------------------------------------------------------------------
    # L1: deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_pagewindow_source_file_exists(self):
        """packages/query-core/src/pageWindow.ts must exist and define pushBounded."""
        path = os.path.join(SRC_DIR, "pageWindow.ts")
        assert os.path.isfile(path), "pageWindow.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "pushBounded" in content, "pushBounded not defined in pageWindow.ts"
        assert len(content.strip()) > 80, "pageWindow.ts looks empty/stub"

    def test_index_reexports_pushbounded(self):
        """index.ts must re-export pushBounded and the FetchDirection type."""
        path = os.path.join(SRC_DIR, "index.ts")
        assert os.path.isfile(path), "index.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "pushBounded" in content, "index.ts does not re-export pushBounded"
        assert "FetchDirection" in content, (
            "index.ts does not re-export FetchDirection"
        )

    def test_agent_test_suite_exists(self):
        """The required vitest suite file must exist."""
        path = os.path.join(TESTS_SUBDIR, "pageWindow.test.tsx")
        assert os.path.isfile(path), "pageWindow.test.tsx not found"

    def test_pushbounded_importable_from_index(self):
        """pushBounded must be a callable export resolvable from the package
        index (catches a missing re-export or a non-function export)."""
        probe = _probe(
            "importable",
            "    expect(typeof pushBounded).toBe('function')\n"
            "    expect(pushBounded({ items: [], item: 1, direction: 'forward' })).toEqual([1])",
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    # ------------------------------------------------------------------
    # L2: dynamic execution via the repo's native vitest toolchain.
    # Each method injects its own focused probe importing pushBounded from
    # the package index, so the agent's own test file is not trusted.
    # ------------------------------------------------------------------

    def test_documented_expected_functionality(self):
        """All six documented Expected-Functionality scenarios produce exactly
        the specified array."""
        probe = _probe(
            "documented",
            "    expect(pushBounded({ items: [1, 2], item: 3, direction: 'forward' })).toEqual([1, 2, 3])\n"
            "    expect(pushBounded({ items: [1, 2, 3], item: 4, direction: 'forward', maxPages: 3 })).toEqual([2, 3, 4])\n"
            "    expect(pushBounded({ items: [1, 2, 3], item: 0, direction: 'backward', maxPages: 3 })).toEqual([0, 1, 2])\n"
            "    expect(pushBounded({ items: [], item: 9, direction: 'forward', maxPages: 3 })).toEqual([9])\n"
            "    expect(pushBounded({ items: [1, 2], item: 3, direction: 'forward', maxPages: 0 })).toEqual([1, 2, 3])\n"
            "    expect(pushBounded({ items: [1, 2], item: 3, direction: 'backward', maxPages: 5 })).toEqual([3, 1, 2])",
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_forward_appends_and_trims_front(self):
        """Forward push appends at the END; when exceeding maxPages it drops the
        FIRST element (an impl that trims the wrong end fails)."""
        probe = _probe(
            "forward-trim-front",
            "    // below limit: pure append, no trim\n"
            "    expect(pushBounded({ items: [1, 2], item: 3, direction: 'forward', maxPages: 5 })).toEqual([1, 2, 3])\n"
            "    // exactly at limit after append: drop exactly one from front\n"
            "    expect(pushBounded({ items: ['a', 'b', 'c'], item: 'd', direction: 'forward', maxPages: 3 })).toEqual(['b', 'c', 'd'])\n"
            "    // result length pinned to maxPages\n"
            "    const r = pushBounded({ items: [10, 20, 30, 40], item: 50, direction: 'forward', maxPages: 3 })\n"
            "    expect(r).toEqual([30, 40, 50])\n"
            "    expect(r.length).toBe(3)",
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_backward_prepends_and_trims_back(self):
        """Backward push prepends at the START; when exceeding maxPages it drops
        the LAST element (an impl that trims the wrong end fails)."""
        probe = _probe(
            "backward-trim-back",
            "    // below limit: pure prepend, no trim\n"
            "    expect(pushBounded({ items: [1, 2], item: 0, direction: 'backward', maxPages: 5 })).toEqual([0, 1, 2])\n"
            "    // exactly at limit after prepend: drop exactly one from back\n"
            "    expect(pushBounded({ items: ['b', 'c', 'd'], item: 'a', direction: 'backward', maxPages: 3 })).toEqual(['a', 'b', 'c'])\n"
            "    // result length pinned to maxPages\n"
            "    const r = pushBounded({ items: [20, 30, 40, 50], item: 10, direction: 'backward', maxPages: 3 })\n"
            "    expect(r).toEqual([10, 20, 30])\n"
            "    expect(r.length).toBe(3)",
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_no_limit_semantics(self):
        """maxPages of 0, undefined, negative, or omitted means no trimming in
        either direction (a naive impl that always trims, or that treats 0 as a
        hard cap, fails)."""
        probe = _probe(
            "no-limit",
            "    // omitted maxPages\n"
            "    expect(pushBounded({ items: [1, 2, 3, 4], item: 5, direction: 'forward' })).toEqual([1, 2, 3, 4, 5])\n"
            "    // maxPages === 0\n"
            "    expect(pushBounded({ items: [1, 2, 3, 4], item: 5, direction: 'forward', maxPages: 0 })).toEqual([1, 2, 3, 4, 5])\n"
            "    // negative maxPages\n"
            "    expect(pushBounded({ items: [1, 2, 3, 4], item: 5, direction: 'forward', maxPages: -2 })).toEqual([1, 2, 3, 4, 5])\n"
            "    // undefined explicitly\n"
            "    expect(pushBounded({ items: [1, 2, 3, 4], item: 5, direction: 'forward', maxPages: undefined })).toEqual([1, 2, 3, 4, 5])\n"
            "    // backward no-limit\n"
            "    expect(pushBounded({ items: [2, 3, 4], item: 1, direction: 'backward', maxPages: 0 })).toEqual([1, 2, 3, 4])",
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_empty_list_returns_single_element(self):
        """Adding to an empty list returns a one-element list regardless of
        direction or maxPages."""
        probe = _probe(
            "empty-list",
            "    expect(pushBounded({ items: [], item: 9, direction: 'forward', maxPages: 3 })).toEqual([9])\n"
            "    expect(pushBounded({ items: [], item: 9, direction: 'backward', maxPages: 3 })).toEqual([9])\n"
            "    expect(pushBounded({ items: [], item: 7, direction: 'forward' })).toEqual([7])\n"
            "    expect(pushBounded({ items: [], item: 7, direction: 'backward', maxPages: 0 })).toEqual([7])\n"
            "    expect(pushBounded({ items: [], item: 7, direction: 'forward', maxPages: 1 })).toEqual([7])",
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_below_limit_no_trim(self):
        """When the list is below maxPages, no trimming occurs in either
        direction; only the newly added element changes the length."""
        probe = _probe(
            "below-limit",
            "    for (let max = 4; max <= 8; max++) {\n"
            "      const fwd = pushBounded({ items: [1, 2], item: 3, direction: 'forward', maxPages: max })\n"
            "      expect(fwd).toEqual([1, 2, 3])\n"
            "      const bwd = pushBounded({ items: [1, 2], item: 0, direction: 'backward', maxPages: max })\n"
            "      expect(bwd).toEqual([0, 1, 2])\n"
            "    }",
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_maxpages_one_keeps_only_latest(self):
        """maxPages of 1 keeps exactly the newest item in each direction (tight
        boundary: every prior page is dropped)."""
        probe = _probe(
            "maxpages-one",
            "    expect(pushBounded({ items: [1, 2, 3], item: 4, direction: 'forward', maxPages: 1 })).toEqual([4])\n"
            "    expect(pushBounded({ items: [1, 2, 3], item: 0, direction: 'backward', maxPages: 1 })).toEqual([0])\n"
            "    // already a single element at the cap\n"
            "    expect(pushBounded({ items: [5], item: 6, direction: 'forward', maxPages: 1 })).toEqual([6])\n"
            "    expect(pushBounded({ items: [5], item: 6, direction: 'backward', maxPages: 1 })).toEqual([6])",
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_returns_new_array_no_mutation(self):
        """The function MUST return a NEW array and MUST NOT mutate `items`
        (catches push/unshift/splice on the input or returning the same ref)."""
        probe = _probe(
            "purity",
            "    const items = [1, 2, 3]\n"
            "    const snapshot = items.slice()\n"
            "    const out = pushBounded({ items, item: 4, direction: 'forward', maxPages: 3 })\n"
            "    // input untouched\n"
            "    expect(items).toEqual(snapshot)\n"
            "    expect(items.length).toBe(3)\n"
            "    // a fresh array, not the same reference\n"
            "    expect(out).not.toBe(items)\n"
            "    expect(out).toEqual([2, 3, 4])\n"
            "    // backward direction must also not mutate\n"
            "    const items2 = [2, 3, 4]\n"
            "    const snap2 = items2.slice()\n"
            "    const out2 = pushBounded({ items: items2, item: 1, direction: 'backward', maxPages: 3 })\n"
            "    expect(items2).toEqual(snap2)\n"
            "    expect(out2).not.toBe(items2)\n"
            "    expect(out2).toEqual([1, 2, 3])\n"
            "    // no-limit path must also return a new array\n"
            "    const items3 = [1, 2]\n"
            "    const out3 = pushBounded({ items: items3, item: 3, direction: 'forward', maxPages: 0 })\n"
            "    expect(out3).not.toBe(items3)\n"
            "    expect(items3).toEqual([1, 2])",
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_direction_is_honored(self):
        """direction MUST drive WHERE the item lands: forward vs backward on the
        SAME inputs give different results (an impl that ignores direction
        fails)."""
        probe = _probe(
            "direction-honored",
            "    const fwd = pushBounded({ items: [1, 2], item: 3, direction: 'forward' })\n"
            "    const bwd = pushBounded({ items: [1, 2], item: 3, direction: 'backward' })\n"
            "    expect(fwd).toEqual([1, 2, 3])\n"
            "    expect(bwd).toEqual([3, 1, 2])\n"
            "    expect(fwd).not.toEqual(bwd)\n"
            "    // and at the cap the dropped end differs\n"
            "    const fwdCap = pushBounded({ items: [1, 2, 3], item: 4, direction: 'forward', maxPages: 3 })\n"
            "    const bwdCap = pushBounded({ items: [1, 2, 3], item: 4, direction: 'backward', maxPages: 3 })\n"
            "    expect(fwdCap).toEqual([2, 3, 4])\n"
            "    expect(bwdCap).toEqual([4, 1, 2])",
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_invariants_over_grid(self):
        """Over a grid of inputs the result satisfies the structural invariants:
        item is present; length is min(len+1, maxPages) when bounded else len+1;
        forward preserves a suffix of the original and ends with item; backward
        preserves a prefix of the original and starts with item."""
        probe = (
            f"{_PROBE_HEADER}"
            "describe('pushBounded invariants', () => {\n"
            "  it('grid invariants', () => {\n"
            "    const bases = [[], [1], [1, 2], [1, 2, 3], [1, 2, 3, 4, 5]]\n"
            "    const caps = [undefined, 0, -1, 1, 2, 3, 10]\n"
            "    for (const base of bases) {\n"
            "      for (const max of caps) {\n"
            "        const fwd = pushBounded({ items: base, item: 99, direction: 'forward', maxPages: max as number | undefined })\n"
            "        const bwd = pushBounded({ items: base, item: 99, direction: 'backward', maxPages: max as number | undefined })\n"
            "        const bounded = typeof max === 'number' && max > 0\n"
            "        const expectedLen = bounded ? Math.min(base.length + 1, max) : base.length + 1\n"
            "        expect(fwd.length).toBe(expectedLen)\n"
            "        expect(bwd.length).toBe(expectedLen)\n"
            "        // item is always present\n"
            "        expect(fwd).toContain(99)\n"
            "        expect(bwd).toContain(99)\n"
            "        // forward: ends with item, body is a suffix of base\n"
            "        expect(fwd[fwd.length - 1]).toBe(99)\n"
            "        const fwdBody = fwd.slice(0, fwd.length - 1)\n"
            "        expect(fwdBody).toEqual(base.slice(base.length - fwdBody.length))\n"
            "        // backward: starts with item, body is a prefix of base\n"
            "        expect(bwd[0]).toBe(99)\n"
            "        const bwdBody = bwd.slice(1)\n"
            "        expect(bwdBody).toEqual(base.slice(0, bwdBody.length))\n"
            "      }\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)
