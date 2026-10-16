"""Tests for the `asyncio-patterns` skill task (variant ext5).

Task: add an async result cache with single-flight deduplication
`aiohttp.single_flight.AsyncCache` to the aiohttp repository.

Public API under test (from the variant requirement doc):
    class AsyncCache:
        def __init__(self) -> None: ...
        async def get(self, key, loader) -> object: ...
        def invalidate(self, key) -> None: ...

Verified behaviors (mapped to the requirement doc):
  * aiohttp/single_flight.py exists and AsyncCache is importable (L1).
  * AsyncCache.get is a coroutine function; invalidate is a plain callable (L1).
  * The deliverable test file tests/test_single_flight.py exists and is
    non-trivial (L1).
  * Cache miss calls loader once, returns the loaded value (L2).
  * Cache hit on a second get does NOT re-invoke loader (L2).
  * Single-flight: N concurrent same-key gets collapse to ONE loader call and
    all callers receive the identical value (L2).
  * Different keys load in parallel (a slow key does not block a fast key) (L2).
  * A failing loader propagates the exception to every current waiter and caches
    nothing; a later get retries the load (L2).
  * invalidate(key) forces recomputation on the next get; invalidate of an
    absent key is a no-op (L2).
  * The loaded value (not a hardcoded constant) is returned and is key-specific
    (L2).
  * The native deliverable suite passes (L2).

Strategy: every L2 case writes a focused async driver into REPO_DIR and runs it
with the repo's own python, asserting on printed JSON. This exercises the real
AsyncCache independently of any test file the agent authored, so a naive
implementation (one that never dedups, always re-invokes loader, hardcodes a
value, or caches failures) cannot pass.
"""

import json
import os
import subprocess
import sys
import textwrap
import uuid

import pytest


