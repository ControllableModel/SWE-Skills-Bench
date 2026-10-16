# Task: Add a Schema/Adapter Consistency Checker for the Prisma Package

## Background

In `@calcom/prisma` (`packages/prisma`), the database engine is declared in two places that must agree: the `provider` in the `datasource` block of `packages/prisma/schema.prisma`, and the runtime driver adapter chosen from the connection string in `packages/prisma/index.ts`. If these drift apart (for example a `postgresql` schema with a `mysql://` connection string) the application fails confusingly at runtime. This task asks you to add a pure checker that reports whether a declared provider and a runtime connection string are mutually consistent.

## Files to Create/Modify

- `packages/prisma/schema-consistency.ts` (new) — a pure module exporting the checker. It must not import the generated Prisma client, the adapter, or `pg`, and must not open any connection.
- `packages/prisma/schema-consistency.test.ts` (new) — the Vitest unit test.

## Requirements

### Checker Contract

Export a function `checkSchemaConsistency(provider: string, connectionString: string)` that returns a plain object with at least:

- `consistent` — boolean: whether the declared provider matches the engine implied by the connection string's scheme.
- `declaredProvider` — the normalized provider that was declared.
- `connectionProvider` — the provider implied by the connection string's scheme.

The function is pure: no I/O, no environment reads, equal input always yields equal output. It must never throw for a *recognized* provider and *recognized* scheme — consistency is reported through `consistent`. (It may throw only for the unrecognized-input cases described below.)

### Scheme-to-Provider Mapping (connection side)

- `postgres://` or `postgresql://` -> connection provider `postgresql`.
- `mysql://` -> connection provider `mysql`.
- `sqlserver://` -> connection provider `sqlserver`.
- `file:` -> connection provider `sqlite`.

### Consistency Rules

- `cockroachdb` declared with a `postgres://`/`postgresql://` connection string is **consistent** (CockroachDB is PostgreSQL-wire-compatible and uses the same connection scheme). This is the one case where the declared provider name and the connection provider name differ but are still consistent.
- In all other cases, `consistent` is `true` only when `declaredProvider` equals `connectionProvider` (after normalization).
- Provider and scheme matching must be case-insensitive.

### Edge Cases

- An unrecognized declared provider (not one of `postgresql`, `mysql`, `sqlite`, `sqlserver`, `cockroachdb`, `mongodb`) must cause the function to throw an `Error` naming the unknown provider.
- An unrecognized or missing connection scheme (empty string, or a scheme not in the mapping table) must cause the function to throw an `Error` naming the unsupported scheme.
- A `mongodb` declared provider combined with any SQL connection scheme must yield `consistent === false` (MongoDB does not use a SQL connection string), and must NOT throw on the provider alone.

## Acceptance Criteria

- `packages/prisma/schema-consistency.ts` exists and exports `checkSchemaConsistency`, importable on its own without pulling in the generated Prisma client, the adapter, or `pg`.
- The function is pure: it does no I/O and equal inputs produce deep-equal outputs.
- All mapping, CockroachDB-compatibility, case-insensitivity, and throw rules above hold.
- The added Vitest suite passes:

  ```bash
  yarn vitest run packages/prisma/schema-consistency.test.ts
  ```

  The suite must contain at least 10 distinct assertions covering: matching postgresql provider with postgres URL (consistent), mismatched postgresql provider with mysql URL (inconsistent), matching mysql, matching sqlserver, matching sqlite with `file:` URL, cockroachdb with postgres URL (consistent despite differing names), mongodb provider with a SQL URL (inconsistent, no throw), case-insensitive matching, the unknown-provider throw, and the unsupported-scheme throw.
