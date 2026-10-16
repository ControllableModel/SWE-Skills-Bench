# Task: Build a Parent Orchestrator with Per-Item Worker Actors

## Background

The `xstate` core package (`packages/core`) is the finite-state-machine runtime for this monorepo. This task adds a self-contained batch-processing module where a parent coordinator spawns one child worker per work item, each child owning its own async processing lifecycle, and the parent aggregates results and completes when all children finish, exercised by a new deterministic test.

## Files to Create/Modify

- `packages/core/test/fixtures/batchProcessor.ts` (new) — the batch module: a single exported factory plus any helper exports the test imports. Import everything you need from `../../src/index.ts`.
- `packages/core/test/batchProcessor.test.ts` (new) — the deterministic test that drives the parent and its children through every scenario below.

You may import only from the package's public surface (`../../src/index.ts`); do not reach into internal files.

## Requirements

### Module surface

Export a factory `createBatchProcessor(config)` from `batchProcessor.ts`. `config` carries:

- `process(item)` — returns a promise that resolves to a per-item result value, or rejects (with an `Error`) on failure. The module only orchestrates this call inside each child.

The factory must return something the test can start with the package's actor API, send events to, and read snapshots from. A started parent accepts a `{ items }` event listing the work items.

### Lifecycle behavior

- On receiving `{ items }`, the parent creates **one child worker actor per item**. Each child runs `process(item)` independently. The parent must not inline all the per-item async work as its own flat sequence of states; the per-item lifecycle belongs to the child.
- Each child ends in a per-item success (with the result value) or per-item failure (with the failure reason). When a child finishes, it reports its outcome back to the parent.
- The parent aggregates: it keeps durable counts of succeeded and failed items, plus the collected successful result values keyed by item.
- When every child has finished, the parent moves to a terminal **done** outcome exposing the aggregate. The parent's "processing" vs "done" phase must be derivable purely from the reported state.

### Constraints and edge cases

- Each item's processing must be owned by a distinct child actor; the parent only orchestrates and aggregates. A naive single flat parent loop must not satisfy this.
- A per-item result or failure reason must travel from the child's completion back into the parent's aggregation, not be reconstructed from a placeholder.
- The parent reaches **done** only after all children have finished, regardless of the order in which their async work settles.
- Items with an empty list must take the parent straight to **done** with empty aggregates.

### Expected Functionality

- start, send items `["a","b","c"]`, `process` resolves each to its uppercase -> terminal **done**, succeeded = 3, failed = 0, results include `a->"A"`, `b->"B"`, `c->"C"`.
- items `["x","y"]` where `process("y")` rejects with "bad" -> terminal **done**, succeeded = 1, failed = 1, results include `x->"X"`, and the failure for `y` records reason "bad".
- items `[]` -> immediately terminal **done**, succeeded = 0, failed = 0.
- the parent does not reach **done** until both a slow-resolving and a fast-resolving child have each completed (ordering independence).

## Acceptance Criteria

- Both new files exist at the paths above; the module imports solely from `../../src/index.ts`.
- Per-item work is owned by distinct child actors that report completion back to the parent; the parent aggregates counts and keyed results in its context.
- The processing/done phase is queried through the snapshot's reported state; aggregates are read from the snapshot's context.
- Each scenario in **Expected Functionality** is covered by at least one assertion, including the mixed success/failure batch, the empty batch, and the ordering-independent completion.
- The following command passes from the repository root:

  ```
  pnpm vitest run --project xstate packages/core/test/batchProcessor.test.ts
  ```
