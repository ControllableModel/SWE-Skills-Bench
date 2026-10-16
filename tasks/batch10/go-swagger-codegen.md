# Task: Reject Duplicate `@Router` Path+Method on a Single Operation

## Background

`swaggo/swag` allows a handler to declare more than one `@Router` line (an operation can be reachable via several paths). Each line is parsed by `ParseRouterComment` and appended to the operation's list of route signatures. Nothing today prevents the *same* path-and-method pair from being registered twice on one operation, which silently produces a duplicate route entry and an ambiguous generated spec. This task makes the parser reject an exact duplicate.

## Files to Create/Modify

- `operation.go` (modify) — update `ParseRouterComment` so that registering a route whose path and HTTP method exactly match an already-registered route on the same operation returns an error instead of appending a duplicate.
- `operation_test.go` (new test) — add a test covering the duplicate-rejection behavior and the still-allowed distinct cases.

## Requirements

### Behavior

- When `ParseRouterComment` is called with a path+method pair that is **already present** in `operation.RouterProperties`, it MUST return a non-nil error and MUST NOT append a second identical entry.
- Comparison is on the parsed `Path` and the upper-cased `HTTPMethod` together. Both must match an existing entry for it to count as a duplicate.
- Two routes that share a path but differ in method (e.g. `GET` vs `POST` on `/users`) MUST both be accepted.
- Two routes that share a method but differ in path MUST both be accepted.
- The deprecated variant (`@Deprecated.Router`, which calls the same function with `deprecated=true`) MUST still register normally, and a duplicate of an existing path+method MUST still be rejected regardless of the deprecated flag.

### Constraints

- All existing single-route and multi-distinct-route behavior MUST be preserved: a first `@Router` line for a given path+method always succeeds.
- Existing error cases (malformed comment, invalid HTTP method) MUST keep returning errors as before; the new duplicate check applies only after the line parses successfully into a valid path+method.

### Expected Functionality

| Sequence of `@Router` lines on one operation | Result |
| --- | --- |
| `/users [get]` | accepted (1 entry) |
| `/users [get]`, then `/users [get]` | second call errors; still 1 entry |
| `/users [get]`, then `/users [post]` | both accepted (2 entries) |
| `/users [get]`, then `/accounts [get]` | both accepted (2 entries) |

## Acceptance Criteria

- Calling `ParseRouterComment` twice with `/users [get]` on the same `Operation`: the first returns nil, the second returns a non-nil error, and `operation.RouterProperties` has length 1.
- Calling it with `/users [get]` then `/users [post]`: both return nil and `RouterProperties` has length 2.
- Calling it with `/users [get]` then `/accounts [get]`: both return nil and `RouterProperties` has length 2.
- A single `/users [get]` still succeeds and produces one entry with `Path == "/users"` and `HTTPMethod == "GET"`.
- The pre-existing router-parsing tests (`TestParseRouterComment`, `TestParseRouterMultipleComments`) continue to pass.
- The following command passes from the repository root:

  ```bash
  go test -run 'TestParseRouter' ./...
  ```

  (Name the new test so it is matched by the `TestParseRouter` prefix, e.g. `TestParseRouterCommentDuplicate`.)
