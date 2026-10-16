# Task: Add Map, FlatMap, and Eval/Exec Methods to the State Monad

## Background

`samber/mo`'s `State[S, A]` type (`state.go`) models a stateful computation `func(S) (A, S)` and currently exposes only `Run`, `Get`, `Modify`, and `Put`. It lacks the core monadic composition operators that make `State` useful for threading state through a pipeline, and convenience runners that return only the value or only the final state. This task adds them.

## Files to Create/Modify

- `state.go` (modify) — add `Map`, `FlatMap`, `Eval`, and `Exec` methods on `State[S, A]`
- `state_test.go` (new) — tests covering composition and state threading

## Requirements

### `State[S, A].Map`

- Signature: `func (s State[S, A]) Map(f func(A) A) State[S, A]`.
- Returns a new `State` that runs the receiver to obtain `(a, s2)`, then yields `(f(a), s2)` — the state is threaded through unchanged; only the result value is transformed.

### `State[S, A].FlatMap`

- Signature: `func (s State[S, A]) FlatMap(f func(A) State[S, A]) State[S, A]`.
- Returns a new `State` that runs the receiver to obtain `(a, s2)`, then runs `f(a)` starting from state `s2`, returning that computation's `(value, finalState)`.
- State must thread left-to-right: the second computation observes the state produced by the first.

### `State[S, A].Eval` and `State[S, A].Exec`

- `Eval(initial S) A` runs the computation from `initial` and returns only the result value (discarding the final state).
- `Exec(initial S) S` runs the computation from `initial` and returns only the final state (discarding the value).

### Constraints

- All methods keep the type parameters `S` and `A` unchanged (no new type parameters), consistent with Go method limitations and the existing `State` API.
- The returned `State` values must remain lazy: composing with `Map`/`FlatMap` must not execute anything until `Run`/`Eval`/`Exec` is called.

### Expected Functionality

- A counter built as `mo.NewState(func(s int) (int, int) { return s, s+1 })` composed via `FlatMap` to draw two successive values, then `Run(0)`, yields the second value `1` and final state `2`.
- `mo.NewState(func(s int) (int, int) { return s*2, s+1 }).Map(func(a int) int { return a+100 }).Run(5)` → value `110`, state `6`.
- `Eval(0)` on a state computation returns only the value; `Exec(0)` returns only the final state.

## Acceptance Criteria

- `State[S, A].Map`, `FlatMap`, `Eval`, and `Exec` exist with the signatures above and `go build ./...` succeeds.
- Composed computations thread state correctly (the second `FlatMap` step sees the first step's output state).
- `Eval` returns only the value and `Exec` returns only the final state for the same computation and initial state.
- `go test ./... -run State` passes, including the newly added cases.
