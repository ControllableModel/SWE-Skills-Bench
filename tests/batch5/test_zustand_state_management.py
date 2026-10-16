"""Benchmark tests for the `zustand-state-management` skill (variant ext5).

Variant task (source of truth: tasks/ext5/zustand-state-management.md): the agent
must implement a self-contained PAGINATED DATA-TABLE store module on top of
zustand's public vanilla + middleware API. Deliverables:
  - examples/table-store/tableStore.ts  (factory `createTableStore` + types)
  - tests/tableStore.test.ts             (the agent's own Vitest suite)

The store returns the vanilla handles `getState` / `setState` / `subscribe`
(with the selector-aware `subscribe(selector, listener, options?)` form) and
exposes paging/sorting state plus derived fields `sortedRows`, `pageRows`,
`pageCount`, an async `fetchRows(fetcher)` with status/error states, and
actions `setRows`, `setSort`, `goToPage`, `nextPage`, `prevPage`.

Verification strategy:
  * L1 — the deliverable files exist, are non-trivial, declare the factory, and
    the agent's own `tests/tableStore.test.ts` suite passes (>=10 cases).
  * L2 — discriminative DYNAMIC EXECUTION. We DO NOT trust the agent's own tests.
    We inject INDEPENDENT Vitest driver files into REPO_DIR/tests/ that import
    the agent's `createTableStore` factory directly and exercise real runtime
    behavior: pageCount/pageRows math, duplicate-id rejection, sorting by score
    and name in both directions, goToPage clamping, next/prev boundaries,
    derived-consistency across an action sequence, async success/error paths,
    the invalid-fetcher guard, and a `pageRows` selector subscription that fires
    on a page change but not on an unrelated `status` change. Each driver runs
    via the repo's native `pnpm vitest run`; we assert on returncode.

A naive / hardcoded / "looks related" implementation (fixed pageRows, ignored
sort direction, no clamping, swallowed duplicates, throwing async path) fails
these driver tests.
"""

import os
import re
import shutil
import subprocess
import uuid

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - helper is present at runtime
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/zustand"
TABLE_STORE = os.path.join(REPO_DIR, "examples", "table-store", "tableStore.ts")
AGENT_TEST = os.path.join(REPO_DIR, "tests", "tableStore.test.ts")

# Independent driver written under tests/ so vitest (dir: 'tests') picks it up.
_TAG = uuid.uuid4().hex[:8]
_DRIVER_BASENAME = f"_bench_table_driver_{_TAG}.test.ts"
DRIVER_PATH = os.path.join(REPO_DIR, "tests", _DRIVER_BASENAME)

VITEST_TIMEOUT = 600

# Relative import path from a file living in tests/ to the table store module.
_IMPORT = "../examples/table-store/tableStore"


def _pnpm_available():
    return shutil.which("pnpm") is not None


@pytest.fixture(scope="module", autouse=True)
def _prepare_deps():
    """Best-effort install of node deps before running native vitest."""
    if ensure_npm_dependencies is not None:
        try:
            ensure_npm_dependencies(REPO_DIR)
        except Exception:
            if _pnpm_available():
                subprocess.run(
                    ["pnpm", "install", "--frozen-lockfile=false"],
                    cwd=REPO_DIR,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )
    yield


def _run_vitest(rel_file):
    """Run `pnpm vitest run <rel_file>` (or npx fallback) from REPO_DIR."""
    if _pnpm_available():
        cmd = ["pnpm", "vitest", "run", rel_file, "--reporter=verbose"]
    else:
        cmd = ["npx", "vitest", "run", rel_file, "--reporter=verbose"]
    return subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=VITEST_TIMEOUT,
    )


def _write_driver(body):
    os.makedirs(os.path.dirname(DRIVER_PATH), exist_ok=True)
    with open(DRIVER_PATH, "w") as fh:
        fh.write(body)
    return _DRIVER_BASENAME


def _cleanup_driver():
    try:
        if os.path.exists(DRIVER_PATH):
            os.remove(DRIVER_PATH)
    except OSError:
        pass


