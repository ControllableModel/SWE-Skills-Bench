"""Benchmark verification for skill: jest-advanced-patterns.

Task: Add a deduplicating async resource loader to the React monorepo's
``shared`` package (``packages/shared/createResourceLoader.js``) plus a
deterministic Jest suite (``packages/shared/__tests__/createResourceLoader-test.js``).

Strategy
--------
L1 cases assert the two deliverable files exist, expose a default export, and
that the implementation imports no other module (a hard constraint from the
requirement doc).

L2 cases independently EXERCISE the real loader behavior. Rather than trusting
the agent's own test file, each L2 method writes ITS OWN focused Jest probe
spec into ``packages/shared/__tests__/`` and runs that single spec through the
repo's native Jest CLI (``yarn test <path>`` -> ``node scripts/jest/jest-cli.js
<path>``, which forwards the path as a testPathPattern). Every probe drives the
loader with a fully controllable, deterministic fetcher (no timers, network, or
randomness) and deep-validates exactly ONE behavior from the requirement doc:

  * concurrent de-duplication of the same key
  * success caching (no re-fetch after resolve)
  * per-key isolation
  * rejection propagation WITHOUT caching (retry re-fetches)
  * peek: undefined while never/pending/failed, value after success
  * peek never invokes the fetcher and never returns a promise
  * invalidate returns true for cached / false for absent keys
  * invalidate forces the next load to re-fetch
  * invalidating a pending key is harmless to the in-flight promise
  * clear drops all cached values and forces re-fetch
  * the TypeError guard for a non-function fetcher

Because each behavior is its own probe spec and its own pytest method, a
partial / buggy solution fails the SPECIFIC behavior it got wrong instead of
one monolithic probe. We also confirm the agent's own suite runs green via the
exact Acceptance-Criteria command.

Module resolution note: this repo resolves ``shared/<name>`` via Jest haste
(``roots: ['<rootDir>/packages', ...]``), so the probe ``require``s
``'shared/createResourceLoader'`` exactly like the repo's own shared tests.
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

SRC_REL = "packages/shared/createResourceLoader.js"
AGENT_TEST_REL = "packages/shared/__tests__/createResourceLoader-test.js"

# Each probe is written under __tests__ (so the repo's testRegex matches it) and
# is removed after the run. Unique names avoid cross-test collisions.
PROBE_DIR_REL = "packages/shared/__tests__"
PROBE_PREFIX = "createResourceLoader-probe-"


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


# Shared JS preamble: a deterministic, manually-driven fetcher. It records every
# call (key + order) and exposes resolve/reject so probes never touch timers,
# the network, or randomness. Injected verbatim into each probe spec.
_FETCHER_PREAMBLE = """\
'use strict';

function makeFetcher() {
  const calls = [];
  const deferreds = {};
  function fetcher(key) {
    calls.push(key);
    return new Promise((resolve, reject) => {
      deferreds[key] = deferreds[key] || [];
      deferreds[key].push({resolve, reject});
    });
  }
  fetcher.calls = calls;
  fetcher.countFor = key => calls.filter(k => k === key).length;
  fetcher.resolve = (key, value) => {
    const list = deferreds[key] || [];
    list.forEach(d => d.resolve(value));
    deferreds[key] = [];
  };
  fetcher.reject = (key, err) => {
    const list = deferreds[key] || [];
    list.forEach(d => d.reject(err));
    deferreds[key] = [];
  };
  return fetcher;
}

