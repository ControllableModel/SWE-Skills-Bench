# Task: Add a Fold Combinator to the either3 Sub-Package

## Background

`samber/mo` extends two-way unions to a three-way one with `Either3[T1, T2, T3]` (`either3.go`), which has its own sub-package `either3` (`either3/transforms.go`) holding point-free transformations. While `Either3` has a `Match` method that returns another `Either3`, the sub-package has no combinator to *collapse* a three-way union into a single ordinary value by handling all three arms. This task adds a `Fold` combinator to the `either3` sub-package.

## Files to Create/Modify

- `either3/transforms.go` (modify) — add the `Fold` combinator for `mo.Either3`
- `either3/transforms_test.go` (modify) — add tests covering all three arms

## Requirements

### `either3.Fold`

- `Fold` accepts three handlers, `onArg1 func(T1) R`, `onArg2 func(T2) R`, and `onArg3 func(T3) R`, sharing a single output type `R`, and returns a function `func(mo.Either3[T1, T2, T3]) R`.
- The returned function inspects which arm is populated and invokes exactly the matching handler, returning its result.
- Exactly one handler is invoked per call; the other two are never called.

### Constraints

- The signature must introduce a fresh output type parameter `R` distinct from `T1`, `T2`, and `T3`.
- The combinator returns an ordinary value of type `R`, not another `Either3`, so it can terminate a transformation chain by extracting a final value.
- Detection of the active arm must use the public `Either3` API (`IsArg1`/`Arg1`, etc.), not unexported fields.

### Expected Functionality

- `either3.Fold(f1, f2, f3)(mo.NewEither3Arg1[int, string, bool](7))` invokes only `f1` with `7`.
- `either3.Fold(f1, f2, f3)(mo.NewEither3Arg2[int, string, bool]("x"))` invokes only `f2` with `"x"`.
- `either3.Fold(f1, f2, f3)(mo.NewEither3Arg3[int, string, bool](true))` invokes only `f3` with `true`.
- Given handlers that all return a common type (e.g. `string`), `Fold` returns the matching handler's string for each arm and never invokes the other two (verified via counter closures).

## Acceptance Criteria

- `either3.Fold` exists as a package-level generic function returning `func(mo.Either3[T1, T2, T3]) R`, and `go build ./...` succeeds.
- For each of the three arms, only the matching handler runs and its return value is propagated unchanged.
- A test confirming the two non-matching handlers are never invoked passes.
- `go test ./either3/...` passes, including the newly added cases.
