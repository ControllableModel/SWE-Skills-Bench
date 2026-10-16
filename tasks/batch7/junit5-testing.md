# Task: Add a Distinct-Preserving Helper to CollectionUtils and Verify It

## Background

The `junit-platform-commons` module provides an internal `CollectionUtils`
helper (`org.junit.platform.commons.util.CollectionUtils`) with small,
dependency-free collection operations. This task adds an order-preserving
de-duplication operation to that class together with a verification suite under
the `platform-tests` module.

## Files to Create/Modify

- `junit-platform-commons/src/main/java/org/junit/platform/commons/util/CollectionUtils.java` (modify) — add the new public static method described below.
- `platform-tests/src/test/java/org/junit/platform/commons/util/CollectionDistinctTests.java` (new) — the verification suite. Place it in package `org.junit.platform.commons.util`, alongside the existing `CollectionUtilsTests`.

## Requirements

### New method

Add a public static method to `CollectionUtils` with exactly this signature:

```java
public static <T> java.util.List<T> distinct(java.util.List<T> list)
```

It returns a new list containing the elements of `list` with duplicates removed,
keeping only the FIRST occurrence of each element and preserving that order.

### Behavior

- The result preserves the order in which elements first appear in `list`.
- Each distinct element (by `equals`/`hashCode`) appears exactly once.
- An empty input yields an empty list.
- The input list must not be mutated; a new list is returned.

### Constraints and edge cases

- `list` must not be `null`; passing `null` must cause a
  `org.junit.platform.commons.PreconditionViolationException` (use the module's
  existing precondition mechanism), with a message conveying that the list must
  not be `null`.
- When the input has no duplicates, the result has the same elements in the same
  order (but is a distinct list instance).
- Later duplicate occurrences are dropped, not the first occurrence.

### Expected Functionality

- `distinct([1,2,1,3,2])` -> `[1,2,3]`
- `distinct([3,3,3])` -> `[3]`
- `distinct([1,2,3])` -> `[1,2,3]`
- `distinct([])` -> `[]`
- `distinct(["b","a","b","c","a"])` -> `["b","a","c"]` (first-occurrence order)
- `distinct(null)` -> throws `PreconditionViolationException`

### Test suite

The new `CollectionDistinctTests` class must verify the behavior above as a
self-contained, deterministic unit suite that does not rely on any external
service, file system, network, or execution order. It must, at minimum:

- Cover the duplicates-removed case, the all-identical case, the
  already-distinct case, and the empty case.
- Express the value cases as a single data-driven test method fed by multiple
  `(input, expected)` rows rather than one method per row.
- Verify the precondition failure (`null` list) by asserting the exception type
  and that its message is meaningful.
- Use grouping so a batch of related expectations (e.g. result content, result
  size, and that the input list is unmodified) is all evaluated even when one
  fails.
- Carry human-readable descriptions for the test class and its methods.

Tests must pass for a correct implementation and must fail for a naive stub
(e.g. one that returns the input unchanged, sorts instead of preserving first
order, keeps last occurrences, or skips the precondition check).

## Acceptance Criteria

- `CollectionUtils.distinct(List)` exists with the exact signature and the
  contract above.
- The new test class lives at
  `platform-tests/src/test/java/org/junit/platform/commons/util/CollectionDistinctTests.java`
  and contains at least 10 distinct test executions (counting each data-driven
  row separately), including the precondition-violation case and at least one
  grouped-assertion method.
- Running the suite in isolation passes:

  ```
  ./gradlew :platform-tests:test --tests "org.junit.platform.commons.util.CollectionDistinctTests"
  ```

- All "Expected Functionality" rows are satisfied, and a naive implementation
  that preserves duplicates or reorders elements fails at least one test.
