# Task: Build a Streaming Activity-Feed Module

## Background

The `hono` repository ships small, self-contained helper modules under `src/helper/` (for example `src/helper/route/` and `src/helper/streaming/`), each exporting a focused feature plus a colocated `index.test.ts`. This task adds a new helper module that emits a buffered activity feed as a streamed text response, alongside conventional JSON routes for managing the buffer.

## Files to Create/Modify

- `src/helper/activity-feed/index.ts` (new) — the activity-feed module.
- `src/helper/activity-feed/index.test.ts` (new) — the deterministic test suite for the module.

## Requirements

### Module Surface

The module must export a factory function named `createFeed()`. Calling it returns a fresh sub-application instance holding its own private in-memory ordered list of activity lines (strings). The returned value must be mountable into a parent application under an arbitrary prefix. Two separate calls hold independent buffers.

### Routes and Behavior

The contract must hold both directly and when mounted under a non-empty prefix. The streamed route must produce a finite, fully-readable response body (the test reads the response to completion as text).

#### Appending activity
- A `POST` request to `/events` with a JSON body `{ "line": string }` appends that line to the buffer and returns `201` with a JSON body `{ "index": <number> }`, where `index` is the zero-based position of the appended line.
- If the body lacks a string `line`, the request returns `400` with a JSON body `{ "error": <string> }` and nothing is appended.

#### Streaming the feed
- A `GET` request to `/stream` returns `200` with a `Content-Type` response header that begins with `text/plain`, and a streamed body consisting of every buffered line, each followed by a single newline character (`\n`), in buffer order. With an empty buffer the streamed body is the empty string.
- The full streamed body, once read to completion, must equal the lines joined such that each line (including the last) is terminated by `\n`.

#### Counting
- A `GET` request to `/count` returns `200` with a JSON body `{ "count": <number> }` equal to the current number of buffered lines.

#### Clearing
- A `DELETE` request to `/events` empties the buffer and returns `200` with a JSON body `{ "count": 0 }`. A subsequent `GET /count` returns `0` and `GET /stream` returns the empty body.

### Constraints and Edge Cases

- Lines must stream in the exact order they were appended.
- The streamed response must be finite and terminate on its own so the body can be read to completion deterministically.
- A `400` append must not change the buffer or the next assigned index.
- All behavior must be verifiable through in-memory request dispatch, reading the streamed response body fully as text (no network, no external services, no timers).

### Expected Functionality

- append `"a"` then `"b"`, `GET /stream` -> body equals `"a\nb\n"`.
- `GET /stream` on a fresh feed -> body equals `""`.
- append returns `index` `0` then `1`.
- `POST /events` with a non-string `line` -> `400`, buffer unchanged.
- append two lines, `DELETE /events`, then `GET /count` -> `0`.

## Acceptance Criteria

- `src/helper/activity-feed/index.ts` exports `createFeed`, which returns a value mountable into a parent application, with each call producing an isolated ordered buffer and a streamed feed route.
- All append, streaming, count, clear, ordering, `Content-Type`, and edge-case behaviors above are satisfied, verified by dispatching in-memory requests against both a directly-used and a mounted instance and reading the streamed body to completion.
- A naive implementation (e.g. a non-terminating stream, wrong line ordering, missing trailing newline, or sharing the buffer globally) must fail the test suite.
- The colocated test suite contains at least 10 distinct test cases and passes with:

```
npx vitest --run src/helper/activity-feed/index.test.ts
```
