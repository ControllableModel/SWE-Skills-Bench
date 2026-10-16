# Task: Add a request-query parsing utility for module URLs

## Background

Vite passes module identifiers around as URL-like strings that may carry a query string (e.g. `./Comp.vue?vue&type=style&index=0`) and/or a hash. The node-side utilities in `packages/vite/src/node/utils.ts` already split files from their postfix, but there is no helper that turns the query portion into a structured, easy-to-inspect object. This task adds that helper together with a focused test suite.

## Files to Create/Modify

- `packages/vite/src/node/utils.ts` (modify) — add and export a new function `parseRequestQuery`.
- `packages/vite/src/node/__tests__/parseRequestQuery.spec.ts` (new) — a dedicated test file that exercises the new function.

## Requirements

### Function signature

Add an exported function to `packages/vite/src/node/utils.ts`:

```ts
export function parseRequestQuery(url: string): Record<string, string>
```

It takes a single request string and returns a plain object mapping each query parameter name to its value. The function must be pure (no I/O, no global state) and must not mutate its input.

### Parsing behavior

- The query portion is the substring that begins at the first `?` and ends just before a `#` hash (if any). Everything before the first `?` (the file path) and everything from the `#` onward (the hash fragment) must be ignored.
- Parameters are separated by `&`. Each parameter may be in `name=value` or bare `name` form.
- A bare parameter (a flag with no `=`) maps to the empty string `""`. For example the `vue` flag in `?vue&type=style` becomes the entry `vue: ""`.
- A parameter written as `name=` (equals sign present but nothing after it) also maps to `""`.
- Parameter names and values are percent-decoded (as in standard URL query decoding), and `+` in a value is treated as a space. For example `?msg=hello+world` yields `msg: "hello world"`, and `?path=a%2Fb` yields `path: "a/b"`.
- When the same parameter name appears more than once, the value from the **last** occurrence wins.

### Edge cases

- A url with no `?` at all returns an empty object `{}`.
- A url whose only postfix is a hash (e.g. `./a.js#section`) returns an empty object `{}`.
- A url ending in a bare `?` with nothing after it (e.g. `./a.js?`) returns an empty object `{}`.
- An empty segment between separators (e.g. a trailing or doubled `&`, as in `?a=1&&b=2` or `?a=1&`) must be skipped and must not create an empty-named key.
- The returned object must contain only the parsed parameters — no inherited or prototype keys.

### Expected Functionality

| Input | Output |
|-------|--------|
| `./Comp.vue?vue&type=style&index=0` | `{ vue: "", type: "style", index: "0" }` |
| `./a.js?raw#L10` | `{ raw: "" }` |
| `./a.js#frag` | `{}` |
| `./a.js` | `{}` |
| `./a.js?` | `{}` |
| `./a.js?msg=hello+world` | `{ msg: "hello world" }` |
| `./a.js?path=a%2Fb` | `{ path: "a/b" }` |
| `./a.js?x=1&x=2` | `{ x: "2" }` |
| `./a.js?a=1&&b=2` | `{ a: "1", b: "2" }` |

## Acceptance Criteria

- `parseRequestQuery` is exported from `packages/vite/src/node/utils.ts` with the signature above.
- The new test file `packages/vite/src/node/__tests__/parseRequestQuery.spec.ts` imports `parseRequestQuery` from `../utils`, contains at least 10 assertions, and covers: a multi-parameter query mixing flags and `name=value`, a query followed by a hash, a hash-only url, a no-query url, a bare-`?` url, percent-decoding, `+`-as-space decoding, duplicate-key last-wins, and empty-segment skipping.
- Every test in the new file passes when run from the repo root:

```
pnpm exec vitest run packages/vite/src/node/__tests__/parseRequestQuery.spec.ts
```

- A naive implementation (e.g. ignoring the hash boundary, not decoding values, treating bare flags as `undefined`, or letting the first duplicate win) must fail at least one assertion.