def _run_driver(body):
    rel = _write_driver(body)
    try:
        return _run_vitest(rel)
    finally:
        _cleanup_driver()


def _assert_passed(proc, scenario):
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, (
        f"vitest driver for '{scenario}' failed (rc={proc.returncode}).\n"
        f"{combined[-4000:]}"
    )


# Shared TS prelude: a deterministic dataset and a helper to read row arrays.
_PRELUDE = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createTableStore }} from '{_IMPORT}'

const ROWS = [
  {{ id: 'r1', name: 'Charlie', score: 30 }},
  {{ id: 'r2', name: 'alice',   score: 10 }},
  {{ id: 'r3', name: 'Bob',     score: 20 }},
  {{ id: 'r4', name: 'dave',    score: 50 }},
  {{ id: 'r5', name: 'Eve',     score: 40 }},
]

function ids(rows: any): string[] {{
  return (rows as any[]).map((r) => r.id)
}}
"""


class TestZustandStateManagement:
    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------ L1
    def test_table_store_module_exists(self):
        """L1: examples/table-store/tableStore.ts exists and is non-trivial."""
        assert os.path.isfile(TABLE_STORE), f"missing {TABLE_STORE}"
        size = os.path.getsize(TABLE_STORE)
        assert size > 200, f"tableStore.ts suspiciously small ({size} bytes)"

    def test_module_exports_factory(self):
        """L1: module declares an exported `createTableStore`."""
        with open(TABLE_STORE) as fh:
            src = fh.read()
        assert re.search(r"export\b.*\bcreateTableStore\b", src) or re.search(
            r"\bcreateTableStore\b", src
        ), "createTableStore not found in tableStore.ts"

    def test_agent_test_suite_exists(self):
        """L1: the agent's own Vitest suite file exists and is non-trivial."""
        assert os.path.isfile(AGENT_TEST), f"missing {AGENT_TEST}"
        assert os.path.getsize(AGENT_TEST) > 200

    def test_agent_suite_passes(self):
        """L1/L2: the agent's own `tests/tableStore.test.ts` suite passes (>=10)."""
        proc = _run_vitest("tests/tableStore.test.ts")
        _assert_passed(proc, "agent tableStore.test.ts suite")
        combined = (proc.stdout or "") + (proc.stderr or "")
        m = re.search(r"Tests\s+(\d+)\s+passed", combined)
        if m:
            assert int(m.group(1)) >= 10, (
                f"expected >=10 passing tests, parsed {m.group(1)}\n"
                f"{combined[-2000:]}"
            )

    # ------------------------------------------------------------------ L2
    def test_setrows_pagecount_and_pagerows(self):
        """L2: setRows fills rows; pageCount=ceil(n/pageSize); pageRows is page 0."""
        body = _PRELUDE + """
describe('bench-setrows', () => {
  it('computes pageCount and the first page slice', () => {
    const store = createTableStore({ pageSize: 2 })
    store.getState().setRows(ROWS)
    const s = store.getState()
    expect((s.rows as any[]).length).toBe(5)
    expect(s.pageSize).toBe(2)
    expect(s.pageIndex).toBe(0)
    expect(s.pageCount).toBe(3)            // ceil(5/2)
    expect((s.pageRows as any[]).length).toBe(2)
    // default sort key/dir must keep derived data consistent: pageRows is the
    // first pageSize entries of sortedRows.
    expect(ids(s.pageRows)).toEqual(ids((s.sortedRows as any[]).slice(0, 2)))
  })

  it('pageCount is at least 1 even with zero rows', () => {
    const store = createTableStore({ pageSize: 4 })
    store.getState().setRows([])
    const s = store.getState()
    expect((s.rows as any[]).length).toBe(0)
    expect(s.pageCount).toBe(1)
    expect((s.pageRows as any[]).length).toBe(0)
  })
})
"""
        _assert_passed(_run_driver(body), "setRows pageCount/pageRows")

    def test_setrows_rejects_duplicate_ids(self):
        """L2: setRows with duplicate ids is rejected (no state change)."""
        body = _PRELUDE + """
describe('bench-dupe', () => {
  it('rejects duplicate ids and leaves state unchanged', () => {
    const store = createTableStore({ pageSize: 10 })
    store.getState().setRows(ROWS)
    const before = store.getState()
    const beforeIds = ids(before.rows as any[])
    // attempt to set rows that contain a duplicate id
    store.getState().setRows([
      { id: 'd', name: 'D', score: 1 },
      { id: 'd', name: 'D2', score: 2 },
      { id: 'e', name: 'E', score: 3 },
    ])
    const after = store.getState()
    expect(ids(after.rows as any[])).toEqual(beforeIds)
    expect((after.rows as any[]).length).toBe(5)
  })
})
"""
        _assert_passed(_run_driver(body), "duplicate id rejection")

    def test_sort_by_score_both_directions(self):
        """L2: setSort('score', dir) orders numerically asc and desc."""
        body = _PRELUDE + """
describe('bench-sort-score', () => {
  it('sorts numerically by score ascending and descending', () => {
    const store = createTableStore({ pageSize: 10 })
    store.getState().setRows(ROWS)
    store.getState().setSort('score', 'asc')
    let s = store.getState()
    expect(s.sortKey).toBe('score')
    expect(s.sortDir).toBe('asc')
    expect((s.sortedRows as any[]).map((r) => r.score)).toEqual([10, 20, 30, 40, 50])
    expect(s.pageIndex).toBe(0)
    store.getState().setSort('score', 'desc')
    s = store.getState()
    expect((s.sortedRows as any[]).map((r) => r.score)).toEqual([50, 40, 30, 20, 10])
    // pageRows (pageSize 10) mirrors sortedRows here
    expect(ids(s.pageRows)).toEqual(ids(s.sortedRows))
  })
})
"""
        _assert_passed(_run_driver(body), "sort by score")

    def test_sort_by_name_both_directions(self):
        """L2: setSort('name', dir) orders lexicographically asc and desc."""
        body = _PRELUDE + """
describe('bench-sort-name', () => {
  it('sorts lexicographically by name ascending and descending', () => {
    const store = createTableStore({ pageSize: 10 })
    store.getState().setRows(ROWS)
    store.getState().setSort('name', 'asc')
    let asc = (store.getState().sortedRows as any[]).map((r) => r.name)
    const expectedAsc = [...ROWS.map((r) => r.name)].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0))
    expect(asc).toEqual(expectedAsc)
    store.getState().setSort('name', 'desc')
    let desc = (store.getState().sortedRows as any[]).map((r) => r.name)
    expect(desc).toEqual([...expectedAsc].reverse())
  })
})
"""
        _assert_passed(_run_driver(body), "sort by name")

    def test_gotopage_clamps_to_range(self):
        """L2: goToPage clamps the index into [0, pageCount-1]."""
        body = _PRELUDE + """
describe('bench-goto', () => {
  it('clamps goToPage to the valid range', () => {
    const store = createTableStore({ pageSize: 2 })
    store.getState().setRows(ROWS)            // 5 rows -> pageCount 3
    store.getState().goToPage(1)
    expect(store.getState().pageIndex).toBe(1)
    // beyond the last page clamps to pageCount-1 (2)
    store.getState().goToPage(99)
    expect(store.getState().pageIndex).toBe(2)
    // below 0 clamps to 0
    store.getState().goToPage(-5)
    expect(store.getState().pageIndex).toBe(0)
    // page index 2 (last) has the single remaining row
    store.getState().goToPage(2)
    const s = store.getState()
    expect(s.pageIndex).toBe(2)
    expect((s.pageRows as any[]).length).toBe(1)
    expect(ids(s.pageRows)).toEqual([ids(s.sortedRows as any[])[4]])
  })
})
"""
        _assert_passed(_run_driver(body), "goToPage clamping")

    def test_next_prev_page_boundaries(self):
        """L2: nextPage/prevPage move one page and no-op at the boundaries."""
        body = _PRELUDE + """
describe('bench-next-prev', () => {
  it('moves a page and is a no-op at each boundary', () => {
    const store = createTableStore({ pageSize: 2 })
    store.getState().setRows(ROWS)            // pageCount 3
    expect(store.getState().pageIndex).toBe(0)
    // prevPage at page 0 is a no-op
    store.getState().prevPage()
    expect(store.getState().pageIndex).toBe(0)
    store.getState().nextPage()
    expect(store.getState().pageIndex).toBe(1)
    store.getState().nextPage()
    expect(store.getState().pageIndex).toBe(2)
    // nextPage at the last page is a no-op
    store.getState().nextPage()
    expect(store.getState().pageIndex).toBe(2)
    store.getState().prevPage()
    expect(store.getState().pageIndex).toBe(1)
  })
})
"""
        _assert_passed(_run_driver(body), "next/prev boundaries")

    def test_derived_never_drift(self):
        """L2: derived fields equal an independent recompute after every action."""
        body = _PRELUDE + """
function recompute(rows: any[], pageSize: number, pageIndex: number, key: string, dir: string) {
  const sorted = [...rows].sort((a, b) => {
    let c: number
    if (key === 'score') c = a.score - b.score
    else c = a.name < b.name ? -1 : a.name > b.name ? 1 : 0
    return dir === 'asc' ? c : -c
  })
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize))
  const clamped = Math.min(Math.max(pageIndex, 0), pageCount - 1)
  const start = clamped * pageSize
  const pageRows = sorted.slice(start, start + pageSize)
  return { sorted, pageCount, clamped, pageRows }
}

describe('bench-drift', () => {
  it('sortedRows / pageRows / pageCount / pageIndex match a recompute', () => {
    const store = createTableStore({ pageSize: 2 })
    const ops: Array<() => void> = [
      () => store.getState().setRows(ROWS),
      () => store.getState().setSort('score', 'desc'),
      () => store.getState().goToPage(2),
      () => store.getState().setSort('name', 'asc'),
      () => store.getState().nextPage(),
      () => store.getState().setRows(ROWS.slice(0, 3)),
      () => store.getState().goToPage(5),
    ]
    for (const op of ops) {
      op()
      const s = store.getState()
      const r = recompute(
        s.rows as any[], s.pageSize, s.pageIndex, s.sortKey, s.sortDir,
      )
      expect(ids(s.sortedRows)).toEqual(ids(r.sorted))
      expect(s.pageCount).toBe(r.pageCount)
      expect(s.pageIndex).toBe(r.clamped)
      expect(ids(s.pageRows)).toEqual(ids(r.pageRows))
    }
  })
})
"""
        _assert_passed(_run_driver(body), "derived no-drift invariant")

    def test_pagerows_selector_fires_only_on_slice_change(self):
        """L2: pageRows selector fires on a page change, not on unrelated status."""
        body = _PRELUDE + """
describe('bench-selector', () => {
  it('pageRows subscriber ignores unrelated status changes', () => {
    const store = createTableStore({ pageSize: 2 })
    store.getState().setRows(ROWS)            // pageCount 3
    let calls = 0
    const seen: string[][] = []
    const unsub = store.subscribe(
      (s: any) => s.pageRows,
      (cur: any[]) => { calls += 1; seen.push(ids(cur)) },
    )
    // changing the page changes the pageRows slice -> fires
    store.getState().nextPage()
    expect(calls).toBe(1)
    // an unrelated status-only change must NOT fire a pageRows listener
    store.setState({ status: 'loading' } as any)
    expect(calls).toBe(1)
    // a sort that reorders the visible page changes pageRows -> fires
    store.getState().goToPage(0)
    const before = calls
    store.getState().setSort('score', 'desc')
    expect(calls).toBeGreaterThan(before)
    unsub()
  })

  it('fireImmediately delivers the current slice synchronously', () => {
    const store = createTableStore({ pageSize: 2 })
    store.getState().setRows(ROWS)
    const seen: string[][] = []
    const unsub = store.subscribe(
      (s: any) => s.pageRows,
      (cur: any[]) => { seen.push(ids(cur)) },
      { fireImmediately: true },
    )
    expect(seen.length).toBe(1)
    expect(seen[0].length).toBe(2)
    unsub()
  })
})
"""
        _assert_passed(_run_driver(body), "pageRows selector subscription")

    def test_async_fetch_success_path(self):
        """L2: fetchRows success replaces rows and leaves status 'success'."""
        body = _PRELUDE + """
describe('bench-fetch-success', () => {
  it('fetchRows success replaces rows, status success, errorMessage null', async () => {
    const store = createTableStore({ pageSize: 10 })
    store.getState().setRows(ROWS)
    const fetcher = async () => ([
      { id: 'n1', name: 'N1', score: 5 },
      { id: 'n2', name: 'N2', score: 15 },
    ])
    await store.getState().fetchRows(fetcher)
    const s = store.getState()
    expect(s.status).toBe('success')
    expect(s.errorMessage).toBeNull()
    expect(ids(s.rows as any[]).sort()).toEqual(['n1', 'n2'])
    expect(s.pageCount).toBe(1)
    expect((s.pageRows as any[]).length).toBe(2)
  })
})
"""
        _assert_passed(_run_driver(body), "async fetch success")

    def test_async_fetch_rejection_path(self):
        """L2: fetchRows rejection sets error state, keeps rows, never throws."""
        body = _PRELUDE + """
describe('bench-fetch-error', () => {
  it('fetchRows rejection sets error state without throwing', async () => {
    const store = createTableStore({ pageSize: 10 })
    store.getState().setRows(ROWS)
    const before = store.getState()
    const beforeIds = ids(before.rows as any[])
    const fetcher = async () => { throw new Error('boom network') }
    let threw = false
    try {
      await store.getState().fetchRows(fetcher)
    } catch (e) {
      threw = true
    }
    expect(threw).toBe(false)
    const s = store.getState()
    expect(s.status).toBe('error')
    expect(typeof s.errorMessage).toBe('string')
    expect((s.errorMessage as string).length).toBeGreaterThan(0)
    // rows unchanged
    expect(ids(s.rows as any[])).toEqual(beforeIds)
  })
})
"""
        _assert_passed(_run_driver(body), "async fetch rejection")

    def test_invalid_fetcher_guard(self):
        """L2: non-function fetcher sets error state, no async work, no throw."""
        body = _PRELUDE + """
describe('bench-guard', () => {
  it('invalid fetcher is guarded into error state', async () => {
    const store = createTableStore({ pageSize: 10 })
    store.getState().setRows(ROWS)
    const beforeIds = ids(store.getState().rows as any[])
    let threw = false
    try {
      // @ts-expect-error intentionally invalid
      await store.getState().fetchRows(42)
    } catch (e) {
      threw = true
    }
    expect(threw).toBe(false)
    const s = store.getState()
    expect(s.status).toBe('error')
    expect(typeof s.errorMessage).toBe('string')
    expect((s.errorMessage as string).length).toBeGreaterThan(0)
    // rows untouched
    expect(ids(s.rows as any[])).toEqual(beforeIds)
  })
})
"""
        _assert_passed(_run_driver(body), "invalid fetcher guard")

    def test_default_pagesize_and_handles(self):
        """L2: default pageSize is 10 and the vanilla handles exist."""
        body = _PRELUDE + """
describe('bench-defaults', () => {
  it('exposes getState/setState/subscribe and defaults pageSize to 10', () => {
    const store = createTableStore()
    expect(typeof store.getState).toBe('function')
    expect(typeof store.setState).toBe('function')
    expect(typeof store.subscribe).toBe('function')
    expect(store.getState().pageSize).toBe(10)
    store.getState().setRows(ROWS)
    const s = store.getState()
    // 5 rows / pageSize 10 -> single page holding all rows
    expect(s.pageCount).toBe(1)
    expect((s.pageRows as any[]).length).toBe(5)
  })
})
"""
        _assert_passed(_run_driver(body), "defaults + handles")
