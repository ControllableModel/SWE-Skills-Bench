# Task: Add Error-Recovery Combinators to the result Sub-Package

## Background

`samber/mo`'s `result` sub-package (`result/transforms.go`) provides point-free combinators (`Map`, `FlatMap`, `Match`, `FlatMatch`) that return `func(mo.Result[I]) mo.Result[O]` for use in `result.Pipe` chains. There is no combinator to *recover from a failure* by turning an error back into a success value, nor one to rewrite the carried error. This task adds two single-type recovery combinators.

## Files to Create/Modify

- `result/transforms.go` (modify) — add `Recover` and `MapErr` combinators for `mo.Result`
- `result/transforms_test.go` (modify) — add table-driven tests covering the new functions

## Requirements

### `result.Recover`

- `Recover` accepts a function `func(error) T` and returns `func(mo.Result[T]) mo.Result[T]`.
- When the input result is `Ok`, the value passes through unchanged and the recovery function is not invoked.
- When the input result is an error, the recovery function is applied to the carried error and its return value is wrapped as `Ok`.

### `result.MapErr`

- `MapErr` accepts a function `func(error) error` and returns `func(mo.Result[T]) mo.Result[T]`.
- When the input result is `Ok`, it passes through unchanged and the mapper is not invoked.
- When the input result is an error, the mapper transforms the carried error and the result remains an error holding the new error.
- If the mapper returns `nil`, the result must still be treated as an error (the contract of `MapErr` is error-to-error; it must not silently become `Ok`).

### Constraints

- Both functions keep the single type parameter `T` (no type change of the success value), consistent with the existing `result.Map` signature shape so they compose inside `result.Pipe` chains.
- The supplied function must be invoked at most once and only on the error branch.

### Expected Functionality

- `result.Recover(func(error) int { return -1 })(mo.Ok(5))` → `Ok(5)`, recovery not called
- `result.Recover(func(error) int { return -1 })(mo.Err[int](errBoom))` → `Ok(-1)`
- `result.MapErr(func(e error) error { return fmt.Errorf("wrapped: %w", e) })(mo.Ok(5))` → `Ok(5)`, mapper not called
- `result.MapErr(wrap)(mo.Err[int](errBoom))` → error whose message contains the wrapped original

## Acceptance Criteria

- `result.Recover` and `result.MapErr` exist as package-level generic functions returning `func(mo.Result[T]) mo.Result[T]`, and `go build ./...` succeeds.
- `Ok` inputs are passed through untouched with the callback never invoked (verified via a counter closure).
- `Recover` converts an error into `Ok` with the recovered value; `MapErr` keeps the error branch but with the transformed error, including when the mapped error is the same instance.
- `go test ./result/...` passes, including the newly added cases.
