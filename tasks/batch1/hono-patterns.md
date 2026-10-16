# Task: Build a Mountable In-Memory Notes Resource Module

## Background

The `hono` repository ships small, self-contained helper modules under `src/helper/` (for example `src/helper/route/` and `src/helper/testing/`), each exporting a focused feature plus a colocated `index.test.ts`. This task adds a new helper module that exposes a reusable, mountable notes resource so applications can compose it into a larger app.

## Files to Create/Modify

- `src/helper/notes-resource/index.ts` (new) — the notes resource module.
- `src/helper/notes-resource/index.test.ts` (new) — the deterministic test suite for the module.

## Requirements

### Module Surface

The module must export a factory function named `createNotesResource()`. Calling it returns a fresh, fully independent sub-application instance that holds its own private in-memory note store. Two separate calls must never share state. The returned sub-application must be a value that can be mounted into a parent application under an arbitrary prefix so that all of its routes become reachable beneath that prefix.

Each note is an object with:
- `id`: a string, assigned by the module (callers never supply it on creation).
- `title`: a string.
- `tags`: an array of strings (may be empty).

IDs must be assigned so that, within a single resource instance, every created note receives a distinct `id`, and the values are stable for the lifetime of that note.

### Routes and Behavior

The sub-application must serve the following request/response contract. All response bodies are JSON unless stated otherwise. The contract must hold both when the sub-application is exercised directly and when it is mounted beneath a non-empty prefix in a parent application.

#### Listing notes
- A `GET` request to the collection root returns `200` with a JSON object of the shape `{ "notes": [...] }` containing every stored note.
- When the query parameter `tag` is present, the result must include only notes whose `tags` array contains that exact value. When `tag` is absent, all notes are returned.
- When the query parameter `tag` appears more than once (e.g. `?tag=work&tag=urgent`), a note must be included only if its `tags` contain every supplied value.

#### Creating a note
- A `POST` request to the collection root with a JSON body `{ "title": string, "tags"?: string[] }` creates and stores a new note and returns `201` with the created note (including its assigned `id`) as the JSON body.
- If `tags` is omitted from the body, the created note's `tags` must be an empty array.
- If the body is missing a string `title`, the request must fail with `400` and a JSON body of the shape `{ "error": <string> }`; nothing is added to the store.

#### Reading a single note
- A `GET` request to an individual note path that embeds the note id returns `200` with that note as the JSON body.
- Requesting an id that does not exist returns `404` with a JSON body of the shape `{ "error": <string> }`.

#### Replacing a note
- A `PUT` request to an individual note path with a JSON body `{ "title": string, "tags"?: string[] }` replaces the `title` and `tags` of the existing note while preserving its `id`, and returns `200` with the updated note.
- A `PUT` to a non-existent id returns `404` with `{ "error": <string> }`.

#### Deleting a note
- A `DELETE` request to an individual note path removes the note and returns `200`. After deletion, a subsequent read of that id returns `404`.
- A `DELETE` for a non-existent id returns `404` with `{ "error": <string> }`.

### Constraints and Edge Cases

- Individual-note routes must only match well-formed numeric ids consisting solely of digits. A request whose id segment contains non-digit characters must not be handled by the single-note routes (it must surface as an unmatched route, i.e. `404`, rather than being treated as an existing-or-missing note lookup). Created note ids must therefore be numeric strings.
- The list filter must perform exact, case-sensitive matching of tag values; a partial or substring match must not include a note.
- Error responses (`400`/`404`) must never mutate the store.
- The module must rely only on in-process request handling (no network, no external services); all behavior must be verifiable through in-memory request dispatch.

### Expected Functionality

- `createNotesResource()` twice -> mutating one resource's notes leaves the other empty.
- mount resource at `/api/notes`, `POST /api/notes` then `GET /api/notes/<id>` -> the same note round-trips.
- `GET /api/notes?tag=work&tag=home` -> only notes tagged with both `work` and `home`.
- `GET /api/notes/abc` (non-numeric id) -> `404`.
- `DELETE` an existing id, then `GET` it -> `404`.

## Acceptance Criteria

- `src/helper/notes-resource/index.ts` exports `createNotesResource`, which returns a value mountable into a parent application via the parent's sub-app mounting mechanism, with each call producing an isolated in-memory store.
- All route, status-code, filtering, isolation, and edge-case behaviors above are satisfied, verified by dispatching in-memory requests against both a directly-used and a mounted instance.
- A naive implementation (e.g. shared global store, ignoring repeated `tag` params, treating non-numeric ids as valid lookups, or omitting the `400`/`404` paths) must fail the test suite.
- The colocated test suite contains at least 10 distinct test cases and passes with:

```
npx vitest --run src/helper/notes-resource/index.test.ts
```
