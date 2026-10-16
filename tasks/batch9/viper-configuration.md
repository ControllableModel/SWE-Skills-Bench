# Task: Add a Per-Service Configuration Accessor for Hugo

## Background

Hugo groups third-party integration settings under a `services` block — e.g. `services.googleAnalytics`, `services.disqus`, `services.rss` (see `config/services/servicesConfig.go`). This task adds a self-contained loader that reads the whole services block from a config file and hands out a scoped, isolated view of a single named service's sub-tree on demand.

## Files to Create/Modify

- `internal/svcconfig/svcconfig.go` (new) — the services config loader and sub-tree accessor.
- `internal/svcconfig/svcconfig_test.go` (new) — deterministic unit tests.
- `internal/svcconfig/testdata/` (new) — optional fixture config files for the tests.
- `go.mod` (modify) — add the dependency required to implement the loader.
- `go.sum` (modify) — the corresponding checksums.

## Requirements

### Loader API

Provide `Load(path string) (*Services, error)` returning a `*Services` handle over the resolved configuration. Each call must build its configuration independently — repeated calls and all test cases must not share or leak state.

### Sub-tree accessor

`Services` must expose:

- `Service(name string) (*ServiceView, bool)` — returns a scoped view of `services.<name>` and `true` when that sub-tree exists, or `nil` and `false` when it does not. A request for a missing service must not panic and must be cleanly distinguishable from an existing-but-empty service.
- On a `*ServiceView`, a method `GetString(key string) string` and `GetBool(key string) bool` that read keys within that service's sub-tree only (so `ServiceView` for `disqus` reading `shortname` reads `services.disqus.shortname`).

### Decoding a service

`ServiceView` must also offer `Decode(dst any) error` that decodes that single service's sub-tree into a caller-provided struct, honoring `mapstructure`-style tags including underscore-named keys (e.g. a struct field tagged `tracking_id` decodes from `services.googleAnalytics.tracking_id`).

### Missing-file handling

- If `path` is empty or names a nonexistent file, `Load` must succeed and return a handle for which every `Service(...)` lookup returns `(nil, false)`.
- A present-but-unparseable file must cause `Load` to return a non-nil error.

### Expected Functionality

- Scenario: file sets `services.disqus.shortname: myforum` -> `Service("disqus")` returns a view and `true`; `view.GetString("shortname") == "myforum"`.
- Scenario: `Service("nonexistent")` -> returns `(nil, false)`, no panic.
- Scenario: file sets `services.googleAnalytics.tracking_id: G-XYZ` -> `Service("googleAnalytics")`'s `Decode` into a struct with field tagged `tracking_id` yields `"G-XYZ"`.
- Scenario: file sets `services.rss.limit: 20` -> `Service("rss")`'s `GetString`/`GetBool` read only within that service's sub-tree (e.g. reading `services.disqus.shortname` from the rss view yields empty).
- Scenario: empty/nonexistent path -> `Load` succeeds and `Service(anything)` returns `(nil, false)`.
- Scenario: present file with invalid syntax -> `Load` returns a non-nil error.

## Acceptance Criteria

- Package `internal/svcconfig` exports `Services`, `ServiceView`, `Load`, and the methods `Service`, `GetString`, `GetBool`, `Decode`.
- `Service` returns `(nil, false)` for a missing name without panicking.
- A `ServiceView` reads and decodes only within its own service sub-tree; the underscore-named `tracking_id` decodes correctly.
- A missing/absent config file is not an error and yields a handle with no services; a present-but-unparseable file is an error.
- Tests are isolated: each case builds its own loader state and does not depend on execution order.
- The following command passes from the repository root:

  ```
  go test ./internal/svcconfig/
  ```
