# Task: Build an In-Memory Webhook Delivery Ledger

## Background

The dub monorepo (`apps/web`) is a link-management platform; `apps/web/lib/webhook/` holds webhook helpers (creation, publishing, failure handling). This task adds a self-contained, embedded ledger that tracks webhook delivery attempts and their outcomes entirely in-process, so retry and failure-accounting logic can be unit-tested without the production database or any network service.

## Files to Create/Modify

- `apps/web/lib/webhook/delivery-store/schema.ts` (new) — table and relation definitions plus the inferred row types.
- `apps/web/lib/webhook/delivery-store/store.ts` (new) — the `DeliveryLedger` class implementing the public API below, backed by an embedded SQLite database opened with the `better-sqlite3` driver (already available in the workspace).
- `apps/web/lib/webhook/delivery-store/index.ts` (new) — re-exports the ledger, its factory, and the public types.
- `apps/web/package.json` (modify) — add the `drizzle-orm` runtime dependency required to build the ledger.
- `apps/web/tests/webhooks/delivery-store.test.ts` (new) — vitest suite covering the behavior and edge cases below.

> The store must run against an in-memory database (e.g. constructed from `":memory:"`) so tests never hit a network, file, or external service. Do not reuse the Prisma client or the live API; this module stands alone.

## Requirements

### Data model

Model two related entities inside the embedded database:

- **webhooks** — `id` (string, primary key), `url` (string, required), `consecutiveFailures` (integer, default `0`), `disabled` (boolean, default `false`).
- **deliveries** — `id` (string, primary key), `webhookId` (string, required, referencing a webhook), `event` (string, required), `payload` (a structured JSON object stored in one column and read back as a typed object `{ event: string; data: Record<string, unknown> }`, not as an opaque blob), `status` (one of exactly `"pending"`, `"success"`, `"failed"`), and `attemptedAt` (epoch-millis integer, required).

One webhook has many deliveries, navigable in a single round trip. Row types used by `store.ts` must be derived from the table definitions themselves. The `payload` column must surface as the typed shape above (no `any`/untyped reads), and `status` must be constrained to the three values at the type level.

### Construction and lifecycle

- A factory (e.g. `createDeliveryLedger()`) returns a fresh, empty ledger backed by a new in-memory database with both tables created.
- Each new ledger is fully isolated.

### Write API

- `registerWebhook(input)` inserts a webhook (defaulting `consecutiveFailures` to `0` and `disabled` to `false`) and returns it.
- `recordSuccess(deliveryId)` and `recordFailure(deliveryId)` each update one delivery's outcome **and** the parent webhook's failure bookkeeping as a single atomic unit (both updates commit together or neither does):
  - On success: set the delivery `status` to `"success"` and reset the webhook's `consecutiveFailures` to `0`.
  - On failure: set the delivery `status` to `"failed"` and increment the webhook's `consecutiveFailures` by `1`; once it reaches `5`, also set the webhook's `disabled` to `true`.
- `enqueueDelivery(input)` inserts a `"pending"` delivery for a webhook and returns it; enqueuing for a non-existent webhook throws and inserts nothing.

### Read API

- `getDeliveries(webhookId)` returns that webhook's deliveries ordered by `attemptedAt` ascending.
- `getFailureCounts()` returns, per webhook, its `id`, `url`, and the number of `"failed"` deliveries — including webhooks with zero failures (count `0`).
- `getDisabledWebhooks()` returns webhooks whose `disabled` is `true`, ordered by `id`.

### Constraints & edge cases

- The atomic success/failure updates must be wrapped so that a thrown error inside leaves both the delivery and the webhook unchanged (no partial update).
- All filtering, counting, and the failure-threshold increment must be expressed against the database, not by reading rows into JavaScript and mutating them there.
- Values passed into queries must be safely parameterized; string-concatenating caller input is not acceptable.
- Recording an outcome for an unknown delivery id throws and changes nothing.

### Expected Functionality

- Five consecutive `recordFailure` calls on one webhook drive its `consecutiveFailures` to `5` and `disabled` to `true`; it then appears in `getDisabledWebhooks()`.
- A `recordSuccess` after some failures resets `consecutiveFailures` to `0`.
- `getFailureCounts()` includes a never-failed webhook with count `0`.
- Reading back a delivery exposes `payload.event` and `payload.data` as a typed object, not a raw string.
- `enqueueDelivery` for a missing webhook id throws and adds no delivery.

## Acceptance Criteria

- The new module builds and is importable from `apps/web/lib/webhook/delivery-store`.
- `apps/web/package.json` declares `drizzle-orm` as a dependency.
- A deterministic vitest suite at `apps/web/tests/webhooks/delivery-store.test.ts` exercises: typed JSON payload round-tripping, status-constrained transitions, atomic delivery+webhook updates on success and failure (including no partial update on error), the failure-threshold auto-disable at `5`, the success reset to `0`, per-webhook failure counts including zero-failure webhooks, the disabled-webhook listing, ledger isolation, and unknown-id rejection.
- The suite runs fully in-memory with no network, filesystem, or external-service access and passes deterministically on repeated runs.
- The following command passes:

  ```bash
  cd apps/web && pnpm vitest run tests/webhooks/delivery-store.test.ts
  ```
