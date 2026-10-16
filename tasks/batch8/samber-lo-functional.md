# Task: Build a Slug and Keyword Extractor

## Background

This repository (`github.com/samber/lo`) is a generics-first utility library for Go. To exercise the library against a realistic workload, add a small self-contained example application under a new `examples/textkit` package that normalizes free-form titles into URL slugs and extracts a ranked keyword list.

## Files to Create/Modify

- `examples/textkit/textkit.go` (new) — the text logic, in `package textkit`.
- `examples/textkit/textkit_test.go` (new) — table-driven tests, in `package textkit`, using only the Go stdlib `testing` package.

Both files belong to the existing module `github.com/samber/lo` (`go 1.18`), so the import path for the new package is `github.com/samber/lo/examples/textkit`. You may import `github.com/samber/lo` from within the new package.

## Requirements

### Behavior — Slugify

Implement:

```go
func Slugify(title string) string
```

with the following rules:
- Split the title into words on any run of whitespace.
- Lowercase each word and strip any character that is not an ASCII letter (`a`-`z`) or ASCII digit (`0`-`9`); keep the remaining characters in order.
- Drop words that become empty after stripping.
- Join the surviving words with a single hyphen `-`.
- An input that is empty or contains no alphanumeric characters yields the empty string `""`.

### Behavior — Keywords

Define and implement:

```go
type Keyword struct {
    Word  string
    Count int
}

// stopWords are excluded from the result. minLen is the minimum word length to keep.
func Keywords(title string, stopWords []string, minLen int, topN int) []Keyword
```

with the following rules:
- Tokenize using the SAME normalization as `Slugify` (whitespace split, lowercase, strip non-alphanumeric, drop empties).
- Exclude any token that is in `stopWords` (compare after normalization, case-insensitively) or whose length is `< minLen`.
- Count occurrences of each surviving token.
- Return the `topN` keywords ordered by `Count` descending, breaking ties by `Word` ascending. If `topN <= 0`, return an empty (non-nil) slice. If fewer keywords exist than `topN`, return all of them.
- The result slice is non-nil even when empty.

### Edge cases
- Mixed-case and punctuation-laden titles normalize identically regardless of original casing/punctuation.
- A stop word that also exceeds `minLen` is still excluded.
- `Keywords` and `Slugify` must not panic on empty input.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| `"Hello, World!"` | `Slugify` -> `"hello-world"` |
| Title with double spaces / tabs | Collapsed; no empty slug segments |
| Title that is all punctuation | `Slugify` -> `""` |
| Repeated keyword | Higher `Count`, ranked above rarer words |
| Two keywords tie on count | Ordered by `Word` ascending |
| `topN` smaller than keyword count | Only top `topN` returned |

## Acceptance Criteria

- The package `github.com/samber/lo/examples/textkit` compiles.
- `Slugify` and `Keywords` satisfy every rule above, verified by the new table-driven test covering: whitespace splitting and hyphen joining, non-alphanumeric stripping, empty/all-punctuation input, stop-word and `minLen` filtering, count-descending then lexicographic tie-break ordering, and `topN` truncation including `topN <= 0` (at least 10 assertions/cases total).
- The following command, run from the repository root, passes with no failures:

```
go test ./examples/textkit/ -run 'TestSlugify|TestKeywords' -count=1
```

- A naive implementation that leaves punctuation in slugs, emits empty hyphen segments, ignores stop words/`minLen`, or skips the tie-break must fail the test.
