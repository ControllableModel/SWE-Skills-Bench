# Task: Add a Hash-by-Scheme Grouping Helper to the Provider Package

## Background

The `internal/getproviders` package handles provider package checksums via the `Hash` type, a `scheme:value` string parsed by `ParseHash` and inspected via `Hash.Scheme()` / `Hash.Value()`. Provider lock files mix hashes of several schemes (e.g. `zh:` and `h1:`), but the package offers no helper to group a raw list of hash strings by scheme. This task adds a deterministic, self-contained grouping helper.

## Files to Create/Modify

- `internal/getproviders/hash_group.go` (new) — a self-contained helper in package `getproviders`.
- `internal/getproviders/hash_group_test.go` (new) — the deterministic test for the new helper.

The new code must live in the existing `getproviders` package and must not perform any I/O (no package-location reads), network calls, or randomness. It must use `ParseHash` and the `Hash` accessor methods.

## Requirements

### `GroupHashesByScheme`

Add an exported function:

```go
func GroupHashesByScheme(raw []string) (groups map[string][]string, invalid []string)
```

It parses each raw hash string and groups the **value** portions by scheme name.

Behavior and constraints:

- Each entry is parsed with `ParseHash`. On success the entry contributes its `Value()` (the part after the scheme prefix) to the slice keyed by its `Scheme()` (as a string).
- An entry that `ParseHash` rejects (e.g. no scheme prefix / empty) is appended to `invalid` as its original raw string.
- Within each scheme group the value slice is **sorted ascending** and **de-duplicated** (an identical `scheme:value` listed twice contributes one value).
- The `invalid` slice is also **sorted ascending** and **de-duplicated**.
- Both `groups` and `invalid` must be non-nil even when empty. A scheme with no valid entries must not appear as an empty key in `groups`.
- Unrecognized but well-formed schemes (a scheme prefix this Terraform version does not specifically know) are still grouped under their scheme name — they are not treated as invalid (consistent with `ParseHash` accepting future schemes).
- The function must be deterministic and order-independent: shuffling `raw` yields identical `groups` and `invalid`.

### Expected Functionality

- mixing `zh:abc`, `h1:xyz`, `zh:def` -> `groups["zh"] = ["abc","def"]`, `groups["h1"] = ["xyz"]`.
- a malformed entry without a `:` prefix -> appears in `invalid`, not in any group.
- the same `h1:xyz` listed twice -> contributes one `xyz` value.

(Exact valid scheme strings must be derived from what `ParseHash` actually accepts, not from hard-coded private constants.)

## Acceptance Criteria

The new test file `internal/getproviders/hash_group_test.go` must exercise `GroupHashesByScheme` using `github.com/stretchr/testify` (the project already depends on it) and must cover, at minimum:

- multiple schemes each collecting their own values;
- value slices sorted ascending and de-duplicated within a group;
- malformed entries collected into `invalid` (sorted, de-duplicated) and excluded from all groups;
- both return values being non-nil and empty for an empty input;
- order-independence (shuffled input yields identical output).

The following command, run from the repository root, must pass:

```
go test ./internal/getproviders/ -run TestGroupHashesByScheme -v
```
