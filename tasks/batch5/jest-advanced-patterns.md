# Task: Add a Shallow Object Diff utility to the shared package

## Background
The `shared` package in this React monorepo holds small, dependency-free comparison utilities (for example `shallowEqual.js`, `objectIs.js`). This task adds a companion utility that reports the precise shallow differences between two plain objects, useful for debugging prop changes between renders.

## Files to Create/Modify
- `packages/shared/shallowDiff.js` (new) — the diff implementation.
- `packages/shared/__tests__/shallowDiff-test.js` (new) — the deterministic test suite for the diff.

## Requirements

### Public API
`shallowDiff.js` must `export default` a function:

```
shallowDiff(prev, next)
```

It returns a result object of the exact shape:

```
{ added: string[], removed: string[], changed: string[], unchanged: string[] }
```

describing the differences between the own enumerable keys of `prev` and `next`.

### Classification rules
- `added`: keys present in `next` but not in `prev`.
- `removed`: keys present in `prev` but not in `next`.
- `changed`: keys present in both whose values are **not** the same value. Sameness must follow `Object.is` semantics — in particular `NaN` is the same as `NaN`, and `+0` and `-0` are **different**.
- `unchanged`: keys present in both whose values are the same value under those semantics.
- Only own enumerable keys participate; inherited keys must be ignored.
- Each of the four arrays must contain its keys sorted in ascending lexicographic order, and no key may appear in more than one array.

### Edge cases
- Comparing two empty objects -> all four arrays empty.
- Identical objects (same keys, same values) -> every key in `unchanged`, others empty.
- If either argument is not a non-null object, `shallowDiff` throws a `TypeError`.

### Expected Functionality
- `shallowDiff({a:1,b:2}, {b:2,c:3})` -> `added:['c'], removed:['a'], changed:[], unchanged:['b']`.
- A key whose value changes from `1` to `2` -> that key in `changed`.
- A key whose value is `NaN` in both -> that key in `unchanged` (not `changed`).
- A key that is `+0` in `prev` and `-0` in `next` -> that key in `changed`.
- Output arrays are always sorted regardless of insertion order.

## Acceptance Criteria
- `packages/shared/shallowDiff.js` exists and exports the function by default.
- `packages/shared/__tests__/shallowDiff-test.js` exists and covers, with independent test cases, every behavior above (added/removed/changed/unchanged classification, `Object.is` semantics for `NaN` and signed zero, empty-object handling, deterministic sorting, exclusion of inherited keys, and the `TypeError` for non-object inputs). The suite must assert the full structural shape of the returned result (for example with object/array equality matchers) rather than spot-checking a single field, and must include at least one case verifying the result against a captured expected snapshot of the structure. Tests must not depend on wall-clock timing, randomness, network, or a running server.
- The following command passes with all assertions green:

```
yarn test packages/shared/__tests__/shallowDiff-test.js
```
