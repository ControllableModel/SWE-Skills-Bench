"""Benchmark tests for the `zustand-state-management` skill.

Verifies the agent's implementation of a self-contained shopping-cart store
module built on top of zustand's public vanilla + middleware API.

Source of truth: tasks/ext1/zustand-state-management.md. The task asks the agent
to create:
  - examples/cart-store/cartStore.ts  (factory `createCartStore` + types)
  - tests/cartStore.test.ts           (the agent's own Vitest suite)

L1 checks: the deliverable files exist and are minimally well-formed, and the
agent's own suite passes via `pnpm vitest run tests/cartStore.test.ts`.

L2 checks: discriminative DYNAMIC EXECUTION. We DO NOT trust the agent's own
test file. Instead we write an INDEPENDENT Vitest driver into REPO_DIR/tests/
that imports the agent's `createCartStore` factory directly and exercises the
real runtime behavior (merging quantities, derived totals, selector
subscriptions, fireImmediately, async success/error paths, the invalid-fetcher
guard, and in-memory storage rehydration). Each driver runs via the repo's
native `pnpm vitest run` and we assert on returncode + parsed results.

A naive / hardcoded / "looks related" implementation fails these driver tests.
"""

import json
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
CART_STORE = os.path.join(REPO_DIR, "examples", "cart-store", "cartStore.ts")
AGENT_TEST = os.path.join(REPO_DIR, "tests", "cartStore.test.ts")

# Driver files we create under tests/ so vitest (dir: 'tests') picks them up.
# Each is removed in teardown. Use a unique tag to avoid clobbering anything.
_TAG = uuid.uuid4().hex[:8]
_DRIVER_BASENAME = f"_bench_cart_driver_{_TAG}.test.ts"
DRIVER_PATH = os.path.join(REPO_DIR, "tests", _DRIVER_BASENAME)

VITEST_TIMEOUT = 600


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


