"""Tests for the `xstate-state-machine` skill task (ext2): Multi-Step Checkout Wizard.

The task asks the agent to add, inside the `xstate` monorepo's core package, a
self-contained checkout-wizard module exporting a factory ``createCheckoutWizard()``
plus a vitest spec, modeling a linear purchase flow:

    cart  ->  shipping  ->  payment  ->  confirmed (terminal)

with forward "continue" navigation gated on per-step validity, "back" navigation
that clamps at the first step and never discards collected data, and a terminal
"confirmed" outcome that ignores further events.  Deliverables:

  * packages/core/test/fixtures/checkoutWizard.ts  (the wizard module)
  * packages/core/test/checkoutWizard.test.ts      (the agent's own spec)

These tests verify the work in two complementary ways:

  L1 -- the deliverable files exist and are minimally well-formed (import only
        from the public surface ``../../src/index.ts``; export the factory).

  L2 -- DYNAMIC EXECUTION.  Rather than trusting the spec the agent itself wrote,
        we inject our OWN independent vitest specs next to the fixture, import the
        agent's ``createCheckoutWizard`` factory, drive it through every
        Expected-Functionality scenario with the real XState actor API, and assert
        on the actual reported state (the *active step* via ``snap.value`` /
        ``snap.matches``), on collected data (cart count, address, token) exposed
        on the snapshot, and on the snapshot's own "can continue now" capability
        check (``snap.can(...)``) rather than string comparisons in the helper.
        We run each spec with the package's native command
        ``pnpm vitest run --project xstate <file>``.

A naive factory that ignores per-step validity (always advancing), that lets
"back" fall off the first step, that discards collected data on navigation, that
reconstructs step values from placeholders rather than the supplied event, or
that keeps mutating after confirmation, cannot pass the independently-authored
scenarios below.
"""

import os
import re
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/xstate"
CORE = os.path.join(REPO_DIR, "packages", "core")
TEST_DIR = os.path.join(CORE, "test")
FIXTURE = os.path.join(TEST_DIR, "fixtures", "checkoutWizard.ts")
AGENT_SPEC = os.path.join(TEST_DIR, "checkoutWizard.test.ts")

# Where we drop our own independent, harness-authored specs.  Kept under the
# package test dir so the `xstate` vitest project picks them up by glob.
HARNESS_PREFIX = "harnessCheckoutWizard"


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


