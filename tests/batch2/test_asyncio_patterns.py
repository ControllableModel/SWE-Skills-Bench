"""Tests for the `asyncio-patterns` skill task (variant ext2).

Task: add a concurrency-limited async task pool `aiohttp.task_pool.TaskPool`
to the aiohttp repository, plus a deliverable test suite
`tests/test_task_pool.py`.

`TaskPool` is an async context manager:
    * ``__init__(max_concurrency)`` — positive int; ``<= 0`` raises ValueError.
    * ``submit(coro)`` — schedule an already-created coroutine under the
      concurrency cap; returns an awaitable handle yielding the job result.
    * ``join()`` — await all submitted jobs, return results in *submission order*.
    * ``__aenter__`` / ``__aexit__`` — normal exit drains all jobs; an exception
      in the body cancels unfinished jobs before propagating.
    * ``submit`` after the context has exited raises RuntimeError.

Verified behaviors (mapped to the requirement doc):
  * The deliverable module + test file exist and are minimally well-formed (L1).
  * ``TaskPool`` is importable and usable as an async context manager (L1).
  * ``TaskPool(0)`` / negatives raise ValueError from __init__ (L2).
  * ``join()`` returns results in submission order, not completion order (L2).
  * Awaiting a submitted handle yields that job's return value (L2).
  * Peak simultaneously-running jobs equals ``max_concurrency`` exactly (L2).
  * A finishing job immediately frees a slot (no fixed-size batching) (L2).
  * Submitting nothing then exiting completes cleanly (L2).
  * ``submit`` after context exit raises RuntimeError (L2).
  * An exception in the ``async with`` body cancels unfinished jobs and
    propagates the original exception, leaving nothing running (L2).
  * An exception raised inside a submitted job re-propagates when awaited (L2).
  * The native deliverable test suite passes (L2).

Strategy: L2 cases write a focused async driver into REPO_DIR and run it with
the repo's own python, asserting on printed JSON. This exercises the real
``TaskPool`` independently of any test file the agent may have authored, so a
naive/hardcoded implementation (fixed cap, lock-step batching, completion-order
results, no cancellation) cannot pass.
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
    def test_task_pool_module_present(self):
        """L1: aiohttp/task_pool.py (the new deliverable module) exists."""
        assert os.path.isfile(
            os.path.join(self.REPO_DIR, "aiohttp", "task_pool.py")
        ), "aiohttp/task_pool.py must be created"

    def test_task_pool_importable_with_api(self):
        """L1: TaskPool is importable and exposes the required async-CM + methods."""
        body = """
        import asyncio, inspect, json
        from aiohttp.task_pool import TaskPool

        has_aenter = hasattr(TaskPool, "__aenter__")
        has_aexit = hasattr(TaskPool, "__aexit__")
        has_submit = callable(getattr(TaskPool, "submit", None))
        join = getattr(TaskPool, "join", None)
        join_coro = inspect.iscoroutinefunction(join) if join else False
        print(json.dumps({
            "aenter": has_aenter,
            "aexit": has_aexit,
            "submit": has_submit,
            "join_coro": join_coro,
        }))
        """
        res = self._run_json(body)
        assert res["aenter"] is True
        assert res["aexit"] is True
        assert res["submit"] is True
        assert res["join_coro"] is True

    def test_deliverable_test_file_present_and_nontrivial(self):
        """L1: the required tests/test_task_pool.py exists and is non-trivial."""
        p = os.path.join(self.REPO_DIR, "tests", "test_task_pool.py")
        assert os.path.isfile(p), "tests/test_task_pool.py must be created"
        with open(p) as fh:
            content = fh.read()
        assert "TaskPool" in content
        # at least one real test function
        assert "def test_" in content

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavior
    # ------------------------------------------------------------------ #
    def test_invalid_max_concurrency_raises_valueerror(self):
        """L2: max_concurrency <= 0 raises ValueError from __init__."""
        body = """
        import json
        from aiohttp.task_pool import TaskPool

        results = {}
        for bad in (0, -1, -7):
            try:
                TaskPool(bad)
                results[str(bad)] = "no-raise"
            except ValueError:
                results[str(bad)] = "ValueError"
            except Exception as exc:
                results[str(bad)] = type(exc).__name__
        # a valid value must construct fine
        ok = "ok"
        try:
            TaskPool(3)
        except Exception as exc:
            ok = type(exc).__name__
        print(json.dumps({"results": results, "valid": ok}))
        """
        res = self._run_json(body)
        assert res["results"]["0"] == "ValueError"
        assert res["results"]["-1"] == "ValueError"
        assert res["results"]["-7"] == "ValueError"
        assert res["valid"] == "ok"

    def test_join_returns_submission_order(self):
        """L2: join() returns results in submission order even when later jobs
        finish first.

        Job i sleeps (N-i) ticks so earlier-submitted jobs complete LAST, yet
        join() must return them squared in submission order. max_concurrency is
        large enough that all run concurrently and completion order is reversed.
        """
        body = """
        import asyncio, json
        from aiohttp.task_pool import TaskPool

        completion = []

        async def work(i):
            # earlier index sleeps longer -> finishes later
            await asyncio.sleep((10 - i) * 0.01)
            completion.append(i)
            return i * i

        async def main():
            async with TaskPool(10) as pool:
                for i in range(6):
                    pool.submit(work(i))
                res = await pool.join()
            print(json.dumps({"res": res, "completion": completion}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["res"] == [0, 1, 4, 9, 16, 25]
        # completion order must differ from submission order (out-of-order finish)
        assert res["completion"] != [0, 1, 2, 3, 4, 5]
        assert res["completion"][0] == 5  # last-submitted finished first

    def test_handle_awaitable_yields_result(self):
        """L2: awaiting a submitted handle yields that job's return value."""
        body = """
        import asyncio, json
        from aiohttp.task_pool import TaskPool

        async def work(i):
            await asyncio.sleep(0.01)
            return i * 100

        async def main():
            async with TaskPool(2) as pool:
                h0 = pool.submit(work(0))
                h1 = pool.submit(work(1))
                h2 = pool.submit(work(2))
                # await out of submission order; each handle yields its own value
                v2 = await h2
                v0 = await h0
                v1 = await h1
            print(json.dumps({"v0": v0, "v1": v1, "v2": v2}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["v0"] == 0
        assert res["v1"] == 100
        assert res["v2"] == 200

    def test_peak_concurrency_equals_cap(self):
        """L2: with 8 jobs and max_concurrency=3 the observed peak running count
        is exactly 3 (never 1, never 8)."""
        body = """
        import asyncio, json
        from aiohttp.task_pool import TaskPool

        live = 0
        peak = 0

        async def work(i):
            global live, peak
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.05)
            live -= 1
            return i

        async def main():
            async with TaskPool(3) as pool:
                for i in range(8):
                    pool.submit(work(i))
                res = await pool.join()
            print(json.dumps({"res": res, "peak": peak}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["res"] == list(range(8))
        assert res["peak"] == 3, f"peak running must be exactly 3, got {res['peak']}"

    def test_slots_refilled_eagerly_not_batched(self):
        """L2: a finishing job immediately frees a slot for the next waiting job
        (no fixed-size batching).

        With cap=2 and a long job 0 plus short jobs 1..5, a lock-step-batch impl
        would only run {0,1} then {2,3} then {4,5}; jobs 2..5 would not start
        until job 0 finishes. We assert several later jobs START while job 0
        (the long one) is still running.
        """
        body = """
        import asyncio, json
        from aiohttp.task_pool import TaskPool

        started = []
        long_done = {"flag": False}

        async def work(i):
            started.append(i)
            if i == 0:
                await asyncio.sleep(0.30)
                long_done["flag"] = True
            else:
                await asyncio.sleep(0.02)
            return (i, long_done["flag"])

        async def main():
            async with TaskPool(2) as pool:
                for i in range(6):
                    pool.submit(work(i))
                res = await pool.join()
            print(json.dumps({"res": res, "started": started}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert [r[0] for r in res["res"]] == list(range(6))
        assert sorted(res["started"]) == list(range(6))
        # Jobs that began before job 0 finished have flag False.
        flags = {r[0]: r[1] for r in res["res"]}
        early_starts = [i for i in (2, 3, 4, 5) if flags.get(i) is False]
        assert len(early_starts) >= 2, (
            f"slots were not refilled eagerly (lock-step batching); "
            f"flags={flags}, started={res['started']}"
        )

    def test_cap_one_serializes(self):
        """L2: max_concurrency=1 forces strict serial execution (peak == 1)."""
        body = """
        import asyncio, json
        from aiohttp.task_pool import TaskPool

        live = 0
        peak = 0
        order = []

        async def work(i):
            global live, peak
            live += 1
            peak = max(peak, live)
            order.append(i)
            await asyncio.sleep(0.02)
            live -= 1
            return i

        async def main():
            async with TaskPool(1) as pool:
                for i in range(4):
                    pool.submit(work(i))
                res = await pool.join()
            print(json.dumps({"res": res, "peak": peak, "order": order}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["res"] == [0, 1, 2, 3]
        assert res["peak"] == 1, f"cap=1 must serialize, peak={res['peak']}"
        assert res["order"] == [0, 1, 2, 3]

    def test_empty_pool_exits_cleanly(self):
        """L2: submitting nothing then exiting the context completes cleanly and
        join() returns an empty list."""
        body = """
        import asyncio, json
        from aiohttp.task_pool import TaskPool

        async def main():
            joined = None
            async with TaskPool(3) as pool:
                joined = await pool.join()
            # second, do-nothing context too
            async with TaskPool(2):
                pass
            print(json.dumps({"joined": joined, "ok": True}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["joined"] == []
        assert res["ok"] is True

    def test_submit_after_exit_raises_runtimeerror(self):
        """L2: submit() called after the context has exited raises RuntimeError."""
        body = """
        import asyncio, json
        from aiohttp.task_pool import TaskPool

        async def noop():
            return 1

        async def main():
            pool = None
            async with TaskPool(2) as p:
                pool = p
                pool.submit(noop())
                await pool.join()
            outcome = "no-raise"
            try:
                pool.submit(noop())
            except RuntimeError:
                outcome = "RuntimeError"
            except Exception as exc:
                outcome = type(exc).__name__
            print(json.dumps({"outcome": outcome}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["outcome"] == "RuntimeError"

    def test_body_exception_cancels_unfinished_jobs(self):
        """L2: if the async-with body raises, __aexit__ cancels unfinished jobs
        before propagating; the original exception escapes and no job keeps
        running to completion afterward."""
        body = """
        import asyncio, json
        from aiohttp.task_pool import TaskPool

        completed = []
        cancelled = []

        class Boom(Exception):
            pass

        async def work(i):
            try:
                # long-running so still in flight when the body raises
                await asyncio.sleep(1.0)
                completed.append(i)
                return i
            except asyncio.CancelledError:
                cancelled.append(i)
                raise

        async def main():
            raised = None
            try:
                async with TaskPool(4) as pool:
                    for i in range(4):
                        pool.submit(work(i))
                    # let jobs actually start before we blow up
                    await asyncio.sleep(0.05)
                    raise Boom("body failed")
            except Boom as exc:
                raised = str(exc)
            except Exception as exc:
                raised = "OTHER:" + type(exc).__name__
            # give any leaked jobs a chance to (wrongly) finish
            await asyncio.sleep(0.2)
            print(json.dumps({
                "raised": raised,
                "completed": sorted(completed),
                "cancelled": sorted(cancelled),
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["raised"] == "body failed", (
            f"original body exception must propagate, got {res['raised']}"
        )
        assert res["completed"] == [], f"jobs leaked and completed: {res['completed']}"
        assert set(res["cancelled"]) == {0, 1, 2, 3}, (
            f"unfinished jobs not cancelled on error exit; cancelled={res['cancelled']}"
        )

    def test_job_exception_propagates_through_handle(self):
        """L2: an exception raised by a submitted job re-propagates when its
        handle is awaited, while other jobs are unaffected."""
        body = """
        import asyncio, json
        from aiohttp.task_pool import TaskPool

        class Boom(Exception):
            pass

        async def good(i):
            await asyncio.sleep(0.01)
            return i * 10

        async def bad():
            await asyncio.sleep(0.01)
            raise Boom("kaboom")

        async def main():
            err = None
            good_val = None
            async with TaskPool(3) as pool:
                hg = pool.submit(good(2))
                hb = pool.submit(bad())
                good_val = await hg
                try:
                    await hb
                except Boom as exc:
                    err = str(exc)
                except Exception as exc:
                    err = "OTHER:" + type(exc).__name__
            print(json.dumps({"err": err, "good_val": good_val}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["err"] == "kaboom", f"job exception must propagate, got {res['err']}"
        assert res["good_val"] == 20

    def test_native_deliverable_suite_passes(self):
        """L2: the task's specified command passes:
        python -m pytest tests/test_task_pool.py -v
        """
        target = os.path.join(self.REPO_DIR, "tests", "test_task_pool.py")
        assert os.path.isfile(target), "deliverable test file missing"
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_task_pool.py",
                "-v",
                "-p",
                "no:cacheprovider",
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
        # ensure tests actually ran (not 0 collected)
        assert "passed" in proc.stdout, f"no tests passed in output:\n{proc.stdout[-2000:]}"
