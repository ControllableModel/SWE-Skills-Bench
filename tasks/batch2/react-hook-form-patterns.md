# Task: Build an Autosave-Enabled Profile Settings Form

## Background

This is the `react-hook-form` library source repository. Tests run directly against `src/` with Jest + `@testing-library/react` (see `scripts/jest/jest.config.js`, `testMatch: '**/__tests__/**/*.(spec|test).ts?(x)'`). Build a self-contained "profile settings" form feature on top of the library's own public API plus a deterministic test that pins down its autosave and re-render behavior. Several existing suites assert exact render counts to prove update isolation.

## Files to Create/Modify

- `src/__tests__/examples/profileSettingsForm.tsx` (new) — the reusable form feature (a React component plus any small child components/helpers), importing only from the library's own entry points (`../../index` or specific module files under `src/`).
- `src/__tests__/examples/profileSettingsForm.test.tsx` (new) — the deterministic test suite exercising the component through rendered DOM interactions.

> Both files live under the existing `src/__tests__/` tree (create the `examples/` subdirectory). Do not modify the library's published source modules; build entirely on existing public hooks/components.

## Requirements

### Form shape

A single `useForm` instance models a profile with:

- `displayName` — string text input.
- `bio` — string textarea.
- `theme` — string select with values `light` / `dark`.

The form must accept an `initialValues` prop and an `onAutosave(values)` callback prop. Expose all controls through rendered DOM with stable, queryable identifiers (`aria-label`, `data-testid`, or role + accessible name).

### Autosave side-effect

#### Expected Functionality

- The form must call `onAutosave` with the **current full form values** every time **any** field value changes, and pass the exact latest `{ displayName, bio, theme }` snapshot.
- The autosave callback must NOT be invoked on initial mount before any user edit.
- A visible **"Saved" indicator** (e.g. text `Saved` or `data-testid="save-status"` whose text becomes `saved`) must appear after the form notifies an autosave, and the indicator text must reflect how many times autosave has fired (e.g. `Saved (3)`).

### Re-render isolation

- The top-level profile form component must expose a **render counter** (increment on each render of that component, render the current value as text, e.g. `Form renders: 2`).
- The autosave mechanism that observes value changes MUST NOT cause the top-level form component to re-render on every keystroke. Typing several characters into `displayName` must update the value and fire autosave callbacks but must NOT increase the top-level form component's render count beyond its mount render(s).

### Reset behavior

- A **"Revert"** button must restore the form to the `initialValues` it was given, clearing any edits.
- After reverting, the next user edit must again fire autosave with values derived from `initialValues` (i.e. revert must not desynchronize the autosave snapshot from the actual form state).

### Constraints

- No external network, real-clock timers, randomness, or running server. The `onAutosave` callback is supplied by the test as a mock.
- The component must rely on the library's value-subscription primitives for the autosave side-effect rather than mirroring the whole form into local React state or wiring an `onChange` on every input by hand.

## Acceptance Criteria

A deterministic Jest suite at `src/__tests__/examples/profileSettingsForm.test.tsx` must pass and cover at least, all via rendered DOM (`render`, `screen`, `fireEvent`/`userEvent`, `waitFor`):

1. **No autosave on mount** — rendering with `initialValues` does not call `onAutosave`.
2. **Autosave on edit** — editing `displayName` calls `onAutosave` with the full current values including the new name.
3. **Multiple fields** — editing `bio` then `theme` each fire autosave with the correct cumulative snapshot.
4. **Save indicator count** — after N edits the save status reflects N saves.
5. **Form body not re-rendered per keystroke** — capture the top-level render-count text, type several characters into `displayName`, assert the top-level render count did NOT increase as a result.
6. **Revert** — after edits, clicking "Revert" restores all fields to `initialValues`.
7. **Autosave consistent after revert** — editing after a revert fires autosave with a snapshot based on `initialValues` plus the new edit.

Exact command that must pass (scoped to the new suite):

```bash
TEST_ENV=web pnpm test -- src/__tests__/examples/profileSettingsForm.test.tsx
```

The suite must contain at least 7 distinct test cases covering criteria 1–7. A naive implementation that re-renders the whole form on every keystroke, or that fires autosave on mount, must fail criteria 1 and/or 5.
