# Task: Add a Cache-Fingerprint Builder

## Background

Black caches formatting results keyed on the file content together with the active
mode/options, so it must build a stable fingerprint string from a structured set
of inputs and reject malformed records. This task adds a self-contained
fingerprint builder to the `black` package that turns a structured cache record
into a deterministic key, independent of `black.cache`.

## Files to Create/Modify

- `src/black/cache_fingerprint.py` (new) — the fingerprint module described below.
- `tests/test_cache_fingerprint.py` (new) — the deterministic unit tests for it.

The new module must live in the `black` package and import only from the Python
standard library (you may use `hashlib`).

## Requirements

### Public surface

`from black.cache_fingerprint import CacheRecord, fingerprint, FingerprintError`
must succeed. The module exposes exactly `CacheRecord`, `fingerprint`, and
`FingerprintError` (a subclass of `ValueError`). Private helpers may begin with `_`.

### `CacheRecord`

`CacheRecord` describes the fingerprint inputs and carries exactly these fields:

- `content` — a `str` (the source text).
- `line_length` — an `int` (must be `> 0`).
- `target_versions` — a collection of `str` version tags (order must not affect
  the fingerprint; duplicates collapse).
- `flags` — a mapping from `str` flag name to `bool`.

It may be a `dataclass`, a `TypedDict`, or a small class; whichever you choose, a
record may be constructed from a plain `dict` via a `CacheRecord.from_dict(data)`
classmethod that validates types and raises `FingerprintError` on any wrong type
or missing field (e.g. a non-`int` `line_length`, a `line_length <= 0`, a
non-`str` element in `target_versions`, or a non-`bool` flag value).

### `fingerprint(record)`

Returns a deterministic 64-character lowercase hexadecimal `str` (a SHA-256 hex
digest) computed from the record's normalized contents. The function must satisfy:

- **Determinism**: the same logical record always yields the same fingerprint
  within a process and across calls.
- **Order independence**: two records that differ only in the order of
  `target_versions` (or in the iteration order of `flags`) produce the **same**
  fingerprint.
- **Sensitivity**: changing `content`, `line_length`, the *set* of
  `target_versions`, or any flag value produces a **different** fingerprint.

### Expected Functionality

- `fingerprint(r)` is a 64-char hex string matching `^[0-9a-f]{64}$`.
- A record with `target_versions=["py311", "py38"]` and one with
  `["py38", "py311"]` (all else equal) fingerprint identically.
- Flipping a single flag from `False` to `True` changes the fingerprint.
- Changing `line_length` from `88` to `100` changes the fingerprint.

### Edge cases

- `CacheRecord.from_dict({...})` with `line_length=0` or `line_length="88"`
  raises `FingerprintError`.
- A `flags` mapping with a non-`bool` value (e.g. `{"skip_magic": "yes"}`) raises
  `FingerprintError`.
- An empty `target_versions` and an empty `content` are valid and produce a stable
  fingerprint.

## Acceptance Criteria

- The module exposes `CacheRecord`, `fingerprint`, and `FingerprintError` with the
  behavior above.
- `tests/test_cache_fingerprint.py` contains at least 12 independent test cases
  covering the hex-format contract, determinism, order independence over both
  `target_versions` and `flags`, sensitivity to each field, and at least three
  distinct `FingerprintError`-raising validation inputs.
- A naive implementation that hashes a raw `repr()` (and so is order-sensitive) or
  that skips validation fails the tests.
- The following command passes from the repository root:

  ```bash
  python -m pytest tests/test_cache_fingerprint.py -q
  ```

- Running the project's configured type checker over the new module reports no errors:

  ```bash
  mypy src/black/cache_fingerprint.py
  ```
