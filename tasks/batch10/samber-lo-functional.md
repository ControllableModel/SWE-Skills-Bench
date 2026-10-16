# Task: Build a Shopping-Cart Pricing Calculator

## Background

This repository (`github.com/samber/lo`) is a generics-first utility library for Go. To exercise the library against a realistic workload, add a small self-contained example application under a new `examples/cart` package that prices a shopping cart by consolidating duplicate line-items, applying per-item discounts, and computing an itemized total.

## Files to Create/Modify

- `examples/cart/cart.go` (new) — the pricing logic, in `package cart`.
- `examples/cart/cart_test.go` (new) — table-driven tests, in `package cart`, using only the Go stdlib `testing` package.

Both files belong to the existing module `github.com/samber/lo` (`go 1.18`), so the import path for the new package is `github.com/samber/lo/examples/cart`. You may import `github.com/samber/lo` from within the new package.

## Requirements

### Input and output types

Define the following exported types in `examples/cart/cart.go`:

```go
type CartLine struct {
    SKU       string
    UnitPrice int // price in cents, always >= 0
    Quantity  int // may be 0 or positive
}

// PercentOff maps SKU -> integer percent discount in [0,100].
type PercentOff map[string]int

type LineTotal struct {
    SKU      string // distinct SKU
    Quantity int    // consolidated quantity across all lines for this SKU
    Gross    int    // UnitPrice * Quantity in cents (before discount)
    Discount int    // cents removed by the discount, floor-rounded
    Net      int    // Gross - Discount
}

type Receipt struct {
    Lines    []LineTotal // one per distinct SKU, sorted ascending by SKU
    NetTotal int         // sum of all LineTotal.Net
}
```

### Behavior

Implement:

```go
func Price(lines []CartLine, discounts PercentOff) (Receipt, error)
```

with the following rules:

#### Consolidation
- Lines sharing the same `SKU` are merged into one `LineTotal` whose `Quantity` is the sum of the merged quantities. All merged lines for a SKU are guaranteed to carry the same `UnitPrice`; if they do not, return `(Receipt{}, error)` with a non-nil error; do not panic.
- A SKU whose consolidated `Quantity` is `0` must NOT appear in `Lines` and contributes nothing to `NetTotal`.

#### Discount
- For a SKU with `pct = discounts[SKU]` (absent means 0), `Discount = (Gross * pct) / 100` using integer floor division. `Net = Gross - Discount`.
- If any discount percent is outside `[0,100]`, return `(Receipt{}, error)`; do not panic.

#### Output shape
- `Lines` is sorted ascending by `SKU` and is non-nil even when empty.
- `NetTotal` is the sum of all `Net`.

### Edge cases
- An empty cart yields a `Receipt` with empty (non-nil) `Lines` and `NetTotal == 0`, nil error.
- A SKU appearing in multiple lines is consolidated before the discount is applied (discount on the summed gross, not per-line).
- `Price` must not mutate the caller's `lines` slice or `discounts` map.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| Same SKU across two lines | One consolidated `LineTotal`, summed `Quantity` |
| 25% discount on gross 1000c | `Discount == 250`, `Net == 750` |
| Discount applied to non-integer result | Floor-rounded (e.g. 33% of 1000 -> 330) |
| SKU with consolidated quantity 0 | Omitted from `Lines` |
| Conflicting `UnitPrice` for one SKU | Non-nil error |
| Discount percent > 100 or < 0 | Non-nil error |
| Empty cart | Empty non-nil `Lines`, `NetTotal == 0` |

## Acceptance Criteria

- The package `github.com/samber/lo/examples/cart` compiles.
- `Price` satisfies every rule above, verified by the new table-driven test covering: multi-line consolidation, discount-on-consolidated-gross with floor rounding, zero-quantity omission, ascending SKU sorting, the conflicting-unit-price error, the out-of-range-percent error, the empty-cart case, and input-immutability (at least 10 assertions/cases total).
- The following command, run from the repository root, passes with no failures:

```
go test ./examples/cart/ -run TestPrice -count=1
```

- A naive implementation that discounts per-line instead of on consolidated gross, rounds discounts the wrong way, keeps zero-quantity SKUs, or fails to sort must fail the test.
