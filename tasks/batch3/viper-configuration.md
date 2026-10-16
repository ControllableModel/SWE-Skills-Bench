# Task: Add a Layered Module Configuration Merger for Hugo

## Background

Hugo's module system (see `modules/`) lets a site import other modules, each able to contribute its own configuration. This task adds a small, self-contained loader that composes a module's effective configuration by merging a base config file with a project-level override config file, so that a higher-precedence file fills in or overrides keys from the lower-precedence one.

## Files to Create/Modify

- `internal/moduleconf/moduleconf.go` (new) — the layered config merger.
- `internal/moduleconf/moduleconf_test.go` (new) — deterministic unit tests.
- `internal/moduleconf/testdata/` (new) — optional fixture config files for the tests.
- `go.mod` (modify) — add the dependency required to implement the merger.
- `go.sum` (modify) — the corresponding checksums.

## Requirements

### Configuration shape

Define an exported struct `ModuleConfig` decoded from the merged configuration:

| Key            | Field        | Type       | Meaning                              |
| -------------- | ------------ | ---------- | ------------------------------------ |
| `path`         | `Path`       | `string`   | module import path                   |
| `replacements` | `Replacements` | `[]string` | replacement directives             |
| `mounts`       | `Mounts`     | `[]Mount`  | mount entries (nested list)          |

`Mount` has `Source` (`string`, key `source`), `Target` (`string`, key `target`), and `ExcludeFiles` (`[]string`, key `exclude_files`). The structs must be populated by decoding the merged config tree, and the underscore-named `exclude_files` field must decode from its `exclude_files` key.

### Merge API

Provide `Merge(basePath, overridePath string) (*ModuleConfig, error)`:

- Read the base config file first, then merge the override file on top of it so that keys present in the override take precedence, while keys only in the base are preserved.
- Each `Merge` call must construct its configuration independently — repeated calls and all test cases must not share or leak state.

### Missing-file handling

- If `basePath` is empty or points to a nonexistent file, `Merge` must still succeed and produce a config drawn from the override file alone (or an empty config if both are absent).
- The same graceful behavior applies when `overridePath` is empty or nonexistent: the base file alone is used.
- A file that IS present but contains malformed/unparseable content must cause `Merge` to return a non-nil error.

### Expected Functionality

- Scenario: base sets `path: github.com/x/base` and one mount; override sets a second mount only -> merged config keeps `path` from base and the override's value wins where both set the same key.
- Scenario: base sets `path: a` and override sets `path: b` -> merged `Path == "b"`.
- Scenario: a mount entry sets `exclude_files: ["*.tmp"]` -> the decoded `Mount.ExcludeFiles == ["*.tmp"]`.
- Scenario: `basePath` points to a nonexistent file but `overridePath` exists -> `Merge` succeeds using the override only.
- Scenario: both paths are empty strings -> `Merge` succeeds and returns a zero-valued config, no error.
- Scenario: `overridePath` points to a file with invalid syntax -> `Merge` returns a non-nil error.

## Acceptance Criteria

- Package `internal/moduleconf` exports `ModuleConfig`, `Mount`, and `Merge`.
- The override file's keys override the base file's keys; base-only keys are preserved.
- Nested `mounts` lists and the underscore-named `exclude_files` field decode correctly.
- A missing/absent base or override file is not an error; a present-but-unparseable file is.
- Tests are isolated: each case builds its own merger state and does not depend on execution order.
- The following command passes from the repository root:

  ```
  go test ./internal/moduleconf/
  ```
