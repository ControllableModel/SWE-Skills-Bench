# Task: Add a Retry-and-Backoff Planner

## Background

In the framework-agnostic core (`packages/query-core`), a failed fetch may be retried a configurable number of times, with a configurable (often exponential) delay between attempts. This task adds a self-contained public utility to `@tanstack/query-core` that, given the retry configuration and a failure, decides whether another attempt should run and how long to wait before it.

## Files to Create/Modify

- `packages/query-core/src/retryPlan.ts` (new) — implementation of the planner and its exported types.
- `packages/query-core/src/index.ts` (modify) — re-export the new function and its types from the package entry point.
- `packages/query-core/src/__tests__/retryPlan.test.tsx` (new) — vitest suite covering the behavior described below.

## Requirements

Add a single exported function with the signature:

```ts
export interface RetryPlanInput {
  failureCount: number   // number of failures so far (1 after the first failure)
  error: unknown
  retry?: number | boolean | ((failureCount: number, error: unknown) => boolean)
  retryDelay?: number | ((failureCount: number, error: unknown) => number)
}

export function planRetry(input: RetryPlanInput): {
  shouldRetry: boolean
  delayMs: number
}
```

The function reports whether another attempt should be scheduled and the delay before it.

### Planning semantics

- `retry` controls whether to retry:
  - A number `n` means retry while `failureCount <= n` (i.e. up to `n` retries). Default when `retry` is omitted is `3`.
  - `true` means always retry; `false` means never retry.
  - A function is called with `(failureCount, error)` and its boolean return decides.
- `retryDelay` controls the wait before the next attempt:
  - A number is used directly.
  - A function is called with `(failureCount, error)` and its numeric return is used.
  - When `retryDelay` is omitted, the default is exponential backoff capped at 30000 ms: `Math.min(1000 * 2 ** (failureCount - 1), 30000)`.
- When `shouldRetry` is `false`, `delayMs` MUST be `0` and `retryDelay` MUST NOT be evaluated.

### Edge cases and constraints

- With default `retry` (3): `failureCount` 1, 2, 3 -> `shouldRetry: true`; `failureCount` 4 -> `shouldRetry: false`.
- With default backoff: `failureCount` 1 -> 1000 ms, 2 -> 2000 ms, 3 -> 4000 ms; large counts cap at 30000 ms.
- The `retry` function and `retryDelay` function each receive the same `failureCount`/`error` passed in, and are each evaluated at most once per call; `retryDelay` is only evaluated when retrying.
- The function MUST be pure aside from invoking the provided `retry`/`retryDelay` callbacks, MUST NOT mutate inputs, and MUST NOT require a `QueryClient`, cache, timers, network, or framework.

### Expected Functionality

- `planRetry({ failureCount: 1, error: new Error('x') })` -> `{ shouldRetry: true, delayMs: 1000 }`
- `planRetry({ failureCount: 4, error: new Error('x') })` -> `{ shouldRetry: false, delayMs: 0 }`
- `planRetry({ failureCount: 1, error: e, retry: false })` -> `{ shouldRetry: false, delayMs: 0 }`
- `planRetry({ failureCount: 2, error: e, retry: true, retryDelay: 250 })` -> `{ shouldRetry: true, delayMs: 250 }`
- `planRetry({ failureCount: 5, error: e, retry: (c) => c < 6, retryDelay: (c) => c * 100 })` -> `{ shouldRetry: true, delayMs: 500 }`
- Default backoff caps: a `failureCount` of `20` yields `delayMs: 30000`.

## Acceptance Criteria

- `planRetry` and the `RetryPlanInput` type are exported from `@tanstack/query-core` via `packages/query-core/src/index.ts`.
- The function correctly handles numeric/boolean/function `retry`, numeric/function/default `retryDelay`, the default retry count of 3, and the 30000 ms backoff cap.
- When not retrying, `delayMs` is `0` and `retryDelay` is not evaluated.
- Calling the function does not mutate its inputs.
- The test suite is deterministic and runs fully in-process (no network, no timers, no `QueryClient`).
- The following command passes (run from the repo root):

```bash
pnpm --filter @tanstack/query-core exec vitest run src/__tests__/retryPlan.test.tsx
```
