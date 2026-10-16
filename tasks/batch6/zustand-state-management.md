# Task: Implement a Multi-Step Form Wizard Store Module

## Background

The `zustand` repository (pmndrs/zustand) exposes the framework-agnostic `createStore` factory from `zustand/vanilla`. This task adds a self-contained multi-step form-wizard domain module on top of that public API, so its step navigation and field-validation behavior can be driven and asserted entirely outside of React using the existing Vitest setup.

## Files to Create/Modify

- `examples/wizard-store/wizardStore.ts` (new) — the form-wizard store factory and its public TypeScript types.
- `tests/wizardStore.test.ts` (new) — the deterministic Vitest suite for the module.

(The repo aliases `zustand` / `zustand/*` imports to `src/*` via `vitest.config.mts`, and the Vitest `dir` is `tests`. Place the new module under `examples/wizard-store/` and import it from the test by relative path, e.g. `../examples/wizard-store/wizardStore`.)

## Requirements

Implement a factory `createWizardStore()` in `examples/wizard-store/wizardStore.ts`. It must return a store object exposing the standard vanilla handles `getState`, `setState`, and `subscribe`. The wizard models a three-step signup flow: step `0` collects `{ email }`, step `1` collects `{ password }`, step `2` collects `{ displayName }`.

### State shape

- The state exposes `stepIndex: number` (zero-based, `0..2`), a `values` object holding the collected fields (`email: string`, `password: string`, `displayName: string`, each defaulting to `''`), and an `errors` object mapping field names to error strings.
- The state exposes these read-only derived fields, always consistent with `values` and `stepIndex`:
  - `currentStepValid: boolean` — whether the fields required by the current step pass validation (see below).
  - `isComplete: boolean` — whether every step's fields are valid.
  - `stepCount: number` — the total number of steps (`3`).

### Validation rules

- `email` is valid when it is non-empty and contains exactly one `@` with non-empty parts on both sides.
- `password` is valid when its length is at least `8`.
- `displayName` is valid when, after trimming, its length is between `1` and `30` inclusive.

### Actions

- `setField(field, value)`: updates a single field in `values`, recomputes that field's entry in `errors` (a non-empty message when invalid, removed/absent when valid), and recomputes the derived fields.
- `next()`: advances `stepIndex` by one **only when** `currentStepValid` is `true`; otherwise it is a no-op (and the current step's error is recorded in `errors`). It must never advance past the last step.
- `prev()`: decrements `stepIndex` by one; a no-op at step `0`. Going back never clears already-entered values.
- `reset()`: returns to step `0`, clears all `values` to `''`, and clears all `errors`.

### Derived consistency

`currentStepValid`, `isComplete`, and `errors` must always equal the values recomputed from `values`/`stepIndex` after every action and must never drift. A test that drives the wizard through several actions and recomputes validity independently must always agree with the stored derived fields.

## Acceptance Criteria

- `examples/wizard-store/wizardStore.ts` exports `createWizardStore` and the relevant TypeScript types; the module compiles under the repo's TypeScript config.
- A new Vitest suite `tests/wizardStore.test.ts` contains at least 10 `it`/`test` cases covering: `setField` for each field setting/clearing the matching `errors` entry, `currentStepValid` for valid and invalid input on each step, `next()` blocked on an invalid step and recording an error, `next()` advancing on a valid step, `next()` never advancing past the last step, `prev()` decrementing and being a no-op at step `0`, `prev()` preserving values, `isComplete` becoming `true` only when all steps are valid, `reset()` restoring the initial state, and derived consistency across a mixed sequence of actions.
- All new tests pass deterministically with no reliance on network, timers, randomness, real `localStorage`, or a running server.
- The following command passes:

  ```
  pnpm vitest run tests/wizardStore.test.ts
  ```
