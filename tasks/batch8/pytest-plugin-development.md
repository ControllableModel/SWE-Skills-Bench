# Task: Add a test-outcome counts summary aggregator with an exhaustive test suite

## Background

The pytest codebase (`pytest-dev/pytest`) summarizes a run as counts of passed /
failed / skipped / xfailed / error outcomes and renders a one-line summary (see
`src/_pytest/terminal.py`). This task adds a small, self-contained module under
`src/_pytest/` that aggregates outcomes and formats the summary line, plus a
thorough test module under `testing/`.

## Files to Create/Modify

- `src/_pytest/_outcomestats.py` (new) — the utility module described below.
- `testing/test_outcomestats_util.py` (new) — the test module for the utility.

## Requirements

Implement `src/_pytest/_outcomestats.py` as a pure, dependency-free module (only
the Python standard library and `from __future__ import annotations` are allowed
— no imports from other `_pytest` modules). It MUST export exactly the following
with the listed behavior. The test module `testing/test_outcomestats_util.py`
MUST verify every behavior, constraint, and edge case enumerated here, including
each distinct failure mode.

### `OutcomeStats` (class)

- Constructed with no arguments; starts with all counts at zero.
- `record(outcome: str) -> None` increments the count for one of the allowed
  outcomes: `"passed"`, `"failed"`, `"skipped"`, `"xfailed"`, `"xpassed"`,
  `"error"`. An unknown outcome MUST raise `ValueError` containing the value.
- `count(outcome: str) -> int` returns the current count for a valid outcome and
  raises `ValueError` for an unknown one.
- `total` (property) returns the sum of all recorded outcomes.
- `failed_total` (property) returns `failed + error` (the outcomes that make a
  run non-green).
- `merge(other: OutcomeStats) -> OutcomeStats` returns a NEW `OutcomeStats` whose
  counts are the element-wise sum; neither operand is mutated.

### `summary_line(stats: OutcomeStats) -> str`

- Renders a comma-joined summary in this fixed order, omitting any outcome whose
  count is zero: `passed`, `failed`, `skipped`, `xfailed`, `xpassed`, `error`.
- Each present outcome is rendered as `"<n> <name>"`, e.g. `"3 passed, 1 failed"`.
- When `total == 0`, returns the literal string `"no tests ran"`.

### Expected Functionality

- Recording 3 passes and 1 failure then calling `summary_line` returns
  `"3 passed, 1 failed"`.
- `merge` is commutative for counts: `a.merge(b)` and `b.merge(a)` produce equal
  count vectors, and `total` of the merge equals `a.total + b.total`.
- `failed_total` reflects both `failed` and `error` and is unaffected by
  `skipped`/`xfailed`.

### Constraints

- All behavior is deterministic and free of I/O and global mutable state.
- No third-party packages and no other `_pytest` imports.
- `record`, `count`, and `merge` MUST never silently accept an invalid outcome
  name.

## Acceptance Criteria

- `src/_pytest/_outcomestats.py` exists and exports `OutcomeStats` and
  `summary_line` with the behavior specified above.
- `testing/test_outcomestats_util.py` contains test functions asserting:
  zero-init, recording and counting each valid outcome, the unknown-outcome
  error for both `record` and `count`, `total`, `failed_total` (including its
  independence from skipped/xfailed), non-mutating `merge` with its sum and
  commutativity, the fixed-order zero-omitting `summary_line`, and the
  `"no tests ran"` empty case.
- The following command passes with every test collected and no failures:

  ```
  python -m pytest testing/test_outcomestats_util.py -p no:cacheprovider -q
  ```

- A partial or hardcoded implementation that does not handle each enumerated edge
  case MUST cause at least one assertion in `testing/test_outcomestats_util.py`
  to fail.
