# Task: Build a Log-Line Batch Dispatcher

## Background

This repository (`github.com/samber/lo`) is a generics-first utility library for Go. To exercise the library against a realistic workload, add a small self-contained example application under a new `examples/logbatch` package that takes a flat stream of structured log records and prepares them for delivery to a downstream sink in fixed-size, deduplicated batches.

## Files to Create/Modify

- `examples/logbatch/batch.go` (new) — the batching logic, in `package logbatch`.
- `examples/logbatch/batch_test.go` (new) — table-driven tests, in `package logbatch`, using only the Go stdlib `testing` package.

Both files belong to the existing module `github.com/samber/lo` (`go 1.18`), so the import path for the new package is `github.com/samber/lo/examples/logbatch`. You may import `github.com/samber/lo` from within the new package.

## Requirements

### Input and output types

Define the following exported types in `examples/logbatch/batch.go`:

```go
type LogRecord struct {
    ID    string // unique-ish event id; duplicates may occur
    Level string // "debug", "info", "warn", "error"
    Msg   string
}

type Batch struct {
    Index   int         // 0-based position of this batch in the output
    Records []LogRecord // the records assigned to this batch, original order preserved
}
```

### Behavior

Implement:

```go
func PrepareBatches(records []LogRecord, size int, keepLevels []string) ([]Batch, error)
```

with the following rules:

#### Level filtering
- Only records whose `Level` appears in `keepLevels` are retained. Comparison is case-sensitive and exact.
- If `keepLevels` is empty, all records are retained.

#### Deduplication
- Among the retained records, drop any record whose `ID` has already appeared earlier in the retained stream (first occurrence wins, later duplicates discarded). Original relative order of the surviving records must be preserved.

#### Batching
- The surviving records are split into consecutive batches of at most `size` records each, preserving order. The final batch may be smaller.
- Each returned `Batch.Index` equals its 0-based position in the returned slice.

#### Errors and edge cases
- If `size <= 0`, return `(nil, error)` with a non-nil error; do not panic.
- An input that produces zero surviving records returns an empty (non-nil) `[]Batch` and a nil error.
- `PrepareBatches` must not mutate or reorder the caller's input slice.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| 7 surviving records, size 3 | 3 batches of sizes 3, 3, 1 with sequential `Index` |
| Duplicate `ID`s in retained stream | Only first occurrence of each `ID` survives |
| `keepLevels` excludes some levels | Excluded-level records never appear in any batch |
| Empty `keepLevels` | No level filtering applied |
| `size <= 0` | Non-nil error, nil batches |
| All records filtered out | Empty non-nil batch slice, nil error |

## Acceptance Criteria

- The package `github.com/samber/lo/examples/logbatch` compiles.
- `PrepareBatches` satisfies every rule above, verified by the new table-driven test covering: correct chunk sizing and indexing, level filtering, first-wins deduplication with order preservation, the `size <= 0` error path, the empty-result case, and input-immutability (at least 10 assertions/cases total).
- The following command, run from the repository root, passes with no failures:

```
go test ./examples/logbatch/ -run TestPrepareBatches -count=1
```

- A naive implementation that keeps duplicate IDs, mis-sizes the final batch, ignores level filtering, or panics on non-positive `size` must fail the test.
