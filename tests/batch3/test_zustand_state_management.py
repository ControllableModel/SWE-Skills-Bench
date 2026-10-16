"""Benchmark tests for the `zustand-state-management` skill (variant ext3).

Verifies the agent's implementation of a self-contained undo/redo HISTORY store
module built on top of zustand's framework-agnostic `createStore` (vanilla) API.

Source of truth: tasks/ext3/zustand-state-management.md. The task asks the agent
to create:
  - examples/history-store/historyStore.ts  (factory `createHistoryStore` + types)
  - tests/historyStore.test.ts              (the agent's own Vitest suite)

The store models a drawing canvas of shapes (`{ id, kind, x, y }`) with a
"present" exposing `shapes`, plus derived read-only `canUndo` / `canRedo`.
Mutating actions (addShape / moveShape / removeShape) push history and clear
redo; `undo()` / `redo()` walk the history stacks; an optional `options.limit`
caps the retained undo depth.

L1 checks: the deliverable files exist and are minimally well-formed, and the
agent's own suite passes via `pnpm vitest run tests/historyStore.test.ts`.

L2 checks: discriminative DYNAMIC EXECUTION. We DO NOT trust the agent's own
test file. Instead we write our OWN independent Vitest drivers into REPO_DIR/
tests/ that import the agent's `createHistoryStore` factory directly and exercise
the real runtime behavior (shape mutations, duplicate-id rejection, unknown-id
no-ops, undo/redo restoration, boundary no-ops, canUndo/canRedo correctness,
redo-stack invalidation after a post-undo mutation, and the history depth limit).
Each driver runs via the repo's native `pnpm vitest run` and we assert on
returncode.

A naive / hardcoded / "looks related" implementation — one that ignores history,
returns a fixed `canUndo`/`canRedo`, fails to clear the redo stack, or ignores
`options.limit` — fails these driver tests.
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
HISTORY_STORE = os.path.join(
    REPO_DIR, "examples", "history-store", "historyStore.ts"
)
AGENT_TEST = os.path.join(REPO_DIR, "tests", "historyStore.test.ts")

# Driver files we create under tests/ so vitest (dir: 'tests') picks them up.
# Each is removed in teardown. Use a unique tag to avoid clobbering anything.
_TAG = uuid.uuid4().hex[:8]
_DRIVER_BASENAME = f"_bench_history_driver_{_TAG}.test.ts"
DRIVER_PATH = os.path.join(REPO_DIR, "tests", _DRIVER_BASENAME)

VITEST_TIMEOUT = 600

# Relative import path from a file living in tests/ to the history store module.
_IMPORT = "../examples/history-store/historyStore"


def _pnpm_available():
    return shutil.which("pnpm") is not None


@pytest.fixture(scope="module", autouse=True)
def _prepare_deps():
    """Best-effort install of node deps before running native vitest."""
    if ensure_npm_dependencies is not None:
        try:
            ensure_npm_dependencies(REPO_DIR)
        except Exception:
            # The container image typically ships deps preinstalled; if npm
            # install fails (e.g. pnpm-only lockfile) fall back to a pnpm
            # install so the toolchain is usable.
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
    """Write an independent vitest driver file under tests/ and return path."""
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
    """Helper: write a driver, run it, clean up, return CompletedProcess."""
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


# A small TS prelude shared by drivers: helpers to read the shapes list out of
# the present in a layout-agnostic way (array or keyed object), and to look up
# a shape / its coordinates by id.
_PRELUDE = """
function shapesOf(s: any): any[] {
  const sh = s.shapes
  if (Array.isArray(sh)) return sh
  if (sh && typeof sh === 'object') return Object.values(sh)
  return []
}
function findShape(s: any, id: string): any {
  return shapesOf(s).find((x: any) => x && x.id === id)
}
"""


class TestZustandStateManagement:
    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------ L1
    def test_history_store_module_exists(self):
        """L1: examples/history-store/historyStore.ts exists and is non-trivial."""
        assert os.path.isfile(HISTORY_STORE), f"missing {HISTORY_STORE}"
        size = os.path.getsize(HISTORY_STORE)
        assert size > 200, f"historyStore.ts suspiciously small ({size} bytes)"

    def test_module_exports_factory(self):
        """L1: module declares an exported `createHistoryStore`."""
        with open(HISTORY_STORE) as fh:
            src = fh.read()
        assert re.search(
            r"export\b.*\bcreateHistoryStore\b", src
        ) or re.search(r"\bcreateHistoryStore\b", src), (
            "createHistoryStore not found in historyStore.ts"
        )

    def test_agent_test_suite_exists(self):
        """L1: the agent's own Vitest suite file exists and is non-trivial."""
        assert os.path.isfile(AGENT_TEST), f"missing {AGENT_TEST}"
        assert os.path.getsize(AGENT_TEST) > 200

    def test_agent_suite_passes(self):
        """L1/L2: the agent's own `tests/historyStore.test.ts` suite passes."""
        proc = _run_vitest("tests/historyStore.test.ts")
        _assert_passed(proc, "agent historyStore.test.ts suite")
        # The task requires at least 10 cases; verify vitest actually ran a
        # healthy number of tests rather than a single rubber-stamp.
        combined = (proc.stdout or "") + (proc.stderr or "")
        m = re.search(r"Tests\s+(\d+)\s+passed", combined)
        if m:
            assert int(m.group(1)) >= 10, (
                f"expected >=10 passing tests, parsed {m.group(1)}\n"
                f"{combined[-2000:]}"
            )

    # ------------------------------------------------------------------ L2
    def test_vanilla_handles_present(self):
        """L2: factory returns getState/setState/subscribe; present has shapes."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createHistoryStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-handles', () => {{
  it('exposes the standard vanilla handles and an empty present', () => {{
    const store: any = createHistoryStore()
    expect(typeof store.getState).toBe('function')
    expect(typeof store.setState).toBe('function')
    expect(typeof store.subscribe).toBe('function')
    const s = store.getState()
    expect(shapesOf(s).length).toBe(0)
    // nothing added yet: both history flags must be false
    expect(s.canUndo).toBe(false)
    expect(s.canRedo).toBe(false)
  }})
}})
"""
        _assert_passed(_run_driver(body), "vanilla handles + empty present")

    def test_add_move_remove_shapes(self):
        """L2: addShape/moveShape/removeShape mutate the present correctly."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createHistoryStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-mutations', () => {{
  it('adds, moves and removes shapes', () => {{
    const store: any = createHistoryStore()
    store.getState().addShape({{ id: 'a', kind: 'rect', x: 1, y: 2 }})
    store.getState().addShape({{ id: 'b', kind: 'circle', x: 5, y: 6 }})
    let s = store.getState()
    expect(shapesOf(s).length).toBe(2)
    expect(findShape(s, 'a').kind).toBe('rect')

    store.getState().moveShape('a', 10, 20)
    s = store.getState()
    const a = findShape(s, 'a')
    expect(a.x).toBe(10)
    expect(a.y).toBe(20)
    // moving 'a' must not disturb 'b'
    expect(findShape(s, 'b').x).toBe(5)

    store.getState().removeShape('b')
    s = store.getState()
    expect(shapesOf(s).length).toBe(1)
    expect(findShape(s, 'b')).toBeUndefined()
    expect(findShape(s, 'a')).toBeTruthy()
  }})
}})
"""
        _assert_passed(_run_driver(body), "add/move/remove shapes")

    def test_duplicate_id_rejected(self):
        """L2: addShape with an existing id is rejected; no state, no history."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createHistoryStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-dup', () => {{
  it('rejects a duplicate id without changing state or history', () => {{
    const store: any = createHistoryStore()
    store.getState().addShape({{ id: 'a', kind: 'rect', x: 0, y: 0 }})
    const before = store.getState()
    expect(before.canUndo).toBe(true)   // one real add happened
    // duplicate id: must be a no-op (no second shape, no extra history entry)
    expect(() => store.getState().addShape({{ id: 'a', kind: 'circle', x: 9, y: 9 }})).not.toThrow()
    const after = store.getState()
    expect(shapesOf(after).length).toBe(1)
    // original shape untouched (kind/coords unchanged)
    expect(findShape(after, 'a').kind).toBe('rect')
    expect(findShape(after, 'a').x).toBe(0)
    // since the duplicate add added no history entry, exactly one undo brings
    // us back to empty and there is nothing further to undo.
    store.getState().undo()
    const undone = store.getState()
    expect(shapesOf(undone).length).toBe(0)
    expect(undone.canUndo).toBe(false)
  }})
}})
"""
        _assert_passed(_run_driver(body), "duplicate id rejected")

    def test_unknown_id_noops(self):
        """L2: moveShape/removeShape on unknown ids are silent no-ops, no history."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createHistoryStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-noop', () => {{
  it('unknown ids are no-ops and add no history', () => {{
    const store: any = createHistoryStore()
    store.getState().addShape({{ id: 'a', kind: 'rect', x: 3, y: 4 }})
    const before = store.getState()
    expect(() => store.getState().moveShape('zzz', 1, 1)).not.toThrow()
    expect(() => store.getState().removeShape('zzz')).not.toThrow()
    const after = store.getState()
    expect(shapesOf(after).length).toBe(1)
    expect(findShape(after, 'a').x).toBe(3)
    expect(findShape(after, 'a').y).toBe(4)
    // no history was added by the no-ops: a single undo returns to empty and
    // then canUndo is false.
    store.getState().undo()
    const undone = store.getState()
    expect(shapesOf(undone).length).toBe(0)
    expect(undone.canUndo).toBe(false)
  }})
}})
"""
        _assert_passed(_run_driver(body), "unknown id no-op")

    def test_undo_restores_prior_present(self):
        """L2: undo restores the most recent previous present exactly."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createHistoryStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-undo', () => {{
  it('undo walks back through prior presents', () => {{
    const store: any = createHistoryStore()
    store.getState().addShape({{ id: 'a', kind: 'rect', x: 0, y: 0 }})
    store.getState().addShape({{ id: 'b', kind: 'circle', x: 1, y: 1 }})
    store.getState().moveShape('a', 7, 8)
    // present: 2 shapes, a at (7,8)
    expect(findShape(store.getState(), 'a').x).toBe(7)

    store.getState().undo()  // undo the move
    let s = store.getState()
    expect(findShape(s, 'a').x).toBe(0)
    expect(findShape(s, 'a').y).toBe(0)
    expect(shapesOf(s).length).toBe(2)

    store.getState().undo()  // undo adding b
    s = store.getState()
    expect(shapesOf(s).length).toBe(1)
    expect(findShape(s, 'b')).toBeUndefined()

    store.getState().undo()  // undo adding a -> empty
    s = store.getState()
    expect(shapesOf(s).length).toBe(0)
    expect(s.canUndo).toBe(false)
  }})
}})
"""
        _assert_passed(_run_driver(body), "undo restores prior present")

    def test_redo_reapplies_undone_present(self):
        """L2: redo re-applies the most recently undone present."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createHistoryStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-redo', () => {{
  it('redo re-applies an undone change', () => {{
    const store: any = createHistoryStore()
    store.getState().addShape({{ id: 'a', kind: 'rect', x: 0, y: 0 }})
    store.getState().addShape({{ id: 'b', kind: 'circle', x: 2, y: 3 }})
    // undo adding b
    store.getState().undo()
    let s = store.getState()
    expect(shapesOf(s).length).toBe(1)
    expect(s.canRedo).toBe(true)
    // redo brings b back
    store.getState().redo()
    s = store.getState()
    expect(shapesOf(s).length).toBe(2)
    const b = findShape(s, 'b')
    expect(b).toBeTruthy()
    expect(b.x).toBe(2)
    expect(b.y).toBe(3)
    expect(s.canRedo).toBe(false)
    expect(s.canUndo).toBe(true)
  }})
}})
"""
        _assert_passed(_run_driver(body), "redo re-applies undone present")

    def test_boundary_noops(self):
        """L2: undo with empty undo stack / redo with empty redo stack are no-ops."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createHistoryStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-boundary', () => {{
  it('undo/redo at the boundaries do nothing and do not throw', () => {{
    const store: any = createHistoryStore()
    // empty store: undo and redo are no-ops
    expect(() => store.getState().undo()).not.toThrow()
    expect(() => store.getState().redo()).not.toThrow()
    let s = store.getState()
    expect(shapesOf(s).length).toBe(0)
    expect(s.canUndo).toBe(false)
    expect(s.canRedo).toBe(false)

    store.getState().addShape({{ id: 'a', kind: 'rect', x: 0, y: 0 }})
    // redo at the leading edge (no undone future) is a no-op
    expect(() => store.getState().redo()).not.toThrow()
    s = store.getState()
    expect(shapesOf(s).length).toBe(1)
    expect(s.canRedo).toBe(false)

    // undo back to empty, then a second undo is a no-op
    store.getState().undo()
    expect(() => store.getState().undo()).not.toThrow()
    s = store.getState()
    expect(shapesOf(s).length).toBe(0)
    expect(s.canUndo).toBe(false)
  }})
}})
"""
        _assert_passed(_run_driver(body), "boundary no-ops")

    def test_can_undo_can_redo_flags(self):
        """L2: canUndo/canRedo track the undo/redo stack emptiness exactly."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createHistoryStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-flags', () => {{
  it('canUndo/canRedo reflect stack state through a sequence', () => {{
    const store: any = createHistoryStore()
    expect(store.getState().canUndo).toBe(false)
    expect(store.getState().canRedo).toBe(false)

    store.getState().addShape({{ id: 'a', kind: 'rect', x: 0, y: 0 }})
    expect(store.getState().canUndo).toBe(true)
    expect(store.getState().canRedo).toBe(false)

    store.getState().addShape({{ id: 'b', kind: 'circle', x: 1, y: 1 }})
    expect(store.getState().canUndo).toBe(true)
    expect(store.getState().canRedo).toBe(false)

    store.getState().undo()
    expect(store.getState().canUndo).toBe(true)   // still 'a' add to undo
    expect(store.getState().canRedo).toBe(true)   // 'b' add can be redone

    store.getState().undo()
    expect(store.getState().canUndo).toBe(false)  // back to empty
    expect(store.getState().canRedo).toBe(true)

    store.getState().redo()
    expect(store.getState().canUndo).toBe(true)
    expect(store.getState().canRedo).toBe(true)
  }})
}})
"""
        _assert_passed(_run_driver(body), "canUndo/canRedo flags")

    def test_mutation_after_undo_clears_redo(self):
        """L2: a mutation after undo discards the redo future (canRedo -> false)."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createHistoryStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-clear-redo', () => {{
  it('mutating after an undo clears the redo stack', () => {{
    const store: any = createHistoryStore()
    store.getState().addShape({{ id: 'a', kind: 'rect', x: 0, y: 0 }})
    store.getState().addShape({{ id: 'b', kind: 'circle', x: 1, y: 1 }})
    store.getState().undo()  // drop b, b-add now redoable
    expect(store.getState().canRedo).toBe(true)

    // a fresh mutation must invalidate the redo future
    store.getState().addShape({{ id: 'c', kind: 'rect', x: 9, y: 9 }})
    let s = store.getState()
    expect(s.canRedo).toBe(false)
    // present should hold a and c, NOT b
    expect(findShape(s, 'a')).toBeTruthy()
    expect(findShape(s, 'c')).toBeTruthy()
    expect(findShape(s, 'b')).toBeUndefined()

    // redo is now a no-op: b never comes back
    store.getState().redo()
    s = store.getState()
    expect(findShape(s, 'b')).toBeUndefined()
    expect(shapesOf(s).length).toBe(2)
  }})
}})
"""
        _assert_passed(_run_driver(body), "mutation after undo clears redo")

    def test_history_depth_limit(self):
        """L2: options.limit caps the number of consecutive undo calls."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createHistoryStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-limit', () => {{
  it('limit caps retained undo depth', () => {{
    const limit = 3
    const store: any = createHistoryStore({{ limit }})
    // perform 6 mutations (well over the limit)
    for (let i = 0; i < 6; i++) {{
      store.getState().addShape({{ id: 's' + i, kind: 'rect', x: i, y: i }})
    }}
    expect(shapesOf(store.getState()).length).toBe(6)

    // undo as many times as possible; with a limit of 3 we can only undo 3x.
    let undos = 0
    for (let i = 0; i < 20; i++) {{
      const before = shapesOf(store.getState()).length
      const couldUndo = store.getState().canUndo
      store.getState().undo()
      const after = shapesOf(store.getState()).length
      if (couldUndo && after !== before) {{
        undos++
      }} else {{
        break
      }}
    }}
    expect(undos).toBe(limit)
    // exactly `limit` shapes were rolled back: 6 -> 3 remain
    expect(shapesOf(store.getState()).length).toBe(6 - limit)
    expect(store.getState().canUndo).toBe(false)
  }})

  it('unbounded history when no limit is given', () => {{
    const store: any = createHistoryStore()
    for (let i = 0; i < 8; i++) {{
      store.getState().addShape({{ id: 'u' + i, kind: 'circle', x: i, y: 0 }})
    }}
    let undos = 0
    while (store.getState().canUndo) {{
      store.getState().undo()
      undos++
      if (undos > 100) break
    }}
    expect(undos).toBe(8)
    expect(shapesOf(store.getState()).length).toBe(0)
  }})
}})
"""
        _assert_passed(_run_driver(body), "history depth limit")
