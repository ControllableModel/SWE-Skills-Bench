"""
Test for the 'vitest-unit-testing' skill — variant ext6.

Task (ext6): add a bounded LRU cache `LruCache<K, V>` at
packages/vite/src/node/lruCache.ts plus a dedicated vitest spec at
packages/vite/src/node/__tests__/lruCache.spec.ts.

The cache must implement get/set/has/delete/clear/size with:
- true recency-aware (LRU) eviction once size would exceed `max`,
- an optional `onEvict(key, value)` callback fired exactly once per eviction,
  in least-recently-used-first order,
- `get` (hit) and re-`set` mark a key most-recently-used,
- `has` probes WITHOUT changing recency,
- updating an existing key never evicts,
- `delete` / `clear` never call `onEvict`.

Verification strategy:
- L1: the deliverable source/spec files exist, the class is exported, and the
  agent spec imports it from ../lruCache.
- L2: DYNAMIC EXECUTION via the repo's native toolchain (vitest, run with
  `pnpm exec vitest run ...`). To avoid trusting the agent's own spec, we write
  INDEPENDENT driver spec files into the repo's __tests__ directory that import
  `LruCache` from `../lruCache` and exercise the exact behaviors required by the
  task. A naive implementation (insertion-order eviction ignoring recency,
  `has` refreshing recency, `onEvict` fired on delete/clear, eviction count or
  argument wrong, or `size` exceeding `max`) makes at least one driver spec
  fail. We also run the agent's delivered spec.
"""

import os
import re
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/vite"
TESTS_DIR = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "__tests__")
LRU_TS = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "lruCache.ts")
AGENT_SPEC = os.path.join(TESTS_DIR, "lruCache.spec.ts")

# rel paths (abs, for cleanup) of driver specs we drop in; filled by _write_spec.
_DRIVER_FILES = []


def _vitest(rel_spec_path, timeout=600):
    """Run a single spec file via the repo's native vitest from repo root."""
    cmd = ["pnpm", "exec", "vitest", "run", rel_spec_path]
    return subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _write_spec(name, body):
    """Write a driver spec into the repo __tests__ dir; return its repo-rel path."""
    assert os.path.isdir(TESTS_DIR), f"tests dir missing: {TESTS_DIR}"
    fname = name if name.endswith(".spec.ts") else name + ".spec.ts"
    abspath = os.path.join(TESTS_DIR, fname)
    with open(abspath, "w") as f:
        f.write(textwrap.dedent(body).lstrip("\n"))
    rel = os.path.relpath(abspath, REPO_DIR)
    _DRIVER_FILES.append(abspath)
    return rel


@pytest.fixture(scope="module", autouse=True)
def _cleanup_driver_specs():
    """Remove any driver specs we created so we leave the repo clean."""
    yield
    for p in _DRIVER_FILES:
        try:
            os.remove(p)
        except OSError:
            pass


