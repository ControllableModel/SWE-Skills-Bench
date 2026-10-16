# Task: Add a Run-Length Grouping Helper to CollectionUtils and Verify It

## Background

The `junit-platform-commons` module provides an internal `CollectionUtils`
helper (`org.junit.platform.commons.util.CollectionUtils`) with small,
dependency-free collection operations. This task adds a consecutive-run grouping
operation to that class together with a verification suite under the
`platform-tests` module.

## Files to Create/Modify

- `junit-platform-commons/src/main/java/org/junit/platform/commons/util/CollectionUtils.java` (modify) — add the new public static method described below.
- `platform-tests/src/test/java/org/junit/platform/commons/util/CollectionRunsTests.java` (new) — the verification suite. Place it in package `org.junit.platform.commons.util`, alongside the existing `CollectionUtilsTests`.

## Requirements

### New method

Add a public static method to `CollectionUtils` with exactly this signature:

```java
public static <T> java.util.List<java.util.List<T>> groupConsecutive(java.util.List<T> list)
```

It splits `list` into maximal runs of consecutive EQUAL elements, preserving
order.

### Behavior

- Each returned sub-list ("run") is a maximal contiguous block of elements that
  are equal to one another (by `equals`/`hashCode`).
- A new run begins whenever an element differs from the immediately preceding
  element.
- The concatenation of the returned runs, in order, equals the original list.
- An empty input yields an empty list of runs (`[]`).

### Constraints and edge cases

- `list` must not be `null`; passing `null` must cause a
  `org.junit.platform.commons.PreconditionViolationException` (use the module's
  existing precondition mechanism), with a message conveying that the list must
  not be `null`.
- Non-adjacent equal elements belong to separate runs (only consecutive equal
  elements are grouped together).
- The runs preserve element order and contain every element exactly once.

### Expected Functionality

- `groupConsecutive([1,1,2,3,3,3,1])` -> `[[1,1],[2],[3,3,3],[1]]`
- `groupConsecutive([1,2,3])` -> `[[1],[2],[3]]`
- `groupConsecutive([5,5,5])` -> `[[5,5,5]]`
- `groupConsecutive([])` -> `[]`
- `groupConsecutive([1])` -> `[[1]]`
- `groupConsecutive(["a","a","b","a"])` -> `[["a","a"],["b"],["a"]]` (non-adjacent equals split)
- `groupConsecutive(null)` -> throws `PreconditionViolationException`

### Test suite

The new `CollectionRunsTests` class must verify the behavior above as a
self-contained, deterministic unit suite that does not rely on any external
service, file system, network, or execution order. It must, at minimum:

- Cover the multiple-runs case, the all-distinct case, the all-equal case, the
  empty case, the single-element case, and the non-adjacent-equals case.
- Express the value cases as a single data-driven test method fed by multiple
  rows that pair an input with its expected number of runs (and/or expected run
  contents) rather than one method per row.
- Verify the precondition failure (`null` list) by asserting the exception type
  and that its message is meaningful.
- Use grouping so a batch of related expectations (e.g. number of runs, order
  preservation, and round-trip concatenation back to the input) is all evaluated
  even when one fails.
- Carry human-readable descriptions for the test class and its methods.

Tests must pass for a correct implementation and must fail for a naive stub
(e.g. one that groups all equal elements regardless of adjacency, returns one
run for the whole list, or skips the precondition check).

## Acceptance Criteria

- `CollectionUtils.groupConsecutive(List)` exists with the exact signature and
  the contract above.
- The new test class lives at
  `platform-tests/src/test/java/org/junit/platform/commons/util/CollectionRunsTests.java`
  and contains at least 10 distinct test executions (counting each data-driven
  row separately), including the precondition-violation case and at least one
  grouped-assertion method.
- Running the suite in isolation passes:

  ```
  ./gradlew :platform-tests:test --tests "org.junit.platform.commons.util.CollectionRunsTests"
  ```

- All "Expected Functionality" rows are satisfied, and a naive implementation
  that groups non-adjacent equals or returns a single run fails at least one
  test.
