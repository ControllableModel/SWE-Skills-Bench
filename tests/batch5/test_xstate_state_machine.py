"""Tests for the `xstate-state-machine` skill task (ext5): Subscription Heartbeat Module.

The task asks the agent to add, inside the `xstate` monorepo's core package, a
self-contained "connection" module exporting a factory
``createHeartbeatConnection(config)`` plus a deterministic vitest spec.  The
module wires an external push subscription -- ``subscribe(onMessage, onClosed)``
returning a teardown function -- into machine events that flow back over time.

Deliverables:

  * packages/core/test/fixtures/heartbeatConnection.ts   (the connection module)
  * packages/core/test/heartbeatConnection.test.ts        (the agent's own spec)

Verification strategy (two complementary levels):

  L1  -- the deliverable files exist, are non-empty, export the required factory
          and import ONLY from the public surface ``../../src/index.ts`` (no
          deep reach-ins into internal modules).

  L2  -- DYNAMIC EXECUTION.  Rather than trust the agent's own spec, we inject
          our OWN independent vitest specs next to the fixture, import the
          agent's ``createHeartbeatConnection`` factory, build a *controllable*
          ``subscribe`` (so the harness -- not the module -- decides exactly when
          messages arrive and when the source closes), drive every
          Expected-Functionality scenario through the real XState actor API, and
          assert on the actual reported state (status / matched mode) and on the
          snapshot context (running message count, latest payload).  We also
          instrument the teardown function to assert it fires exactly once on
          leaving the connected mode, and prove that a message delivered after a
          terminal outcome is ignored.

A stub factory that hard-codes a mode string, never increments the count, never
records the latest payload or close reason, forgets to invoke teardown, or keeps
mutating after a terminal outcome cannot pass the independently-authored
scenarios below.  Finally we also run the agent's own spec via the exact
Acceptance-Criteria command.
"""

import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/xstate"
CORE = os.path.join(REPO_DIR, "packages", "core")
TEST_DIR = os.path.join(CORE, "test")
FIXTURE = os.path.join(TEST_DIR, "fixtures", "heartbeatConnection.ts")
AGENT_SPEC = os.path.join(TEST_DIR, "heartbeatConnection.test.ts")

