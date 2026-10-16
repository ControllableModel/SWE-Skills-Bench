# Task: Add First-Success Aggregation Helpers for Option and Result Slices

## Background

`samber/mo` offers `Option[T]` and `Result[T]` (`option.go`, `result.go`) for representing presence and success. A common combinator missing from the root `mo` package is "pick the first usable value from a list of candidates": the first present `Option`, or the first `Ok` `Result`. This task adds two top-level aggregation helpers.

## Files to Create/Modify

- `aggregate.go` (new) — in package `mo`, add `FirstSome` and `FirstOk`
- `aggregate_test.go` (new) — tests covering first-match selection, empty input, and all-fail input

## Requirements

### `mo.FirstSome`

- Signature: `func FirstSome[T any](options []Option[T]) Option[T]`.
- Scans the slice in order and returns the first present option encountered (preserving its value).
- If no element is present, or the slice is empty, returns an absent `Option[T]` (`None`).
- Scanning must stop at the first present element (later elements are not inspected once a match is found).

### `mo.FirstOk`

- Signature: `func FirstOk[T any](results []Result[T]) Result[T]`.
- Scans the slice in order and returns the first `Ok` result encountered.
- If no element is `Ok`, returns an error `Result[T]` carrying the error of the **last** element (the most recent failure). If the input slice is empty, returns an error `Result[T]` whose error is non-nil (a sentinel "no results" error).

### Constraints

- Selection must use only the public API of `Option`/`Result` (`IsPresent`/`Get`, `IsOk`/`Error`), not unexported fields.
- `FirstSome` returns the matched option unchanged; `FirstOk` returns the matched `Ok` result unchanged.

### Expected Functionality

- `mo.FirstSome([]mo.Option[int]{ None, None, Some(3), Some(4) })` → `Some(3)`
- `mo.FirstSome([]mo.Option[int]{ None, None })` → `None`
- `mo.FirstSome([]mo.Option[int]{})` → `None`
- `mo.FirstOk([]mo.Result[int]{ Err(e1), Ok(2), Ok(3) })` → `Ok(2)`
- `mo.FirstOk([]mo.Result[int]{ Err(e1), Err(e2) })` → error result carrying `e2`
- `mo.FirstOk([]mo.Result[int]{})` → error result with a non-nil sentinel error

## Acceptance Criteria

- `mo.FirstSome` and `mo.FirstOk` exist in package `mo` with the signatures above and `go build ./...` succeeds.
- First-match selection short-circuits and returns the matched value unchanged.
- All-fail / empty inputs return `None` (for `FirstSome`) and a non-nil error result (for `FirstOk`, with the last error or a sentinel).
- `go test ./... -run First` passes, including the newly added cases.
