# Task: Add a concatWs helper for PostgreSQL

## Background

Kysely's PostgreSQL helper module (`src/helpers/postgres.ts`) provides JSON helpers, but has no helper for PostgreSQL's `concat_ws(<separator>, <arg0>, <arg1>, ...)` function, which concatenates a variadic list of expressions using a separator while skipping NULLs. This task adds that helper.

## Files to Create/Modify

- `src/helpers/postgres.ts` (modify) — add and export a new `concatWs` function.
- `test/node/src/concat-ws-postgres.test.ts` (new) — deterministic compilation tests for the new function.

## Requirements

### Public API

The module must export a function named `concatWs` taking two arguments, in order:

1. `separator`: a `string` separator (e.g. `' '`).
2. `values`: an array (tuple) of `Expression<unknown>` values to concatenate (column references, `eb.val(...)` values, or raw `sql` fragments).

It returns a single expression (a `RawBuilder`) that can be aliased with `.as(...)` and placed inside a `select(...)` callback.

The value order MUST follow the input `values` array order, left to right.

### Compiled SQL

The function must compile to PostgreSQL's `concat_ws(<separator>, <value0>, <value1>, ...)`:

- The `separator` is emitted as the FIRST argument and must be a bound parameter (`$1` placeholder, collected into the parameter list) — it must NOT be inlined as a literal.
- Each value expression is compiled through Kysely's normal expression compilation, after the separator: column references are double-quoted; `eb.val(...)` values become subsequent `$2`, `$3`, ... placeholders collected, in order, into the parameter list; raw `sql` fragments are emitted verbatim.
- Exactly one pair of parentheses; all arguments (separator first, then values) separated by `, ` with no trailing separator.

### Type inference

The result expression's value type must be `string`. The exported function must not be `any`-typed and must accept any tuple of `Expression<unknown>` as `values`.

### Constraints

- Do not introduce a new runtime dependency; reuse the primitives already imported by `src/helpers/postgres.ts`.
- Do not change the behavior, signature, or output of any existing exported helper (`jsonArrayFrom`, `jsonObjectFrom`, `jsonBuildObject`, `mergeAction`).
- Keep the module importable via `kysely/helpers/postgres`.

### Expected Functionality

- `concatWs(' ', [eb.ref('first_name'), eb.ref('last_name')])` aliased `full`, selected from `person` → `select concat_ws($1, "first_name", "last_name") as "full" from "person"` with the parameter list `[' ']`.
- `concatWs('-', [eb.ref('a'), eb.val('x')])` → the separator `'-'` is `$1` and the value `'x'` is `$2`, both in the parameter list in that order; `"a"` stays a quoted identifier.
- ``concatWs(', ', [sql`upper(first_name)`, eb.ref('last_name')])`` → the raw fragment `upper(first_name)` is emitted verbatim as the first value, the separator bound as `$1`.

## Acceptance Criteria

- A new `concatWs` function exists and is exported from `src/helpers/postgres.ts`.
- A new node test file `test/node/src/concat-ws-postgres.test.ts` builds a `Kysely` instance using the PostgreSQL adapter and query compiler together with `DummyDriver` (no real database connection or network), constructs `select` queries using `concatWs`, calls `.compile()`, and asserts on both the produced `sql` string and the `parameters` array for the scenarios above (two column-ref values, a column-ref + `eb.val` value, and a raw `sql` fragment value) — verifying the separator is always the first bound parameter.
- Existing tests continue to pass; no existing helper output changes.
- The following commands succeed from the repository root:

```bash
pnpm install
pnpm build
pnpm test:node:build
npx mocha --timeout 15000 test/node/dist/concat-ws-postgres.test.js
```
