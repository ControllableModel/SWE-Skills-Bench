# Task: Build a Permission Set Resolver

## Background

This repository (`github.com/samber/lo`) is a generics-first utility library for Go. To exercise the library against a realistic workload, add a small self-contained example application under a new `examples/perm` package that resolves the effective permissions of a user from grants and explicit denials drawn from multiple roles.

## Files to Create/Modify

- `examples/perm/resolve.go` (new) — the resolution logic, in `package perm`.
- `examples/perm/resolve_test.go` (new) — table-driven tests, in `package perm`, using only the Go stdlib `testing` package.

Both files belong to the existing module `github.com/samber/lo` (`go 1.18`), so the import path for the new package is `github.com/samber/lo/examples/perm`. You may import `github.com/samber/lo` from within the new package.

## Requirements

### Input and output types

Define the following exported types in `examples/perm/resolve.go`:

```go
type Role struct {
    Name   string
    Grants []string // permission strings this role grants
    Denies []string // permission strings this role explicitly denies
}

type Resolution struct {
    Effective []string // sorted ascending: granted minus denied
    Granted   []string // sorted ascending: union of all grants (before applying denies)
    Denied    []string // sorted ascending: union of all denies that actually removed a granted permission
}
```

### Behavior

Implement:

```go
func Resolve(roles []Role) Resolution
```

with the following rules:

#### Union and dedup
- `Granted` is the de-duplicated union of every role's `Grants`, sorted ascending.
- A permission is denied if it appears in ANY role's `Denies`.

#### Effective set
- `Effective` is `Granted` minus every denied permission, sorted ascending.
- `Denied` lists only the denied permissions that were actually present in `Granted` (i.e., denials that had an effect). A denial of a permission never granted does not appear in `Denied`. `Denied` is de-duplicated and sorted ascending.

#### Output shape
- All three slices are non-nil even when empty.

### Edge cases
- A permission granted by one role and denied by another must be absent from `Effective` and present in `Denied`.
- A permission both granted and denied within the SAME role is still denied (deny wins).
- Empty `roles` yields three empty (non-nil) slices.
- `Resolve` must not mutate the caller's input or any role's `Grants`/`Denies` slice.

### Expected Functionality

| Scenario | Outcome |
| --- | --- |
| Same permission granted by two roles | Appears once in `Granted` |
| Permission granted then denied by another role | Excluded from `Effective`, listed in `Denied` |
| Deny for a never-granted permission | Absent from `Denied` and `Effective` |
| Grant and deny in same role | Deny wins |
| All permissions denied | `Effective` empty non-nil |
| Empty input | Three empty non-nil slices |

## Acceptance Criteria

- The package `github.com/samber/lo/examples/perm` compiles.
- `Resolve` satisfies every rule above, verified by the new table-driven test covering: grant union de-duplication, cross-role deny precedence, same-role deny precedence, exclusion of no-op denials from `Denied`, ascending sort of all slices, non-nil-empty outputs, and input-immutability (at least 10 assertions/cases total).
- The following command, run from the repository root, passes with no failures:

```
go test ./examples/perm/ -run TestResolve -count=1
```

- A naive implementation that leaves duplicates in `Granted`, lets denied permissions leak into `Effective`, lists no-op denials, or fails to sort must fail the test.
