# Task: Build a Guarded Withdrawal Module with Reusable Conditions

## Background

The `xstate` core package (`packages/core`) is the finite-state-machine runtime for this monorepo. This task adds a self-contained account-withdrawal module whose transitions are gated by several conditions that must be combined (balance sufficient, account not frozen, amount within a per-transaction limit), exercised by a new deterministic test. No async work is involved — this is a synchronous, condition-driven flow.

## Files to Create/Modify

- `packages/core/test/fixtures/withdrawalGuard.ts` (new) — the withdrawal module: a single exported factory plus any helper exports the test imports. Import everything you need from `../../src/index.ts`.
- `packages/core/test/withdrawalGuard.test.ts` (new) — the deterministic test that drives the module through every scenario below.

You may import only from the package's public surface (`../../src/index.ts`); do not reach into internal files.

## Requirements

### Module surface

Export a factory `createWithdrawalMachine(config)` from `withdrawalGuard.ts`. `config` carries:

- `perTxnLimit` — the maximum amount allowed in a single withdrawal.

The factory must return something the test can start with the package's actor API, send events to, and read snapshots from. Durable data includes the current `balance` and a `frozen` boolean (whether the account is frozen). The machine has a finite phase **ready** plus a transient evaluation path, and a per-withdrawal outcome that the test can read.

### Behavior

- A "withdraw" event carries an `amount`. The withdrawal succeeds only when **all** of these hold: the account is not frozen, the amount is at most `perTxnLimit`, and the amount is at most the current `balance`. On success, the balance is reduced by the amount and the last outcome is recorded as **approved** with the new balance.
- If any condition fails, the balance is unchanged and the last outcome records a **declined** result whose reason identifies the first failing condition among: frozen, over-limit, insufficient-funds (in that priority order).
- A "freeze" event sets `frozen` to true; an "unfreeze" event sets it to false. These never change the balance.
- After any withdrawal attempt, the machine returns to **ready** to accept the next event.

### Constraints and edge cases

- The amount being withdrawn travels with the "withdraw" event; the machine must not stash a pending amount and read it later.
- The three approval conditions must be combined as guarding logic on the transition, not duplicated ad hoc; the declined reason must reflect the documented priority order (frozen first, then over-limit, then insufficient-funds).
- A withdrawal of exactly `perTxnLimit` (and exactly the current balance) is allowed; only strictly exceeding either is declined.
- Freezing then attempting a withdrawal that would otherwise be valid must decline with the frozen reason.

### Expected Functionality

- balance 100, `perTxnLimit` 50; withdraw 30 -> **approved**, balance 70.
- withdraw 50 (equals limit) from balance 70 -> **approved**, balance 20.
- withdraw 60 from balance 20 -> **declined**, reason over-limit (limit 50), balance unchanged at 20.
- withdraw 50 from balance 20 (within limit, exceeds balance) -> **declined**, reason insufficient-funds, balance unchanged.
- freeze, then withdraw 10 from balance 20 -> **declined**, reason frozen, balance unchanged; unfreeze, withdraw 10 -> **approved**, balance 10.

## Acceptance Criteria

- Both new files exist at the paths above; the module imports solely from `../../src/index.ts`.
- Withdrawals are gated by combined conditions; the declined reason follows the documented priority order (frozen, over-limit, insufficient-funds) and is read from the snapshot's recorded outcome.
- Balance and frozen flag are read from the snapshot's context; the machine returns to **ready** after each attempt.
- Each scenario in **Expected Functionality** is covered by at least one assertion, including the exactly-at-limit approval and each declined reason at least once.
- The following command passes from the repository root:

  ```
  pnpm vitest run --project xstate packages/core/test/withdrawalGuard.test.ts
  ```
