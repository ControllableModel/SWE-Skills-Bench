# Task: Add Fixed-Length Support (`len`) to the `validate` Struct Tag

## Background

`swaggo/swag` translates Go struct tags into OpenAPI schema constraints. The `validate` tag already maps `min`/`max` onto a string field's length bounds and an array's item-count bounds, but it has no way to express an *exact* length, which validation libraries spell `len=N`. This task adds the `len` rule.

## Files to Create/Modify

- `field_parser.go` (modify) — extend `validate`-tag handling so a `len=<n>` rule is recognized and turned into the appropriate fixed-length constraint on the generated schema.
- `field_parser_test.go` (modify) — add a focused subtest (a new `t.Run(...)` inside `TestValidTags`) covering the new behavior and its edge cases.

## Requirements

### Tag Syntax

The `validate` tag is a comma-separated list of rules. A new `len=<n>` rule MUST be recognized, where `<n>` is a non-negative integer. Example field tags:

```go
Code   string   `json:"code"   validate:"len=6"`
Coords []float64 `json:"coords" validate:"len=2"`
```

### Mapping to the Generated Schema

- On a **string** field, `len=<n>` MUST set BOTH the minimum-length and maximum-length constraints of the schema to `<n>` (an exact length is the same lower and upper bound).
- On an **array** field, `len=<n>` MUST set BOTH the minimum-item-count and maximum-item-count constraints of the schema to `<n>`.
- The rule MUST coexist with `required` and with other length rules in the same tag. When both `len` and an explicit `min`/`max` appear, the rule processed later in left-to-right tag order wins for the bound it sets (i.e., `len` does not get special precedence; it behaves like setting both bounds).

### Type Handling

- On a numeric scalar field (`integer`, `number`) or a `boolean` field, `len=<n>` MUST be silently ignored: no constraint, no error.

### Edge Cases

- A non-integer value (e.g. `len=abc`) MUST be ignored without error and set no constraint.
- An empty value (`validate:"len="`) MUST be treated as "no constraint": nothing set, no error.
- `len=0` on a string MUST set both length bounds to 0.
- A `validate` tag with no `len` rule MUST leave length/item-count bounds unchanged from current behavior.
- `ComplementSchema` MUST NOT return a non-nil error in any of these cases.

### Expected Functionality

| Field tag | Schema type | Outcome |
| --- | --- | --- |
| `validate:"len=6"` | string | `MinLength == 6` and `MaxLength == 6` |
| `validate:"len=2"` | array | `MinItems == 2` and `MaxItems == 2` |
| `validate:"len=6"` | integer | no length/item bounds, no error |
| `validate:"len=0"` | string | `MinLength == 0` and `MaxLength == 0` |
| `validate:"required,len=4"` | string | both length bounds `== 4` |

## Acceptance Criteria

- A `tagBaseFieldParser` built from `json:"v" validate:"len=6"` applied to a `string`-typed `spec.Schema` yields `*MinLength == 6` and `*MaxLength == 6`, no error.
- The same rule on an `array`-typed schema yields `*MinItems == 2` and `*MaxItems == 2` for `validate:"len=2"`.
- `validate:"len=6"` on an `integer`-typed schema leaves all length and item bounds nil, no error.
- `validate:"len="` and `validate:"len=abc"` set nothing and return no error.
- All previously passing assertions in `TestValidTags` continue to pass unchanged.
- The following command passes from the repository root:

  ```bash
  go test -run TestValidTags ./...
  ```
