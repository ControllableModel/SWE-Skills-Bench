"""Tests for the `xstate-state-machine` skill task (ext7): Persistable Counter-Session Module.

The task asks the agent to add, inside the `xstate` monorepo's core package, a
self-contained "scored session" module whose full running state (a finite phase
plus durable data) can be serialized and later restored so a session resumes
exactly where it left off.  Deliverables:

  * packages/core/test/fixtures/scoredSession.ts   (the session module)
  * packages/core/test/scoredSession.test.ts        (the agent's own spec)

Module surface (per the requirement doc):
  * createScoredSession()        -- returns the session definition plus a way to
                                    start a fresh runnable session via the actor API.
  * a helper that produces a runnable session REHYDRATED from a previously saved
    snapshot so that both the finite phase and the durable score/rounds are
    restored together.

The session has three finite phases -- idle, active, ended -- plus durable data
``score`` (number) and ``rounds`` (count).  Behavior:
  * fresh session starts idle.
  * "begin" : idle -> active, resets score and rounds to 0.
  * "score" (carrying points) while active : adds points to score, +1 round.
    A "score" while idle or ended is IGNORED.
  * "end" : active -> ended.  From ended, only "begin" starts a new session.
  * Saving captures the WHOLE running state; restoring reconstructs phase plus
    durable data together (not a guessed phase string + partial blob).

Verification strategy:

  L1  -- the deliverable files exist and are minimally well-formed (import only
          from the public surface ``../../src/index.ts``).

  L2  -- DYNAMIC EXECUTION.  Rather than trusting the spec the agent itself
          wrote, we inject our OWN independent vitest specs next to the fixture,
          import the agent's ``createScoredSession`` factory + its rehydrate
          helper, drive them through every Expected-Functionality scenario with
          the real XState actor API, and assert on the actual reported phase
          (snapshot.value via .matches()) and durable context (score / rounds),
          including a genuine save-and-restore round trip via the package's own
          ``getPersistedSnapshot()`` + ``{ snapshot }`` restore mechanism.

A stub that hard-codes a phase string, ignores the points carried by a "score"
event, fails to ignore out-of-phase "score" events, or "restores" by pasting a
partial data blob (losing the finite phase) cannot pass the independently
authored scenarios below.  We run them with the package's native command
``pnpm vitest run --project xstate <file>``.
"""

import os
import re
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/xstate"
CORE = os.path.join(REPO_DIR, "packages", "core")
TEST_DIR = os.path.join(CORE, "test")
FIXTURE = os.path.join(TEST_DIR, "fixtures", "scoredSession.ts")
AGENT_SPEC = os.path.join(TEST_DIR, "scoredSession.test.ts")

# Where we drop our own independent, harness-authored specs.  Kept under the
# package test dir so the `xstate` vitest project picks them up by glob.
HARNESS_PREFIX = "harnessScoredSession"


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


