# Task: Add a Human-Readable Byte-Size Formatter to the Output Format Package

## Background

The `internal/command/format` package contains helpers Terraform uses to render CLI output (diagnostics, object ids, and related trivia). It currently has no helper for rendering byte counts in a human-friendly way, which several commands could use when reporting plan/state payload sizes. This task adds a deterministic, self-contained byte-size formatter.

## Files to Create/Modify

- `internal/command/format/bytesize.go` (new) — a self-contained formatter in package `format`.
- `internal/command/format/bytesize_test.go` (new) — the deterministic test for the new helper.

The new code must live in the existing `format` package and must not perform any I/O or use randomness.

## Requirements

### `HumanByteSize`

Add an exported function:

```go
func HumanByteSize(n int64) string
```

It renders a byte count using binary (1024-based) units.

Behavior and constraints:

- Units, in increasing order: `B`, `KiB`, `MiB`, `GiB`, `TiB`, `PiB`. Each step is a factor of `1024`.
- Values below `1024` render as an integer count of bytes followed by a space and `B` — e.g. `0` -> `"0 B"`, `512` -> `"512 B"`, `1023` -> `"1023 B"`.
- At or above `1024`, divide into the largest unit for which the value is at least `1`, and render the scaled value with **exactly two decimal places**, a space, then the unit — e.g. `1024` -> `"1.00 KiB"`, `1536` -> `"1.50 KiB"`, `1048576` -> `"1.00 MiB"`.
- Rounding is half-away-from-zero to two decimals (e.g. `1127` bytes -> `"1.10 KiB"`).
- Negative inputs render with a leading `-` applied to the formatted magnitude — e.g. `-2048` -> `"-2.00 KiB"`, `-100` -> `"-100 B"`.
- Very large values that exceed `PiB` still use `PiB` (the largest unit) rather than overflowing to a missing unit.

### Expected Functionality

- `1` -> `"1 B"`; `1023` -> `"1023 B"`; `1024` -> `"1.00 KiB"`.
- `2_621_440` -> `"2.50 MiB"`.
- `1_099_511_627_776` -> `"1.00 TiB"`.

## Acceptance Criteria

The new test file `internal/command/format/bytesize_test.go` must exercise `HumanByteSize` using `github.com/stretchr/testify` (the project already depends on it) and must cover, at minimum:

- the raw-bytes branch (`< 1024`) including `0` and `1023`;
- exact unit boundaries (`1024`, `1048576`, `1073741824`) rendering `1.00 KiB`/`1.00 MiB`/`1.00 GiB`;
- two-decimal rendering and rounding behavior for non-exact values;
- negative inputs in both the raw-bytes and scaled branches;
- a value beyond `PiB` still rendering with the `PiB` unit.

The following command, run from the repository root, must pass:

```
go test ./internal/command/format/ -run TestHumanByteSize -v
```
