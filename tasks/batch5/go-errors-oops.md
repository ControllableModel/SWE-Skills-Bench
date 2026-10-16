# Task: Build a Panic-Safe Job Runner Module

## Background

The `samber/oops` repository ships several self-contained demonstration modules under `examples/` (each its own Go module, wired into the workspace via `go.work`). This task adds a new example module, `examples/jobrunner`, that runs a batch of user-supplied job functions where any individual job may panic, and collects all outcomes into a single aggregate error without letting any panic crash the process.

## Files to Create/Modify

- `examples/jobrunner/jobrunner.go` (new) — the runner and its panic-safe execution helper.
- `examples/jobrunner/jobrunner_test.go` (new) — the deterministic tests described below.
- `examples/jobrunner/go.mod` (new) — module `github.com/samber/oops/examples/jobrunner`, Go 1.21, requiring `github.com/samber/oops`.
- `go.work` (modify) — add `./examples/jobrunner` to the `use (...)` block.

## Requirements

The module executes jobs sequentially in-process (no goroutines required, no scheduler, no network). Each job is a `func() error`.

### Domain types

Define in `examples/jobrunner/jobrunner.go`:

- `Job struct { Name string; Run func() error }`

### Per-job safe execution

Provide:

```go
func RunOne(job Job) error
```

`RunOne` executes `job.Run`. If `job.Run` returns an error, `RunOne` returns it as a `samber/oops` error annotated with domain `"job-runner"`, context `"job"` equal to `job.Name`, and code `"job_failed"`. If `job.Run` **panics**, `RunOne` MUST recover the panic (the panic MUST NOT escape) and return a `samber/oops` error with code `"job_panic"`, domain `"job-runner"`, and context `"job"` equal to `job.Name`. If `job.Run` returns `nil`, `RunOne` returns `nil`.

### Batch aggregation

Provide:

```go
func RunAll(jobs []Job) error
```

`RunAll` executes every job via `RunOne` (so one panicking job does not prevent later jobs from running) and combines the non-nil results into a **single** aggregate error such that:

- if no job fails, `RunAll` returns `nil`.
- if one or more jobs fail/panic, the returned error MUST satisfy `oops.AsOops(err)` (`ok == true`) and MUST report each failed job through Go's standard `errors.Is` against the corresponding individual error value — i.e. the aggregate unwraps to each contributing error.
- the number of contributing errors MUST equal the number of failed/panicked jobs (successful jobs contribute nothing).

### Expected Functionality

- `RunOne(Job{Name:"ok", Run: func() error { return nil }})` -> `nil`.
- `RunOne(Job{Name:"bad", Run: func() error { return errors.New("x") }})` -> oops error, code `job_failed`, context `job == "bad"`.
- `RunOne(Job{Name:"boom", Run: func() error { panic("kaboom") }})` -> oops error, code `job_panic`, context `job == "boom"`, no panic propagates.
- `RunAll` over `[ok, bad, boom, ok]` -> single non-nil aggregate that unwraps (via `errors.Is`) to both the `bad` failure and the `boom` failure, and runs the trailing `ok` job (proving execution did not stop at the panic).
- `RunAll` over all-succeeding jobs -> `nil`.

## Acceptance Criteria

- `examples/jobrunner/go.mod` declares module `github.com/samber/oops/examples/jobrunner` and `go.work` lists `./examples/jobrunner`.
- A naive implementation that stops at the first panic, or lets a panic escape, fails the tests.
- The added tests are deterministic and pass:

```
go test ./examples/jobrunner/...
```

  run from the repository root, including the success/failure/panic `RunOne` cases and the `RunAll` aggregation case that asserts both failures are reachable via `errors.Is` and that a job after a panicking job still executed.
