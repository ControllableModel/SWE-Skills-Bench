"""Tests for the `asyncio-patterns` skill task (variant ext9).

Task: add an async background-task supervisor `aiohttp.supervisor.TaskSupervisor`
to the aiohttp repository.

The supervisor owns a set of background asyncio tasks: it keeps strong
references so they are not garbage-collected mid-flight, auto-removes tasks that
finish on their own, can `shutdown()` (cancel + drain) all active tasks to a
count of 0 with optional timeout enforcement, contains exceptions raised inside
spawned tasks, and works as an async context manager that shuts down on exit.

Verified behaviors (mapped to the requirement doc):
  * aiohttp/supervisor.py exists and TaskSupervisor is importable (L1).
  * The deliverable tests/test_supervisor.py exists and is non-trivial (L1).
  * spawn() schedules a task, returns it, and active_count() reports unfinished
    tasks (== 3 while three sleepers run) (L2).
  * A task that finishes on its own is auto-removed; active_count() drops and the
    supervisor stops holding a strong reference (proved via weakref) (L2).
  * shutdown() cancels all active tasks and drives active_count() to 0 (L2).
  * shutdown(timeout=...) raises asyncio.TimeoutError for a task that refuses to
    stop, and that task is no longer the supervisor's responsibility (L2).
  * An exception inside a spawned task does NOT break the supervisor; the task
    object reports the exception and the supervisor remains usable (L2).
  * Using the supervisor as `async with` shuts tasks down on exit, including when
    the body raises (the body exception still propagates) (L2).
  * shutdown() on an empty supervisor completes immediately; double shutdown is a
    safe no-op (L2).
  * The native deliverable test suite passes (L2).

Strategy: L2 cases write a focused async driver into REPO_DIR and execute it
with the repo's own python, asserting on printed JSON. This exercises the real
TaskSupervisor independently of any test file the agent may have authored, so a
naive or hardcoded implementation cannot pass.
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
    def test_supervisor_module_present(self):
        """L1: aiohttp/supervisor.py (the new deliverable) exists."""
        assert os.path.isfile(
            os.path.join(self.REPO_DIR, "aiohttp", "supervisor.py")
        ), "aiohttp/supervisor.py must be created"

    def test_supervisor_importable_with_required_api(self):
        """L1: TaskSupervisor is importable and exposes the required public API."""
        body = """
        import json
        import inspect
        from aiohttp.supervisor import TaskSupervisor

        sup = TaskSupervisor()
        api = {
            "has_spawn": callable(getattr(sup, "spawn", None)),
            "has_active_count": callable(getattr(sup, "active_count", None)),
            "shutdown_is_coro": inspect.iscoroutinefunction(getattr(TaskSupervisor, "shutdown", None)),
            "aenter_is_coro": inspect.iscoroutinefunction(getattr(TaskSupervisor, "__aenter__", None)),
            "aexit_is_coro": inspect.iscoroutinefunction(getattr(TaskSupervisor, "__aexit__", None)),
            "active_count_zero": sup.active_count(),
        }
        print(json.dumps(api))
        """
        res = self._run_json(body)
        assert res["has_spawn"] is True
        assert res["has_active_count"] is True
        assert res["shutdown_is_coro"] is True, "shutdown must be a coroutine"
        assert res["aenter_is_coro"] is True, "__aenter__ must be a coroutine"
        assert res["aexit_is_coro"] is True, "__aexit__ must be a coroutine"
        assert res["active_count_zero"] == 0, "fresh supervisor must report 0 active"

    def test_deliverable_test_file_present_and_nontrivial(self):
        """L1: the required tests/test_supervisor.py exists and is non-trivial."""
        p = os.path.join(self.REPO_DIR, "tests", "test_supervisor.py")
        assert os.path.isfile(p), "tests/test_supervisor.py must be created"
        with open(p) as fh:
            content = fh.read()
        assert "TaskSupervisor" in content
        assert "def test_" in content

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavior
    # ------------------------------------------------------------------ #
    def test_spawn_returns_task_and_active_count_tracks(self):
        """L2: spawn() returns the created task and active_count() == 3 while
        three sleepers are running."""
        body = """
        import asyncio, json
        from aiohttp.supervisor import TaskSupervisor

        async def sleeper():
            await asyncio.sleep(0.3)

        async def main():
            sup = TaskSupervisor()
            tasks = [sup.spawn(sleeper()) for _ in range(3)]
            # let them get scheduled
            await asyncio.sleep(0.05)
            are_tasks = all(isinstance(t, asyncio.Task) for t in tasks)
            count_while_running = sup.active_count()
            await sup.shutdown()
            print(json.dumps({
                "are_tasks": are_tasks,
                "count_while_running": count_while_running,
                "count_after": sup.active_count(),
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["are_tasks"] is True, "spawn() must return the created asyncio.Task"
        assert res["count_while_running"] == 3, (
            f"active_count must report 3 unfinished tasks, got {res['count_while_running']}"
        )
        assert res["count_after"] == 0

    def test_finished_task_auto_removed_and_reference_dropped(self):
        """L2: a task that returns on its own is auto-removed from the active set
        AND its strong reference is dropped (proved with weakref -> collectable)."""
        body = """
        import asyncio, gc, json, weakref
        from aiohttp.supervisor import TaskSupervisor

        async def quick():
            return 42

        async def main():
            sup = TaskSupervisor()
            t = sup.spawn(quick())
            ref = weakref.ref(t)
            count_before = sup.active_count()
            # let it finish
            await asyncio.sleep(0.05)
            count_after = sup.active_count()
            result = t.result()
            # drop our own ref; if the supervisor still holds one the object
            # survives garbage collection.
            del t
            gc.collect()
            collected = ref() is None
            print(json.dumps({
                "count_before": count_before,
                "count_after": count_after,
                "result": result,
                "collected": collected,
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["count_before"] == 1
        assert res["count_after"] == 0, "finished task must be auto-removed from active set"
        assert res["result"] == 42
        assert res["collected"] is True, (
            "supervisor must drop its strong reference to a finished task so it "
            "can be garbage-collected"
        )

    def test_shutdown_cancels_all_active(self):
        """L2: shutdown() cancels every still-active task and drives active_count
        to 0; the long-running bodies are actually cancelled (never complete)."""
        body = """
        import asyncio, json
        from aiohttp.supervisor import TaskSupervisor

        completed = []
        cancelled = []

        async def longrun(x):
            try:
                await asyncio.sleep(10)
                completed.append(x)
            except asyncio.CancelledError:
                cancelled.append(x)
                raise

        async def main():
            sup = TaskSupervisor()
            for i in range(4):
                sup.spawn(longrun(i))
            await asyncio.sleep(0.05)
            count_running = sup.active_count()
            await sup.shutdown()
            print(json.dumps({
                "count_running": count_running,
                "count_after": sup.active_count(),
                "completed": sorted(completed),
                "cancelled": sorted(cancelled),
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["count_running"] == 4
        assert res["count_after"] == 0, "shutdown must drain active tasks to 0"
        assert res["completed"] == [], "no long task should have run to completion"
        assert res["cancelled"] == [0, 1, 2, 3], "all active tasks must be cancelled"

    def test_shutdown_timeout_raises_timeouterror(self):
        """L2: shutdown(timeout=...) raises asyncio.TimeoutError when a task
        refuses to stop in time, and the supervisor disowns it afterwards."""
        body = """
        import asyncio, json
        from aiohttp.supervisor import TaskSupervisor

        async def stubborn():
            # swallow cancellation repeatedly so it cannot stop in time
            while True:
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    # keep going despite cancellation
                    try:
                        await asyncio.sleep(10)
                    except asyncio.CancelledError:
                        pass

        async def main():
            sup = TaskSupervisor()
            sup.spawn(stubborn())
            await asyncio.sleep(0.05)
            raised = None
            try:
                await sup.shutdown(timeout=0.2)
            except asyncio.TimeoutError:
                raised = "TimeoutError"
            except Exception as exc:
                raised = "OTHER:" + type(exc).__name__
            print(json.dumps({
                "raised": raised,
                "count_after": sup.active_count(),
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["raised"] == "TimeoutError", (
            f"shutdown(timeout=...) must raise asyncio.TimeoutError, got {res['raised']}"
        )
        # the unresponsive task is no longer the supervisor's responsibility
        assert res["count_after"] == 0, (
            "after a timeout the supervisor must disown the stuck task "
            f"(active_count expected 0, got {res['count_after']})"
        )

    def test_background_exception_does_not_break_supervisor(self):
        """L2: an exception raised inside a spawned task is contained; the task
        object reports it, the supervisor stays usable, and shutdown completes."""
        body = """
        import asyncio, json
        from aiohttp.supervisor import TaskSupervisor

        class Boom(Exception):
            pass

        async def boomer():
            await asyncio.sleep(0.02)
            raise Boom("kapow")

        async def survivor():
            await asyncio.sleep(0.3)
            return "ok"

        async def main():
            sup = TaskSupervisor()
            bad = sup.spawn(boomer())
            # let the bad task fail
            await asyncio.sleep(0.1)
            exc = bad.exception()
            exc_name = type(exc).__name__ if exc is not None else None
            exc_msg = str(exc) if exc is not None else None
            count_after_fail = sup.active_count()
            # supervisor must still be usable
            good = sup.spawn(survivor())
            await asyncio.sleep(0.05)
            count_with_good = sup.active_count()
            await sup.shutdown()
            print(json.dumps({
                "exc_name": exc_name,
                "exc_msg": exc_msg,
                "count_after_fail": count_after_fail,
                "count_with_good": count_with_good,
                "count_final": sup.active_count(),
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["exc_name"] == "Boom", "the failed task must report its exception"
        assert res["exc_msg"] == "kapow"
        assert res["count_after_fail"] == 0, "the failed task must be removed from active set"
        assert res["count_with_good"] == 1, "supervisor must remain usable after a task failed"
        assert res["count_final"] == 0

    def test_async_context_manager_shuts_down_on_exit(self):
        """L2: `async with TaskSupervisor()` cancels active tasks on normal exit."""
        body = """
        import asyncio, json
        from aiohttp.supervisor import TaskSupervisor

        cancelled = []

        async def longrun(x):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.append(x)
                raise

        async def main():
            ref = {}
            async with TaskSupervisor() as sup:
                for i in range(3):
                    sup.spawn(longrun(i))
                await asyncio.sleep(0.05)
                ref["inside"] = sup.active_count()
                ref["sup"] = sup
            # after the block, shutdown should have run
            ref["after"] = ref["sup"].active_count()
            print(json.dumps({
                "inside": ref["inside"],
                "after": ref["after"],
                "cancelled": sorted(cancelled),
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["inside"] == 3
        assert res["after"] == 0, "context-manager exit must shut tasks down"
        assert res["cancelled"] == [0, 1, 2], "all tasks must be cancelled on exit"

    def test_async_context_manager_shuts_down_and_propagates_on_error(self):
        """L2: when the `async with` body raises, active tasks are still shut
        down AND the body's exception propagates unchanged."""
        body = """
        import asyncio, json
        from aiohttp.supervisor import TaskSupervisor

        cancelled = []

        class BodyError(Exception):
            pass

        async def longrun(x):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.append(x)
                raise

        async def main():
            sup_holder = {}
            raised = None
            try:
                async with TaskSupervisor() as sup:
                    sup_holder["sup"] = sup
                    for i in range(2):
                        sup.spawn(longrun(i))
                    await asyncio.sleep(0.05)
                    raise BodyError("boom-body")
            except BodyError as exc:
                raised = str(exc)
            except Exception as exc:
                raised = "OTHER:" + type(exc).__name__
            print(json.dumps({
                "raised": raised,
                "after": sup_holder["sup"].active_count(),
                "cancelled": sorted(cancelled),
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["raised"] == "boom-body", (
            f"body exception must propagate unchanged, got {res['raised']}"
        )
        assert res["after"] == 0, "tasks must be shut down even when the body raises"
        assert res["cancelled"] == [0, 1]

    def test_empty_shutdown_and_double_shutdown_safe(self):
        """L2: shutdown() on an empty supervisor completes immediately, and a
        second shutdown() is a safe no-op (no exception, count stays 0)."""
        body = """
        import asyncio, json
        from aiohttp.supervisor import TaskSupervisor

        async def longrun():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                raise

        async def main():
            # empty shutdown
            sup = TaskSupervisor()
            await sup.shutdown()
            empty_after = sup.active_count()

            # populate, shutdown, then shutdown again
            sup2 = TaskSupervisor()
            for _ in range(2):
                sup2.spawn(longrun())
            await asyncio.sleep(0.05)
            await sup2.shutdown()
            first = sup2.active_count()
            second_error = None
            try:
                await sup2.shutdown()
            except Exception as exc:
                second_error = type(exc).__name__
            print(json.dumps({
                "empty_after": empty_after,
                "first": first,
                "second_error": second_error,
                "second_count": sup2.active_count(),
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["empty_after"] == 0, "empty shutdown must complete with count 0"
        assert res["first"] == 0
        assert res["second_error"] is None, "double shutdown must not raise"
        assert res["second_count"] == 0

    def test_spawn_named_runs_coroutine_body(self):
        """L2: spawn actually runs the supplied coroutine to completion (it is not
        dropped/stubbed); a side effect from the coroutine body is observed and the
        optional name is accepted."""
        body = """
        import asyncio, json
        from aiohttp.supervisor import TaskSupervisor

        seen = []

        async def worker(tag):
            await asyncio.sleep(0.02)
            seen.append(tag)
            return tag

        async def main():
            sup = TaskSupervisor()
            t = sup.spawn(worker("alpha"), name="alpha-task")
            # the coroutine must actually be scheduled and run
            await asyncio.sleep(0.1)
            result = t.result()
            name_attr = None
            try:
                name_attr = t.get_name()
            except Exception:
                name_attr = "no-get-name"
            await sup.shutdown()
            print(json.dumps({
                "seen": seen,
                "result": result,
                "name_attr": name_attr,
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["seen"] == ["alpha"], "spawned coroutine body must actually execute"
        assert res["result"] == "alpha", "spawn must run the real coroutine, not a stub"
        # name should propagate to the underlying task when provided
        assert res["name_attr"] == "alpha-task", (
            f"name= must propagate to the created task, got {res['name_attr']}"
        )

    def test_native_deliverable_suite_passes(self):
        """L2: the task's specified command passes:
        python -m pytest tests/test_supervisor.py -v
        """
        target = os.path.join(self.REPO_DIR, "tests", "test_supervisor.py")
        assert os.path.isfile(target), "deliverable test file missing"
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                "tests/test_supervisor.py", "-v", "-p", "no:cacheprovider",
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
