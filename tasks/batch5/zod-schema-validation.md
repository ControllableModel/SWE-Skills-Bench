# Task: Build a Recurring-Event Rule Validator

## Background

The cal.com scheduling core (`packages/lib`) supports recurring event types (a daily/weekly/monthly series with a fixed occurrence count). The recurrence rule is submitted from a settings form where the interval and count arrive as strings, so it must be validated and normalized before being stored. This task adds a reusable validator in the `@calcom/lib` package.

## Files to Create/Modify

- `packages/lib/recurringRuleSchema.ts` (new) — the validator module: schema(s), the public validation function, and exported types.
- `packages/lib/recurringRuleSchema.test.ts` (new) — the vitest suite covering the behavior below.

## Requirements

Implement and export from `packages/lib/recurringRuleSchema.ts`:

### Public API

- A function `parseRecurringRule(input: unknown)` returning a tagged result:
  - On success: `{ success: true; data: RecurringRule }` (normalized).
  - On failure: `{ success: false; errors: Record<string, string[]> }` mapping field names to non-empty arrays of messages.
  - It must never throw, including for non-object inputs.
- An exported TypeScript type `RecurringRule` derived from the schema (not a hand-written duplicate).

### Field rules (raw input -> normalized output)

- `freq`: required; one of `"DAILY"`, `"WEEKLY"`, `"MONTHLY"`. Input may be lowercase (`"weekly"`) and is uppercased in the output.
- `interval`: arrives as a string (e.g. `"2"`); must be an integer between 1 and 12 inclusive, and is a `number` in the output.
- `count`: arrives as a string; must be an integer between 1 and 24 inclusive, and is a `number` in the output.
- `byWeekday`: optional array of strings each one of `"MO"`,`"TU"`,`"WE"`,`"TH"`,`"FR"`,`"SA"`,`"SU"`; duplicates must be collapsed (first-seen order preserved) in the output. When absent it is omitted.

### Cross-field and edge-case rules

- The total span (`interval * count`) of the series must not exceed 365 (in the unit implied by `freq`: days for DAILY, weeks for WEEKLY, months for MONTHLY is not converted — the raw product of `interval * count` is what is bounded). If `interval * count > 365`, the error is reported on the `count` field.
- `byWeekday` is only meaningful when `freq === "WEEKLY"`; if `byWeekday` is present while `freq` is not `"WEEKLY"`, it is rejected with the error reported on the `byWeekday` field.
- Unknown top-level keys must be rejected under their own key name.
- All violations must be collected and returned together.

### Expected Functionality

- `{ freq: "weekly", interval: "1", count: "5", byWeekday: ["MO","MO","WE"] }` -> `{ success: true }` with `data.freq === "WEEKLY"`, `data.interval === 1`, `data.count === 5`, and `data.byWeekday === ["MO","WE"]`.
- `{ freq: "DAILY", interval: "30", count: "20" }` -> `{ success: false }` with an error on `count` (product 600 > 365).
- `{ freq: "DAILY", interval: "1", count: "5", byWeekday: ["MO"] }` -> `{ success: false }` with an error on `byWeekday`.
- `{ freq: "yearly", interval: "1", count: "5" }` -> `{ success: false }` with an error on `freq`.
- `parseRecurringRule(null)` -> `{ success: false }` without throwing.

## Acceptance Criteria

- `packages/lib/recurringRuleSchema.ts` exports `parseRecurringRule` and the type `RecurringRule`.
- For valid input `data.freq` is uppercased, `interval` and `count` are numbers, `byWeekday` is deduplicated, and absent `byWeekday` is omitted.
- For invalid input the returned `errors` includes out-of-range interval/count, the `interval*count > 365` span violation on `count`, the `byWeekday`-without-WEEKLY violation, invalid freq, and unknown keys, with all simultaneous violations included.
- The function returns a failure result (never throws) for non-object inputs.
- The added test suite passes deterministically with no network/server/database access:

```
yarn vitest run packages/lib/recurringRuleSchema.test.ts
```
