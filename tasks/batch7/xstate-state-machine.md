# Task: Build a Persistable Counter-Session Module

## Background

The `xstate` core package (`packages/core`) is the finite-state-machine runtime for this monorepo. This task adds a self-contained "scored session" module whose full running state can be serialized and later restored so a session resumes exactly where it left off, exercised by a new deterministic test.

## Files to Create/Modify

- `packages/core/test/fixtures/scoredSession.ts` (new) — the session module: a single exported factory plus any helper exports the test imports. Import everything you need from `../../src/index.ts`.
- `packages/core/test/scoredSession.test.ts` (new) — the deterministic test that drives the module through every scenario below, including a save-and-restore round trip.

You may import only from the package's public surface (`../../src/index.ts`); do not reach into internal files.

## Requirements

### Module surface

Export from `scoredSession.ts`:

- `createScoredSession()` — returns the session definition, plus a way to start a fresh runnable session via the package's actor API.
- a helper that produces a runnable session **rehydrated from a previously saved snapshot** so that both the finite phase and the durable score are restored together.

The session has three finite phases — **idle**, **active**, **ended** — plus durable data: a numeric `score` and a `rounds` count.

### Behavior

- A fresh session starts **idle**.
- A "begin" intent moves **idle** -> **active** and resets `score` and `rounds` to zero.
- While **active**, a "score" event (carrying points) adds points to `score` and increments `rounds`. A "score" event sent while **idle** or **ended** must be ignored.
- An "end" intent moves **active** -> **ended**; from **ended**, only a "begin" can start a new session.
- The phase must be derivable purely from the reported state, not from data flags.

### Constraints and edge cases

- The points to add travel with the "score" event; the module must not stash pending points to apply later.
- Saving must capture the whole running state (phase plus durable data), and restoring must reconstruct both together — not by guessing a phase string and pasting a partial data blob. A session restored mid-**active** must continue accepting "score" events and accumulating onto the restored `score`/`rounds`.
- Restoring a session that was saved in **ended** must come back **ended** (further "score" events ignored) until "begin".

### Expected Functionality

- fresh start -> **idle**, score 0, rounds 0.
- begin, score +3, score +5 -> **active**, score 8, rounds 2.
- score while **idle** -> ignored (still idle, score 0).
- after begin and two score events, save the snapshot; build a new session restored from that snapshot -> resumes **active** with score and rounds intact; a further score +2 -> score 10, rounds 3.
- begin, end, save; restore -> comes back **ended**; a score event is ignored; begin -> **active** with score reset to 0.

## Acceptance Criteria

- Both new files exist at the paths above; the module imports solely from `../../src/index.ts`.
- The phase is queried through the snapshot's reported state; score and rounds are read from the snapshot's context.
- Saving captures the full running state and restoring reconstructs phase and durable data together; the restore round trip is exercised by at least one assertion that continues accumulating after rehydration.
- Each scenario in **Expected Functionality** is covered by at least one assertion, including the ignored-score-when-idle case and the restored-**ended** case.
- The following command passes from the repository root:

  ```
  pnpm vitest run --project xstate packages/core/test/scoredSession.test.ts
  ```
