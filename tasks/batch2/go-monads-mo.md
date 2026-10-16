# Task: Add Filtering Combinators to the option Sub-Package

## Background

`samber/mo` ships an `option` sub-package (`option/transforms.go`) that exposes type-changing, point-free transformation functions such as `Map`, `FlatMap`, `Match`, and `FlatMatch`, each returning a `func(mo.Option[I]) mo.Option[O]` so they slot into the package's `Pipe` chains. The sub-package currently has no way to *conditionally discard* a present value based on a predicate. This task adds value-filtering combinators to that sub-package.

## Files to Create/Modify

- `option/transforms.go` (modify) — add `Filter` and `Reject` combinators for `mo.Option`
- `option/transforms_test.go` (modify) — add table-driven tests covering the new functions

## Requirements

### `option.Filter`

- `Filter` accepts a predicate `func(T) bool` and returns a function `func(mo.Option[T]) mo.Option[T]`.
- When the input option is present and the predicate returns `true` for the contained value, the returned option is present and holds the same value.
- When the input option is present but the predicate returns `false`, the returned option is absent.
- When the input option is already absent, the predicate must not be invoked and the result is absent.

### `option.Reject`

- `Reject` is the logical inverse of `Filter`: it keeps a present value only when the predicate returns `false`, and drops it (absent) when the predicate returns `true`.
- When the input is absent, the predicate must not be invoked and the result is absent.

### Constraints

- Both functions must preserve the same single-type signature shape as the existing `option.Map` / `option.FlatMap` so they can be inserted into existing `option.Pipe2`/`option.Pipe3` chains operating on a single element type.
- The predicate must be invoked at most once and only when a value is present.

### Expected Functionality

- `option.Filter(func(n int) bool { return n > 0 })(mo.Some(5))` → present `Some(5)`
- `option.Filter(func(n int) bool { return n > 0 })(mo.Some(-1))` → absent
- `option.Filter(anyPredicate)(mo.None[int]())` → absent, predicate never called
- `option.Reject(func(s string) bool { return s == "" })(mo.Some(""))` → absent
- `option.Reject(func(s string) bool { return s == "" })(mo.Some("hi"))` → present `Some("hi")`

## Acceptance Criteria

- `option.Filter` and `option.Reject` exist as package-level generic functions returning `func(mo.Option[T]) mo.Option[T]`, and `go build ./...` succeeds.
- Present values are retained or dropped strictly according to the predicate; absent inputs stay absent without invoking the predicate.
- A test asserting that the predicate is not called for an absent input passes (e.g. via a counter closure).
- `go test ./option/...` passes, including the newly added cases.
