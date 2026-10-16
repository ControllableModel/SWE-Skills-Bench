# Task: Add Single-Value Enum Support (`eq`) to the `validate` Struct Tag

## Background

`swaggo/swag` derives an OpenAPI schema's allowed-values list (`enum`) from struct tags. The `validate` tag already maps `oneof=a b c` onto a multi-value enum, but validation libraries also express a single fixed allowed value as `eq=<value>`, which `swag` currently ignores. This task makes `eq` contribute a one-element enum.

## Files to Create/Modify

- `field_parser.go` (modify) — extend `validate`-tag handling so an `eq=<value>` rule produces a single-element enum on the generated schema.
- `field_parser_test.go` (modify) — add a focused subtest (a new `t.Run(...)` inside `TestValidTags`) covering the behavior and edge cases.

## Requirements

### Tag Syntax

The `validate` tag is a comma-separated list of rules. A new `eq=<value>` rule MUST be recognized. Example field tags:

```go
Kind   string `json:"kind"   validate:"eq=admin"`
Status int    `json:"status" validate:"eq=1"`
```

### Mapping to the Generated Schema

- An `eq=<value>` rule MUST set the schema's enum to a slice containing exactly the single value `<value>`, typed according to the field's schema type (string stays a string; integer/number are parsed numerically; boolean is parsed as a bool).
- If a `oneof` rule is also present in the same tag, the value set first (left-to-right in tag order) wins and the later one MUST NOT overwrite a non-empty enum. (The existing `oneof` behavior already declines to overwrite a non-empty enum; `eq` MUST behave the same way — it sets the enum only when no enum has been set yet.)

### Type Handling

- For an **array** field, the enum value is typed according to the array's element type (mirroring how `oneof` is typed for arrays).
- A value that cannot be converted to the field's type (e.g. `eq=abc` on an `integer` field) MUST be ignored without error and MUST NOT add an enum entry.

### Edge Cases

- An empty value (`validate:"eq="`) MUST be treated as "no constraint": no enum entry, no error.
- A `validate` tag with no `eq` (and no `oneof`) MUST leave the enum empty (unchanged behavior).
- `ComplementSchema` MUST NOT return a non-nil error in any of these cases.

### Expected Functionality

| Field tag | Schema type | Outcome |
| --- | --- | --- |
| `validate:"eq=admin"` | string | enum == `["admin"]` |
| `validate:"eq=1"` | integer | enum == `[1]` |
| `validate:"eq=abc"` | integer | enum empty, no error |
| `validate:"eq="` | string | enum empty, no error |
| `validate:"oneof=a b,eq=c"` | string | enum == `["a","b"]` (oneof set first; eq does not overwrite) |

## Acceptance Criteria

- A `tagBaseFieldParser` built from `json:"v" validate:"eq=admin"` applied to a `string`-typed `spec.Schema` yields `schema.Enum` equal to `[]any{"admin"}`, no error.
- `validate:"eq=1"` on an `integer`-typed schema yields an enum containing the single integer value `1`.
- `validate:"eq=abc"` on an integer schema leaves the enum empty and returns no error.
- `validate:"oneof=a b,eq=c"` on a string schema yields enum `["a", "b"]` (the `eq` does not overwrite).
- All previously passing assertions in `TestValidTags` continue to pass unchanged.
- The following command passes from the repository root:

  ```bash
  go test -run TestValidTags ./...
  ```
