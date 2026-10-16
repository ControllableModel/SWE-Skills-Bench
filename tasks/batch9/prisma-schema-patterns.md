# Task: Add a Connection-String Component Parser for the Prisma Package

## Background

In `@calcom/prisma` (`packages/prisma`), the PostgreSQL connection string from `DATABASE_URL` is passed wholesale into the driver adapter in `packages/prisma/index.ts`, but diagnostics and tooling sometimes need its individual components (host, port, database name) without the credentials. This task asks you to add a pure parser that breaks a PostgreSQL connection string into its structured components.

## Files to Create/Modify

- `packages/prisma/connection-parts.ts` (new) — a pure module exporting the parser. It must not import the generated Prisma client, the adapter, or `pg`, and must not open any connection.
- `packages/prisma/connection-parts.test.ts` (new) — the Vitest unit test.

## Requirements

### Parser Contract

Export a function `parseConnectionString(url: string)` that returns a plain object with at least:

- `scheme` — the URL scheme (`postgres` or `postgresql`, without `://`).
- `user` — the username, or `null` when no userinfo is present.
- `host` — the host name.
- `port` — the port as a number, defaulting to `5432` when the URL omits it.
- `database` — the database name (the path after the host, with the leading `/` removed), or `null` when no database path is present.
- `params` — an object of query parameters parsed from the part after `?` (empty object when there are none).

The function is pure: no I/O, no environment reads, equal input always yields equal output. The password is intentionally NOT returned (it must never be included in the result).

### Parsing Rules

- Only `postgres://` and `postgresql://` schemes are accepted. Any other scheme (or empty string) must cause the function to throw an `Error` naming the unsupported scheme.
- When the port is omitted (`postgresql://host/db`), `port` must default to `5432`.
- When the database path is omitted (`postgresql://host:5432`), `database` must be `null`.
- Query parameters (`?sslmode=require&connection_limit=10`) must be parsed into `params` as string key/value pairs. A parameter with no value (`?foo`) must map to an empty string.
- The result must never contain the password, even when one is present in the input URL.

### Edge Cases

- A URL with userinfo `user:pass@` must yield `user` equal to the username and must not leak the password anywhere in the result.
- A URL with no userinfo must yield `user === null`.
- A non-numeric explicit port (e.g. `host:abc`) must cause the function to throw an `Error` indicating the port is invalid.

## Acceptance Criteria

- `packages/prisma/connection-parts.ts` exists and exports `parseConnectionString`, importable on its own without pulling in the generated Prisma client, the adapter, or `pg`.
- The function is pure: it does no I/O and equal inputs produce deep-equal outputs.
- All scheme, default-port, default-database, query-parameter, password-omission, and throw rules above hold.
- The added Vitest suite passes:

  ```bash
  yarn vitest run packages/prisma/connection-parts.test.ts
  ```

  The suite must contain at least 10 distinct assertions covering: parsing host/port/database from a full URL, default port `5432` when omitted, `database === null` when omitted, `user` extracted from userinfo, `user === null` without userinfo, the password never appearing in the result, query parameters parsed into `params`, a valueless query parameter mapping to empty string, the unsupported-scheme throw, and the non-numeric-port throw.
