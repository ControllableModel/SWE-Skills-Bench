# Task: Implement a Todo-List Store Module

## Background

The `zustand` repository (pmndrs/zustand) exposes the framework-agnostic `createStore` factory from `zustand/vanilla` and the selector-aware subscription helper from `zustand/middleware`. This task adds a self-contained todo-list domain module on top of that public API so it can be driven and asserted entirely outside of React using the existing Vitest setup.

## Files to Create/Modify

- `examples/todo-store/todoStore.ts` (new) — the todo store factory and its public TypeScript types.
- `tests/todoStore.test.ts` (new) — the deterministic Vitest suite for the module.

(The repo aliases `zustand` / `zustand/*` imports to `src/*` via `vitest.config.mts`, and the Vitest `dir` is `tests`. Place the new module under `examples/todo-store/` and import it from the test by relative path, e.g. `../examples/todo-store/todoStore`.)

## Requirements

Implement a factory `createTodoStore()` in `examples/todo-store/todoStore.ts`. It must return a store object exposing (at minimum) the standard vanilla handles `getState`, `setState`, and `subscribe`, where `subscribe` additionally accepts a selector form `(selector, listener, options?)`.

### Todo items and state shape

- A todo has at least `{ id: string; title: string; completed: boolean; createdAt: number }`.
- The state exposes the current todos as a list keyed by `id` (no duplicate ids may coexist) and a `filter: 'all' | 'active' | 'completed'`.
- The state exposes these read-only derived fields, always consistent with the todos:
  - `activeCount` — number of todos with `completed === false`.
  - `completedCount` — number of todos with `completed === true`.
  - `visibleTodos` — the todos matching the current `filter` (all todos for `'all'`, incomplete for `'active'`, complete for `'completed'`).

### Synchronous actions

- `addTodo(title)`: appends a new incomplete todo with a unique `id`; a blank or whitespace-only `title` is rejected (no state change). The derived counts and `visibleTodos` must update.
- `toggleTodo(id)`: flips `completed` for the matching todo; an unknown `id` is a no-op.
- `removeTodo(id)`: removes the matching todo; an unknown `id` is a no-op.
- `setFilter(filter)`: changes the active filter and recomputes `visibleTodos`.
- `clearCompleted()`: removes all completed todos.

### Derived fields must stay consistent

`activeCount`, `completedCount`, and `visibleTodos` must always equal the values recomputed from the current todos and filter after every action. A test that mutates the store through several actions and recomputes these independently must always agree with the stored derived fields.

### Selector-scoped subscriptions

Consumers must be able to subscribe to a single derived slice and be notified **only** when that slice changes:

- `subscribe(state => state.activeCount, listener)` fires when (and only when) `activeCount` changes; it must NOT fire when an unrelated change leaves `activeCount` the same (e.g. changing only the `filter`).
- When the selector option `fireImmediately: true` is provided, the listener is called once synchronously at subscription time with the current slice.
- The listener receives `(currentSlice, previousSlice)`.

## Acceptance Criteria

- `examples/todo-store/todoStore.ts` exports `createTodoStore` and the relevant TypeScript types; the module compiles under the repo's TypeScript config.
- A new Vitest suite `tests/todoStore.test.ts` contains at least 10 `it`/`test` cases covering: adding todos, rejecting blank titles, toggling, removing, no-ops for unknown ids, `setFilter` changing `visibleTodos`, `clearCompleted`, `activeCount`/`completedCount` correctness across a sequence of mutations, a selector subscription firing only on the relevant slice change, the `fireImmediately` behavior, and that changing only the filter does not fire an `activeCount` subscription.
- All new tests pass deterministically with no reliance on network, timers, randomness, real `localStorage`, or a running server.
- The following command passes:

  ```
  pnpm vitest run tests/todoStore.test.ts
  ```
