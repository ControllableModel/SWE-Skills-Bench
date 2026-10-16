# Task: Build an Asynchronous Username Reservation Validator

## Background

This repository (`fabian-hiller/valibot`) is the Valibot schema library, with its full public API exported from `library/src/index.ts`. We need a self-contained module that validates a requested username, where one of the checks (availability) depends on an injected asynchronous lookup rather than a purely synchronous rule.

## Files to Create/Modify

- `library/src/usernameReservation/usernameReservation.ts` (new) — the async validation function and the schema factory.
- `library/src/usernameReservation/index.ts` (new) — re-export the public surface of the module.
- `library/src/usernameReservation/usernameReservation.test.ts` (new) — the deterministic test suite described below.

Build the module using the library's own public API by importing from the package source root, e.g. `import * as v from '../index.ts';`. Do not add new third-party dependencies. The availability check is injected as a function parameter, so the test can supply a deterministic in-memory implementation — no real network or database.

## Requirements

Implement and export:

- A factory `buildUsernameSchema(isAvailable: (name: string) => Promise<boolean>)` that returns a schema incorporating the injected availability check.
- An async function `reserveUsername(input: unknown, isAvailable: (name: string) => Promise<boolean>)` that resolves to a discriminated result:
  - On success: `{ ok: true, username: <normalized name> }`.
  - On failure: `{ ok: false, messages: <array of message strings> }`.

`reserveUsername` must never reject/throw; it always resolves to one of the two shapes.

### Validation rules (applied in order)

- Input must be a string. Surrounding whitespace is trimmed and the value is lower-cased before any further checks and in the output.
- After normalization, length must be between 3 and 20 inclusive.
- May only contain ASCII lowercase letters, digits, and underscores.
- Finally, the normalized name must be reported available by the injected async check. If `isAvailable(name)` resolves `false`, validation fails with an "already taken" style message. The async availability check must only run after the synchronous rules pass.

### Expected Functionality

Given an `isAvailable` that resolves `true` for every name except `"taken"`:

- `reserveUsername("  Ada_99  ", isAvailable)` -> `{ ok: true, username: "ada_99" }` (trimmed + lower-cased).
- `reserveUsername("ab", isAvailable)` -> failure (too short); the synchronous failure means availability need not have been consulted.
- `reserveUsername("has space", isAvailable)` -> failure (illegal character).
- `reserveUsername("Taken", isAvailable)` -> failure after normalization to `"taken"` because the async check resolves `false`.
- `reserveUsername(42, isAvailable)` -> failure (not a string), no throw.
- A name that passes all sync rules and is available -> success with the normalized name.

### Expected Functionality (determinism)

The injected `isAvailable` lets the test fully control the async outcome, so the test is deterministic and uses no real I/O.

## Acceptance Criteria

- A module exists at `library/src/usernameReservation/usernameReservation.ts` exporting `buildUsernameSchema` and `reserveUsername`.
- The schema validates asynchronously: the availability decision comes from the injected `isAvailable` function, and `reserveUsername` is awaited to obtain its result.
- The normalized `username` in a success result is trimmed and lower-cased; a name unavailable per the injected check fails even though it passes all synchronous rules.
- `reserveUsername` always resolves (never rejects) to `{ ok: true, username }` or `{ ok: false, messages }` with a non-empty `messages` array on failure.
- The added test suite contains at least 10 distinct test cases (using an injected in-memory `isAvailable`) covering: a fully valid reservation, the trimming + lower-casing normalization, the too-short and too-long rejections, the illegal-character rejection, the not-a-string rejection, the unavailable-name (async-false) rejection, and confirmation that a name normalizing to an available value succeeds.
- The following command, run from the `library/` directory, passes with all tests green:

```bash
npx vitest run src/usernameReservation/usernameReservation.test.ts
```
