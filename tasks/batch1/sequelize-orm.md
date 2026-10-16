# Task: Build a Library Catalog Domain Model

## Background
This is the [Sequelize](https://github.com/sequelize/sequelize) monorepo. Inside the `@sequelize/core` package's unit-test tree, we need a small in-memory "library catalog" domain module that defines its models and relationships against the shared test `Sequelize` instance, so that downstream code can query authors, books, and their tags consistently. Unit tests in this package run against the default dialect without opening a real database connection, so model definitions, relationships, validations, and named query presets can all be exercised in-process.

## Files to Create/Modify
- `packages/core/test/unit/model/library-catalog.ts` (new) — the domain module that defines and wires up the three models described below and exports a factory.
- `packages/core/test/unit/model/library-catalog.test.ts` (new) — the unit test that exercises the module's behavior.

## Requirements

### Module shape
- The new module must export a single function `defineLibraryCatalog(sequelize)` that accepts a `Sequelize` instance, defines the models and their relationships on it, and returns an object `{ Author, Book, Tag }` holding the three defined model classes.
- All three models must be defined on the passed-in `sequelize` instance only. Calling `defineLibraryCatalog` on a fresh instance must not depend on, or leak into, any other instance.

### Models and fields
- **Author** — fields: `name` (text, required) and `email` (text, required, must be unique). An author with a missing or empty `name` must fail validation. An author whose `email` is not a syntactically valid email address must fail validation, and the produced validation error for that field must carry the message text `must be a valid email`.
- **Book** — fields: `title` (text, required) and `pageCount` (integer, required). A book with a `pageCount` below `1` must fail validation, and the produced validation error for that field must carry the message text `pageCount must be at least 1`. A book with `pageCount` of `1` or greater must pass validation.
- **Tag** — fields: `label` (text, required, must be unique).

### Relationships
- Each **Book** belongs to exactly one **Author**, and each **Author** may have many **Books**. The reverse navigation from an author to its books must be reachable under the accessor name `books`, and from a book to its author under the accessor name `author`. The foreign key that links a book to its author must be the column `authorId`.
- A **Book** may carry many **Tags** and a **Tag** may apply to many **Books**, linked through a junction relation named `BookTags`. The books reachable from a tag must use the accessor name `books`, and the tags reachable from a book must use the accessor name `tags`.

### Named query preset
- The **Book** model must expose a reusable named query preset called `published` that, when applied, restricts results to books whose `published` attribute is truthy. (Add a `published` boolean field to **Book** to support this; books default to not published.)
- Applying the `published` preset must not mutate the base model: the base `Book` must still query without any such restriction, while the preset-applied variant must include the `published = true` restriction in its effective query options.

### Edge cases and constraints
- `defineLibraryCatalog` must be idempotent with respect to separate instances: two different `Sequelize` instances passed in separate calls must each receive a fully independent set of models.
- Validation must be triggerable in-process (i.e., without persisting), so that building a model instance and validating it surfaces the field errors described above.
- A naive implementation that hardcodes return values or skips wiring the relationships/validations/preset must fail the tests.

### Expected Functionality
- Building an `Author` with `name: ''` and validating it -> rejects with a validation error on `name`.
- Building an `Author` with `email: 'not-an-email'` and validating it -> rejects with a validation error whose message includes `must be a valid email`.
- Building a `Book` with `pageCount: 0` and validating it -> rejects with a validation error whose message includes `pageCount must be at least 1`.
- Building a `Book` with `pageCount: 200` and otherwise valid fields and validating it -> resolves.
- Inspecting the defined relationships -> `Author` has a `books` association targeting `Book` with foreign key `authorId`; `Book` has an `author` association targeting `Author`; `Book` has a `tags` association and `Tag` has a `books` association, both routed through the `BookTags` junction.
- The base `Book` query options carry no `published` restriction, while the `published`-preset variant's query options restrict `published` to a truthy value.

## Acceptance Criteria
- A new, self-contained unit test file `packages/core/test/unit/model/library-catalog.test.ts` exists and exercises: required/format/range validations (including the exact message texts above), the author↔book and book↔tag relationships (accessor names and foreign key), and the base-vs-`published` query-preset distinction.
- The implementation lives in `packages/core/test/unit/model/library-catalog.ts` and is imported by the test.
- All assertions are objectively verifiable in-process without a live database server.
- From the `packages/core` directory, the following command runs and passes with no failing tests:

  ```bash
  yarn mocha "test/unit/model/library-catalog.test.ts"
  ```
