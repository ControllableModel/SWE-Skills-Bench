"""Tests for the `xstate-state-machine` skill task (ext10): Guarded Withdrawal Module.

The task asks the agent to add, inside the `xstate` monorepo's core package, a
self-contained, *synchronous* account-withdrawal module whose transitions are
gated by several combined conditions, plus a deterministic vitest spec.
Deliverables:

  * packages/core/test/fixtures/withdrawalGuard.ts   (the withdrawal module)
  * packages/core/test/withdrawalGuard.test.ts        (the agent's own spec)

Module surface (per the requirement doc):
  * exported factory ``createWithdrawalMachine(config)`` where ``config`` carries
    ``perTxnLimit`` (max amount per single withdrawal).
  * the returned machine can be started with the package actor API; durable
    context holds ``balance`` (number) and ``frozen`` (boolean) and a per-
    withdrawal ``outcome`` readable from the snapshot.
  * events: ``withdraw`` (carries ``amount``), ``freeze``, ``unfreeze``.

Behavior gated by COMBINED guarding logic:
  A withdraw succeeds iff NOT frozen AND amount <= perTxnLimit AND amount <=
  balance.  On success: balance -= amount; outcome = approved with new balance.
  On failure: balance unchanged; outcome = declined with the *first* failing
  reason in priority order frozen -> over-limit -> insufficient-funds.
  exactly-at-limit and exactly-at-balance are ALLOWED (strict-exceed declines).
  After every attempt the machine returns to the finite **ready** phase.

Verification strategy (two complementary levels):

  L1  -- deliverable files exist, are minimally well-formed, export the factory,
          and import only from the public surface ``../../src/index.ts``.

  L2  -- DYNAMIC EXECUTION.  Rather than trusting the agent's own spec, we inject
          our OWN independent vitest specs next to the fixture, import the
          agent's ``createWithdrawalMachine`` factory, drive it through every
          Expected-Functionality scenario with the real XState actor API, and
          assert on the actual snapshot context (balance / frozen) and the
          recorded outcome (approved/declined + reason).  We run each spec with
          the package's native command
          ``pnpm vitest run --project xstate <file>``.

A stub factory that hard-codes "approved", ignores the frozen flag, mutates the
balance on declines, mis-orders the decline priority, or stashes a pending
amount instead of reading it off the event, cannot pass the scenarios below.
"""

import os
import re
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/xstate"
CORE = os.path.join(REPO_DIR, "packages", "core")
TEST_DIR = os.path.join(CORE, "test")
FIXTURE = os.path.join(TEST_DIR, "fixtures", "withdrawalGuard.ts")
AGENT_SPEC = os.path.join(TEST_DIR, "withdrawalGuard.test.ts")

# Where we drop our own independent, harness-authored specs.  Kept under the
# package test dir so the `xstate` vitest project picks them up by glob.
HARNESS_PREFIX = "harnessWithdrawalGuard"


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


# Common preamble for every harness spec.  The core vitest config enables
# `globals: true`, so `it`/`expect` are ambient.  We import the real actor API
# and the agent's factory, and provide small helpers used by several scenarios.
PREAMBLE = textwrap.dedent(
    """\
    import { createActor } from '../src/index.ts';
    import { createWithdrawalMachine } from './fixtures/withdrawalGuard.ts';

    // Start an actor with given durable context overrides applied via input or
    // post-start events is left to the agent's design; tests below seed balance
    // and frozen through the actor input where supported and otherwise rely on
    // the documented defaults.  We always read state from getSnapshot().context.
    const ctxOf = (actor) => actor.getSnapshot().context;

    // The recorded per-withdrawal outcome must live somewhere on the snapshot
    // context.  We locate it defensively: a field that contains the approved/
    // declined verdict and (for declines) the reason.  This avoids over-fitting
    // to one exact field name while still asserting concrete recorded values.
    const outcomeBlob = (actor) =>
      JSON.stringify(actor.getSnapshot().context).toLowerCase();
    """
)


def _start_snippet(balance, frozen=False, per_txn_limit=50):
    """Return JS that constructs and starts an actor seeded with balance/frozen.

    The requirement doc says durable data includes the current ``balance`` and a
    ``frozen`` boolean.  We seed them through actor ``input`` (the standard
    XState way to parameterize initial context); the factory is expected to read
    ``perTxnLimit`` from its config argument.
    """
    fr = "true" if frozen else "false"
    return textwrap.dedent(
        f"""\
        const machine = createWithdrawalMachine({{ perTxnLimit: {per_txn_limit} }});
        const actor = createActor(machine, {{
          input: {{ balance: {balance}, frozen: {fr} }}
        }}).start();
        """
    )


