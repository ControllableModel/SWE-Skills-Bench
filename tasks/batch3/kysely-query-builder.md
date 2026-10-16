# Task: Add a toJson single-expression helper for PostgreSQL

## Background

Kysely's PostgreSQL helper module (`src/helpers/postgres.ts`) already exposes subquery-oriented JSON helpers (`jsonArrayFrom`, `jsonObjectFrom`) and the builder `jsonBuildObject`, but it has no helper that wraps a single arbitrary expression with the PostgreSQL `to_json` scalar function. This task adds that scalar helper.

## Files to Create/Modify

- `src/helpers/postgres.ts` (modify) — add and export a new `toJson` function.
- `test/node/src/to-json-postgres.test.ts` (new) — deterministic compilation tests for the new function.

## Requirements

### Public API

The module must export a function named `toJson` that accepts a single `Expression<unknown>` argument (a column reference, an `eb.val(...)` value, a raw `sql` fragment, or a nested helper result) and returns a single expression (a `RawBuilder`) that can be aliased with `.as(...)` and placed inside a `select(...)` callback, exactly like the other helpers in the module.

### Compiled SQL

The function must compile to PostgreSQL's `to_json(<arg>)` with the single input expression compiled and emitted as the sole argument:

- A column reference is rendered with PostgreSQL identifier quoting (double quotes), e.g. `to_json("data")`.
- A value passed via `eb.val(...)` is emitted as a parameter placeholder (`$1`, `$2`, ...) and collected into the compiled query's parameter list — never inlined as a literal.
- A raw `sql` fragment is emitted verbatim inside the parentheses.

There must be exactly one pair of parentheses and exactly one argument; no comma separators.

### Type inference

Given an input expression whose value type is `V`, the result expression's value type must be the shallow-dehydrated form of `V` (consistent with how the existing helpers in this module derive their value types). The exported function must not be `any`-typed.

### Constraints

- Do not introduce a new runtime dependency; reuse the primitives already imported by `src/helpers/postgres.ts`.
- Do not change the behavior, signature, or output of any existing exported helper (`jsonArrayFrom`, `jsonObjectFrom`, `jsonBuildObject`, `mergeAction`).
- Keep the module importable via `kysely/helpers/postgres`.

### Expected Functionality

- `toJson(eb.ref('data'))` aliased `doc`, selected from `person` → `select to_json("data") as "doc" from "person"` with no parameters.
- `toJson(eb.val(42))` aliased `n` → the argument compiles to `$1` and `42` appears in the parameter list, not in the SQL text.
- ``toJson(sql`now()`)`` → emits `to_json(now())` verbatim with no parameters.
- The call inside a `select((eb) => [...])` callback composes with other selected columns without altering their output.

## Acceptance Criteria

- A new `toJson` function exists and is exported from `src/helpers/postgres.ts`.
- A new node test file `test/node/src/to-json-postgres.test.ts` builds a `Kysely` instance using the PostgreSQL adapter and query compiler together with `DummyDriver` (no real database connection or network), constructs `select` queries using `toJson`, calls `.compile()`, and asserts on both the produced `sql` string and the `parameters` array for the scenarios above (column-ref arg, `eb.val` bound-parameter arg, and raw `sql` fragment arg).
- Existing tests continue to pass; no existing helper output changes.
- The following commands succeed from the repository root:

```bash
pnpm install
pnpm build
pnpm test:node:build
npx mocha --timeout 15000 test/node/dist/to-json-postgres.test.js
```
