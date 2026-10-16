"""Tests for the `xstate-state-machine` skill task: Document Approval Workflow Module.

The task asks the agent to add, inside the `xstate` monorepo's core package, a
self-contained workflow factory `createApprovalWorkflow(config)` plus a vitest
spec, modeling a document moving through automated validation, human review and
publication.  Deliverables:

  * packages/core/test/fixtures/approvalWorkflow.ts  (the workflow module)
  * packages/core/test/approvalWorkflow.test.ts      (the agent's own spec)

These tests verify the work in two complementary ways:

  L1  -- the deliverable files exist and are minimally well-formed (import only
          from the public surface ``../../src/index.ts``).

  L2  -- DYNAMIC EXECUTION.  Rather than trusting the spec the agent itself
          wrote, we inject our OWN independent vitest spec next to the fixture,
          import the agent's ``createApprovalWorkflow`` factory, drive it through
          every Expected-Functionality scenario with the real XState actor API
          plus a ``SimulatedClock`` (fake timers), and assert on the actual
          terminal status / output payloads.  We run that spec with the package's
          native command ``pnpm vitest run --project xstate <file>``.

A stub factory that merely satisfies the agent's own assertions, or hard-codes
phase strings, cannot pass the independently-authored scenarios below.
"""

import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/xstate"
CORE = os.path.join(REPO_DIR, "packages", "core")
TEST_DIR = os.path.join(CORE, "test")
FIXTURE = os.path.join(TEST_DIR, "fixtures", "approvalWorkflow.ts")
AGENT_SPEC = os.path.join(TEST_DIR, "approvalWorkflow.test.ts")

# Where we drop our own independent, harness-authored specs.  Kept under the
# package test dir so the `xstate` vitest project picks them up by glob.
HARNESS_PREFIX = "harnessApprovalWorkflow"


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
    """Write an independent vitest spec into the core test dir and return path.

    `name` should be unique per test method to avoid cross-test interference.
    """
    path = os.path.join(TEST_DIR, f"{HARNESS_PREFIX}{name}.test.ts")
    with open(path, "w") as fh:
        fh.write(body)
    return path


# Common preamble for every harness spec: import vitest globals are enabled
# (config has globals:true), the real actor API, the SimulatedClock, and the
# agent's factory.  We re-export a tiny helper to advance fake time.
PREAMBLE = textwrap.dedent(
    """\
    import { createActor, SimulatedClock, toPromise } from '../src/index.ts';
    import { createApprovalWorkflow } from './fixtures/approvalWorkflow.ts';

    // microtask flush helper: lets queued promise continuations run.
    const flush = async () => {
      for (let i = 0; i < 8; i++) {
        await Promise.resolve();
      }
    };
    """
)


