# Task: Build an In-Memory API Request Audit Log with Cursor Pagination

## Background

The dub monorepo (`apps/web`) is a link-management platform that exposes a public API; `apps/web/lib/api/` and `apps/web/lib/api-logs/` hold request-handling and logging helpers. This task adds a self-contained, embedded audit log that records API requests per workspace and serves them through stable cursor pagination, with soft deletion, entirely in-process — so audit retrieval can be unit-tested without the production database or any network service.

## Files to Create/Modify

- `apps/web/lib/api-logs/audit-store/schema.ts` (new) — table and index definitions plus the inferred row types.
- `apps/web/lib/api-logs/audit-store/store.ts` (new) — the `AuditStore` class implementing the public API below, backed by an embedded SQLite database opened with the `better-sqlite3` driver (already available in the workspace).
- `apps/web/lib/api-logs/audit-store/index.ts` (new) — re-exports the store, its factory, and the public types.
- `apps/web/package.json` (modify) — add the `drizzle-orm` runtime dependency required to build the store.
- `apps/web/tests/misc/audit-store.test.ts` (new) — vitest suite covering the behavior and edge cases below.

> The store must run against an in-memory database (e.g. constructed from `":memory:"`) so tests never hit a network, file, or external service. Do not reuse the Prisma client or the live API; this module stands alone.

## Requirements

### Data model

Model one entity inside the embedded database:

- **audit_logs** — `id` (string, primary key), `workspaceId` (string, required), `method` (string, required), `path` (string, required), `statusCode` (integer, required), `seq` (integer, required, strictly increasing per insert across the whole store — a stable total order), and `deletedAt` (epoch-millis integer or null; `null` means active). There must be a database index supporting efficient retrieval of a workspace's active rows in `seq` order.

Row types used by `store.ts` must be derived from the table definition itself — hand-written interfaces that can silently drift from the columns are not acceptable.

### Construction and lifecycle

- A factory (e.g. `createAuditStore()`) returns a fresh, empty store backed by a new in-memory database with the table and its index created.
- Each new store is fully isolated. The store assigns a monotonically increasing `seq` to each inserted row.

### Write API

- `record(input)` inserts one active log row (assigning the next `seq`, `deletedAt` = `null`) and returns it.
- `softDelete(id)` sets a row's `deletedAt` to a provided/derived timestamp; the row is retained physically but excluded from default reads. Soft-deleting an already-deleted or unknown id is a no-op (never throws).

### Read API

- `page(workspaceId, { limit, cursor })` returns up to `limit` **active** rows for the workspace in ascending `seq` order, starting strictly after the row identified by `cursor` (a `seq` value); when `cursor` is omitted it starts from the beginning. The result includes the rows and a `nextCursor` (the `seq` of the last returned row, or `null` when no more rows remain). Soft-deleted rows must never appear and must not occupy a page slot.
- `countActive(workspaceId)` returns the number of active (non-deleted) rows for the workspace.
- `getById(id, { includeDeleted })` returns the row by id; by default it returns `null` for a soft-deleted row, but returns it when `includeDeleted` is true.

### Constraints & edge cases

- Paging is stable: concatenating successive pages (feeding each `nextCursor` into the next call) visits every active row exactly once, in `seq` order, with no gaps or repeats — even after some rows are soft-deleted.
- A `limit` of `0` returns no rows and a `nextCursor` of `null`; a cursor past the last row returns an empty page.
- Rows from other workspaces never appear.
- All filtering, ordering, and slicing must be performed by the database query, not by loading every row into memory and paginating in JavaScript.
- Values passed into queries must be safely parameterized; string-concatenating caller input is not acceptable.

### Expected Functionality

- Record 5 rows for `w1` and 2 for `w2`; paging `w1` with `limit: 2` yields `[r1,r2]` then `[r3,r4]` then `[r5]` then an empty page with `nextCursor: null`, never showing `w2`'s rows.
- Soft-deleting `r3` makes paging `w1` with `limit: 2` yield `[r1,r2]` then `[r4,r5]`; `countActive("w1")` becomes `4`.
- `getById(r3)` returns `null` by default but the row when `includeDeleted` is true.
- `page` with `limit: 0` returns `{ rows: [], nextCursor: null }`.

## Acceptance Criteria

- The new module builds and is importable from `apps/web/lib/api-logs/audit-store`.
- `apps/web/package.json` declares `drizzle-orm` as a dependency.
- A deterministic vitest suite at `apps/web/tests/misc/audit-store.test.ts` exercises: monotonic `seq` assignment, cursor pagination that walks every active row exactly once across pages (with and without soft-deleted rows in between), `nextCursor` becoming `null` at the end, `limit: 0` and past-the-end cursor returning empty pages, workspace isolation, soft-delete excluding rows from default reads and `countActive`, `getById` honoring `includeDeleted`, and store isolation.
- The suite runs fully in-memory with no network, filesystem, or external-service access and passes deterministically on repeated runs.
- The following command passes:

  ```bash
  cd apps/web && pnpm vitest run tests/misc/audit-store.test.ts
  ```
