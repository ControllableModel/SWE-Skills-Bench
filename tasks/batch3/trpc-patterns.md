# Task: Build an Audit-Logging Procedure Pipeline

## Background

This repository is the tRPC monorepo. Its server package (`@trpc/server`) exposes `initTRPC`, `TRPCError`, and a caller factory. This task adds a self-contained "task tracker" API whose procedures share a chain of cross-cutting behaviors (timing, request tagging, and an in-context audit log) layered before the business logic, plus a deterministic test that drives it through callers.

## Files to Create/Modify

- `packages/tests/server/auditLog.ts` (new) — the module: an in-memory task store, the tRPC helpers, a reusable chain of cross-cutting steps, the router, and an exported caller factory.
- `packages/tests/server/auditLog.test.ts` (new) — the deterministic test that imports only the public surface from `auditLog.ts`.

All implementation lives in `auditLog.ts`. The test must consume only the exported caller factory and exported types.

## Requirements

### Data Layer & Context

`auditLog.ts` keeps an in-memory store of tasks (each `{ id: string; title: string; done: boolean }`) plus an in-memory, per-request audit sink. Provide a factory that produces a fresh store and a fresh audit sink per call so independent tests start clean. The store and the audit sink must be reachable inside procedures via the request context, not via module-level access.

### Cross-Cutting Pipeline

Define a reusable, composable chain of steps applied to a base procedure such that, for every procedure built on it, the following all happen in order before the procedure body runs and are observable afterwards:

1. A per-call request id (a non-empty string) is attached and made available to the procedure body.
2. The start time is captured, and after the body completes a `durationMs` (a non-negative number) is recorded.
3. An audit record is appended to the per-request audit sink describing the call: `{ requestId, path, durationMs, ok }`, where `path` is the called procedure's path string, and `ok` reflects whether the body threw.

Each step must add to the accumulated context rather than replacing it, so the request id added by an earlier step is still visible to a later step and to the body.

### Procedures

Expose a single root router nesting a `tasks` sub-router:

- `create` — input `{ title: string }`; appends a task with a generated id and `done: false`; returns the created task.
- `toggle` — input `{ id: string }`; flips `done` for the task and returns it; not-found if the id is unknown.
- `list` — no input; returns all tasks.
- `audit` — no input; returns the audit records accumulated so far in this request's sink.

### Error Behavior in the Pipeline

When a procedure body throws (e.g. `toggle` on an unknown id), the audit record for that call must still be appended with `ok: false` and a recorded `durationMs`, and the original error must still propagate to the caller with its tRPC code intact. A not-found target reports a not-found condition.

### Input Validation

`title` must be a non-empty string; `id` must be a non-empty string. Malformed input is rejected as a validation failure before the body runs. The audit record for a call that fails validation, if any is produced, must reflect that the call did not succeed.

### Expected Functionality

- `create({ title })` then `list` → the new task appears; an audit record for the `create` path exists with `ok: true` and a numeric `durationMs >= 0`.
- Two successive `create` calls → two distinct request ids in the audit sink.
- `toggle({ id })` on an existing task → flips `done`; calling again flips it back.
- `toggle({ id: "missing" })` → not-found error propagates, and an audit record for that path with `ok: false` is present.
- `create({ title: "" })` → validation failure.
- Independent stores from separate factory calls do not share audit records or tasks.

## Acceptance Criteria

- A new module `packages/tests/server/auditLog.ts` exports a caller factory and router type built on the existing `@trpc/server` primitives, using a composed chain of cross-cutting steps applied to a shared base procedure.
- A new test file `packages/tests/server/auditLog.test.ts` with at least 12 cases covering: request-id presence and uniqueness, `durationMs` recorded for both success and failure, ordered context accumulation (request id visible in the body), audit records for success and for a thrown procedure, error-code propagation through the pipeline, validation rejection, and store/audit isolation.
- Tests assert on tRPC error **codes** where an error is expected.
- The following command passes:

  ```bash
  pnpm vitest run packages/tests/server/auditLog.test.ts
  ```

- A naive implementation that skips the pipeline, drops audit records on failure, overwrites context instead of accumulating it, or swallows thrown errors must fail the suite.
