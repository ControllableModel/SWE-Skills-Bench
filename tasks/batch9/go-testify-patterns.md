# Task: Add a Severity-Summary Helper to the Diagnostics Package

## Background

The `internal/tfdiags` package models Terraform's diagnostics, each carrying a `Severity()` of either `tfdiags.Error` or `tfdiags.Warning`. Callers frequently need a quick numeric summary of a `Diagnostics` collection (how many errors, how many warnings, whether it failed) but the package has no single helper that produces one. This task adds a deterministic, self-contained summary helper.

## Files to Create/Modify

- `internal/tfdiags/summary.go` (new) — a self-contained helper in package `tfdiags`.
- `internal/tfdiags/summary_test.go` (new) — the deterministic test for the new helper.

The new code must live in the existing `tfdiags` package and must not perform any I/O or use randomness.

## Requirements

### `SummarizeSeverities`

Add an exported type and method on the existing `Diagnostics` type:

```go
type SeveritySummary struct {
    Errors   int
    Warnings int
    Other    int
}

func (diags Diagnostics) SummarizeSeverities() SeveritySummary
```

It walks the diagnostics and tallies them by severity.

Behavior and constraints:

- `Errors` counts diagnostics whose `Severity()` is `tfdiags.Error`.
- `Warnings` counts diagnostics whose `Severity()` is `tfdiags.Warning`.
- `Other` counts diagnostics whose severity is neither of those two known values (defensive: future/unknown severities), so `Errors + Warnings + Other == len(diags)` always holds.
- A nil or empty `Diagnostics` yields a zero summary (all fields `0`) and must not panic.
- The method must not mutate the receiver and must be deterministic.

### `HasErrors` convenience

Also add:

```go
func (s SeveritySummary) HasErrors() bool
```

which returns `true` iff `Errors > 0`.

### Expected Functionality

- a `Diagnostics` with two errors and one warning -> `{Errors:2, Warnings:1, Other:0}`, and `HasErrors() == true`.
- an empty `Diagnostics` -> `{0,0,0}`, `HasErrors() == false`.
- the sum of the three counts always equals the number of diagnostics.

(The test may build `Diagnostics` using the package's existing constructors/append helpers — e.g. appending simple errors and warnings — rather than implementing `Diagnostic` from scratch, but must verify counts and `HasErrors` behavior.)

## Acceptance Criteria

The new test file `internal/tfdiags/summary_test.go` must exercise `SummarizeSeverities` and `HasErrors` using `github.com/stretchr/testify` (the project already depends on it) and must cover, at minimum:

- a mixed collection with both errors and warnings producing the exact counts;
- an errors-only collection where `HasErrors()` is true and `Warnings == 0`;
- a warnings-only collection where `HasErrors()` is false;
- an empty / nil `Diagnostics` yielding an all-zero summary without panicking;
- the invariant that `Errors + Warnings + Other` equals the total number of diagnostics.

The following command, run from the repository root, must pass:

```
go test ./internal/tfdiags/ -run TestSummarizeSeverities -v
```
