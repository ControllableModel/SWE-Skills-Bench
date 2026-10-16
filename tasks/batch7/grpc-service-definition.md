# Task: Pin down server-to-client error conversion in rpctypes

## Background

etcd's `api/v3rpc/rpctypes` package is the shared vocabulary of over-the-wire errors. Its
`Error` function converts a server-side transport error into the corresponding client-side
`EtcdError` (which exposes a stable classification code and message), and `ErrorDesc`
extracts the human-readable description from any error. Clients depend on this conversion to
map a received error back to a known sentinel so they can branch on it.

## Files to Create/Modify

- `api/v3rpc/rpctypes/error.go` (modify only if a real defect is found; otherwise leave the
  production logic intact).
- `api/v3rpc/rpctypes/error_test.go` (modify) — add a test (e.g. `TestErrorConversion`)
  covering the round-trip and the fallback behavior.

## Requirements

### Round-trip for known errors

For a representative set of the package's server-side errors (at least one each whose
classification is invalid-argument, not-found, and resource-exhausted), `Error` applied to
the server-side error MUST produce an `EtcdError` whose classification code equals the
server error's code and whose description equals the server error's description.

### Pass-through for unknown errors

`Error` applied to an error that is not one of the package's known server-side errors (for
example a plain `errors.New("something")`) MUST return that error unchanged — it MUST NOT
be coerced into an `EtcdError`, and its description MUST be preserved.

### Nil handling

`Error(nil)` MUST return `nil`.

### Description extraction

`ErrorDesc` MUST return the transport message for a transport-classified error, and MUST
return the plain `.Error()` string for a non-transport Go error. For the package's known
errors, `ErrorDesc` of the server-side error and of the client-side error produced by
`Error` MUST be equal (the description is preserved across conversion).

### Constraints

- Identification of known errors MUST go through the package's description-keyed lookup,
  not by comparing arbitrary Go error strings outside the package's own table.
- The classification code carried by the resulting `EtcdError` MUST match the source code.

### Expected Functionality

- `Error(<known invalid-argument server err>)` -> `EtcdError` with invalid-argument code,
  same description.
- `Error(<known not-found server err>)` -> `EtcdError` with not-found code, same description.
- `Error(errors.New("x"))` -> the same error back (not an `EtcdError`), description "x".
- `Error(nil)` -> nil.
- `ErrorDesc(serverErr) == ErrorDesc(Error(serverErr))` for known errors.

## Acceptance Criteria

- The new test uses the package's exported server-side errors and `EtcdError` type, asserts
  the converted classification code (via the `Code()` method) and description equality for
  known errors, asserts the unchanged pass-through and nil cases, and asserts the
  `ErrorDesc` equalities.
- All existing tests in the package, including `TestConvert`, continue to pass.
- The following command, run from the repository root, MUST succeed:

  ```
  cd api && go test ./v3rpc/rpctypes/ -run 'TestErrorConversion|TestConvert' -count=1 -v
  ```
