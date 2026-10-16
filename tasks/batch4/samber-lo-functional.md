# Task: Build a CSV Column Projector

## Background

This repository (`github.com/samber/lo`) is a generics-first utility library for Go. To exercise the library against a realistic workload, add a small self-contained example application under a new `examples/csvproj` package that reshapes parsed CSV rows by selecting, renaming, and reordering a subset of columns.

## Files to Create/Modify

- `examples/csvproj/project.go` (new) — the projection logic, in `package csvproj`.
- `examples/csvproj/project_test.go` (new) — table-driven tests, in `package csvproj`, using only the Go stdlib `testing` package.

Both files belong to the existing module `github.com/samber/lo` (`go 1.18`), so the import path for the new package is `github.com/samber/lo/examples/csvproj`. You may import `github.com/samber/lo` from within the new package.

## Requirements

### Input and output

A parsed CSV is a header row plus data rows, all `[]string`. Implement:

```go
// header: column names. rows: each row is one record aligned to header by index.
// selection: ordered list of source column names to project, in output order.
func Project(header []string, rows [][]string, selection []string) ([][]string, error)
```

with the following rules:

#### Header handling
- The returned slice's first element is the projected header: exactly `selection`, in the given order. (The output includes a header row.)
- Each data row is projected to the values at the columns named by `selection`, in `selection` order.

#### Validation
- If any name in `selection` does not exist in `header`, return `(nil, error)` with a non-nil error naming the missing column; do not panic.
- If `selection` contains a duplicate column name, return `(nil, error)` with a non-nil error; do not panic.
- If any data row's length does not equal `len(header)`, return `(nil, error)`; do not panic.

#### Output shape
- Output is `len(rows)+1` rows (header + one per input row). Every output row has length `len(selection)`.
- When `selection` is empty, every output row (including the header) is an empty non-nil `[]string`, and the result has `len(rows)+1` rows.

### Edge cases
- Zero data rows but a valid `selection` returns exactly one row (the projected header).
- `Project` must not mutate the caller's `header`, `rows`, or any inner row slice.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| Reorder columns via `selection` | Output columns follow `selection` order, not header order |
| `selection` references a missing column | Non-nil error, nil result |
| Duplicate name in `selection` | Non-nil error, nil result |
| A data row with wrong width | Non-nil error, nil result |
| Empty `selection` | Each output row is empty non-nil slice |
| Zero data rows | Exactly the projected header row returned |

## Acceptance Criteria

- The package `github.com/samber/lo/examples/csvproj` compiles.
- `Project` satisfies every rule above, verified by the new table-driven test covering: column reordering, value extraction by name, the missing-column error, the duplicate-selection error, the ragged-row error, the empty-selection case, the zero-rows case, and input-immutability (at least 10 assertions/cases total).
- The following command, run from the repository root, passes with no failures:

```
go test ./examples/csvproj/ -run TestProject -count=1
```

- A naive implementation that projects by header order instead of `selection` order, ignores missing/duplicate columns, or mutates the input must fail the test.
