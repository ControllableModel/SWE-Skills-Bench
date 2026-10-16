"""Benchmark verification for skill: jest-advanced-patterns (variant ext6).

Task: Add a bounded least-recently-used (LRU) cache to the React monorepo's
``shared`` package (``packages/shared/createLRUCache.js``) plus a deterministic
Jest suite (``packages/shared/__tests__/createLRUCache-test.js``).

This variant is DISTINCT from ext1 (an async resource loader). Here the
deliverable is a synchronous, capacity-bounded LRU cache exposing
``get / set / has / delete / keys / size`` with strict recency + eviction
semantics and a ``RangeError`` guard on the capacity argument.

Strategy
--------
L1 cases assert the two deliverable files exist, expose a default export, and
that the implementation imports/requires no other module (a hard Acceptance
constraint).

L2 cases independently EXERCISE the real cache behavior. Rather than trusting
the agent's own test file, each L2 method writes ITS OWN focused Jest probe
spec into ``packages/shared/__tests__/`` and runs that single spec through the
repo's native Jest CLI (``yarn test <path>`` -> ``node scripts/jest/jest-cli.js
<path>``, which forwards the path as a testPathPattern). Every probe drives the
cache deterministically (no timers, network, or randomness) and deep-validates
exactly ONE behavior from the requirement doc, asserting precise ``keys()``
ordering and exact ``size()`` values with array/value equality matchers:

  * insertion + eviction of the LRU entry on capacity overflow
  * ``get`` refreshes recency so a different entry is evicted next
  * updating an existing key: size unchanged + recency refreshed
  * ``get`` miss returns undefined and changes nothing
  * ``has`` reports membership WITHOUT affecting recency
  * ``delete`` returns true then false; deleted key not evicted/counted
  * ``keys()`` ordering is least- to most-recently-used
  * ``size()`` never exceeds capacity across a long sequence
  * capacity-1 degenerate cache evicts on every new insert
  * ``RangeError`` for non-positive / non-integer / non-number capacity

Because each behavior is its own probe spec and its own pytest method, a
partial / buggy or stub solution (e.g. a plain Map with no eviction, or a cache
that ignores recency on ``get``) fails the SPECIFIC behavior it got wrong. We
also confirm the agent's own suite runs green via the exact Acceptance command.

Module resolution note: this repo resolves ``shared/<name>`` via Jest haste
(``roots: ['<rootDir>/packages', ...]``), so the probe ``require``s
``'shared/createLRUCache'`` exactly like the repo's own shared tests.
"""

import os
import re
import subprocess
import textwrap

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies  # noqa: F401
except Exception:  # pragma: no cover - utils may be absent locally
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/react"

SRC_REL = "packages/shared/createLRUCache.js"
AGENT_TEST_REL = "packages/shared/__tests__/createLRUCache-test.js"

# Each probe is written under __tests__ (so the repo's testRegex matches it) and
# is removed after the run. Unique names avoid cross-test collisions.
PROBE_DIR_REL = "packages/shared/__tests__"
PROBE_PREFIX = "createLRUCache-probe-"


def _src_path():
    return os.path.join(REPO_DIR, SRC_REL)


def _agent_test_path():
    return os.path.join(REPO_DIR, AGENT_TEST_REL)


def _probe_rel(name):
    return os.path.join(PROBE_DIR_REL, PROBE_PREFIX + name + ".bench-test.js")


def _probe_abs(name):
    return os.path.join(REPO_DIR, _probe_rel(name))


def _read_src():
    with open(_src_path()) as fh:
        return fh.read()