# Where we drop our own independent, harness-authored specs.  Kept under the
# package test dir so the `xstate` vitest project picks them up by glob.
HARNESS_PREFIX = "harnessHeartbeatConnection"


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
    task's Acceptance Criteria.
    """
    rel = os.path.relpath(spec_abspath, REPO_DIR)
    cmd = ["pnpm", "vitest", "run", "--project", "xstate", rel]
    return subprocess.run(
        cmd, cwd=REPO_DIR, capture_output=True, text=True, timeout=timeout
    )


def _write_harness_spec(name, body):
    """Write an independent vitest spec into the core test dir; return its path.

    `name` should be unique per test method to avoid cross-test interference.
    """
    path = os.path.join(TEST_DIR, f"{HARNESS_PREFIX}{name}.test.ts")
    with open(path, "w") as fh:
        fh.write(body)
    return path


# Common preamble for every harness spec.  vitest globals are enabled
# (config has globals:true), so `it`/`expect` are in scope.  We import the
# real actor API and the agent's factory, and provide a microtask flush helper
# plus a controllable subscription builder that lets the harness drive message
# delivery and closure deterministically (no timers, no randomness).
PREAMBLE = textwrap.dedent(
    """\
    import { createActor } from '../src/index.ts';
    import { createHeartbeatConnection } from './fixtures/heartbeatConnection.ts';

    // microtask flush helper: lets queued promise continuations / event
    // ingestion run to completion deterministically.
    const flush = async () => {
      for (let i = 0; i < 12; i++) {
        await Promise.resolve();
      }
    };

    // Build a controllable subscription. The returned `ctl` exposes:
    //   emit(payload)  -> deliver one message (onMessage)
    //   close(reason)  -> signal source closed/failed (onClosed)
    //   teardownCalls  -> how many times the module invoked teardown
    //   opened         -> how many times the module opened the subscription
    function makeSub() {
      const ctl = {
        teardownCalls: 0,
        opened: 0,
        _onMessage: null,
        _onClosed: null,
        emit(payload) { if (this._onMessage) this._onMessage(payload); },
        close(reason) { if (this._onClosed) this._onClosed(reason); },
        subscribe(onMessage, onClosed) {
          this.opened += 1;
          this._onMessage = onMessage;
          this._onClosed = onClosed;
          return () => { this.teardownCalls += 1; };
        }
      };
      // bind so it can be passed directly as config.subscribe
      ctl.subscribe = ctl.subscribe.bind(ctl);
      return ctl;
    }

    // Resolve the current "mode" purely from the reported state, tolerating
    // either a string state value or a snapshot exposing matches().
    function mode(snap) {
      const v = snap.value;
      if (typeof v === 'string') return v;
      if (v && typeof v === 'object') {
        const ks = Object.keys(v);
        if (ks.length === 1) return ks[0];
      }
      return JSON.stringify(v);
    }
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
        """L1: the connection module fixture file was created at the required path."""
        assert os.path.isfile(FIXTURE), f"missing connection module: {FIXTURE}"
        assert os.path.getsize(FIXTURE) > 0, "heartbeatConnection.ts is empty"

    def test_agent_spec_file_exists(self):
        """L1: the agent's own deterministic spec file was created."""
        assert os.path.isfile(AGENT_SPEC), f"missing spec: {AGENT_SPEC}"
        assert os.path.getsize(AGENT_SPEC) > 0, "heartbeatConnection.test.ts is empty"

    def test_fixture_exports_factory_and_uses_public_surface(self):
        """L1: module exports `createHeartbeatConnection` and imports only from src/index.ts.

        We do not keyword-match behavior; we only enforce the import discipline
        (Acceptance Criterion: import solely from ../../src/index.ts) and that
        the named export is present so our L2 specs can import it.
        """
        with open(FIXTURE) as fh:
            src = fh.read()
        assert "createHeartbeatConnection" in src, "factory export not found"
        # No deep reach-ins past the public index barrel.
        forbidden = [
            "../../src/StateMachine",
            "../../src/State.ts",
            "../../src/createActor",
            "from '../../src/actors",
            'from "../../src/actors',
        ]
        for f in forbidden:
            assert f not in src, f"module reaches into internal file: {f}"

    # ------------------------------------------------------------------ #
    # L2: independent dynamic scenarios driving the agent's factory
    # ------------------------------------------------------------------ #
    def test_starts_connected_and_opens_subscription(self):
        """L2: start -> connected mode, count 0, and the subscription is opened once."""
        body = textwrap.dedent(
            """\
            it('starts connected with zero count and opens the source', async () => {
              const sub = makeSub();
              const conn = createHeartbeatConnection({ subscribe: sub.subscribe });
              const actor = createActor(conn).start();
              await flush();
              const snap = actor.getSnapshot();
              expect(mode(snap)).toBe('connected');
              expect(snap.context.count).toBe(0);
              expect(sub.opened).toBe(1);          // subscription opened immediately
              expect(sub.teardownCalls).toBe(0);   // still connected
            });
            """
        )
        ok, out = _passed(_run_scenario("Start", body))
        assert ok, f"start-connected scenario failed:\n{out[-3000:]}"

    def test_messages_update_count_and_latest_payload(self):
        """L2: deliver "a" then "b" -> still connected, count == 2, latest payload == "b".

        A stub that ignores delivered messages (count stays 0) or never records
        the latest payload fails here.
        """
        body = textwrap.dedent(
            """\
            it('ingests messages over time updating count and latest payload', async () => {
              const sub = makeSub();
              const conn = createHeartbeatConnection({ subscribe: sub.subscribe });
              const actor = createActor(conn).start();
              await flush();
              sub.emit('a');
              await flush();
              expect(mode(actor.getSnapshot())).toBe('connected');
              expect(actor.getSnapshot().context.count).toBe(1);
              expect(actor.getSnapshot().context.latest).toBe('a');
              sub.emit('b');
              await flush();
              const snap = actor.getSnapshot();
              expect(mode(snap)).toBe('connected');
              expect(snap.context.count).toBe(2);
              expect(snap.context.latest).toBe('b');   // most-recent payload
            });
            """
        )
        ok, out = _passed(_run_scenario("Messages", body))
        assert ok, f"message-ingestion scenario failed:\n{out[-3000:]}"

    def test_close_moves_to_terminal_closed_with_reason(self):
        """L2: deliver "a" then close("server-gone") -> terminal closed, reason recorded, count==1.

        Asserts the reported state is a terminal 'closed' mode (status done),
        the close reason text travels with the callback into context, and the
        single pre-close message was counted.
        """
        body = textwrap.dedent(
            """\
            it('source close yields terminal closed carrying the reason', async () => {
              const sub = makeSub();
              const conn = createHeartbeatConnection({ subscribe: sub.subscribe });
              const actor = createActor(conn).start();
              await flush();
              sub.emit('a');
              await flush();
              sub.close('server-gone');
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              expect(mode(snap)).toBe('closed');
              expect(snap.context.count).toBe(1);
              const blob = JSON.stringify({ c: snap.context, o: snap.output });
              expect(blob).toContain('server-gone');   // reason recorded
            });
            """
        )
        ok, out = _passed(_run_scenario("Closed", body))
        assert ok, f"close-terminal scenario failed:\n{out[-3000:]}"

    def test_disconnect_intent_moves_to_terminal_disconnected(self):
        """L2: deliver one message, consumer disconnects -> terminal disconnected.

        Drives the consumer "disconnect" intent and asserts the machine reaches
        a terminal 'disconnected' mode (status done), distinct from 'closed'.
        """
        body = textwrap.dedent(
            """\
            it('consumer disconnect yields terminal disconnected', async () => {
              const sub = makeSub();
              const conn = createHeartbeatConnection({ subscribe: sub.subscribe });
              const actor = createActor(conn).start();
              await flush();
              sub.emit('a');
              await flush();
              actor.send({ type: 'disconnect' });
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              expect(mode(snap)).toBe('disconnected');
              expect(snap.context.count).toBe(1);
            });
            """
        )
        ok, out = _passed(_run_scenario("Disconnect", body))
        assert ok, f"disconnect-terminal scenario failed:\n{out[-3000:]}"

    def test_teardown_invoked_exactly_once_on_close(self):
        """L2: teardown fires exactly once when leaving connected via source close.

        The discriminating case for cleanup discipline: a module that forgets to
        invoke teardown (0 calls) or invokes it repeatedly (>1) fails here.
        """
        body = textwrap.dedent(
            """\
            it('teardown invoked exactly once on close', async () => {
              const sub = makeSub();
              const conn = createHeartbeatConnection({ subscribe: sub.subscribe });
              const actor = createActor(conn).start();
              await flush();
              sub.emit('x');
              await flush();
              expect(sub.teardownCalls).toBe(0);   // still connected
              sub.close('bye');
              await flush();
              expect(mode(actor.getSnapshot())).toBe('closed');
              expect(sub.teardownCalls).toBe(1);   // exactly once
            });
            """
        )
        ok, out = _passed(_run_scenario("TeardownClose", body))
        assert ok, f"teardown-on-close scenario failed:\n{out[-3000:]}"

    def test_teardown_invoked_exactly_once_on_disconnect(self):
        """L2: teardown fires exactly once when leaving connected via explicit disconnect."""
        body = textwrap.dedent(
            """\
            it('teardown invoked exactly once on disconnect', async () => {
              const sub = makeSub();
              const conn = createHeartbeatConnection({ subscribe: sub.subscribe });
              const actor = createActor(conn).start();
              await flush();
              expect(sub.teardownCalls).toBe(0);
              actor.send({ type: 'disconnect' });
              await flush();
              expect(mode(actor.getSnapshot())).toBe('disconnected');
              expect(sub.teardownCalls).toBe(1);   // exactly once, even with no messages
            });
            """
        )
        ok, out = _passed(_run_scenario("TeardownDisc", body))
        assert ok, f"teardown-on-disconnect scenario failed:\n{out[-3000:]}"

    def test_message_after_close_is_ignored(self):
        """L2: a message delivered after a terminal close must not change data or state.

        A naive module that keeps mutating context after termination fails here:
        count and the recorded reason/state must be frozen post-terminal.
        """
        body = textwrap.dedent(
            """\
            it('message delivered after close is ignored', async () => {
              const sub = makeSub();
              const conn = createHeartbeatConnection({ subscribe: sub.subscribe });
              const actor = createActor(conn).start();
              await flush();
              sub.emit('a');
              await flush();
              sub.close('gone');
              await flush();
              const before = actor.getSnapshot();
              expect(mode(before)).toBe('closed');
              expect(before.context.count).toBe(1);
              // Source delivers a late message (teardown not yet observed).
              sub.emit('late');
              await flush();
              const after = actor.getSnapshot();
              expect(mode(after)).toBe('closed');         // state unchanged
              expect(after.context.count).toBe(1);        // count unchanged
              expect(after.context.latest).toBe('a');     // latest payload unchanged
            });
            """
        )
        ok, out = _passed(_run_scenario("LateAfterClose", body))
        assert ok, f"late-message-after-close scenario failed:\n{out[-3000:]}"

    def test_message_after_disconnect_is_ignored(self):
        """L2: a message delivered after disconnect leaves count and state unchanged.

        Matches the final Expected-Functionality scenario: start, deliver one
        message, disconnect, then a further delivered message must not change
        count or state.
        """
        body = textwrap.dedent(
            """\
            it('message delivered after disconnect is ignored', async () => {
              const sub = makeSub();
              const conn = createHeartbeatConnection({ subscribe: sub.subscribe });
              const actor = createActor(conn).start();
              await flush();
              sub.emit('first');
              await flush();
              actor.send({ type: 'disconnect' });
              await flush();
              const before = actor.getSnapshot();
              expect(mode(before)).toBe('disconnected');
              expect(before.context.count).toBe(1);
              sub.emit('second');   // post-terminal delivery
              await flush();
              const after = actor.getSnapshot();
              expect(mode(after)).toBe('disconnected');   // unchanged
              expect(after.context.count).toBe(1);        // unchanged
              expect(after.context.latest).toBe('first'); // unchanged
            });
            """
        )
        ok, out = _passed(_run_scenario("LateAfterDisc", body))
        assert ok, f"late-message-after-disconnect scenario failed:\n{out[-3000:]}"

    def test_close_reason_travels_per_event_not_placeholder(self):
        """L2: the recorded close reason matches the exact reason passed to onClosed.

        Two independent connections close with distinct reasons; each must record
        its own reason.  A module that stashes a fixed placeholder reason (rather
        than carrying the reason on the callback) fails this discriminator.
        """
        body = textwrap.dedent(
            """\
            function closeWith(reason) {
              const sub = makeSub();
              const conn = createHeartbeatConnection({ subscribe: sub.subscribe });
              const actor = createActor(conn).start();
              return { sub, actor };
            }

            it('distinct close reasons are each recorded faithfully', async () => {
              const a = closeWith();
              await flush();
              a.sub.close('reason-alpha');
              await flush();
              const sa = a.actor.getSnapshot();
              expect(mode(sa)).toBe('closed');
              const ba = JSON.stringify({ c: sa.context, o: sa.output });
              expect(ba).toContain('reason-alpha');
              expect(ba).not.toContain('reason-beta');

              const b = closeWith();
              await flush();
              b.sub.close('reason-beta');
              await flush();
              const sb = b.actor.getSnapshot();
              expect(mode(sb)).toBe('closed');
              const bb = JSON.stringify({ c: sb.context, o: sb.output });
              expect(bb).toContain('reason-beta');
              expect(bb).not.toContain('reason-alpha');
            });
            """
        )
        ok, out = _passed(_run_scenario("ReasonPerEvent", body))
        assert ok, f"close-reason-per-event scenario failed:\n{out[-3000:]}"

    def test_terminal_outcomes_are_distinct_and_final(self):
        """L2: closed and disconnected are distinct terminal modes, and both are final.

        Confirms (a) the two terminal outcomes report different modes, (b) once a
        terminal outcome is reached an additional disconnect intent does not move
        the machine out of it, and (c) the subscription is only opened once.
        """
        body = textwrap.dedent(
            """\
            it('terminal outcomes are distinct and final', async () => {
              const sub = makeSub();
              const conn = createHeartbeatConnection({ subscribe: sub.subscribe });
              const actor = createActor(conn).start();
              await flush();
              expect(sub.opened).toBe(1);
              sub.close('done-now');
              await flush();
              const snap = actor.getSnapshot();
              expect(snap.status).toBe('done');
              expect(mode(snap)).toBe('closed');
              // A late disconnect intent on a terminal machine is a no-op.
              actor.send({ type: 'disconnect' });
              await flush();
              expect(mode(actor.getSnapshot())).toBe('closed');
              // teardown was invoked exactly once across the whole lifecycle.
              expect(sub.teardownCalls).toBe(1);
              expect(sub.opened).toBe(1);   // never re-opened
            });
            """
        )
        ok, out = _passed(_run_scenario("DistinctFinal", body))
        assert ok, f"distinct-terminal scenario failed:\n{out[-3000:]}"

    def test_agent_spec_passes_native_command(self):
        """L2: the agent's own deterministic spec passes via the exact Acceptance command.

        Runs `pnpm vitest run --project xstate packages/core/test/heartbeatConnection.test.ts`
        from the repo root and requires a clean pass with at least one test.
        """
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        proc = _vitest(AGENT_SPEC, timeout=600)
        ok, out = _passed(proc)
        assert ok, f"agent's heartbeatConnection.test.ts did not pass:\n{out[-4000:]}"
        assert ("passed" in out.lower()) or ("✓" in out), (
            f"agent spec produced no passing tests:\n{out[-2000:]}"
        )
