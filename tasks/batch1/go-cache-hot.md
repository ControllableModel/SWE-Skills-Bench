# Task: Build a Read-Through Contact Directory Service

## Background

The `github.com/samber/hot` repository is a generic, type-safe in-memory caching library for Go. This task adds a small **application-level service** that lives inside the repository (a new package under `pkg/`) and uses the library to serve contact records from a slow backing store without hammering that store. The package must compile as part of the main module (`module github.com/samber/hot`, Go 1.22+) and be exercised by a deterministic in-process test.

## Files to Create/Modify

- `pkg/directory/directory.go` (new) — the `DirectoryService` implementation.
- `pkg/directory/directory_test.go` (new) — the deterministic unit tests described in the Acceptance Criteria.

Both files belong to a new package `directory` and may import `github.com/samber/hot` plus the standard library only. Do not add new third-party dependencies and do not modify `go.mod`.

## Requirements

### Backend abstraction

Define an exported interface that represents the slow source of truth:

```go
type Contact struct {
    ID    string
    Name  string
    Email string
    Tags  []string
}

type Backend interface {
    // Fetch is given a batch of IDs and returns the records that exist,
    // keyed by ID. IDs that do not exist are simply absent from the result.
    // Fetch returns an error only on an infrastructure failure.
    Fetch(ids []string) (map[string]*Contact, error)
}
```

### Constructor

Provide:

```go
func NewDirectoryService(backend Backend, capacity int, ttl time.Duration) *DirectoryService
```

- `capacity` is the maximum number of records held in memory at once.
- `ttl` is how long a successfully resolved record stays usable before it must be obtained from the backend again.
- The service owns any background machinery it starts; calling `Close()` must release it so no goroutines leak after the service is discarded.

### Lookup behavior

`func (s *DirectoryService) Lookup(id string) (*Contact, bool, error)` must:

- Return `(record, true, nil)` when a contact with that ID exists.
- Return `(nil, false, nil)` when the backend confirms no such contact exists.
- Return `(nil, false, err)` when the backend reports an infrastructure failure; a failed lookup must **not** be remembered as a result.

### Reducing backend pressure

The whole point of the service is to avoid redundant backend work for the same medium-cardinality set of IDs queried at high frequency:

- A second `Lookup` for an ID that was already resolved (whether it existed or not) must be answered **without** consulting the backend again, as long as the record has not expired.
- Repeatedly looking up an ID that the backend reports as **non-existent** must also stop hitting the backend on subsequent calls — a confirmed "no such contact" is itself worth remembering, not just successful records.
- When `ttl` has elapsed for a given ID, the next lookup for that ID is allowed to consult the backend again.
- When many distinct IDs are looked up far in excess of `capacity`, memory must stay bounded to roughly `capacity` live records rather than growing without limit.

### Concurrency and dedup

The service must be safe to call from many goroutines simultaneously. When a large burst of concurrent `Lookup` calls arrives for the **same** currently-uncached ID, the backend must not be asked for that ID once per call — the concurrent demand must collapse into a single backend request whose result is shared by all the waiting callers.

### Mutation isolation

The records the service hands back must be insulated from each other across calls:

- A caller that mutates a returned `*Contact` (including appending to its `Tags` slice) must not corrupt the copy that a later caller receives for the same ID from the in-memory store.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| First lookup of existing ID `A` | Backend asked once; returns the contact, `found=true` |
| Immediate second lookup of `A` | Backend not asked again; same data returned |
| Lookup of ID `Z` that does not exist | `found=false`, no error; backend asked once |
| Second lookup of non-existent `Z` | Backend **not** asked again; still `found=false` |
| Backend `Fetch` returns an error for `B` | `Lookup("B")` returns that error; a later successful `Lookup("B")` works and is not poisoned by the earlier failure |
| 100 concurrent lookups of the same uncached ID | Backend receives that ID in a single request, not 100 |
| Lookup after `ttl` has elapsed | Backend consulted again for that ID |
| Caller appends to returned `Tags`, then re-looks up | The freshly returned record is unaffected by the earlier mutation |
| `> capacity` distinct IDs resolved | Number of live in-memory records stays around `capacity` |

## Acceptance Criteria

- `pkg/directory/directory.go` compiles as part of the module with `go build ./...` from the repository root.
- A test backend implementing `Backend` that records, per ID, how many times each ID was passed to `Fetch` (safe under concurrent access) demonstrates all of the following, all asserted in `pkg/directory/directory_test.go`:
  - An existing ID looked up twice in a row triggers exactly **one** backend fetch for that ID and returns identical contact data both times.
  - A non-existent ID looked up twice in a row returns `found=false` both times and triggers exactly **one** backend fetch for that ID (the second call is served from memory).
  - A backend that returns an error on the first attempt for an ID causes `Lookup` to return a non-nil error, and a subsequent attempt for the same ID (with the backend now healthy) succeeds — proving the failure was not cached.
  - Launching at least 50 goroutines that each call `Lookup` for the same previously-uncached ID results in exactly **one** backend fetch for that ID, and every goroutine observes `found=true` with the correct data. (Use a backend whose `Fetch` blocks briefly, e.g. on a channel or short sleep, so the concurrent window is real.)
  - After a lookup with a very short `ttl`, waiting past the `ttl` and looking the same ID up again triggers a **second** backend fetch for that ID.
  - Mutating the `Tags` slice of a returned `*Contact` and then looking the same ID up again yields a record whose `Tags` do not contain the mutation.
  - Resolving more distinct IDs than `capacity` leaves the service holding no more than `capacity` records (assert via whatever size accessor the service exposes, or by observing that previously-resolved-but-evicted IDs cause a fresh backend fetch on re-lookup).
  - After `Close()`, `go.uber.org/goleak` (already a test dependency of this module) reports no leaked goroutines. Wrap this with `goleak.VerifyTestMain` in a `TestMain`, or call `goleak.VerifyNone(t)` at the end of the relevant test.

- The following command, run from the repository root, passes:

```
go test ./pkg/directory/ -run TestDirectory -count=1
```

(The test functions you add must collectively be matched by `-run TestDirectory`, e.g. `TestDirectory_DedupesConcurrentLookups`, `TestDirectory_CachesMissingKeys`, etc. A naive implementation that simply calls the backend on every `Lookup`, that never remembers non-existent IDs, that shares mutable slices between callers, or that lets records live forever must fail at least one of these tests.)
