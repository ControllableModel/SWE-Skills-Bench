"""Tests for the `asyncio-patterns` skill task (variant ext6).

Task: add an async token-bucket rate limiter `aiohttp.rate_limit.TokenBucket`
to the aiohttp repository.

Public API under test (from the variant requirement doc):

    class TokenBucket:
        def __init__(self, rate, capacity, *, time_func=None, sleep=None) -> None: ...
        async def acquire(self, tokens: int = 1) -> None: ...
        async def __aenter__(self) -> "TokenBucket": ...
        async def __aexit__(self, exc_type, exc, tb) -> None: ...

Verified behaviors (mapped to the requirement doc):
  * The deliverable module aiohttp/rate_limit.py exists (L1).
  * TokenBucket is importable and exposes acquire + async-context-manager API (L1).
  * The deliverable test file tests/test_rate_limit.py exists and is non-trivial (L1).
  * Full bucket: first acquire returns immediately with NO sleep call (L2).
  * Insufficient tokens -> sleep requested with EXACTLY shortfall / rate seconds (L2).
  * Tokens regenerate from elapsed injected-clock time and are capped at capacity (L2).
  * acquire(0) consumes nothing and never sleeps (L2).
  * acquire(capacity + 1) raises ValueError (L2).
  * Invalid rate / capacity raise ValueError at construction (L2).
  * The async context manager takes exactly one token on entry (L2).
  * Continuous (fractional) refill at `rate` per second (L2).
  * The native deliverable test suite passes (L2).

Strategy: L2 cases inject a fake monotonic clock and a recording `sleep`
coroutine into TokenBucket, then drive the real object with the repo's own
python and assert on printed JSON. Because timing is fully deterministic via
the injected clock/sleep, a naive implementation (e.g. one that never sleeps,
ignores elapsed time, never caps at capacity, or hardcodes results) cannot
pass. This exercises the real class independently of any test the agent wrote.
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

    # Reusable preamble defining a deterministic fake clock + recording sleep,
    # then constructing a TokenBucket. Subclasses of test bodies append usage.
    _HARNESS = """
    import asyncio, json
    from aiohttp.rate_limit import TokenBucket

    class Clock:
        def __init__(self, start=0.0):
            self.t = float(start)
        def __call__(self):
            return self.t
        def advance(self, dt):
            self.t += dt

    def make_recorder():
        calls = []
        async def fake_sleep(d):
            calls.append(d)
            # do not actually wait
            return None
        return calls, fake_sleep
    """

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_rate_limit_module_present(self):
        """L1: aiohttp/rate_limit.py (the file to create) exists."""
        assert os.path.isfile(
            os.path.join(self.REPO_DIR, "aiohttp", "rate_limit.py")
        ), "aiohttp/rate_limit.py must be created"

    def test_token_bucket_importable_with_api(self):
        """L1: TokenBucket is importable and exposes the required API surface
        (acquire is a coroutine function; __aenter__/__aexit__ exist)."""
        body = self._HARNESS + """
        import inspect
        has_acquire = inspect.iscoroutinefunction(TokenBucket.acquire)
        has_aenter = hasattr(TokenBucket, "__aenter__")
        has_aexit = hasattr(TokenBucket, "__aexit__")
        print(json.dumps({
            "acquire_coro": bool(has_acquire),
            "aenter": bool(has_aenter),
            "aexit": bool(has_aexit),
        }))
        """
        res = self._run_json(body)
        assert res["acquire_coro"] is True
        assert res["aenter"] is True
        assert res["aexit"] is True

    def test_deliverable_test_file_present_and_nontrivial(self):
        """L1: tests/test_rate_limit.py exists and references the class with a real test."""
        p = os.path.join(self.REPO_DIR, "tests", "test_rate_limit.py")
        assert os.path.isfile(p), "tests/test_rate_limit.py must be created"
        with open(p) as fh:
            content = fh.read()
        assert "TokenBucket" in content
        assert "def test_" in content

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavior with injected clock + recording sleep
    # ------------------------------------------------------------------ #
    def test_full_bucket_first_acquire_no_sleep(self):
        """L2: a full bucket (capacity 5) returns immediately on acquire(1) and
        never calls sleep."""
        body = self._HARNESS + """
        async def main():
            clk = Clock()
            calls, fsleep = make_recorder()
            tb = TokenBucket(rate=1, capacity=5, time_func=clk, sleep=fsleep)
            await tb.acquire(1)
            print(json.dumps({"sleep_calls": calls}))
        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["sleep_calls"] == [], (
            f"full bucket must not sleep, got {res['sleep_calls']}"
        )

    def test_insufficient_tokens_sleep_exact_shortfall(self):
        """L2: empty the bucket then acquire(1) with rate=2 and a non-advancing
        clock -> sleep requested with exactly 0.5 seconds (shortfall / rate)."""
        body = self._HARNESS + """
        async def main():
            clk = Clock()
            calls, fsleep = make_recorder()
            # capacity 1, rate 2; start full then drain the single token.
            tb = TokenBucket(rate=2, capacity=1, time_func=clk, sleep=fsleep)
            await tb.acquire(1)          # consumes the starting token, no wait
            after_first = list(calls)
            # bucket now empty, clock did not advance -> need 1 token -> 1/2 = 0.5s
            await tb.acquire(1)
            print(json.dumps({
                "after_first": after_first,
                "all_calls": calls,
            }))
        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["after_first"] == [], "first acquire on a full bucket must not sleep"
        # exactly one sleep, of 0.5s (shortfall 1 / rate 2)
        assert len(res["all_calls"]) == 1, (
            f"second acquire should sleep exactly once, got {res['all_calls']}"
        )
        assert abs(res["all_calls"][0] - 0.5) < 1e-9, (
            f"sleep must be shortfall/rate = 0.5s, got {res['all_calls'][0]}"
        )

    def test_refill_proportional_to_elapsed(self):
        """L2: after consuming, advancing the clock regenerates exactly rate*dt
        tokens so a subsequent acquire within that budget needs no sleep, and one
        just beyond it sleeps for the precise remaining shortfall."""
        body = self._HARNESS + """
        async def main():
            clk = Clock()
            calls, fsleep = make_recorder()
            # rate=4 tokens/sec, capacity=10, start full (10 tokens).
            tb = TokenBucket(rate=4, capacity=10, time_func=clk, sleep=fsleep)
            await tb.acquire(10)         # drain completely, full bucket -> no sleep
            drained_calls = list(calls)
            clk.advance(1.0)             # +4 tokens available
            await tb.acquire(4)          # exactly 4 available -> no sleep
            mid_calls = list(calls)
            # now empty again; advance 0.5s -> +2 tokens; ask for 3 -> short by 1
            clk.advance(0.5)
            await tb.acquire(3)          # need 1 more token at rate 4 -> 0.25s
            print(json.dumps({
                "drained": drained_calls,
                "mid": mid_calls,
                "final": calls,
            }))
        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["drained"] == [], "draining a full bucket must not sleep"
        assert res["mid"] == [], "consuming exactly the refilled tokens must not sleep"
        assert len(res["final"]) == 1, f"only the last acquire should sleep: {res['final']}"
        assert abs(res["final"][0] - 0.25) < 1e-9, (
            f"shortfall 1 token at rate 4 -> 0.25s, got {res['final'][0]}"
        )

    def test_tokens_capped_at_capacity(self):
        """L2: advancing the clock far beyond what is needed to fill the bucket
        does not let available tokens exceed capacity.

        rate=1, capacity=3, start full, drain, advance 10s. Only <=3 tokens are
        available, so acquire(3) succeeds with no sleep but acquire(4) raises
        ValueError (over capacity) and, crucially, acquiring more than 3 in two
        steps (3 then 1) forces a sleep proving only 3 were ever available."""
        body = self._HARNESS + """
        async def main():
            clk = Clock()
            calls, fsleep = make_recorder()
            tb = TokenBucket(rate=1, capacity=3, time_func=clk, sleep=fsleep)
            await tb.acquire(3)          # drain full bucket, no sleep
            clk.advance(10.0)            # would be +10 tokens, but capped at 3
            await tb.acquire(3)          # exactly the cap -> no sleep
            no_sleep_yet = list(calls)
            # bucket now empty; without advancing further, acquire(1) must sleep 1s
            await tb.acquire(1)
            print(json.dumps({
                "no_sleep_yet": no_sleep_yet,
                "final": calls,
            }))
        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["no_sleep_yet"] == [], (
            "after 10s of refill capped at capacity=3, acquire(3) must not sleep"
        )
        assert len(res["final"]) == 1, f"the over-cap acquire should sleep once: {res['final']}"
        assert abs(res["final"][0] - 1.0) < 1e-9, (
            f"only 3 tokens were ever available (cap), so acquire(1) sleeps 1s; got {res['final'][0]}"
        )

    def test_acquire_zero_is_noop(self):
        """L2: acquire(0) returns immediately, consumes nothing, and never sleeps."""
        body = self._HARNESS + """
        async def main():
            clk = Clock()
            calls, fsleep = make_recorder()
            tb = TokenBucket(rate=1, capacity=2, time_func=clk, sleep=fsleep)
            await tb.acquire(0)
            zero_calls = list(calls)
            # the two starting tokens must still be present: two acquire(1) with
            # no clock advance must not sleep.
            await tb.acquire(1)
            await tb.acquire(1)
            no_sleep = list(calls)
            print(json.dumps({"zero_calls": zero_calls, "no_sleep": no_sleep}))
        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["zero_calls"] == [], "acquire(0) must not sleep"
        assert res["no_sleep"] == [], (
            "acquire(0) must not consume tokens; two later acquire(1) on a "
            f"capacity-2 bucket must not sleep, got {res['no_sleep']}"
        )

    def test_over_capacity_acquire_raises(self):
        """L2: acquire(capacity + 1) raises ValueError."""
        body = self._HARNESS + """
        async def main():
            clk = Clock()
            calls, fsleep = make_recorder()
            tb = TokenBucket(rate=1, capacity=5, time_func=clk, sleep=fsleep)
            outcome = None
            try:
                await tb.acquire(6)
                outcome = "no-raise"
            except ValueError:
                outcome = "ValueError"
            except Exception as exc:
                outcome = type(exc).__name__
            print(json.dumps({"outcome": outcome, "sleeps": calls}))
        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["outcome"] == "ValueError", (
            f"acquire(capacity+1) must raise ValueError, got {res['outcome']}"
        )

    def test_invalid_construction_raises(self):
        """L2: invalid rate (<=0) and invalid capacity (<1) raise ValueError."""
        body = self._HARNESS + """
        def classify(fn):
            try:
                fn()
                return "no-raise"
            except ValueError:
                return "ValueError"
            except Exception as exc:
                return type(exc).__name__

        results = {
            "rate0": classify(lambda: TokenBucket(rate=0, capacity=5)),
            "rate_neg": classify(lambda: TokenBucket(rate=-1, capacity=5)),
            "cap0": classify(lambda: TokenBucket(rate=1, capacity=0)),
            "cap_neg": classify(lambda: TokenBucket(rate=1, capacity=-3)),
            "valid": classify(lambda: TokenBucket(rate=1, capacity=1)),
        }
        print(json.dumps(results))
        """
        res = self._run_json(body)
        assert res["rate0"] == "ValueError", f"rate=0 must raise ValueError, got {res['rate0']}"
        assert res["rate_neg"] == "ValueError", f"rate<0 must raise ValueError, got {res['rate_neg']}"
        assert res["cap0"] == "ValueError", f"capacity=0 must raise ValueError, got {res['cap0']}"
        assert res["cap_neg"] == "ValueError", f"capacity<0 must raise ValueError, got {res['cap_neg']}"
        assert res["valid"] == "no-raise", "rate=1,capacity=1 must construct fine"

    def test_context_manager_takes_one_token(self):
        """L2: entering the async context manager acquires exactly one token.

        Use a capacity-1 bucket: the first `async with` succeeds with no sleep,
        and a second acquire(1) immediately afterwards (no clock advance) must
        sleep, proving the context manager consumed the single token on entry."""
        body = self._HARNESS + """
        async def main():
            clk = Clock()
            calls, fsleep = make_recorder()
            tb = TokenBucket(rate=1, capacity=1, time_func=clk, sleep=fsleep)
            async with tb as entered:
                same = entered is tb
            after_enter = list(calls)
            # bucket should now be empty; acquiring another token without
            # advancing the clock must request a 1.0s sleep.
            await tb.acquire(1)
            print(json.dumps({
                "same": bool(same),
                "after_enter": after_enter,
                "final": calls,
            }))
        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["same"] is True, "__aenter__ should return the bucket itself"
        assert res["after_enter"] == [], "entering a full capacity-1 bucket must not sleep"
        assert len(res["final"]) == 1 and abs(res["final"][0] - 1.0) < 1e-9, (
            "context entry must consume exactly one token; subsequent acquire(1) "
            f"on the now-empty bucket sleeps 1s, got {res['final']}"
        )

    def test_fractional_refill_precision(self):
        """L2: refill is continuous/fractional, not integer-stepped.

        rate=3, capacity=10, drain fully, advance 0.5s -> 1.5 tokens available.
        acquire(1) consumes 1 (no sleep, 0.5 left); acquire(1) again is short by
        0.5 token -> sleep 0.5/3 s. This fails any integer-bucket or no-refill
        implementation."""
        body = self._HARNESS + """
        async def main():
            clk = Clock()
            calls, fsleep = make_recorder()
            tb = TokenBucket(rate=3, capacity=10, time_func=clk, sleep=fsleep)
            await tb.acquire(10)          # drain, full bucket -> no sleep
            clk.advance(0.5)             # +1.5 tokens
            await tb.acquire(1)          # 1.5 >= 1 -> no sleep, 0.5 left
            after_one = list(calls)
            await tb.acquire(1)          # short by 0.5 token -> 0.5/3 s
            print(json.dumps({"after_one": after_one, "final": calls}))
        asyncio.run(main())
        """
        res = self._run_json(body)
        assert res["after_one"] == [], "1.5 available tokens cover acquire(1) without sleep"
        assert len(res["final"]) == 1, f"second acquire should sleep once: {res['final']}"
        assert abs(res["final"][0] - (0.5 / 3.0)) < 1e-9, (
            f"shortfall 0.5 token at rate 3 -> {0.5/3.0}s, got {res['final'][0]}"
        )

    def test_native_deliverable_suite_passes(self):
        """L2: the task's specified command passes:
        python -m pytest tests/test_rate_limit.py -v
        """
        target = os.path.join(self.REPO_DIR, "tests", "test_rate_limit.py")
        assert os.path.isfile(target), "deliverable test file missing"
        env = dict(os.environ)
        env["PYTHONPATH"] = self.REPO_DIR
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                "tests/test_rate_limit.py", "-v",
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