def _passed(proc):
    """vitest passed iff returncode 0 and no failed tests reported."""
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, out
    if "No test files found" in out:
        return False, out
    m = re.search(r"(\d+)\s+failed", out.lower())
    if m and int(m.group(1)) > 0:
        return False, out
    return True, out


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


class TestXstateStateMachine:
    REPO_DIR = "/workspace/xstate"

    # ------------------------------------------------------------------ #
    # L1: deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_fixture_file_exists(self):
        """L1: the withdrawal module fixture was created at the required path."""
        assert os.path.isfile(FIXTURE), f"missing withdrawal module: {FIXTURE}"
        assert os.path.getsize(FIXTURE) > 0, "withdrawalGuard.ts is empty"

    def test_agent_spec_file_exists(self):
        """L1: the agent's own deterministic spec file was created."""
        assert os.path.isfile(AGENT_SPEC), f"missing spec: {AGENT_SPEC}"
        assert os.path.getsize(AGENT_SPEC) > 0, "withdrawalGuard.test.ts is empty"

    def test_fixture_exports_factory_and_uses_public_surface(self):
        """L1: module exports `createWithdrawalMachine` and imports only from src/index.ts.

        Checks import discipline (Acceptance Criterion: import solely from
        ``../../src/index.ts``) and that the named export is present so our L2
        specs can import it.  Not a behavioral keyword match.
        """
        with open(FIXTURE) as fh:
            src = fh.read()
        assert "createWithdrawalMachine" in src, "factory export not found"
        # Must import from the public barrel.
        assert "../../src/index.ts" in src or "../../src/index" in src, (
            "module does not import from the public surface ../../src/index.ts"
        )
        # No deep reach-ins past the public index barrel.
        forbidden = [
            "../../src/StateMachine",
            "../../src/State.ts",
            "../../src/createActor",
            "from '../../src/actors",
            "../../src/guards",
            "../../src/actions/",
        ]
        for f in forbidden:
            assert f not in src, f"module reaches into internal file: {f}"

    # ------------------------------------------------------------------ #
    # L2: independent dynamic scenarios driving the agent's factory
    # ------------------------------------------------------------------ #
    def test_approved_basic_decrements_balance(self):
        """L2: balance 100, limit 50; withdraw 30 -> approved, balance 70.

        The first Expected-Functionality row.  Asserts the outcome is recorded
        as approved AND the durable balance actually decreased by the amount.
        """
        body = _start_snippet(100, per_txn_limit=50) + textwrap.dedent(
            """\
            it('withdraw 30 from 100 (limit 50) is approved, balance 70', () => {
              actor.send({ type: 'withdraw', amount: 30 });
              const c = ctxOf(actor);
              expect(c.balance).toBe(70);
              expect(c.frozen).toBe(false);
              const blob = outcomeBlob(actor);
              expect(blob).toContain('approv');
              expect(blob).not.toMatch(/declin|insufficient|over.?limit|frozen/);
            });
            """
        )
        ok, out = _run_scenario("ApprovedBasic", body)
        assert ok, f"basic approved scenario failed:\n{out[-3000:]}"

    def test_exactly_at_limit_is_approved(self):
        """L2: withdraw 50 (== perTxnLimit) from balance 70 -> approved, balance 20.

        Boundary discriminator: a naive `amount < limit` guard wrongly declines
        the exactly-at-limit case.  Per the doc only strictly exceeding declines.
        """
        body = _start_snippet(70, per_txn_limit=50) + textwrap.dedent(
            """\
            it('withdraw exactly the limit is approved', () => {
              actor.send({ type: 'withdraw', amount: 50 });
              const c = ctxOf(actor);
              expect(c.balance).toBe(20);
              expect(outcomeBlob(actor)).toContain('approv');
            });
            """
        )
        ok, out = _run_scenario("AtLimit", body)
        assert ok, f"exactly-at-limit scenario failed:\n{out[-3000:]}"

    def test_exactly_at_balance_is_approved(self):
        """L2: withdraw an amount equal to the full balance (within limit) -> approved, balance 0.

        Second boundary: `amount <= balance` must allow equality.  A `amount <
        balance` stub wrongly declines a full-balance withdrawal.
        """
        body = _start_snippet(40, per_txn_limit=50) + textwrap.dedent(
            """\
            it('withdraw equal to balance is approved, leaving zero', () => {
              actor.send({ type: 'withdraw', amount: 40 });
              const c = ctxOf(actor);
              expect(c.balance).toBe(0);
              expect(outcomeBlob(actor)).toContain('approv');
            });
            """
        )
        ok, out = _run_scenario("AtBalance", body)
        assert ok, f"exactly-at-balance scenario failed:\n{out[-3000:]}"

    def test_over_limit_declined_balance_unchanged(self):
        """L2: withdraw 60 from balance 20 (limit 50) -> declined over-limit, balance 20.

        The amount exceeds the per-txn limit (and also the balance, but over-
        limit has higher priority).  Asserts decline, the over-limit reason, and
        that the balance is unchanged (a stub that always decrements fails).
        """
        body = _start_snippet(20, per_txn_limit=50) + textwrap.dedent(
            """\
            it('over-limit withdrawal is declined, balance unchanged', () => {
              actor.send({ type: 'withdraw', amount: 60 });
              const c = ctxOf(actor);
              expect(c.balance).toBe(20);
              const blob = outcomeBlob(actor);
              expect(blob).toContain('declin');
              expect(blob).toMatch(/over.?limit|limit/);
              expect(blob).not.toContain('approv');
              // over-limit takes priority over insufficient-funds here.
              expect(blob).not.toContain('insufficient');
            });
            """
        )
        ok, out = _run_scenario("OverLimit", body)
        assert ok, f"over-limit decline scenario failed:\n{out[-3000:]}"

    def test_insufficient_funds_declined_balance_unchanged(self):
        """L2: withdraw 50 from balance 20 (within limit) -> declined insufficient-funds, balance 20.

        Within the per-txn limit but exceeds balance.  Asserts decline with the
        insufficient-funds reason (NOT over-limit) and an unchanged balance.
        """
        body = _start_snippet(20, per_txn_limit=50) + textwrap.dedent(
            """\
            it('insufficient funds withdrawal is declined, balance unchanged', () => {
              actor.send({ type: 'withdraw', amount: 50 });
              const c = ctxOf(actor);
              expect(c.balance).toBe(20);
              const blob = outcomeBlob(actor);
              expect(blob).toContain('declin');
              expect(blob).toContain('insufficient');
              expect(blob).not.toContain('approv');
            });
            """
        )
        ok, out = _run_scenario("Insufficient", body)
        assert ok, f"insufficient-funds decline scenario failed:\n{out[-3000:]}"

    def test_frozen_blocks_otherwise_valid_withdrawal(self):
        """L2: freeze, then withdraw 10 from balance 20 -> declined frozen, balance unchanged.

        The withdrawal is otherwise valid (within limit and balance).  Freezing
        must decline it with the frozen reason -- a stub ignoring `frozen`
        approves and decrements, and so fails.
        """
        body = _start_snippet(20, per_txn_limit=50) + textwrap.dedent(
            """\
            it('frozen account declines an otherwise valid withdrawal', () => {
              actor.send({ type: 'freeze' });
              expect(ctxOf(actor).frozen).toBe(true);
              expect(ctxOf(actor).balance).toBe(20); // freeze never touches balance
              actor.send({ type: 'withdraw', amount: 10 });
              const c = ctxOf(actor);
              expect(c.balance).toBe(20);
              const blob = outcomeBlob(actor);
              expect(blob).toContain('declin');
              expect(blob).toContain('frozen');
              expect(blob).not.toContain('approv');
            });
            """
        )
        ok, out = _run_scenario("Frozen", body)
        assert ok, f"frozen-declines scenario failed:\n{out[-3000:]}"

    def test_unfreeze_restores_withdrawals(self):
        """L2: after unfreeze a previously-blocked withdrawal succeeds, decrementing balance.

        Continuation of the freeze row: freeze -> declined; unfreeze -> withdraw
        10 from balance 20 -> approved, balance 10.  Verifies freeze/unfreeze
        toggle the boolean and never alter balance themselves.
        """
        body = _start_snippet(20, per_txn_limit=50) + textwrap.dedent(
            """\
            it('unfreeze allows the withdrawal to go through', () => {
              actor.send({ type: 'freeze' });
              actor.send({ type: 'withdraw', amount: 10 });  // declined frozen
              expect(ctxOf(actor).balance).toBe(20);
              actor.send({ type: 'unfreeze' });
              expect(ctxOf(actor).frozen).toBe(false);
              expect(ctxOf(actor).balance).toBe(20);         // unfreeze keeps balance
              actor.send({ type: 'withdraw', amount: 10 });  // now approved
              const c = ctxOf(actor);
              expect(c.balance).toBe(10);
              expect(outcomeBlob(actor)).toContain('approv');
            });
            """
        )
        ok, out = _run_scenario("Unfreeze", body)
        assert ok, f"unfreeze scenario failed:\n{out[-3000:]}"

    def test_decline_priority_frozen_over_limit(self):
        """L2: when frozen AND over-limit, the recorded reason is frozen (highest priority).

        Priority discriminator #1: frozen beats over-limit.  A stub that checks
        limit before the frozen flag records the wrong reason and fails.
        """
        body = _start_snippet(20, frozen=True, per_txn_limit=50) + textwrap.dedent(
            """\
            it('frozen wins over over-limit in the decline reason', () => {
              // amount 60 is both over the limit (50) and the account is frozen.
              actor.send({ type: 'withdraw', amount: 60 });
              const c = ctxOf(actor);
              expect(c.balance).toBe(20);
              const blob = outcomeBlob(actor);
              expect(blob).toContain('declin');
              expect(blob).toContain('frozen');
              // frozen reason wins; the limit reason must not be what's recorded.
              expect(blob).not.toMatch(/over.?limit/);
            });
            """
        )
        ok, out = _run_scenario("PriorityFrozen", body)
        assert ok, f"frozen-priority scenario failed:\n{out[-3000:]}"

    def test_decline_priority_over_limit_beats_insufficient(self):
        """L2: not frozen, amount over limit AND over balance -> reason is over-limit.

        Priority discriminator #2: over-limit beats insufficient-funds.  Balance
        10, limit 50, withdraw 80: exceeds both, but the recorded reason must be
        over-limit (higher priority than insufficient-funds).
        """
        body = _start_snippet(10, per_txn_limit=50) + textwrap.dedent(
            """\
            it('over-limit wins over insufficient-funds in the decline reason', () => {
              actor.send({ type: 'withdraw', amount: 80 });
              const c = ctxOf(actor);
              expect(c.balance).toBe(10);
              const blob = outcomeBlob(actor);
              expect(blob).toContain('declin');
              expect(blob).toMatch(/over.?limit|limit/);
              expect(blob).not.toContain('insufficient');
            });
            """
        )
        ok, out = _run_scenario("PriorityOverLimit", body)
        assert ok, f"over-limit-priority scenario failed:\n{out[-3000:]}"

    def test_amount_read_from_event_not_stashed(self):
        """L2: two different withdraw amounts in a row are each honored from their own event.

        The doc forbids stashing a pending amount and reading it later.  We send
        withdraw 10 then withdraw 25 from balance 100; the balance must reflect
        BOTH distinct amounts (100 -> 90 -> 65).  A machine that stashes the
        first amount and reuses it would produce 80, not 65.
        """
        body = _start_snippet(100, per_txn_limit=50) + textwrap.dedent(
            """\
            it('each withdrawal uses the amount from its own event', () => {
              actor.send({ type: 'withdraw', amount: 10 });
              expect(ctxOf(actor).balance).toBe(90);
              actor.send({ type: 'withdraw', amount: 25 });
              expect(ctxOf(actor).balance).toBe(65);
              expect(outcomeBlob(actor)).toContain('approv');
            });
            """
        )
        ok, out = _run_scenario("AmountFromEvent", body)
        assert ok, f"amount-from-event scenario failed:\n{out[-3000:]}"

    def test_returns_to_ready_and_accepts_next_event(self):
        """L2: the machine returns to the finite **ready** phase and accepts the next event.

        After a withdrawal (approved or declined) the machine must be back in a
        finite state that can process another event.  We exercise a sequence and
        confirm a later event still mutates context, and the snapshot value names
        the `ready` phase.  A machine stuck in a transient evaluation state would
        ignore the follow-up event.
        """
        body = _start_snippet(100, per_txn_limit=50) + textwrap.dedent(
            """\
            it('returns to ready and processes subsequent events', () => {
              actor.send({ type: 'withdraw', amount: 200 }); // declined over-limit
              expect(ctxOf(actor).balance).toBe(100);
              // snapshot must indicate a stable finite phase named "ready".
              const v = JSON.stringify(actor.getSnapshot().value).toLowerCase();
              expect(v).toContain('ready');
              // a follow-up valid withdrawal must still be honored.
              actor.send({ type: 'withdraw', amount: 40 });
              expect(ctxOf(actor).balance).toBe(60);
              expect(outcomeBlob(actor)).toContain('approv');
              // and a freeze afterwards must take effect.
              actor.send({ type: 'freeze' });
              expect(ctxOf(actor).frozen).toBe(true);
            });
            """
        )
        ok, out = _run_scenario("ReadyPhase", body)
        assert ok, f"ready-phase scenario failed:\n{out[-3000:]}"

    def test_agent_spec_passes_native_command(self):
        """L2: the agent's own deterministic spec passes via the exact Acceptance command.

        Runs `pnpm vitest run --project xstate packages/core/test/withdrawalGuard.test.ts`
        from the repo root and requires a clean pass with at least one test.
        """
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        proc = _vitest(AGENT_SPEC, timeout=600)
        ok, out = _passed(proc)
        assert ok, f"agent's withdrawalGuard.test.ts did not pass:\n{out[-4000:]}"
        assert ("passed" in out.lower()) or ("✓" in out), (
            f"agent spec produced no passing tests:\n{out[-2000:]}"
        )
