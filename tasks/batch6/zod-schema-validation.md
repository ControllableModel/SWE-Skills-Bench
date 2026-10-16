# Task: Build an API Key Creation Request Validator

## Background

The cal.com platform (`packages/lib`) lets users mint personal API keys with an optional expiry and a set of scopes. The creation request comes from an untrusted API body where the expiry arrives as a string, so it must be validated and normalized before a key is issued. This task adds a reusable validator in the `@calcom/lib` package.

## Files to Create/Modify

- `packages/lib/apiKeyRequestSchema.ts` (new) — the validator module: schema(s), the public validation function, and exported types.
- `packages/lib/apiKeyRequestSchema.test.ts` (new) — the vitest suite covering the behavior below.

## Requirements

Implement and export from `packages/lib/apiKeyRequestSchema.ts`:

### Public API

- A function `parseApiKeyRequest(input: unknown)` returning a tagged result:
  - On success: `{ success: true; data: ApiKeyRequest }` (normalized).
  - On failure: `{ success: false; errors: Record<string, string[]> }` mapping field names to non-empty arrays of messages.
  - It must never throw, including for non-object inputs.
- An exported TypeScript type `ApiKeyRequest` derived from the schema (not a hand-written duplicate).

### Field rules (raw input -> normalized output)

- `note`: optional string; when present must be 1–80 characters after trimming and is trimmed in the output; when absent it is omitted.
- `neverExpires`: optional boolean; defaults to `false` in the output when absent.
- `expiresAt`: optional ISO-8601 datetime string; when present it is normalized to a `Date` in the output.
- `scopes`: required non-empty array; each element one of `"booking:read"`, `"booking:write"`, `"event-type:read"`, `"event-type:write"`. Duplicates must be collapsed (first-seen order preserved). An empty array is rejected.

### Cross-field and edge-case rules

- Exactly one of `neverExpires === true` or a provided `expiresAt` must hold: if `neverExpires` is `true` then `expiresAt` must be absent (otherwise an error is reported on `expiresAt`); if `neverExpires` is falsy (or absent) then `expiresAt` is required (otherwise an error is reported on `expiresAt`).
- Any `*:write` scope present in `scopes` requires the corresponding `*:read` scope to also be present (e.g. `"booking:write"` requires `"booking:read"`); a missing read scope is reported on the `scopes` field.
- Unknown top-level keys must be rejected under their own key name.
- All violations must be collected and returned together.

### Expected Functionality

- `{ scopes: ["booking:read","booking:write","booking:read"], neverExpires: true }` -> `{ success: true }` with `data.scopes === ["booking:read","booking:write"]` and `data.neverExpires === true`.
- `{ scopes: ["event-type:read"], expiresAt: "2030-01-01T00:00:00Z" }` -> `{ success: true }` with `data.expiresAt` being a `Date` and `data.neverExpires === false`.
- `{ scopes: ["booking:write"], expiresAt: "2030-01-01T00:00:00Z" }` -> `{ success: false }` with an error on `scopes` (missing `booking:read`).
- `{ scopes: ["booking:read"], neverExpires: true, expiresAt: "2030-01-01T00:00:00Z" }` -> `{ success: false }` with an error on `expiresAt`.
- `{ scopes: [] }` -> `{ success: false }` with errors on both `scopes` and `expiresAt`.
- `parseApiKeyRequest(null)` -> `{ success: false }` without throwing.

## Acceptance Criteria

- `packages/lib/apiKeyRequestSchema.ts` exports `parseApiKeyRequest` and the type `ApiKeyRequest`.
- For valid input `scopes` is deduplicated, `expiresAt` (when present) is a `Date`, `neverExpires` defaults to `false`, and absent optional fields are omitted.
- For invalid input the returned `errors` includes the neverExpires/expiresAt mutual-exclusion violation, the write-without-read scope violation, empty scopes, and unknown keys, with all simultaneous violations included.
- The function returns a failure result (never throws) for non-object inputs.
- The added test suite passes deterministically with no network/server/database access:

```
yarn vitest run packages/lib/apiKeyRequestSchema.test.ts
```