class TestAsyncioPatterns:
    REPO_DIR = "/workspace/aiohttp"

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _run_driver(self, body, timeout=120):
        """Write `body` as a standalone script into REPO_DIR, run it with the
        repo python, and return (returncode, stdout, stderr).

        The script is placed inside REPO_DIR so that `import aiohttp` resolves
        to the in-repo package. PYTHONPATH is forced to REPO_DIR only.
        """
        script_name = f"_drv_{uuid.uuid4().hex}.py"
        script_path = os.path.join(self.REPO_DIR, script_name)
        with open(script_path, "w") as fh:
            fh.write(textwrap.dedent(body))
        try:
            env = dict(os.environ)
            env["PYTHONPATH"] = self.REPO_DIR
            proc = subprocess.run(
                [sys.executable, script_path],
                cwd=self.REPO_DIR,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            return proc.returncode, proc.stdout, proc.stderr
        finally:
            try:
                os.remove(script_path)
            except OSError:
                pass

    def _run_json(self, body, timeout=120):
        """Run a driver expected to print a single JSON object on the last
        non-empty stdout line; return that parsed object."""
        rc, out, err = self._run_driver(body, timeout=timeout)
        assert rc == 0, f"driver exited {rc}\nSTDOUT:\n{out}\nSTDERR:\n{err}"
        lines = [ln for ln in out.splitlines() if ln.strip()]
        assert lines, f"no stdout produced\nSTDERR:\n{err}"
        try:
            return json.loads(lines[-1])
        except json.JSONDecodeError as exc:  # pragma: no cover
            pytest.fail(f"last stdout line not JSON: {lines[-1]!r} ({exc})\nFULL:\n{out}")

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_single_flight_module_present(self):
        """L1: aiohttp/single_flight.py (the file to create) exists."""
        assert os.path.isfile(
            os.path.join(self.REPO_DIR, "aiohttp", "single_flight.py")
        ), "aiohttp/single_flight.py must be created"

    def test_async_cache_importable_and_api_shape(self):
        """L1: AsyncCache is importable; get is a coroutine function and
        invalidate is a (non-coroutine) callable."""
        body = """
        import asyncio, inspect, json
        from aiohttp.single_flight import AsyncCache

        c = AsyncCache()
        get_is_coro = inspect.iscoroutinefunction(AsyncCache.get)
        inv = getattr(c, "invalidate", None)
        inv_callable = callable(inv)
        inv_is_coro = inspect.iscoroutinefunction(inv) if inv else None
        print(json.dumps({
            "get_is_coro": bool(get_is_coro),
            "inv_callable": bool(inv_callable),
            "inv_is_coro": bool(inv_is_coro),
        }))
        """
        res = self._run_json(body)
        assert res["get_is_coro"] is True, "AsyncCache.get must be `async def`"
        assert res["inv_callable"] is True, "AsyncCache.invalidate must be callable"
        assert res["inv_is_coro"] is False, "invalidate must be a plain (sync) method"

    def test_deliverable_test_file_present_and_nontrivial(self):
        """L1: the required tests/test_single_flight.py exists and is non-trivial."""
        p = os.path.join(self.REPO_DIR, "tests", "test_single_flight.py")
        assert os.path.isfile(p), "tests/test_single_flight.py must be created"
        with open(p) as fh:
            content = fh.read()
        assert "AsyncCache" in content
        assert "def test_" in content

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavior
    # ------------------------------------------------------------------ #
    def test_miss_calls_loader_once_and_returns_value(self):
        """L2: a single get on an empty cache invokes loader exactly once and
        returns the value the loader produced."""
        body = """
        import asyncio, json
        from aiohttp.single_flight import AsyncCache

        calls = {"n": 0}

        async def loader(key):
            calls["n"] += 1
            await asyncio.sleep(0)
            return "value-for-" + key

        async def main():
            c = AsyncCache()
            v = await c.get("x", loader)
            print(json.dumps({"v": v, "calls": calls["n"]}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["v"] == "value-for-x", f"loaded value must be returned, got {res['v']!r}"
        assert res["calls"] == 1, f"loader must run exactly once on a miss, ran {res['calls']}"

    def test_cache_hit_skips_loader(self):
        """L2: a second sequential get for the same key returns the stored value
        without re-invoking loader; the returned value is the originally loaded one."""
        body = """
        import asyncio, json
        from aiohttp.single_flight import AsyncCache

        calls = {"n": 0}

        async def loader(key):
            calls["n"] += 1
            await asyncio.sleep(0)
            return calls["n"] * 10   # changes each call so a re-load is detectable

        async def main():
            c = AsyncCache()
            v1 = await c.get("k", loader)
            v2 = await c.get("k", loader)
            v3 = await c.get("k", loader)
            print(json.dumps({"v1": v1, "v2": v2, "v3": v3, "calls": calls["n"]}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["calls"] == 1, f"loader must run only once across cache hits, ran {res['calls']}"
        assert res["v1"] == 10
        assert res["v2"] == 10, "cache hit must return the stored value, not reload"
        assert res["v3"] == 10

    def test_keys_are_independent(self):
        """L2: different keys store and return their own loaded values (not a
        single shared/hardcoded value)."""
        body = """
        import asyncio, json
        from aiohttp.single_flight import AsyncCache

        async def loader(key):
            await asyncio.sleep(0)
            return {"a": 1, "b": 2, "c": 3}[key]

        async def main():
            c = AsyncCache()
            a = await c.get("a", loader)
            b = await c.get("b", loader)
            cc = await c.get("c", loader)
            # re-fetch to confirm each key retained its own value
            a2 = await c.get("a", loader)
            print(json.dumps({"a": a, "b": b, "c": cc, "a2": a2}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["a"] == 1
        assert res["b"] == 2
        assert res["c"] == 3
        assert res["a2"] == 1

    def test_single_flight_concurrent_same_key(self):
        """L2: 10 concurrent gets for the same key collapse to exactly ONE loader
        invocation, and all 10 callers receive the identical loaded value."""
        body = """
        import asyncio, json
        from aiohttp.single_flight import AsyncCache

        calls = {"n": 0}

        async def loader(key):
            calls["n"] += 1
            # hold the in-flight slot so all 10 gets pile up on the same load
            await asyncio.sleep(0.1)
            return "loaded-" + key + "-#" + str(calls["n"])

        async def main():
            c = AsyncCache()
            results = await asyncio.gather(*[c.get("x", loader) for _ in range(10)])
            print(json.dumps({
                "calls": calls["n"],
                "n_results": len(results),
                "distinct": sorted(set(results)),
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["calls"] == 1, (
            f"concurrent same-key loads must collapse to ONE loader call, got {res['calls']}"
        )
        assert res["n_results"] == 10
        assert res["distinct"] == ["loaded-x-#1"], (
            f"all concurrent waiters must receive the SAME value, got {res['distinct']}"
        )

    def test_different_keys_load_in_parallel(self):
        """L2: a slow load for key 'a' must not block a fast load for key 'b';
        both proceed concurrently so total wall time is bounded by the slow one,
        not the sum, and 'b' finishes before 'a'."""
        body = """
        import asyncio, json, time
        from aiohttp.single_flight import AsyncCache

        finish_order = []

        async def loader(key):
            delay = 0.30 if key == "a" else 0.02
            await asyncio.sleep(delay)
            finish_order.append(key)
            return key.upper()

        async def main():
            c = AsyncCache()
            t0 = time.monotonic()
            a, b = await asyncio.gather(c.get("a", loader), c.get("b", loader))
            elapsed = time.monotonic() - t0
            print(json.dumps({
                "a": a, "b": b,
                "elapsed": elapsed,
                "finish_order": finish_order,
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["a"] == "A"
        assert res["b"] == "B"
        # 'b' (fast) must finish before 'a' (slow) -> they ran in parallel
        assert res["finish_order"] == ["b", "a"], (
            f"different keys must load in parallel; finish_order={res['finish_order']}"
        )
        # parallel: total time near the slow loader (0.30s), well under the serial sum (~0.32s+).
        assert res["elapsed"] < 0.30, (
            f"loads were serialized across distinct keys; elapsed={res['elapsed']:.3f}s"
        )

    def test_failing_loader_propagates_to_all_waiters_and_caches_nothing(self):
        """L2: when loader raises while 3 callers await the same key, every caller
        receives that exception and nothing is cached; a following get retries."""
        body = """
        import asyncio, json
        from aiohttp.single_flight import AsyncCache

        calls = {"n": 0}

        class Boom(Exception):
            pass

        async def loader(key):
            calls["n"] += 1
            await asyncio.sleep(0.05)
            # fail on the first load only; succeed on the retry
            if calls["n"] == 1:
                raise Boom("boom-" + key)
            return "ok-" + key

        async def main():
            c = AsyncCache()
            outcomes = await asyncio.gather(
                *[c.get("x", loader) for _ in range(3)],
                return_exceptions=True,
            )
            described = []
            for o in outcomes:
                if isinstance(o, BaseException):
                    described.append(["exc", type(o).__name__, str(o)])
                else:
                    described.append(["val", o])
            # nothing should have been cached after the failure: a retry must
            # actually re-run the loader and now succeed.
            retry = await c.get("x", loader)
            print(json.dumps({
                "described": described,
                "calls_after_failure": calls["n"],
                "retry": retry,
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        d = res["described"]
        assert len(d) == 3
        for slot in d:
            assert slot[0] == "exc", f"every waiter must see the exception, got {slot}"
            assert slot[1] == "Boom", f"wrong exception type propagated: {slot}"
            assert slot[2] == "boom-x", f"wrong exception value propagated: {slot}"
        # First (failed) load + the retry load = exactly 2 invocations total.
        assert res["calls_after_failure"] == 2, (
            f"failure must not be cached; expected a retry load, total calls={res['calls_after_failure']}"
        )
        assert res["retry"] == "ok-x", "the retry after a failed load must succeed"

    def test_invalidate_forces_recompute(self):
        """L2: invalidate(key) drops the stored value so the next get re-invokes
        loader and returns the freshly computed value."""
        body = """
        import asyncio, json
        from aiohttp.single_flight import AsyncCache

        calls = {"n": 0}

        async def loader(key):
            calls["n"] += 1
            await asyncio.sleep(0)
            return calls["n"]   # increments each real load

        async def main():
            c = AsyncCache()
            v1 = await c.get("x", loader)   # load #1 -> 1
            v1b = await c.get("x", loader)  # cache hit -> still 1
            c.invalidate("x")
            v2 = await c.get("x", loader)   # load #2 -> 2
            print(json.dumps({"v1": v1, "v1b": v1b, "v2": v2, "calls": calls["n"]}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["v1"] == 1
        assert res["v1b"] == 1, "before invalidate, get must be a cache hit"
        assert res["v2"] == 2, "after invalidate, get must recompute via loader"
        assert res["calls"] == 2, f"exactly two real loads expected, got {res['calls']}"

    def test_invalidate_absent_key_is_noop(self):
        """L2: invalidate of a key that was never loaded raises no error, and an
        existing different key remains cached/untouched."""
        body = """
        import asyncio, json
        from aiohttp.single_flight import AsyncCache

        calls = {"n": 0}

        async def loader(key):
            calls["n"] += 1
            await asyncio.sleep(0)
            return "v-" + key

        async def main():
            c = AsyncCache()
            err = None
            try:
                c.invalidate("never-loaded")   # must not raise
            except Exception as exc:
                err = type(exc).__name__
            a1 = await c.get("a", loader)      # load #1
            c.invalidate("other-absent")       # must not disturb 'a'
            a2 = await c.get("a", loader)       # cache hit, no new load
            print(json.dumps({"err": err, "a1": a1, "a2": a2, "calls": calls["n"]}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["err"] is None, f"invalidate of absent key raised {res['err']}"
        assert res["a1"] == "v-a"
        assert res["a2"] == "v-a"
        assert res["calls"] == 1, (
            f"invalidating an unrelated absent key must not evict 'a'; loads={res['calls']}"
        )

    def test_loader_not_called_when_value_present_under_concurrency(self):
        """L2: once a key is cached, a fresh burst of concurrent gets are all pure
        cache hits (zero additional loader calls)."""
        body = """
        import asyncio, json
        from aiohttp.single_flight import AsyncCache

        calls = {"n": 0}

        async def loader(key):
            calls["n"] += 1
            await asyncio.sleep(0.02)
            return "cached-" + key

        async def main():
            c = AsyncCache()
            first = await c.get("x", loader)        # populate -> 1 call
            burst = await asyncio.gather(*[c.get("x", loader) for _ in range(8)])
            print(json.dumps({
                "first": first,
                "burst_distinct": sorted(set(burst)),
                "calls": calls["n"],
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["first"] == "cached-x"
        assert res["burst_distinct"] == ["cached-x"], (
            f"post-cache burst must all return the stored value, got {res['burst_distinct']}"
        )
        assert res["calls"] == 1, (
            f"cached key must not re-invoke loader under a concurrent burst, calls={res['calls']}"
        )

    def test_native_deliverable_suite_passes(self):
        """L2: the task's specified command passes:
        python -m pytest tests/test_single_flight.py -v
        """
        target = os.path.join(self.REPO_DIR, "tests", "test_single_flight.py")
        assert os.path.isfile(target), "deliverable test file missing"
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                "tests/test_single_flight.py", "-v", "-p", "no:cacheprovider",
            ],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        assert proc.returncode == 0, (
            f"native test suite failed (rc={proc.returncode})\n"
            f"STDOUT:\n{proc.stdout[-4000:]}\nSTDERR:\n{proc.stderr[-2000:]}"
        )
        assert "passed" in proc.stdout, f"no tests passed in output:\n{proc.stdout[-2000:]}"
