# Task: Build a Library Catalog Persistence Layer

## Background

The TypeORM repository (`typeorm/typeorm`) contains an extensive functional test suite under `test/functional/` that exercises the ORM against real (in-memory SQLite) databases. This task adds a new self-contained functional test feature, a small "library catalog" domain whose persistence behavior must be verified end-to-end through the public TypeORM API.

## Files to Create/Modify

- `test/functional/library-catalog/entity/Author.ts` (new) — the author record type.
- `test/functional/library-catalog/entity/Book.ts` (new) — the book record type, owned by an author.
- `test/functional/library-catalog/catalog-service.ts` (new) — a small service/helper module exposing the catalog operations described below, built on top of a `DataSource`.
- `test/functional/library-catalog/library-catalog.test.ts` (new) — the functional test that wires the entities into a testing `DataSource` and verifies every requirement below.

Follow the existing conventions in `test/functional/` (see `test/functional/custom-repository/custom-repository.test.ts` and `test/functional/custom-repository/entity/User.ts`): import decorators/types from the repo's own `src/` via relative paths, use `createTestingConnections`, `reloadTestingDatabases`, and `closeTestingConnections` from `../../utils/test-utils`, and assert with `chai`.

## Requirements

### Domain model

An **Author** has a numeric, database-generated identity, a `name` string, and a `country` string. An author owns zero or more **Books**.

A **Book** has a numeric, database-generated identity, a `title` string, a published `year` (integer), a `genre` string, and a `copiesSold` integer that defaults to `0` when not supplied at insert time. Every book belongs to exactly one author. The book table must carry the foreign key to its owning author; deleting an author must remove that author's books at the database level (not only in application memory).

Both record types must be usable as ordinary persisted records through a `DataSource`: saving an author together with new books in a single save call must persist the author and all of its books, with each book's owning-author linkage stored correctly.

### Catalog service

`catalog-service.ts` must export a class (or factory) constructed from a `DataSource` that provides at least the following operations. None may issue one query per book in a loop, the relation data must be retrieved in a single round trip where a relation is needed.

- **addAuthorWithBooks(name, country, books)** — persists a brand-new author and the supplied books in one operation, returning the saved author including the generated ids of the author and each book.
- **findAuthorWithBooks(authorId)** — returns the author and, attached to it, the full list of that author's books; returns `null` (not a throw) when no such author exists.
- **topSellingBooks(limit)** — returns up to `limit` books across all authors, ordered by `copiesSold` descending; ties may break in any order, but the list must never exceed `limit` and must be globally ordered, not per-author.
- **genreRevenueReport()** — returns one aggregate row per genre, where each row reports the genre and the total `copiesSold` summed across every book of that genre. The result must be computed by the database, not by loading all books into memory and summing in JavaScript. Genres with no books must not appear.
- **removeAuthor(authorId)** — deletes the author; afterwards neither the author nor any of its books may remain retrievable.

### Constraints

- The test must run without any external database server. Restrict the testing connections to the in-memory/file SQLite driver family only (i.e. enable only the SQLite-based driver(s) when creating the testing connections) so the suite is fully deterministic and self-contained.
- Do not use `synchronize`-free manual SQL or hand-written `CREATE TABLE` statements, the schema must be derived from the record-type definitions by the ORM during test setup.
- `copiesSold` must come back as `0` for a book inserted without specifying it.

### Expected Functionality

- Saving an author with three books, then re-reading that author by id → the re-read author exposes exactly those three books, each with a generated id and the correct owning author.
- Inserting a book without `copiesSold` → reading it back yields `copiesSold === 0`.
- Across several authors and books, `topSellingBooks(3)` → returns exactly 3 books and they are the three highest `copiesSold` values overall, in descending order.
- `genreRevenueReport()` over a mixed dataset → returns one row per distinct genre with the correct summed `copiesSold`, and the sum equals the JavaScript-side total for that genre.
- `findAuthorWithBooks(<missing id>)` → returns `null`.
- `removeAuthor(id)` on an author that has books → afterwards `findAuthorWithBooks(id)` returns `null` and a direct query for that author's books returns an empty set.

## Acceptance Criteria

- The four files above exist under `test/functional/library-catalog/` and the entities/service are imported by the test from the repo's own `src/` and `utils`.
- All scenarios in **Expected Functionality** are asserted in `library-catalog.test.ts` and pass against the SQLite driver.
- A naive implementation that loops issuing per-book queries, that sums revenue in JavaScript instead of via a database aggregate, or that fails to cascade book deletion at the database level, must fail at least one assertion.
- The test compiles and passes. The following command, run from the repo root, must succeed:

```bash
pnpm run compile && npx mocha ./build/compiled/test/functional/library-catalog/library-catalog.test.js
```

(Equivalently, after compilation the test is collected by the default `pnpm run test:fast` mocha run with no failures and no leaked connections.)
