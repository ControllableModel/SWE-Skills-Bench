# Task: Add a Props Shape Validator to the shared package

## Background
The `shared` package in this React monorepo holds small, dependency-free utility modules (for example `isArray.js`, `hasOwnProperty.js`) consumed across renderers. This task adds a lightweight runtime validator that checks a plain options object against a declared shape and reports every violation, useful for guarding internal configuration objects.

## Files to Create/Modify
- `packages/shared/validateShape.js` (new) — the validator implementation.
- `packages/shared/__tests__/validateShape-test.js` (new) — the deterministic test suite for the validator.

## Requirements

### Public API
`validateShape.js` must `export default` a function:

```
validateShape(schema, value)
```

- `schema` is an object mapping field names to descriptors `{ type, required }`, where `type` is one of the strings `'string'`, `'number'`, `'boolean'`, `'function'`, `'array'`, `'object'`, and `required` is a boolean (default `false` when omitted).
- The function returns an array of human-readable error message strings, one per violation, in the order the schema's fields are declared. An empty array means the value is valid.

### Validation rules
- A field whose descriptor is `required: true` and is missing from `value` (key absent) produces a "missing required field" violation for that field.
- A field that is present but whose value does not match the declared `type` produces a "type mismatch" violation naming the field, the expected type, and the actual type. Type checks must be precise: `'array'` matches arrays but not plain objects; `'object'` matches non-null non-array objects but not arrays or `null`; `'number'` must reject `NaN`.
- A field that is absent and not required produces no violation.
- Unknown keys present in `value` but not in `schema` produce an "unexpected field" violation, listed after all declared-field violations, sorted lexicographically.

### Validation of inputs
- If `schema` is not a non-null object, the function throws a `TypeError`.
- If `value` is not a non-null object, the function throws a `TypeError`.

### Expected Functionality
- Valid value matching every field -> returns `[]`.
- Missing a required field -> returns exactly one violation referencing that field.
- A field declared `'number'` given `NaN` -> a type-mismatch violation.
- A field declared `'array'` given a plain object -> a type-mismatch violation.
- An extra key not in the schema -> an "unexpected field" violation appended at the end.
- Multiple violations -> declared-field violations appear in schema order, then unexpected-field violations in lexicographic order.

## Acceptance Criteria
- `packages/shared/validateShape.js` exists and exports the function by default.
- `packages/shared/__tests__/validateShape-test.js` exists and covers, with independent test cases, every behavior above (valid pass-through, missing-required detection, precise type checks including `NaN`/array/object/null distinctions, unexpected-key detection, message ordering, and the `TypeError` for non-object `schema` or `value`). The suite must assert both the number of violations and the content of individual messages (for example using a substring/length matcher), and must assert that invalid inputs cause the function to throw. Tests must not depend on wall-clock timing, randomness, network, or a running server.
- The following command passes with all assertions green:

```
yarn test packages/shared/__tests__/validateShape-test.js
```
