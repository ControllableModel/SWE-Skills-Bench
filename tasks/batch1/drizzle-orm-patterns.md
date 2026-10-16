# Task: Build an In-Memory Link Click Analytics Store

## Background

The dub monorepo (`apps/web`) is a link-management platform whose `apps/web/lib/analytics/` directory holds helpers that summarize link activity. This task adds a self-contained, embedded analytics store that aggregates per-link click events for a workspace entirely in-process, so reporting logic can be unit-tested without touching the production database or any network service.

## Files to Create/Modify

- `apps/web/lib/analytics/click-store/schema.ts` (new) — table and relation definitions plus the inferred row types.
- `apps/web/lib/analytics/click-store/store.ts` (new) — the `ClickAnalyticsStore` class implementing the public API described below, backed by an embedded SQLite database opened with the `better-sqlite3` driver (already available in the workspace).
- `apps/web/lib/analytics/click-store/index.ts` (new) — re-exports the store, its factory, and the public types.
- `apps/web/package.json` (modify) — add the `drizzle-orm` runtime dependency required to build the store.
- `apps/web/tests/analytics/click-store.test.ts` (new) — vitest suite covering the behavior and edge cases below.

> The store must be usable against an in-memory database (e.g. constructed from `":memory:"`) so tests never hit a network, file, or external service. Do not reuse the Prisma client or the live API; this module stands alone.

## Requirements

### Data model

Model three related entities inside the embedded database:

- **workspaces** — `id` (string, primary key) and `name` (string, required).
- **links** — `id` (string, primary key), `workspaceId` (string, required, referencing a workspace), `domain` (string, required), `key` (string, required), and `createdAt` (epoch-millis integer, required). The combination of `domain` + `key` must be unique across all links.
- **clicks** — `id` (string, primary key), `linkId` (string, required, referencing a link), `country` (2-letter string or absent/unknown), and `clickedAt` (epoch-millis integer, required).

The model must express that one workspace has many links and one link has many clicks, and these associations must be queryable in a single round trip (no per-row follow-up queries). The schema definitions and the row types used by `store.ts` must be derived from the table definitions themselves — duplicated hand-written interfaces that can silently drift from the columns are not acceptable.

### Construction and lifecycle

- A factory (e.g. `createClickAnalyticsStore()`) returns a fresh, empty store backed by a new in-memory database with all three tables created.
- Each new store is fully isolated: data inserted into one instance is never visible from another.

### Write API

- `addWorkspace(input)` and `addLink(input)` insert a single row and return the stored row.
- `recordClicks(linkId, clicks[])` inserts many click rows for one link. It must be **all-or-nothing**: if any click in the batch is invalid (e.g. references a non-existent link, or a non-positive `clickedAt`), no click from that batch is persisted and the call throws.
- Inserting a link whose `domain` + `key` pair already exists must throw, and must not create a duplicate row.

### Read API

- `getLinkClickCounts(workspaceId)` returns, for every link in the given workspace, the link's `id`, `domain`, `key`, and its total click count — **including links with zero clicks** (count `0`). Links from other workspaces must never appear.
- `getTopLinks(workspaceId, { limit, offset })` returns links of the workspace ordered by click count descending, then by `createdAt` ascending as a tie-breaker, sliced by `limit`/`offset`. Each entry includes `id`, `domain`, `key`, and `clickCount`.
- `getClicksByCountry(workspaceId)` returns, per country code present in the workspace's clicks, the number of clicks; clicks with an absent/unknown country must be grouped under the key `"unknown"`.
- `getWorkspaceReport(workspaceId)` returns the workspace row together with its links, and each link together with its clicks, assembled from a single query against the related tables.

### Constraints & edge cases

- Querying a workspace id that does not exist returns an empty list (for list-returning methods) or `null` (for `getWorkspaceReport`), never throws.
- A `limit` of `0` returns an empty list; an `offset` beyond the number of links returns an empty list.
- All filtering and aggregation must be performed by the database query, not by loading every row into memory and computing in JavaScript.
- Values passed into queries must be safely parameterized; building query fragments by string-concatenating caller input is not acceptable.

### Expected Functionality

- Seed workspace `w1` with links `l1`,`l2`,`l3` and workspace `w2` with link `l4`; record 3 clicks on `l1`, 1 on `l2`, 0 on `l3` -> `getLinkClickCounts("w1")` yields counts `{l1:3, l2:1, l3:0}` and never includes `l4`.
- With the same seed, `getTopLinks("w1", { limit: 2, offset: 0 })` -> `[l1, l2]`; `{ limit: 2, offset: 2 }` -> `[l3]`.
- Two links created at the same `createdAt` with equal click counts are returned in ascending `createdAt`/insertion-stable order.
- Recording a batch where the 2nd click references a missing link leaves the click count unchanged and the call throws.
- `getClicksByCountry("w1")` with clicks from `"US"`, `"US"`, and one with no country -> `{ US: 2, unknown: 1 }`.
- `getWorkspaceReport("w2")` returns `w2` with `l4` nested, and `l4.clicks` reflecting exactly the clicks recorded for `l4`.

## Acceptance Criteria

- The new module builds and is importable from `apps/web/lib/analytics/click-store`.
- `apps/web/package.json` declares `drizzle-orm` as a dependency.
- A deterministic vitest suite at `apps/web/tests/analytics/click-store.test.ts` exercises: relation-aware report assembly, zero-click links appearing with count `0`, descending-count ordering with `createdAt` tie-break, `limit`/`offset` pagination boundaries (including `limit: 0` and out-of-range `offset`), country grouping with the `"unknown"` bucket, workspace isolation, unknown-workspace empty/`null` results, the unique `domain`+`key` rejection, and the all-or-nothing batch insert (no partial rows after a failed batch).
- The suite runs fully in-memory with no network, filesystem, or external-service access and passes deterministically on repeated runs.
- The following command passes:

  ```bash
  cd apps/web && pnpm vitest run tests/analytics/click-store.test.ts
  ```
