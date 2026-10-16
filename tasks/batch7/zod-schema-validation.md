# Task: Build an Organization Branding Config Validator

## Background

The cal.com organizations feature (`packages/lib`) lets admins customize an organization's public branding: name, slug, brand color, logo, and a small set of feature flags. The config is submitted from a settings form, so the raw object must be validated and normalized before being stored. This task adds a reusable validator in the `@calcom/lib` package.

## Files to Create/Modify

- `packages/lib/orgBrandingSchema.ts` (new) — the validator module: schema(s), the public validation function, and exported types.
- `packages/lib/orgBrandingSchema.test.ts` (new) — the vitest suite covering the behavior below.

## Requirements

Implement and export from `packages/lib/orgBrandingSchema.ts`:

### Public API

- A function `parseOrgBranding(input: unknown)` returning a tagged result:
  - On success: `{ success: true; data: OrgBranding }` (normalized).
  - On failure: `{ success: false; errors: Record<string, string[]> }` mapping field names (including nested `"theme.lightBrandColor"`) to non-empty arrays of messages.
  - It must never throw, including for non-object inputs.
- An exported TypeScript type `OrgBranding` derived from the schema (not a hand-written duplicate).

### Field rules (raw input -> normalized output)

- `name`: required; 1–50 characters after trimming; trimmed in the output.
- `slug`: required; in the output it must match `^[a-z0-9-]+$`, be 1–40 characters, and start/end with an alphanumeric (no leading/trailing dash and no consecutive dashes). The raw input may include uppercase letters and surrounding whitespace, which are lowercased/trimmed in the output; if after normalization it still violates the slug pattern, it is rejected on the `slug` field.
- `theme`: required object with:
  - `lightBrandColor`: required hex color string matching `^#[0-9a-fA-F]{6}$`; lowercased in the output.
  - `darkBrandColor`: required hex color string matching `^#[0-9a-fA-F]{6}$`; lowercased in the output.
- `logoUrl`: optional; when present must be a valid `https://` URL; when absent it is omitted.
- `flags`: optional object; defaults in the output to `{ hideBranding: false, allowSEOIndexing: true }`. When provided, each present key (`hideBranding`, `allowSEOIndexing`) must be boolean, and any missing key falls back to the listed default.

### Cross-field and edge-case rules

- `lightBrandColor` and `darkBrandColor` must not be equal (after normalization); an equality violation is reported on `theme.darkBrandColor`.
- Unknown top-level keys must be rejected under their own key name.
- All violations must be collected and returned together.

### Expected Functionality

- `{ name: " Acme ", slug: "Acme-Co", theme: { lightBrandColor: "#FFFFFF", darkBrandColor: "#111111" } }` -> `{ success: true }` with `data.name === "Acme"`, `data.slug === "acme-co"`, colors lowercased, and `data.flags === { hideBranding: false, allowSEOIndexing: true }`.
- `{ ..., slug: "-bad-" }` -> `{ success: false }` with an error on `slug`.
- A theme whose `lightBrandColor` and `darkBrandColor` are both `"#abcabc"` -> `{ success: false }` with an error on `theme.darkBrandColor`.
- `{ ..., theme: { lightBrandColor: "blue", ... } }` -> `{ success: false }` with an error on `theme.lightBrandColor`.
- `parseOrgBranding("nope")` -> `{ success: false }` without throwing.

## Acceptance Criteria

- `packages/lib/orgBrandingSchema.ts` exports `parseOrgBranding` and the type `OrgBranding`.
- For valid input `data.name` is trimmed, `data.slug` is lowercased and pattern-valid, both colors are lowercased, `logoUrl` is omitted when absent, and `data.flags` carries the documented defaults.
- For invalid input the returned `errors` includes slug-pattern violations, the equal-colors violation on `theme.darkBrandColor`, invalid hex colors, and unknown keys, with all simultaneous violations included.
- The function returns a failure result (never throws) for non-object inputs.
- The added test suite passes deterministically with no network/server/database access:

```
yarn vitest run packages/lib/orgBrandingSchema.test.ts
```
