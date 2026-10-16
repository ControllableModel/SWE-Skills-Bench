# Task: Build a Mountable URL-Shortener Redirect Module

## Background

The `hono` repository ships small, self-contained helper modules under `src/helper/` (for example `src/helper/route/` and `src/helper/testing/`), each exporting a focused feature plus a colocated `index.test.ts`. This task adds a new helper module that exposes a reusable, mountable URL-shortener whose primary job is issuing HTTP redirects.

## Files to Create/Modify

- `src/helper/url-shortener/index.ts` (new) — the URL-shortener module.
- `src/helper/url-shortener/index.test.ts` (new) — the deterministic test suite for the module.

## Requirements

### Module Surface

The module must export a factory function named `createShortener()`. Calling it returns a fresh, fully independent sub-application instance that holds its own private in-memory mapping from short codes to destination URLs. Two separate calls must never share state. The returned sub-application must be a value that can be mounted into a parent application under an arbitrary prefix so that all of its routes become reachable beneath that prefix.

### Routes and Behavior

The sub-application must serve the following request/response contract. The contract must hold both when the sub-application is exercised directly and when it is mounted beneath a non-empty prefix in a parent application.

#### Registering a link
- A `POST` request to the collection root with a JSON body `{ "url": string, "code"?: string }` registers a mapping and returns `201` with a JSON body of the shape `{ "code": <string>, "url": <string> }`.
- When `code` is supplied, that exact code is used. When `code` is omitted, the module assigns a distinct code made solely of lowercase letters and digits.
- If the body lacks a string `url`, the request fails with `400` and a JSON body `{ "error": <string> }`; nothing is registered.
- If a supplied `code` is already registered, the request fails with `409` and a JSON body `{ "error": <string> }`; the existing mapping is unchanged.

#### Following a short link
- A `GET` request to the path that embeds a registered code responds with a redirect whose status is `302` and whose `Location` response header is exactly the registered destination URL. The response must not follow the redirect itself.
- A `GET` request whose code is not registered returns `404` with a JSON body `{ "error": <string> }`.
- When the query parameter `permanent=true` is present on the follow request for a registered code, the redirect status must be `301` instead of `302`, with the same `Location`.

#### Inspecting a link
- A `GET` request to an inspect path that embeds a registered code (distinct from the follow path) returns `200` with a JSON body `{ "code": <string>, "url": <string>, "hits": <number> }`, where `hits` is the count of successful follow redirects performed for that code so far.

### Constraints and Edge Cases

- Code segments must consist solely of lowercase letters and digits; a follow or inspect request whose code segment contains any other character must surface as an unmatched route (`404`) rather than a "not registered" lookup.
- The `hits` counter increments only on successful follow redirects, never on `404` follows or on inspect requests.
- Error responses (`400`/`404`/`409`) must never mutate the mapping or the hit counts.
- All behavior must be verifiable through in-memory request dispatch (no network, no external services).

### Expected Functionality

- `POST` with `{ "url": "https://example.com", "code": "ex" }` then `GET` the follow path for `ex` -> `302` with `Location: https://example.com`.
- the same follow with `?permanent=true` -> `301`.
- two follows then inspect -> `hits` is `2`.
- `POST` a `code` that already exists -> `409`, original mapping intact.
- follow path with code `EX!` -> `404` (unmatched route).

## Acceptance Criteria

- `src/helper/url-shortener/index.ts` exports `createShortener`, which returns a value mountable into a parent application via the parent's sub-app mounting mechanism, with each call producing an isolated in-memory mapping.
- All route, status-code, redirect, header, hit-counting, and edge-case behaviors above are satisfied, verified by dispatching in-memory requests against both a directly-used and a mounted instance, inspecting redirect status codes and the `Location` header without following redirects.
- A naive implementation (e.g. shared global mapping, always returning `302`, never counting hits, or treating malformed codes as valid lookups) must fail the test suite.
- The colocated test suite contains at least 10 distinct test cases and passes with:

```
npx vitest --run src/helper/url-shortener/index.test.ts
```
