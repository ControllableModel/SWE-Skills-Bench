# Task: Add Filter and FlatMapNone Methods to Option

## Background

`samber/mo`'s core `Option[T]` type (`option.go`) offers same-type instance methods like `Map`, `MapValue`, `FlatMap`, `Match`, and `MapNone`. Two common ergonomic operations are missing as direct methods: conditionally discarding a present value with a predicate, and supplying a *fallback option* (not just a fallback value) when the option is absent. This task adds both as `Option[T]` methods.

## Files to Create/Modify

- `option.go` (modify) — add the `Filter` and `FlatMapNone` methods on `Option[T]`
- `option_test.go` (modify) — add tests covering both methods

## Requirements

### `Option[T].Filter`

- Signature: `func (o Option[T]) Filter(predicate func(value T) bool) Option[T]`.
- If the option is present and `predicate(value)` is `true`, return the option unchanged (still present with the same value).
- If the option is present and `predicate(value)` is `false`, return an absent option (`None`).
- If the option is absent, return an absent option and do not call `predicate`.

### `Option[T].FlatMapNone`

- Signature: `func (o Option[T]) FlatMapNone(mapper func() Option[T]) Option[T]`.
- If the option is present, return it unchanged and do not call `mapper`.
- If the option is absent, return the option produced by `mapper()` (which may itself be present or absent).

### Constraints

- Both methods operate purely on the same type parameter `T` (no new type parameters), consistent with Go's method limitations and the style of existing `Option[T]` methods.
- `Filter` must invoke the predicate at most once and only for a present value; `FlatMapNone` must invoke `mapper` at most once and only for an absent option.

### Expected Functionality

- `mo.Some(10).Filter(func(n int) bool { return n%2 == 0 })` → `Some(10)`
- `mo.Some(7).Filter(func(n int) bool { return n%2 == 0 })` → `None`
- `mo.None[int]().Filter(p)` → `None`, `p` never invoked
- `mo.Some("a").FlatMapNone(func() mo.Option[string] { return mo.Some("b") })` → `Some("a")`
- `mo.None[string]().FlatMapNone(func() mo.Option[string] { return mo.Some("b") })` → `Some("b")`
- `mo.None[string]().FlatMapNone(func() mo.Option[string] { return mo.None[string]() })` → `None`

## Acceptance Criteria

- The methods `Option[T].Filter` and `Option[T].FlatMapNone` exist with the signatures above and `go build ./...` succeeds.
- Present/absent transitions match the rules exactly, verified for `int` and `string` instantiations.
- Tests proving the callback is skipped on the no-op branch (counter closure) pass.
- `go test ./... -run Option` passes, including the newly added cases.
