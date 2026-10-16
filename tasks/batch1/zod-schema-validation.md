# Task: Build a Booking Import Payload Validator

## Background

The cal.com codebase (`packages/lib`) lets operators bulk-import historical bookings from external calendar exports. Raw import rows arrive from CSV/form sources where every field is a string and the shape varies by meeting type, so they must be validated and normalized into a clean, strongly-typed object before being persisted. This task adds a reusable validator utility in the `@calcom/lib` package.

## Files to Create/Modify

- `packages/lib/bookingImportSchema.ts` (new) — the validator module: schema(s), the public validation function, and exported types.
- `packages/lib/bookingImportSchema.test.ts` (new) — the vitest suite covering the behavior below.

## Requirements

Implement and export from `packages/lib/bookingImportSchema.ts`:

### Public API

- A function `parseBookingImportRow(input: unknown)` that validates a single raw import row and returns a tagged result object:
  - On success: `{ success: true; data: BookingImportRow }` where `data` is the normalized row.
  - On failure: `{ success: false; errors: Record<string, string[]> }` where the keys are field names (including nested locations such as `"attendee.email"` / `"location.url"`) and each value is the list of human-readable messages for that field. The function must never throw on invalid input, including non-object inputs like `null`, a string, or a number.
- An exported TypeScript type `BookingImportRow` that is derived from the schema (it must not be a hand-written `interface`/`type` duplicate of the field shape — changing a schema field must change the type automatically).

### Field rules (raw input -> normalized output)

A raw row is an object with string-ish fields originating from a CSV/form export:

- `title`: required, after trimming must be 1–200 characters. Surrounding whitespace is trimmed in the output.
- `startTime`: required ISO-8601 datetime string; normalized to a `Date` in the output.
- `durationMinutes`: arrives as a string (e.g. `"30"`); must represent an integer between 5 and 1440 inclusive, and is an actual `number` in the output.
- `attendee`: required object with:
  - `name`: required, 1–100 characters after trimming.
  - `email`: required, must be a valid email; lowercased in the output.
- `paid`: optional flag arriving as a string `"true"`/`"false"` (or already boolean); normalized to a `boolean` in the output and defaulting to `false` when absent.
- `location`: required, and its accepted shape depends on a `type` field:
  - `type: "inPerson"` requires an `address` (non-empty string after trimming); no `url` is allowed/used.
  - `type: "link"` requires a `url` that is a valid URL (`http`/`https`); no `address` is used.
  - `type: "phone"` requires a `phone` (non-empty string after trimming); no other fields are used.
  - Any other `type` value is rejected with an error reported on the `location.type` field.

### Cross-field and edge-case rules

- The import row must reject when `durationMinutes` would push the meeting end past `endTime` if an optional `endTime` (ISO-8601) field is provided; i.e. if both `startTime`+`durationMinutes` and `endTime` are present, the computed end (`startTime + durationMinutes`) must equal `endTime` (to the minute). Mismatches are reported on the `endTime` field. When `endTime` is omitted, this check is skipped.
- Unknown top-level keys in the input must be rejected (not silently dropped), with the error reported under that unknown key's name.
- All field violations in a single input must be collected and returned together — the function must not stop at the first error.

### Expected Functionality

- A fully valid `link`-type row -> `{ success: true, data }` with `startTime` as a `Date`, `durationMinutes` as a `number`, `attendee.email` lowercased, and `paid` defaulting to `false` when omitted.
- A valid `inPerson` row missing `address` -> `{ success: false }` with an `"location.address"` (or `"address"`-scoped) error message present.
- A row whose `location.type` is `"zoom"` -> `{ success: false }` with an error keyed at `location.type`.
- A row with `durationMinutes: "3"` and a bad `attendee.email` -> `{ success: false }` whose `errors` contains entries for both `durationMinutes` and `attendee.email`.
- A row with an extra `foo` key -> `{ success: false }` with `foo` present in `errors`.
- `parseBookingImportRow(null)` and `parseBookingImportRow("oops")` -> `{ success: false }` without throwing.

## Acceptance Criteria

- `packages/lib/bookingImportSchema.ts` exports `parseBookingImportRow` and the type `BookingImportRow`.
- For valid input the returned `data` has `startTime` typed/valued as a `Date`, `durationMinutes` as a `number`, `paid` as a `boolean` (default `false`), and `attendee.email` lowercased.
- For invalid input the returned `errors` object maps offending field names (including nested `attendee.email`, `location.url`, `location.type`, and unknown keys) to non-empty arrays of message strings, with all simultaneous violations included.
- The function returns a failure result (never throws) for non-object inputs.
- The added test suite passes deterministically with no network/server/database access:

```
yarn vitest run packages/lib/bookingImportSchema.test.ts
```
