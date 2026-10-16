# Task: Build a Pre-Built Config and Test-Override Example

## Background

The `docs/ex` directory of the `go.uber.org/fx` repository is a standalone Go module (`go.uber.org/fx/docs`, with `replace go.uber.org/fx => ../`) hosting small self-contained example applications, each in its own package with a co-located `_test.go`. This task adds a new example showing how a pre-built configuration value (not produced by a constructor) flows into a service, and how a test can swap a real dependency for a fake without rewiring the application.

## Files to Create/Modify

- `docs/ex/configsvc/config.go` (new) — a `Config` value type and a `Clock` interface with a real implementation.
- `docs/ex/configsvc/service.go` (new) — a `Greeter` service that depends on the config and the clock.
- `docs/ex/configsvc/app.go` (new) — the composition root exposing a reusable `Module` plus a default base option set.
- `docs/ex/configsvc/configsvc_test.go` (new) — the deterministic test described in Acceptance Criteria.

All files use package name `configsvc`. Reuse the existing `go.uber.org/fx/docs` module; do not create a new module or edit `go.mod`.

## Requirements

### Config and clock

- Define an exported `Config` struct with fields `Greeting string` and `Suffix string`. The `Config` is a fixed, pre-built value, not the output of a constructor that does work.
- Define an exported `Clock` interface with `Now() string`. Provide an exported real implementation `SystemClock` and a constructor `NewSystemClock` returning a `Clock`.

### Service

- Define an exported `Greeter` struct with a method `Greet(name string) string` returning `Config.Greeting + " " + name + Config.Suffix + " @" + clock.Now()`.
- Provide an exported `NewGreeter` constructor depending on `Config` and `Clock`.

### Composition root

- Expose two exported items: `Module` (`fx.Option`) that provides `Clock` and `Greeter` and consumes `Config`; and `Base` (`fx.Option`) that supplies a default pre-built `Config{Greeting: "Hello", Suffix: "!"}`. Booting `Base` together with `Module` must yield a working `*Greeter`.
- The `Config` must enter the graph as a pre-built value, not via a constructor that fabricates it.

### Edge cases & constraints

- Booting `Base` + `Module` must not produce a missing-dependency or cycle error.
- A test must be able to (a) supply a different pre-built `Config` instead of the default and (b) replace the real `Clock` with a fake returning a fixed string, both without editing `Module` or `service.go`.
- The fake clock used in tests must return a constant (e.g. `"T0"`) so output is fully deterministic.

## Expected Functionality

- Scenario: boot `Base` + `Module` with a fake clock returning `"T0"` → outcome: `Greet("Sam") == "Hello Sam! @T0"`.
- Scenario: replace the supplied config with `{Greeting:"Hi", Suffix:"?"}` and keep the fake clock → outcome: `Greet("Sam") == "Hi Sam? @T0"`, with no change to `Module`.

## Acceptance Criteria

- A new package `configsvc` exists under `docs/ex/configsvc/` exposing `Config`, `Clock`, `SystemClock`, `Greeter`, `NewGreeter`, `Module`, and `Base`.
- `docs/ex/configsvc/configsvc_test.go` contains at least two boots:
  - one boots `Module` together with a pre-built default `Config` and a fake clock (overriding the real `Clock`), populates a `*Greeter`, and asserts `Greet("Sam") == "Hello Sam! @T0"`;
  - a second boots `Module` with an overridden pre-built `Config{Greeting:"Hi", Suffix:"?"}` plus the fake clock and asserts `Greet("Sam") == "Hi Sam? @T0"`.
- Both boots use `fxtest.New(...).RequireStart().RequireStop()` and `fx.Populate`.
- The naive approach of hardcoding the greeting inside `Greeter` fails the second boot, which changes only the pre-built config.
- The following command, run from the `docs` directory, passes:

  ```bash
  cd docs && go test ./ex/configsvc/...
  ```
