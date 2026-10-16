# Task: Build a Cache-Optional Service Example with Degraded Fallback

## Background

The `docs/ex` directory of the `go.uber.org/fx` repository is a standalone Go module (`go.uber.org/fx/docs`, with `replace go.uber.org/fx => ../`) hosting small self-contained example applications, each in its own package with a co-located `_test.go`. This task adds a new example showing how a service can consume a dependency that may or may not be present in the graph, behaving in full mode when it is wired and in a degraded mode when it is absent — all without the consuming constructor failing to build.

## Files to Create/Modify

- `docs/ex/optcache/cache.go` (new) — a `Cache` interface and an in-memory implementation.
- `docs/ex/optcache/lookup.go` (new) — a `Lookup` service that uses the cache when available.
- `docs/ex/optcache/app.go` (new) — the composition root exposing `Module` (core, no cache) and `CacheModule` (adds the cache).
- `docs/ex/optcache/optcache_test.go` (new) — the deterministic test described in Acceptance Criteria.

All files use package name `optcache`. Reuse the existing `go.uber.org/fx/docs` module; do not create a new module or edit `go.mod`.

## Requirements

### Cache

- Define an exported `Cache` interface with `Get(key string) (string, bool)` and `Set(key, val string)`. Provide an exported `NewMemoryCache` constructor returning a `Cache` backed by a concurrency-safe map.

### Lookup service with optional dependency

- Define an exported `Lookup` struct with a method `Resolve(key string) string`.
- `NewLookup` must build successfully whether or not a `Cache` is present in the graph. When the cache is absent, `Resolve` must return `"miss:" + key` and report `CacheEnabled() == false`. When the cache is present, `Resolve` must consult the cache: on a populated key it returns the cached value, and `CacheEnabled()` must report `true`.
- The constructor must not panic, must not require the cache, and must not produce a missing-dependency error when the cache is not wired.

### Composition roots

- Expose `Module` (`fx.Option`) that provides `Lookup` only (no cache). Booting `Module` alone must yield a working `*Lookup` in degraded mode.
- Expose `CacheModule` (`fx.Option`) that provides the `Cache`. Booting `Module` + `CacheModule` must yield a `*Lookup` with the cache enabled.

### Edge cases & constraints

- Booting `Module` alone must not produce a missing-dependency or cycle error.
- The same `Lookup` constructor source must serve both wirings unchanged — the only difference between the two boots is whether `CacheModule` is included.
- In the cache-enabled boot the test pre-populates a key through the resolved `Cache` and confirms `Lookup` reads it back.

## Expected Functionality

- Scenario: boot `Module` alone, then `Resolve("k")` → outcome: `"miss:k"` and `CacheEnabled() == false`.
- Scenario: boot `Module` + `CacheModule`, set `"k" -> "v"` on the cache, then `Resolve("k")` → outcome: `"v"` and `CacheEnabled() == true`.
- Scenario: boot `Module` + `CacheModule`, `Resolve("absent")` → outcome: `"miss:absent"`.

## Acceptance Criteria

- A new package `optcache` exists under `docs/ex/optcache/` exposing `Cache`, `NewMemoryCache`, `Lookup` (with `Resolve` and `CacheEnabled`), `NewLookup`, `Module`, and `CacheModule`.
- `docs/ex/optcache/optcache_test.go` contains two boots:
  - one boots `Module` alone via `fxtest.New`, populates a `*Lookup` and `*Cache` interface target (the cache target must be absent / the boot must still succeed), and asserts degraded behavior;
  - one boots `Module` + `CacheModule`, populates both `*Lookup` and `Cache`, seeds a key, and asserts the cached value is returned and `CacheEnabled() == true`.
- Both boots use `RequireStart().RequireStop()`.
- A `Lookup` that hard-requires the cache fails the first (cache-absent) boot with a missing-dependency error.
- The following command, run from the `docs` directory, passes:

  ```bash
  cd docs && go test ./ex/optcache/...
  ```
