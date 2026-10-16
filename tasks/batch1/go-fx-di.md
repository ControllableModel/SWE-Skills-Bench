# Task: Build a Pluggable Job-Runner Example Application

## Background

The `docs/ex` directory of the `go.uber.org/fx` repository is a standalone Go module (`go.uber.org/fx/docs`, with `replace go.uber.org/fx => ../`) that hosts small, self-contained example applications, each in its own package with a co-located `_test.go`. This task adds a new example app under that module that demonstrates how a long-running service collects independently-registered background workers and coordinates their boot and shutdown.

## Files to Create/Modify

- `docs/ex/job-runner/job.go` (new) — the `Job` abstraction and the shared run recorder.
- `docs/ex/job-runner/worker.go` (new) — two independent worker packages-worth of constructors that contribute jobs, kept in one file for simplicity.
- `docs/ex/job-runner/runner.go` (new) — the runner/scheduler that consumes all registered jobs and coordinates their boot/shutdown via the application lifecycle.
- `docs/ex/job-runner/app.go` (new) — the composition root exposing a single reusable `Module` that wires the whole example.
- `docs/ex/job-runner/job_runner_test.go` (new) — the deterministic test described in Acceptance Criteria.

All files use package name `jobrunner`. Reuse the existing `go.uber.org/fx/docs` module; do not create a new module or edit `go.mod`.

## Requirements

### Job abstraction and recorder

- Define an exported interface `Job` with a `Name() string` method and a `Run(ctx context.Context) error` method.
- Define an exported struct `Recorder` that safely records, in order, the events that happen during the application's life. It must be usable concurrently. Provide a method `Events() []string` that returns a copy of the recorded events in the order they occurred.
- The recorder must distinguish at minimum these event kinds, formatted exactly as:
  - `"start:<jobName>"` — recorded when a job begins running during application start.
  - `"stop:<jobName>"` — recorded when a job is drained during application stop.
  - `"scheduler:ready"` — recorded by the runner exactly once, after it has taken ownership of the full set of jobs and is about to begin running them.

### Independent workers contributing jobs

- Provide at least three distinct job constructors that each produce a `Job` with a distinct name (e.g. `"emailer"`, `"indexer"`, `"reporter"`). Each job's `Run` must record its own `"start:<name>"` event through the injected `Recorder`.
- The set of jobs must NOT be assembled by any single constructor enumerating the others. Each job must be registered independently, and the runner must receive the complete collection without referencing the individual job constructors by name. Adding a fourth job later must require only registering one more constructor, with no edit to the runner.

### Runner / scheduler coordination

- Define an exported `Runner` type that receives the full collection of registered `Job` values plus the `Recorder`.
- The runner must record `"scheduler:ready"` exactly once, and only after the whole application graph has been constructed — never from a constructor body, and never before every job constructor has been built.
- When the application starts, every registered job's `Run` must be executed (each producing its `"start:<name>"`), and `"scheduler:ready"` must appear in the recorded events strictly before any `"start:<name>"` event.
- When the application stops, the runner must drain the jobs, recording `"stop:<name>"` for every job that was started. Shutdown ordering relative to startup must be deterministic and reversible: the drain order of the jobs must be the exact reverse of the order in which they were started.
- Job execution and draining must not be triggered from constructor bodies; constructors must remain cheap and side-effect-free with respect to the recorder (constructors must never append `"start:"`, `"stop:"`, or `"scheduler:ready"` events).

### Composition root

- Expose a single exported variable `Module` (an `fx.Option`) that, when combined with a supplied `*Recorder`, produces a fully wired, bootable application: all jobs registered, the runner constructed, and the lifecycle coordination active.
- A consumer must be able to boot the example with nothing more than `Module` and a way to supply a `*Recorder`; no other wiring should be required.

### Edge cases & constraints

- The application graph must be valid: booting it must not produce a missing-dependency or cycle error.
- The recorder's `Events()` slice must never be mutated by callers in a way that affects the runner's internal state (return a copy).
- If the application is started and then stopped, the total number of `"stop:"` events must equal the total number of `"start:"` events.

## Expected Functionality

- Scenario: boot the app with three registered jobs → outcome: `Events()` contains exactly one `"scheduler:ready"`, followed by three `"start:"` events (one per job), and after stop, three matching `"stop:"` events.
- Scenario: register a fourth job constructor and re-boot → outcome: four `"start:"` and four `"stop:"` events appear with no change to `runner.go`.
- Scenario: inspect the recorded sequence → outcome: `"scheduler:ready"` precedes every `"start:"`, and the sub-sequence of `"stop:"` job names is the reverse of the sub-sequence of `"start:"` job names.

## Acceptance Criteria

- A new package `jobrunner` exists under `docs/ex/job-runner/` exposing `Job`, `Recorder` (with `Events() []string`), `Runner`, and `Module`.
- `docs/ex/job-runner/job_runner_test.go` boots the example using `fxtest.New(t, Module, fx.Supply(rec))` (where `rec` is a freshly constructed `*Recorder`), calls `RequireStart().RequireStop()`, and then asserts on `rec.Events()`:
  - exactly one `"scheduler:ready"` event is present;
  - `"scheduler:ready"` appears at an index strictly less than every `"start:"` event index;
  - the number of `"start:"` events equals the number of registered jobs (≥ 3) and equals the number of `"stop:"` events;
  - the ordered list of job names in `"stop:"` events is the exact reverse of the ordered list of job names in `"start:"` events.
- The naive/hardcoded approach fails: a constructor that simply appends fixed strings cannot satisfy the start-before-`scheduler:ready` ordering being enforced through actual boot/shutdown, nor the reverse drain order.
- The following command, run from the `docs` directory, passes:

  ```bash
  cd docs && go test ./ex/job-runner/...
  ```
