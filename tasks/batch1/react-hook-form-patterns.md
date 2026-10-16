# Task: Build a Render-Isolated Invoice Line-Items Form

## Background

This is the `react-hook-form` library source repository. Tests run directly against `src/` with Jest + `@testing-library/react` (see `scripts/jest/jest.config.js`, `testMatch: '**/__tests__/**/*.(spec|test).ts?(x)'`). Several existing suites (e.g. `src/__tests__/useWatch.test.tsx`) assert exact component render counts to prove update isolation. Your task is to build a small invoice form feature on top of the library's own public API and a deterministic test that pins down both its behavior and its re-render characteristics.

## Files to Create/Modify

- `src/__tests__/examples/invoiceForm.tsx` (new) — the reusable form feature (React component plus any small child components/helpers it needs), importing only from the library's own entry points (`../../index` or the specific module files under `src/`).
- `src/__tests__/examples/invoiceForm.test.tsx` (new) — the deterministic test suite that exercises the component through rendered DOM interactions.

> Both files live under the existing `src/__tests__/` tree (create the `examples/` subdirectory). Do not modify the library's published source modules; build entirely on the existing public hooks/components (`useForm`, `useWatch`, `useController`, `useFieldArray`, `Controller`, `FormProvider`, `useFormContext`, `subscribe`, etc.).

## Requirements

### Form shape

The form models an invoice with these fields under a single `useForm` instance:

- `customer` — string, top-level text input.
- `items` — a dynamic array; each item is an object `{ description: string; quantity: number; unitPrice: number }`.

The component must expose, through rendered DOM, the controls described below. Use stable, queryable identifiers (e.g. `aria-label`, `data-testid`, role + accessible name) so a test can target each control unambiguously. Document the chosen identifiers in code comments where helpful.

### Dynamic line items

#### Expected Functionality

- Rendering the form with no initial data shows the `customer` input and **zero** item rows.
- An **"Add item"** control appends a new, fully-formed item row whose three inputs start empty/zero (not `undefined`), so the new row's inputs are immediately editable and reflected in form state.
- Each item row has a **"Remove"** control that deletes exactly that row, leaving the other rows' current edited values intact and correctly positioned.
- A **"Move up"** control on each row (except the first) swaps that row with the one above it; after the move, every row's edited values move with their row — i.e. row identity is preserved across reordering, values do not smear onto neighboring rows.
- Adding several rows, editing each, then removing a middle row and moving rows around must never corrupt, duplicate, or lose any other row's edited values.

### Live total (isolated subscription)

- The form renders a **running total** equal to the sum of `quantity * unitPrice` across all current items, formatted as a plain number (e.g. `Total: 42`). The total updates as item quantities/prices change.
- A **render counter** is exposed by the top-level invoice form component (increment a counter on each render of that component and render its current value as text, e.g. `Form renders: 3`). This counter is used by the test to verify update isolation.

#### Expected Functionality (re-render isolation)

- Typing into the `customer` input MUST update the customer value but MUST NOT increase the top-level invoice form component's render count. (The customer field's own display may live in a child; the top-level form body must not re-render on each customer keystroke.)
- Typing into an item's `quantity` or `unitPrice` updates the running total. The mechanism that reads item values to compute the total must be isolated such that editing the `customer` field causes no recomputation-driven re-render of unrelated parts.
- Adding or removing a row legitimately re-renders the structural part of the form (row count changes); that is acceptable and expected.

### Async submit lifecycle

- The form accepts an async `onSubmit(values)` callback prop. On submit it must call `onSubmit` with the current `{ customer, items }` values.
- While the submit promise is pending, a **submit button** must be in a disabled/pending state and expose a queryable pending indicator (e.g. text `Submitting...` or `aria-busy="true"`).
- When `onSubmit` resolves successfully, the form must clear back to its initial empty state (no item rows, empty `customer`) and the submit button must return to its idle state.
- When `onSubmit` rejects, the form values must be **preserved** (not cleared), the pending state must end, and a root-level error message (e.g. text containing `Submission failed`) must be displayed. A subsequent successful submit must clear that error.

### Constraints

- No external network, timers-by-real-clock, randomness, or running server. Async submit behavior must be driven by promises resolved/rejected by the test (the test supplies the `onSubmit` mock).
- All item-array mutations (add / remove / move) must operate on the form's field array such that React keys remain stable per logical row across reorders (no index-as-key smearing).
- The component must rely on the library's controlled/subscription primitives rather than mirroring the entire form into local React state.

## Acceptance Criteria

A deterministic Jest suite at `src/__tests__/examples/invoiceForm.test.tsx` must pass and must cover at least the following, all via rendered DOM (using `render`, `screen`, `fireEvent`/`userEvent`, `waitFor` from `@testing-library/react`):

1. **Empty render** — fresh form shows the customer input and no item rows; total reads `0`.
2. **Add item** — clicking "Add item" creates one editable row with empty/zero inputs; adding twice yields two rows.
3. **Running total** — entering quantity `3` and unit price `4` in one row, and `2` / `5` in another, makes the total read `22`.
4. **Remove preserves others** — with three edited rows, removing the middle row leaves the remaining two rows showing their original edited values in the correct order.
5. **Move preserves identity** — editing two rows distinctly, then moving the second row up, shows the two rows swapped with each row's values intact (assert by reading each row's input values after the move).
6. **Customer keystrokes do not re-render the form body** — capture the top-level form's render-count text, type several characters into `customer`, and assert the top-level render count did **not** increase as a result of those keystrokes (while the customer value is still updated, verified on submit).
7. **Async submit success** — submit with a mock `onSubmit` returning a pending-then-resolved promise; assert the button shows its pending state while pending, that `onSubmit` was called once with the exact current values, and that after resolution the form is cleared (no rows, empty customer) and the button is idle.
8. **Async submit failure** — submit with a rejecting mock; assert the pending state ends, the form values are preserved (rows and customer unchanged), and a `Submission failed` message appears; then a follow-up resolving submit clears the error and the form.

Exact command that must pass (scoped to the new suite):

```bash
TEST_ENV=web pnpm test -- src/__tests__/examples/invoiceForm.test.tsx
```

(Equivalently, `pnpm jest --config ./scripts/jest/jest.config.js src/__tests__/examples/invoiceForm.test.tsx` for the web project.) The suite must contain at least 8 distinct test cases covering criteria 1–8 above, and a naive implementation that re-renders the whole form on every keystroke, or that mirrors array items by index, must fail criteria 5 and/or 6.
