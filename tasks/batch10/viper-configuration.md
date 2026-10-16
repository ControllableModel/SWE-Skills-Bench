# Task: Add an Output Formats Configuration Loader for Hugo

## Background

Hugo lets a site configure custom output formats and which formats each page kind emits (see `output/` and Hugo's `outputs` / `outputFormats` configuration). This task adds a self-contained loader that reads a comma-or-list configured set of output formats and the per-kind output mapping, decoding them into typed structs and string slices.

## Files to Create/Modify

- `internal/outputconf/outputconf.go` (new) — the output-formats config loader.
- `internal/outputconf/outputconf_test.go` (new) — deterministic unit tests.
- `internal/outputconf/testdata/` (new) — optional fixture config files for the tests.
- `go.mod` (modify) — add the dependency required to implement the loader.
- `go.sum` (modify) — the corresponding checksums.

## Requirements

### Configuration shape

Define exported structs in package `outputconf`:

- `OutputConfig` with:
  - `Outputs` (`map[string][]string`, key `outputs`) — per page kind (e.g. `home`, `page`) to the list of format names.
  - `Formats` (`[]Format`, key `output_formats`) — custom format definitions.
- `Format` with `Name` (`string`, key `name`), `MediaType` (`string`, key `media_type`), and `BaseName` (`string`, key `base_name`).

The structs must be populated by decoding the resolved configuration, with the underscore-named `output_formats` / `media_type` / `base_name` keys decoding into their fields, and the `outputs` map of string slices decoding correctly.

### Slice handling

- A format list supplied as a YAML/TOML list (e.g. `["html","rss"]`) must decode into a `[]string`.
- A format list supplied as a single comma-separated string (e.g. `"html,rss"`) must ALSO decode into the equivalent `[]string{"html","rss"}`.

### Loader API

Provide `Load(opts Options) (*OutputConfig, error)`, where `Options` carries at minimum an optional config-file path. Each call must build its configuration independently — repeated calls and all test cases must not share or leak state, and tests must construct their own isolated loader rather than relying on any global/shared configuration.

### Missing-file handling

- If `Options` carries no path, or names a nonexistent file, `Load` must succeed and return an empty `OutputConfig`.
- A present-but-unparseable file must cause `Load` to return a non-nil error.

### Expected Functionality

- Scenario: file sets `outputs.home: ["html","rss","json"]` -> resolved `Outputs["home"] == ["html","rss","json"]`.
- Scenario: file sets `outputs.page: "html,amp"` (single comma-separated string) -> resolved `Outputs["page"] == ["html","amp"]`.
- Scenario: file defines one `output_formats` entry with `name: bibtex`, `media_type: application/x-bibtex`, `base_name: index` -> the decoded `Format` has those three fields populated (including the underscore-named ones).
- Scenario: no path / nonexistent path -> `Load` succeeds, empty config, `err == nil`.
- Scenario: present file with invalid syntax -> `Load` returns a non-nil error.
- Scenario: two independent `Load` calls in the same test process produce independent results and do not contaminate one another.

## Acceptance Criteria

- Package `internal/outputconf` exports `OutputConfig`, `Format`, `Options`, and `Load`.
- `outputs` decodes into `map[string][]string`; a comma-separated string value decodes into the equivalent slice.
- The underscore-named `output_formats` / `media_type` / `base_name` keys decode into their struct fields.
- A missing/absent config file is not an error; a present-but-unparseable file is.
- Tests are isolated: each case constructs its own loader state (no shared/global config) and does not depend on execution order.
- The following command passes from the repository root:

  ```
  go test ./internal/outputconf/
  ```
