# Task: Build a Membership API Router for the tRPC Test Suite

## Background

This repository is the tRPC monorepo. Its server package (`@trpc/server`) exposes `initTRPC`, `TRPCError`, and caller factories that the test suite under `packages/tests/server/` exercises in-process. This task adds a small, self-contained "organization membership" API built on top of these primitives, plus a deterministic test that drives it.

## Files to Create/Modify

- `packages/tests/server/membership.ts` (new) — the membership API module: an in-memory data layer, the tRPC instance/helpers, the routers, and an exported caller factory.
- `packages/tests/server/membership.test.ts` (new) — the deterministic test suite that imports from `membership.ts` and verifies behavior end-to-end via callers.

All implementation code lives in `membership.ts`. The test file must only import the public surface re-exported from `membership.ts` (the caller factory and any exported types); it must not re-implement routers or procedures.

## Requirements

### Data Layer

`membership.ts` must maintain an in-memory store of organizations and their members, with no external services, no network, no filesystem, and no global mutable singletons shared across callers in a way that leaks state between independent test runs. Expose a factory that produces a fresh, isolated data store on demand so each test can start clean.

Each organization has a string `id` and a `name`. Each membership ties a `userId` to an `orgId` with a `role` that is one of `"owner"`, `"admin"`, or `"member"`.

### Request Context

Every call is made on behalf of a caller. The caller may be unauthenticated (no user) or authenticated (carrying a `userId`). The data store must be reachable from inside every procedure through the request context rather than via module-level imports inside the procedures. The caller factory must accept, per call, both the acting user (or absence of one) and the data store to operate against.

### Procedures and Authorization Tiers

Expose a single root router (suitable for an exported `AppRouter` type) that nests a `membership` sub-router. The sub-router must offer procedures at three distinct access tiers:

1. **Public** — callable with no authenticated user.
   - `listOrganizations` — returns all organizations (id + name). No input.

2. **Authenticated** — requires a logged-in user; rejects callers with no user.
   - `myRoles` — returns the list of `{ orgId, role }` for the acting user across all organizations.
   - `joinOrganization` — input `{ orgId: string }`; adds the acting user as a `member` of the org. Rejects if the org does not exist, or if the user is already a member of it.

3. **Admin-or-owner** — requires that the acting user holds the `owner` or `admin` role **in the targeted organization**; rejects otherwise.
   - `setRole` — input `{ orgId: string; userId: string; role: "owner" | "admin" | "member" }`; updates (or creates) the target user's role in that org and returns the resulting membership record.
   - `removeMember` — input `{ orgId: string; userId: string }`; removes the target user's membership in that org and returns `{ removed: true }`.

The acting user must never be able to remove themselves via `removeMember` (such a call must be rejected), so that an org cannot be left without the acting administrator.

### Input Validation

All procedures that take input must reject malformed input before any business logic runs. In particular, an empty `orgId`, a missing field, or a `role` value outside the allowed set must be rejected as a validation failure (not as a generic runtime crash and not silently coerced). The `role` field must only accept the three allowed string values.

### Error Semantics

Failures must surface as tRPC errors carrying meaningful, distinguishable codes:

- Unauthenticated access to an authenticated/admin procedure must report an unauthorized condition.
- An authenticated user lacking the required org role on an admin-tier procedure must report a forbidden condition.
- Operating on a non-existent organization, or removing a non-member, must report a not-found condition.
- Joining an org the user already belongs to must report a conflict condition.

Distinct failure categories must use distinct codes so a caller can tell them apart programmatically. Internal data-layer details must not leak into error messages exposed to the caller.

### Expected Functionality

- Unauthenticated caller → `listOrganizations` → succeeds and lists all orgs.
- Unauthenticated caller → `joinOrganization` / `myRoles` / `setRole` / `removeMember` → fails with the unauthorized code.
- Authenticated member (role `member`) of org X → `setRole` on org X → fails with the forbidden code.
- Authenticated `admin` of org X → `setRole` on org X promoting a member to `admin` → succeeds and the new role is observable via that member's `myRoles`.
- Authenticated `admin` of org X → `setRole` / `removeMember` on org Y where they have no role → fails with the forbidden code.
- Authenticated user not in org X → `joinOrganization({ orgId: X })` → succeeds and subsequently appears in their `myRoles` as `member`; a second `joinOrganization` for the same org → fails with the conflict code.
- Authenticated owner → `removeMember` targeting their own `userId` → fails (not allowed).
- Any input-taking procedure called with an empty `orgId` or an out-of-range `role` → fails as a validation error.

## Acceptance Criteria

- A new module `packages/tests/server/membership.ts` exports a caller factory (and the router type) implementing the behavior above, using the repository's existing `@trpc/server` primitives.
- A new test file `packages/tests/server/membership.test.ts` contains at least 12 test cases covering: the three access tiers, each error category (unauthorized, forbidden, not-found, conflict, validation), the self-removal guard, role updates being observable across callers, and store isolation between independent stores.
- Tests assert on tRPC error **codes** (not on substring matching of messages) where an error is expected.
- The following command passes with all assertions green:

  ```bash
  pnpm vitest run packages/tests/server/membership.test.ts
  ```

- The suite must fail if any single tier check, validation rule, error code, or the self-removal guard is removed or hardcoded — i.e., a naive implementation that ignores roles, skips validation, or returns fixed values cannot pass.
