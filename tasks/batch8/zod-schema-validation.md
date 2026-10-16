# Task: Build a Booking-Question Field Definition Validator

## Background

The cal.com booking-form builder (`packages/lib`) lets organizers define custom booking questions (text, number, select, multiselect, etc.) that attendees answer when booking. Each field definition comes from the form-builder UI as an untrusted object, so it must be validated and normalized before being saved to the event type. This task adds a reusable validator in the `@calcom/lib` package.

## Files to Create/Modify

- `packages/lib/bookingFieldSchema.ts` (new) — the validator module: schema(s), the public validation function, and exported types.
- `packages/lib/bookingFieldSchema.test.ts` (new) — the vitest suite covering the behavior below.

## Requirements

Implement and export from `packages/lib/bookingFieldSchema.ts`:

### Public API

- A function `parseBookingField(input: unknown)` returning a tagged result:
  - On success: `{ success: true; data: BookingField }` (normalized).
  - On failure: `{ success: false; errors: Record<string, string[]> }` mapping field names (including nested `"options.0.value"`) to non-empty arrays of messages.
  - It must never throw, including for non-object inputs.
- An exported TypeScript type `BookingField` derived from the schema (not a hand-written duplicate). The union of field variants must be type-narrowable by the `type` discriminant.

### Field rules (raw input -> normalized output)

A field definition is one of several variants chosen by a required `type` discriminant. Common fields on every variant:

- `name`: required; must match `^[a-zA-Z][a-zA-Z0-9_]*$`, 1–40 characters.
- `label`: required; 1–100 characters after trimming; trimmed in the output.
- `required`: optional boolean; defaults to `false` in the output when absent.

Variants:

- `type: "text"` — adds `maxLength`: optional, arrives as a string, must be an integer 1–500, and is a `number` in the output (omitted when absent).
- `type: "number"` — adds `min` and `max`: both optional, arrive as strings, must be integers, and are `number`s in the output (omitted when absent).
- `type: "select"` — adds `options`: required non-empty array of `{ label: string (1–100), value: string (1–60, matching `^[a-z0-9_-]+$`) }`.
- `type: "multiselect"` — same `options` rules as `select`, and adds `maxSelections`: optional, arrives as a string, must be an integer >= 1, is a `number` in the output (omitted when absent).
- Any other `type` value is rejected with an error reported on the `type` field.

### Cross-field and edge-case rules

- For `number`, when both `min` and `max` are present, `max` must be >= `min`; a violation is reported on the `max` field.
- For `select`/`multiselect`, the `value`s across all options must be unique; a duplicate is reported on the offending option's `value` (e.g. `options.2.value`).
- For `multiselect`, when present, `maxSelections` must not exceed the number of options; a violation is reported on `maxSelections`.
- Unknown keys (beyond those allowed for the resolved variant) must be rejected under their own key name.
- All violations must be collected and returned together.

### Expected Functionality

- A valid `text` field with `maxLength: "120"` -> `{ success: true }` with `data.type === "text"` and `data.maxLength === 120` (a number); `data.required === false` when omitted.
- A `number` field with `min: "5", max: "2"` -> `{ success: false }` with an error on `max`.
- A `select` field with two options sharing `value: "a"` -> `{ success: false }` with an error keyed at the second option's `value`.
- A field with `type: "rating"` -> `{ success: false }` with an error on `type`.
- `parseBookingField(null)` -> `{ success: false }` without throwing.

## Acceptance Criteria

- `packages/lib/bookingFieldSchema.ts` exports `parseBookingField` and the type `BookingField`.
- For valid input the numeric variant fields are real `number`s, absent optional fields are omitted, and `required` defaults to `false`.
- For invalid input the returned `errors` includes the invalid-`type` discriminant case, number min/max ordering, duplicate option values (indexed paths), maxSelections exceeding options, and unknown keys, with all simultaneous violations included.
- The function returns a failure result (never throws) for non-object inputs.
- The added test suite passes deterministically with no network/server/database access:

```
yarn vitest run packages/lib/bookingFieldSchema.test.ts
```
