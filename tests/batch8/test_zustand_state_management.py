"""Benchmark tests for the `zustand-state-management` skill (variant ext8).

Verifies the agent's implementation of a self-contained notification/toast
QUEUE store module built on top of zustand's public vanilla + middleware API.

Source of truth: tasks/ext8/zustand-state-management.md. The task asks the
agent to create:
  - examples/notifications-store/notificationsStore.ts
        (factory `createNotificationsStore` + TypeScript types)
  - tests/notificationsStore.test.ts   (the agent's own Vitest suite)

The store returns the standard vanilla handles (getState/setState/subscribe,
with subscribe also accepting a selector form), an ordered `notifications`
queue (oldest-first, unique ids), and derived read-only fields `count`,
`hasErrors`, and `visible` (the tail of size `maxVisible`, default 3). Actions:
`push`, `dismiss`, `dismissAll`, with an optional `capacity` cap that evicts
the oldest entries on overflow. Selector subscriptions fire only on the
subscribed slice changing, and support `fireImmediately`.

L1 checks: the deliverable files exist and are minimally well-formed, and the
agent's own suite passes via `pnpm vitest run tests/notificationsStore.test.ts`.

L2 checks: discriminative DYNAMIC EXECUTION. We DO NOT trust the agent's own
test file. Instead we write INDEPENDENT Vitest drivers into REPO_DIR/tests/
that import the agent's `createNotificationsStore` factory directly and
exercise the real runtime behavior (ordered append, duplicate-id handling,
dismiss / dismiss-unknown no-op, dismissAll, count/hasErrors correctness,
`visible` tail, `capacity` eviction, selector-scoped subscriptions for `count`
and the `hasErrors` boolean flip, and `fireImmediately`). Each driver runs via
the repo's native `pnpm vitest run` and we assert on returncode.

A naive / hardcoded / "looks related" implementation (e.g. one that ignores
`capacity`, returns the whole queue for `visible`, fires selector listeners on
every change, or lets derived fields drift) MUST fail these driver tests.
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
NOTIF_STORE = os.path.join(
    REPO_DIR, "examples", "notifications-store", "notificationsStore.ts"
)
AGENT_TEST = os.path.join(REPO_DIR, "tests", "notificationsStore.test.ts")

# Driver files we create under tests/ so vitest (dir: 'tests') picks them up.
# Each is removed in teardown. Use a unique tag to avoid clobbering anything.
_TAG = uuid.uuid4().hex[:8]
_DRIVER_BASENAME = f"_bench_notif_driver_{_TAG}.test.ts"
DRIVER_PATH = os.path.join(REPO_DIR, "tests", _DRIVER_BASENAME)

VITEST_TIMEOUT = 600

# Relative import path from a file living in tests/ to the notifications module.
_IMPORT = "../examples/notifications-store/notificationsStore"


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


class TestZustandStateManagement:
    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------ L1
    def test_notifications_store_module_exists(self):
        """L1: examples/notifications-store/notificationsStore.ts exists."""
        assert os.path.isfile(NOTIF_STORE), f"missing {NOTIF_STORE}"
        size = os.path.getsize(NOTIF_STORE)
        assert size > 200, f"notificationsStore.ts suspiciously small ({size} bytes)"

    def test_module_exports_factory(self):
        """L1: module declares an exported `createNotificationsStore`."""
        with open(NOTIF_STORE) as fh:
            src = fh.read()
        assert re.search(
            r"export\b.*\bcreateNotificationsStore\b", src
        ) or re.search(
            r"\bcreateNotificationsStore\b", src
        ), "createNotificationsStore not found in notificationsStore.ts"

    def test_agent_test_suite_exists(self):
        """L1: the agent's own Vitest suite file exists and is non-trivial."""
        assert os.path.isfile(AGENT_TEST), f"missing {AGENT_TEST}"
        assert os.path.getsize(AGENT_TEST) > 200

    def test_agent_suite_passes(self):
        """L1/L2: the agent's own `tests/notificationsStore.test.ts` passes."""
        proc = _run_vitest("tests/notificationsStore.test.ts")
        _assert_passed(proc, "agent notificationsStore.test.ts suite")
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
    def test_push_appends_in_order(self):
        """L2: push appends oldest-first and exposes vanilla handles."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createNotificationsStore }} from '{_IMPORT}'

describe('bench-push-order', () => {{
  it('appends notifications in insertion order', () => {{
    const store = createNotificationsStore()
    expect(typeof store.getState).toBe('function')
    expect(typeof store.setState).toBe('function')
    expect(typeof store.subscribe).toBe('function')
    store.getState().push({{ id: 'a', message: 'first', level: 'info' }})
    store.getState().push({{ id: 'b', message: 'second', level: 'warning' }})
    store.getState().push({{ id: 'c', message: 'third', level: 'info' }})
    const s = store.getState()
    expect(s.notifications.map((n: any) => n.id)).toEqual(['a', 'b', 'c'])
    expect(s.notifications[0].message).toBe('first')
    expect(s.count).toBe(3)
  }})
}})
"""
        _assert_passed(_run_driver(body), "push appends in order")

    def test_duplicate_id_handling(self):
        """L2: pushing a duplicate id does not create two same-id rows."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createNotificationsStore }} from '{_IMPORT}'

describe('bench-dup', () => {{
  it('keeps ids unique in the queue', () => {{
    const store = createNotificationsStore()
    store.getState().push({{ id: 'a', message: 'one', level: 'info' }})
    store.getState().push({{ id: 'a', message: 'again', level: 'info' }})
    const s = store.getState()
    const aRows = s.notifications.filter((n: any) => n.id === 'a')
    expect(aRows.length).toBe(1)
    // count must reflect a queue with no duplicate-id rows
    const ids = s.notifications.map((n: any) => n.id)
    expect(new Set(ids).size).toBe(ids.length)
  }})
}})
"""
        _assert_passed(_run_driver(body), "duplicate id handling")

    def test_dismiss_removes_and_unknown_is_noop(self):
        """L2: dismiss(id) removes a row; an unknown id is a silent no-op."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createNotificationsStore }} from '{_IMPORT}'

describe('bench-dismiss', () => {{
  it('dismiss removes matching id; unknown id is a no-op', () => {{
    const store = createNotificationsStore()
    store.getState().push({{ id: 'a', message: 'A', level: 'info' }})
    store.getState().push({{ id: 'b', message: 'B', level: 'error' }})
    store.getState().push({{ id: 'c', message: 'C', level: 'info' }})
    store.getState().dismiss('b')
    let s = store.getState()
    expect(s.notifications.map((n: any) => n.id)).toEqual(['a', 'c'])
    expect(s.count).toBe(2)
    expect(s.hasErrors).toBe(false)
    // unknown id no-op
    const before = store.getState().count
    expect(() => store.getState().dismiss('zzz')).not.toThrow()
    s = store.getState()
    expect(s.count).toBe(before)
    expect(s.notifications.map((n: any) => n.id)).toEqual(['a', 'c'])
  }})
}})
"""
        _assert_passed(_run_driver(body), "dismiss + unknown no-op")

    def test_dismiss_all_clears(self):
        """L2: dismissAll empties queue and resets all derived fields."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createNotificationsStore }} from '{_IMPORT}'

describe('bench-dismiss-all', () => {{
  it('dismissAll resets count, hasErrors, visible', () => {{
    const store = createNotificationsStore()
    store.getState().push({{ id: 'a', message: 'A', level: 'error' }})
    store.getState().push({{ id: 'b', message: 'B', level: 'info' }})
    expect(store.getState().count).toBe(2)
    expect(store.getState().hasErrors).toBe(true)
    store.getState().dismissAll()
    const s = store.getState()
    expect(s.notifications.length).toBe(0)
    expect(s.count).toBe(0)
    expect(s.hasErrors).toBe(false)
    expect(s.visible).toEqual([])
  }})
}})
"""
        _assert_passed(_run_driver(body), "dismissAll clears")

    def test_count_and_haserrors_correctness(self):
        """L2: count and hasErrors track a sequence of mutations exactly."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createNotificationsStore }} from '{_IMPORT}'

describe('bench-count-haserrors', () => {{
  it('count and hasErrors stay correct across mutations', () => {{
    const store = createNotificationsStore()
    expect(store.getState().count).toBe(0)
    expect(store.getState().hasErrors).toBe(false)

    store.getState().push({{ id: 'a', message: 'A', level: 'info' }})
    expect(store.getState().count).toBe(1)
    expect(store.getState().hasErrors).toBe(false)

    store.getState().push({{ id: 'b', message: 'B', level: 'error' }})
    expect(store.getState().count).toBe(2)
    expect(store.getState().hasErrors).toBe(true)

    store.getState().push({{ id: 'c', message: 'C', level: 'warning' }})
    expect(store.getState().count).toBe(3)
    expect(store.getState().hasErrors).toBe(true)

    // removing the only error flips hasErrors back to false
    store.getState().dismiss('b')
    expect(store.getState().count).toBe(2)
    expect(store.getState().hasErrors).toBe(false)
  }})
}})
"""
        _assert_passed(_run_driver(body), "count + hasErrors correctness")

    def test_visible_is_tail_of_max_visible(self):
        """L2: visible is the tail of size maxVisible (default 3, configurable)."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createNotificationsStore }} from '{_IMPORT}'

describe('bench-visible', () => {{
  it('default maxVisible=3 returns the 3 most recent', () => {{
    const store = createNotificationsStore()
    for (const id of ['a', 'b', 'c', 'd', 'e']) {{
      store.getState().push({{ id, message: id, level: 'info' }})
    }}
    const s = store.getState()
    expect(s.count).toBe(5)
    expect(s.visible.map((n: any) => n.id)).toEqual(['c', 'd', 'e'])
  }})

  it('configurable maxVisible controls the tail size', () => {{
    const store = createNotificationsStore({{ maxVisible: 2 }})
    for (const id of ['a', 'b', 'c', 'd']) {{
      store.getState().push({{ id, message: id, level: 'info' }})
    }}
    const s = store.getState()
    expect(s.visible.map((n: any) => n.id)).toEqual(['c', 'd'])
  }})

  it('fewer items than maxVisible returns the whole queue', () => {{
    const store = createNotificationsStore({{ maxVisible: 5 }})
    store.getState().push({{ id: 'x', message: 'x', level: 'info' }})
    store.getState().push({{ id: 'y', message: 'y', level: 'info' }})
    expect(store.getState().visible.map((n: any) => n.id)).toEqual(['x', 'y'])
  }})
}})
"""
        _assert_passed(_run_driver(body), "visible tail = maxVisible")

    def test_capacity_evicts_oldest(self):
        """L2: capacity caps queue length, evicting oldest from the front."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createNotificationsStore }} from '{_IMPORT}'

describe('bench-capacity', () => {{
  it('queue never exceeds capacity; oldest are evicted', () => {{
    const store = createNotificationsStore({{ capacity: 3 }})
    for (const id of ['a', 'b', 'c', 'd', 'e']) {{
      store.getState().push({{ id, message: id, level: 'info' }})
    }}
    const s = store.getState()
    // only the 3 newest survive, oldest-first order preserved
    expect(s.notifications.map((n: any) => n.id)).toEqual(['c', 'd', 'e'])
    expect(s.count).toBe(3)
    expect(s.notifications.length).toBeLessThanOrEqual(3)
  }})

  it('eviction updates hasErrors when an evicted error leaves the queue', () => {{
    const store = createNotificationsStore({{ capacity: 2 }})
    store.getState().push({{ id: 'err', message: 'boom', level: 'error' }})
    expect(store.getState().hasErrors).toBe(true)
    store.getState().push({{ id: 'a', message: 'A', level: 'info' }})
    store.getState().push({{ id: 'b', message: 'B', level: 'info' }})
    const s = store.getState()
    // 'err' has been evicted (capacity 2): only a,b remain, no errors
    expect(s.notifications.map((n: any) => n.id)).toEqual(['a', 'b'])
    expect(s.hasErrors).toBe(false)
    expect(s.count).toBe(2)
  }})

  it('unbounded when capacity omitted', () => {{
    const store = createNotificationsStore()
    for (let i = 0; i < 10; i++) {{
      store.getState().push({{ id: 'n' + i, message: 'm', level: 'info' }})
    }}
    expect(store.getState().count).toBe(10)
  }})
}})
"""
        _assert_passed(_run_driver(body), "capacity eviction")

    def test_derived_fields_never_drift(self):
        """L2: count/hasErrors/visible always equal an independent recompute."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createNotificationsStore }} from '{_IMPORT}'

const MAXV = 3
function recompute(notifs: any[]) {{
  return {{
    count: notifs.length,
    hasErrors: notifs.some((n) => n.level === 'error'),
    visibleIds: notifs.slice(Math.max(0, notifs.length - MAXV)).map((n) => n.id),
  }}
}}

describe('bench-drift', () => {{
  it('derived fields match recompute after every op', () => {{
    const store = createNotificationsStore({{ maxVisible: MAXV }})
    const ops: Array<() => void> = [
      () => store.getState().push({{ id: 'a', message: 'A', level: 'info' }}),
      () => store.getState().push({{ id: 'b', message: 'B', level: 'error' }}),
      () => store.getState().push({{ id: 'c', message: 'C', level: 'warning' }}),
      () => store.getState().push({{ id: 'd', message: 'D', level: 'info' }}),
      () => store.getState().dismiss('b'),
      () => store.getState().push({{ id: 'e', message: 'E', level: 'error' }}),
      () => store.getState().dismiss('zzz'),
      () => store.getState().push({{ id: 'f', message: 'F', level: 'info' }}),
    ]
    for (const op of ops) {{
      op()
      const s = store.getState()
      const r = recompute(s.notifications)
      expect(s.count).toBe(r.count)
      expect(s.hasErrors).toBe(r.hasErrors)
      expect(s.visible.map((n: any) => n.id)).toEqual(r.visibleIds)
    }}
  }})
}})
"""
        _assert_passed(_run_driver(body), "no-drift invariant")

    def test_count_selector_fires_only_on_count_change(self):
        """L2: a count-selector subscriber fires only when count changes."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createNotificationsStore }} from '{_IMPORT}'

describe('bench-count-selector', () => {{
  it('count subscriber ignores unrelated state mutations', () => {{
    const store = createNotificationsStore()
    const calls: Array<[number, number]> = []
    const unsub = store.subscribe(
      (s: any) => s.count,
      (cur: number, prev: number) => {{ calls.push([cur, prev]) }},
    )
    store.getState().push({{ id: 'a', message: 'A', level: 'info' }})
    expect(calls.length).toBe(1)
    expect(calls[0][0]).toBe(1)
    expect(calls[0][1]).toBe(0)
    // an unrelated setState that does not change count must NOT fire
    store.setState({{ unrelated: 'x' }} as any)
    expect(calls.length).toBe(1)
    store.getState().push({{ id: 'b', message: 'B', level: 'info' }})
    expect(calls.length).toBe(2)
    expect(calls[1][0]).toBe(2)
    unsub()
    // after unsubscribe no further fires
    store.getState().push({{ id: 'c', message: 'C', level: 'info' }})
    expect(calls.length).toBe(2)
  }})
}})
"""
        _assert_passed(_run_driver(body), "count selector subscription")

    def test_haserrors_selector_fires_only_on_flip(self):
        """L2: hasErrors subscriber fires on the boolean flip, not on a 2nd error."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createNotificationsStore }} from '{_IMPORT}'

describe('bench-haserrors-selector', () => {{
  it('hasErrors subscriber fires only when the boolean value flips', () => {{
    const store = createNotificationsStore()
    const calls: Array<[boolean, boolean]> = []
    const unsub = store.subscribe(
      (s: any) => s.hasErrors,
      (cur: boolean, prev: boolean) => {{ calls.push([cur, prev]) }},
    )
    // info push: hasErrors stays false -> no fire
    store.getState().push({{ id: 'a', message: 'A', level: 'info' }})
    expect(calls.length).toBe(0)
    // first error: false -> true -> fire
    store.getState().push({{ id: 'e1', message: 'E1', level: 'error' }})
    expect(calls.length).toBe(1)
    expect(calls[0][0]).toBe(true)
    expect(calls[0][1]).toBe(false)
    // second error: hasErrors stays true -> NO fire
    store.getState().push({{ id: 'e2', message: 'E2', level: 'error' }})
    expect(calls.length).toBe(1)
    // dismiss one error, still one error left: stays true -> NO fire
    store.getState().dismiss('e1')
    expect(calls.length).toBe(1)
    // dismiss last error: true -> false -> fire
    store.getState().dismiss('e2')
    expect(calls.length).toBe(2)
    expect(calls[1][0]).toBe(false)
    expect(calls[1][1]).toBe(true)
    unsub()
  }})
}})
"""
        _assert_passed(_run_driver(body), "hasErrors selector flip")

    def test_fire_immediately(self):
        """L2: fireImmediately invokes the listener once synchronously at sub."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createNotificationsStore }} from '{_IMPORT}'

describe('bench-fire-immediately', () => {{
  it('fireImmediately delivers the current slice synchronously', () => {{
    const store = createNotificationsStore()
    store.getState().push({{ id: 'a', message: 'A', level: 'info' }})
    store.getState().push({{ id: 'b', message: 'B', level: 'info' }})
    const seen: number[] = []
    const unsub = store.subscribe(
      (s: any) => s.count,
      (cur: number) => {{ seen.push(cur) }},
      {{ fireImmediately: true }},
    )
    // called immediately with the current count (2)
    expect(seen.length).toBe(1)
    expect(seen[0]).toBe(2)
    // a later change fires again
    store.getState().push({{ id: 'c', message: 'C', level: 'info' }})
    expect(seen.length).toBe(2)
    expect(seen[1]).toBe(3)
    unsub()
  }})

  it('without fireImmediately the listener is not called at subscription', () => {{
    const store = createNotificationsStore()
    store.getState().push({{ id: 'a', message: 'A', level: 'info' }})
    const seen: number[] = []
    const unsub = store.subscribe((s: any) => s.count, (c: number) => {{ seen.push(c) }})
    expect(seen.length).toBe(0)
    unsub()
  }})
}})
"""
        _assert_passed(_run_driver(body), "fireImmediately")
