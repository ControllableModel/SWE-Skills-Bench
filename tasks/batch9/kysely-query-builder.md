# Task: Add a jsonMergePatch helper for MySQL

## Background

Kysely's MySQL helper module (`src/helpers/mysql.ts`) provides JSON object and aggregation helpers, but has no helper for MySQL's `json_merge_patch(...)` function, which merges two or more JSON documents using RFC 7396 patch semantics. This task adds that variadic helper.

## Files to Create/Modify

- `src/helpers/mysql.ts` (modify) — add and export a new `jsonMergePatch` function.
- `test/node/src/json-merge-patch-mysql.test.ts` (new) — deterministic compilation tests for the new function.

## Requirements

### Public API

The module must export a function named `jsonMergePatch` accepting a single argument: an array (tuple) of `Expression<unknown>` documents (column references, `eb.val(...)` values, raw `sql` fragments, or nested helper results). It returns a single expression (a `RawBuilder`) that can be aliased with `.as(...)` and placed inside a `select(...)` callback.

The argument order MUST follow the input array order, left to right.

### Compiled SQL

The function must compile to MySQL's `json_merge_patch(<arg0>, <arg1>, ...)` with every input expression compiled and emitted as a comma-separated argument in order:

- Column references are rendered with MySQL identifier quoting (backticks).
- `eb.val(...)` values are emitted as `?` placeholders and collected, in order, into the parameter list — never inlined as literals.
- Raw `sql` fragments are emitted verbatim.

There must be exactly one pair of parentheses, arguments separated by `, ` with no trailing separator. At least two arguments are the realistic case; a single-argument call must still compile to a valid `json_merge_patch(<arg0>)`.

### Type inference

The result expression's value type must be a single object/record value type derived from the inputs (an unknown-keyed JSON object is acceptable; the function must not be `any`-typed and must accept any tuple of `Expression<unknown>`).

### Constraints

- Do not introduce a new runtime dependency; reuse the primitives already imported by `src/helpers/mysql.ts`.
- Do not change the behavior, signature, or output of any existing exported helper (`jsonArrayFrom`, `jsonObjectFrom`, `jsonBuildObject`).
- Keep the module importable via `kysely/helpers/mysql`.

### Expected Functionality

- `jsonMergePatch([eb.ref('a'), eb.ref('b')])` aliased `merged`, selected from `person` → ``select json_merge_patch(`a`, `b`) as `merged` from `person` `` with no parameters.
- ``jsonMergePatch([eb.ref('a'), eb.val('{"x":1}')])`` → the second argument compiles to `?` and `'{"x":1}'` appears in the parameter list, not in the SQL text.
- ``jsonMergePatch([sql`'{}'`, eb.ref('a'), eb.ref('b')])`` → three arguments joined in input order with `, ` between each, the raw fragment emitted verbatim first.

## Acceptance Criteria

- A new `jsonMergePatch` function exists and is exported from `src/helpers/mysql.ts`.
- A new node test file `test/node/src/json-merge-patch-mysql.test.ts` builds a `Kysely` instance using the MySQL adapter and query compiler together with `DummyDriver` (no real database connection or network), constructs `select` queries using `jsonMergePatch`, calls `.compile()`, and asserts on both the produced `sql` string and the `parameters` array for the scenarios above (two column-ref args, a column-ref + `eb.val` bound-parameter arg, and three args with a raw `sql` fragment).
- Existing tests continue to pass; no existing helper output changes.
- The following commands succeed from the repository root:

```bash
pnpm install
pnpm build
pnpm test:node:build
npx mocha --timeout 15000 test/node/dist/json-merge-patch-mysql.test.js
```
