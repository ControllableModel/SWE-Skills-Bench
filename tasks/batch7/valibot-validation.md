# Task: Build a Field-Error Reporter for a Booking Form

## Background

This repository (`fabian-hiller/valibot`) is the Valibot schema library, with its full public API exported from `library/src/index.ts`. We need a self-contained module that validates a hotel-booking request and, on failure, produces a UI-friendly report that maps each dotted field path to its error messages — without ever throwing.

## Files to Create/Modify

- `library/src/bookingForm/bookingForm.ts` (new) — the validation function, schema, and report builder.
- `library/src/bookingForm/index.ts` (new) — re-export the public surface of the module.
- `library/src/bookingForm/bookingForm.test.ts` (new) — the deterministic test suite described below.

Build the module using the library's own public API by importing from the package source root, e.g. `import * as v from '../index.ts';`. Do not add new third-party dependencies.

## Requirements

Implement and export a function `validateBooking(input: unknown)` plus the underlying schema. The function must return a discriminated result:

- On success: `{ ok: true, data: <validated booking> }`.
- On failure: `{ ok: false, fieldErrors: <map from dotted path to message-array> }`.

`validateBooking` must never throw. The `fieldErrors` keys must be the dotted path strings (e.g. `"guest.email"`, `"nights"`) identifying the precise location of each issue, and the values must be arrays of message strings. Building the path strings from the validation issues is part of the task — derive them from the issues' path information; do not hardcode a flat key list.

### Input contract (nested)

```json
{
  "guest": { "name": "Ada", "email": "ada@host.io" },
  "nights": 3,
  "roomType": "deluxe",
  "checkIn": "2025-06-01"
}
```

### Field rules

- `guest.name` — string, trimmed, length 2..60 after trimming.
- `guest.email` — valid email string (lower-cased in the output).
- `nights` — integer in the inclusive range 1 to 30.
- `roomType` — one of `"standard"`, `"deluxe"`, `"suite"`.
- `checkIn` — string in ISO date format `YYYY-MM-DD`.

### Output shape

On success, `data` is the validated booking with `guest.name` trimmed and `guest.email` lower-cased; unknown keys (at top level and inside `guest`) are stripped. On failure, `fieldErrors` maps each offending dotted path to its messages and omits valid fields.

### Expected Functionality

- The example payload above -> success.
- `{ guest: { name: "A", email: "x" }, nights: 0, roomType: "loft", checkIn: "06/01/2025" }` -> failure whose `fieldErrors` has keys for `guest.name`, `guest.email`, `nights`, `roomType`, and `checkIn`.
- `{ guest: { name: "Ada", email: "BAD" }, nights: 3, roomType: "suite", checkIn: "2025-06-01" }` -> failure with a `guest.email` key and no other keys.
- `{ guest: { name: "Ada", email: "ada@host.io" }, nights: 40, roomType: "suite", checkIn: "2025-06-01" }` -> failure with only a `nights` key.
- A valid payload with `guest.email: "ADA@HOST.IO"` -> success with `data.guest.email === "ada@host.io"`.
- A valid payload carrying an extra top-level key -> success with that key absent from `data`.
- `null`, `42`, `"x"` -> failure (no throw) with a non-empty `fieldErrors`.

## Acceptance Criteria

- A module exists at `library/src/bookingForm/bookingForm.ts` exporting `validateBooking` and its schema.
- `validateBooking` returns `{ ok: true, data }` for valid bookings and `{ ok: false, fieldErrors }` for invalid ones, never throwing on any input.
- `fieldErrors` is keyed by dotted field path (including nested paths such as `guest.email`) with arrays of message strings, and omits valid fields.
- The validated `data` reflects trimming of `guest.name`, lower-casing of `guest.email`, and stripping of unknown keys at the top level and inside `guest`.
- The added test suite contains at least 10 distinct test cases covering: the full valid path, a multi-error failure asserting the exact set of dotted keys, the nested `guest.email` path appearing as `"guest.email"`, single-field failures, the email lower-casing, unknown-key stripping, and non-object inputs.
- The following command, run from the `library/` directory, passes with all tests green:

```bash
npx vitest run src/bookingForm/bookingForm.test.ts
```
