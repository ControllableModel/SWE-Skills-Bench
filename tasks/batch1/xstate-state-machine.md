# Task: Build a Document Approval Workflow Module

## Background

The `xstate` core package (`packages/core`) is the runtime for finite state machines and statecharts in this monorepo. This task adds a new self-contained workflow module under that package that models the lifecycle of a document moving through automated validation, human review, and publication, with the deterministic behavior exercised by a new test file.

## Files to Create/Modify

- `packages/core/test/fixtures/approvalWorkflow.ts` (new) — the workflow module: a single exported factory plus any helper exports the test imports. Import everything you need from `../../src/index.ts`.
- `packages/core/test/approvalWorkflow.test.ts` (new) — the deterministic test that drives the workflow through every scenario below.

You may import only from the package's public surface (`../../src/index.ts`); do not reach into internal files.

## Requirements

### Module surface

Export a factory `createApprovalWorkflow(config)` from `approvalWorkflow.ts`. `config` carries:

- `validate(doc)` — returns a promise that resolves when the document passes automated structural checks and rejects (with an `Error`) when it fails. The module must not implement validation rules itself; it only orchestrates this call.
- `publish(doc)` — returns a promise that resolves to a published-document id string, or rejects on failure.
- `reviewWindowMs` — how long a document may wait for a human decision before the workflow gives up on it.

`createApprovalWorkflow` must return something the test can start with the package's actor API, send events to, and read snapshots from. Validation and publication side effects must run only through the supplied `validate` / `publish` functions, and the document under review must be carried by the running workflow, not passed again on later events.

### Lifecycle behavior

A started workflow accepts a `doc` describing the document to process. From there:

1. The workflow first runs automated validation.
2. If validation rejects, the workflow ends in a terminal **rejected** outcome that records the failure reason text.
3. If validation resolves, the workflow waits for a human decision.
4. While waiting, a reviewer may approve or request changes. Approval moves the document toward publication; requesting changes ends the workflow in a terminal **changes-requested** outcome that records the reviewer's note.
5. If no human decision arrives within `reviewWindowMs`, the workflow abandons the document and ends in a terminal **expired** outcome.
6. On approval, the workflow runs publication. Success ends the workflow in a terminal **published** outcome that exposes the published id. Failure does **not** end the workflow: it returns to waiting for a human decision so the reviewer can retry by approving again or request changes instead.

### Constraints and edge cases

- The current lifecycle phase (validating, awaiting decision, publishing, and each terminal outcome) must be derivable purely from the workflow's reported status, not from boolean flags carried as data.
- A reviewer's approve / request-changes / any other decision event sent while validation or publication is still in flight must be ignored (it must not skip or short-circuit the in-flight phase).
- The expiry clock applies only to the human-decision wait. Time elapsed during validation or publication must not count against `reviewWindowMs`, and re-entering the waiting phase after a failed publication restarts the wait window.
- A reviewer note / failure reason must travel with its triggering event or async result; the workflow must not stash a placeholder earlier and reconstruct it later.
- The workflow must expose a way for a consumer to check, given the live snapshot, whether an approve event would currently be acted upon, without the consumer hard-coding phase names.

### Expected Functionality

- start with `{ doc }`, `validate` rejects ("missing title") -> terminal rejected, reason is `"missing title"`.
- `validate` resolves, reviewer approves, `publish` resolves to `"pub-42"` -> terminal published, published id is `"pub-42"`.
- `validate` resolves, reviewer requests changes with note "tone" -> terminal changes-requested, note is `"tone"`.
- `validate` resolves, no decision within `reviewWindowMs` -> terminal expired.
- `validate` resolves, reviewer approves, `publish` rejects, reviewer approves again, `publish` resolves -> terminal published.
- `validate` resolves, an approve event sent before validation settles is ignored: the workflow still publishes only after a post-validation approve.

## Acceptance Criteria

- Both new files exist at the paths above; the module imports solely from `../../src/index.ts`.
- The phase/outcome of the workflow is queried through the snapshot's reported state, and "can an approve be acted on now" is answered via the snapshot's own capability check rather than string comparisons in the test helper.
- Each scenario in **Expected Functionality** is covered by at least one assertion, including the post-publish-failure retry returning to the waiting phase and the expiry path driven by simulated time (use fake timers; do not rely on real wall-clock waits).
- Terminal outcomes carry the correct payloads: rejection reason text, reviewer note text, and published id string, each obtained from the event or async result that produced it.
- An out-of-phase decision event leaves the in-flight phase unchanged.
- The following command passes from the repository root:

  ```
  pnpm vitest run --project xstate packages/core/test/approvalWorkflow.test.ts
  ```
