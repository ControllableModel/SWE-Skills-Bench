# Task: Add a Route Path Matcher to the shared package

## Background
The `shared` package in this React monorepo holds small, dependency-free utility modules (for example `isArray.js`) consumed across renderers and tooling. This task adds a small path-pattern matcher that compiles a colon-style route pattern into a matcher able to test concrete paths and extract named parameters.

## Files to Create/Modify
- `packages/shared/createPathMatcher.js` (new) — the path matcher implementation.
- `packages/shared/__tests__/createPathMatcher-test.js` (new) — the deterministic test suite for the matcher.

## Requirements

### Public API
`createPathMatcher.js` must `export default` a factory function:

```
createPathMatcher(pattern)
```

- `pattern` is a string like `'/users/:userId/posts/:postId'`. Segments beginning with `:` are named parameters; all other segments are literals.
- The factory returns a matcher object exposing exactly these methods:
  - `match(path) -> { params: object } | null`
  - `paramNames() -> string[]`

### Matching rules
- A `path` matches only if it has the same number of `/`-separated segments as the pattern and every literal segment is identical.
- Each parameter segment captures exactly one non-empty segment. The captured value must be the raw segment text (no decoding).
- On a successful match, `match` returns `{ params }` where `params` maps each parameter name to its captured value; a pattern with no parameters yields `params: {}`.
- On no match (segment count differs, a literal differs, or a parameter segment would be empty), `match` returns `null`.
- A trailing slash makes the path's segment count differ from a pattern without one, so it must not match.
- `paramNames()` returns the parameter names in the order they appear in the pattern.

### Validation
- If `pattern` is not a string, the factory throws a `TypeError`.
- If `pattern` declares the same parameter name twice, the factory throws an `Error`.

### Expected Functionality
- Pattern `'/users/:id'` against `'/users/42'` -> `{ params: { id: '42' } }`.
- The same matcher against `'/users'` or `'/users/42/extra'` -> `null` (segment-count mismatch).
- Pattern `'/about'` against `'/about'` -> `{ params: {} }`; against `'/about/'` -> `null`.
- Pattern `'/users/:userId/posts/:postId'` -> `paramNames()` returns `['userId','postId']`.
- A path with an empty parameter segment (e.g. `'/users/'` against `'/users/:id'`) -> `null`.

## Acceptance Criteria
- `packages/shared/createPathMatcher.js` exists, exports the factory by default, and imports no other module.
- `packages/shared/__tests__/createPathMatcher-test.js` exists and covers, with independent test cases, every behavior above (single and multi-parameter capture, literal matching, segment-count and trailing-slash rejection, empty-parameter rejection, no-parameter patterns, `paramNames()` ordering, and the `TypeError`/duplicate-name `Error` validations). The suite should use string and value matchers to assert captured parameter values and to confirm non-matches return `null`. Tests must not depend on wall-clock timing, randomness, network, or a running server.
- The following command passes with all assertions green:

```
yarn test packages/shared/__tests__/createPathMatcher-test.js
```
