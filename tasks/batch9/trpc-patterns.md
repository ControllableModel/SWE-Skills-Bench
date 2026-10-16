# Task: Build a Payments Router with a Custom Error Formatter

## Background

This repository is the tRPC monorepo. Its server package (`@trpc/server`) lets an application install an error formatter that shapes how thrown errors are surfaced, alongside the standard tRPC error codes. This task adds a self-contained "payments" API that maps domain failures onto distinguishable error codes and enriches surfaced errors through a formatter, plus a deterministic test driven through callers.

## Files to Create/Modify

- `packages/tests/server/payments.ts` (new) — the module: an in-memory ledger, the tRPC instance configured with a custom error formatter, the helpers, the router, and an exported caller factory.
- `packages/tests/server/payments.test.ts` (new) — the deterministic test importing only the public surface from `payments.ts`.

All implementation lives in `payments.ts`. The test must consume only the exported caller factory and exported types.

## Requirements

### Error Formatter

The tRPC instance must be created with a custom error formatter that adds a structured `data` field to surfaced errors carrying a domain category string drawn from the thrown error's metadata (for example `"insufficient_funds"`, `"account_frozen"`, `"validation"`). The formatter must derive this category from the error rather than from the procedure path, must preserve the original tRPC error code, and must never include internal stack details or raw ledger contents in the surfaced payload.

### Data Layer & Context

`payments.ts` keeps an in-memory ledger of accounts, each `{ id: string; balanceCents: number; frozen: boolean }`. Provide a factory producing a fresh ledger per call. The ledger is reachable inside procedures via context.

### Procedures

Expose a single root router nesting a `payments` sub-router:

- `balance` — input `{ accountId: string }`; returns `{ accountId, balanceCents }`; not-found if the account is unknown.
- `transfer` — input `{ fromId: string; toId: string; amountCents: number }`; moves funds and returns `{ fromBalanceCents, toBalanceCents }`.
- `freeze` — input `{ accountId: string }`; marks the account frozen and returns `{ frozen: true }`; not-found if unknown.

### Domain Rules & Error Mapping

`transfer` must enforce, mapping each failure to a distinguishable surfaced category and an appropriate tRPC code:

- `amountCents` must be an integer `>= 1` → otherwise a validation category failure.
- `fromId` and `toId` must reference existing accounts → otherwise a not-found category failure.
- `fromId` must not equal `toId` → otherwise a validation category failure.
- The source account must not be `frozen` → otherwise an `account_frozen` category failure carrying a forbidden-style code.
- The source balance must be `>= amountCents` → otherwise an `insufficient_funds` category failure carrying a bad-request/precondition code.
- On success, debit the source and credit the destination atomically (no partial mutation if any check fails).

### Expected Functionality

- `balance` for a seeded account → returns its balance; for an unknown id → not-found.
- A valid `transfer` → both balances reflect the moved amount; the sum across the two accounts is unchanged.
- `transfer` exceeding the source balance → fails; the surfaced error's `data` category is `"insufficient_funds"` and no balance changed.
- `transfer` from a frozen account → fails with the `"account_frozen"` category; balances unchanged.
- `transfer` with `fromId === toId`, or `amountCents` of `0`/negative/fractional → validation category failure.
- `transfer` referencing an unknown account → not-found category failure.
- Every surfaced failure exposes a domain `data` category and preserves a tRPC error code, and none leak ledger internals.

## Acceptance Criteria

- A new module `packages/tests/server/payments.ts` exports a caller factory and router type built on `@trpc/server`, with a custom error formatter that attaches a domain category to surfaced errors and preserves codes.
- A new test file `packages/tests/server/payments.test.ts` with at least 12 cases covering: a successful transfer preserving the total, the insufficient-funds path, the frozen-account path, same-account and amount validation, not-found on unknown accounts, atomicity (no partial mutation when a check fails), and that the surfaced error carries the expected domain category while preserving the tRPC code.
- Tests assert on tRPC error **codes** and on the formatter's domain category field where errors are expected (not substring matching of free-text messages).
- The following command passes:

  ```bash
  pnpm vitest run packages/tests/server/payments.test.ts
  ```

- A naive implementation that omits the formatter, conflates the failure categories, mutates balances before all checks pass, or leaks ledger internals must fail the suite.
