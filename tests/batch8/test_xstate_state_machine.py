"""Tests for the `xstate-state-machine` skill task (ext8): Notifying Form Machine.

The task asks the agent to add, inside the `xstate` monorepo's core package, a
self-contained form module `createNotifyingForm(config)` plus a vitest spec.  The
form tracks finite phases -- **editing**, **submitting**, terminal **submitted** --
and a current field value with a non-empty validity check.  Crucially it must
**emit outcome notifications outward** to the surrounding system (via the
machine's own emit / actorRef.on mechanism), NOT merely leave values in context:

  * a `validation-failed` notification when a submit is attempted with an empty
    value (and `submit` is never invoked),
  * a `submitted` notification carrying the confirmation id when `submit`
    resolves (terminal **submitted**),
  * a `submit-failed` notification carrying the failure reason when `submit`
    rejects (returning to **editing** so the user can retry).

Deliverables:
  * packages/core/test/fixtures/notifyingForm.ts   (the form module)
  * packages/core/test/notifyingForm.test.ts        (the agent's own spec)

Verification strategy
---------------------
L1  -- the deliverable files exist, are non-empty, export the factory, and
        import only from the public surface ``../../src/index.ts``.

L2  -- DYNAMIC EXECUTION.  Rather than trusting the spec the agent itself wrote,
        we inject our OWN independent vitest specs next to the fixture, import
        the agent's ``createNotifyingForm`` factory, drive it through every
        Expected-Functionality scenario with the real XState actor API, and --
        critically -- subscribe to the actor's OUTWARD notifications via
        ``actor.on(...)`` and assert on the emitted payloads (not on context).
        We also assert phase via ``snapshot.value`` and the
        "can a submit be acted on now" capability via ``snapshot.can(...)``.
        Each independent spec is run with the package's native command
        ``pnpm vitest run --project xstate <file>`` (the Acceptance command).

Discriminators a naive/stub factory cannot pass:
  * empty-value submit emits a distinct ``validation-failed`` notification AND
    never calls ``submit`` -> a stub that always runs submit, or never emits,
    fails;
  * the confirmation id / failure reason must travel with the async result
    (so the notification payload must contain the *actual* resolved/rejected
    value, not a hard-coded placeholder);
  * a rejected submit must return to **editing** and a *second* submit must
    succeed -> a factory that terminates on first submit attempt fails;
  * "can submit" must come from the snapshot's own capability check, true only
    when the value is non-empty and the form is editing.
"""

import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/xstate"
CORE = os.path.join(REPO_DIR, "packages", "core")
TEST_DIR = os.path.join(CORE, "test")
FIXTURE = os.path.join(TEST_DIR, "fixtures", "notifyingForm.ts")
AGENT_SPEC = os.path.join(TEST_DIR, "notifyingForm.test.ts")

# Where we drop our own independent, harness-authored specs.  Kept under the
# package test dir so the `xstate` vitest project picks them up by glob.
HARNESS_PREFIX = "harnessNotifyingForm"


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

    Passes the path relative to the repo root, matching the command in the
    task's Acceptance Criteria:
        pnpm vitest run --project xstate <file>
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


