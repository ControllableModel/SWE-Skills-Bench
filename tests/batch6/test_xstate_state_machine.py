"""Tests for the `xstate-state-machine` skill task (ext6): Traffic-Light Module
with Pedestrian Crossing and History.

The task asks the agent to add, inside the `xstate` monorepo's core package, a
self-contained traffic-light factory ``createTrafficLight(config)`` plus a
deterministic vitest spec.  The light cycles green -> yellow -> red -> green on
configured delays (``greenMs`` / ``yellowMs`` / ``redMs``), a "pedestrian
request" event halts the cycle in a distinct ``walk`` mode (no automatic
advance), and a "pedestrian clear" event RESUMES the *interrupted* phase from
the start of that phase's timer.  A duplicate pedestrian request while already
in ``walk`` must be ignored.  Deliverables:

  * packages/core/test/fixtures/trafficLight.ts  (the traffic-light module)
  * packages/core/test/trafficLight.test.ts      (the agent's own spec)

These tests verify the work in two complementary ways:

  L1  -- the deliverable files exist and are minimally well-formed (the module
          imports only from the public surface ``../../src/index.ts`` and
          exports ``createTrafficLight``).

  L2  -- DYNAMIC EXECUTION.  Rather than trusting the spec the agent itself
          wrote, we inject our OWN independent vitest specs next to the fixture,
          import the agent's ``createTrafficLight`` factory, drive it through
          every Expected-Functionality scenario with the real XState actor API
          plus a ``SimulatedClock`` (simulated time), and assert on the actual
          reported state (``snapshot.value``).  We run each spec with the
          package's native command
          ``pnpm vitest run --project xstate <file>``.

Discriminators a stub/naive implementation cannot pass:
  * Phases must advance ONLY on the configured delay (not immediately, not on
    wall-clock); partial time must not advance, full time must.
  * ``walk`` must freeze the cycle even after huge simulated time.
  * Resume must return to the EXACT interrupted phase (green/yellow/red), with
    its timer restarted from zero -- recovered from the cycle's remembered
    position, verified by partial-then-full advances after clear.
  * A second pedestrian request while in ``walk`` is a no-op.
A factory that hardcodes a phase, ignores durations, or reconstructs the resume
phase incorrectly fails the independently-authored scenarios below.
"""

import os
import re
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/xstate"
CORE = os.path.join(REPO_DIR, "packages", "core")
TEST_DIR = os.path.join(CORE, "test")
FIXTURE = os.path.join(TEST_DIR, "fixtures", "trafficLight.ts")
AGENT_SPEC = os.path.join(TEST_DIR, "trafficLight.test.ts")

# Where we drop our own independent, harness-authored specs.  Kept under the
# package test dir so the `xstate` vitest project picks them up by glob.
HARNESS_PREFIX = "harnessTrafficLight"


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


