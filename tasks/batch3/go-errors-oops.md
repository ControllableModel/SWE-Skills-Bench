# Task: Build a Config Validation Module with Assertion Guards

## Background

The `samber/oops` repository ships several self-contained demonstration modules under `examples/` (each its own Go module, wired into the workspace via `go.work`). This task adds a new example module, `examples/configcheck`, that validates an application configuration struct and reports the first violated invariant as a richly-structured failure.

## Files to Create/Modify

- `examples/configcheck/configcheck.go` (new) — the config type and its validation function.
- `examples/configcheck/configcheck_test.go` (new) — the deterministic table tests described below.
- `examples/configcheck/go.mod` (new) — module `github.com/samber/oops/examples/configcheck`, Go 1.21, requiring `github.com/samber/oops`.
- `go.work` (modify) — add `./examples/configcheck` to the `use (...)` block.

## Requirements

The module validates an in-memory configuration value. No files are read; the config is passed in directly.

### Domain types

Define in `examples/configcheck/configcheck.go`:

- `Config struct { ListenPort int; MaxConnections int; LogLevel string; ShutdownTimeoutSeconds int }`

### Entry point

```go
func Validate(c Config) error
```

`Validate` checks a series of invariants and returns the **first** violated one as a non-nil error, or `nil` if all invariants hold. Each invariant MUST be expressed as a guard that, when its condition is not satisfied, short-circuits and produces a structured failure (i.e. validation must stop at the first failing invariant; later fields are not reported once one fails).

### Invariants and failure attributes

Every non-nil error MUST satisfy `oops.AsOops(err)` (returns `ok == true`), MUST have domain (`Domain()`) equal to `"config-validation"`, and MUST carry the offending value under the context key `"value"`. The checks, in order, are:

1. `ListenPort` must be in the inclusive range `1..65535`. Violation -> `Code()` equals `"port_out_of_range"`, context `"value"` equals the supplied `ListenPort`.
2. `MaxConnections` must be `> 0`. Violation -> `Code()` equals `"non_positive_max_connections"`, context `"value"` equals the supplied `MaxConnections`.
3. `LogLevel` must be one of `"debug"`, `"info"`, `"warn"`, `"error"`. Violation -> `Code()` equals `"invalid_log_level"`, context `"value"` equals the supplied `LogLevel`.
4. `ShutdownTimeoutSeconds` must be in `0..300` inclusive. Violation -> `Code()` equals `"shutdown_timeout_out_of_range"`, context `"value"` equals the supplied `ShutdownTimeoutSeconds`.

The ordering MUST be respected: a `Config` that violates both invariant 1 and invariant 3 reports `port_out_of_range`, not `invalid_log_level`.

### Low cardinality

For a given failing invariant, `err.Error()` MUST be constant regardless of the specific offending value (e.g. `ListenPort` of `0` and `ListenPort` of `70000` produce byte-identical `Error()` strings, distinguished only by the `"value"` context entry).

### Expected Functionality

- `Validate(Config{ListenPort:0, MaxConnections:10, LogLevel:"info", ShutdownTimeoutSeconds:5})` -> code `port_out_of_range`, context `value == 0`.
- `Validate(Config{ListenPort:8080, MaxConnections:-1, LogLevel:"info", ShutdownTimeoutSeconds:5})` -> code `non_positive_max_connections`, context `value == -1`.
- `Validate(Config{ListenPort:8080, MaxConnections:10, LogLevel:"trace", ShutdownTimeoutSeconds:5})` -> code `invalid_log_level`, context `value == "trace"`.
- `Validate(Config{ListenPort:8080, MaxConnections:10, LogLevel:"info", ShutdownTimeoutSeconds:9999})` -> code `shutdown_timeout_out_of_range`, context `value == 9999`.
- `Validate(Config{ListenPort:0, ..., LogLevel:"trace", ...})` (two violations) -> code `port_out_of_range` (ordering).
- `Validate(Config{ListenPort:8080, MaxConnections:10, LogLevel:"warn", ShutdownTimeoutSeconds:30})` -> `nil`.

## Acceptance Criteria

- `examples/configcheck/go.mod` declares module `github.com/samber/oops/examples/configcheck` and `go.work` lists `./examples/configcheck`.
- A naive implementation that ignores ordering, or bakes the offending value into the message string, fails the tests.
- The added tests are deterministic and pass:

```
go test ./examples/configcheck/...
```

  run from the repository root, including each invariant case, the multi-violation ordering case, the success case, and a cardinality case asserting two different out-of-range ports produce identical `Error()` strings but different `"value"` context entries.
