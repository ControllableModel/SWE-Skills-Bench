# Task: Add a Database Connection Resolver for the Prisma Layer

## Background

In `@calcom/prisma` (`packages/prisma`), the database client is wired up in `packages/prisma/index.ts`, where a PostgreSQL driver adapter is built from environment variables and (optionally) a connection pool. Today this wiring logic is inlined and duplicated, has no validation, and is impossible to unit-test because it lives next to the generated client import. This task asks you to introduce a small, self-contained, fully testable module that resolves the database connection configuration the prisma package should use, and then have `index.ts` consume it.

## Files to Create/Modify

- `packages/prisma/connection-config.ts` (new) — a pure module exporting the resolver function and its types. It must not import the generated Prisma client, the driver adapter, or the `pg` package, and must not open any connection.
- `packages/prisma/connection-config.test.ts` (new) — the Vitest unit test for the resolver.
- `packages/prisma/index.ts` (modify) — replace the inlined environment parsing / pool decision with a call to the new resolver, preserving current runtime behavior.

## Requirements

### Resolver Contract

Export a function `resolveConnectionConfig(env: Record<string, string | undefined>)` from `packages/prisma/connection-config.ts`. It receives an environment-variable map (so it can be tested without mutating `process.env`) and returns a plain configuration object. It must be a pure function: same input always yields the same output, no I/O, no reads of the ambient `process.env`, no thrown side effects beyond input validation.

The returned object must contain at least the following fields:

- `connectionString` — the resolved primary connection string for the writable client.
- `directConnectionString` — the connection string to use for operations that must bypass any external connection pooler (migrations / long-lived work), or the same value as `connectionString` when no separate direct URL is configured.
- `readonlyConnectionString` — the connection string the read-only client should use, or the same value as `connectionString` when no separate read replica is configured.
- `pooling` — an object describing whether and how a local connection pool should be created.

### Source Environment Variables

The resolver reads these keys from the passed-in `env` map (matching the names already used by the prisma package):

- `DATABASE_URL` — the primary connection string.
- `DATABASE_DIRECT_URL` — optional; the pooler-bypassing direct connection string.
- `INSIGHTS_DATABASE_URL` — optional; the read-replica/read-only connection string.
- `USE_POOL` — opt-in flag for creating a local connection pool.

### Pooling Decision

The `pooling` field must distinguish "no local pool" from "local pool". When pooling is disabled, `pooling.enabled` must be `false` and no pool-sizing fields are required. When pooling is enabled, `pooling.enabled` must be `true` and the object must expose the numeric pool settings the client needs (a maximum connection count and an idle timeout in milliseconds), so that a caller can construct a pool purely from this object without re-reading the environment.

The pool must be enabled only when `USE_POOL` is an explicit, truthy opt-in. Treat the strings `"true"` and `"1"` as opt-in. Any other value — including `"false"`, `"0"`, the empty string, an unrelated value, or an absent variable — must leave pooling disabled. The decision must not be affected by surrounding whitespace differences beyond exact-string matching (i.e. `" true "` is not an opt-in).

### Connection-String Resolution Rules

- `connectionString` comes from `DATABASE_URL`. If `DATABASE_URL` is missing or empty, the resolver must throw an `Error` whose message identifies the missing primary database URL (the writable client cannot exist without it).
- `directConnectionString` comes from `DATABASE_DIRECT_URL` when that value is present and non-empty; otherwise it falls back to `connectionString`.
- `readonlyConnectionString` comes from `INSIGHTS_DATABASE_URL` when that value is present and non-empty; otherwise it falls back to `connectionString`.
- A variable that is present but empty (or whitespace-only) must be treated as "not configured" for the optional URLs (i.e. fall back), and as missing for the required `DATABASE_URL` (i.e. throw).

### Validation

- A configured connection string (primary, direct, or readonly) must use a PostgreSQL scheme: it must begin with `postgres://` or `postgresql://`. If any configured (non-empty) URL does not, the resolver must throw an `Error` that names which URL was invalid. The fallback values do not need to be re-validated separately (validate each distinct configured source once).

### index.ts Integration

Refactor `packages/prisma/index.ts` so the primary client, the read-only client decision, and the pool decision all derive from `resolveConnectionConfig(process.env)` instead of reading the individual environment variables inline. The observable runtime behavior (which client is writable, when a `pg.Pool` is created and with what size/idle-timeout, and when `readonlyPrisma` falls back to `prisma`) must remain equivalent to the current implementation. Do not change the exported names or the public surface of the module.

### Expected Functionality

- `DATABASE_URL` set, `USE_POOL` unset -> primary string resolved, `pooling.enabled === false`, direct and readonly equal to primary.
- `DATABASE_URL` set, `USE_POOL="1"` -> `pooling.enabled === true` with numeric max and idle-timeout fields populated.
- `DATABASE_URL` set, `USE_POOL="false"` -> `pooling.enabled === false`.
- `DATABASE_URL` missing -> throws.
- `DATABASE_DIRECT_URL` set -> `directConnectionString` differs from primary; readonly still falls back to primary.
- `INSIGHTS_DATABASE_URL` set -> `readonlyConnectionString` differs from primary; direct still falls back to primary.
- `DATABASE_URL="mysql://..."` -> throws (wrong scheme).

## Acceptance Criteria

- `packages/prisma/connection-config.ts` exists and exports `resolveConnectionConfig`, importable on its own without pulling in the generated Prisma client, the driver adapter, or `pg`.
- `resolveConnectionConfig` is pure: calling it does not read or mutate `process.env`, and equal inputs produce deep-equal outputs.
- All resolution, pooling, fallback, and validation rules above hold, including the throw cases.
- `packages/prisma/index.ts` derives its connection/pool configuration from the resolver and keeps its current public exports and runtime behavior.
- The added Vitest suite passes:

  ```bash
  yarn vitest run packages/prisma/connection-config.test.ts
  ```

  The suite must contain at least 10 distinct assertions covering: pool enabled/disabled across `USE_POOL` values (`"true"`, `"1"`, `"false"`, `"0"`, empty, absent, an unrelated value), the missing-`DATABASE_URL` throw, the wrong-scheme throw, direct-URL override and fallback, readonly-URL override and fallback, empty-but-present optional URLs falling back, and purity (a second call with the same input deep-equals the first, and `process.env` is untouched).
