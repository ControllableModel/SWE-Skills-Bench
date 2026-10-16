# Task: Build a Streaming Metrics Feed Procedure

## Background

This repository is the tRPC monorepo. Its server package (`@trpc/server`) supports procedures implemented as async generators that yield a sequence of validated values which a caller consumes as an async iterable. This task adds a self-contained "metrics feed" API that streams a bounded, deterministic sequence, plus a deterministic test that consumes the stream in-process.

## Files to Create/Modify

- `packages/tests/server/metricsFeed.ts` (new) — the module: an in-memory metrics source, the tRPC helpers, a streaming procedure plus supporting procedures, the router, and an exported caller factory.
- `packages/tests/server/metricsFeed.test.ts` (new) — the deterministic test importing only the public surface from `metricsFeed.ts`.

All implementation lives in `metricsFeed.ts`. The test must consume only the exported caller factory and exported types, and must consume the streamed procedure as an async iterable.

## Requirements

### Data Layer & Context

`metricsFeed.ts` keeps an in-memory ordered list of metric samples, each `{ seq: number; valueCents: number }`, where `seq` starts at `1` and increases by `1`. Provide a factory producing a fresh source per call. The source is reachable inside procedures via context.

### Procedures

Expose a single root router nesting a `metrics` sub-router:

- `record` — input `{ valueCents: number }`; appends a sample with the next `seq` and returns it.
- `stream` — input `{ fromSeq: number; limit: number }`; an async-generator procedure that yields, in order, up to `limit` samples whose `seq >= fromSeq`, each shaped `{ seq, valueCents }`. The stream must be finite and end after yielding the available/limited samples.
- `count` — no input; returns the number of recorded samples.

### Streaming Contract

- Each yielded value must conform to a declared per-item output shape (`seq` and `valueCents` both numbers); a value not matching that shape must be rejected rather than silently emitted.
- The stream yields strictly increasing `seq` values, starting at the first sample with `seq >= fromSeq`.
- The stream yields at most `limit` items; if fewer qualifying samples exist, it yields exactly those and then completes.
- The stream must be deterministic and contain no timers, randomness, network, or external services.

### Input Validation

`valueCents` must be an integer; `fromSeq` must be an integer `>= 1`; `limit` must be an integer `>= 1`. Malformed input is rejected as a validation failure before streaming begins.

### Error Semantics

- Invalid input to any procedure → validation failure.
- Distinct from any not-found behavior; codes must be distinguishable.

### Expected Functionality

- After recording N samples, consuming `stream({ fromSeq: 1, limit: N })` yields all N in `seq` order.
- `stream({ fromSeq: 3, limit: 2 })` after recording at least 4 samples → yields exactly the samples with `seq` 3 and 4.
- `stream({ fromSeq: 99, limit: 5 })` when only a few samples exist → yields zero items and completes without error.
- `stream({ fromSeq: 1, limit: 1 })` → yields exactly one item.
- `count` reflects the number recorded.
- `stream({ fromSeq: 0, limit: 5 })` or `limit: 0` → validation failure.
- Independent sources from separate factory calls do not share samples.

## Acceptance Criteria

- A new module `packages/tests/server/metricsFeed.ts` exports a caller factory and router type built on `@trpc/server`, including an async-generator streaming procedure with a declared per-item output shape.
- A new test file `packages/tests/server/metricsFeed.test.ts` with at least 12 cases covering: full-range streaming, windowed streaming (`fromSeq`/`limit`), an empty-but-valid stream completing cleanly, the single-item case, ordering of `seq`, validation rejections for out-of-range `fromSeq`/`limit`, and source isolation. The test must collect the async iterable into an array to assert on contents.
- Tests assert on tRPC error **codes** where errors are expected.
- The following command passes:

  ```bash
  pnpm vitest run packages/tests/server/metricsFeed.test.ts
  ```

- A naive implementation that returns a single array from a normal query, ignores `fromSeq`/`limit`, yields out of order, or skips validation must fail the suite.
