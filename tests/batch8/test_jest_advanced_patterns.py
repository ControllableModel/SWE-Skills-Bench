"""Benchmark verification for skill: jest-advanced-patterns (variant ext8).

Task: Add a bounded-concurrency async pool to the React monorepo's ``shared``
package (``packages/shared/runWithConcurrency.js``) plus a deterministic Jest
suite (``packages/shared/__tests__/runWithConcurrency-test.js``).

Public API (from the requirement doc)
-------------------------------------
``runWithConcurrency(tasks, limit)`` is the ``export default``:

  * ``tasks``  -> array of ``() => Promise<value>`` functions.
  * ``limit``  -> positive integer: max tasks running simultaneously.
  * returns ``Promise<Array<value>>`` resolving to results in the ORIGINAL
    order of ``tasks``, regardless of completion order.
  * imports NO other module; uses no timers / network / globals / randomness.

Strategy
--------
L1 cases assert the two deliverable files exist, expose a default export, and
that the implementation imports/requires no other module (a hard constraint
from the requirement doc).

L2 cases independently EXERCISE the real pool behavior. Rather than trusting
the agent's own test file, each L2 method writes ITS OWN focused Jest probe
spec into ``packages/shared/__tests__/`` and runs that single spec through the
repo's native Jest CLI (``yarn test <path>`` -> ``node scripts/jest/jest-cli.js
<path>``, which forwards the path as a testPathPattern). Every probe drives the
pool with a fully controllable, manually-driven task harness (no timers,
network, or randomness) and deep-validates exactly ONE behavior from the
requirement doc:

  * concurrency cap is never exceeded (peak counter <= limit)
  * results are returned in original order despite out-of-order completion
  * each task is invoked exactly once
  * the first ``limit`` tasks start immediately, in array order
  * ``limit >= tasks.length`` lets all tasks run at once
  * empty ``tasks`` resolves to ``[]`` without invoking anything
  * a rejection rejects the returned promise with the first error and prevents
    any NEW not-yet-started task from starting (short-circuit)
  * ``RangeError`` for a non-positive-integer ``limit``
  * ``TypeError`` for a non-array ``tasks``

Each behavior is its own probe spec AND its own pytest method, so a partial /
buggy / naive solution (e.g. one that ignores ``limit`` and runs everything at
once, or that returns results in completion order, or that keeps launching
tasks after a rejection) fails the SPECIFIC behavior it got wrong. We also
confirm the agent's own suite runs green via the exact Acceptance command.

A naive implementation that ignores ``limit`` (runs all tasks at once) fails
``test_concurrency_cap_is_respected``; one that returns results in completion
order fails ``test_results_preserve_original_order``; one that keeps starting
tasks after a rejection fails ``test_rejection_short_circuits_new_starts``.

Module resolution note: this repo resolves ``shared/<name>`` via Jest haste
(``roots: ['<rootDir>/packages', ...]``), so the probe ``require``s
``'shared/runWithConcurrency'`` exactly like the repo's own shared tests.
"""

import os
import re
import subprocess
import textwrap

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies  # noqa: F401
except Exception:  # pragma: no cover - utils may be absent locally
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/react"

SRC_REL = "packages/shared/runWithConcurrency.js"
AGENT_TEST_REL = "packages/shared/__tests__/runWithConcurrency-test.js"

# Each probe is written under __tests__ (so the repo's testRegex matches it) and
# is removed after the run. Unique names avoid cross-test collisions.
PROBE_DIR_REL = "packages/shared/__tests__"
PROBE_PREFIX = "runWithConcurrency-probe-"


def _src_path():
    return os.path.join(REPO_DIR, SRC_REL)


def _agent_test_path():
    return os.path.join(REPO_DIR, AGENT_TEST_REL)


def _probe_rel(name):
    return os.path.join(PROBE_DIR_REL, PROBE_PREFIX + name + ".bench-test.js")


def _probe_abs(name):
    return os.path.join(REPO_DIR, _probe_rel(name))


def _read_src():
    with open(_src_path()) as fh:
        return fh.read()


