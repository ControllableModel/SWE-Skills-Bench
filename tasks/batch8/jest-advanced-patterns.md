# Task: Add a Bounded-Concurrency Async Pool to the shared package

## Background
The `shared` package in this React monorepo holds small, dependency-free utility modules (for example `enqueueTask.js`) consumed across renderers. This task adds a helper that runs many asynchronous tasks with a cap on how many may be in flight at once, so that a burst of async work never exceeds a configured concurrency limit.

## Files to Create/Modify
- `packages/shared/runWithConcurrency.js` (new) — the async pool implementation.
- `packages/shared/__tests__/runWithConcurrency-test.js` (new) — the deterministic test suite for the pool.

## Requirements

### Public API
`runWithConcurrency.js` must `export default` a function:

```
runWithConcurrency(tasks, limit)
```

- `tasks` is an array of functions, each `() => Promise<value>`.
- `limit` is a positive integer: the maximum number of tasks allowed to be running simultaneously.
- Returns a `Promise<Array<value>>` resolving to the results **in the original order of `tasks`**, regardless of completion order. The helper must rely only on the supplied tasks; it must never use timers, the network, globals, or any other module.

### Concurrency behavior
- At no instant may more than `limit` tasks be running concurrently.
- As soon as a running task settles, the next not-yet-started task (in array order) is started, until all tasks have run.
- Each task is invoked exactly once.
- Tasks are started in array order (the first `limit` tasks start immediately).
- If `limit` is greater than or equal to `tasks.length`, all tasks may run at once.

### Result and error handling
- The resolved array maps position-for-position to `tasks`, even though tasks may finish out of order.
- An empty `tasks` array resolves to `[]` without invoking anything.
- If any task rejects, the returned promise rejects with the first such error; once a rejection has occurred no **new** tasks may be started.

### Validation
- If `limit` is not a positive integer, the function throws a `RangeError`.
- If `tasks` is not an array, the function throws a `TypeError`.

### Expected Functionality
- Six tasks with `limit: 2` -> a peak-concurrency counter recorded inside the tasks never exceeds `2`.
- Tasks finishing out of order -> the resolved array is still ordered by original index.
- One task rejects -> the returned promise rejects with that error, and tasks not yet started are never invoked.
- Empty `tasks` -> resolves to `[]`.

## Acceptance Criteria
- `packages/shared/runWithConcurrency.js` exists, exports the function by default, and imports no other module.
- `packages/shared/__tests__/runWithConcurrency-test.js` exists and covers, with independent test cases, every behavior above (concurrency cap enforcement via a peak counter, order-preserving results despite out-of-order completion, exactly-once invocation, rejection short-circuit preventing new starts, empty input, and the `RangeError`/`TypeError` validations). The suite must supply its own controllable mock tasks (for example tasks backed by manually-resolved promises) so concurrency and ordering can be asserted deterministically without timers, and must assert the recorded peak concurrency and per-task invocation counts. Async outcomes must be asserted on the returned promise for both resolution and rejection paths. Tests must not depend on wall-clock timing, randomness, network, or a running server.
- The following command passes with all assertions green:

```
yarn test packages/shared/__tests__/runWithConcurrency-test.js
```
