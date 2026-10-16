# Task: Add a Flag-Bound Build Settings Resolver for Hugo

## Background

Hugo's build-related commands define flags such as `--minify`, `--baseURL`, and `--gc` (see `commands/hugobuilder.go` and `commands/commandeer.go`). This task adds a self-contained settings resolver that binds a flag set to the same setting keys, so build settings can be supplied by flags, environment variables, a config file, or built-in defaults through one API.

## Files to Create/Modify

- `internal/buildsettings/buildsettings.go` (new) — the flag-bound settings resolver.
- `internal/buildsettings/buildsettings_test.go` (new) — deterministic unit tests.
- `internal/buildsettings/testdata/` (new) — optional fixture config files for the tests.
- `go.mod` (modify) — add the dependency required to implement the resolver.
- `go.sum` (modify) — the corresponding checksums.

## Requirements

### Settings shape

Define an exported struct `BuildSettings` decoded from the resolved configuration:

| Key         | Field      | Type     | Default     |
| ----------- | ---------- | -------- | ----------- |
| `minify`    | `Minify`   | `bool`   | `false`     |
| `base_url`  | `BaseURL`  | `string` | `""`        |
| `gc`        | `GC`       | `bool`   | `false`     |
| `cache_dir` | `CacheDir` | `string` | `""`        |

The struct must be populated by decoding the resolved configuration, with the underscore-named `base_url` / `cache_dir` fields decoding from their respective keys.

### Resolver API

Provide `Resolve(flags *pflag.FlagSet, opts Options) (*BuildSettings, error)`, where `Options` carries at minimum an optional config-file path. The caller supplies a `*pflag.FlagSet` that defines the flags `minify`, `base-url`, `gc`, and `cache-dir`; the resolver must bind those flags to the matching setting keys (mapping the dash-named flags `base-url` / `cache-dir` to the underscore-named keys `base_url` / `cache_dir`). Binding must happen so that an explicitly-set flag value participates in resolution. Each call must build its configuration independently — repeated calls and test cases must not share or leak state.

### Source layering and precedence

When a setting is supplied by multiple sources, resolution must follow this priority, highest first:

1. a flag whose value was explicitly set on the flag set,
2. an environment variable,
3. a value in the config file,
4. the built-in default from the table.

A flag that was NOT explicitly set must not override a value coming from env or file.

### Environment variables

- Variables are namespaced under the prefix `HUGOBUILD`. For example `minify` is read from `HUGOBUILD_MINIFY`, and `base_url` from `HUGOBUILD_BASE_URL`.
- A bare unprefixed `MINIFY` must NOT influence any setting.

### Expected Functionality

- Scenario: nothing supplied (default flag values, no env, no file) -> defaults from the table.
- Scenario: the flag set has `--minify` explicitly set true and `HUGOBUILD_MINIFY=false` -> resolved `Minify == true` (flag wins).
- Scenario: `--base-url` not explicitly set, `HUGOBUILD_BASE_URL=https://env.example` set, file sets `base_url: https://file.example` -> resolved `BaseURL == "https://env.example"` (env beats file).
- Scenario: `--base-url` not set, no env, file sets `base_url: https://file.example` -> resolved `BaseURL == "https://file.example"`.
- Scenario: `--cache-dir` explicitly set to `/tmp/c` -> resolved `CacheDir == "/tmp/c"` regardless of env/file.
- Scenario: a bare `MINIFY=true` env var with no `HUGOBUILD_MINIFY` -> `Minify` stays `false`.

## Acceptance Criteria

- Package `internal/buildsettings` exports `BuildSettings`, `Options`, and `Resolve`.
- Flags bound from the supplied `*pflag.FlagSet` participate in resolution only when explicitly set; the dash-named flags map to the underscore-named keys.
- Precedence flag > env > file > default holds for every setting, verified per the scenarios.
- Environment lookups are namespaced under `HUGOBUILD_`; a bare `MINIFY` is ignored.
- Tests are isolated: each case constructs its own flag set and resolver state, does not depend on ordering, and uses `t.Setenv`.
- The following command passes from the repository root:

  ```
  go test ./internal/buildsettings/
  ```
