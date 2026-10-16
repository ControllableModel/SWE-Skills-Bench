"""Benchmark verification for skill: jest-advanced-patterns (variant ext4).

Task: Add a SERIAL ASYNC TASK QUEUE to the React monorepo's ``shared`` package
(``packages/shared/createSerialQueue.js``) plus a deterministic Jest suite
(``packages/shared/__tests__/createSerialQueue-test.js``).

The queue's factory ``createSerialQueue()`` returns an object exposing exactly
``add(task) -> Promise``, ``size() -> number`` and ``onIdle() -> Promise``.
Tasks run strictly one-at-a-time, in FIFO submission order; a rejecting task
rejects only its own ``add`` promise yet must not stall the rest of the queue.

Strategy
--------
L1 cases assert the two deliverable files exist, expose a default export, and
that the implementation imports no other module (a hard constraint from the
requirement doc).

L2 cases independently EXERCISE the real queue behavior. Rather than trusting
the agent's own test file, each L2 method writes ITS OWN focused Jest probe
spec into ``packages/shared/__tests__/`` and runs that single spec through the
repo's native Jest CLI (``yarn test <path>`` -> ``node scripts/jest/jest-cli.js
<path>``, which forwards the path as a testPathPattern). Every probe drives the
queue with fully controllable, manually-resolved deferred tasks (no timers,
network, or randomness) and deep-validates exactly ONE behavior from the doc:

  * FIFO start order across three tasks
  * strict non-overlap / serialization (only one task ever running)
  * a back-to-back second task's body does not run until the first settled
  * each add() promise resolves with its OWN task's value
  * a rejecting task rejects only its own add() promise
  * failure isolation: later tasks still run after a mid-queue rejection
  * size() counts queued + running and decreases to 0 as tasks complete
  * onIdle() resolves only after the last task settles
  * onIdle() called while already idle resolves on the next microtask

Because each behavior is its own probe spec and its own pytest method, a
partial / buggy solution (e.g. one that runs tasks concurrently, drops a task
after a rejection, or mis-counts size) fails the SPECIFIC behavior it got wrong
instead of one monolithic probe. We also confirm the agent's own suite runs
green via the exact Acceptance-Criteria command.

Module resolution note: this repo resolves ``shared/<name>`` via Jest haste
(``roots: ['<rootDir>/packages', ...]``), so the probe ``require``s
``'shared/createSerialQueue'`` exactly like the repo's own shared tests.
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

SRC_REL = "packages/shared/createSerialQueue.js"
AGENT_TEST_REL = "packages/shared/__tests__/createSerialQueue-test.js"

# Each probe is written under __tests__ (so the repo's testRegex matches it) and
# is removed after the run. Unique names avoid cross-test collisions.
PROBE_DIR_REL = "packages/shared/__tests__"
PROBE_PREFIX = "createSerialQueue-probe-"


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


# Shared JS preamble: a deterministic, manually-driven "deferred task" factory.
# Each task records when its body starts and finishes (against a shared event
# log) and exposes resolve/reject so probes never touch timers, the network, or
# randomness. ``running`` lets a probe assert strict non-overlap. Injected
# verbatim into each probe spec.
_TASK_PREAMBLE = """\
'use strict';

// A shared harness producing fully controllable async tasks. Every task body
// pushes a 'start:<id>' marker, then awaits a manually settled promise, then
// pushes 'end:<id>'. `state.running` tracks concurrency so non-overlap is
// directly assertable.
function makeHarness() {
  const log = [];
  const state = {running: 0, maxRunning: 0};
  const deferreds = {};
  // Build a task whose returned promise is controlled by harness.settle(id,...).
  function task(id, value) {
    return () => {
      log.push('start:' + id);
      state.running += 1;
      if (state.running > state.maxRunning) state.maxRunning = state.running;
      return new Promise((resolve, reject) => {
        deferreds[id] = {resolve, reject};
      }).then(
        v => {
          state.running -= 1;
          log.push('end:' + id);
          return v === undefined ? value : v;
        },
        e => {
          state.running -= 1;
          log.push('reject:' + id);
          throw e;
        }
      );
    };
  }
  function resolve(id, v) {
    const d = deferreds[id];
    if (!d) throw new Error('task ' + id + ' has not started yet');
    d.resolve(v);
  }
  function reject(id, e) {
    const d = deferreds[id];
    if (!d) throw new Error('task ' + id + ' has not started yet');
    d.reject(e);
  }
  function started(id) {
    return Object.prototype.hasOwnProperty.call(deferreds, id);
  }
  // Flush pending microtasks so queue progression can be observed step by step.
  function flush() {
    return Promise.resolve().then(() => Promise.resolve());
  }
  return {task, resolve, reject, started, flush, log, state};
}

