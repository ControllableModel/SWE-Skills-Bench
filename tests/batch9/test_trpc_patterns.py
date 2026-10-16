"""Tests for the `trpc-patterns` skill task (variant ext9).

Task: Build a Payments Router with a Custom Error Formatter for the tRPC suite.

The agent must create two files inside the tRPC monorepo:
  * packages/tests/server/payments.ts       -- in-memory ledger + tRPC instance
                                                configured with a CUSTOM error
                                                formatter, the payments router,
                                                a fresh-ledger factory and an
                                                exported caller factory.
  * packages/tests/server/payments.test.ts  -- a deterministic vitest suite
                                                driving the API through callers.

The router exposes a `payments` sub-router with:
  * balance(  { accountId } )                 -> { accountId, balanceCents }
  * transfer( { fromId, toId, amountCents } ) -> { fromBalanceCents, toBalanceCents }
  * freeze(   { accountId } )                 -> { frozen: true }

Domain failures map to distinguishable tRPC error CODES and to a domain
`data` category produced by the custom error formatter (e.g.
"insufficient_funds", "account_frozen", "validation").

Verification strategy
=====================

L1  -- the deliverable files exist, are non-trivial real source, are built on
       the repo's `@trpc/server` primitives (initTRPC + a custom errorFormatter),
       export a public surface, and the test file consumes only that surface.

L2  -- DYNAMIC EXECUTION via the repo's native toolchain (`pnpm vitest run`):
       * The agent's own acceptance suite must pass, contain >= 12 cases, and
         genuinely assert on tRPC error *codes* (NOT_FOUND / FORBIDDEN /
         BAD_REQUEST / PRECONDITION_FAILED) plus the formatter's domain
         category field.
       * An INDEPENDENT vitest driver, written by THIS test into the repo,
         imports the agent's public caller + ledger factories by INTROSPECTION
         (their export names are not fixed by the task) and exercises the real
         behaviour directly:
           - a valid transfer moves funds and preserves the two-account total;
           - an over-balance transfer fails with insufficient-funds semantics
             and mutates NOTHING (atomicity);
           - a transfer from a frozen source fails with a forbidden-style code
             and mutates nothing;
           - same-account / zero / negative / fractional amounts fail as
             validation (BAD_REQUEST) before any mutation;
           - unknown accounts fail as NOT_FOUND;
           - the surfaced error exposes a domain `data` category and never
             leaks raw ledger contents.
       A naive implementation that hardcodes balances, skips a check, mutates
       before validating, conflates the failure categories, or omits the
       formatter cannot pass.
"""

import os
import re
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/trpc"
SERVER_DIR = os.path.join(REPO_DIR, "packages", "tests", "server")
PAYMENTS_TS = os.path.join(SERVER_DIR, "payments.ts")
PAYMENTS_TEST_TS = os.path.join(SERVER_DIR, "payments.test.ts")

VITEST_TIMEOUT = 600


# --------------------------------------------------------------------------- #
# dependency / toolchain preparation
# --------------------------------------------------------------------------- #
def _have_node_modules():
    """The container ships the repo toolchain installed; detect it."""
    return os.path.isdir(os.path.join(REPO_DIR, "node_modules")) and (
        os.path.isdir(os.path.join(REPO_DIR, "packages", "tests", "node_modules"))
        or os.path.exists(os.path.join(REPO_DIR, "node_modules", ".bin", "vitest"))
        or os.path.isdir(os.path.join(REPO_DIR, "node_modules", "vitest"))
    )


@pytest.fixture(scope="module", autouse=True)
def _prepare_deps():
    """Best-effort: install workspace deps with pnpm if they are missing.

    In the benchmark container the toolchain is pre-installed, so this is
    usually a no-op. If node_modules is absent we attempt a pnpm install.
    """
    if not _have_node_modules():
        for cmd in (
            ["pnpm", "install", "--frozen-lockfile", "--prefer-offline"],
            ["pnpm", "install", "--prefer-offline"],
        ):
            try:
                res = subprocess.run(
                    cmd,
                    cwd=REPO_DIR,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )
                if res.returncode == 0:
                    break
            except Exception:
                continue
    yield


