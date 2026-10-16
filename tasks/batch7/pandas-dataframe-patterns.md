# Task: Build a Student Grades Aggregation Module

## Background
The pandas repository keeps small, self-contained utilities under `scripts/`, each paired with a deterministic test in `scripts/tests/`. This task adds a utility that aggregates raw grade records into per-student and per-course summaries with weighted scores.

## Files to Create/Modify
- `scripts/grades_aggregate.py` (new) — the aggregation module described below.
- `scripts/tests/test_grades_aggregate.py` (new) — the deterministic test suite for the module.

The module must `import pandas as pd` and operate purely in-process (no files, network, or external services).

## Requirements

The module exposes the following public functions. They must work for arbitrary inputs satisfying the stated contracts, not just the examples below.

### `weighted_course_average(grades)`
- `grades` has columns: `student_id` (int), `course` (str), `assignment` (str), `score` (float, 0–100), `weight` (float, positive).
- For each `(student_id, course)`, compute the weighted average score: `sum(score * weight) / sum(weight)` over that group's rows.
- Return a flat frame with columns `student_id`, `course`, `weighted_avg`, sorted by `student_id` then `course` ascending, with the index reset to `0..n-1`.
- The caller's `grades` object must not be mutated.

### `student_gpa(course_averages, scale)`
Given the output of `weighted_course_average` and a `scale` mapping (a frame with columns `low`, `high`, `points`, where a `weighted_avg` in the half-open band `[low, high)` maps to `points`), return a frame with columns `student_id` and `gpa`: the unweighted mean of `points` across that student's courses.
- Each `weighted_avg` falls in exactly one band; bands are contiguous and non-overlapping for the tested data.
- Result sorted by `student_id` ascending, index reset to `0..n-1`. Neither input may be mutated.

### `course_stats(grades)`
Return a per-course summary frame with columns `course`, `student_count` (number of distinct `student_id` in the course), `mean_score` (mean of raw `score`), `max_score` (max raw `score`). Sorted by `course` ascending, index reset to `0..n-1`. Input must not be mutated.

### Expected Functionality
- weighted_course_average with scores `[80, 100]` and weights `[1, 3]` for one `(student, course)` -> `95.0`.
- weighted_course_average -> flat, sorted by `(student_id, course)`, contiguous index.
- student_gpa with a band `[90, 100) -> 4.0` -> a course average of `95.0` contributes `4.0`.
- course_stats -> `student_count` counts distinct students, `max_score` is the raw maximum.

## Acceptance Criteria
- `scripts/grades_aggregate.py` defines `weighted_course_average`, `student_gpa`, and `course_stats` with the behavior above.
- Weighted averages are computed per group, not as a plain mean.
- Summaries are flat, sorted, and contiguously indexed.
- All functions leave their inputs unmodified.
- The following command passes from the repository root:

```
python -m pytest scripts/tests/test_grades_aggregate.py -q
```
