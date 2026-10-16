"""Tests for the `xstate-state-machine` skill task (variant ext9):
Parent Orchestrator with Per-Item Worker Actors.

The agent must add, inside the `xstate` monorepo's core package, a self-contained
batch-processing module `createBatchProcessor(config)` plus a vitest spec.  The
parent coordinator spawns ONE child worker actor per work item; each child runs
``process(item)`` on its own; children report their per-item outcome back to the
parent, which aggregates succeeded/failed counts and the collected successful
result values keyed by item, and reaches a terminal **done** outcome only once
every child has finished.  Deliverables:

  * packages/core/test/fixtures/batchProcessor.ts   (the batch module)
  * packages/core/test/batchProcessor.test.ts        (the agent's own spec)

Verification strategy (two complementary levels):

  L1 -- the deliverable files exist, are minimally well-formed, export the
        `createBatchProcessor` factory, and import ONLY from the public surface
        ``../../src/index.ts`` (no reach-ins to internal files).

  L2 -- DYNAMIC EXECUTION.  Rather than trusting the agent's own spec, we inject
        our OWN independent vitest specs next to the fixture, import the agent's
        ``createBatchProcessor`` factory, drive it through every
        Expected-Functionality scenario with the real XState actor API, and
        assert on concrete terminal status, aggregate counts, and keyed result
        values.  We run them with the package's native command
        ``pnpm vitest run --project xstate <file>``.

Discriminators a stub cannot satisfy:
  * a flat single-parent loop that never spawns children (we assert distinct
    child actors exist during processing and that per-item work is delegated);
  * hard-coded counts / placeholder results (we vary item lists and process
    behaviors and read the actual aggregates back);
  * "done immediately" stubs (we assert the parent stays active until BOTH a
    slow- and a fast-settling child have completed, in either order);
  * reconstructing the failure reason rather than carrying it from the child
    (we assert the exact reject message text travels into the aggregate).
"""

import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/xstate"
CORE = os.path.join(REPO_DIR, "packages", "core")
TEST_DIR = os.path.join(CORE, "test")
FIXTURE = os.path.join(TEST_DIR, "fixtures", "batchProcessor.ts")
AGENT_SPEC = os.path.join(TEST_DIR, "batchProcessor.test.ts")

# Where we drop our own independent, harness-authored specs.  Kept under the
# package test dir so the `xstate` vitest project picks them up by glob.
HARNESS_PREFIX = "harnessBatchProcessor"


# --------------------------------------------------------------------------- #
# dependency / environment setup
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module", autouse=True)
def _ensure_deps():
    """Install workspace deps with pnpm if node_modules is missing."""
    root_nm = os.path.join(REPO_DIR, "node_modules")
    if not os.path.isdir(root_nm):
        for cmd in (
            ["pnpm", "install", "--frozen-lockfile"],
            ["pnpm", "install", "--no-frozen-lockfile"],
        ):
            try:
                r = subprocess.run(
                    cmd, cwd=REPO_DIR, capture_output=True, text=True, timeout=1800
                )
            except Exception:
                continue
            if r.returncode == 0:
                break
    yield


def _vitest(spec_abspath, timeout=600):
    """Run the native vitest command for the `xstate` project on one spec file.

    Returns the CompletedProcess. We pass the path relative to the repo root,
    matching the command in the task's Acceptance Criteria.
    """
    rel = os.path.relpath(spec_abspath, REPO_DIR)
    cmd = ["pnpm", "vitest", "run", "--project", "xstate", rel]
    return subprocess.run(
        cmd, cwd=REPO_DIR, capture_output=True, text=True, timeout=timeout
    )


def _write_harness_spec(name, body):
    """Write an independent vitest spec into the core test dir and return path."""
    path = os.path.join(TEST_DIR, f"{HARNESS_PREFIX}{name}.test.ts")
    with open(path, "w") as fh:
        fh.write(body)
    return path


# Common preamble for every harness spec: vitest globals are enabled
# (config has globals:true); import the real actor API and the agent's factory.
# `flush` lets queued promise continuations run so async children settle.
PREAMBLE = textwrap.dedent(
    """\
    import { createActor } from '../src/index.ts';
    import { createBatchProcessor } from './fixtures/batchProcessor.ts';

    // microtask flush helper: lets queued promise continuations run.
    const flush = async () => {
      for (let i = 0; i < 24; i++) {
        await Promise.resolve();
      }
    };
    """
)


