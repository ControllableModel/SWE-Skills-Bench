"""
Test for the 'sequelize-orm' skill (variant ext6) — Atomic Funds-Transfer.

The agent must create two files inside @sequelize/core's INTEGRATION-test tree:
  - packages/core/test/integration/wallet-transfer.ts       (the domain module)
  - packages/core/test/integration/wallet-transfer.test.ts  (its integration test)

The module exports:
  - setupWallet(sequelize)  -> defines and returns { Wallet, Ledger } and
                               creates their tables (sync) so the operation runs.
  - transferFunds(sequelize, fromId, toId, amount) -> moves `amount` from the
                               source wallet to the destination wallet as ONE
                               atomic unit of work: decrement source balance,
                               increment destination balance, and append two
                               Ledger rows (delta = -amount and delta = +amount).

The transfer must REJECT and leave ALL data unchanged when:
  - amount is not strictly positive (0 or negative),
  - the source wallet would go negative (insufficient balance),
  - either wallet id does not exist.

Verification strategy
---------------------
L1 cases check that the deliverable files exist and are minimally well-formed
(both files present, module exports setupWallet/transferFunds, the agent test
imports the module).

L2 cases DO NOT trust the agent's own test file. Instead we drop our OWN
independent mocha specs into packages/core/test/integration/ that *import the
agent's wallet-transfer module* and exercise the real behaviour against the
default in-process test database:

  * a successful transfer mutates BOTH balances and appends EXACTLY the two
    expected Ledger rows (deltas -amount / +amount) and nothing else;
  * each failure mode (non-positive amount, insufficient funds, unknown source,
    unknown destination) throws AND leaves both balances and the ledger count
    byte-for-byte identical to the pre-call state (atomic rollback);
  * a naive non-atomic implementation that performs partial writes before
    throwing is detected because we re-read persisted state from the DB after
    the rejection and assert no partial mutation survived.

Specs are run via the repository's native command from packages/core:

    yarn mocha "test/integration/<spec>.test.ts"

The agent's own acceptance command is also driven directly:

    yarn mocha "test/integration/wallet-transfer.test.ts"
"""

import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/sequelize"
CORE_DIR = os.path.join(REPO_DIR, "packages", "core")
INT_DIR = os.path.join(CORE_DIR, "test", "integration")
MODULE_FILE = os.path.join(INT_DIR, "wallet-transfer.ts")
AGENT_TEST_FILE = os.path.join(INT_DIR, "wallet-transfer.test.ts")

# Basename for the independent specs we drop into the integration dir.
_BENCH_BASENAME = "zzz-bench-wallet-transfer"


