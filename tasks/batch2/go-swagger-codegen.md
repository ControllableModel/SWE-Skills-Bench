# Task: Add Exclusive Numeric Bound Support to the `validate` Struct Tag

## Background

`swaggo/swag` reads Go struct tags to enrich the generated OpenAPI schema for each field. The `validate` tag already understands inclusive numeric bounds (`min`/`gte`, `max`/`lte`) which become the schema's `minimum`/`maximum`. It has no notion of *exclusive* bounds, so a strictly-greater-than / strictly-less-than rule never reaches the spec. This task adds that.

## Files to Create/Modify

- `field_parser.go` (modify) — extend the `validate`-tag handling so strict (exclusive) numeric-bound rules are recognized and carried onto the generated schema.
- `field_parser_test.go` (modify) — add a focused subtest (a new `t.Run(...)` inside the existing `TestValidTags` function) covering the new behavior and edge cases.

## Requirements

### Tag Syntax

The `validate` tag is a comma-separated list of rules. Two new `key=value` rules MUST be recognized on numeric fields:

- `gt=<number>` — value is strictly greater than `<number>`.
- `lt=<number>` — value is strictly less than `<number>`.

Example field tags:

```go
Age   int     `json:"age"   validate:"gt=0,lt=130"`
Price float64 `json:"price" validate:"gt=0"`
```

### Mapping to the Generated Schema

- A `gt=<n>` rule on an `integer` or `number` field MUST set the schema's lower-bound (`minimum`) constraint to `<n>` AND mark that bound as exclusive (the schema's `exclusiveMinimum` flag becomes true).
- A `lt=<n>` rule MUST set the upper-bound (`maximum`) constraint to `<n>` AND mark that bound as exclusive (the schema's `exclusiveMaximum` flag becomes true).
- These MUST coexist in the same tag and with `required` (order independent).
- The existing inclusive rules (`min`/`gte`, `max`/`lte`) MUST keep working exactly as before and MUST leave the exclusive flags unset.

### Type Handling

- The rules apply only to numeric scalar fields (`integer`, `number`). On a `string` or `boolean` field, `gt=`/`lt=` MUST be silently ignored: no bound, no exclusive flag, no error.
- For an **array of integers** field, the bound and exclusive flag apply to the element (item) schema, mirroring how other per-element numeric constraints are placed on the items schema; the array schema itself must not gain the bound.

### Edge Cases

- A non-numeric value (e.g. `gt=abc`) MUST be ignored without error and MUST NOT set any bound or flag.
- An empty value (`validate:"gt="`) MUST be treated as "no constraint": no bound set, no flag set, no error.
- A `validate` tag with neither `gt` nor `lt` MUST leave both exclusive flags false (unchanged behavior).
- `ComplementSchema` MUST NOT return a non-nil error in any of these cases.

### Expected Functionality

| Field tag | Schema type | Outcome |
| --- | --- | --- |
| `validate:"gt=0"` | integer | `Minimum == 0`, `ExclusiveMinimum == true` |
| `validate:"lt=10"` | number | `Maximum == 10`, `ExclusiveMaximum == true` |
| `validate:"gte=0"` | integer | `Minimum == 0`, `ExclusiveMinimum == false` |
| `validate:"gt=0"` | string | no bound, `ExclusiveMinimum == false`, no error |
| `validate:"gt=0,lt=5"` | array (items: integer) | bounds + exclusive flags on items schema; top-level none |

## Acceptance Criteria

- A `tagBaseFieldParser` built from `json:"v" validate:"gt=0,lt=130"` applied to an `integer`-typed `spec.Schema` yields `*Minimum == 0`, `ExclusiveMinimum == true`, `*Maximum == 130`, `ExclusiveMaximum == true`, no error.
- The same tag on a `string`-typed schema leaves `Minimum`/`Maximum` nil and both exclusive flags false, no error.
- `validate:"gte=1,lte=9"` on an integer schema sets the bounds but both exclusive flags stay false.
- For an `array` of integers, the bounds and flags land on `schema.Items.Schema`, and the top-level schema has no bounds.
- All previously passing assertions in `TestValidTags` continue to pass unchanged.
- The following command passes from the repository root:

  ```bash
  go test -run TestValidTags ./...
  ```
