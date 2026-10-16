# Task: Build a Batch Profile Enrichment Service

## Background

The `github.com/samber/hot` repository is a generic, type-safe in-memory caching library for Go (`module github.com/samber/hot`, Go 1.22+). This task adds an application-level **batch enrichment service** in a new package under `pkg/` that, given a list of user ids in one call, returns their profiles while consulting a slow backing store only for the ids it does not already hold. The package must compile as part of the main module and be exercised by a deterministic in-process test.

## Files to Create/Modify

- `pkg/enrich/enrich.go` (new) — the `Enricher` implementation.
- `pkg/enrich/enrich_test.go` (new) — the deterministic unit tests described in the Acceptance Criteria.

Both files belong to a new package `enrich` and may import `github.com/samber/hot` plus the standard library only. Do not add new third-party dependencies and do not modify `go.mod`.

## Requirements

### Types and backend

```go
type Profile struct {
    ID          string
    DisplayName string
}

// Source is the slow batch backing store.
type Source interface {
    // FetchBatch is called with a de-duplicated set of ids and returns the
    // profiles that exist, keyed by id. Ids that do not exist are absent
    // from the result. A non-nil error indicates infrastructure failure.
    FetchBatch(ids []string) (map[string]*Profile, error)
}
```

### Constructor

```go
func NewEnricher(src Source, capacity int, ttl time.Duration) *Enricher
```

`Close()` must release any background machinery so no goroutines leak.

### Batch lookup behavior

`func (e *Enricher) Enrich(ids []string) (map[string]*Profile, []string, error)` must:

- Return `found` keyed by id for every requested id that resolves to an existing profile.
- Return `missing` listing every requested id that the source confirms does not exist.
- Together, `found` keys and `missing` must account for every requested id (each requested id appears in exactly one of them) on success.
- Return a non-nil error only on infrastructure failure; on error the partial maps need not be meaningful.

### Reducing backend pressure across calls

- A second `Enrich` call must request from `Source` **only** the ids not already resolved in memory (and not yet expired). Ids resolved by a prior call must not be re-fetched.
- Duplicate ids within a single `Enrich` request must be coalesced — the source must not receive the same id twice in one batch.
- When a batch mixes already-cached ids with new ids, exactly the new ids are forwarded to the source in a single `FetchBatch` call.
- Once `ttl` elapses for a resolved id, a later `Enrich` containing that id may consult the source again for it.
- With far more distinct ids resolved over time than `capacity`, in-memory records stay bounded around `capacity`.

### Concurrency and dedup

Safe for concurrent use. Concurrent `Enrich` calls whose batches overlap on the **same** uncached id must not each trigger a separate fetch for that id; overlapping demand for a given id collapses into shared backend work.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| `Enrich(["A","B"])` first time, both exist | `FetchBatch` receives `{A,B}`; both in `found` |
| `Enrich(["A","C"])` next, `A` cached, `C` new | `FetchBatch` receives only `{C}` |
| `Enrich(["A","A","D"])` | Source never receives `A` twice in the same batch |
| `Enrich(["Z"])`, `Z` does not exist | `Z` in `missing`, not `found`, no error |
| `Enrich` after `ttl` for previously resolved id | id may be re-fetched |
| Concurrent overlapping batches sharing uncached `E` | `E` fetched once, not once per call |

## Acceptance Criteria

- `pkg/enrich/enrich.go` compiles with `go build ./...` from the repository root.
- A test `Source` that records, per id, how many times each id appeared across all `FetchBatch` calls (safe under concurrency) asserts in `pkg/enrich/enrich_test.go`:
  - Two sequential `Enrich` calls whose id sets overlap cause each overlapping id to be fetched exactly **once** in total, and the second call forwards only its genuinely-new ids to the source.
  - A single `Enrich` request containing the same id twice forwards that id to the source at most once.
  - Requesting a mix of existing and non-existent ids returns the existing ones in `found` and the non-existent ones in `missing`, with the two sets together covering exactly the requested ids.
  - Launching at least 50 goroutines that each call `Enrich` with a batch all containing the same previously-uncached id results in that id being fetched exactly **once** total (use a `FetchBatch` that blocks briefly), and every goroutine observes that id in `found`.
  - After a short `ttl` elapses, re-enriching a previously-resolved id allows a fresh fetch for it.
  - After `Close()`, `go.uber.org/goleak` reports no leaked goroutines.
- The following command, run from the repository root, passes:

```
go test ./pkg/enrich/ -run TestEnrich -count=1
```

(A naive implementation that re-fetches already-resolved ids, that fails to de-duplicate within a batch, that mislabels existing vs non-existent ids, or that fans out concurrent identical ids into separate fetches must fail at least one test.)
