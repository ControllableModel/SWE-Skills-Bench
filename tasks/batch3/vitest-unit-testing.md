# Task: Add a monotonic timestamp source backed by the system clock

## Background

Vite already ships `monotonicDateNow` in `packages/vite/src/node/utils.ts`, which guarantees strictly increasing timestamps even when the wall clock does not advance between calls. This task adds a self-contained, resettable counter factory with the same guarantee so it can be embedded in modules that need their own isolated monotonic source, and verifies it against a controlled clock.

## Files to Create/Modify

- `packages/vite/src/node/utils.ts` (modify) — add and export a new factory function `createMonotonicClock`.
- `packages/vite/src/node/__tests__/createMonotonicClock.spec.ts` (new) — a dedicated test file exercising the new factory under a controlled system clock.

## Requirements

### Function signature

Add an exported function:

```ts
export function createMonotonicClock(): { now: () => number }
```

Each call to `createMonotonicClock()` returns an independent object with a `now()` method.

### Behavior

- `now()` reads the current wall-clock time via `Date.now()`.
- If the freshly read time is strictly greater than the last value this clock returned, `now()` returns (and remembers) the fresh time.
- Otherwise (the wall clock did not advance, or went backwards), `now()` returns the previous value plus one, and remembers that incremented value.
- The very first call returns the current `Date.now()` value.
- Two clocks created by separate `createMonotonicClock()` calls maintain fully independent internal state; advancing one must not affect the other.

### Edge cases

- Calling `now()` many times within the same millisecond yields a strictly increasing sequence with no repeats.
- If the wall clock jumps forward by a large amount, the next `now()` returns the new larger wall-clock value (not merely previous+1).
- If the wall clock is moved backward, `now()` still returns a value strictly greater than the previous return.

### Expected Functionality

| Scenario | Outcome |
|----------|---------|
| clock frozen at T, call `now()` three times | returns `T`, `T+1`, `T+2` |
| clock frozen at T then advanced to T+1000 | next `now()` returns `T+1000` |
| two independent clocks both frozen at T | each returns `T` on its own first call |

## Acceptance Criteria

- `createMonotonicClock` is exported from `packages/vite/src/node/utils.ts` with the signature above.
- The new test file imports `createMonotonicClock` from `../utils` and drives the wall clock to deterministic values so that no test depends on real elapsed time; the clock must be restored to its real behavior after each test so test order does not matter.
- The file asserts: strictly-increasing sequence within a frozen instant, a large forward jump returning the new wall value, and independence of two clock instances. At least 10 assertions total.
- Every test passes when run from the repo root:

```
pnpm exec vitest run packages/vite/src/node/__tests__/createMonotonicClock.spec.ts
```

- A naive implementation (returning `Date.now()` directly, or sharing global state across instances) must fail at least one assertion.
