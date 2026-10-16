# Task: Add an Async Retry Runner to the shared package

## Background
The `shared` package in this React monorepo holds small, dependency-free utility modules (for example `enqueueTask.js`, `objectIs.js`) consumed across renderers. This task adds a utility that retries a failure-prone asynchronous operation a bounded number of times before giving up, useful for transient async work that occasionally rejects.

## Files to Create/Modify
- `packages/shared/createRetryRunner.js` (new) — the retry runner implementation.
- `packages/shared/__tests__/createRetryRunner-test.js` (new) — the deterministic test suite for the runner.

## Requirements

### Public API
`createRetryRunner.js` must `export default` a factory function:

```
createRetryRunner(options)
```

- `options` is an object `{ maxAttempts, shouldRetry }`.
  - `maxAttempts` is a positive integer: the total number of times the operation may be attempted (the first try counts as attempt 1).
  - `shouldRetry` is an optional predicate `(error, attemptNumber) => boolean`. When omitted, every failure is retried until attempts are exhausted.
- The factory returns a function `run(operation) -> Promise<value>`, where `operation` is `(attemptNumber) => Promise<value>`. The runner must rely only on the injected `operation` and `shouldRetry`; it must never use timers, the network, globals, or any other module.

### run(operation)
- Calls `operation(1)`. If it resolves, `run` resolves with that value and `operation` is not called again.
- If `operation(n)` rejects and `n < maxAttempts` and `shouldRetry(error, n)` returns truthy, the runner calls `operation(n + 1)`; the attempt number passed must increase by exactly one each time.
- If the operation rejects on the final allowed attempt, or `shouldRetry` returns falsy, `run` rejects with the **last** error encountered, and no further attempts are made.
- A successful attempt after earlier failures resolves normally; the earlier errors must not surface.
- `operation` must be invoked at most `maxAttempts` times across the whole run, never more.

### Validation
- If `maxAttempts` is not a positive integer, the factory throws a `RangeError`.
- If `operation` is not a function when `run` is called, `run` rejects (or throws synchronously) — choose one and make it deterministic.

### Expected Functionality
- `operation` that rejects twice then resolves, `maxAttempts: 3` -> `run` resolves with the third value; `operation` called exactly 3 times with attempt numbers 1, 2, 3.
- `operation` that always rejects, `maxAttempts: 2` -> `run` rejects with the second error; `operation` called exactly twice.
- `shouldRetry` returning `false` after the first failure -> `run` rejects with the first error; `operation` called exactly once.
- `operation` resolves immediately -> `operation` called exactly once with attempt number 1.

## Acceptance Criteria
- `packages/shared/createRetryRunner.js` exists, exports the factory by default, and imports no other module.
- `packages/shared/__tests__/createRetryRunner-test.js` exists and covers, with independent test cases, every behavior above (eventual success after retries, exhaustion rejecting with the last error, `shouldRetry` short-circuit, single-attempt success, attempt-number sequencing, and the `RangeError` for an invalid `maxAttempts`). The suite must supply its own controllable mock `operation` (rather than any real async source), assert how many times it was invoked and with which attempt numbers, and assert async outcomes on the returned promises for both resolution and rejection paths. Tests must not depend on wall-clock timing, randomness, network, or a running server.
- The following command passes with all assertions green:

```
yarn test packages/shared/__tests__/createRetryRunner-test.js
```
