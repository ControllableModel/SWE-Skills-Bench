# Task: Build a Webhook Subscription Payload Validator

## Background

The cal.com platform (`packages/lib`) lets users register outgoing webhooks that fire on booking lifecycle events. Webhook subscriptions are created from an untrusted JSON request body (API or settings form), so a raw subscription object must be validated and normalized before it is stored. This task adds a reusable validator in the `@calcom/lib` package.

## Files to Create/Modify

- `packages/lib/webhookSubscriptionSchema.ts` (new) — the validator module: schema(s), the public validation function, and exported types.
- `packages/lib/webhookSubscriptionSchema.test.ts` (new) — the vitest suite covering the behavior below.

## Requirements

Implement and export from `packages/lib/webhookSubscriptionSchema.ts`:

### Public API

- A function `parseWebhookSubscription(input: unknown)` that validates a raw subscription and returns a tagged result:
  - On success: `{ success: true; data: WebhookSubscription }` (normalized).
  - On failure: `{ success: false; errors: Record<string, string[]> }` where keys are field names (including nested ones such as `"payloadTemplate.format"`) and each value is a non-empty array of human-readable messages.
  - It must never throw, including for non-object inputs (`null`, a string, a number, an array).
- An exported TypeScript type `WebhookSubscription` derived from the schema (not a hand-written duplicate — editing a schema field must change the type automatically).

### Field rules (raw input -> normalized output)

- `subscriberUrl`: required; must be a valid `https://` URL (plain `http://` is rejected). Surrounding whitespace is trimmed in the output.
- `eventTriggers`: required non-empty array; each element must be one of `"BOOKING_CREATED"`, `"BOOKING_CANCELLED"`, `"BOOKING_RESCHEDULED"`, `"MEETING_ENDED"`. Duplicate triggers must be collapsed so the output array has no repeats, preserving first-seen order. An empty array is rejected.
- `active`: optional boolean; defaults to `true` in the output when absent.
- `secret`: optional; when present must be 8–128 characters; when absent it is omitted from the output (not set to `null`).
- `payloadTemplate`: optional object with `format` (one of `"json"` or `"text"`, required when the object is present) and `body` (non-empty string after trimming). When the whole object is absent it is omitted.

### Cross-field and edge-case rules

- When `eventTriggers` contains `"MEETING_ENDED"`, a `payloadTemplate` is required; otherwise the error is reported on the `payloadTemplate` field.
- Unknown top-level keys must be rejected, with the error reported under that unknown key's name.
- All violations in one input must be collected and returned together — never stop at the first error.

### Expected Functionality

- A valid subscription with `["BOOKING_CREATED","BOOKING_CREATED"]` -> `{ success: true }` whose `data.eventTriggers` equals `["BOOKING_CREATED"]`, and `data.active === true` when `active` was omitted.
- A subscription with `subscriberUrl: "http://x.test/hook"` -> `{ success: false }` with an error on `subscriberUrl`.
- A subscription whose `eventTriggers` includes `"MEETING_ENDED"` but omits `payloadTemplate` -> `{ success: false }` with an error on `payloadTemplate`.
- A subscription with an unknown `foo` key and an empty `eventTriggers` array -> `{ success: false }` with errors for both `foo` and `eventTriggers`.
- `parseWebhookSubscription(null)` -> `{ success: false }` without throwing.

## Acceptance Criteria

- `packages/lib/webhookSubscriptionSchema.ts` exports `parseWebhookSubscription` and the type `WebhookSubscription`.
- For valid input the returned `data` has a trimmed `subscriberUrl`, a deduplicated `eventTriggers`, `active` defaulting to `true`, and omits absent optional fields.
- For invalid input the returned `errors` maps offending field names (including nested `payloadTemplate.format`, the conditional `payloadTemplate`, and unknown keys) to non-empty arrays of message strings, with all simultaneous violations included.
- The function returns a failure result (never throws) for non-object inputs.
- The added test suite passes deterministically with no network/server/database access:

```
yarn vitest run packages/lib/webhookSubscriptionSchema.test.ts
```
