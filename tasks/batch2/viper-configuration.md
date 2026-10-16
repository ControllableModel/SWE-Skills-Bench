# Task: Add a Deploy Target Configuration Loader for Hugo

## Background

Hugo's `hugo deploy` command (see `deploy/deploy.go` and `deploy/deployconfig/`) ships site output to a named remote target. This task adds a small, self-contained loader package that reads the deploy configuration — a list of named targets and a default target — from a config file, environment variables, and programmatic overrides, decoding the result into typed structs.

## Files to Create/Modify

- `internal/deployconf/deployconf.go` (new) — the deploy configuration loader.
- `internal/deployconf/deployconf_test.go` (new) — deterministic unit tests for the loader.
- `internal/deployconf/testdata/` (new) — optional fixture config files used by the tests.
- `go.mod` (modify) — add the dependency required to implement the loader.
- `go.sum` (modify) — the corresponding checksums.

## Requirements

### Configuration shape

Define exported structs in package `deployconf`:

- `DeployConfig` with fields:
  - `Default` (`string`, key `default`) — the name of the default target.
  - `Targets` (`[]Target`, key `targets`) — the configured targets.
- `Target` with fields:
  - `Name` (`string`, key `name`).
  - `URL` (`string`, key `url`).
  - `CloudFrontID` (`string`, key `cloud_front_id`) — an underscore-named field that must be decoded correctly.

The structs must be populated by decoding the resolved configuration tree into them (not by hand-reading individual keys). The underscore-named `cloud_front_id` field must decode from the `cloud_front_id` config key.

### Loader API

Provide `Load(opts Options) (*DeployConfig, error)`. `Options` must at minimum let a caller pass an optional config-file path and a programmatic set of overrides expressed as key/value pairs. Each `Load` call must build its configuration independently — repeated and concurrent calls, plus all test cases, must not share or leak state.

### Source layering and precedence

When the same key is supplied by multiple sources, resolution must follow this priority, highest first:

1. a programmatic override passed via `Options`,
2. an environment variable,
3. a value in the config file,
4. nothing (zero value).

### Environment variables

- Setting-related environment variables are namespaced under the prefix `HUGODEPLOY`. For example `default` is read from `HUGODEPLOY_DEFAULT`.
- A bare, unprefixed variable (e.g. `DEFAULT`) must NOT influence any setting.

### Sub-tree access

Provide `TargetByName(cfg *DeployConfig, name string) (*Target, bool)` that returns the matching target and `true`, or `nil` and `false` when no target with that name exists. A request for a missing name must not panic.

### Expected Functionality

- Scenario: a config file defines two targets (`production`, `staging`) and `default: production` -> `Load` returns both targets decoded, with `Default == "production"`.
- Scenario: a target sets `cloud_front_id: ABC123` in the file -> the decoded `Target.CloudFrontID == "ABC123"`.
- Scenario: the file sets `default: staging` and `HUGODEPLOY_DEFAULT=production` is set -> resolved `Default == "production"`.
- Scenario: the file sets `default: staging`, env sets `HUGODEPLOY_DEFAULT=production`, an override sets `default=qa` -> resolved `Default == "qa"`.
- Scenario: `TargetByName(cfg, "staging")` on a config containing `staging` -> returns that target and `true`.
- Scenario: `TargetByName(cfg, "missing")` -> returns `nil`, `false`, no panic.
- Scenario: a bare `DEFAULT` env var is set but `HUGODEPLOY_DEFAULT` is not -> the bare value is ignored.

## Acceptance Criteria

- Package `internal/deployconf` exports `DeployConfig`, `Target`, `Options`, `Load`, and `TargetByName`.
- Override > env > file precedence holds for `default`, verified per the scenarios.
- Nested target lists and the underscore-named `cloud_front_id` decode correctly into the structs.
- Environment lookups are namespaced under `HUGODEPLOY_`; a bare `DEFAULT` is ignored.
- `TargetByName` returns `(nil, false)` for an unknown name without panicking.
- Tests are isolated: each case builds its own loader state, does not depend on ordering, and uses `t.Setenv` for environment mutations.
- The following command passes from the repository root:

  ```
  go test ./internal/deployconf/
  ```
