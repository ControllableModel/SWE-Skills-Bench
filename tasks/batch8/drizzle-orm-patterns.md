# Task: Build an In-Memory Reward Rule Store with Typed Conditions

## Background

The dub monorepo (`apps/web`) is a link-management platform whose partner program evaluates reward rules; `apps/web/lib/partners/` holds helpers such as `evaluate-reward-conditions.ts` and `get-reward-amount.ts`. This task adds a self-contained, embedded store that persists reward rules with structured condition objects entirely in-process, so rule lookup and matching can be unit-tested without the production database or any network service.

## Files to Create/Modify

- `apps/web/lib/partners/reward-store/schema.ts` (new) — table and relation definitions plus the inferred row types.
- `apps/web/lib/partners/reward-store/store.ts` (new) — the `RewardStore` class implementing the public API below, backed by an embedded SQLite database opened with the `better-sqlite3` driver (already available in the workspace).
- `apps/web/lib/partners/reward-store/index.ts` (new) — re-exports the store, its factory, and the public types.
- `apps/web/package.json` (modify) — add the `drizzle-orm` runtime dependency required to build the store.
- `apps/web/tests/rewards/reward-store.test.ts` (new) — vitest suite covering the behavior and edge cases below.

> The store must run against an in-memory database (e.g. constructed from `":memory:"`) so tests never hit a network, file, or external service. Do not reuse the Prisma client or the live API; this module stands alone.

## Requirements

### Data model

Model two related entities inside the embedded database:

- **programs** — `id` (string, primary key), `name` (string, required).
- **rules** — `id` (string, primary key), `programId` (string, required, referencing a program), `event` (one of exactly `"click"`, `"lead"`, `"sale"`), `amount` (integer cents, required, non-negative), `priority` (integer, required), and `conditions` (a structured JSON object stored in one column and read back as a typed object `{ minQuantity?: number; country?: string }`, not as an opaque blob).

One program has many rules, navigable in a single round trip. Row types used by `store.ts` must be derived from the table definitions themselves. `event` must be constrained to the three values, and `conditions` must surface as the typed shape above (no `any`/untyped reads).

### Construction and lifecycle

- A factory (e.g. `createRewardStore()`) returns a fresh, empty store backed by a new in-memory database with both tables created.
- Each new store is fully isolated.

### Write API

- `addProgram(input)` and `addRule(input)` insert one row and return it. `addRule` with a negative `amount` or referencing a non-existent program must throw and insert nothing.
- When `conditions` is omitted it persists as an empty object `{}` and reads back as such.

### Read API

- `getRulesForEvent(programId, event)` returns the program's rules for that event ordered by `priority` descending (highest first), with `createdAt`-independent stable ordering when priorities tie (break ties by `id` ascending). Each rule's `conditions` is returned as the typed object.
- `getProgramWithRules(programId)` returns the program row with its rules nested, assembled from a single relation-aware query; unknown program returns `null`.
- `countRulesByEvent(programId)` returns, for each of the three event kinds, how many rules the program has for it — including event kinds with `0` rules.

### Constraints & edge cases

- `conditions` must round-trip exactly: writing `{ minQuantity: 3, country: "US" }` reads back the same object; an omitted `conditions` reads back as `{}`.
- All filtering, ordering, and counting must be performed by the database query, not by loading rows into JavaScript and computing there.
- Values passed into queries must be safely parameterized; string-concatenating caller input is not acceptable.
- Unknown program ids yield empty lists / `null`, never throw.

### Expected Functionality

- Program `pr1` has sale rules with priorities `10`, `5`, `5`; `getRulesForEvent("pr1","sale")` orders them `[10, 5, 5]` with the two priority-`5` rules in ascending `id` order.
- A rule stored with `conditions: { minQuantity: 3, country: "US" }` reads back that exact typed object; a rule stored without conditions reads back `{}`.
- `getProgramWithRules("pr1")` nests all of `pr1`'s rules in one query.
- `countRulesByEvent("pr1")` reports counts for `click`, `lead`, and `sale`, with `0` for any event kind that has no rules.

## Acceptance Criteria

- The new module builds and is importable from `apps/web/lib/partners/reward-store`.
- `apps/web/package.json` declares `drizzle-orm` as a dependency.
- A deterministic vitest suite at `apps/web/tests/rewards/reward-store.test.ts` exercises: typed JSON `conditions` round-tripping (populated and empty-default), event-constrained rules, priority-descending ordering with deterministic tie-break, single-round-trip nested program+rules loading, per-event counts including zero-count events, negative-amount and invalid-program rejection, store isolation, and unknown-id empty/`null` results.
- The suite runs fully in-memory with no network, filesystem, or external-service access and passes deterministically on repeated runs.
- The following command passes:

  ```bash
  cd apps/web && pnpm vitest run tests/rewards/reward-store.test.ts
  ```
