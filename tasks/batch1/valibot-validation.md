# Task: Build a Signup Payload Validation Module

## Background

This repository (`fabian-hiller/valibot`) is the Valibot schema library. The `library/` package exposes the full public API from `library/src/index.ts`. We need a small, self-contained feature module that uses this public API to validate and normalize the JSON payload submitted by a user-registration form, returning a clean, typed result that an HTTP handler can consume directly.

## Files to Create/Modify

- `library/src/signupForm/signupForm.ts` (new) — the validation module and its exported function(s)/schema.
- `library/src/signupForm/index.ts` (new) — re-export the public surface of the module.
- `library/src/signupForm/signupForm.test.ts` (new) — the deterministic test suite described in Acceptance Criteria.

Implement the module using the library's own public API by importing from the package source root, e.g. `import * as v from '../index.ts';`. Do not add new third-party dependencies.

## Requirements

Implement and export a function `validateSignup(input: unknown)` plus the underlying schema it uses. The function must take an arbitrary, untrusted value and return a discriminated result object:

- On success: `{ ok: true, data: <normalized payload> }`.
- On failure: `{ ok: false, errors: <field-keyed error map> }`, where `errors` is an object whose keys are the offending top-level field names and whose values are arrays of human-readable message strings for that field. Fields with no problem must not appear in the map. (Producing this map from the underlying validation issues is part of the task — do not hand-roll issue traversal if the library already offers a helper for collapsing nested issues into a field map.)

`validateSignup` must never throw for invalid input; it must always return one of the two shapes above.

### Input contract

The raw payload is expected to look like:

```json
{
  "username": "  Ada_Lovelace  ",
  "email": "ADA@Example.COM ",
  "age": "37",
  "role": "admin",
  "password": "hunter2hunter2",
  "confirmPassword": "hunter2hunter2",
  "tags": ["math", "engineering"]
}
```

### Field rules

#### `username` (required)
- Must be a string. Surrounding whitespace is insignificant and must be removed before any further checks and before it appears in the output.
- After trimming, length must be between 3 and 20 characters inclusive.
- May only contain ASCII letters, digits, and underscores. Any other character is rejected.

#### `email` (required)
- Must be a string. Surrounding whitespace is insignificant and must be removed; the value must be lower-cased before validation and in the output.
- After normalization it must be a syntactically valid email address.

#### `age` (required)
- Arrives as a string in the raw payload but the normalized output must hold a numeric `age`.
- The numeric value must be a whole number between 13 and 120 inclusive.
- Non-numeric strings, fractional values, and out-of-range values are rejected.

#### `role` (optional)
- When present, must be exactly one of `"admin"`, `"editor"`, or `"viewer"`. Any other string is rejected.
- When absent or `undefined`, the normalized output must contain `role: "viewer"`.

#### `password` / `confirmPassword` (required)
- Both must be strings of at least 10 characters.
- `password` must contain at least one ASCII uppercase letter and at least one digit. (Note the example payload above intentionally violates the uppercase rule.)
- The two fields must be equal. When they differ, the resulting error map must report this problem under the `confirmPassword` key (not under `password`).

#### `tags` (optional)
- When present, must be an array of strings with at most 5 entries; an empty array is allowed only by omitting the field.
- When absent, the normalized output must contain `tags: []`.

### Normalized output shape

On success, `data` must contain exactly: `username` (trimmed string), `email` (trimmed + lower-cased string), `age` (number), `role` (string, defaulted), `password` (string), `confirmPassword` (string), and `tags` (string array, defaulted). Unknown extra keys in the raw payload must not appear in `data`.

### Expected Functionality

- The example payload above -> failure: the error map contains a `password` entry (missing uppercase). All other fields are valid, so no other keys appear.
- `{ username: "  bob  ", email: "B@X.io", age: "20", password: "Abcdefghi9", confirmPassword: "Abcdefghi9" }` -> success with `data.username === "bob"`, `data.email === "b@x.io"`, `data.age === 20` (number), `data.role === "viewer"`, `data.tags` deep-equals `[]`.
- `{ ...validPayload, confirmPassword: "Different99X" }` -> failure with an error map that has a `confirmPassword` key and no `password` key.
- `{ ...validPayload, age: "9" }` -> failure with an `age` key.
- `{ ...validPayload, role: "superuser" }` -> failure with a `role` key.
- `42`, `null`, `"hello"`, and `undefined` -> failure (no throw), with a non-empty error map.

## Acceptance Criteria

- A new module exists at `library/src/signupForm/signupForm.ts` exporting `validateSignup` and the schema it is built on.
- `validateSignup` returns `{ ok: true, data }` for every valid payload and `{ ok: false, errors }` for every invalid one, never throwing.
- The normalized `data` reflects trimming, lower-casing, the string-to-number conversion of `age`, the defaulting of `role` and `tags`, and the stripping of unknown keys, exactly as specified.
- The `errors` map is keyed by top-level field name with arrays of message strings, omits valid fields, and reports the password-mismatch problem under `confirmPassword`.
- The added test suite contains at least 10 distinct test cases covering: each field's success and failure paths, the type conversion of `age`, the defaults for `role` and `tags`, unknown-key stripping, the cross-field mismatch routing, and non-object/null/undefined inputs.
- The following command, run from the `library/` directory, passes with all tests green:

```bash
npx vitest run src/signupForm/signupForm.test.ts
```
