# Task: Tighten range-request validation in the KV service

## Background

In etcd's v3 KV service (`server/etcdserver/api/v3rpc`), every incoming `Range`
RPC is screened by `checkRangeRequest` before it reaches storage. This guard is the
sole place where malformed read requests are rejected with the correct over-the-wire
error so that a client can tell a bad request apart from a transient failure.

## Files to Create/Modify

- `server/etcdserver/api/v3rpc/key.go` (modify) — extend `checkRangeRequest`.
- `server/etcdserver/api/v3rpc/key_test.go` (modify) — extend `TestCheckRangeRequest`
  (or add a sibling test) to cover the new behavior.

## Requirements

### Current behavior to preserve

A request with an empty key MUST still be rejected as an empty-key error, and a
request whose sort order or sort target is not one of the defined enum values MUST
still be rejected as an invalid-sort-option error. Every existing
`TestCheckRangeRequest` case MUST keep passing unchanged.

### Range-bound consistency

A range read may carry a `RangeEnd` that selects a half-open interval `[Key, RangeEnd)`.
The guard MUST reject a request whose bounds cannot describe a valid interval:

- When `RangeEnd` is non-empty and is lexicographically smaller than `Key`, the
  request describes an empty/inverted interval and MUST be rejected.
- The single-key form (empty `RangeEnd`) and the all-keys form (`RangeEnd` set to
  the single zero byte `\x00`, meaning "from Key to the end of the keyspace") MUST
  remain accepted.
- Equal `Key` and `RangeEnd` is a degenerate-but-defined case and MUST remain accepted
  (storage already returns an empty result for it).

### Negative pagination limit

A `Limit` field that is negative is meaningless for a read and MUST be rejected,
while a zero limit (meaning "no limit") and any positive limit MUST be accepted.

### Error contract

- Each rejection above MUST surface as an over-the-wire error whose classification is
  the one etcd already uses for malformed input (the same classification produced for an
  empty key or a bad sort option), not an opaque/unknown classification and not a plain
  Go error.
- A fully valid request MUST continue to return no error.
- Ordering: the empty-key check MUST take precedence over the new bound/limit checks
  (an empty-key request stays an empty-key error regardless of its other fields).

### Expected Functionality

- `Key="b"`, `RangeEnd="a"` -> rejected (inverted interval).
- `Key="a"`, `RangeEnd="b"` -> accepted.
- `Key="a"`, `RangeEnd=""` -> accepted (single key).
- `Key="a"`, `RangeEnd="\x00"` -> accepted (to end of keyspace).
- `Key="a"`, `RangeEnd="a"` -> accepted.
- `Limit=-1` -> rejected; `Limit=0` and `Limit=5` -> accepted.
- Empty key -> empty-key error regardless of other fields.

## Acceptance Criteria

- All existing `TestCheckRangeRequest` cases continue to pass.
- New cases prove: inverted-interval rejection, accepted forward/single/all-keys/equal
  ranges, negative-limit rejection, zero/positive-limit acceptance, and that the returned
  errors carry the malformed-input classification (compare with `.Error()` against the
  existing empty-key / invalid-sort errors, as `TestCheckRangeRequest` already does).
- The behavior is driven by field values, not by string matching on messages.
- The following command, run from the repository root, MUST succeed:

  ```
  cd server && go test ./etcdserver/api/v3rpc/ -run TestCheckRangeRequest -count=1 -v
  ```

  (If new cases live in a separate function, widen `-run` accordingly, e.g.
  `-run 'TestCheckRangeRequest|TestCheckRangeRequestBounds'`.)