# Common preamble for every harness spec: vitest globals are enabled (config has
# globals:true), the real actor API, and the agent's factory.  We add a microtask
# flush helper so queued promise continuations (the async submit) run, and a
# small `collect` helper that subscribes to a notification channel and records
# every emitted payload.
PREAMBLE = textwrap.dedent(
    """\
    import { createActor, SimulatedClock } from '../src/index.ts';
    import { createNotifyingForm } from './fixtures/notifyingForm.ts';

    // microtask flush helper: lets queued promise continuations run.
    const flush = async () => {
      for (let i = 0; i < 12; i++) {
        await Promise.resolve();
      }
    };

    // subscribe to ALL outward notifications and record them, so a test can
    // assert on emitted payloads regardless of the exact event-type spelling.
    const recordAll = (actor) => {
      const events = [];
      actor.on('*', (ev) => { events.push(ev); });
      return events;
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
        """L1: the form module fixture file was created at the required path."""
        assert os.path.isfile(FIXTURE), f"missing form module: {FIXTURE}"
        assert os.path.getsize(FIXTURE) > 0, "notifyingForm.ts is empty"

    def test_agent_spec_file_exists(self):
        """L1: the agent's own deterministic spec file was created."""
        assert os.path.isfile(AGENT_SPEC), f"missing spec: {AGENT_SPEC}"
        assert os.path.getsize(AGENT_SPEC) > 0, "notifyingForm.test.ts is empty"

    def test_fixture_exports_factory_and_uses_public_surface(self):
        """L1: module exports `createNotifyingForm` and imports only from src/index.ts.

        We do not keyword-match behavior; we only check the import discipline
        (Acceptance Criterion: import solely from ../../src/index.ts) and that
        the named export is present so our L2 specs can import it.
        """
        with open(FIXTURE) as fh:
            src = fh.read()
        assert "createNotifyingForm" in src, "factory export not found"
        # No deep reach-ins past the public index barrel.
        forbidden = [
            "../../src/StateMachine",
            "../../src/State.ts",
            "../../src/createActor",
            "from '../../src/actors",
            "from '../../src/actions",
        ]
        for f in forbidden:
            assert f not in src, f"module reaches into internal file: {f}"

    # ------------------------------------------------------------------ #
    # L2: independent dynamic scenarios driving the agent's factory
    # ------------------------------------------------------------------ #
    def test_starts_editing_with_empty_value(self):
        """L2: the form starts in the editing phase with an empty value.

        Phase is derived purely from the reported state (snapshot.value), and an
        empty value must not be submittable -- queried via the snapshot's own
        capability check, not a string comparison.
        """
        body = textwrap.dedent(
            """\
            it('starts editing, empty value, submit not actionable', async () => {
              let called = 0;
              const form = createNotifyingForm({
                submit: () => { called += 1; return Promise.resolve('cnf-0'); },
              });
              const actor = createActor(form, { clock: new SimulatedClock() }).start();
              const snap = actor.getSnapshot();
              // phase derivable from reported state
              expect(JSON.stringify(snap.value).toLowerCase()).toContain('edit');
              expect(snap.status).toBe('active');
              // empty value -> a submit must not be actionable per snapshot.can
              expect(snap.can({ type: 'submit' })).toBe(false);
              expect(called).toBe(0);
            });
            """
        )
        ok, out = _passed(_run_scenario("Start", body))
        assert ok, f"start-editing scenario failed:\n{out[-3000:]}"

    def test_empty_submit_emits_validation_failed_and_never_calls_submit(self):
        """L2: submit with empty value -> stays editing, emits validation-failed, submit never called.

        Core discriminator: a stub that always runs submit, or that emits nothing,
        fails.  We subscribe to outward notifications and require a distinct
        validation-failed notification while `submit` is never invoked, and the
        phase stays editing.
        """
        body = textwrap.dedent(
            """\
            it('empty submit emits validation-failed and does not call submit', async () => {
              let called = 0;
              const form = createNotifyingForm({
                submit: () => { called += 1; return Promise.resolve('cnf-1'); },
              });
              const actor = createActor(form, { clock: new SimulatedClock() }).start();
              const events = recordAll(actor);
              actor.send({ type: 'submit' });   // empty value -> ignored
              await flush();
              const snap = actor.getSnapshot();
              // still editing, not submitting/submitted
              expect(JSON.stringify(snap.value).toLowerCase()).toContain('edit');
              expect(snap.status).toBe('active');
              // submit() never invoked
              expect(called).toBe(0);
              // a distinct validation-failed notification was emitted outward
              const types = events.map((e) => e.type);
              const blob = JSON.stringify(events).toLowerCase();
              expect(blob).toContain('validation');
              // it must NOT be a submitted/submit-failed notification
              expect(blob).not.toContain('cnf-1');
            });
            """
        )
        ok, out = _passed(_run_scenario("ValidationFailed", body))
        assert ok, f"validation-failed scenario failed:\n{out[-3500:]}"

    def test_change_then_submit_resolves_emits_submitted_with_id(self):
        """L2: change to "x", submit, submit resolves to "cnf-7" -> terminal submitted, notification carries cnf-7.

        The confirmation id must travel with the async result (no placeholder),
        so the emitted submitted-notification payload must contain the literal
        resolved id, and the phase must reach terminal submitted.
        """
        body = textwrap.dedent(
            """\
            it('successful submit emits submitted carrying the resolved id', async () => {
              const form = createNotifyingForm({
                submit: () => Promise.resolve('cnf-7'),
              });
              const actor = createActor(form, { clock: new SimulatedClock() }).start();
              const events = recordAll(actor);
              actor.send({ type: 'change', value: 'x' });
              await flush();
              actor.send({ type: 'submit' });
              await flush();
              const snap = actor.getSnapshot();
              // terminal submitted phase, reachable via reported state
              expect(JSON.stringify(snap.value).toLowerCase()).toContain('submit');
              // the submitted notification carries the actual resolved id
              const blob = JSON.stringify(events);
              expect(blob).toContain('cnf-7');
              // a submitted-style notification (not a failure) reached the consumer
              expect(blob.toLowerCase()).not.toContain('fail');
            });
            """
        )
        ok, out = _passed(_run_scenario("Submitted", body))
        assert ok, f"submitted scenario failed:\n{out[-3500:]}"

    def test_terminal_submitted_is_done_status(self):
        """L2: after a resolved submit the form reaches the terminal submitted phase (status done).

        Distinguishes terminal **submitted** from the transient **submitting**:
        a factory that leaves the machine active forever fails here.
        """
        body = textwrap.dedent(
            """\
            it('resolved submit reaches a terminal (done) submitted phase', async () => {
              const form = createNotifyingForm({
                submit: () => Promise.resolve('cnf-9'),
              });
              const actor = createActor(form, { clock: new SimulatedClock() }).start();
              actor.send({ type: 'change', value: 'hello' });
              await flush();
              actor.send({ type: 'submit' });
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              expect(JSON.stringify(snap.value).toLowerCase()).toContain('submit');
            });
            """
        )
        ok, out = _passed(_run_scenario("TerminalDone", body))
        assert ok, f"terminal-submitted scenario failed:\n{out[-3000:]}"

    def test_rejected_submit_emits_submit_failed_then_retry_succeeds(self):
        """L2: submit rejects with "busy" -> back to editing, submit-failed carries "busy"; second submit succeeds.

        The central discriminator from the spec's Expected Functionality:
        a naive factory that terminates on the first submit attempt cannot
        return to editing nor accept a successful retry.  The failure reason
        must travel with the rejection (payload contains 'busy').
        """
        body = textwrap.dedent(
            """\
            it('rejected submit returns to editing, emits submit-failed, retry succeeds', async () => {
              let calls = 0;
              const form = createNotifyingForm({
                submit: () => {
                  calls += 1;
                  return calls === 1
                    ? Promise.reject(new Error('busy'))
                    : Promise.resolve('cnf-ok');
                },
              });
              const actor = createActor(form, { clock: new SimulatedClock() }).start();
              const events = recordAll(actor);
              actor.send({ type: 'change', value: 'x' });
              await flush();
              actor.send({ type: 'submit' });   // -> rejects
              await flush();
              // back to editing (NOT terminal) so the user can retry
              let snap = actor.getSnapshot();
              expect(snap.status).toBe('active');
              expect(JSON.stringify(snap.value).toLowerCase()).toContain('edit');
              // submit-failed notification carries the failure reason text
              const failBlob = JSON.stringify(events).toLowerCase();
              expect(failBlob).toContain('busy');
              // a second submit then succeeds -> terminal submitted with new id
              actor.send({ type: 'submit' });
              await flush();
              snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              expect(JSON.stringify(events)).toContain('cnf-ok');
              expect(calls).toBe(2);
            });
            """
        )
        ok, out = _passed(_run_scenario("FailRetry", body, timeout=600))
        assert ok, f"reject-then-retry scenario failed:\n{out[-4000:]}"

    def test_can_submit_capability_reflects_value_and_phase(self):
        """L2: snapshot.can({type:'submit'}) is true only with a non-empty value while editing.

        "Whether a submit would be acted on" must be answerable from the live
        snapshot's own capability check -- false on empty, true after a change to
        a non-empty value, and false again once terminal.
        """
        body = textwrap.dedent(
            """\
            it('snapshot.can reflects submittability from value and phase', async () => {
              const form = createNotifyingForm({
                submit: () => Promise.resolve('cnf-c'),
              });
              const actor = createActor(form, { clock: new SimulatedClock() }).start();
              // empty -> not submittable
              expect(actor.getSnapshot().can({ type: 'submit' })).toBe(false);
              // non-empty -> submittable
              actor.send({ type: 'change', value: 'abc' });
              await flush();
              expect(actor.getSnapshot().can({ type: 'submit' })).toBe(true);
              // clearing back to empty -> not submittable again
              actor.send({ type: 'change', value: '' });
              await flush();
              expect(actor.getSnapshot().can({ type: 'submit' })).toBe(false);
              // restore and submit to terminal -> no longer submittable
              actor.send({ type: 'change', value: 'abc' });
              await flush();
              actor.send({ type: 'submit' });
              await flush();
              expect(actor.getSnapshot().can({ type: 'submit' })).toBe(false);
            });
            """
        )
        ok, out = _passed(_run_scenario("CanSubmit", body))
        assert ok, f"can-submit capability scenario failed:\n{out[-3500:]}"

    def test_in_flight_submit_is_not_short_circuited(self):
        """L2: a change/submit sent while a submit is in flight must not short-circuit the in-flight submission.

        We hold the submit promise pending, send extra change/submit events, then
        resolve it.  The original in-flight submit must still complete (its id
        emitted) and submit must be invoked exactly once.
        """
        body = textwrap.dedent(
            """\
            it('events during an in-flight submit do not cancel it', async () => {
              let resolveSubmit;
              let calls = 0;
              const form = createNotifyingForm({
                submit: () => { calls += 1; return new Promise((res) => { resolveSubmit = res; }); },
              });
              const actor = createActor(form, { clock: new SimulatedClock() }).start();
              const events = recordAll(actor);
              actor.send({ type: 'change', value: 'x' });
              await flush();
              actor.send({ type: 'submit' });   // enters submitting, submit in flight
              await flush();
              expect(calls).toBe(1);
              // phase is the transient submitting phase (not terminal submitted yet)
              expect(actor.getSnapshot().status).toBe('active');
              // noise while in flight must not short-circuit the pending submit
              actor.send({ type: 'change', value: 'y' });
              actor.send({ type: 'submit' });
              await flush();
              expect(calls).toBe(1);                       // no extra submit call
              expect(actor.getSnapshot().status).toBe('active');  // still in flight
              // now resolve the original submit -> terminal submitted with its id
              resolveSubmit('cnf-inflight');
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              expect(JSON.stringify(events)).toContain('cnf-inflight');
              expect(calls).toBe(1);
            });
            """
        )
        ok, out = _passed(_run_scenario("InFlight", body, timeout=600))
        assert ok, f"in-flight-submit scenario failed:\n{out[-4000:]}"

    def test_notification_id_is_not_a_placeholder(self):
        """L2: the emitted submitted-id is the actual resolved value, not a stashed placeholder.

        Two runs resolving to distinct ids must emit those distinct ids; a
        factory that hard-codes / stashes a placeholder id fails because it would
        emit the same fixed value (or the wrong one) in both runs.
        """
        body = textwrap.dedent(
            """\
            const drive = async (id) => {
              const form = createNotifyingForm({ submit: () => Promise.resolve(id) });
              const actor = createActor(form, { clock: new SimulatedClock() }).start();
              const events = recordAll(actor);
              actor.send({ type: 'change', value: 'x' });
              await flush();
              actor.send({ type: 'submit' });
              await flush();
              return { snap: actor.getSnapshot(), blob: JSON.stringify(events) };
            };

            it('distinct resolved ids produce distinct submitted notifications', async () => {
              const a = await drive('cnf-aaa');
              const b = await drive('cnf-bbb');
              expect(a.snap.status).toBe('done');
              expect(b.snap.status).toBe('done');
              expect(a.blob).toContain('cnf-aaa');
              expect(b.blob).toContain('cnf-bbb');
              // the wrong id must NOT leak across runs (no shared placeholder)
              expect(a.blob).not.toContain('cnf-bbb');
              expect(b.blob).not.toContain('cnf-aaa');
            });
            """
        )
        ok, out = _passed(_run_scenario("DistinctIds", body, timeout=600))
        assert ok, f"distinct-id (no placeholder) scenario failed:\n{out[-3500:]}"

    def test_submit_receives_current_field_value(self):
        """L2: submitting runs submit(values) with the durable current field value.

        The value carried by the change event is durable data the form holds; the
        submit call must receive that value rather than an empty/default.  We
        capture the argument passed to submit and assert it reflects the last
        change.
        """
        body = textwrap.dedent(
            """\
            it('submit() is invoked with the current durable field value', async () => {
              let seen;
              const form = createNotifyingForm({
                submit: (values) => { seen = values; return Promise.resolve('cnf-v'); },
              });
              const actor = createActor(form, { clock: new SimulatedClock() }).start();
              actor.send({ type: 'change', value: 'first' });
              await flush();
              actor.send({ type: 'change', value: 'second' });   // latest wins
              await flush();
              actor.send({ type: 'submit' });
              await flush();
              expect(actor.getSnapshot().status).toBe('done');
              // submit saw the durable latest value (directly or wrapped)
              expect(JSON.stringify(seen)).toContain('second');
              expect(JSON.stringify(seen)).not.toContain('first');
            });
            """
        )
        ok, out = _passed(_run_scenario("SubmitValue", body))
        assert ok, f"submit-receives-value scenario failed:\n{out[-3500:]}"

    def test_agent_spec_passes_native_command(self):
        """L2: the agent's own deterministic spec passes via the exact Acceptance-Criteria command.

        Runs `pnpm vitest run --project xstate packages/core/test/notifyingForm.test.ts`
        from the repo root and requires a clean pass with at least one test.
        """
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        proc = _vitest(AGENT_SPEC, timeout=600)
        ok, out = _passed(proc)
        assert ok, f"agent's notifyingForm.test.ts did not pass:\n{out[-4000:]}"
        # ensure it actually executed at least one test (no empty/skipped pass)
        assert ("passed" in out.lower()) or ("✓" in out), (
            f"agent spec produced no passing tests:\n{out[-2000:]}"
        )
