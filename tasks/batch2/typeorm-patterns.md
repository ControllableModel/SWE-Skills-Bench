# Task: Build a Blog Tagging Persistence Layer

## Background

The TypeORM repository (`typeorm/typeorm`) verifies the ORM end-to-end with functional tests under `test/functional/` that run against an in-memory SQLite database via the repo's own public API. This task adds a self-contained "blog tagging" feature whose persistence behavior must be exercised through that API.

## Files to Create/Modify

- `test/functional/blog-tagging/entity/Article.ts` (new) — the article record type.
- `test/functional/blog-tagging/entity/Tag.ts` (new) — the tag record type.
- `test/functional/blog-tagging/tag-service.ts` (new) — a service constructed from a `DataSource` exposing the operations below.
- `test/functional/blog-tagging/blog-tagging.test.ts` (new) — the functional test that wires the entities into a testing `DataSource` and verifies every requirement.

Follow the existing conventions in `test/functional/` (see `test/functional/custom-repository/custom-repository.test.ts` and `test/functional/custom-repository/entity/User.ts`): import decorators/types from the repo's own `src/` via relative paths, use `createTestingConnections`, `reloadTestingDatabases`, and `closeTestingConnections` from `../../utils/test-utils`, and assert with `chai`.

## Requirements

### Domain model

An **Article** has a database-generated numeric identity and a `title` string. A **Tag** has a database-generated numeric identity and a `name` string that must be unique across all tags. An article may carry many tags and a tag may apply to many articles; the same tag instance must be shareable by multiple articles rather than duplicated per article. The association between articles and tags must be stored in a dedicated junction table, and the same `(article, tag)` pair must never be stored twice.

### Tag service

`tag-service.ts` must export a class (or factory) built from a `DataSource` providing at least:

- **createArticleWithTags(title, tagNames)** — persists a new article and ensures each named tag exists (reusing any tag whose name already exists rather than creating a duplicate), associating all of them with the article; returns the saved article including its generated id.
- **getArticleTags(articleId)** — returns the article's tags retrieved in a single database round trip (not one query per tag); returns `null` when the article does not exist.
- **articlesForTag(tagName)** — returns every article that carries the given tag, ordered by article id ascending; returns an empty list when the tag is unknown.
- **mostUsedTags(limit)** — returns up to `limit` tags ordered by the number of articles using each tag (descending), where the usage count is computed by the database, not by loading associations into memory and counting in JavaScript.

### Constraints

- The test must run without any external database server: enable only the SQLite-based driver(s) when creating the testing connections.
- The schema must be derived from the record-type definitions by the ORM during test setup; no hand-written `CREATE TABLE` SQL.
- Inserting an article with a tag name that already exists must not create a second `Tag` row with that name.

### Expected Functionality

- Creating two articles that share a tag name → only one `Tag` row exists for that name and both articles reference it.
- `getArticleTags` on an article with three tags → returns exactly those three tags.
- `articlesForTag` for a tag used by two articles → returns exactly those two articles ordered by id.
- `mostUsedTags(2)` over a dataset where tags have differing usage → returns exactly the two most-used tags in descending usage order.
- `getArticleTags(<missing id>)` → returns `null`.

## Acceptance Criteria

- The four files exist under `test/functional/blog-tagging/`; entities and service are imported by the test from the repo's own `src/` and `utils`.
- All scenarios in **Expected Functionality** are asserted and pass against the SQLite driver.
- A naive implementation that duplicates tags by name, that issues one query per tag, or that counts tag usage in JavaScript instead of via a database aggregate, must fail at least one assertion.
- The test compiles and passes. From the repo root:

```bash
pnpm run compile && npx mocha ./build/compiled/test/functional/blog-tagging/blog-tagging.test.js
```
