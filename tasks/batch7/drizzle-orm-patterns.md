# Task: Build an In-Memory Commission Ledger with Running Balances

## Background

The dub monorepo (`apps/web`) is a link-management platform with a partner program that accrues commissions; `apps/web/tests/commissions/` already houses commission tests. This task adds a self-contained, embedded ledger that records commission entries per partner and computes per-entry running balances entirely in-process, so accrual math can be unit-tested without the production database or any network service.

## Files to Create/Modify

- `apps/web/lib/partners/commission-ledger/schema.ts` (new) — table and relation definitions plus the inferred row types.
- `apps/web/lib/partners/commission-ledger/store.ts` (new) — the `CommissionLedger` class implementing the public API below, backed by an embedded SQLite database opened with the `better-sqlite3` driver (already available in the workspace).
- `apps/web/lib/partners/commission-ledger/index.ts` (new) — re-exports the ledger, its factory, and the public types.
- `apps/web/package.json` (modify) — add the `drizzle-orm` runtime dependency required to build the ledger.
- `apps/web/tests/commissions/commission-ledger.test.ts` (new) — vitest suite covering the behavior and edge cases below.

> The store must run against an in-memory database (e.g. constructed from `":memory:"`) so tests never hit a network, file, or external service. Do not reuse the Prisma client or the live API; this module stands alone.

## Requirements

### Data model

Model two related entities inside the embedded database:

- **partners** — `id` (string, primary key), `name` (string, required).
- **entries** — `id` (string, primary key), `partnerId` (string, required, referencing a partner), `kind` (one of exactly `"accrual"`, `"reversal"`, `"payout"`), `amount` (integer cents, required, positive), and `createdAt` (epoch-millis integer, required). An `accrual` adds to a partner's balance; a `reversal` and a `payout` subtract from it.

One partner has many entries, navigable in a single round trip. Row types used by `store.ts` must be derived from the table definitions themselves. `kind` must be constrained to the three values at the type level.

### Construction and lifecycle

- A factory (e.g. `createCommissionLedger()`) returns a fresh, empty ledger backed by a new in-memory database with both tables created.
- Each new ledger is fully isolated.

### Write API

- `addPartner(input)` and `appendEntry(input)` insert one row and return it.
- `appendEntry` with a non-positive `amount`, or referencing a non-existent partner, must throw and insert nothing.
- `recordPayout(partnerId, amount)` appends a `"payout"` entry but only if the partner's **current balance** is at least `amount`; otherwise it throws and inserts nothing. The balance check and the insert must happen as a single atomic unit so that two interleaved logical steps cannot both succeed against the same balance.

### Read API (computed in the database)

- `getBalance(partnerId)` returns the signed integer balance (accruals minus reversals and payouts); a partner with no entries has balance `0`.
- `getStatement(partnerId)` returns the partner's entries ordered by `createdAt` ascending, each annotated with the **running balance** after that entry is applied — the cumulative figure must be produced by the database (e.g. an ordered cumulative computation), not by iterating the rows in JavaScript.
- `getBalances()` returns every partner's `id`, `name`, and current balance — including partners with no entries (balance `0`).

### Constraints & edge cases

- The running balance in `getStatement` must reflect the entry order by `createdAt` and be internally consistent (the last row's running balance equals `getBalance`).
- All summation and cumulative computation must be performed by the database query, not by loading rows into JavaScript and reducing there.
- Values passed into queries must be safely parameterized; string-concatenating caller input is not acceptable.
- Unknown partner ids yield balance `0` / empty statement, never throw.

### Expected Functionality

- For `p1`: accrual `100`, accrual `50`, reversal `30`, payout `20` (in that `createdAt` order) -> `getStatement("p1")` running balances `[100, 150, 120, 100]`; `getBalance("p1")` -> `100`.
- `recordPayout("p1", 1000)` against a balance of `100` throws and inserts no entry; balance stays `100`.
- `recordPayout("p1", 40)` succeeds and reduces balance to `60`.
- A partner with no entries appears in `getBalances()` with balance `0`.

## Acceptance Criteria

- The new module builds and is importable from `apps/web/lib/partners/commission-ledger`.
- `apps/web/package.json` declares `drizzle-orm` as a dependency.
- A deterministic vitest suite at `apps/web/tests/commissions/commission-ledger.test.ts` exercises: kind-constrained entries, in-database signed balance, in-database ordered running balance whose final value equals the standalone balance, the atomic balance-checked payout (rejecting overdraw and inserting nothing), zero-balance partners appearing in `getBalances()`, non-positive-amount and invalid-partner rejection, ledger isolation, and unknown-id zero/empty results.
- The suite runs fully in-memory with no network, filesystem, or external-service access and passes deterministically on repeated runs.
- The following command passes:

  ```bash
  cd apps/web && pnpm vitest run tests/commissions/commission-ledger.test.ts
  ```
