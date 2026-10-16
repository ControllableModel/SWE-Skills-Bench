# Task: Add Sequence and Traverse Combinators to the option and result Sub-Packages

## Background

`samber/mo` provides the monadic types `mo.Option[T]` and `mo.Result[T]`, each with a companion sub-package (`option`, `result`) that holds type-changing transformation functions such as `Map`, `FlatMap`, `Match`, and `Pipe1..Pipe10`. These sub-packages currently offer no way to turn a *collection of monadic values* into a *single monadic value wrapping a collection*. This task adds two standard combinators — `Sequence` and `Traverse` — to both sub-packages.

## Files to Create/Modify

- `option/transforms.go` (modify) — add `Sequence` and `Traverse` for `mo.Option`
- `option/transforms_test.go` (modify) — add table-driven tests covering the new functions
- `result/transforms.go` (modify) — add `Sequence` and `Traverse` for `mo.Result`
- `result/transforms_test.go` (modify) — add table-driven tests covering the new functions

## Requirements

### `option.Sequence` / `option.Traverse`

- `Sequence` accepts a `[]mo.Option[T]` and returns a single `mo.Option[[]T]`. When every element is present, the result is present and holds the unwrapped values in their original order. When any element is absent, the result is absent.
- `Traverse` accepts a slice `[]I` and a function `func(I) mo.Option[O]`, applies the function to each element in order, and collects the outcomes into a single `mo.Option[[]O]` with the same all-present-or-absent behavior as `Sequence`.
- An empty input slice yields a *present* result wrapping an empty, non-nil slice.
- The result becomes absent as soon as a single element is absent; a later present element must not "rescue" the result.
- Both must be exposed as package-level generic functions in the `option` sub-package, with signatures consistent in style with the existing `option.Map` / `option.FlatMap` functions (so that callers can use them the same way, including inside `Pipe` chains where applicable).

### `result.Sequence` / `result.Traverse`

- `Sequence` accepts a `[]mo.Result[T]` and returns a single `mo.Result[[]T]`. When every element is `Ok`, the result is `Ok` holding the values in original order. When any element is an error, the result is an error.
- The error carried by the failed result must be the error of the **first** failing element; subsequent elements must not overwrite it.
- `Traverse` accepts a `[]I` and a function `func(I) mo.Result[O]` and collects into `mo.Result[[]O]` with the same first-error-wins semantics.
- An empty input slice yields `Ok` wrapping an empty, non-nil slice.

### Expected Functionality

- `option.Sequence([]mo.Option[int]{Some(1), Some(2), Some(3)})` → `Some([]int{1,2,3})`
- `option.Sequence([]mo.Option[int]{Some(1), None, Some(3)})` → `None`
- `option.Sequence([]mo.Option[int]{})` → `Some([]int{})` (present, length 0)
- `option.Traverse([]int{1,2,3}, func(x int) mo.Option[int]{return Some(x*2)})` → `Some([]int{2,4,6})`
- `option.Traverse([]int{1,-1,2}, parseNonNegative)` where `parseNonNegative` returns `None` for negatives → `None`
- `result.Sequence([]mo.Result[int]{Ok(1), Err(errA), Err(errB)})` → error equal to `errA`
- `result.Traverse([]string{"1","x","3"}, atoiResult)` → error from the `"x"` element

## Acceptance Criteria

- `option.Sequence`, `option.Traverse`, `result.Sequence`, and `result.Traverse` exist as package-level generic functions and the module builds with `go build ./...`.
- For all-present / all-`Ok` inputs the collected slice preserves the original element order.
- A single absent / error element makes the whole result absent / error; for `Result`, the surfaced error is the first failing element's error.
- An empty input slice produces a present / `Ok` result wrapping a non-nil empty slice.
- `go test ./option/... ./result/...` passes, including the newly added cases.
