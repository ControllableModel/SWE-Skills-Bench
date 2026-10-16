# Task: Support Quoted Multi-Word Values in the `@Tags` Operation Annotation

## Background

`swaggo/swag` parses doc-comment annotations on handler functions. The `@Tags` annotation groups an operation under one or more tag names, parsed today by splitting the comment line on commas. Because the split happens on bare commas with no quoting awareness, a tag whose name contains a comma cannot be expressed, and surrounding quotes are kept verbatim in the tag name. This task makes `@Tags` quote-aware.

## Files to Create/Modify

- `operation.go` (modify) — change `ParseTagsComment` so a double-quoted tag value is treated as a single tag with the quotes stripped, and commas inside quotes do not split.
- `operation_test.go` (modify) — extend or add a test (build on the existing `TestParseTagsComment`) covering quoted and mixed quoted/unquoted inputs.

## Requirements

### Parsing Rules

The argument to `@Tags` is a comma-separated list of tag names. The parser MUST honor double quotes as grouping delimiters:

- A tag wrapped in double quotes is a single tag; the surrounding quotes MUST be removed from the stored tag name.
- A comma that appears **inside** a pair of double quotes MUST NOT split the value.
- A comma **outside** quotes still separates tags.
- Leading/trailing ASCII whitespace around each resulting tag name MUST be trimmed (current behavior).

### Expected Functionality

| `@Tags` argument | Resulting `operation.Tags` |
| --- | --- |
| `pets, store` | `["pets", "store"]` |
| `"user accounts"` | `["user accounts"]` |
| `"user accounts", store` | `["user accounts", "store"]` |
| `"a, b", c` | `["a, b", "c"]` |
| `pets` | `["pets"]` |

### Constraints

- Unquoted input MUST continue to behave exactly as before (no quotes are stripped from a value that was never quoted; e.g. `pets` stays `pets`).
- A quoted empty value `""` MUST produce a single empty-string tag (it is a tag entry, just empty), consistent with stripping the quotes.
- The order of tags MUST be preserved.

## Acceptance Criteria

- Calling `ParseTagsComment` (via a fresh `Operation`) with `"user accounts", store` results in `operation.Tags` equal to `[]string{"user accounts", "store"}`.
- Calling it with `"a, b", c` results in `[]string{"a, b", "c"}`.
- Calling it with `pets, store` still results in `[]string{"pets", "store"}` (unchanged).
- The pre-existing `TestParseTagsComment` assertions continue to pass.
- The following command passes from the repository root:

  ```bash
  go test -run TestParseTagsComment ./...
  ```
