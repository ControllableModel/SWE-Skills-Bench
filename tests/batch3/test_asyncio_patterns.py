"""Tests for the `asyncio-patterns` skill task (variant ext3).

Task: add an async retry-with-backoff wrapper `aiohttp.retry.retry` to the
aiohttp repository.

Public API (from the requirement doc):

    async def retry(factory, *, attempts, retry_on=(Exception,),
                    backoff=None, sleep=None):
        ...

Verified behaviors (each mapped to the requirement doc):
  * `aiohttp/retry.py` exists; `retry` is importable and a coroutine fn (L1).
  * Deliverable test file `tests/test_retry.py` exists and is non-trivial (L1).
  * First-success short-circuit: returns value, `factory` called once,
    `sleep` never called (L2).
  * Two retryable failures then success with attempts=5 -> value returned,
    `factory` called 3x, `sleep` called 2x (L2).
  * Always-failing retryable error, attempts=3 -> 3rd failure propagates,
    `factory` called 3x, `sleep` called 2x (L2).
  * Non-retryable error propagates immediately; `factory` called once;
    `sleep` never called (L2).
  * backoff callable receives zero-based failed-attempt index 0,1,...; sleep
    gets exactly those delay values in order (L2).
  * attempts < 1 (0 and negatives) raises ValueError before calling factory (L2).
  * attempts == 1: factory called once, failure propagates, no sleep (L2).
  * `sleep` defaults to a real awaitable (asyncio.sleep) when omitted (L2).
  * Each retry uses a FRESH awaitable from factory() (no awaitable reuse) (L2).
  * The native deliverable suite `pytest tests/test_retry.py -v` passes (L2).

Strategy: L2 cases write a focused async driver into REPO_DIR and execute it
with the repo's own python, asserting on printed JSON. This exercises the real
`retry` coroutine independently of any test file the agent may have authored,
so a naive/hardcoded implementation (e.g. one that ignores `attempts`, never
sleeps, reuses the awaitable, or swallows non-retryable errors) cannot pass.
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
    def test_retry_module_present(self):
        """L1: aiohttp/retry.py (the file to create) exists."""
        assert os.path.isfile(
            os.path.join(self.REPO_DIR, "aiohttp", "retry.py")
        ), "aiohttp/retry.py must be created"

    def test_retry_importable_and_coroutine_function(self):
        """L1: aiohttp.retry.retry is importable and is a coroutine function."""
        body = """
        import asyncio, inspect, json
        from aiohttp.retry import retry
        ok = inspect.iscoroutinefunction(retry)
        print(json.dumps({"is_coro": bool(ok)}))
        """
        res = self._run_json(body)
        assert res["is_coro"] is True

    def test_deliverable_test_file_present_and_nontrivial(self):
        """L1: the required tests/test_retry.py exists and is non-trivial."""
        p = os.path.join(self.REPO_DIR, "tests", "test_retry.py")
        assert os.path.isfile(p), "tests/test_retry.py must be created"
        with open(p) as fh:
            content = fh.read()
        assert "retry" in content
        # at least one real test function
        assert "def test_" in content

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavior
    # ------------------------------------------------------------------ #
    def test_first_success_short_circuits(self):
        """L2: first awaitable succeeds -> returns its value, factory called once,
        sleep never called (must not call factory again)."""
        body = """
        import asyncio, json
        from aiohttp.retry import retry

        calls = {"factory": 0, "sleep": 0}

        def factory():
            calls["factory"] += 1
            async def coro():
                return 42
            return coro()

        async def rec_sleep(delay):
            calls["sleep"] += 1

        async def main():
            val = await retry(factory, attempts=5, sleep=rec_sleep)
            print(json.dumps({"val": val, "factory": calls["factory"], "sleep": calls["sleep"]}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["val"] == 42
        assert res["factory"] == 1, "factory must be called exactly once on first success"
        assert res["sleep"] == 0, "sleep must not be called when first attempt succeeds"

    def test_two_failures_then_success(self):
        """L2: fail twice (retryable) then succeed with attempts=5 ->
        returns success value; factory called 3x; sleep called 2x."""
        body = """
        import asyncio, json
        from aiohttp.retry import retry

        state = {"n": 0}
        calls = {"factory": 0, "sleep": 0}

        class Transient(Exception):
            pass

        def factory():
            calls["factory"] += 1
            async def coro():
                state["n"] += 1
                if state["n"] <= 2:
                    raise Transient("flaky")
                return "ok-value"
            return coro()

        async def rec_sleep(delay):
            calls["sleep"] += 1

        async def main():
            val = await retry(factory, attempts=5, retry_on=(Transient,), sleep=rec_sleep)
            print(json.dumps({"val": val, "factory": calls["factory"], "sleep": calls["sleep"]}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["val"] == "ok-value"
        assert res["factory"] == 3, "factory must be called exactly 3 times (2 fails + 1 success)"
        assert res["sleep"] == 2, "sleep must be called exactly twice (once per failed-then-retried attempt)"

    def test_exhausts_attempts_and_propagates_last_exception(self):
        """L2: always-failing retryable error with attempts=3 -> the 3rd failure
        propagates; factory called 3x; sleep called 2x."""
        body = """
        import asyncio, json
        from aiohttp.retry import retry

        calls = {"factory": 0, "sleep": 0}
        ids = []

        class Transient(Exception):
            pass

        def factory():
            calls["factory"] += 1
            tag = calls["factory"]
            async def coro():
                raise Transient("fail-%d" % tag)
            return coro()

        async def rec_sleep(delay):
            calls["sleep"] += 1

        async def main():
            raised = None
            try:
                await retry(factory, attempts=3, retry_on=(Transient,), sleep=rec_sleep)
            except Transient as exc:
                raised = ("Transient", str(exc))
            except Exception as exc:
                raised = ("OTHER:" + type(exc).__name__, str(exc))
            print(json.dumps({
                "raised": raised,
                "factory": calls["factory"],
                "sleep": calls["sleep"],
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["raised"][0] == "Transient", f"final retryable exception must propagate, got {res['raised']}"
        # The last (3rd) attempt's exception must be the one that propagates.
        assert res["raised"][1] == "fail-3", f"propagated exception must be from the last attempt, got {res['raised']}"
        assert res["factory"] == 3, "factory must be called exactly attempts(=3) times"
        assert res["sleep"] == 2, "sleep called for the first two failures only, not the terminal one"

    def test_non_retryable_propagates_immediately(self):
        """L2: an exception NOT in retry_on propagates immediately; factory called
        once; sleep never called."""
        body = """
        import asyncio, json
        from aiohttp.retry import retry

        calls = {"factory": 0, "sleep": 0}

        class Transient(Exception):
            pass

        class Fatal(Exception):
            pass

        def factory():
            calls["factory"] += 1
            async def coro():
                raise Fatal("boom")
            return coro()

        async def rec_sleep(delay):
            calls["sleep"] += 1

        async def main():
            raised = None
            try:
                await retry(factory, attempts=5, retry_on=(Transient,), sleep=rec_sleep)
            except Fatal as exc:
                raised = ("Fatal", str(exc))
            except Exception as exc:
                raised = ("OTHER:" + type(exc).__name__, str(exc))
            print(json.dumps({"raised": raised, "factory": calls["factory"], "sleep": calls["sleep"]}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["raised"][0] == "Fatal", f"non-retryable exception must propagate as-is, got {res['raised']}"
        assert res["factory"] == 1, "non-retryable failure must not trigger another factory() call"
        assert res["sleep"] == 0, "non-retryable failure must not sleep"

    def test_backoff_arguments_and_order(self):
        """L2: backoff(i) is called with the zero-based failed-attempt index, and
        sleep receives exactly those delays in order. backoff=lambda i: i*0.5 with
        two failures -> sleep receives 0.0 then 0.5."""
        body = """
        import asyncio, json
        from aiohttp.retry import retry

        state = {"n": 0}
        backoff_args = []
        sleep_args = []

        class Transient(Exception):
            pass

        def factory():
            async def coro():
                state["n"] += 1
                if state["n"] <= 2:
                    raise Transient("x")
                return "done"
            return coro()

        def backoff(i):
            backoff_args.append(i)
            return i * 0.5

        async def rec_sleep(delay):
            sleep_args.append(delay)

        async def main():
            val = await retry(factory, attempts=5, retry_on=(Transient,),
                              backoff=backoff, sleep=rec_sleep)
            print(json.dumps({
                "val": val,
                "backoff_args": backoff_args,
                "sleep_args": sleep_args,
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["val"] == "done"
        # backoff invoked with zero-based failed-attempt indices 0 then 1
        assert res["backoff_args"] == [0, 1], f"backoff must receive 0-based failed indices in order, got {res['backoff_args']}"
        # sleep receives the corresponding delays 0.0 then 0.5, in that order
        assert res["sleep_args"] == [0.0, 0.5], f"sleep must receive backoff delays in order, got {res['sleep_args']}"

    def test_default_delay_zero_when_no_backoff(self):
        """L2: when backoff is None the delay passed to sleep is always 0."""
        body = """
        import asyncio, json
        from aiohttp.retry import retry

        state = {"n": 0}
        sleep_args = []

        class Transient(Exception):
            pass

        def factory():
            async def coro():
                state["n"] += 1
                if state["n"] <= 2:
                    raise Transient("x")
                return "ok"
            return coro()

        async def rec_sleep(delay):
            sleep_args.append(delay)

        async def main():
            val = await retry(factory, attempts=5, retry_on=(Transient,), sleep=rec_sleep)
            print(json.dumps({"val": val, "sleep_args": sleep_args}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["val"] == "ok"
        assert res["sleep_args"] == [0, 0], f"default delay must be 0 for every retry, got {res['sleep_args']}"

    def test_invalid_attempts_raises_valueerror_before_factory(self):
        """L2: attempts < 1 (0 and negatives) raises ValueError before factory is
        ever called and before any sleep."""
        body = """
        import asyncio, json
        from aiohttp.retry import retry

        calls = {"factory": 0, "sleep": 0}

        def factory():
            calls["factory"] += 1
            async def coro():
                return 1
            return coro()

        async def rec_sleep(delay):
            calls["sleep"] += 1

        async def main():
            results = {}
            for bad in (0, -1, -10):
                try:
                    await retry(factory, attempts=bad, sleep=rec_sleep)
                    results[str(bad)] = "no-raise"
                except ValueError:
                    results[str(bad)] = "ValueError"
                except Exception as exc:
                    results[str(bad)] = type(exc).__name__
            print(json.dumps({"results": results, "factory": calls["factory"], "sleep": calls["sleep"]}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["results"]["0"] == "ValueError"
        assert res["results"]["-1"] == "ValueError"
        assert res["results"]["-10"] == "ValueError"
        assert res["factory"] == 0, "factory must never be called for invalid attempts"
        assert res["sleep"] == 0, "sleep must never be called for invalid attempts"

    def test_attempts_one_calls_once_no_sleep(self):
        """L2: attempts == 1 -> factory called exactly once and any failure
        propagates without sleeping."""
        body = """
        import asyncio, json
        from aiohttp.retry import retry

        calls = {"factory": 0, "sleep": 0}

        class Transient(Exception):
            pass

        def factory():
            calls["factory"] += 1
            async def coro():
                raise Transient("only-try")
            return coro()

        async def rec_sleep(delay):
            calls["sleep"] += 1

        async def main():
            raised = None
            try:
                await retry(factory, attempts=1, retry_on=(Transient,), sleep=rec_sleep)
            except Transient as exc:
                raised = str(exc)
            except Exception as exc:
                raised = "OTHER:" + type(exc).__name__
            print(json.dumps({"raised": raised, "factory": calls["factory"], "sleep": calls["sleep"]}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["raised"] == "only-try", f"failure on the single attempt must propagate, got {res['raised']}"
        assert res["factory"] == 1, "attempts=1 must call factory exactly once"
        assert res["sleep"] == 0, "attempts=1 must never sleep"

    def test_default_sleep_is_real_awaitable(self):
        """L2: when `sleep` is omitted it defaults to a real async delay
        (asyncio.sleep) so retries still work without an injected recorder.

        We use backoff returning 0 so the test stays fast, and assert the retry
        actually retried and produced the success value via the default sleep
        path (a naive impl that crashes when sleep is None would fail here)."""
        body = """
        import asyncio, json
        from aiohttp.retry import retry

        state = {"n": 0}

        class Transient(Exception):
            pass

        def factory():
            async def coro():
                state["n"] += 1
                if state["n"] <= 2:
                    raise Transient("x")
                return "via-default-sleep"
            return coro()

        async def main():
            # no sleep= kwarg -> exercise the default asyncio.sleep path
            val = await retry(factory, attempts=5, retry_on=(Transient,),
                              backoff=lambda i: 0)
            print(json.dumps({"val": val, "n": state["n"]}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["val"] == "via-default-sleep", "default sleep path must allow retries to proceed"
        assert res["n"] == 3, f"factory awaitable should have run 3 times, ran {res['n']}"

    def test_fresh_awaitable_each_attempt(self):
        """L2: each retry must call factory() to obtain a FRESH awaitable; the
        same awaitable object is never awaited twice.

        We hand out distinct coroutine objects and record their ids; a buggy
        impl that re-awaits a stored awaitable would raise RuntimeError
        ('cannot reuse already awaited coroutine') instead of succeeding."""
        body = """
        import asyncio, json
        from aiohttp.retry import retry

        state = {"n": 0}
        ids = []

        class Transient(Exception):
            pass

        def factory():
            async def coro():
                state["n"] += 1
                if state["n"] <= 2:
                    raise Transient("retry-me")
                return "fresh-ok"
            c = coro()
            ids.append(id(c))
            return c

        async def rec_sleep(delay):
            pass

        async def main():
            err = None
            val = None
            try:
                val = await retry(factory, attempts=5, retry_on=(Transient,), sleep=rec_sleep)
            except Exception as exc:
                err = type(exc).__name__ + ":" + str(exc)
            print(json.dumps({"val": val, "err": err, "n_unique": len(set(ids)), "n_total": len(ids)}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["err"] is None, f"reusing an awaitable would error; got {res['err']}"
        assert res["val"] == "fresh-ok"
        # three distinct awaitables were created and each used exactly once
        assert res["n_total"] == 3, f"factory should have produced 3 awaitables, got {res['n_total']}"
        assert res["n_unique"] == 3, "each attempt must use a distinct (fresh) awaitable"

    def test_native_deliverable_suite_passes(self):
        """L2: the task's specified command passes:
        python -m pytest tests/test_retry.py -v
        """
        target = os.path.join(self.REPO_DIR, "tests", "test_retry.py")
        assert os.path.isfile(target), "deliverable test file missing"
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_retry.py", "-v", "-p", "no:cacheprovider"],
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
