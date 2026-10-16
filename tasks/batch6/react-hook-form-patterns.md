# Task: Build a Tag-Editor Field-Array Form with Per-Row Validation

## Background

This is the `react-hook-form` library source repository. Tests run directly against `src/` with Jest + `@testing-library/react` (see `scripts/jest/jest.config.js`). Build a self-contained "tag editor" feature where a dynamic list of tag rows is added, removed, reordered, and validated per-row. Add a deterministic test pinning down row identity and per-row error placement.

## Files to Create/Modify

- `src/__tests__/examples/tagEditorForm.tsx` (new) — the reusable form feature, importing only from the library's own entry points (`../../index` or specific module files under `src/`).
- `src/__tests__/examples/tagEditorForm.test.tsx` (new) — the deterministic test suite exercising the component through rendered DOM.

> Both files live under `src/__tests__/` (create the `examples/` subdirectory). Do not modify the library's published source modules. Use the library's dynamic-list primitive to manage rows.

## Requirements

### Form shape

A single `useForm` instance models:

- `tags` — a dynamic array; each element is `{ label: string; color: string }`. `color` is a select with values `red` / `green` / `blue`.

Expose, through rendered DOM with stable queryable identifiers: an **"Add tag"** control, and per row a label input, a color select, a **"Remove"** control, and a **"Duplicate"** control that inserts a copy of that row directly beneath it.

### Dynamic rows

#### Expected Functionality

- Rendering with no initial tags shows zero rows; "Add tag" appends a fully-formed row with an empty label and a default color (e.g. `red`), immediately editable.
- "Remove" deletes exactly that row, leaving other rows' edited values intact and in order.
- "Duplicate" inserts a new row right after the source row whose `label` and `color` equal the source row's current edited values; editing the duplicate afterward must NOT change the original (and vice versa) — the two rows are independent.
- Adding several rows, editing each, then removing a middle row and duplicating another must never corrupt, lose, or smear any other row's values; React keys remain stable per logical row across these mutations.

### Per-row validation

- Each row's `label` is required and must be non-empty after trimming; an empty/whitespace label shows an error message **adjacent to that specific row's label input** (queryable per row).
- Duplicate **labels across rows** (case-insensitive, trimmed) are invalid: every row sharing a label with another row shows a "duplicate" error next to its own label input. Fixing one of the conflicting labels clears the error on the rows that are no longer in conflict.
- A **"Save"** button calls an `onSubmit(values)` prop with `{ tags }` only when all rows are valid; while any row is invalid, submitting must not call `onSubmit` and must reveal the per-row errors.

### Constraints

- No external network, real-clock timers, randomness, or running server. `onSubmit` is supplied by the test as a mock.
- Row mutations must operate on the form's field array (stable keys per logical row), not on index-keyed local state.

## Acceptance Criteria

A deterministic Jest suite at `src/__tests__/examples/tagEditorForm.test.tsx` must pass and cover at least, all via rendered DOM:

1. **Empty + add** — fresh form shows zero rows; "Add tag" yields one editable row with default color.
2. **Remove preserves others** — with three edited rows, removing the middle leaves the other two with their values in correct order.
3. **Duplicate independence** — duplicating a row yields a copy of its current values; editing the copy does not affect the original.
4. **Required label** — an empty/whitespace label shows an error next to that row; submitting is blocked.
5. **Duplicate-label detection** — two rows with the same (trimmed, case-insensitive) label both show a duplicate error; fixing one clears the now-resolved errors.
6. **Save gating** — `onSubmit` is called only when all rows are valid, with the full `{ tags }` payload.

Exact command that must pass (scoped to the new suite):

```bash
TEST_ENV=web pnpm test -- src/__tests__/examples/tagEditorForm.test.tsx
```

The suite must contain at least 6 distinct test cases covering criteria 1–6. A naive implementation that keys rows by index, or that shares state between a row and its duplicate, must fail criteria 2 and/or 3.
