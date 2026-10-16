"""Tests for the `asyncio-patterns` skill task (variant ext7).

Task: add a cancellation-safe async timeout guard
`aiohttp.timeout_guard.timeout_after(delay)` to the aiohttp repository.

`timeout_after(delay)` returns an async context manager that bounds the
enclosed async block to `delay` seconds. Verified behaviors (mapped to the
requirement doc):
  * The module + helper exist and are importable (L1).
  * The deliverable test file exists and is non-trivial (L1).
  * Returned object is usable as an async context manager exposing `expired` (L1).
  * Block finishing in time leaves `expired == False`, no exception (L2).
  * Exceeding the deadline raises asyncio.TimeoutError and sets expired True (L2).
  * The inner awaiting operation is actually cancelled on timeout (L2).
  * A child task launched inside the block ends cancelled, not still running (L2).
  * Negative delay raises ValueError (L2).
  * delay is None disables the timeout entirely (L2).
  * delay == 0 with any await times out (L2).
  * External cancellation propagates as CancelledError, not TimeoutError (L2).
  * A timeout-induced CancelledError surfaces as TimeoutError, not bare cancel (L2).
  * The native deliverable test suite passes (L2).

Strategy: L2 cases write a focused async driver into REPO_DIR and execute it
with the repo's own python, asserting on printed JSON. This exercises the real
context manager independently of any test file the agent may have authored, so
a naive or hardcoded implementation (e.g. one that never cancels, never raises,
or always reports expired) cannot pass.
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
    def test_module_file_present(self):
        """L1: aiohttp/timeout_guard.py (the new file) exists."""
        assert os.path.isfile(
            os.path.join(self.REPO_DIR, "aiohttp", "timeout_guard.py")
        ), "aiohttp/timeout_guard.py must be created"

    def test_timeout_after_importable(self):
        """L1: timeout_after is importable and callable from the new module."""
        body = """
        import json
        from aiohttp.timeout_guard import timeout_after
        print(json.dumps({"callable": callable(timeout_after)}))
        """
        res = self._run_json(body)
        assert res["callable"] is True

    def test_returns_async_context_manager_with_expired(self):
        """L1: timeout_after(...) returns an object usable as an async context
        manager that exposes an `expired` attribute."""
        body = """
        import asyncio, json
        from aiohttp.timeout_guard import timeout_after

        async def main():
            cm = timeout_after(1.0)
            has_aenter = hasattr(cm, "__aenter__")
            has_aexit = hasattr(cm, "__aexit__")
            async with timeout_after(1.0) as guard:
                pass
            print(json.dumps({
                "aenter": has_aenter,
                "aexit": has_aexit,
                "has_expired": hasattr(guard, "expired"),
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["aenter"] is True
        assert res["aexit"] is True
        assert res["has_expired"] is True

    def test_deliverable_test_file_present_and_nontrivial(self):
        """L1: the required tests/test_timeout_guard.py exists and is non-trivial."""
        p = os.path.join(self.REPO_DIR, "tests", "test_timeout_guard.py")
        assert os.path.isfile(p), "tests/test_timeout_guard.py must be created"
        with open(p) as fh:
            content = fh.read()
        assert "timeout_after" in content
        assert "def test_" in content

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavior
    # ------------------------------------------------------------------ #
    def test_completes_in_time_not_expired(self):
        """L2: a block sleeping 0.01s inside timeout_after(1.0) completes normally
        and leaves guard.expired == False with no exception raised."""
        body = """
        import asyncio, json
        from aiohttp.timeout_guard import timeout_after

        async def main():
            raised = None
            expired = None
            try:
                async with timeout_after(1.0) as guard:
                    await asyncio.sleep(0.01)
                    ran = True
                expired = guard.expired
            except BaseException as exc:
                raised = type(exc).__name__
            print(json.dumps({"raised": raised, "expired": expired, "ran": ran}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["raised"] is None, f"unexpected exception {res['raised']}"
        assert res["ran"] is True
        assert res["expired"] is False, "expired must be False when block finishes in time"

    def test_deadline_exceeded_raises_timeout_and_sets_expired(self):
        """L2: a block sleeping 1.0s inside timeout_after(0.02) raises
        asyncio.TimeoutError and the guard reports expired == True."""
        body = """
        import asyncio, json
        from aiohttp.timeout_guard import timeout_after

        async def main():
            captured_guard = {}
            raised = None
            try:
                async with timeout_after(0.02) as guard:
                    captured_guard["g"] = guard
                    await asyncio.sleep(1.0)
            except asyncio.TimeoutError:
                raised = "TimeoutError"
            except BaseException as exc:
                raised = "OTHER:" + type(exc).__name__
            print(json.dumps({
                "raised": raised,
                "expired": captured_guard["g"].expired,
            }))

        asyncio.run(main())
        """
        res = self._run_json(body, timeout=60)
        assert res["raised"] == "TimeoutError", (
            f"expected asyncio.TimeoutError, got {res['raised']}"
        )
        assert res["expired"] is True, "expired must be True after the deadline fires"

    def test_inner_await_is_cancelled_on_timeout(self):
        """L2: when the timeout fires the inner awaiting operation actually
        receives CancelledError (it is not left running to completion)."""
        body = """
        import asyncio, json
        from aiohttp.timeout_guard import timeout_after

        async def main():
            inner_cancelled = {"flag": False}
            inner_completed = {"flag": False}
            try:
                async with timeout_after(0.02):
                    try:
                        await asyncio.sleep(1.0)
                        inner_completed["flag"] = True
                    except asyncio.CancelledError:
                        inner_cancelled["flag"] = True
                        raise
            except asyncio.TimeoutError:
                pass
            print(json.dumps({
                "inner_cancelled": inner_cancelled["flag"],
                "inner_completed": inner_completed["flag"],
            }))

        asyncio.run(main())
        """
        res = self._run_json(body, timeout=60)
        assert res["inner_cancelled"] is True, "inner await must be cancelled on timeout"
        assert res["inner_completed"] is False, "inner work must not run to completion"

    def test_child_task_ends_cancelled_after_timeout(self):
        """L2: a child task launched inside the block must be cancelled (not still
        running) after the context exits via timeout."""
        body = """
        import asyncio, json
        from aiohttp.timeout_guard import timeout_after

        async def main():
            state = {"child_done": False}

            async def child():
                try:
                    await asyncio.sleep(1.0)
                    state["child_done"] = True
                except asyncio.CancelledError:
                    raise

            task = None
            try:
                async with timeout_after(0.02):
                    task = asyncio.ensure_future(child())
                    await asyncio.sleep(1.0)
            except asyncio.TimeoutError:
                pass

            # Give a leaked child a chance to (wrongly) complete.
            await asyncio.sleep(0.2)
            print(json.dumps({
                "child_done": state["child_done"],
                "task_cancelled": bool(task.cancelled()) if task is not None else None,
                "task_running": (not task.done()) if task is not None else None,
            }))

        asyncio.run(main())
        """
        res = self._run_json(body, timeout=60)
        assert res["child_done"] is False, "child task must not run to completion"
        assert res["task_running"] is False, "child task must not still be running after exit"
        assert res["task_cancelled"] is True, "child task must end cancelled"

    def test_negative_delay_raises_valueerror(self):
        """L2: timeout_after(-1) raises ValueError."""
        body = """
        import asyncio, json
        from aiohttp.timeout_guard import timeout_after

        async def main():
            results = {}
            for bad in (-1, -0.5, -100):
                try:
                    cm = timeout_after(bad)
                    # creation may be lazy; entering must surface the error too
                    async with cm:
                        pass
                    results[str(bad)] = "no-raise"
                except ValueError:
                    results[str(bad)] = "ValueError"
                except Exception as exc:
                    results[str(bad)] = type(exc).__name__
            print(json.dumps({"results": results}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["results"]["-1"] == "ValueError"
        assert res["results"]["-0.5"] == "ValueError"
        assert res["results"]["-100"] == "ValueError"

    def test_none_delay_disables_timeout(self):
        """L2: timeout_after(None) never times out, even for a long inner sleep
        relative to a tiny comparison deadline; block completes and not expired."""
        body = """
        import asyncio, json
        from aiohttp.timeout_guard import timeout_after

        async def main():
            raised = None
            expired = None
            ran = False
            try:
                async with timeout_after(None) as guard:
                    await asyncio.sleep(0.2)
                    ran = True
                expired = guard.expired
            except BaseException as exc:
                raised = type(exc).__name__
            print(json.dumps({"raised": raised, "expired": expired, "ran": ran}))

        asyncio.run(main())
        """
        res = self._run_json(body, timeout=60)
        assert res["raised"] is None, f"None delay must not raise, got {res['raised']}"
        assert res["ran"] is True, "block must run to completion when timeout disabled"
        assert res["expired"] is False, "expired must stay False when timeout disabled"

    def test_zero_delay_times_out(self):
        """L2: delay == 0 with a block that awaits anything must time out."""
        body = """
        import asyncio, json
        from aiohttp.timeout_guard import timeout_after

        async def main():
            raised = None
            try:
                async with timeout_after(0):
                    await asyncio.sleep(0.5)
            except asyncio.TimeoutError:
                raised = "TimeoutError"
            except BaseException as exc:
                raised = "OTHER:" + type(exc).__name__
            print(json.dumps({"raised": raised}))

        asyncio.run(main())
        """
        res = self._run_json(body, timeout=60)
        assert res["raised"] == "TimeoutError", (
            f"delay==0 with an await must time out, got {res['raised']}"
        )

    def test_external_cancellation_propagates_as_cancellederror(self):
        """L2: when the caller's own task is cancelled from OUTSIDE the guard
        (not by the deadline), that cancellation surfaces as CancelledError and
        is NOT masked as a TimeoutError."""
        body = """
        import asyncio, json
        from aiohttp.timeout_guard import timeout_after

        async def main():
            outcome = {"v": None}

            async def worker():
                try:
                    # generous timeout so the guard itself never fires
                    async with timeout_after(10.0):
                        await asyncio.sleep(10.0)
                except asyncio.CancelledError:
                    outcome["v"] = "CancelledError"
                    raise
                except asyncio.TimeoutError:
                    outcome["v"] = "TimeoutError"
                except BaseException as exc:
                    outcome["v"] = "OTHER:" + type(exc).__name__

            task = asyncio.ensure_future(worker())
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            print(json.dumps({"outcome": outcome["v"]}))

        asyncio.run(main())
        """
        res = self._run_json(body, timeout=60)
        assert res["outcome"] == "CancelledError", (
            f"external cancellation must remain CancelledError, got {res['outcome']}"
        )

    def test_timeout_not_surfaced_as_bare_cancellederror(self):
        """L2: a CancelledError caused by the timeout must reach the caller as
        asyncio.TimeoutError, never as a bare CancelledError. We assert the
        outermost caller sees TimeoutError and NOT CancelledError."""
        body = """
        import asyncio, json
        from aiohttp.timeout_guard import timeout_after

        async def main():
            seen = {"v": None}
            try:
                async with timeout_after(0.02):
                    await asyncio.sleep(1.0)
            except asyncio.TimeoutError:
                seen["v"] = "TimeoutError"
            except asyncio.CancelledError:
                seen["v"] = "CancelledError"
            except BaseException as exc:
                seen["v"] = "OTHER:" + type(exc).__name__
            print(json.dumps({"seen": seen["v"]}))

        asyncio.run(main())
        """
        res = self._run_json(body, timeout=60)
        assert res["seen"] == "TimeoutError", (
            f"timeout-induced cancel must become TimeoutError, got {res['seen']}"
        )

    def test_reentry_independent_guards(self):
        """L2: distinct timeout_after(...) instances are independent — a fresh
        guard after a timed-out one starts with expired == False and works."""
        body = """
        import asyncio, json
        from aiohttp.timeout_guard import timeout_after

        async def main():
            # first one times out
            first_expired = None
            try:
                async with timeout_after(0.02) as g1:
                    await asyncio.sleep(1.0)
            except asyncio.TimeoutError:
                first_expired = g1.expired
            # second one, independent, should complete cleanly
            async with timeout_after(1.0) as g2:
                await asyncio.sleep(0.01)
            print(json.dumps({
                "first_expired": first_expired,
                "second_expired": g2.expired,
            }))

        asyncio.run(main())
        """
        res = self._run_json(body, timeout=60)
        assert res["first_expired"] is True
        assert res["second_expired"] is False, "a fresh guard must not inherit expired state"

    def test_native_deliverable_suite_passes(self):
        """L2: the task's specified command passes:
        python -m pytest tests/test_timeout_guard.py -v
        """
        target = os.path.join(self.REPO_DIR, "tests", "test_timeout_guard.py")
        assert os.path.isfile(target), "deliverable test file missing"
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                "tests/test_timeout_guard.py", "-v",
                "-p", "no:cacheprovider",
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
