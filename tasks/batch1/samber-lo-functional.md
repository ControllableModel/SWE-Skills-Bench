# Task: Build a Sales Aggregation Report Generator

## Background

This repository (`github.com/samber/lo`) is a generics-first utility library for Go. To exercise the library against a realistic workload, add a small self-contained example application under a new `examples/sales` package that turns a flat stream of raw sales line-items into a structured, aggregated report.

## Files to Create/Modify

- `examples/sales/report.go` (new) — the report-generation logic, in `package sales`.
- `examples/sales/report_test.go` (new) — table-driven tests, in `package sales`, using only the Go stdlib `testing` package.

Both files belong to the existing module `github.com/samber/lo` (`go 1.18`), so the import path for the new package is `github.com/samber/lo/examples/sales`. You may import `github.com/samber/lo` from within the new package.

## Requirements

### Input and output types

Define the following exported types in `examples/sales/report.go`:

```go
// A single raw sales line-item.
type LineItem struct {
    OrderID  string
    Region   string
    Product  string
    Quantity int
    Unit     float64 // unit price
    Refunded bool
}

// Per-region aggregated summary.
type RegionSummary struct {
    Region       string
    OrderCount   int     // number of DISTINCT OrderIDs contributing to this region
    UnitsSold    int     // total Quantity across non-refunded line-items
    Revenue      float64 // total Quantity*Unit across non-refunded line-items
    TopProduct   string  // product with the highest UnitsSold in this region (see tie-break)
}

// The full report.
type Report struct {
    Regions     []RegionSummary // sorted ascending by Region name
    GrandTotal  float64         // sum of all RegionSummary.Revenue
}
```

### Behavior

Implement:

```go
func BuildReport(items []LineItem) Report
```

with the following rules:

#### Refund handling
- A line-item with `Refunded == true` contributes **nothing** to `UnitsSold`, `Revenue`, `TopProduct`, or `GrandTotal`.
- However, a refunded line-item still counts toward `OrderCount` only if that same `OrderID` also has at least one non-refunded line-item in the region; a region whose every line-item is refunded must not appear in the report at all.

#### Region grouping
- Line-items are grouped by `Region`. Each distinct region that has at least one non-refunded line-item produces exactly one `RegionSummary`.
- `Regions` must be sorted in ascending lexicographic order by `Region`.

#### OrderCount
- `OrderCount` is the number of **distinct** `OrderID` values among the non-refunded line-items of that region (duplicate line-items sharing an `OrderID` count once).

#### TopProduct and tie-break
- Within a region, `TopProduct` is the `Product` with the greatest total `UnitsSold` (summed over its non-refunded line-items).
- If two products tie on units sold, choose the one whose `Product` name is lexicographically smaller.

#### Revenue and totals
- `Revenue` per region is the sum of `Quantity * Unit` over its non-refunded line-items.
- `GrandTotal` is the sum of every region's `Revenue`.

### Edge cases
- An empty input slice yields a `Report` with an empty (non-nil) `Regions` slice and `GrandTotal == 0`.
- Input that is entirely refunded yields an empty `Regions` slice and `GrandTotal == 0`.
- `BuildReport` must not mutate or reorder the caller's input slice.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| Two regions, mixed products | One `RegionSummary` per region, sorted by region name |
| Same `OrderID` split across multiple line-items in a region | Counted once in `OrderCount` |
| Product tie on units within a region | `TopProduct` resolves to the lexicographically smaller product name |
| A region with only refunded items | Region omitted entirely |
| Refunded item under an order that also has paid items | `OrderCount` includes that order; refunded amounts excluded from revenue/units |
| Empty input | Empty non-nil `Regions`, `GrandTotal == 0` |

## Acceptance Criteria

- The package `github.com/samber/lo/examples/sales` compiles.
- `BuildReport` satisfies every rule above, verified by the new table-driven test which must cover: multi-region sorting, distinct-order counting, refund exclusion, the all-refunded region omission, the product tie-break, input-immutability, and the empty-input case (at least 10 assertions/cases total).
- The following command, run from the repository root, passes with no failures:

```
go test ./examples/sales/ -run TestBuildReport -count=1
```

- A naive implementation that ignores refunds, double-counts duplicate order IDs, skips the tie-break, or fails to sort regions must fail the test.
