# Task: Add a type-level utility for deeply-readonly config objects

## Background

Vite's `packages/vite/src/node/typeUtils.ts` houses type-only helpers used to derive plugin and config types. Config objects are often frozen at runtime; a matching compile-time `DeepReadonly<T>` type is useful for APIs that hand out immutable config snapshots. This task adds the type and pins its behavior with type-level tests.

## Files to Create/Modify

- `packages/vite/src/node/typeUtils.ts` (modify) — add and export a new type `DeepReadonly<T>`.
- `packages/vite/src/node/__tests__/deepReadonly.spec.ts` (new) — a dedicated type-testing file.

## Requirements

### Type definition

Add an exported type:

```ts
export type DeepReadonly<T> = /* ... */
```

It recursively makes every property of an object type `readonly` at every depth.

### Behavior (type level)

- For a plain object type, every own property becomes `readonly`, and each property's type is itself wrapped in `DeepReadonly`.
- For an array type `U[]`, the result is `ReadonlyArray<DeepReadonly<U>>` (or the equivalent `readonly DeepReadonly<U>[]`).
- For a tuple type, the result is a `readonly` tuple whose element types are each wrapped in `DeepReadonly`.
- Primitive types (`string`, `number`, `boolean`, `null`, `undefined`, `symbol`, `bigint`) are left unchanged.
- Function types are left unchanged (not descended into).
- Nesting must be applied recursively — an object three levels deep is fully readonly at every level.

### Edge cases

- `DeepReadonly<{ a: { b: number } }>` makes both `a` and the nested `b` readonly.
- `DeepReadonly<number[]>` is assignable from `readonly number[]` and rejects mutation.
- `DeepReadonly<string>` equals `string`.
- An optional property stays optional after the transform.

## Acceptance Criteria

- `DeepReadonly` is exported from `packages/vite/src/node/typeUtils.ts`.
- The new test file imports the type from `../typeUtils` and uses Vitest's type-level testing API (`expectTypeOf` and/or `assertType`) to assert, at minimum: a nested object's inner property is `readonly`, an array becomes a readonly array, a primitive passes through unchanged, a function type passes through unchanged, and an optional property remains optional. At least 8 type-level assertions.
- The test file must compile without type errors and the runtime test run must pass from the repo root:

```
pnpm exec vitest run packages/vite/src/node/__tests__/deepReadonly.spec.ts
```

- A shallow-only implementation (top-level `Readonly<T>`) or one that breaks optionality must fail at least one type-level assertion.