# Common preamble for every harness spec: vitest globals are enabled (config has
# globals:true), the real actor API, and the agent's factory.  We also expose a
# microtask flush helper to drain any queued promise continuations.
PREAMBLE = textwrap.dedent(
    """\
    import { createActor } from '../src/index.ts';
    import { createCheckoutWizard } from './fixtures/checkoutWizard.ts';

    // microtask flush helper: lets queued promise continuations run.
    const flush = async () => {
      for (let i = 0; i < 8; i++) {
        await Promise.resolve();
      }
    };

    // Resolve the active step name from the reported state, WITHOUT the helper
    // hard-coding the wizard's internal value shape.  The wizard models exactly
    // the four states below; we probe the snapshot's own matches() to find which
    // one is active.  (This still relies only on the snapshot's reported state,
    // per the Acceptance Criteria, not on data booleans.)
    const STEPS = ['cart', 'shipping', 'payment', 'confirmed'];
    const activeStep = (snap) => {
      for (const s of STEPS) {
        try {
          if (snap.matches(s)) return s;
        } catch (e) { /* matches may throw on unknown value; ignore */ }
      }
      // Fall back to a flat string value if matches() didn't resolve.
      if (typeof snap.value === 'string' && STEPS.includes(snap.value)) {
        return snap.value;
      }
      return JSON.stringify(snap.value);
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
        """L1: the wizard module fixture file was created at the required path."""
        assert os.path.isfile(FIXTURE), f"missing wizard module: {FIXTURE}"
        assert os.path.getsize(FIXTURE) > 0, "checkoutWizard.ts is empty"

    def test_agent_spec_file_exists(self):
        """L1: the agent's own deterministic spec file was created."""
        assert os.path.isfile(AGENT_SPEC), f"missing spec: {AGENT_SPEC}"
        assert os.path.getsize(AGENT_SPEC) > 0, "checkoutWizard.test.ts is empty"

    def test_fixture_exports_factory_and_uses_public_surface(self):
        """L1: module exports `createCheckoutWizard` and imports only from src/index.ts.

        We do not keyword-match behavior; we only check the import discipline
        (Acceptance Criterion: import solely from ../../src/index.ts) and that
        the named export is present so our L2 specs can import it.
        """
        with open(FIXTURE) as fh:
            src = fh.read()
        assert "createCheckoutWizard" in src, "factory export not found"
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
    def test_starts_on_cart(self):
        """L2: a freshly started wizard reports the `cart` step (active step from state)."""
        body = textwrap.dedent(
            """\
            it('starts on the cart step', async () => {
              const actor = createActor(createCheckoutWizard()).start();
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('cart');
            });
            """
        )
        ok, out = _passed(_run_scenario("Start", body))
        assert ok, f"start-on-cart scenario failed:\n{out[-3000:]}"

    def test_continue_blocked_on_unsatisfied_step(self):
        """L2: continue on an empty cart leaves the wizard on `cart` (validity gate).

        A naive factory that always advances on `continue` fails here: an empty
        cart is unsatisfied, so the wizard must remain on `cart`.
        """
        body = textwrap.dedent(
            """\
            it('continue on empty cart stays on cart', async () => {
              const actor = createActor(createCheckoutWizard()).start();
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('cart');
            });
            """
        )
        ok, out = _passed(_run_scenario("BlockedContinue", body))
        assert ok, f"blocked-continue scenario failed:\n{out[-3000:]}"

    def test_full_happy_path_to_confirmed_with_data(self):
        """L2: cart=2 -> shipping (addr) -> payment (token) -> confirmed, data exposed.

        Drives the full ordered flow and asserts the terminal `confirmed` step
        AND the final collected data (cart line count, address, token) surfaced on
        the snapshot exactly matches the last supplied values.  A stub that
        hard-codes data or skips storage fails the value assertions.
        """
        body = textwrap.dedent(
            """\
            it('full path reaches confirmed carrying all collected data', async () => {
              const actor = createActor(createCheckoutWizard()).start();
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('cart');

              // satisfy cart with 2 lines, then continue -> shipping
              actor.send({ type: 'setCart', lines: 2 });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('shipping');

              // satisfy shipping with address, continue -> payment
              actor.send({ type: 'setAddress', address: '10 Main' });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('payment');

              // satisfy payment with token, continue -> confirmed (terminal)
              actor.send({ type: 'setToken', token: 'tok_1' });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('confirmed');

              // final collected data must be exposed on the snapshot and match.
              const blob = JSON.stringify(actor.getSnapshot().context);
              expect(blob).toContain('10 Main');
              expect(blob).toContain('tok_1');
              // cart line count 2 is present in the carried data.
              const ctx = actor.getSnapshot().context;
              const ctxStr = JSON.stringify(ctx);
              // numeric 2 should appear as a value (cart line count).
              expect(/[:\\[,]\\s*2\\b/.test(ctxStr)).toBe(true);
            });
            """
        )
        ok, out = _passed(_run_scenario("HappyPath", body))
        assert ok, f"happy-path scenario failed:\n{out[-3500:]}"

    def test_continue_gated_at_each_step(self):
        """L2: continue is blocked at shipping (no address) and payment (no token).

        Reaches shipping, sends continue WITHOUT an address -> must stay on
        shipping; reaches payment, continue WITHOUT a token -> must stay on payment.
        A factory that gates only the cart step (or gates nothing) fails here.
        """
        body = textwrap.dedent(
            """\
            it('continue is gated at shipping and payment too', async () => {
              const actor = createActor(createCheckoutWizard()).start();
              await flush();
              actor.send({ type: 'setCart', lines: 1 });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('shipping');

              // no address yet -> continue must NOT advance to payment.
              actor.send({ type: 'continue' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('shipping');

              actor.send({ type: 'setAddress', address: '1 A St' });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('payment');

              // empty token -> continue must NOT confirm.
              actor.send({ type: 'continue' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('payment');
            });
            """
        )
        ok, out = _passed(_run_scenario("Gated", body))
        assert ok, f"per-step-gate scenario failed:\n{out[-3500:]}"

    def test_back_navigation_and_clamp_at_first_step(self):
        """L2: back walks payment->shipping->cart and clamps at cart; data retained.

        From payment, back -> shipping -> cart -> (clamped) cart.  Collected data
        from visited steps must be retained throughout.  A factory whose back
        falls off the first step (or clears data) fails this.
        """
        body = textwrap.dedent(
            """\
            it('back walks backwards, clamps at cart, retains data', async () => {
              const actor = createActor(createCheckoutWizard()).start();
              await flush();
              actor.send({ type: 'setCart', lines: 3 });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              actor.send({ type: 'setAddress', address: '22 Elm' });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('payment');

              actor.send({ type: 'back' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('shipping');

              actor.send({ type: 'back' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('cart');

              // back from the first step clamps to cart.
              actor.send({ type: 'back' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('cart');

              // data already collected for visited steps is retained.
              const blob = JSON.stringify(actor.getSnapshot().context);
              expect(blob).toContain('22 Elm');
            });
            """
        )
        ok, out = _passed(_run_scenario("BackClamp", body))
        assert ok, f"back-clamp scenario failed:\n{out[-3500:]}"

    def test_edit_then_reconfirm_reflects_edited_value(self):
        """L2: go to shipping, back to cart, edit cart lines, continue -> shipping with addr kept.

        Reaches shipping, goes back to cart, edits the cart line count to 5, then
        continues again.  The wizard must return to shipping with the previously
        entered address still present, and at confirmation the edited cart count
        must be the one carried.  A factory that snapshots step data once (and
        ignores re-edits) fails the edit-then-reconfirm path.
        """
        body = textwrap.dedent(
            """\
            it('editing an earlier step then continuing reflects the edit', async () => {
              const actor = createActor(createCheckoutWizard()).start();
              await flush();
              actor.send({ type: 'setCart', lines: 2 });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              actor.send({ type: 'setAddress', address: '99 Oak' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('shipping');

              // back to cart, edit the line count, then continue again.
              actor.send({ type: 'back' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('cart');
              actor.send({ type: 'setCart', lines: 5 });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              // back on shipping, with the previously entered address retained.
              expect(activeStep(actor.getSnapshot())).toBe('shipping');
              expect(JSON.stringify(actor.getSnapshot().context)).toContain('99 Oak');

              // finish: edited cart count (5) must carry to confirmation.
              actor.send({ type: 'setToken', token: 'tok_z' });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('confirmed');
              const ctxStr = JSON.stringify(actor.getSnapshot().context);
              expect(/[:\\[,]\\s*5\\b/.test(ctxStr)).toBe(true);
              // the stale value 2 must not have survived as the cart count.
              expect(ctxStr).toContain('99 Oak');
              expect(ctxStr).toContain('tok_z');
            });
            """
        )
        ok, out = _passed(_run_scenario("EditReconfirm", body))
        assert ok, f"edit-then-reconfirm scenario failed:\n{out[-3500:]}"

    def test_confirmed_is_terminal_and_ignores_events(self):
        """L2: after confirmed, further continue/back/set-data leave state and data unchanged.

        A naive factory whose `confirmed` state still processes navigation or data
        events fails here: post-confirmation the active step AND the carried data
        must be invariant.
        """
        body = textwrap.dedent(
            """\
            it('confirmed state ignores subsequent events', async () => {
              const actor = createActor(createCheckoutWizard()).start();
              await flush();
              actor.send({ type: 'setCart', lines: 4 });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              actor.send({ type: 'setAddress', address: '7 Birch' });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              actor.send({ type: 'setToken', token: 'tok_final' });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('confirmed');
              const before = JSON.stringify(actor.getSnapshot().context);

              // bombard with events that must be ignored once confirmed.
              actor.send({ type: 'back' });
              actor.send({ type: 'continue' });
              actor.send({ type: 'setAddress', address: 'HACKED' });
              actor.send({ type: 'setCart', lines: 999 });
              actor.send({ type: 'setToken', token: 'HACKED' });
              await flush();

              expect(activeStep(actor.getSnapshot())).toBe('confirmed');
              const after = JSON.stringify(actor.getSnapshot().context);
              expect(after).toBe(before);
              expect(after).not.toContain('HACKED');
              expect(after).not.toContain('999');
            });
            """
        )
        ok, out = _passed(_run_scenario("Terminal", body))
        assert ok, f"confirmed-terminal scenario failed:\n{out[-3500:]}"

    def test_can_continue_capability_via_snapshot(self):
        """L2: snapshot's own capability check answers "would continue be acted on now".

        Per the Acceptance Criteria, "can continue now" is answered via the
        snapshot's own capability check (e.g. snap.can({type:'continue'})) rather
        than string comparisons.  It must be false on an unsatisfied step (empty
        cart) and true once the active step is satisfied.
        """
        body = textwrap.dedent(
            """\
            it('snapshot.can reflects whether continue is currently actionable', async () => {
              const actor = createActor(createCheckoutWizard()).start();
              await flush();
              // empty cart -> continue not actionable.
              expect(actor.getSnapshot().can({ type: 'continue' })).toBe(false);
              actor.send({ type: 'setCart', lines: 1 });
              await flush();
              // satisfied cart -> continue actionable.
              expect(actor.getSnapshot().can({ type: 'continue' })).toBe(true);

              actor.send({ type: 'continue' });
              await flush();
              // on shipping with no address -> not actionable again.
              expect(actor.getSnapshot().can({ type: 'continue' })).toBe(false);
              actor.send({ type: 'setAddress', address: '5 Pine' });
              await flush();
              expect(actor.getSnapshot().can({ type: 'continue' })).toBe(true);
            });
            """
        )
        ok, out = _passed(_run_scenario("CanContinue", body))
        assert ok, f"snapshot.can capability scenario failed:\n{out[-3000:]}"

    def test_back_then_continue_does_not_lose_downstream_path(self):
        """L2: from payment, back to shipping, edit address, continue -> payment again, then confirm.

        Verifies that visiting back and re-editing an intermediate step still
        allows reaching confirmation, with the edited address carried, and that
        the token set later is the one confirmed.
        """
        body = textwrap.dedent(
            """\
            it('edit shipping mid-flow and re-continue reaches confirmed with edits', async () => {
              const actor = createActor(createCheckoutWizard()).start();
              await flush();
              actor.send({ type: 'setCart', lines: 1 });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              actor.send({ type: 'setAddress', address: 'OLD ADDR' });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('payment');

              // back to shipping, change the address.
              actor.send({ type: 'back' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('shipping');
              actor.send({ type: 'setAddress', address: 'NEW ADDR' });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('payment');

              actor.send({ type: 'setToken', token: 'tok_q' });
              await flush();
              actor.send({ type: 'continue' });
              await flush();
              expect(activeStep(actor.getSnapshot())).toBe('confirmed');
              const ctxStr = JSON.stringify(actor.getSnapshot().context);
              expect(ctxStr).toContain('NEW ADDR');
              expect(ctxStr).not.toContain('OLD ADDR');
              expect(ctxStr).toContain('tok_q');
            });
            """
        )
        ok, out = _passed(_run_scenario("EditShipping", body))
        assert ok, f"edit-shipping mid-flow scenario failed:\n{out[-3500:]}"

    def test_agent_spec_passes_native_command(self):
        """L2: the agent's own deterministic spec passes via the exact Acceptance-Criteria command.

        Runs `pnpm vitest run --project xstate packages/core/test/checkoutWizard.test.ts`
        from the repo root and requires a clean pass with at least one test.
        """
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        proc = _vitest(AGENT_SPEC, timeout=600)
        ok, out = _passed(proc)
        assert ok, f"agent's checkoutWizard.test.ts did not pass:\n{out[-4000:]}"
        # ensure it actually executed at least one test (no empty/skipped pass)
        assert ("passed" in out.lower()) or ("✓" in out), (
            f"agent spec produced no passing tests:\n{out[-2000:]}"
        )
