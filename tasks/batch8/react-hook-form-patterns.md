# Task: Build a Conditional Booking Form with Dependent Fields

## Background

This is the `react-hook-form` library source repository. Tests run directly against `src/` with Jest + `@testing-library/react` (see `scripts/jest/jest.config.js`). Build a self-contained "trip booking" form where the set of visible fields and their validation rules depend on the current value of other fields. Add a deterministic test pinning down the dependent-field and conditional-validation behavior.

## Files to Create/Modify

- `src/__tests__/examples/bookingForm.tsx` (new) — the reusable form feature, importing only from the library's own entry points (`../../index` or specific module files under `src/`).
- `src/__tests__/examples/bookingForm.test.tsx` (new) — the deterministic test suite exercising the component through rendered DOM.

> Both files live under `src/__tests__/` (create the `examples/` subdirectory). Do not modify the library's published source modules. Read dependent values through the library's value-subscription primitives so that the conditional UI updates as the controlling field changes.

## Requirements

### Form shape

A single `useForm` instance models:

- `tripType` — string select with values `oneway` / `roundtrip`.
- `departDate` — string text input (always shown).
- `returnDate` — string text input, **shown only when** `tripType === 'roundtrip'`.
- `passengers` — number input, min 1.
- `needsAssistance` — boolean checkbox; when `true`, a dependent `assistanceNotes` textarea appears and becomes required.

Expose all currently-visible controls plus a submit button through rendered DOM with stable queryable identifiers.

### Dependent visibility & validation

#### Expected Functionality

- `returnDate` is rendered only while `tripType === 'roundtrip'`. Switching from `roundtrip` back to `oneway` must hide `returnDate` and ensure it does not block submission or leak its prior value into the submitted payload.
- When `tripType === 'roundtrip'`, `returnDate` is required and must be a non-empty value; submitting without it reveals a field-level error and does not call `onSubmit`.
- `assistanceNotes` is rendered and required only while `needsAssistance` is checked; unchecking it removes the field and its requirement, and the notes must not appear in the submitted payload.
- `passengers` must always be ≥ 1; a value of 0 or empty reveals an error and blocks submit.

### Submit payload shape

- On a valid submit, `onSubmit(values)` (a prop) must be called with only the fields relevant to the current selections: for a one-way trip with no assistance, the payload must NOT contain a `returnDate` or `assistanceNotes` key (or they must be cleared/undefined), and for a round-trip with assistance it must contain both.

### Constraints

- No external network, real-clock timers, randomness, or running server. `onSubmit` is supplied by the test as a mock.
- Conditional fields must be driven by subscribing to the controlling field's value through the form, not by an independent local state copy of `tripType` / `needsAssistance`.

## Acceptance Criteria

A deterministic Jest suite at `src/__tests__/examples/bookingForm.test.tsx` must pass and cover at least, all via rendered DOM:

1. **Conditional visibility** — `returnDate` is hidden for `oneway` and appears when `tripType` is set to `roundtrip`.
2. **Conditional requirement** — with `roundtrip` selected and `returnDate` empty, submitting shows a field error and does not call `onSubmit`.
3. **Assistance toggle** — checking `needsAssistance` reveals a required `assistanceNotes` field; unchecking removes it and its requirement.
4. **Passengers floor** — `passengers` of 0/empty shows an error and blocks submit; 1+ is accepted.
5. **One-way payload** — a valid one-way, no-assistance submit calls `onSubmit` without a meaningful `returnDate`/`assistanceNotes`.
6. **Round-trip payload** — a valid round-trip with assistance submit calls `onSubmit` including both `returnDate` and `assistanceNotes`.

Exact command that must pass (scoped to the new suite):

```bash
TEST_ENV=web pnpm test -- src/__tests__/examples/bookingForm.test.tsx
```

The suite must contain at least 6 distinct test cases covering criteria 1–6. A naive implementation that mirrors `tripType` in separate local state, or that always submits hidden-field values, must fail criteria 1 and/or 5.
