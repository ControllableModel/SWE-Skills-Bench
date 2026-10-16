# Task: Add a String Abbreviation Utility and Its Test Suite

## Background

The `junit-platform-commons` module exposes an internal `StringUtils` helper
(`org.junit.platform.commons.util.StringUtils`) used throughout the JUnit
framework for safe string handling. This task adds a new abbreviation helper to
that class and a thorough verification suite for it under the `platform-tests`
module.

## Files to Create/Modify

- `junit-platform-commons/src/main/java/org/junit/platform/commons/util/StringUtils.java` (modify) — add the new public static method described below.
- `platform-tests/src/test/java/org/junit/platform/commons/util/StringAbbreviationTests.java` (new) — the verification suite for the new behavior. Place it in package `org.junit.platform.commons.util`, alongside the existing `StringUtilsTests`.

## Requirements

### New method

Add a public static method to `StringUtils` with exactly this signature:

```java
public static String abbreviate(String value, int maxLength)
```

It shortens `value` so that the returned string is never longer than
`maxLength` characters, appending an ellipsis marker when truncation occurs.

### Behavior

- The ellipsis marker is the three-character ASCII string `"..."` (three period
  characters). When the value must be shortened, the result consists of a
  prefix taken from the start of `value` followed immediately by the ellipsis,
  and the total length of the result must equal `maxLength`.
- If `value` is already no longer than `maxLength`, it is returned unchanged
  (same character content; the same reference is acceptable).
- Counting is by Java `char` length (`String.length()`), consistent with the
  rest of `StringUtils`.

### Constraints and edge cases

- `value` must not be `null`; passing `null` must cause a
  `org.junit.platform.commons.PreconditionViolationException` to be thrown
  (use the module's existing precondition mechanism). The exception message
  must mention that the value must not be `null`.
- `maxLength` must be at least `4` (enough room for at least one prefix
  character plus the three-character marker). A `maxLength` below `4` must cause
  a `PreconditionViolationException` whose message conveys the minimum-length
  requirement. This precondition is checked regardless of how short `value` is.
- When truncation occurs, exactly `maxLength - 3` leading characters of `value`
  are retained before the ellipsis. The marker itself is never truncated.
- The empty string and strings whose length equals `maxLength` exactly are
  returned unchanged (no ellipsis is appended).

### Expected Functionality

- `abbreviate("hello", 4)` -> `"h..."`
- `abbreviate("hello world", 8)` -> `"hello..."`
- `abbreviate("hello", 5)` -> `"hello"` (length equals limit, unchanged)
- `abbreviate("hi", 4)` -> `"hi"` (already short enough)
- `abbreviate("", 4)` -> `""`
- `abbreviate("abcdefghij", 7)` -> `"abcd..."`
- `abbreviate(null, 10)` -> throws `PreconditionViolationException`
- `abbreviate("hello", 3)` -> throws `PreconditionViolationException`

### Test suite

The new `StringAbbreviationTests` class must verify the behavior above as a
self-contained, deterministic unit suite that does not rely on any external
service, file system, network, or execution order. It must, at minimum:

- Cover the unchanged-input cases (value shorter than, and value exactly equal
  to, the limit), the truncation cases (including verifying the exact prefix and
  that the returned length equals `maxLength`), and the empty-string case.
- Verify both precondition failures (`null` value; `maxLength` smaller than the
  minimum) by asserting that the correct exception type is thrown and that its
  message is meaningful.
- Express the truncation cases as a single data-driven test method fed by
  multiple `(input, limit, expected)` rows rather than one method per row, so
  that adding a new row does not require a new method.
- Use grouping so that a batch of related expectations is all evaluated even
  when one of them fails.
- Carry human-readable descriptions for the test class and its methods.

Tests must pass when the new method is implemented correctly and must fail if
the method is replaced by a naive stub (e.g. one that always returns the input
unchanged, omits the ellipsis, miscounts the retained prefix, or skips the
precondition checks).

## Acceptance Criteria

- `StringUtils.abbreviate(String, int)` exists with the exact signature and the
  contract described above.
- The new test class `StringAbbreviationTests` lives at
  `platform-tests/src/test/java/org/junit/platform/commons/util/StringAbbreviationTests.java`
  and contains at least 10 distinct test executions (counting each row of the
  data-driven method as a separate execution), including the two
  precondition-violation cases and at least one grouped-assertion method.
- Running the suite in isolation passes:

  ```
  ./gradlew :platform-tests:test --tests "org.junit.platform.commons.util.StringAbbreviationTests"
  ```

- The full set of expectations in "Expected Functionality" is satisfied, and a
  naive implementation that ignores the limit, drops the ellipsis, or skips the
  precondition checks fails at least one test.
