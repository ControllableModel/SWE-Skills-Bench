"""Tests for the `asyncio-patterns` skill task.

Task: add a bounded-concurrency coroutine mapper `aiohttp.helpers.map_concurrent`
to the aiohttp repository.

Verified behaviors (mapped to the requirement doc):
  * The helper exists, is importable and is a coroutine function (L1).
  * The deliverable test file exists and is non-trivial (L1).
  * Positional result ordering independent of completion order (L2).
  * Peak in-flight concurrency equals `limit` exactly (not 1, not N) (L2).
  * Work proceeds concurrently / not in lock-step batches (L2).
  * `limit >= len(items)` runs everything at once (L2).
  * Invalid `limit` raises ValueError before any work (L2).
  * Empty input returns [] and never calls func (L2).
  * Accepts arbitrary iterables (generators), not only sequences (L2).
  * return_exceptions=False re-raises and cancels pending invocations (L2).
  * return_exceptions=True places exception objects positionally (L2).
  * The native deliverable test suite passes (L2).

Strategy: L2 cases write a focused async driver into REPO_DIR and execute it
with the repo's own python, asserting on printed JSON. This exercises the real
helper independently of any test file the agent may have authored, so a naive
or hardcoded implementation cannot pass.
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
    def test_helpers_module_present(self):
        """L1: aiohttp/helpers.py (the file to modify) exists."""
        assert os.path.isfile(os.path.join(self.REPO_DIR, "aiohttp", "helpers.py"))

    def test_map_concurrent_importable_and_coroutine_function(self):
        """L1: map_concurrent is importable and is a coroutine function."""
        body = """
        import asyncio, inspect, json
        from aiohttp.helpers import map_concurrent
        ok = inspect.iscoroutinefunction(map_concurrent)
        print(json.dumps({"is_coro": bool(ok)}))
        """
        res = self._run_json(body)
        assert res["is_coro"] is True

    def test_deliverable_test_file_present_and_nontrivial(self):
        """L1: the required tests/test_map_concurrent.py exists and is non-trivial."""
        p = os.path.join(self.REPO_DIR, "tests", "test_map_concurrent.py")
        assert os.path.isfile(p), "tests/test_map_concurrent.py must be created"
        with open(p) as fh:
            content = fh.read()
        assert "map_concurrent" in content
        # at least one real test function
        assert "def test_" in content

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavior
    # ------------------------------------------------------------------ #
    def test_squares_correct_order(self):
        """L2: squares of [1,2,3,4] with limit=2 returns [1,4,9,16]."""
        body = """
        import asyncio, json
        from aiohttp.helpers import map_concurrent

        async def square(x):
            await asyncio.sleep(0)
            return x * x

        async def main():
            res = await map_concurrent(square, [1, 2, 3, 4], limit=2)
            print(json.dumps({"res": res}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["res"] == [1, 4, 9, 16]

    def test_ordering_independent_of_completion(self):
        """L2: results are positionally aligned even when later items finish first.

        Item i sleeps for (N-i) ticks so earlier items complete LAST; the output
        must still be the input squared in input order. Limit is large enough to
        let all run concurrently so completion order is reversed vs input order.
        """
        body = """
        import asyncio, json
        from aiohttp.helpers import map_concurrent

        completion = []

        async def work(x):
            # earlier index sleeps longer -> finishes later
            await asyncio.sleep((10 - x) * 0.01)
            completion.append(x)
            return x * 10

        async def main():
            items = [0, 1, 2, 3, 4, 5]
            res = await map_concurrent(work, items, limit=10)
            print(json.dumps({"res": res, "completion": completion}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["res"] == [0, 10, 20, 30, 40, 50]
        # completion order must differ from input order (proves out-of-order finish)
        assert res["completion"] != [0, 1, 2, 3, 4, 5]
        assert res["completion"][0] == 5  # last-indexed item finished first

    def test_peak_concurrency_equals_limit(self):
        """L2: with 6 items and limit=2 the observed peak in-flight count is exactly 2."""
        body = """
        import asyncio, json
        from aiohttp.helpers import map_concurrent

        live = 0
        peak = 0

        async def work(x):
            global live, peak
            live += 1
            peak = max(peak, live)
            # hold the slot long enough for scheduling to overlap
            await asyncio.sleep(0.05)
            live -= 1
            return x

        async def main():
            res = await map_concurrent(work, list(range(6)), limit=2)
            print(json.dumps({"res": res, "peak": peak}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["res"] == list(range(6))
        assert res["peak"] == 2, f"peak concurrency must be exactly 2, got {res['peak']}"

    def test_not_lockstep_batches(self):
        """L2: a finished invocation immediately frees a slot for the next pending
        item (no batches of size `limit`).

        With limit=2 and items whose durations are [long, short, short, short, ...],
        in a lock-step-batch implementation the 2nd item would block the whole
        first batch until the long one finishes. We assert that more than `limit`
        invocations have *started* before the slowest first-batch item finishes.
        """
        body = """
        import asyncio, json
        from aiohttp.helpers import map_concurrent

        started_order = []
        long_done = {"flag": False}

        async def work(x):
            started_order.append(x)
            if x == 0:
                # the long one
                await asyncio.sleep(0.30)
                long_done["flag"] = True
            else:
                await asyncio.sleep(0.02)
            return (x, long_done["flag"])

        async def main():
            items = list(range(6))
            res = await map_concurrent(work, items, limit=2)
            print(json.dumps({
                "res": res,
                "started": started_order,
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert [r[0] for r in res["res"]] == list(range(6))
        # All 6 must have been started.
        assert sorted(res["started"]) == list(range(6))
        # Items 2..5 must have started while item 0 (the long one) was still
        # running -> their long_done flag is False. A lock-step batch impl would
        # only run {0,1} then {2,3} then {4,5}; here items beyond the first batch
        # begin before the long item completes.
        flags_after_first = {r[0]: r[1] for r in res["res"]}
        # at least items 2 and 3 should have begun before item 0 finished
        early_starts = [
            i for i in (2, 3, 4, 5) if flags_after_first.get(i) is False
        ]
        assert len(early_starts) >= 2, (
            f"slots were not refilled eagerly; flags={flags_after_first}, "
            f"started={res['started']}"
        )

    def test_limit_geq_len_runs_all_at_once(self):
        """L2: when limit >= number of items, all invocations run simultaneously."""
        body = """
        import asyncio, json
        from aiohttp.helpers import map_concurrent

        live = 0
        peak = 0

        async def work(x):
            global live, peak
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.05)
            live -= 1
            return x

        async def main():
            res = await map_concurrent(work, list(range(4)), limit=10)
            print(json.dumps({"res": res, "peak": peak}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["res"] == list(range(4))
        assert res["peak"] == 4, f"all 4 should run at once, peak={res['peak']}"

    def test_accepts_arbitrary_iterable(self):
        """L2: items may be any iterable (a generator), not only a sequence."""
        body = """
        import asyncio, json
        from aiohttp.helpers import map_concurrent

        async def dbl(x):
            await asyncio.sleep(0)
            return x * 2

        def gen():
            for i in range(5):
                yield i

        async def main():
            res = await map_concurrent(dbl, gen(), limit=2)
            print(json.dumps({"res": res}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["res"] == [0, 2, 4, 6, 8]

    def test_invalid_limit_raises_valueerror_before_work(self):
        """L2: limit=0 (and negatives) raise ValueError and func is never called."""
        body = """
        import asyncio, json
        from aiohttp.helpers import map_concurrent

        called = {"n": 0}

        async def work(x):
            called["n"] += 1
            return x

        async def main():
            results = {}
            for bad in (0, -1, -5):
                try:
                    await map_concurrent(work, [1, 2, 3], limit=bad)
                    results[str(bad)] = "no-raise"
                except ValueError:
                    results[str(bad)] = "ValueError"
                except Exception as exc:
                    results[str(bad)] = type(exc).__name__
            print(json.dumps({"results": results, "called": called["n"]}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["results"]["0"] == "ValueError"
        assert res["results"]["-1"] == "ValueError"
        assert res["results"]["-5"] == "ValueError"
        assert res["called"] == 0, "func must never be called for invalid limit"

    def test_empty_input_returns_empty_list(self):
        """L2: empty items returns [] and never invokes func."""
        body = """
        import asyncio, json
        from aiohttp.helpers import map_concurrent

        called = {"n": 0}

        async def work(x):
            called["n"] += 1
            return x

        async def main():
            res = await map_concurrent(work, [], limit=3)
            print(json.dumps({"res": res, "called": called["n"]}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["res"] == []
        assert res["called"] == 0

    def test_return_exceptions_false_reraises_and_cancels(self):
        """L2: return_exceptions=False re-raises the failure and cancels other
        still-pending invocations it had started (they don't run to completion)."""
        body = """
        import asyncio, json
        from aiohttp.helpers import map_concurrent

        completed = []        # items that ran fully to completion
        cancelled = []        # items whose work got cancelled

        class Boom(Exception):
            pass

        async def work(x):
            try:
                if x == 0:
                    # fail quickly
                    await asyncio.sleep(0.02)
                    raise Boom("boom for 0")
                else:
                    # long-running so it is still pending when 0 fails
                    await asyncio.sleep(1.0)
                    completed.append(x)
                    return x
            except asyncio.CancelledError:
                cancelled.append(x)
                raise

        async def main():
            raised = None
            try:
                await map_concurrent(work, [0, 1, 2, 3], limit=4, return_exceptions=False)
            except Boom as exc:
                raised = str(exc)
            except Exception as exc:
                raised = "OTHER:" + type(exc).__name__
            # give any leaked tasks a chance to (wrongly) finish
            await asyncio.sleep(0.2)
            print(json.dumps({
                "raised": raised,
                "completed": sorted(completed),
                "cancelled": sorted(cancelled),
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["raised"] == "boom for 0", f"must re-raise original exception, got {res['raised']}"
        # No long-running invocation should have completed in the background.
        assert res["completed"] == [], f"pending invocations leaked: {res['completed']}"
        # The still-pending ones should have been cancelled.
        assert set(res["cancelled"]) == {1, 2, 3}, (
            f"pending invocations not cancelled; cancelled={res['cancelled']}"
        )

    def test_return_exceptions_true_inplace_objects(self):
        """L2: return_exceptions=True puts the exception object at the failing
        item's index while others keep their values, preserving positional order."""
        body = """
        import asyncio, json
        from aiohttp.helpers import map_concurrent

        class Boom(Exception):
            pass

        async def work(x):
            await asyncio.sleep(0.01)
            if x == 2:
                raise Boom("fail-2")
            return x * 100

        async def main():
            res = await map_concurrent(work, [0, 1, 2, 3, 4], limit=2, return_exceptions=True)
            # describe each slot: ("exc", type, msg) or ("val", value)
            described = []
            for r in res:
                if isinstance(r, BaseException):
                    described.append(["exc", type(r).__name__, str(r)])
                else:
                    described.append(["val", r])
            print(json.dumps({"described": described, "n": len(res)}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        d = res["described"]
        assert res["n"] == 5
        assert d[0] == ["val", 0]
        assert d[1] == ["val", 100]
        assert d[2][0] == "exc" and d[2][1] == "Boom" and d[2][2] == "fail-2"
        assert d[3] == ["val", 300]
        assert d[4] == ["val", 400]

    def test_return_exceptions_true_others_complete(self):
        """L2: return_exceptions=True does NOT abort the other invocations; all
        non-failing items still produce their results."""
        body = """
        import asyncio, json
        from aiohttp.helpers import map_concurrent

        completed = []

        class Boom(Exception):
            pass

        async def work(x):
            if x == 1:
                await asyncio.sleep(0.01)
                raise Boom("x1")
            await asyncio.sleep(0.05)
            completed.append(x)
            return x

        async def main():
            res = await map_concurrent(work, [0, 1, 2, 3, 4, 5], limit=2, return_exceptions=True)
            vals = [r if not isinstance(r, BaseException) else None for r in res]
            print(json.dumps({"vals": vals, "completed": sorted(completed)}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["vals"] == [0, None, 2, 3, 4, 5]
        assert res["completed"] == [0, 2, 3, 4, 5]

    def test_native_deliverable_suite_passes(self):
        """L2: the task's specified command passes:
        python -m pytest tests/test_map_concurrent.py -v
        """
        target = os.path.join(self.REPO_DIR, "tests", "test_map_concurrent.py")
        assert os.path.isfile(target), "deliverable test file missing"
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_map_concurrent.py", "-v", "-p", "no:cacheprovider"],
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
        # ensure tests actually ran (not 0 collected)
        assert "passed" in proc.stdout, f"no tests passed in output:\n{proc.stdout[-2000:]}"
