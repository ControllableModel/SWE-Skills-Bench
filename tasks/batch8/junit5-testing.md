# Task: Add a Left-Padding Helper to StringUtils and Verify It

## Background

The `junit-platform-commons` module exposes an internal `StringUtils` helper
(`org.junit.platform.commons.util.StringUtils`) used across the framework for
safe string handling. This task adds a left-padding helper to that class
together with a verification suite under the `platform-tests` module.

## Files to Create/Modify

- `junit-platform-commons/src/main/java/org/junit/platform/commons/util/StringUtils.java` (modify) — add the new public static method described below.
- `platform-tests/src/test/java/org/junit/platform/commons/util/StringPadLeftTests.java` (new) — the verification suite. Place it in package `org.junit.platform.commons.util`, alongside the existing `StringUtilsTests`.

## Requirements

### New method

Add a public static method to `StringUtils` with exactly this signature:

```java
public static String padLeft(String value, int minLength, char padChar)
```

It left-pads `value` with `padChar` until it reaches `minLength` characters.

### Behavior

- If `value.length()` is already greater than or equal to `minLength`, `value`
  is returned unchanged (same character content; the same reference is
  acceptable).
- Otherwise the result has length exactly `minLength`: `minLength - value.length()`
  copies of `padChar` prepended to the original `value`, with `value` kept
  intact and on the right.
- Counting is by Java `char` length (`String.length()`).

### Constraints and edge cases

- `value` must not be `null`; passing `null` must cause a
  `org.junit.platform.commons.PreconditionViolationException` (use the module's
  existing precondition mechanism), with a message conveying that the value must
  not be `null`.
- A `minLength` less than `0` must cause a `PreconditionViolationException`
  whose message conveys the non-negative requirement.
- The empty string padded to `minLength` becomes `minLength` copies of
  `padChar`.
- Padding is added only on the LEFT; the original characters are never altered or
  reordered.

### Expected Functionality

- `padLeft("42", 5, '0')` -> `"00042"`
- `padLeft("42", 2, '0')` -> `"42"` (already long enough)
- `padLeft("hello", 3, '0')` -> `"hello"` (longer than min, unchanged)
- `padLeft("", 3, '*')` -> `"***"`
- `padLeft("7", 4, ' ')` -> `"   7"`
- `padLeft(null, 5, '0')` -> throws `PreconditionViolationException`
- `padLeft("42", -1, '0')` -> throws `PreconditionViolationException`

### Test suite

The new `StringPadLeftTests` class must verify the behavior above as a
self-contained, deterministic unit suite that does not rely on any external
service, file system, network, or execution order. It must, at minimum:

- Cover the padding-needed case, the already-long-enough case, the
  longer-than-min case, and the empty-string case.
- Express the value cases as a single data-driven test method fed by multiple
  `(value, minLength, padChar, expected)` rows rather than one method per row.
- Verify both precondition failures (`null` value; negative `minLength`) by
  asserting the exception type and that each message is meaningful.
- Use grouping so a batch of related expectations (e.g. resulting length, that
  the original suffix is preserved, and that only the left side was padded) is
  all evaluated even when one fails.
- Carry human-readable descriptions for the test class and its methods.

Tests must pass for a correct implementation and must fail for a naive stub
(e.g. one that pads on the right, alters the original characters, or skips the
precondition checks).

## Acceptance Criteria

- `StringUtils.padLeft(String, int, char)` exists with the exact signature and
  the contract above.
- The new test class lives at
  `platform-tests/src/test/java/org/junit/platform/commons/util/StringPadLeftTests.java`
  and contains at least 10 distinct test executions (counting each data-driven
  row separately), including the two precondition-violation cases and at least
  one grouped-assertion method.
- Running the suite in isolation passes:

  ```
  ./gradlew :platform-tests:test --tests "org.junit.platform.commons.util.StringPadLeftTests"
  ```

- All "Expected Functionality" rows are satisfied, and a naive implementation
  that pads on the right or skips the precondition checks fails at least one
  test.
