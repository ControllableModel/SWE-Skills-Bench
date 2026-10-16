# Task: Add a human-readable byte-size formatter

## Background

Vite's node utilities in `packages/vite/src/node/utils.ts` include `displayTime` for rendering durations in a compact human-readable form. Build reporting also needs a compact representation of file sizes. This task adds a byte-size formatter and a thorough test suite that pins its exact output.

## Files to Create/Modify

- `packages/vite/src/node/utils.ts` (modify) — add and export a new function `formatByteSize`.
- `packages/vite/src/node/__tests__/formatByteSize.spec.ts` (new) — a dedicated test file exercising the new function across boundaries.

## Requirements

### Function signature

Add an exported function:

```ts
export function formatByteSize(bytes: number): string
```

It converts a non-negative byte count into a compact string using binary (1024-based) units.

### Behavior

- Values below 1024 are rendered in bytes with the suffix `B` and no decimals: e.g. `0` -> `"0 B"`, `512` -> `"512 B"`, `1023` -> `"1023 B"`.
- At 1024 and above, the value is divided by 1024 repeatedly and rendered with the largest unit whose quotient is `< 1024`, using the unit ladder `KB`, `MB`, `GB`, `TB`.
- Non-byte units are rendered with exactly two decimal places: e.g. `1024` -> `"1.00 KB"`, `1536` -> `"1.50 KB"`, `1048576` -> `"1.00 MB"`.
- There is always exactly one space between the number and the unit.
- The largest unit is `TB`; values at or beyond `1024^5` are still expressed in `TB` (the ladder does not extend past `TB`).

### Edge cases

- `0` returns `"0 B"`.
- Exactly `1024` returns `"1.00 KB"` (it uses the next unit, not `1024.00 B`).
- A value one below a unit boundary (e.g. `1048575`) stays in the smaller unit (`KB`).
- The function may assume `bytes` is a finite non-negative number; no special handling for negatives is required.

### Expected Functionality

| Input | Output |
|-------|--------|
| `0` | `"0 B"` |
| `512` | `"512 B"` |
| `1023` | `"1023 B"` |
| `1024` | `"1.00 KB"` |
| `1536` | `"1.50 KB"` |
| `1048576` | `"1.00 MB"` |
| `1073741824` | `"1.00 GB"` |
| `1099511627776` | `"1.00 TB"` |

## Acceptance Criteria

- `formatByteSize` is exported from `packages/vite/src/node/utils.ts` with the signature above.
- The new test file imports `formatByteSize` from `../utils` and uses a `test.each` (or `it.each`) table covering every row in the table above plus at least two boundary cases (e.g. `1023`/`1024` and `1048575`/`1048576`).
- The file contains at least 10 assertions total, including at least one inline snapshot assertion that pins a formatted value exactly.
- Every test passes when run from the repo root:

```
pnpm exec vitest run packages/vite/src/node/__tests__/formatByteSize.spec.ts
```

- A naive implementation (decimal 1000-based division, wrong decimal count, missing space, or using `B` at 1024) must fail at least one assertion.
