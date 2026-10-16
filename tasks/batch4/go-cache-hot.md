# Task: Build a Stale-While-Revalidate Price Feed

## Background

The `github.com/samber/hot` repository is a generic, type-safe in-memory caching library for Go (`module github.com/samber/hot`, Go 1.22+). This task adds an application-level **price feed** in a new package under `pkg/` that serves the last-known price for a symbol immediately — even slightly outdated — while refreshing it from a slow upstream in the background, so reads never block on the upstream once a price is warm. The package must compile as part of the main module and be exercised by a deterministic in-process test.

## Files to Create/Modify

- `pkg/pricefeed/pricefeed.go` (new) — the `PriceFeed` implementation.
- `pkg/pricefeed/pricefeed_test.go` (new) — the deterministic unit tests described in the Acceptance Criteria.

Both files belong to a new package `pricefeed` and may import `github.com/samber/hot` plus the standard library only. Do not add new third-party dependencies and do not modify `go.mod`.

## Requirements

### Types and upstream

```go
type Quote struct {
    Symbol string
    Price  int64 // price in cents, monotonically updated by the upstream
}

// Upstream is the slow price source.
type Upstream interface {
    // Fetch returns current quotes for the requested symbols, keyed by symbol.
    // Unknown symbols are absent. A non-nil error is an infrastructure failure.
    Fetch(symbols []string) (map[string]*Quote, error)
}
```

### Constructor

```go
func NewPriceFeed(up Upstream, capacity int, fresh, stale time.Duration) *PriceFeed
```

- `fresh` is the window during which a cached quote is considered fully current.
- `stale` is an additional window after `fresh` during which a cached quote may still be **served immediately**, but the next read should trigger a background refresh of that symbol from `up`.
- Beyond `fresh + stale`, a quote is fully expired and must be re-fetched before it can be served.
- `Close()` must release any background machinery so no goroutines leak.

### Read behavior

`func (f *PriceFeed) Price(symbol string) (*Quote, bool, error)` must:

- On a cold symbol, fetch synchronously and return the result (`found=true` if it exists, `found=false` if the upstream has no such symbol, `err` on infrastructure failure; a failure is not remembered).
- While a quote is within `fresh`, return the cached quote without contacting `up`.
- While a quote is within the `stale` window (older than `fresh`, younger than `fresh + stale`), return the cached (possibly slightly old) quote **immediately**, and arrange for that symbol to be refreshed from `up` so that a later read observes the newer price without a synchronous upstream call.
- Once a quote passes `fresh + stale`, the next read must fetch synchronously again.

### Concurrency

Safe for concurrent use. Concurrent reads of the same cold symbol must collapse into a single synchronous upstream fetch. A burst of reads of a symbol in its stale window must not spawn a separate refresh per read.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| Cold read of `AAPL` | Synchronous `Fetch`; quote returned, `found=true` |
| Read within `fresh` | No upstream call; cached quote |
| Read within stale window | Cached quote returned immediately; symbol refreshed in background |
| Later read after a background refresh settled | Newer price observed without a synchronous upstream call |
| Read past `fresh+stale` | Synchronous `Fetch` again |
| Unknown symbol | `found=false`, no error |

## Acceptance Criteria

- `pkg/pricefeed/pricefeed.go` compiles with `go build ./...` from the repository root.
- A test `Upstream` whose returned price for a symbol increases on each `Fetch`, and which records per-symbol `Fetch` counts (safe under concurrency), asserts in `pkg/pricefeed/pricefeed_test.go`:
  - A cold read fetches once; an immediate second read within `fresh` does not fetch again and returns the same price.
  - After the `fresh` window passes but within `stale`, a read returns a value **immediately** (it must return the previously-cached price, i.e. it does not block waiting for a brand-new upstream value), and a subsequent read — after allowing the background refresh to complete — observes the **newer** price without itself performing a synchronous fetch. (Drive timing with short, deterministic `fresh`/`stale` durations and a brief settle wait, not by racing.)
  - After `fresh + stale` elapses, the next read performs a synchronous fetch and returns the newest price.
  - An unknown symbol returns `found=false` with no error.
  - Launching at least 50 goroutines reading the same cold symbol triggers exactly **one** synchronous fetch (use a `Fetch` that blocks briefly).
  - After `Close()`, `go.uber.org/goleak` reports no leaked goroutines.
- The following command, run from the repository root, passes:

```
go test ./pkg/pricefeed/ -run TestPriceFeed -count=1
```

(A naive implementation that blocks the caller on the upstream during the stale window, that never refreshes stale entries, that treats stale the same as expired, or that re-fetches on every read must fail at least one test.)
