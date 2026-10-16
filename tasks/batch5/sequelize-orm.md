# Task: Compose Reusable Query Presets

## Background
This is the [Sequelize](https://github.com/sequelize/sequelize) monorepo. Inside the `@sequelize/core` package's unit-test tree we need a "ticket" model that ships a set of reusable, composable named query presets so that common filtered views can be requested by name without rebuilding query options each time. Unit tests in this package run against the default dialect without opening a real database connection, so the effective query options produced by applying presets can be inspected in-process.

## Files to Create/Modify
- `packages/core/test/unit/model/ticket-presets.ts` (new) — the module defining the `Ticket` model and exporting `defineTicket(sequelize)`.
- `packages/core/test/unit/model/ticket-presets.test.ts` (new) — the unit test that exercises the presets.

## Requirements

### Module shape
- The module must export `defineTicket(sequelize)` which defines and returns the `Ticket` model on the passed-in `Sequelize` instance.

### Fields
- `subject` (text, required).
- `status` (text) — one of `open`, `pending`, `closed`.
- `priority` (integer) — defaults to `0`.
- `assigneeId` (integer, optional).

### Default and named presets
- The model's default query view must, with no preset applied, restrict results to tickets whose `status` is not `closed`.
- A named preset `closed` must restrict results to tickets whose `status` equals `closed`.
- A named preset `highPriority` must restrict results to tickets whose `priority` is greater than or equal to `3`.
- A parameterized named preset `assignedTo(userId)` must restrict results to tickets whose `assigneeId` equals the supplied `userId`.

### Composition and independence
- Applying `highPriority` together with `assignedTo(7)` must yield effective query options that contain BOTH restrictions (priority ≥ 3 AND assigneeId = 7).
- A variant with NO preset applied must carry only the default (non-closed) restriction and must not carry the priority or assignee restrictions.
- A variant must not mutate the base model: requesting a preset-applied view and then the default view again must show the default view still carries only its own restriction.

### Edge cases and constraints
- `assignedTo` must accept its argument at apply-time and reflect that exact value in the produced options.
- A naive implementation that hardcodes the produced options, or that lets one preset leak into another, must fail the tests.

### Expected Functionality
- Default view options -> include a `status != closed` restriction; no priority/assignee restriction.
- `closed` preset options -> include a `status == closed` restriction.
- `highPriority` preset options -> include a `priority >= 3` restriction.
- `assignedTo(7)` preset options -> include an `assigneeId == 7` restriction.
- `highPriority` + `assignedTo(7)` -> include both the priority and assignee restrictions.

## Acceptance Criteria
- A new self-contained unit test `packages/core/test/unit/model/ticket-presets.test.ts` exists and asserts: the default restriction, each named preset's restriction, the parameterized preset's argument handling, the composed (multi-preset) options carrying both restrictions, and that the base/default view is not mutated.
- The implementation lives in `packages/core/test/unit/model/ticket-presets.ts` and is imported by the test.
- All assertions are objectively verifiable in-process without a live database server.
- From the `packages/core` directory, the following command runs and passes with no failing tests:

  ```bash
  yarn mocha "test/unit/model/ticket-presets.test.ts"
  ```