class TestVitestUnitTesting:
    """Verify the LruCache implementation and its vitest coverage."""

    REPO_DIR = "/workspace/vite"

    # ------------------------------------------------------------------
    # L1 — deliverables exist / minimally well-formed
    # ------------------------------------------------------------------

    def test_lru_source_file_exists(self):
        """lruCache.ts (the new implementation file) must exist."""
        assert os.path.isfile(LRU_TS), f"missing {LRU_TS}"

    def test_lru_class_is_exported(self):
        """lruCache.ts must export a class named LruCache."""
        with open(LRU_TS) as f:
            src = f.read()
        assert re.search(
            r"export\s+class\s+LruCache\b", src
        ), "LruCache not exported as a class from lruCache.ts"

    def test_lru_declares_required_members(self):
        """The class must mention the full required surface (get/set/has/delete/clear/size)."""
        with open(LRU_TS) as f:
            src = f.read()
        for member in ("get", "set", "has", "delete", "clear", "size"):
            assert member in src, f"lruCache.ts does not reference member '{member}'"

    def test_agent_spec_file_exists(self):
        """The dedicated spec file must be delivered."""
        assert os.path.isfile(AGENT_SPEC), f"missing {AGENT_SPEC}"

    def test_agent_spec_imports_from_lru_cache(self):
        """The spec must import LruCache from ../lruCache (not redefine it)."""
        with open(AGENT_SPEC) as f:
            spec = f.read()
        assert "LruCache" in spec, "spec does not reference LruCache"
        assert re.search(
            r"from\s+['\"]\.\./lruCache['\"]", spec
        ), "spec must import from '../lruCache'"

    # ------------------------------------------------------------------
    # L2 — dynamic execution against INDEPENDENT driver specs.
    # Each test drops a focused spec that imports the real implementation
    # and asserts the precise required behavior via vitest.
    # ------------------------------------------------------------------

    def test_basic_get_set_has_size(self):
        """set/get/has/size basics: present vs absent keys, size bounded by content."""
        rel = _write_spec(
            "zz_driver_basic",
            """
            import { expect, test } from 'vitest'
            import { LruCache } from '../lruCache'

            test('basic get/set/has/size', () => {
              const c = new LruCache<string, number>({ max: 3 })
              expect(c.size).toBe(0)
              expect(c.get('a')).toBeUndefined()
              expect(c.has('a')).toBe(false)

              c.set('a', 1)
              c.set('b', 2)
              expect(c.get('a')).toBe(1)
              expect(c.get('b')).toBe(2)
              expect(c.get('missing')).toBeUndefined()
              expect(c.has('a')).toBe(true)
              expect(c.has('missing')).toBe(false)
              expect(c.size).toBe(2)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "basic get/set/has/size behavior wrong\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_lru_eviction_order_and_callback(self):
        """max:2, set a/b/c -> 'a' evicted; onEvict('a',1) called exactly once; size 2."""
        rel = _write_spec(
            "zz_driver_evict",
            """
            import { expect, test, vi } from 'vitest'
            import { LruCache } from '../lruCache'

            test('lru eviction with onEvict spy', () => {
              const onEvict = vi.fn()
              const c = new LruCache<string, number>({ max: 2, onEvict })
              c.set('a', 1)
              c.set('b', 2)
              c.set('c', 3)   // pushes past max -> evict LRU 'a'

              expect(c.size).toBe(2)
              expect(c.has('a')).toBe(false)
              expect(c.get('a')).toBeUndefined()
              expect(c.get('b')).toBe(2)
              expect(c.get('c')).toBe(3)

              expect(onEvict).toHaveBeenCalledTimes(1)
              expect(onEvict).toHaveBeenCalledWith('a', 1)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "LRU eviction order / onEvict callback wrong (naive insertion-order "
            "or wrong args would fail here)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_get_refreshes_recency(self):
        """max:2, set a/b, get a, set c -> 'b' evicted (a was refreshed), not 'a'."""
        rel = _write_spec(
            "zz_driver_get_refresh",
            """
            import { expect, test, vi } from 'vitest'
            import { LruCache } from '../lruCache'

            test('get refreshes recency', () => {
              const onEvict = vi.fn()
              const c = new LruCache<string, number>({ max: 2, onEvict })
              c.set('a', 1)
              c.set('b', 2)
              expect(c.get('a')).toBe(1)   // refresh 'a' -> 'b' is now LRU
              c.set('c', 3)                // evict 'b', NOT 'a'

              expect(c.has('a')).toBe(true)
              expect(c.has('b')).toBe(false)
              expect(c.has('c')).toBe(true)
              expect(c.get('a')).toBe(1)
              expect(c.get('c')).toBe(3)
              expect(onEvict).toHaveBeenCalledTimes(1)
              expect(onEvict).toHaveBeenCalledWith('b', 2)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "get() does not refresh recency (an impl that evicts by raw insertion "
            "order would wrongly evict 'a')\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_has_does_not_refresh_recency(self):
        """has() must NOT protect a key from eviction (probing is recency-neutral)."""
        rel = _write_spec(
            "zz_driver_has_norefresh",
            """
            import { expect, test, vi } from 'vitest'
            import { LruCache } from '../lruCache'

            test('has does not refresh', () => {
              const onEvict = vi.fn()
              const c = new LruCache<string, number>({ max: 2, onEvict })
              c.set('a', 1)
              c.set('b', 2)
              // probing 'a' with has() must NOT make it most-recently-used
              expect(c.has('a')).toBe(true)
              c.set('c', 3)   // 'a' is still LRU -> evicted

              expect(c.has('a')).toBe(false)
              expect(c.has('b')).toBe(true)
              expect(c.has('c')).toBe(true)
              expect(onEvict).toHaveBeenCalledTimes(1)
              expect(onEvict).toHaveBeenCalledWith('a', 1)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "has() wrongly refreshed recency (must be a pure probe)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_update_existing_key_no_eviction(self):
        """Re-setting an existing key on a full cache updates value, evicts nothing."""
        rel = _write_spec(
            "zz_driver_update",
            """
            import { expect, test, vi } from 'vitest'
            import { LruCache } from '../lruCache'

            test('update existing key does not evict', () => {
              const onEvict = vi.fn()
              const c = new LruCache<string, number>({ max: 2, onEvict })
              c.set('a', 1)
              c.set('b', 2)
              c.set('a', 99)   // update, not insert -> no eviction

              expect(c.size).toBe(2)
              expect(c.get('a')).toBe(99)
              expect(c.get('b')).toBe(2)
              expect(onEvict).not.toHaveBeenCalled()

              // and the update also refreshed 'a' to MRU, so next insert evicts 'b'
              c.set('c', 3)
              expect(c.has('b')).toBe(false)
              expect(c.has('a')).toBe(true)
              expect(onEvict).toHaveBeenCalledTimes(1)
              expect(onEvict).toHaveBeenCalledWith('b', 2)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "updating an existing key triggered eviction or did not refresh it\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_delete_semantics_and_no_evict_callback(self):
        """delete returns true/false correctly and never calls onEvict."""
        rel = _write_spec(
            "zz_driver_delete",
            """
            import { expect, test, vi } from 'vitest'
            import { LruCache } from '../lruCache'

            test('delete semantics', () => {
              const onEvict = vi.fn()
              const c = new LruCache<string, number>({ max: 3, onEvict })
              c.set('a', 1)
              c.set('b', 2)

              expect(c.delete('a')).toBe(true)    // present
              expect(c.delete('a')).toBe(false)   // already gone
              expect(c.delete('zzz')).toBe(false) // never existed

              expect(c.has('a')).toBe(false)
              expect(c.get('a')).toBeUndefined()
              expect(c.size).toBe(1)
              expect(c.has('b')).toBe(true)
              // delete must NOT be treated as eviction
              expect(onEvict).not.toHaveBeenCalled()
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "delete() return values wrong or it wrongly fired onEvict\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_clear_empties_without_evict_callback(self):
        """clear() removes all entries, resets size to 0, and never calls onEvict."""
        rel = _write_spec(
            "zz_driver_clear",
            """
            import { expect, test, vi } from 'vitest'
            import { LruCache } from '../lruCache'

            test('clear does not evict', () => {
              const onEvict = vi.fn()
              const c = new LruCache<string, number>({ max: 3, onEvict })
              c.set('a', 1)
              c.set('b', 2)
              c.set('c', 3)
              expect(c.size).toBe(3)

              c.clear()
              expect(c.size).toBe(0)
              expect(c.has('a')).toBe(false)
              expect(c.has('b')).toBe(false)
              expect(c.has('c')).toBe(false)
              expect(c.get('b')).toBeUndefined()
              expect(onEvict).not.toHaveBeenCalled()

              // cache is reusable after clear
              c.set('x', 10)
              expect(c.get('x')).toBe(10)
              expect(c.size).toBe(1)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "clear() left entries, wrong size, or wrongly fired onEvict\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_max_one_holds_only_mru(self):
        """max:1 keeps only the single most-recently-used entry; size never exceeds max."""
        rel = _write_spec(
            "zz_driver_max1",
            """
            import { expect, test, vi } from 'vitest'
            import { LruCache } from '../lruCache'

            test('max 1', () => {
              const onEvict = vi.fn()
              const c = new LruCache<string, number>({ max: 1, onEvict })
              c.set('a', 1)
              expect(c.size).toBe(1)
              c.set('b', 2)   // evict 'a'
              expect(c.size).toBe(1)
              expect(c.has('a')).toBe(false)
              expect(c.get('b')).toBe(2)
              expect(onEvict).toHaveBeenCalledTimes(1)
              expect(onEvict).toHaveBeenNthCalledWith(1, 'a', 1)

              c.set('c', 3)   // evict 'b'
              expect(c.size).toBe(1)
              expect(c.get('c')).toBe(3)
              expect(onEvict).toHaveBeenCalledTimes(2)
              expect(onEvict).toHaveBeenNthCalledWith(2, 'b', 2)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "max:1 cache does not keep only the MRU entry / size exceeded max\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_eviction_lru_first_order_multiple(self):
        """Multiple insertions evict strictly LRU-first; onEvict args track that order."""
        rel = _write_spec(
            "zz_driver_order",
            """
            import { expect, test, vi } from 'vitest'
            import { LruCache } from '../lruCache'

            test('lru-first eviction order over many inserts', () => {
              const onEvict = vi.fn()
              const c = new LruCache<string, number>({ max: 3, onEvict })
              c.set('a', 1)
              c.set('b', 2)
              c.set('c', 3)
              // touch 'a' so recency (LRU -> MRU) is: b, c, a
              expect(c.get('a')).toBe(1)

              c.set('d', 4)   // evict LRU 'b'
              c.set('e', 5)   // now order was c, a, d -> evict 'c'

              expect(onEvict).toHaveBeenCalledTimes(2)
              expect(onEvict).toHaveBeenNthCalledWith(1, 'b', 2)
              expect(onEvict).toHaveBeenNthCalledWith(2, 'c', 3)
              expect(c.size).toBe(3)
              expect(c.has('a')).toBe(true)
              expect(c.has('d')).toBe(true)
              expect(c.has('e')).toBe(true)
              expect(c.has('b')).toBe(false)
              expect(c.has('c')).toBe(false)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "multi-insert eviction did not follow strict LRU-first order\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_no_onevict_callback_is_optional(self):
        """A cache built without onEvict still evicts correctly and does not throw."""
        rel = _write_spec(
            "zz_driver_no_callback",
            """
            import { expect, test } from 'vitest'
            import { LruCache } from '../lruCache'

            test('onEvict optional', () => {
              const c = new LruCache<string, number>({ max: 2 })
              expect(() => {
                c.set('a', 1)
                c.set('b', 2)
                c.set('c', 3)   // evicts 'a'; must not throw without a callback
              }).not.toThrow()
              expect(c.size).toBe(2)
              expect(c.has('a')).toBe(false)
              expect(c.get('b')).toBe(2)
              expect(c.get('c')).toBe(3)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "cache without onEvict threw or evicted incorrectly\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_agent_delivered_spec_passes(self):
        """The agent's own delivered lruCache.spec.ts must pass under native vitest."""
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        rel = os.path.relpath(AGENT_SPEC, REPO_DIR)
        res = _vitest(rel)
        assert res.returncode == 0, (
            "agent's lruCache.spec.ts does not pass\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
        combined = (res.stdout + res.stderr)
        assert "no test" not in combined.lower(), "agent spec contains no tests"
