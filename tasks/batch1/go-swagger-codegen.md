# Task: Add Regular-Expression Constraint Support to the `validate` Struct Tag

## Background

`swaggo/swag` reads Go struct tags to enrich the generated OpenAPI schema for each field without altering the underlying Go type. Today the parser understands several constraints carried in the `validate` tag (length, numeric bounds, allowed values, uniqueness), but it ignores any regular-expression rule, so a `regexp`-style constraint declared on a string field never reaches the generated spec. This task adds support for that constraint.

## Files to Create/Modify

- `field_parser.go` (modify) — extend the `validate`-tag handling so a regular-expression constraint is recognized and carried onto the resulting schema.
- `field_parser_test.go` (modify) — add a focused test (a new `t.Run(...)` subtest inside the existing `TestValidTags` function) covering the new behavior and its edge cases.

## Requirements

### Tag Syntax

The `validate` struct tag is a comma-separated list of rules. Each rule is either a bare keyword (e.g. `required`) or a `key=value` pair (e.g. `max=10`). A new rule of the form `regexp=<expression>` MUST be recognized. Example field tags:

```go
Username string `json:"username" validate:"required,regexp=^[a-z0-9_]+$"`
Slug     string `json:"slug"     validate:"regexp=^[a-z]+(-[a-z]+)*$"`
```

The `<expression>` is the literal regular expression that the field value is expected to match.

### Mapping to the Generated Schema

- When a `regexp=<expression>` rule appears in the `validate` tag of a **string** field, the generated schema for that field MUST carry `<expression>` as its regular-expression (pattern) constraint in the produced OpenAPI schema object.
- The constraint MUST appear on the schema produced by `ComplementSchema`, alongside any other constraints already derived from the same tag (presence of `regexp` must not suppress `max`, `min`, `oneof`, etc., and vice versa).
- The rule MUST coexist with `required` in the same tag (order independent).

### Type Handling

- The constraint applies only when the field's schema type is `string`. For a non-string scalar field (e.g. an `integer` field), a `regexp=...` rule MUST be silently ignored — it MUST NOT appear on the generated schema and MUST NOT cause an error.
- For an **array of strings** field, the constraint applies to the element (item) schema, mirroring how other per-element string constraints are placed on the items schema rather than the array schema. (For an array field, the array schema itself must not gain the constraint.)

### Edge Cases

- An empty value (`validate:"regexp="`) MUST be treated as "no constraint": the generated schema's pattern constraint stays empty and no error is returned.
- A `validate` tag that contains no `regexp` rule MUST leave the schema's pattern constraint empty (unchanged from current behavior).
- The presence of a `regexp` rule MUST NOT cause `ComplementSchema` to return a non-nil error.
- Expressions may legitimately contain `=` characters (e.g. lookahead-free patterns are not required, but characters after the first `=` belong to the expression); only the first `=` separates the key from the value, so the full remainder is the expression.

### Expected Functionality

| Field tag | Schema type | Outcome |
| --- | --- | --- |
| `validate:"required,regexp=^[a-z]+$"` | string | schema pattern constraint == `^[a-z]+$` |
| `validate:"regexp=^[a-z]+$"` | integer | no pattern constraint on schema; no error |
| `validate:"regexp=^[a-z]+$"` | array (items: string) | items schema pattern constraint == `^[a-z]+$`; array schema has none |
| `validate:"regexp="` | string | empty pattern constraint; no error |
| `validate:"required,max=10"` | string | empty pattern constraint (unchanged) |

## Acceptance Criteria

- Building a `tagBaseFieldParser` from a field whose tag is `json:"test" validate:"required,regexp=^[a-z0-9_]+$"` and calling `ComplementSchema` on a `string`-typed `spec.Schema` results in the schema's `Pattern` field equal to `^[a-z0-9_]+$`, with no error returned.
- The same tag applied to an `integer`-typed schema leaves `Pattern` empty and returns no error.
- For an `array` schema whose items are `string`, the `regexp` expression lands on `schema.Items.Schema.Pattern` and the top-level `schema.Pattern` stays empty.
- A `validate:"regexp="` tag on a string schema leaves `Pattern` empty and returns no error.
- All previously passing assertions in `TestValidTags` (length, numeric bounds, `oneof`, `unique`) continue to pass unchanged.
- The following command passes from the repository root:

  ```bash
  go test -run TestValidTags ./...
  ```
