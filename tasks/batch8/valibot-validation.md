# Task: Build a Profile Schema Family with Derived Views

## Background

This repository (`fabian-hiller/valibot`) is the Valibot schema library, with its full public API exported from `library/src/index.ts`. We need a self-contained module that defines one canonical `account` schema and derives several related schemas from it — a public view, a credential-free view, an editable-patch view, and an extended view — instead of redeclaring fields by hand.

## Files to Create/Modify

- `library/src/accountSchemas/accountSchemas.ts` (new) — the base schema, derived schemas, and validation functions.
- `library/src/accountSchemas/index.ts` (new) — re-export the public surface of the module.
- `library/src/accountSchemas/accountSchemas.test.ts` (new) — the deterministic test suite described below.

Build the module using the library's own public API by importing from the package source root, e.g. `import * as v from '../index.ts';`. Do not add new third-party dependencies.

## Requirements

Define a single base object schema `AccountSchema` and four derived schemas that MUST be obtained from it (not re-declared field-by-field), plus a small set of parsing functions.

### Base shape — `AccountSchema`

- `id` — integer `>= 1`.
- `username` — string, length 3..20.
- `email` — valid email string.
- `password` — string, length >= 8.
- `bio` — string, length <= 200.

### Derived schemas (must be built from `AccountSchema`)

1. `PublicAccountSchema` — contains only `id` and `username`.
2. `SafeAccountSchema` — contains every field of the base **except** `password`.
3. `AccountPatchSchema` — has the same fields as `SafeAccountSchema` but every field is optional (a partial update view; `id` is also optional here).
4. `ExtendedAccountSchema` — has every field of the base **plus** a new required `createdAt` field that must be a valid ISO date-time string.

### Exported functions

- `parsePublic(input: unknown)` — validates against `PublicAccountSchema`, returning the parsed object and throwing on failure.
- `parsePatch(input: unknown)` — validates against `AccountPatchSchema` the same way; an empty object `{}` is a valid patch.
- `parseExtended(input: unknown)` — validates against `ExtendedAccountSchema`.

Unknown keys are stripped by every schema.

### Expected Functionality

- `parsePublic({ id: 1, username: "ada" })` -> `{ id: 1, username: "ada" }`.
- `parsePublic({ id: 1, username: "ada", email: "a@b.io" })` -> succeeds but the result has no `email` key (the public schema does not carry it).
- `parsePublic({ id: 0, username: "ada" })` -> throws (`id` < 1).
- A full valid account parsed via `SafeAccountSchema` -> result has no `password` key.
- `parsePatch({})` -> `{}` (valid empty patch).
- `parsePatch({ username: "newname" })` -> `{ username: "newname" }`.
- `parsePatch({ username: "x" })` -> throws (still under min length when the field is present).
- `parseExtended({ id: 1, username: "ada", email: "a@b.io", password: "longenough", bio: "", createdAt: "2025-01-01T00:00:00.000Z" })` -> succeeds.
- `parseExtended` with a missing or malformed `createdAt` -> throws.

## Acceptance Criteria

- A module exists at `library/src/accountSchemas/accountSchemas.ts` exporting `AccountSchema`, the four derived schemas, and the three parse functions.
- `PublicAccountSchema`, `SafeAccountSchema`, `AccountPatchSchema`, and `ExtendedAccountSchema` are each derived from `AccountSchema` rather than re-declaring its field validators, and their resulting object keys match the specification (public = id+username; safe = all but password; patch = all-optional; extended = all + createdAt).
- The patch view accepts `{}` and validates any present field against the base rules; the public and safe views omit the dropped fields from their output; the extended view requires a valid ISO date-time `createdAt`.
- Every schema strips unknown keys; `parsePublic`/`parsePatch`/`parseExtended` throw on invalid input.
- The added test suite contains at least 10 distinct test cases covering: each derived schema's accepted shape, the omission of `password`/`email` in the safe/public outputs, the empty-patch acceptance, a present-but-invalid patch field, the `id >= 1` rule surviving into the derived views, the required `createdAt` on the extended view, and unknown-key stripping.
- The following command, run from the `library/` directory, passes with all tests green:

```bash
npx vitest run src/accountSchemas/accountSchemas.test.ts
```