# Common preamble for every harness spec: vitest globals are enabled (the core
# config sets globals:true), the real actor API + snapshot persistence helpers,
# and the agent's factory.  We import from the SAME public surface the module is
# required to use, so an internal-reach-in module would not even resolve here the
# same way.  We deliberately do NOT import the agent's own helper by a fixed
# name beyond `createScoredSession`; the rehydrate path is exercised through the
# package's `getPersistedSnapshot()` + `{ snapshot }` restore so the test does
# not depend on the helper's exact name -- but several scenarios also try the
# documented rehydrate helper if exported.
PREAMBLE = textwrap.dedent(
    """\
    import { createActor } from '../src/index.ts';
    import * as mod from './fixtures/scoredSession.ts';

    // Build a fresh running session from the agent's factory, started.
    function startFresh() {
      const def = mod.createScoredSession();
      // The factory may return the machine directly, or an object exposing it
      // and/or a start helper.  Support the common shapes.
      const machine =
        def && def.machine ? def.machine :
        (def && def.session) ? def.session :
        def;
      if (def && typeof def.start === 'function') {
        const a = def.start();
        return a.start ? a.start() : a;
      }
      return createActor(machine).start();
    }

    // Resolve the underlying machine definition (for direct restore).
    function machineOf() {
      const def = mod.createScoredSession();
      return def && def.machine ? def.machine :
             (def && def.session) ? def.session :
             def;
    }

    // Restore a running session from a previously persisted snapshot.  Prefer
    // the agent's documented rehydrate helper if it exported one; otherwise use
    // the package's own snapshot-restore mechanism on the same machine.
    function restoreFrom(persisted) {
      const helperName = Object.keys(mod).find(
        (k) => k !== 'createScoredSession' && typeof mod[k] === 'function'
      );
      if (helperName) {
        const a = mod[helperName](persisted);
        if (a && typeof a.getSnapshot === 'function') {
          return a.start ? a.start() : a;
        }
      }
      return createActor(machineOf(), { snapshot: persisted }).start();
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
        """L1: the session module fixture file was created at the required path."""
        assert os.path.isfile(FIXTURE), f"missing session module: {FIXTURE}"
        assert os.path.getsize(FIXTURE) > 0, "scoredSession.ts is empty"

    def test_agent_spec_file_exists(self):
        """L1: the agent's own deterministic spec file was created."""
        assert os.path.isfile(AGENT_SPEC), f"missing spec: {AGENT_SPEC}"
        assert os.path.getsize(AGENT_SPEC) > 0, "scoredSession.test.ts is empty"

    def test_fixture_exports_factory_and_uses_public_surface(self):
        """L1: module exports `createScoredSession` and imports only from src/index.ts.

        We do not keyword-match behavior; we only check the import discipline
        (Acceptance Criterion: import solely from ../../src/index.ts) and that
        the named export is present so our L2 specs can import it.
        """
        with open(FIXTURE) as fh:
            src = fh.read()
        assert "createScoredSession" in src, "createScoredSession export not found"
        # No deep reach-ins past the public index barrel.
        forbidden = [
            "../../src/StateMachine",
            "../../src/State.ts",
            "../../src/createActor",
            "from '../../src/actors",
            "from '../../src/createMachine",
        ]
        for f in forbidden:
            assert f not in src, f"module reaches into internal file: {f}"

    # ------------------------------------------------------------------ #
    # L2: independent dynamic scenarios driving the agent's factory
    # ------------------------------------------------------------------ #
    def test_fresh_session_starts_idle_zeroed(self):
        """L2: a fresh session is in phase 'idle' with score 0 and rounds 0.

        Phase is read from the reported state via snapshot.matches('idle')
        (NOT a data flag); durable data from snapshot.context.
        """
        body = textwrap.dedent(
            """\
            it('fresh session is idle with zeroed durable data', () => {
              const actor = startFresh();
              const snap = actor.getSnapshot();
              expect(snap.matches('idle')).toBe(true);
              expect(snap.matches('active')).toBe(false);
              expect(snap.context.score).toBe(0);
              expect(snap.context.rounds).toBe(0);
            });
            """
        )
        ok, out = _passed(_run_scenario("FreshIdle", body))
        assert ok, f"fresh-idle scenario failed:\n{out[-3000:]}"

    def test_begin_then_two_scores_accumulate(self):
        """L2: begin -> active; score +3 then +5 -> score 8, rounds 2.

        The points carried by each 'score' event must be added; a factory that
        ignores the event payload (hardcodes an increment) fails here.
        """
        body = textwrap.dedent(
            """\
            it('begin then two scoring events accumulate carried points', () => {
              const actor = startFresh();
              actor.send({ type: 'begin' });
              expect(actor.getSnapshot().matches('active')).toBe(true);
              actor.send({ type: 'score', points: 3 });
              actor.send({ type: 'score', points: 5 });
              const snap = actor.getSnapshot();
              expect(snap.matches('active')).toBe(true);
              expect(snap.context.score).toBe(8);
              expect(snap.context.rounds).toBe(2);
            });
            """
        )
        ok, out = _passed(_run_scenario("BeginScore", body))
        assert ok, f"begin+score scenario failed:\n{out[-3000:]}"

    def test_score_while_idle_is_ignored(self):
        """L2: a 'score' event sent while idle is ignored (still idle, score 0, rounds 0).

        Discriminator against a factory that always applies score regardless of
        phase.
        """
        body = textwrap.dedent(
            """\
            it('score while idle is ignored', () => {
              const actor = startFresh();
              expect(actor.getSnapshot().matches('idle')).toBe(true);
              actor.send({ type: 'score', points: 7 });
              const snap = actor.getSnapshot();
              expect(snap.matches('idle')).toBe(true);
              expect(snap.context.score).toBe(0);
              expect(snap.context.rounds).toBe(0);
            });
            """
        )
        ok, out = _passed(_run_scenario("IdleIgnore", body))
        assert ok, f"score-while-idle scenario failed:\n{out[-3000:]}"

    def test_begin_resets_durable_data(self):
        """L2: 'begin' from ended resets score and rounds to zero.

        After accumulating score, end the session, then begin again: durable
        data must be reset to 0 on the fresh active session.
        """
        body = textwrap.dedent(
            """\
            it('begin resets durable data to zero', () => {
              const actor = startFresh();
              actor.send({ type: 'begin' });
              actor.send({ type: 'score', points: 4 });
              actor.send({ type: 'score', points: 6 });
              expect(actor.getSnapshot().context.score).toBe(10);
              actor.send({ type: 'end' });
              expect(actor.getSnapshot().matches('ended')).toBe(true);
              actor.send({ type: 'begin' });
              const snap = actor.getSnapshot();
              expect(snap.matches('active')).toBe(true);
              expect(snap.context.score).toBe(0);
              expect(snap.context.rounds).toBe(0);
            });
            """
        )
        ok, out = _passed(_run_scenario("BeginReset", body))
        assert ok, f"begin-reset scenario failed:\n{out[-3000:]}"

    def test_end_transition_and_ended_ignores_score(self):
        """L2: active -> ended via 'end'; while ended a 'score' is ignored.

        From ended only 'begin' starts a new session; a 'score' while ended must
        not change durable data.
        """
        body = textwrap.dedent(
            """\
            it('end moves to ended and ended ignores score', () => {
              const actor = startFresh();
              actor.send({ type: 'begin' });
              actor.send({ type: 'score', points: 9 });
              actor.send({ type: 'end' });
              const ended = actor.getSnapshot();
              expect(ended.matches('ended')).toBe(true);
              expect(ended.context.score).toBe(9);
              expect(ended.context.rounds).toBe(1);
              // score while ended -> ignored.
              actor.send({ type: 'score', points: 100 });
              const after = actor.getSnapshot();
              expect(after.matches('ended')).toBe(true);
              expect(after.context.score).toBe(9);
              expect(after.context.rounds).toBe(1);
            });
            """
        )
        ok, out = _passed(_run_scenario("EndIgnore", body))
        assert ok, f"end/ended-ignore scenario failed:\n{out[-3000:]}"

    def test_save_restore_active_continues_accumulating(self):
        """L2 (core): save mid-active, restore, and keep accumulating onto restored data.

        begin, score +3, score +5 -> save snapshot.  Build a NEW session
        restored from that snapshot: it must resume 'active' with score 8 /
        rounds 2 intact, and a further score +2 -> score 10, rounds 3.

        This is the central discriminator: restoring must reconstruct BOTH the
        finite phase and the durable data together.  A "restore" that only
        pastes a data blob (losing 'active') or that drops accumulated score
        fails here.
        """
        body = textwrap.dedent(
            """\
            it('restored mid-active session continues accumulating', () => {
              const a = startFresh();
              a.send({ type: 'begin' });
              a.send({ type: 'score', points: 3 });
              a.send({ type: 'score', points: 5 });
              const pre = a.getSnapshot();
              expect(pre.matches('active')).toBe(true);
              expect(pre.context.score).toBe(8);
              expect(pre.context.rounds).toBe(2);

              const persisted = a.getPersistedSnapshot();

              const b = restoreFrom(persisted);
              const r = b.getSnapshot();
              // BOTH phase and durable data restored together.
              expect(r.matches('active')).toBe(true);
              expect(r.context.score).toBe(8);
              expect(r.context.rounds).toBe(2);

              // continues accepting score events, accumulating onto restored data.
              b.send({ type: 'score', points: 2 });
              const after = b.getSnapshot();
              expect(after.matches('active')).toBe(true);
              expect(after.context.score).toBe(10);
              expect(after.context.rounds).toBe(3);
            });
            """
        )
        ok, out = _passed(_run_scenario("RestoreActive", body, timeout=600))
        assert ok, f"save/restore-active scenario failed:\n{out[-4000:]}"

    def test_save_restore_ended_phase_preserved(self):
        """L2: a session saved in 'ended' restores back to 'ended' (score still ignored).

        begin, end, save; restore -> comes back 'ended'; a 'score' is ignored;
        a 'begin' -> 'active' with score reset to 0.  Proves the finite phase
        (not just data) survives the round trip.
        """
        body = textwrap.dedent(
            """\
            it('restored ended session stays ended until begin', () => {
              const a = startFresh();
              a.send({ type: 'begin' });
              a.send({ type: 'score', points: 5 });
              a.send({ type: 'end' });
              expect(a.getSnapshot().matches('ended')).toBe(true);
              const persisted = a.getPersistedSnapshot();

              const b = restoreFrom(persisted);
              const r = b.getSnapshot();
              expect(r.matches('ended')).toBe(true);
              // score ignored while ended.
              b.send({ type: 'score', points: 50 });
              const ignored = b.getSnapshot();
              expect(ignored.matches('ended')).toBe(true);
              expect(ignored.context.score).toBe(5);
              // begin starts a fresh active session with reset data.
              b.send({ type: 'begin' });
              const fresh = b.getSnapshot();
              expect(fresh.matches('active')).toBe(true);
              expect(fresh.context.score).toBe(0);
              expect(fresh.context.rounds).toBe(0);
            });
            """
        )
        ok, out = _passed(_run_scenario("RestoreEnded", body, timeout=600))
        assert ok, f"save/restore-ended scenario failed:\n{out[-4000:]}"

    def test_no_pending_points_stash(self):
        """L2: points travel with the 'score' event; no pending-points stash applied later.

        We send two score events with DIFFERENT payloads and assert the total is
        exactly their sum.  A module that stashes pending points and re-applies a
        stale value on a later transition would diverge from the precise total.
        """
        body = textwrap.dedent(
            """\
            it('points come solely from each score event, not a stash', () => {
              const actor = startFresh();
              actor.send({ type: 'begin' });
              actor.send({ type: 'score', points: 11 });
              actor.send({ type: 'score', points: 0 });
              actor.send({ type: 'score', points: 4 });
              const snap = actor.getSnapshot();
              // exact sum 11 + 0 + 4 = 15, rounds 3 (every score event counts).
              expect(snap.context.score).toBe(15);
              expect(snap.context.rounds).toBe(3);
              // ending must not retroactively re-apply any stashed points.
              actor.send({ type: 'end' });
              expect(actor.getSnapshot().context.score).toBe(15);
              expect(actor.getSnapshot().context.rounds).toBe(3);
            });
            """
        )
        ok, out = _passed(_run_scenario("NoStash", body))
        assert ok, f"no-pending-points scenario failed:\n{out[-3000:]}"

    def test_phase_derivable_from_state_not_data(self):
        """L2: the phase is derivable from the reported state, not a data flag.

        We assert exactly one of idle/active/ended matches at each step, proving
        the phase lives in the finite state value rather than being encoded only
        as context data.
        """
        body = textwrap.dedent(
            """\
            it('exactly one finite phase is reported at each step', () => {
              const phases = ['idle', 'active', 'ended'];
              const count = (snap) => phases.filter((p) => snap.matches(p)).length;
              const actor = startFresh();
              expect(count(actor.getSnapshot())).toBe(1);
              expect(actor.getSnapshot().matches('idle')).toBe(true);
              actor.send({ type: 'begin' });
              expect(count(actor.getSnapshot())).toBe(1);
              expect(actor.getSnapshot().matches('active')).toBe(true);
              actor.send({ type: 'end' });
              expect(count(actor.getSnapshot())).toBe(1);
              expect(actor.getSnapshot().matches('ended')).toBe(true);
            });
            """
        )
        ok, out = _passed(_run_scenario("PhaseDerivable", body))
        assert ok, f"phase-derivable scenario failed:\n{out[-3000:]}"

    def test_agent_spec_passes_native_command(self):
        """L2: the agent's own deterministic spec passes via the exact Acceptance-Criteria command.

        Runs `pnpm vitest run --project xstate packages/core/test/scoredSession.test.ts`
        from the repo root and requires a clean pass with at least one test.
        """
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        proc = _vitest(AGENT_SPEC, timeout=600)
        ok, out = _passed(proc)
        assert ok, f"agent's scoredSession.test.ts did not pass:\n{out[-4000:]}"
        # ensure it actually executed at least one test (no empty/skipped pass)
        assert ("passed" in out.lower()) or ("✓" in out), (
            f"agent spec produced no passing tests:\n{out[-2000:]}"
        )
