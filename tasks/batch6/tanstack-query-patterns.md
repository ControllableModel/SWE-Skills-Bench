# Task: Add a Placeholder-Data Resolver for Pagination

## Background

In the framework-agnostic core (`packages/query-core`), while a new query result is being fetched a consumer can show stand-in data so the UI does not flash empty — commonly the previously displayed data while a paginated key changes. This task adds a self-contained public utility to `@tanstack/query-core` that resolves which data to display during a pending fetch and flags whether that data is a placeholder.

## Files to Create/Modify

- `packages/query-core/src/placeholder.ts` (new) — implementation of the resolver and its exported types.
- `packages/query-core/src/index.ts` (modify) — re-export the new function and its types from the package entry point.
- `packages/query-core/src/__tests__/placeholder.test.tsx` (new) — vitest suite covering the behavior described below.

## Requirements

Add a single exported function with the signature:

```ts
export interface ResolveDisplayInput<TData> {
  data: TData | undefined           // freshly resolved data for the current key, if any
  previousData: TData | undefined   // data displayed for the prior key
  placeholder?: TData | ((previous: TData | undefined) => TData | undefined)
}

export function resolveDisplayData<TData>(
  input: ResolveDisplayInput<TData>,
): { data: TData | undefined; isPlaceholderData: boolean }
```

The function decides what to display and whether it is real data or a placeholder.

### Resolution semantics

- When `data` is defined (the current key has resolved), it MUST be returned with `isPlaceholderData: false`, regardless of `placeholder`.
- When `data` is `undefined` and `placeholder` is provided:
  - If `placeholder` is a function, it is called once with `previousData`; its return value is the displayed data.
  - If `placeholder` is a non-function value, that value is the displayed data.
  - The displayed value is a placeholder, so `isPlaceholderData` MUST be `true` — UNLESS the resolved placeholder is `undefined`, in which case there is nothing to show and `isPlaceholderData` MUST be `false`.
- When `data` is `undefined` and no `placeholder` is provided, the result is `{ data: undefined, isPlaceholderData: false }`.

### Edge cases and constraints

- A placeholder function that returns `previousData` (the keep-previous-data pattern) yields the previous data flagged as a placeholder while the new key loads.
- A placeholder function that returns `undefined` (e.g. there was no previous data) yields `{ data: undefined, isPlaceholderData: false }`.
- `data` that is a falsy-but-defined value (e.g. `0`, `''`, `false`, `[]`) is still "defined" and MUST be returned as real data with `isPlaceholderData: false`.
- The function MUST be pure aside from the single optional `placeholder` call, MUST NOT mutate inputs, and MUST NOT require a `QueryClient`, cache, timers, network, or framework.

### Expected Functionality

- `resolveDisplayData({ data: ['new'], previousData: ['old'] })` -> `{ data: ['new'], isPlaceholderData: false }`
- `resolveDisplayData({ data: undefined, previousData: ['old'], placeholder: (p) => p })` -> `{ data: ['old'], isPlaceholderData: true }`
- `resolveDisplayData({ data: undefined, previousData: undefined, placeholder: (p) => p })` -> `{ data: undefined, isPlaceholderData: false }`
- `resolveDisplayData({ data: undefined, previousData: undefined, placeholder: ['seed'] })` -> `{ data: ['seed'], isPlaceholderData: true }`
- `resolveDisplayData({ data: 0 as any, previousData: undefined })` -> `{ data: 0, isPlaceholderData: false }`
- `resolveDisplayData({ data: undefined, previousData: undefined })` -> `{ data: undefined, isPlaceholderData: false }`

## Acceptance Criteria

- `resolveDisplayData` and the `ResolveDisplayInput` type are exported from `@tanstack/query-core` via `packages/query-core/src/index.ts`.
- The function correctly prioritizes resolved data, applies function/value placeholders, treats a resolved-`undefined` placeholder as "not a placeholder", and handles defined-but-falsy data.
- The placeholder function is invoked at most once and only when `data` is `undefined`.
- Calling the function does not mutate its inputs.
- The test suite is deterministic and runs fully in-process (no network, no timers, no `QueryClient`).
- The following command passes (run from the repo root):

```bash
pnpm --filter @tanstack/query-core exec vitest run src/__tests__/placeholder.test.tsx
```