def _run_vitest(rel_file):
    """Run `pnpm vitest run <rel_file>` from the repo root."""
    cmd = ["pnpm", "vitest", "run", rel_file]
    return subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=VITEST_TIMEOUT,
    )


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _write_driver(name, body):
    """Write an independent vitest driver next to the deliverables and return
    the repo-relative path used to invoke vitest."""
    path = os.path.join(SERVER_DIR, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return os.path.relpath(path, REPO_DIR)


def _cleanup(rel_file):
    abs_path = os.path.join(REPO_DIR, rel_file)
    try:
        os.remove(abs_path)
    except OSError:
        pass


class TestTrpcPatterns:
    REPO_DIR = "/workspace/trpc"

    # ------------------------------------------------------------------ #
    # L1 -- deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_payments_module_exists(self):
        """L1: payments.ts deliverable exists and is non-trivial source."""
        assert os.path.isfile(PAYMENTS_TS), f"missing {PAYMENTS_TS}"
        src = _read(PAYMENTS_TS)
        assert len(src.strip()) > 300, "payments.ts is suspiciously small"

    def test_payments_test_exists(self):
        """L1: payments.test.ts deliverable exists and is non-trivial."""
        assert os.path.isfile(PAYMENTS_TEST_TS), f"missing {PAYMENTS_TEST_TS}"
        src = _read(PAYMENTS_TEST_TS)
        assert len(src.strip()) > 300, "payments.test.ts is suspiciously small"

    def test_module_uses_trpc_with_custom_formatter(self):
        """L1: implementation is built on @trpc/server (initTRPC) with a CUSTOM
        error formatter and exports a public surface (so the test file can
        import a caller factory)."""
        src = _read(PAYMENTS_TS)
        assert "@trpc/server" in src, "payments.ts must use @trpc/server"
        assert "initTRPC" in src, "payments.ts must initialize tRPC via initTRPC"
        assert "errorFormatter" in src, (
            "payments.ts must configure a custom errorFormatter on initTRPC"
        )
        assert "export" in src, "payments.ts must export a public surface"
        # The router type / nested 'payments' sub-router is part of the contract.
        assert "payments" in src, "payments.ts must expose a 'payments' sub-router"
        assert "Router" in src or "router" in src

    def test_test_file_imports_only_public_surface(self):
        """L1: the test file imports from the payments module rather than
        re-implementing the router/formatter inline."""
        src = _read(PAYMENTS_TEST_TS)
        assert (
            "./payments" in src or "payments'" in src or 'payments"' in src
        ), "payments.test.ts must import from ./payments"
        # It must NOT itself stand up a parallel tRPC instance / formatter.
        assert "initTRPC" not in src, (
            "test file must import the caller factory, not re-init tRPC"
        )

    # ------------------------------------------------------------------ #
    # L2 -- the agent's acceptance suite passes
    # ------------------------------------------------------------------ #
    def test_acceptance_suite_passes(self):
        """L2: the exact Acceptance-Criteria command passes with all green.

        `pnpm vitest run packages/tests/server/payments.test.ts`
        """
        rel = os.path.relpath(PAYMENTS_TEST_TS, REPO_DIR)
        res = _run_vitest(rel)
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        assert res.returncode == 0, (
            "payments.test.ts must pass.\n"
            f"stdout tail:\n{(res.stdout or '')[-3000:]}\n"
            f"stderr tail:\n{(res.stderr or '')[-2000:]}"
        )
        assert "no test" not in combined.lower(), (
            "vitest reported no tests were collected"
        )

    def test_acceptance_suite_has_enough_cases(self):
        """L2: the acceptance suite actually contains >= 12 passing cases as
        required by the doc, proven by running it and parsing the summary."""
        rel = os.path.relpath(PAYMENTS_TEST_TS, REPO_DIR)
        res = _run_vitest(rel)
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        passed = 0
        m = re.search(r"Tests\s+(\d+)\s+passed", combined)
        if m:
            passed = int(m.group(1))
        else:
            passed = combined.count("✓")
        assert passed >= 12, (
            f"acceptance suite must have >= 12 passing cases, saw {passed}.\n"
            f"output tail:\n{combined[-2500:]}"
        )

    def test_acceptance_suite_asserts_on_codes_and_category(self):
        """L2: the acceptance test asserts on tRPC error *codes* for the
        required failure categories AND on the formatter's domain category,
        not on message substrings."""
        src = _read(PAYMENTS_TEST_TS)
        # Validation failures surface as BAD_REQUEST; unknown accounts NOT_FOUND.
        assert "BAD_REQUEST" in src, (
            "acceptance suite must assert validation -> BAD_REQUEST code"
        )
        assert "NOT_FOUND" in src, (
            "acceptance suite must assert unknown account -> NOT_FOUND code"
        )
        # A frozen source is a forbidden-style failure; an over-balance transfer
        # is a bad-request / precondition failure. Require at least one of the
        # forbidden-style codes and one of the precondition-style codes.
        assert "FORBIDDEN" in src, (
            "acceptance suite must assert the frozen-account FORBIDDEN code"
        )
        assert ("PRECONDITION_FAILED" in src) or ("BAD_REQUEST" in src), (
            "acceptance suite must assert the insufficient-funds code"
        )
        # Domain category field surfaced by the formatter.
        assert "insufficient_funds" in src, (
            "acceptance suite must assert the 'insufficient_funds' domain category"
        )
        assert "account_frozen" in src, (
            "acceptance suite must assert the 'account_frozen' domain category"
        )

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: happy-path transfer preserves the total
    # ------------------------------------------------------------------ #
    def test_independent_transfer_moves_funds_and_preserves_total(self):
        """L2 (independent): a valid transfer debits the source, credits the
        destination by the same amount, and leaves the two-account TOTAL
        unchanged. This imports the agent's caller + ledger factories by
        introspection and does not trust the agent's own tests.

        A stub that hardcodes return balances, ignores `amountCents`, or only
        mutates one side cannot satisfy both the per-account deltas and the
        conserved total simultaneously.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import {
              makeLedger, makeCaller, seedAccounts, accountIds,
            } from './__pay_helpers';

            test('valid transfer moves funds and conserves the total', async () => {
              const ledger = makeLedger();
              const [a, b] = seedAccounts(ledger, [
                { id: 'acc-a', balanceCents: 1000 },
                { id: 'acc-b', balanceCents: 250 },
              ]);
              const caller = makeCaller(ledger);

              const before = await Promise.all([
                caller.payments.balance({ accountId: a }),
                caller.payments.balance({ accountId: b }),
              ]);
              const totalBefore = before[0].balanceCents + before[1].balanceCents;

              const res = await caller.payments.transfer({
                fromId: a, toId: b, amountCents: 300,
              });
              expect(typeof res.fromBalanceCents).toBe('number');
              expect(typeof res.toBalanceCents).toBe('number');
              expect(res.fromBalanceCents).toBe(700);
              expect(res.toBalanceCents).toBe(550);

              const after = await Promise.all([
                caller.payments.balance({ accountId: a }),
                caller.payments.balance({ accountId: b }),
              ]);
              expect(after[0].balanceCents).toBe(700);
              expect(after[1].balanceCents).toBe(550);
              const totalAfter = after[0].balanceCents + after[1].balanceCents;
              expect(totalAfter).toBe(totalBefore);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_transfer_ok", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: insufficient funds -> fail + atomicity
    # ------------------------------------------------------------------ #
    def test_independent_insufficient_funds_is_atomic(self):
        """L2 (independent): a transfer exceeding the source balance fails, the
        surfaced error carries the 'insufficient_funds' domain category with a
        bad-request/precondition code, and NEITHER balance changes (atomicity).

        An implementation that debits before checking the balance, or that
        conflates this with validation, will fail either the code/category
        assertion or the no-mutation assertion.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import {
              makeLedger, makeCaller, seedAccounts, errInfo,
            } from './__pay_helpers';

            test('over-balance transfer fails as insufficient_funds, no mutation', async () => {
              const ledger = makeLedger();
              const [a, b] = seedAccounts(ledger, [
                { id: 'acc-a', balanceCents: 100 },
                { id: 'acc-b', balanceCents: 0 },
              ]);
              const caller = makeCaller(ledger);

              const info = await errInfo(
                caller.payments.transfer({ fromId: a, toId: b, amountCents: 500 }),
              );
              expect(info.threw).toBe(true);
              expect(['BAD_REQUEST', 'PRECONDITION_FAILED']).toContain(info.code);
              expect(info.category).toBe('insufficient_funds');

              // Atomicity: nothing moved.
              const ba = await caller.payments.balance({ accountId: a });
              const bb = await caller.payments.balance({ accountId: b });
              expect(ba.balanceCents).toBe(100);
              expect(bb.balanceCents).toBe(0);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_insufficient", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: frozen source rejected (forbidden) + atomic
    # ------------------------------------------------------------------ #
    def test_independent_frozen_source_rejected(self):
        """L2 (independent): freezing the source then transferring from it fails
        with the 'account_frozen' domain category and a forbidden-style code,
        and leaves both balances untouched. This also proves `freeze` actually
        flips state (a no-op freeze would let the transfer succeed).
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import {
              makeLedger, makeCaller, seedAccounts, errInfo,
            } from './__pay_helpers';

            test('transfer from frozen source -> account_frozen, no mutation', async () => {
              const ledger = makeLedger();
              const [a, b] = seedAccounts(ledger, [
                { id: 'acc-a', balanceCents: 800 },
                { id: 'acc-b', balanceCents: 50 },
              ]);
              const caller = makeCaller(ledger);

              const fr = await caller.payments.freeze({ accountId: a });
              expect(fr.frozen).toBe(true);

              const info = await errInfo(
                caller.payments.transfer({ fromId: a, toId: b, amountCents: 100 }),
              );
              expect(info.threw).toBe(true);
              expect(info.code).toBe('FORBIDDEN');
              expect(info.category).toBe('account_frozen');

              const ba = await caller.payments.balance({ accountId: a });
              const bb = await caller.payments.balance({ accountId: b });
              expect(ba.balanceCents).toBe(800);
              expect(bb.balanceCents).toBe(50);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_frozen", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: validation failures (BAD_REQUEST), atomic
    # ------------------------------------------------------------------ #
    def test_independent_validation_failures(self):
        """L2 (independent): same-account, zero, negative and fractional amounts
        are each a validation failure (BAD_REQUEST) and mutate nothing.

        Validation must run before funds move, so each rejected call leaves the
        source balance exactly as seeded. A stub that only checks the balance
        and not the amount would let amountCents=0 'succeed' and fail here.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import {
              makeLedger, makeCaller, seedAccounts, errInfo,
            } from './__pay_helpers';

            function fresh() {
              const ledger = makeLedger();
              const [a, b] = seedAccounts(ledger, [
                { id: 'acc-a', balanceCents: 1000 },
                { id: 'acc-b', balanceCents: 1000 },
              ]);
              return { caller: makeCaller(ledger), a, b };
            }

            const badAmounts = [0, -5, 3.5];
            for (const amt of badAmounts) {
              test('amountCents=' + amt + ' -> validation BAD_REQUEST, no mutation', async () => {
                const { caller, a, b } = fresh();
                const info = await errInfo(
                  caller.payments.transfer({ fromId: a, toId: b, amountCents: amt }),
                );
                expect(info.threw).toBe(true);
                expect(info.code).toBe('BAD_REQUEST');
                const ba = await caller.payments.balance({ accountId: a });
                expect(ba.balanceCents).toBe(1000);
              });
            }

            test('same-account transfer -> validation BAD_REQUEST, no mutation', async () => {
              const { caller, a } = fresh();
              const info = await errInfo(
                caller.payments.transfer({ fromId: a, toId: a, amountCents: 10 }),
              );
              expect(info.threw).toBe(true);
              expect(info.code).toBe('BAD_REQUEST');
              const ba = await caller.payments.balance({ accountId: a });
              expect(ba.balanceCents).toBe(1000);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_validation", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: unknown accounts -> NOT_FOUND
    # ------------------------------------------------------------------ #
    def test_independent_unknown_accounts_not_found(self):
        """L2 (independent): `balance` and `transfer` against an unknown account
        fail with NOT_FOUND, and the unknown side never causes a partial
        mutation of the known side.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import {
              makeLedger, makeCaller, seedAccounts, errInfo,
            } from './__pay_helpers';

            test('balance of unknown account -> NOT_FOUND', async () => {
              const ledger = makeLedger();
              seedAccounts(ledger, [{ id: 'acc-a', balanceCents: 500 }]);
              const caller = makeCaller(ledger);
              const info = await errInfo(
                caller.payments.balance({ accountId: 'nope' }),
              );
              expect(info.threw).toBe(true);
              expect(info.code).toBe('NOT_FOUND');
            });

            test('transfer to unknown toId -> NOT_FOUND, source unchanged', async () => {
              const ledger = makeLedger();
              const [a] = seedAccounts(ledger, [{ id: 'acc-a', balanceCents: 500 }]);
              const caller = makeCaller(ledger);
              const info = await errInfo(
                caller.payments.transfer({ fromId: a, toId: 'ghost', amountCents: 100 }),
              );
              expect(info.threw).toBe(true);
              expect(info.code).toBe('NOT_FOUND');
              const ba = await caller.payments.balance({ accountId: a });
              expect(ba.balanceCents).toBe(500);
            });

            test('transfer from unknown fromId -> NOT_FOUND', async () => {
              const ledger = makeLedger();
              const [a] = seedAccounts(ledger, [{ id: 'acc-a', balanceCents: 500 }]);
              const caller = makeCaller(ledger);
              const info = await errInfo(
                caller.payments.transfer({ fromId: 'ghost', toId: a, amountCents: 100 }),
              );
              expect(info.threw).toBe(true);
              expect(info.code).toBe('NOT_FOUND');
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_not_found", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: distinct categories + no ledger leakage
    # ------------------------------------------------------------------ #
    def test_independent_categories_distinct_and_no_leak(self):
        """L2 (independent): the surfaced domain categories for the three
        failure families are DISTINCT (validation vs account_frozen vs
        insufficient_funds), proving the formatter does not conflate them, and
        the surfaced error payload never leaks raw ledger internals (account
        objects, balanceCents of OTHER accounts, the ledger array, etc.).
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import {
              makeLedger, makeCaller, seedAccounts, errInfo,
            } from './__pay_helpers';

            test('the three failure categories are mutually distinct', async () => {
              // insufficient_funds
              {
                const ledger = makeLedger();
                const [a, b] = seedAccounts(ledger, [
                  { id: 'a', balanceCents: 10 }, { id: 'b', balanceCents: 0 },
                ]);
                const caller = makeCaller(ledger);
                const info = await errInfo(
                  caller.payments.transfer({ fromId: a, toId: b, amountCents: 9999 }),
                );
                expect(info.category).toBe('insufficient_funds');
              }
              // account_frozen
              let frozenCat: string | undefined;
              {
                const ledger = makeLedger();
                const [a, b] = seedAccounts(ledger, [
                  { id: 'a', balanceCents: 1000 }, { id: 'b', balanceCents: 0 },
                ]);
                const caller = makeCaller(ledger);
                await caller.payments.freeze({ accountId: a });
                const info = await errInfo(
                  caller.payments.transfer({ fromId: a, toId: b, amountCents: 10 }),
                );
                frozenCat = info.category;
                expect(info.category).toBe('account_frozen');
              }
              // validation
              let valCat: string | undefined;
              {
                const ledger = makeLedger();
                const [a, b] = seedAccounts(ledger, [
                  { id: 'a', balanceCents: 1000 }, { id: 'b', balanceCents: 0 },
                ]);
                const caller = makeCaller(ledger);
                const info = await errInfo(
                  caller.payments.transfer({ fromId: a, toId: b, amountCents: 0 }),
                );
                valCat = info.category;
              }
              // all three are defined and pairwise different
              const cats = new Set(['insufficient_funds', frozenCat, valCat]);
              expect(cats.size).toBe(3);
            });

            test('surfaced error never leaks raw ledger contents', async () => {
              const ledger = makeLedger();
              const [a, b] = seedAccounts(ledger, [
                { id: 'a', balanceCents: 4242 }, { id: 'b', balanceCents: 7331 },
              ]);
              const caller = makeCaller(ledger);
              const info = await errInfo(
                caller.payments.transfer({ fromId: a, toId: b, amountCents: 999999 }),
              );
              const blob = JSON.stringify(info.data ?? {});
              // The OTHER account's secret balance must not appear in the
              // surfaced domain payload, nor any internal array/object dump.
              expect(blob.includes('7331')).toBe(false);
              expect(blob.includes('balanceCents')).toBe(false);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_categories", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: fresh ledger per call (isolation)
    # ------------------------------------------------------------------ #
    def test_independent_ledger_factory_isolation(self):
        """L2 (independent): the ledger factory yields a FRESH, isolated ledger
        each call -- a transfer applied through a caller bound to ledger A is
        invisible to a caller bound to an independent ledger B. This rules out a
        leaked global mutable singleton.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import {
              makeLedger, makeCaller, seedAccounts,
            } from './__pay_helpers';

            test('mutations on ledger A do not leak into a fresh ledger B', async () => {
              const ledgerA = makeLedger();
              const [a1, b1] = seedAccounts(ledgerA, [
                { id: 'a', balanceCents: 1000 }, { id: 'b', balanceCents: 0 },
              ]);
              const ledgerB = makeLedger();
              const [a2] = seedAccounts(ledgerB, [
                { id: 'a', balanceCents: 1000 }, { id: 'b', balanceCents: 0 },
              ]);

              const callerA = makeCaller(ledgerA);
              await callerA.payments.transfer({ fromId: a1, toId: b1, amountCents: 400 });

              const callerB = makeCaller(ledgerB);
              const bA = await callerA.payments.balance({ accountId: a1 });
              const bB = await callerB.payments.balance({ accountId: a2 });
              expect(bA.balanceCents).toBe(600);
              expect(bB.balanceCents).toBe(1000);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_isolation", driver)

    # ------------------------------------------------------------------ #
    # helper bridge (introspection) + independent driver runner
    # ------------------------------------------------------------------ #
    _HELPERS_TS = textwrap.dedent(
        r"""
        /* Independent test bridge for the payments task. Locates the agent's
           public ledger factory and caller factory exported from payments.ts by
           introspection, because the task does not fix their export names. It
           also normalises how a caller is created and how account seeding is
           performed across plausible implementation shapes. */
        import * as M from './payments';

        type AnyFn = (...args: any[]) => any;

        function exportedFns(): Array<[string, AnyFn]> {
          return Object.entries(M as Record<string, unknown>)
            .filter(([, v]) => typeof v === 'function')
            .map(([k, v]) => [k, v as AnyFn]);
        }

        function looksLikeCaller(o: any): boolean {
          return !!o && typeof o === 'object' && 'payments' in o;
        }

        /** Build a fresh, isolated ledger using the module's ledger factory. */
        export function makeLedger(): any {
          const fns = exportedFns();
          const named =
            fns.find(([k]) => /(ledger|accounts?|store|db|data)/i.test(k) &&
                              /(create|make|new|factory|init|fresh)/i.test(k)) ||
            fns.find(([k]) => /ledger/i.test(k)) ||
            null;
          if (named) {
            try {
              const out = named[1]();
              if (out !== undefined && out !== null) return out;
            } catch { /* fall through */ }
          }
          // Fallback: a zero-arg factory whose result is not a caller.
          for (const [, fn] of fns) {
            try {
              const out = fn();
              if (out && typeof out === 'object' &&
                  typeof out.then !== 'function' && !looksLikeCaller(out)) {
                return out;
              }
            } catch { /* ignore */ }
          }
          throw new Error('Could not locate a ledger factory exported from payments.ts');
        }

        function callerFactory(): AnyFn {
          const fns = exportedFns();
          const named =
            fns.find(([k]) => /caller/i.test(k)) ||
            fns.find(([k]) => /(create|make).*call/i.test(k));
          if (named) return named[1];
          throw new Error('Could not locate a caller factory exported from payments.ts');
        }

        /** Invoke the caller factory tolerating several context shapes. */
        export function makeCaller(ledger: any): any {
          const factory = callerFactory();
          const attempts: Array<() => any> = [
            () => factory(ledger),
            () => factory({ ledger }),
            () => factory({ ctx: { ledger } }),
            () => factory({ db: ledger }),
            () => factory({ data: ledger }),
            () => factory({ accounts: ledger }),
            () => factory({ ctx: { db: ledger } }),
          ];
          let lastErr: unknown;
          for (const attempt of attempts) {
            try {
              const caller = attempt();
              if (looksLikeCaller(caller)) return caller;
              if (caller && typeof caller === 'object') return caller;
            } catch (e) {
              lastErr = e;
            }
          }
          throw new Error(
            'Could not invoke caller factory with a ledger in any known shape: ' +
              String(lastErr),
          );
        }

        type Seed = { id: string; balanceCents: number };

        /** Seed accounts into a ledger across plausible representations
            (Map, plain object keyed by id, or array of account records) and
            return the seeded ids in order. */
        export function seedAccounts(ledger: any, seeds: Seed[]): string[] {
          for (const s of seeds) {
            const account = { id: s.id, balanceCents: s.balanceCents, frozen: false };
            if (ledger instanceof Map) {
              ledger.set(s.id, account);
            } else if (Array.isArray(ledger)) {
              ledger.push(account);
            } else if (ledger && typeof ledger === 'object') {
              // Common container fields, else key directly by id.
              const inner =
                (ledger.accounts instanceof Map && ledger.accounts) ||
                (Array.isArray(ledger.accounts) && ledger.accounts) ||
                null;
              if (inner instanceof Map) {
                inner.set(s.id, account);
              } else if (Array.isArray(inner)) {
                inner.push(account);
              } else if (ledger.accounts && typeof ledger.accounts === 'object') {
                ledger.accounts[s.id] = account;
              } else {
                ledger[s.id] = account;
              }
            } else {
              throw new Error('Unsupported ledger shape for seeding');
            }
          }
          return seeds.map((s) => s.id);
        }

        export function accountIds(seeds: Seed[]): string[] {
          return seeds.map((s) => s.id);
        }

        /** Run a procedure call and extract code + domain category robustly. */
        export async function errInfo(p: Promise<unknown>): Promise<{
          threw: boolean; code?: string; category?: string; data?: any;
        }> {
          try {
            await p;
            return { threw: false };
          } catch (err: any) {
            const code = err?.code ?? err?.cause?.code;
            // The domain category may surface on the formatted shape's data, on
            // the error's own data, or via the original error metadata/cause.
            const data =
              err?.data ??
              err?.shape?.data ??
              err?.cause?.data ??
              undefined;
            const category =
              data?.category ??
              data?.domain ??
              data?.kind ??
              err?.category ??
              err?.cause?.category ??
              undefined;
            return { threw: true, code, category, data };
          }
        }
        """
    ).lstrip()

    def _run_independent_driver(self, slug, driver_body):
        helpers_rel = _write_driver("__pay_helpers.ts", self._HELPERS_TS)
        driver_rel = _write_driver(f"{slug}.indep.test.ts", driver_body)
        try:
            res = _run_vitest(driver_rel)
            combined = (res.stdout or "") + "\n" + (res.stderr or "")
            assert res.returncode == 0, (
                f"independent driver '{slug}' failed.\n"
                f"stdout tail:\n{(res.stdout or '')[-3000:]}\n"
                f"stderr tail:\n{(res.stderr or '')[-2000:]}"
            )
            assert "no test" not in combined.lower(), (
                f"independent driver '{slug}' collected no tests:\n{combined[-1500:]}"
            )
        finally:
            _cleanup(driver_rel)
            _cleanup(helpers_rel)
