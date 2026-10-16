# Task: Build a Hit-Rate-Reporting Avatar Cache

## Background

The `github.com/samber/hot` repository is a generic, type-safe in-memory caching library for Go (`module github.com/samber/hot`, Go 1.22+). This task adds an application-level **avatar cache** in a new package under `pkg/` that serves user avatar blobs from a slow object store and exposes operational counters — how many reads were served from memory versus how many fell through to the store — so operators can tell whether the cache is sized correctly. The package must compile as part of the main module and be exercised by a deterministic in-process test.

## Files to Create/Modify

- `pkg/avatar/avatar.go` (new) — the `AvatarCache` implementation.
- `pkg/avatar/avatar_test.go` (new) — the deterministic unit tests described in the Acceptance Criteria.

Both files belong to a new package `avatar` and may import `github.com/samber/hot` plus the standard library only. Do not add new third-party dependencies and do not modify `go.mod`.

## Requirements

### Types and backend

```go
type Avatar struct {
    UserID string
    Blob   []byte
}

// ObjectStore is the slow backing store.
type ObjectStore interface {
    // Get returns the avatar for userID, or (nil, false, nil) if none exists.
    // A non-nil error is an infrastructure failure.
    Get(userID string) (*Avatar, bool, error)
}

// Stats is an immutable snapshot of cache counters.
type Stats struct {
    Hits   int64 // reads served from memory
    Misses int64 // reads that fell through to the store
}
```

### Constructor

```go
func NewAvatarCache(store ObjectStore, capacity int, ttl time.Duration) *AvatarCache
```

`Close()` must release any background machinery so no goroutines leak.

### Fetch behavior

`func (c *AvatarCache) Fetch(userID string) (*Avatar, bool, error)`:

- `(avatar, true, nil)` when it exists; resolving the same id again within `ttl` is served from memory without consulting the store.
- `(nil, false, nil)` when the store confirms none exists.
- `(nil, false, err)` on infrastructure failure (not remembered).

### Hit/miss accounting

`func (c *AvatarCache) Stats() Stats` returns a snapshot of counters that obey these rules:

- A read served entirely from memory (the value, fresh, was already resident) counts as exactly **one hit** and **zero misses**.
- A read that had to consult the store — because the id was never cached, was evicted, or expired — counts as exactly **one miss** (it does not also count as a hit), regardless of whether the store ultimately had the value.
- An infrastructure error during a store consultation counts the attempt as a **miss** (it left memory and went to the backend), and does not later flip to a hit.
- Counters are monotonically non-decreasing and must be safe to read concurrently with ongoing `Fetch` calls.
- Each `Fetch` call adjusts the counters by exactly one (one read = one hit XOR one miss); `Stats().Hits + Stats().Misses` must equal the total number of completed `Fetch` calls.

### Concurrency and dedup

Safe for concurrent use. A burst of concurrent `Fetch` calls for the **same** uncached id must collapse into a single `store.Get`. (For counting purposes, callers that block waiting on that shared store consultation are reads that went to the backend and therefore count as misses, not hits.)

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| First `Fetch("u1")` exists | Store once; `+1 miss` |
| Re-fetch within `ttl` | No store call; `+1 hit` |
| Re-fetch after `ttl` | Store again; `+1 miss` |
| Unknown id | `found=false`; `+1 miss` |
| Store errors | error; `+1 miss`; not cached |
| `Hits + Misses` | equals total completed `Fetch` calls |

## Acceptance Criteria

- `pkg/avatar/avatar.go` compiles with `go build ./...` from the repository root.
- A test `ObjectStore` recording per-id `Get` counts (safe under concurrency) asserts in `pkg/avatar/avatar_test.go`:
  - Starting from a fresh cache, the first `Fetch` of an existing id records exactly one miss and zero hits; an immediate second `Fetch` of the same id records one additional hit and no additional miss, and does not call the store again.
  - After a short `ttl` elapses, re-fetching the same id calls the store again and records an additional **miss** (not a hit).
  - A `Fetch` of an unknown id records a miss; the store reports `found=false`.
  - A store error records a miss and is not cached: a subsequent healthy `Fetch` of the same id resolves normally.
  - For any deterministic sequence of `Fetch` calls, the final `Stats().Hits + Stats().Misses` equals the exact number of `Fetch` calls made, and the individual hit/miss counts match the expected outcome of each call in the sequence.
  - Launching at least 50 goroutines fetching the same uncached id triggers exactly **one** `store.Get` (use a blocking `Get`); afterward a final fetch of that id (now resident) records a hit.
  - After `Close()`, `go.uber.org/goleak` reports no leaked goroutines.
- The following command, run from the repository root, passes:

```
go test ./pkg/avatar/ -run TestAvatar -count=1
```

(A naive implementation that miscounts a memory-served read as a miss or a backend read as a hit, that re-fetches on every call, that caches errors, or whose counters drift from the total call count must fail at least one test.)
