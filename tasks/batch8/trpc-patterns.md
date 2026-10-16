# Task: Build a Registration Router with Deep Input Schemas

## Background

This repository is the tRPC monorepo. Its server package (`@trpc/server`) validates and parses each procedure's input through a schema before the body runs, and the in-process test suite exercises this through callers. This task adds a self-contained "registration" API whose procedures depend on a layered, refined input schema that both rejects malformed data and normalizes accepted data, plus a deterministic test.

## Files to Create/Modify

- `packages/tests/server/registration.ts` (new) — the module: an in-memory account store, the tRPC helpers, the router, and an exported caller factory.
- `packages/tests/server/registration.test.ts` (new) — the deterministic test importing only the public surface from `registration.ts`.

All implementation lives in `registration.ts`. The test must consume only the exported caller factory and exported types.

## Requirements

### Data Layer & Context

`registration.ts` keeps an in-memory store of accounts keyed by normalized email. Provide a factory producing a fresh store per call. The store is reachable inside procedures via context.

### Procedures

Expose a single root router nesting an `account` sub-router:

- `register` — input an object with `email`, `password`, `confirmPassword`, `age`, and an optional `profile` object `{ displayName?: string; tags?: string[] }`; creates an account and returns the stored, normalized account `{ email, age, profile }` (never the password).
- `exists` — input `{ email: string }`; returns `{ exists: boolean }` using the normalized email.
- `get` — input `{ email: string }`; returns the stored account; not-found if unknown.

### Input Schema & Normalization

The `register` input schema must enforce all of the following, rejecting any violation as a validation failure before the body runs:

- `email` is a syntactically valid email; it is normalized (trimmed and lowercased) before being used as the store key and in the returned account.
- `password` is a string of length `>= 8`; `confirmPassword` must equal `password` (a cross-field constraint), otherwise the input is rejected.
- `age` must be an integer `>= 13` and `<= 120`. A numeric string that represents a valid integer in range is accepted and coerced to a number; a value out of range or non-integer is rejected.
- `profile.tags`, when present, must be an array of non-empty strings with no duplicates after trimming; duplicates or empty entries are rejected.
- The returned account must never contain `password` or `confirmPassword`.

### Error Semantics

- All schema violations surface as a validation failure (a single distinguishable tRPC code) — never as an unhandled runtime crash.
- Registering an email (after normalization) that already exists → conflict.
- `get` for an unknown normalized email → not-found.
- Distinct categories use distinct tRPC codes.

### Expected Functionality

- `register` with valid data including `"  USER@Example.COM "` → succeeds; `exists({ email: "user@example.com" })` → `{ exists: true }`; the returned account's `email` is the normalized form and contains no password field.
- `register` with `confirmPassword` not matching `password` → validation failure.
- `register` with `age: 12` or `age: 200` or a fractional age → validation failure.
- `register` with `age: "30"` (numeric string in range) → accepted and stored as the number `30`.
- `register` with `profile.tags: ["a", "a"]` or `["", "b"]` → validation failure.
- A second `register` for the same normalized email → conflict.
- `get` for an unknown email → not-found.

## Acceptance Criteria

- A new module `packages/tests/server/registration.ts` exports a caller factory and router type built on `@trpc/server`, with a layered, refined input schema performing both rejection and normalization/coercion.
- A new test file `packages/tests/server/registration.test.ts` with at least 12 cases covering: email normalization affecting store keys and output, the password-confirmation cross-field rule, the age bounds and integer-string coercion, the tags de-duplication/empty rule, password never appearing in output, duplicate-registration conflict, and not-found on `get`.
- Tests assert on tRPC error **codes** where errors are expected.
- The following command passes:

  ```bash
  pnpm vitest run packages/tests/server/registration.test.ts
  ```

- A naive implementation that skips the cross-field and range checks, fails to normalize the email, leaks the password into the output, or ignores duplicates must fail the suite.
