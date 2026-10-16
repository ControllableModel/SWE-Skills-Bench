# Task: Add a Token-Aware Name Suggestion Ranker

## Background

The `internal/didyoumean` package in this repository provides `NameSuggestion`, which proposes a close-by name from a candidate list when a user mistypes an identifier. It only returns the first candidate within a fixed edit-distance threshold and exposes no ranking. This task adds a deterministic, dependency-free ranking helper so callers can present the best-matching candidates in a stable order.

## Files to Create/Modify

- `internal/didyoumean/rank.go` (new) — a self-contained, network-free ranking helper in package `didyoumean`.
- `internal/didyoumean/rank_test.go` (new) — the deterministic test for the new helper.

The new code must live in the existing `didyoumean` package and must not perform any I/O, use the clock, or use randomness.

## Requirements

### `RankSuggestions`

Add an exported function:

```go
func RankSuggestions(given string, candidates []string, maxResults int) []string
```

It returns the candidates that are "close enough" to `given`, ordered best-match first, capped at `maxResults` entries.

Behavior and constraints:

- A candidate's distance is the case-insensitive Levenshtein edit distance between `given` and the candidate (lowercase both before comparing). A candidate qualifies only when its distance is strictly less than `3`.
- Results are sorted ascending by distance. Ties (equal distance) must preserve the **original order** in `candidates` (stable ordering).
- An exact case-insensitive match (distance `0`) must always rank first among qualifying candidates.
- `maxResults <= 0` means "no cap" — return all qualifying candidates.
- When `maxResults` is positive and more candidates qualify than `maxResults`, return exactly the first `maxResults` after sorting.
- Duplicate strings in `candidates` are each treated independently (no de-duplication).
- An empty `candidates` slice, or no qualifying candidates, yields an empty (non-nil acceptable) slice — never a panic.

### Expected Functionality

- given `"resourse"`, candidates `["resource","resources","datasource"]` -> `["resource","resources"]` (both within threshold; `resource` distance 1 before `resources` distance 2).
- given `"Output"`, candidates `["output","input"]`, case-insensitive -> `"output"` first (distance 0).
- two candidates with the same distance keep their input order in the output.

## Acceptance Criteria

The new test file `internal/didyoumean/rank_test.go` must exercise `RankSuggestions` using `github.com/stretchr/testify` (the project already depends on it) and must cover, at minimum:

- ordering by ascending distance with a stable tie-break that preserves input order;
- case-insensitivity (an upper/lower-case-only difference counts as distance 0);
- the strict `< 3` threshold (a candidate at distance 3 is excluded);
- `maxResults` capping (positive cap truncates after sorting; `maxResults <= 0` returns all qualifying);
- empty `candidates` and "no candidate qualifies" both returning an empty result without panicking.

The following command, run from the repository root, must pass:

```
go test ./internal/didyoumean/ -run TestRankSuggestions -v
```
