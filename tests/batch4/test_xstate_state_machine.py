"""Tests for the `xstate-state-machine` skill task (variant ext4): Parallel Media-Player Module.

The task asks the agent to add, inside the `xstate` monorepo's core package, a
self-contained media-player module exporting a factory ``createMediaPlayer()``
plus a deterministic vitest spec.  The player tracks two CONCURRENT, INDEPENDENT
concerns expressed as parallel states:

  * Playback : stopped | playing | paused
  * Sound    : unmuted | muted   (plus a durable `volume` number in context)

Deliverables:

  * packages/core/test/fixtures/mediaPlayer.ts   (the player module)
  * packages/core/test/mediaPlayer.test.ts       (the agent's own spec)

Verification strategy (two complementary levels):

  L1 -- the deliverable files exist, are non-empty, export ``createMediaPlayer``
        and import only from the public surface ``../../src/index.ts``.

  L2 -- DYNAMIC EXECUTION.  Rather than trusting the spec the agent itself wrote,
        we inject our OWN independent vitest specs next to the fixture, import the
        agent's ``createMediaPlayer`` factory, drive it with the real XState actor
        API, and assert on the live snapshot using the snapshot's own
        ``matches`` / ``value`` / ``context`` capabilities.  We run each spec with
        the package's native command
        ``pnpm vitest run --project xstate <file>``.

The decisive discriminators (a naive/stub implementation must FAIL):
  * the two concerns are PARALLEL -- toggling sound never resets playback and
    vice-versa (a sequential single-region machine fails the cross-region
    independence assertions);
  * a pause sent while stopped is IGNORED (no transition);
  * volume travels with the set-volume event and is read back from the snapshot,
    while the muted/unmuted MODE is unaffected by setting volume;
  * playback and sound modes are expressed as STATES (readable via
    snapshot.matches), not as context flags.
"""

import os
import re
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/xstate"
CORE = os.path.join(REPO_DIR, "packages", "core")
TEST_DIR = os.path.join(CORE, "test")
FIXTURE = os.path.join(TEST_DIR, "fixtures", "mediaPlayer.ts")
AGENT_SPEC = os.path.join(TEST_DIR, "mediaPlayer.test.ts")

# Where we drop our own independent, harness-authored specs.  Kept under the
# package test dir so the `xstate` vitest project picks them up by glob.
HARNESS_PREFIX = "harnessMediaPlayer"


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

    Path is passed relative to the repo root, matching the command in the
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


