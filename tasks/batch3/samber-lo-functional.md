# Task: Build an Inventory Reconciliation Engine

## Background

This repository (`github.com/samber/lo`) is a generics-first utility library for Go. To exercise the library against a realistic workload, add a small self-contained example application under a new `examples/inventory` package that compares two snapshots of warehouse stock keyed by SKU and reports what changed.

## Files to Create/Modify

- `examples/inventory/reconcile.go` (new) — the reconciliation logic, in `package inventory`.
- `examples/inventory/reconcile_test.go` (new) — table-driven tests, in `package inventory`, using only the Go stdlib `testing` package.

Both files belong to the existing module `github.com/samber/lo` (`go 1.18`), so the import path for the new package is `github.com/samber/lo/examples/inventory`. You may import `github.com/samber/lo` from within the new package.

## Requirements

### Input and output types

Define the following exported types in `examples/inventory/reconcile.go`:

```go
// Snapshot maps SKU -> on-hand quantity.
type Snapshot map[string]int

type Diff struct {
    AddedSKUs     []string       // SKUs present only in the new snapshot, sorted ascending
    RemovedSKUs   []string       // SKUs present only in the old snapshot, sorted ascending
    ChangedQty    map[string]int // SKU -> (new - old) for SKUs present in both with a different quantity
    UnchangedSKUs []string       // SKUs present in both with identical quantity, sorted ascending
}
```

### Behavior

Implement:

```go
func Reconcile(oldSnap, newSnap Snapshot) Diff
```

with the following rules:

#### Set membership
- `AddedSKUs` are keys in `newSnap` but not `oldSnap`.
- `RemovedSKUs` are keys in `oldSnap` but not `newSnap`.
- The three sorted SKU slices (`AddedSKUs`, `RemovedSKUs`, `UnchangedSKUs`) must each be sorted in ascending lexicographic order and must be non-nil even when empty.

#### Quantity changes
- For SKUs present in both snapshots whose quantities differ, `ChangedQty[sku]` is `newSnap[sku] - oldSnap[sku]` (may be negative). SKUs with equal quantities must NOT appear in `ChangedQty`.
- `ChangedQty` must be non-nil even when empty.

#### Unchanged
- `UnchangedSKUs` are SKUs present in both with the same quantity.

### Edge cases
- Two empty snapshots yield a `Diff` whose slices are empty (non-nil) and whose `ChangedQty` is empty (non-nil).
- A SKU present in both with the same quantity must appear in `UnchangedSKUs` and nowhere else.
- `Reconcile` must not mutate either input map.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| SKU only in new | Listed in `AddedSKUs` |
| SKU only in old | Listed in `RemovedSKUs` |
| SKU in both, qty 5 -> 8 | `ChangedQty[sku] == 3` |
| SKU in both, qty 8 -> 5 | `ChangedQty[sku] == -3` |
| SKU in both, identical qty | Listed in `UnchangedSKUs`, absent from `ChangedQty` |
| Empty inputs | All slices/maps empty and non-nil |

## Acceptance Criteria

- The package `github.com/samber/lo/examples/inventory` compiles.
- `Reconcile` satisfies every rule above, verified by the new table-driven test covering: added/removed set membership, positive and negative quantity deltas, exclusion of unchanged SKUs from `ChangedQty`, ascending sort of all SKU slices, non-nil-empty outputs, and input-immutability (at least 10 assertions/cases total).
- The following command, run from the repository root, passes with no failures:

```
go test ./examples/inventory/ -run TestReconcile -count=1
```

- A naive implementation that returns nil slices/maps, leaves unchanged SKUs in `ChangedQty`, fails to sort, or computes the delta in the wrong direction must fail the test.
