# Task: Build a Public Booking-Page Query Validator

## Background

The cal.com public booking page (`packages/lib`) accepts a number of prefill/control parameters via the URL query string (date, month, duration, layout, locale, attendee email, etc.). Query values arrive as strings or string-arrays, so the raw query must be validated and normalized into a typed control object before the page consumes it. This task adds a reusable validator in the `@calcom/lib` package.

## Files to Create/Modify

- `packages/lib/bookingPageQuerySchema.ts` (new) — the validator module: schema(s), the public validation function, and exported types.
- `packages/lib/bookingPageQuerySchema.test.ts` (new) — the vitest suite covering the behavior below.

## Requirements

Implement and export from `packages/lib/bookingPageQuerySchema.ts`:

### Public API

- A function `parseBookingPageQuery(input: unknown)` returning a tagged result:
  - On success: `{ success: true; data: BookingPageQuery }` (normalized).
  - On failure: `{ success: false; errors: Record<string, string[]> }` mapping field names to non-empty arrays of messages.
  - It must never throw, including for non-object inputs.
- An exported TypeScript type `BookingPageQuery` derived from the schema (not a hand-written duplicate).

### Field rules (raw query input -> normalized output)

All values originate from a URL query (strings / string arrays). The output is a clean typed object.

- `month`: optional `"YYYY-MM"` string; when present month part must be `01`–`12`; when absent it is omitted.
- `date`: optional `"YYYY-MM-DD"` string; when absent it is omitted.
- `duration`: optional; arrives as a string (e.g. `"30"`); must be an integer between 5 and 480 inclusive; is a `number` in the output; omitted when absent.
- `layout`: optional; one of `"month_view"`, `"week_view"`, `"column_view"`; defaults to `"month_view"` in the output when absent.
- `locale`: optional; a 2-letter lowercase language code matching `^[a-z]{2}$`; the raw input may be uppercase and is lowercased in the output; defaults to `"en"` when absent.
- `email`: optional; when present must be a valid email and is lowercased in the output; omitted when absent.
- `guests`: optional; may arrive as a single string OR a string array of emails; in the output it is always an array of lowercased, valid emails with duplicates removed (first-seen order preserved); omitted when absent. An empty resulting array (e.g. an empty incoming array) is omitted.

### Cross-field and edge-case rules

- If both `month` and `date` are present, the `date` must fall within the given `month` (same year and month); a mismatch is reported on the `date` field.
- Any invalid email inside `guests` is reported on the `guests` field.
- Unknown top-level query keys must be rejected under their own key name.
- All violations must be collected and returned together.

### Expected Functionality

- `{ duration: "45", locale: "EN", guests: ["a@x.com","A@X.com"] }` -> `{ success: true }` with `data.duration === 45` (a number), `data.locale === "en"`, `data.layout === "month_view"`, and `data.guests === ["a@x.com"]`.
- `{ month: "2030-02", date: "2030-03-01" }` -> `{ success: false }` with an error on `date`.
- `{ guests: ["ok@x.com","not-an-email"] }` -> `{ success: false }` with an error on `guests`.
- `{ duration: "2" }` -> `{ success: false }` with an error on `duration`.
- `parseBookingPageQuery(null)` -> `{ success: false }` without throwing.

## Acceptance Criteria

- `packages/lib/bookingPageQuerySchema.ts` exports `parseBookingPageQuery` and the type `BookingPageQuery`.
- For valid input `data.duration` is a `number`, `locale`/`email`/`guests` emails are lowercased, `guests` is a deduplicated array, `layout`/`locale` carry their defaults, and absent optional fields are omitted.
- For invalid input the returned `errors` includes the month/date mismatch on `date`, invalid emails inside `guests`, out-of-range `duration`, invalid `month`, and unknown keys, with all simultaneous violations included.
- The function returns a failure result (never throws) for non-object inputs.
- The added test suite passes deterministically with no network/server/database access:

```
yarn vitest run packages/lib/bookingPageQuerySchema.test.ts
```