# Common preamble for every harness spec.  Vitest globals are enabled
# (config has globals:true).  We import the real actor API and the agent's
# factory from the package public surface, plus a microtask-flush helper.
PREAMBLE = textwrap.dedent(
    """\
    import { createActor } from '../src/index.ts';
    import { createMediaPlayer } from './fixtures/mediaPlayer.ts';

    // microtask flush helper: lets queued promise continuations run.
    const flush = async () => {
      for (let i = 0; i < 8; i++) {
        await Promise.resolve();
      }
    };

    // Build + start an actor for the agent's factory.
    const startPlayer = () => {
      const logic = createMediaPlayer();
      return createActor(logic).start();
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
        """L1: the media-player module fixture file was created at the required path."""
        assert os.path.isfile(FIXTURE), f"missing media-player module: {FIXTURE}"
        assert os.path.getsize(FIXTURE) > 0, "mediaPlayer.ts is empty"

    def test_agent_spec_file_exists(self):
        """L1: the agent's own deterministic spec file was created."""
        assert os.path.isfile(AGENT_SPEC), f"missing spec: {AGENT_SPEC}"
        assert os.path.getsize(AGENT_SPEC) > 0, "mediaPlayer.test.ts is empty"

    def test_fixture_exports_factory_and_uses_public_surface(self):
        """L1: module exports `createMediaPlayer` and imports only from src/index.ts.

        We check import discipline (Acceptance Criterion: import solely from
        ``../../src/index.ts``) and that the named export is present so our L2
        specs can import it.  No behavioral keyword matching.
        """
        with open(FIXTURE) as fh:
            src = fh.read()
        assert "createMediaPlayer" in src, "factory export `createMediaPlayer` not found"
        # No deep reach-ins past the public index barrel.
        forbidden = [
            "../../src/StateMachine",
            "../../src/State.ts",
            "../../src/createActor",
            "from '../../src/actors",
            "from '../../src/setup",
        ]
        for f in forbidden:
            assert f not in src, f"module reaches into internal file: {f}"
        # Any relative import that touches src must go through the index barrel.
        for m in re.finditer(r"""from\s+['"]([^'"]*src[^'"]*)['"]""", src):
            spec = m.group(1)
            assert spec.rstrip("'\"").endswith(
                ("src/index.ts", "src/index")
            ), f"non-public src import: {spec}"

    # ------------------------------------------------------------------ #
    # L2: independent dynamic scenarios driving the agent's factory
    # ------------------------------------------------------------------ #
    def test_initial_parallel_state(self):
        """L2: start -> playback stopped, sound unmuted, both readable from one snapshot.

        Uses snapshot.matches for BOTH region modes simultaneously (proving the
        regions coexist in a single snapshot) and reads the durable volume from
        context.  A single-region machine cannot satisfy matching both at once.
        """
        body = textwrap.dedent(
            """\
            it('initial snapshot exposes both parallel modes plus volume', () => {
              const actor = startPlayer();
              const snap = actor.getSnapshot();
              expect(snap.matches({ playback: 'stopped' })).toBe(true);
              expect(snap.matches({ sound: 'unmuted' })).toBe(true);
              // both regions visible in one snapshot value (object form).
              expect(typeof snap.value).toBe('object');
              expect(snap.matches({ playback: 'playing' })).toBe(false);
              expect(snap.matches({ sound: 'muted' })).toBe(false);
              // durable volume present as a number.
              expect(typeof snap.context.volume).toBe('number');
            });
            """
        )
        ok, out = _passed(_run_scenario("Initial", body))
        assert ok, f"initial parallel-state scenario failed:\n{out[-3000:]}"

    def test_play_then_mute_simultaneous_combination(self):
        """L2: play + mute-toggle -> playback PLAYING and sound MUTED simultaneously.

        Discriminative simultaneous-combination assertion required by the doc:
        both modes must hold at the same time in one snapshot.
        """
        body = textwrap.dedent(
            """\
            it('playing AND muted hold simultaneously', () => {
              const actor = startPlayer();
              actor.send({ type: 'play' });
              actor.send({ type: 'toggleMute' });
              const snap = actor.getSnapshot();
              expect(snap.matches({ playback: 'playing' })).toBe(true);
              expect(snap.matches({ sound: 'muted' })).toBe(true);
              // and not the alternatives.
              expect(snap.matches({ playback: 'stopped' })).toBe(false);
              expect(snap.matches({ sound: 'unmuted' })).toBe(false);
            });
            """
        )
        ok, out = _passed(_run_scenario("PlayMute", body))
        assert ok, f"play+mute combination scenario failed:\n{out[-3000:]}"

    def test_playback_transitions(self):
        """L2: full playback path stopped->playing->paused->playing->stopped.

        Drives every playback transition from the doc and asserts the mode after
        each step via snapshot.matches.
        """
        body = textwrap.dedent(
            """\
            it('playback follows the specified transitions', () => {
              const actor = startPlayer();
              expect(actor.getSnapshot().matches({ playback: 'stopped' })).toBe(true);
              actor.send({ type: 'play' });
              expect(actor.getSnapshot().matches({ playback: 'playing' })).toBe(true);
              actor.send({ type: 'pause' });
              expect(actor.getSnapshot().matches({ playback: 'paused' })).toBe(true);
              actor.send({ type: 'play' });   // resume
              expect(actor.getSnapshot().matches({ playback: 'playing' })).toBe(true);
              actor.send({ type: 'stop' });
              expect(actor.getSnapshot().matches({ playback: 'stopped' })).toBe(true);
            });

            it('paused can stop directly', () => {
              const actor = startPlayer();
              actor.send({ type: 'play' });
              actor.send({ type: 'pause' });
              expect(actor.getSnapshot().matches({ playback: 'paused' })).toBe(true);
              actor.send({ type: 'stop' });
              expect(actor.getSnapshot().matches({ playback: 'stopped' })).toBe(true);
            });
            """
        )
        ok, out = _passed(_run_scenario("Playback", body))
        assert ok, f"playback transitions scenario failed:\n{out[-3500:]}"

    def test_pause_while_stopped_is_ignored(self):
        """L2: a pause sent while stopped must be IGNORED (remains stopped).

        Required edge case.  A naive machine that pauses unconditionally fails.
        We also confirm sound is untouched.
        """
        body = textwrap.dedent(
            """\
            it('pause while stopped is a no-op', () => {
              const actor = startPlayer();
              expect(actor.getSnapshot().matches({ playback: 'stopped' })).toBe(true);
              actor.send({ type: 'pause' });
              const snap = actor.getSnapshot();
              expect(snap.matches({ playback: 'stopped' })).toBe(true);
              expect(snap.matches({ playback: 'paused' })).toBe(false);
              // sound concern undisturbed.
              expect(snap.matches({ sound: 'unmuted' })).toBe(true);
            });
            """
        )
        ok, out = _passed(_run_scenario("PauseStopped", body))
        assert ok, f"pause-while-stopped scenario failed:\n{out[-3000:]}"

    def test_mute_toggle_does_not_disturb_playback(self):
        """L2: toggling sound never resets/disturbs playback (cross-region independence).

        Core parallel-state discriminator: from playing+muted, toggling mute back
        to unmuted leaves playback at PLAYING.  A sequential machine that shares a
        single region would reset playback.
        """
        body = textwrap.dedent(
            """\
            it('mute toggling leaves playback mode intact', () => {
              const actor = startPlayer();
              actor.send({ type: 'play' });
              actor.send({ type: 'toggleMute' });   // -> muted
              expect(actor.getSnapshot().matches({ playback: 'playing' })).toBe(true);
              expect(actor.getSnapshot().matches({ sound: 'muted' })).toBe(true);
              actor.send({ type: 'toggleMute' });   // -> unmuted
              const snap = actor.getSnapshot();
              expect(snap.matches({ sound: 'unmuted' })).toBe(true);
              // playback unchanged by the sound toggle.
              expect(snap.matches({ playback: 'playing' })).toBe(true);
            });

            it('from paused+muted, mute-toggle keeps playback paused', () => {
              const actor = startPlayer();
              actor.send({ type: 'play' });
              actor.send({ type: 'pause' });
              actor.send({ type: 'toggleMute' });   // paused + muted
              expect(actor.getSnapshot().matches({ playback: 'paused' })).toBe(true);
              expect(actor.getSnapshot().matches({ sound: 'muted' })).toBe(true);
              actor.send({ type: 'toggleMute' });   // paused + unmuted
              const snap = actor.getSnapshot();
              expect(snap.matches({ playback: 'paused' })).toBe(true);
              expect(snap.matches({ sound: 'unmuted' })).toBe(true);
            });
            """
        )
        ok, out = _passed(_run_scenario("MuteIndep", body))
        assert ok, f"mute-independence scenario failed:\n{out[-3500:]}"

    def test_playback_does_not_disturb_sound(self):
        """L2: play/pause/stop never reset the sound concern (reverse independence).

        Mute the player, then run a full playback cycle; sound must stay muted
        throughout, and volume must be preserved.
        """
        body = textwrap.dedent(
            """\
            it('playback events never reset the sound region or volume', () => {
              const actor = startPlayer();
              actor.send({ type: 'toggleMute' });           // muted
              actor.send({ type: 'setVolume', volume: 4 });  // volume 4, still muted
              expect(actor.getSnapshot().matches({ sound: 'muted' })).toBe(true);
              expect(actor.getSnapshot().context.volume).toBe(4);
              actor.send({ type: 'play' });
              actor.send({ type: 'pause' });
              actor.send({ type: 'play' });
              actor.send({ type: 'stop' });
              const snap = actor.getSnapshot();
              // sound concern survived the whole playback cycle.
              expect(snap.matches({ sound: 'muted' })).toBe(true);
              expect(snap.matches({ sound: 'unmuted' })).toBe(false);
              expect(snap.context.volume).toBe(4);
            });
            """
        )
        ok, out = _passed(_run_scenario("PlaybackIndep", body))
        assert ok, f"playback-independence scenario failed:\n{out[-3000:]}"

    def test_set_volume_updates_value_not_mode(self):
        """L2: setVolume updates the volume number and does NOT change muted/unmuted mode.

        Also asserts volume travels with the event (last value wins) and playback
        is unaffected -- per the doc's 'set volume to 7 while playing' scenario.
        """
        body = textwrap.dedent(
            """\
            it('set volume to 7 while playing keeps modes, updates volume', () => {
              const actor = startPlayer();
              actor.send({ type: 'play' });
              const before = actor.getSnapshot();
              expect(before.matches({ sound: 'unmuted' })).toBe(true);
              actor.send({ type: 'setVolume', volume: 7 });
              const snap = actor.getSnapshot();
              expect(snap.context.volume).toBe(7);
              expect(snap.matches({ playback: 'playing' })).toBe(true);  // playback unchanged
              expect(snap.matches({ sound: 'unmuted' })).toBe(true);     // sound mode unchanged
            });

            it('volume is the last value supplied (no pending stash)', () => {
              const actor = startPlayer();
              actor.send({ type: 'setVolume', volume: 2 });
              actor.send({ type: 'setVolume', volume: 9 });
              expect(actor.getSnapshot().context.volume).toBe(9);
            });
            """
        )
        ok, out = _passed(_run_scenario("SetVolume", body))
        assert ok, f"set-volume scenario failed:\n{out[-3500:]}"

    def test_full_expected_functionality_sequence(self):
        """L2: end-to-end scenario chain mirroring the doc's Expected Functionality.

        start -> play+mute -> pause(still muted) -> mute-toggle(unmuted, still
        paused) -> setVolume 7 -> verify every intermediate combination via the
        snapshot's mode-matching capability and context.volume.
        """
        body = textwrap.dedent(
            """\
            it('drives the documented end-to-end functionality', () => {
              const actor = startPlayer();
              let s = actor.getSnapshot();
              expect(s.matches({ playback: 'stopped' })).toBe(true);
              expect(s.matches({ sound: 'unmuted' })).toBe(true);
              const initialVol = s.context.volume;

              actor.send({ type: 'play' });
              actor.send({ type: 'toggleMute' });
              s = actor.getSnapshot();
              expect(s.matches({ playback: 'playing' })).toBe(true);
              expect(s.matches({ sound: 'muted' })).toBe(true);

              actor.send({ type: 'pause' });
              s = actor.getSnapshot();
              expect(s.matches({ playback: 'paused' })).toBe(true);
              expect(s.matches({ sound: 'muted' })).toBe(true);   // still muted

              actor.send({ type: 'toggleMute' });
              s = actor.getSnapshot();
              expect(s.matches({ playback: 'paused' })).toBe(true);   // playback unchanged
              expect(s.matches({ sound: 'unmuted' })).toBe(true);

              // volume unchanged so far.
              expect(s.context.volume).toBe(initialVol);

              actor.send({ type: 'play' });
              actor.send({ type: 'setVolume', volume: 7 });
              s = actor.getSnapshot();
              expect(s.context.volume).toBe(7);
              expect(s.matches({ playback: 'playing' })).toBe(true);
              expect(s.matches({ sound: 'unmuted' })).toBe(true);
            });
            """
        )
        ok, out = _passed(_run_scenario("EndToEnd", body))
        assert ok, f"end-to-end functionality scenario failed:\n{out[-4000:]}"

    def test_modes_are_states_not_context_flags(self):
        """L2: playback/sound modes are expressed as STATES, not data flags.

        We assert via snapshot.matches (state matching), and additionally confirm
        the snapshot value is a parallel object holding BOTH region keys -- a
        context-flag implementation (flat string value) would fail to match both
        partial state values from a single snapshot.
        """
        body = textwrap.dedent(
            """\
            it('both regions are present as state value keys', () => {
              const actor = startPlayer();
              actor.send({ type: 'play' });
              actor.send({ type: 'toggleMute' });
              const snap = actor.getSnapshot();
              // value is an object with both region paths (parallel root).
              expect(typeof snap.value).toBe('object');
              const keys = Object.keys(snap.value);
              expect(keys).toContain('playback');
              expect(keys).toContain('sound');
              // matching by state value (not by a context boolean) works.
              expect(snap.matches({ playback: 'playing', sound: 'muted' })).toBe(true);
            });
            """
        )
        ok, out = _passed(_run_scenario("StatesNotFlags", body))
        assert ok, f"states-not-flags scenario failed:\n{out[-3000:]}"

    def test_agent_spec_passes_native_command(self):
        """L2: the agent's own deterministic spec passes via the exact Acceptance command.

        Runs `pnpm vitest run --project xstate packages/core/test/mediaPlayer.test.ts`
        from the repo root and requires a clean pass with at least one test.
        """
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        proc = _vitest(AGENT_SPEC, timeout=600)
        ok, out = _passed(proc)
        assert ok, f"agent's mediaPlayer.test.ts did not pass:\n{out[-4000:]}"
        # ensure it actually executed at least one test (no empty/skipped pass)
        assert ("passed" in out.lower()) or ("✓" in out), (
            f"agent spec produced no passing tests:\n{out[-2000:]}"
        )
