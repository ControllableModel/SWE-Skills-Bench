# Task: Add a Bracket-Balance Checker to the REPL Package

## Background

The `internal/repl` package powers `terraform console`. It already has `ExpressionEntryCouldContinue`, which decides whether a multi-line entry is still open. It lacks a reusable, self-contained helper that reports the precise bracket-balance state of a snippet — useful for deciding prompt continuation and for diagnosing mismatched delimiters. This task adds a deterministic, self-contained checker.

## Files to Create/Modify

- `internal/repl/brackets.go` (new) — a self-contained helper in package `repl`.
- `internal/repl/brackets_test.go` (new) — the deterministic test for the new helper.

The new code must live in the existing `repl` package and must not perform any I/O or use randomness.

## Requirements

### `CheckBracketBalance`

Add an exported type and function:

```go
type BracketBalance struct {
    Open    int  // count of brackets still open at end of input
    Balanced bool // true iff every opener is matched and none closed too early
}

func CheckBracketBalance(src string) BracketBalance
```

It scans `src` once and tracks the three bracket pairs `()`, `[]`, and `{}`.

Behavior and constraints:

- Openers are `(`, `[`, `{`; closers are `)`, `]`, `}`. A closer must match the most recent unmatched opener of the **same** kind (proper nesting). A mismatched closer (e.g. `]` while the innermost open is `(`) makes the input unbalanced.
- A closer with no matching opener (e.g. leading `)`) makes the input unbalanced and must not drive the open count negative — `Open` is never negative.
- `Open` is the number of brackets still unclosed when scanning finishes (the depth of the remaining open stack). `Balanced` is `true` iff scanning encountered no mismatched/unmatched closer **and** `Open == 0` at the end.
- Brackets inside **double-quoted string literals** are ignored. A `"` toggles in/out of a string; a `\"` (backslash-escaped quote) inside a string does not end the string. Brackets while inside a string never affect the counts.
- Characters other than brackets, quotes, and the escape handling above are ignored.
- An empty string is balanced with `Open == 0`.
- The function must be deterministic.

### Expected Functionality

- `"foo(bar[1])"` -> `{Open:0, Balanced:true}`.
- `"foo(bar"` -> `{Open:1, Balanced:false}`.
- `"a]b"` (closer with no opener) -> `{Balanced:false, Open:0}` (open count never negative).
- `"([)]"` (improper nesting) -> `Balanced:false`.
- `"x = \"(]{\""` (brackets only inside a string) -> `{Open:0, Balanced:true}`.

## Acceptance Criteria

The new test file `internal/repl/brackets_test.go` must exercise `CheckBracketBalance` using `github.com/stretchr/testify` (the project already depends on it) and must cover, at minimum:

- a fully balanced nested snippet (`Balanced:true`, `Open:0`);
- an unclosed snippet reporting the correct positive `Open` and `Balanced:false`;
- a stray closer keeping `Open` at `0` (never negative) and `Balanced:false`;
- improperly nested brackets (`([)]`) reported as unbalanced;
- brackets inside a double-quoted string (including an escaped `\"`) being ignored;
- the empty string being balanced with `Open == 0`.

The following command, run from the repository root, must pass:

```
go test ./internal/repl/ -run TestCheckBracketBalance -v
```
