# Task: Add a Common-Prefix Helper to StringUtils and Verify It

## Background

The `junit-platform-commons` module exposes an internal `StringUtils` helper
(`org.junit.platform.commons.util.StringUtils`) used across the framework for
safe string handling. This task adds a longest-common-prefix helper to that
class together with a thorough verification suite under the `platform-tests`
module.

## Files to Create/Modify

- `junit-platform-commons/src/main/java/org/junit/platform/commons/util/StringUtils.java` (modify) — add the new public static method described below.
- `platform-tests/src/test/java/org/junit/platform/commons/util/StringCommonPrefixTests.java` (new) — the verification suite. Place it in package `org.junit.platform.commons.util`, alongside the existing `StringUtilsTests`.

## Requirements

### New method

Add a public static method to `StringUtils` with exactly this signature:

```java
public static String commonPrefix(String first, String second)
```

It returns the longest leading run of characters shared by both arguments.

### Behavior

- The returned string is the longest prefix `p` such that both `first` and
  `second` start with `p`. If the two strings share no leading character, the
  result is the empty string `""`.
- Comparison is case-sensitive and by Java `char` (`String.charAt`), consistent
  with the rest of `StringUtils`.
- If either argument is the empty string, the result is the empty string.
- When one argument is itself a prefix of the other, the shorter argument is
  returned in full.

### Constraints and edge cases

- Neither `first` nor `second` may be `null`; passing `null` for either must
  cause a `org.junit.platform.commons.PreconditionViolationException` (use the
  module's existing precondition mechanism). The message must convey that the
  arguments must not be `null`.
- The method must not return a string longer than the shorter of the two
  arguments.
- A single differing character at any position ends the common prefix at that
  position (the differing character is not included).

### Expected Functionality

- `commonPrefix("foobar", "foobaz")` -> `"fooba"`
- `commonPrefix("abc", "abc")` -> `"abc"`
- `commonPrefix("abc", "abcdef")` -> `"abc"`
- `commonPrefix("xyz", "abc")` -> `""`
- `commonPrefix("", "abc")` -> `""`
- `commonPrefix("Abc", "abc")` -> `""` (case-sensitive)
- `commonPrefix(null, "abc")` -> throws `PreconditionViolationException`
- `commonPrefix("abc", null)` -> throws `PreconditionViolationException`

### Test suite

The new `StringCommonPrefixTests` class must verify the behavior above as a
self-contained, deterministic unit suite that does not rely on any external
service, file system, network, or execution order. It must, at minimum:

- Cover the shared-prefix cases, the prefix-of-the-other cases, the no-overlap
  case, and the empty-input cases.
- Express the value cases as a single data-driven test method fed by multiple
  `(first, second, expected)` rows rather than one method per row, so that
  adding a new row does not require a new method.
- Verify both precondition failures (`null` first; `null` second) by asserting
  that the correct exception type is thrown and that its message is meaningful.
- Use grouping so a batch of related expectations is all evaluated even when one
  of them fails.
- Carry human-readable descriptions for the test class and its methods.

Tests must pass when the new method is implemented correctly and must fail for a
naive stub (e.g. one that returns one of the inputs unchanged, ignores
case-sensitivity, or skips the precondition checks).

## Acceptance Criteria

- `StringUtils.commonPrefix(String, String)` exists with the exact signature and
  the contract above.
- The new test class lives at
  `platform-tests/src/test/java/org/junit/platform/commons/util/StringCommonPrefixTests.java`
  and contains at least 10 distinct test executions (counting each row of the
  data-driven method as a separate execution), including the two
  precondition-violation cases and at least one grouped-assertion method.
- Running the suite in isolation passes:

  ```
  ./gradlew :platform-tests:test --tests "org.junit.platform.commons.util.StringCommonPrefixTests"
  ```

- All "Expected Functionality" rows are satisfied, and a naive implementation
  that returns an input unchanged or skips the precondition checks fails at
  least one test.
