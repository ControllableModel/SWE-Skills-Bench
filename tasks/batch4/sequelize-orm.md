# Task: Normalize Records Through Lifecycle Callbacks

## Background
This is the [Sequelize](https://github.com/sequelize/sequelize) monorepo. Inside the `@sequelize/core` package's unit-test tree we need a "contact" model whose lifecycle callbacks normalize and derive fields as a record moves through validation and saving. Unit tests in this package run against the default dialect without opening a real database connection, so lifecycle behavior can be observed in-process by building, validating, and saving instances (the default test dialect persists in-memory).

## Files to Create/Modify
- `packages/core/test/unit/model/contact-normalize.ts` (new) — the module defining the `Contact` model and exporting `defineContact(sequelize)`.
- `packages/core/test/unit/model/contact-normalize.test.ts` (new) — the unit test that exercises the callbacks.

## Requirements

### Module shape
- The module must export `defineContact(sequelize)` which defines and returns the `Contact` model on the passed-in `Sequelize` instance.

### Fields
- `email` (text, required, unique).
- `displayName` (text, optional).
- `searchKey` (text, optional) — a derived field.
- `saveCount` (integer) — defaults to `0`.

### Lifecycle behavior
- Before validation runs, `email` must be normalized to lowercase with surrounding whitespace trimmed. As a consequence, an input email of `'  USER@Example.COM  '` must validate and be stored as `'user@example.com'`.
- Before validation runs, if `displayName` is missing or empty, it must be populated from the local part of the (already-normalized) email (the text before the `@`).
- Immediately before a record is persisted, `searchKey` must be set to the normalized email with the `@` and any dots removed (so `'user@example.com'` -> `'userexamplecom'`).
- Each time a record is successfully saved, its `saveCount` must be incremented by exactly one and that increment must be persisted, so saving a brand-new record once yields `saveCount === 1`, and updating-then-saving it again yields `saveCount === 2`.

### Edge cases and constraints
- Email normalization must happen early enough that uniqueness/format validation sees the normalized value.
- `displayName` derivation must only fill in a missing/empty value; an explicitly provided non-empty `displayName` must be left unchanged.
- A naive implementation that hardcodes any of these derived values, or that does not actually run on the lifecycle, must fail the tests.

### Expected Functionality
- Create a contact with `email: '  Mixed@Case.IO '` and no `displayName` -> after creation, `email === 'mixed@case.io'`, `displayName === 'mixed'`, `searchKey === 'mixedcaseio'`, `saveCount === 1`.
- Create a contact with an explicit `displayName: 'Custom'` -> `displayName` remains `'Custom'`.
- Save a created contact a second time after changing a field -> `saveCount === 2`.

## Acceptance Criteria
- A new self-contained unit test `packages/core/test/unit/model/contact-normalize.test.ts` exists and asserts: email normalization, conditional `displayName` derivation, `searchKey` derivation on save, and the per-save `saveCount` increment across two saves.
- The implementation lives in `packages/core/test/unit/model/contact-normalize.ts` and is imported by the test.
- All assertions are objectively verifiable in-process without an external database server.
- From the `packages/core` directory, the following command runs and passes with no failing tests:

  ```bash
  yarn mocha "test/unit/model/contact-normalize.test.ts"
  ```
