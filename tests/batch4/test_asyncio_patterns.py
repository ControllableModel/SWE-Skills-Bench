"""Tests for the `asyncio-patterns` skill task (variant ext4).

Task: add an async producer/consumer pipeline runner
``aiohttp.pipeline.run_pipeline(items, worker, *, workers, queue_size=0)`` to
the aiohttp repository, plus a deliverable test suite ``tests/test_pipeline.py``.

Contract (re-derived from tasks/ext4/asyncio-patterns.md):
  * ``run_pipeline`` is importable and a coroutine function (L1).
  * Returns a dict mapping each input item to its worker result (L2).
  * Every input is processed exactly once (L2).
  * At most ``workers`` consumer coroutines run concurrently; with 12 items and
    3 workers the observed peak is exactly 3 (L2).
  * ``workers`` greater than item count is allowed; extra workers stay idle and
    shut down cleanly (L2).
  * ``queue_size`` bounds the internal queue; a bounded full queue makes the
    producer wait rather than overflow (L2).
  * A worker exception stops feeding, cancels remaining/idle worker tasks and
    propagates the first exception without hanging or leaking tasks (L2).
  * ``workers < 1`` raises ``ValueError``; empty input returns ``{}`` (L2).
  * The native deliverable suite ``pytest tests/test_pipeline.py -v`` passes (L2).

Verification strategy mirrors the ext1 harness: each L2 case writes a focused
async driver into REPO_DIR and runs it with the repo's own python, asserting on
printed JSON. The driver imports the real ``aiohttp.pipeline`` package, so a
naive / hardcoded / single-worker / non-cancelling implementation cannot pass.
Native command driven: ``python -m pytest tests/test_pipeline.py -v``.
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
    def test_pipeline_module_present(self):
        """L1: aiohttp/pipeline.py (the new deliverable) exists."""
        assert os.path.isfile(
            os.path.join(self.REPO_DIR, "aiohttp", "pipeline.py")
        ), "aiohttp/pipeline.py must be created"

    def test_run_pipeline_importable_and_coroutine_function(self):
        """L1: run_pipeline is importable and is a coroutine function."""
        body = """
        import inspect, json
        from aiohttp.pipeline import run_pipeline
        ok = inspect.iscoroutinefunction(run_pipeline)
        print(json.dumps({"is_coro": bool(ok)}))
        """
        res = self._run_json(body)
        assert res["is_coro"] is True

    def test_deliverable_test_file_present_and_nontrivial(self):
        """L1: the required tests/test_pipeline.py exists and is non-trivial."""
        p = os.path.join(self.REPO_DIR, "tests", "test_pipeline.py")
        assert os.path.isfile(p), "tests/test_pipeline.py must be created"
        with open(p) as fh:
            content = fh.read()
        assert "run_pipeline" in content
        # at least one real test function
        assert "def test_" in content

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavior
    # ------------------------------------------------------------------ #
    def test_returns_dict_mapping_items_to_results(self):
        """L2: items=range(10), worker returns x*10, workers=4 -> the exact
        {item: result} mapping. A stub returning a fixed value or list fails."""
        body = """
        import asyncio, json
        from aiohttp.pipeline import run_pipeline

        async def worker(x):
            await asyncio.sleep(0)
            return x * 10

        async def main():
            res = await run_pipeline(range(10), worker, workers=4)
            # JSON keys are strings; serialise deterministically as pairs.
            assert isinstance(res, dict), f"expected dict, got {type(res).__name__}"
            pairs = sorted((int(k), v) for k, v in res.items())
            print(json.dumps({"pairs": pairs, "n": len(res)}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["n"] == 10
        assert res["pairs"] == [[i, i * 10] for i in range(10)]

    def test_each_item_processed_exactly_once(self):
        """L2: every input is fed to the worker exactly once (no drops, no dupes)."""
        body = """
        import asyncio, json
        from collections import Counter
        from aiohttp.pipeline import run_pipeline

        seen = []

        async def worker(x):
            await asyncio.sleep(0.001)
            seen.append(x)
            return x + 1000

        async def main():
            items = list(range(25))
            res = await run_pipeline(items, worker, workers=5)
            counts = Counter(seen)
            dupes = [k for k, c in counts.items() if c != 1]
            mapped = sorted((int(k), v) for k, v in res.items())
            print(json.dumps({
                "seen_sorted": sorted(seen),
                "dupes": dupes,
                "mapped": mapped,
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["seen_sorted"] == list(range(25))
        assert res["dupes"] == [], f"items processed more/less than once: {res['dupes']}"
        assert res["mapped"] == [[i, i + 1000] for i in range(25)]

    def test_peak_concurrency_equals_workers(self):
        """L2: with 12 items and workers=3 the observed peak in-flight worker
        count is exactly 3 (not 1, not 12). A serial impl peaks at 1."""
        body = """
        import asyncio, json
        from aiohttp.pipeline import run_pipeline

        live = 0
        peak = 0

        async def worker(x):
            global live, peak
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.05)
            live -= 1
            return x

        async def main():
            res = await run_pipeline(list(range(12)), worker, workers=3)
            mapped = sorted((int(k), v) for k, v in res.items())
            print(json.dumps({"mapped": mapped, "peak": peak}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["mapped"] == [[i, i] for i in range(12)]
        assert res["peak"] == 3, f"peak concurrent workers must be exactly 3, got {res['peak']}"

    def test_concurrency_capped_below_item_count(self):
        """L2: with many items and a small worker pool, the peak never exceeds
        `workers`. 20 items / workers=4 must cap at exactly 4 (proves bounding)."""
        body = """
        import asyncio, json
        from aiohttp.pipeline import run_pipeline

        live = 0
        peak = 0

        async def worker(x):
            global live, peak
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.03)
            live -= 1
            return x * 2

        async def main():
            res = await run_pipeline(list(range(20)), worker, workers=4)
            mapped = sorted((int(k), v) for k, v in res.items())
            print(json.dumps({"mapped": mapped, "peak": peak}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["mapped"] == [[i, i * 2] for i in range(20)]
        assert res["peak"] == 4, f"peak must be exactly the worker count 4, got {res['peak']}"

    def test_more_workers_than_items_clean(self):
        """L2: workers > item count is allowed; extra workers stay idle and the
        call still returns the full correct mapping without hanging."""
        body = """
        import asyncio, json
        from aiohttp.pipeline import run_pipeline

        live = 0
        peak = 0

        async def worker(x):
            global live, peak
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.02)
            live -= 1
            return x * 7

        async def main():
            # 3 items but 8 workers -> at most 3 can ever be live at once
            res = await run_pipeline([1, 2, 3], worker, workers=8)
            mapped = sorted((int(k), v) for k, v in res.items())
            print(json.dumps({"mapped": mapped, "peak": peak}))

        asyncio.run(main())
        """
        res = self._run_json(body, timeout=60)
        assert res["mapped"] == [[1, 7], [2, 14], [3, 21]]
        assert res["peak"] <= 3, f"only 3 items -> at most 3 live workers, got {res['peak']}"

    def test_invalid_workers_raises_valueerror(self):
        """L2: workers < 1 (0 and negatives) raises ValueError and the worker is
        never invoked. A naive impl that ignores the guard fails."""
        body = """
        import asyncio, json
        from aiohttp.pipeline import run_pipeline

        called = {"n": 0}

        async def worker(x):
            called["n"] += 1
            return x

        async def main():
            results = {}
            for bad in (0, -1, -3):
                try:
                    await run_pipeline([1, 2, 3], worker, workers=bad)
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
        assert res["results"]["-3"] == "ValueError"
        assert res["called"] == 0, "worker must never be called for invalid workers"

    def test_empty_input_returns_empty_dict(self):
        """L2: empty items returns {} and never invokes the worker."""
        body = """
        import asyncio, json
        from aiohttp.pipeline import run_pipeline

        called = {"n": 0}

        async def worker(x):
            called["n"] += 1
            return x

        async def main():
            res = await run_pipeline([], worker, workers=4)
            print(json.dumps({"res": res, "is_dict": isinstance(res, dict), "called": called["n"]}))

        asyncio.run(main())
        """
        res = self._run_json(body, timeout=60)
        assert res["is_dict"] is True
        assert res["res"] == {}
        assert res["called"] == 0

    def test_bounded_queue_backpressure(self):
        """L2: queue_size bounds the internal queue. With queue_size=1 and a
        single slow worker, the producer must block instead of front-loading all
        items, so at most a small number are buffered/in-flight at once.

        We sample, from inside the worker, how many items have been *produced*
        (handed to the queue+workers) but not yet completed. With one worker and
        queue_size=1 that backlog must stay tiny; an unbounded/front-loading impl
        would show a backlog approaching the full input size.
        """
        body = """
        import asyncio, json
        from aiohttp.pipeline import run_pipeline

        produced = {"n": 0}   # items handed to a worker (entered worker body)
        done = {"n": 0}       # items fully processed
        max_inflight_plus_queued = {"v": 0}

        async def producer_gen():
            # yields lazily; count how many have been pulled by the pipeline
            for i in range(10):
                produced["n"] += 1
                # record outstanding = produced - done at the moment of feeding
                outstanding = produced["n"] - done["n"]
                if outstanding > max_inflight_plus_queued["v"]:
                    max_inflight_plus_queued["v"] = outstanding
                yield i

        async def worker(x):
            # slow consumer
            await asyncio.sleep(0.05)
            done["n"] += 1
            return x

        async def main():
            res = await run_pipeline(producer_gen(), worker, workers=1, queue_size=1)
            mapped = sorted((int(k), v) for k, v in res.items())
            print(json.dumps({
                "mapped": mapped,
                "max_outstanding": max_inflight_plus_queued["v"],
            }))

        asyncio.run(main())
        """
        res = self._run_json(body, timeout=60)
        assert res["mapped"] == [[i, i] for i in range(10)]
        # 1 worker + queue_size=1 -> at most ~ (1 in-flight + 1 queued + the one
        # being produced) outstanding. Must stay well under the full 10.
        assert res["max_outstanding"] <= 3, (
            f"bounded queue not enforcing backpressure; "
            f"max outstanding={res['max_outstanding']} (expected <= 3)"
        )

    def test_bounded_queue_does_not_drop_items(self):
        """L2: a bounded queue must not lose items under pressure. queue_size=2,
        workers=2, many items -> all results still present and correct."""
        body = """
        import asyncio, json
        from aiohttp.pipeline import run_pipeline

        async def worker(x):
            await asyncio.sleep(0.01)
            return x * x

        async def main():
            items = list(range(30))
            res = await run_pipeline(items, worker, workers=2, queue_size=2)
            mapped = sorted((int(k), v) for k, v in res.items())
            print(json.dumps({"mapped": mapped, "n": len(res)}))

        asyncio.run(main())
        """
        res = self._run_json(body, timeout=60)
        assert res["n"] == 30
        assert res["mapped"] == [[i, i * i] for i in range(30)]

    def test_worker_exception_propagates_and_cancels(self):
        """L2: when a worker raises, run_pipeline propagates that exception,
        cancels the remaining in-flight/idle worker tasks, does not hang, and
        leaves no worker task running.

        Item 0 fails fast; the long-running siblings must be cancelled (not run
        to completion) and the original exception must surface.
        """
        body = """
        import asyncio, json
        from aiohttp.pipeline import run_pipeline

        completed = []   # items that ran fully to completion
        cancelled = []   # items whose work got cancelled

        class Boom(Exception):
            pass

        async def worker(x):
            try:
                if x == 0:
                    await asyncio.sleep(0.02)
                    raise Boom("boom for 0")
                else:
                    await asyncio.sleep(1.0)
                    completed.append(x)
                    return x
            except asyncio.CancelledError:
                cancelled.append(x)
                raise

        async def main():
            raised = None
            try:
                await run_pipeline([0, 1, 2, 3], worker, workers=4)
            except Boom as exc:
                raised = str(exc)
            except Exception as exc:
                raised = "OTHER:" + type(exc).__name__
            # give any leaked tasks a chance to (wrongly) finish
            await asyncio.sleep(0.25)
            # count tasks still alive besides this one
            others = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            alive = [t for t in others if not t.done()]
            print(json.dumps({
                "raised": raised,
                "completed": sorted(completed),
                "cancelled": sorted(cancelled),
                "alive_after": len(alive),
            }))

        asyncio.run(main())
        """
        res = self._run_json(body, timeout=60)
        assert res["raised"] == "boom for 0", f"must propagate original exception, got {res['raised']}"
        assert res["completed"] == [], f"siblings should not complete: {res['completed']}"
        assert set(res["cancelled"]) == {1, 2, 3}, (
            f"pending worker invocations not cancelled; cancelled={res['cancelled']}"
        )
        assert res["alive_after"] == 0, (
            f"worker tasks left running after exception: {res['alive_after']}"
        )

    def test_exception_does_not_hang_with_backpressure(self):
        """L2: a worker exception must surface promptly even when many unfed
        items remain behind a bounded queue (no deadlock on the producer side)."""
        body = """
        import asyncio, json
        from aiohttp.pipeline import run_pipeline

        class Boom(Exception):
            pass

        async def worker(x):
            if x == 1:
                await asyncio.sleep(0.02)
                raise Boom("fail-1")
            await asyncio.sleep(0.5)
            return x

        async def main():
            raised = None
            # bounded queue + small pool + lots of items: producer would block
            # if the pipeline didn't tear down on the first error.
            try:
                await asyncio.wait_for(
                    run_pipeline(list(range(200)), worker, workers=2, queue_size=2),
                    timeout=5.0,
                )
            except Boom as exc:
                raised = str(exc)
            except asyncio.TimeoutError:
                raised = "TIMEOUT"
            except Exception as exc:
                raised = "OTHER:" + type(exc).__name__
            print(json.dumps({"raised": raised}))

        asyncio.run(main())
        """
        res = self._run_json(body, timeout=60)
        assert res["raised"] == "fail-1", (
            f"exception must surface without hanging; got {res['raised']}"
        )

    def test_results_independent_of_completion_order(self):
        """L2: the result mapping is keyed by item, so out-of-order completion
        still yields the correct per-item result (no positional smearing)."""
        body = """
        import asyncio, json
        from aiohttp.pipeline import run_pipeline

        completion = []

        async def worker(x):
            # higher x finishes sooner -> completion order reversed vs input
            await asyncio.sleep((6 - x) * 0.01)
            completion.append(x)
            return x * 11

        async def main():
            items = [0, 1, 2, 3, 4, 5]
            res = await run_pipeline(items, worker, workers=6)
            mapped = sorted((int(k), v) for k, v in res.items())
            print(json.dumps({"mapped": mapped, "completion": completion}))

        asyncio.run(main())
        """
        res = self._run_json(body, timeout=60)
        assert res["mapped"] == [[i, i * 11] for i in range(6)]
        # completion order must differ from input order (proves real concurrency)
        assert res["completion"] != [0, 1, 2, 3, 4, 5]
        assert res["completion"][0] == 5  # highest-indexed item finished first

    def test_native_deliverable_suite_passes(self):
        """L2: the task's specified command passes:
        python -m pytest tests/test_pipeline.py -v
        """
        target = os.path.join(self.REPO_DIR, "tests", "test_pipeline.py")
        assert os.path.isfile(target), "deliverable test file missing"
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_pipeline.py", "-v", "-p", "no:cacheprovider"],
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
