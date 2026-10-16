# Task: Add a Driver-Adapter Selector for the Prisma Package

## Background

In `@calcom/prisma` (`packages/prisma`), `packages/prisma/index.ts` always builds a PostgreSQL driver adapter (`@prisma/adapter-pg`) directly from the connection string. As the project anticipates running against more than one database engine, the choice of which JS driver and adapter package to use needs to be derived from the connection string in one isolated, testable place rather than hardcoded at the import site. This task asks you to add a pure module that maps a connection string to the adapter/driver descriptor the package should use.

## Files to Create/Modify

- `packages/prisma/adapter-selector.ts` (new) — a pure module exporting the selector. It must not import the generated Prisma client or instantiate any adapter/driver, and must not open any connection.
- `packages/prisma/adapter-selector.test.ts` (new) — the Vitest unit test.

## Requirements

### Selector Contract

Export a function `selectAdapter(connectionString: string)` returning a plain descriptor object with at least the fields:

- `provider` — a short identifier string for the database engine implied by the URL scheme.
- `adapterPackage` — the npm package name of the driver adapter that matches that engine.
- `driverPackage` — the npm package name of the underlying JS driver that matches that engine.

The function is pure: no I/O, no environment reads, equal input always yields equal output, and it constructs no adapter.

### Scheme-to-Adapter Mapping

The selector inspects the URL scheme (the part before `://`) and returns the matching descriptor:

- A `postgres://` or `postgresql://` URL -> provider `postgresql`, adapter package `@prisma/adapter-pg`, driver package `pg`.
- A `mysql://` URL -> provider `mysql`, adapter package `@prisma/adapter-mariadb`, driver package `mariadb`.
- A `file:` URL (SQLite local file) -> provider `sqlite`, adapter package `@prisma/adapter-better-sqlite3`, driver package `better-sqlite3`.
- A `sqlserver://` URL -> provider `sqlserver`, adapter package `@prisma/adapter-mssql`, driver package `node-mssql`.

### Constraints and Edge Cases

- A `mongodb://` or `mongodb+srv://` URL must cause the function to throw an `Error` whose message makes clear that MongoDB does not use a SQL driver adapter (it is not part of this adapter workflow).
- An unrecognized or missing scheme (empty string, or a scheme not in the table above) must throw an `Error` naming the unsupported scheme.
- Scheme detection must be case-insensitive for the scheme token only (e.g. `POSTGRES://...` is still PostgreSQL); the rest of the URL is irrelevant to the decision.
- The descriptor must not contain a live connection string, credentials, or any constructed object — only the static package/provider identifiers.

## Acceptance Criteria

- `packages/prisma/adapter-selector.ts` exists and exports `selectAdapter`, importable on its own without pulling in the generated Prisma client or any adapter/driver package.
- The function is pure and constructs no adapter or connection.
- All mapping, MongoDB-rejection, unsupported-scheme, and case-insensitivity rules above hold.
- The added Vitest suite passes:

  ```bash
  yarn vitest run packages/prisma/adapter-selector.test.ts
  ```

  The suite must contain at least 10 distinct assertions covering: each supported scheme mapping (postgres, postgresql, mysql, file, sqlserver) to the correct adapter and driver packages, the MongoDB throw (both `mongodb://` and `mongodb+srv://`), the unknown-scheme throw, the empty-string throw, and case-insensitive scheme detection.
