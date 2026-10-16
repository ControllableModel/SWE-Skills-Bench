# Task: Implement a Reducer-Dispatch Game Store Module Using redux

## Background

The `zustand` repository (pmndrs/zustand) exposes the framework-agnostic `createStore` factory from `zustand/vanilla` and the `redux` helper from `zustand/middleware`, which attaches a `dispatch(action)` method driven by a pure reducer. This task adds a self-contained tic-tac-toe game domain module on top of that public API, so its state-machine behavior can be driven and asserted entirely outside of React using the existing Vitest setup.

## Files to Create/Modify

- `examples/game-store/gameStore.ts` (new) — the game store factory, its reducer, and its public TypeScript types.
- `tests/gameStore.test.ts` (new) — the deterministic Vitest suite for the module.

(The repo aliases `zustand` / `zustand/*` imports to `src/*` via `vitest.config.mts`, and the Vitest `dir` is `tests`. Place the new module under `examples/game-store/` and import it from the test by relative path, e.g. `../examples/game-store/gameStore`.)

## Requirements

Implement, in `examples/game-store/gameStore.ts`, a pure reducer `gameReducer(state, action)` plus a factory `createGameStore()` that returns a store object exposing the standard vanilla handles `getState`, `setState`, and `subscribe`, **and** a `dispatch(action)` method that runs every state transition through `gameReducer`.

### Game state shape

- The board is a fixed-length array of `9` cells, each `'X' | 'O' | null`, in row-major order.
- The state exposes `board`, `currentPlayer: 'X' | 'O'` (starting as `'X'`), `status: 'playing' | 'won' | 'draw'`, and `winner: 'X' | 'O' | null`.
- `gameReducer` must be a pure function: calling it with the same `(state, action)` always yields an equal next state and never mutates its inputs.

### Actions (dispatched objects with a `type` field)

- `{ type: 'play', index }`: places `currentPlayer`'s mark in the given cell and toggles `currentPlayer`. It is rejected (returns the state unchanged) when `index` is out of range `0..8`, the target cell is already occupied, or `status` is not `'playing'`.
- `{ type: 'reset' }`: returns the game to the initial empty board, `currentPlayer: 'X'`, `status: 'playing'`, `winner: null`.

### Win / draw detection

After a valid `play`, the reducer must detect terminal conditions over the eight standard lines (three rows, three columns, two diagonals):

- When a line is completed by one mark, `status` becomes `'won'`, `winner` is that mark, and `currentPlayer` is NOT advanced (the game is over).
- When all `9` cells are filled with no winner, `status` becomes `'draw'` and `winner` stays `null`.
- Once `status` is `'won'` or `'draw'`, further `play` actions are no-ops until a `reset`.

## Acceptance Criteria

- `examples/game-store/gameStore.ts` exports `gameReducer`, `createGameStore`, and the relevant TypeScript types; the module compiles under the repo's TypeScript config.
- `createGameStore()` returns a store whose `dispatch` mutates state only through `gameReducer`, and whose `getState` reflects each dispatched transition.
- A new Vitest suite `tests/gameStore.test.ts` contains at least 10 `it`/`test` cases covering: `play` placing a mark and toggling the player, rejecting an out-of-range index, rejecting an occupied cell, a row win setting `status: 'won'`/`winner`, a column win, a diagonal win, the winner not advancing the player and further `play` being a no-op, a filled board with no winner setting `status: 'draw'`, `reset` restoring the initial state, and `gameReducer` purity (no mutation of the input `state`/`board` for both accepted and rejected actions).
- All new tests pass deterministically with no reliance on network, timers, randomness, real `localStorage`, or a running server.
- The following command passes:

  ```
  pnpm vitest run tests/gameStore.test.ts
  ```
