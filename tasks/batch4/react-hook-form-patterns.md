# Task: Build a Currency-Input Payment Form with Value Transforms

## Background

This is the `react-hook-form` library source repository. Tests run directly against `src/` with Jest + `@testing-library/react` (see `scripts/jest/jest.config.js`). Build a self-contained "payment" form whose inputs render formatted strings to the user but store typed primitives in form state. Add a deterministic test that pins down the transform behavior at the form-state boundary.

## Files to Create/Modify

- `src/__tests__/examples/paymentForm.tsx` (new) — the reusable form feature, importing only from the library's own entry points (`../../index` or specific module files under `src/`).
- `src/__tests__/examples/paymentForm.test.tsx` (new) — the deterministic test suite exercising the component through rendered DOM.

> Both files live under `src/__tests__/` (create the `examples/` subdirectory). Do not modify the library's published source modules. Use the library's controlled-input primitives to bridge the displayed string and the stored value.

## Requirements

### Form shape

A single `useForm` instance models a payment with:

- `amount` — stored in form state as a **number** of cents (integer), but displayed to the user as a formatted decimal string (e.g. user types/sees `12.50`, form state holds `1250`).
- `cardLast4` — stored as a 4-character **string**; the input must reject/strip non-digits and never store more than 4 characters.
- `currency` — string select with values `USD` / `EUR`.

The form accepts an `onSubmit(values)` callback prop and exposes all controls plus a submit button through rendered DOM with stable, queryable identifiers.

### Display-vs-stored transforms

#### Expected Functionality

- **amount:** what the user types is a decimal currency string; the value committed to form state must be the integer cent count. Typing `12.50` stores `1250`; typing `0.05` stores `5`; clearing the field stores `0` (not `NaN`/`undefined`). The visible input must show the formatted decimal string at all times, including after a programmatic reset.
- **cardLast4:** typing `12a34` must result in stored value `1234`; typing `123456` must store `1234` (first four digits) — the stored value is always 0–4 digit characters, never letters.
- On submit, `onSubmit` must receive `amount` as an integer number of cents and `cardLast4` as a digits-only string of length ≤ 4 — i.e. the test asserts the **stored** (not displayed) shapes.

### Default values & reset

- The form accepts `defaultValues`; given `{ amount: 999, cardLast4: '4242', currency: 'USD' }` the amount input must initially display `9.99` and the card input `4242`.
- A **"Reset"** button restores defaults; after reset the amount input again displays the formatted default and the stored value is the integer default.

### Constraints

- No external network, real-clock timers, randomness, or running server. `onSubmit` is supplied by the test as a mock.
- The display/store conversion must happen at the controlled-input boundary; the form state must never transiently hold the raw display string for `amount`.

## Acceptance Criteria

A deterministic Jest suite at `src/__tests__/examples/paymentForm.test.tsx` must pass and cover at least, all via rendered DOM:

1. **Amount transform** — typing `12.50` then submitting yields `amount === 1250`; the input still displays `12.50`.
2. **Amount edge cases** — `0.05` stores `5`; clearing stores `0` (asserted on submit).
3. **Card sanitization** — typing `12a34` stores `1234`; typing `123456` stores `1234`.
4. **Default formatting** — with defaults `{ amount: 999, cardLast4: '4242' }` the amount input initially shows `9.99` and card shows `4242`.
5. **Reset** — after edits, "Reset" restores the displayed `9.99` and stored integer default.
6. **Submit shapes** — `onSubmit` receives `amount` as an integer and `cardLast4` as a digits-only string of length ≤ 4.

Exact command that must pass (scoped to the new suite):

```bash
TEST_ENV=web pnpm test -- src/__tests__/examples/paymentForm.test.tsx
```

The suite must contain at least 6 distinct test cases covering criteria 1–6. A naive implementation that stores the raw display string in form state, or that lets letters into `cardLast4`, must fail criteria 1–3.
