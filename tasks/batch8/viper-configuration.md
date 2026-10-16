# Task: Add a Cache TTL Configuration Loader for Hugo

## Background

Hugo configures several named caches, each with an expiration window (see `config/allconfig/` and Hugo's `caches` configuration). This task adds a self-contained loader that reads per-cache settings — including human-readable duration strings such as `"10m"` and `"24h"` — and decodes them into typed `time.Duration` values.

## Files to Create/Modify

- `internal/cachettl/cachettl.go` (new) — the cache-TTL config loader.
- `internal/cachettl/cachettl_test.go` (new) — deterministic unit tests.
- `internal/cachettl/testdata/` (new) — optional fixture config files for the tests.
- `go.mod` (modify) — add the dependency required to implement the loader.
- `go.sum` (modify) — the corresponding checksums.

## Requirements

### Configuration shape

Define exported structs in package `cachettl`:

- `CacheConfig` with field `Caches` (`map[string]CacheEntry`, key `caches`).
- `CacheEntry` with:
  - `MaxAge` (`time.Duration`, key `max_age`) — decoded from a duration string such as `"10m"`.
  - `Dir` (`string`, key `dir`).

The struct must be populated by decoding the resolved configuration. The `max_age` keys, expressed in the config as duration strings (e.g. `"10m"`, `"1h30m"`, `"-1"`), must decode into Go `time.Duration` values; a plain integer must decode as a count of nanoseconds is NOT required — duration-string decoding is the requirement.

### Loader API

Provide `Load(opts Options) (*CacheConfig, error)`, where `Options` carries at minimum an optional config-file path. Each call must build its configuration independently — repeated calls and test cases must not share or leak state.

### Duration decoding

- A `max_age` value written as a Go duration string (`"10m"`, `"24h"`, `"1h30m"`) must decode to the corresponding `time.Duration`.
- A `max_age` of `"0"` must decode to a zero duration; a `max_age` of `"-1"` (meaning "never expire") must decode to `-1 * time.Nanosecond` (i.e. `time.Duration(-1)`).
- Environment variables are namespaced under the prefix `HUGOCACHE`; for example a per-cache value can be overridden via `HUGOCACHE_CACHES_ASSETS_MAX_AGE`.

### Missing-file handling

- If `Options` carries no path, or points to a nonexistent file, `Load` must succeed and return an empty cache set.
- A present-but-unparseable file must cause `Load` to return a non-nil error.

### Expected Functionality

- Scenario: file sets `caches.assets.max_age: "10m"` -> resolved `Caches["assets"].MaxAge == 10*time.Minute`.
- Scenario: file sets `caches.images.max_age: "1h30m"` -> resolved `Caches["images"].MaxAge == 90*time.Minute`.
- Scenario: file sets `caches.getjson.max_age: "-1"` -> resolved `MaxAge == time.Duration(-1)`.
- Scenario: file sets `caches.assets.dir: /tmp/a` -> resolved `Caches["assets"].Dir == "/tmp/a"`.
- Scenario: `HUGOCACHE_CACHES_ASSETS_MAX_AGE=5m` set with no file -> resolved `Caches["assets"].MaxAge == 5*time.Minute`.
- Scenario: no path / nonexistent path -> `Load` succeeds, empty cache set, `err == nil`.
- Scenario: present file with invalid syntax -> `Load` returns a non-nil error.

## Acceptance Criteria

- Package `internal/cachettl` exports `CacheConfig`, `CacheEntry`, `Options`, and `Load`.
- `max_age` duration strings decode into `time.Duration`, including `"-1"` -> `time.Duration(-1)`.
- Per-cache env overrides resolve under the `HUGOCACHE_` prefix.
- A missing/absent config file is not an error; a present-but-unparseable file is.
- Tests are isolated: each case builds its own loader state, does not depend on ordering, and uses `t.Setenv` for environment mutations.
- The following command passes from the repository root:

  ```
  go test ./internal/cachettl/
  ```
