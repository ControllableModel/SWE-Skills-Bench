# Task: Add an Optional Security Policy Loader for Hugo

## Background

Hugo enforces a security policy controlling which external commands and network calls a build may make (see `config/security/securityConfig.go`). This task adds a self-contained loader that reads an optional security-policy file, where the file is genuinely optional: a build run without one must fall back to safe defaults rather than fail.

## Files to Create/Modify

- `internal/securitypolicy/securitypolicy.go` (new) — the optional policy loader.
- `internal/securitypolicy/securitypolicy_test.go` (new) — deterministic unit tests.
- `internal/securitypolicy/testdata/` (new) — optional fixture config files for the tests.
- `go.mod` (modify) — add the dependency required to implement the loader.
- `go.sum` (modify) — the corresponding checksums.

## Requirements

### Policy shape

Define an exported struct `Policy` decoded from the resolved configuration:

| Key                  | Field        | Type       | Default        |
| -------------------- | ------------ | ---------- | -------------- |
| `enable_inline_shortcodes` | `EnableInlineShortcodes` | `bool` | `false` |
| `exec.allow`         | `Exec.Allow` (nested) | `[]string` | `["^go$", "^git$"]` |
| `http.urls`          | `HTTP.URLs` (nested)  | `[]string` | `[".*"]`       |

The struct must be populated by decoding the resolved configuration, correctly filling the nested `exec.allow` / `http.urls` slices and the underscore-named top-level field.

### Loader API

Provide `Load(path string) (*Policy, error)`:

- `path` names an optional config file. Each call must build its configuration independently — repeated calls and test cases must not share or leak state.

### Missing-file vs error handling

- If `path` is an empty string, or names a file that does not exist, `Load` must succeed and return the built-in default policy from the table. A missing or unspecified file is explicitly NOT an error.
- If `path` names a file that IS present but whose contents are malformed/unparseable, `Load` must return a non-nil error.
- A present, well-formed file may supply any subset of the keys; unspecified keys keep their table defaults.

### Expected Functionality

- Scenario: `Load("")` -> succeeds, returns the defaults (`EnableInlineShortcodes=false`, `Exec.Allow=["^go$","^git$"]`, `HTTP.URLs=[".*"]`), `err == nil`.
- Scenario: `Load("/path/does/not/exist.yaml")` -> succeeds with the defaults, `err == nil`.
- Scenario: a present file sets `enable_inline_shortcodes: true` -> resolved `EnableInlineShortcodes == true`; the unspecified `exec.allow` keeps its default.
- Scenario: a present file sets `exec.allow: ["^npm$"]` -> resolved `Exec.Allow == ["^npm$"]`.
- Scenario: a present file with invalid syntax -> `Load` returns a non-nil error.

## Acceptance Criteria

- Package `internal/securitypolicy` exports `Policy` and `Load`.
- A missing, empty-path, or absent config file is NOT an error and yields the documented defaults.
- A present-but-unparseable file IS an error.
- A present, valid file overrides only the keys it specifies; nested `exec.allow` / `http.urls` slices and the underscore-named top-level field decode correctly.
- Tests are isolated: each case builds its own loader state and does not depend on execution order.
- The following command passes from the repository root:

  ```
  go test ./internal/securitypolicy/
  ```
