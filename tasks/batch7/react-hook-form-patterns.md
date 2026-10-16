# Task: Build a Dirty-Field Tracking Edit Form with Selective Submit

## Background

This is the `react-hook-form` library source repository. Tests run directly against `src/` with Jest + `@testing-library/react` (see `scripts/jest/jest.config.js`). Build a self-contained "account edit" form that tracks which fields the user actually changed, sends only the changed subset on submit, and isolates the dirty-state UI from input re-renders. Add a deterministic test pinning down this behavior.

## Files to Create/Modify

- `src/__tests__/examples/accountEditForm.tsx` (new) — the reusable form feature, importing only from the library's own entry points (`../../index` or specific module files under `src/`).
- `src/__tests__/examples/accountEditForm.test.tsx` (new) — the deterministic test suite exercising the component through rendered DOM.

> Both files live under `src/__tests__/` (create the `examples/` subdirectory). Do not modify the library's published source modules.

## Requirements

### Form shape

A single `useForm` instance is initialized from a `defaultValues` prop and models:

- `firstName` — string text input.
- `lastName` — string text input.
- `email` — string text input.
- `newsletter` — boolean checkbox.

Expose all controls plus a **"Save"** button through rendered DOM with stable queryable identifiers.

### Dirty tracking & selective submit

#### Expected Functionality

- A queryable **dirty indicator** must show whether the form has unsaved changes (e.g. text `Unsaved changes` vs `No changes`) and the **count of changed fields** (e.g. `Changed: 2`).
- A field counts as changed only if its current value differs from its default. Editing a field and then typing the original value back must make it no longer count as changed (count returns to 0).
- The **"Save"** button calls an `onSubmit(changed)` prop where `changed` is an object containing **only** the fields whose values differ from their defaults — not the full form. If nothing is dirty, "Save" must be disabled (or calling it must not invoke `onSubmit`).
- After a successful save, the form must treat the just-saved values as the new baseline: the dirty count returns to 0 and the same values no longer count as changed.

### Re-render isolation

- The top-level form component must expose a **render counter** (increment per render, render as text e.g. `Form renders: 1`).
- The dirty-indicator UI must subscribe to dirty state in isolation so that updating it does NOT force the top-level form component to re-render on each keystroke: typing into `firstName` updates the dirty indicator but must not increase the top-level form component's render count.

### Constraints

- No external network, real-clock timers, randomness, or running server. `onSubmit` is supplied by the test as a mock.
- Changed-field detection and dirty UI must use the form's own state tracking, not a hand-rolled diff stored in local React state that mirrors every field.

## Acceptance Criteria

A deterministic Jest suite at `src/__tests__/examples/accountEditForm.test.tsx` must pass and cover at least, all via rendered DOM:

1. **Initially clean** — with `defaultValues`, the dirty indicator shows no changes and count 0; "Save" does not call `onSubmit`.
2. **Becomes dirty** — editing two fields shows `Changed: 2` and an unsaved-changes indicator.
3. **Revert-by-retyping** — editing a field then restoring its original value returns the changed count to 0.
4. **Selective payload** — saving after changing only `email` and `newsletter` calls `onSubmit` with exactly `{ email, newsletter }` (no other keys).
5. **Baseline reset after save** — after a successful save, the dirty count is 0 and the saved values no longer count as changed.
6. **Isolation** — capture the top-level render-count text, type several characters into `firstName`, assert the top-level render count did NOT increase as a result.

Exact command that must pass (scoped to the new suite):

```bash
TEST_ENV=web pnpm test -- src/__tests__/examples/accountEditForm.test.tsx
```

The suite must contain at least 6 distinct test cases covering criteria 1–6. A naive implementation that submits the full form, or that re-renders everything on every keystroke, must fail criteria 4 and/or 6.
