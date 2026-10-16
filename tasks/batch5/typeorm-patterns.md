# Task: Build an Account Transfer Layer with Atomic Guarantees

## Background

The TypeORM repository (`typeorm/typeorm`) exercises the ORM end-to-end with functional tests under `test/functional/` that run against an in-memory SQLite database via the repo's own public API. This task adds a self-contained "bank transfer" feature whose multi-step write must be all-or-nothing, verified through that API.

## Files to Create/Modify

- `test/functional/account-transfer/entity/Account.ts` (new) — the account record type.
- `test/functional/account-transfer/entity/LedgerEntry.ts` (new) — the ledger record type.
- `test/functional/account-transfer/transfer-service.ts` (new) — a service constructed from a `DataSource` exposing the operations below.
- `test/functional/account-transfer/account-transfer.test.ts` (new) — the functional test that wires the entities into a testing `DataSource` and verifies every requirement.

Follow the existing conventions in `test/functional/` (see `test/functional/custom-repository/custom-repository.test.ts` and `test/functional/custom-repository/entity/User.ts`): import decorators/types from the repo's own `src/` via relative paths, use `createTestingConnections`, `reloadTestingDatabases`, and `closeTestingConnections` from `../../utils/test-utils`, and assert with `chai`.

## Requirements

### Domain model

An **Account** has a database-generated numeric identity, an `owner` string, and a `balance` integer (in minor units). A **LedgerEntry** has a database-generated numeric identity, references the account it belongs to, a signed `delta` integer, and a `memo` string. A transfer between two accounts must debit one and credit the other and write a matching pair of ledger entries.

### Transfer service

`transfer-service.ts` must export a class (or factory) built from a `DataSource` providing at least:

- **openAccount(owner, initialBalance)** — persists a new account and returns it with its generated id.
- **transfer(fromId, toId, amount)** — within a single atomic unit of work: decrements the source balance by `amount`, increments the destination balance by `amount`, and records one ledger entry per side. If the source account would go negative, the entire operation must leave both balances and the ledger completely unchanged (no partial debit, no orphan ledger entry) and signal the failure to the caller (rejected promise or thrown error).
- **balanceOf(accountId)** — returns the current balance.
- **ledgerFor(accountId)** — returns that account's ledger entries ordered by id ascending.

### Constraints

- The test must run without any external database server: enable only the SQLite-based driver(s) when creating the testing connections.
- The schema must be derived from the record-type definitions by the ORM during test setup; no hand-written `CREATE TABLE` SQL.
- The two balance updates and the two ledger inserts of a single `transfer` must succeed or fail together as one atomic unit; a failure midway must roll everything back.

### Expected Functionality

- A successful transfer of `amount` → source balance drops by `amount`, destination rises by `amount`, and exactly two ledger entries (one per account) exist for that transfer.
- A transfer that would overdraw the source → rejects, and afterwards both balances equal their pre-transfer values and no ledger entry from the failed transfer remains.
- `ledgerFor` after several transfers → returns the account's entries in id order with the correct signed deltas.
- The sum of all ledger deltas for an account equals its balance change relative to its initial balance.

## Acceptance Criteria

- The four files exist under `test/functional/account-transfer/`; entities and service are imported by the test from the repo's own `src/` and `utils`.
- All scenarios in **Expected Functionality** are asserted and pass against the SQLite driver.
- An implementation that performs the debit/credit/ledger writes as independent non-atomic statements (leaving a partial effect after an overdraw) must fail at least one assertion.
- The test compiles and passes. From the repo root:

```bash
pnpm run compile && npx mocha ./build/compiled/test/functional/account-transfer/account-transfer.test.js
```
