# Task: Build a Recoverable Document Trash Layer

## Background

The TypeORM repository (`typeorm/typeorm`) exercises the ORM end-to-end with functional tests under `test/functional/` that run against an in-memory SQLite database via the repo's own public API. This task adds a self-contained "document trash" feature where records can be discarded and later restored, verified through that API.

## Files to Create/Modify

- `test/functional/document-trash/entity/Document.ts` (new) — the document record type.
- `test/functional/document-trash/trash-service.ts` (new) — a service constructed from a `DataSource` exposing the operations below.
- `test/functional/document-trash/document-trash.test.ts` (new) — the functional test that wires the entity into a testing `DataSource` and verifies every requirement.

Follow the existing conventions in `test/functional/` (see `test/functional/custom-repository/custom-repository.test.ts` and `test/functional/custom-repository/entity/User.ts`): import decorators/types from the repo's own `src/` via relative paths, use `createTestingConnections`, `reloadTestingDatabases`, and `closeTestingConnections` from `../../utils/test-utils`, and assert with `chai`.

## Requirements

### Domain model

A **Document** has a database-generated numeric identity, a `title` string, a `body` text field, and timestamps for when it was created and last modified that the ORM maintains automatically. A document may be discarded such that it stops appearing in ordinary listings yet its row is retained in the database and can be restored later; the moment it was discarded must be recorded automatically and become empty again once restored.

### Trash service

`trash-service.ts` must export a class (or factory) built from a `DataSource` providing at least:

- **create(title, body)** — persists a new active document and returns it with its generated id and creation timestamp populated.
- **listActive()** — returns all documents that are not currently discarded, excluding discarded ones automatically (the caller does not pass any "not discarded" filter).
- **discard(id)** — marks the document as discarded without physically deleting the row; afterwards it must not appear in `listActive()`.
- **listTrashed()** — returns only the documents currently discarded.
- **restore(id)** — reverses a discard so the document reappears in `listActive()` and disappears from `listTrashed()`.
- **purge(id)** — permanently removes the row so it can no longer be retrieved by any of the above, even including discarded ones.

### Constraints

- The test must run without any external database server: enable only the SQLite-based driver(s) when creating the testing connections.
- The schema must be derived from the record-type definition by the ORM during test setup; no hand-written `CREATE TABLE` SQL.
- A discarded document's row must still physically exist after `discard` (verifiable by a query that explicitly includes discarded rows), and its discard timestamp must be set; after `restore` that timestamp must be cleared.

### Expected Functionality

- Creating three documents then discarding one → `listActive()` returns two, `listTrashed()` returns one.
- Discarding then restoring a document → it returns to `listActive()` and leaves `listTrashed()`.
- After `discard`, a query that explicitly includes discarded rows still finds the document (the row was not physically deleted).
- After `purge`, no query (including one that includes discarded rows) can retrieve the document.
- A freshly created document has its creation timestamp set and an empty discard timestamp.

## Acceptance Criteria

- The three files exist under `test/functional/document-trash/`; entity and service are imported by the test from the repo's own `src/` and `utils`.
- All scenarios in **Expected Functionality** are asserted and pass against the SQLite driver.
- An implementation that physically deletes rows on `discard`, or that fails to auto-exclude discarded rows from ordinary listings, must fail at least one assertion.
- The test compiles and passes. From the repo root:

```bash
pnpm run compile && npx mocha ./build/compiled/test/functional/document-trash/document-trash.test.js
```
