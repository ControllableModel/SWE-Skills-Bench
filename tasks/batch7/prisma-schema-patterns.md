# Task: Add a Read-Replica Routing Resolver for the Prisma Package

## Background

In `@calcom/prisma` (`packages/prisma`), `packages/prisma/index.ts` exports both a primary `prisma` client and a `readonlyPrisma` client; the read-only client is pointed at `INSIGHTS_DATABASE_URL` when that variable is set, and otherwise falls back to the primary connection. The branch that decides this is inlined and untested. This task asks you to extract the routing decision into a pure, testable resolver that tells callers which connection a given operation should use.

## Files to Create/Modify

- `packages/prisma/replica-routing.ts` (new) — a pure module exporting the resolver. It must not import the generated Prisma client, the adapter, or `pg`, and must not open any connection.
- `packages/prisma/replica-routing.test.ts` (new) — the Vitest unit test.

## Requirements

### Resolver Contract

Export a function `resolveReplicaRouting(env: Record<string, string | undefined>)` that returns a plain object with at least:

- `primaryUrl` — the writable connection string.
- `readonlyUrl` — the connection string the read-only client should use.
- `hasDedicatedReplica` — boolean: whether a distinct read replica is configured.

It receives an environment map (testable without mutating `process.env`) and is pure: no I/O, no ambient `process.env` reads, equal input always yields equal output.

### Routing Rules

- `primaryUrl` comes from `DATABASE_URL`. If `DATABASE_URL` is missing, empty, or whitespace-only, the resolver must throw an `Error` identifying the missing primary URL.
- When `INSIGHTS_DATABASE_URL` is present and non-empty (after trimming), `readonlyUrl` is that value and `hasDedicatedReplica` is `true`.
- When `INSIGHTS_DATABASE_URL` is absent, empty, or whitespace-only, `readonlyUrl` falls back to `primaryUrl` and `hasDedicatedReplica` is `false`.
- A configured replica URL that is byte-for-byte equal to the primary URL must be treated as **not** a dedicated replica: `hasDedicatedReplica` must be `false` and `readonlyUrl` equals the primary (pointing reads at the same database is not a real replica).

### Validation

- Both the primary URL and any configured (non-empty) replica URL must use a PostgreSQL scheme (`postgres://` or `postgresql://`). If either configured URL uses any other scheme, the resolver must throw an `Error` naming which URL was invalid.
- The replica URL is only validated when it is actually configured (non-empty); when it falls back to the primary, it is not re-validated separately.

## Acceptance Criteria

- `packages/prisma/replica-routing.ts` exists and exports `resolveReplicaRouting`, importable on its own without pulling in the generated Prisma client, the adapter, or `pg`.
- The function is pure: it does not read or mutate `process.env`, and equal inputs produce deep-equal outputs.
- All routing, fallback, same-URL, and validation rules above hold, including the throw cases.
- The added Vitest suite passes:

  ```bash
  yarn vitest run packages/prisma/replica-routing.test.ts
  ```

  The suite must contain at least 10 distinct assertions covering: dedicated replica when `INSIGHTS_DATABASE_URL` differs, fallback when it is absent, fallback when it is empty, fallback when it is whitespace-only, the same-URL-as-primary treated as no dedicated replica, the missing-`DATABASE_URL` throw, the wrong-scheme primary throw, the wrong-scheme replica throw, `hasDedicatedReplica` matching the routing, and purity (`process.env` untouched).
