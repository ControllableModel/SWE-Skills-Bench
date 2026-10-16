# Task: Build an In-Memory Workspace Usage Counter Store

## Background

The dub monorepo (`apps/web`) is a link-management platform where each workspace has plan limits and metered usage (links, clicks, AI calls); `apps/web/lib/plan-capabilities.ts` and related code gate features by usage. This task adds a self-contained, embedded store that tracks per-workspace usage counters with atomic increments entirely in-process, so quota accounting can be unit-tested without the production database or any network service.

## Files to Create/Modify

- `apps/web/lib/workspace-usage/schema.ts` (new) — table and relation definitions plus the inferred row types.
- `apps/web/lib/workspace-usage/store.ts` (new) — the `UsageStore` class implementing the public API below, backed by an embedded SQLite database opened with the `better-sqlite3` driver (already available in the workspace).
- `apps/web/lib/workspace-usage/index.ts` (new) — re-exports the store, its factory, and the public types.
- `apps/web/package.json` (modify) — add the `drizzle-orm` runtime dependency required to build the store.
- `apps/web/tests/workspaces/usage-store.test.ts` (new) — vitest suite covering the behavior and edge cases below.

> The store must run against an in-memory database (e.g. constructed from `":memory:"`) so tests never hit a network, file, or external service. Do not reuse the Prisma client or the live API; this module stands alone.

## Requirements

### Data model

Model two related entities inside the embedded database:

- **workspaces** — `id` (string, primary key), `name` (string, required), `linkLimit` (integer, required).
- **usage** — per-metric counters for a workspace: `workspaceId` (string, required, referencing a workspace), `metric` (one of exactly `"links"`, `"clicks"`, `"ai"`), `used` (integer, default `0`). A workspace has at most one counter per metric; the (workspace, metric) pair identifies the counter.

One workspace has many usage rows, navigable in a single round trip. Row types used by `store.ts` must be derived from the table definitions themselves. `metric` must be constrained to the three values at the type level.

### Construction and lifecycle

- A factory (e.g. `createUsageStore()`) returns a fresh, empty store backed by a new in-memory database with both tables created.
- Each new store is fully isolated.

### Write API

- `addWorkspace(input)` inserts a workspace (and no usage rows yet) and returns it.
- `increment(workspaceId, metric, by = 1)` raises that counter by `by`, creating the counter at `by` if it does not exist yet. The increment must be expressed as a single atomic database update against the stored value (read-modify-write inside one statement/transaction), not by reading the number into JavaScript, adding, and writing it back.
- `incrementLinkIfUnderLimit(workspaceId)` increments the `"links"` counter by `1` only if the workspace's current `"links"` usage is strictly below its `linkLimit`; otherwise it throws and changes nothing. The limit check and the increment must commit as one atomic unit so the limit can never be exceeded.
- `reset(workspaceId, metric)` sets that counter back to `0` (creating it at `0` if absent).

### Read API

- `getUsage(workspaceId, metric)` returns the current count (or `0` if no counter row exists).
- `getWorkspaceUsage(workspaceId)` returns the workspace with its usage counters nested, assembled from a single relation-aware query; unknown workspace returns `null`.
- `getOverLimitWorkspaces()` returns workspaces whose `"links"` usage is greater than or equal to their `linkLimit`, ordered by `id`.

### Constraints & edge cases

- Calling `increment` repeatedly yields the exact arithmetic sum (e.g. 1000 single increments produce `1000`); no lost updates.
- `incrementLinkIfUnderLimit` at exactly the limit throws and leaves usage unchanged.
- All arithmetic and limit comparison must be performed by the database, not in JavaScript.
- Values passed into queries must be safely parameterized; string-concatenating caller input is not acceptable.
- Unknown workspace ids yield `0` / `null`, never throw (except the explicit limit-exceeded throw).

### Expected Functionality

- `increment("w1","clicks")` twenty times -> `getUsage("w1","clicks")` is `20`; the counter was auto-created on first call.
- With `linkLimit` `3` and links usage `2`, `incrementLinkIfUnderLimit("w1")` succeeds (usage `3`); a further call throws and usage stays `3`.
- `getOverLimitWorkspaces()` includes a workspace at or above its link limit.
- `getWorkspaceUsage("w1")` nests all of `w1`'s metric counters in one query.

## Acceptance Criteria

- The new module builds and is importable from `apps/web/lib/workspace-usage`.
- `apps/web/package.json` declares `drizzle-orm` as a dependency.
- A deterministic vitest suite at `apps/web/tests/workspaces/usage-store.test.ts` exercises: metric-constrained counters, auto-creating atomic increments producing exact sums over many calls, the atomic limit-checked link increment (succeeding under limit, throwing and not mutating at the limit), reset-to-zero (including creating an absent counter), single-round-trip nested workspace+usage loading, the over-limit listing, store isolation, and unknown-id zero/`null` results.
- The suite runs fully in-memory with no network, filesystem, or external-service access and passes deterministically on repeated runs.
- The following command passes:

  ```bash
  cd apps/web && pnpm vitest run tests/workspaces/usage-store.test.ts
  ```
