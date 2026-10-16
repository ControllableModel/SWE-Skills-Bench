# Task: Support AND-Combined Security Requirements in `@Security`

## Background

`swaggo/swag` parses the `@Security` annotation on a handler into the operation's security requirements. Each call to `ParseSecurityComment` appends one requirement object. In OpenAPI, listing multiple schemes **inside the same requirement object** means all of them are required together (logical AND), while separate objects mean any one suffices (logical OR). Today `ParseSecurityComment` splits the line so that each scheme becomes its own entry but cannot express two schemes that must both be satisfied within a single annotation. This task adds AND-combining on one line via `&&`.

## Files to Create/Modify

- `operation.go` (modify) — update `ParseSecurityComment` so that schemes joined by `&&` on a single `@Security` line are collected into one requirement object (one map containing all of them).
- `operation_test.go` (new test) — add a test that parses combined and non-combined security lines and inspects `operation.Security`.

## Requirements

### Parsing Rules

The argument to `@Security` is a sequence of scheme references. A new separator `&&` (two ampersands, optionally surrounded by spaces) MUST be supported:

- Schemes joined by `&&` MUST all appear as keys in **one** requirement map appended to `operation.Security` (AND semantics).
- A scheme may carry scopes in brackets, e.g. `OAuth2[read, write]`; scopes MUST be parsed into the string slice for that scheme exactly as today.
- A line with no `&&` MUST keep the existing behavior (each space/separated scheme becomes its own key in the single appended map).

### Expected Functionality

| `@Security` line | Appended requirement object |
| --- | --- |
| `Bearer` | `{ "Bearer": [] }` |
| `BasicAuth && ApiKeyAuth` | `{ "BasicAuth": [], "ApiKeyAuth": [] }` |
| `OAuth2[read, write] && ApiKeyAuth` | `{ "OAuth2": ["read","write"], "ApiKeyAuth": [] }` |

### Constraints

- Each `ParseSecurityComment` call appends exactly one requirement object to `operation.Security`.
- Scheme names MUST be trimmed of surrounding whitespace.
- An empty line still resets `operation.Security` to an empty (non-nil) slice (unchanged behavior).
- Scope lists keep their order and are trimmed of whitespace.

## Acceptance Criteria

- After parsing `BasicAuth && ApiKeyAuth`, `operation.Security` contains exactly one map with both keys `BasicAuth` and `ApiKeyAuth`, each mapped to an empty (or nil) scope slice.
- After parsing `OAuth2[read, write] && ApiKeyAuth`, the single appended map has `OAuth2` → `["read", "write"]` and `ApiKeyAuth` → empty.
- After parsing a plain `Bearer` line, the appended map has the single key `Bearer`.
- Parsing an empty line yields `operation.Security == []map[string][]string{}`.
- The following command passes from the repository root:

  ```bash
  go test -run TestParseSecurityComment ./...
  ```

  (Name the new test `TestParseSecurityComment`.)
