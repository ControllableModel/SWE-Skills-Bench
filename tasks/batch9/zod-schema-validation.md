# Task: Build a Workflow Reminder Step Validator

## Background

The cal.com workflows feature (`packages/lib`) lets organizers attach automated reminder steps (email or SMS) that fire relative to a booking's start time. Each step is configured in the workflow editor and arrives as an untrusted object where the timing offset is string-ish, so it must be validated and normalized before being saved. This task adds a reusable validator in the `@calcom/lib` package.

## Files to Create/Modify

- `packages/lib/workflowStepSchema.ts` (new) — the validator module: schema(s), the public validation function, and exported types.
- `packages/lib/workflowStepSchema.test.ts` (new) — the vitest suite covering the behavior below.

## Requirements

Implement and export from `packages/lib/workflowStepSchema.ts`:

### Public API

- A function `parseWorkflowStep(input: unknown)` returning a tagged result:
  - On success: `{ success: true; data: WorkflowStep }` (normalized).
  - On failure: `{ success: false; errors: Record<string, string[]> }` mapping field names (including nested `"timing.value"`) to non-empty arrays of messages.
  - It must never throw, including for non-object inputs.
- An exported TypeScript type `WorkflowStep` derived from the schema (not a hand-written duplicate). The `action` discriminant must narrow the variant.

### Field rules (raw input -> normalized output)

A step is one of two variants selected by a required `action` discriminant. Common fields:

- `timing`: required object with:
  - `when`: one of `"BEFORE"` or `"AFTER"` (relative to booking start).
  - `unit`: one of `"MINUTE"`, `"HOUR"`, `"DAY"`.
  - `value`: arrives as a string; must be an integer >= 1, and is a `number` in the output.
- `sendTo`: optional; one of `"ATTENDEE"` or `"ORGANIZER"`; defaults to `"ATTENDEE"` in the output.

Variants:

- `action: "EMAIL"` — adds `subject` (required, 1–120 chars after trimming, trimmed) and `body` (required, 1–2000 chars after trimming, trimmed).
- `action: "SMS"` — adds `body` (required, 1–320 chars after trimming, trimmed); no `subject` field is used.
- Any other `action` value is rejected with an error reported on the `action` field.

### Cross-field and edge-case rules

- The total offset must not exceed 30 days. Convert `timing.value` to minutes using `unit` (`MINUTE`=1, `HOUR`=60, `DAY`=1440); if the result exceeds `30 * 1440` minutes, the error is reported on `timing.value`.
- For `action: "SMS"`, the offset (in the same minute conversion) must be at least 5 minutes; otherwise an error is reported on `timing.value`.
- Unknown keys (beyond those allowed for the resolved variant) must be rejected under their own key name.
- All violations must be collected and returned together.

### Expected Functionality

- A valid `EMAIL` step with `timing: { when: "BEFORE", unit: "HOUR", value: "2" }` -> `{ success: true }` with `data.action === "EMAIL"`, `data.timing.value === 2` (a number), and `data.sendTo === "ATTENDEE"` when omitted.
- A step with `timing: { when: "BEFORE", unit: "DAY", value: "40" }` -> `{ success: false }` with an error on `timing.value` (exceeds 30 days).
- An `SMS` step with `timing: { unit: "MINUTE", value: "1", when: "BEFORE" }` -> `{ success: false }` with an error on `timing.value` (under 5 minutes).
- A step with `action: "PUSH"` -> `{ success: false }` with an error on `action`.
- `parseWorkflowStep(null)` -> `{ success: false }` without throwing.

## Acceptance Criteria

- `packages/lib/workflowStepSchema.ts` exports `parseWorkflowStep` and the type `WorkflowStep`.
- For valid input `data.timing.value` is a `number`, `subject`/`body` are trimmed, and `sendTo` defaults to `"ATTENDEE"`.
- For invalid input the returned `errors` includes the invalid-`action` discriminant case, the 30-day cap on `timing.value`, the SMS 5-minute floor, and unknown keys, with all simultaneous violations included.
- The function returns a failure result (never throws) for non-object inputs.
- The added test suite passes deterministically with no network/server/database access:

```
yarn vitest run packages/lib/workflowStepSchema.test.ts
```