# Relative import path from a file living in tests/ to the cart store module.
_IMPORT = "../examples/cart-store/cartStore"


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
    def test_cart_store_module_exists(self):
        """L1: examples/cart-store/cartStore.ts exists and is non-trivial."""
        assert os.path.isfile(CART_STORE), f"missing {CART_STORE}"
        size = os.path.getsize(CART_STORE)
        assert size > 200, f"cartStore.ts suspiciously small ({size} bytes)"

    def test_module_exports_factory(self):
        """L1: module declares an exported `createCartStore`."""
        with open(CART_STORE) as fh:
            src = fh.read()
        assert re.search(r"export\b.*\bcreateCartStore\b", src) or re.search(
            r"\bcreateCartStore\b", src
        ), "createCartStore not found in cartStore.ts"

    def test_agent_test_suite_exists(self):
        """L1: the agent's own Vitest suite file exists."""
        assert os.path.isfile(AGENT_TEST), f"missing {AGENT_TEST}"
        assert os.path.getsize(AGENT_TEST) > 200

    def test_agent_suite_passes(self):
        """L1/L2: the agent's own `tests/cartStore.test.ts` suite passes."""
        proc = _run_vitest("tests/cartStore.test.ts")
        _assert_passed(proc, "agent cartStore.test.ts suite")
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
    def test_add_and_derived_totals(self):
        """L2: addItem updates items and derived itemCount/subtotal exactly."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCartStore }} from '{_IMPORT}'

describe('bench-add-totals', () => {{
  it('computes itemCount and subtotal from items', () => {{
    const store = createCartStore()
    store.getState().addItem({{ id: 'a', name: 'Apple', unitPrice: 1.5, quantity: 2 }})
    store.getState().addItem({{ id: 'b', name: 'Bread', unitPrice: 3, quantity: 1 }})
    const s = store.getState()
    expect(s.itemCount).toBe(3)
    expect(s.subtotal).toBeCloseTo(6, 6)
    const items = (s.items as any)
    const list = Array.isArray(items) ? items : Object.values(items)
    expect(list.length).toBe(2)
  }})
}})
"""
        _assert_passed(_run_driver(body), "add + derived totals")

    def test_duplicate_id_merges_quantity(self):
        """L2: adding an existing id increments quantity, no duplicate row."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCartStore }} from '{_IMPORT}'

describe('bench-merge', () => {{
  it('merges quantity for duplicate id', () => {{
    const store = createCartStore()
    store.getState().addItem({{ id: 'a', name: 'Apple', unitPrice: 2, quantity: 1 }})
    store.getState().addItem({{ id: 'a', name: 'Apple', unitPrice: 2, quantity: 3 }})
    const s = store.getState()
    const items = (s.items as any)
    const list = Array.isArray(items) ? items : Object.values(items)
    expect(list.length).toBe(1)
    const apple = list.find((x: any) => x.id === 'a')
    expect(apple.quantity).toBe(4)
    expect(s.itemCount).toBe(4)
    expect(s.subtotal).toBeCloseTo(8, 6)
  }})
}})
"""
        _assert_passed(_run_driver(body), "duplicate id merge")

    def test_set_quantity_removes_at_zero_and_below(self):
        """L2: setQuantity(id, <=0) removes the item; positive updates it."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCartStore }} from '{_IMPORT}'

describe('bench-setqty', () => {{
  it('removes item when quantity <= 0', () => {{
    const store = createCartStore()
    store.getState().addItem({{ id: 'a', name: 'A', unitPrice: 5, quantity: 2 }})
    store.getState().addItem({{ id: 'b', name: 'B', unitPrice: 1, quantity: 5 }})
    store.getState().setQuantity('a', 4)
    let s = store.getState()
    let list = Array.isArray(s.items) ? s.items : Object.values(s.items as any)
    expect((list.find((x: any) => x.id === 'a')).quantity).toBe(4)
    expect(s.itemCount).toBe(9)
    expect(s.subtotal).toBeCloseTo(25, 6)
    store.getState().setQuantity('b', 0)
    s = store.getState()
    list = Array.isArray(s.items) ? s.items : Object.values(s.items as any)
    expect(list.find((x: any) => x.id === 'b')).toBeUndefined()
    expect(s.itemCount).toBe(4)
    expect(s.subtotal).toBeCloseTo(20, 6)
    store.getState().setQuantity('a', -3)
    s = store.getState()
    list = Array.isArray(s.items) ? s.items : Object.values(s.items as any)
    expect(list.length).toBe(0)
    expect(s.itemCount).toBe(0)
    expect(s.subtotal).toBe(0)
  }})
}})
"""
        _assert_passed(_run_driver(body), "setQuantity removal")

    def test_unknown_id_noops(self):
        """L2: setQuantity/removeItem for unknown ids are silent no-ops."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCartStore }} from '{_IMPORT}'

describe('bench-noop', () => {{
  it('unknown ids are no-ops without error', () => {{
    const store = createCartStore()
    store.getState().addItem({{ id: 'a', name: 'A', unitPrice: 10, quantity: 2 }})
    const before = store.getState()
    expect(() => store.getState().setQuantity('zzz', 9)).not.toThrow()
    expect(() => store.getState().removeItem('zzz')).not.toThrow()
    const after = store.getState()
    expect(after.itemCount).toBe(before.itemCount)
    expect(after.subtotal).toBe(before.subtotal)
    const list = Array.isArray(after.items) ? after.items : Object.values(after.items as any)
    expect(list.length).toBe(1)
  }})
}})
"""
        _assert_passed(_run_driver(body), "unknown id no-op")

    def test_remove_and_clear(self):
        """L2: removeItem drops a row; clear empties cart and zeroes totals."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCartStore }} from '{_IMPORT}'

describe('bench-remove-clear', () => {{
  it('removeItem and clear reset derived totals', () => {{
    const store = createCartStore()
    store.getState().addItem({{ id: 'a', name: 'A', unitPrice: 2, quantity: 3 }})
    store.getState().addItem({{ id: 'b', name: 'B', unitPrice: 4, quantity: 1 }})
    store.getState().removeItem('a')
    let s = store.getState()
    let list = Array.isArray(s.items) ? s.items : Object.values(s.items as any)
    expect(list.length).toBe(1)
    expect(s.itemCount).toBe(1)
    expect(s.subtotal).toBeCloseTo(4, 6)
    store.getState().clear()
    s = store.getState()
    list = Array.isArray(s.items) ? s.items : Object.values(s.items as any)
    expect(list.length).toBe(0)
    expect(s.itemCount).toBe(0)
    expect(s.subtotal).toBe(0)
  }})
}})
"""
        _assert_passed(_run_driver(body), "remove + clear")

    def test_derived_totals_never_drift(self):
        """L2: after a long mutation sequence, derived fields match a recompute."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCartStore }} from '{_IMPORT}'

function recompute(items: any) {{
  const list = Array.isArray(items) ? items : Object.values(items)
  let count = 0, subtotal = 0
  for (const it of list) {{ count += it.quantity; subtotal += it.unitPrice * it.quantity }}
  return {{ count, subtotal }}
}}

describe('bench-drift', () => {{
  it('derived fields equal independent recompute after each op', () => {{
    const store = createCartStore()
    const ops: Array<() => void> = [
      () => store.getState().addItem({{ id: 'a', name: 'A', unitPrice: 1.25, quantity: 4 }}),
      () => store.getState().addItem({{ id: 'b', name: 'B', unitPrice: 7, quantity: 2 }}),
      () => store.getState().addItem({{ id: 'a', name: 'A', unitPrice: 1.25, quantity: 1 }}),
      () => store.getState().setQuantity('b', 5),
      () => store.getState().removeItem('a'),
      () => store.getState().addItem({{ id: 'c', name: 'C', unitPrice: 3.5, quantity: 3 }}),
      () => store.getState().setQuantity('c', 0),
    ]
    for (const op of ops) {{
      op()
      const s = store.getState()
      const r = recompute(s.items)
      expect(s.itemCount).toBe(r.count)
      expect(s.subtotal).toBeCloseTo(r.subtotal, 6)
    }}
  }})
}})
"""
        _assert_passed(_run_driver(body), "no-drift invariant")

    def test_selector_subscription_fires_only_on_slice_change(self):
        """L2: subtotal-selector subscriber fires only when subtotal changes."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCartStore }} from '{_IMPORT}'

describe('bench-selector', () => {{
  it('subtotal subscriber ignores unrelated status changes', () => {{
    const store = createCartStore()
    const calls: Array<[number, number]> = []
    const unsub = store.subscribe(
      (s: any) => s.subtotal,
      (cur: number, prev: number) => {{ calls.push([cur, prev]) }},
    )
    // change subtotal
    store.getState().addItem({{ id: 'a', name: 'A', unitPrice: 5, quantity: 2 }})
    expect(calls.length).toBe(1)
    expect(calls[0][0]).toBeCloseTo(10, 6)
    expect(calls[0][1]).toBeCloseTo(0, 6)
    // change an unrelated field only (status) WITHOUT touching subtotal
    store.setState({{ status: 'loading' }} as any)
    expect(calls.length).toBe(1)
    // change subtotal again
    store.getState().addItem({{ id: 'b', name: 'B', unitPrice: 1, quantity: 3 }})
    expect(calls.length).toBe(2)
    expect(calls[1][0]).toBeCloseTo(13, 6)
    unsub()
  }})
}})
"""
        _assert_passed(_run_driver(body), "subtotal selector subscription")

    def test_itemcount_selector_and_fire_immediately(self):
        """L2: itemCount selector; fireImmediately invokes once at sub time."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCartStore }} from '{_IMPORT}'

describe('bench-fireimmediately', () => {{
  it('fireImmediately delivers current slice synchronously', () => {{
    const store = createCartStore()
    store.getState().addItem({{ id: 'a', name: 'A', unitPrice: 2, quantity: 3 }})
    const seen: number[] = []
    const unsub = store.subscribe(
      (s: any) => s.itemCount,
      (cur: number) => {{ seen.push(cur) }},
      {{ fireImmediately: true }},
    )
    // immediate call with the current itemCount (3)
    expect(seen.length).toBe(1)
    expect(seen[0]).toBe(3)
    // unrelated change does not fire itemCount listener
    store.setState({{ status: 'success' }} as any)
    expect(seen.length).toBe(1)
    // itemCount change fires
    store.getState().setQuantity('a', 5)
    expect(seen.length).toBe(2)
    expect(seen[1]).toBe(5)
    unsub()
  }})
}})
"""
        _assert_passed(_run_driver(body), "itemCount selector + fireImmediately")

    def test_async_load_success_path(self):
        """L2: loadItems success replaces contents and sets status 'success'."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCartStore }} from '{_IMPORT}'

describe('bench-load-success', () => {{
  it('loadItems success replaces items and sets status', async () => {{
    const store = createCartStore()
    store.getState().addItem({{ id: 'old', name: 'Old', unitPrice: 9, quantity: 1 }})
    const fetcher = async () => ([
      {{ id: 'x', name: 'X', unitPrice: 2, quantity: 2 }},
      {{ id: 'y', name: 'Y', unitPrice: 5, quantity: 1 }},
    ])
    await store.getState().loadItems(fetcher)
    const s = store.getState()
    expect(s.status).toBe('success')
    expect(s.errorMessage).toBeNull()
    const list = Array.isArray(s.items) ? s.items : Object.values(s.items as any)
    const ids = list.map((i: any) => i.id).sort()
    expect(ids).toEqual(['x', 'y'])
    expect(s.itemCount).toBe(3)
    expect(s.subtotal).toBeCloseTo(9, 6)
  }})
}})
"""
        _assert_passed(_run_driver(body), "async load success")

    def test_async_load_rejection_path(self):
        """L2: loadItems rejection captures error, keeps items, never throws."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCartStore }} from '{_IMPORT}'

describe('bench-load-error', () => {{
  it('loadItems rejection sets error state without throwing', async () => {{
    const store = createCartStore()
    store.getState().addItem({{ id: 'keep', name: 'Keep', unitPrice: 4, quantity: 2 }})
    const before = store.getState()
    const beforeList = Array.isArray(before.items) ? before.items : Object.values(before.items as any)
    const fetcher = async () => {{ throw new Error('boom network') }}
    let threw = false
    let resolved: any = 'sentinel'
    try {{
      resolved = await store.getState().loadItems(fetcher)
    }} catch (e) {{
      threw = true
    }}
    expect(threw).toBe(false)
    const s = store.getState()
    expect(s.status).toBe('error')
    expect(typeof s.errorMessage).toBe('string')
    expect((s.errorMessage as string).length).toBeGreaterThan(0)
    // items unchanged
    const afterList = Array.isArray(s.items) ? s.items : Object.values(s.items as any)
    expect(afterList.length).toBe(beforeList.length)
    expect(s.itemCount).toBe(before.itemCount)
    expect(s.subtotal).toBeCloseTo(before.subtotal, 6)
  }})
}})
"""
        _assert_passed(_run_driver(body), "async load rejection")

    def test_invalid_fetcher_guard(self):
        """L2: non-function fetcher sets error state, no async work, no throw."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCartStore }} from '{_IMPORT}'

describe('bench-guard', () => {{
  it('invalid fetcher is guarded into error state', async () => {{
    const store = createCartStore()
    store.getState().addItem({{ id: 'k', name: 'K', unitPrice: 1, quantity: 1 }})
    let threw = false
    try {{
      // @ts-expect-error intentionally invalid
      await store.getState().loadItems(42)
    }} catch (e) {{
      threw = true
    }}
    expect(threw).toBe(false)
    const s = store.getState()
    expect(s.status).toBe('error')
    expect(typeof s.errorMessage).toBe('string')
    expect((s.errorMessage as string).length).toBeGreaterThan(0)
    // items untouched
    const list = Array.isArray(s.items) ? s.items : Object.values(s.items as any)
    expect(list.length).toBe(1)
  }})
}})
"""
        _assert_passed(_run_driver(body), "invalid fetcher guard")

    def test_storage_persist_and_rehydrate(self):
        """L2: items persist to in-memory storage and rehydrate in a new store."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCartStore }} from '{_IMPORT}'

function makeStorage() {{
  const map = new Map<string, string>()
  return {{
    getItem: (name: string) => (map.has(name) ? map.get(name)! : null),
    setItem: (name: string, value: string) => {{ map.set(name, value) }},
    removeItem: (name: string) => {{ map.delete(name) }},
    _map: map,
  }}
}}

describe('bench-storage', () => {{
  it('persists to storage and rehydrates a fresh store', () => {{
    const storage = makeStorage()
    const s1 = createCartStore({{ storage }})
    s1.getState().addItem({{ id: 'a', name: 'A', unitPrice: 2.5, quantity: 2 }})
    s1.getState().addItem({{ id: 'b', name: 'B', unitPrice: 4, quantity: 1 }})
    // something must have been written to storage
    expect(storage._map.size).toBeGreaterThan(0)
    // a fresh store given the same storage rehydrates the items + totals
    const s2 = createCartStore({{ storage }})
    const st = s2.getState()
    const list = Array.isArray(st.items) ? st.items : Object.values(st.items as any)
    const ids = list.map((i: any) => i.id).sort()
    expect(ids).toEqual(['a', 'b'])
    expect(st.itemCount).toBe(3)
    expect(st.subtotal).toBeCloseTo(9, 6)
  }})

  it('works with no storage (no side effects, no throw)', () => {{
    const s = createCartStore()
    expect(() => s.getState().addItem({{ id: 'z', name: 'Z', unitPrice: 1, quantity: 1 }})).not.toThrow()
    expect(s.getState().itemCount).toBe(1)
  }})
}})
"""
        _assert_passed(_run_driver(body), "storage persist + rehydrate")
