# Task: Make a Funds-Transfer Operation Atomic

## Background
This is the [Sequelize](https://github.com/sequelize/sequelize) monorepo. Inside the `@sequelize/core` package's integration-test tree we need a small "wallet" domain plus a `transferFunds` operation that moves balance between two accounts atomically. Integration tests in this package run against the default test dialect (an in-memory/file database), so multi-statement atomicity and rollback-on-error can be exercised in-process.

## Files to Create/Modify
- `packages/core/test/integration/wallet-transfer.ts` (new) — the module defining the `Wallet` and `Ledger` models and exporting `setupWallet(sequelize)` and `transferFunds(sequelize, fromId, toId, amount)`.
- `packages/core/test/integration/wallet-transfer.test.ts` (new) — the integration test that exercises the operation.

## Requirements

### Module shape
- `setupWallet(sequelize)` must define and return `{ Wallet, Ledger }`, then create their tables so the operation can run.
- `transferFunds(sequelize, fromId, toId, amount)` must perform the whole transfer as one atomic unit of work.

### Models
- **Wallet** — fields: `owner` (text, required), `balance` (integer, defaults to `0`).
- **Ledger** — fields: `walletId` (integer, required), `delta` (integer, required), `note` (text, optional).

### Transfer behavior
- A successful transfer must, as a single atomic operation: decrement the source wallet's `balance` by `amount`, increment the destination wallet's `balance` by `amount`, and append two `Ledger` rows — one with `delta = -amount` for the source and one with `delta = +amount` for the destination.
- The operation must reject (throw) and leave ALL data unchanged when: `amount` is not strictly positive; the source wallet would go negative (insufficient balance); or either wallet id does not exist. In every rejection case, neither balance may change and no `Ledger` rows may be added.
- After a rejected transfer, querying both wallets and counting `Ledger` rows must show exactly the pre-call state.

### Edge cases and constraints
- A partial transfer (e.g. source debited but destination not credited, or balances changed but ledger rows missing) must never be observable after either success or failure.
- A naive implementation that performs the writes without atomicity, leaving partial state on error, must fail the tests.

### Expected Functionality
- Two wallets with balances 100 and 0; `transferFunds(seq, A, B, 40)` -> A.balance = 60, B.balance = 40, and two ledger rows exist with deltas `-40` and `+40`.
- `transferFunds(seq, A, B, 0)` or a negative amount -> rejects; balances and ledger count unchanged.
- `transferFunds(seq, A, B, 1000)` when A has only 60 -> rejects (insufficient); balances and ledger count unchanged.
- `transferFunds(seq, A, 99999, 10)` (unknown destination) -> rejects; balances and ledger count unchanged.

## Acceptance Criteria
- A new self-contained test `packages/core/test/integration/wallet-transfer.test.ts` exists and asserts: a successful atomic transfer (both balances + both ledger rows), and that each failure mode (non-positive amount, insufficient funds, unknown wallet) leaves balances and ledger count exactly as before the call.
- The implementation lives in `packages/core/test/integration/wallet-transfer.ts` and is imported by the test.
- All assertions are objectively verifiable in-process against the default test database (no external server).
- From the `packages/core` directory, the following command runs and passes with no failing tests:

  ```bash
  yarn mocha "test/integration/wallet-transfer.test.ts"
  ```