def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _run_mocha(spec_rel_path, timeout=900):
    """Run one mocha spec from packages/core using the repo's native command."""
    cmd = ["yarn", "mocha", spec_rel_path]
    return subprocess.run(
        cmd,
        cwd=CORE_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _write_spec_and_run(spec_name, spec_body, timeout=900):
    """
    Write a self-contained mocha .test.ts spec into the integration dir, run it,
    then clean it up. Returns the CompletedProcess.
    """
    spec_path = os.path.join(INT_DIR, spec_name)
    rel_path = os.path.join("test", "integration", spec_name)
    with open(spec_path, "w", encoding="utf-8") as fh:
        fh.write(spec_body)
    try:
        return _run_mocha(rel_path, timeout=timeout)
    finally:
        try:
            os.remove(spec_path)
        except OSError:
            pass


def _assert_mocha_passed(result, context=""):
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    assert result.returncode == 0, (
        f"mocha spec failed ({context}).\n"
        f"returncode={result.returncode}\n"
        f"--- stdout (tail) ---\n{(result.stdout or '')[-6000:]}\n"
        f"--- stderr (tail) ---\n{(result.stderr or '')[-3000:]}"
    )
    # Guard against a silent zero-test run being treated as success.
    assert "0 passing" not in combined, (
        f"mocha reported 0 passing tests ({context}); the spec did not run.\n"
        f"{combined[-4000:]}"
    )


# Common TS preamble used by every independent spec. It builds a fresh wallet
# domain on the default integration test database, exposes helpers that re-read
# persisted state from the DB (NOT cached in-memory instances) so partial /
# non-atomic writes are detectable, and a helper to capture full state.
_PREAMBLE = textwrap.dedent(
    """\
    import { expect } from 'chai';
    import { createSequelizeInstance } from '../support';
    import { setupWallet, transferFunds } from './wallet-transfer';

    async function buildWallets(balA: number, balB: number) {
      const sequelize = createSequelizeInstance();
      const models = setupWallet(sequelize as any);
      expect(models, 'setupWallet must return { Wallet, Ledger }').to.exist;
      const { Wallet, Ledger } = models as any;
      expect(Wallet, 'Wallet model missing').to.exist;
      expect(Ledger, 'Ledger model missing').to.exist;
      // In case setupWallet did not (re)create tables, make sure they exist.
      await sequelize.sync({ force: true });
      const a = await Wallet.create({ owner: 'A', balance: balA });
      const b = await Wallet.create({ owner: 'B', balance: balB });
      return { sequelize, Wallet, Ledger, aId: a.id, bId: b.id };
    }

    // Re-read balance straight from the DB by primary key.
    async function dbBalance(Wallet: any, id: number): Promise<number> {
      const row = await Wallet.findByPk(id);
      expect(row, 'wallet row vanished from DB: ' + id).to.exist;
      return Number(row.balance);
    }

    async function ledgerCount(Ledger: any): Promise<number> {
      return Number(await Ledger.count());
    }

    // Capture a full snapshot of mutable state for rollback assertions.
    async function snapshot(Wallet: any, Ledger: any, aId: number, bId: number) {
      return {
        a: await dbBalance(Wallet, aId),
        b: await dbBalance(Wallet, bId),
        ledgers: await ledgerCount(Ledger),
      };
    }

    async function expectRejects(fn: () => Promise<any>): Promise<any> {
      let err: any;
      try {
        await fn();
      } catch (e) {
        err = e;
      }
      expect(err, 'expected transferFunds to reject but it resolved').to.exist;
      return err;
    }
    """
)


# ---------------------------------------------------------------------------
# Module-scope dependency guard: best-effort ensure node_modules is present so
# the native `yarn mocha` command can resolve mocha/chai/esbuild.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module", autouse=True)
def _ensure_dependencies():
    if not os.path.isdir(os.path.join(REPO_DIR, "node_modules")) and not os.path.isdir(
        os.path.join(CORE_DIR, "node_modules")
    ):
        try:
            subprocess.run(
                ["yarn", "install", "--immutable"],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=1800,
            )
        except Exception:
            pass
    yield


class TestSequelizeOrm:
    """Verify the atomic funds-transfer deliverable (ext6 variant)."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """The domain module wallet-transfer.ts must exist."""
        assert os.path.isfile(MODULE_FILE), f"missing module file: {MODULE_FILE}"

    def test_agent_test_file_exists(self):
        """The agent's own integration test wallet-transfer.test.ts must exist."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing test file: {AGENT_TEST_FILE}"

    def test_module_exports_setup_and_transfer(self):
        """wallet-transfer.ts must export setupWallet and transferFunds symbols."""
        src = _read(MODULE_FILE)
        assert "export" in src, "module does not export anything"
        assert "setupWallet" in src, "setupWallet not found in module"
        assert "transferFunds" in src, "transferFunds not found in module"

    def test_agent_test_imports_module(self):
        """The agent's test must import from the local wallet-transfer module."""
        src = _read(AGENT_TEST_FILE)
        assert "wallet-transfer" in src, "test does not reference the wallet-transfer module"
        assert "transferFunds" in src, "test does not exercise transferFunds"

    # ------------------------------------------------------------------
    # L2 — independent dynamic execution via native `yarn mocha`.
    # Each test drops its own spec, so failures are isolated and specific.
    # ------------------------------------------------------------------

    def test_setup_returns_wallet_and_ledger_models(self):
        """setupWallet returns real, distinct Wallet & Ledger models with the required fields."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('wallet-transfer: setupWallet shape', () => {
              it('returns distinct Wallet/Ledger model classes with the right attributes', async () => {
                const sequelize = createSequelizeInstance();
                const models: any = setupWallet(sequelize as any);
                const { Wallet, Ledger } = models;
                expect(Wallet, 'Wallet missing').to.exist;
                expect(Ledger, 'Ledger missing').to.exist;
                expect(Wallet).to.not.equal(Ledger);
                for (const m of [Wallet, Ledger]) {
                  expect(typeof m.getAttributes, 'not a model class').to.equal('function');
                  expect(typeof m.create, 'not a model class').to.equal('function');
                }
                const wAttrs: any = Wallet.getAttributes();
                expect(wAttrs, 'Wallet has no owner column').to.have.property('owner');
                expect(wAttrs, 'Wallet has no balance column').to.have.property('balance');
                const lAttrs: any = Ledger.getAttributes();
                expect(lAttrs, 'Ledger has no walletId column').to.have.property('walletId');
                expect(lAttrs, 'Ledger has no delta column').to.have.property('delta');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-shape.test.ts", spec)
        _assert_mocha_passed(result, "setupWallet shape")

    def test_wallet_balance_defaults_to_zero(self):
        """A Wallet created with no balance defaults to 0 (persisted)."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('wallet-transfer: balance default', () => {
              it('defaults a freshly created wallet balance to 0', async () => {
                const sequelize = createSequelizeInstance();
                const models: any = setupWallet(sequelize as any);
                const { Wallet } = models;
                await sequelize.sync({ force: true });
                const w = await Wallet.create({ owner: 'Z' });
                // Re-read from DB to ensure the default is actually stored.
                const stored = await Wallet.findByPk(w.id);
                expect(stored, 'wallet not persisted').to.exist;
                expect(Number(stored.balance)).to.equal(0);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-default.test.ts", spec)
        _assert_mocha_passed(result, "wallet balance default 0")

    def test_successful_transfer_mutates_balances_and_ledger(self):
        """A successful transfer of 40 yields A=60, B=40 and exactly two ledger rows -40/+40."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('wallet-transfer: successful transfer', () => {
              it('decrements source, increments destination and appends both ledger rows', async () => {
                const { sequelize, Wallet, Ledger, aId, bId } = await buildWallets(100, 0);
                const before = await snapshot(Wallet, Ledger, aId, bId);
                expect(before).to.deep.equal({ a: 100, b: 0, ledgers: 0 });

                await transferFunds(sequelize as any, aId, bId, 40);

                // Re-read from the DB (not the cached creation instances).
                expect(await dbBalance(Wallet, aId), 'source balance').to.equal(60);
                expect(await dbBalance(Wallet, bId), 'destination balance').to.equal(40);

                // Exactly two ledger rows were appended.
                expect(await ledgerCount(Ledger), 'ledger row count').to.equal(2);

                const rows = await Ledger.findAll();
                const deltas = rows.map((r: any) => Number(r.delta)).sort((x: number, y: number) => x - y);
                expect(deltas, 'ledger deltas must be -40 and +40').to.deep.equal([-40, 40]);

                // The two ledger rows must reference the two wallets correctly.
                const byWallet: Record<string, number> = {};
                for (const r of rows) {
                  byWallet[String(r.walletId)] = Number(r.delta);
                }
                expect(byWallet[String(aId)], 'source ledger delta').to.equal(-40);
                expect(byWallet[String(bId)], 'destination ledger delta').to.equal(40);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-success.test.ts", spec)
        _assert_mocha_passed(result, "successful transfer")

    def test_conservation_of_total_balance(self):
        """A transfer conserves total balance across both wallets (no money created/destroyed)."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('wallet-transfer: conservation', () => {
              it('keeps the sum of balances constant after a successful transfer', async () => {
                const { sequelize, Wallet, Ledger, aId, bId } = await buildWallets(70, 30);
                const totalBefore = (await dbBalance(Wallet, aId)) + (await dbBalance(Wallet, bId));
                await transferFunds(sequelize as any, aId, bId, 25);
                const a = await dbBalance(Wallet, aId);
                const b = await dbBalance(Wallet, bId);
                expect(a, 'A debited').to.equal(45);
                expect(b, 'B credited').to.equal(55);
                expect(a + b, 'total balance conserved').to.equal(totalBefore);
                // Ledger deltas must net to zero.
                const rows = await Ledger.findAll();
                const sum = rows.reduce((acc: number, r: any) => acc + Number(r.delta), 0);
                expect(sum, 'ledger deltas must net to zero').to.equal(0);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-conserve.test.ts", spec)
        _assert_mocha_passed(result, "conservation of total balance")

    def test_non_positive_amount_rejected_no_mutation(self):
        """transferFunds with amount 0 or negative rejects and leaves all state unchanged."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('wallet-transfer: non-positive amount', () => {
              it('rejects amount = 0 and mutates nothing', async () => {
                const { sequelize, Wallet, Ledger, aId, bId } = await buildWallets(100, 0);
                const before = await snapshot(Wallet, Ledger, aId, bId);
                await expectRejects(() => transferFunds(sequelize as any, aId, bId, 0));
                const after = await snapshot(Wallet, Ledger, aId, bId);
                expect(after, 'amount=0 must leave state unchanged').to.deep.equal(before);
              });

              it('rejects a negative amount and mutates nothing', async () => {
                const { sequelize, Wallet, Ledger, aId, bId } = await buildWallets(100, 0);
                const before = await snapshot(Wallet, Ledger, aId, bId);
                await expectRejects(() => transferFunds(sequelize as any, aId, bId, -5));
                const after = await snapshot(Wallet, Ledger, aId, bId);
                expect(after, 'negative amount must leave state unchanged').to.deep.equal(before);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-nonpositive.test.ts", spec)
        _assert_mocha_passed(result, "non-positive amount rejected, no mutation")

    def test_insufficient_funds_rejected_no_mutation(self):
        """Transferring more than the source holds rejects and rolls back atomically."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('wallet-transfer: insufficient funds', () => {
              it('rejects when the source would go negative and leaves all state unchanged', async () => {
                const { sequelize, Wallet, Ledger, aId, bId } = await buildWallets(60, 5);
                const before = await snapshot(Wallet, Ledger, aId, bId);
                expect(before).to.deep.equal({ a: 60, b: 5, ledgers: 0 });

                await expectRejects(() => transferFunds(sequelize as any, aId, bId, 1000));

                // Atomicity: a non-atomic impl that debited A or wrote a ledger row
                // before discovering the shortfall would be caught here.
                const after = await snapshot(Wallet, Ledger, aId, bId);
                expect(after, 'insufficient transfer must roll back fully').to.deep.equal(before);
                expect(after.a, 'source balance untouched').to.equal(60);
                expect(after.b, 'destination balance untouched').to.equal(5);
                expect(after.ledgers, 'no ledger rows added').to.equal(0);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-insufficient.test.ts", spec)
        _assert_mocha_passed(result, "insufficient funds rejected, atomic rollback")

    def test_unknown_destination_rejected_no_mutation(self):
        """Transferring to a non-existent destination rejects and rolls back (source not debited)."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('wallet-transfer: unknown destination', () => {
              it('rejects on an unknown destination id and leaves the source untouched', async () => {
                const { sequelize, Wallet, Ledger, aId, bId } = await buildWallets(100, 0);
                const before = await snapshot(Wallet, Ledger, aId, bId);

                await expectRejects(() => transferFunds(sequelize as any, aId, 99999, 10));

                const after = await snapshot(Wallet, Ledger, aId, bId);
                expect(after, 'unknown destination must roll back fully').to.deep.equal(before);
                expect(after.a, 'source must not be debited').to.equal(100);
                expect(after.ledgers, 'no ledger rows added').to.equal(0);
                // The phantom destination must not have been created.
                expect(await Wallet.findByPk(99999), 'phantom wallet created').to.not.exist;
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-unknowndest.test.ts", spec)
        _assert_mocha_passed(result, "unknown destination rejected, atomic rollback")

    def test_unknown_source_rejected_no_mutation(self):
        """Transferring from a non-existent source rejects and leaves the destination untouched."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('wallet-transfer: unknown source', () => {
              it('rejects on an unknown source id and credits nothing', async () => {
                const { sequelize, Wallet, Ledger, aId, bId } = await buildWallets(0, 50);
                const before = await snapshot(Wallet, Ledger, aId, bId);

                await expectRejects(() => transferFunds(sequelize as any, 88888, bId, 10));

                const after = await snapshot(Wallet, Ledger, aId, bId);
                expect(after, 'unknown source must roll back fully').to.deep.equal(before);
                expect(after.b, 'destination must not be credited').to.equal(50);
                expect(after.ledgers, 'no ledger rows added').to.equal(0);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-unknownsrc.test.ts", spec)
        _assert_mocha_passed(result, "unknown source rejected, atomic rollback")

    def test_recovery_after_failure_then_success(self):
        """After a rejected transfer the domain is still consistent and a valid transfer succeeds."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('wallet-transfer: recovery after failure', () => {
              it('a failed transfer does not corrupt a subsequent valid transfer', async () => {
                const { sequelize, Wallet, Ledger, aId, bId } = await buildWallets(100, 0);

                // First, an invalid transfer that must roll back.
                await expectRejects(() => transferFunds(sequelize as any, aId, bId, 1000));
                let snap = await snapshot(Wallet, Ledger, aId, bId);
                expect(snap, 'state after failed transfer').to.deep.equal({ a: 100, b: 0, ledgers: 0 });

                // Then a valid transfer must work cleanly and produce exactly 2 ledger rows.
                await transferFunds(sequelize as any, aId, bId, 30);
                snap = await snapshot(Wallet, Ledger, aId, bId);
                expect(snap.a, 'source after good transfer').to.equal(70);
                expect(snap.b, 'destination after good transfer').to.equal(30);
                expect(snap.ledgers, 'exactly two ledger rows after one good transfer').to.equal(2);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-recovery.test.ts", spec)
        _assert_mocha_passed(result, "recovery after failure")

    def test_sequential_transfers_accumulate_ledger(self):
        """Two successive successful transfers accumulate four ledger rows and correct balances."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('wallet-transfer: sequential transfers', () => {
              it('accumulates ledger rows and applies each delta exactly once', async () => {
                const { sequelize, Wallet, Ledger, aId, bId } = await buildWallets(100, 0);
                await transferFunds(sequelize as any, aId, bId, 40);
                await transferFunds(sequelize as any, bId, aId, 15);
                expect(await dbBalance(Wallet, aId), 'A after two transfers').to.equal(75);
                expect(await dbBalance(Wallet, bId), 'B after two transfers').to.equal(25);
                expect(await ledgerCount(Ledger), 'four ledger rows total').to.equal(4);
                const rows = await Ledger.findAll();
                const sum = rows.reduce((acc: number, r: any) => acc + Number(r.delta), 0);
                expect(sum, 'all ledger deltas net to zero').to.equal(0);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-sequential.test.ts", spec)
        _assert_mocha_passed(result, "sequential transfers accumulate ledger")

    def test_agent_supplied_test_passes(self):
        """The agent's own acceptance command must pass: yarn mocha wallet-transfer.test.ts."""
        result = _run_mocha(
            os.path.join("test", "integration", "wallet-transfer.test.ts"),
            timeout=900,
        )
        _assert_mocha_passed(result, "agent-supplied wallet-transfer.test.ts")
