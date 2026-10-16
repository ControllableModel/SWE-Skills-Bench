# Task: Add a simple glob-to-RegExp matcher

## Background

Vite matches file paths against glob-like patterns in several places (include/exclude options, watch filters). A small, self-contained matcher for the common subset of glob syntax is a useful primitive. This task adds a `matchGlob` helper to the node utilities together with a fixture-driven test suite.

## Files to Create/Modify

- `packages/vite/src/node/utils.ts` (modify) — add and export a new function `matchGlob`.
- `packages/vite/src/node/__tests__/matchGlob.spec.ts` (new) — a dedicated test file exercising the matcher across many cases.

## Requirements

### Function signature

Add an exported function:

```ts
export function matchGlob(pattern: string, path: string): boolean
```

It returns whether `path` matches `pattern` under the simplified glob rules below. Paths use forward slashes.

### Matching rules

- `?` matches exactly one character that is not a `/`.
- `*` matches zero or more characters that are not `/` (single path segment).
- `**` matches zero or more characters including `/` (crosses segment boundaries). When written as `**/`, it also matches zero segments (so `**/a.js` matches `a.js`).
- A character class `[abc]` matches one character from the set; `[a-z]` supports ranges; `[!abc]` (leading `!`) negates the set. The negation/character-class still never matches `/`.
- Every other character is matched literally, and regex-special characters in the pattern (`.`, `+`, `(`, `)`, etc.) are treated as literals, not regex.
- The match is anchored: the entire `path` must be consumed by the pattern (full match, not partial).

### Edge cases

- `*` must not cross a `/`: `src/*.ts` does not match `src/a/b.ts`.
- `**` does cross `/`: `src/**/*.ts` matches `src/a/b/c.ts` and `src/a.ts`.
- A literal dot in the pattern matches only a real dot: `a.ts` matches `a.ts` but not `axts`.
- An empty pattern matches only the empty path.

### Expected Functionality

| Pattern | Path | Result |
|---------|------|--------|
| `*.ts` | `index.ts` | `true` |
| `*.ts` | `a/b.ts` | `false` |
| `src/**/*.ts` | `src/a/b/c.ts` | `true` |
| `src/**/*.ts` | `src/a.ts` | `true` |
| `**/a.js` | `a.js` | `true` |
| `file.?s` | `file.ts` | `true` |
| `[abc].ts` | `b.ts` | `true` |
| `[!abc].ts` | `b.ts` | `false` |
| `a.ts` | `axts` | `false` |

## Acceptance Criteria

- `matchGlob` is exported from `packages/vite/src/node/utils.ts` with the signature above.
- The new test file imports `matchGlob` from `../utils` and drives all pattern/path/result rows above via a shared, table-driven mechanism (e.g. a per-row fixture or `test.each` table), plus dedicated assertions for the `*`-does-not-cross-slash and `**`-does-cross-slash rules.
- The file contains at least 12 assertions total.
- Every test passes when run from the repo root:

```
pnpm exec vitest run packages/vite/src/node/__tests__/matchGlob.spec.ts
```

- A naive implementation (translating `*` to `.*`, not anchoring the match, or not escaping regex-special literals) must fail at least one assertion.
