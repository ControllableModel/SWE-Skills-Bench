# Task: Add a Generator-Block Validator for the Prisma Schema

## Background

In `@calcom/prisma` (`packages/prisma`), `packages/prisma/schema.prisma` declares a `generator client { ... }` block that uses the modern `prisma-client` provider and an explicit `output` path. Misconfiguring this block (wrong provider, missing output path) silently breaks client generation. This task asks you to add a pure validator that checks a parsed-out generator-client declaration for the rules the package relies on, so the configuration can be guarded in CI without invoking the Prisma engine.

## Files to Create/Modify

- `packages/prisma/generator-validate.ts` (new) — a pure module exporting the validator. It must not import the generated Prisma client, the adapter, or `pg`, and must not read files itself.
- `packages/prisma/generator-validate.test.ts` (new) — the Vitest unit test.

## Requirements

### Validator Contract

Export a function `validateClientGenerator(generator: { provider?: string; output?: string })` that returns a result object with at least:

- `valid` — boolean.
- `errors` — an array of human-readable error strings (empty when `valid` is `true`).

The function is pure: no I/O, no environment reads, equal input always yields equal output. It must never throw — invalid input is reported through `errors`, not exceptions.

### Validation Rules

- The `provider` must be one of the two recognized Prisma client generator providers: `prisma-client` or `prisma-client-js`. Any other value (including a database provider name like `postgresql`, an empty string, or an absent provider) is invalid and contributes an error naming the offending provider.
- When the provider is `prisma-client` (the modern generator), an explicit non-empty `output` path is **required**. A missing or empty `output` for `prisma-client` is invalid and contributes an error stating that the modern generator requires an explicit output path.
- When the provider is `prisma-client-js` (the legacy generator), `output` is optional: its presence or absence is both valid.
- `valid` is `true` only when `errors` is empty.

### Edge Cases

- Both problems at once (unrecognized provider AND missing output) must yield a result with `valid === false` and an `errors` array containing one entry for each distinct problem.
- An `output` value that is only whitespace must be treated as empty (i.e. as missing) for the `prisma-client` requirement.
- A valid `prisma-client` generator with a non-empty `output` must yield `valid === true` and an empty `errors` array.

## Acceptance Criteria

- `packages/prisma/generator-validate.ts` exists and exports `validateClientGenerator`, importable on its own without pulling in the generated Prisma client, the adapter, or `pg`.
- The function is pure and never throws; equal inputs produce deep-equal outputs.
- All provider, output-requirement, and combined-error rules above hold.
- The added Vitest suite passes:

  ```bash
  yarn vitest run packages/prisma/generator-validate.test.ts
  ```

  The suite must contain at least 10 distinct assertions covering: a valid `prisma-client` with output, `prisma-client` missing output (error), `prisma-client` with whitespace-only output (error), valid `prisma-client-js` with output, valid `prisma-client-js` without output, an unrecognized provider (error), an empty provider (error), an absent provider (error), the combined two-error case, and that `valid` tracks `errors` being empty.
