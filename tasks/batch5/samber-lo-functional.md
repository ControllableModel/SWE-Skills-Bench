# Task: Build a Tag Co-occurrence Counter

## Background

This repository (`github.com/samber/lo`) is a generics-first utility library for Go. To exercise the library against a realistic workload, add a small self-contained example application under a new `examples/tagstats` package that, given a collection of tagged documents, computes per-tag frequency and the most common pairs of tags that appear together.

## Files to Create/Modify

- `examples/tagstats/tags.go` (new) — the counting logic, in `package tagstats`.
- `examples/tagstats/tags_test.go` (new) — table-driven tests, in `package tagstats`, using only the Go stdlib `testing` package.

Both files belong to the existing module `github.com/samber/lo` (`go 1.18`), so the import path for the new package is `github.com/samber/lo/examples/tagstats`. You may import `github.com/samber/lo` from within the new package.

## Requirements

### Input and output types

Define the following exported types in `examples/tagstats/tags.go`:

```go
// A document carries an ordered list of tags; the same tag may be repeated within a document.
type Document struct {
    ID   string
    Tags []string
}

type Pair struct {
    A, B  string // A is lexicographically <= B
    Count int    // number of documents whose distinct tag set contains BOTH A and B
}

type Stats struct {
    TagCounts map[string]int // tag -> number of DISTINCT documents containing that tag
    TopPairs  []Pair         // co-occurring tag pairs, see ordering rules
}
```

### Behavior

Implement:

```go
func Compute(docs []Document, topN int) Stats
```

with the following rules:

#### Per-document distinct tags
- Within a single document, repeated tags collapse to a distinct set before counting. A document mentioning `"go"` three times counts once toward `"go"`.

#### Tag counts
- `TagCounts[tag]` is the number of distinct documents whose distinct tag set contains `tag`. Tags appearing in no document do not appear as keys. `TagCounts` is non-nil even when empty.

#### Pairs
- For every unordered pair of distinct tags `{A,B}` that co-occur in at least one document's distinct tag set, count the number of documents containing both. In each `Pair`, `A <= B` lexicographically.
- `TopPairs` contains the pairs with the highest `Count`, limited to `topN` entries. Sort by `Count` descending; break ties by `A` ascending, then `B` ascending.
- If `topN <= 0`, `TopPairs` is an empty (non-nil) slice. If fewer than `topN` pairs exist, return all of them.

### Edge cases
- A document with fewer than two distinct tags contributes to `TagCounts` but to no pair.
- Empty `docs` yields empty (non-nil) `TagCounts` and empty (non-nil) `TopPairs`.
- `Compute` must not mutate the caller's input or any document's `Tags` slice.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| Repeated tag within one document | Counted once for that tag and pairs |
| Three docs sharing tags `a`,`b` | `Pair{A:"a",B:"b"}` count reflects co-occurring docs |
| Two pairs tie on count | Ordered by `A` then `B` ascending |
| `topN` smaller than pair count | Only the top `topN` pairs returned |
| Document with a single distinct tag | Contributes to `TagCounts`, no pairs |
| Empty input | Empty non-nil outputs |

## Acceptance Criteria

- The package `github.com/samber/lo/examples/tagstats` compiles.
- `Compute` satisfies every rule above, verified by the new table-driven test covering: intra-document tag de-duplication, distinct-document tag counts, pair counting with `A <= B` normalization, count-descending then lexicographic tie-break ordering, `topN` truncation, the `topN <= 0` case, and input-immutability (at least 10 assertions/cases total).
- The following command, run from the repository root, passes with no failures:

```
go test ./examples/tagstats/ -run TestCompute -count=1
```

- A naive implementation that double-counts repeated tags, emits pairs with `A > B`, skips the tie-break, or ignores `topN` must fail the test.
