# Task: Build a Permission-Metadata Document Router

## Background

This repository is the tRPC monorepo. Its server package (`@trpc/server`) lets each procedure carry typed metadata via `.meta()` that is visible to the cross-cutting layer through `initTRPC.meta<...>()`. This task adds a self-contained "documents" API where the required permission for each procedure is declared as metadata and enforced centrally, plus a deterministic test driven through callers.

## Files to Create/Modify

- `packages/tests/server/docPerms.ts` (new) — the module: an in-memory document store, the metadata-typed tRPC helpers, a central enforcement step, the router, and an exported caller factory.
- `packages/tests/server/docPerms.test.ts` (new) — the deterministic test importing only the public surface from `docPerms.ts`.

All implementation lives in `docPerms.ts`. The test must consume only the exported caller factory and exported types.

## Requirements

### Metadata Shape

Each procedure must be able to declare metadata of the form `{ requiredPermission?: "doc:read" | "doc:write" | "doc:delete" }`. The metadata type must be wired into the tRPC instance so the enforcement step can read it. Procedures that omit the metadata are treated as requiring no permission.

### Context

Every call carries an acting principal with a set of granted permission strings (possibly empty, or absent for anonymous callers). The caller factory must accept, per call, the acting principal (or absence of one) and the document store to operate against. The store must be reachable inside procedures via context.

### Central Enforcement

A single cross-cutting step applied to the base procedure must read the declared `requiredPermission` from the current procedure's metadata and:

- allow the call when the procedure declares no required permission;
- allow the call when the acting principal's granted set contains the declared permission;
- reject otherwise — distinguishing an anonymous principal (unauthorized) from an authenticated principal that lacks the needed permission (forbidden).

The enforcement must derive the required permission solely from metadata, so adding a new procedure only requires tagging it — no per-procedure inline permission checks.

### Procedures

Expose a single root router nesting a `docs` sub-router. Each document is `{ id: string; title: string; body: string }`.

- `get` — meta requires `doc:read`; input `{ id: string }`; returns the document; not-found if unknown.
- `list` — meta requires `doc:read`; no input; returns all documents.
- `upsert` — meta requires `doc:write`; input `{ id: string; title: string; body: string }`; creates or replaces and returns the stored document.
- `remove` — meta requires `doc:delete`; input `{ id: string }`; deletes and returns `{ removed: true }`; not-found if unknown.
- `ping` — no required permission; no input; returns `{ ok: true }` for anyone including anonymous callers.

### Input Validation

`id` must be a non-empty string; `title` and `body` must be strings (`title` non-empty). Malformed input is rejected as a validation failure before enforcement-passing business logic runs.

### Error Semantics

- Anonymous caller hitting a permission-gated procedure → unauthorized.
- Authenticated caller without the declared permission → forbidden.
- Operating on a non-existent document → not-found.
- Distinct categories use distinct tRPC codes.

### Expected Functionality

- Anonymous → `ping` → succeeds.
- Anonymous → `get` → unauthorized.
- Principal granted `["doc:read"]` → `get`/`list` succeed; `upsert` → forbidden; `remove` → forbidden.
- Principal granted `["doc:read","doc:write"]` → `upsert` succeeds and is observable via `get`; `remove` still forbidden.
- Principal granted `["doc:delete","doc:read"]` → `remove` succeeds; a second `remove` of the same id → not-found.
- `upsert({ id: "", ... })` → validation failure.

## Acceptance Criteria

- A new module `packages/tests/server/docPerms.ts` exports a caller factory and router type built on `@trpc/server`, with a metadata-typed tRPC instance and a single central enforcement step that reads `requiredPermission` from metadata.
- A new test file `packages/tests/server/docPerms.test.ts` with at least 12 cases covering: the no-permission procedure for anonymous callers, unauthorized vs forbidden distinction, each gated permission level, a write becoming observable via a read, not-found on a deleted document, and validation rejection.
- Tests assert on tRPC error **codes** where an error is expected.
- The following command passes:

  ```bash
  pnpm vitest run packages/tests/server/docPerms.test.ts
  ```

- A naive implementation that hardcodes permission checks per procedure but ignores the declared metadata, or that fails to distinguish anonymous from under-privileged callers, must fail the suite.