def _run_scenario(name, body, timeout=600):
    """Write+run an independent spec, clean it up, return CompletedProcess."""
    spec = PREAMBLE + "\n" + body
    path = _write_harness_spec(name, spec)
    try:
        return _vitest(path, timeout=timeout)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _passed(proc):
    """vitest passed iff returncode 0 and no failed tests reported."""
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, out
    # Guard against "No test files found" silently exiting 0.
    if "No test files found" in out:
        return False, out
    if "failed" in out.lower() and "0 failed" not in out.lower():
        import re

        m = re.search(r"(\d+)\s+failed", out)
        if m and int(m.group(1)) > 0:
            return False, out
    return True, out


class TestXstateStateMachine:
    REPO_DIR = "/workspace/xstate"

    # ------------------------------------------------------------------ #
    # L1: deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_fixture_file_exists(self):
        """L1: the batch module fixture file was created at the required path."""
        assert os.path.isfile(FIXTURE), f"missing batch module: {FIXTURE}"
        assert os.path.getsize(FIXTURE) > 0, "batchProcessor.ts is empty"

    def test_agent_spec_file_exists(self):
        """L1: the agent's own deterministic spec file was created."""
        assert os.path.isfile(AGENT_SPEC), f"missing spec: {AGENT_SPEC}"
        assert os.path.getsize(AGENT_SPEC) > 0, "batchProcessor.test.ts is empty"

    def test_fixture_exports_factory_and_uses_public_surface(self):
        """L1: module exports `createBatchProcessor` and imports only from src/index.ts.

        We check import discipline (Acceptance Criterion: import solely from
        ../../src/index.ts) and that the named export is present so our L2 specs
        can import it.  No behavioral keyword matching here.
        """
        with open(FIXTURE) as fh:
            src = fh.read()
        assert "createBatchProcessor" in src, "factory export not found"
        # The module must import from the public barrel only.
        assert "../../src/index" in src, (
            "module does not import from the public surface ../../src/index.ts"
        )
        # No deep reach-ins past the public index barrel.
        forbidden = [
            "../../src/StateMachine",
            "../../src/State.ts",
            "../../src/createActor",
            "from '../../src/actors",
            "from '../../src/actions",
            "../../src/spawn",
        ]
        for f in forbidden:
            assert f not in src, f"module reaches into internal file: {f}"

    def test_fixture_delegates_to_child_actors_not_flat_loop(self):
        """L1/structure: the module wires up child worker actors (spawn), not a flat loop.

        The task requires per-item work be owned by DISTINCT child actors that
        report back to the parent.  Such a design must invoke an actor-spawning
        primitive (spawn/spawnChild/invoke of an actor) and a parent-reporting
        primitive (sendParent) -- a flat single-parent loop would use neither.
        This is a cheap structural gate; the real proof is the L2 child-count
        and aggregation scenarios below.
        """
        with open(FIXTURE) as fh:
            src = fh.read()
        spawns_children = any(
            tok in src for tok in ("spawnChild", "spawn(", "spawn ", "invoke")
        )
        assert spawns_children, (
            "no actor-spawning primitive found; per-item work must be owned by "
            "distinct child actors, not inlined in the parent"
        )

    # ------------------------------------------------------------------ #
    # L2: independent dynamic scenarios driving the agent's factory
    # ------------------------------------------------------------------ #
    def test_all_success_aggregate(self):
        """L2: items ["a","b","c"], process -> uppercase => done, succeeded=3, failed=0, keyed results.

        Asserts the terminal done outcome exposes succeeded=3, failed=0, and the
        collected successful values keyed by item (a->A, b->B, c->C).  A stub
        that hard-codes counts or drops keyed results cannot match all three.
        """
        body = textwrap.dedent(
            """\
            it('all-success batch aggregates counts and keyed results', async () => {
              const proc = createBatchProcessor({
                process: (item) => Promise.resolve(String(item).toUpperCase())
              });
              const actor = createActor(proc).start();
              actor.send({ type: 'items', items: ['a', 'b', 'c'] });
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');

              // phase derivable purely from reported state.
              const blob = JSON.stringify({ v: snap.value, c: snap.context, o: snap.output });
              expect(blob.toLowerCase()).toContain('done');

              // dig out the aggregate from context or output.
              const agg = JSON.stringify({ c: snap.context, o: snap.output });
              // succeeded=3 failed=0 must be present as values.
              const ctxAndOut = { ...(snap.context || {}), ...(snap.output || {}) };
              const numbers = JSON.stringify(ctxAndOut);
              expect(numbers).toMatch(/(succeed|success)[^0-9]*3/i);
              // keyed results for each item present.
              expect(agg).toContain('A');
              expect(agg).toContain('B');
              expect(agg).toContain('C');
              // failed count is zero (no failure reason text expected).
              expect(numbers).toMatch(/(fail)[^0-9]*0/i);
            });
            """
        )
        ok, out = _passed(_run_scenario("AllSuccess", body))
        assert ok, f"all-success aggregate scenario failed:\n{out[-3500:]}"

    def test_keyed_results_actually_keyed_by_item(self):
        """L2: successful results are keyed BY ITEM, not just a flat list of values.

        process returns the item index suffixed so each value is distinct AND we
        verify each item key maps to its own produced value.  A naive impl that
        stores values without keying by item, or keys them wrongly, fails here.
        """
        body = textwrap.dedent(
            """\
            it('results map each item key to its own produced value', async () => {
              const proc = createBatchProcessor({
                process: (item) => Promise.resolve('val-' + item)
              });
              const actor = createActor(proc).start();
              actor.send({ type: 'items', items: ['p', 'q'] });
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');

              // Find the keyed results object: an object whose values include
              // 'val-p' and 'val-q', keyed by 'p' and 'q' respectively.
              const candidates = [snap.context, snap.output].filter(Boolean);
              const findResults = (root) => {
                const seen = new Set();
                const stack = [root];
                while (stack.length) {
                  const cur = stack.pop();
                  if (!cur || typeof cur !== 'object' || seen.has(cur)) continue;
                  seen.add(cur);
                  if (!Array.isArray(cur) &&
                      cur['p'] === 'val-p' && cur['q'] === 'val-q') {
                    return cur;
                  }
                  for (const k of Object.keys(cur)) {
                    const v = cur[k];
                    if (v && typeof v === 'object') stack.push(v);
                  }
                }
                return null;
              };
              let found = null;
              for (const c of candidates) {
                found = findResults(c);
                if (found) break;
              }
              expect(found).not.toBeNull();
              expect(found['p']).toBe('val-p');
              expect(found['q']).toBe('val-q');
            });
            """
        )
        ok, out = _passed(_run_scenario("Keyed", body))
        assert ok, f"keyed-results scenario failed:\n{out[-3500:]}"

    def test_mixed_success_failure_batch(self):
        """L2: items ["x","y"] with process("y") reject "bad" => succeeded=1, failed=1, x->X kept, reason 'bad'.

        The failure reason must travel from the child's rejection back into the
        parent's aggregate (not be reconstructed).  We assert the exact reject
        text 'bad' is present, the success x->'X' is recorded, and counts are 1/1.
        """
        body = textwrap.dedent(
            """\
            it('mixed batch records one success, one failure with reason', async () => {
              const proc = createBatchProcessor({
                process: (item) =>
                  item === 'y'
                    ? Promise.reject(new Error('bad'))
                    : Promise.resolve(String(item).toUpperCase())
              });
              const actor = createActor(proc).start();
              actor.send({ type: 'items', items: ['x', 'y'] });
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');

              const ctxAndOut = JSON.stringify({ c: snap.context, o: snap.output });
              // counts: succeeded 1, failed 1.
              expect(ctxAndOut).toMatch(/(succeed|success)[^0-9]*1/i);
              expect(ctxAndOut).toMatch(/(fail)[^0-9]*1/i);
              // success value for x retained.
              expect(ctxAndOut).toContain('X');
              // failure reason 'bad' carried from the rejected child.
              expect(ctxAndOut).toContain('bad');
            });
            """
        )
        ok, out = _passed(_run_scenario("Mixed", body))
        assert ok, f"mixed success/failure scenario failed:\n{out[-3500:]}"

    def test_empty_batch_immediately_done(self):
        """L2: items [] => immediately terminal done, succeeded=0, failed=0.

        An empty list must take the parent straight to done with empty aggregates.
        A stub that waits forever for children (or never reaches done) fails.
        """
        body = textwrap.dedent(
            """\
            it('empty batch goes straight to done with zero aggregates', async () => {
              let processCalls = 0;
              const proc = createBatchProcessor({
                process: (item) => { processCalls += 1; return Promise.resolve('x'); }
              });
              const actor = createActor(proc).start();
              actor.send({ type: 'items', items: [] });
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              // process must never be invoked for an empty batch.
              expect(processCalls).toBe(0);
              const ctxAndOut = JSON.stringify({ c: snap.context, o: snap.output });
              expect(ctxAndOut).toMatch(/(succeed|success)[^0-9]*0/i);
              expect(ctxAndOut).toMatch(/(fail)[^0-9]*0/i);
            });
            """
        )
        ok, out = _passed(_run_scenario("Empty", body))
        assert ok, f"empty-batch scenario failed:\n{out[-3500:]}"

    def test_not_done_until_all_children_finish(self):
        """L2: parent stays active until BOTH a slow and a fast child complete.

        We hold one item's process() pending (slow) while another resolves
        immediately (fast).  The parent must NOT be done while the slow child is
        still in flight, and must reach done only once the slow child settles.
        Discriminates against any 'done immediately' stub.
        """
        body = textwrap.dedent(
            """\
            it('parent waits for the slow child before reaching done', async () => {
              let resolveSlow;
              const proc = createBatchProcessor({
                process: (item) =>
                  item === 'slow'
                    ? new Promise((res) => { resolveSlow = res; })
                    : Promise.resolve(String(item).toUpperCase())
              });
              const actor = createActor(proc).start();
              actor.send({ type: 'items', items: ['fast', 'slow'] });
              await flush();
              // fast child settled, slow child pending -> NOT done yet.
              expect(actor.getSnapshot().status).toBe('active');
              // now settle the slow child.
              resolveSlow('SLOW');
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              const ctxAndOut = JSON.stringify({ c: snap.context, o: snap.output });
              expect(ctxAndOut).toMatch(/(succeed|success)[^0-9]*2/i);
              expect(ctxAndOut).toContain('FAST');
              expect(ctxAndOut).toContain('SLOW');
            });
            """
        )
        ok, out = _passed(_run_scenario("WaitAll", body))
        assert ok, f"wait-for-all-children scenario failed:\n{out[-3500:]}"

    def test_ordering_independence_slow_then_fast(self):
        """L2: completion is order-independent regardless of which child settles first.

        Mirror of the previous scenario but with the slow child queued first and
        the fast child resolving while the slow one is still pending.  Done must
        still occur only after BOTH settle, and aggregates must be complete.
        """
        body = textwrap.dedent(
            """\
            it('done occurs after both settle irrespective of settle order', async () => {
              let resolveSlow;
              const proc = createBatchProcessor({
                process: (item) =>
                  item === 's'
                    ? new Promise((res) => { resolveSlow = res; })
                    : Promise.resolve(String(item).toUpperCase())
              });
              const actor = createActor(proc).start();
              // slow item listed FIRST.
              actor.send({ type: 'items', items: ['s', 'f'] });
              await flush();
              // fast settled, slow pending -> still active.
              expect(actor.getSnapshot().status).toBe('active');
              resolveSlow('S-DONE');
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              const ctxAndOut = JSON.stringify({ c: snap.context, o: snap.output });
              expect(ctxAndOut).toMatch(/(succeed|success)[^0-9]*2/i);
              expect(ctxAndOut).toContain('F');
              expect(ctxAndOut).toContain('S-DONE');
            });
            """
        )
        ok, out = _passed(_run_scenario("OrderIndep", body))
        assert ok, f"ordering-independence scenario failed:\n{out[-3500:]}"

    def test_one_distinct_child_actor_per_item(self):
        """L2: the parent spawns one DISTINCT child actor per item (not a flat loop).

        While processing is in flight (children held pending), the parent's
        snapshot must expose one running child actor per item.  We hold all
        children pending and count the parent's child actors -- a flat single
        loop exposes zero children and fails this.
        """
        body = textwrap.dedent(
            """\
            it('parent has one child actor per item during processing', async () => {
              const proc = createBatchProcessor({
                // never settle: keep all children alive so we can count them.
                process: () => new Promise(() => {})
              });
              const actor = createActor(proc).start();
              actor.send({ type: 'items', items: ['i1', 'i2', 'i3'] });
              await flush();
              const snap = actor.getSnapshot();
              // still processing -> not terminal.
              expect(snap.status).toBe('active');
              const children = snap.children || {};
              const count = Object.keys(children).length;
              expect(count).toBeGreaterThanOrEqual(3);
            });
            """
        )
        ok, out = _passed(_run_scenario("ChildCount", body))
        assert ok, f"one-child-per-item scenario failed:\n{out[-3500:]}"

    def test_failure_reason_carried_not_reconstructed(self):
        """L2: a unique per-item failure reason from the child reaches the aggregate verbatim.

        We reject with a distinctive token that no stub could guess; it must
        appear in the parent's aggregate, proving the reason travelled from the
        child rather than being reconstructed from a placeholder.
        """
        body = textwrap.dedent(
            """\
            it('distinctive failure reason travels from child into aggregate', async () => {
              const TOKEN = 'reason-7f3aQ9-unique';
              const proc = createBatchProcessor({
                process: (item) =>
                  item === 'boom'
                    ? Promise.reject(new Error(TOKEN))
                    : Promise.resolve(String(item).toUpperCase())
              });
              const actor = createActor(proc).start();
              actor.send({ type: 'items', items: ['ok', 'boom'] });
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              const ctxAndOut = JSON.stringify({ c: snap.context, o: snap.output });
              expect(ctxAndOut).toContain(TOKEN);
              expect(ctxAndOut).toMatch(/(fail)[^0-9]*1/i);
              expect(ctxAndOut).toMatch(/(succeed|success)[^0-9]*1/i);
            });
            """
        )
        ok, out = _passed(_run_scenario("ReasonCarried", body))
        assert ok, f"failure-reason-carried scenario failed:\n{out[-3500:]}"

    def test_larger_batch_counts_exact(self):
        """L2: a larger heterogeneous batch yields exact succeeded/failed split.

        Six items, every third rejects -> succeeded=4, failed=2.  Hard-coded
        small counts from the earlier scenarios cannot satisfy this.
        """
        body = textwrap.dedent(
            """\
            it('six-item batch with every-third failing -> 4 ok / 2 failed', async () => {
              const proc = createBatchProcessor({
                process: (item) => {
                  const n = Number(item);
                  return (n % 3 === 2)
                    ? Promise.reject(new Error('e' + n))
                    : Promise.resolve('r' + n);
                }
              });
              const actor = createActor(proc).start();
              actor.send({ type: 'items', items: ['0','1','2','3','4','5'] });
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              const ctxAndOut = JSON.stringify({ c: snap.context, o: snap.output });
              // items 2 and 5 fail -> 2 failed, 4 succeeded.
              expect(ctxAndOut).toMatch(/(succeed|success)[^0-9]*4/i);
              expect(ctxAndOut).toMatch(/(fail)[^0-9]*2/i);
              // a couple of success values present, failure tokens too.
              expect(ctxAndOut).toContain('r0');
              expect(ctxAndOut).toContain('e2');
              expect(ctxAndOut).toContain('e5');
            });
            """
        )
        ok, out = _passed(_run_scenario("LargeBatch", body))
        assert ok, f"larger-batch exact-count scenario failed:\n{out[-3500:]}"

    def test_agent_spec_passes_native_command(self):
        """L2: the agent's own deterministic spec passes via the exact Acceptance-Criteria command.

        Runs `pnpm vitest run --project xstate packages/core/test/batchProcessor.test.ts`
        from the repo root and requires a clean pass with at least one test.
        """
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        proc = _vitest(AGENT_SPEC, timeout=600)
        ok, out = _passed(proc)
        assert ok, f"agent's batchProcessor.test.ts did not pass:\n{out[-4000:]}"
        assert ("passed" in out.lower()) or ("✓" in out), (
            f"agent spec produced no passing tests:\n{out[-2000:]}"
        )
