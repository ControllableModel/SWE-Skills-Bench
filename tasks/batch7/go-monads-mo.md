# Task: Add Map, FlatMap, and ToResult Methods to the IO Monad

## Background

`samber/mo`'s `IO[R]` type (`io.go`) wraps a lazy, side-effecting computation `func() R` and exposes only a constructor (`NewIO`) and a `Run()` executor. There is no way to compose two `IO` values or to defer and capture a panic into a `Result`. This task adds composition and conversion methods to `IO[R]` without changing its existing constructor or `Run` semantics.

## Files to Create/Modify

- `io.go` (modify) — add `Map`, `FlatMap`, and `ToResult` methods on `IO[R]`
- `io_test.go` (modify) — add tests covering laziness, composition, and panic capture

## Requirements

### `IO[R].Map`

- Signature: `func (io IO[R]) Map(mapper func(R) R) IO[R]`.
- Returns a new `IO[R]` that, when `Run()`, first runs the receiver and then applies `mapper` to its result.
- Construction must be lazy: building the new `IO` via `Map` must not run the receiver or call `mapper`; both run only when the new `IO` is `Run()`.

### `IO[R].FlatMap`

- Signature: `func (io IO[R]) FlatMap(mapper func(R) IO[R]) IO[R]`.
- Returns a new `IO[R]` that, when `Run()`, runs the receiver, passes its result to `mapper` to obtain a second `IO[R]`, and runs that one, returning its result.
- Must also be lazy: nothing runs until the returned `IO` is `Run()`.

### `IO[R].ToResult`

- Signature: `func (io IO[R]) ToResult() Result[R]`.
- Runs the receiver and returns `Ok(value)` with the produced value.
- If running the receiver panics, the panic is captured and returned as an error `Result[R]` (an `error` panic preserves the error; a non-error panic is wrapped into an `error`).

### Constraints

- All methods keep the single type parameter `R` (no new type parameters), matching Go method limitations and the existing `IO[R]` API.
- Side effects inside the wrapped computations must execute exactly once per `Run()` and never at construction time.

### Expected Functionality

- `mo.NewIO(func() int { return 21 }).Map(func(n int) int { return n*2 }).Run()` → `42`
- `mo.NewIO(func() int { return 2 }).FlatMap(func(n int) mo.IO[int] { return mo.NewIO(func() int { return n+40 }) }).Run()` → `42`
- Building (without `Run`) an `IO` from `Map`/`FlatMap` increments no side-effect counter; calling `Run()` increments it exactly once.
- `mo.NewIO(func() int { panic(errBoom) }).ToResult()` → error `Result` carrying `errBoom`.
- `mo.NewIO(func() int { return 7 }).ToResult()` → `Ok(7)`.

## Acceptance Criteria

- `IO[R].Map`, `IO[R].FlatMap`, and `IO[R].ToResult` exist with the signatures above and `go build ./...` succeeds.
- A counter-based test proves construction is lazy and each `Run()` executes the effect exactly once.
- `ToResult` returns `Ok` for normal completion and an error `Result` carrying the panic value otherwise.
- `go test ./... -run IO` passes, including the newly added cases.
