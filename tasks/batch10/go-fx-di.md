# Task: Build a Startup-Failure and Timeout Example for Graph Boot

## Background

The `docs/ex` directory of the `go.uber.org/fx` repository is a standalone Go module (`go.uber.org/fx/docs`, with `replace go.uber.org/fx => ../`) hosting small self-contained example applications, each in its own package with a co-located `_test.go`. This task adds a new example focused on boot failure semantics: how a graph validates eagerly, how a failing start hook aborts boot with the right error, and how a slow start hook is bounded by a configured startup timeout.

## Files to Create/Modify

- `docs/ex/bootfail/components.go` (new) — components whose start behavior is configurable (succeed, fail, or hang).
- `docs/ex/bootfail/app.go` (new) — composition roots: a healthy `Module`, a `FailingModule`, and a `SlowModule`, plus a helper to build an `fx.App` with a chosen startup timeout.
- `docs/ex/bootfail/bootfail_test.go` (new) — the deterministic test described in Acceptance Criteria.

All files use package name `bootfail`. Reuse the existing `go.uber.org/fx/docs` module; do not create a new module or edit `go.mod`.

## Requirements

### Configurable components

- Define an exported `Sentinel` struct, safe for concurrent use, recording whether each phase ran: `Started() bool`, `Stopped() bool`.
- Define a healthy component whose start hook succeeds quickly and records start/stop into the `Sentinel`.
- Define a failing component whose start hook returns a non-nil error `ErrBoot` (an exported sentinel error) instead of succeeding.
- Define a slow component whose start hook respects context cancellation but does not complete until a duration longer than any reasonable test timeout — it must return promptly with the context's error when the start context is cancelled.

### Composition roots and boot helper

- Expose exported `Module` (healthy), `FailingModule`, and `SlowModule` (`fx.Option`s).
- Expose an exported helper `New(opts ...fx.Option) *fx.App` (or equivalent) that builds an app with a short, explicit startup timeout so a hanging start hook is bounded rather than blocking forever.

### Boot semantics

- Booting the healthy `Module` must start cleanly: `Start(ctx)` returns nil, the `Sentinel` reports started, and after `Stop(ctx)` it reports stopped.
- Booting `FailingModule` must cause `Start(ctx)` to return a non-nil error that wraps `ErrBoot` (verifiable with `errors.Is`); the app must not be left reporting a successful start.
- Booting `SlowModule` under the short startup timeout must cause `Start(ctx)` to return a non-nil (deadline/cancellation) error within the timeout window; it must not hang the test.
- A graph missing a required provider must surface a validation error before any start hook runs.

### Edge cases & constraints

- The slow start hook must honor `ctx.Done()` and return its error rather than ignoring cancellation.
- Tests must use real `fx.New(...).Start/Stop` with a `context.Context`, not `fxtest`, so failure errors are observable as return values (these boots are expected to fail).
- All timeouts in the test must be small and bounded so the suite is fast and deterministic.

## Expected Functionality

- Scenario: start the healthy app → outcome: `Start` returns nil; `Sentinel.Started()` true; after `Stop`, `Sentinel.Stopped()` true.
- Scenario: start the failing app → outcome: `Start` returns an error and `errors.Is(err, ErrBoot)` is true.
- Scenario: start the slow app under a short startup timeout → outcome: `Start` returns a non-nil error promptly (deadline exceeded / context cancelled), without the goroutine leaking past return.
- Scenario: build an app missing a provider → outcome: a validation error is reported before any start hook runs.

## Acceptance Criteria

- A new package `bootfail` exists under `docs/ex/bootfail/` exposing `Sentinel`, `ErrBoot`, `Module`, `FailingModule`, `SlowModule`, and the `New` helper.
- `docs/ex/bootfail/bootfail_test.go`:
  - boots the healthy app, asserts `Start(ctx) == nil`, `Sentinel.Started()`, then `Stop(ctx) == nil` and `Sentinel.Stopped()`;
  - boots `FailingModule`, asserts `Start(ctx)` is non-nil and `errors.Is(err, ErrBoot)`;
  - boots `SlowModule` under a short startup timeout (e.g. 50ms) and asserts `Start(ctx)` returns a non-nil error within a bounded wait;
  - builds a deliberately under-wired app and asserts a non-nil error is observable (via `.Err()` or `Start`).
- Tests use real `fx.New` + `Start`/`Stop` with `context.Context` and bounded timeouts; no fixed long sleeps.
- The following command, run from the `docs` directory, passes:

  ```bash
  cd docs && go test ./ex/bootfail/...
  ```
