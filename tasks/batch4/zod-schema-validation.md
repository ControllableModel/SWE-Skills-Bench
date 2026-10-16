# Task: Build a Paid Event-Type Price Validator

## Background

The cal.com payments layer (`packages/lib`) lets organizers attach a price and currency to an event type so attendees pay when booking. The price configuration is submitted from a settings form where amounts arrive as strings, so it must be validated and normalized into a canonical money representation before being persisted. This task adds a reusable validator in the `@calcom/lib` package.

## Files to Create/Modify

- `packages/lib/eventPriceSchema.ts` (new) — the validator module: schema(s), the public validation function, and exported types.
- `packages/lib/eventPriceSchema.test.ts` (new) — the vitest suite covering the behavior below.

## Requirements

Implement and export from `packages/lib/eventPriceSchema.ts`:

### Public API

- A function `parseEventPrice(input: unknown)` returning a tagged result:
  - On success: `{ success: true; data: EventPrice }` (normalized).
  - On failure: `{ success: false; errors: Record<string, string[]> }` mapping field names to non-empty arrays of messages.
  - It must never throw, including for non-object inputs.
- An exported TypeScript type `EventPrice` derived from the schema (not a hand-written duplicate).

### Field rules (raw input -> normalized output)

- `currency`: required; an ISO-4217 3-letter code restricted to the supported set `"USD"`, `"EUR"`, `"GBP"`, `"JPY"`, `"KRW"`. The input may be lowercase or mixed-case (`"usd"`); it is uppercased in the output. Any code outside the set is rejected.
- `amountMajor`: arrives as a string (e.g. `"19.99"`) representing the human-facing amount in the currency's major unit; must be a positive number.
- `requirePayment`: optional boolean; defaults to `true` in the output when absent.
- `paymentOption`: optional; one of `"ON_BOOKING"` or `"HOLD"`; defaults to `"ON_BOOKING"` in the output when absent.

### Cross-field, conversion, and edge-case rules

- The output must include `amountMinor`: an integer count of the smallest currency unit derived from `amountMajor`. For zero-decimal currencies (`"JPY"`, `"KRW"`) `amountMinor` equals the rounded integer amount; for the others it equals the amount multiplied by 100 and rounded to an integer. `amountMinor` must be an actual `number` in the output.
- For two-decimal currencies, `amountMajor` must not have more than 2 decimal places (e.g. `"1.999"` for USD is rejected on the `amountMajor` field). For zero-decimal currencies, `amountMajor` must be a whole number (e.g. `"100.5"` for JPY is rejected).
- `amountMinor` must be at least 1 (a price that rounds to zero, e.g. `"0.004"` USD, is rejected on `amountMajor`).
- Unknown top-level keys must be rejected under their own key name.
- All violations must be collected and returned together.

### Expected Functionality

- `{ currency: "usd", amountMajor: "19.99" }` -> `{ success: true }` with `data.currency === "USD"`, `data.amountMinor === 1999` (a number), `data.requirePayment === true`, `data.paymentOption === "ON_BOOKING"`.
- `{ currency: "JPY", amountMajor: "500" }` -> `{ success: true }` with `data.amountMinor === 500`.
- `{ currency: "JPY", amountMajor: "100.5" }` -> `{ success: false }` with an error on `amountMajor`.
- `{ currency: "CAD", amountMajor: "10" }` -> `{ success: false }` with an error on `currency`.
- `parseEventPrice(42)` -> `{ success: false }` without throwing.

## Acceptance Criteria

- `packages/lib/eventPriceSchema.ts` exports `parseEventPrice` and the type `EventPrice`.
- For valid input `data.currency` is uppercased, `data.amountMinor` is the correct integer for zero- and two-decimal currencies, and `requirePayment`/`paymentOption` carry their defaults when omitted.
- For invalid input the returned `errors` includes unsupported currencies, excess-precision amounts, sub-unit rounding to zero, and unknown keys, with all simultaneous violations included.
- The function returns a failure result (never throws) for non-object inputs.
- The added test suite passes deterministically with no network/server/database access:

```
yarn vitest run packages/lib/eventPriceSchema.test.ts
```
