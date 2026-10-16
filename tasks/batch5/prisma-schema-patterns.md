# Task: Add a Datasource-Block Parser for the Prisma Schema

## Background

In `@calcom/prisma` (`packages/prisma`), the database provider and the environment variables that supply connection URLs are declared in the `datasource db { ... }` block of `packages/prisma/schema.prisma`. Tooling in the package needs to read that declaration programmatically (for example to verify that the schema's provider and the runtime adapter agree) without depending on the Prisma engine. This task asks you to add a pure parser that extracts the datasource declaration from raw schema text.

## Files to Create/Modify

- `packages/prisma/schema-datasource.ts` (new) — a pure module exporting the parser. It must not import the generated Prisma client, the adapter, or `pg`, and must not read files itself (it receives schema text as a string).
- `packages/prisma/schema-datasource.test.ts` (new) — the Vitest unit test.

## Requirements

### Parser Contract

Export a function `parseDatasource(schemaText: string)` that returns a plain object with at least:

- `provider` — the value of the `provider` key inside the `datasource` block (e.g. `postgresql`).
- `urlEnv` — when `url` is declared as `env("NAME")`, the environment-variable name `NAME`; otherwise `null`.
- `directUrlEnv` — when `directUrl` is declared as `env("NAME")`, the environment-variable name `NAME`; otherwise `null`.

The function is pure: no file or network I/O, no environment reads, equal input always yields equal output.

### Parsing Rules

- The parser locates the first block of the form `datasource <name> { ... }` and reads the `provider`, `url`, and `directUrl` keys inside it. The datasource block's `<name>` (e.g. `db`) is irrelevant and may be any identifier.
- `provider` is a double-quoted string literal (`provider = "postgresql"`); the surrounding quotes must be stripped and the inner value returned.
- `url` and `directUrl` are typically `env("DATABASE_URL")`. When the value is an `env(...)` call, return the inner variable name (without quotes). When `url`/`directUrl` is a plain quoted string literal instead of an `env()` call, the corresponding `*Env` field must be `null` (it is not sourced from the environment). When the key is absent, the field must be `null`.
- Whitespace around `=`, inside the block, and around the `env(...)` argument must not affect parsing.
- Lines beginning with `//` (Prisma comments) inside the block must be ignored and must not be mistaken for keys.

### Edge Cases

- Schema text containing no `datasource` block must cause the function to throw an `Error` stating that no datasource block was found.
- A `datasource` block missing the required `provider` key must cause the function to throw an `Error` naming the missing key.
- Only the first `datasource` block is parsed; additional blocks (if any) are ignored.

## Acceptance Criteria

- `packages/prisma/schema-datasource.ts` exists and exports `parseDatasource`, importable on its own without pulling in the generated Prisma client, the adapter, or `pg`.
- The function is pure: it does no I/O and equal inputs produce deep-equal outputs.
- All extraction, `env()` handling, comment-skipping, whitespace-tolerance, and throw rules above hold.
- The added Vitest suite passes:

  ```bash
  yarn vitest run packages/prisma/schema-datasource.test.ts
  ```

  The suite must contain at least 10 distinct assertions covering: extracting `provider`, extracting `url` and `directUrl` env names, a plain (non-env) `url` yielding `null`, an absent `directUrl` yielding `null`, tolerance to extra whitespace, comment lines being ignored, the no-datasource-block throw, the missing-provider throw, and arbitrary datasource block names being accepted.
