# Task: Build an Availability Time-Range Validator

## Background

The cal.com scheduling core (`packages/lib`) stores each user's weekly availability as a set of day/time ranges submitted from the availability settings UI. The raw payload comes from form/query data where times are strings, so it must be validated and normalized before being saved. This task adds a reusable validator in the `@calcom/lib` package.

## Files to Create/Modify

- `packages/lib/availabilityRangeSchema.ts` (new) — the validator module: schema(s), the public validation function, and exported types.
- `packages/lib/availabilityRangeSchema.test.ts` (new) — the vitest suite covering the behavior below.

## Requirements

Implement and export from `packages/lib/availabilityRangeSchema.ts`:

### Public API

- A function `parseAvailabilityPayload(input: unknown)` returning a tagged result:
  - On success: `{ success: true; data: AvailabilityPayload }` (normalized).
  - On failure: `{ success: false; errors: Record<string, string[]> }` whose keys are field paths (including indexed nested paths such as `"slots.0.end"`) mapping to non-empty arrays of messages.
  - It must never throw, including for non-object inputs.
- An exported TypeScript type `AvailabilityPayload` derived from the schema (not a hand-written duplicate).

### Field rules (raw input -> normalized output)

- `timeZone`: required non-empty string after trimming; trimmed in the output.
- `slots`: required non-empty array. Each slot is an object with:
  - `weekday`: arrives as a string (e.g. `"0"`–`"6"`) or number; must be an integer 0–6 inclusive and is a `number` in the output.
  - `start`: required `"HH:MM"` 24-hour string (`"09:00"`); minutes and hours must be in valid range.
  - `end`: required `"HH:MM"` 24-hour string.
- `overrides`: optional array of objects each with `date` (required `"YYYY-MM-DD"` string) and `available` (boolean). When absent it is omitted from the output.

### Cross-field and edge-case rules

- Within each slot, `end` must be strictly later than `start` (compared as minutes-since-midnight); a violation is reported on that slot's `end` field (e.g. `"slots.1.end"`).
- Two slots in the same payload that share the same `weekday` and have overlapping time ranges must be rejected; the overlap error is reported on the later slot's `start` field.
- Unknown top-level keys must be rejected under their own key name.
- All violations must be collected and returned together.

### Expected Functionality

- A valid payload with `weekday: "1"` and `start: "09:00", end: "17:00"` -> `{ success: true }` with `data.slots[0].weekday === 1` (a number).
- A slot with `start: "17:00", end: "09:00"` -> `{ success: false }` with an error on that slot's `end`.
- Two `weekday: 2` slots `"09:00"-"12:00"` and `"11:00"-"13:00"` -> `{ success: false }` with an overlap error on the second slot's `start`.
- A slot `start: "25:00"` -> `{ success: false }` with an error on that slot's `start`.
- `parseAvailabilityPayload("nope")` -> `{ success: false }` without throwing.

## Acceptance Criteria

- `packages/lib/availabilityRangeSchema.ts` exports `parseAvailabilityPayload` and the type `AvailabilityPayload`.
- For valid input each slot's `weekday` is a `number`, `timeZone` is trimmed, and absent `overrides` is omitted.
- For invalid input the returned `errors` uses indexed paths (e.g. `slots.0.end`, `slots.1.start`) and includes all simultaneous violations, including end<=start, same-weekday overlaps, out-of-range times, and unknown keys.
- The function returns a failure result (never throws) for non-object inputs.
- The added test suite passes deterministically with no network/server/database access:

```
yarn vitest run packages/lib/availabilityRangeSchema.test.ts
```
