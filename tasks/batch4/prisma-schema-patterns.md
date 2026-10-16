# Task: Add a Pool-Options Builder for the Prisma Connection Pool

## Background

In `@calcom/prisma` (`packages/prisma`), `packages/prisma/index.ts` creates a `pg.Pool` with hardcoded sizing (`max: 5`, `idleTimeoutMillis: 300000`) only when `USE_POOL` is set. To make pool sizing operationally tunable and independently testable, the numeric pool options should be computed in one pure place from environment variables, with safe defaults. This task asks you to add that builder.

## Files to Create/Modify

- `packages/prisma/pool-options.ts` (new) — a pure module exporting the builder. It must not import `pg`, the generated Prisma client, or the adapter, and must not create a pool.
- `packages/prisma/pool-options.test.ts` (new) — the Vitest unit test.

## Requirements

### Builder Contract

Export a function `buildPoolOptions(env: Record<string, string | undefined>)`. It receives an environment-variable map (so it is testable without mutating `process.env`) and returns a plain object with at least:

- `enabled` — boolean: whether a local pool should be created at all.
- `max` — the maximum number of connections in the pool.
- `idleTimeoutMillis` — the idle timeout in milliseconds before a connection is released.

The function is pure: no I/O, no reads of ambient `process.env`, equal input always yields equal output.

### Enablement

`enabled` is `true` only when `USE_POOL` is exactly `"true"` or `"1"`. Any other value — `"false"`, `"0"`, empty string, whitespace-padded `" true "`, an unrelated word, or an absent variable — yields `enabled === false`.

### Sizing Rules

- The maximum connection count comes from `DATABASE_POOL_MAX`. When that variable is absent or empty, `max` defaults to `5`.
- The idle timeout comes from `DATABASE_POOL_IDLE_TIMEOUT_MS`. When that variable is absent or empty, `idleTimeoutMillis` defaults to `300000`.
- Both numeric values must be parsed as base-10 integers.

### Validation and Edge Cases

- A provided `max` that does not parse to a positive integer (non-numeric, zero, negative, or a float like `"2.5"`) must cause the function to throw an `Error` naming the offending variable. `max` must be a whole number `>= 1`.
- A provided idle timeout that does not parse to a non-negative integer (non-numeric, negative, or a float) must cause the function to throw an `Error` naming the offending variable. The idle timeout may be `0` (meaning never time out) but must be a whole number `>= 0`.
- When pooling is disabled, the defaults (or provided valid values) are still returned for `max` and `idleTimeoutMillis`, but `enabled` is `false`. (Validation of any explicitly provided sizing values still applies even when disabled.)

## Acceptance Criteria

- `packages/prisma/pool-options.ts` exists and exports `buildPoolOptions`, importable on its own without pulling in `pg`, the generated Prisma client, or the adapter.
- The function is pure: it does not read or mutate `process.env`, and equal inputs produce deep-equal outputs.
- All enablement, default, parsing, and validation rules above hold, including the throw cases.
- The added Vitest suite passes:

  ```bash
  yarn vitest run packages/prisma/pool-options.test.ts
  ```

  The suite must contain at least 10 distinct assertions covering: enablement across `USE_POOL` values (`"true"`, `"1"`, `"false"`, empty, absent, `" true "`), default `max` and idle timeout when unset, custom valid `max` and idle timeout, the invalid-`max` throw (zero, negative, float, non-numeric), the invalid-idle-timeout throw, and idle timeout of `0` being accepted.
