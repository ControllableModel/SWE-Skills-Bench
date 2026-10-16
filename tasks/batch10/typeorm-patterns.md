# Task: Build an Audit-Trail Layer Driven by Persistence Events

## Background

The TypeORM repository (`typeorm/typeorm`) exercises the ORM end-to-end with functional tests under `test/functional/` that run against an in-memory SQLite database via the repo's own public API. This task adds a self-contained "audit trail" feature where an audit row is written automatically as a side effect of persisting domain records, verified through that API.

## Files to Create/Modify

- `test/functional/audit-trail/entity/Account.ts` (new) — the auditable account record type.
- `test/functional/audit-trail/entity/AuditLog.ts` (new) — the audit-log record type.
- `test/functional/audit-trail/audit-subscriber.ts` (new) — a persistence-event subscriber that records inserts/updates of the account.
- `test/functional/audit-trail/audit-service.ts` (new) — a service constructed from a `DataSource` exposing the operations below.
- `test/functional/audit-trail/audit-trail.test.ts` (new) — the functional test that wires the entities and subscriber into a testing `DataSource` and verifies every requirement.

Follow the existing conventions in `test/functional/` (see `test/functional/custom-repository/custom-repository.test.ts` and the existing subscriber tests under `test/functional/entity-subscriber/`): import decorators/types from the repo's own `src/` via relative paths, register the subscriber through the testing `DataSource`, use `createTestingConnections`, `reloadTestingDatabases`, and `closeTestingConnections` from `../../utils/test-utils`, and assert with `chai`.

## Requirements

### Domain model

An **Account** has a database-generated numeric identity, a `name` string, and a `status` string. An **AuditLog** has a database-generated numeric identity, an `entityId` referencing the affected account, an `action` string (`"created"` or `"updated"`), and a timestamp the ORM sets automatically.

### Audit behavior via persistence events

`audit-subscriber.ts` must export a subscriber that listens to the account's persistence lifecycle so that:

- Inserting a new account automatically writes exactly one `AuditLog` row with `action = "created"` and the new account's `entityId`, without the caller explicitly creating the audit row.
- Updating an existing account automatically writes exactly one `AuditLog` row with `action = "updated"` and the account's `entityId`.
- The audit row is written as part of the same persistence operation that triggered it (it must be present immediately after the save completes, not on a later flush the caller performs).

### Audit service

`audit-service.ts` must export a class (or factory) built from a `DataSource` providing at least:

- **createAccount(name)** — persists a new account (with status `"active"`) and returns it.
- **changeStatus(accountId, status)** — updates an existing account's status.
- **historyOf(accountId)** — returns that account's audit-log rows ordered by id ascending.

### Constraints

- The test must run without any external database server: enable only the SQLite-based driver(s) when creating the testing connections.
- The schema must be derived from the record-type definitions by the ORM during test setup; no hand-written `CREATE TABLE` SQL.
- The audit rows must be produced by the persistence-event mechanism, not by the service method manually inserting an `AuditLog` after each save.

### Expected Functionality

- Creating an account → exactly one audit row exists for it with `action = "created"`.
- Then changing that account's status once → a second audit row exists with `action = "updated"`, and `historyOf` returns the two rows in order (`created` then `updated`).
- Creating two accounts → each has its own single `created` audit row referencing the correct `entityId`, with no cross-contamination.
- No audit row is written by the service methods themselves (removing the subscriber registration makes the audit history empty), proving the events drive the audit.

## Acceptance Criteria

- The five files exist under `test/functional/audit-trail/`; entities, subscriber, and service are imported by the test from the repo's own `src/` and `utils`.
- All scenarios in **Expected Functionality** are asserted and pass against the SQLite driver.
- An implementation that writes audit rows directly inside the service methods instead of via the persistence-event subscriber must fail at least one assertion (notably the "removing the subscriber empties the history" check).
- The test compiles and passes. From the repo root:

```bash
pnpm run compile && npx mocha ./build/compiled/test/functional/audit-trail/audit-trail.test.js
```
