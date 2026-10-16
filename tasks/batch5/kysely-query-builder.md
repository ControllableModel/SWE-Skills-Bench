# Task: Add a jsonbBuildObject helper for PostgreSQL

## Background

Kysely's PostgreSQL helper module (`src/helpers/postgres.ts`) exposes `jsonBuildObject`, which compiles to the `json_build_object(...)` function (the `json` type). PostgreSQL also offers a binary-JSON variant, `jsonb_build_object(...)`, with no helper counterpart in the module. This task adds the `jsonb` variant.

## Files to Create/Modify

- `src/helpers/postgres.ts` (modify) — add and export a new `jsonbBuildObject` function.
- `test/node/src/jsonb-build-object-postgres.test.ts` (new) — deterministic compilation tests for the new function.

## Requirements

### Public API

The module must export a function named `jsonbBuildObject` accepting a single argument: a record (object) mapping string keys to `Expression<unknown>` values — exactly the same argument shape as the existing `jsonBuildObject`. It returns a single expression (a `RawBuilder`) that can be aliased with `.as(...)` and placed inside a `select(...)` callback.

The order of the object's keys MUST be preserved in the compiled output.

### Compiled SQL

The function must compile to PostgreSQL's `jsonb_build_object(<key0>, <val0>, <key1>, <val1>, ...)`:

- Each property key is emitted as a single-quoted string literal (e.g. `'first'`), inlined into the SQL text — keys must NOT become bound parameters.
- Each property value expression is compiled through Kysely's normal expression compilation: column references are double-quoted; `eb.val(...)` values become `$1`, `$2`, ... placeholders collected, in order, into the parameter list; raw `sql` fragments are emitted verbatim.
- Keys and values alternate (`key, value, key, value, ...`) in the object's key order, separated by `, `.

There must be exactly one pair of parentheses for the call.

### Type inference

Given an object whose properties are `{ k0: Expression<V0>, k1: Expression<V1>, ... }`, the result expression's value type must be `{ k0: <dehydrated V0>, k1: <dehydrated V1>, ... }`, consistent with how the existing `jsonBuildObject` derives its property value types.

### Constraints

- Do not introduce a new runtime dependency; reuse the primitives already imported by `src/helpers/postgres.ts`.
- Do not change the behavior, signature, or output of any existing exported helper (`jsonArrayFrom`, `jsonObjectFrom`, `jsonBuildObject`, `mergeAction`). In particular, `jsonBuildObject` must still emit `json_build_object`, not `jsonb_build_object`.
- Keep the module importable via `kysely/helpers/postgres`.

### Expected Functionality

- `jsonbBuildObject({ first: eb.ref('first_name'), last: eb.ref('last_name') })` aliased `name`, selected from `person` → `select jsonb_build_object('first', "first_name", 'last', "last_name") as "name" from "person"` with no parameters.
- `jsonbBuildObject({ greeting: eb.val('hi'), id: eb.ref('id') })` → `'hi'` becomes a `$1` placeholder in the parameter list while `'greeting'` and `'id'` stay inline.
- ``jsonbBuildObject({ full: sql`first_name || ' ' || last_name` })`` → the raw fragment is emitted verbatim as the value.

## Acceptance Criteria

- A new `jsonbBuildObject` function exists and is exported from `src/helpers/postgres.ts`.
- A new node test file `test/node/src/jsonb-build-object-postgres.test.ts` builds a `Kysely` instance using the PostgreSQL adapter and query compiler together with `DummyDriver` (no real database connection or network), constructs `select` queries using `jsonbBuildObject`, calls `.compile()`, and asserts on both the produced `sql` string and the `parameters` array for the scenarios above (column-ref values, `eb.val` bound-parameter value with inline keys, and raw `sql` fragment value).
- A test also confirms the existing `jsonBuildObject` still compiles to `json_build_object(...)` and is unchanged.
- Existing tests continue to pass.
- The following commands succeed from the repository root:

```bash
pnpm install
pnpm build
pnpm test:node:build
npx mocha --timeout 15000 test/node/dist/jsonb-build-object-postgres.test.js
```
