"""
Test for 'tanstack-query-patterns' skill (variant ext9) — Mutation Filter Matcher.

Verifies the agent added a pure `selectMutations(filter, mutations)` utility to
`@tanstack/query-core` (packages/query-core/src/mutationFilter.ts), re-exported
it (with its `MutationFilter` / `MutationRecord` types) from the package entry
point, and that the matching semantics match the requirement doc exactly:

  * key matching by prefix in broad (default) mode,
  * exact key equivalence in `exact: true` mode,
  * a mutation with no `mutationKey` never matches a key filter,
  * `status` equality matching,
  * AND-combination of every present criterion,
  * an empty filter `{}` matches all mutations,
  * input order is preserved (duplicates each independently included),
  * the function is pure (does not mutate its inputs).

Strategy: rather than trusting the agent's own test file, this suite writes its
OWN vitest probe specs into packages/query-core/src/__tests__/ and runs them
with the repo's native vitest — the SAME command family the Acceptance Criteria
specifies:

    pnpm --filter @tanstack/query-core exec vitest run src/__tests__/<probe>.tsx

Each probe imports `selectMutations` from the package index (`..`) and asserts
concrete return values / ordering / purity, so a stub, hardcoded, status-only,
or order-shuffling implementation fails. One probe additionally cross-checks
that `selectMutations` agrees with the package's own `partialMatchKey` /
`hashKey` primitives (which the doc requires it to reuse).
"""

import os
import subprocess

import pytest


REPO_DIR = "/workspace/query"
CORE_DIR = os.path.join(REPO_DIR, "packages", "query-core")
SRC_DIR = os.path.join(CORE_DIR, "src")
TESTS_SUBDIR = os.path.join(SRC_DIR, "__tests__")

# Probe specs we inject live under src/__tests__ so the package's vitest config
# (test.dir === './src') picks them up. Distinct name to avoid clobbering the
# agent's own mutationFilter.test.tsx.
PROBE_BASENAME = "zzMutationFilterProbe.gen.test.tsx"
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


# A reusable JS preamble defining a representative mutation corpus.
_CORPUS = (
    "const mutations = [\n"
    "  { mutationKey: ['todo', 1], status: 'pending' },\n"
    "  { mutationKey: ['todo', 2], status: 'idle' },\n"
    "  { mutationKey: ['user', 1], status: 'pending' },\n"
    "  { status: 'success' },\n"
    "  { mutationKey: ['todo'], status: 'error' },\n"
    "]\n"
)


