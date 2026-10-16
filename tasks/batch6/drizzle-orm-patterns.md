# Task: Build an In-Memory Short-Link Key Registry with Upsert

## Background

The dub monorepo (`apps/web`) is a link-management platform where every short link is identified by a `domain` + `key` pair that must be globally unique. This task adds a self-contained, embedded registry that reserves and resolves short-link keys entirely in-process, so uniqueness and upsert logic can be unit-tested without the production database or any network service.

## Files to Create/Modify

- `apps/web/lib/links/key-registry/schema.ts` (new) — table and index definitions plus the inferred row types.
- `apps/web/lib/links/key-registry/store.ts` (new) — the `KeyRegistry` class implementing the public API below, backed by an embedded SQLite database opened with the `better-sqlite3` driver (already available in the workspace).
- `apps/web/lib/links/key-registry/index.ts` (new) — re-exports the registry, its factory, and the public types.
- `apps/web/package.json` (modify) — add the `drizzle-orm` runtime dependency required to build the registry.
- `apps/web/tests/links/key-registry.test.ts` (new) — vitest suite covering the behavior and edge cases below.

> The store must run against an in-memory database (e.g. constructed from `":memory:"`) so tests never hit a network, file, or external service. Do not reuse the Prisma client or the live API; this module stands alone.

## Requirements

### Data model

Model one entity inside the embedded database:

- **link_keys** — `id` (string, primary key), `domain` (string, required), `key` (string, required), `destinationUrl` (string, required), `updatedAt` (epoch-millis integer, required). The combination of `domain` + `key` must be enforced unique by a database constraint, and there must be a database index supporting fast lookup by that pair.

Row types used by `store.ts` must be derived from the table definition itself — hand-written interfaces that can silently drift from the columns are not acceptable.

### Construction and lifecycle

- A factory (e.g. `createKeyRegistry()`) returns a fresh, empty registry backed by a new in-memory database with the table and its index created.
- Each new registry is fully isolated.

### Write API

- `reserve(input)` inserts a new key reservation and returns the stored row. Reserving a `domain` + `key` pair that already exists must throw, and must not create a duplicate row or overwrite the existing destination.
- `upsert(input)` reserves the pair if free, or updates the existing reservation's `destinationUrl` and `updatedAt` in place if the pair already exists — performed as a single conflict-handling write, not a read-then-branch in JavaScript. It returns the resulting row and never creates a duplicate.
- `release(domain, key)` deletes the reservation if present and is a no-op otherwise (never throws).

### Read API

- `resolve(domain, key)` returns the reservation for that pair using the indexed lookup, or `null` if none exists.
- `existsBatch(pairs[])` takes a list of `{ domain, key }` and returns the subset that are already reserved, computed with a single query (not one query per pair).
- `listByDomain(domain)` returns all reservations under one domain ordered by `key` ascending.

### Constraints & edge cases

- Two pairs that share a `domain` but differ in `key` (or vice versa) are independent and may both be reserved.
- `existsBatch([])` returns an empty list; lookups must not run per-element queries.
- All filtering and conflict handling must be performed by the database query, not by loading rows and comparing in JavaScript.
- Values passed into queries must be safely parameterized; string-concatenating caller input is not acceptable.

### Expected Functionality

- `reserve({domain:"d", key:"a", ...})` then `reserve({domain:"d", key:"a", ...})` -> the second throws and leaves exactly one row with the original destination.
- `upsert` on an existing pair updates its `destinationUrl`/`updatedAt` and keeps one row; `upsert` on a free pair creates one row.
- `resolve("d","a")` returns the row; `resolve("d","missing")` -> `null`.
- `existsBatch([{d,a},{d,zzz}])` -> only `{d,a}`.
- `("d","a")` and `("d","b")` may both be reserved; `("e","a")` is independent of `("d","a")`.

## Acceptance Criteria

- The new module builds and is importable from `apps/web/lib/links/key-registry`.
- `apps/web/package.json` declares `drizzle-orm` as a dependency.
- A deterministic vitest suite at `apps/web/tests/links/key-registry.test.ts` exercises: unique `domain`+`key` enforcement (duplicate `reserve` rejected, no overwrite), conflict-handling `upsert` (insert-or-update with no duplicates), no-op `release`, indexed `resolve` returning `null` when absent, batch existence check via a single query (including the empty-input case), per-domain listing ordered by key, independence of pairs sharing only one component, registry isolation, and unknown-id behavior.
- The suite runs fully in-memory with no network, filesystem, or external-service access and passes deterministically on repeated runs.
- The following command passes:

  ```bash
  cd apps/web && pnpm vitest run tests/links/key-registry.test.ts
  ```
