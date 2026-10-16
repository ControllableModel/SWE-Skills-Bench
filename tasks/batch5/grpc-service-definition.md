# Task: Verify duplicate-key detection across transaction operations

## Background

In etcd's v3 KV service (`server/etcdserver/api/v3rpc`), `checkIntervals` walks the
operations of a `Txn` request and rejects any transaction in which two writes touch the
same key or a write overlaps a delete range, because such a transaction has no
well-defined result. This is the guard that turns conflicting intra-transaction writes
into a precise over-the-wire error before execution.

## Files to Create/Modify

- `server/etcdserver/api/v3rpc/key.go` (modify only if a real defect is found; otherwise
  leave the production logic intact).
- `server/etcdserver/api/v3rpc/key_test.go` (modify) — add a test (e.g. `TestCheckIntervals`)
  that pins down the overlap-detection contract.

## Requirements

### Conflict cases that MUST be rejected

`checkIntervals` takes a slice of operations and MUST report a duplicate-key
classification when:

- Two `Put` operations target the same key.
- A `Put` targets a key that falls inside a `DeleteRange` interval `[Key, RangeEnd)`
  present in the same operation set.
- A `Put` targets a key equal to a single-key `Delete` (empty `RangeEnd`).

### Cases that MUST be accepted

The function MUST return no error (and the put/delete sets it produces) when:

- All `Put` keys are distinct and none overlaps any delete.
- A `Put` and a `DeleteRange` touch disjoint key spans.
- The operation set is empty.

### Nested then/else exclusivity

When operations are nested transactions, a key that appears in the `then` branch and the
`else` branch of the same nested transaction MUST NOT be treated as a conflict (the two
branches are mutually exclusive at runtime). A genuine conflict that spans the same branch,
or a nested put overlapping an outer delete, MUST still be rejected.

### Error contract

- Every rejection MUST surface the duplicate-key over-the-wire classification, never an
  opaque/unknown classification and never a plain Go error.
- Detection MUST be driven by the keys and ranges in the request, not by string matching
  on error messages.

### Expected Functionality

- Two puts on `"k"` -> duplicate-key error.
- Put `"b"` plus delete range `["a","c")` -> duplicate-key error.
- Put `"a"` plus delete range `["b","c")` -> accepted.
- Same key in then-branch and else-branch of one nested txn -> accepted.
- Empty operation slice -> accepted.

## Acceptance Criteria

- The new test constructs `[]*pb.RequestOp` values (using `pb.RequestOp_RequestPut`,
  `pb.RequestOp_RequestDeleteRange`, and `pb.RequestOp_RequestTxn`) and asserts, for each
  scenario, either the duplicate-key error (`.Error()` compared against the existing
  `rpctypes` duplicate-key error) or a nil error.
- All existing v3rpc tests continue to pass.
- The following command, run from the repository root, MUST succeed:

  ```
  cd server && go test ./etcdserver/api/v3rpc/ -run TestCheckIntervals -count=1 -v
  ```
