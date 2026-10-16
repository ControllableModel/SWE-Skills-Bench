"""Tests for the `xstate-state-machine` skill task (ext3 variant):
Retrying Upload Module with Backoff.

The task asks the agent to add, inside the `xstate` monorepo's core package, a
self-contained upload module factory `createUploadMachine(config)` plus a vitest
spec.  The machine runs an async `upload(payload)`, and on failure retries with a
fixed `backoffMs` delay up to `maxAttempts` total attempts, then terminates in a
**succeeded** (carrying the returned upload id) or **failed** (carrying the last
failure reason text) terminal outcome, recording the attempt count.  Deliverables:

  * packages/core/test/fixtures/uploadWithRetry.ts  (the upload module)
  * packages/core/test/uploadWithRetry.test.ts       (the agent's own spec)

These tests verify the work in two complementary ways:

  L1  -- the deliverable files exist and are minimally well-formed (the module
          imports only from the public surface ``../../src/index.ts`` and exports
          the ``createUploadMachine`` factory).

  L2  -- DYNAMIC EXECUTION.  Rather than trusting the spec the agent itself
          wrote, we inject our OWN independent vitest specs next to the fixture,
          import the agent's ``createUploadMachine`` factory, drive it through
          every Expected-Functionality scenario with the real XState actor API
          plus a ``SimulatedClock`` (fake timers), and assert on the actual
          terminal status / output payloads (success id + attempt count;
          failure reason text + attempt count) and on backoff timing semantics.
          We run each spec with the package's native command
          ``pnpm vitest run --project xstate <file>``.

Discriminators: a stub factory that hard-codes an id, ignores `maxAttempts`,
terminates on the first rejection, miscounts attempts, fakes the failure reason,
or ignores `backoffMs` timing cannot pass the independently-authored scenarios.
"""

import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/xstate"
CORE = os.path.join(REPO_DIR, "packages", "core")
TEST_DIR = os.path.join(CORE, "test")
FIXTURE = os.path.join(TEST_DIR, "fixtures", "uploadWithRetry.ts")
AGENT_SPEC = os.path.join(TEST_DIR, "uploadWithRetry.test.ts")

# Where we drop our own independent, harness-authored specs.  Kept under the
# package test dir so the `xstate` vitest project picks them up by glob.
HARNESS_PREFIX = "harnessUploadWithRetry"


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

    Returns the CompletedProcess.  We pass the path relative to the repo root,
    matching the command in the task's Acceptance Criteria:
        pnpm vitest run --project xstate <file>
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