function load() {
  return require('shared/createResourceLoader').default;
}
"""


def _make_probe(body):
    """Wrap a single-behavior ``it(...)`` body in the shared preamble."""
    return _FETCHER_PREAMBLE + "\n" + textwrap.dedent(body) + "\n"


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
    def test_loader_source_exists(self):
        """L1: the loader module file exists and is non-empty."""
        path = _src_path()
        assert os.path.isfile(path), f"missing deliverable: {SRC_REL}"
        assert os.path.getsize(path) > 0, "loader source is empty"

    def test_agent_test_file_exists(self):
        """L1: the agent's Jest test suite file exists and is non-empty."""
        path = _agent_test_path()
        assert os.path.isfile(path), f"missing deliverable: {AGENT_TEST_REL}"
        assert os.path.getsize(path) > 0, "agent test file is empty"

    def test_loader_has_default_export(self):
        """L1: the loader exposes a default export (the factory)."""
        src = _read_src()
        assert "export default" in src or "module.exports" in src, (
            "loader must export the factory by default"
        )

    def test_loader_imports_no_other_module(self):
        """L1: hard constraint — the module imports/requires no other module."""
        src = _read_src()
        no_block = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
        no_line = re.sub(r"//[^\n]*", "", no_block)
        assert not re.search(r"^\s*import\s", no_line, flags=re.MULTILINE), (
            "loader must contain no `import` statement"
        )
        assert not re.search(r"\brequire\s*\(", no_line), (
            "loader must not `require` any other module"
        )

    # -----------------------------------------------------------------------
    # L2 — each behavior gets its OWN independent probe spec run via Jest.
    # -----------------------------------------------------------------------
    def test_concurrent_loads_dedupe_to_single_fetch(self):
        """L2: two concurrent load(key) for the same key share one fetch.

        While the first load is pending, a second load of the same key must
        NOT call the fetcher again; both awaited promises resolve to the one
        fetched value.
        """
        result = _run_probe(
            "dedupe",
            """
            it('concurrent same-key loads dedupe to one fetch', async () => {
              const fetcher = makeFetcher();
              const loader = load()(fetcher);
              const p1 = loader.load('a');
              const p2 = loader.load('a');
              expect(fetcher.countFor('a')).toBe(1);
              fetcher.resolve('a', 'VALUE_A');
              const [r1, r2] = await Promise.all([p1, p2]);
              expect(r1).toBe('VALUE_A');
              expect(r2).toBe('VALUE_A');
              expect(fetcher.countFor('a')).toBe(1);
              expect(fetcher.calls).toEqual(['a']);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"dedupe probe failed:\n{out[-4000:]}"

    def test_resolved_value_is_cached(self):
        """L2: after a key resolves, a later load resolves from cache.

        The second load of an already-resolved key must NOT re-invoke the
        fetcher and must return the cached value.
        """
        result = _run_probe(
            "cache",
            """
            it('resolved value is cached; later load does not re-fetch', async () => {
              const fetcher = makeFetcher();
              const loader = load()(fetcher);
              const p = loader.load('a');
              fetcher.resolve('a', 42);
              await expect(p).resolves.toBe(42);
              const again = await loader.load('a');
              expect(again).toBe(42);
              expect(fetcher.countFor('a')).toBe(1);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"caching probe failed:\n{out[-4000:]}"

    def test_distinct_keys_are_isolated(self):
        """L2: concurrent loads of different keys each fetch exactly once.

        Keys are independent: load('a') and load('b') in flight together must
        produce one fetch per distinct key and resolve to their own values.
        """
        result = _run_probe(
            "isolation",
            """
            it('distinct keys are isolated; one fetch per key', async () => {
              const fetcher = makeFetcher();
              const loader = load()(fetcher);
              const pa = loader.load('a');
              const pb = loader.load('b');
              expect(fetcher.countFor('a')).toBe(1);
              expect(fetcher.countFor('b')).toBe(1);
              fetcher.resolve('a', 'A');
              fetcher.resolve('b', 'B');
              await expect(pa).resolves.toBe('A');
              await expect(pb).resolves.toBe('B');
              expect(fetcher.calls.slice().sort()).toEqual(['a', 'b']);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"isolation probe failed:\n{out[-4000:]}"

    def test_rejection_propagates_to_caller(self):
        """L2: a fetcher rejection rejects load(key) with the same error.

        The returned promise must reject with the exact error object thrown by
        the fetcher (not a wrapped/swallowed one).
        """
        result = _run_probe(
            "reject-propagate",
            """
            it('rejection propagates with the same error', async () => {
              const fetcher = makeFetcher();
              const loader = load()(fetcher);
              const boom = new Error('boom-x');
              const p = loader.load('x');
              fetcher.reject('x', boom);
              await expect(p).rejects.toBe(boom);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"rejection-propagation probe failed:\n{out[-4000:]}"

    def test_rejection_is_not_cached_retry_refetches(self):
        """L2: a failure is not memoized — a later load re-invokes the fetcher.

        After a rejected load, peek(key) is undefined and a subsequent load(key)
        calls the fetcher again and can succeed.
        """
        result = _run_probe(
            "reject-no-cache",
            """
            it('failure is not cached; retry re-fetches and can succeed', async () => {
              const fetcher = makeFetcher();
              const loader = load()(fetcher);
              const boom = new Error('boom-x');
              const p = loader.load('x');
              fetcher.reject('x', boom);
              await expect(p).rejects.toBe(boom);
              expect(loader.peek('x')).toBeUndefined();
              const p2 = loader.load('x');
              expect(fetcher.countFor('x')).toBe(2);
              fetcher.resolve('x', 'ok-now');
              await expect(p2).resolves.toBe('ok-now');
              expect(loader.peek('x')).toBe('ok-now');
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"rejection-no-cache probe failed:\n{out[-4000:]}"

    def test_peek_states_undefined_then_value(self):
        """L2: peek is undefined for never/pending keys and the value after success.

        peek must return undefined before any load, while a load is pending,
        and the cached value only once the load has resolved.
        """
        result = _run_probe(
            "peek-states",
            """
            it('peek: undefined for never/pending, value after success', async () => {
              const fetcher = makeFetcher();
              const loader = load()(fetcher);
              expect(loader.peek('a')).toBeUndefined();
              const p = loader.load('a');
              expect(loader.peek('a')).toBeUndefined();
              fetcher.resolve('a', 'PV');
              await p;
              expect(loader.peek('a')).toBe('PV');
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"peek-states probe failed:\n{out[-4000:]}"

    def test_peek_never_fetches_nor_returns_promise(self):
        """L2: peek must not invoke the fetcher and must never return a promise.

        Calling peek any number of times must not increase the fetch count, and
        a peeked, resolved value must be a plain value (never a Promise).
        """
        result = _run_probe(
            "peek-pure",
            """
            it('peek never fetches and never returns a promise', async () => {
              const fetcher = makeFetcher();
              const loader = load()(fetcher);
              loader.peek('a');
              loader.peek('a');
              expect(fetcher.calls.length).toBe(0);
              const p = loader.load('a');
              const before = fetcher.calls.length;
              loader.peek('a');
              expect(fetcher.calls.length).toBe(before);
              const pending = loader.peek('a');
              expect(pending).toBeUndefined();
              fetcher.resolve('a', {ok: true});
              await p;
              const peeked = loader.peek('a');
              expect(peeked).not.toBeInstanceOf(Promise);
              expect(peeked).toEqual({ok: true});
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"peek-pure probe failed:\n{out[-4000:]}"

    def test_invalidate_returns_true_for_cached_false_for_absent(self):
        """L2: invalidate returns true iff a cached value was present.

        invalidate on a cached key returns true and removes it; invalidate on a
        never-loaded key returns false.
        """
        result = _run_probe(
            "invalidate-bool",
            """
            it('invalidate returns true for cached, false for absent', async () => {
              const fetcher = makeFetcher();
              const loader = load()(fetcher);
              const p = loader.load('a');
              fetcher.resolve('a', 'AV');
              await p;
              expect(loader.invalidate('never-loaded')).toBe(false);
              expect(loader.invalidate('a')).toBe(true);
              expect(loader.peek('a')).toBeUndefined();
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"invalidate-bool probe failed:\n{out[-4000:]}"

    def test_invalidate_forces_refetch(self):
        """L2: after invalidate(key), the next load(key) re-invokes the fetcher.

        Invalidation must clear the cache so the subsequent load triggers a
        fresh fetch and resolves to the new value.
        """
        result = _run_probe(
            "invalidate-refetch",
            """
            it('next load after invalidate re-fetches', async () => {
              const fetcher = makeFetcher();
              const loader = load()(fetcher);
              const p = loader.load('a');
              fetcher.resolve('a', 'AV');
              await p;
              expect(loader.invalidate('a')).toBe(true);
              const p2 = loader.load('a');
              expect(fetcher.countFor('a')).toBe(2);
              fetcher.resolve('a', 'AV2');
              await expect(p2).resolves.toBe('AV2');
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"invalidate-refetch probe failed:\n{out[-4000:]}"

    def test_invalidate_pending_key_is_harmless(self):
        """L2: invalidating a still-pending key does not disturb the in-flight load.

        Nothing is cached while pending, so invalidate returns false, the
        in-flight promise still resolves, and no extra fetch is issued.
        """
        result = _run_probe(
            "invalidate-pending",
            """
            it('invalidating a pending key is harmless', async () => {
              const fetcher = makeFetcher();
              const loader = load()(fetcher);
              const p = loader.load('a');
              expect(loader.invalidate('a')).toBe(false);
              fetcher.resolve('a', 'still-good');
              await expect(p).resolves.toBe('still-good');
              expect(fetcher.countFor('a')).toBe(1);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"invalidate-pending probe failed:\n{out[-4000:]}"

    def test_clear_drops_all_and_forces_refetch(self):
        """L2: clear() empties the cache so every peek is undefined and loads re-fetch.

        After several successful loads, clear() must make peek undefined for all
        keys and cause the next load of any key to re-invoke the fetcher.
        """
        result = _run_probe(
            "clear",
            """
            it('clear drops all cached values and forces re-fetch', async () => {
              const fetcher = makeFetcher();
              const loader = load()(fetcher);
              const pa = loader.load('a');
              const pb = loader.load('b');
              fetcher.resolve('a', 'A');
              fetcher.resolve('b', 'B');
              await Promise.all([pa, pb]);
              expect(loader.peek('a')).toBe('A');
              expect(loader.peek('b')).toBe('B');
              loader.clear();
              expect(loader.peek('a')).toBeUndefined();
              expect(loader.peek('b')).toBeUndefined();
              const pa2 = loader.load('a');
              expect(fetcher.countFor('a')).toBe(2);
              fetcher.resolve('a', 'A2');
              await expect(pa2).resolves.toBe('A2');
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"clear probe failed:\n{out[-4000:]}"

    def test_factory_throws_typeerror_for_non_function_fetcher(self):
        """L2: the factory throws a TypeError when fetcher is not a function.

        undefined, a number, and an object must each cause createResourceLoader
        to throw a TypeError at construction time.
        """
        result = _run_probe(
            "typeerror",
            """
            it('factory throws TypeError for a non-function fetcher', () => {
              const factory = load();
              expect(() => factory(undefined)).toThrow(TypeError);
              expect(() => factory(123)).toThrow(TypeError);
              expect(() => factory({})).toThrow(TypeError);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"TypeError-guard probe failed:\n{out[-4000:]}"

    # -----------------------------------------------------------------------
    # L2 — the agent's own suite must pass via the spec'd command.
    # -----------------------------------------------------------------------
    def test_agent_suite_passes(self):
        """L2: the agent's own Jest suite passes via the Acceptance command.

        Mirrors the Acceptance Criteria command exactly:
        ``yarn test packages/shared/__tests__/createResourceLoader-test.js``.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        ok, out = _jest_passed(result)
        assert ok, f"agent suite did not pass green:\n{out[-4000:]}"

    def test_agent_suite_has_multiple_independent_cases(self):
        """L2: the agent suite must contain several independent passing cases.

        The requirement mandates per-behavior independent cases, so a single
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
