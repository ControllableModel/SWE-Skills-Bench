# Task: Add Recursive File Inclusion to ripgrep's Config Parser

## Background

ripgrep reads a "configuration rc" file (pointed to by `RIPGREP_CONFIG_PATH`) whose lines are turned into command-line arguments that are prepended to the arguments given on the command line. The parsing of that file lives in `crates/core/flags/config.rs`. This task extends that parser so that a single rc file can pull in arguments defined in other rc files.

## Files to Create/Modify

- `crates/core/flags/config.rs` (modify) — extend the rc-file line parser to support file-inclusion directives and trailing inline comments, with cycle protection.
- `crates/core/flags/config.rs` (modify) — add unit tests to the existing `#[cfg(test)] mod tests` block at the bottom of this file covering the new behavior.

## Requirements

### Inline comment trimming

A line may carry a trailing comment introduced by a space-prefixed `#`. Everything from the first occurrence of ` #` (a space immediately followed by `#`) to the end of the line must be discarded before the line is interpreted as an argument; the remaining text must then be trimmed of surrounding whitespace.

- A `#` that is *not* preceded by a space (for example inside a value such as `--glob=*.c#temp`) must NOT start a comment and must be preserved verbatim.
- A line whose content becomes empty after stripping the trailing comment must be skipped, exactly like a blank or whole-line `#` comment is today.
- The pre-existing rules must be preserved: fully blank lines are skipped, and a line whose first non-whitespace byte is `#` is skipped entirely (a whole-line comment).

### Include directive

A non-comment line whose first non-whitespace character is `@` is an *include directive*. The text following the `@` (after trimming surrounding whitespace) is a path to another rc file whose parsed arguments must be spliced into the output stream at exactly the position where the directive appears, preserving order relative to the surrounding arguments.

- Includes may nest: an included file may itself contain further `@` include directives, and their arguments must be flattened in depth-first, left-to-right order.
- A relative include path must be resolved relative to the directory of the file that contains the directive (not relative to the process working directory). An absolute include path is used as-is.
- If an included file cannot be opened, that single directive must be reported as a per-line error (it must appear in the returned error list with enough context to identify the failing path) while parsing of the remaining lines continues; it must not abort the whole parse.

### Cycle and depth protection

The parser must not loop forever or overflow the stack when files include one another.

- If following an include directive would re-enter a file that is already on the current include chain (a direct or indirect cycle), that directive must be reported as a per-line error and must not be followed; parsing continues with the rest of the file.
- Two distinct files that both include the same third file (a "diamond", not a cycle) must both succeed; the shared file's arguments appear once per inclusion site.

### Preserved semantics

- The existing public entry point that yields arguments from `RIPGREP_CONFIG_PATH` must keep returning a `Vec<OsString>` of shell arguments and must continue to surface per-line parse errors as it does today.
- Each ordinary (non-blank, non-comment, non-include) line still maps to exactly one argument, and invalid-UTF-8 handling on the respective platform is unchanged for those ordinary lines.

### Expected Functionality

- rc file containing `--smart-case`, then `@common.rc`, then `--hidden`, where `common.rc` contains `--ignore-case` and `-u` → arguments `["--smart-case", "--ignore-case", "-u", "--hidden"]`.
- rc line `--context=2  # widen context` → argument `--context=2` (comment and surrounding whitespace removed).
- rc line `--glob=*.rs#scratch` → argument `--glob=*.rs#scratch` (the `#` is not a comment because no space precedes it).
- `a.rc` includes `b.rc`, and `b.rc` includes `a.rc` → the cyclic directive is recorded as an error and is not followed; no infinite recursion occurs.
- `top.rc` includes both `left.rc` and `right.rc`, each of which includes `shared.rc` → both inclusions succeed and `shared.rc`'s arguments appear twice in order.

## Acceptance Criteria

- A non-comment line beginning with `@` is replaced by the flattened argument sequence of the referenced file, resolved relative to the including file's directory, in depth-first left-to-right order.
- Trailing ` #` comments are stripped while embedded `#` (not preceded by a space) is preserved.
- Direct and indirect include cycles terminate and are reported as per-line errors rather than crashing or looping.
- An unreadable include is reported as a per-line error without aborting the surrounding parse.
- All pre-existing tests in the file continue to pass unchanged.
- The new and existing unit tests in `crates/core/flags/config.rs` pass via:

  ```
  cargo test --bin rg flags::config::
  ```
