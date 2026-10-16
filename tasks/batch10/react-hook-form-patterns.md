# Task: Build a Debounced Async-Uniqueness Validation Form

## Background

This is the `react-hook-form` library source repository. Tests run directly against `src/` with Jest + `@testing-library/react` (see `scripts/jest/jest.config.js`). Build a self-contained "register" form whose `username` field is validated asynchronously against a caller-supplied uniqueness checker, with the in-flight/availability state surfaced to the UI. Add a deterministic test pinning down the async-validation lifecycle.

## Files to Create/Modify

- `src/__tests__/examples/registerForm.tsx` (new) — the reusable form feature, importing only from the library's own entry points (`../../index` or specific module files under `src/`).
- `src/__tests__/examples/registerForm.test.tsx` (new) — the deterministic test suite exercising the component through rendered DOM.

> Both files live under `src/__tests__/` (create the `examples/` subdirectory). Do not modify the library's published source modules.

## Requirements

### Form shape

A single `useForm` instance models:

- `username` — string text input, required, min length 3, validated for uniqueness via an async `checkUsername(name) => Promise<boolean>` prop (`true` = available).
- `password` — string, required, min length 8.

Expose both inputs plus a submit button through rendered DOM with stable queryable identifiers.

### Async uniqueness validation

#### Expected Functionality

- When `username` changes and passes the synchronous rules (required, min length 3), the form must validate uniqueness by calling the `checkUsername` prop with the current value.
- While that async check is pending, a queryable **checking indicator** (e.g. text `Checking...` next to the username field) must be shown; it must disappear once the check settles.
- If `checkUsername` resolves `false`, a field-level error (e.g. `Username taken`) must be shown adjacent to the username input and submit must be blocked. If it resolves `true`, no uniqueness error is shown and an optional `Available` indicator may be displayed.
- The synchronous rules must short-circuit the async check: a username shorter than 3 must show its length error and must NOT trigger a `checkUsername` call.
- **Stale-response safety:** if the username is changed again before a prior `checkUsername` promise resolves, the final displayed availability/error must reflect the **latest** username, not a late-arriving result for a previous value.

### Submit

- The submit button calls `onSubmit(values)` (a prop) only when all sync rules pass and the latest uniqueness check resolved available; otherwise submitting reveals the relevant errors and does not call `onSubmit`.

### Constraints

- No external network, real-clock timers, randomness, or running server. Both `checkUsername` and `onSubmit` are supplied by the test as mocks whose resolution the test controls (e.g. via deferred promises), so ordering/staleness is deterministic.
- Uniqueness state must flow through the form's own validation/error machinery, not via independent local error state.

## Acceptance Criteria

A deterministic Jest suite at `src/__tests__/examples/registerForm.test.tsx` must pass and cover at least, all via rendered DOM:

1. **Sync short-circuit** — a 2-character username shows the length error and `checkUsername` is never called.
2. **Pending indicator** — entering a valid-length username shows the checking indicator while the deferred `checkUsername` promise is pending.
3. **Taken** — resolving `checkUsername` to `false` shows a taken error next to the field and blocks submit.
4. **Available** — resolving `checkUsername` to `true` clears the checking indicator and allows submit (given a valid password).
5. **Stale response** — change the username to value B while A's check is still pending, then resolve A's (false) and B's (true) promises; the final UI reflects B's availability, not A's stale failure.
6. **Submit gating** — `onSubmit` is called only once all sync rules pass and the latest username resolved available.

Exact command that must pass (scoped to the new suite):

```bash
TEST_ENV=web pnpm test -- src/__tests__/examples/registerForm.test.tsx
```

The suite must contain at least 6 distinct test cases covering criteria 1–6. A naive implementation that ignores response ordering, or that runs the async check for too-short usernames, must fail criteria 5 and/or 1.
