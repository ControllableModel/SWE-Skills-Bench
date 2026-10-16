# Task: Add an arrayToString helper for PostgreSQL

## Background

Kysely's PostgreSQL helper module (`src/helpers/postgres.ts`) provides JSON helpers but nothing for PostgreSQL's `array_to_string(<array>, <delimiter>)` function, which joins an array's elements into a single text value using a delimiter. This task adds that two-argument helper.

## Files to Create/Modify

- `src/helpers/postgres.ts` (modify) — add and export a new `arrayToString` function.
- `test/node/src/array-to-string-postgres.test.ts` (new) — deterministic compilation tests for the new function.

## Requirements

### Public API

The module must export a function named `arrayToString` taking two arguments, in order:

1. `array`: an `Expression<unknown>` that yields an array (a column reference, an `eb.val(...)` value, or a raw `sql` fragment).
2. `delimiter`: a `string` delimiter (e.g. `', '`).

It returns a single expression (a `RawBuilder`) that can be aliased with `.as(...)` and placed inside a `select(...)` callback, exactly like the existing helpers in the module.

### Compiled SQL

The function must compile to PostgreSQL's `array_to_string(<array>, <delimiter>)`:

- The `array` argument is compiled through Kysely's normal expression compilation: a column reference is double-quoted; an `eb.val(...)` value becomes a `$1`, `$2`, ... placeholder collected into the parameter list; a raw `sql` fragment is emitted verbatim.
- The `delimiter` argument must be emitted as a single bound parameter (placeholder, collected into the parameter list) — it must NOT be inlined into the SQL text as a literal.
- Exactly one pair of parentheses, with the two arguments separated by `, `.

### Type inference

The result expression's value type must be `string`. The exported function must not be `any`-typed.

### Constraints

- Do not introduce a new runtime dependency; reuse the primitives already imported by `src/helpers/postgres.ts`.
- Do not change the behavior, signature, or output of any existing exported helper (`jsonArrayFrom`, `jsonObjectFrom`, `jsonBuildObject`, `mergeAction`).
- Keep the module importable via `kysely/helpers/postgres`.

### Expected Functionality

- `arrayToString(eb.ref('tags'), ', ')` aliased `csv`, selected from `person` → `select array_to_string("tags", $1) as "csv" from "person"` with the parameter list `[', ']`.
- `arrayToString(eb.val(['a', 'b']), '-')` aliased `joined` → both the array value `['a','b']` and the delimiter `'-'` appear in the parameter list, in argument order, and neither is inlined in the SQL text.
- ``arrayToString(sql`array['a','b']`, ', ')`` → emits `array_to_string(array['a','b'], $1)` with the delimiter bound as the single parameter `[', ']`.

## Acceptance Criteria

- A new `arrayToString` function exists and is exported from `src/helpers/postgres.ts`.
- A new node test file `test/node/src/array-to-string-postgres.test.ts` builds a `Kysely` instance using the PostgreSQL adapter and query compiler together with `DummyDriver` (no real database connection or network), constructs `select` queries using `arrayToString`, calls `.compile()`, and asserts on both the produced `sql` string and the `parameters` array for the scenarios above (column-ref array, `eb.val` array, and raw `sql` fragment array — each with a string delimiter bound as a parameter).
- Existing tests continue to pass; no existing helper output changes.
- The following commands succeed from the repository root:

```bash
pnpm install
pnpm build
pnpm test:node:build
npx mocha --timeout 15000 test/node/dist/array-to-string-postgres.test.js
```
