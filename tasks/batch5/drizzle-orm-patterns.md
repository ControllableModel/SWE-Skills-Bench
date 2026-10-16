# Task: Build an In-Memory Partner Payout Aggregation Store

## Background

The dub monorepo (`apps/web`) is a link-management platform with a partner program; `apps/web/lib/payouts/` holds payout helpers (idempotency keys, marking processed, recomputing state). This task adds a self-contained, embedded store that aggregates partner payouts by status and period entirely in-process, so payout-reporting math can be unit-tested without the production database or any network service.

## Files to Create/Modify

- `apps/web/lib/payouts/payout-store/schema.ts` (new) — table and relation definitions plus the inferred row types.
- `apps/web/lib/payouts/payout-store/store.ts` (new) — the `PayoutStore` class implementing the public API below, backed by an embedded SQLite database opened with the `better-sqlite3` driver (already available in the workspace).
- `apps/web/lib/payouts/payout-store/index.ts` (new) — re-exports the store, its factory, and the public types.
- `apps/web/package.json` (modify) — add the `drizzle-orm` runtime dependency required to build the store.
- `apps/web/tests/payouts/payout-store.test.ts` (new) — vitest suite covering the behavior and edge cases below.

> The store must run against an in-memory database (e.g. constructed from `":memory:"`) so tests never hit a network, file, or external service. Do not reuse the Prisma client or the live API; this module stands alone.

## Requirements

### Data model

Model two related entities inside the embedded database:

- **partners** — `id` (string, primary key), `name` (string, required).
- **payouts** — `id` (string, primary key), `partnerId` (string, required, referencing a partner), `amount` (integer cents, required, non-negative), `status` (one of exactly `"pending"`, `"processing"`, `"completed"`), and `periodStart` (epoch-millis integer, required).

One partner has many payouts, navigable in a single round trip. Row types used by `store.ts` must be derived from the table definitions themselves. `status` must be constrained to the three values at the type level.

### Construction and lifecycle

- A factory (e.g. `createPayoutStore()`) returns a fresh, empty store backed by a new in-memory database with both tables created.
- Each new store is fully isolated.

### Write API

- `addPartner(input)` and `addPayout(input)` insert one row and return it.
- `addPayout` with a negative `amount`, or referencing a non-existent partner, must throw and insert nothing.

### Read API (all aggregation done in the database)

- `getPartnerTotals()` returns, for every partner, its `id`, `name`, the **total** payout amount, and the **count** of payouts — including partners with no payouts (total `0`, count `0`).
- `getTotalsByStatus(partnerId)` returns, per status that the partner has payouts in, the summed amount and count for that status; statuses with no payouts for that partner are omitted.
- `getPartnersOwedAtLeast(minCents)` returns partners whose summed amount across **non-completed** payouts (`"pending"` + `"processing"`) is greater than or equal to `minCents`, ordered by that owed amount descending; each entry includes the partner `id`, `name`, and `owed` total. Partners owing less than the threshold (or owing `0`) are excluded.
- `getPartnerWithPayouts(partnerId)` returns the partner row with its payouts nested, assembled from a single relation-aware query; unknown partner returns `null`.

### Constraints & edge cases

- All summing, counting, grouping, and threshold filtering must be performed by the database query (group-by / aggregate / having semantics), not by loading rows into JavaScript and reducing there.
- A partner with only `"completed"` payouts is owed `0` and must not appear in `getPartnersOwedAtLeast` for any positive threshold.
- Values passed into queries must be safely parameterized; string-concatenating caller input is not acceptable.
- Unknown partner ids yield empty results / `null`, never throw.

### Expected Functionality

- Partner `p1` with payouts `{pending 100, processing 50, completed 1000}` and `p2` with `{completed 30}`; `getPartnerTotals()` -> `p1` total `1150`/count `3`, `p2` total `30`/count `1`.
- `getTotalsByStatus("p1")` -> `pending {amount:100,count:1}`, `processing {amount:50,count:1}`, `completed {amount:1000,count:1}`.
- `getPartnersOwedAtLeast(100)` -> only `p1` with `owed: 150`; `p2` (owed `0`) is excluded.
- A partner with zero payouts appears in `getPartnerTotals()` with total `0`/count `0`.

## Acceptance Criteria

- The new module builds and is importable from `apps/web/lib/payouts/payout-store`.
- `apps/web/package.json` declares `drizzle-orm` as a dependency.
- A deterministic vitest suite at `apps/web/tests/payouts/payout-store.test.ts` exercises: in-database sum/count aggregation, zero-payout partners with total/count `0`, per-status breakdown omitting empty statuses, the owed-at-least threshold filter with descending order (excluding completed-only and below-threshold partners), single-round-trip nested partner+payouts loading, negative-amount and invalid-partner rejection, store isolation, and unknown-id empty/`null` results.
- The suite runs fully in-memory with no network, filesystem, or external-service access and passes deterministically on repeated runs.
- The following command passes:

  ```bash
  cd apps/web && pnpm vitest run tests/payouts/payout-store.test.ts
  ```