# Common preamble for every harness spec: vitest globals are enabled
# (the xstate project config sets globals:true), the real actor API, the
# SimulatedClock, and the agent's factory.  A microtask flush helper lets
# queued promise continuations run between assertions.
PREAMBLE = textwrap.dedent(
    """\
    import { createActor, SimulatedClock } from '../src/index.ts';
    import { createUploadMachine } from './fixtures/uploadWithRetry.ts';

    // microtask flush helper: lets queued promise continuations run.
    const flush = async () => {
      for (let i = 0; i < 12; i++) {
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
        """L1: the upload module fixture file was created at the required path."""
        assert os.path.isfile(FIXTURE), f"missing upload module: {FIXTURE}"
        assert os.path.getsize(FIXTURE) > 0, "uploadWithRetry.ts is empty"

    def test_agent_spec_file_exists(self):
        """L1: the agent's own deterministic spec file was created."""
        assert os.path.isfile(AGENT_SPEC), f"missing spec: {AGENT_SPEC}"
        assert os.path.getsize(AGENT_SPEC) > 0, "uploadWithRetry.test.ts is empty"

    def test_fixture_exports_factory_and_uses_public_surface(self):
        """L1: module exports `createUploadMachine` and imports only from src/index.ts.

        We do not keyword-match behavior; we only check the import discipline
        (Acceptance Criterion: import solely from ../../src/index.ts) and that
        the named export is present so our L2 specs can import it.
        """
        with open(FIXTURE) as fh:
            src = fh.read()
        assert "createUploadMachine" in src, "factory export not found"
        # No deep reach-ins past the public index barrel.
        forbidden = [
            "../../src/StateMachine",
            "../../src/State.ts",
            "../../src/createActor",
            "from '../../src/actors",
            "../../src/SimulatedClock",
        ]
        for f in forbidden:
            assert f not in src, f"module reaches into internal file: {f}"

    # ------------------------------------------------------------------ #
    # L2: independent dynamic scenarios driving the agent's factory
    # ------------------------------------------------------------------ #
    def test_success_first_attempt(self):
        """L2: upload resolves to 'up-1' first try -> succeeded, id 'up-1', attempts=1.

        A naive factory that hard-codes a different id, or that counts attempts
        wrong, fails here.  We assert the terminal status is 'done', the output
        carries the exact returned id, and the recorded attempt count is 1.
        """
        body = textwrap.dedent(
            """\
            it('succeeds on the first attempt with attempts=1', async () => {
              let calls = 0;
              const machine = createUploadMachine({
                upload: () => { calls += 1; return Promise.resolve('up-1'); },
                maxAttempts: 3,
                backoffMs: 1000
              });
              const actor = createActor(machine, { clock: new SimulatedClock() }).start();
              actor.send({ type: 'payload', payload: { bytes: 7 } });
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              const blob = JSON.stringify({ o: snap.output, c: snap.context, v: snap.value });
              // success outcome, not a failed one.
              expect(blob.toLowerCase()).toContain('succe');
              expect(blob).toContain('up-1');
              expect(calls).toBe(1);
              // attempt count surfaced as data and equals upload invocations.
              expect(JSON.stringify({ o: snap.output, c: snap.context })).toContain('1');
            });
            """
        )
        ok, out = _passed(_run_scenario("SuccessFirst", body))
        assert ok, f"success-first-attempt scenario failed:\n{out[-3000:]}"

    def test_success_after_retries_with_backoff_timing(self):
        """L2: reject, reject, then resolve 'up-9' (maxAttempts=3) -> succeeded id 'up-9', attempts=3.

        Each retry must be separated by backoffMs of *simulated* time: advancing
        less than backoffMs must not start the next attempt; the full backoffMs
        must.  A factory that retries immediately (ignoring backoffMs) or stops
        after the first failure fails this scenario.
        """
        body = textwrap.dedent(
            """\
            it('succeeds on the third attempt with backoff-gated retries', async () => {
              const clock = new SimulatedClock();
              let calls = 0;
              const machine = createUploadMachine({
                upload: () => {
                  calls += 1;
                  if (calls < 3) return Promise.reject(new Error('flaky'));
                  return Promise.resolve('up-9');
                },
                maxAttempts: 3,
                backoffMs: 1000
              });
              const actor = createActor(machine, { clock }).start();
              actor.send({ type: 'payload', payload: { bytes: 1 } });
              await flush();
              // first attempt ran and rejected -> now waiting to retry, not terminal.
              expect(calls).toBe(1);
              expect(actor.getSnapshot().status).toBe('active');
              // sub-backoff time must NOT trigger the next attempt.
              clock.increment(999);
              await flush();
              expect(calls).toBe(1);
              expect(actor.getSnapshot().status).toBe('active');
              // crossing the full backoff starts attempt #2 (which also rejects).
              clock.increment(1);
              await flush();
              expect(calls).toBe(2);
              expect(actor.getSnapshot().status).toBe('active');
              // second backoff window -> attempt #3 resolves.
              clock.increment(1000);
              await flush();
              expect(calls).toBe(3);
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              const blob = JSON.stringify({ o: snap.output, c: snap.context, v: snap.value });
              expect(blob.toLowerCase()).toContain('succe');
              expect(blob).toContain('up-9');
              // attempts recorded equals invocations.
              expect(JSON.stringify({ o: snap.output, c: snap.context })).toContain('3');
            });
            """
        )
        ok, out = _passed(_run_scenario("RetrySuccess", body, timeout=600))
        assert ok, f"success-after-retries scenario failed:\n{out[-3500:]}"

    def test_give_up_failed_terminal_with_reason(self):
        """L2: maxAttempts=2, upload always rejects '503' -> failed, reason '503', attempts=2.

        The give-up path: after exhausting maxAttempts the machine terminates in
        a **failed** outcome carrying the last failure reason text and the attempt
        count.  A factory that retries forever, or that hard-codes a reason,
        fails here.
        """
        body = textwrap.dedent(
            """\
            it('gives up after maxAttempts with the failure reason and count', async () => {
              const clock = new SimulatedClock();
              let calls = 0;
              const machine = createUploadMachine({
                upload: () => { calls += 1; return Promise.reject(new Error('503')); },
                maxAttempts: 2,
                backoffMs: 1000
              });
              const actor = createActor(machine, { clock }).start();
              actor.send({ type: 'payload', payload: { bytes: 1 } });
              await flush();
              // first failed -> waiting, not terminal.
              expect(calls).toBe(1);
              expect(actor.getSnapshot().status).toBe('active');
              clock.increment(1000);   // backoff -> second (last) attempt.
              await flush();
              expect(calls).toBe(2);
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              const blob = JSON.stringify({ o: snap.output, c: snap.context, v: snap.value });
              expect(blob.toLowerCase()).toContain('fail');
              expect(blob).toContain('503');
              // exactly maxAttempts invocations -> no extra retry past the cap.
              expect(calls).toBe(2);
              expect(JSON.stringify({ o: snap.output, c: snap.context })).toContain('2');
            });
            """
        )
        ok, out = _passed(_run_scenario("GiveUp", body, timeout=600))
        assert ok, f"give-up scenario failed:\n{out[-3500:]}"

    def test_attempt_count_equals_upload_invocations(self):
        """L2: the recorded attempt counter equals the number of upload() calls actually made.

        With maxAttempts=4 and an upload that rejects 3 times then resolves, the
        terminal succeeded outcome must record 4 attempts and upload must have
        been invoked exactly 4 times -- not a constant, not off by one.
        """
        body = textwrap.dedent(
            """\
            it('attempt counter tracks real upload invocations', async () => {
              const clock = new SimulatedClock();
              let calls = 0;
              const machine = createUploadMachine({
                upload: () => {
                  calls += 1;
                  if (calls < 4) return Promise.reject(new Error('e' + calls));
                  return Promise.resolve('done-id');
                },
                maxAttempts: 4,
                backoffMs: 500
              });
              const actor = createActor(machine, { clock }).start();
              actor.send({ type: 'payload', payload: 'p' });
              await flush();
              for (let i = 0; i < 3; i++) {       // drive 3 backoff windows.
                clock.increment(500);
                await flush();
              }
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              expect(calls).toBe(4);
              const blob = JSON.stringify({ o: snap.output, c: snap.context });
              expect(blob).toContain('done-id');
              expect(blob).toContain('4');
              // attempts must not be a stuck constant like 1.
              expect(blob).not.toMatch(/"attempts"\\s*:\\s*1\\b/);
            });
            """
        )
        ok, out = _passed(_run_scenario("CountInvocations", body, timeout=600))
        assert ok, f"attempt-count scenario failed:\n{out[-3500:]}"

    def test_last_failure_reason_travels_from_rejection(self):
        """L2: the failed outcome reason comes from the *last* rejection, not a placeholder.

        Each attempt rejects with a distinct reason; the terminal failed outcome
        must carry the LAST one ('reason-3'), proving the reason travels from the
        rejection that produced it rather than a fixed/earlier value.
        """
        body = textwrap.dedent(
            """\
            it('failed reason is the last rejection text', async () => {
              const clock = new SimulatedClock();
              let calls = 0;
              const machine = createUploadMachine({
                upload: () => {
                  calls += 1;
                  return Promise.reject(new Error('reason-' + calls));
                },
                maxAttempts: 3,
                backoffMs: 1000
              });
              const actor = createActor(machine, { clock }).start();
              actor.send({ type: 'payload', payload: 'p' });
              await flush();
              clock.increment(1000);
              await flush();
              clock.increment(1000);
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              expect(calls).toBe(3);
              const blob = JSON.stringify({ o: snap.output, c: snap.context });
              // carries the LAST failure reason, not an earlier one.
              expect(blob).toContain('reason-3');
              expect(blob).not.toContain('reason-1');
              expect(blob).not.toContain('reason-2');
            });
            """
        )
        ok, out = _passed(_run_scenario("LastReason", body, timeout=600))
        assert ok, f"last-failure-reason scenario failed:\n{out[-3500:]}"

    def test_backoff_excludes_in_flight_upload_time(self):
        """L2: time spent inside an in-flight upload must not count toward backoffMs.

        Hold the first upload pending while burning more than backoffMs of
        simulated time.  That time must NOT trigger a second attempt (no backoff
        wait is active during upload).  Only after the upload rejects AND a full
        backoffMs elapses does attempt #2 begin.
        """
        body = textwrap.dedent(
            """\
            it('in-flight upload time does not count toward backoff', async () => {
              const clock = new SimulatedClock();
              let calls = 0;
              let rejectFirst;
              const machine = createUploadMachine({
                upload: () => {
                  calls += 1;
                  if (calls === 1) {
                    return new Promise((_res, rej) => { rejectFirst = rej; });
                  }
                  return Promise.resolve('up-2');
                },
                maxAttempts: 3,
                backoffMs: 1000
              });
              const actor = createActor(machine, { clock }).start();
              actor.send({ type: 'payload', payload: 'p' });
              await flush();
              expect(calls).toBe(1);
              // burn lots of time while the first upload is still in flight.
              clock.increment(5000);
              await flush();
              // must NOT have started a second attempt: no backoff is running.
              expect(calls).toBe(1);
              expect(actor.getSnapshot().status).toBe('active');
              // now the in-flight upload rejects -> enter backoff wait.
              rejectFirst(new Error('late'));
              await flush();
              expect(calls).toBe(1);
              // sub-backoff must not retry; full backoff does.
              clock.increment(999);
              await flush();
              expect(calls).toBe(1);
              clock.increment(1);
              await flush();
              expect(calls).toBe(2);
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              expect(JSON.stringify({ o: snap.output, c: snap.context })).toContain('up-2');
            });
            """
        )
        ok, out = _passed(_run_scenario("BackoffScope", body, timeout=600))
        assert ok, f"backoff-excludes-upload-time scenario failed:\n{out[-4000:]}"

    def test_phase_derivable_from_state_not_boolean_flags(self):
        """L2: uploading vs waiting-to-retry vs terminal are derivable from reported state.

        Per the spec the current phase must come from the machine's reported
        state (snap.value / status), not boolean flags in data.  We assert the
        reported state changes between the in-flight phase and the wait-to-retry
        phase, and that no boolean phase flag (e.g. isWaiting/isUploading=true)
        is exposed as context data.
        """
        body = textwrap.dedent(
            """\
            it('phase is reflected in reported state, not boolean data flags', async () => {
              const clock = new SimulatedClock();
              let calls = 0;
              let rejectFirst;
              const machine = createUploadMachine({
                upload: () => {
                  calls += 1;
                  if (calls === 1) {
                    return new Promise((_res, rej) => { rejectFirst = rej; });
                  }
                  return Promise.resolve('ok');
                },
                maxAttempts: 3,
                backoffMs: 1000
              });
              const actor = createActor(machine, { clock }).start();
              actor.send({ type: 'payload', payload: 'p' });
              await flush();
              const uploadingState = JSON.stringify(actor.getSnapshot().value);
              rejectFirst(new Error('x'));
              await flush();
              const waitingState = JSON.stringify(actor.getSnapshot().value);
              // the reported state must distinguish in-flight from waiting-to-retry.
              expect(waitingState).not.toBe(uploadingState);
              // no boolean phase flags masquerading as context data.
              const ctx = JSON.stringify(actor.getSnapshot().context || {});
              expect(ctx).not.toMatch(/"isUploading"\\s*:\\s*(true|false)/);
              expect(ctx).not.toMatch(/"isWaiting"\\s*:\\s*(true|false)/);
              expect(ctx).not.toMatch(/"isRetrying"\\s*:\\s*(true|false)/);
            });
            """
        )
        ok, out = _passed(_run_scenario("PhaseState", body, timeout=600))
        assert ok, f"phase-from-state scenario failed:\n{out[-3500:]}"

    def test_payload_carried_by_machine_not_resent(self):
        """L2: the payload is carried by the running machine, not re-supplied on later events.

        We supply `payload` only on the initial start event.  Across a retry the
        upload must still be invoked with that carried payload, proving the
        machine carries it rather than requiring it on each event.
        """
        body = textwrap.dedent(
            """\
            it('upload receives the payload carried by the machine across retries', async () => {
              const clock = new SimulatedClock();
              let calls = 0;
              const seen = [];
              const machine = createUploadMachine({
                upload: (payload) => {
                  calls += 1;
                  seen.push(payload);
                  if (calls === 1) return Promise.reject(new Error('retry-me'));
                  return Promise.resolve('up-final');
                },
                maxAttempts: 3,
                backoffMs: 1000
              });
              const actor = createActor(machine, { clock }).start();
              actor.send({ type: 'payload', payload: { id: 'CARRIED', n: 42 } });
              await flush();
              expect(calls).toBe(1);
              clock.increment(1000);   // retry without resending payload.
              await flush();
              expect(calls).toBe(2);
              // both invocations saw the same carried payload object.
              expect(seen.length).toBe(2);
              expect(seen[0] && seen[0].id).toBe('CARRIED');
              expect(seen[1] && seen[1].id).toBe('CARRIED');
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              expect(JSON.stringify({ o: snap.output, c: snap.context })).toContain('up-final');
            });
            """
        )
        ok, out = _passed(_run_scenario("PayloadCarried", body, timeout=600))
        assert ok, f"payload-carried scenario failed:\n{out[-3500:]}"

    def test_stray_events_do_not_short_circuit_in_flight_upload(self):
        """L2: events sent during an in-flight upload that aren't part of the retry protocol are ignored.

        While the first upload is pending we send an unrelated/stray event; it
        must NOT skip or short-circuit the in-flight attempt.  The upload still
        resolves normally to its id and the machine succeeds with attempts=1.
        """
        body = textwrap.dedent(
            """\
            it('stray event during upload does not short-circuit the attempt', async () => {
              let calls = 0;
              let resolveFirst;
              const machine = createUploadMachine({
                upload: () => {
                  calls += 1;
                  return new Promise((res) => { resolveFirst = res; });
                },
                maxAttempts: 3,
                backoffMs: 1000
              });
              const actor = createActor(machine, { clock: new SimulatedClock() }).start();
              actor.send({ type: 'payload', payload: 'p' });
              await flush();
              expect(calls).toBe(1);
              // a stray event mid-upload must not skip/finish the attempt.
              actor.send({ type: 'noopStrayEvent' });
              await flush();
              expect(actor.getSnapshot().status).toBe('active');
              expect(calls).toBe(1);
              // the in-flight upload resolves normally.
              resolveFirst('up-7');
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              const blob = JSON.stringify({ o: snap.output, c: snap.context });
              expect(blob).toContain('up-7');
              expect(blob).toContain('1');
              expect(calls).toBe(1);
            });
            """
        )
        ok, out = _passed(_run_scenario("StrayEvent", body, timeout=600))
        assert ok, f"stray-event scenario failed:\n{out[-3500:]}"

    def test_single_attempt_failure_gives_up_immediately(self):
        """L2: maxAttempts=1 with a rejecting upload -> failed immediately, attempts=1, no backoff retry.

        Boundary case: with only one attempt allowed there is no retry; the
        machine must terminate failed after the single rejection without ever
        entering a backoff wait or invoking upload twice.
        """
        body = textwrap.dedent(
            """\
            it('maxAttempts=1 fails immediately with no retry', async () => {
              const clock = new SimulatedClock();
              let calls = 0;
              const machine = createUploadMachine({
                upload: () => { calls += 1; return Promise.reject(new Error('nope')); },
                maxAttempts: 1,
                backoffMs: 1000
              });
              const actor = createActor(machine, { clock }).start();
              actor.send({ type: 'payload', payload: 'p' });
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              expect(calls).toBe(1);
              const blob = JSON.stringify({ o: snap.output, c: snap.context, v: snap.value });
              expect(blob.toLowerCase()).toContain('fail');
              expect(blob).toContain('nope');
              // advancing time must not produce a second attempt.
              clock.increment(10000);
              await flush();
              expect(calls).toBe(1);
            });
            """
        )
        ok, out = _passed(_run_scenario("SingleAttempt", body, timeout=600))
        assert ok, f"single-attempt scenario failed:\n{out[-3500:]}"

    def test_agent_spec_passes_native_command(self):
        """L2: the agent's own deterministic spec passes via the exact Acceptance-Criteria command.

        Runs `pnpm vitest run --project xstate packages/core/test/uploadWithRetry.test.ts`
        from the repo root and requires a clean pass with at least one test.
        """
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        proc = _vitest(AGENT_SPEC, timeout=600)
        ok, out = _passed(proc)
        assert ok, f"agent's uploadWithRetry.test.ts did not pass:\n{out[-4000:]}"
        # ensure it actually executed at least one test (no empty/skipped pass)
        assert ("passed" in out.lower()) or ("✓" in out), (
            f"agent spec produced no passing tests:\n{out[-2000:]}"
        )
