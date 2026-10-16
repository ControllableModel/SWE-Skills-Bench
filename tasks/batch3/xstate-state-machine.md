# Task: Build a Retrying Upload Module with Backoff

## Background

The `xstate` core package (`packages/core`) is the finite-state-machine runtime for this monorepo. This task adds a self-contained file-upload module that retries a failing async upload a bounded number of times with delayed backoff, then either succeeds or gives up, exercised by a new deterministic test using simulated time.

## Files to Create/Modify

- `packages/core/test/fixtures/uploadWithRetry.ts` (new) — the upload module: a single exported factory plus any helper exports the test imports. Import everything you need from `../../src/index.ts`.
- `packages/core/test/uploadWithRetry.test.ts` (new) — the deterministic test that drives the module through every scenario below using fake/simulated timers.

You may import only from the package's public surface (`../../src/index.ts`); do not reach into internal files.

## Requirements

### Module surface

Export a factory `createUploadMachine(config)` from `uploadWithRetry.ts`. `config` carries:

- `upload(payload)` — returns a promise that resolves to an upload id string on success and rejects (with an `Error`) on failure. The module must not implement upload logic; it only orchestrates this call.
- `maxAttempts` — total number of upload attempts allowed (including the first).
- `backoffMs` — the delay to wait before each retry.

The factory must return something the test can start with the package's actor API, send events to, and read snapshots from. The payload to upload must be carried by the running machine, not re-supplied on later events.

### Lifecycle behavior

- A started machine accepts a `payload`, then immediately runs the first upload attempt.
- On a resolved upload, the machine ends in a terminal **succeeded** outcome exposing the returned upload id, recording how many attempts were used.
- On a rejected upload, if fewer than `maxAttempts` attempts have been made, the machine waits `backoffMs` and then runs another attempt. If `maxAttempts` is reached, the machine ends in a terminal **failed** outcome that records the last failure reason text and the attempt count.
- The current phase (uploading, waiting-to-retry, and each terminal outcome) must be derivable purely from the machine's reported state, not from boolean flags carried as data.

### Constraints and edge cases

- The backoff delay applies only to the wait-before-retry phase; time spent inside an in-flight upload must not count toward `backoffMs`.
- The attempt counter must be durable data on the machine and must equal the number of `upload` invocations actually made.
- The last failure reason recorded on a terminal **failed** outcome must travel from the rejection that produced it, not from an earlier placeholder.
- Events sent while an upload is in flight that are not part of the retry protocol must not skip or short-circuit the in-flight attempt.

### Expected Functionality

- `upload` resolves to `"up-1"` on the first attempt -> terminal **succeeded**, id `"up-1"`, attempts = 1.
- `maxAttempts` = 3, `upload` rejects twice then resolves to `"up-9"` on the third -> terminal **succeeded**, id `"up-9"`, attempts = 3, with each retry separated by `backoffMs` of simulated time.
- `maxAttempts` = 2, `upload` always rejects with "503" -> terminal **failed**, reason `"503"`, attempts = 2.
- During the wait-to-retry window, advancing simulated time by less than `backoffMs` does not trigger the next attempt; advancing the full `backoffMs` does.

## Acceptance Criteria

- Both new files exist at the paths above; the module imports solely from `../../src/index.ts`.
- The phase/outcome and attempt count are queried through the snapshot's reported state and context; no boolean phase flags are carried as data.
- Each scenario in **Expected Functionality** is covered by at least one assertion, including the success-after-retries path and the give-up path, with retry timing driven by simulated time (do not rely on real wall-clock waits).
- Terminal outcomes carry correct payloads: success id and attempt count on success; last failure reason and attempt count on failure.
- The following command passes from the repository root:

  ```
  pnpm vitest run --project xstate packages/core/test/uploadWithRetry.test.ts
  ```