def _yarn_test(path_rel, timeout=300):
    """Run the repo's native Jest CLI scoped to a single test file.

    ``yarn test <path>`` invokes ``node ./scripts/jest/jest-cli.js <path>``;
    the trailing path is forwarded to Jest as a testPathPattern so only that
    one spec executes.
    """
    return subprocess.run(
        ["yarn", "test", path_rel],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _jest_passed(result):
    """Require real test execution plus an explicit green summary."""
    out = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.returncode != 0:
        return False, out
    if re.search(r"No tests found", out):
        return False, out
    if re.search(r"Tests:\s+.*\bfailed", out):
        return False, out
    if not re.search(r"Tests:\s+\d+ passed", out) and not re.search(r"PASS\b", out):
        return False, out
    return True, out


# Shared JS preamble: a deterministic helper that loads the factory exactly the
# way the repo's own shared tests resolve sibling modules. No timers, network,
# or randomness anywhere. Injected verbatim into each probe spec.
_PREAMBLE = """\
'use strict';

function makeCache(capacity) {
  return require('shared/createLRUCache').default(capacity);
}

function factory() {
  return require('shared/createLRUCache').default;
}
"""


def _make_probe(body):
    """Wrap a single-behavior ``it(...)`` body in the shared preamble."""
    return _PREAMBLE + "\n" + textwrap.dedent(body) + "\n"


def _run_probe(name, body, timeout=300):
    """Write a one-behavior probe spec, run it via native Jest, clean up."""
    rel = _probe_rel(name)
    abs_path = _probe_abs(name)
    with open(abs_path, "w") as fh:
        fh.write(_make_probe(body))
    try:
        result = _yarn_test(rel, timeout=timeout)
    finally:
        try:
            os.remove(abs_path)
        except OSError:
            pass
    return result


@pytest.fixture(scope="module", autouse=True)
def _deps():
    """Ensure JS toolchain deps are present, and sweep stray probe files."""
    node_modules = os.path.join(REPO_DIR, "node_modules")
    jest_marker = os.path.join(node_modules, "chalk")
    if not os.path.isdir(jest_marker):
        try:
            subprocess.run(
                ["yarn", "install", "--frozen-lockfile"],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=1800,
            )
        except Exception:
            pass
        if not os.path.isdir(jest_marker) and ensure_npm_dependencies is not None:
            try:
                ensure_npm_dependencies(REPO_DIR)
            except Exception:
                pass
    yield
    probe_dir = os.path.join(REPO_DIR, PROBE_DIR_REL)
    try:
        for fname in os.listdir(probe_dir):
            if fname.startswith(PROBE_PREFIX):
                try:
                    os.remove(os.path.join(probe_dir, fname))
                except OSError:
                    pass
    except OSError:
        pass


class TestJestAdvancedPatterns:
    REPO_DIR = REPO_DIR

    # -----------------------------------------------------------------------
    # L1 — deliverables exist and respect the structural constraints.
    # -----------------------------------------------------------------------
    def test_cache_source_exists(self):
        """L1: the LRU cache module file exists and is non-empty."""
        path = _src_path()
        assert os.path.isfile(path), f"missing deliverable: {SRC_REL}"
        assert os.path.getsize(path) > 0, "cache source is empty"

    def test_agent_test_file_exists(self):
        """L1: the agent's Jest test suite file exists and is non-empty."""
        path = _agent_test_path()
        assert os.path.isfile(path), f"missing deliverable: {AGENT_TEST_REL}"
        assert os.path.getsize(path) > 0, "agent test file is empty"

    def test_cache_has_default_export(self):
        """L1: the cache module exposes a default export (the factory)."""
        src = _read_src()
        assert "export default" in src or "module.exports" in src, (
            "cache must export the factory by default"
        )

    def test_cache_imports_no_other_module(self):
        """L1: hard constraint — the module imports/requires no other module."""
        src = _read_src()
        no_block = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
        no_line = re.sub(r"//[^\n]*", "", no_block)
        assert not re.search(r"^\s*import\s", no_line, flags=re.MULTILINE), (
            "cache must contain no `import` statement"
        )
        assert not re.search(r"\brequire\s*\(", no_line), (
            "cache must not `require` any other module"
        )

    # -----------------------------------------------------------------------
    # L2 — each behavior gets its OWN independent probe spec run via Jest.
    # -----------------------------------------------------------------------
    def test_insertion_and_lru_eviction_on_overflow(self):
        """L2: inserting beyond capacity evicts the least-recently-used entry.

        Capacity 2: set a, set b, set c -> 'a' (LRU) evicted; has('a') false;
        keys() is ['b','c'] (LRU->MRU); size() is 2. A Map-without-eviction stub
        would over-grow and fail the size/keys assertions.
        """
        result = _run_probe(
            "evict",
            """
            it('overflow evicts the LRU entry and bounds size', () => {
              const c = makeCache(2);
              c.set('a', 1);
              c.set('b', 2);
              c.set('c', 3);
              expect(c.has('a')).toBe(false);
              expect(c.has('b')).toBe(true);
              expect(c.has('c')).toBe(true);
              expect(c.get('a')).toBeUndefined();
              expect(c.keys()).toEqual(['b', 'c']);
              expect(c.size()).toBe(2);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"eviction probe failed:\n{out[-4000:]}"

    def test_get_refreshes_recency_changes_eviction_victim(self):
        """L2: ``get`` marks a key most-recently-used, changing who is evicted.

        Capacity 2: set a, set b, get a, set c -> 'b' is now LRU and evicted;
        keys() is ['a','c']. A stub that ignores recency on get would wrongly
        evict 'a' and fail this.
        """
        result = _run_probe(
            "get-recency",
            """
            it('get refreshes recency so a different entry is evicted', () => {
              const c = makeCache(2);
              c.set('a', 1);
              c.set('b', 2);
              expect(c.get('a')).toBe(1);
              c.set('c', 3);
              expect(c.has('b')).toBe(false);
              expect(c.has('a')).toBe(true);
              expect(c.has('c')).toBe(true);
              expect(c.keys()).toEqual(['a', 'c']);
              expect(c.size()).toBe(2);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"get-recency probe failed:\n{out[-4000:]}"

    def test_update_existing_key_keeps_size_and_refreshes_recency(self):
        """L2: updating an existing key does not change size and refreshes recency.

        Capacity 2: set a, set b, set a (update) -> size stays 2, 'a' becomes
        MRU (keys ['b','a']); then set c evicts 'b' (now LRU), keys ['a','c'].
        """
        result = _run_probe(
            "update",
            """
            it('updating an existing key keeps size and refreshes recency', () => {
              const c = makeCache(2);
              c.set('a', 1);
              c.set('b', 2);
              c.set('a', 99);
              expect(c.size()).toBe(2);
              expect(c.get('a')).toBe(99);
              expect(c.keys()).toEqual(['b', 'a']);
              c.set('c', 3);
              expect(c.has('b')).toBe(false);
              expect(c.keys()).toEqual(['a', 'c']);
              expect(c.size()).toBe(2);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"update probe failed:\n{out[-4000:]}"

    def test_get_miss_returns_undefined_and_no_recency_change(self):
        """L2: a ``get`` miss returns undefined and changes nothing.

        Capacity 2: set a, set b, get('zzz') (miss) -> undefined; recency order
        unchanged so set c still evicts 'a' (the true LRU); keys ['b','c'].
        """
        result = _run_probe(
            "get-miss",
            """
            it('get miss returns undefined and does not alter recency', () => {
              const c = makeCache(2);
              c.set('a', 1);
              c.set('b', 2);
              expect(c.get('zzz')).toBeUndefined();
              expect(c.size()).toBe(2);
              expect(c.keys()).toEqual(['a', 'b']);
              c.set('c', 3);
              expect(c.has('a')).toBe(false);
              expect(c.keys()).toEqual(['b', 'c']);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"get-miss probe failed:\n{out[-4000:]}"

    def test_has_does_not_affect_recency(self):
        """L2: ``has`` reports membership without touching recency.

        Capacity 2: set a, set b, has('a') (true) -> recency unchanged so 'a'
        is still LRU; set c evicts 'a'; keys ['b','c']. A stub that bumps
        recency in has() would wrongly keep 'a'.
        """
        result = _run_probe(
            "has-neutral",
            """
            it('has reports membership without affecting recency', () => {
              const c = makeCache(2);
              c.set('a', 1);
              c.set('b', 2);
              expect(c.has('a')).toBe(true);
              expect(c.has('nope')).toBe(false);
              c.set('c', 3);
              expect(c.has('a')).toBe(false);
              expect(c.keys()).toEqual(['b', 'c']);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"has-neutral probe failed:\n{out[-4000:]}"

    def test_delete_returns_true_then_false_and_frees_slot(self):
        """L2: ``delete`` returns true once, false thereafter, and frees a slot.

        delete on a present key returns true and decrements size; deleting again
        returns false; a deleted key is no longer counted or evicted, so after
        delete the cache has room for a new key without eviction.
        """
        result = _run_probe(
            "delete",
            """
            it('delete returns true then false and frees the slot', () => {
              const c = makeCache(2);
              c.set('a', 1);
              c.set('b', 2);
              expect(c.delete('a')).toBe(true);
              expect(c.size()).toBe(1);
              expect(c.has('a')).toBe(false);
              expect(c.delete('a')).toBe(false);
              expect(c.delete('never')).toBe(false);
              c.set('c', 3);
              expect(c.size()).toBe(2);
              expect(c.has('b')).toBe(true);
              expect(c.has('c')).toBe(true);
              expect(c.keys()).toEqual(['b', 'c']);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"delete probe failed:\n{out[-4000:]}"

    def test_keys_ordering_is_lru_to_mru(self):
        """L2: ``keys()`` is ordered least- to most-recently-used.

        With capacity 3 and a mix of set/get, the exact LRU->MRU ordering is
        asserted. set a,b,c then get('a') -> order ['b','c','a']; set d evicts
        'b'; keys ['c','a','d'].
        """
        result = _run_probe(
            "keys-order",
            """
            it('keys() is ordered least- to most-recently-used', () => {
              const c = makeCache(3);
              c.set('a', 1);
              c.set('b', 2);
              c.set('c', 3);
              expect(c.keys()).toEqual(['a', 'b', 'c']);
              expect(c.get('a')).toBe(1);
              expect(c.keys()).toEqual(['b', 'c', 'a']);
              c.set('d', 4);
              expect(c.has('b')).toBe(false);
              expect(c.keys()).toEqual(['c', 'a', 'd']);
              expect(c.size()).toBe(3);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"keys-order probe failed:\n{out[-4000:]}"

    def test_size_never_exceeds_capacity_over_long_sequence(self):
        """L2: ``size()`` never exceeds capacity across many inserts.

        Insert 50 distinct keys into a capacity-4 cache; size() must equal 4
        afterward and only the last 4 inserted keys survive in MRU order.
        """
        result = _run_probe(
            "size-bound",
            """
            it('size never exceeds capacity over a long insert sequence', () => {
              const c = makeCache(4);
              for (let i = 0; i < 50; i++) {
                c.set('k' + i, i);
                expect(c.size()).toBeLessThanOrEqual(4);
              }
              expect(c.size()).toBe(4);
              expect(c.keys()).toEqual(['k46', 'k47', 'k48', 'k49']);
              expect(c.has('k45')).toBe(false);
              expect(c.get('k49')).toBe(49);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"size-bound probe failed:\n{out[-4000:]}"

    def test_capacity_one_evicts_on_every_new_insert(self):
        """L2: a capacity-1 cache holds only the most-recent key.

        set a then set b -> 'a' evicted, size 1, keys ['b']; updating 'b' keeps
        size 1 and the value; a get of the surviving key returns its value.
        """
        result = _run_probe(
            "cap-one",
            """
            it('capacity 1 keeps only the most-recently-set key', () => {
              const c = makeCache(1);
              c.set('a', 1);
              expect(c.keys()).toEqual(['a']);
              c.set('b', 2);
              expect(c.has('a')).toBe(false);
              expect(c.size()).toBe(1);
              expect(c.keys()).toEqual(['b']);
              c.set('b', 22);
              expect(c.size()).toBe(1);
              expect(c.get('b')).toBe(22);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"cap-one probe failed:\n{out[-4000:]}"

    def test_factory_throws_rangeerror_for_invalid_capacity(self):
        """L2: the factory throws a RangeError for non-positive-integer capacity.

        0, negative, non-integer, NaN, and non-number capacities must each
        cause createLRUCache to throw a RangeError; a valid positive integer
        must not throw.
        """
        result = _run_probe(
            "rangeerror",
            """
            it('factory throws RangeError for invalid capacity', () => {
              const f = factory();
              expect(() => f(0)).toThrow(RangeError);
              expect(() => f(-1)).toThrow(RangeError);
              expect(() => f(1.5)).toThrow(RangeError);
              expect(() => f(NaN)).toThrow(RangeError);
              expect(() => f('2')).toThrow(RangeError);
              expect(() => f(undefined)).toThrow(RangeError);
              expect(() => f(3)).not.toThrow();
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"RangeError-guard probe failed:\n{out[-4000:]}"

    # -----------------------------------------------------------------------
    # L2 — the agent's own suite must pass via the spec'd command.
    # -----------------------------------------------------------------------
    def test_agent_suite_passes(self):
        """L2: the agent's own Jest suite passes via the Acceptance command.

        Mirrors the Acceptance Criteria command exactly:
        ``yarn test packages/shared/__tests__/createLRUCache-test.js``.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        ok, out = _jest_passed(result)
        assert ok, f"agent suite did not pass green:\n{out[-4000:]}"

    def test_agent_suite_has_multiple_independent_cases(self):
        """L2: the agent suite must contain several independent passing cases.

        The requirement mandates independent cases per behavior, so a single
        trivial test would not satisfy it; require a multi-case green run.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        out = (result.stdout or "") + "\n" + (result.stderr or "")
        assert result.returncode == 0, f"agent suite nonzero rc:\n{out[-3000:]}"
        m = re.search(r"Tests:\s+(\d+) passed", out)
        assert m is not None, f"no passing summary in agent run:\n{out[-3000:]}"
        assert int(m.group(1)) >= 5, (
            f"agent suite should have multiple cases, saw {m.group(1)}"
        )
