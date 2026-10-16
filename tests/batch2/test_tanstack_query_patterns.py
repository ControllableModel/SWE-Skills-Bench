"""
Test for 'tanstack-query-patterns' skill — Prefix-Based Cache Key Selector.

Verifies the agent added a pure `selectKeys(filter, candidates, options?)`
utility to `@tanstack/query-core` (packages/query-core/src/selectKeys.ts) plus
its `SelectKeysOptions` type, re-exported both from the package entry point
(packages/query-core/src/index.ts), and that the selection semantics match the
requirement doc exactly:

  * Broad (default) mode: a candidate is selected when `filter` matches it as a
    leading-scope filter (prefix / structural partial match) — a shorter filter
    selects every candidate it is a prefix of.
  * Object elements match structurally (every property in the filter element
    must be present and recursively match; extra candidate props are allowed;
    property ordering is irrelevant).
  * Exact mode (`options.exact === true`): only candidates equivalent to the
    filter under the package's stable, order-independent key hash.
  * Result preserves input order of `candidates` and includes matching dups.
  * Empty filter `[]` selects everything in broad mode, only `[]` in exact mode.
  * Purity: no mutation of filter or candidates, no QueryClient/cache/timers.

Strategy: rather than trusting the agent's own test file, this suite writes its
OWN vitest probe specs into packages/query-core/src/__tests__/ and runs them
with the repo's native vitest (the SAME command family the Acceptance Criteria
specifies). Each probe imports `selectKeys` / `SelectKeysOptions` from the
package index (`..`) and asserts concrete returned arrays (deep equal), so a
stub / hardcoded / order-dropping / dedup-ing / always-return-all
implementation fails. One probe cross-checks consistency with the package's own
`partialMatchKey` / `hashKey` primitives over a key grid.
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
PROBE_BASENAME = "zzSelectKeysProbe.gen.test.tsx"
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


# A small JS preamble used by several probes that deep-compares the returned
# array of keys to an expected array of keys via vitest's toEqual.
_HEADER = (
    "import { describe, expect, it } from 'vitest'\n"
    "import { selectKeys } from '..'\n"
)


class TestTanstackQueryPatterns:
    """Verify the selectKeys prefix-based cache key selector."""

    REPO_DIR = "/workspace/query"

    # ------------------------------------------------------------------
    # L1: deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_selectkeys_source_file_exists(self):
        """packages/query-core/src/selectKeys.ts must exist and define selectKeys."""
        path = os.path.join(SRC_DIR, "selectKeys.ts")
        assert os.path.isfile(path), "selectKeys.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "selectKeys" in content, "selectKeys not defined in selectKeys.ts"
        assert "SelectKeysOptions" in content, "SelectKeysOptions not in selectKeys.ts"
        assert len(content.strip()) > 80, "selectKeys.ts looks empty/stub"

    def test_index_reexports_selectkeys(self):
        """index.ts must re-export selectKeys and the SelectKeysOptions type."""
        path = os.path.join(SRC_DIR, "index.ts")
        assert os.path.isfile(path), "index.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "selectKeys" in content, "index.ts does not re-export selectKeys"
        assert "SelectKeysOptions" in content, (
            "index.ts does not re-export SelectKeysOptions"
        )

    def test_agent_test_suite_exists(self):
        """The required vitest suite file must exist."""
        path = os.path.join(TESTS_SUBDIR, "selectKeys.test.tsx")
        assert os.path.isfile(path), "selectKeys.test.tsx not found"

    # ------------------------------------------------------------------
    # L2: dynamic execution via the repo's native vitest toolchain.
    # Each method injects its own focused probe importing selectKeys from
    # the package index, so the agent's own test file is not trusted.
    # ------------------------------------------------------------------

    def test_documented_broad_scenarios(self):
        """The documented Expected-Functionality broad-mode scenarios return the
        exact subset arrays, in candidate input order."""
        probe = (
            _HEADER
            + "describe('selectKeys broad scenarios', () => {\n"
            "  it('matches documented examples', () => {\n"
            "    expect(selectKeys(['todos'], [['todos'], ['todos', 5], ['users', 5]]))\n"
            "      .toEqual([['todos'], ['todos', 5]])\n"
            "    expect(selectKeys(['todos', 5], [['todos'], ['todos', 5], ['todos', 5, 'comments']]))\n"
            "      .toEqual([['todos', 5], ['todos', 5, 'comments']])\n"
            "    // a deeper filter selects only deeper-or-equal candidates\n"
            "    expect(selectKeys(['todos', 5, 'comments'], [['todos'], ['todos', 5], ['todos', 5, 'comments']]))\n"
            "      .toEqual([['todos', 5, 'comments']])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_prefix_selects_all_extensions(self):
        """A shorter filter selects every candidate it is a prefix of, and only
        those; an unrelated leading element selects nothing."""
        probe = (
            _HEADER
            + "describe('selectKeys prefix', () => {\n"
            "  it('selects every extension of the prefix', () => {\n"
            "    const cands = [['todos'], ['todos', 1], ['todos', 1, 'x'], ['todos', 2], ['users'], ['users', 1]]\n"
            "    expect(selectKeys(['todos'], cands)).toEqual([['todos'], ['todos', 1], ['todos', 1, 'x'], ['todos', 2]])\n"
            "    expect(selectKeys(['users'], cands)).toEqual([['users'], ['users', 1]])\n"
            "    expect(selectKeys(['nope'], cands)).toEqual([])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_structural_object_partial_match(self):
        """Object elements match structurally: every property in the filter
        element must be present & match; extra candidate props are fine; a
        differing value excludes the candidate."""
        probe = (
            _HEADER
            + "describe('selectKeys structural objects', () => {\n"
            "  it('partial-matches object elements', () => {\n"
            "    const cands = [\n"
            "      ['todos', { status: 'done' }],\n"
            "      ['todos', { status: 'done', page: 2 }],\n"
            "      ['todos', { status: 'open' }],\n"
            "      ['todos', { status: 'open', page: 2 }],\n"
            "    ]\n"
            "    expect(selectKeys(['todos', { status: 'done' }], cands)).toEqual([\n"
            "      ['todos', { status: 'done' }],\n"
            "      ['todos', { status: 'done', page: 2 }],\n"
            "    ])\n"
            "    // nested object partial match\n"
            "    expect(selectKeys(['t', { meta: { a: 1 } }], [['t', { meta: { a: 1, b: 2 } }], ['t', { meta: { a: 9 } }]]))\n"
            "      .toEqual([['t', { meta: { a: 1, b: 2 } }]])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_exact_mode_basic(self):
        """exact:true selects only candidates equivalent to the filter, never the
        prefixes/extensions selected in broad mode."""
        probe = (
            _HEADER
            + "describe('selectKeys exact', () => {\n"
            "  it('selects only equivalent candidates', () => {\n"
            "    const cands = [['todos'], ['todos', 5], ['todos', 5, 'comments'], ['todos']]\n"
            "    // broad picks the whole subtree...\n"
            "    expect(selectKeys(['todos'], cands)).toEqual([['todos'], ['todos', 5], ['todos', 5, 'comments'], ['todos']])\n"
            "    // ...exact picks only the two ['todos'] entries (dups preserved)\n"
            "    expect(selectKeys(['todos'], cands, { exact: true })).toEqual([['todos'], ['todos']])\n"
            "    expect(selectKeys(['todos', 5], cands, { exact: true })).toEqual([['todos', 5]])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_exact_mode_property_order_independent(self):
        """Exact equivalence uses the stable, order-independent key hash, so
        differing object property order still counts as equal."""
        probe = (
            _HEADER
            + "describe('selectKeys exact order-independent', () => {\n"
            "  it('ignores property ordering under exact', () => {\n"
            "    expect(selectKeys(['t', { b: 2, a: 1 }], [['t', { a: 1, b: 2 }]], { exact: true }))\n"
            "      .toEqual([['t', { a: 1, b: 2 }]])\n"
            "    // nested order independence\n"
            "    expect(selectKeys(['t', { x: { q: 2, p: 1 } }], [['t', { x: { p: 1, q: 2 } }]], { exact: true }))\n"
            "      .toEqual([['t', { x: { p: 1, q: 2 } }]])\n"
            "    // an extra property is NOT exact-equal\n"
            "    expect(selectKeys(['t', { a: 1 }], [['t', { a: 1, b: 2 }]], { exact: true }))\n"
            "      .toEqual([])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_empty_filter_edge_cases(self):
        """Empty filter [] selects everything in broad mode but only []
        candidates in exact mode."""
        probe = (
            _HEADER
            + "describe('selectKeys empty filter', () => {\n"
            "  it('handles empty filter in both modes', () => {\n"
            "    const cands = [[], ['a'], ['a', 1], ['b', { x: 1 }], []]\n"
            "    expect(selectKeys([], cands)).toEqual(cands)\n"
            "    expect(selectKeys([], cands, { exact: true })).toEqual([[], []])\n"
            "    // empty candidate list -> empty result regardless of mode\n"
            "    expect(selectKeys(['a'], [])).toEqual([])\n"
            "    expect(selectKeys([], [])).toEqual([])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_order_and_duplicate_preservation(self):
        """Result MUST preserve the original candidate ordering and include each
        matching duplicate independently (no dedup, no sorting)."""
        probe = (
            _HEADER
            + "describe('selectKeys order/dups', () => {\n"
            "  it('preserves input order and duplicates', () => {\n"
            "    const cands = [['todos', 3], ['todos', 1], ['todos', 1], ['users', 1], ['todos', 2]]\n"
            "    expect(selectKeys(['todos'], cands)).toEqual([['todos', 3], ['todos', 1], ['todos', 1], ['todos', 2]])\n"
            "    // interleaved non-matching entries are dropped but order otherwise kept\n"
            "    const mixed = [['todos', 9], ['x'], ['todos', 8], ['y'], ['todos', 9]]\n"
            "    expect(selectKeys(['todos'], mixed)).toEqual([['todos', 9], ['todos', 8], ['todos', 9]])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_equal_length_non_prefix_excluded(self):
        """Equal-length candidates that differ in a value are NOT selected in
        broad mode (a strict prefix relationship requires the candidate to be at
        least as long AND share every filter element)."""
        probe = (
            _HEADER
            + "describe('selectKeys equal length', () => {\n"
            "  it('excludes differing equal-length candidates', () => {\n"
            "    expect(selectKeys(['a', 1], [['a', 2], ['b', 1], ['a', 1], ['a', 1, 9]]))\n"
            "      .toEqual([['a', 1], ['a', 1, 9]])\n"
            "    // a longer filter never selects a shorter candidate\n"
            "    expect(selectKeys(['a', 1, 2], [['a'], ['a', 1], ['a', 1, 2]]))\n"
            "      .toEqual([['a', 1, 2]])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_purity_no_mutation(self):
        """selectKeys MUST NOT mutate the filter or any candidate (stable
        stringify snapshot before/after), and the returned array MUST NOT be the
        same reference as the input candidates array."""
        probe = (
            _HEADER
            + "describe('selectKeys purity', () => {\n"
            "  it('does not mutate inputs', () => {\n"
            "    const filter = ['todos', { status: 'done', meta: { p: 1 } }]\n"
            "    const cands = [\n"
            "      ['todos', { status: 'done', meta: { p: 1 }, page: 2 }],\n"
            "      ['todos', { status: 'open' }],\n"
            "    ]\n"
            "    const sf = JSON.stringify(filter)\n"
            "    const sc = JSON.stringify(cands)\n"
            "    const out = selectKeys(filter, cands)\n"
            "    expect(JSON.stringify(filter)).toBe(sf)\n"
            "    expect(JSON.stringify(cands)).toBe(sc)\n"
            "    expect(cands.length).toBe(2)\n"
            "    expect(out).not.toBe(cands)\n"
            "    // selected element references should still point at originals\n"
            "    expect(out[0]).toBe(cands[0])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_consistency_with_package_primitives(self):
        """selectKeys MUST reuse the package's existing comparison semantics: its
        membership decisions must agree with partialMatchKey (broad mode) and
        hashKey (exact mode) over a representative candidate grid, and order MUST
        match a manual filter of candidates by the primitive predicate."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { selectKeys } from '..'\n"
            "import { hashKey, partialMatchKey } from '../utils'\n"
            "const candidates = [\n"
            "  [], ['todos'], ['todos', 5], ['todos', 5, 'comments'],\n"
            "  ['users', 5], ['todos', 6],\n"
            "  ['todos', { status: 'done' }], ['todos', { status: 'done', page: 2 }],\n"
            "  ['todos', { status: 'open' }], ['t', { a: 1, b: 2 }], ['t', { b: 2, a: 1 }],\n"
            "  ['a', 1], ['a', 2], ['todos', 5],\n"
            "]\n"
            "const filters = [\n"
            "  [], ['todos'], ['todos', 5], ['users'], ['todos', { status: 'done' }],\n"
            "  ['t', { b: 2, a: 1 }], ['a', 1], ['nope'],\n"
            "]\n"
            "describe('selectKeys consistency', () => {\n"
            "  it('broad agrees with partialMatchKey, exact with hashKey, order preserved', () => {\n"
            "    for (const filter of filters) {\n"
            "      // broad: filter selects candidate iff partialMatchKey(candidate, filter)\n"
            "      const expectedBroad = candidates.filter((c) => partialMatchKey(c, filter))\n"
            "      expect(selectKeys(filter, candidates)).toEqual(expectedBroad)\n"
            "      // exact: filter selects candidate iff hashKey equal\n"
            "      const fh = hashKey(filter)\n"
            "      const expectedExact = candidates.filter((c) => hashKey(c) === fh)\n"
            "      expect(selectKeys(filter, candidates, { exact: true })).toEqual(expectedExact)\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_no_queryclient_required(self):
        """selectKeys runs purely in-process: importing and calling it without a
        QueryClient, cache, or timers produces correct results (a stub that
        depends on framework state would throw)."""
        probe = (
            _HEADER
            + "describe('selectKeys pure', () => {\n"
            "  it('works without any QueryClient/cache', () => {\n"
            "    // large-ish candidate grid evaluated entirely synchronously\n"
            "    const cands = []\n"
            "    for (let i = 0; i < 50; i++) cands.push(['todos', i])\n"
            "    cands.push(['users', 0])\n"
            "    const out = selectKeys(['todos'], cands)\n"
            "    expect(out.length).toBe(50)\n"
            "    expect(out[0]).toEqual(['todos', 0])\n"
            "    expect(out[49]).toEqual(['todos', 49])\n"
            "    expect(selectKeys(['todos', 25], cands, { exact: true })).toEqual([['todos', 25]])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)
