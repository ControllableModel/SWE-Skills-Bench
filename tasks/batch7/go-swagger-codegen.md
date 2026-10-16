# Task: Add `multipleOf` Support to the `validate` Struct Tag

## Background

`swaggo/swag` maps Go struct tags onto OpenAPI schema constraints. A field's "must be a multiple of N" constraint is expressed in OpenAPI as `multipleOf`. Today `multipleOf` can only be set through the dedicated `multipleOf:"..."` struct tag, never through the `validate` tag that already carries the other numeric constraints. This task lets the `validate` tag express it too.

## Files to Create/Modify

- `field_parser.go` (modify) — extend `validate`-tag handling so a multiple-of rule is recognized and carried onto the generated schema's `multipleOf` constraint.
- `field_parser_test.go` (modify) — add a focused subtest (a new `t.Run(...)` inside `TestValidTags`) covering the behavior and edge cases.

## Requirements

### Tag Syntax

The `validate` tag is a comma-separated list of rules. A new `key=value` rule of the form `multiple=<number>` MUST be recognized, where `<number>` is a positive number (integer or float). Example field tags:

```go
Quantity int     `json:"quantity" validate:"multiple=5"`
Step     float64 `json:"step"     validate:"multiple=0.25"`
```

### Mapping to the Generated Schema

- On an `integer` or `number` field, `multiple=<n>` MUST set the schema's `multipleOf` constraint to `<n>`.
- The rule MUST coexist with `required` and with `min`/`max`/`gte`/`lte` in the same tag (order independent); enabling `multiple` MUST NOT suppress those bounds, and vice versa.

### Type Handling

- On a non-numeric field (`string`, `boolean`), a `multiple=<n>` rule MUST be silently ignored: no `multipleOf` set, no error.
- For an **array of numbers** field, the constraint applies to the element (item) schema, mirroring how other per-element numeric constraints are placed on the items schema; the array schema itself must not gain `multipleOf`.

### Edge Cases

- A non-numeric value (e.g. `multiple=abc`) MUST be ignored without error.
- An empty value (`validate:"multiple="`) MUST be treated as "no constraint": nothing set, no error.
- A `validate` tag with no `multiple` rule MUST leave `multipleOf` nil (unchanged behavior).
- `ComplementSchema` MUST NOT return a non-nil error in any of these cases.

### Expected Functionality

| Field tag | Schema type | Outcome |
| --- | --- | --- |
| `validate:"multiple=5"` | integer | `MultipleOf == 5` |
| `validate:"multiple=0.25"` | number | `MultipleOf == 0.25` |
| `validate:"multiple=5"` | string | no `multipleOf`, no error |
| `validate:"required,min=10,multiple=5"` | integer | `Minimum == 10` and `MultipleOf == 5` |
| `validate:"multiple=2"` | array (items: integer) | items schema `MultipleOf == 2`; top-level none |

## Acceptance Criteria

- A `tagBaseFieldParser` built from `json:"v" validate:"multiple=5"` applied to an `integer`-typed `spec.Schema` yields `*MultipleOf == 5`, no error.
- `validate:"multiple=0.25"` on a `number`-typed schema yields `*MultipleOf == 0.25`.
- `validate:"multiple=5"` on a `string`-typed schema leaves `MultipleOf` nil, no error.
- For an `array` of integers, the value lands on `schema.Items.Schema.MultipleOf` and the top-level stays nil.
- All previously passing assertions in `TestValidTags` continue to pass unchanged.
- The following command passes from the repository root:

  ```bash
  go test -run TestValidTags ./...
  ```
