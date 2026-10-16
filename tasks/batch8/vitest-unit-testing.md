# Task: Add a promise timeout wrapper

## Background

Vite performs many asynchronous operations (resolving, transforming, network-ish probes) where a hung promise should be bounded by a deadline. This task adds a small `withTimeout` helper to the node utilities together with a test suite that drives time deterministically.

## Files to Create/Modify

- `packages/vite/src/node/utils.ts` (modify) — add and export a new function `withTimeout`.
- `packages/vite/src/node/__tests__/withTimeout.spec.ts` (new) — a dedicated test file exercising timing behavior under a controlled clock.

## Requirements

### Function signature

Add an exported function:

```ts
export function withTimeout<T>(
  promise: Promise<T>,
  ms: number,
  message?: string,
): Promise<T>
```

It races the supplied promise against a timer of `ms` milliseconds.

### Behavior

- If `promise` settles (resolves or rejects) before `ms` elapses, the returned promise settles with the same value or rejection reason.
- If `ms` elapses first, the returned promise rejects with an `Error` whose `message` is the provided `message`, or `"Timed out after {ms}ms"` when `message` is omitted.
- The internal timer must be cleared once the race settles either way, so no timer remains pending after the returned promise settles (no dangling `setTimeout`).
- The original `promise`'s eventual settlement after a timeout must not cause an unhandled rejection or alter the already-rejected result.

### Edge cases

- A promise that resolves exactly when the timer would fire: the test must establish a clear winner by advancing time deliberately (resolve strictly before, or let the timeout fire strictly first); the implementation need not define a tie-break beyond "whichever settles first wins".
- `ms` of `0` means the timeout can fire on the next timer tick; a promise that is already resolved still wins (it settles before any timer).
- A rejection from `promise` before the deadline propagates the original error, not a timeout error.

### Expected Functionality

| Scenario | Outcome |
|----------|---------|
| promise resolves at 50ms, `ms`=100 | returned promise resolves with the value; no timeout error |
| promise never settles, `ms`=100, time advanced past 100ms | returned promise rejects with `Timed out after 100ms` |
| custom `message` provided and timeout fires | rejection message equals the custom message |
| promise rejects at 10ms, `ms`=100 | returned promise rejects with the original error |

## Acceptance Criteria

- `withTimeout` is exported from `packages/vite/src/node/utils.ts` with the signature above.
- The new test file imports `withTimeout` from `../utils` and controls timer progression deterministically so that no test waits on real elapsed time; the timer environment must be restored after each test so test order does not matter.
- The file asserts: a pre-deadline resolution, a default-message timeout, a custom-message timeout, and a pre-deadline rejection passing through. At least 8 assertions, using async rejection matchers.
- Every test passes when run from the repo root:

```
pnpm exec vitest run packages/vite/src/node/__tests__/withTimeout.spec.ts
```

- A naive implementation (never clearing the timer, ignoring the custom message, or converting a real rejection into a timeout error) must fail at least one assertion.
