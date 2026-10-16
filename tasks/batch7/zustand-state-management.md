# Task: Implement a Counter-Group Store Module Using combine

## Background

The `zustand` repository (pmndrs/zustand) exposes the framework-agnostic `createStore` factory from `zustand/vanilla` and the `combine` helper from `zustand/middleware`, which separates an initial state object from a creator that returns the actions. This task adds a self-contained named-counters domain module on top of that public API, so its aggregate behavior can be driven and asserted entirely outside of React using the existing Vitest setup.

## Files to Create/Modify

- `examples/counters-store/countersStore.ts` (new) — the counter-group store factory and its public TypeScript types.
- `tests/countersStore.test.ts` (new) — the deterministic Vitest suite for the module.

(The repo aliases `zustand` / `zustand/*` imports to `src/*` via `vitest.config.mts`, and the Vitest `dir` is `tests`. Place the new module under `examples/counters-store/` and import it from the test by relative path, e.g. `../examples/counters-store/countersStore`.)

## Requirements

Implement a factory `createCountersStore(initialCounters?)` in `examples/counters-store/countersStore.ts`. It must return a store object exposing the standard vanilla handles `getState`, `setState`, and `subscribe`. The store manages a set of independent named integer counters, where the initial state is supplied separately from the actions.

### State shape

- The state exposes `counters: Record<string, number>` (each value an integer) and these read-only derived fields, always consistent with `counters`:
  - `total: number` — the sum of all counter values.
  - `countersCount: number` — the number of distinct counter names.
  - `maxName: string | null` — the name of the counter with the largest value (ties broken by the lexicographically smallest name); `null` when there are no counters.
- `createCountersStore` accepts an optional `initialCounters: Record<string, number>` to seed the counters; when omitted the store starts with no counters.

### Actions

- `add(name, by = 1)`: increments the named counter by the integer `by` (which may be negative), creating it at `by` if it does not yet exist. A non-integer `by` is rejected (no state change).
- `set(name, value)`: sets the named counter to the integer `value`, creating it if absent. A non-integer `value` is rejected (no state change).
- `remove(name)`: deletes the named counter; an unknown name is a no-op.
- `reset()`: removes all counters, returning `total`/`countersCount` to `0` and `maxName` to `null`.

### Derived consistency

`total`, `countersCount`, and `maxName` must always equal the values recomputed from `counters` after every action and must never drift. A test that mutates the store through several actions and recomputes these independently must always agree with the stored derived fields, including the tie-break rule for `maxName`.

## Acceptance Criteria

- `examples/counters-store/countersStore.ts` exports `createCountersStore` and the relevant TypeScript types; the module compiles under the repo's TypeScript config.
- A new Vitest suite `tests/countersStore.test.ts` contains at least 10 `it`/`test` cases covering: seeding via `initialCounters`, `add` creating and incrementing (including a negative `by`), rejecting a non-integer `by`, `set` creating/overwriting, rejecting a non-integer `value`, `remove` deleting and being a no-op for an unknown name, `total` and `countersCount` correctness across a sequence of mutations, `maxName` correctness including the lexicographic tie-break, `maxName` being `null` when empty, and `reset()` clearing all derived fields.
- All new tests pass deterministically with no reliance on network, timers, randomness, real `localStorage`, or a running server.
- The following command passes:

  ```
  pnpm vitest run tests/countersStore.test.ts
  ```
