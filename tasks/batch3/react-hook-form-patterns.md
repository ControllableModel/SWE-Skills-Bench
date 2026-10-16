# Task: Build a Survey Form with Server-Error Surfacing

## Background

This is the `react-hook-form` library source repository. Tests run directly against `src/` with Jest + `@testing-library/react` (see `scripts/jest/jest.config.js`). Build a self-contained "survey submission" form feature on top of the library's public API plus a deterministic test that pins down its submit lifecycle and server-error handling.

## Files to Create/Modify

- `src/__tests__/examples/surveyForm.tsx` (new) — the reusable form feature, importing only from the library's own entry points (`../../index` or specific module files under `src/`).
- `src/__tests__/examples/surveyForm.test.tsx` (new) — the deterministic test suite exercising the component through rendered DOM.

> Both files live under `src/__tests__/` (create the `examples/` subdirectory). Do not modify the library's published source modules.

## Requirements

### Form shape

A single `useForm` instance models a survey with:

- `email` — string text input.
- `rating` — number select with values `1`–`5`.
- `comment` — string textarea (optional).

The form accepts an async `onSubmit(values)` callback prop. Expose all controls and the submit button through rendered DOM with stable, queryable identifiers.

### Submit lifecycle & server errors

#### Expected Functionality

- On submit, the form must call `onSubmit` with the current `{ email, rating, comment }` values.
- While the submit promise is pending, the submit button must be in a disabled/pending state with a queryable pending indicator (e.g. text `Submitting...` or `aria-busy="true"`).
- **Field-level server errors:** when `onSubmit` rejects with an object shaped `{ fieldErrors: { email?: string; rating?: string; comment?: string } }`, each present message must be surfaced **adjacent to its own field** so the test can read, per field, the error text for that field. The form values must be preserved.
- **Form-level server error:** when `onSubmit` rejects with `{ formError: string }` (no `fieldErrors`), a single root-level error message must be displayed (e.g. an element with `role="alert"` containing that text), with form values preserved.
- On a successful resolve, all previously displayed server errors (field-level and form-level) must be cleared, and the submit button returns to idle.

### Re-submit clears stale errors

- After a failed submit that displayed errors, editing the offending field and re-submitting must first clear the previously shown server errors before the new submit result is reflected. A second failure with different errors must replace the old error set, never accumulate duplicates.

### Constraints

- No external network, real-clock timers, randomness, or running server. The async `onSubmit` is supplied by the test as a mock whose resolution/rejection the test controls.
- Server errors must be surfaced through the form's own error state, not via ad-hoc local React state holding error strings.

## Acceptance Criteria

A deterministic Jest suite at `src/__tests__/examples/surveyForm.test.tsx` must pass and cover at least, all via rendered DOM:

1. **Pending state** — submitting with a pending mock shows the button's pending indicator; resolving clears it.
2. **Calls onSubmit with values** — submit passes the exact current `{ email, rating, comment }`.
3. **Field-level errors** — rejecting with `{ fieldErrors: { email: 'taken', rating: 'invalid' } }` shows each message next to its field; values preserved.
4. **Form-level error** — rejecting with `{ formError: 'service down' }` shows a single root alert; values preserved.
5. **Success clears errors** — after a failure that showed errors, a follow-up resolving submit removes all error messages.
6. **Re-submit replaces errors** — a second failure with different field errors replaces the prior set (no duplicate/stale messages).

Exact command that must pass (scoped to the new suite):

```bash
TEST_ENV=web pnpm test -- src/__tests__/examples/surveyForm.test.tsx
```

The suite must contain at least 6 distinct test cases covering criteria 1–6. A naive implementation that never clears prior server errors, or that loses form values on rejection, must fail criteria 5 and/or 3.
