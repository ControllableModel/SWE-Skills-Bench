# Task: Build a Multi-Step Wizard Form with Per-Step Validity Gating

## Background

This is the `react-hook-form` library source repository. Tests run directly against `src/` with Jest + `@testing-library/react` (see `scripts/jest/jest.config.js`). Build a self-contained "signup wizard" form that splits one form across three steps, gates the "Next" button on the current step's validity, and preserves values across step navigation. Add a deterministic test pinning down the gating and persistence behavior.

## Files to Create/Modify

- `src/__tests__/examples/wizardForm.tsx` (new) — the reusable form feature, importing only from the library's own entry points (`../../index` or specific module files under `src/`).
- `src/__tests__/examples/wizardForm.test.tsx` (new) — the deterministic test suite exercising the component through rendered DOM.

> Both files live under `src/__tests__/` (create the `examples/` subdirectory). Do not modify the library's published source modules.

## Requirements

### Form shape & steps

A single `useForm` instance backs all three steps:

- Step 1 — `email` (required, must contain `@`), `username` (required, min length 3).
- Step 2 — `password` (required, min length 8), `confirmPassword` (required, must equal `password`).
- Step 3 — `acceptedTerms` (boolean, must be `true`).

Only the current step's fields are rendered at a time. A **"Next"**, **"Back"**, and final **"Submit"** button are exposed with stable, queryable identifiers, along with a queryable current-step indicator (e.g. `Step 2 of 3`).

### Per-step gating

#### Expected Functionality

- The **"Next"** button must be disabled until **all fields of the current step** are valid; it becomes enabled only once they are. Validity of fields on other (not-yet-visited) steps must NOT affect the current step's "Next" enablement.
- Clicking "Next" while the step is valid advances to the next step; "Back" returns to the previous step.
- Values entered on a step must persist when navigating away and back (e.g. typing an email on step 1, going to step 2 and back, still shows that email).
- On the final step, "Submit" must be disabled until `acceptedTerms` is true; submitting calls an `onSubmit(values)` prop with the full accumulated `{ email, username, password, confirmPassword, acceptedTerms }`.

### Cross-field validation

- `confirmPassword` must be considered invalid (and step 2's "Next" disabled) whenever it does not exactly equal the current `password`, including when `password` is edited after `confirmPassword` was already typed.

### Constraints

- No external network, real-clock timers, randomness, or running server. `onSubmit` is supplied by the test as a mock.
- Step navigation must preserve form state through the form's own state, not by unmounting-and-losing values; re-entering a step shows previously entered values.

## Acceptance Criteria

A deterministic Jest suite at `src/__tests__/examples/wizardForm.test.tsx` must pass and cover at least, all via rendered DOM:

1. **Initial gating** — on step 1 with empty fields, "Next" is disabled; filling a valid email + username (≥3) enables it.
2. **Advance/back** — clicking "Next" shows `Step 2 of 3`; "Back" returns to step 1.
3. **Value persistence** — an email typed on step 1 is still present after navigating to step 2 and back.
4. **Cross-field** — on step 2, "Next" stays disabled while `confirmPassword !== password`, and re-disables if `password` is later changed to differ.
5. **Final gating** — on step 3, "Submit" is disabled until `acceptedTerms` is checked.
6. **Submit payload** — submitting calls `onSubmit` once with the full accumulated values from all three steps.

Exact command that must pass (scoped to the new suite):

```bash
TEST_ENV=web pnpm test -- src/__tests__/examples/wizardForm.test.tsx
```

The suite must contain at least 6 distinct test cases covering criteria 1–6. A naive implementation that gates "Next" on whole-form validity, or that loses values across steps, must fail criteria 1 and/or 3.
