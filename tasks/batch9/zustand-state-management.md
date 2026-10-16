# Task: Implement a Versioned Preferences Store Module

## Background

The `zustand` repository (pmndrs/zustand) exposes the framework-agnostic `createStore` factory from `zustand/vanilla`. This task adds a self-contained user-preferences domain module on top of that public API, with persistence and schema versioning, so its save/rehydrate/migration behavior can be driven and asserted entirely outside of React using the existing Vitest setup.

## Files to Create/Modify

- `examples/preferences-store/preferencesStore.ts` (new) — the preferences store factory and its public TypeScript types.
- `tests/preferencesStore.test.ts` (new) — the deterministic Vitest suite for the module.

(The repo aliases `zustand` / `zustand/*` imports to `src/*` via `vitest.config.mts`, and the Vitest `dir` is `tests`. Place the new module under `examples/preferences-store/` and import it from the test by relative path, e.g. `../examples/preferences-store/preferencesStore`.)

## Requirements

Implement a factory `createPreferencesStore(options?)` in `examples/preferences-store/preferencesStore.ts`. It must return a store object exposing the standard vanilla handles `getState`, `setState`, and `subscribe`.

### Preferences state shape

- The state exposes `theme: 'light' | 'dark' | 'system'` (default `'system'`), `fontScale: number` (default `1`, clamped to `[0.5, 2]`), and `language: string` (default `'en'`).
- The state exposes a read-only derived field `isDefault: boolean` that is `true` exactly when all three preferences equal their defaults.

### Actions

- `setTheme(theme)`: sets the theme to one of the allowed values; an invalid value is rejected (no state change).
- `setFontScale(scale)`: sets the font scale, clamping the value into `[0.5, 2]`; a non-finite number is rejected (no state change).
- `setLanguage(language)`: sets the language to a non-empty trimmed string; a blank value is rejected (no state change).
- `resetToDefaults()`: restores all three preferences to their defaults, making `isDefault` become `true`.

### Derived consistency

`isDefault` must always equal "all preferences equal their defaults" after every action and must never drift.

### Persistence with versioning and migration

`createPreferencesStore` accepts an optional `options.storage` implementing a minimal key/value contract (`getItem(name)`, `setItem(name, value)`, `removeItem(name)`; values are strings). When supplied:

- After every mutating action the current preferences are serialized under a stable key together with a numeric schema `version` (the current version is `2`).
- A freshly created store given a populated `storage` rehydrates the saved preferences and recomputes `isDefault` from them.
- When the stored payload carries an older `version` of `1` whose shape used a boolean `darkMode` field instead of `theme`, rehydration migrates it: `darkMode === true` becomes `theme: 'dark'`, `darkMode === false` becomes `theme: 'light'`, and the remaining fields keep their defaults. The migrated, current-version payload must then be written back to `storage`.
- When the stored payload is missing, malformed (invalid JSON), or carries an unrecognized future `version`, the store falls back to defaults without throwing.

When `options.storage` is omitted, the store works normally with no persistence side effects. The contract must be satisfiable by a plain in-memory object in tests (no `window`, no real `localStorage`, no network).

## Acceptance Criteria

- `examples/preferences-store/preferencesStore.ts` exports `createPreferencesStore` and the relevant TypeScript types; the module compiles under the repo's TypeScript config.
- A new Vitest suite `tests/preferencesStore.test.ts` contains at least 10 `it`/`test` cases covering: `setTheme` accepting valid and rejecting invalid values, `setFontScale` clamping and rejecting non-finite input, `setLanguage` rejecting blank input, `isDefault` derived consistency, `resetToDefaults`, saving to an in-memory storage after mutations, rehydrating a current-version payload, migrating a `version: 1` `darkMode` payload to `theme` and writing the migrated payload back, and falling back to defaults on a missing/malformed/unrecognized-version payload without throwing.
- All new tests pass deterministically with no reliance on network, timers, randomness, real `localStorage`, or a running server.
- The following command passes:

  ```
  pnpm vitest run tests/preferencesStore.test.ts
  ```
