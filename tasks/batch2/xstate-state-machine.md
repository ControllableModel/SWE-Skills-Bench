# Task: Build a Multi-Step Checkout Wizard Module

## Background

The `xstate` core package (`packages/core`) is the finite-state-machine runtime for this monorepo. This task adds a self-contained checkout-wizard module that models a linear, step-by-step purchase flow with forward/back navigation, per-step validity, and a terminal confirmation, exercised by a new deterministic test.

## Files to Create/Modify

- `packages/core/test/fixtures/checkoutWizard.ts` (new) — the wizard module: a single exported factory plus any helper exports the test imports. Import everything you need from `../../src/index.ts`.
- `packages/core/test/checkoutWizard.test.ts` (new) — the deterministic test that drives the wizard through every scenario below.

You may import only from the package's public surface (`../../src/index.ts`); do not reach into internal files.

## Requirements

### Module surface

Export a factory `createCheckoutWizard()` from `checkoutWizard.ts`. It must return something the test can start with the package's actor API, send events to, and read snapshots from. The wizard models exactly three ordered steps — **cart**, **shipping**, **payment** — followed by a terminal **confirmed** outcome.

Collected step data (cart line count, a shipping address string, a payment token string) must be carried by the running wizard as durable data. The currently active step, and whether the flow has reached confirmation, must be derivable purely from the wizard's reported state, not from booleans carried as data.

### Navigation behavior

- The wizard starts on the **cart** step.
- A "continue" intent advances to the next step, but only when the current step's data requirement is satisfied: cart requires at least one line; shipping requires a non-empty address; payment requires a non-empty token. A continue sent while the current step is unsatisfied must leave the wizard on the same step.
- A "back" intent returns to the previous step. Back from the first step (**cart**) must leave the wizard on **cart**. Back must never discard data already collected for steps the user has visited.
- From the **payment** step, a continue (when payment data is present) reaches the terminal **confirmed** outcome. Once confirmed, further continue/back/data events must not change the state.

### Constraints and edge cases

- Each step's collected value travels in with the event that sets it; the wizard must not stash a placeholder for a step and reconstruct it on a later transition.
- The wizard must expose a way for a consumer to check, given the live snapshot, whether a "continue" event would currently be acted upon (i.e. whether the active step is satisfied), without the consumer hard-coding step names.
- Returning **back** to an earlier step and editing its data, then continuing again, must reflect the edited value at confirmation.

### Expected Functionality

- start, continue on empty cart -> stays on **cart**.
- set cart lines to 2, continue -> **shipping**; set address "10 Main", continue -> **payment**; set token "tok_1", continue -> terminal **confirmed**, with cart=2, address="10 Main", token="tok_1".
- on **payment**, back -> **shipping**; back -> **cart**; back -> **cart** (clamped); collected data retained.
- reach **shipping**, back to **cart**, edit cart lines to 5, continue -> **shipping** with previously entered address still present.
- after **confirmed**, sending continue/back/set-data leaves state and data unchanged.

## Acceptance Criteria

- Both new files exist at the paths above; the module imports solely from `../../src/index.ts`.
- The active step and the confirmed outcome are queried through the snapshot's reported state; "can continue now" is answered via the snapshot's own capability check rather than string comparisons in the test helper.
- Each scenario in **Expected Functionality** is covered by at least one assertion, including the back-clamp at the first step and the edit-then-reconfirm path.
- Final collected data (cart line count, address, payment token) is exposed on the snapshot and matches the last values supplied for each step.
- The following command passes from the repository root:

  ```
  pnpm vitest run --project xstate packages/core/test/checkoutWizard.test.ts
  ```
