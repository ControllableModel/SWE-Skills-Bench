# Task: Build a Pre-Warmed Country Catalog

## Background

The `github.com/samber/hot` repository is a generic, type-safe in-memory caching library for Go (`module github.com/samber/hot`, Go 1.22+). This task adds an application-level **country reference catalog** in a new package under `pkg/` that loads a small, fixed, low-cardinality dataset once at startup so the very first user request is already a hit, while still falling back to a slow loader for any id not present in the initial set. The package must compile as part of the main module and be exercised by a deterministic in-process test.

## Files to Create/Modify

- `pkg/catalog/catalog.go` (new) — the `Catalog` implementation.
- `pkg/catalog/catalog_test.go` (new) — the deterministic unit tests described in the Acceptance Criteria.

Both files belong to a new package `catalog` and may import `github.com/samber/hot` plus the standard library only. Do not add new third-party dependencies and do not modify `go.mod`.

## Requirements

### Types and loaders

```go
type Country struct {
    Code string
    Name string
}

// Bootstrap supplies the full initial dataset, computed once at startup.
type Bootstrap func() (map[string]*Country, error)

// Loader resolves a single code on demand for ids not in the bootstrap set.
type Loader interface {
    // Load returns the country for code, or (nil, false, nil) if no such
    // country exists. A non-nil error is an infrastructure failure.
    Load(code string) (*Country, bool, error)
}
```

### Constructor

```go
func NewCatalog(boot Bootstrap, loader Loader, capacity int, ttl time.Duration) (*Catalog, error)
```

- During construction, the catalog must populate itself from `boot` so that every code present in the bootstrap map is already resident **before** any `Lookup` call. If `boot` returns an error, `NewCatalog` returns that error and no usable catalog.
- `Close()` must release any background machinery so no goroutines leak.

### Lookup behavior

`func (c *Catalog) Lookup(code string) (*Country, bool, error)`:

- A code present in the bootstrap set must resolve from memory on its **first** lookup without ever invoking `loader.Load` for it (proving warm-up actually populated the catalog).
- A code absent from the bootstrap set falls back to `loader.Load`, then is cached like any resolved entry; a second lookup within `ttl` does not call `loader.Load` again.
- `(nil, false, nil)` when neither the bootstrap set nor the loader knows the code.
- `(nil, false, err)` on loader infrastructure failure (not remembered).

### Introspection

- `func (c *Catalog) Len() int` returns the number of resident entries.
- `func (c *Catalog) Codes() []string` returns the codes currently resident (order unspecified). Immediately after construction these must include every bootstrap code.

### Concurrency and dedup

Safe for concurrent use. A burst of concurrent `Lookup` calls for the **same** non-bootstrap, uncached code must collapse into a single `loader.Load`.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| Construct with N bootstrap countries | `Len() >= N`; `Codes()` contains all bootstrap codes |
| First `Lookup` of a bootstrap code | Served from memory; `loader.Load` never called for it |
| `Lookup` of a non-bootstrap code | `loader.Load` called once; cached afterwards |
| Re-lookup within `ttl` | No loader call |
| Unknown code (neither source) | `found=false`, no error |
| `boot` returns error | `NewCatalog` returns that error |
| 50 concurrent lookups of one uncached non-bootstrap code | `loader.Load` called once |

## Acceptance Criteria

- `pkg/catalog/catalog.go` compiles with `go build ./...` from the repository root.
- A test `Loader` recording per-code `Load` counts (safe under concurrency) and a `Bootstrap` returning a known fixed set assert in `pkg/catalog/catalog_test.go`:
  - After `NewCatalog` succeeds, `Codes()` contains every bootstrap code and `Len()` is at least the bootstrap size.
  - Looking up a bootstrap code returns it correctly while the loader's `Load` count for that code stays **zero**.
  - Looking up a non-bootstrap, existing code calls `Load` exactly once; an immediate second lookup does not call `Load` again.
  - A `Bootstrap` that returns an error makes `NewCatalog` return a non-nil error and a nil (unusable) catalog.
  - An unknown code returns `found=false` with no error.
  - Launching at least 50 goroutines looking up the same uncached non-bootstrap code triggers exactly **one** `Load` (use a blocking `Load`).
  - After `Close()`, `go.uber.org/goleak` reports no leaked goroutines.
- The following command, run from the repository root, passes:

```
go test ./pkg/catalog/ -run TestCatalog -count=1
```

(A naive implementation that lazily loads bootstrap codes on first access instead of pre-populating, that ignores a bootstrap error, that re-loads on every lookup, or that never expires entries must fail at least one test.)
