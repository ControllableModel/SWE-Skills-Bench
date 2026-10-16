# Task: Build a Wildcard File-Tree Browser Module

## Background

The `hono` repository ships small, self-contained helper modules under `src/helper/` (for example `src/helper/route/` and `src/helper/ssg/`), each exporting a focused feature plus a colocated `index.test.ts`. This task adds a new helper module that serves a read-only virtual file tree, addressed by arbitrarily deep paths and numeric revision ids.

## Files to Create/Modify

- `src/helper/file-tree/index.ts` (new) — the file-tree browser module.
- `src/helper/file-tree/index.test.ts` (new) — the deterministic test suite for the module.

## Requirements

### Module Surface

The module must export a factory function named `createFileTree(files)` that accepts a mapping from full slash-separated path strings (e.g. `docs/intro.md`) to string contents. Calling it returns a fresh sub-application instance serving a read-only view of that mapping. The returned value must be mountable into a parent application under an arbitrary prefix. Two separate calls hold independent file maps.

### Routes and Behavior

The module must distinguish, by route shape alone, between deep file-path lookups, numeric revision lookups, and a directory listing. The contract must hold both directly and when mounted under a non-empty prefix.

#### Fetching a file by deep path
- A `GET` request to `/files/<deep/path>` where `<deep/path>` is an arbitrarily deep slash-separated path returns `200` with a JSON body `{ "path": <the full path>, "content": <string> }` when that exact path exists in the map.
- A `GET` to `/files/<deep/path>` for a path not present returns `404` with a JSON body `{ "error": <string> }`.

#### Fetching by numeric revision
- A `GET` request to `/rev/:n` where `:n` is purely numeric returns `200` with a JSON body `{ "revision": <number>, "path": <string> }`, treating the revision number as a zero-based index into the file paths in their original insertion order. An out-of-range index returns `404` with `{ "error": <string> }`.
- A `GET` to `/rev/:n` where the segment is not purely numeric must NOT match the revision route; such a request returns `404` as an unmatched route.

#### Listing a directory
- A `GET` request to `/list` with a query parameter `prefix` returns `200` with a JSON body `{ "prefix": <string>, "paths": [...] }` listing every file path that begins with that prefix, in insertion order. When `prefix` is absent, all paths are listed.

### Constraints and Edge Cases

- The deep-path route must capture the entire remaining path including embedded slashes (e.g. `a/b/c.txt`), not just a single segment.
- The numeric-revision route must only match digit-only segments; alphanumeric or empty segments must fall through to an unmatched `404`.
- `prefix` matching is a literal string-prefix test on the full path, case-sensitive.
- The view is read-only; there are no mutating routes. All behavior must be verifiable through in-memory request dispatch (no network, no external services).

### Expected Functionality

- files include `a/b/c.txt`; `GET /files/a/b/c.txt` -> `{ "path": "a/b/c.txt", "content": ... }`.
- `GET /files/a/b/missing` -> `404`.
- `GET /rev/0` -> the first inserted path; `GET /rev/999` -> `404`.
- `GET /rev/abc` -> `404` (unmatched route).
- `GET /list?prefix=a/` -> only paths under `a/`.

## Acceptance Criteria

- `src/helper/file-tree/index.ts` exports `createFileTree`, which returns a value mountable into a parent application, serving a read-only view distinguishing deep-path, numeric-revision, and listing routes by shape.
- All deep-path capture, numeric-revision constraint, listing, status-code, and edge-case behaviors above are satisfied, verified by dispatching in-memory requests against both a directly-used and a mounted instance.
- A naive implementation (e.g. capturing only one path segment, matching non-numeric revision segments, or ignoring the `prefix` filter) must fail the test suite.
- The colocated test suite contains at least 10 distinct test cases and passes with:

```
npx vitest --run src/helper/file-tree/index.test.ts
```
