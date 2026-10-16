# Task: Add a jsonQuote helper for MySQL

## Background

Kysely's MySQL helper module (`src/helpers/mysql.ts`) provides JSON aggregation and object helpers but has no helper for MySQL's `json_quote` function, which wraps a scalar expression as a quoted JSON string value. This task adds that scalar helper.

## Files to Create/Modify

- `src/helpers/mysql.ts` (modify) — add and export a new `jsonQuote` function.
- `test/node/src/json-quote-mysql.test.ts` (new) — deterministic compilation tests for the new function.

## Requirements

### Public API

The module must export a function named `jsonQuote` accepting a single `Expression<unknown>` argument (a column reference, an `eb.val(...)` value, or a raw `sql` fragment) and returning a single expression (a `RawBuilder`) that can be aliased with `.as(...)` and placed inside a `select(...)` callback, exactly like the existing helpers in the module.

### Compiled SQL

The function must compile to MySQL's `json_quote(<arg>)` with the single input expression compiled and emitted as the sole argument:

- A column reference is rendered with MySQL identifier quoting (backticks), e.g. ``json_quote(`name`)``.
- A value passed via `eb.val(...)` is emitted as the `?` parameter placeholder and collected into the compiled query's parameter list — never inlined as a literal.
- A raw `sql` fragment is emitted verbatim inside the parentheses.

There must be exactly one pair of parentheses and exactly one argument; no comma separators.

### Type inference

Given an input expression whose value type is `V`, the result expression's value type must be `string` (a quoted JSON string is always returned). The exported function must not be `any`-typed and must accept any `Expression<unknown>`.

### Constraints

- Do not introduce a new runtime dependency; reuse the primitives already imported by `src/helpers/mysql.ts`.
- Do not change the behavior, signature, or output of any existing exported helper (`jsonArrayFrom`, `jsonObjectFrom`, `jsonBuildObject`).
- Keep the module importable via `kysely/helpers/mysql`.

### Expected Functionality

- `jsonQuote(eb.ref('first_name'))` aliased `q`, selected from `person` → ``select json_quote(`first_name`) as `q` from `person` `` with no parameters.
- `jsonQuote(eb.val('hi'))` aliased `q` → the argument compiles to `?` and `'hi'` appears in the parameter list, not in the SQL text.
- ``jsonQuote(sql`concat(first_name, last_name)`)`` → emits ``json_quote(concat(first_name, last_name))`` verbatim with no parameters.

## Acceptance Criteria

- A new `jsonQuote` function exists and is exported from `src/helpers/mysql.ts`.
- A new node test file `test/node/src/json-quote-mysql.test.ts` builds a `Kysely` instance using the MySQL adapter and query compiler together with `DummyDriver` (no real database connection or network), constructs `select` queries using `jsonQuote`, calls `.compile()`, and asserts on both the produced `sql` string and the `parameters` array for the scenarios above (column-ref arg, `eb.val` bound-parameter arg, and raw `sql` fragment arg).
- Existing tests continue to pass; no existing helper output changes.
- The following commands succeed from the repository root:

```bash
pnpm install
pnpm build
pnpm test:node:build
npx mocha --timeout 15000 test/node/dist/json-quote-mysql.test.js
```
