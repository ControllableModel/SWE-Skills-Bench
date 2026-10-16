# Task: Build an Eviction-Aware Renderer Pool

## Background

The `github.com/samber/hot` repository is a generic, type-safe in-memory caching library for Go (`module github.com/samber/hot`, Go 1.22+). This task adds an application-level **template renderer pool** in a new package under `pkg/` that keeps a bounded set of compiled templates hot, but — unlike a plain cache — must run a cleanup hook on any compiled template the moment it leaves the cache (evicted, expired, or explicitly removed), because each compiled template owns a resource handle that has to be released. The package must compile as part of the main module and be exercised by a deterministic in-process test.

## Files to Create/Modify

- `pkg/renderpool/renderpool.go` (new) — the `RenderPool` implementation.
- `pkg/renderpool/renderpool_test.go` (new) — the deterministic unit tests described in the Acceptance Criteria.

Both files belong to a new package `renderpool` and may import `github.com/samber/hot` plus the standard library only. Do not add new third-party dependencies and do not modify `go.mod`.

## Requirements

### Types and compiler

```go
type Compiled struct {
    Name   string
    closed bool // set true by the pool's cleanup hook when released
}

// Compiler is the slow source that compiles a template by name.
type Compiler interface {
    // Compile returns the compiled template for name, or (nil, false, nil)
    // if no such template exists. A non-nil error is an infrastructure failure.
    Compile(name string) (*Compiled, error)
}

// OnRelease is invoked exactly once per compiled template when it leaves
// the pool, regardless of the reason it left.
type OnRelease func(c *Compiled)
```

### Constructor

```go
func NewRenderPool(c Compiler, capacity int, ttl time.Duration, onRelease OnRelease) *RenderPool
```

- When a compiled template leaves the pool — because it was evicted to make room, because its `ttl` expired, or because it was explicitly removed — `onRelease` must be invoked with that template, exactly once.
- `Close()` must release any background machinery so no goroutines leak. (Whether `Close()` also releases all still-resident templates is up to the implementation, but if it does, it must do so through the same exactly-once `onRelease` contract.)

### Acquire behavior

`func (p *RenderPool) Acquire(name string) (*Compiled, bool, error)`:

- `(compiled, true, nil)` when the template exists; a second acquire within `ttl` returns the same instance without recompiling.
- `(nil, false, nil)` when the compiler reports no such template.
- `(nil, false, err)` on infrastructure failure (not remembered).

### Eviction-driven cleanup

- When more than `capacity` distinct templates are compiled, the templates dropped to stay within `capacity` must each have `onRelease` invoked exactly once.
- When a template's `ttl` elapses and it is removed from the pool, `onRelease` must be invoked for it.
- `func (p *RenderPool) Remove(name string) bool` explicitly removes a template; if it was present, `onRelease` must run for it and the method returns `true`.
- `onRelease` must never be invoked more than once for the same compiled instance.

### Concurrency and dedup

Safe for concurrent use. A burst of concurrent `Acquire` calls for the **same** uncached name must collapse into a single `Compile`.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| Acquire existing `home` | Compiled once; `found=true` |
| Re-acquire within `ttl` | No recompile; same instance |
| `> capacity` distinct templates compiled | Each evicted template's `onRelease` runs exactly once |
| Template expires past `ttl` | Its `onRelease` runs |
| `Remove("home")` while present | `onRelease` runs; returns `true` |
| Unknown template | `found=false`, no error |

## Acceptance Criteria

- `pkg/renderpool/renderpool.go` compiles with `go build ./...` from the repository root.
- A test `Compiler` that records per-name `Compile` counts, plus an `onRelease` that records (under a mutex) every released template name and its release count, asserts in `pkg/renderpool/renderpool_test.go`:
  - An existing template acquired twice in a row compiles exactly **once** and returns the same instance.
  - Compiling strictly more than `capacity` distinct templates triggers `onRelease` for the templates that had to be dropped, with the total release count equal to the number of templates that left the pool and **no** template released more than once.
  - A template acquired with a very short `ttl`, after waiting past the `ttl`, has its `onRelease` invoked (assert the release was recorded; e.g. enable the pool's background cleanup so expiry actively releases it).
  - `Remove(name)` on a present template invokes `onRelease` once for it and returns `true`; `Remove` on an absent name returns `false` and triggers no release.
  - Launching at least 50 goroutines acquiring the same uncached name triggers exactly **one** `Compile` (use a `Compile` that blocks briefly).
  - After `Close()`, `go.uber.org/goleak` reports no leaked goroutines.
- The following command, run from the repository root, passes:

```
go test ./pkg/renderpool/ -run TestRenderPool -count=1
```

(A naive implementation that never runs a cleanup hook on eviction/expiry, that releases a template more than once, that recompiles on every acquire, or that lets templates live forever must fail at least one test.)
