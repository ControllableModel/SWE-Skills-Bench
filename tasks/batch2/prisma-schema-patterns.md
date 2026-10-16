# Task: Add a Connection-String Redactor for Prisma Logging

## Background

In `@calcom/prisma` (`packages/prisma`), database connection strings come from environment variables such as `DATABASE_URL`, `DATABASE_DIRECT_URL`, and `INSIGHTS_DATABASE_URL` and are wired into the client in `packages/prisma/index.ts`. When connection problems are logged, the raw URL — which contains the password and host — must never appear in plaintext. This task asks you to add a small, pure, fully testable helper that turns a database connection string into a safe, redacted form suitable for logs.

## Files to Create/Modify

- `packages/prisma/connection-redact.ts` (new) — a pure module exporting the redaction helper. It must not import the generated Prisma client, the driver adapter, or `pg`, and must not open any connection.
- `packages/prisma/connection-redact.test.ts` (new) — the Vitest unit test.

## Requirements

### Redactor Contract

Export a function `redactConnectionString(url: string): string`. Given a PostgreSQL connection string, it returns a string in which the password is replaced by a fixed mask while the scheme, username, host, port, database name, and any query parameters remain visible. It is a pure function: no I/O, no environment reads, equal input always yields equal output.

### Redaction Rules

- The userinfo portion of the URL has the shape `user:password@`. The `password` segment (everything between the first `:` after the scheme separator and the `@`) must be replaced with the literal mask `****`. The username must be preserved exactly.
- When a URL has a username but no password (`postgres@host`), the output must be unchanged (there is nothing to mask).
- When a URL has no userinfo at all (`postgresql://host:5432/db`), the output must be unchanged.
- The scheme must be preserved exactly; both `postgres://` and `postgresql://` are valid PostgreSQL schemes and must be accepted. A string whose scheme is neither must cause the function to throw an `Error` naming the unsupported scheme (the helper only handles PostgreSQL URLs).
- Query parameters after `?` (for example `?sslmode=require&connection_limit=5`) must be preserved verbatim, even if a value there resembles a password.
- A password that itself contains URL-encoded characters (for example `%40`) must still be fully masked — the entire password segment is replaced regardless of its content.

### Edge Cases

- Empty string input must throw an `Error` (there is no URL to redact).
- A password containing a colon (e.g. `user:pa:ss@host`) must be masked entirely; only the first `:` after the userinfo start separates user from password — but the whole remainder up to `@` is the password and must be masked.
- The host and port must never be altered.

## Acceptance Criteria

- `packages/prisma/connection-redact.ts` exists and exports `redactConnectionString`, importable on its own without pulling in the generated Prisma client, the adapter, or `pg`.
- The function is pure: it does not read or mutate `process.env`, and equal inputs produce equal outputs.
- All masking, scheme-acceptance, throw, and preservation rules above hold.
- The added Vitest suite passes:

  ```bash
  yarn vitest run packages/prisma/connection-redact.test.ts
  ```

  The suite must contain at least 10 distinct assertions covering: masking with `postgres://` and `postgresql://` schemes, preserving a no-password URL, preserving a no-userinfo URL, preserving query parameters, masking a password with encoded characters, masking a password containing a colon, the unsupported-scheme throw, the empty-string throw, and host/port preservation.
