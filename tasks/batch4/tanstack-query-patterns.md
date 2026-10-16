# Task: Add a Cache Eviction Scheduler Helper

## Background

In the framework-agnostic core (`packages/query-core`), an unused cached entry is removed from memory after a configurable garbage-collection window elapses, and the effective window is the largest of the windows requested by the entry's observers. This task adds a self-contained public utility to `@tanstack/query-core` that computes the effective eviction window and the resulting eviction timestamp for an entry.

## Files to Create/Modify

- `packages/query-core/src/evictionSchedule.ts` (new) — implementation of the helper and its exported types.
- `packages/query-core/src/index.ts` (modify) — re-export the new function and its return type from the package entry point.
- `packages/query-core/src/__tests__/evictionSchedule.test.tsx` (new) — vitest suite covering the behavior described below.

## Requirements

Add a single exported function with the signature:

```ts
export interface EvictionInput {
  requestedGcTimes: ReadonlyArray<number | undefined> // gcTime requested by each observer
  lastActiveAt: number                                // epoch ms the entry last had an active observer
  isServer?: boolean                                  // server environment flag
}

export interface EvictionSchedule {
  effectiveGcTime: number
  evictAt: number
}

export function planEviction(input: EvictionInput): EvictionSchedule
```

The function reports the effective garbage-collection window and the absolute epoch-ms time at which the entry should be evicted.

### Scheduling semantics

- `effectiveGcTime` is the maximum of all defined, non-negative requested windows.
- A requested entry that is `undefined` (no explicit window) contributes a default window: `5 * 60 * 1000` ms in a browser environment, and `Infinity` when `isServer` is `true`.
- If `requestedGcTimes` is empty, `effectiveGcTime` is the environment default (browser default, or `Infinity` on the server).
- A negative requested window MUST be clamped to `0` before being considered.
- `evictAt` is `lastActiveAt + effectiveGcTime`. When `effectiveGcTime` is `Infinity`, `evictAt` MUST be `Infinity`.

### Edge cases and constraints

- Mixing defined and `undefined` entries: the effective window is the max across both the defined values and the contributed defaults (so a single `undefined` observer in the browser forces at least the 5-minute default).
- A single explicit `0` among other defined windows does not lower the maximum.
- The function MUST be pure: it MUST NOT read the real clock or environment itself (both `lastActiveAt` and `isServer` are provided), MUST NOT mutate its input, and MUST NOT require a `QueryClient`, cache, timers, network, or framework.

### Expected Functionality

- `planEviction({ requestedGcTimes: [1000, 5000, 2000], lastActiveAt: 100 })` -> `{ effectiveGcTime: 5000, evictAt: 5100 }`
- `planEviction({ requestedGcTimes: [1000, undefined], lastActiveAt: 0 })` -> `effectiveGcTime` is `300000` (browser default wins).
- `planEviction({ requestedGcTimes: [], lastActiveAt: 0 })` -> `effectiveGcTime` is `300000`.
- `planEviction({ requestedGcTimes: [undefined], lastActiveAt: 0, isServer: true })` -> `{ effectiveGcTime: Infinity, evictAt: Infinity }`.
- `planEviction({ requestedGcTimes: [-5, 1000], lastActiveAt: 10 })` -> `{ effectiveGcTime: 1000, evictAt: 1010 }`.

## Acceptance Criteria

- `planEviction` and the `EvictionSchedule` type are exported from `@tanstack/query-core` via `packages/query-core/src/index.ts`.
- The function returns the correct `effectiveGcTime` and `evictAt` for the max-window, default-contribution, empty, server, and clamping cases.
- `Infinity` windows produce an `Infinity` `evictAt`.
- Calling `planEviction` does not mutate its input or read the real clock/environment.
- The test suite is deterministic and runs fully in-process (no network, no timers, no `QueryClient`).
- The following command passes (run from the repo root):

```bash
pnpm --filter @tanstack/query-core exec vitest run src/__tests__/evictionSchedule.test.tsx
```
