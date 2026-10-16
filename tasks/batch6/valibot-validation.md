# Task: Build a Nested Comment Tree Validation Module

## Background

This repository (`fabian-hiller/valibot`) is the Valibot schema library, with its full public API exported from `library/src/index.ts`. We need a self-contained module that validates an arbitrarily deep comment thread, where each comment can contain a list of child comments of the exact same shape.

## Files to Create/Modify

- `library/src/commentTree/commentTree.ts` (new) — the validation function and the recursive schema.
- `library/src/commentTree/index.ts` (new) — re-export the public surface of the module.
- `library/src/commentTree/commentTree.test.ts` (new) — the deterministic test suite described below.

Build the module using the library's own public API by importing from the package source root, e.g. `import * as v from '../index.ts';`. Do not add new third-party dependencies.

## Requirements

Implement and export a function `parseComment(input: unknown)` plus the recursive schema and the inferred `Comment` type. The function returns the validated comment directly and throws on invalid input.

### Recursive node shape

Each comment node has:

- `id` — string, non-empty (required).
- `author` — string; trimmed; non-empty after trimming (required).
- `text` — string with length between 1 and 500 inclusive after trimming both ends (required; the output value is the trimmed text).
- `replies` — an array of comment nodes of the same shape (optional). When absent, the output must contain `replies: []`. Each element is validated recursively to arbitrary depth.

Unknown extra keys at any node must be stripped from the output.

### Output shape

The output mirrors the input tree with `author`/`text` trimmed and `replies` defaulted to `[]` at every node where it was absent. The recursive structure and ordering are preserved.

### Expected Functionality

- A leaf `{ id: "1", author: "Ada", text: "hi" }` -> `{ id: "1", author: "Ada", text: "hi", replies: [] }`.
- A node with two nested levels of `replies` validates successfully and the nested defaults/trimming apply at every level.
- `{ id: "1", author: "  Bo  ", text: "  hey  " }` -> `author === "Bo"`, `text === "hey"`.
- A node whose `replies` contains one valid child and one child missing `text` -> throws.
- `{ id: "", author: "x", text: "y" }` -> throws (empty id).
- `{ id: "1", author: "   ", text: "y" }` -> throws (empty author after trim).
- `{ id: "1", author: "x", text: "" }` -> throws (text too short).
- A node whose `text` exceeds 500 characters -> throws.
- A deeply nested tree (e.g. 5 levels) with one invalid node at the deepest level -> throws.
- `null`, `42`, `[]` -> throws.

## Acceptance Criteria

- A module exists at `library/src/commentTree/commentTree.ts` exporting `parseComment`, the recursive schema, and the `Comment` type.
- The schema validates nodes recursively to arbitrary depth; an invalid node anywhere in the tree causes the whole parse to throw.
- `author` and `text` are trimmed in the output, `text` length is bounded to 1..500 after trimming, and `replies` defaults to `[]` at every node where it was absent.
- Unknown keys are stripped at every node.
- The added test suite contains at least 10 distinct test cases covering: a leaf node with `replies` defaulting, a multi-level valid tree, trimming of `author`/`text`, the empty-`id`/empty-`author`/empty-`text` rejections, the over-length `text` rejection, an invalid deeply-nested child causing a throw, unknown-key stripping at a nested node, and non-object inputs.
- The following command, run from the `library/` directory, passes with all tests green:

```bash
npx vitest run src/commentTree/commentTree.test.ts
```
