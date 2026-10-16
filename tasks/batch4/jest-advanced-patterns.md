# Task: Add a Serial Async Task Queue to the shared package

## Background
The `shared` package in this React monorepo holds small, dependency-free utility modules (for example `enqueueTask.js`) consumed across renderers. This task adds a queue that runs asynchronous tasks strictly one at a time in submission order, so that side-effecting async work never overlaps even when many tasks are submitted at once.

## Files to Create/Modify
- `packages/shared/createSerialQueue.js` (new) — the serial queue implementation.
- `packages/shared/__tests__/createSerialQueue-test.js` (new) — the deterministic test suite for the queue.

## Requirements

### Public API
`createSerialQueue.js` must `export default` a zero-argument factory function:

```
createSerialQueue()
```

It returns a queue object exposing exactly these methods:
- `add(task) -> Promise<value>` where `task` is `() => Promise<value>`.
- `size() -> number` — number of tasks queued or running.
- `onIdle() -> Promise<void>` — resolves when no task is queued or running.

The queue must rely only on the tasks it is given; it must never use timers, the network, globals, or any other module.

### add(task)
- Returns a promise that settles with the result of running `task`.
- Tasks run strictly sequentially: a task must not start until the previous task has settled. At no point may two tasks be running concurrently, regardless of how many were added synchronously.
- Tasks start in the exact order they were added (FIFO).
- If a task rejects, the promise returned by its own `add` call rejects with that error, but the queue continues with the next task — one failure must not stall or skip the remaining queue.
- The resolved/rejected value of each `add` call corresponds to its own task only.

### size / onIdle
- `size()` reflects the count of tasks that are queued plus the one currently running.
- `onIdle()` resolves once the queue has fully drained. Calling `onIdle()` when already idle resolves on the next microtask without error.

### Expected Functionality
- Add three tasks that each record their start order -> they start in the order added, and the recorded log shows no overlap (each task observes that the previous one already finished before it began).
- A task that rejects in the middle -> its `add` promise rejects, but later tasks still run and their `add` promises resolve.
- `size()` decreases to `0` as tasks complete; `onIdle()` resolves after the last task settles.
- Two tasks added back-to-back -> the second task's body does not execute until the first task's promise has settled.

## Acceptance Criteria
- `packages/shared/createSerialQueue.js` exists, exports the factory by default, and imports no other module.
- `packages/shared/__tests__/createSerialQueue-test.js` exists and covers, with independent test cases, every behavior above (FIFO ordering, non-overlap / serialization, failure isolation between tasks, `size`, and `onIdle`). The suite must supply its own controllable mock tasks (for example tasks backed by manually-resolved promises) so that ordering and non-overlap can be asserted deterministically without relying on timers, and must assert which tasks ran and in what order. Async outcomes must be asserted on the returned promises for both resolution and rejection paths. Tests must not depend on wall-clock timing, randomness, network, or a running server.
- The following command passes with all assertions green:

```
yarn test packages/shared/__tests__/createSerialQueue-test.js
```
