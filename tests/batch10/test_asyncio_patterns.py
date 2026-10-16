"""Tests for the `asyncio-patterns` skill task (variant ext10).

Task: add an async **circuit breaker** to the aiohttp repository:
  * `aiohttp/circuit_breaker.py` (new) exposing a `CircuitBreaker` class and a
    `CircuitOpenError` exception.
  * `tests/test_circuit_breaker.py` (new) — deterministic test suite.

The breaker wraps async calls and trips from `closed` -> `open` after
`failure_threshold` consecutive failures, fast-failing with `CircuitOpenError`
without invoking the factory while open, then allowing a single `half_open`
trial after `reset_timeout` seconds (measured by an injectable `time_func`),
returning to `closed` on success or `open` on failure.

Verification strategy
---------------------
L1 cases check the deliverable files exist and are minimally well-formed
(importable symbols, the breaker is a class with a `call` coroutine and a
`state` property, the deliverable test file is non-trivial).

L2 cases drive the REAL breaker dynamically. Each L2 test writes a focused
async driver into REPO_DIR and runs it with the repo's own python (PYTHONPATH
pinned to REPO_DIR so `import aiohttp` resolves to the in-repo package). The
driver injects a deterministic fake clock (`time_func`) so open/half-open/closed
transitions are reproducible with zero real sleeping, then prints a single JSON
object that the test asserts on. This exercises the agent's implementation
independently of whatever test file the agent authored, so a stub that hardcodes
`state`, ignores the clock, never fast-fails, or swallows exceptions cannot pass.

A separate L2 case runs the task's native acceptance command:
    python -m pytest tests/test_circuit_breaker.py -v
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

        The script lives inside REPO_DIR so `import aiohttp` resolves to the
        in-repo package; PYTHONPATH is forced to REPO_DIR only.
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

    # A reusable preamble: a deterministic fake clock + factory builders.
    _PREAMBLE = """
        import asyncio, json
        from aiohttp.circuit_breaker import CircuitBreaker, CircuitOpenError

        class Clock:
            def __init__(self):
                self.now = 1000.0
            def __call__(self):
                return self.now
            def advance(self, dt):
                self.now += dt

        class Boom(Exception):
            pass

        # tracks how many times the failing/succeeding factories were invoked
        calls = {"n": 0}

        def fail_factory():
            async def _f():
                calls["n"] += 1
                raise Boom("boom")
            return _f()

        def ok_factory(value=42):
            def make():
                async def _f():
                    calls["n"] += 1
                    return value
                return _f()
            return make
    """

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_circuit_breaker_module_present(self):
        """L1: aiohttp/circuit_breaker.py (the file to create) exists."""
        p = os.path.join(self.REPO_DIR, "aiohttp", "circuit_breaker.py")
        assert os.path.isfile(p), "aiohttp/circuit_breaker.py must be created"

    def test_symbols_importable_and_shaped(self):
        """L1: CircuitBreaker (class with async `call` + `state` property) and
        CircuitOpenError (an Exception subclass) are importable."""
        body = self._PREAMBLE + """
        import inspect
        info = {
            "breaker_is_class": inspect.isclass(CircuitBreaker),
            "error_is_exc": isinstance(CircuitOpenError, type) and issubclass(CircuitOpenError, Exception),
            "call_is_coro": inspect.iscoroutinefunction(getattr(CircuitBreaker, "call", None)),
            "has_state": isinstance(getattr(CircuitBreaker, "state", None), property)
                          or hasattr(CircuitBreaker, "state"),
        }
        print(json.dumps(info))
        """
        res = self._run_json(body)
        assert res["breaker_is_class"] is True
        assert res["error_is_exc"] is True
        assert res["call_is_coro"] is True, "CircuitBreaker.call must be a coroutine function"
        assert res["has_state"] is True

    def test_deliverable_test_file_present_and_nontrivial(self):
        """L1: tests/test_circuit_breaker.py exists, references the breaker and
        defines at least one real test function."""
        p = os.path.join(self.REPO_DIR, "tests", "test_circuit_breaker.py")
        assert os.path.isfile(p), "tests/test_circuit_breaker.py must be created"
        with open(p) as fh:
            content = fh.read()
        assert "CircuitBreaker" in content
        assert "def test_" in content

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavior driven by an injected deterministic clock
    # ------------------------------------------------------------------ #
    def test_starts_closed_and_success_returns_value(self):
        """L2: a fresh breaker is `closed` and a successful call returns the
        factory's result and keeps the breaker closed."""
        body = self._PREAMBLE + """
        async def main():
            clk = Clock()
            cb = CircuitBreaker(failure_threshold=3, reset_timeout=5, time_func=clk)
            start_state = cb.state
            val = await cb.call(ok_factory(7))
            print(json.dumps({"start": start_state, "val": val, "end": cb.state}))
        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["start"] == "closed"
        assert res["val"] == 7
        assert res["end"] == "closed"

    def test_subthreshold_failures_then_success_clears_count(self):
        """L2: failure_threshold=3 with 2 failures then a success -> stays closed
        and the consecutive-failure count is cleared (a later single failure must
        NOT re-trip immediately)."""
        body = self._PREAMBLE + """
        async def main():
            clk = Clock()
            cb = CircuitBreaker(failure_threshold=3, reset_timeout=5, time_func=clk)
            seen = []
            # two failures (sub-threshold)
            for _ in range(2):
                try:
                    await cb.call(fail_factory)
                except Boom:
                    pass
                seen.append(cb.state)
            # one success clears the accumulated count
            await cb.call(ok_factory(1))
            seen.append(cb.state)
            # a single subsequent failure must not be enough to open (count was reset)
            try:
                await cb.call(fail_factory)
            except Boom:
                pass
            seen.append(cb.state)
            print(json.dumps({"states": seen}))
        asyncio.run(main())
        """
        res = self._run_json(body)
        # after 2 fails still closed, after success still closed, after 1 more fail still closed
        assert res["states"] == ["closed", "closed", "closed", "closed"], res["states"]

    def test_threshold_failures_open_the_breaker(self):
        """L2: exactly failure_threshold consecutive failures trips to `open`."""
        body = self._PREAMBLE + """
        async def main():
            clk = Clock()
            cb = CircuitBreaker(failure_threshold=3, reset_timeout=5, time_func=clk)
            states = []
            for _ in range(3):
                try:
                    await cb.call(fail_factory)
                except Boom:
                    pass
                states.append(cb.state)
            print(json.dumps({"states": states}))
        asyncio.run(main())
        """
        res = self._run_json(body)
        # not open after 1 or 2 failures, open exactly at the 3rd
        assert res["states"] == ["closed", "closed", "open"], res["states"]

    def test_open_fast_fails_without_invoking_factory(self):
        """L2: while open, `call` raises CircuitOpenError immediately and the
        factory is never invoked."""
        body = self._PREAMBLE + """
        async def main():
            clk = Clock()
            cb = CircuitBreaker(failure_threshold=2, reset_timeout=5, time_func=clk)
            for _ in range(2):
                try:
                    await cb.call(fail_factory)
                except Boom:
                    pass
            assert cb.state == "open"
            calls_before = calls["n"]
            raised = None
            try:
                await cb.call(ok_factory(99))  # should NOT run
            except CircuitOpenError:
                raised = "CircuitOpenError"
            except Exception as exc:
                raised = "OTHER:" + type(exc).__name__
            print(json.dumps({
                "raised": raised,
                "factory_calls_during_open": calls["n"] - calls_before,
                "state": cb.state,
            }))
        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["raised"] == "CircuitOpenError", res["raised"]
        assert res["factory_calls_during_open"] == 0, "factory must not run while open"
        assert res["state"] == "open"

    def test_open_persists_until_reset_timeout_elapses(self):
        """L2: the breaker stays open (fast-fails) until reset_timeout seconds
        have elapsed per the injected clock; one tick short still fast-fails."""
        body = self._PREAMBLE + """
        async def main():
            clk = Clock()
            cb = CircuitBreaker(failure_threshold=2, reset_timeout=10, time_func=clk)
            for _ in range(2):
                try:
                    await cb.call(fail_factory)
                except Boom:
                    pass
            assert cb.state == "open"
            results = {}

            # advance almost to the timeout -> still fast-fail, factory not called
            clk.advance(9.0)
            calls_before = calls["n"]
            try:
                await cb.call(ok_factory(1))
                results["before_timeout"] = "no-raise"
            except CircuitOpenError:
                results["before_timeout"] = "CircuitOpenError"
            results["calls_before_timeout"] = calls["n"] - calls_before

            # cross the timeout boundary -> trial allowed (half-open), factory runs
            clk.advance(2.0)  # total 11 > 10
            calls_before = calls["n"]
            val = await cb.call(ok_factory(5))
            results["after_timeout_val"] = val
            results["calls_after_timeout"] = calls["n"] - calls_before
            print(json.dumps(results))
        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["before_timeout"] == "CircuitOpenError"
        assert res["calls_before_timeout"] == 0, "factory ran before timeout elapsed"
        assert res["after_timeout_val"] == 5
        assert res["calls_after_timeout"] == 1, "trial call should invoke the factory once"

    def test_half_open_success_closes_and_resets(self):
        """L2: after reset_timeout, a succeeding trial returns to `closed` and the
        failure count is reset (so it takes a full new threshold to re-open)."""
        body = self._PREAMBLE + """
        async def main():
            clk = Clock()
            cb = CircuitBreaker(failure_threshold=2, reset_timeout=5, time_func=clk)
            for _ in range(2):
                try:
                    await cb.call(fail_factory)
                except Boom:
                    pass
            assert cb.state == "open"
            clk.advance(6.0)
            val = await cb.call(ok_factory(123))   # half-open trial succeeds
            after_trial = cb.state
            # one fresh failure must NOT immediately re-open (count was reset)
            try:
                await cb.call(fail_factory)
            except Boom:
                pass
            after_one_fail = cb.state
            print(json.dumps({
                "val": val,
                "after_trial": after_trial,
                "after_one_fail": after_one_fail,
            }))
        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["val"] == 123
        assert res["after_trial"] == "closed", "successful trial must close the breaker"
        assert res["after_one_fail"] == "closed", "failure count must have reset on close"

    def test_half_open_failure_reopens_and_restarts_timer(self):
        """L2: a failing trial returns to `open`, propagates the error, and the
        timer restarts (still fast-fails until reset_timeout elapses again)."""
        body = self._PREAMBLE + """
        async def main():
            clk = Clock()
            cb = CircuitBreaker(failure_threshold=2, reset_timeout=5, time_func=clk)
            for _ in range(2):
                try:
                    await cb.call(fail_factory)
                except Boom:
                    pass
            assert cb.state == "open"
            clk.advance(6.0)  # eligible for trial
            trial_err = None
            try:
                await cb.call(fail_factory)  # half-open trial FAILS
            except Boom:
                trial_err = "Boom"
            except Exception as exc:
                trial_err = "OTHER:" + type(exc).__name__
            state_after_trial = cb.state

            # timer restarted: a small advance (< reset_timeout) must still fast-fail
            clk.advance(3.0)
            calls_before = calls["n"]
            second = None
            try:
                await cb.call(ok_factory(1))
            except CircuitOpenError:
                second = "CircuitOpenError"
            fast_fail_calls = calls["n"] - calls_before

            # advancing past the (restarted) timeout allows a new trial
            clk.advance(3.0)  # total 6 since reopen
            val = await cb.call(ok_factory(8))
            print(json.dumps({
                "trial_err": trial_err,
                "state_after_trial": state_after_trial,
                "second": second,
                "fast_fail_calls": fast_fail_calls,
                "recovered_val": val,
                "final_state": cb.state,
            }))
        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["trial_err"] == "Boom", "failing trial must propagate the underlying error"
        assert res["state_after_trial"] == "open", "failing trial must reopen the breaker"
        assert res["second"] == "CircuitOpenError", "timer must restart after a failed trial"
        assert res["fast_fail_calls"] == 0
        assert res["recovered_val"] == 8
        assert res["final_state"] == "closed"

    def test_failure_propagates_in_closed_state(self):
        """L2: in closed state the factory's exception propagates to the caller
        (the breaker records but does not swallow it)."""
        body = self._PREAMBLE + """
        async def main():
            clk = Clock()
            cb = CircuitBreaker(failure_threshold=5, reset_timeout=5, time_func=clk)
            raised = None
            try:
                await cb.call(fail_factory)
            except Boom as exc:
                raised = "Boom:" + str(exc)
            except Exception as exc:
                raised = "OTHER:" + type(exc).__name__
            print(json.dumps({"raised": raised, "state": cb.state}))
        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["raised"] == "Boom:boom", res["raised"]
        # one failure with threshold 5 keeps it closed
        assert res["state"] == "closed"

    def test_invalid_constructor_args_raise_valueerror(self):
        """L2: failure_threshold < 1 or reset_timeout <= 0 raise ValueError."""
        body = self._PREAMBLE + """
        def build(**kw):
            try:
                CircuitBreaker(time_func=Clock(), **kw)
                return "no-raise"
            except ValueError:
                return "ValueError"
            except Exception as exc:
                return "OTHER:" + type(exc).__name__

        out = {
            "thr0": build(failure_threshold=0, reset_timeout=5),
            "thr_neg": build(failure_threshold=-2, reset_timeout=5),
            "rt0": build(failure_threshold=2, reset_timeout=0),
            "rt_neg": build(failure_threshold=2, reset_timeout=-1),
            "valid": build(failure_threshold=1, reset_timeout=1),
        }
        print(json.dumps(out))
        """
        res = self._run_json(body)
        assert res["thr0"] == "ValueError"
        assert res["thr_neg"] == "ValueError"
        assert res["rt0"] == "ValueError"
        assert res["rt_neg"] == "ValueError"
        assert res["valid"] == "no-raise", "threshold=1, reset_timeout=1 must be accepted"

    def test_threshold_one_trips_on_single_failure(self):
        """L2: with failure_threshold=1, a single failure opens the breaker and
        the immediately following call fast-fails with CircuitOpenError."""
        body = self._PREAMBLE + """
        async def main():
            clk = Clock()
            cb = CircuitBreaker(failure_threshold=1, reset_timeout=5, time_func=clk)
            try:
                await cb.call(fail_factory)
            except Boom:
                pass
            opened = cb.state
            calls_before = calls["n"]
            raised = None
            try:
                await cb.call(ok_factory(1))
            except CircuitOpenError:
                raised = "CircuitOpenError"
            print(json.dumps({
                "opened": opened,
                "raised": raised,
                "factory_calls": calls["n"] - calls_before,
            }))
        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["opened"] == "open"
        assert res["raised"] == "CircuitOpenError"
        assert res["factory_calls"] == 0

    def test_native_deliverable_suite_passes(self):
        """L2: the task's specified native command passes:
            python -m pytest tests/test_circuit_breaker.py -v
        """
        target = os.path.join(self.REPO_DIR, "tests", "test_circuit_breaker.py")
        assert os.path.isfile(target), "deliverable test file missing"
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_circuit_breaker.py", "-v", "-p", "no:cacheprovider"],
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
