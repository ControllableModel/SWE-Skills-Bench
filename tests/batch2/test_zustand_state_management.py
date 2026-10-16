"""Benchmark tests for the `zustand-state-management` skill (variant ext2).

Verifies the agent's implementation of a self-contained TODO-LIST store module
built on top of zustand's public vanilla + middleware API.

Source of truth: tasks/ext2/zustand-state-management.md. The task asks the agent
to create:
  - examples/todo-store/todoStore.ts  (factory `createTodoStore` + types)
  - tests/todoStore.test.ts           (the agent's own Vitest suite)

This is a DIFFERENT task than ext1 (which built a cart-store with async loading
and persistence). Here the domain is a todo list with: per-id todos, a
`filter: 'all' | 'active' | 'completed'`, derived `activeCount` /
`completedCount` / `visibleTodos`, synchronous actions (addTodo / toggleTodo /
removeTodo / setFilter / clearCompleted), and selector-scoped subscriptions
(including `fireImmediately`).

L1 checks: the deliverable files exist and are minimally well-formed, and the
agent's own suite passes via `pnpm vitest run tests/todoStore.test.ts`.

L2 checks: discriminative DYNAMIC EXECUTION. We DO NOT trust the agent's own
test file. Instead we write INDEPENDENT Vitest drivers into REPO_DIR/tests/ that
import the agent's `createTodoStore` factory directly and exercise the real
runtime behavior (adding, blank-title rejection, toggling, removing, unknown-id
no-ops, filter-scoped visibleTodos, clearCompleted, the activeCount/
completedCount/visibleTodos no-drift invariant across a long mutation sequence,
a selector subscription firing only on the relevant slice change, the
fireImmediately behavior, and that a filter-only change does NOT fire an
activeCount subscription). Each driver runs via the repo's native
`pnpm vitest run` and we assert on returncode.

A naive / hardcoded / "looks related" implementation (e.g. one that does not
reject blank titles, lets unknown ids mutate, drifts the derived counts, or
fires selector listeners on every change) fails these driver tests.
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
TODO_STORE = os.path.join(REPO_DIR, "examples", "todo-store", "todoStore.ts")
AGENT_TEST = os.path.join(REPO_DIR, "tests", "todoStore.test.ts")

# Driver files we create under tests/ so vitest (dir: 'tests') picks them up.
# Each is removed in teardown. Use a unique tag to avoid clobbering anything.
_TAG = uuid.uuid4().hex[:8]
_DRIVER_BASENAME = f"_bench_todo_driver_{_TAG}.test.ts"
DRIVER_PATH = os.path.join(REPO_DIR, "tests", _DRIVER_BASENAME)

VITEST_TIMEOUT = 600

# Relative import path from a file living in tests/ to the todo store module.
_IMPORT = "../examples/todo-store/todoStore"


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


# A small shared TS preamble that normalizes the todos collection (the doc says
# it is "keyed by id" but allows either an array or an object map) and exposes
# helpers for independent recomputation of the derived fields.
_PRELUDE = """
function todoList(s: any): any[] {
  const t = s.todos
  return Array.isArray(t) ? t : Object.values(t)
}
function recompute(s: any) {
  const list = todoList(s)
  const active = list.filter((x: any) => x.completed === false).length
  const completed = list.filter((x: any) => x.completed === true).length
  let visible = list
  if (s.filter === 'active') visible = list.filter((x: any) => x.completed === false)
  else if (s.filter === 'completed') visible = list.filter((x: any) => x.completed === true)
  return { active, completed, visibleLen: visible.length }
}
"""


class TestZustandStateManagement:
    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------ L1
    def test_todo_store_module_exists(self):
        """L1: examples/todo-store/todoStore.ts exists and is non-trivial."""
        assert os.path.isfile(TODO_STORE), f"missing {TODO_STORE}"
        size = os.path.getsize(TODO_STORE)
        assert size > 200, f"todoStore.ts suspiciously small ({size} bytes)"

    def test_module_exports_factory(self):
        """L1: module declares an exported `createTodoStore`."""
        with open(TODO_STORE) as fh:
            src = fh.read()
        assert re.search(r"export\b.*\bcreateTodoStore\b", src) or re.search(
            r"\bcreateTodoStore\b", src
        ), "createTodoStore not found in todoStore.ts"

    def test_agent_test_suite_exists(self):
        """L1: the agent's own Vitest suite file exists and is non-trivial."""
        assert os.path.isfile(AGENT_TEST), f"missing {AGENT_TEST}"
        assert os.path.getsize(AGENT_TEST) > 200

    def test_agent_suite_passes(self):
        """L1/L2: the agent's own `tests/todoStore.test.ts` suite passes
        with at least 10 cases (the task mandates >=10)."""
        proc = _run_vitest("tests/todoStore.test.ts")
        _assert_passed(proc, "agent todoStore.test.ts suite")
        combined = (proc.stdout or "") + (proc.stderr or "")
        m = re.search(r"Tests\s+(\d+)\s+passed", combined)
        if m:
            assert int(m.group(1)) >= 10, (
                f"expected >=10 passing tests, parsed {m.group(1)}\n"
                f"{combined[-2000:]}"
            )

    # ------------------------------------------------------------------ L2
    def test_add_assigns_unique_ids_and_counts(self):
        """L2: addTodo appends incomplete todos with unique ids; activeCount
        and completedCount reflect them; visibleTodos == all under 'all'."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createTodoStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-add', () => {{
  it('adds incomplete todos with unique ids', () => {{
    const store = createTodoStore()
    store.getState().addTodo('Buy milk')
    store.getState().addTodo('Walk dog')
    const s = store.getState()
    const list = todoList(s)
    expect(list.length).toBe(2)
    const ids = list.map((x: any) => x.id)
    expect(new Set(ids).size).toBe(2)            // unique ids
    expect(list.every((x: any) => x.completed === false)).toBe(true)
    expect(list.every((x: any) => typeof x.id === 'string' && x.id.length > 0)).toBe(true)
    expect(list.map((x: any) => x.title).sort()).toEqual(['Buy milk', 'Walk dog'])
    expect(s.activeCount).toBe(2)
    expect(s.completedCount).toBe(0)
    // default filter is 'all' -> visibleTodos is everything
    const vis = s.visibleTodos
    const visList = Array.isArray(vis) ? vis : Object.values(vis)
    expect(visList.length).toBe(2)
  }})
}})
"""
        _assert_passed(_run_driver(body), "add + unique ids + counts")

    def test_blank_title_rejected(self):
        """L2: addTodo with a blank/whitespace-only title is rejected (no
        state change). A naive impl that appends unconditionally fails here."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createTodoStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-blank', () => {{
  it('rejects blank and whitespace-only titles', () => {{
    const store = createTodoStore()
    store.getState().addTodo('real')
    const baseline = todoList(store.getState()).length
    expect(baseline).toBe(1)
    expect(() => store.getState().addTodo('')).not.toThrow()
    expect(() => store.getState().addTodo('   ')).not.toThrow()
    expect(() => store.getState().addTodo('\\t\\n  ')).not.toThrow()
    const s = store.getState()
    expect(todoList(s).length).toBe(1)          // nothing added
    expect(s.activeCount).toBe(1)
  }})
}})
"""
        _assert_passed(_run_driver(body), "blank title rejected")

    def test_toggle_flips_completed_and_unknown_noop(self):
        """L2: toggleTodo flips completed for a matching id and updates the
        derived counts; an unknown id is a silent no-op."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createTodoStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-toggle', () => {{
  it('toggles a todo and ignores unknown ids', () => {{
    const store = createTodoStore()
    store.getState().addTodo('A')
    store.getState().addTodo('B')
    const first = todoList(store.getState())[0]
    store.getState().toggleTodo(first.id)
    let s = store.getState()
    const updated = todoList(s).find((x: any) => x.id === first.id)
    expect(updated.completed).toBe(true)
    expect(s.activeCount).toBe(1)
    expect(s.completedCount).toBe(1)
    // toggle back
    store.getState().toggleTodo(first.id)
    s = store.getState()
    expect(todoList(s).find((x: any) => x.id === first.id).completed).toBe(false)
    expect(s.activeCount).toBe(2)
    expect(s.completedCount).toBe(0)
    // unknown id is a no-op (no throw, no count change)
    expect(() => store.getState().toggleTodo('does-not-exist')).not.toThrow()
    s = store.getState()
    expect(s.activeCount).toBe(2)
    expect(s.completedCount).toBe(0)
    expect(todoList(s).length).toBe(2)
  }})
}})
"""
        _assert_passed(_run_driver(body), "toggle + unknown no-op")

    def test_remove_and_unknown_noop(self):
        """L2: removeTodo drops the matching row and updates counts; unknown
        id is a no-op."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createTodoStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-remove', () => {{
  it('removes a todo and ignores unknown ids', () => {{
    const store = createTodoStore()
    store.getState().addTodo('A')
    store.getState().addTodo('B')
    store.getState().addTodo('C')
    const list0 = todoList(store.getState())
    const target = list0[1].id
    store.getState().removeTodo(target)
    let s = store.getState()
    const list = todoList(s)
    expect(list.length).toBe(2)
    expect(list.find((x: any) => x.id === target)).toBeUndefined()
    expect(s.activeCount).toBe(2)
    // unknown removal is a no-op
    expect(() => store.getState().removeTodo('nope')).not.toThrow()
    s = store.getState()
    expect(todoList(s).length).toBe(2)
    expect(s.activeCount).toBe(2)
  }})
}})
"""
        _assert_passed(_run_driver(body), "remove + unknown no-op")

    def test_set_filter_scopes_visible_todos(self):
        """L2: setFilter changes the active filter and recomputes visibleTodos
        to exactly the matching subset ('active' -> incomplete, 'completed' ->
        complete, 'all' -> everything)."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createTodoStore }} from '{_IMPORT}'
{_PRELUDE}
function visIds(s: any): string[] {{
  const v = s.visibleTodos
  const list = Array.isArray(v) ? v : Object.values(v)
  return list.map((x: any) => x.id).sort()
}}
describe('bench-filter', () => {{
  it('visibleTodos matches the active filter', () => {{
    const store = createTodoStore()
    store.getState().addTodo('keep-active')
    store.getState().addTodo('will-complete')
    const all = todoList(store.getState())
    const activeId = all.find((x: any) => x.title === 'keep-active').id
    const completeId = all.find((x: any) => x.title === 'will-complete').id
    store.getState().toggleTodo(completeId)   // mark one completed

    store.getState().setFilter('all')
    let s = store.getState()
    expect(s.filter).toBe('all')
    expect(visIds(s)).toEqual([activeId, completeId].sort())

    store.getState().setFilter('active')
    s = store.getState()
    expect(s.filter).toBe('active')
    expect(visIds(s)).toEqual([activeId])

    store.getState().setFilter('completed')
    s = store.getState()
    expect(s.filter).toBe('completed')
    expect(visIds(s)).toEqual([completeId])
  }})
}})
"""
        _assert_passed(_run_driver(body), "setFilter scopes visibleTodos")

    def test_clear_completed(self):
        """L2: clearCompleted removes only completed todos, leaving active
        ones and zeroing completedCount."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createTodoStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-clear', () => {{
  it('clearCompleted drops completed only', () => {{
    const store = createTodoStore()
    store.getState().addTodo('a')
    store.getState().addTodo('b')
    store.getState().addTodo('c')
    const list = todoList(store.getState())
    store.getState().toggleTodo(list[0].id)   // complete a
    store.getState().toggleTodo(list[2].id)   // complete c
    let s = store.getState()
    expect(s.completedCount).toBe(2)
    expect(s.activeCount).toBe(1)
    store.getState().clearCompleted()
    s = store.getState()
    const remaining = todoList(s)
    expect(remaining.length).toBe(1)
    expect(remaining[0].title).toBe('b')
    expect(remaining.every((x: any) => x.completed === false)).toBe(true)
    expect(s.completedCount).toBe(0)
    expect(s.activeCount).toBe(1)
  }})
}})
"""
        _assert_passed(_run_driver(body), "clearCompleted")

    def test_derived_fields_never_drift(self):
        """L2: after a long mutation sequence the stored activeCount,
        completedCount and visibleTodos length always equal an independent
        recomputation from the current todos + filter."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createTodoStore }} from '{_IMPORT}'
{_PRELUDE}
function visLen(s: any): number {{
  const v = s.visibleTodos
  const list = Array.isArray(v) ? v : Object.values(v)
  return list.length
}}
describe('bench-drift', () => {{
  it('derived fields equal an independent recompute after each op', () => {{
    const store = createTodoStore()
    const ops: Array<() => void> = [
      () => store.getState().addTodo('t1'),
      () => store.getState().addTodo('t2'),
      () => store.getState().addTodo('t3'),
      () => store.getState().toggleTodo(todoList(store.getState())[0].id),
      () => store.getState().setFilter('active'),
      () => store.getState().toggleTodo(todoList(store.getState())[1].id),
      () => store.getState().setFilter('completed'),
      () => store.getState().removeTodo(todoList(store.getState())[2].id),
      () => store.getState().addTodo('t4'),
      () => store.getState().setFilter('all'),
      () => store.getState().clearCompleted(),
      () => store.getState().setFilter('active'),
    ]
    for (const op of ops) {{
      op()
      const s = store.getState()
      const r = recompute(s)
      expect(s.activeCount).toBe(r.active)
      expect(s.completedCount).toBe(r.completed)
      expect(visLen(s)).toBe(r.visibleLen)
    }}
  }})
}})
"""
        _assert_passed(_run_driver(body), "no-drift invariant")

    def test_selector_subscription_fires_only_on_slice_change(self):
        """L2: an activeCount-selector subscriber fires when (and only when)
        activeCount changes, and receives (current, previous). It must NOT fire
        when only the filter changes (activeCount unchanged)."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createTodoStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-selector', () => {{
  it('activeCount subscriber ignores filter-only changes', () => {{
    const store = createTodoStore()
    const calls: Array<[number, number]> = []
    const unsub = store.subscribe(
      (s: any) => s.activeCount,
      (cur: number, prev: number) => {{ calls.push([cur, prev]) }},
    )
    // adding an active todo changes activeCount 0 -> 1
    store.getState().addTodo('one')
    expect(calls.length).toBe(1)
    expect(calls[0][0]).toBe(1)
    expect(calls[0][1]).toBe(0)
    // changing ONLY the filter leaves activeCount the same -> no fire
    store.getState().setFilter('completed')
    expect(calls.length).toBe(1)
    store.getState().setFilter('all')
    expect(calls.length).toBe(1)
    // adding another active todo changes activeCount 1 -> 2
    store.getState().addTodo('two')
    expect(calls.length).toBe(2)
    expect(calls[1][0]).toBe(2)
    expect(calls[1][1]).toBe(1)
    unsub()
    // after unsubscribe, no further notifications
    store.getState().addTodo('three')
    expect(calls.length).toBe(2)
  }})
}})
"""
        _assert_passed(_run_driver(body), "activeCount selector subscription")

    def test_fire_immediately(self):
        """L2: a selector subscription with { fireImmediately: true } invokes
        the listener once synchronously at subscription time with the current
        slice, and then on subsequent slice changes."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createTodoStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-fireimmediately', () => {{
  it('fireImmediately delivers the current slice synchronously', () => {{
    const store = createTodoStore()
    store.getState().addTodo('a')
    store.getState().addTodo('b')   // activeCount is now 2
    const seen: number[] = []
    const unsub = store.subscribe(
      (s: any) => s.activeCount,
      (cur: number) => {{ seen.push(cur) }},
      {{ fireImmediately: true }},
    )
    // immediate synchronous call with current activeCount (2)
    expect(seen.length).toBe(1)
    expect(seen[0]).toBe(2)
    // filter-only change must not fire (activeCount unchanged)
    store.getState().setFilter('active')
    expect(seen.length).toBe(1)
    // completing a todo lowers activeCount 2 -> 1 and fires
    store.getState().toggleTodo(todoList(store.getState())[0].id)
    expect(seen.length).toBe(2)
    expect(seen[1]).toBe(1)
    unsub()
  }})
}})
"""
        _assert_passed(_run_driver(body), "fireImmediately")

    def test_completed_count_selector_independent_of_active(self):
        """L2: a completedCount-selector subscriber fires only on
        completedCount changes (e.g. toggling) and not when an unrelated active
        todo is merely added then removed leaving completedCount unchanged."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createTodoStore }} from '{_IMPORT}'
{_PRELUDE}
describe('bench-completed-selector', () => {{
  it('completedCount subscriber tracks only completedCount', () => {{
    const store = createTodoStore()
    const calls: number[] = []
    const unsub = store.subscribe(
      (s: any) => s.completedCount,
      (cur: number) => {{ calls.push(cur) }},
    )
    // add then remove an active todo: completedCount stays 0 throughout
    store.getState().addTodo('temp')
    const tempId = todoList(store.getState())[0].id
    store.getState().removeTodo(tempId)
    expect(calls.length).toBe(0)
    // now add a todo and complete it -> completedCount 0 -> 1
    store.getState().addTodo('done-me')
    const id = todoList(store.getState())[0].id
    store.getState().toggleTodo(id)
    expect(calls.length).toBe(1)
    expect(calls[0]).toBe(1)
    // clearCompleted lowers completedCount 1 -> 0
    store.getState().clearCompleted()
    expect(calls.length).toBe(2)
    expect(calls[1]).toBe(0)
    unsub()
  }})
}})
"""
        _assert_passed(_run_driver(body), "completedCount selector")
