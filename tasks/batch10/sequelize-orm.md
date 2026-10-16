# Task: Implement Soft-Deletable Documents

## Background
This is the [Sequelize](https://github.com/sequelize/sequelize) monorepo. Inside the `@sequelize/core` package's integration-test tree we need a "document" model that supports soft deletion (rows are hidden, not physically removed) together with helper functions to archive, restore, and list documents. Integration tests in this package run against the default test dialect (an in-memory/file database), so deletion visibility and restoration can be exercised in-process.

## Files to Create/Modify
- `packages/core/test/integration/soft-documents.ts` (new) — the module defining the `Document` model and exporting `setupDocuments(sequelize)`, `archive(Document, id)`, `restore(Document, id)`, `listVisible(Document)`, and `listAll(Document)`.
- `packages/core/test/integration/soft-documents.test.ts` (new) — the integration test that exercises the behavior.

## Requirements

### Module shape
- `setupDocuments(sequelize)` must define and return the `Document` model and create its table.
- The helper functions operate on that model.

### Model
- **Document** — fields: `title` (text, required), `body` (text, optional). The model must record a deletion timestamp when a row is soft-deleted rather than removing the row.

### Behavior
- `archive(Document, id)` must soft-delete the document with the given primary key (mark it deleted without physically removing the row). It must return `true` when a visible document was archived and `false` when no visible document with that id existed.
- `restore(Document, id)` must un-delete a previously soft-deleted document so it becomes visible again. It must return `true` when a deleted document was restored and `false` when no deleted document with that id existed.
- `listVisible(Document)` must return only documents that are NOT soft-deleted, ordered by `title` ascending.
- `listAll(Document)` must return ALL documents including soft-deleted ones, ordered by `title` ascending.
- A normal lookup by primary key (the kind used by `archive` to find a target) must NOT find a soft-deleted row; finding a soft-deleted row (the kind used by `restore`) must explicitly include deleted rows.

### Edge cases and constraints
- After `archive`, the document must be absent from `listVisible` but present in `listAll`.
- After `restore`, the document must reappear in `listVisible`.
- Archiving an already-archived (or non-existent) id must return `false` and change nothing.
- Restoring a never-deleted (or non-existent) id must return `false` and change nothing.
- A naive implementation that physically deletes rows, or that cannot bring a row back, must fail the tests.

### Expected Functionality
- Create three documents; `archive` one -> `listVisible` returns the other two; `listAll` returns all three; the archived one carries a deletion timestamp.
- `restore` the archived document -> it reappears in `listVisible`.
- `archive` a non-existent id -> returns `false`; counts unchanged.
- `restore` an id that was never archived -> returns `false`; counts unchanged.

## Acceptance Criteria
- A new self-contained test `packages/core/test/integration/soft-documents.test.ts` exists and asserts: soft-delete hides from `listVisible` but keeps the row in `listAll` with a deletion timestamp, restore brings it back, the boolean return values of `archive`/`restore` for both hit and miss cases, and that visible-only lookup cannot see a soft-deleted row while include-deleted lookup can.
- The implementation lives in `packages/core/test/integration/soft-documents.ts` and is imported by the test.
- All assertions are objectively verifiable in-process against the default test database (no external server).
- From the `packages/core` directory, the following command runs and passes with no failing tests:

  ```bash
  yarn mocha "test/integration/soft-documents.test.ts"
  ```
