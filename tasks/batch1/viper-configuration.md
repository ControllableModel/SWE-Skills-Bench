# Task: Add a Resolved Settings Loader for the Hugo Server Runtime

## Background

Hugo's `hugo server` command (see `commands/server.go`) reads runtime settings such as the listen port, bind interface and live-reload port from CLI flags, while Hugo overall honors `HUGO_`-prefixed environment variables (e.g. `HUGO_ENVIRONMENT`, `HUGO_NUMWORKERMULTIPLIER`). Today those server settings can only come from flags. This task adds a small, self-contained settings loader (a new internal package) that resolves the same set of server settings from several sources at once, so an operator can supply them through a config file, environment variables, or flags interchangeably.

## Files to Create/Modify

- `internal/serveconfig/serveconfig.go` (new) — the settings loader package.
- `internal/serveconfig/serveconfig_test.go` (new) — the deterministic unit tests for the loader.
- `go.mod` (modify) — add the dependency required to implement the loader.
- `go.sum` (modify) — the corresponding checksums.

You may add small test fixture files (e.g. config files) under `internal/serveconfig/testdata/` (new) if your tests need them.

## Requirements

### Settings shape

Define an exported struct `Settings` in package `serveconfig` with exactly these fields, decoded from the resolved configuration:

| Setting key            | Type            | Meaning                                  | Default        |
| ---------------------- | --------------- | ---------------------------------------- | -------------- |
| `port`                 | `int`           | port the server listens on               | `1313`         |
| `bind`                 | `string`        | interface to bind to                     | `"127.0.0.1"`  |
| `live_reload_port`     | `int`           | live-reload port                         | `-1`           |
| `environment`          | `string`        | named build environment                  | `"development"`|
| `render.to_disk`       | `bool` (nested) | whether to render to disk                | `false`        |
| `render.cache_dir`     | `string` (nested) | cache directory used while serving     | `""`           |

The struct must be populated by decoding the resolved configuration into it (not by hand-reading each key), and decoding must correctly fill the nested `render.to_disk` / `render.cache_dir` values as well as the underscore-named top-level field `live_reload_port`.

### Loader API

Provide an exported constructor `Load(opts Options) (*Settings, error)` (you choose the exact `Options` fields, but it must at minimum let a caller specify an optional config-file path). Each call to `Load` must build its configuration independently — concurrent or repeated calls, and the test cases, must not share or leak state between one another.

### Source layering and precedence

A single requested setting may be supplied by more than one source at the same time. When that happens, the loader must resolve it deterministically using this priority, highest first:

1. an explicit programmatic override passed in via `Options`,
2. an environment variable,
3. a value present in the config file,
4. the built-in default from the table above.

### Environment variables

- Environment variables for these settings are namespaced under the prefix `HUGO`. For example the `port` setting is read from `HUGO_PORT`, and `bind` from `HUGO_BIND`.
- Nested and underscore-named settings must also be reachable through this scheme: `render.to_disk` must be settable via `HUGO_RENDER_TO_DISK`, and `live_reload_port` via `HUGO_LIVE_RELOAD_PORT`.
- Unrelated, unprefixed environment variables (e.g. a bare `PORT`) must NOT influence any setting.

### Config files

- The config-file path is optional. If `Options` carries no path, or points to a file that does not exist, `Load` must still succeed and return settings drawn from the remaining sources (overrides, env, defaults). A missing config file is not an error.
- Any other failure while reading a config file that IS present (e.g. malformed/unparseable content) must be returned as an error from `Load`.
- A config file may supply any subset of the settings, including the nested `render.*` keys.

### Expected Functionality

- Scenario: nothing supplied -> `Load` returns the defaults from the table (`port=1313`, `bind="127.0.0.1"`, `live_reload_port=-1`, `environment="development"`, `render.to_disk=false`, `render.cache_dir=""`).
- Scenario: a config file sets `port` and `render.cache_dir`, env sets `HUGO_PORT`, an override sets `port` -> the override wins for `port`; `render.cache_dir` comes from the file.
- Scenario: a config file sets `port`, env sets `HUGO_PORT`, no override -> the env value wins for `port`.
- Scenario: only a config file sets `bind` -> that value is used.
- Scenario: `HUGO_RENDER_TO_DISK=true` is set -> resolved `render.to_disk` is `true`.
- Scenario: `HUGO_LIVE_RELOAD_PORT=443` is set -> resolved `live_reload_port` is `443`.
- Scenario: `Options` carries a path to a nonexistent file -> `Load` succeeds with defaults/env/override values.
- Scenario: `Options` carries a path to a file with invalid syntax -> `Load` returns a non-nil error.

## Acceptance Criteria

- A new package exists at `internal/serveconfig` exporting `Settings`, `Options`, and `Load`.
- The resolution order (override > env > file > default) holds for every setting, verified per the scenarios above.
- Environment lookups are namespaced under `HUGO_`; nested (`render.to_disk`) and underscore (`live_reload_port`) settings resolve from their `HUGO_RENDER_TO_DISK` / `HUGO_LIVE_RELOAD_PORT` forms; a bare `PORT` is ignored.
- A missing/absent config file does not produce an error; a present-but-unparseable file does.
- Tests are isolated: each test case constructs its own loader state and does not depend on execution order; environment mutations use `t.Setenv`.
- The following command passes from the repository root:

  ```
  go test ./internal/serveconfig/
  ```
