# Task: Coerce Boolean Values in OpenAPI Extension Parameters

## Background

`swaggo/swag` lets annotation authors attach vendor extensions (`x-*`) to parameters and schemas. The `setExtensionParam` helper in `operation.go` parses an extension attribute such as `x-nullable=true,x-order=3` into a `spec.Extensions` map. Today every `key=value` pair is stored with the value as a raw string, so `x-nullable=true` serializes as the string `"true"` rather than the JSON boolean `true`. This task adds boolean coercion for those literal values.

## Files to Create/Modify

- `operation.go` (modify) — update `setExtensionParam` so an explicit value of `true` or `false` (case-sensitive, exact) is stored as a Go `bool`, while all other values remain strings.
- `operation_test.go` (new test) — add a test that exercises `setExtensionParam` directly across boolean, string, and bare-key cases.

## Requirements

### Parsing Rules

`setExtensionParam` receives a comma-separated attribute string. For each comma-separated entry (commas inside brackets/braces stay grouped, as today):

- A `key=true` entry MUST store the boolean `true` under `key`.
- A `key=false` entry MUST store the boolean `false` under `key`.
- A `key=value` entry whose value is anything else MUST store `value` as a string (unchanged behavior).
- A bare `key` (no `=`) MUST store boolean `true` (unchanged behavior).
- A `!key` entry MUST store boolean `false` (unchanged behavior).

### Constraints

- Only the exact lowercase tokens `true` and `false` are coerced. Values like `True`, `TRUE`, `1`, or `yes` MUST remain strings.
- Coercion applies only to the value portion after the first `=`; keys are never altered.
- The stored map key MUST retain its original casing.

### Expected Functionality

| Attribute | Stored extension entry |
| --- | --- |
| `x-nullable=true` | `x-nullable` → boolean `true` |
| `x-internal=false` | `x-internal` → boolean `false` |
| `x-order=3` | `x-order` → string `"3"` |
| `x-flag` | `x-flag` → boolean `true` |
| `!x-flag` | `x-flag` → boolean `false` |
| `x-name=True` | `x-name` → string `"True"` |

## Acceptance Criteria

- `setExtensionParam("x-nullable=true")` returns a map where the value for `x-nullable` is the boolean `true` (Go type `bool`), not the string `"true"`.
- `setExtensionParam("x-internal=false")` stores the boolean `false`.
- `setExtensionParam("x-order=3")` stores the string `"3"`.
- `setExtensionParam("x-name=True")` stores the string `"True"` (no coercion).
- The pre-existing extension-related behavior (bare key → true, `!key` → false) still holds.
- The following command passes from the repository root:

  ```bash
  go test -run TestSetExtensionParam ./...
  ```

  (Name the new test `TestSetExtensionParam`.)
