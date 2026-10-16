# Task: Classify client-side cancellation in streaming handlers

## Background

In etcd's v3 RPC layer (`server/etcdserver/api/v3rpc`), streaming handlers (lease
keep-alive, watch) call `isClientCtxErr` to decide whether a stream error was caused by
the client going away (cancellation, deadline, disconnect) versus a genuine server-side
fault. This decision controls log severity and failure metrics, so it must read the
transport-level classification of the error rather than guess.

## Files to Create/Modify

- `server/etcdserver/api/v3rpc/util.go` (modify only if a real defect is found in
  `isClientCtxErr`; otherwise leave the production logic intact).
- `server/etcdserver/api/v3rpc/util_test.go` (modify) — add a test (e.g.
  `TestIsClientCtxErr`) that pins down the classification contract.

## Requirements

### Inputs

`isClientCtxErr` takes two arguments: the stream's context error (which is non-nil when
the server-side context was already cancelled) and the error returned by a send/receive.
It returns `true` when the error should be attributed to the client.

### Behavior that MUST hold

- If the context-error argument is non-nil, the result MUST be `true` regardless of the
  second argument (the server already observed cancellation).
- When the context-error argument is `nil`, the decision MUST be driven by the
  transport-level classification of the second error:
  - An error classified as cancelled or as deadline-exceeded MUST yield `true`.
  - An error classified as "unavailable" whose message is exactly the client-disconnect
    message MUST yield `true`.
  - An error classified as "unavailable" whose message describes a cancelled stream
    (begins with the stream-error prefix and ends with the cancel marker) MUST yield `true`.
  - An "unavailable" error with any other message MUST yield `false`.
  - An error carrying any other classification (for example a server-internal
    classification), or a plain non-transport Go error, MUST yield `false`.

### Constraints

- The decision MUST come from the error's transport classification and message, not from
  matching against the literal Go error string of arbitrary errors.
- A `nil` second error together with a `nil` context error MUST yield `false`.

### Expected Functionality

- non-nil context error + any error -> true.
- nil context error + cancelled-classified error -> true.
- nil context error + deadline-exceeded-classified error -> true.
- nil context error + unavailable error "client disconnected" -> true.
- nil context error + unavailable error matching the cancelled-stream pattern -> true.
- nil context error + unavailable error with an unrelated message -> false.
- nil context error + internal-classified error -> false.
- nil context error + plain Go error -> false.

## Acceptance Criteria

- The new test builds errors with `google.golang.org/grpc/status` and
  `google.golang.org/grpc/codes` (and a plain `errors.New`), and asserts the boolean
  result of `isClientCtxErr` for every scenario above.
- All existing v3rpc tests continue to pass.
- The following command, run from the repository root, MUST succeed:

  ```
  cd server && go test ./etcdserver/api/v3rpc/ -run TestIsClientCtxErr -count=1 -v
  ```
