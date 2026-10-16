# Task: Build a Route Registry Example Aggregating Independently-Provided Handlers

## Background

The `docs/ex` directory of the `go.uber.org/fx` repository is a standalone Go module (`go.uber.org/fx/docs`, with `replace go.uber.org/fx => ../`) hosting small self-contained example applications, each in its own package with a co-located `_test.go`. This task adds a new example showing how many constructors, each contributing one HTTP route, are collected into a single mux by a consumer that never names the individual routes.

## Files to Create/Modify

- `docs/ex/routereg/route.go` (new) — the `Route` abstraction (name + `http.Handler`).
- `docs/ex/routereg/handlers.go` (new) — three independent route constructors.
- `docs/ex/routereg/mux.go` (new) — a mux builder that consumes the full collection of routes, plus the reusable `Module`.
- `docs/ex/routereg/routereg_test.go` (new) — the deterministic test described in Acceptance Criteria.

All files use package name `routereg`. Reuse the existing `go.uber.org/fx/docs` module; do not create a new module or edit `go.mod`.

## Requirements

### Route abstraction

- Define an exported interface `Route` with `Pattern() string` and an embedded `http.Handler` (i.e. it satisfies `ServeHTTP`).
- Provide three independent constructors `NewHealthRoute`, `NewVersionRoute`, and `NewEchoRoute`. Each produces a `Route` whose `Pattern()` is `"/healthz"`, `"/version"`, and `"/echo"` respectively, and whose `ServeHTTP` writes a deterministic body: `"ok"` for health, a fixed version string `"v1"` for version, and the echo route writes back the request URL's raw query string.

### Mux builder

- Define an exported `NewMux` constructor that receives the complete collection of all registered `Route` values and returns a `*http.ServeMux` with every route registered at its `Pattern()`.
- `NewMux` must NOT reference the individual route constructors by name or import their concrete types; it must operate purely over the aggregated collection. Adding a fourth route later must require registering one more constructor with no edit to `mux.go`.

### Composition root

- Expose an exported `Module` (`fx.Option`) wiring the three routes and the mux builder, such that a consumer can boot with only `Module` and pull out a `*http.ServeMux`.

### Edge cases & constraints

- Booting must not produce a missing-dependency or cycle error.
- The collection passed to `NewMux` must contain exactly the registered routes (3 here). The number of patterns registered on the returned mux must equal the number of provided routes.
- Routing is verified via `net/http/httptest` against an in-memory `*http.ServeMux` — no real network listener is opened.

## Expected Functionality

- Scenario: build the mux and issue an in-memory request to `/healthz` → outcome: body is `"ok"`.
- Scenario: request `/version` → outcome: body is `"v1"`.
- Scenario: request `/echo?msg=hi` → outcome: body is `"msg=hi"`.
- Scenario: add a fourth route constructor → outcome: it is reachable with no change to `mux.go`.

## Acceptance Criteria

- A new package `routereg` exists under `docs/ex/routereg/` exposing `Route`, `NewHealthRoute`, `NewVersionRoute`, `NewEchoRoute`, `NewMux`, and `Module`.
- `docs/ex/routereg/routereg_test.go` boots via `fxtest.New(t, Module, fx.Populate(&mux))` for a `*http.ServeMux`, calls `RequireStart().RequireStop()`, then uses `httptest.NewRecorder` + `httptest.NewRequest` to drive requests through `mux.ServeHTTP` and asserts the three bodies (`"ok"`, `"v1"`, `"msg=hi"`).
- The test asserts the aggregated collection length equals 3 by counting distinct served patterns.
- A naive `NewMux` that hardcodes three patterns from named constructors would not survive adding a fourth route; the test's correctness rests on the aggregation, not on hardcoded patterns.
- The following command, run from the `docs` directory, passes:

  ```bash
  cd docs && go test ./ex/routereg/...
  ```
