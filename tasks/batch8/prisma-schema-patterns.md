# Task: Add a Provider-Capability Lookup for Prisma Databases

## Background

In `@calcom/prisma` (`packages/prisma`), the package is built around PostgreSQL but the codebase increasingly needs to reason about what features a given database provider supports (some providers lack enum types or scalar lists, MongoDB follows a different workflow entirely). This task asks you to add a pure capability-lookup module so feature-gating code can ask "does this provider support X?" without hardcoding the answer in many places.

## Files to Create/Modify

- `packages/prisma/provider-capabilities.ts` (new) — a pure module exporting the lookup. It must not import the generated Prisma client, the adapter, or `pg`, and must not open any connection.
- `packages/prisma/provider-capabilities.test.ts` (new) — the Vitest unit test.

## Requirements

### Lookup Contract

Export a function `getProviderCapabilities(provider: string)` that returns a plain object with at least these boolean fields:

- `supportsEnums` — whether the provider supports native enum types.
- `supportsScalarLists` — whether the provider supports scalar list fields.
- `usesSqlDriverAdapter` — whether the provider follows the SQL driver-adapter workflow.
- `requiresDirectUrl` — whether the provider commonly needs a separate direct (pooler-bypassing) connection URL.

The function is pure: no I/O, no environment reads, equal input always yields equal output.

### Provider Table

The function accepts the canonical Prisma provider strings and returns capabilities consistent with the following:

- `postgresql` -> enums: yes, scalar lists: yes, SQL adapter: yes, direct URL: yes.
- `cockroachdb` -> enums: yes, scalar lists: yes, SQL adapter: yes, direct URL: yes.
- `mysql` -> enums: yes, scalar lists: no, SQL adapter: yes, direct URL: no.
- `sqlite` -> enums: no, scalar lists: no, SQL adapter: yes, direct URL: no.
- `sqlserver` -> enums: no, scalar lists: no, SQL adapter: yes, direct URL: no.
- `mongodb` -> enums: yes, scalar lists: yes, SQL adapter: **no** (MongoDB does not use a SQL driver adapter), direct URL: no.

### Constraints and Edge Cases

- Provider matching must be case-insensitive (`"PostgreSQL"` resolves the same as `"postgresql"`).
- An unrecognized provider string (including empty string) must cause the function to throw an `Error` naming the unknown provider.
- The returned object must be a fresh value on each call (mutating one call's result must not affect another call's result), and equal inputs must produce deep-equal outputs.

## Acceptance Criteria

- `packages/prisma/provider-capabilities.ts` exists and exports `getProviderCapabilities`, importable on its own without pulling in the generated Prisma client, the adapter, or `pg`.
- The function is pure and returns a fresh object each call; equal inputs produce deep-equal outputs.
- All capability values in the table, the MongoDB-no-SQL-adapter rule, case-insensitivity, and the unknown-provider throw hold.
- The added Vitest suite passes:

  ```bash
  yarn vitest run packages/prisma/provider-capabilities.test.ts
  ```

  The suite must contain at least 10 distinct assertions covering: each provider's capability set (postgresql, cockroachdb, mysql, sqlite, sqlserver, mongodb), MongoDB's `usesSqlDriverAdapter === false`, SQLite's `supportsEnums === false`, case-insensitive lookup, the unknown-provider throw, and result objects being independent across calls.
