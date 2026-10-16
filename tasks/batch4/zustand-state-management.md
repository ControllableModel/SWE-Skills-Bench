# Task: Implement an Authentication Session Store Module

## Background

The `zustand` repository (pmndrs/zustand) exposes the framework-agnostic `createStore` factory from `zustand/vanilla`. This task adds a self-contained authentication-session domain module on top of that public API, so its async login flow and session persistence can be driven and asserted entirely outside of React using the existing Vitest setup.

## Files to Create/Modify

- `examples/auth-store/authStore.ts` (new) — the auth-session store factory and its public TypeScript types.
- `tests/authStore.test.ts` (new) — the deterministic Vitest suite for the module.

(The repo aliases `zustand` / `zustand/*` imports to `src/*` via `vitest.config.mts`, and the Vitest `dir` is `tests`. Place the new module under `examples/auth-store/` and import it from the test by relative path, e.g. `../examples/auth-store/authStore`.)

## Requirements

Implement a factory `createAuthStore(options?)` in `examples/auth-store/authStore.ts`. It must return a store object exposing the standard vanilla handles `getState`, `setState`, and `subscribe`.

### Session state shape

- A user has at least `{ id: string; email: string }`.
- The state exposes `user: User | null`, `token: string | null`, `status: 'idle' | 'loading' | 'authenticated' | 'error'`, and `errorMessage: string | null`.
- The state exposes a read-only derived field `isAuthenticated: boolean` that is `true` exactly when both `user` and `token` are non-null.

### Async login action with explicit status/error states

- `login(authenticate)`: accepts a function returning a `Promise<{ user: User; token: string }>`. Before awaiting, `status` becomes `'loading'` and `errorMessage` becomes `null`. On success, `user` and `token` are set, `status` becomes `'authenticated'`, and `isAuthenticated` becomes `true`. If the promise rejects (or `authenticate` throws synchronously), `user`/`token` are left unchanged, `status` becomes `'error'`, `errorMessage` is set to a non-empty message derived from the failure, and `login` must NOT throw to its caller — the error must be captured into store state instead.
- A guard rejects invalid input early: if `authenticate` is not a function, `status` becomes `'error'` with a meaningful `errorMessage` and no async work is performed.

### Logout

- `logout()`: clears `user` and `token` (back to `null`), sets `status` to `'idle'`, clears `errorMessage`, and `isAuthenticated` becomes `false`. When persistence is configured, the saved session must also be cleared.

### Derived consistency

`isAuthenticated` must always equal `user !== null && token !== null` after every action and must never drift.

### Optional session persistence

`createAuthStore` accepts an optional `options.storage` implementing a minimal key/value contract (`getItem(name)`, `setItem(name, value)`, `removeItem(name)`; values are strings). When supplied, a successful `login` serializes the session (`user` + `token`) under a stable key, `logout` removes it, and a freshly created store given the same populated `storage` rehydrates the saved session (with `status: 'authenticated'` and `isAuthenticated: true`). When omitted, the store works normally with no persistence side effects. The contract must be satisfiable by a plain in-memory object in tests (no `window`, no real `localStorage`, no network).

## Acceptance Criteria

- `examples/auth-store/authStore.ts` exports `createAuthStore` and the relevant TypeScript types; the module compiles under the repo's TypeScript config.
- A new Vitest suite `tests/authStore.test.ts` contains at least 10 `it`/`test` cases covering: the login success path setting `user`/`token`/`status: 'authenticated'`/`isAuthenticated: true`, the login rejection path leaving `status: 'error'` with a non-empty `errorMessage` and unchanged session without throwing, the invalid-input guard, `logout` clearing the session, `isAuthenticated` derived consistency across actions, persistence on login, clearing on logout, and rehydration from an in-memory storage object.
- The async-failure tests assert that `login` resolves (does not reject) and that state reflects the error.
- All new tests pass deterministically with no reliance on network, timers, randomness, real `localStorage`, or a running server.
- The following command passes:

  ```
  pnpm vitest run tests/authStore.test.ts
  ```
