# Task: Add jsonBuildArray helpers for MySQL and MSSQL

## Background

Kysely ships per-dialect helper modules under `src/helpers/` (one file per database). The PostgreSQL and SQLite helpers already provide a positional `jsonBuildArray` for assembling a JSON array from an ordered list of expressions, but the MySQL (`src/helpers/mysql.ts`) and MS SQL Server (`src/helpers/mssql.ts`) helper modules do not. This task adds that positional helper to the MySQL and MSSQL modules.

## Files to Create/Modify

- `src/helpers/mysql.ts` (modify) — add and export a new `jsonBuildArray` function for MySQL.
- `src/helpers/mssql.ts` (modify) — add and export a new `jsonBuildArray` function for MSSQL.
- `test/node/src/json-build-array-mysql-mssql.test.ts` (new) — deterministic compilation tests for both new functions.

## Requirements

### Public API

Each module must export a function named `jsonBuildArray` taking a single argument: an array (tuple) of `Expression<unknown>` values — column references from an expression builder, `eb.val(...)` values, raw `sql` fragments, or nested helper results. It returns a single expression (a `RawBuilder`) that can be aliased with `.as(...)` and placed inside a `select(...)` callback exactly like the existing `jsonBuildObject` helper in the same module.

The produced argument order MUST follow the input array order, left to right.

### Compiled SQL

The function must compile to the dialect's native positional JSON-array function with every input expression compiled and emitted as a comma-separated argument in order:

- MySQL must emit `json_array(<arg0>, <arg1>, ...)`.
- MSSQL must emit `json_array(<arg0>, <arg1>, ...)`.

Each argument must be compiled through Kysely's normal expression compilation so that:

- Column references are rendered with the dialect's identifier quoting (backticks for MySQL, double quotes for MSSQL).
- Values passed via `eb.val(...)` are emitted as the dialect's parameter placeholder (`?` for MySQL; `@1`, `@2`, ... for MSSQL) and collected, in order, into the compiled query's parameter list — never inlined as literals.
- Raw `sql` fragments are emitted verbatim.

There must be exactly one pair of parentheses for the call and arguments separated by `, ` (comma + space) with no trailing separator.

### Type inference

The return type must reflect the element types of the input tuple: given expressions whose value types are `V0, V1, ...`, the result expression's value type must be an array whose elements are the union of the shallow-dehydrated value types of the inputs, consistent with how the same module's `jsonBuildObject` derives its value types.

### Constraints

- Do not introduce a new runtime dependency; reuse the primitives already imported by each helper module.
- Do not change the behavior, signature, or output of any existing exported helper in either module (`jsonArrayFrom`, `jsonObjectFrom`, `jsonBuildObject`, and MSSQL's other exports).
- Keep the two modules independently importable via `kysely/helpers/mysql` and `kysely/helpers/mssql`; no cross-imports between them.

### Expected Functionality

- `jsonBuildArray([eb.ref('first_name'), eb.ref('last_name')])` aliased `name`, selected from `person` → MySQL: ``select json_array(`first_name`, `last_name`) as `name` from `person` `` with no parameters.
- The same call under MSSQL → `select json_array("first_name", "last_name") as "name" from "person"` with no parameters.
- `jsonBuildArray([eb.ref('first_name'), eb.val('!')])` under MySQL → the second argument compiles to `?` and `'!'` appears in the parameter list, not the SQL text.
- ``jsonBuildArray([sql<number>`1 + 1`, eb.ref('id')])`` → the raw fragment `1 + 1` is emitted verbatim as the first argument.
- Three or more arguments are joined in input order with `, ` between each.

## Acceptance Criteria

- New `jsonBuildArray` functions exist and are exported from both `src/helpers/mysql.ts` and `src/helpers/mssql.ts`.
- A new node test file `test/node/src/json-build-array-mysql-mssql.test.ts` builds a `Kysely` instance per dialect using that dialect's adapter and query compiler together with `DummyDriver` (no real database connection or network), constructs `select` queries that use `jsonBuildArray`, calls `.compile()`, and asserts on both the produced `sql` string and the `parameters` array for the scenarios above (column-ref args, `eb.val` bound-parameter args, raw `sql` fragment args, and 3+ args), for both MySQL and MSSQL.
- Existing tests continue to pass; no existing helper output changes.
- The following commands succeed from the repository root:

```bash
pnpm install
pnpm build
pnpm test:node:build
npx mocha --timeout 15000 test/node/dist/json-build-array-mysql-mssql.test.js
```
