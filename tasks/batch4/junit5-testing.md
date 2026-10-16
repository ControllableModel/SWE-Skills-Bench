# Task: Add a String Centering Helper to StringUtils and Verify It

## Background

The `junit-platform-commons` module exposes an internal `StringUtils` helper
(`org.junit.platform.commons.util.StringUtils`) used across the framework for
safe string handling. This task adds a fixed-width centering helper to that
class together with a verification suite under the `platform-tests` module.

## Files to Create/Modify

- `junit-platform-commons/src/main/java/org/junit/platform/commons/util/StringUtils.java` (modify) — add the new public static method described below.
- `platform-tests/src/test/java/org/junit/platform/commons/util/StringCenterTests.java` (new) — the verification suite. Place it in package `org.junit.platform.commons.util`, alongside the existing `StringUtilsTests`.

## Requirements

### New method

Add a public static method to `StringUtils` with exactly this signature:

```java
public static String center(String value, int width, char padChar)
```

It returns `value` centered within a field of the given `width`, padded on both
sides with `padChar`.

### Behavior

- If `value.length()` is already greater than or equal to `width`, `value` is
  returned unchanged (same character content; the same reference is acceptable).
- Otherwise the result has length exactly `width`. The total padding is
  `width - value.length()` copies of `padChar`, split between the two sides.
- When the total padding is odd, the extra single pad character goes on the
  right side (left padding `= floor(total / 2)`, right padding `= ceil(total / 2)`).
- Counting is by Java `char` length (`String.length()`).

### Constraints and edge cases

- `value` must not be `null`; passing `null` must cause a
  `org.junit.platform.commons.PreconditionViolationException` (use the module's
  existing precondition mechanism), with a message conveying that the value must
  not be `null`.
- A `width` less than `0` must cause a `PreconditionViolationException` whose
  message conveys the non-negative requirement.
- The empty string centered in a field of `width` becomes `width` copies of
  `padChar`.

### Expected Functionality

- `center("ab", 6, '*')` -> `"**ab**"`
- `center("ab", 5, '*')` -> `"*ab**"` (extra pad on the right)
- `center("abc", 3, '*')` -> `"abc"` (already wide enough)
- `center("abcdef", 4, '*')` -> `"abcdef"` (longer than width, unchanged)
- `center("", 3, '-')` -> `"---"`
- `center("x", 4, '.')` -> `".x.."`
- `center(null, 5, '*')` -> throws `PreconditionViolationException`
- `center("ab", -1, '*')` -> throws `PreconditionViolationException`

### Test suite

The new `StringCenterTests` class must verify the behavior above as a
self-contained, deterministic unit suite that does not rely on any external
service, file system, network, or execution order. It must, at minimum:

- Cover even-padding, odd-padding (extra-on-right), already-wide, empty-string,
  and single-character cases.
- Express the value cases as a single data-driven test method fed by multiple
  `(value, width, padChar, expected)` rows rather than one method per row.
- Verify both precondition failures (`null` value; negative `width`) by
  asserting the exception type and that its message is meaningful.
- Use grouping so a batch of related expectations (e.g. resulting length and
  resulting content) is all evaluated even when one fails.
- Carry human-readable descriptions for the test class and its methods.

Tests must pass for a correct implementation and must fail for a naive stub
(e.g. one that pads only one side, puts the extra pad on the wrong side, or
skips the precondition checks).

## Acceptance Criteria

- `StringUtils.center(String, int, char)` exists with the exact signature and
  the contract above.
- The new test class lives at
  `platform-tests/src/test/java/org/junit/platform/commons/util/StringCenterTests.java`
  and contains at least 10 distinct test executions (counting each data-driven
  row separately), including the two precondition-violation cases and at least
  one grouped-assertion method.
- Running the suite in isolation passes:

  ```
  ./gradlew :platform-tests:test --tests "org.junit.platform.commons.util.StringCenterTests"
  ```

- All "Expected Functionality" rows are satisfied, and a naive implementation
  that pads one side only or misplaces the odd pad fails at least one test.
