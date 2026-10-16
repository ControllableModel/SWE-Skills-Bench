# Task: Build a Checkout Error-Reporting Module

## Background

The `samber/oops` repository ships several self-contained demonstration modules under `examples/` (each its own Go module, wired into the workspace via `go.work`). This task adds a new example module, `examples/checkout`, that models a tiny order-checkout flow and surfaces rich, machine-inspectable failures using the library in this repository.

## Files to Create/Modify

- `examples/checkout/checkout.go` (new) — the checkout flow and its error-producing functions.
- `examples/checkout/checkout_test.go` (new) — the deterministic table tests described below.
- `examples/checkout/go.mod` (new) — module `github.com/samber/oops/examples/checkout`, Go 1.21, requiring `github.com/samber/oops`.
- `go.work` (modify) — add `./examples/checkout` to the `use (...)` block so the module resolves the in-repo `github.com/samber/oops`.

## Requirements

The module simulates a single checkout operation made of three layers: a **repository** that looks up a product, a **service** that validates the order, and a **handler** that callers invoke. All data is in-memory; there is no network, database, or running server.

### Domain types

Define exported types in `examples/checkout/checkout.go`:

- `Product struct { ID string; Name string; Stock int }`
- `OrderRequest struct { UserID string; TenantID string; ProductID string; Quantity int }`
- A `Catalog` type backed by an in-memory `map[string]Product`, with a constructor `NewCatalog(products map[string]Product) *Catalog`.

### Entry point

Provide a single exported function:

```go
func Checkout(cat *Catalog, req OrderRequest) error
```

`Checkout` orchestrates the repository lookup and service validation and returns the resulting error (or `nil` on success). Internally it MUST be composed of at least two distinct helper layers (e.g. a product-lookup step and a stock-validation step), and each layer that detects or forwards a failure MUST contribute its own contextual information to the returned error so that the final error carries information from every layer it passed through.

### Failure behaviors

Every non-nil error returned from `Checkout` MUST be inspectable as a `samber/oops` error (i.e. `oops.AsOops(err)` returns `ok == true`) and MUST expose the following when probed through that error's accessors:

1. **Product not found** — when `req.ProductID` is not present in the catalog:
   - error `Code()` equals `"product_not_found"`.
   - the public-facing message (via `oops.GetPublic(err, "<fallback>")`) equals `"That product is unavailable."`.
   - the domain (`Domain()`) of the originating layer is `"checkout-repository"`.
   - the error context (`Context()`) contains the key `"product_id"` whose value equals the requested product id.

2. **Insufficient stock** — when the product exists but `req.Quantity` exceeds its `Stock`:
   - error `Code()` equals `"insufficient_stock"`.
   - the public message equals `"Not enough items in stock."`.
   - the error context contains `"requested"` (equal to `req.Quantity`) and `"available"` (equal to the product's stock) as separate entries.
   - the error is tagged such that `HasTag("checkout")` is true.

3. **Invalid quantity** — when `req.Quantity <= 0`:
   - error `Code()` equals `"invalid_quantity"`.
   - the public message equals `"Quantity must be at least one."`.

4. **Successful checkout** — when the product exists and `0 < req.Quantity <= Stock`, `Checkout` returns `nil`.

### Message cardinality constraint

For each failure above, the underlying error message text (the value returned by `err.Error()`) MUST be constant for that failure category — it MUST NOT change when `UserID`, `TenantID`, `ProductID`, or `Quantity` change. The variable details (product id, requested/available quantities, user, tenant) MUST instead be retrievable through the error's structured accessors (`Context()`, `User()`, `Tenant()`), not by parsing the message string. The tests assert this by triggering the same failure category with two different request payloads and comparing the two error strings for exact equality while confirming the structured attributes differ.

### Panic recovery

Provide one more exported function:

```go
func SafeCheckout(cat *Catalog, req OrderRequest) (err error)
```

`SafeCheckout` calls into a helper that may `panic` (for the test, panic whenever `cat == nil`). It MUST NOT let the panic escape: it returns a non-nil `samber/oops` error instead. That recovered error MUST have `Code()` equal to `"checkout_panic"` and a domain (`Domain()`) of `"checkout-service"`. When `cat != nil`, `SafeCheckout` behaves identically to `Checkout` (same return value for the same input).

### Expected Functionality

- `Checkout(cat, {ProductID:"missing", Quantity:1})` -> error with code `product_not_found`, public message `"That product is unavailable."`, context `product_id == "missing"`.
- `Checkout(cat, {ProductID:"sku-1", Quantity:99})` where stock is 5 -> error with code `insufficient_stock`, context `requested == 99`, `available == 5`, `HasTag("checkout") == true`.
- `Checkout(cat, {ProductID:"sku-1", Quantity:0})` -> error with code `invalid_quantity`.
- `Checkout(cat, {ProductID:"sku-1", Quantity:3})` where stock is 5 -> `nil`.
- `SafeCheckout(nil, anyReq)` -> non-nil error with code `checkout_panic`, no panic propagates.

## Acceptance Criteria

- `examples/checkout/go.mod` declares module `github.com/samber/oops/examples/checkout` and `go.work` lists `./examples/checkout`, so the new module compiles against the in-repo library.
- A naive implementation that hardcodes the same message/code/context for every failure, or that interpolates variable data into the message string, fails the tests (the cardinality and per-category assertions above must hold).
- The added tests are deterministic (in-memory only) and pass:

```
go test ./examples/checkout/...
```

  run from the repository root. All test cases in `examples/checkout/checkout_test.go` must pass, including: the four `Checkout` outcome cases, the panic-recovery case, and the message-cardinality case that asserts two same-category failures with different payloads produce byte-identical `Error()` strings but different structured attributes.
