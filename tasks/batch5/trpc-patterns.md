# Task: Compose a Workspace API from Feature Routers

## Background

This repository is the tRPC monorepo. Its server package (`@trpc/server`) lets routers be split by feature and combined into a single namespaced application router. This task adds a self-contained "workspace" API assembled from several independently defined feature routers under one root, plus a deterministic test driven through callers.

## Files to Create/Modify

- `packages/tests/server/workspace.ts` (new) — the module: an in-memory store, the tRPC helpers, several feature routers (projects, members, tags), their composition into one root router, and an exported caller factory.
- `packages/tests/server/workspace.test.ts` (new) — the deterministic test importing only the public surface from `workspace.ts`.

All implementation lives in `workspace.ts`. The test must consume only the exported caller factory and exported types.

## Requirements

### Feature Decomposition

The API must be built as at least three separately defined feature routers — `projects`, `members`, and `tags` — each defined in its own router object and then combined into a single root router so calls are addressed as `projects.*`, `members.*`, and `tags.*`. The root router must expose a type suitable for an exported `AppRouter`. No single monolithic router may contain all procedures inline; each feature's procedures must come from its own router definition and be nested under its namespace.

### Data Layer & Context

`workspace.ts` keeps an in-memory store with projects (`{ id, name }`), members (`{ userId, displayName }`), and tags (`{ id, label }`), plus the associations between them. Provide a factory producing a fresh store per call. The store is reachable inside procedures via context.

### Procedures

- `projects.create` — input `{ name: string }`; returns the new project `{ id, name }`.
- `projects.list` — no input; returns all projects.
- `members.add` — input `{ userId: string; displayName: string }`; returns the member.
- `members.assignToProject` — input `{ userId: string; projectId: string }`; links an existing member to an existing project; returns `{ assigned: true }`. Not-found if either does not exist; conflict if the assignment already exists.
- `members.ofProject` — input `{ projectId: string }`; returns the members assigned to that project.
- `tags.create` — input `{ label: string }`; returns the tag `{ id, label }`.
- `tags.attachToProject` — input `{ tagId: string; projectId: string }`; attaches an existing tag to an existing project; returns `{ attached: true }`. Not-found if either is missing; conflict on duplicate attachment.
- `tags.ofProject` — input `{ projectId: string }`; returns the tags attached to that project.

### Input Validation

All string inputs must be non-empty; malformed input is rejected as a validation failure before any cross-feature lookup runs.

### Error Semantics

- Referencing a non-existent project, member, or tag → not-found.
- Creating a duplicate association → conflict.
- Distinct categories use distinct tRPC codes; store internals must not leak into messages.

### Expected Functionality

- `projects.create` then `projects.list` → the project appears.
- `members.add` + `members.assignToProject` (valid ids) → succeeds; `members.ofProject` includes that member.
- `members.assignToProject` with an unknown `projectId` → not-found.
- A repeated `members.assignToProject` of the same pair → conflict.
- `tags.create` + `tags.attachToProject` → `tags.ofProject` lists the tag; duplicate attach → conflict.
- An assignment created via the `members` namespace must be observable via `members.ofProject` and must not appear under `tags.ofProject`, demonstrating the namespaces stay independent while sharing the same context store.
- Empty-string input on any procedure → validation failure.

## Acceptance Criteria

- A new module `packages/tests/server/workspace.ts` exports a caller factory and router type, composed from at least three separately defined feature routers nested under distinct namespaces on `@trpc/server`.
- A new test file `packages/tests/server/workspace.test.ts` with at least 12 cases covering: each feature namespace, cross-namespace association (member↔project, tag↔project), not-found and conflict categories, namespace independence (a member assignment not surfacing as a tag attachment), and store isolation between factory calls.
- Tests assert on tRPC error **codes** where an error is expected.
- The following command passes:

  ```bash
  pnpm vitest run packages/tests/server/workspace.test.ts
  ```

- A naive implementation that collapses everything into one flat router, mixes up the associations, or ignores duplicate/missing-reference checks must fail the suite.
