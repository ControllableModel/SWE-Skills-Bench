# Task: Build a Copy-Isolated Config Snapshot Cache

## Background

The `github.com/samber/hot` repository is a generic, type-safe in-memory caching library for Go (`module github.com/samber/hot`, Go 1.22+). This task adds an application-level **config snapshot cache** in a new package under `pkg/` that hands out per-namespace configuration objects loaded from a slow store. Callers routinely mutate the config they receive (toggle a key, append to a list) before using it, so the cache must guarantee that one caller's edits never leak into the copy another caller later receives. The package must compile as part of the main module and be exercised by a deterministic in-process test.

## Files to Create/Modify

- `pkg/configcache/configcache.go` (new) — the `ConfigCache` implementation.
- `pkg/configcache/configcache_test.go` (new) — the deterministic unit tests described in the Acceptance Criteria.

Both files belong to a new package `configcache` and may import `github.com/samber/hot` plus the standard library only. Do not add new third-party dependencies and do not modify `go.mod`.

## Requirements

### Types and store

```go
type Config struct {
    Namespace string
    Settings  map[string]string // mutable
    Allow     []string          // mutable
}

// Store is the slow source of truth for configs.
type Store interface {
    // Get returns the config for namespace, or (nil, false, nil) if none
    // exists. A non-nil error is an infrastructure failure.
    Get(namespace string) (*Config, bool, error)
}
```

### Constructor

```go
func NewConfigCache(store Store, capacity int, ttl time.Duration) *ConfigCache
```

`Close()` must release any background machinery so no goroutines leak.

### Resolve behavior and mutation isolation

`func (c *ConfigCache) Resolve(namespace string) (*Config, bool, error)`:

- `(config, true, nil)` when it exists; resolving the same namespace again within `ttl` does not re-consult `store`.
- `(nil, false, nil)` when the store confirms none exists.
- `(nil, false, err)` on infrastructure failure (not remembered).

Mutation isolation is the central requirement:

- A caller that mutates a returned `*Config` — reassigning or writing into its `Settings` map, appending to or overwriting elements of its `Allow` slice — must not affect the `*Config` that any **later** caller receives for the same namespace from the in-memory store.
- This must hold even though the underlying entry stays cached between the two resolves (i.e. no `store` re-fetch happens in between). In other words, each `Resolve` must yield an independently-mutable view; the maps and slices reachable from one returned `*Config` must not be the same underlying maps/slices reachable from another returned `*Config` for that namespace.
- Mutating a returned config must likewise not corrupt the object the store originally supplied.

### Concurrency and dedup

Safe for concurrent use. A burst of concurrent `Resolve` calls for the **same** uncached namespace must collapse into a single `store.Get`, and each caller must still receive an independently-mutable view.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| First `Resolve("svc")` exists | `store.Get` once; `found=true` |
| Re-resolve within `ttl` | No store call |
| Caller writes `Settings["x"]="y"`, re-resolves | Fresh config lacks `x` |
| Caller appends to `Allow`, re-resolves | Fresh config's `Allow` unchanged |
| Unknown namespace | `found=false`, no error |
| 50 concurrent resolves of one uncached namespace | `store.Get` once; each gets isolated copy |

## Acceptance Criteria

- `pkg/configcache/configcache.go` compiles with `go build ./...` from the repository root.
- A test `Store` recording per-namespace `Get` counts (safe under concurrency) asserts in `pkg/configcache/configcache_test.go`:
  - An existing namespace resolved twice in a row triggers exactly **one** `Get`.
  - After a first `Resolve`, writing a new key into the returned config's `Settings` map AND appending a new element to its `Allow` slice, then resolving the same namespace again (served from memory, no new `Get`), yields a config whose `Settings` does **not** contain the injected key and whose `Allow` does **not** contain the appended element.
  - Two `Resolve` results for the same namespace do not share the same underlying `Settings` map header or `Allow` backing array such that mutating one is observable in the other (demonstrate by mutating the first and re-reading via a second resolve).
  - An unknown namespace returns `found=false` with no error.
  - Launching at least 50 goroutines resolving the same uncached namespace triggers exactly **one** `Get` (use a blocking `Get`), and each goroutine, after independently mutating its returned config, does not affect the others' or a final fresh resolve's contents.
  - After `Close()`, `go.uber.org/goleak` reports no leaked goroutines.
- The following command, run from the repository root, passes:

```
go test ./pkg/configcache/ -run TestConfigCache -count=1
```

(A naive implementation that returns the same shared `*Config` pointer or shares its inner maps/slices between callers, that re-fetches on every resolve, or that never expires entries must fail at least one test.)
