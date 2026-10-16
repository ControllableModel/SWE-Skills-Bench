# Task: Build an Environment Configuration Loader

## Background

This repository (`fabian-hiller/valibot`) is the Valibot schema library, whose full public API is exported from `library/src/index.ts`. We need a self-contained module that reads a raw, string-only environment map (the shape of `process.env`) and turns it into a strongly-typed, normalized application configuration object.

## Files to Create/Modify

- `library/src/envConfig/envConfig.ts` (new) — the loader function and the schema it is built on.
- `library/src/envConfig/index.ts` (new) — re-export the public surface of the module.
- `library/src/envConfig/envConfig.test.ts` (new) — the deterministic test suite described below.

Build the module using the library's own public API by importing from the package source root, e.g. `import * as v from '../index.ts';`. Do not add new third-party dependencies.

## Requirements

Implement and export a function `loadConfig(env: unknown)` plus the underlying schema. Every value in the raw `env` arrives as a string (or is missing); the loader must coerce values to their proper runtime types, apply defaults, and reject malformed configuration.

### Input contract

The raw env map looks like:

```json
{
  "NODE_ENV": "production",
  "PORT": "8080",
  "DATABASE_URL": "https://db.example.com",
  "LOG_LEVEL": "debug",
  "ENABLE_CACHE": "true",
  "MAX_CONNECTIONS": "25"
}
```

### Field rules

#### `NODE_ENV` (optional)
- When present must be exactly one of `"development"`, `"production"`, or `"test"`. Any other value is rejected.
- When absent, the output must be `"development"`.

#### `PORT` (required)
- Arrives as a string; the output must hold a `number`.
- Must be a whole number in the inclusive range 1 to 65535. Non-numeric, fractional, or out-of-range values are rejected.

#### `DATABASE_URL` (required)
- Must be a syntactically valid URL string. Invalid URLs are rejected. Stored unchanged in the output.

#### `LOG_LEVEL` (optional)
- When present must be one of `"error"`, `"warn"`, `"info"`, or `"debug"`. Other values are rejected.
- When absent, the output must be `"info"`.

#### `ENABLE_CACHE` (optional)
- Arrives as a string; the output must hold a `boolean`. The strings `"true"` and `"false"` (exactly, case-sensitive) map to the corresponding boolean. Any other value is rejected.
- When absent, the output must be `false`.

#### `MAX_CONNECTIONS` (optional)
- Arrives as a string; the output must hold a `number` that is a whole number of at least 1.
- When absent, the output must be `10`.

### Output shape

`loadConfig` returns the normalized, fully-typed config object directly (not a result wrapper). It must throw when the input is invalid. Unknown extra keys in the raw env map must not appear in the output.

### Expected Functionality

- The example payload above -> `{ NODE_ENV: "production", PORT: 8080, DATABASE_URL: "https://db.example.com", LOG_LEVEL: "debug", ENABLE_CACHE: true, MAX_CONNECTIONS: 25 }`.
- `{ PORT: "3000", DATABASE_URL: "http://localhost" }` -> all defaults applied: `NODE_ENV === "development"`, `LOG_LEVEL === "info"`, `ENABLE_CACHE === false`, `MAX_CONNECTIONS === 10`, and `PORT === 3000` (number).
- `{ PORT: "70000", DATABASE_URL: "http://x" }` -> throws (port out of range).
- `{ PORT: "abc", DATABASE_URL: "http://x" }` -> throws.
- `{ PORT: "80", DATABASE_URL: "not a url" }` -> throws.
- `{ PORT: "80", DATABASE_URL: "http://x", ENABLE_CACHE: "yes" }` -> throws.
- `{ PORT: "80", DATABASE_URL: "http://x", NODE_ENV: "staging" }` -> throws.

## Acceptance Criteria

- A module exists at `library/src/envConfig/envConfig.ts` exporting `loadConfig` and its schema.
- `loadConfig` returns a normalized object whose `PORT` and `MAX_CONNECTIONS` are numbers and `ENABLE_CACHE` is a boolean, with `NODE_ENV`, `LOG_LEVEL`, `ENABLE_CACHE`, and `MAX_CONNECTIONS` defaulted when absent, and unknown keys stripped.
- `loadConfig` throws for every invalid configuration described above and never silently returns a malformed object.
- The added test suite contains at least 10 distinct test cases covering: each field's success path, the string-to-number coercion of `PORT` and `MAX_CONNECTIONS`, the string-to-boolean coercion of `ENABLE_CACHE`, all defaults, URL rejection, picklist rejection for `NODE_ENV`/`LOG_LEVEL`, range rejection for `PORT`, and unknown-key stripping.
- The following command, run from the `library/` directory, passes with all tests green:

```bash
npx vitest run src/envConfig/envConfig.test.ts
```
