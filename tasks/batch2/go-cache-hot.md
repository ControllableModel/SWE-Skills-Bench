# Task: Build a Sliding-Expiry Session Store

## Background

The `github.com/samber/hot` repository is a generic, type-safe in-memory caching library for Go (`module github.com/samber/hot`, Go 1.22+). This task adds an application-level **session store** in a new package under `pkg/` that keeps live web sessions in memory and discards idle ones, without re-reading sessions from a slow backing store more often than necessary. The package must compile as part of the main module and be exercised by a deterministic in-process test.

## Files to Create/Modify

- `pkg/session/session.go` (new) — the `SessionStore` implementation.
- `pkg/session/session_test.go` (new) — the deterministic unit tests described in the Acceptance Criteria.

Both files belong to a new package `session` and may import `github.com/samber/hot` plus the standard library only. Do not add new third-party dependencies and do not modify `go.mod`.

## Requirements

### Types and backend

```go
type Session struct {
    ID       string
    UserID   string
    Roles    []string
}

// Store is the slow source of truth for sessions (e.g. a database table).
type Store interface {
    // Load returns the session for id, or (nil, false, nil) if no such
    // session exists. A non-nil error means an infrastructure failure.
    Load(id string) (*Session, bool, error)
}
```

### Constructor

```go
func NewSessionStore(store Store, capacity int, idleTTL time.Duration) *SessionStore
```

- `capacity` bounds the number of sessions held in memory.
- `idleTTL` is how long a session may remain in memory after its **most recent** access before it must be re-loaded from `store`.
- The store owns any background machinery it starts; `Close()` must release it so no goroutines leak.

### Access behavior

`func (s *SessionStore) Access(id string) (*Session, bool, error)` must:

- Return `(session, true, nil)` for a session that exists.
- Return `(nil, false, nil)` when `store` confirms no such session.
- Return `(nil, false, err)` on infrastructure failure, and must **not** remember a failed access as a result.

### Sliding expiry (recency-driven)

- Each successful `Access` of an id refreshes that session's in-memory lifetime, so a session that is touched repeatedly within `idleTTL` stays resident and is served without re-loading from `store`.
- A session that is **not** accessed for longer than `idleTTL` must be re-loaded from `store` on its next access.
- When the number of distinct live sessions exceeds `capacity`, the sessions evicted to stay within `capacity` must be the **least-recently accessed** ones: given a workload where a small hot set of session ids is accessed continuously while many cold ids are accessed once, the hot set must remain memory-resident (re-access does not re-load `store`) while the cold ids get evicted.

### Concurrency and dedup

Safe for concurrent use. A burst of concurrent `Access` calls for the **same** currently-uncached id must collapse into a single `store.Load` for that id, shared by all waiting callers.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| First `Access` of existing id `A` | `store.Load` called once; `found=true` |
| Re-access `A` within `idleTTL` | No new `store.Load`; lifetime refreshed |
| `A` idle past `idleTTL`, then accessed | `store.Load` called again |
| Hot id touched each round while cold ids flood past `capacity` | Hot id never re-loaded; cold ids evicted |
| 50 concurrent accesses of one uncached id | Exactly one `store.Load` for that id |
| `store.Load` returns an error for `B` | `Access("B")` returns the error; a later healthy `Access("B")` succeeds |

## Acceptance Criteria

- `pkg/session/session.go` compiles with `go build ./...` from the repository root.
- A test `Store` that records per-id `Load` call counts (safe under concurrency) asserts in `pkg/session/session_test.go`:
  - An existing id accessed twice within `idleTTL` triggers exactly **one** `Load`, returning identical data both times.
  - After waiting past a short `idleTTL`, re-accessing the same id triggers a **second** `Load`.
  - With `capacity` small, a single continuously-touched hot id survives a flood of `> capacity` distinct cold ids: the hot id is loaded exactly once across the whole test while at least one cold id, re-accessed after eviction, is loaded again.
  - Launching at least 50 goroutines that each `Access` the same previously-uncached id results in exactly **one** `Load` (use a `Load` that blocks briefly so the window is real), and every goroutine observes `found=true`.
  - A `Load` that errors on the first attempt for an id makes `Access` return a non-nil error; a later attempt (store now healthy) succeeds, proving the failure was not cached.
  - After `Close()`, `go.uber.org/goleak` (already a test dependency) reports no leaked goroutines (`goleak.VerifyTestMain` or `goleak.VerifyNone(t)`).
- The following command, run from the repository root, passes:

```
go test ./pkg/session/ -run TestSession -count=1
```

(A naive implementation that re-loads on every access, that uses a fixed expiry not refreshed on access, that evicts arbitrarily rather than by recency, or that lets sessions live forever must fail at least one test.)
