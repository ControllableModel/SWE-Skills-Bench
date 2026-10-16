# Task: Build a Layered Payment Settlement Module

## Background

The `samber/oops` repository ships several self-contained demonstration modules under `examples/` (each its own Go module, wired into the workspace via `go.work`). This task adds a new example module, `examples/settlement`, that models a three-layer payment-settlement flow and propagates a single failure outward so the final error carries information contributed by every layer it passed through.

## Files to Create/Modify

- `examples/settlement/settlement.go` (new) — the gateway/service/handler layers and their error-producing functions.
- `examples/settlement/settlement_test.go` (new) — the deterministic table tests described below.
- `examples/settlement/go.mod` (new) — module `github.com/samber/oops/examples/settlement`, Go 1.21, requiring `github.com/samber/oops`.
- `go.work` (modify) — add `./examples/settlement` to the `use (...)` block so the module resolves the in-repo `github.com/samber/oops`.

## Requirements

The module simulates one settlement attempt that flows through three in-process layers. There is no network, database, or running server — the "gateway" is a function backed by in-memory data.

### Domain types

Define exported types in `examples/settlement/settlement.go`:

- `Charge struct { ID string; AccountID string; AmountCents int; Currency string }`
- A `Gateway` type with a constructor `NewGateway(balanceCents map[string]int) *Gateway`, where the map is account-id -> available balance in cents.

### Entry point

Provide a single exported function:

```go
func Settle(g *Gateway, charge Charge) error
```

`Settle` is the outermost (handler) layer. It MUST delegate to an intermediate service layer, which MUST delegate to a gateway layer; each of those three layers MUST add its own contextual attribute(s) to the error before returning it, so that a single returned error aggregates information from all three.

### Failure behaviors

Every non-nil error returned from `Settle` MUST be inspectable as a `samber/oops` error (`oops.AsOops(err)` returns `ok == true`) and MUST expose:

1. **Unknown account** — when `charge.AccountID` is not present in the gateway balance map:
   - `Code()` equals `"account_not_found"`.
   - the error context contains `"account_id"` equal to the requested account id.
   - the originating (deepest) layer domain (`Domain()`) is `"settlement-gateway"`.
2. **Insufficient funds** — when the account exists but `charge.AmountCents` exceeds its balance:
   - `Code()` equals `"insufficient_funds"`.
   - context contains `"amount_cents"` (equal to the charge amount) and `"balance_cents"` (equal to the account balance) as separate entries.
   - the public-facing message (via `oops.GetPublic(err, "<fallback>")`) equals `"Payment could not be completed."`.
3. **Unsupported currency** — when `charge.Currency` is not `"USD"`:
   - `Code()` equals `"unsupported_currency"`.
   - context contains `"currency"` equal to the supplied currency.

For every failure, the error MUST expose a non-empty `Owner()` identifying the responsible team and a non-empty `Hint()` for the on-call engineer, and these MUST be identical regardless of which failure category occurred.

### Success

When the account exists, the currency is `"USD"`, and `0 < charge.AmountCents <= balance`, `Settle` returns `nil`.

### Message cardinality constraint

For each failure category, the value returned by `err.Error()` MUST be constant for that category — it MUST NOT change when `ID`, `AccountID`, `AmountCents`, or `Currency` change. The variable details MUST instead be retrievable through `Context()`. The tests assert this by triggering the same failure category with two different charges and comparing the two error strings for exact equality while confirming the context maps differ.

### Expected Functionality

- `Settle(g, {AccountID:"ghost", AmountCents:100, Currency:"USD"})` -> code `account_not_found`, context `account_id == "ghost"`, deepest domain `settlement-gateway`.
- `Settle(g, {AccountID:"acc-1", AmountCents:9999, Currency:"USD"})` where balance is 500 -> code `insufficient_funds`, context `amount_cents == 9999`, `balance_cents == 500`, public message `"Payment could not be completed."`.
- `Settle(g, {AccountID:"acc-1", AmountCents:100, Currency:"EUR"})` -> code `unsupported_currency`, context `currency == "EUR"`.
- `Settle(g, {AccountID:"acc-1", AmountCents:100, Currency:"USD"})` where balance is 500 -> `nil`.

## Acceptance Criteria

- `examples/settlement/go.mod` declares module `github.com/samber/oops/examples/settlement` and `go.work` lists `./examples/settlement`, so the new module compiles against the in-repo library.
- A naive implementation that hardcodes one message/code for all failures, or interpolates variable data into the message string, fails the tests.
- The added tests are deterministic (in-memory only) and pass:

```
go test ./examples/settlement/...
```

  run from the repository root, including the three failure cases, the success case, the constant `Owner()`/`Hint()` assertions, and the message-cardinality case.
