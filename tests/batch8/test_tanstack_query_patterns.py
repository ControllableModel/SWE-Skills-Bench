"""
Test for 'tanstack-query-patterns' skill (variant ext8) — Optimistic List
Update and Rollback Helper.

Verifies the agent added a pure, framework-agnostic optimistic-list utility to
`@tanstack/query-core`:

  packages/query-core/src/optimisticList.ts  (new)
    export interface OptimisticEdit<TItem> { type: 'add'|'update'|'remove'; item: TItem }
    export interface OptimisticResult<TItem> { next: Array<TItem>; snapshot: Array<TItem> }
    export function applyOptimistic<TItem extends { id: string|number }>(
      current: ReadonlyArray<TItem>, edit: OptimisticEdit<TItem>): OptimisticResult<TItem>
    export function rollback<TItem>(result: OptimisticResult<TItem>): Array<TItem>

  packages/query-core/src/index.ts            (re-exports applyOptimistic, rollback,
                                               OptimisticEdit / OptimisticResult)
  packages/query-core/src/__tests__/optimisticList.test.tsx  (agent's vitest suite)

Update semantics (identity by `id`):
  * 'add'    -> append; duplicate id is a no-op (contents unchanged)
  * 'update' -> replace same-id item in place (order preserved); missing id no-op
  * 'remove' -> drop same-id item (order preserved); missing id no-op
  * snapshot is a shallow copy of `current` captured before the edit
  * rollback(result) returns result.snapshot
  * next is ALWAYS a new array; current is never mutated

Verification strategy: instead of trusting the agent's own test file, this
suite injects its OWN vitest probe specs under packages/query-core/src/__tests__/
and runs them with the repo's native vitest — the exact command family the
Acceptance Criteria specifies:

    pnpm --filter @tanstack/query-core exec vitest run src/__tests__/<probe>

Each probe imports `applyOptimistic` / `rollback` from the package index (`..`)
and asserts concrete contents, identity (new-array / no-mutation) and the
rollback round-trip, so a stub / hardcoded / mutating / no-op-collapsing
implementation fails. A naive impl that returns `current` itself (same ref),
mutates in place, ignores `edit.type`, drops the snapshot, or duplicates ids
will be caught.
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
PROBE_BASENAME = "zzOptimisticListProbe.gen.test.tsx"
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


# Common probe preamble: imports the helpers from the package index.
_IMPORT = (
    "import { describe, expect, it } from 'vitest'\n"
    "import { applyOptimistic, rollback } from '..'\n"
)


class TestTanstackQueryPatterns:
    """Verify the applyOptimistic / rollback optimistic-list utility."""

    REPO_DIR = "/workspace/query"

    # ------------------------------------------------------------------
    # L1: deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_optimisticlist_source_file_exists(self):
        """packages/query-core/src/optimisticList.ts must exist and be non-trivial."""
        path = os.path.join(SRC_DIR, "optimisticList.ts")
        assert os.path.isfile(path), "optimisticList.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "applyOptimistic" in content, "applyOptimistic not defined in optimisticList.ts"
        assert "rollback" in content, "rollback not defined in optimisticList.ts"
        assert len(content.strip()) > 120, "optimisticList.ts looks empty/stub"

    def test_index_reexports_helpers_and_types(self):
        """index.ts must re-export the functions and the OptimisticEdit type."""
        path = os.path.join(SRC_DIR, "index.ts")
        assert os.path.isfile(path), "index.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "applyOptimistic" in content, "index.ts does not re-export applyOptimistic"
        assert "rollback" in content, "index.ts does not re-export rollback"
        assert "OptimisticEdit" in content, "index.ts does not re-export OptimisticEdit type"

    def test_agent_test_suite_exists(self):
        """The required vitest suite file must exist."""
        path = os.path.join(TESTS_SUBDIR, "optimisticList.test.tsx")
        assert os.path.isfile(path), "optimisticList.test.tsx not found"

    def test_helpers_are_importable_from_index(self):
        """Both helpers resolve from the package entry point and are functions."""
        probe = (
            _IMPORT
            + "describe('exports', () => {\n"
            "  it('are functions', () => {\n"
            "    expect(typeof applyOptimistic).toBe('function')\n"
            "    expect(typeof rollback).toBe('function')\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    # ------------------------------------------------------------------
    # L2: dynamic execution via the repo's native vitest toolchain.
    # ------------------------------------------------------------------

    def test_add_appends_to_end(self):
        """'add' appends edit.item at the end, preserving prior order."""
        probe = (
            _IMPORT
            + "describe('add', () => {\n"
            "  it('appends new item', () => {\n"
            "    const cur = [{ id: 1, t: 'a' }]\n"
            "    const r = applyOptimistic(cur, { type: 'add', item: { id: 2, t: 'b' } })\n"
            "    expect(r.next).toEqual([{ id: 1, t: 'a' }, { id: 2, t: 'b' }])\n"
            "    // append at end, not prepend\n"
            "    const r2 = applyOptimistic([{ id: 5 }, { id: 6 }], { type: 'add', item: { id: 7 } })\n"
            "    expect(r2.next.map((x) => x.id)).toEqual([5, 6, 7])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_add_duplicate_id_is_noop(self):
        """Adding an item with an already-present id leaves contents unchanged
        but still yields a fresh array (no duplicate id)."""
        probe = (
            _IMPORT
            + "describe('add dup', () => {\n"
            "  it('does not duplicate ids', () => {\n"
            "    const cur = [{ id: 1, t: 'a' }]\n"
            "    const r = applyOptimistic(cur, { type: 'add', item: { id: 1, t: 'dupe' } })\n"
            "    expect(r.next).toEqual([{ id: 1, t: 'a' }])\n"
            "    expect(r.next.length).toBe(1)\n"
            "    // must remain a new array even for the no-op\n"
            "    expect(r.next).not.toBe(cur)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_update_replaces_in_place(self):
        """'update' replaces the same-id item, preserving its position."""
        probe = (
            _IMPORT
            + "describe('update', () => {\n"
            "  it('replaces preserving order', () => {\n"
            "    const cur = [{ id: 1, t: 'a' }, { id: 2, t: 'b' }, { id: 3, t: 'c' }]\n"
            "    const r = applyOptimistic(cur, { type: 'update', item: { id: 2, t: 'B' } })\n"
            "    expect(r.next).toEqual([{ id: 1, t: 'a' }, { id: 2, t: 'B' }, { id: 3, t: 'c' }])\n"
            "    // position index unchanged\n"
            "    expect(r.next.findIndex((x) => x.id === 2)).toBe(1)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_update_missing_id_is_noop(self):
        """'update' of a non-existent id leaves contents unchanged (fresh array)."""
        probe = (
            _IMPORT
            + "describe('update missing', () => {\n"
            "  it('is a no-op for unknown id', () => {\n"
            "    const cur = [{ id: 1, t: 'a' }, { id: 2, t: 'b' }]\n"
            "    const r = applyOptimistic(cur, { type: 'update', item: { id: 99, t: 'z' } })\n"
            "    expect(r.next).toEqual([{ id: 1, t: 'a' }, { id: 2, t: 'b' }])\n"
            "    expect(r.next.length).toBe(2)\n"
            "    expect(r.next).not.toBe(cur)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_remove_drops_item_preserving_order(self):
        """'remove' drops the same-id item and preserves the order of the rest."""
        probe = (
            _IMPORT
            + "describe('remove', () => {\n"
            "  it('removes and keeps order', () => {\n"
            "    const cur = [{ id: 1 }, { id: 2 }, { id: 3 }]\n"
            "    const r = applyOptimistic(cur, { type: 'remove', item: { id: 2 } })\n"
            "    expect(r.next.map((x) => x.id)).toEqual([1, 3])\n"
            "    const r2 = applyOptimistic([{ id: 1 }, { id: 2 }], { type: 'remove', item: { id: 1 } })\n"
            "    expect(r2.next).toEqual([{ id: 2 }])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_remove_missing_id_is_noop(self):
        """'remove' of a non-existent id leaves contents unchanged (fresh array)."""
        probe = (
            _IMPORT
            + "describe('remove missing', () => {\n"
            "  it('is a no-op for unknown id', () => {\n"
            "    const cur = [{ id: 1 }, { id: 2 }]\n"
            "    const r = applyOptimistic(cur, { type: 'remove', item: { id: 42 } })\n"
            "    expect(r.next.map((x) => x.id)).toEqual([1, 2])\n"
            "    expect(r.next).not.toBe(cur)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_string_id_identity(self):
        """Identity by `id` works for string ids across all three edit types."""
        probe = (
            _IMPORT
            + "describe('string ids', () => {\n"
            "  it('matches by string id', () => {\n"
            "    const cur = [{ id: 'a', v: 1 }, { id: 'b', v: 2 }]\n"
            "    expect(applyOptimistic(cur, { type: 'update', item: { id: 'b', v: 20 } }).next)\n"
            "      .toEqual([{ id: 'a', v: 1 }, { id: 'b', v: 20 }])\n"
            "    expect(applyOptimistic(cur, { type: 'remove', item: { id: 'a', v: 1 } }).next)\n"
            "      .toEqual([{ id: 'b', v: 2 }])\n"
            "    expect(applyOptimistic(cur, { type: 'add', item: { id: 'b', v: 9 } }).next.length).toBe(2)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_next_is_new_array_and_no_mutation(self):
        """next is never the same ref as current, and current/its elements are
        never mutated, across add/update/remove (including no-op cases)."""
        probe = (
            _IMPORT
            + "describe('purity', () => {\n"
            "  it('fresh array, no mutation', () => {\n"
            "    const edits = [\n"
            "      { type: 'add', item: { id: 9, t: 'n' } },\n"
            "      { type: 'add', item: { id: 1, t: 'dup' } },\n"
            "      { type: 'update', item: { id: 2, t: 'B' } },\n"
            "      { type: 'update', item: { id: 99, t: 'z' } },\n"
            "      { type: 'remove', item: { id: 1 } },\n"
            "      { type: 'remove', item: { id: 77 } },\n"
            "    ]\n"
            "    for (const e of edits) {\n"
            "      const cur = [{ id: 1, t: 'a' }, { id: 2, t: 'b' }]\n"
            "      const snap = JSON.stringify(cur)\n"
            "      const r = applyOptimistic(cur, e)\n"
            "      expect(Array.isArray(r.next)).toBe(true)\n"
            "      expect(r.next).not.toBe(cur)\n"
            "      // current untouched (length + deep content)\n"
            "      expect(JSON.stringify(cur)).toBe(snap)\n"
            "      expect(cur.length).toBe(2)\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_snapshot_captures_pre_edit_state(self):
        """snapshot is a shallow copy of current captured BEFORE the edit: it is
        a new array equal in contents to the original current, distinct from next."""
        probe = (
            _IMPORT
            + "describe('snapshot', () => {\n"
            "  it('captures the prior state', () => {\n"
            "    const cur = [{ id: 1, t: 'a' }, { id: 2, t: 'b' }]\n"
            "    const r = applyOptimistic(cur, { type: 'add', item: { id: 3, t: 'c' } })\n"
            "    // snapshot equals original contents, not the post-edit list\n"
            "    expect(r.snapshot).toEqual([{ id: 1, t: 'a' }, { id: 2, t: 'b' }])\n"
            "    expect(r.snapshot.length).toBe(2)\n"
            "    expect(r.next.length).toBe(3)\n"
            "    // snapshot is a copy, not aliasing current or next\n"
            "    expect(r.snapshot).not.toBe(cur)\n"
            "    expect(r.snapshot).not.toBe(r.next)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_rollback_restores_pre_edit_snapshot(self):
        """rollback(result) returns result.snapshot — contents equal to the
        pre-edit current — for each edit type."""
        probe = (
            _IMPORT
            + "describe('rollback', () => {\n"
            "  it('restores the prior snapshot', () => {\n"
            "    const cur = [{ id: 1, t: 'a' }, { id: 2, t: 'b' }]\n"
            "    for (const e of [\n"
            "      { type: 'add', item: { id: 3, t: 'c' } },\n"
            "      { type: 'update', item: { id: 1, t: 'A' } },\n"
            "      { type: 'remove', item: { id: 2 } },\n"
            "    ]) {\n"
            "      const r = applyOptimistic(cur, e)\n"
            "      const restored = rollback(r)\n"
            "      expect(restored).toBe(r.snapshot)\n"
            "      expect(restored).toEqual([{ id: 1, t: 'a' }, { id: 2, t: 'b' }])\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_empty_list_and_full_cycle(self):
        """Empty-list edge cases plus an apply -> rollback round-trip that recovers
        the exact original list contents end-to-end."""
        probe = (
            _IMPORT
            + "describe('edge + cycle', () => {\n"
            "  it('handles empty and full cycle', () => {\n"
            "    // add into empty\n"
            "    expect(applyOptimistic([], { type: 'add', item: { id: 1 } }).next).toEqual([{ id: 1 }])\n"
            "    // update/remove on empty are no-ops\n"
            "    expect(applyOptimistic([], { type: 'update', item: { id: 1 } }).next).toEqual([])\n"
            "    expect(applyOptimistic([], { type: 'remove', item: { id: 1 } }).next).toEqual([])\n"
            "    // full optimistic-then-rollback cycle\n"
            "    const original = [{ id: 1, t: 'x' }, { id: 2, t: 'y' }, { id: 3, t: 'z' }]\n"
            "    const r = applyOptimistic(original, { type: 'remove', item: { id: 2 } })\n"
            "    expect(r.next.map((i) => i.id)).toEqual([1, 3])\n"
            "    expect(rollback(r)).toEqual(original)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)
