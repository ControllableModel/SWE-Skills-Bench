# Task: Add a dotenv-style single-line parser

## Background

Vite loads environment variables for builds; alongside the existing env handling under `packages/vite/src/node/env.ts`, it is useful to have a small, pure parser for a single `KEY=VALUE` line that understands quoting and inline comments. This task adds that parser to the node utilities and a dedicated test suite.

## Files to Create/Modify

- `packages/vite/src/node/utils.ts` (modify) — add and export a new function `parseEnvLine`.
- `packages/vite/src/node/__tests__/parseEnvLine.spec.ts` (new) — a dedicated test file exercising the new function.

## Requirements

### Function signature

Add an exported function:

```ts
export function parseEnvLine(line: string): { key: string; value: string } | null
```

It parses one line of dotenv-style input and returns the key/value pair, or `null` when the line carries no assignment.

### Parsing behavior

- A valid line has the form `KEY=VALUE`. The key is the text before the first `=`, trimmed of surrounding whitespace; the value is everything after the first `=`, processed as below.
- Leading and trailing whitespace around the raw value is trimmed before further processing.
- If the trimmed value is wrapped in matching double quotes (`"..."`) or single quotes (`'...'`), the surrounding quotes are removed and the inner text is used verbatim (no trimming inside the quotes).
- For an **unquoted** value, an inline comment introduced by ` #` (a `#` preceded by whitespace) and everything after it is discarded, and the remaining value is right-trimmed. A `#` with no preceding whitespace is part of the value.
- For a **quoted** value, a `#` inside the quotes is literal and never treated as a comment.
- Inside a double-quoted value, the escape sequence `\n` is converted to a real newline character. Single-quoted values are taken literally with no escape processing.

### Edge cases

- A blank line, a whitespace-only line, or a line whose first non-whitespace character is `#` (a full-line comment) returns `null`.
- A line with no `=` returns `null`.
- `KEY=` (empty value) returns `{ key: "KEY", value: "" }`.
- Surrounding whitespace around the key (e.g. `  KEY = value`) is trimmed from the key.
- A value containing an `=` (e.g. `KEY=a=b`) keeps everything after the first `=` (`value` is `"a=b"`).

### Expected Functionality

| Input | Output |
|-------|--------|
| `FOO=bar` | `{ key: "FOO", value: "bar" }` |
| `  FOO = bar ` | `{ key: "FOO", value: "bar" }` |
| `FOO="bar baz"` | `{ key: "FOO", value: "bar baz" }` |
| `FOO=bar # comment` | `{ key: "FOO", value: "bar" }` |
| `FOO="a # b"` | `{ key: "FOO", value: "a # b" }` |
| `FOO="line\nbreak"` | `{ key: "FOO", value: "line\nbreak" }` (real newline) |
| `FOO=` | `{ key: "FOO", value: "" }` |
| `# whole line` | `null` |
| `noequals` | `null` |

## Acceptance Criteria

- `parseEnvLine` is exported from `packages/vite/src/node/utils.ts` with the signature above.
- The new test file imports `parseEnvLine` from `../utils`, contains at least 10 assertions, and covers every row above plus: a single-quoted value with a literal `#`, and a value containing an `=`.
- Every test passes when run from the repo root:

```
pnpm exec vitest run packages/vite/src/node/__tests__/parseEnvLine.spec.ts
```

- A naive implementation (splitting on every `=`, stripping all `#`, not handling quotes, or not decoding `\n` in double quotes) must fail at least one assertion.
