# Task: Strengthen put-request validation in the KV service

## Background

In etcd's v3 KV service (`server/etcdserver/api/v3rpc`), each `Put` RPC is validated by
`checkPutRequest` before it mutates storage. This guard is the only place where a
mutating write with self-contradictory fields is turned away with a precise over-the-wire
error, so the client knows the request was malformed rather than the cluster being at fault.

## Files to Create/Modify

- `server/etcdserver/api/v3rpc/key.go` (modify) — extend `checkPutRequest`.
- `server/etcdserver/api/v3rpc/key_test.go` (modify) — add a test (e.g. `TestCheckPutRequest`)
  that exercises the new behavior.

## Requirements

### Current behavior to preserve

A put with an empty key MUST stay rejected as an empty-key error. A put that sets
`IgnoreValue` while also carrying a non-empty `Value` MUST stay rejected as a
value-provided error. A put that sets `IgnoreLease` while also carrying a non-zero `Lease`
MUST stay rejected as a lease-provided error. None of these existing behaviors may change.

### Contradictory ignore flags

`IgnoreValue` means "keep the existing value"; `IgnoreLease` means "keep the existing
lease". When `IgnoreValue` is set, supplying a `Value` is contradictory; when `IgnoreLease`
is set, supplying a `Lease` is contradictory. The guard MUST detect these independently:

- `IgnoreValue=true` with empty `Value` -> accepted.
- `IgnoreValue=true` with non-empty `Value` -> rejected (value-provided classification).
- `IgnoreLease=true` with `Lease=0` -> accepted.
- `IgnoreLease=true` with `Lease!=0` -> rejected (lease-provided classification).

### Negative lease guard

A `Lease` identifier is never negative. A put carrying a negative `Lease` MUST be rejected
with the malformed-input classification (the same classification used for an empty key),
while `Lease=0` (no lease) and any positive lease MUST be accepted.

### Error contract and ordering

- Each rejection MUST surface as an over-the-wire error with the specific classification
  named above, never an opaque/unknown classification and never a plain Go error.
- The empty-key check MUST take precedence over every other check.
- A fully valid put (non-empty key, no contradictions, non-negative lease) MUST return no
  error.

### Expected Functionality

- Empty key -> empty-key error (even if other fields are also wrong).
- `IgnoreValue=true,Value="x"` -> value-provided error.
- `IgnoreLease=true,Lease=7` -> lease-provided error.
- `Lease=-1` -> malformed-input error.
- `Key="k",Value="v",Lease=3` -> accepted.

## Acceptance Criteria

- The new test asserts each scenario above by comparing the returned error's `.Error()`
  against the corresponding existing `rpctypes` error (empty-key, value-provided,
  lease-provided), and asserts `nil` for the accepted cases.
- No existing test in the package regresses.
- Validation is driven by field values, not by string matching on messages.
- The following command, run from the repository root, MUST succeed:

  ```
  cd server && go test ./etcdserver/api/v3rpc/ -run TestCheckPutRequest -count=1 -v
  ```