function factory() {
  return require('shared/createSerialQueue').default;
}
"""


def _make_probe(body):
    """Wrap a single-behavior ``it(...)`` body in the shared preamble."""
    return _TASK_PREAMBLE + "\n" + textwrap.dedent(body) + "\n"


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
    def test_queue_source_exists(self):
        """L1: the serial-queue module file exists and is non-empty."""
        path = _src_path()
        assert os.path.isfile(path), f"missing deliverable: {SRC_REL}"
        assert os.path.getsize(path) > 0, "queue source is empty"

    def test_agent_test_file_exists(self):
        """L1: the agent's Jest test suite file exists and is non-empty."""
        path = _agent_test_path()
        assert os.path.isfile(path), f"missing deliverable: {AGENT_TEST_REL}"
        assert os.path.getsize(path) > 0, "agent test file is empty"

    def test_queue_has_default_export(self):
        """L1: the queue module exposes a default export (the factory)."""
        src = _read_src()
        assert "export default" in src or "module.exports" in src, (
            "queue must export the factory by default"
        )

    def test_queue_imports_no_other_module(self):
        """L1: hard constraint — the module imports/requires no other module."""
        src = _read_src()
        no_block = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
        no_line = re.sub(r"//[^\n]*", "", no_block)
        assert not re.search(r"^\s*import\s", no_line, flags=re.MULTILINE), (
            "queue must contain no `import` statement"
        )
        assert not re.search(r"\brequire\s*\(", no_line), (
            "queue must not `require` any other module"
        )

    # -----------------------------------------------------------------------
    # L2 — each behavior gets its OWN independent probe spec run via Jest.
    # -----------------------------------------------------------------------
    def test_tasks_start_in_fifo_order(self):
        """L2: three added tasks start in exact submission order (FIFO).

        Adding A, B, C synchronously and settling them in order must produce a
        log whose start markers are start:A, start:B, start:C in that order.
        A naive implementation that starts tasks eagerly/out of order fails.
        """
        result = _run_probe(
            "fifo-order",
            """
            it('tasks start in FIFO submission order', async () => {
              const h = makeHarness();
              const q = factory()();
              const pa = q.add(h.task('A', 'va'));
              const pb = q.add(h.task('B', 'vb'));
              const pc = q.add(h.task('C', 'vc'));
              await h.flush();
              // Only the first task should have begun so far.
              expect(h.log).toEqual(['start:A']);
              h.resolve('A');
              await h.flush();
              expect(h.log).toEqual(['start:A', 'end:A', 'start:B']);
              h.resolve('B');
              await h.flush();
              expect(h.log).toEqual(
                ['start:A', 'end:A', 'start:B', 'end:B', 'start:C']);
              h.resolve('C');
              const [a, b, c] = await Promise.all([pa, pb, pc]);
              expect([a, b, c]).toEqual(['va', 'vb', 'vc']);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"fifo-order probe failed:\n{out[-4000:]}"

    def test_tasks_never_overlap(self):
        """L2: at most one task runs at a time regardless of submission burst.

        Five tasks added synchronously, then settled one by one, must never let
        two bodies be in-flight simultaneously: maxRunning stays 1. A concurrent
        (non-serial) implementation drives maxRunning above 1 and fails.
        """
        result = _run_probe(
            "non-overlap",
            """
            it('never runs two tasks at once (maxRunning === 1)', async () => {
              const h = makeHarness();
              const q = factory()();
              const ids = ['t0', 't1', 't2', 't3', 't4'];
              const ps = ids.map(id => q.add(h.task(id, id)));
              for (const id of ids) {
                await h.flush();
                expect(h.state.running).toBe(1);   // exactly one in flight
                expect(h.started(id)).toBe(true);
                // none of the later tasks may have started yet
                for (const other of ids) {
                  if (other > id) expect(h.started(other)).toBe(false);
                }
                h.resolve(id);
              }
              await Promise.all(ps);
              expect(h.state.maxRunning).toBe(1);
              expect(h.state.running).toBe(0);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"non-overlap probe failed:\n{out[-4000:]}"

    def test_second_task_waits_for_first_to_settle(self):
        """L2: a back-to-back second task's body does not run until the first settles.

        Two tasks added together: while the first is pending, the second must
        not have started; only after the first settles does the second begin.
        """
        result = _run_probe(
            "back-to-back",
            """
            it('second task body waits until first settles', async () => {
              const h = makeHarness();
              const q = factory()();
              const p1 = q.add(h.task('first', 1));
              const p2 = q.add(h.task('second', 2));
              await h.flush();
              expect(h.started('first')).toBe(true);
              expect(h.started('second')).toBe(false);   // not started yet
              h.resolve('first');
              await expect(p1).resolves.toBe(1);
              await h.flush();
              expect(h.started('second')).toBe(true);     // now it starts
              h.resolve('second');
              await expect(p2).resolves.toBe(2);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"back-to-back probe failed:\n{out[-4000:]}"

    def test_each_add_resolves_with_its_own_value(self):
        """L2: each add() promise settles with the result of its OWN task only.

        Tasks resolve to distinct values; every add() promise must carry exactly
        its task's value (no cross-talk between queued promises).
        """
        result = _run_probe(
            "own-value",
            """
            it('each add() resolves with its own task value', async () => {
              const h = makeHarness();
              const q = factory()();
              const pa = q.add(h.task('A', 'AAA'));
              const pb = q.add(h.task('B', 'BBB'));
              await h.flush();
              h.resolve('A', 'AAA');
              await h.flush();
              h.resolve('B', 'BBB');
              await expect(pa).resolves.toBe('AAA');
              await expect(pb).resolves.toBe('BBB');
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"own-value probe failed:\n{out[-4000:]}"

    def test_rejecting_task_rejects_only_its_own_promise(self):
        """L2: a task that rejects rejects only its own add() promise.

        The rejecting task's add() promise rejects with the thrown error; a
        sibling task added after it still resolves normally.
        """
        result = _run_probe(
            "reject-own",
            """
            it('a rejecting task rejects only its own add() promise', async () => {
              const h = makeHarness();
              const q = factory()();
              const boom = new Error('boom-mid');
              const pBad = q.add(h.task('bad'));
              const pGood = q.add(h.task('good', 'OK'));
              await h.flush();
              h.reject('bad', boom);
              await expect(pBad).rejects.toBe(boom);
              await h.flush();
              h.resolve('good', 'OK');
              await expect(pGood).resolves.toBe('OK');
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"reject-own probe failed:\n{out[-4000:]}"

    def test_failure_does_not_stall_remaining_queue(self):
        """L2: one mid-queue failure must not stall or skip the rest.

        With A (ok), B (rejects), C (ok) queued, after B rejects the queue must
        still run C; the final start order is A, B, C and C resolves.
        A buggy queue that halts on the first rejection drops C and fails.
        """
        result = _run_probe(
            "failure-isolation",
            """
            it('one failure does not stall the remaining queue', async () => {
              const h = makeHarness();
              const q = factory()();
              const boom = new Error('mid-failure');
              const pa = q.add(h.task('A', 'a'));
              const pb = q.add(h.task('B'));
              const pc = q.add(h.task('C', 'c'));
              await h.flush();
              h.resolve('A', 'a');
              await expect(pa).resolves.toBe('a');
              await h.flush();
              h.reject('B', boom);
              await expect(pb).rejects.toBe(boom);
              await h.flush();
              expect(h.started('C')).toBe(true);   // C still scheduled
              h.resolve('C', 'c');
              await expect(pc).resolves.toBe('c');
              // start markers in submission order, C definitely ran
              const starts = h.log.filter(e => e.startsWith('start:'));
              expect(starts).toEqual(['start:A', 'start:B', 'start:C']);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"failure-isolation probe failed:\n{out[-4000:]}"

    def test_size_counts_queued_plus_running(self):
        """L2: size() == queued + currently-running, decreasing to 0.

        After adding three tasks size() is 3; it decrements as each settles and
        reaches 0 when the queue drains. A stub returning a constant fails here.
        """
        result = _run_probe(
            "size",
            """
            it('size() reflects queued + running and decreases to 0', async () => {
              const h = makeHarness();
              const q = factory()();
              q.add(h.task('A', 1));
              q.add(h.task('B', 2));
              q.add(h.task('C', 3));
              expect(q.size()).toBe(3);
              await h.flush();
              expect(q.size()).toBe(3);   // one running + two queued
              h.resolve('A');
              await h.flush();
              expect(q.size()).toBe(2);
              h.resolve('B');
              await h.flush();
              expect(q.size()).toBe(1);
              h.resolve('C');
              await h.flush();
              expect(q.size()).toBe(0);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"size probe failed:\n{out[-4000:]}"

    def test_size_drops_after_rejection(self):
        """L2: size() also decrements when a task REJECTS, not only on resolve.

        A failing task must still be removed from the count so the queue does
        not leak phantom work after a rejection.
        """
        result = _run_probe(
            "size-reject",
            """
            it('size() decrements on rejection too', async () => {
              const h = makeHarness();
              const q = factory()();
              const pBad = q.add(h.task('bad'));
              const pOk = q.add(h.task('ok', 'v'));
              expect(q.size()).toBe(2);
              await h.flush();
              h.reject('bad', new Error('x'));
              await pBad.catch(() => {});
              await h.flush();
              expect(q.size()).toBe(1);
              h.resolve('ok', 'v');
              await expect(pOk).resolves.toBe('v');
              await h.flush();
              expect(q.size()).toBe(0);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"size-reject probe failed:\n{out[-4000:]}"

    def test_on_idle_resolves_after_last_task_settles(self):
        """L2: onIdle() resolves only AFTER the final task settles.

        With work pending, onIdle() must stay unresolved; it resolves once the
        queue fully drains. A naive onIdle() that resolves immediately fails.
        """
        result = _run_probe(
            "on-idle",
            """
            it('onIdle() resolves only after the last task settles', async () => {
              const h = makeHarness();
              const q = factory()();
              q.add(h.task('A', 1));
              q.add(h.task('B', 2));
              let idle = false;
              const idleP = q.onIdle().then(() => { idle = true; });
              await h.flush();
              expect(idle).toBe(false);        // still busy
              h.resolve('A');
              await h.flush();
              expect(idle).toBe(false);        // B still pending
              h.resolve('B');
              await idleP;
              expect(idle).toBe(true);
              expect(q.size()).toBe(0);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"on-idle probe failed:\n{out[-4000:]}"

    def test_on_idle_when_already_idle_resolves(self):
        """L2: onIdle() on an empty/idle queue resolves on the next microtask.

        Calling onIdle() with nothing queued must resolve (not hang, not throw),
        and must do so asynchronously (next microtask), per the doc.
        """
        result = _run_probe(
            "on-idle-empty",
            """
            it('onIdle() when already idle resolves on next microtask', async () => {
              const h = makeHarness();
              const q = factory()();
              expect(q.size()).toBe(0);
              let resolved = false;
              const p = q.onIdle().then(() => { resolved = true; });
              expect(resolved).toBe(false);    // not synchronous
              await p;                          // resolves without error
              expect(resolved).toBe(true);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"on-idle-empty probe failed:\n{out[-4000:]}"

    def test_on_idle_resolves_even_when_a_task_rejected(self):
        """L2: onIdle() still resolves after a queue containing a rejecting task.

        A rejection must not leave the queue permanently "busy": after the bad
        task rejects and the good one resolves, onIdle() resolves and size is 0.
        """
        result = _run_probe(
            "on-idle-after-reject",
            """
            it('onIdle() resolves after a rejecting task drains', async () => {
              const h = makeHarness();
              const q = factory()();
              const pBad = q.add(h.task('bad'));
              const pOk = q.add(h.task('ok', 'done'));
              let idle = false;
              const idleP = q.onIdle().then(() => { idle = true; });
              await h.flush();
              h.reject('bad', new Error('boom'));
              await pBad.catch(() => {});
              await h.flush();
              expect(idle).toBe(false);
              h.resolve('ok', 'done');
              await expect(pOk).resolves.toBe('done');
              await idleP;
              expect(idle).toBe(true);
              expect(q.size()).toBe(0);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"on-idle-after-reject probe failed:\n{out[-4000:]}"

    # -----------------------------------------------------------------------
    # L2 — the agent's own suite must pass via the spec'd command.
    # -----------------------------------------------------------------------
    def test_agent_suite_passes(self):
        """L2: the agent's own Jest suite passes via the Acceptance command.

        Mirrors the Acceptance Criteria command exactly:
        ``yarn test packages/shared/__tests__/createSerialQueue-test.js``.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        ok, out = _jest_passed(result)
        assert ok, f"agent suite did not pass green:\n{out[-4000:]}"

    def test_agent_suite_has_multiple_independent_cases(self):
        """L2: the agent suite must contain several independent passing cases.

        The requirement mandates per-behavior independent cases (FIFO, non-
        overlap, failure isolation, size, onIdle), so a single trivial test
        would not satisfy it; require a multi-case green run.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        out = (result.stdout or "") + "\n" + (result.stderr or "")
        assert result.returncode == 0, f"agent suite nonzero rc:\n{out[-3000:]}"
        m = re.search(r"Tests:\s+(\d+) passed", out)
        assert m is not None, f"no passing summary in agent run:\n{out[-3000:]}"
        assert int(m.group(1)) >= 4, (
            f"agent suite should have multiple cases, saw {m.group(1)}"
        )
