# Task: Add a Comment-Pragma Registry

## Background

Black recognizes special trailing comments such as `# fmt: off`, `# fmt: on`,
`# fmt: skip`, and `# type: ignore`, and must classify an arbitrary comment to
decide how it affects formatting. This task adds a self-contained pragma registry
to the `black` package that detects and classifies these directives, independent
of `black.comments`.

## Files to Create/Modify

- `src/black/pragma_registry.py` (new) — the registry module described below.
- `tests/test_pragma_registry.py` (new) — the deterministic unit tests for it.

The new module must live in the `black` package and import only from the Python
standard library.

## Requirements

### Public surface

`from black.pragma_registry import Pragma, classify_comment, PragmaError` must
succeed. The module exposes exactly an `enum.Enum` named `Pragma`, a function
`classify_comment`, and an exception `PragmaError` (a subclass of `ValueError`).

### `Pragma`

An `Enum` with exactly these members: `NONE`, `FMT_OFF`, `FMT_ON`, `FMT_SKIP`,
`TYPE_IGNORE`. (`NONE` represents an ordinary comment with no recognized directive.)

### `classify_comment(text)`

Given a comment string `text`, return the `Pragma` it represents. The argument
must begin with a `#` after optional leading whitespace; otherwise raise
`PragmaError`. Recognition rules (applied to the comment body after the `#`):

- Body equal to `fmt: off` (or `fmt:off`) -> `FMT_OFF`.
- Body equal to `fmt: on` (or `fmt:on`) -> `FMT_ON`.
- Body equal to `fmt: skip` (or `fmt:skip`) -> `FMT_SKIP`; additionally, a
  trailing `# fmt: skip` appended to any other comment (e.g.
  `# noqa: E501 # fmt: skip`) also classifies as `FMT_SKIP`.
- Body that starts with `type: ignore` (optionally followed by an error code in
  square brackets, e.g. `type: ignore[arg-type]`) -> `TYPE_IGNORE`.
- Anything else -> `NONE`.

Matching of the `fmt:`/`type:` keyword must be exact: the spacing around the colon
may be zero or one space (`fmt: off` and `fmt:off` both match) but unrelated
comments such as `# format: off` or `# fmtoff` must classify as `NONE`.

### Expected Functionality

| Input | Result |
|-------|--------|
| `"# fmt: off"` | `FMT_OFF` |
| `"#fmt:on"` | `FMT_ON` |
| `"# fmt: skip"` | `FMT_SKIP` |
| `"# noqa: E501 # fmt: skip"` | `FMT_SKIP` |
| `"# type: ignore"` | `TYPE_IGNORE` |
| `"# type: ignore[arg-type]"` | `TYPE_IGNORE` |
| `"# a normal comment"` | `NONE` |
| `"# format: off"` | `NONE` |

### Edge cases

- Leading whitespace before the `#` is allowed (`"   # fmt: off"` -> `FMT_OFF`).
- A non-comment string (no leading `#`) raises `PragmaError`.
- `"# typeignore"` and `"# type:ignoreextra"` classify as `NONE` (must not be
  matched as `TYPE_IGNORE`); `"# type: ignore"` and `"# type: ignore[x]"` do match.

## Acceptance Criteria

- The module exposes `Pragma`, `classify_comment`, and `PragmaError` with the
  behavior above.
- `tests/test_pragma_registry.py` contains at least 12 independent test cases
  (parametrized cases count individually) covering every `Pragma` member, the
  trailing-`fmt: skip` case, the `type: ignore[code]` case, the lookalike-`NONE`
  cases, and the missing-`#` `PragmaError` case.
- A naive implementation that merely checks for the substring `fmt` or `type`
  (and so misclassifies `# format: off` or `# typeignore`) fails the tests.
- The following command passes from the repository root:

  ```bash
  python -m pytest tests/test_pragma_registry.py -q
  ```

- Running the project's configured type checker over the new module reports no errors:

  ```bash
  mypy src/black/pragma_registry.py
  ```
