# Task: Implement an Undo/Redo History Store Module

## Background

The `zustand` repository (pmndrs/zustand) exposes the framework-agnostic `createStore` factory from `zustand/vanilla`. This task adds a self-contained drawing-canvas domain module with full undo/redo support on top of that public API, so its history behavior can be driven and asserted entirely outside of React using the existing Vitest setup.

## Files to Create/Modify

- `examples/history-store/historyStore.ts` (new) — the history-tracking store factory and its public TypeScript types.
- `tests/historyStore.test.ts` (new) — the deterministic Vitest suite for the module.

(The repo aliases `zustand` / `zustand/*` imports to `src/*` via `vitest.config.mts`, and the Vitest `dir` is `tests`. Place the new module under `examples/history-store/` and import it from the test by relative path, e.g. `../examples/history-store/historyStore`.)

## Requirements

Implement a factory `createHistoryStore(options?)` in `examples/history-store/historyStore.ts`. It must return a store object exposing the standard vanilla handles `getState`, `setState`, and `subscribe`.

### Tracked state and history

- The store models a list of shapes; a shape has at least `{ id: string; kind: 'rect' | 'circle'; x: number; y: number }`.
- The "present" state exposes the current `shapes` list (keyed by `id`, no duplicates) plus the read-only derived fields `canUndo: boolean` and `canRedo: boolean`.
- Every mutating action that changes `shapes` pushes the previous present onto an undo stack and clears the redo stack.

### Mutating actions

- `addShape(shape)`: appends a shape with a unique `id`; a duplicate `id` is rejected (no state change, no history entry).
- `moveShape(id, x, y)`: updates the position of the matching shape; an unknown `id` is a no-op (no history entry).
- `removeShape(id)`: removes the matching shape; an unknown `id` is a no-op (no history entry).

### Undo / redo behavior

- `undo()`: restores the most recent previous present and moves the current present onto the redo stack. When there is nothing to undo it is a no-op.
- `redo()`: re-applies the most recently undone present. When there is nothing to redo it is a no-op.
- A mutating action performed after one or more `undo()` calls must clear the redo stack (the redone future is discarded), so `canRedo` becomes `false`.
- `canUndo` is `true` exactly when the undo stack is non-empty; `canRedo` is `true` exactly when the redo stack is non-empty.

### History depth limit

- `createHistoryStore` accepts an optional `options.limit` (a positive integer) capping the number of retained undo entries. When more mutations occur than the limit, the oldest entries are discarded and the number of consecutive `undo()` calls possible never exceeds `limit`. When `options.limit` is omitted, history is unbounded for the purposes of these tests.

## Acceptance Criteria

- `examples/history-store/historyStore.ts` exports `createHistoryStore` and the relevant TypeScript types; the module compiles under the repo's TypeScript config.
- A new Vitest suite `tests/historyStore.test.ts` contains at least 10 `it`/`test` cases covering: adding/moving/removing shapes, rejecting duplicate ids, no-ops for unknown ids, `undo` restoring the prior present, `redo` re-applying it, `undo`/`redo` no-ops at the boundaries, `canUndo`/`canRedo` correctness, a mutation after `undo` clearing the redo stack, and the `options.limit` capping the number of possible `undo` calls.
- All new tests pass deterministically with no reliance on network, timers, randomness, real `localStorage`, or a running server.
- The following command passes:

  ```
  pnpm vitest run tests/historyStore.test.ts
  ```
