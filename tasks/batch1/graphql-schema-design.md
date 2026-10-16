# Task: Build a Library Catalog GraphQL API Module

## Background

This is the [Apollo Server](https://github.com/apollographql/apollo-server) monorepo. The `@apollo/server` package (`packages/server`) lets applications stand up a GraphQL service from `typeDefs` and `resolvers` and execute operations in-process via `new ApolloServer(...).executeOperation(...)`. This task adds a small, self-contained example feature module — a library catalog API — that ships inside the server package's source tree so it can be exercised by the package's existing Jest test harness.

## Files to Create/Modify

- `packages/server/src/examples/libraryCatalog.ts` (new) — exports `typeDefs` (a GraphQL SDL string), `resolvers`, and an in-memory data store factory for a library catalog domain (books and authors). This module must be importable on its own and must not import from any other example file.
- `packages/server/src/__tests__/examples/libraryCatalog.test.ts` (new) — the Jest test suite that builds an `ApolloServer` from the module's `typeDefs`/`resolvers` and asserts behavior through `executeOperation`.

Do **not** modify the existing public `index.ts` exports; the module is internal to the package's source and is consumed only by the new test.

## Requirements

### Domain

The catalog manages two kinds of entities: **books** and **authors**. Every entity has a stable, server-assigned identifier that is distinct from any human-readable field (a book's title or an author's name is not its identifier). The data store factory seeds a deterministic, fixed set of authors and books so that every test run sees identical data without randomness, time, or external I/O.

A book belongs to exactly one author. An author has zero or more books. A book also carries a publication year, a reading status, and an optional short summary.

### Reading status

Each book has a reading status that may take exactly one of three values: not started, in progress, or finished. A request that supplies any other status value (for filtering or for a mutation) must be rejected by the server before any resolver runs — i.e. the operation must fail validation rather than return a resolver-level result. The set of permitted values must be discoverable through GraphQL introspection.

### Querying the catalog

The root query must expose:

1. A way to fetch a single book by its identifier. Fetching a non-existent identifier must yield an absent book (the field resolves to nothing) rather than an execution error.
2. A way to fetch a single author by its identifier, with the same absent-on-miss behavior.
3. A way to list books with **forward pagination**: callers pass a page size and an optional opaque cursor, and receive back a page of books, one opaque cursor per returned book, and page metadata indicating whether more books follow and the cursor to resume from. Cursors are opaque to the client (clients must not need to parse them) and paging through the whole catalog in fixed-size pages must visit every book exactly once with no duplicates and no omissions. The list may optionally be filtered by reading status; when no status filter is given, all books are listed.

When a book is returned, its author must be resolvable as a nested object (not merely an author identifier), and an author's books must be resolvable as a nested list.

### Mutations

Provide a mutation that adds a new book to the catalog. The mutation accepts its arguments as a **single structured argument** (not a flat list of many separate scalar arguments). The new book requires a title, a publication year, and the identifier of an existing author; the summary is optional, and the reading status defaults to "not started" when the caller omits it.

The mutation must report success and failure through its return value rather than only through top-level GraphQL errors:

- Adding a book that references an existing author succeeds and the response carries the newly created book, including its freshly assigned identifier, which must not collide with any existing identifier.
- Adding a book that references a non-existent author is a recoverable, expected outcome: the response must distinguish this case so a client can tell "author not found" apart from a successful creation, by inspecting the shape/contents of the returned data — without relying on the GraphQL `errors` array.

### Nullability and list contracts

The schema's nullability must be intentional and verifiable through introspection:

- Identifier fields, a book's title, a book's publication year, a book's reading status, and an author's name are always present (never null).
- A book's summary is optional and may be absent.
- List-valued fields (such as an author's books and the items within a page of books) never resolve to null and never contain null entries; an author with no books yields an empty list, not null.

### Expected Functionality

- Query a known book by id -> returns that book with correct title, year, status, and a nested author whose name matches the seed data.
- Query an unknown book id -> the `book` field is `null`, and no execution error is raised.
- List books in pages of size 2 across the whole catalog -> concatenating the pages reproduces the full set of book ids exactly once each; the final page reports that no more books follow.
- List books filtered by `FINISHED` -> only finished books appear.
- Filter or mutate with an invalid status string -> the operation fails validation (a non-empty `errors` array, no `data` for that field) without invoking resolvers.
- Add a book for an existing author with no status supplied -> succeeds, the returned book has status "not started", a non-empty id distinct from all seeded ids, and subsequently fetching that id returns the same book.
- Add a book for a missing author id -> the mutation result indicates the author-not-found case via its returned payload, and the top-level `errors` array is empty.

## Acceptance Criteria

- `packages/server/src/examples/libraryCatalog.ts` exports `typeDefs` (string SDL), `resolvers`, and a factory that produces a fresh in-memory store, with no dependency on network, filesystem, timers, or randomness; repeated runs are deterministic.
- An `ApolloServer` constructed from the module's `typeDefs` and `resolvers` starts successfully (the SDL is valid and resolvers are consistent with it).
- The new test suite `packages/server/src/__tests__/examples/libraryCatalog.test.ts` contains at least 10 `it`/`test` cases covering: single fetch hit and miss for both entities, nested author/books resolution, full pagination traversal with no duplicates/omissions, status filtering, the introspectable fixed status value set, invalid-status validation failure, default-status creation, id uniqueness of created books, and the author-not-found mutation outcome distinguished from success without using the top-level `errors` array.
- Reading-status validation failures surface as GraphQL validation errors (populated `errors`, absent `data` for that field), demonstrably before resolvers execute.
- The following command, run from `packages/server`, passes with all assertions green:

  ```
  npx jest src/__tests__/examples/libraryCatalog.test.ts --verbose
  ```
