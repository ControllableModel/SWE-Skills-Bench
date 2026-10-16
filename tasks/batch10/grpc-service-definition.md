# Task: Gate which RPCs a learner member may serve

## Background

In etcd's v3 RPC layer (`server/etcdserver/api/v3rpc`), a learner member is a non-voting
node that may only serve a restricted set of requests. The interceptor consults
`isRPCSupportedForLearner` for each incoming unary request and rejects anything the learner
is not allowed to serve, so that reads that must be linearizable—or any mutation—never reach
a learner. This predicate is the single source of truth for that policy.

## Files to Create/Modify

- `server/etcdserver/api/v3rpc/util.go` (modify only if a real defect is found; otherwise
  leave the production logic intact).
- `server/etcdserver/api/v3rpc/util_test.go` (modify) — add a test (e.g.
  `TestIsRPCSupportedForLearner`) that pins down the policy.

## Requirements

### Allowed and disallowed requests

`isRPCSupportedForLearner` takes a request value (`any`) and returns whether a learner may
serve it:

- A status request MUST be allowed.
- A range (read) request MUST be allowed ONLY when it is marked serializable; a range
  request that is not serializable MUST be disallowed (a linearizable read needs the leader).
- Any other request type—put, delete-range, txn, compaction, lease, auth, member, and any
  unrecognized type—MUST be disallowed.

### Robustness

- A request value whose concrete type is none of the recognized types (including an
  arbitrary unrelated value) MUST be disallowed rather than cause a panic.

### Constraints

- The decision MUST be based on the request's concrete type and, for range requests, on the
  serializable flag—not on any string representation of the request.

### Expected Functionality

- `*pb.StatusRequest` -> allowed.
- `*pb.RangeRequest{Serializable: true}` -> allowed.
- `*pb.RangeRequest{Serializable: false}` -> disallowed.
- `*pb.PutRequest`, `*pb.DeleteRangeRequest`, `*pb.TxnRequest`,
  `*pb.CompactionRequest` -> disallowed.
- An unrelated value (e.g. a plain string) -> disallowed, no panic.

## Acceptance Criteria

- The new test constructs the request values above and asserts the boolean result of
  `isRPCSupportedForLearner` for each, including the serializable-versus-linearizable range
  distinction and the no-panic behavior for an unrelated value.
- All existing v3rpc tests continue to pass.
- The following command, run from the repository root, MUST succeed:

  ```
  cd server && go test ./etcdserver/api/v3rpc/ -run TestIsRPCSupportedForLearner -count=1 -v
  ```
