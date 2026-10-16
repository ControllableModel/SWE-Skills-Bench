# Task: Add an Ordered String-Set Diff Helper to the Collections Package

## Background

The `internal/collections` package provides generic set/map building blocks used throughout Terraform. It lacks a convenience helper for computing the difference between two simple string sets in a deterministic, sorted order — something callers need when reporting "added" vs "removed" identifiers. This task adds a self-contained diff helper.

## Files to Create/Modify

- `internal/collections/strdiff.go` (new) — a self-contained helper in package `collections`.
- `internal/collections/strdiff_test.go` (new) — the deterministic test for the new helper.

The new code must live in the existing `collections` package and must not perform any I/O or use randomness.

## Requirements

### `StringSetDiff`

Add an exported type and function:

```go
type StringSetDiff struct {
    Added   []string
    Removed []string
    Common  []string
}

func DiffStringSets(before []string, after []string) StringSetDiff
```

It compares two collections of strings treated as **sets** and reports what changed when moving from `before` to `after`.

Behavior and constraints:

- `Added` = strings present in `after` but not in `before`.
- `Removed` = strings present in `before` but not in `after`.
- `Common` = strings present in both.
- Each of the three result slices is **sorted ascending** (lexicographic) and contains **no duplicates**, regardless of duplicates in the inputs.
- Inputs are treated as sets: a string appearing multiple times in `before` or `after` counts once.
- Empty inputs are valid: if `before` is empty, every distinct string in `after` is `Added`; if `after` is empty, every distinct string in `before` is `Removed`.
- The three result slices must be non-nil even when empty (an empty diff yields three empty, non-nil slices).
- The function must be deterministic: identical inputs always produce identical results, and input order must not affect the output.

### Expected Functionality

- `before=["b","a","a"]`, `after=["a","c"]` -> `Added=["c"]`, `Removed=["b"]`, `Common=["a"]`.
- `before=[]`, `after=["z","y"]` -> `Added=["y","z"]`, `Removed=[]`, `Common=[]`.
- identical sets (in any order) -> empty `Added`/`Removed`, `Common` = the sorted distinct set.

## Acceptance Criteria

The new test file `internal/collections/strdiff_test.go` must exercise `DiffStringSets` using `github.com/stretchr/testify` (the project already depends on it) and must cover, at minimum:

- a mixed case with non-empty `Added`, `Removed`, and `Common`;
- de-duplication of repeated inputs in both `before` and `after`;
- ascending sort order of all three result slices;
- empty `before` (everything added) and empty `after` (everything removed);
- order-independence (shuffling the inputs yields identical output);
- all three result slices being non-nil and empty for two identical empty inputs.

The following command, run from the repository root, must pass:

```
go test ./internal/collections/ -run TestDiffStringSets -v
```
