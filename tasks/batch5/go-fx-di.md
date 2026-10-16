# Task: Build a Scoped-Logger-Naming Example Across Two Sibling Modules

## Background

The `docs/ex` directory of the `go.uber.org/fx` repository is a standalone Go module (`go.uber.org/fx/docs`, with `replace go.uber.org/fx => ../`) hosting small self-contained example applications, each in its own package with a co-located `_test.go`. This task adds a new example demonstrating that a per-concern rewrite of a shared dependency is visible only inside the concern that performs it and never leaks to a sibling concern or to the root.

## Files to Create/Modify

- `docs/ex/scopedlog/tag.go` (new) — a small `Tag` value type used as the shared dependency and a thread-safe `Sink` that records observations.
- `docs/ex/scopedlog/dbmod.go` (new) — a `DBModule` that locally rewrites the shared `Tag` to a database-scoped variant and observes it.
- `docs/ex/scopedlog/httpmod.go` (new) — an `HTTPModule` that locally rewrites the shared `Tag` to an http-scoped variant and observes it.
- `docs/ex/scopedlog/app.go` (new) — the root composition exposing a reusable `Module` and a root-level observer.
- `docs/ex/scopedlog/scopedlog_test.go` (new) — the deterministic test described in Acceptance Criteria.

All files use package name `scopedlog`. Reuse the existing `go.uber.org/fx/docs` module; do not create a new module or edit `go.mod`.

## Requirements

### Shared dependency and sink

- Define an exported value type `Tag` (a `string`-backed type) and a root constructor `NewBaseTag` returning `Tag("base")`.
- Define an exported `Sink` struct, safe for concurrent use, with `Record(scope, tag string)` and `Observations() map[string]string` (returning a copy mapping scope name to the tag value seen there).

### Two modules that rewrite the shared dependency locally

- `DBModule` must contain an invoke (or a consumer that runs at start) that observes the shared `Tag` and records it into the `Sink` under scope `"db"`. Inside this module, the shared `Tag` must be rewritten so the observed value is `"base.db"`.
- `HTTPModule` must do the same under scope `"http"`, with the shared `Tag` rewritten so the observed value is `"base.http"`.
- A root-level observer must record the shared `Tag` into the `Sink` under scope `"root"`; the value observed at the root must remain `"base"` — neither module's rewrite may affect it.
- The rewrite each module performs must be scoped strictly to that module: the `"db"` rewrite must not change what `"http"` or `"root"` observe, and vice versa.

### Composition root

- Expose an exported `Module` (`fx.Option`) combining the base tag provider, both sub-modules, and the root observer, such that booting `Module` plus a supplied `*Sink` runs all three observers.

### Edge cases & constraints

- Booting must not produce a missing-dependency or cycle error.
- A top-level (non-scoped) rewrite that leaks to all scopes must fail the test, because `"root"`, `"db"`, and `"http"` must each observe a distinct value.

## Expected Functionality

- Scenario: boot with a fresh `*Sink` → outcome: `Observations()` equals `{"root":"base", "db":"base.db", "http":"base.http"}`.
- Scenario: remove the rewrite from `DBModule` only → outcome: the `"db"` observation reverts to `"base"` while `"http"` stays `"base.http"`.

## Acceptance Criteria

- A new package `scopedlog` exists under `docs/ex/scopedlog/` exposing `Tag`, `Sink` (with `Observations()`), `DBModule`, `HTTPModule`, and `Module`.
- `docs/ex/scopedlog/scopedlog_test.go` boots via `fxtest.New(t, Module, fx.Supply(sink))` with a fresh `*Sink`, calls `RequireStart().RequireStop()`, and asserts `sink.Observations()` equals exactly `{"root":"base", "db":"base.db", "http":"base.http"}`.
- The test proves scoping: a globally-applied rewrite would make all three scopes equal and fail the distinct-value assertion.
- The following command, run from the `docs` directory, passes:

  ```bash
  cd docs && go test ./ex/scopedlog/...
  ```
