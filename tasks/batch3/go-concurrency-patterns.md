# Task: Add a Bounded Work Pool to lib/routine

## Background

Consul's `lib/routine` package (`lib/routine/routine.go`) manages the lifecycle
of long-lived background goroutines via a `Manager`. A separate need across the
agent is to fan a finite batch of independent jobs out across a bounded number
of workers, collect the first error, and cancel the rest. This task adds a
reusable bounded work pool to the same package.

## Files to Create/Modify

- `lib/routine/pool.go` (new) — the work-pool type and its public API.
- `lib/routine/pool_test.go` (new) — deterministic tests that run clean under `go test -race`.

## Requirements

Add an exported type to package `routine` that runs a set of submitted jobs
concurrently with a configurable maximum parallelism. Each job is a function
that takes a `context.Context` and returns an `error`. The exact method/field
names are up to you, but the public surface must support the scenarios below.

### Construction and submission

- A constructor accepts a maximum concurrency limit (a positive integer) and a
  parent `context.Context`, and returns a ready-to-use pool.
- Callers submit jobs to the pool. At no point may more than the configured
  number of jobs be executing simultaneously, even when far more jobs are
  submitted than the limit.
- Each running job receives a context derived from the pool's parent context.

### Waiting and error handling

- A caller can wait for all submitted jobs to finish. The wait returns the first
  non-nil error reported by any job (or nil if all jobs succeeded).
- When any job returns an error, the context passed to all still-running and
  not-yet-started jobs must be cancelled, so cooperative jobs can stop early.
  Jobs that have not started when cancellation occurs must not run their body.
- When the parent context is cancelled by the caller, in-flight jobs receive
  cancellation through their context and the wait returns promptly.

### Concurrency and safety

- Submitting jobs from multiple goroutines concurrently must be safe.
- The maximum-parallelism guarantee must hold under the race detector: at no
  instant may the number of concurrently executing job bodies exceed the limit.
- No goroutine started by the pool may remain running after all jobs have
  completed and the caller has waited. The implementation must be free of data
  races and must not leak goroutines across repeated create/use/wait cycles.

### Expected Functionality

- Submit 20 jobs with a limit of 3, each recording the peak observed concurrency -> the recorded peak never exceeds 3 and all 20 run.
- Submit several jobs where one returns an error -> the wait returns that error and not-yet-started jobs observe a cancelled context.
- Submit long-running cooperative jobs, then cancel the parent context -> jobs see cancellation and the wait returns promptly.
- Submit only successful jobs -> the wait returns a nil error.

## Acceptance Criteria

- A new file `lib/routine/pool.go` exists in package `routine` exposing an
  exported bounded work-pool type with a constructor taking a max-concurrency
  limit and a parent context, a job-submission operation, and a wait operation
  that returns the first job error.
- The package builds: `go build ./lib/routine/` succeeds.
- All scenarios above are covered by deterministic tests in
  `lib/routine/pool_test.go`, including: the concurrency cap never being
  exceeded, first-error propagation with cancellation of remaining jobs,
  parent-context cancellation, and the all-success case.
- The following command passes with no failures and no race-detector or
  goroutine-leak reports:

  ```
  go test -race -run 'Pool' ./lib/routine/
  ```

- Tests must not rely on `time.Sleep` to assert ordering or completion; use
  synchronization primitives so the suite finishes deterministically well within
  the package's default test timeout.
