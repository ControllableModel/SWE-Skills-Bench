# Task: Build a Context-Backed Rate-Limited Counter API

## Background

This repository is the tRPC monorepo. Its server package (`@trpc/server`) builds a per-request context that procedures read shared resources from, and supports an asynchronous context factory. This task adds a self-contained "quota counter" API where a per-caller rate limit and shared resources live in the request context, with public and authenticated tiers, plus a deterministic test driven through callers.

## Files to Create/Modify

- `packages/tests/server/quotaCounter.ts` (new) — the module: an in-memory counter store and a quota tracker, an asynchronous context factory, the tRPC helpers, the router, and an exported caller factory.
- `packages/tests/server/quotaCounter.test.ts` (new) — the deterministic test importing only the public surface from `quotaCounter.ts`.

All implementation lives in `quotaCounter.ts`. The test must consume only the exported caller factory and exported types.

## Requirements

### Context Factory

`quotaCounter.ts` must expose an asynchronous context factory that, given the acting caller (an optional `userId`) and shared backing stores, produces the per-request context. The context must carry: the shared counter store, a per-user remaining-quota value resolved at context-creation time, and the acting user (or absence of one). Procedures must read these only from the context, never via module-level access. The caller factory must accept, per call, the acting user (or absence) and the shared stores so independent runs stay isolated.

### Quota Model

Each authenticated user has a per-request quota of mutating operations (a small fixed integer, e.g. `3`). The quota is resolved into the context when the context is created. Each successful mutating procedure consumes one unit from the in-context remaining quota; once it reaches zero, further mutating calls within that same context are rejected with a too-many-requests condition. Read-only procedures never consume quota.

### Procedures

Expose a single root router nesting a `counter` sub-router:

- `current` — public; input `{ key: string }`; returns `{ key, value }` (default `0` if never set). Consumes no quota; callable by anonymous callers.
- `increment` — authenticated; input `{ key: string; by?: number }`; adds `by` (default `1`) to the counter for `key` and returns the new value. Mutating; consumes quota.
- `reset` — authenticated; input `{ key: string }`; sets the counter for `key` to `0` and returns `{ key, value: 0 }`. Mutating; consumes quota.
- `remaining` — authenticated; no input; returns `{ remaining }` reflecting the quota left in the current context. Consumes no quota.

### Authorization Tiers

- `current` is callable with no authenticated user.
- `increment`, `reset`, and `remaining` require an authenticated user; an anonymous caller is rejected with an unauthorized condition.

### Input Validation

`key` must be a non-empty string; `by`, when present, must be an integer (may be negative). Malformed input is rejected as a validation failure before any mutation or quota consumption occurs — a call that fails validation must not consume quota.

### Error Semantics

- Anonymous caller on an authenticated procedure → unauthorized.
- Exceeding the per-request quota on a mutating procedure → too-many-requests.
- Invalid input → validation failure.
- Distinct categories use distinct tRPC codes; internal store details must not leak.

### Expected Functionality

- Anonymous → `current({ key })` → `{ key, value: 0 }`; anonymous → `increment` → unauthorized.
- Authenticated → `increment({ key, by: 5 })` then `current({ key })` → value `5`.
- Authenticated with quota `3` → three successful mutating calls; a fourth mutating call in the same context → too-many-requests; `remaining` reflects `0` and does not itself error.
- A mutating call that fails input validation does not decrement `remaining`.
- A fresh context (new caller-factory call) for the same user restores the full quota, proving quota lives per request/context, not globally.
- `current` and `remaining` never consume quota even when called repeatedly.

## Acceptance Criteria

- A new module `packages/tests/server/quotaCounter.ts` exports a caller factory and router type built on `@trpc/server`, using an asynchronous context factory that resolves per-user quota and shared stores into the request context.
- A new test file `packages/tests/server/quotaCounter.test.ts` with at least 12 cases covering: the public vs authenticated tiers, quota consumption on mutating calls, the too-many-requests boundary at the quota limit, read-only calls not consuming quota, validation failures not consuming quota, per-context quota reset across independent caller-factory calls, and store isolation.
- Tests assert on tRPC error **codes** where errors are expected.
- The following command passes:

  ```bash
  pnpm vitest run packages/tests/server/quotaCounter.test.ts
  ```

- A naive implementation that stores quota globally, decrements on validation failures, lets read-only calls consume quota, or ignores the authenticated tier must fail the suite.
