# Task: Build a Nested FormProvider Address-Book Form

## Background

This is the `react-hook-form` library source repository. Tests run directly against `src/` with Jest + `@testing-library/react` (see `scripts/jest/jest.config.js`). Build a self-contained "address book" form composed of deeply-nested child field components that read and write the shared form via context rather than prop-drilling. Add a deterministic test pinning down context wiring and per-field state access.

## Files to Create/Modify

- `src/__tests__/examples/addressBookForm.tsx` (new) — the reusable form feature: a top-level form component plus at least two levels of nested child field components that access the form through context, importing only from the library's own entry points (`../../index` or specific module files under `src/`).
- `src/__tests__/examples/addressBookForm.test.tsx` (new) — the deterministic test suite exercising the component through rendered DOM.

> Both files live under `src/__tests__/` (create the `examples/` subdirectory). Do not modify the library's published source modules. The nested children must obtain form access through context, not through props passed down from the top component.

## Requirements

### Form shape

A single `useForm` instance, shared via context with nested children, models:

- `contact.firstName`, `contact.lastName` — strings (nested under `contact`).
- `address.street`, `address.city`, `address.zip` — strings (nested under `address`); `zip` must be exactly 5 digits.

The structure must be: a top-level form component → an intermediate `ContactSection` and `AddressSection` → individual field components (e.g. a generic `TextField` that takes only a field `name` and looks up everything else from context). Expose all inputs plus a submit button through rendered DOM with stable queryable identifiers (e.g. by accessible label).

### Context-driven fields & per-field state

#### Expected Functionality

- Each leaf field component must register/connect its input and surface its own validation error message **adjacent to its own input**, reading both the registration and its error from form context — without the parent passing down the form object.
- `zip` validation: a value that is not exactly 5 digits shows a field-specific error and blocks submit; exactly 5 digits is accepted. The error must appear next to the `zip` input only, not elsewhere.
- Required fields (`firstName`, `street`, `city`) each show their own error adjacent to their input when empty on submit; filling one clears only that field's error.
- A **per-field "touched/dirty" badge**: each leaf field shows a small queryable indicator (e.g. `data-testid="dirty-<name>"` text `dirty`/`clean`) reflecting whether that single field has been modified from its default, accessing that single field's state without subscribing the whole form.

### Submit

- On a valid submit, `onSubmit(values)` (a prop) must receive the full nested shape `{ contact: { firstName, lastName }, address: { street, city, zip } }`.

### Constraints

- No external network, real-clock timers, randomness, or running server. `onSubmit` is supplied by the test as a mock.
- Leaf field components must consume the form via context; the top component must not thread the form instance through props to the leaves.

## Acceptance Criteria

A deterministic Jest suite at `src/__tests__/examples/addressBookForm.test.tsx` must pass and cover at least, all via rendered DOM:

1. **Context wiring** — typing into nested leaf inputs updates the corresponding nested form values (verified on submit) even though leaves get the form from context.
2. **Zip validation** — a non-5-digit zip shows an error next to the zip input and blocks submit; a 5-digit zip is accepted.
3. **Per-field required errors** — submitting with empty `firstName` and `street` shows an error next to each, and only those; filling `firstName` clears just its error.
4. **Per-field dirty badge** — editing only `city` flips its dirty badge to `dirty` while other fields' badges stay `clean`.
5. **Nested payload** — a valid submit calls `onSubmit` with the full nested `{ contact, address }` shape.
6. **Independent field errors** — fixing one invalid field does not clear another still-invalid field's error.

Exact command that must pass (scoped to the new suite):

```bash
TEST_ENV=web pnpm test -- src/__tests__/examples/addressBookForm.test.tsx
```

The suite must contain at least 6 distinct test cases covering criteria 1–6. A naive implementation that prop-drills the form object to the leaves, or that surfaces a shared error for all fields, must fail the context-wiring intent and criteria 3/6.
