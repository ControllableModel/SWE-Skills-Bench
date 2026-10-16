# Task: Audit transaction-request size and key validation

## Background

In etcd's v3 KV service (`server/etcdserver/api/v3rpc`), every `Txn` RPC is screened by
`checkTxnRequest` before execution. This guard caps the number of operations per
transaction and rejects empty comparison keys, so oversized or malformed transactions are
turned away at the edge with a precise over-the-wire error instead of reaching the raft log.

## Files to Create/Modify

- `server/etcdserver/api/v3rpc/key.go` (modify) — `checkTxnRequest` (and only if needed,
  the helper it calls).
- `server/etcdserver/api/v3rpc/key_test.go` (modify) — add a test (e.g. `TestCheckTxnRequest`)
  covering the operation-count cap and the empty-comparison-key rule.

## Requirements

### Operation-count cap

The cap applies to the largest of the three operation lists in the request: the number of
comparisons, the number of success operations, and the number of failure operations. Given
a maximum `N`:

- A transaction whose largest list has at most `N` entries MUST be accepted (size-wise).
- A transaction whose largest list exceeds `N` MUST be rejected with the
  too-many-operations classification.
- The cap MUST be evaluated against the maximum across all three lists, not their sum: a
  transaction with `N` successes and `N` failures and `N` comparisons MUST still be
  accepted on size grounds.

### Empty comparison key

Every entry in the comparison list identifies a key. A comparison whose key is empty MUST
cause the transaction to be rejected with the empty-key classification.

### Nested-operation budget

When a success or failure entry is itself a nested transaction, the operations it contains
count against the remaining budget so that a request cannot smuggle unbounded work inside
nested transactions. A nested transaction that, together with the outer operations, pushes
the effective operation count past `N` MUST be rejected with the too-many-operations
classification. (The existing recursive budget mechanism MUST be preserved — do not loosen
it.)

### Error contract and ordering

- Each rejection MUST surface as the specific over-the-wire classification named above
  (too-many-operations, or empty-key), never an opaque/unknown classification and never a
  plain Go error.
- A transaction that is within the cap, has no empty comparison key, and whose operations
  are individually valid MUST return no error.

### Expected Functionality

- maxTxnOps=4, success list length 5 -> too-many-operations error.
- maxTxnOps=4, success/failure/comparison each length 4 -> accepted (size-wise).
- A comparison with an empty key -> empty-key error.
- A within-budget transaction with valid ops -> nil.

## Acceptance Criteria

- The new test builds requests with `*pb.TxnRequest` / `*pb.Compare` / `*pb.RequestOp`
  and asserts the returned error's `.Error()` against the matching `rpctypes` errors, and
  asserts `nil` for accepted cases.
- All existing v3rpc tests continue to pass.
- Validation is driven by list lengths and field values, not by string matching on messages.
- The following command, run from the repository root, MUST succeed:

  ```
  cd server && go test ./etcdserver/api/v3rpc/ -run TestCheckTxnRequest -count=1 -v
  ```
