# Task: Provide Bidirectional Cursor Pagination Over a Comment Thread

## Background

This is the [Apollo Server](https://github.com/apollographql/apollo-server) monorepo. The `@apollo/server` package (`packages/server`) builds a GraphQL service from `typeDefs` and `resolvers` and executes operations in-process. This task adds a self-contained comment-thread module whose central concern is paging through an ordered list of comments both forward and backward using opaque cursors.

## Files to Create/Modify

- `packages/server/src/examples/commentThread.ts` (new) — exports `typeDefs` (a GraphQL SDL string), `resolvers`, and an in-memory data store factory for a thread-of-comments domain. Importable on its own; must not import from any other example file.
- `packages/server/src/__tests__/examples/commentThread.test.ts` (new) — a Jest suite building an `ApolloServer` and asserting through `executeOperation`.

Do **not** modify the package's public `index.ts` exports.

## Requirements

### Domain

The module serves a single **thread** containing an ordered list of **comments**. Each comment has a stable identifier, an author handle, and a body. The thread's comment order is fixed and deterministic. The store seeds a deterministic, fixed sequence of comments (no randomness, time, or I/O).

### Paged comment access

The root query exposes a field returning the thread's comments as a **page**. A page request supplies a count and an opaque cursor, and supports paging in **both directions**:

- forward: "give me the first N after this cursor."
- backward: "give me the last N before this cursor."

The page response carries, per returned comment, an opaque cursor, plus page metadata reporting whether more comments exist before the page, whether more exist after it, and the boundary cursors of the page. Cursors are opaque to the client (the client must never parse them). Paging forward in fixed-size pages from the start visits every comment exactly once with no duplicates or omissions and the final page reports no further comments after it. Paging backward from the end likewise visits every comment exactly once in reverse and the final page reports no further comments before it.

A cursor obtained while paging forward must be usable to page backward from that point and land on the expected neighbors (the directions are consistent over the same ordering).

### A page also reports the total

The page response exposes the total number of comments in the thread (independent of the current page window), discoverable alongside the page items.

### Nullability and list contracts

The list of returned comments and the per-comment cursor list never resolve to null and never contain null entries. A comment's identifier, author handle, and body are always present (never null). An empty page (e.g. paging past the end) yields an empty item list, not null, with page metadata reporting no further comments in that direction.

### Expected Functionality

- Page forward from the start in pages of size 2 -> concatenating pages reproduces the full ordered comment id sequence exactly once each; the last page reports no more after it.
- Page backward from the end in pages of size 2 -> reproduces the reversed sequence exactly once each; the last page reports no more before it.
- Take a cursor from a forward page, then page backward from it -> lands on the expected preceding comments.
- Page past the end -> empty item list (not null) and metadata showing no further comments after.
- Read the total count -> equals the seeded comment count regardless of the page window.

## Acceptance Criteria

- `packages/server/src/examples/commentThread.ts` exports `typeDefs` (string SDL), `resolvers`, and a fresh-store factory; deterministic, no external dependencies.
- An `ApolloServer` built from the module starts successfully.
- Forward and backward paging both use opaque cursors, traverse the whole thread without duplicates or omissions, and report direction-appropriate "more before / more after" metadata; a forward cursor is consistently usable for backward paging.
- The new suite contains at least 10 `it`/`test` cases covering: full forward traversal, full backward traversal, cross-direction cursor reuse, empty page past the end, total-count independence from the window, per-page boundary-cursor metadata, and non-null list/cursor contracts.
- The following command, run from the repository root, passes with all assertions green:

  ```
  npx jest packages/server/src/__tests__/examples/commentThread.test.ts --verbose
  ```
