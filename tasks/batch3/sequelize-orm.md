# Task: Enforce Account Field Constraints

## Background
This is the [Sequelize](https://github.com/sequelize/sequelize) monorepo. Inside the `@sequelize/core` package's unit-test tree we need a self-contained "account" model whose fields enforce a set of business rules at the model layer. Unit tests in this package run against the default dialect without opening a real database connection, so validation can be triggered in-process by building an instance and validating it without persisting.

## Files to Create/Modify
- `packages/core/test/unit/model/account-rules.ts` (new) — the module defining the `Account` model and exporting a factory `defineAccount(sequelize)`.
- `packages/core/test/unit/model/account-rules.test.ts` (new) — the unit test that exercises the rules.

## Requirements

### Module shape
- The module must export `defineAccount(sequelize)` which defines and returns the `Account` model on the passed-in `Sequelize` instance.

### Fields and rules
- `handle` (text, required): length must be between 3 and 20 characters inclusive; a value outside that range must fail validation with a message that includes `handle length must be 3 to 20`.
- `email` (text, required): must be a syntactically valid email; an invalid value must fail validation with a message that includes `email is not valid`.
- `age` (integer, optional): when present, must be at least 13 and at most 120; an out-of-range value must fail validation with a message that includes `age must be between 13 and 120`.
- `slug` (text, required): must contain only lowercase letters, digits, and hyphens. A value containing uppercase letters, spaces, or other punctuation must fail validation with a message that includes `slug must be kebab-case`.
- `referralCount` (integer, optional): a custom rule must reject any negative value with a message that includes `referralCount cannot be negative`. Zero and positive values must pass.

### Edge cases and constraints
- All rules must surface when an instance is built and validated in-process (no database write).
- A fully valid instance (e.g. `handle: 'alice'`, `email: 'a@b.com'`, `age: 30`, `slug: 'cool-account-1'`, `referralCount: 0`) must validate successfully.
- Each rejection must report the error on the offending field (the failing path must be the field name), not on an unrelated field.
- A naive implementation that omits any single rule must fail the tests.

### Expected Functionality
- Build with `handle: 'ab'` and validate -> rejects with a `handle` error including `handle length must be 3 to 20`.
- Build with `email: 'nope'` and validate -> rejects with an `email` error including `email is not valid`.
- Build with `age: 5` and validate -> rejects with an `age` error including `age must be between 13 and 120`.
- Build with `slug: 'Not Kebab'` and validate -> rejects with a `slug` error including `slug must be kebab-case`.
- Build with `referralCount: -1` and validate -> rejects with a `referralCount` error including `referralCount cannot be negative`.
- Build a fully valid instance and validate -> resolves.

## Acceptance Criteria
- A new self-contained unit test `packages/core/test/unit/model/account-rules.test.ts` exists and asserts every rule above, including the exact message substrings and that each error is reported on the correct field path.
- The implementation lives in `packages/core/test/unit/model/account-rules.ts` and is imported by the test.
- All assertions are objectively verifiable in-process without a live database server.
- From the `packages/core` directory, the following command runs and passes with no failing tests:

  ```bash
  yarn mocha "test/unit/model/account-rules.test.ts"
  ```
