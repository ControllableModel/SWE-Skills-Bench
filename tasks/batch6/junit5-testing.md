# Task: Add a Substring-Counting Helper to StringUtils and Verify It

## Background

The `junit-platform-commons` module exposes an internal `StringUtils` helper
(`org.junit.platform.commons.util.StringUtils`) used across the framework for
safe string handling. This task adds a non-overlapping substring-counting helper
to that class together with a verification suite under the `platform-tests`
module.

## Files to Create/Modify

- `junit-platform-commons/src/main/java/org/junit/platform/commons/util/StringUtils.java` (modify) — add the new public static method described below.
- `platform-tests/src/test/java/org/junit/platform/commons/util/StringCountOccurrencesTests.java` (new) — the verification suite. Place it in package `org.junit.platform.commons.util`, alongside the existing `StringUtilsTests`.

## Requirements

### New method

Add a public static method to `StringUtils` with exactly this signature:

```java
public static int countOccurrences(String value, String token)
```

It returns the number of non-overlapping occurrences of `token` within `value`.

### Behavior

- Counting is non-overlapping: after a match is found, the search resumes
  immediately after the matched span (so `countOccurrences("aaaa", "aa")` is `2`,
  not `3`).
- Matching is case-sensitive and by Java `char` (`String.indexOf`), consistent
  with the rest of `StringUtils`.
- If `token` does not appear in `value`, the result is `0`.

### Constraints and edge cases

- Neither `value` nor `token` may be `null`; passing `null` for either must
  cause a `org.junit.platform.commons.PreconditionViolationException` (use the
  module's existing precondition mechanism), with a message conveying that the
  arguments must not be `null`.
- `token` must not be the empty string; an empty `token` must cause a
  `PreconditionViolationException` whose message conveys that the token must not
  be empty.
- Overlapping potential matches are not double-counted.

### Expected Functionality

- `countOccurrences("banana", "a")` -> `3`
- `countOccurrences("aaaa", "aa")` -> `2` (non-overlapping)
- `countOccurrences("hello", "z")` -> `0`
- `countOccurrences("abcabcabc", "abc")` -> `3`
- `countOccurrences("AaAa", "a")` -> `2` (case-sensitive)
- `countOccurrences(null, "a")` -> throws `PreconditionViolationException`
- `countOccurrences("abc", null)` -> throws `PreconditionViolationException`
- `countOccurrences("abc", "")` -> throws `PreconditionViolationException`

### Test suite

The new `StringCountOccurrencesTests` class must verify the behavior above as a
self-contained, deterministic unit suite that does not rely on any external
service, file system, network, or execution order. It must, at minimum:

- Cover single-character tokens, multi-character non-overlapping tokens, the
  no-match case, and the case-sensitivity case.
- Express the count cases as a single data-driven test method fed by multiple
  `(value, token, expectedCount)` rows rather than one method per row.
- Verify all three precondition failures (`null` value; `null` token; empty
  token) by asserting the exception type and that each message is meaningful.
- Use grouping so a batch of related expectations is all evaluated even when one
  fails.
- Carry human-readable descriptions for the test class and its methods.

Tests must pass for a correct implementation and must fail for a naive stub
(e.g. one that counts overlapping matches, ignores case-sensitivity, or skips
the precondition checks).

## Acceptance Criteria

- `StringUtils.countOccurrences(String, String)` exists with the exact signature
  and the contract above.
- The new test class lives at
  `platform-tests/src/test/java/org/junit/platform/commons/util/StringCountOccurrencesTests.java`
  and contains at least 10 distinct test executions (counting each data-driven
  row separately), including the three precondition-violation cases and at least
  one grouped-assertion method.
- Running the suite in isolation passes:

  ```
  ./gradlew :platform-tests:test --tests "org.junit.platform.commons.util.StringCountOccurrencesTests"
  ```

- All "Expected Functionality" rows are satisfied, and a naive implementation
  that counts overlapping matches or skips the precondition checks fails at
  least one test.
