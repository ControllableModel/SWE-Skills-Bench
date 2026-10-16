# Task: Add a jsonValue path-extraction helper for MSSQL

## Background

Kysely's MS SQL Server helper module (`src/helpers/mssql.ts`) provides JSON aggregation and object helpers, but has no helper for MSSQL's `json_value(<document>, <path>)` function, which extracts a scalar value from a JSON document at a given path. This task adds that two-argument helper.

## Files to Create/Modify

- `src/helpers/mssql.ts` (modify) — add and export a new `jsonValue` function.
- `test/node/src/json-value-mssql.test.ts` (new) — deterministic compilation tests for the new function.

## Requirements

### Public API

The module must export a function named `jsonValue` taking two arguments, in order:

1. `document`: an `Expression<unknown>` identifying the JSON document (a column reference, an `eb.val(...)` value, or a raw `sql` fragment).
2. `path`: a `string` JSON path (e.g. `'$.name'`).

It returns a single expression (a `RawBuilder`) that can be aliased with `.as(...)` and placed inside a `select(...)` callback, exactly like the existing helpers in the module.

### Compiled SQL

The function must compile to MSSQL's `json_value(<document>, <path>)`:

- The `document` argument is compiled through Kysely's normal expression compilation: a column reference is double-quoted (e.g. `"data"`); an `eb.val(...)` value becomes an `@1`, `@2`, ... placeholder collected into the parameter list; a raw `sql` fragment is emitted verbatim.
- The `path` argument must be emitted as a single bound parameter (placeholder, collected into the parameter list) — it must NOT be inlined into the SQL text as a literal.
- Exactly one pair of parentheses, with the two arguments separated by `, `.

### Type inference

The result expression's value type must be `string | null` (MSSQL `json_value` returns a nullable scalar string). The exported function must not be `any`-typed.

### Constraints

- Do not introduce a new runtime dependency; reuse the primitives already imported by `src/helpers/mssql.ts`.
- Do not change the behavior, signature, or output of any existing exported helper in the module (`jsonArrayFrom`, `jsonObjectFrom`, `jsonBuildObject`).
- Keep the module importable via `kysely/helpers/mssql`.

### Expected Functionality

- `jsonValue(eb.ref('data'), '$.name')` aliased `name`, selected from `person` → `select json_value("data", @1) as "name" from "person"` with the parameter list `['$.name']`.
- `jsonValue(eb.val('{}'), '$.x')` aliased `x` → both the document value `'{}'` and the path `'$.x'` appear in the parameter list, in argument order (`['{}', '$.x']`), and neither is inlined in the SQL text.
- ``jsonValue(sql`data`, '$.a.b')`` → emits `json_value(data, @1)` with the path bound as the single parameter `['$.a.b']`.

## Acceptance Criteria

- A new `jsonValue` function exists and is exported from `src/helpers/mssql.ts`.
- A new node test file `test/node/src/json-value-mssql.test.ts` builds a `Kysely` instance using the MSSQL adapter and query compiler together with `DummyDriver` (no real database connection or network), constructs `select` queries using `jsonValue`, calls `.compile()`, and asserts on both the produced `sql` string and the `parameters` array for the scenarios above (column-ref document, `eb.val` document, and raw `sql` fragment document — each with a string path bound as a parameter).
- Existing tests continue to pass; no existing helper output changes.
- The following commands succeed from the repository root:

```bash
pnpm install
pnpm build
pnpm test:node:build
npx mocha --timeout 15000 test/node/dist/json-value-mssql.test.js
```
