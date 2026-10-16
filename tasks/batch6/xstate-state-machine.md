# Task: Build a Traffic-Light Module with Pedestrian Crossing and History

## Background

The `xstate` core package (`packages/core`) is the finite-state-machine runtime for this monorepo. This task adds a self-contained traffic-light module whose phases advance on delays, which can be interrupted by a pedestrian crossing request and then resume the interrupted phase, exercised by a new deterministic test using simulated time.

## Files to Create/Modify

- `packages/core/test/fixtures/trafficLight.ts` (new) — the traffic-light module: a single exported factory plus any helper exports the test imports. Import everything you need from `../../src/index.ts`.
- `packages/core/test/trafficLight.test.ts` (new) — the deterministic test that drives the module through every scenario below using fake/simulated timers.

You may import only from the package's public surface (`../../src/index.ts`); do not reach into internal files.

## Requirements

### Module surface

Export a factory `createTrafficLight(config)` from `trafficLight.ts`. `config` carries the phase durations: `greenMs`, `yellowMs`, `redMs`. The factory must return something the test can start with the package's actor API, send events to, and read snapshots from.

The light cycles through three running phases — **green** -> **yellow** -> **red** -> **green** — advancing automatically after each phase's configured duration. The current phase, and whether the light is currently halted for a pedestrian, must be derivable purely from the reported state, not from data flags.

### Behavior

- On start, the light begins at **green** and, after `greenMs`, advances to **yellow**; after `yellowMs`, to **red**; after `redMs`, back to **green**; and so on indefinitely.
- A "pedestrian request" event halts the normal cycle and enters a distinct **walk** mode where no automatic phase advance happens.
- A "pedestrian clear" event leaves **walk** and resumes the running cycle **at the phase that was active when the request arrived**, restarting that phase's timer from the beginning.
- A pedestrian request while already in **walk** must be ignored.

### Constraints and edge cases

- Phase advancement is driven by configured delays, not by external ticks; the test must use simulated time to advance phases.
- The phase to resume after a pedestrian crossing must be recovered from the cycle's own remembered position, not reconstructed by guessing from a data field the module maintained by hand.
- Entering and leaving **walk** must not corrupt the configured durations or skip a phase: resuming restarts the interrupted phase fresh.

### Expected Functionality

- start -> **green**; advance `greenMs` -> **yellow**; advance `yellowMs` -> **red**; advance `redMs` -> **green** again.
- at **yellow**, pedestrian request -> **walk** (no advance even after large simulated time); pedestrian clear -> back to **yellow**; advancing `yellowMs` from there -> **red**.
- at **red**, pedestrian request, pedestrian request again (ignored, still **walk**), pedestrian clear -> back to **red**.
- after resuming a phase, advancing less than that phase's duration does not advance; advancing the full duration does.

## Acceptance Criteria

- Both new files exist at the paths above; the module imports solely from `../../src/index.ts`.
- Phase and walk-mode are queried through the snapshot's reported state; no data flags restate the phase.
- Each scenario in **Expected Functionality** is covered by at least one assertion, including the resume-to-interrupted-phase behavior and the ignored duplicate pedestrian request, all driven by simulated time (do not rely on real wall-clock waits).
- Resuming an interrupted phase restarts that phase's full timer, verified by partial-then-full time advances.
- The following command passes from the repository root:

  ```
  pnpm vitest run --project xstate packages/core/test/trafficLight.test.ts
  ```
