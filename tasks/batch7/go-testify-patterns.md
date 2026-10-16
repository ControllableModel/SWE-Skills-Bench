# Task: Add an Experiment-Keyword List Classifier

## Background

The `internal/experiments` package models Terraform's opt-in language experiments. Its `GetCurrent` lookup distinguishes three outcomes for a keyword: it is a currently-active experiment, it is a recognized-but-concluded experiment (returns a `ConcludedError`), or it is completely unknown (returns an `UnavailableError`). There is no helper that classifies a whole list of user-supplied keywords into those three buckets at once. This task adds a deterministic, self-contained classifier.

## Files to Create/Modify

- `internal/experiments/classify_list.go` (new) — a self-contained helper in package `experiments`.
- `internal/experiments/classify_list_test.go` (new) — the deterministic test for the new helper.

The new code must live in the existing `experiments` package and must not perform any I/O or use randomness. It must rely on the package's existing lookup (`GetCurrent`) and its `ConcludedError` / `UnavailableError` error types to decide each keyword's category.

## Requirements

### `ClassifyKeywords`

Add an exported type and function:

```go
type KeywordClassification struct {
    Current   []string
    Concluded []string
    Unknown   []string
}

func ClassifyKeywords(raw []string) KeywordClassification
```

It classifies each raw experiment-keyword string into exactly one of three buckets.

Behavior and constraints:

- Each raw entry is trimmed of surrounding ASCII whitespace before classification.
- A trimmed entry that `GetCurrent` accepts (no error) is placed in `Current`.
- A trimmed entry whose `GetCurrent` error is a `ConcludedError` is placed in `Concluded`.
- A trimmed entry whose `GetCurrent` error is an `UnavailableError` (or otherwise unrecognized) is placed in `Unknown`.
- A trimmed entry that is the empty string is ignored entirely (placed in no bucket).
- Every bucket is **sorted ascending** and **de-duplicated** (a keyword listed twice, possibly with differing surrounding whitespace, appears at most once in its bucket).
- A keyword appears in at most one bucket.
- All three slices must be non-nil even when empty.
- The function must be deterministic and order-independent: shuffling `raw` yields identical buckets.

### Expected Functionality

- a recognized-but-concluded keyword (e.g. one the package registered as concluded) lands in `Concluded`, not `Unknown`.
- a fabricated string such as `"definitely_not_an_experiment"` lands in `Unknown`.
- a whitespace-only entry is dropped; a duplicate keyword appears once.

(The test must derive its expectations of which keyword is concluded vs unknown from the `experiments` package's own `GetCurrent` behavior and error types — not from a hard-coded private list — so it stays valid as the experiment registry evolves.)

## Acceptance Criteria

The new test file `internal/experiments/classify_list_test.go` must exercise `ClassifyKeywords` using `github.com/stretchr/testify` (the project already depends on it) and must cover, at minimum:

- a concluded keyword routed to `Concluded` and a fabricated keyword routed to `Unknown`, with expectations obtained via `GetCurrent` and the error types rather than literals;
- whitespace trimming around entries;
- empty / whitespace-only entries being dropped;
- de-duplication and ascending sort of every bucket;
- order-independence (shuffled input yields identical buckets);
- all three slices being non-nil and empty for an empty input.

The following command, run from the repository root, must pass:

```
go test ./internal/experiments/ -run TestClassifyKeywords -v
```
