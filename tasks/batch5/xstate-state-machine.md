# Task: Build a Subscription Heartbeat Module

## Background

The `xstate` core package (`packages/core`) is the finite-state-machine runtime for this monorepo. This task adds a self-contained "connection" module that subscribes to an external push source which delivers messages over time and can fail or close, where the subscription must send events back into the machine as they arrive, exercised by a new deterministic test.

## Files to Create/Modify

- `packages/core/test/fixtures/heartbeatConnection.ts` (new) — the connection module: a single exported factory plus any helper exports the test imports. Import everything you need from `../../src/index.ts`.
- `packages/core/test/heartbeatConnection.test.ts` (new) — the deterministic test that drives the module through every scenario below.

You may import only from the package's public surface (`../../src/index.ts`); do not reach into internal files.

## Requirements

### Module surface

Export a factory `createHeartbeatConnection(config)` from `heartbeatConnection.ts`. `config` carries:

- `subscribe(onMessage, onClosed)` — a function that opens an external push source. It calls `onMessage(payload)` zero or more times as messages arrive, calls `onClosed(reason)` once if the source closes/fails, and returns a teardown function that the module must call when it stops listening. The module must not implement the source; it only wires this subscription into machine events that flow back over time.

The factory must return something the test can start with the package's actor API, send events to, and read snapshots from.

### Lifecycle behavior

- A started machine begins in a **connected** mode and immediately opens the subscription.
- Each delivered message must update durable data: a running count of messages received and the payload of the most recent message.
- If the source signals closed/failure, the machine moves to a terminal **closed** outcome that records the close reason text.
- A consumer "disconnect" intent stops listening (the teardown function must be invoked) and moves the machine to a terminal **disconnected** outcome. After either terminal outcome, further delivered messages must not change data or state.
- The current mode (connected, and each terminal outcome) must be derivable purely from the machine's reported state.

### Constraints and edge cases

- Messages arrive asynchronously over time and must be ingested as events the machine handles, not collected by reaching into context from outside.
- The teardown function returned by `subscribe` must be invoked exactly once when the machine leaves the **connected** mode for any reason (close, failure, or explicit disconnect).
- The most-recent-message payload and the close reason each travel with the event/callback that produced them; the machine must not stash placeholders to fill in later.
- A message delivered after a terminal outcome (e.g. teardown not yet observed by the source) must be ignored.

### Expected Functionality

- start -> **connected**, message count 0.
- source delivers "a" then "b" -> still **connected**, count = 2, latest payload = "b".
- source delivers "a", then signals closed with reason "server-gone" -> terminal **closed**, reason "server-gone", count = 1, teardown invoked once.
- start, deliver one message, consumer disconnects -> terminal **disconnected**, teardown invoked once; a further delivered message leaves count and state unchanged.

## Acceptance Criteria

- Both new files exist at the paths above; the module imports solely from `../../src/index.ts`.
- The subscription delivers messages as events over time that the machine ingests; the teardown is asserted to be invoked exactly once when leaving the connected mode.
- Mode/outcome is queried through the snapshot's reported state; message count and latest payload are read from the snapshot's context.
- Each scenario in **Expected Functionality** is covered by at least one assertion, including the close-reason path and the post-terminal ignored-message case.
- The following command passes from the repository root:

  ```
  pnpm vitest run --project xstate packages/core/test/heartbeatConnection.test.ts
  ```
