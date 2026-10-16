# Task: Add jsonBuildArray dialect helpers

## Background

Kysely ships a small set of database-specific helper functions under `src/helpers/` (one module per dialect) for assembling JSON values inside a query. The PostgreSQL and SQLite helper modules each already expose a `jsonBuildObject` function that turns a record of named expressions into a single JSON object expression, but neither offers a positional (array) counterpart. This task adds that counterpart for the PostgreSQL and SQLite dialects.

## Files to Create/Modify

- `src/helpers/postgres.ts` (modify) — add and export a new `jsonBuildArray` function for PostgreSQL.
- `src/helpers/sqlite.ts` (modify) — add and export a new `jsonBuildArray` function for SQLite.
- `test/node/src/json-build-array.test.ts` (new) — deterministic compilation tests for both new functions, placed alongside the other node tests.

## Requirements

### Public API

Each of the two helper modules must export a function named `jsonBuildArray`. The function accepts a single argument: a tuple (variadic-friendly array) of `Expression<unknown>` values, e.g. column references obtained from an expression builder, raw `sql` fragments, values produced by `eb.val(...)`, or nested helper results. It returns a single expression (a `RawBuilder`) that can be aliased with `.as(...)` and placed inside a `select(...)` callback exactly like the existing `jsonBuildObject` helper.

The argument order of the produced JSON array MUST follow the order of the input tuple, left to right.

### Compiled SQL

The function must compile to the dialect's native "build a JSON array from a positional argument list" SQL function, with every input expression compiled and emitted as a comma-separated argument in order:

- PostgreSQL must emit `json_build_array(<arg0>, <arg1>, ...)`.
- SQLite must emit `json_array(<arg0>, <arg1>, ...)`.

Each argument must be compiled through Kysely's normal expression compilation so that:
- Column references are rendered with the dialect's identifier quoting (double quotes for PostgreSQL, double quotes for SQLite).
- Values passed via `eb.val(...)` (or otherwise carried as bound parameters) are emitted as the dialect's parameter placeholder (`$1`, `$2`, ... for PostgreSQL; `?` for SQLite) and collected, in order, into the compiled query's parameter list — they must NOT be inlined as literals.
- Raw `sql` fragments are emitted verbatim as written.

There must be exactly one pair of parentheses for the function call and the arguments must be separated by `, ` (comma + space) with no trailing separator.

### Type inference

The return type must reflect the element types of the input tuple. Given a tuple of expressions whose value types are `V0, V1, ...`, the resulting expression's value type must be an array whose elements are the union of the (shallow-dehydrated) value types of the inputs — consistent with how the existing `jsonBuildObject` helper derives its object property value types from its inputs. An empty argument tuple is out of scope and need not be specially supported.

### Constraints

- Do not introduce a new runtime dependency; build the expression using the primitives already imported by the existing helper modules.
- Do not change the behavior, signature, or output of any existing exported helper (`jsonArrayFrom`, `jsonObjectFrom`, `jsonBuildObject`, `mergeAction`).
- The two modules must remain independently importable via their existing entry points (`kysely/helpers/postgres` and `kysely/helpers/sqlite`); no cross-imports between the two helper modules.

### Expected Functionality

- `jsonBuildArray([eb.ref('first_name'), eb.ref('last_name')])` aliased as `name`, selected from `person` → PostgreSQL: `select json_build_array("first_name", "last_name") as "name" from "person"` with no parameters.
- The same call under SQLite → `select json_array("first_name", "last_name") as "name" from "person"` with no parameters.
- `jsonBuildArray([eb.ref('first_name'), eb.val('!')])` under PostgreSQL → the second argument compiles to `$1` and `'!'` appears in the parameter list, not in the SQL text.
- `jsonBuildArray([sql<number>\`1 + 1\`, eb.ref('id')])` → the raw fragment `1 + 1` is emitted verbatim as the first argument.
- Three or more arguments are joined in input order with `, ` between each.

## Acceptance Criteria

- New `jsonBuildArray` functions exist and are exported from both `src/helpers/postgres.ts` and `src/helpers/sqlite.ts`.
- A new node test file `test/node/src/json-build-array.test.ts` builds a `Kysely` instance per dialect using that dialect's adapter/compiler together with `DummyDriver` (no real database connection or network), constructs `select` queries that use `jsonBuildArray`, calls `.compile()`, and asserts on both the produced `sql` string and the `parameters` array for the scenarios described above (column-ref args, `eb.val` bound-parameter args, raw `sql` fragment args, and 3+ args), for both PostgreSQL and SQLite.
- Existing tests continue to pass; no existing helper output changes.
- The following commands succeed from the repository root (building the library and the node test sources, then running only the new test file):

```bash
pnpm install
pnpm build
pnpm test:node:build
npx mocha --timeout 15000 test/node/dist/json-build-array.test.js
```
