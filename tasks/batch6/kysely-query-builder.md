# Task: Add a jsonQuote helper for SQLite

## Background

Kysely's SQLite helper module (`src/helpers/sqlite.ts`) provides JSON aggregation and object helpers but has no helper for SQLite's `json_quote` function, which converts a scalar SQL value into its JSON representation. This task adds that scalar helper.

## Files to Create/Modify

- `src/helpers/sqlite.ts` (modify) — add and export a new `jsonQuote` function.
- `test/node/src/json-quote-sqlite.test.ts` (new) — deterministic compilation tests for the new function.

## Requirements

### Public API

The module must export a function named `jsonQuote` accepting a single `Expression<unknown>` argument (a column reference, an `eb.val(...)` value, or a raw `sql` fragment) and returning a single expression (a `RawBuilder`) that can be aliased with `.as(...)` and placed inside a `select(...)` callback, exactly like the existing helpers in the module.

### Compiled SQL

The function must compile to SQLite's `json_quote(<arg>)` with the single input expression compiled and emitted as the sole argument:

- A column reference is rendered with SQLite identifier quoting (double quotes), e.g. `json_quote("name")`.
- A value passed via `eb.val(...)` is emitted as the `?` parameter placeholder and collected into the compiled query's parameter list — never inlined as a literal.
- A raw `sql` fragment is emitted verbatim inside the parentheses.

There must be exactly one pair of parentheses and exactly one argument; no comma separators.

### Type inference

Given an input expression whose value type is `V`, the result expression's value type must be the shallow-dehydrated form of `V` (consistent with how the existing helpers in this module derive their value types). The exported function must not be `any`-typed.

### Constraints

- Do not introduce a new runtime dependency; reuse the primitives already imported by `src/helpers/sqlite.ts`.
- Do not change the behavior, signature, or output of any existing exported helper (`jsonArrayFrom`, `jsonObjectFrom`, `jsonBuildObject`).
- Keep the module importable via `kysely/helpers/sqlite`; do not cross-import from any other helper module.

### Expected Functionality

- `jsonQuote(eb.ref('first_name'))` aliased `q`, selected from `person` → `select json_quote("first_name") as "q" from "person"` with no parameters.
- `jsonQuote(eb.val('hi'))` aliased `q` → the argument compiles to `?` and `'hi'` appears in the parameter list, not in the SQL text.
- ``jsonQuote(sql`1 + 1`)`` → emits `json_quote(1 + 1)` verbatim with no parameters.

## Acceptance Criteria

- A new `jsonQuote` function exists and is exported from `src/helpers/sqlite.ts`.
- A new node test file `test/node/src/json-quote-sqlite.test.ts` builds a `Kysely` instance using the SQLite adapter and query compiler together with `DummyDriver` (no real database connection or network), constructs `select` queries using `jsonQuote`, calls `.compile()`, and asserts on both the produced `sql` string and the `parameters` array for the scenarios above (column-ref arg, `eb.val` bound-parameter arg, and raw `sql` fragment arg).
- Existing tests continue to pass; no existing helper output changes.
- The following commands succeed from the repository root:

```bash
pnpm install
pnpm build
pnpm test:node:build
npx mocha --timeout 15000 test/node/dist/json-quote-sqlite.test.js
```
