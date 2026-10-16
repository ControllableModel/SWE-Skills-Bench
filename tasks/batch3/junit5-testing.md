# Task: Add a List Partition Helper to CollectionUtils and Verify It

## Background

The `junit-platform-commons` module provides an internal `CollectionUtils`
helper (`org.junit.platform.commons.util.CollectionUtils`) with small,
dependency-free collection operations. This task adds a fixed-size partitioning
operation to that class together with a verification suite under the
`platform-tests` module.

## Files to Create/Modify

- `junit-platform-commons/src/main/java/org/junit/platform/commons/util/CollectionUtils.java` (modify) — add the new public static method described below.
- `platform-tests/src/test/java/org/junit/platform/commons/util/CollectionPartitionTests.java` (new) — the verification suite. Place it in package `org.junit.platform.commons.util`, alongside the existing `CollectionUtilsTests`.

## Requirements

### New method

Add a public static method to `CollectionUtils` with exactly this signature:

```java
public static <T> java.util.List<java.util.List<T>> partition(java.util.List<T> list, int size)
```

It splits `list` into consecutive sub-lists ("chunks"), each of at most `size`
elements, preserving the original order.

### Behavior

- Each chunk except possibly the last contains exactly `size` elements; the last
  chunk holds the remaining `1..size` elements.
- The concatenation of the returned chunks, in order, equals the original list.
- An empty input list yields an empty list of chunks (`[]`).
- The number of chunks equals `ceil(list.size() / size)`.

### Constraints and edge cases

- `list` must not be `null`, and `size` must be at least `1`. Violating either
  must cause a `org.junit.platform.commons.PreconditionViolationException` (use
  the module's existing precondition mechanism), with a message that conveys the
  violated requirement.
- When `list.size()` is an exact multiple of `size`, every chunk (including the
  last) has exactly `size` elements and there is no trailing partial chunk.
- The returned chunks must preserve element order and must contain every element
  exactly once.

### Expected Functionality

- `partition([1,2,3,4,5], 2)` -> `[[1,2],[3,4],[5]]`
- `partition([1,2,3,4], 2)` -> `[[1,2],[3,4]]`
- `partition([1,2,3], 5)` -> `[[1,2,3]]`
- `partition([], 3)` -> `[]`
- `partition([1], 1)` -> `[[1]]`
- `partition(null, 2)` -> throws `PreconditionViolationException`
- `partition([1,2], 0)` -> throws `PreconditionViolationException`

### Test suite

The new `CollectionPartitionTests` class must verify the behavior above as a
self-contained, deterministic unit suite that does not rely on any external
service, file system, network, or execution order. It must, at minimum:

- Cover the uneven-last-chunk case, the exact-multiple case, the
  larger-than-list case, the empty-input case, and the single-element case.
- Express the chunk-count and chunk-content cases as a single data-driven test
  method fed by multiple `(input, size, expectedNumberOfChunks)` rows rather
  than one method per row.
- Verify both precondition failures (`null` list; non-positive `size`) by
  asserting the exception type and that its message is meaningful.
- Use grouping so a batch of related expectations (e.g. chunk count, order
  preservation, and round-trip concatenation) is all evaluated even when one
  fails.
- Carry human-readable descriptions for the test class and its methods.

Tests must pass for a correct implementation and must fail for a naive stub
(e.g. one that returns the whole list as a single chunk, drops the trailing
partial chunk, or skips the precondition checks).

## Acceptance Criteria

- `CollectionUtils.partition(List, int)` exists with the exact signature and the
  contract above.
- The new test class lives at
  `platform-tests/src/test/java/org/junit/platform/commons/util/CollectionPartitionTests.java`
  and contains at least 10 distinct test executions (counting each data-driven
  row separately), including the two precondition-violation cases and at least
  one grouped-assertion method.
- Running the suite in isolation passes:

  ```
  ./gradlew :platform-tests:test --tests "org.junit.platform.commons.util.CollectionPartitionTests"
  ```

- All "Expected Functionality" rows are satisfied, and a naive implementation
  that returns the list unchunked or drops the partial chunk fails at least one
  test.
