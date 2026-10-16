# Task: Implement DICOM Date and Time Normalizers

## Background

The `pydicom` library (this repository) stores dates and times in compact DICOM string formats (VR **DA** as `YYYYMMDD`, VR **TM** as `HHMMSS.FFFFFF`). This task adds a self-contained utility to `src/pydicom/util/` that parses those strings into standard Python objects and back, for downstream reporting.

## Files to Create/Modify

- `src/pydicom/util/datetimefmt.py` (new) — the date/time normalization module.
- `tests/test_util_datetimefmt.py` (new) — the deterministic unit tests for the new module.

## Requirements

### Public API

Add `src/pydicom/util/datetimefmt.py` exposing exactly these functions:

```python
def parse_da(value)
def parse_tm(value)
def format_da(d)
def format_tm(t)
```

### Parsing contract

- `parse_da(value)`: given a DICOM **DA** string such as `"20230115"`, return a `datetime.date`. An empty string or `None` returns `None`.
- `parse_tm(value)`: given a DICOM **TM** string, return a `datetime.time`. Must accept the fractional-second form `"131005.500000"`, the second form `"131005"`, and the partial forms `"1310"` (HH:MM) and `"13"` (HH only). An empty string or `None` returns `None`.

### Formatting contract

- `format_da(d)`: given a `datetime.date`, return the DICOM **DA** string `"YYYYMMDD"`.
- `format_tm(t)`: given a `datetime.time`, return a DICOM **TM** string. If the time has nonzero microseconds, include the 6-digit fractional part (`"HHMMSS.FFFFFF"`); otherwise emit `"HHMMSS"`.

### Behavior and edge cases

- `parse_da` must reject a malformed date (wrong length / non-numeric) by raising `ValueError`.
- `parse_tm` must correctly interpret the fractional seconds as microseconds (`".5"`-style fractions scaled to 6 digits): `"131005.5"` → 500000 microseconds.
- Round-trip: for any valid date `d`, `parse_da(format_da(d)) == d`; for a `time` `t` with microsecond resolution expressible in DICOM, `parse_tm(format_tm(t)) == t`.
- `None` and `""` inputs to the parsers return `None` (no exception).

### Expected Functionality

- `parse_da("20230115")` → `date(2023, 1, 15)`; `format_da(date(2023,1,15))` → `"20230115"`.
- `parse_tm("131005.500000")` → `time(13, 10, 5, 500000)`.
- `parse_tm("1310")` → `time(13, 10)`.
- `format_tm(time(9, 0, 0))` → `"090000"`; `format_tm(time(9, 0, 0, 250000))` → `"090000.250000"`.
- `parse_da("2023-01-15")` raises `ValueError`.

## Acceptance Criteria

- `src/pydicom/util/datetimefmt.py` exists and defines `parse_da`, `parse_tm`, `format_da`, `format_tm` as specified.
- DA/TM parsing handles full, partial, and fractional forms; formatting emits the correct compact strings with/without fractional seconds; round-trips hold.
- Malformed dates raise `ValueError`; `None`/`""` parser inputs return `None`.
- The new test file passes deterministically and covers DA parse/format round-trip, TM full/partial/fractional parsing, TM formatting with and without microseconds, the `None`/empty cases, and the malformed-date `ValueError` (≥10 test cases). A naive implementation that ignores partial/fractional TM forms or skips round-trip correctness must fail.

Run exactly:

```bash
python -m pytest tests/test_util_datetimefmt.py -q
```

This command must exit with all tests passing.
