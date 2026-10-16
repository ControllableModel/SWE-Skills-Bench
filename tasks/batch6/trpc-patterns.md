# Task: Build a Calendar Router with a Rich-Type Data Transformer

## Background

This repository is the tRPC monorepo. Its server and client packages support a configurable data transformer that lets non-JSON-native JavaScript values (such as `Date`, `Map`, and `Set`) round-trip across the serialization boundary. This task adds a self-contained "calendar" API whose inputs and outputs carry such rich types, verified across the serialization boundary with a real client/server resource, plus a deterministic test.

## Files to Create/Modify

- `packages/tests/server/calendar.ts` (new) — the module: an in-memory event store, the transformer-configured tRPC instance and helpers, the router, and an exported router (and its type) plus a helper that builds a server+client resource over it.
- `packages/tests/server/calendar.test.ts` (new) — the deterministic test importing only the public surface from `calendar.ts`.

All implementation lives in `calendar.ts`. The test must consume only the exported router/resource helper and exported types, and must drive procedures through a client so values cross the serialization boundary.

## Requirements

### Transformer Configuration

The tRPC instance must be created with a data transformer applied consistently on both server and client sides so that `Date`, `Map`, and `Set` values survive a round trip with their identity and type intact (a `Date` arrives as a `Date`, not a string; a `Set` arrives as a `Set`). The test must obtain its client from the exported resource helper so the same transformer is configured on both ends.

### Data Layer & Context

`calendar.ts` keeps an in-memory store of events, each `{ id: string; title: string; startsAt: Date; attendees: Set<string> }`. Provide a factory producing a fresh store per resource. The store is reachable inside procedures via context.

### Procedures

Expose a router with:

- `add` — input `{ title: string; startsAt: Date; attendees: string[] }`; stores an event with `attendees` as a `Set`; returns the stored event with `startsAt` as a `Date` and `attendees` as a `Set`.
- `get` — input `{ id: string }`; returns the event (with `Date` and `Set` typed fields); not-found if unknown.
- `between` — input `{ from: Date; to: Date }`; returns events whose `startsAt` falls within `[from, to]` inclusive, as an array; the result must be filtered by real `Date` comparison.
- `summary` — no input; returns a `Map` from event `id` to attendee count.

### Input Validation

`title` must be a non-empty string; `startsAt`, `from`, `to` must be valid `Date` instances; `attendees` must be an array of non-empty strings. Malformed input is rejected as a validation failure. A `between` call where `from` is after `to` reports a validation/precondition failure rather than silently returning everything.

### Error Semantics

- `get` for an unknown id → not-found.
- Invalid input → validation failure (distinct code from not-found).

### Expected Functionality

- `add` then `get` → the returned `startsAt` is a `Date` equal to the input instant, and `attendees` is a `Set` whose membership matches the input list (deduplicated).
- `between` with a window covering some events → returns exactly those whose `startsAt` is inside the inclusive window, by real date comparison.
- `between` with `from > to` → validation/precondition failure.
- `summary` → returns a `Map` (not a plain object) whose values are the attendee counts.
- Passing a non-Date where a `Date` is required → validation failure.

## Acceptance Criteria

- A new module `packages/tests/server/calendar.ts` exports the router (and its type) and a helper to build a server+client resource, both configured with a consistent data transformer on `@trpc/server`/`@trpc/client`, and a store factory.
- A new test file `packages/tests/server/calendar.test.ts` with at least 12 cases covering: `Date` round-trip identity, `Set` round-trip (including deduplication), `Map` returned by `summary`, the inclusive `between` window boundaries, the `from > to` rejection, not-found vs validation distinction, and isolation between independent resources.
- Tests must assert that received values are actual `Date`/`Set`/`Map` instances (e.g. via `instanceof`), not merely structurally similar, and assert on tRPC error **codes** where errors are expected.
- The following command passes:

  ```bash
  pnpm vitest run packages/tests/server/calendar.test.ts
  ```

- A naive implementation that drops the transformer (so dates arrive as strings or sets as arrays), returns a plain object instead of a `Map`, or ignores the window boundaries must fail the suite.