class TestTanstackQueryPatterns:
    """Verify the selectMutations mutation-filter matcher utility (ext9)."""

    REPO_DIR = "/workspace/query"

    # ------------------------------------------------------------------
    # L1: deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_mutationfilter_source_file_exists(self):
        """packages/query-core/src/mutationFilter.ts must exist and define
        selectMutations (non-trivial body)."""
        path = os.path.join(SRC_DIR, "mutationFilter.ts")
        assert os.path.isfile(path), "mutationFilter.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "selectMutations" in content, (
            "selectMutations not defined in mutationFilter.ts"
        )
        assert len(content.strip()) > 80, "mutationFilter.ts looks empty/stub"

    def test_index_reexports_selectmutations(self):
        """index.ts must re-export selectMutations and the MutationFilter /
        MutationRecord types."""
        path = os.path.join(SRC_DIR, "index.ts")
        assert os.path.isfile(path), "index.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "selectMutations" in content, (
            "index.ts does not re-export selectMutations"
        )
        assert "MutationFilter" in content, (
            "index.ts does not re-export MutationFilter"
        )
        assert "MutationRecord" in content, (
            "index.ts does not re-export MutationRecord"
        )

    def test_agent_test_suite_exists(self):
        """The required vitest suite file must exist."""
        path = os.path.join(TESTS_SUBDIR, "mutationFilter.test.tsx")
        assert os.path.isfile(path), "mutationFilter.test.tsx not found"

    def test_symbols_importable_from_index(self):
        """selectMutations must be a callable function exported from the package
        index (not merely a re-exported type). A bare smoke import + typeof."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { selectMutations } from '..'\n"
            "describe('selectMutations import', () => {\n"
            "  it('is a function', () => {\n"
            "    expect(typeof selectMutations).toBe('function')\n"
            "    expect(selectMutations({}, [])).toEqual([])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    # ------------------------------------------------------------------
    # L2: dynamic execution via the repo's native vitest toolchain.
    # ------------------------------------------------------------------

    def test_empty_filter_matches_all_in_order(self):
        """`selectMutations({}, mutations)` returns ALL mutations, preserving
        input order. A naive impl that filters out keyless mutations or reorders
        fails here."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { selectMutations } from '..'\n"
            f"{_CORPUS}"
            "describe('selectMutations empty filter', () => {\n"
            "  it('matches all preserving order', () => {\n"
            "    const out = selectMutations({}, mutations)\n"
            "    expect(out).toEqual(mutations)\n"
            "    expect(out.map((m) => m.status)).toEqual(\n"
            "      ['pending', 'idle', 'pending', 'success', 'error'])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_status_only_filter(self):
        """A status-only filter selects exactly the matching-status mutations in
        input order and ignores keys entirely (keyless mutations included)."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { selectMutations } from '..'\n"
            f"{_CORPUS}"
            "describe('selectMutations status only', () => {\n"
            "  it('selects by status, ignoring keys', () => {\n"
            "    const pending = selectMutations({ status: 'pending' }, mutations)\n"
            "    expect(pending.map((m) => m.mutationKey)).toEqual([['todo', 1], ['user', 1]])\n"
            "    const success = selectMutations({ status: 'success' }, mutations)\n"
            "    expect(success).toEqual([{ status: 'success' }])\n"
            "    expect(selectMutations({ status: 'idle' }, mutations).length).toBe(1)\n"
            "    expect(selectMutations({ status: 'error' }, mutations).length).toBe(1)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_broad_key_prefix_match(self):
        """Broad (default) mode matches by leading-scope prefix: filter
        `['todo']` matches `['todo', 5]` and `['todo']`, but not `['user', 1]`.
        A keyless mutation never matches a key filter."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { selectMutations } from '..'\n"
            "const ms = [\n"
            "  { mutationKey: ['todo', 5], status: 'idle' },\n"
            "  { mutationKey: ['todo'], status: 'pending' },\n"
            "  { mutationKey: ['user', 1], status: 'idle' },\n"
            "  { status: 'idle' },\n"
            "  { mutationKey: ['todo', 5, 'edit'], status: 'idle' },\n"
            "]\n"
            "describe('selectMutations broad key', () => {\n"
            "  it('prefix matches in broad mode', () => {\n"
            "    const out = selectMutations({ mutationKey: ['todo'] }, ms)\n"
            "    expect(out.map((m) => m.mutationKey)).toEqual(\n"
            "      [['todo', 5], ['todo'], ['todo', 5, 'edit']])\n"
            "    // keyless + foreign key excluded\n"
            "    expect(out.some((m) => m.mutationKey === undefined)).toBe(false)\n"
            "    expect(out.some((m) => m.mutationKey && m.mutationKey[0] === 'user')).toBe(false)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_exact_key_match(self):
        """In exact mode `{ mutationKey: ['todo'], exact: true }` matches only
        the mutation whose key is equivalent to `['todo']` — NOT `['todo', 5]`.
        This is the case a broad-only stub gets wrong."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { selectMutations } from '..'\n"
            "const ms = [\n"
            "  { mutationKey: ['todo', 5], status: 'idle' },\n"
            "  { mutationKey: ['todo'], status: 'idle' },\n"
            "  { mutationKey: ['todo', 5, 'edit'], status: 'idle' },\n"
            "]\n"
            "describe('selectMutations exact key', () => {\n"
            "  it('exact mode requires key equivalence', () => {\n"
            "    const exact = selectMutations({ mutationKey: ['todo'], exact: true }, ms)\n"
            "    expect(exact).toEqual([{ mutationKey: ['todo'], status: 'idle' }])\n"
            "    // doc scenario: exact filter ['todo'] does NOT match ['todo', 5]\n"
            "    const none = selectMutations(\n"
            "      { mutationKey: ['todo'], exact: true },\n"
            "      [{ mutationKey: ['todo', 5], status: 'idle' }])\n"
            "    expect(none).toEqual([])\n"
            "    // but broad does\n"
            "    const broad = selectMutations(\n"
            "      { mutationKey: ['todo'] },\n"
            "      [{ mutationKey: ['todo', 5], status: 'idle' }])\n"
            "    expect(broad.length).toBe(1)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_exact_key_order_independent_equivalence(self):
        """Exact key equivalence is stable/order-independent for object
        elements: `['todo', {a:1,b:2}]` is exact-equivalent to
        `['todo', {b:2,a:1}]`."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { selectMutations } from '..'\n"
            "const ms = [\n"
            "  { mutationKey: ['todo', { b: 2, a: 1 }], status: 'idle' },\n"
            "  { mutationKey: ['todo', { a: 1 }], status: 'idle' },\n"
            "]\n"
            "describe('selectMutations exact order-independent', () => {\n"
            "  it('object property order does not affect exact match', () => {\n"
            "    const out = selectMutations(\n"
            "      { mutationKey: ['todo', { a: 1, b: 2 }], exact: true }, ms)\n"
            "    expect(out).toEqual([{ mutationKey: ['todo', { b: 2, a: 1 }], status: 'idle' }])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_keyless_mutation_never_matches_key_filter(self):
        """A mutation with no `mutationKey` MUST NOT match any key filter, in
        both broad and exact modes (doc: empty -> no key)."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { selectMutations } from '..'\n"
            "const ms = [{ status: 'idle' }, { status: 'pending' }]\n"
            "describe('selectMutations keyless', () => {\n"
            "  it('keyless mutation excluded by key filter', () => {\n"
            "    expect(selectMutations({ mutationKey: ['todo'] }, ms)).toEqual([])\n"
            "    expect(selectMutations({ mutationKey: ['todo'], exact: true }, ms)).toEqual([])\n"
            "    expect(selectMutations({ mutationKey: [] }, ms)).toEqual([])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_and_combination_of_key_and_status(self):
        """Key + status criteria combine with AND: only mutations matching BOTH
        are returned. A stub that applies only one criterion fails."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { selectMutations } from '..'\n"
            f"{_CORPUS}"
            "describe('selectMutations AND', () => {\n"
            "  it('combines key and status', () => {\n"
            "    // broad key 'todo' AND status pending -> only ['todo',1]/pending\n"
            "    const out = selectMutations({ mutationKey: ['todo'], status: 'pending' }, mutations)\n"
            "    expect(out).toEqual([{ mutationKey: ['todo', 1], status: 'pending' }])\n"
            "    // status matches but key does not -> excluded\n"
            "    const none = selectMutations({ mutationKey: ['todo'], status: 'success' }, mutations)\n"
            "    expect(none).toEqual([])\n"
            "    // key matches (broad 'todo') but status mismatch -> excluded\n"
            "    const noneStatus = selectMutations({ mutationKey: ['todo'], status: 'pending' },\n"
            "      [{ mutationKey: ['todo', 2], status: 'idle' }])\n"
            "    expect(noneStatus).toEqual([])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_order_preserved_with_duplicates(self):
        """Result order matches input order and duplicate matching records are
        each independently included (no de-duplication)."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { selectMutations } from '..'\n"
            "const a = { mutationKey: ['todo', 1], status: 'pending' }\n"
            "const b = { mutationKey: ['todo', 2], status: 'pending' }\n"
            "const ms = [b, a, b, a]\n"
            "describe('selectMutations order/dupes', () => {\n"
            "  it('preserves order and keeps duplicates', () => {\n"
            "    const out = selectMutations({ status: 'pending' }, ms)\n"
            "    expect(out.length).toBe(4)\n"
            "    expect(out).toEqual([b, a, b, a])\n"
            "    // referential identity preserved (no cloning)\n"
            "    expect(out[0]).toBe(b)\n"
            "    expect(out[1]).toBe(a)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_purity_no_mutation_of_inputs(self):
        """selectMutations MUST NOT mutate its inputs: neither the filter, the
        outer array, nor any element."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { selectMutations } from '..'\n"
            "describe('selectMutations purity', () => {\n"
            "  it('does not mutate inputs', () => {\n"
            "    const filter = { mutationKey: ['todo'], status: 'pending' }\n"
            "    const filterSnap = JSON.stringify(filter)\n"
            "    const ms = [\n"
            "      { mutationKey: ['todo', 1], status: 'pending' },\n"
            "      { mutationKey: ['user', 1], status: 'idle' },\n"
            "    ]\n"
            "    const msSnap = JSON.stringify(ms)\n"
            "    const lenBefore = ms.length\n"
            "    selectMutations(filter, ms)\n"
            "    expect(JSON.stringify(filter)).toBe(filterSnap)\n"
            "    expect(JSON.stringify(ms)).toBe(msSnap)\n"
            "    expect(ms.length).toBe(lenBefore)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_consistency_with_package_primitives(self):
        """selectMutations MUST reuse the package's existing key-comparison
        primitives. Its per-mutation verdict over a representative grid must
        agree with a reference oracle built from `partialMatchKey` / `hashKey`
        (broad => partialMatchKey(candidate, filterKey); exact => hashKey
        equality), AND'd with status equality — rather than a divergent compare.
        """
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { selectMutations } from '..'\n"
            "import { hashKey, partialMatchKey } from '../utils'\n"
            "const keys = [\n"
            "  undefined, [], ['todo'], ['todo', 1], ['todo', 1, 'edit'],\n"
            "  ['user', 1], ['todo', { a: 1 }], ['todo', { a: 1, b: 2 }],\n"
            "]\n"
            "const statuses = ['idle', 'pending', 'success', 'error']\n"
            "const corpus = []\n"
            "let si = 0\n"
            "for (const k of keys) {\n"
            "  const status = statuses[si % statuses.length]; si++\n"
            "  corpus.push(k === undefined ? { status } : { mutationKey: k, status })\n"
            "}\n"
            "function matchesRef(filter, m) {\n"
            "  if (filter.mutationKey) {\n"
            "    if (!m.mutationKey) return false\n"
            "    if (filter.exact) {\n"
            "      if (hashKey(m.mutationKey) !== hashKey(filter.mutationKey)) return false\n"
            "    } else if (!partialMatchKey(m.mutationKey, filter.mutationKey)) {\n"
            "      return false\n"
            "    }\n"
            "  }\n"
            "  if (filter.status && m.status !== filter.status) return false\n"
            "  return true\n"
            "}\n"
            "const filters = [\n"
            "  {}, { status: 'idle' }, { status: 'pending' },\n"
            "  { mutationKey: ['todo'] }, { mutationKey: ['todo'], exact: true },\n"
            "  { mutationKey: ['todo', 1] }, { mutationKey: ['todo', 1], exact: true },\n"
            "  { mutationKey: [] }, { mutationKey: ['todo'], status: 'pending' },\n"
            "  { mutationKey: ['todo', { a: 1 }] },\n"
            "  { mutationKey: ['todo', { a: 1, b: 2 }], exact: true },\n"
            "]\n"
            "describe('selectMutations consistency', () => {\n"
            "  it('agrees with partialMatchKey/hashKey oracle and ordering', () => {\n"
            "    for (const f of filters) {\n"
            "      const expected = corpus.filter((m) => matchesRef(f, m))\n"
            "      const actual = selectMutations(f, corpus)\n"
            "      expect(actual).toEqual(expected)\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)
