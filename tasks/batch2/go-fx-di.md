# Task: Build a Graceful TCP Listener Example with Boot/Shutdown Ordering

## Background

The `docs/ex` directory of the `go.uber.org/fx` repository is a standalone Go module (`go.uber.org/fx/docs`, with `replace go.uber.org/fx => ../`) hosting small self-contained example applications, each in its own package with a co-located `_test.go`. This task adds a new example that demonstrates how a long-running network component is booted and torn down in coordination with its dependencies, without launching any goroutine or opening any socket from a constructor body.

## Files to Create/Modify

- `docs/ex/listener/server.go` (new) — a TCP echo server component that binds a port and serves connections only after the application has started.
- `docs/ex/listener/probe.go` (new) — a readiness probe component that depends on the server and records when the server has become reachable.
- `docs/ex/listener/app.go` (new) — the composition root exposing a single reusable `Module`.
- `docs/ex/listener/listener_test.go` (new) — the deterministic test described in Acceptance Criteria.

All files use package name `listener`. Reuse the existing `go.uber.org/fx/docs` module; do not create a new module or edit `go.mod`.

## Requirements

### Server component

- Define an exported `Server` struct holding a `net.Listener` and an address. Provide an exported constructor `NewServer` that takes the application lifecycle and a `*State` (defined below) and returns a `*Server`.
- The constructor must NOT call `net.Listen`, must NOT call `Accept`, and must NOT spawn any goroutine. It must only build the struct and register start/stop coordination.
- When the application starts, the server must bind a TCP listener on `127.0.0.1:0` (an OS-assigned free port), record its resolved address into `State`, and begin accepting and echoing connections in the background. Binding must happen during application start, not during construction.
- When the application stops, the server must stop accepting new connections and close its listener; after stop, the recorded address must no longer be connectable.

### Readiness state and probe

- Define an exported `State` struct, safe for concurrent use, with: `SetAddr(string)`, `Addr() string`, an ordered append-only log of phase strings reachable via `Phases() []string` (returning a copy), and a method to append a phase.
- The server must append `"listen"` to the phase log at the moment it successfully binds during start, and `"close"` when it closes during stop.
- Define an exported `NewProbe` constructor and an exported `Probe` type that, during application start (after the server has bound), dials the recorded address once, confirms the echo server round-trips a single byte, and appends `"probe-ok"` to the phase log. The probe must run after the server has bound — its start coordination must depend on the server already being reachable.

### Composition root

- Expose an exported `Module` (`fx.Option`) that wires `Server` and `Probe` so that booting the module plus a supplied `*State` yields a fully working application with no additional wiring.

### Edge cases & constraints

- Booting must not produce a missing-dependency or cycle error.
- The phase log must contain `"listen"` strictly before `"probe-ok"`, and `"close"` must appear only after a stop.
- A construction that binds the socket inside the constructor must be detectable: before the app is started, no socket may be open and `State.Addr()` must be empty.

## Expected Functionality

- Scenario: boot the app, then stop it → outcome: `Phases()` is exactly `["listen", "probe-ok", "close"]` in that order.
- Scenario: read `State.Addr()` before start → outcome: empty string (constructor did not bind).
- Scenario: dial `State.Addr()` after stop → outcome: connection fails (listener closed).

## Acceptance Criteria

- A new package `listener` exists under `docs/ex/listener/` exposing `Server`, `Probe`, `State` (with `Addr()`, `Phases()`), `NewServer`, `NewProbe`, and `Module`.
- `docs/ex/listener/listener_test.go` boots via `fxtest.New(t, Module, fx.Supply(st))` with a fresh `*State`, calls `RequireStart()`, asserts `st.Addr()` is non-empty and the address is connectable, then calls `RequireStop()` and asserts the address is no longer connectable.
- The test asserts `st.Phases()` equals `["listen", "probe-ok", "close"]`.
- The test also constructs the graph and asserts that before `RequireStart()` the address is empty (proving the bind happens at start, not construction).
- The following command, run from the `docs` directory, passes:

  ```bash
  cd docs && go test ./ex/listener/...
  ```
