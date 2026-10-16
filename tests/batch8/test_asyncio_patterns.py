"""Tests for the `asyncio-patterns` skill task (variant ext8).

Task: add an in-process async **event broker** with topic subscriptions to the
aiohttp repository.

Deliverables under test:
  * ``aiohttp/event_broker.py`` exporting an ``EventBroker`` class.
  * ``tests/test_event_broker.py`` — the agent's own deterministic suite.

Public API (from the requirement doc):
  * ``EventBroker.subscribe(topic) -> Subscription``
  * ``async EventBroker.publish(topic, message) -> int``  (# subscribers delivered to)
  * ``async EventBroker.close()``
  * ``Subscription`` is async-iterable (``async for msg in sub``), has
    ``async aclose()`` and may be used as an async context manager.

Verified behaviors (mapped to the requirement doc):
  * The module/class exist and are importable; ``publish``/``close`` are
    coroutine functions; a subscription is async-iterable (L1).
  * The deliverable test file exists and is non-trivial (L1).
  * Two subscribers on one topic each receive every message in publish order;
    ``publish`` returns the delivered count (L2).
  * Topic isolation: a message on topic A never reaches a subscriber of B (L2).
  * Publishing to a topic with no subscribers returns 0 (L2).
  * Late-subscriber rule: a subscriber created after a publish does not see the
    earlier message, only later ones (L2).
  * A slow subscriber does not lose messages and does not block delivery to
    other subscribers (per-subscription buffering) (L2).
  * ``subscription.aclose()`` ends iteration cleanly and unsubscribes so future
    publishes ignore it (return count drops) (L2).
  * Double-close of a subscription is a no-op (L2).
  * ``broker.close()`` ends every active subscription's iteration (L2).
  * The native deliverable suite passes (L2).

Strategy: each L2 case writes a focused async driver into REPO_DIR and runs it
with the repo's own python (PYTHONPATH forced to REPO_DIR so ``import aiohttp``
resolves to the in-repo package). Assertions are on printed JSON describing the
real broker's observable behavior, so a naive/stub implementation (e.g. one that
ignores topics, drops messages for slow consumers, returns a hardcoded count,
never unsubscribes, or never stops iteration on close) cannot pass. This is
independent of whatever test file the agent authored.
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
    def test_event_broker_module_present(self):
        """L1: aiohttp/event_broker.py (the new deliverable) exists."""
        assert os.path.isfile(
            os.path.join(self.REPO_DIR, "aiohttp", "event_broker.py")
        ), "aiohttp/event_broker.py must be created"

    def test_broker_api_importable_and_async(self):
        """L1: EventBroker imports; publish/close are coroutine functions and a
        subscription is async-iterable (defines __aiter__/__anext__)."""
        body = """
        import asyncio, inspect, json
        from aiohttp.event_broker import EventBroker

        b = EventBroker()
        publish_coro = inspect.iscoroutinefunction(b.publish)
        close_coro = inspect.iscoroutinefunction(b.close)
        sub = b.subscribe("t")
        # async-iterable: must expose __aiter__; iterator must expose __anext__
        has_aiter = hasattr(sub, "__aiter__")
        it = sub.__aiter__() if has_aiter else None
        has_anext = hasattr(it, "__anext__") if it is not None else False

        async def main():
            await b.close()

        asyncio.run(main())
        print(json.dumps({
            "publish_coro": bool(publish_coro),
            "close_coro": bool(close_coro),
            "has_aiter": bool(has_aiter),
            "has_anext": bool(has_anext),
        }))
        """
        res = self._run_json(body)
        assert res["publish_coro"] is True, "EventBroker.publish must be async"
        assert res["close_coro"] is True, "EventBroker.close must be async"
        assert res["has_aiter"] is True, "Subscription must be async-iterable"
        assert res["has_anext"] is True, "Subscription iterator must define __anext__"

    def test_deliverable_test_file_present_and_nontrivial(self):
        """L1: tests/test_event_broker.py exists, references the class, and has at
        least one real test function."""
        p = os.path.join(self.REPO_DIR, "tests", "test_event_broker.py")
        assert os.path.isfile(p), "tests/test_event_broker.py must be created"
        with open(p) as fh:
            content = fh.read()
        assert "EventBroker" in content, "deliverable test must reference EventBroker"
        assert "def test_" in content, "deliverable test must define a test function"

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavior
    # ------------------------------------------------------------------ #
    def test_two_subscribers_receive_in_order(self):
        """L2: two subscribers on "news"; publish "a" then "b". Each subscriber
        iterates exactly ["a","b"] in order and each publish returns 2."""
        body = """
        import asyncio, json
        from aiohttp.event_broker import EventBroker

        async def consume(sub, n):
            out = []
            async for msg in sub:
                out.append(msg)
                if len(out) == n:
                    break
            return out

        async def main():
            b = EventBroker()
            s1 = b.subscribe("news")
            s2 = b.subscribe("news")
            t1 = asyncio.ensure_future(consume(s1, 2))
            t2 = asyncio.ensure_future(consume(s2, 2))
            await asyncio.sleep(0.01)   # let consumers reach the await point
            c1 = await b.publish("news", "a")
            c2 = await b.publish("news", "b")
            r1 = await asyncio.wait_for(t1, 2)
            r2 = await asyncio.wait_for(t2, 2)
            await b.close()
            print(json.dumps({"c1": c1, "c2": c2, "r1": r1, "r2": r2}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["c1"] == 2, "publish to 2 subscribers must return 2"
        assert res["c2"] == 2
        assert res["r1"] == ["a", "b"], "subscriber 1 must see both, in order"
        assert res["r2"] == ["a", "b"], "subscriber 2 must see both, in order"

    def test_topic_isolation(self):
        """L2: a "news" subscriber and a "sports" subscriber; publishing on "news"
        delivers only to the news subscriber (count==1) and the sports subscriber
        receives nothing."""
        body = """
        import asyncio, json
        from aiohttp.event_broker import EventBroker

        async def main():
            b = EventBroker()
            news = b.subscribe("news")
            sports = b.subscribe("sports")

            news_got = []
            sports_got = []

            async def cnews():
                async for m in news:
                    news_got.append(m)
                    break

            async def csports():
                # should never receive; bounded wait then stop
                try:
                    await asyncio.wait_for(sports.__aiter__().__anext__(), 0.2)
                    sports_got.append("UNEXPECTED")
                except asyncio.TimeoutError:
                    pass

            tn = asyncio.ensure_future(cnews())
            ts = asyncio.ensure_future(csports())
            await asyncio.sleep(0.01)
            count = await b.publish("news", "hello")
            await asyncio.wait_for(tn, 2)
            await asyncio.wait_for(ts, 2)
            await b.close()
            print(json.dumps({
                "count": count,
                "news_got": news_got,
                "sports_got": sports_got,
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["count"] == 1, "only the news subscriber should be delivered to"
        assert res["news_got"] == ["hello"]
        assert res["sports_got"] == [], "sports subscriber must not receive news"

    def test_publish_no_subscribers_returns_zero(self):
        """L2: publishing to a topic with no subscribers returns 0."""
        body = """
        import asyncio, json
        from aiohttp.event_broker import EventBroker

        async def main():
            b = EventBroker()
            n = await b.publish("empty", "x")
            # also: a subscriber on a *different* topic does not count
            b.subscribe("other")
            n2 = await b.publish("empty", "y")
            await b.close()
            print(json.dumps({"n": n, "n2": n2}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["n"] == 0, "no subscribers must return 0"
        assert res["n2"] == 0, "a subscriber on another topic must not be counted"

    def test_late_subscriber_misses_earlier_message(self):
        """L2: a subscriber created AFTER a publish does not receive that earlier
        message; it only sees messages published during its lifetime."""
        body = """
        import asyncio, json
        from aiohttp.event_broker import EventBroker

        async def main():
            b = EventBroker()
            early = b.subscribe("news")

            # publish the first message (only `early` exists)
            c1 = await b.publish("news", "first")

            # now a late subscriber joins
            late = b.subscribe("news")
            c2 = await b.publish("news", "second")

            async def collect(sub, n):
                out = []
                async for m in sub:
                    out.append(m)
                    if len(out) == n:
                        break
                return out

            # early should see ["first","second"]; late only ["second"]
            te = asyncio.ensure_future(collect(early, 2))
            tl = asyncio.ensure_future(collect(late, 1))
            early_got = await asyncio.wait_for(te, 2)
            late_got = await asyncio.wait_for(tl, 2)
            await b.close()
            print(json.dumps({
                "c1": c1, "c2": c2,
                "early_got": early_got, "late_got": late_got,
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["c1"] == 1, "only early subscriber present at first publish"
        assert res["c2"] == 2, "both subscribers present at second publish"
        assert res["early_got"] == ["first", "second"]
        assert res["late_got"] == ["second"], (
            "late subscriber must NOT see the message published before it subscribed"
        )

    def test_slow_subscriber_does_not_block_or_lose(self):
        """L2: per-subscription buffering — a slow consumer keeps every message
        (none lost) and does not delay delivery to a fast consumer on the same
        topic. We publish 5 messages up front, then drain a fast consumer fully
        while the slow one trickles; both end with the full ordered sequence."""
        body = """
        import asyncio, json
        from aiohttp.event_broker import EventBroker

        async def main():
            b = EventBroker()
            fast = b.subscribe("news")
            slow = b.subscribe("news")

            msgs = ["m0", "m1", "m2", "m3", "m4"]

            fast_got = []
            slow_got = []

            async def drain_fast():
                async for m in fast:
                    fast_got.append(m)
                    if len(fast_got) == len(msgs):
                        break

            async def drain_slow():
                async for m in slow:
                    await asyncio.sleep(0.03)  # slow consumer
                    slow_got.append(m)
                    if len(slow_got) == len(msgs):
                        break

            tf = asyncio.ensure_future(drain_fast())
            tsl = asyncio.ensure_future(drain_slow())
            await asyncio.sleep(0.01)

            counts = []
            for m in msgs:
                counts.append(await b.publish("news", m))

            # fast must finish well before slow (not blocked behind it)
            await asyncio.wait_for(tf, 2)
            fast_done_first = not tsl.done()
            await asyncio.wait_for(tsl, 3)
            await b.close()
            print(json.dumps({
                "counts": counts,
                "fast_got": fast_got,
                "slow_got": slow_got,
                "fast_done_first": bool(fast_done_first),
            }))

        asyncio.run(main())
        """
        res = self._run_json(body, timeout=120)
        assert res["counts"] == [2, 2, 2, 2, 2], "each publish reaches both subscribers"
        assert res["fast_got"] == ["m0", "m1", "m2", "m3", "m4"]
        assert res["slow_got"] == ["m0", "m1", "m2", "m3", "m4"], (
            "slow subscriber must not lose buffered messages"
        )
        assert res["fast_done_first"] is True, (
            "fast consumer must finish before slow one -> delivery is not blocked "
            "by a slow subscriber (independent per-subscription buffers)"
        )

    def test_aclose_unsubscribes_and_ends_iteration(self):
        """L2: subscription.aclose() ends the async iteration cleanly AND
        unsubscribes, so a later publish on that topic no longer counts/delivers
        to it. A second still-active subscriber keeps working."""
        body = """
        import asyncio, json
        from aiohttp.event_broker import EventBroker

        async def main():
            b = EventBroker()
            a = b.subscribe("news")
            keep = b.subscribe("news")

            a_got = []
            iteration_ended_cleanly = {"ok": False}

            async def run_a():
                async for m in a:
                    a_got.append(m)
                # falling out of the loop (no exception) means clean end
                iteration_ended_cleanly["ok"] = True

            ta = asyncio.ensure_future(run_a())
            await asyncio.sleep(0.01)

            c_before = await b.publish("news", "x")   # both present -> 2
            await asyncio.sleep(0.01)

            await a.aclose()
            await asyncio.wait_for(ta, 2)             # iteration must end

            c_after = await b.publish("news", "y")    # only keep -> 1

            keep_got = []
            async def run_keep():
                async for m in keep:
                    keep_got.append(m)
                    if len(keep_got) == 2:
                        break
            await asyncio.wait_for(asyncio.ensure_future(run_keep()), 2)

            await b.close()
            print(json.dumps({
                "c_before": c_before,
                "c_after": c_after,
                "a_got": a_got,
                "clean": iteration_ended_cleanly["ok"],
                "keep_got": keep_got,
            }))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["c_before"] == 2, "both subscribers present before aclose"
        assert res["clean"] is True, "aclose must end iteration without raising"
        assert res["a_got"] == ["x"], "closed subscriber only saw the pre-close message"
        assert res["c_after"] == 1, (
            "after aclose the subscriber must be unsubscribed -> publish counts 1"
        )
        assert res["keep_got"] == ["x", "y"], "the surviving subscriber keeps receiving"

    def test_double_close_is_noop(self):
        """L2: closing an already-closed subscription is a harmless no-op."""
        body = """
        import asyncio, json
        from aiohttp.event_broker import EventBroker

        async def main():
            b = EventBroker()
            s = b.subscribe("t")
            err = None
            try:
                await s.aclose()
                await s.aclose()   # second close must not raise
            except Exception as exc:
                err = type(exc).__name__
            await b.close()
            print(json.dumps({"err": err}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["err"] is None, f"double aclose must be a no-op, raised {res['err']}"

    def test_broker_close_ends_all_iterations(self):
        """L2: broker.close() ends every active subscription's iteration; the
        consumers' `async for` loops terminate cleanly."""
        body = """
        import asyncio, json
        from aiohttp.event_broker import EventBroker

        async def main():
            b = EventBroker()
            s1 = b.subscribe("a")
            s2 = b.subscribe("b")

            ended = {"s1": False, "s2": False}

            async def run(sub, key):
                async for _ in sub:
                    pass
                ended[key] = True

            t1 = asyncio.ensure_future(run(s1, "s1"))
            t2 = asyncio.ensure_future(run(s2, "s2"))
            await asyncio.sleep(0.02)   # consumers are now blocked awaiting

            await b.close()
            # both iterations should now finish promptly
            await asyncio.wait_for(asyncio.gather(t1, t2), 2)
            print(json.dumps({"ended": ended}))

        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["ended"]["s1"] is True, "broker.close must end subscription 1's loop"
        assert res["ended"]["s2"] is True, "broker.close must end subscription 2's loop"

    def test_async_context_manager_unsubscribes_on_exit(self):
        """L2: using a subscription as an async context manager unsubscribes it on
        exit, so a publish after the `async with` block no longer reaches it.

        Skips gracefully if the optional context-manager protocol is not provided
        (the doc marks it as "may also be used as ...")."""
        body = """
        import asyncio, json
        from aiohttp.event_broker import EventBroker

        async def main():
            b = EventBroker()
            probe = b.subscribe("news")
            supported = hasattr(probe, "__aenter__") and hasattr(probe, "__aexit__")
            await probe.aclose()

            result = {"supported": bool(supported)}
            if supported:
                got = []
                sub = b.subscribe("news")
                async with sub as s:
                    async def one():
                        async for m in s:
                            got.append(m)
                            break
                    t = asyncio.ensure_future(one())
                    await asyncio.sleep(0.01)
                    c_in = await b.publish("news", "inside")
                    await asyncio.wait_for(t, 2)
                # after the block the subscription must be unsubscribed
                c_out = await b.publish("news", "outside")
                result.update({"c_in": c_in, "c_out": c_out, "got": got})
            await b.close()
            print(json.dumps(result))

        asyncio.run(main())
        """
        res = self._run_json(body)
        if not res["supported"]:
            pytest.skip("Subscription does not implement the optional async-CM protocol")
        assert res["c_in"] == 1, "inside the block the subscription is active"
        assert res["got"] == ["inside"]
        assert res["c_out"] == 0, (
            "after exiting `async with` the subscription must be unsubscribed -> count 0"
        )

    def test_native_deliverable_suite_passes(self):
        """L2: the task's specified command passes:
        python -m pytest tests/test_event_broker.py -v
        """
        target = os.path.join(self.REPO_DIR, "tests", "test_event_broker.py")
        assert os.path.isfile(target), "deliverable test file missing"
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_event_broker.py",
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
        assert "passed" in proc.stdout, f"no tests passed in output:\n{proc.stdout[-2000:]}"
