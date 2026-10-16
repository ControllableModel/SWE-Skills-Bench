# Task: Build a Time-Series Window Aggregator

## Background

This repository (`github.com/samber/lo`) is a generics-first utility library for Go. To exercise the library against a realistic workload, add a small self-contained example application under a new `examples/window` package that buckets timestamped metric samples into fixed-width windows and computes per-window summary statistics.

## Files to Create/Modify

- `examples/window/window.go` (new) — the windowing logic, in `package window`.
- `examples/window/window_test.go` (new) — table-driven tests, in `package window`, using only the Go stdlib `testing` package.

Both files belong to the existing module `github.com/samber/lo` (`go 1.18`), so the import path for the new package is `github.com/samber/lo/examples/window`. You may import `github.com/samber/lo` from within the new package.

## Requirements

### Input and output types

Define the following exported types in `examples/window/window.go`:

```go
type Sample struct {
    TS    int64   // unix-second timestamp (may arrive out of order)
    Value float64
}

type WindowStat struct {
    Start int64   // inclusive window start = floor(TS/width)*width
    Count int     // number of samples in this window
    Sum   float64 // sum of values
    Min   float64 // minimum value in window
    Max   float64 // maximum value in window
    Mean  float64 // Sum / Count
}
```

### Behavior

Implement:

```go
func Aggregate(samples []Sample, width int64) ([]WindowStat, error)
```

with the following rules:

#### Bucketing
- Each sample belongs to the window starting at `Start = (TS / width) * width` using integer floor division for non-negative `TS`. Samples may arrive in any order.
- Output `[]WindowStat` contains one entry per non-empty window, sorted ascending by `Start`. Empty windows between populated ones are NOT emitted.

#### Statistics
- `Count`, `Sum`, `Min`, `Max` are computed over the samples in the window; `Mean = Sum / Count`.

#### Validation and edge cases
- If `width <= 0`, return `(nil, error)` with a non-nil error; do not panic.
- All `TS` values are guaranteed non-negative; you need not handle negative timestamps.
- Empty input returns an empty (non-nil) `[]WindowStat` and a nil error.
- A window with a single sample has `Min == Max == Sum == Mean == that value` and `Count == 1`.
- `Aggregate` must not mutate or reorder the caller's input slice.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| Samples spanning 3 windows, shuffled order | 3 `WindowStat` entries sorted ascending by `Start` |
| Multiple samples in one window | `Count`, `Sum`, `Min`, `Max`, `Mean` reflect all of them |
| Gap between populated windows | Empty intermediate windows omitted |
| `width <= 0` | Non-nil error, nil result |
| Single-sample window | Min == Max == that value, Count 1 |
| Empty input | Empty non-nil result, nil error |

## Acceptance Criteria

- The package `github.com/samber/lo/examples/window` compiles.
- `Aggregate` satisfies every rule above, verified by the new table-driven test covering: correct floor-based bucket assignment, ascending window ordering with out-of-order input, per-window Count/Sum/Min/Max/Mean, omission of empty windows, the `width <= 0` error, the empty-input case, and input-immutability (at least 10 assertions/cases total).
- The following command, run from the repository root, passes with no failures:

```
go test ./examples/window/ -run TestAggregate -count=1
```

- A naive implementation that assumes sorted input, emits empty windows, miscomputes the bucket boundary, or panics on non-positive `width` must fail the test.
