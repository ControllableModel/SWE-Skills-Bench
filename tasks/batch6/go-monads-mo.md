# Task: Add a Partition Function for Slices of Either

## Background

`samber/mo` provides `Either[L, R]` (`either.go`) as a discriminated union of two valid alternatives. A frequent need is to take a `[]Either[L, R]` and split it into the two homogeneous slices — all left values and all right values — while preserving their relative order. This task adds a top-level `Partition` function to the root `mo` package.

## Files to Create/Modify

- `partition.go` (new) — in package `mo`, add the `Partition` function over `[]Either[L, R]`
- `partition_test.go` (new) — tests covering ordering, empty input, and all-left / all-right cases

## Requirements

### `mo.Partition`

- Signature: `func Partition[L any, R any](items []Either[L, R]) ([]L, []R)`.
- It iterates the input slice once and appends each element's contained value to the corresponding output slice: left values to the first slice, right values to the second.
- The relative order of left values among themselves, and of right values among themselves, must match their order in the input.

### Constraints

- Both returned slices must be non-nil even when empty (callers should be able to `len(...)`/`range` over them without a nil check).
- An empty input slice yields two non-nil, length-0 slices.
- The function must determine each element's side using the public `Either` API only (e.g. `IsLeft`/`Left`/`Right`), not by reaching into unexported fields.

### Expected Functionality

- `mo.Partition([]mo.Either[int, string]{ Left(1), Right("a"), Left(2), Right("b") })` → `([]int{1,2}, []string{"a","b"})`
- `mo.Partition([]mo.Either[int, string]{})` → `([]int{}, []string{})` (both non-nil, length 0)
- `mo.Partition([]mo.Either[int, string]{ Left(9), Left(8) })` → `([]int{9,8}, []string{})`
- `mo.Partition([]mo.Either[int, string]{ Right("x") })` → `([]int{}, []string{"x"})`

## Acceptance Criteria

- `mo.Partition` exists in package `mo` with the signature above and `go build ./...` succeeds.
- Left and right values are routed to the correct slice with input order preserved within each side.
- Both output slices are always non-nil, including for empty input.
- `go test ./... -run Partition` passes, including the newly added cases.
