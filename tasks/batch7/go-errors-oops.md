# Task: Build a Tag-Driven Error Routing Module

## Background

The `samber/oops` repository ships several self-contained demonstration modules under `examples/` (each its own Go module, wired into the workspace via `go.work`). This task adds a new example module, `examples/alertroute`, that classifies failures with categorization tags and routes each failure to the correct alerting channel purely by inspecting the tags carried on the error.

## Files to Create/Modify

- `examples/alertroute/alertroute.go` (new) — the failure producers and the tag-based router.
- `examples/alertroute/alertroute_test.go` (new) — the deterministic tests described below.
- `examples/alertroute/go.mod` (new) — module `github.com/samber/oops/examples/alertroute`, Go 1.21, requiring `github.com/samber/oops`.
- `go.work` (modify) — add `./examples/alertroute` to the `use (...)` block.

## Requirements

The module produces categorized failures and routes them by their tags. No network or paging service — routing returns a string channel name.

### Failure producers

Provide exported functions that each return a non-nil `samber/oops` error categorized with tags:

- `DatabaseTimeout() error` — tagged with both `"database"` and `"critical"`.
- `RateLimited() error` — tagged with `"throttling"` (and NOT `"critical"`).
- `DiskFull() error` — tagged with both `"storage"` and `"critical"`.
- `ValidationFailed() error` — tagged with `"validation"` (and NOT `"critical"`).

Each error MUST carry a domain and a machine-readable code appropriate to its category (codes MUST be distinct across the four producers).

### Router

Provide:

```go
func Route(err error) string
```

`Route` decides a channel **only by inspecting the error's tags** (via the oops tag accessors), as follows, evaluated in order:

1. if `err` is `nil` -> return `"none"`.
2. if the error carries the tag `"critical"` -> return `"pagerduty"`.
3. else if the error carries the tag `"throttling"` -> return `"slack-ops"`.
4. else if the error carries the tag `"validation"` -> return `"slack-dev"`.
5. otherwise -> return `"default"`.

`Route` MUST NOT branch on the error's code, message, or domain — only on tags. A non-oops error MUST route to `"default"`.

### Expected Functionality

- `Route(nil)` -> `"none"`.
- `Route(DatabaseTimeout())` -> `"pagerduty"` (has `critical`).
- `Route(DiskFull())` -> `"pagerduty"` (has `critical`).
- `Route(RateLimited())` -> `"slack-ops"` (throttling, no critical).
- `Route(ValidationFailed())` -> `"slack-dev"` (validation, no critical).
- `Route(errors.New("plain"))` -> `"default"`.
- The four producers' `Code()` values are pairwise distinct.

## Acceptance Criteria

- `examples/alertroute/go.mod` declares module `github.com/samber/oops/examples/alertroute` and `go.work` lists `./examples/alertroute`.
- A naive implementation that routes by parsing the message string or by code instead of tags, or that hardcodes the same channel, fails the tests.
- The added tests are deterministic and pass:

```
go test ./examples/alertroute/...
```

  run from the repository root, including the nil case, both `critical` producers routing to `pagerduty`, the `throttling` and `validation` cases, the plain-error fallback, and the distinct-codes assertion.
