# Task: Build a Webhook Event Validation Module

## Background

This repository (`fabian-hiller/valibot`) is the Valibot schema library, with its full public API exported from `library/src/index.ts`. We need a self-contained module that validates incoming webhook events whose shape depends entirely on a discriminating `type` field, so each event type carries its own required payload.

## Files to Create/Modify

- `library/src/webhookEvent/webhookEvent.ts` (new) — the validation function and the event schema.
- `library/src/webhookEvent/index.ts` (new) — re-export the public surface of the module.
- `library/src/webhookEvent/webhookEvent.test.ts` (new) — the deterministic test suite described below.

Build the module using the library's own public API by importing from the package source root, e.g. `import * as v from '../index.ts';`. Do not add new third-party dependencies.

## Requirements

Implement and export a function `parseEvent(input: unknown)` plus the underlying schema. Every event is an object whose `type` selects which other fields are required. The function must return a discriminated result:

- On success: `{ ok: true, event: <validated event> }`.
- On failure: `{ ok: false, issues: <array of issue objects> }`.

`parseEvent` must never throw.

### Event variants (discriminated by `type`)

- `type: "user.created"` — also requires `userId` (string, non-empty) and `email` (valid email string).
- `type: "user.deleted"` — also requires `userId` (string, non-empty).
- `type: "payment.succeeded"` — also requires `amount` (a number that is an integer `> 0`, representing cents) and `currency` (one of `"usd"`, `"eur"`, `"gbp"`).
- `type: "payment.failed"` — also requires `amount` (integer `> 0`) and `reason` (string, non-empty).

An object whose `type` is not one of the four above is rejected. An object missing the required fields for its declared `type` is rejected.

### Output shape

On success the validated event must contain exactly the fields defined for its variant (plus `type`); unknown extra keys must be stripped. On failure, `issues` must be the non-empty list of validation issues produced by the schema.

### Expected Functionality

- `{ type: "user.created", userId: "u1", email: "a@b.io" }` -> success; `event.type === "user.created"`.
- `{ type: "user.created", userId: "u1", email: "not-an-email" }` -> failure.
- `{ type: "user.deleted", userId: "u9" }` -> success.
- `{ type: "payment.succeeded", amount: 500, currency: "usd" }` -> success; `event.amount === 500`.
- `{ type: "payment.succeeded", amount: 500, currency: "yen" }` -> failure (bad currency).
- `{ type: "payment.succeeded", amount: 5.5, currency: "usd" }` -> failure (non-integer amount).
- `{ type: "payment.failed", amount: 100, reason: "card_declined" }` -> success.
- `{ type: "user.created", userId: "u1", email: "a@b.io", extra: 1 }` -> success but `event` must not contain `extra`.
- `{ type: "subscription.renewed", userId: "u1" }` -> failure (unknown type).
- `null`, `42`, `"x"`, `{}` -> failure (no throw).

## Acceptance Criteria

- A module exists at `library/src/webhookEvent/webhookEvent.ts` exporting `parseEvent` and its schema.
- The schema dispatches on the `type` field so that each event type validates only its own payload, and the validated output for a given type contains exactly that type's fields with unknown keys stripped.
- `parseEvent` returns `{ ok: true, event }` for valid events and `{ ok: false, issues }` (non-empty) for invalid ones, never throwing on any input including non-objects.
- The added test suite contains at least 10 distinct test cases covering: a success case for each of the four event types, a payload-violation failure for at least two types, an unknown-`type` failure, the integer-and-positive constraint on `amount`, the currency picklist, unknown-key stripping, and non-object inputs.
- The following command, run from the `library/` directory, passes with all tests green:

```bash
npx vitest run src/webhookEvent/webhookEvent.test.ts
```
