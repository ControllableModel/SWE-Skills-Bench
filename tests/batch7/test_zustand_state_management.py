"""Benchmark tests for the `zustand-state-management` skill (variant ext7).

Verifies the agent's implementation of a self-contained named-counters store
module built on top of zustand's public vanilla `createStore` + `combine`
middleware API.

Source of truth: tasks/ext7/zustand-state-management.md. The task asks the agent
to create:
  - examples/counters-store/countersStore.ts  (factory `createCountersStore` + types)
  - tests/countersStore.test.ts                (the agent's own Vitest suite)

The store manages a set of independent named integer counters and exposes
derived read-only fields that must always stay consistent with `counters`:
  - total          : sum of all counter values
  - countersCount  : number of distinct counter names
  - maxName        : name of the largest counter (ties broken lexicographically
                     by smallest name); null when empty
Actions:
  - add(name, by=1)   : increment (creating at `by`); non-integer `by` rejected
  - set(name, value)  : set absolute value (creating); non-integer rejected
  - remove(name)      : delete a counter; unknown name is a no-op
  - reset()           : remove all counters

L1 checks: the deliverable files exist and are minimally well-formed, and the
agent's own suite passes via `pnpm vitest run tests/countersStore.test.ts`.

L2 checks: discriminative DYNAMIC EXECUTION. We DO NOT trust the agent's own
test file. We write INDEPENDENT Vitest drivers into REPO_DIR/tests/ that import
the agent's `createCountersStore` factory directly and exercise the real runtime
behavior (seeding, add/set creating + arithmetic, integer-rejection guards,
remove + no-op, derived total/countersCount/maxName correctness incl. the
lexicographic tie-break, maxName==null when empty, reset clearing, and a long
mutation sequence verified against an independent recompute). Each driver runs
via the repo's native `pnpm vitest run` and we assert on returncode.

A naive / hardcoded / "looks related" implementation (e.g. one that ignores the
integer guards, hardcodes maxName, or lets the derived fields drift) fails these
driver tests.
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
COUNTERS_STORE = os.path.join(
    REPO_DIR, "examples", "counters-store", "countersStore.ts"
)
AGENT_TEST = os.path.join(REPO_DIR, "tests", "countersStore.test.ts")

# Driver files we create under tests/ so vitest (dir: 'tests') picks them up.
# Each is removed in teardown. Use a unique tag to avoid clobbering anything.
_TAG = uuid.uuid4().hex[:8]
_DRIVER_BASENAME = f"_bench_counters_driver_{_TAG}.test.ts"
DRIVER_PATH = os.path.join(REPO_DIR, "tests", _DRIVER_BASENAME)

VITEST_TIMEOUT = 600

# Relative import path from a file living in tests/ to the counters store module.
_IMPORT = "../examples/counters-store/countersStore"


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
    """Write an independent vitest driver file under tests/ and return basename."""
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


# A small TS recompute helper injected into drift/derived drivers so the test
# computes the expected derived fields INDEPENDENTLY of the agent's code.
_RECOMPUTE_TS = """
function recompute(counters: Record<string, number>) {
  const names = Object.keys(counters)
  let total = 0
  for (const n of names) total += counters[n]
  let maxName: string | null = null
  let maxVal = -Infinity
  // sort names so ties break on the lexicographically smallest name
  for (const n of [...names].sort()) {
    if (counters[n] > maxVal) { maxVal = counters[n]; maxName = n }
  }
  return { total, countersCount: names.length, maxName }
}
"""


class TestZustandStateManagement:
    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------ L1
    def test_counters_store_module_exists(self):
        """L1: examples/counters-store/countersStore.ts exists and is non-trivial."""
        assert os.path.isfile(COUNTERS_STORE), f"missing {COUNTERS_STORE}"
        size = os.path.getsize(COUNTERS_STORE)
        assert size > 200, f"countersStore.ts suspiciously small ({size} bytes)"

    def test_module_exports_factory(self):
        """L1: module declares an exported `createCountersStore`."""
        with open(COUNTERS_STORE) as fh:
            src = fh.read()
        assert re.search(r"export\b.*\bcreateCountersStore\b", src) or re.search(
            r"\bcreateCountersStore\b", src
        ), "createCountersStore not found in countersStore.ts"

    def test_agent_test_suite_exists(self):
        """L1: the agent's own Vitest suite file exists and is non-trivial."""
        assert os.path.isfile(AGENT_TEST), f"missing {AGENT_TEST}"
        assert os.path.getsize(AGENT_TEST) > 200

    def test_agent_suite_passes(self):
        """L1/L2: the agent's own `tests/countersStore.test.ts` suite passes.

        Also confirms the task's >=10 `it`/`test` requirement was satisfied so
        a single rubber-stamp test cannot pass this gate.
        """
        proc = _run_vitest("tests/countersStore.test.ts")
        _assert_passed(proc, "agent countersStore.test.ts suite")
        combined = (proc.stdout or "") + (proc.stderr or "")
        m = re.search(r"Tests\s+(\d+)\s+passed", combined)
        if m:
            assert int(m.group(1)) >= 10, (
                f"expected >=10 passing tests, parsed {m.group(1)}\n"
                f"{combined[-2000:]}"
            )

    # ------------------------------------------------------------------ L2
    def test_vanilla_handles_and_empty_defaults(self):
        """L2: store exposes getState/setState/subscribe; empty defaults hold."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCountersStore }} from '{_IMPORT}'

describe('bench-handles', () => {{
  it('exposes vanilla handles and empty derived defaults', () => {{
    const store = createCountersStore()
    expect(typeof store.getState).toBe('function')
    expect(typeof store.setState).toBe('function')
    expect(typeof store.subscribe).toBe('function')
    const s = store.getState()
    expect(s.counters).toEqual({{}})
    expect(s.total).toBe(0)
    expect(s.countersCount).toBe(0)
    expect(s.maxName).toBeNull()
  }})
}})
"""
        _assert_passed(_run_driver(body), "vanilla handles + empty defaults")

    def test_seed_initial_counters(self):
        """L2: initialCounters seeds the store and derived fields are computed."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCountersStore }} from '{_IMPORT}'

describe('bench-seed', () => {{
  it('seeds counters from initialCounters and derives fields', () => {{
    const store = createCountersStore({{ a: 2, b: 5, c: 5 }})
    const s = store.getState()
    expect(s.counters).toEqual({{ a: 2, b: 5, c: 5 }})
    expect(s.total).toBe(12)
    expect(s.countersCount).toBe(3)
    // b and c tie at 5 -> lexicographically smallest name 'b'
    expect(s.maxName).toBe('b')
  }})
}})
"""
        _assert_passed(_run_driver(body), "seed initial counters")

    def test_add_creates_and_increments_including_negative(self):
        """L2: add creates at `by`, increments existing, handles negative `by`."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCountersStore }} from '{_IMPORT}'

describe('bench-add', () => {{
  it('add creates, increments, and applies negative by', () => {{
    const store = createCountersStore()
    store.getState().add('x')          // default by = 1 -> create at 1
    expect(store.getState().counters.x).toBe(1)
    store.getState().add('x', 4)       // increment -> 5
    expect(store.getState().counters.x).toBe(5)
    store.getState().add('x', -2)      // negative -> 3
    expect(store.getState().counters.x).toBe(3)
    store.getState().add('y', 10)      // create at 10
    const s = store.getState()
    expect(s.counters.y).toBe(10)
    expect(s.total).toBe(13)
    expect(s.countersCount).toBe(2)
    expect(s.maxName).toBe('y')
  }})
}})
"""
        _assert_passed(_run_driver(body), "add create/increment/negative")

    def test_add_rejects_non_integer_by(self):
        """L2: a non-integer `by` is rejected with no state change."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCountersStore }} from '{_IMPORT}'

describe('bench-add-guard', () => {{
  it('non-integer by is rejected (no state change)', () => {{
    const store = createCountersStore({{ a: 3 }})
    const before = JSON.stringify(store.getState().counters)
    expect(() => store.getState().add('a', 1.5)).not.toThrow()
    expect(JSON.stringify(store.getState().counters)).toBe(before)
    expect(store.getState().total).toBe(3)
    // a brand-new name with a non-integer by must not be created either
    expect(() => store.getState().add('b', NaN as any)).not.toThrow()
    expect('b' in store.getState().counters).toBe(false)
    expect(store.getState().countersCount).toBe(1)
  }})
}})
"""
        _assert_passed(_run_driver(body), "add rejects non-integer by")

    def test_set_creates_and_overwrites(self):
        """L2: set creates a counter and overwrites an existing absolute value."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCountersStore }} from '{_IMPORT}'

describe('bench-set', () => {{
  it('set creates and overwrites absolute values', () => {{
    const store = createCountersStore()
    store.getState().set('a', 7)       // create at 7
    expect(store.getState().counters.a).toBe(7)
    store.getState().set('a', 2)       // overwrite to 2 (not increment)
    expect(store.getState().counters.a).toBe(2)
    store.getState().set('b', -4)      // negative absolute is allowed
    const s = store.getState()
    expect(s.counters.b).toBe(-4)
    expect(s.total).toBe(-2)
    expect(s.countersCount).toBe(2)
    expect(s.maxName).toBe('a')
  }})
}})
"""
        _assert_passed(_run_driver(body), "set create/overwrite")

    def test_set_rejects_non_integer_value(self):
        """L2: a non-integer `value` for set is rejected with no state change."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCountersStore }} from '{_IMPORT}'

describe('bench-set-guard', () => {{
  it('non-integer value is rejected (no state change)', () => {{
    const store = createCountersStore({{ a: 9 }})
    const before = JSON.stringify(store.getState().counters)
    expect(() => store.getState().set('a', 2.7)).not.toThrow()
    expect(JSON.stringify(store.getState().counters)).toBe(before)
    expect(store.getState().counters.a).toBe(9)
    // new name with non-integer value must not be created
    expect(() => store.getState().set('c', 1.1)).not.toThrow()
    expect('c' in store.getState().counters).toBe(false)
    expect(store.getState().countersCount).toBe(1)
  }})
}})
"""
        _assert_passed(_run_driver(body), "set rejects non-integer value")

    def test_remove_deletes_and_noops_unknown(self):
        """L2: remove deletes a counter; removing an unknown name is a no-op."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCountersStore }} from '{_IMPORT}'

describe('bench-remove', () => {{
  it('remove deletes; unknown name is a silent no-op', () => {{
    const store = createCountersStore({{ a: 1, b: 2, c: 3 }})
    store.getState().remove('b')
    let s = store.getState()
    expect('b' in s.counters).toBe(false)
    expect(s.countersCount).toBe(2)
    expect(s.total).toBe(4)
    expect(s.maxName).toBe('c')
    const before = JSON.stringify(s.counters)
    expect(() => store.getState().remove('zzz')).not.toThrow()
    expect(JSON.stringify(store.getState().counters)).toBe(before)
    expect(store.getState().countersCount).toBe(2)
  }})
}})
"""
        _assert_passed(_run_driver(body), "remove + unknown no-op")

    def test_maxname_tiebreak_and_null_when_empty(self):
        """L2: maxName uses lexicographic tie-break and is null when empty."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCountersStore }} from '{_IMPORT}'

describe('bench-maxname', () => {{
  it('maxName breaks ties lexicographically and is null when empty', () => {{
    const store = createCountersStore()
    // empty -> null
    expect(store.getState().maxName).toBeNull()
    // three-way tie at 5: smallest name wins
    store.getState().set('m', 5)
    store.getState().set('a', 5)
    store.getState().set('z', 5)
    expect(store.getState().maxName).toBe('a')
    // raise 'm' above the tie -> 'm' becomes max
    store.getState().add('m', 1)
    expect(store.getState().maxName).toBe('m')
    // remove the unique max -> recompute against remaining tie ('a','z')
    store.getState().remove('m')
    expect(store.getState().maxName).toBe('a')
    // negative values: single counter is still the max
    const s2 = createCountersStore({{ only: -7 }})
    expect(s2.getState().maxName).toBe('only')
  }})
}})
"""
        _assert_passed(_run_driver(body), "maxName tie-break + null")

    def test_reset_clears_all_derived(self):
        """L2: reset removes all counters and zeroes/nulls every derived field."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCountersStore }} from '{_IMPORT}'

describe('bench-reset', () => {{
  it('reset clears counters and all derived fields', () => {{
    const store = createCountersStore({{ a: 4, b: 9, c: 1 }})
    expect(store.getState().total).toBe(14)
    store.getState().reset()
    const s = store.getState()
    expect(s.counters).toEqual({{}})
    expect(s.total).toBe(0)
    expect(s.countersCount).toBe(0)
    expect(s.maxName).toBeNull()
    // store remains usable after reset
    store.getState().add('fresh', 3)
    expect(store.getState().counters.fresh).toBe(3)
    expect(store.getState().maxName).toBe('fresh')
  }})
}})
"""
        _assert_passed(_run_driver(body), "reset clears derived")

    def test_derived_fields_never_drift(self):
        """L2: after a long op sequence, derived fields match an independent recompute."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCountersStore }} from '{_IMPORT}'
{_RECOMPUTE_TS}
describe('bench-drift', () => {{
  it('total/countersCount/maxName equal independent recompute after each op', () => {{
    const store = createCountersStore({{ a: 5, b: 5 }})
    const ops: Array<() => void> = [
      () => store.getState().add('a', 3),
      () => store.getState().add('c', 5),       // 'a'=8, tie? no
      () => store.getState().set('b', 8),       // tie a=8,b=8 -> 'a'
      () => store.getState().add('b', -8),      // b=0
      () => store.getState().set('d', 8),       // tie a=8,d=8 -> 'a'
      () => store.getState().remove('a'),       // now d=8 unique max
      () => store.getState().add('e', 2),
      () => store.getState().set('d', 1),       // d drops; recompute max
      () => store.getState().remove('zzz'),     // no-op
      () => store.getState().add('aa', 4),
    ]
    for (const op of ops) {{
      op()
      const s = store.getState()
      const r = recompute(s.counters)
      expect(s.total).toBe(r.total)
      expect(s.countersCount).toBe(r.countersCount)
      expect(s.maxName).toBe(r.maxName)
    }}
  }})
}})
"""
        _assert_passed(_run_driver(body), "no-drift invariant")

    def test_subscribe_notified_on_change(self):
        """L2: a plain subscriber is notified when an action mutates state."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createCountersStore }} from '{_IMPORT}'

describe('bench-subscribe', () => {{
  it('subscribe fires on action-driven state change', () => {{
    const store = createCountersStore()
    let totals: number[] = []
    const unsub = store.subscribe((s: any) => {{ totals.push(s.total) }})
    store.getState().add('a', 4)
    store.getState().set('b', 6)
    expect(totals.length).toBeGreaterThanOrEqual(2)
    expect(totals[totals.length - 1]).toBe(store.getState().total)
    expect(store.getState().total).toBe(10)
    unsub()
    store.getState().add('a', 1)
    // no further notifications after unsubscribe
    expect(totals[totals.length - 1]).toBe(10)
  }})
}})
"""
        _assert_passed(_run_driver(body), "subscribe notification")
