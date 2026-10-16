# Task: Build a Parallel Media-Player Module

## Background

The `xstate` core package (`packages/core`) is the finite-state-machine runtime for this monorepo. This task adds a self-contained media-player module whose playback mode and mute mode evolve **independently and concurrently**, exercised by a new deterministic test.

## Files to Create/Modify

- `packages/core/test/fixtures/mediaPlayer.ts` (new) — the player module: a single exported factory plus any helper exports the test imports. Import everything you need from `../../src/index.ts`.
- `packages/core/test/mediaPlayer.test.ts` (new) — the deterministic test that drives the player through every scenario below.

You may import only from the package's public surface (`../../src/index.ts`); do not reach into internal files.

## Requirements

### Module surface

Export a factory `createMediaPlayer()` from `mediaPlayer.ts`. It must return something the test can start with the package's actor API, send events to, and read snapshots from. The player tracks two concurrent concerns that change on their own:

- **Playback**: one of **stopped**, **playing**, **paused**.
- **Sound**: one of **unmuted**, **muted**.

Both concerns must be readable simultaneously from a single snapshot; toggling one must never reset or disturb the other. Durable data must include a volume number, but the playback and sound modes themselves must be expressed as states, not data flags.

### Behavior

- Playback: from **stopped**, a play intent goes to **playing**; from **playing**, a pause intent goes to **paused** and a stop intent goes to **stopped**; from **paused**, a play intent resumes **playing** and a stop intent goes to **stopped**. A pause sent while **stopped** must be ignored.
- Sound: a mute-toggle intent flips between **unmuted** and **muted** regardless of playback mode. A "set volume" event updates the volume number; setting volume must not change the muted/unmuted mode.
- The two concerns must be able to hold any combination (e.g. **playing** + **muted**, **paused** + **unmuted**).

### Constraints and edge cases

- Mute-toggle and set-volume events must affect only the sound concern; play/pause/stop must affect only the playback concern. Neither family of events may reset the other concern to its initial state.
- The new volume travels with the set-volume event; the player must not stash a pending volume and apply it later.
- The player must expose a way for a consumer to read both the current playback mode and the current sound mode from the live snapshot without hard-coding the internal region path layout in the test (i.e. via the snapshot's own mode-matching capability).

### Expected Functionality

- start -> playback **stopped**, sound **unmuted**, volume at its initial value.
- play, mute-toggle -> playback **playing** AND sound **muted** simultaneously.
- from playing+muted, pause -> **paused** AND still **muted**.
- from paused+muted, mute-toggle -> **paused** AND **unmuted** (playback unchanged).
- set volume to 7 while **playing** -> volume = 7, playback still **playing**, sound mode unchanged.
- pause while **stopped** -> remains **stopped**.

## Acceptance Criteria

- Both new files exist at the paths above; the module imports solely from `../../src/index.ts`.
- Playback mode and sound mode are independent and both readable from a single snapshot via the snapshot's mode-matching capability; toggling one is asserted not to disturb the other.
- Each scenario in **Expected Functionality** is covered by at least one assertion, including a simultaneous-combination assertion and the ignored pause-while-stopped case.
- Volume is exposed on the snapshot and matches the last value supplied.
- The following command passes from the repository root:

  ```
  pnpm vitest run --project xstate packages/core/test/mediaPlayer.test.ts
  ```