# Common preamble for every harness spec.  vitest globals are enabled (the core
# vitest config sets globals:true), so `it`/`expect` are ambient.  We import the
# real actor API + SimulatedClock from the public surface and the agent's
# factory, plus small helpers:
#   * flush()  -- drains queued microtasks (delayed transitions on a
#                 SimulatedClock fire synchronously on increment, but flushing
#                 keeps things robust if the module uses promise-based actions).
#   * phaseOf(snap) -- reduces snapshot.value (string OR nested object) to a
#                 single lowercased token string so we can search for the
#                 active leaf phase WITHOUT assuming a particular value shape.
PREAMBLE = textwrap.dedent(
    """\
    import { createActor, SimulatedClock } from '../src/index.ts';
    import { createTrafficLight } from './fixtures/trafficLight.ts';

    const flush = async () => {
      for (let i = 0; i < 8; i++) {
        await Promise.resolve();
      }
    };

    // Flatten any state value (string | object) into one lowercased blob so we
    // can assert on the active leaf phase regardless of nesting / naming shape.
    const valueBlob = (snap) =>
      JSON.stringify(snap.value).toLowerCase();

    // Build a started actor for a config with a fresh SimulatedClock.
    const startLight = (cfg) => {
      const machine = createTrafficLight(cfg);
      const clock = new SimulatedClock();
      const actor = createActor(machine, { clock }).start();
      return { actor, clock };
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
        """L1: the traffic-light module fixture file was created at the required path."""
        assert os.path.isfile(FIXTURE), f"missing traffic-light module: {FIXTURE}"
        assert os.path.getsize(FIXTURE) > 0, "trafficLight.ts is empty"

    def test_agent_spec_file_exists(self):
        """L1: the agent's own deterministic spec file was created."""
        assert os.path.isfile(AGENT_SPEC), f"missing spec: {AGENT_SPEC}"
        assert os.path.getsize(AGENT_SPEC) > 0, "trafficLight.test.ts is empty"

    def test_fixture_exports_factory_and_uses_public_surface(self):
        """L1: module exports `createTrafficLight` and imports only from src/index.ts.

        We do not keyword-match behavior; we only check import discipline
        (Acceptance Criterion: import solely from ../../src/index.ts) and that
        the named export is present so our L2 specs can import it.
        """
        with open(FIXTURE) as fh:
            src = fh.read()
        assert "createTrafficLight" in src, "factory export `createTrafficLight` not found"
        # No deep reach-ins past the public index barrel.
        forbidden = [
            "../../src/StateMachine",
            "../../src/State.ts",
            "../../src/createActor",
            "from '../../src/actors",
            "from '../../src/stateUtils",
        ]
        for f in forbidden:
            assert f not in src, f"module reaches into internal file: {f}"
        # All relative src imports must go through the index barrel.
        for m in re.finditer(r"from\s+['\"](\.\.\/\.\.\/src\/[^'\"]+)['\"]", src):
            target = m.group(1)
            assert target in (
                "../../src/index.ts",
                "../../src/index",
            ), f"non-public src import: {target}"

    # ------------------------------------------------------------------ #
    # L2: independent dynamic scenarios driving the agent's factory
    # ------------------------------------------------------------------ #
    def test_starts_green_and_advances_full_cycle(self):
        """L2: start->green; +greenMs->yellow; +yellowMs->red; +redMs->green.

        Drives a full cycle purely on the SimulatedClock and asserts the
        reported phase at each step.  A factory that ignores durations or starts
        on the wrong phase fails here.
        """
        body = textwrap.dedent(
            """\
            it('cycles green->yellow->red->green on configured delays', async () => {
              const { actor, clock } = startLight({ greenMs: 1000, yellowMs: 400, redMs: 800 });
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('green');

              clock.increment(1000);
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('yellow');

              clock.increment(400);
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('red');

              clock.increment(800);
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('green');
            });
            """
        )
        ok, out = _passed(_run_scenario("FullCycle", body))
        assert ok, f"full-cycle scenario failed:\n{out[-3500:]}"

    def test_phase_does_not_advance_before_duration(self):
        """L2: advancing less than the phase duration must NOT advance the phase.

        Partial-time discriminator: a stub that advances on any tick (or that
        uses real timers) cannot keep green stable for greenMs-1 and then flip
        to yellow exactly at greenMs.
        """
        body = textwrap.dedent(
            """\
            it('green holds before greenMs and flips exactly at greenMs', async () => {
              const { actor, clock } = startLight({ greenMs: 1000, yellowMs: 400, redMs: 800 });
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('green');

              clock.increment(999);
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('green');

              clock.increment(1);   // now exactly greenMs total
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('yellow');
            });
            """
        )
        ok, out = _passed(_run_scenario("PartialHold", body))
        assert ok, f"partial-hold scenario failed:\n{out[-3500:]}"

    def test_walk_freezes_cycle_even_under_large_time(self):
        """L2: pedestrian request -> walk; no advance even after huge simulated time.

        We enter walk from yellow and burn an enormous amount of simulated time;
        the reported state must remain in walk (it must NOT progress to red or
        back to green).  A naive factory that keeps the phase timer running in
        walk fails.
        """
        body = textwrap.dedent(
            """\
            it('walk mode halts automatic advancement', async () => {
              const { actor, clock } = startLight({ greenMs: 1000, yellowMs: 400, redMs: 800 });
              await flush();
              clock.increment(1000);              // -> yellow
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('yellow');

              actor.send({ type: 'PED_REQUEST' });
              await flush();
              const inWalk = valueBlob(actor.getSnapshot());
              expect(inWalk).toContain('walk');
              // walk is a distinct mode, not one of the running phase leaves.
              expect(inWalk).not.toContain('yellow');

              clock.increment(10_000_000);        // enormous time, must not advance
              await flush();
              const still = valueBlob(actor.getSnapshot());
              expect(still).toContain('walk');
              expect(still).not.toContain('red');
            });
            """
        )
        ok, out = _passed(_run_scenario("WalkFreeze", body))
        assert ok, f"walk-freeze scenario failed:\n{out[-3500:]}"

    def test_resume_returns_to_interrupted_yellow(self):
        """L2: walk from yellow, then clear -> back to yellow (the interrupted phase).

        The resume phase must be recovered from the cycle's remembered position.
        We interrupt at yellow and assert clear returns to yellow (not green,
        not red), then a full yellowMs advances to red.
        """
        body = textwrap.dedent(
            """\
            it('clearing walk resumes the interrupted yellow phase', async () => {
              const { actor, clock } = startLight({ greenMs: 1000, yellowMs: 400, redMs: 800 });
              await flush();
              clock.increment(1000);              // -> yellow
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('yellow');

              actor.send({ type: 'PED_REQUEST' });
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('walk');

              actor.send({ type: 'PED_CLEAR' });
              await flush();
              const resumed = valueBlob(actor.getSnapshot());
              expect(resumed).toContain('yellow');
              expect(resumed).not.toContain('walk');

              // a full yellow duration from here advances to red.
              clock.increment(400);
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('red');
            });
            """
        )
        ok, out = _passed(_run_scenario("ResumeYellow", body))
        assert ok, f"resume-yellow scenario failed:\n{out[-3500:]}"

    def test_resume_returns_to_interrupted_red(self):
        """L2: walk from red, then clear -> back to red, with a duplicate request ignored.

        Interrupt at red, send a SECOND pedestrian request while in walk (must be
        ignored, still walk), then clear -> back to red.  Distinguishes the
        interrupted phase from yellow: a factory that always resumes to a fixed
        phase fails because the previous scenario resumed yellow.
        """
        body = textwrap.dedent(
            """\
            it('resumes red and ignores a duplicate pedestrian request', async () => {
              const { actor, clock } = startLight({ greenMs: 1000, yellowMs: 400, redMs: 800 });
              await flush();
              clock.increment(1000);              // -> yellow
              await flush();
              clock.increment(400);               // -> red
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('red');

              actor.send({ type: 'PED_REQUEST' });
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('walk');

              // duplicate request while in walk: ignored, still walk.
              actor.send({ type: 'PED_REQUEST' });
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('walk');

              actor.send({ type: 'PED_CLEAR' });
              await flush();
              const resumed = valueBlob(actor.getSnapshot());
              expect(resumed).toContain('red');
              expect(resumed).not.toContain('walk');

              clock.increment(800);               // full red -> green
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('green');
            });
            """
        )
        ok, out = _passed(_run_scenario("ResumeRed", body))
        assert ok, f"resume-red scenario failed:\n{out[-3500:]}"

    def test_resume_restarts_phase_timer_partial_then_full(self):
        """L2: after resume, partial time does NOT advance; full duration does.

        Core discriminator for "restart that phase's timer from the beginning":
        before walk, we let the green timer run partway; after clear we advance
        less than the FULL greenMs (but more than the remaining-before-walk
        amount) and require green to still be active, proving the timer was
        reset rather than continued.  Then a full greenMs advances to yellow.
        """
        body = textwrap.dedent(
            """\
            it('resumed phase restarts its full timer from zero', async () => {
              const { actor, clock } = startLight({ greenMs: 1000, yellowMs: 400, redMs: 800 });
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('green');

              // run green most of the way (700/1000) BEFORE interrupting.
              clock.increment(700);
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('green');

              actor.send({ type: 'PED_REQUEST' });   // -> walk (from green)
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('walk');

              actor.send({ type: 'PED_CLEAR' });      // resume green, timer reset
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('green');

              // If the timer had merely continued (300 left), 400ms would flip to
              // yellow.  Because it RESTARTED, 400ms must keep us in green.
              clock.increment(400);
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('green');

              // a further 600ms reaches the full fresh 1000 -> yellow.
              clock.increment(600);
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('yellow');
            });
            """
        )
        ok, out = _passed(_run_scenario("ResumeReset", body))
        assert ok, f"resume-timer-reset scenario failed:\n{out[-3500:]}"

    def test_phase_is_read_from_state_not_data_flag(self):
        """L2: the active phase and walk-mode are derivable purely from snapshot.value.

        Acceptance Criterion: "Phase and walk-mode are queried through the
        snapshot's reported state; no data flags restate the phase."  We assert
        that snapshot.value alone (ignoring context) distinguishes every phase
        and walk -- i.e. the value is not a constant placeholder.
        """
        body = textwrap.dedent(
            """\
            it('snapshot.value distinguishes every phase and walk', async () => {
              const { actor, clock } = startLight({ greenMs: 1000, yellowMs: 400, redMs: 800 });
              await flush();
              const seen = new Set();
              seen.add(valueBlob(actor.getSnapshot()));   // green

              clock.increment(1000); await flush();
              seen.add(valueBlob(actor.getSnapshot()));   // yellow

              actor.send({ type: 'PED_REQUEST' }); await flush();
              seen.add(valueBlob(actor.getSnapshot()));   // walk

              actor.send({ type: 'PED_CLEAR' }); await flush();
              clock.increment(400); await flush();
              seen.add(valueBlob(actor.getSnapshot()));   // red

              // green, yellow, red, walk -> at least 4 DISTINCT reported states.
              expect(seen.size).toBeGreaterThanOrEqual(4);
              const joined = [...seen].join('|');
              expect(joined).toContain('green');
              expect(joined).toContain('yellow');
              expect(joined).toContain('red');
              expect(joined).toContain('walk');
            });
            """
        )
        ok, out = _passed(_run_scenario("StateNotFlag", body))
        assert ok, f"state-not-flag scenario failed:\n{out[-3500:]}"

    def test_cycle_continues_indefinitely_after_resume(self):
        """L2: after a walk/resume detour the cycle keeps cycling correctly.

        Ensures entering/leaving walk does not corrupt durations or skip a phase:
        we interrupt at red, resume, and then verify two more full phase
        transitions occur on the configured delays.
        """
        body = textwrap.dedent(
            """\
            it('cycle keeps advancing correctly after a walk detour', async () => {
              const { actor, clock } = startLight({ greenMs: 1000, yellowMs: 400, redMs: 800 });
              await flush();
              clock.increment(1000); await flush();   // yellow
              clock.increment(400);  await flush();   // red
              expect(valueBlob(actor.getSnapshot())).toContain('red');

              actor.send({ type: 'PED_REQUEST' }); await flush();
              actor.send({ type: 'PED_CLEAR' });   await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('red');

              clock.increment(800); await flush();    // red -> green
              expect(valueBlob(actor.getSnapshot())).toContain('green');
              clock.increment(1000); await flush();   // green -> yellow
              expect(valueBlob(actor.getSnapshot())).toContain('yellow');
            });
            """
        )
        ok, out = _passed(_run_scenario("ContinuesAfter", body))
        assert ok, f"continue-after-resume scenario failed:\n{out[-3500:]}"

    def test_distinct_durations_respected_per_phase(self):
        """L2: each phase uses its OWN configured duration, not a shared/first value.

        With clearly different durations, advancing exactly one phase's duration
        must advance only when that phase's value is reached.  This catches a
        factory that hardcodes a single delay for all phases.
        """
        body = textwrap.dedent(
            """\
            it('green/yellow/red honor their distinct durations', async () => {
              const { actor, clock } = startLight({ greenMs: 300, yellowMs: 1200, redMs: 700 });
              await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('green');

              // green is short: 300 advances; a wrong shared 1200 would not.
              clock.increment(299); await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('green');
              clock.increment(1);   await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('yellow');

              // yellow is long: 700 (red's duration) must NOT advance it.
              clock.increment(700); await flush();
              expect(valueBlob(actor.getSnapshot())).toContain('yellow');
              clock.increment(500); await flush();   // total 1200 -> red
              expect(valueBlob(actor.getSnapshot())).toContain('red');

              clock.increment(700); await flush();   // red -> green
              expect(valueBlob(actor.getSnapshot())).toContain('green');
            });
            """
        )
        ok, out = _passed(_run_scenario("DistinctDurations", body))
        assert ok, f"distinct-durations scenario failed:\n{out[-3500:]}"

    def test_agent_spec_passes_native_command(self):
        """L2: the agent's own deterministic spec passes via the exact Acceptance-Criteria command.

        Runs `pnpm vitest run --project xstate packages/core/test/trafficLight.test.ts`
        from the repo root and requires a clean pass with at least one test.
        """
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        proc = _vitest(AGENT_SPEC, timeout=600)
        ok, out = _passed(proc)
        assert ok, f"agent's trafficLight.test.ts did not pass:\n{out[-4000:]}"
        # ensure it actually executed at least one test (no empty/skipped pass)
        assert ("passed" in out.lower()) or ("✓" in out), (
            f"agent spec produced no passing tests:\n{out[-2000:]}"
        )
