# Task: Build a Negative-Caching Name Resolver

## Background

The `github.com/samber/hot` repository is a generic, type-safe in-memory caching library for Go (`module github.com/samber/hot`, Go 1.22+). This task adds an application-level **name resolver** in a new package under `pkg/` that maps hostnames to addresses through a slow lookup service. The service is frequently asked about hostnames that simply do not exist, so the resolver must remember those negative answers separately and briefly — for a shorter time than positive answers — so repeated misses do not hammer the backend, while bad negatives still age out quickly. The package must compile as part of the main module and be exercised by a deterministic in-process test.

## Files to Create/Modify

- `pkg/resolver/resolver.go` (new) — the `Resolver` implementation.
- `pkg/resolver/resolver_test.go` (new) — the deterministic unit tests described in the Acceptance Criteria.

Both files belong to a new package `resolver` and may import `github.com/samber/hot` plus the standard library only. Do not add new third-party dependencies and do not modify `go.mod`.

## Requirements

### Types and backend

```go
type Record struct {
    Host string
    Addr string
}

// Service is the slow name-lookup backend.
type Service interface {
    // Lookup returns the record for host, or (nil, false, nil) if the host
    // is confirmed not to exist. A non-nil error is an infrastructure failure.
    Lookup(host string) (*Record, bool, error)
}
```

### Constructor

```go
func NewResolver(svc Service, capacity int, positiveTTL, negativeTTL time.Duration) *Resolver
```

- `positiveTTL` governs how long a successfully resolved record stays usable.
- `negativeTTL` governs how long a confirmed "no such host" answer is remembered before the backend may be consulted again. `negativeTTL` is expected to be shorter than `positiveTTL`.
- `Close()` must release any background machinery so no goroutines leak.

### Resolve behavior

`func (r *Resolver) Resolve(host string) (*Record, bool, error)`:

- `(record, true, nil)` when the host exists.
- `(nil, false, nil)` when the backend confirms the host does not exist — **and this negative answer must be remembered** so an immediate repeat does not consult the backend again.
- `(nil, false, err)` on infrastructure failure; a failure is **not** remembered as either a positive or a negative result.

### Distinct TTLs for hits vs misses

- A positive answer must be served from memory, without consulting the backend, for up to `positiveTTL`.
- A negative answer ("no such host") must be served from memory, without consulting the backend, for up to `negativeTTL` — and then must be allowed to re-consult the backend, so a host that did not exist but now does becomes resolvable shortly after `negativeTTL` even while `positiveTTL` (which is longer) has not yet elapsed.
- Concretely: with `negativeTTL` short and `positiveTTL` long, a host that returns "not found" on the first call and "found" on later calls must (a) not be re-queried during the negative window, and (b) become resolvable once `negativeTTL` passes.

### Concurrency and dedup

Safe for concurrent use. A burst of concurrent `Resolve` calls for the **same** uncached host must collapse into a single backend `Lookup`, whether that host turns out to exist or not.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| First `Resolve("a")` exists | Backend once; `found=true` |
| Repeat within `positiveTTL` | No backend call |
| First `Resolve("z")` does not exist | `found=false`; backend once |
| Repeat within `negativeTTL` | No backend call; still `found=false` |
| After `negativeTTL` for `z` (now existing) | Backend consulted; `found=true` |
| Backend errors for `b` | error returned; later healthy `Resolve("b")` works |
| 50 concurrent resolves of one uncached host | Backend once |

## Acceptance Criteria

- `pkg/resolver/resolver.go` compiles with `go build ./...` from the repository root.
- A test `Service` recording per-host `Lookup` counts (safe under concurrency), able to switch a given host from "not found" to "found", asserts in `pkg/resolver/resolver_test.go`:
  - An existing host resolved twice within `positiveTTL` triggers exactly **one** backend `Lookup`.
  - A non-existent host resolved twice within `negativeTTL` returns `found=false` both times and triggers exactly **one** backend `Lookup` (the negative answer is remembered).
  - With `negativeTTL` short and `positiveTTL` long: a host that is "not found" initially, queried once (cached negative), then flipped to "found" in the service, becomes resolvable (`found=true`) only after waiting past `negativeTTL` — and the re-query happens well before `positiveTTL` would have elapsed.
  - A backend error for a host makes `Resolve` return a non-nil error and is **not** cached as a negative: a subsequent healthy call resolves normally.
  - Launching at least 50 goroutines resolving the same uncached host triggers exactly **one** backend `Lookup` (use a blocking `Lookup`).
  - After `Close()`, `go.uber.org/goleak` reports no leaked goroutines.
- The following command, run from the repository root, passes:

```
go test ./pkg/resolver/ -run TestResolver -count=1
```

(A naive implementation that does not remember negative answers, that uses one shared TTL for hits and misses, that caches infrastructure errors, or that re-queries on every miss must fail at least one test.)
