# Task: Add a Title-Case Helper to StringUtils and Verify It

## Background

The `junit-platform-commons` module exposes an internal `StringUtils` helper
(`org.junit.platform.commons.util.StringUtils`) used across the framework for
safe string handling. This task adds a whitespace-delimited title-casing helper
to that class together with a verification suite under the `platform-tests`
module.

## Files to Create/Modify

- `junit-platform-commons/src/main/java/org/junit/platform/commons/util/StringUtils.java` (modify) — add the new public static method described below.
- `platform-tests/src/test/java/org/junit/platform/commons/util/StringTitleCaseTests.java` (new) — the verification suite. Place it in package `org.junit.platform.commons.util`, alongside the existing `StringUtilsTests`.

## Requirements

### New method

Add a public static method to `StringUtils` with exactly this signature:

```java
public static String toTitleCase(String value)
```

It returns `value` with the first letter of every whitespace-separated word
upper-cased and the remaining letters of each word lower-cased.

### Behavior

- A "word" is a maximal run of non-whitespace characters; words are separated by
  one or more whitespace characters (as determined by `Character.isWhitespace`).
- For each word, the first character is converted with `Character.toUpperCase`
  and every subsequent character with `Character.toLowerCase`.
- The original whitespace between words is preserved exactly (same characters,
  same counts, same positions).
- An empty string returns the empty string. A string consisting only of
  whitespace is returned unchanged.

### Constraints and edge cases

- `value` must not be `null`; passing `null` must cause a
  `org.junit.platform.commons.PreconditionViolationException` (use the module's
  existing precondition mechanism), with a message conveying that the value must
  not be `null`.
- Leading and trailing whitespace must be preserved.
- Multiple consecutive spaces between words must be preserved as-is (not
  collapsed).

### Expected Functionality

- `toTitleCase("hello world")` -> `"Hello World"`
- `toTitleCase("HELLO WORLD")` -> `"Hello World"`
- `toTitleCase("java IS fun")` -> `"Java Is Fun"`
- `toTitleCase("  spaced   out ")` -> `"  Spaced   Out "` (whitespace preserved)
- `toTitleCase("a")` -> `"A"`
- `toTitleCase("")` -> `""`
- `toTitleCase(null)` -> throws `PreconditionViolationException`

### Test suite

The new `StringTitleCaseTests` class must verify the behavior above as a
self-contained, deterministic unit suite that does not rely on any external
service, file system, network, or execution order. It must, at minimum:

- Cover the basic two-word case, the all-uppercase normalization case, the
  mixed-case case, the preserved-whitespace case, the single-character case, and
  the empty-string case.
- Express the value cases as a single data-driven test method fed by multiple
  `(value, expected)` rows rather than one method per row.
- Verify the precondition failure (`null` value) by asserting the exception type
  and that its message is meaningful.
- Use grouping so a batch of related expectations (e.g. resulting content and
  that the result length equals the input length) is all evaluated even when one
  fails.
- Carry human-readable descriptions for the test class and its methods.

Tests must pass for a correct implementation and must fail for a naive stub
(e.g. one that only upper-cases the very first character, collapses whitespace,
fails to lower-case the rest of each word, or skips the precondition check).

## Acceptance Criteria

- `StringUtils.toTitleCase(String)` exists with the exact signature and the
  contract above.
- The new test class lives at
  `platform-tests/src/test/java/org/junit/platform/commons/util/StringTitleCaseTests.java`
  and contains at least 10 distinct test executions (counting each data-driven
  row separately), including the precondition-violation case and at least one
  grouped-assertion method.
- Running the suite in isolation passes:

  ```
  ./gradlew :platform-tests:test --tests "org.junit.platform.commons.util.StringTitleCaseTests"
  ```

- All "Expected Functionality" rows are satisfied, and a naive implementation
  that collapses whitespace or only capitalizes the first word fails at least
  one test.
