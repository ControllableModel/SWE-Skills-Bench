# Task: Add a Runtime Environment Resolver for Hugo

## Background

Hugo reads a number of runtime tuning values from `HUGO_`-prefixed environment variables today via ad-hoc `os.Getenv` calls (see `config/env.go`, e.g. `HUGO_NUMWORKERMULTIPLIER`, `HUGO_MEMORYLIMIT`, `HUGO_ENVIRONMENT`). This task adds a self-contained resolver package that exposes the same family of runtime values through a single, uniform environment-driven API, including nested keys, instead of one-off getters.

## Files to Create/Modify

- `internal/runtimeenv/runtimeenv.go` (new) — the environment resolver.
- `internal/runtimeenv/runtimeenv_test.go` (new) — deterministic unit tests.
- `go.mod` (modify) — add the dependency required to implement the resolver.
- `go.sum` (modify) — the corresponding checksums.

## Requirements

### Resolved shape

Define an exported struct `RuntimeEnv` decoded from the resolved configuration:

| Key                       | Field               | Type     | Default         |
| ------------------------- | ------------------- | -------- | --------------- |
| `environment`             | `Environment`       | `string` | `"production"`  |
| `num_worker_multiplier`   | `NumWorkerMultiplier` | `int`  | `0`             |
| `memory_limit`            | `MemoryLimit`       | `int`    | `0`             |
| `cache.dir`               | `Cache.Dir` (nested)| `string` | `""`            |
| `cache.max_age`           | `Cache.MaxAge` (nested) | `int`| `0`             |

The struct must be populated by decoding the resolved configuration into it, correctly filling the nested `cache.dir` / `cache.max_age` values and the underscore-named top-level `num_worker_multiplier` / `memory_limit` fields.

### Resolver API

Provide `Resolve() (*RuntimeEnv, error)`. There is no config file involved — values come only from environment variables layered over the built-in defaults. Each call must build its configuration independently; repeated calls and test cases must not share or leak state.

### Environment variables

- All environment variables are namespaced under the prefix `HUGO`. For example `environment` is read from `HUGO_ENVIRONMENT`.
- Underscore-named top-level keys resolve from their flattened form: `num_worker_multiplier` from `HUGO_NUM_WORKER_MULTIPLIER`, `memory_limit` from `HUGO_MEMORY_LIMIT`.
- Nested keys resolve from a flattened, underscore-joined form: `cache.dir` from `HUGO_CACHE_DIR`, `cache.max_age` from `HUGO_CACHE_MAX_AGE`.
- An unprefixed bare variable (e.g. `ENVIRONMENT`) must NOT influence any value.
- When a variable is unset, the corresponding field must take the default from the table.

### Expected Functionality

- Scenario: no environment variables set -> `Resolve` returns the defaults (`environment="production"`, all numeric fields `0`, nested cache fields zero).
- Scenario: `HUGO_ENVIRONMENT=development` set -> resolved `Environment == "development"`.
- Scenario: `HUGO_NUM_WORKER_MULTIPLIER=4` set -> resolved `NumWorkerMultiplier == 4`.
- Scenario: `HUGO_CACHE_DIR=/var/cache/hugo` set -> resolved `Cache.Dir == "/var/cache/hugo"`.
- Scenario: `HUGO_CACHE_MAX_AGE=3600` set -> resolved `Cache.MaxAge == 3600`.
- Scenario: a bare `ENVIRONMENT=staging` is set but `HUGO_ENVIRONMENT` is not -> resolved `Environment` is still `"production"`.

## Acceptance Criteria

- Package `internal/runtimeenv` exports `RuntimeEnv` and `Resolve`.
- Every value resolves from a `HUGO_`-prefixed environment variable, with nested (`cache.dir`) and underscore (`num_worker_multiplier`) keys resolving from their flattened `HUGO_CACHE_DIR` / `HUGO_NUM_WORKER_MULTIPLIER` forms.
- A bare unprefixed variable is ignored; unset keys fall back to their table defaults.
- Tests are isolated: each case builds its own resolver state, does not depend on ordering, and uses `t.Setenv`.
- The following command passes from the repository root:

  ```
  go test ./internal/runtimeenv/
  ```