def _yarn_test(path_rel, timeout=300):
    """Run the repo's native Jest CLI scoped to a single test file.

    ``yarn test <path>`` invokes ``node ./scripts/jest/jest-cli.js <path>``;
    the trailing path is forwarded to Jest as a testPathPattern so only that
    one spec executes.
    """
    return subprocess.run(
        ["yarn", "test", path_rel],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _jest_passed(result):
    """Require real test execution plus an explicit green summary."""
    out = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.returncode != 0:
        return False, out
    if re.search(r"No tests found", out):
        return False, out
    if re.search(r"Tests:\s+.*\bfailed", out):
        return False, out
    if not re.search(r"Tests:\s+\d+ passed", out) and not re.search(r"PASS\b", out):
        return False, out
    return True, out


# Shared JS preamble: a deterministic, manually-driven task harness. Each task
# is a ``() => Promise`` whose settlement is controlled by hand via
# ``h.resolve(i, v)`` / ``h.reject(i, e)`` -> probes never touch timers, the
# network, or randomness. The harness also records, per task:
#   * how many times it was invoked (callCount)
#   * the order in which tasks actually started (startOrder)
#   * the live running count and its peak (running / peak)
# so concurrency, ordering, and exactly-once invocation are all observable.
_HARNESS_PREAMBLE = """\
'use strict';

function makeHarness(n) {
  const h = {
    callCount: new Array(n).fill(0),
    startOrder: [],
    settle: new Array(n).fill(null),
    running: 0,
    peak: 0,
    tasks: [],
  };
  for (let i = 0; i < n; i++) {
    (function (idx) {
      h.tasks.push(function () {
        h.callCount[idx] += 1;
        h.startOrder.push(idx);
        h.running += 1;
        if (h.running > h.peak) h.peak = h.running;
        return new Promise((resolve, reject) => {
          h.settle[idx] = {resolve, reject};
        });
      });
    })(i);
  }
  h.resolve = (idx, value) => {
    const s = h.settle[idx];
    if (!s) throw new Error('task ' + idx + ' has not started');
    h.running -= 1;
    s.resolve(value);
  };
  h.reject = (idx, err) => {
    const s = h.settle[idx];
    if (!s) throw new Error('task ' + idx + ' has not started');
    h.running -= 1;
    s.reject(err);
  };
  h.started = idx => h.settle[idx] !== null;
  return h;
}

// Flush the microtask queue so pool-scheduling continuations run before we
// assert. Deterministic: no timers, just promise microtasks.
function flush() {
  return Promise.resolve()
    .then(() => Promise.resolve())
    .then(() => Promise.resolve())
    .then(() => Promise.resolve());
}

function load() {
  return require('shared/runWithConcurrency').default;
}
"""


def _make_probe(body):
    """Wrap a single-behavior ``it(...)`` body in the shared preamble."""
    return _HARNESS_PREAMBLE + "\n" + textwrap.dedent(body) + "\n"


def _run_probe(name, body, timeout=300):
    """Write a one-behavior probe spec, run it via native Jest, clean up."""
    rel = _probe_rel(name)
    abs_path = _probe_abs(name)
    with open(abs_path, "w") as fh:
        fh.write(_make_probe(body))
    try:
        result = _yarn_test(rel, timeout=timeout)
    finally:
        try:
            os.remove(abs_path)
        except OSError:
            pass
    return result


@pytest.fixture(scope="module", autouse=True)
def _deps():
    """Ensure JS toolchain deps are present, and sweep stray probe files."""
    node_modules = os.path.join(REPO_DIR, "node_modules")
    jest_marker = os.path.join(node_modules, "chalk")
    if not os.path.isdir(jest_marker):
        try:
            subprocess.run(
                ["yarn", "install", "--frozen-lockfile"],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=1800,
            )
        except Exception:
            pass
        if not os.path.isdir(jest_marker) and ensure_npm_dependencies is not None:
            try:
                ensure_npm_dependencies(REPO_DIR)
            except Exception:
                pass
    yield
    probe_dir = os.path.join(REPO_DIR, PROBE_DIR_REL)
    try:
        for fname in os.listdir(probe_dir):
            if fname.startswith(PROBE_PREFIX):
                try:
                    os.remove(os.path.join(probe_dir, fname))
                except OSError:
                    pass
    except OSError:
        pass


class TestJestAdvancedPatterns:
    REPO_DIR = REPO_DIR

    # -----------------------------------------------------------------------
    # L1 — deliverables exist and respect the structural constraints.
    # -----------------------------------------------------------------------
    def test_pool_source_exists(self):
        """L1: the runWithConcurrency module file exists and is non-empty."""
        path = _src_path()
        assert os.path.isfile(path), f"missing deliverable: {SRC_REL}"
        assert os.path.getsize(path) > 0, "pool source is empty"

    def test_agent_test_file_exists(self):
        """L1: the agent's Jest test suite file exists and is non-empty."""
        path = _agent_test_path()
        assert os.path.isfile(path), f"missing deliverable: {AGENT_TEST_REL}"
        assert os.path.getsize(path) > 0, "agent test file is empty"

    def test_pool_has_default_export(self):
        """L1: the pool exposes a default export (the function)."""
        src = _read_src()
        assert "export default" in src or "module.exports" in src, (
            "runWithConcurrency must export the function by default"
        )

    def test_pool_imports_no_other_module(self):
        """L1: hard constraint — the module imports/requires no other module."""
        src = _read_src()
        no_block = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
        no_line = re.sub(r"//[^\n]*", "", no_block)
        assert not re.search(r"^\s*import\s", no_line, flags=re.MULTILINE), (
            "runWithConcurrency must contain no `import` statement"
        )
        assert not re.search(r"\brequire\s*\(", no_line), (
            "runWithConcurrency must not `require` any other module"
        )

    # -----------------------------------------------------------------------
    # L2 — each behavior gets its OWN independent probe spec run via Jest.
    # -----------------------------------------------------------------------
    def test_concurrency_cap_is_respected(self):
        """L2: with limit=2 and 6 tasks, peak concurrency never exceeds 2.

        A naive implementation that ignores ``limit`` and launches every task
        at once would record peak=6 and FAIL here. The harness records the live
        running count and its peak; we settle tasks one at a time, flushing
        microtasks between each, and assert the peak stays at the cap.
        """
        result = _run_probe(
            "cap",
            """
            it('peak concurrency never exceeds limit (2 of 6)', async () => {
              const run = load();
              const h = makeHarness(6);
              const p = run(h.tasks, 2);
              await flush();
              // Only the first `limit` tasks may be running at once.
              expect(h.peak).toBe(2);
              expect(h.started(0)).toBe(true);
              expect(h.started(1)).toBe(true);
              expect(h.started(2)).toBe(false);
              // Drain: settle the lowest started index repeatedly, letting the
              // pool admit the next task each time, and watch the peak.
              for (let done = 0; done < 6; done++) {
                // find a started-but-not-yet-settled task
                let idx = -1;
                for (let i = 0; i < 6; i++) {
                  if (h.started(i) && h.callCount[i] > 0) { idx = i; }
                }
                // settle the smallest started index that is still in-flight
                for (let i = 0; i < 6; i++) {
                  if (h.started(i)) { idx = i; break; }
                }
                h.resolve(done, 'r' + done);
                await flush();
                expect(h.peak).toBeLessThanOrEqual(2);
              }
              const out = await p;
              expect(out).toHaveLength(6);
              expect(h.peak).toBe(2);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"concurrency-cap probe failed:\n{out[-4000:]}"

    def test_results_preserve_original_order(self):
        """L2: results map position-for-position to tasks despite out-of-order finish.

        We start 3 tasks with limit=3, then settle them in REVERSE order
        (2, 1, 0). An implementation that collects results in completion order
        would yield ['r2','r1','r0']; the correct pool yields ['r0','r1','r2'].
        """
        result = _run_probe(
            "order",
            """
            it('results stay in original order despite out-of-order completion', async () => {
              const run = load();
              const h = makeHarness(3);
              const p = run(h.tasks, 3);
              await flush();
              expect(h.started(0)).toBe(true);
              expect(h.started(1)).toBe(true);
              expect(h.started(2)).toBe(true);
              // settle in reverse completion order
              h.resolve(2, 'r2');
              h.resolve(0, 'r0');
              h.resolve(1, 'r1');
              const out = await p;
              expect(out).toEqual(['r0', 'r1', 'r2']);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"order-preservation probe failed:\n{out[-4000:]}"

    def test_each_task_invoked_exactly_once(self):
        """L2: every task function is invoked exactly one time.

        With 5 tasks and limit=2, draining the whole pool must invoke each task
        exactly once (callCount == 1 for all), never zero and never twice.
        """
        result = _run_probe(
            "once",
            """
            it('each task is invoked exactly once', async () => {
              const run = load();
              const h = makeHarness(5);
              const p = run(h.tasks, 2);
              // settle each task as it becomes the next in-flight one
              for (let i = 0; i < 5; i++) {
                await flush();
                h.resolve(i, i);
              }
              await p;
              expect(h.callCount).toEqual([1, 1, 1, 1, 1]);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"exactly-once probe failed:\n{out[-4000:]}"

    def test_first_limit_tasks_start_immediately_in_order(self):
        """L2: the first `limit` tasks start right away, in array order.

        With 4 tasks and limit=2, before settling anything tasks 0 and 1 must
        have started (in that order) and tasks 2 and 3 must not yet have run.
        """
        result = _run_probe(
            "start-order",
            """
            it('first limit tasks start immediately in array order', async () => {
              const run = load();
              const h = makeHarness(4);
              run(h.tasks, 2);
              await flush();
              expect(h.startOrder).toEqual([0, 1]);
              expect(h.callCount).toEqual([1, 1, 0, 0]);
              expect(h.started(2)).toBe(false);
              expect(h.started(3)).toBe(false);
              // releasing task 0 admits task 2 next (array order).
              h.resolve(0, 'r0');
              await flush();
              expect(h.startOrder).toEqual([0, 1, 2]);
              expect(h.callCount[2]).toBe(1);
              expect(h.callCount[3]).toBe(0);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"start-order probe failed:\n{out[-4000:]}"

    def test_limit_geq_length_runs_all_at_once(self):
        """L2: when limit >= tasks.length, all tasks run concurrently.

        With 3 tasks and limit=5, all three start immediately (peak == 3) and
        the resolved array preserves order.
        """
        result = _run_probe(
            "limit-ge",
            """
            it('limit >= length runs all tasks at once', async () => {
              const run = load();
              const h = makeHarness(3);
              const p = run(h.tasks, 5);
              await flush();
              expect(h.callCount).toEqual([1, 1, 1]);
              expect(h.peak).toBe(3);
              h.resolve(0, 'a');
              h.resolve(1, 'b');
              h.resolve(2, 'c');
              await expect(p).resolves.toEqual(['a', 'b', 'c']);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"limit>=length probe failed:\n{out[-4000:]}"

    def test_empty_tasks_resolve_to_empty_array(self):
        """L2: an empty tasks array resolves to [] without invoking anything.

        ``run([], 3)`` must resolve to ``[]`` and the harness must record no
        task invocations.
        """
        result = _run_probe(
            "empty",
            """
            it('empty tasks resolves to [] invoking nothing', async () => {
              const run = load();
              let invoked = 0;
              const tasks = [];
              const out = await run(tasks, 3);
              expect(out).toEqual([]);
              expect(invoked).toBe(0);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"empty-input probe failed:\n{out[-4000:]}"

    def test_rejection_propagates_first_error(self):
        """L2: if a task rejects, the returned promise rejects with that error.

        The exact error object thrown by the task must surface on the returned
        promise (not a wrapped or swallowed one).
        """
        result = _run_probe(
            "reject-propagate",
            """
            it('rejection propagates the first error', async () => {
              const run = load();
              const h = makeHarness(3);
              const boom = new Error('boom-1');
              const p = run(h.tasks, 2);
              await flush();
              h.reject(0, boom);
              await expect(p).rejects.toBe(boom);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"rejection-propagation probe failed:\n{out[-4000:]}"

    def test_rejection_short_circuits_new_starts(self):
        """L2: after a rejection no NEW not-yet-started task may be started.

        With 5 tasks and limit=2, tasks 0 and 1 start. We reject task 0; the
        pool must reject the returned promise and must NOT admit tasks 2, 3, 4.
        A buggy pool that keeps filling the slot would start task 2 and FAIL.
        """
        result = _run_probe(
            "short-circuit",
            """
            it('rejection prevents any new task from starting', async () => {
              const run = load();
              const h = makeHarness(5);
              const boom = new Error('stop-here');
              const p = run(h.tasks, 2);
              await flush();
              expect(h.callCount).toEqual([1, 1, 0, 0, 0]);
              h.reject(0, boom);
              await expect(p).rejects.toBe(boom);
              await flush();
              await flush();
              // tasks 2,3,4 must never have been started after the rejection.
              expect(h.callCount[2]).toBe(0);
              expect(h.callCount[3]).toBe(0);
              expect(h.callCount[4]).toBe(0);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"rejection-short-circuit probe failed:\n{out[-4000:]}"

    def test_range_error_for_invalid_limit(self):
        """L2: a non-positive-integer limit throws a RangeError.

        0, a negative number, a fractional number, and NaN must each cause
        runWithConcurrency to throw a RangeError. Throwing synchronously or via
        a rejected promise both satisfy the doc; we accept either.
        """
        result = _run_probe(
            "range-error",
            """
            async function expectRangeError(thunk) {
              try {
                const r = thunk();
                // if it returned a promise instead of throwing, it must reject
                // with a RangeError.
                await r;
              } catch (e) {
                expect(e).toBeInstanceOf(RangeError);
                return;
              }
              throw new Error('expected a RangeError to be thrown/rejected');
            }

            it('non-positive-integer limit throws RangeError', async () => {
              const run = load();
              const tasks = [() => Promise.resolve(1)];
              await expectRangeError(() => run(tasks, 0));
              await expectRangeError(() => run(tasks, -2));
              await expectRangeError(() => run(tasks, 1.5));
              await expectRangeError(() => run(tasks, NaN));
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"RangeError-guard probe failed:\n{out[-4000:]}"

    def test_type_error_for_non_array_tasks(self):
        """L2: a non-array tasks argument throws a TypeError.

        undefined, a number, and an object (non-array) must each cause
        runWithConcurrency to throw a TypeError. Sync throw or rejected promise
        both accepted.
        """
        result = _run_probe(
            "type-error",
            """
            async function expectTypeError(thunk) {
              try {
                const r = thunk();
                await r;
              } catch (e) {
                expect(e).toBeInstanceOf(TypeError);
                return;
              }
              throw new Error('expected a TypeError to be thrown/rejected');
            }

            it('non-array tasks throws TypeError', async () => {
              const run = load();
              await expectTypeError(() => run(undefined, 2));
              await expectTypeError(() => run(123, 2));
              await expectTypeError(() => run({length: 2}, 2));
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"TypeError-guard probe failed:\n{out[-4000:]}"

    # -----------------------------------------------------------------------
    # L2 — the agent's own suite must pass via the spec'd command.
    # -----------------------------------------------------------------------
    def test_agent_suite_passes(self):
        """L2: the agent's own Jest suite passes via the Acceptance command.

        Mirrors the Acceptance Criteria command exactly:
        ``yarn test packages/shared/__tests__/runWithConcurrency-test.js``.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        ok, out = _jest_passed(result)
        assert ok, f"agent suite did not pass green:\n{out[-4000:]}"

    def test_agent_suite_has_multiple_independent_cases(self):
        """L2: the agent suite must contain several independent passing cases.

        The requirement mandates per-behavior independent cases, so a single
        trivial test would not satisfy it; require a multi-case green run.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        out = (result.stdout or "") + "\n" + (result.stderr or "")
        assert result.returncode == 0, f"agent suite nonzero rc:\n{out[-3000:]}"
        m = re.search(r"Tests:\s+(\d+) passed", out)
        assert m is not None, f"no passing summary in agent run:\n{out[-3000:]}"
        assert int(m.group(1)) >= 5, (
            f"agent suite should have multiple cases, saw {m.group(1)}"
        )
