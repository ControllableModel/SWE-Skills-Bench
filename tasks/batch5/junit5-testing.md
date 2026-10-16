# Task: Add a Frequency-Counting Helper to CollectionUtils and Verify It

## Background

The `junit-platform-commons` module provides an internal `CollectionUtils`
helper (`org.junit.platform.commons.util.CollectionUtils`) with small,
dependency-free collection operations. This task adds an element-frequency
operation to that class together with a verification suite under the
`platform-tests` module.

## Files to Create/Modify

- `junit-platform-commons/src/main/java/org/junit/platform/commons/util/CollectionUtils.java` (modify) — add the new public static method described below.
- `platform-tests/src/test/java/org/junit/platform/commons/util/CollectionFrequencyTests.java` (new) — the verification suite. Place it in package `org.junit.platform.commons.util`, alongside the existing `CollectionUtilsTests`.

## Requirements

### New method

Add a public static method to `CollectionUtils` with exactly this signature:

```java
public static <T> java.util.Map<T, Integer> frequencies(java.util.Collection<T> collection)
```

It returns a map from each distinct element of `collection` to the number of
times it occurs.

### Behavior

- Every distinct element of `collection` appears exactly once as a key; its value
  is its occurrence count (`>= 1`).
- The sum of all counts in the returned map equals `collection.size()`.
- An empty input collection yields an empty map.
- Element identity is determined by `equals`/`hashCode` (standard map semantics).

### Constraints and edge cases

- `collection` must not be `null`; passing `null` must cause a
  `org.junit.platform.commons.PreconditionViolationException` (use the module's
  existing precondition mechanism), with a message conveying that the collection
  must not be `null`.
- The returned map must contain no key whose count is `0`.
- The method must not mutate the input collection.

### Expected Functionality

- `frequencies(["a","b","a","c","a"])` -> `{a=3, b=1, c=1}`
- `frequencies(["x"])` -> `{x=1}`
- `frequencies([])` -> `{}` (empty map)
- `frequencies([1,1,1])` -> `{1=3}`
- `frequencies([1,2,3])` -> `{1=1, 2=1, 3=1}` (sum of counts = 3)
- `frequencies(null)` -> throws `PreconditionViolationException`

### Test suite

The new `CollectionFrequencyTests` class must verify the behavior above as a
self-contained, deterministic unit suite that does not rely on any external
service, file system, network, or execution order. It must, at minimum:

- Cover the repeated-element case, single-element case, all-distinct case,
  all-identical case, and empty case.
- Express the count cases as a single data-driven test method fed by multiple
  rows that pair an input with its expected total count and/or distinct-key
  count, rather than one method per row.
- Verify the precondition failure (`null` collection) by asserting the exception
  type and that its message is meaningful.
- Use grouping so a batch of related expectations (e.g. distinct-key count, sum
  of counts equals input size, and a specific key's count) is all evaluated even
  when one fails.
- Carry human-readable descriptions for the test class and its methods.

Tests must pass for a correct implementation and must fail for a naive stub
(e.g. one that always reports a count of `1`, drops repeated elements, or skips
the precondition check).

## Acceptance Criteria

- `CollectionUtils.frequencies(Collection)` exists with the exact signature and
  the contract above.
- The new test class lives at
  `platform-tests/src/test/java/org/junit/platform/commons/util/CollectionFrequencyTests.java`
  and contains at least 10 distinct test executions (counting each data-driven
  row separately), including the precondition-violation case and at least one
  grouped-assertion method.
- Running the suite in isolation passes:

  ```
  ./gradlew :platform-tests:test --tests "org.junit.platform.commons.util.CollectionFrequencyTests"
  ```

- All "Expected Functionality" rows are satisfied, and a naive implementation
  that ignores duplicates or always reports `1` fails at least one test.
