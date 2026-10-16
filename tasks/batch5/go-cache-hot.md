# Task: Build a Sharded Feature-Flag Resolver

## Background

The `github.com/samber/hot` repository is a generic, type-safe in-memory caching library for Go (`module github.com/samber/hot`, Go 1.22+). This task adds an application-level **feature-flag resolver** in a new package under `pkg/` that answers "is flag F enabled for tenant T?" at very high concurrency, caching resolved flag values per `(tenant, flag)` key and spreading contention across multiple independent partitions so a hot key does not serialize all readers. The package must compile as part of the main module and be exercised by a deterministic in-process test.

## Files to Create/Modify

- `pkg/flags/flags.go` (new) — the `FlagResolver` implementation.
- `pkg/flags/flags_test.go` (new) — the deterministic unit tests described in the Acceptance Criteria.

Both files belong to a new package `flags` and may import `github.com/samber/hot` plus the standard library only. Do not add new third-party dependencies and do not modify `go.mod`.

## Requirements

### Types and backend

```go
type FlagState struct {
    Tenant  string
    Flag    string
    Enabled bool
}

// Provider is the slow source that decides flag states.
type Provider interface {
    // Resolve is given a batch of composite keys (one string per
    // tenant/flag pair) and returns the states it could resolve, keyed by
    // the same composite key. Unresolvable keys are absent. A non-nil error
    // is an infrastructure failure.
    Resolve(keys []string) (map[string]*FlagState, error)
}
```

### Constructor

```go
func NewFlagResolver(p Provider, shards uint64, capacityPerShard int, ttl time.Duration) *FlagResolver
```

- The resolver must internally partition its cached entries across exactly `shards` independent partitions so that operations on keys landing in different partitions do not block one another.
- `capacityPerShard` bounds the entries held in each partition.
- `Close()` must release any background machinery so no goroutines leak.

### Lookup behavior

`func (r *FlagResolver) IsEnabled(tenant, flag string) (bool, bool, error)` returns `(enabled, found, err)`:

- `(state.Enabled, true, nil)` when the pair resolves.
- `(false, false, nil)` when the provider confirms the pair is unresolvable.
- `(false, false, err)` on infrastructure failure (not remembered as a result).

The resolver must derive a single composite cache key from `(tenant, flag)` deterministically, such that the same pair always maps to the same key and the same partition.

### Reducing backend pressure & partitioning

- A repeated `IsEnabled` for the same pair within `ttl` must not consult the provider again.
- Distinct pairs must distribute across the `shards` partitions — not all collapse into one — so that the per-partition capacity (`capacityPerShard`) is what bounds memory, and entries in one partition are evicted independently of other partitions.
- After `ttl`, the next lookup for a pair may consult the provider again.

### Concurrency and dedup

Safe for concurrent use. A burst of concurrent `IsEnabled` calls for the **same** uncached pair must collapse into a single `Resolve` for that key.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| First `IsEnabled(t,f)` resolvable | `Resolve` called once; `(enabled, true, nil)` |
| Repeat within `ttl` | No provider call; same answer |
| Unresolvable pair | `(false, false, nil)`; provider asked once |
| After `ttl` | Provider may be consulted again |
| Many distinct pairs across the keyspace | Entries spread across the `shards` partitions |
| 50 concurrent lookups of one uncached pair | Provider asked once for that key |

## Acceptance Criteria

- `pkg/flags/flags.go` compiles with `go build ./...` from the repository root.
- A test `Provider` that records per-composite-key `Resolve` counts (safe under concurrency) asserts in `pkg/flags/flags_test.go`:
  - The same `(tenant, flag)` pair looked up twice in a row triggers exactly **one** `Resolve` and returns the same `enabled` value.
  - An unresolvable pair returns `found=false` and is resolved at most once across repeated lookups within `ttl`.
  - The resolver is constructed with `shards > 1`; after inserting many distinct pairs, the implementation demonstrably uses more than one partition (assert via a resolver-exposed accessor — e.g. a method returning per-shard lengths or total length together with a shard count — such that the entries are not all concentrated in a single partition).
  - Launching at least 50 goroutines that all look up the same uncached pair triggers exactly **one** `Resolve` for that key (use a `Resolve` that blocks briefly), and all goroutines observe the same result.
  - After a short `ttl` elapses, a re-lookup of a previously-resolved pair allows a fresh `Resolve`.
  - After `Close()`, `go.uber.org/goleak` reports no leaked goroutines.
- The following command, run from the repository root, passes:

```
go test ./pkg/flags/ -run TestFlags -count=1
```

(A naive implementation that uses a single undivided cache, that re-resolves on every lookup, that derives non-deterministic keys, or that fans out concurrent identical lookups must fail at least one test.)
