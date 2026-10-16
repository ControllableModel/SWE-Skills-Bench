# Task: Build a Form Machine that Emits Outcome Notifications

## Background

The `xstate` core package (`packages/core`) is the finite-state-machine runtime for this monorepo. This task adds a self-contained form module that, beyond tracking its own validity and submission, **notifies the surrounding system directly** when meaningful outcomes happen, so a consumer can react without polling context, exercised by a new deterministic test.

## Files to Create/Modify

- `packages/core/test/fixtures/notifyingForm.ts` (new) — the form module: a single exported factory plus any helper exports the test imports. Import everything you need from `../../src/index.ts`.
- `packages/core/test/notifyingForm.test.ts` (new) — the deterministic test that subscribes to outcome notifications and drives the form through every scenario below.

You may import only from the package's public surface (`../../src/index.ts`); do not reach into internal files.

## Requirements

### Module surface

Export a factory `createNotifyingForm(config)` from `notifyingForm.ts`. `config` carries:

- `submit(values)` — returns a promise that resolves to a confirmation id string on success and rejects (with an `Error`) on failure. The module only orchestrates this call.

The factory must return something the test can start with the package's actor API, send events to, read snapshots from, and **subscribe to outcome notifications** that the running form pushes out to the surrounding system (not merely values left in context).

The form tracks finite phases — **editing**, **submitting**, and terminal **submitted** — plus durable data: the current field value and a validity check (the value must be non-empty to be submittable).

### Behavior

- The form starts **editing** with an empty value.
- A "change" event sets the field value (carried by the event).
- A "submit" intent is acted on only when the value is non-empty; submitting moves to **submitting** and runs `submit(values)`. A submit with an empty value must be ignored and must emit a distinct **validation-failed** notification to the surrounding system.
- On a resolved submit, the form moves to terminal **submitted** and emits a **submitted** notification carrying the confirmation id.
- On a rejected submit, the form returns to **editing** (so the user can retry) and emits a **submit-failed** notification carrying the failure reason text.

### Constraints and edge cases

- Outcome notifications must be delivered to the surrounding system through the machine's own outward-notification mechanism, not by the consumer inspecting context after each transition.
- The confirmation id and failure reason travel with the async result that produced them; the form must not stash placeholders to reconstruct later.
- A change/submit event sent while a submit is in flight must not short-circuit the in-flight submission.
- The phase must be derivable purely from the reported state; whether a submit would currently be acted on must be answerable from the live snapshot's own capability check.

### Expected Functionality

- start, submit with empty value -> stays **editing**, a **validation-failed** notification is emitted, `submit` is never called.
- change value to "x", submit, `submit` resolves to "cnf-7" -> terminal **submitted**, a **submitted** notification carrying "cnf-7".
- change value to "x", submit, `submit` rejects with "busy" -> back to **editing**, a **submit-failed** notification carrying "busy"; a second submit then succeeds.

## Acceptance Criteria

- Both new files exist at the paths above; the module imports solely from `../../src/index.ts`.
- Outcome notifications are received by the test through subscribing to the machine's outward notifications; the test asserts on emitted notification payloads, not just context values.
- The phase is queried through the snapshot's reported state; "can submit now" is answered via the snapshot's own capability check rather than string comparisons in the test helper.
- Each scenario in **Expected Functionality** is covered by at least one assertion, including the validation-failed emission (with `submit` never invoked) and the reject-then-retry path.
- The following command passes from the repository root:

  ```
  pnpm vitest run --project xstate packages/core/test/notifyingForm.test.ts
  ```