def _run_scenario(name, body, timeout=600):
    """Helper: write+run an independent spec, clean it up, return CompletedProcess."""
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
        # vitest summary lines like "Tests  1 failed | 2 passed"
        # Accept only if it explicitly shows passed and no failed count > 0.
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
        """L1: the workflow module fixture file was created at the required path."""
        assert os.path.isfile(FIXTURE), f"missing workflow module: {FIXTURE}"
        assert os.path.getsize(FIXTURE) > 0, "approvalWorkflow.ts is empty"

    def test_agent_spec_file_exists(self):
        """L1: the agent's own deterministic spec file was created."""
        assert os.path.isfile(AGENT_SPEC), f"missing spec: {AGENT_SPEC}"
        assert os.path.getsize(AGENT_SPEC) > 0, "approvalWorkflow.test.ts is empty"

    def test_fixture_exports_factory_and_uses_public_surface(self):
        """L1: module exports `createApprovalWorkflow` and imports only from src/index.ts.

        We do not keyword-match behavior; we only check the import discipline
        (Acceptance Criterion: import solely from ../../src/index.ts) and that
        the named export is present so our L2 specs can import it.
        """
        with open(FIXTURE) as fh:
            src = fh.read()
        assert "createApprovalWorkflow" in src, "factory export not found"
        # No deep reach-ins past the public index barrel.
        forbidden = ["../../src/StateMachine", "../../src/State.ts",
                     "../../src/createActor", "from '../../src/actors"]
        for f in forbidden:
            assert f not in src, f"module reaches into internal file: {f}"

    # ------------------------------------------------------------------ #
    # L2: independent dynamic scenarios driving the agent's factory
    # ------------------------------------------------------------------ #
    def test_validation_rejected_terminal(self):
        """L2: validate rejects ("missing title") -> terminal rejected, reason recorded.

        Independently start the workflow, fail validation, advance microtasks,
        and assert the actor reaches a terminal (status 'done') outcome whose
        output reports the rejection reason text 'missing title'.
        """
        body = textwrap.dedent(
            """\
            it('rejected outcome carries reason', async () => {
              const wf = createApprovalWorkflow({
                validate: () => Promise.reject(new Error('missing title')),
                publish: () => Promise.resolve('pub-x'),
                reviewWindowMs: 10_000
              });
              const actor = createActor(wf, { clock: new SimulatedClock() }).start();
              actor.send({ type: 'doc', doc: { id: 'd1' } });
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              const blob = JSON.stringify({ o: snap.output, v: snap.value });
              expect(blob).toContain('missing title');
              // It is a REJECTED outcome, not published.
              expect(blob.toLowerCase()).toContain('reject');
            });
            """
        )
        ok, out = _passed(_run_scenario("Rejected", body))
        assert ok, f"rejected-validation scenario failed:\n{out[-3000:]}"

    def test_approve_then_publish_success(self):
        """L2: validate resolves, approve, publish resolves to 'pub-42' -> published id exposed."""
        body = textwrap.dedent(
            """\
            it('published outcome exposes published id from publish() result', async () => {
              const wf = createApprovalWorkflow({
                validate: () => Promise.resolve(),
                publish: () => Promise.resolve('pub-42'),
                reviewWindowMs: 10_000
              });
              const actor = createActor(wf, { clock: new SimulatedClock() }).start();
              actor.send({ type: 'doc', doc: { id: 'd1' } });
              await flush();
              // validation done -> awaiting decision; approve.
              actor.send({ type: 'approve' });
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              const blob = JSON.stringify({ o: snap.output, v: snap.value });
              expect(blob).toContain('pub-42');
            });
            """
        )
        ok, out = _passed(_run_scenario("Published", body))
        assert ok, f"approve->publish scenario failed:\n{out[-3000:]}"

    def test_request_changes_terminal(self):
        """L2: validate resolves, reviewer requests changes (note 'tone') -> terminal changes-requested carrying note."""
        body = textwrap.dedent(
            """\
            it('changes-requested outcome carries the reviewer note', async () => {
              const wf = createApprovalWorkflow({
                validate: () => Promise.resolve(),
                publish: () => Promise.resolve('pub-1'),
                reviewWindowMs: 10_000
              });
              const actor = createActor(wf, { clock: new SimulatedClock() }).start();
              actor.send({ type: 'doc', doc: { id: 'd1' } });
              await flush();
              actor.send({ type: 'requestChanges', note: 'tone' });
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              const blob = JSON.stringify({ o: snap.output, v: snap.value });
              expect(blob).toContain('tone');
              expect(blob).not.toContain('pub-1');
            });
            """
        )
        ok, out = _passed(_run_scenario("ChangesReq", body))
        assert ok, f"request-changes scenario failed:\n{out[-3000:]}"

    def test_expiry_via_simulated_time(self):
        """L2: no decision within reviewWindowMs -> terminal expired, driven by SimulatedClock.

        We advance the simulated clock past reviewWindowMs *while awaiting a
        decision* and assert the workflow terminates in an expired outcome.
        """
        body = textwrap.dedent(
            """\
            it('expires after reviewWindowMs with no decision', async () => {
              const clock = new SimulatedClock();
              const wf = createApprovalWorkflow({
                validate: () => Promise.resolve(),
                publish: () => Promise.resolve('pub-1'),
                reviewWindowMs: 5_000
              });
              const actor = createActor(wf, { clock }).start();
              actor.send({ type: 'doc', doc: { id: 'd1' } });
              await flush();
              // still awaiting -> not terminal yet.
              expect(actor.getSnapshot().status).toBe('active');
              clock.increment(5_000);
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              const blob = JSON.stringify({ o: snap.output, v: snap.value }).toLowerCase();
              expect(blob).toContain('expir');
            });
            """
        )
        ok, out = _passed(_run_scenario("Expired", body))
        assert ok, f"expiry scenario failed:\n{out[-3000:]}"

    def test_publish_failure_returns_to_waiting_then_retry(self):
        """L2: publish rejects -> back to waiting (not terminal); approve again -> publish resolves -> published.

        This is the core discriminator: a naive factory that ends on the first
        publish attempt fails here.  We assert the workflow stays active after a
        failed publish and only terminates after a successful retry.
        """
        body = textwrap.dedent(
            """\
            it('failed publish returns to waiting and a retry can publish', async () => {
              let calls = 0;
              const wf = createApprovalWorkflow({
                validate: () => Promise.resolve(),
                publish: () => {
                  calls += 1;
                  return calls === 1
                    ? Promise.reject(new Error('boom'))
                    : Promise.resolve('pub-99');
                },
                reviewWindowMs: 50_000
              });
              const actor = createActor(wf, { clock: new SimulatedClock() }).start();
              actor.send({ type: 'doc', doc: { id: 'd1' } });
              await flush();
              actor.send({ type: 'approve' });   // first publish -> rejects
              await flush();
              // must NOT be terminal: back to awaiting decision.
              expect(actor.getSnapshot().status).toBe('active');
              actor.send({ type: 'approve' });   // retry -> resolves
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              expect(JSON.stringify(snap.output)).toContain('pub-99');
              expect(calls).toBe(2);
            });
            """
        )
        ok, out = _passed(_run_scenario("Retry", body, timeout=600))
        assert ok, f"publish-failure retry scenario failed:\n{out[-3500:]}"

    def test_decision_before_validation_settles_is_ignored(self):
        """L2: approve sent before validation settles is ignored; publish only after a post-validation approve.

        Validation is held pending; we send an early approve that must NOT cause
        a publish.  After validation resolves and a *second* approve is sent,
        publication occurs.
        """
        body = textwrap.dedent(
            """\
            it('out-of-phase approve during validation is ignored', async () => {
              let resolveValidate;
              let published = 0;
              const wf = createApprovalWorkflow({
                validate: () => new Promise((res) => { resolveValidate = res; }),
                publish: () => { published += 1; return Promise.resolve('pub-7'); },
                reviewWindowMs: 50_000
              });
              const actor = createActor(wf, { clock: new SimulatedClock() }).start();
              actor.send({ type: 'doc', doc: { id: 'd1' } });
              await flush();
              // validation still in flight -> early approve must be ignored.
              actor.send({ type: 'approve' });
              await flush();
              expect(actor.getSnapshot().status).toBe('active');
              expect(published).toBe(0);
              // now let validation finish, then a real approve publishes.
              resolveValidate();
              await flush();
              expect(published).toBe(0);   // no publish from the stale approve
              actor.send({ type: 'approve' });
              await flush();
              expect(published).toBe(1);
              expect(actor.getSnapshot().status).toBe('done');
            });
            """
        )
        ok, out = _passed(_run_scenario("EarlyApprove", body))
        assert ok, f"out-of-phase approve scenario failed:\n{out[-3500:]}"

    def test_can_approve_capability_via_snapshot(self):
        """L2: snapshot exposes whether an approve would be acted on, via the snapshot's own capability check.

        Per the spec, "can an approve be acted on now" is answered through the
        snapshot (e.g. snap.can({type:'approve'})) -- NOT string comparison.
        It must be true while awaiting a decision and false while validation is
        in flight and after a terminal outcome.
        """
        body = textwrap.dedent(
            """\
            it('snapshot.can reflects whether approve is currently actionable', async () => {
              let resolveValidate;
              const wf = createApprovalWorkflow({
                validate: () => new Promise((res) => { resolveValidate = res; }),
                publish: () => Promise.resolve('pub-7'),
                reviewWindowMs: 50_000
              });
              const actor = createActor(wf, { clock: new SimulatedClock() }).start();
              actor.send({ type: 'doc', doc: { id: 'd1' } });
              await flush();
              // validation in flight -> approve not actionable.
              expect(actor.getSnapshot().can({ type: 'approve' })).toBe(false);
              resolveValidate();
              await flush();
              // awaiting decision -> approve actionable.
              expect(actor.getSnapshot().can({ type: 'approve' })).toBe(true);
              actor.send({ type: 'approve' });
              await flush();
              // terminal -> approve no longer actionable.
              expect(actor.getSnapshot().can({ type: 'approve' })).toBe(false);
            });
            """
        )
        ok, out = _passed(_run_scenario("CanApprove", body))
        assert ok, f"snapshot.can capability scenario failed:\n{out[-3000:]}"

    def test_expiry_clock_excludes_validation_and_restarts_after_failed_publish(self):
        """L2: timer applies only to the human-decision wait; failed publish restarts the window.

        Hold validation longer than reviewWindowMs of simulated time: that time
        must NOT trigger expiry (clock only counts during the decision wait).
        After validation resolves, a full window of waiting without decision
        expires.  Separately, a failed publish must restart the wait window.
        """
        body = textwrap.dedent(
            """\
            it('validation time does not count toward expiry', async () => {
              const clock = new SimulatedClock();
              let resolveValidate;
              const wf = createApprovalWorkflow({
                validate: () => new Promise((res) => { resolveValidate = res; }),
                publish: () => Promise.resolve('pub-1'),
                reviewWindowMs: 5_000
              });
              const actor = createActor(wf, { clock }).start();
              actor.send({ type: 'doc', doc: { id: 'd1' } });
              await flush();
              // burn lots of time during validation -> must NOT expire.
              clock.increment(20_000);
              await flush();
              expect(actor.getSnapshot().status).toBe('active');
              resolveValidate();
              await flush();
              // now in waiting; a sub-window tick should not expire yet.
              clock.increment(4_000);
              await flush();
              expect(actor.getSnapshot().status).toBe('active');
              // crossing the window from entry into waiting expires it.
              clock.increment(1_000);
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              expect(JSON.stringify({ o: snap.output, v: snap.value }).toLowerCase())
                .toContain('expir');
            });

            it('failed publish restarts the wait window', async () => {
              const clock = new SimulatedClock();
              let calls = 0;
              const wf = createApprovalWorkflow({
                validate: () => Promise.resolve(),
                publish: () => {
                  calls += 1;
                  return Promise.reject(new Error('boom'));
                },
                reviewWindowMs: 5_000
              });
              const actor = createActor(wf, { clock }).start();
              actor.send({ type: 'doc', doc: { id: 'd1' } });
              await flush();
              clock.increment(4_000);          // almost expired while waiting
              await flush();
              expect(actor.getSnapshot().status).toBe('active');
              actor.send({ type: 'approve' });  // publish fails -> back to waiting
              await flush();
              expect(actor.getSnapshot().status).toBe('active');
              // window should have restarted: 4s more must NOT expire.
              clock.increment(4_000);
              await flush();
              expect(actor.getSnapshot().status).toBe('active');
              // a full fresh window from re-entry expires.
              clock.increment(1_000);
              await flush();
              expect(actor.getSnapshot().status).toBe('done');
              expect(calls).toBe(1);
            });
            """
        )
        ok, out = _passed(_run_scenario("ClockScope", body, timeout=600))
        assert ok, f"expiry-clock-scope scenario failed:\n{out[-4000:]}"

    def test_doc_carried_by_workflow_not_resent(self):
        """L2: the document under review is carried by the running workflow, not passed again on later events.

        We pass `doc` only on the initial start event.  Subsequent approve/publish
        must operate on that carried document; publish is invoked with a truthy
        document and produces the published id without the test resending `doc`.
        """
        body = textwrap.dedent(
            """\
            it('publish receives the doc carried by the workflow', async () => {
              let seen;
              const wf = createApprovalWorkflow({
                validate: () => Promise.resolve(),
                publish: (doc) => { seen = doc; return Promise.resolve('pub-55'); },
                reviewWindowMs: 50_000
              });
              const actor = createActor(wf, { clock: new SimulatedClock() }).start();
              actor.send({ type: 'doc', doc: { id: 'carried', title: 'T' } });
              await flush();
              actor.send({ type: 'approve' });   // no doc re-sent here
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              expect(seen && seen.id).toBe('carried');
              expect(JSON.stringify(snap.output)).toContain('pub-55');
            });
            """
        )
        ok, out = _passed(_run_scenario("DocCarried", body))
        assert ok, f"doc-carried scenario failed:\n{out[-3000:]}"

    def test_agent_spec_passes_native_command(self):
        """L2: the agent's own deterministic spec passes via the exact Acceptance-Criteria command.

        Runs `pnpm vitest run --project xstate packages/core/test/approvalWorkflow.test.ts`
        from the repo root and requires a clean pass with at least one test.
        """
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        proc = _vitest(AGENT_SPEC, timeout=600)
        ok, out = _passed(proc)
        assert ok, f"agent's approvalWorkflow.test.ts did not pass:\n{out[-4000:]}"
        # ensure it actually executed at least one test (no empty/skipped pass)
        assert ("passed" in out.lower()) or ("✓" in out), (
            f"agent spec produced no passing tests:\n{out[-2000:]}"
        )
