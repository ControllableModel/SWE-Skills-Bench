# Task: Add a Fold Combinator to the either Sub-Package

## Background

`samber/mo`'s `either` sub-package (`either/transforms.go`) holds point-free transformations over `mo.Either[L, R]` such as `MapLeft`, `MapRight`, `FlatMapLeft`, `FlatMapRight`, `Match`, and `Swap`. `Match` always returns another `Either`, so there is no way to *collapse* an `Either` into a single ordinary value of a third type by handling both sides. This task adds a `Fold` combinator that unifies both branches into one output type.

## Files to Create/Modify

- `either/transforms.go` (modify) — add the `Fold` combinator for `mo.Either`
- `either/transforms_test.go` (modify) — add table-driven tests covering the new function

## Requirements

### `either.Fold`

- `Fold` accepts two handlers, `onLeft func(L) T` and `onRight func(R) T`, sharing one output type `T`, and returns a function `func(mo.Either[L, R]) T`.
- When the input holds a left value, the returned function invokes `onLeft` with that value and returns its result.
- When the input holds a right value, the returned function invokes `onRight` with that value and returns its result.
- Exactly one of the two handlers is invoked per call, matching the side actually present.

### Constraints

- The signature must introduce a fresh output type parameter `T` distinct from `L` and `R`, mirroring how the existing `either.Match` introduces output parameters (`Lout`, `Rout`).
- The combinator returns an ordinary value of type `T`, **not** another `mo.Either`, so it can terminate a `Pipe` chain by extracting a final value.
- The non-matching handler must never be called.

### Expected Functionality

- `either.Fold(func(int) string { return "L" }, func(bool) string { return "R" })(mo.Left[int, bool](3))` → `"L"`
- `either.Fold(func(int) string { return "L" }, func(bool) string { return "R" })(mo.Right[int, bool](true))` → `"R"`
- `either.Fold(func(e error) int { return -1 }, func(n int) int { return n })(mo.Right[error, int](42))` → `42`
- For a left input, the right handler is never invoked (verified via a counter closure), and vice versa.

## Acceptance Criteria

- `either.Fold` exists as a package-level generic function with signature `func[L, R, T any](onLeft func(L) T, onRight func(R) T) func(mo.Either[L, R]) T`, and `go build ./...` succeeds.
- The correct handler runs for each side and its return value is propagated unchanged.
- A test confirming that only the matching handler is invoked passes.
- `go test ./either/...` passes, including the newly added cases.
