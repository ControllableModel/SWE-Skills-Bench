# Task: Validate server-streaming watch fragmentation

## Background

In etcd's v3 Watch service (`server/etcdserver/api/v3rpc`), `sendFragments` splits a
`WatchResponse` that is too large for a single message into a sequence of smaller messages
streamed to the client. This keeps individual messages under the transport size limit while
preserving event order, and only the final message in a fragmented sequence is marked as
non-fragment so the client knows the stream of fragments has ended.

## Files to Create/Modify

- `server/etcdserver/api/v3rpc/watch.go` (modify only if a real defect is found; otherwise
  leave the production logic intact).
- `server/etcdserver/api/v3rpc/watch_test.go` (modify) — add a test (e.g.
  `TestSendFragmentsOrdering`) that complements the existing `TestSendFragment` by checking
  ordering and the fragment flags, not only the fragment count.

## Requirements

### Inputs and capture

`sendFragments` takes a `*pb.WatchResponse`, a maximum message size, and a send callback.
The test MUST capture every response handed to the callback so it can inspect the full
emitted sequence.

### Behavior that MUST hold

- When the whole response fits under the limit, or has fewer than two events, exactly one
  message MUST be emitted and that message MUST carry the original (non-fragment) flag.
- When fragmentation occurs, concatenating the `Events` of the emitted messages in order
  MUST reproduce the original event sequence exactly (same count, same order, no
  duplication, no loss).
- In a fragmented sequence, every emitted message except the last MUST have its fragment
  flag set, and the last message MUST have its fragment flag cleared.
- A single event larger than the limit MUST still be emitted on its own (forward progress
  is guaranteed even when one event alone exceeds the limit).

### Constraints

- The callback MUST return no error in the test scenarios; the test asserts that
  `sendFragments` returns no error in those scenarios.
- The assertions MUST be on the emitted messages' contents and flags, not on log output.

### Expected Functionality

- Small response (fits, or <2 events) -> one message, fragment flag false.
- Large response of N events forced to fragment -> concatenated events equal the original N
  in order; all but the last message have fragment=true; last has fragment=false.
- One oversized event among several -> still emitted, ordering preserved.

## Acceptance Criteria

- The new test reuses (or mirrors) the existing `createResponse` helper to build
  `*pb.WatchResponse` values, captures emitted messages via the send callback, and asserts:
  event ordering/equality across the concatenated fragments, the fragment-flag pattern
  (all-but-last true, last false), the single-message case, and a nil return value.
- The existing `TestSendFragment` continues to pass.
- The following command, run from the repository root, MUST succeed:

  ```
  cd server && go test ./etcdserver/api/v3rpc/ -run 'TestSendFragment|TestSendFragmentsOrdering' -count=1 -v
  ```
