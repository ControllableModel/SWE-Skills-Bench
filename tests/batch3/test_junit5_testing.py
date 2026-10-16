"""Verification suite for the `junit5-testing` skill task (variant ext3).

Task: add a fixed-size partitioning helper

    public static <T> java.util.List<java.util.List<T>> partition(java.util.List<T> list, int size)

to `org.junit.platform.commons.util.CollectionUtils` (junit-platform-commons),
plus a data-driven, grouped-assertion JUnit 5 verification suite
(`CollectionPartitionTests`) under the `platform-tests` module.

The `partition` method splits a list into consecutive chunks of at most `size`
elements, preserving order. Empty input yields an empty list of chunks. A
`null` list or a non-positive `size` must raise
`org.junit.platform.commons.PreconditionViolationException`.

What this file verifies:
  * L1 - the deliverable source files exist and are minimally well-formed
    (CollectionUtils declares the exact `partition` signature; the new test
    class sits in the correct package and uses data-driven + grouped-assertion
    + human-readable-description JUnit 5 constructs).
  * L2 - DYNAMIC EXECUTION via the repo's native Gradle toolchain:
      - the agent's own `CollectionPartitionTests` class compiles and passes,
        producing at least 10 executed test results (parsed from JUnit XML).
      - an INDEPENDENT JUnit 5 class (written by THIS file into the repo)
        exercises `CollectionUtils.partition` directly and pins down the exact
        contract from the requirement doc: chunk count = ceil(n/size), order
        preservation, round-trip concatenation, exact-multiple has no trailing
        partial chunk, empty -> [], and both precondition violations. A naive
        stub (returns the whole list as one chunk, drops the trailing partial
        chunk, or skips the precondition checks) fails the independent class
        regardless of what the agent wrote in its own test file.

The independent class is the discriminative core: it does not trust any test
file the agent authored.
"""

import os
import re
import subprocess
import xml.etree.ElementTree as ET

import pytest

REPO_DIR = "/workspace/junit5"

MAIN_SRC = os.path.join(
    REPO_DIR,
    "junit-platform-commons/src/main/java/org/junit/platform/commons/util/CollectionUtils.java",
)
TEST_DIR = os.path.join(
    REPO_DIR,
    "platform-tests/src/test/java/org/junit/platform/commons/util",
)
AGENT_TEST = os.path.join(TEST_DIR, "CollectionPartitionTests.java")

# Name chosen to be unlikely to collide with anything the agent created.
INDEP_CLASS = "PartitionContractProbeTests"
INDEP_TEST = os.path.join(TEST_DIR, INDEP_CLASS + ".java")

GRADLE_TIMEOUT = 1800

# Java toolchain auto-provisioning is driven by these env vars in the repo's
# gradle.properties (org.gradle.java.installations.fromEnv).
_GRADLE_ENV = dict(os.environ)
_GRADLE_ENV.setdefault("GRADLE_OPTS", "-Dorg.gradle.daemon=false")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _gradlew():
    g = os.path.join(REPO_DIR, "gradlew")
    assert os.path.isfile(g), f"gradlew wrapper missing at {g}"
    return g


def _run_gradle_tests(test_filter):
    """Run `:platform-tests:test` for a single fully-qualified test class.

    Returns (CompletedProcess, parsed_report_dict). The report dict maps each
    discovered TEST-*.xml file (for the requested class) to (tests, failures,
    errors, skipped, [testcase-names]).
    """
    g = _gradlew()
    simple = test_filter.split(".")[-1]
    # Clean previous results for this specific class to avoid stale reports.
    results_dir = os.path.join(REPO_DIR, "platform-tests/build/test-results/test")
    if os.path.isdir(results_dir):
        for fn in os.listdir(results_dir):
            if simple in fn:
                try:
                    os.remove(os.path.join(results_dir, fn))
                except OSError:
                    pass

    cmd = [
        g,
        ":platform-tests:test",
        "--tests",
        test_filter,
        "--rerun-tasks",
        "--console=plain",
        "--stacktrace",
    ]
    proc = subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=GRADLE_TIMEOUT,
        env=_GRADLE_ENV,
    )
    report = _parse_reports(results_dir, simple)
    return proc, report


def _parse_reports(results_dir, simple_class_name):
    found = {}
    if not os.path.isdir(results_dir):
        return found
    for fn in os.listdir(results_dir):
        if not fn.endswith(".xml"):
            continue
        if simple_class_name not in fn:
            continue
        path = os.path.join(results_dir, fn)
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")
        for suite in suites:
            tests = int(suite.get("tests", "0"))
            failures = int(suite.get("failures", "0"))
            errors = int(suite.get("errors", "0"))
            skipped = int(suite.get("skipped", "0"))
            names = [tc.get("name", "") for tc in suite.findall("testcase")]
            found[fn] = (tests, failures, errors, skipped, names)
    return found


def _report_totals(report):
    t = f = e = s = 0
    names = []
    for tests, failures, errors, skipped, n in report.values():
        t += tests
        f += failures
        e += errors
        s += skipped
        names.extend(n)
    return t, f, e, s, names


# ---------------------------------------------------------------------------
# Independent verification test class (the discriminative core).
# Compiled & run by gradle against the agent's production code, so a naive
# `partition` cannot pass it.
# ---------------------------------------------------------------------------

_INDEP_SOURCE = r"""/* Auto-generated by the benchmark verifier. Do not edit. */
package org.junit.platform.commons.util;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.platform.commons.PreconditionViolationException;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.stream.Stream;

class __INDEP_CLASS__ {

    private static List<Integer> range(int n) {
        List<Integer> out = new ArrayList<>();
        for (int i = 1; i <= n; i++) {
            out.add(i);
        }
        return out;
    }

    // (input-size, chunk-size, expected-number-of-chunks)
    @ParameterizedTest
    @MethodSource("chunkCountRows")
    void chunkCountIsCeilDivision(int inputSize, int size, int expectedChunks) {
        List<Integer> input = range(inputSize);
        List<List<Integer>> result = CollectionUtils.partition(input, size);

        // round-trip: concatenation in order must equal original input
        List<Integer> flattened = new ArrayList<>();
        for (List<Integer> chunk : result) {
            flattened.addAll(chunk);
        }

        // every chunk except possibly the last has exactly `size` elements
        boolean intermediateChunksFull = true;
        for (int i = 0; i < result.size() - 1; i++) {
            if (result.get(i).size() != size) {
                intermediateChunksFull = false;
                break;
            }
        }
        boolean lastChunkInRange = result.isEmpty()
            || (result.get(result.size() - 1).size() >= 1
                && result.get(result.size() - 1).size() <= size);

        assertAll(
            () -> assertEquals(expectedChunks, result.size(),
                "chunk count must equal ceil(n/size) for n=" + inputSize + " size=" + size),
            () -> assertEquals(input, flattened,
                "concatenation of chunks must equal the original list in order"),
            () -> assertTrue(intermediateChunksFull,
                "every chunk except the last must contain exactly `size` elements"),
            () -> assertTrue(lastChunkInRange,
                "the last chunk must hold between 1 and `size` elements")
        );
    }

    static Stream<Arguments> chunkCountRows() {
        return Stream.of(
            Arguments.of(5, 2, 3),    // uneven last chunk -> [[1,2],[3,4],[5]]
            Arguments.of(4, 2, 2),    // exact multiple    -> [[1,2],[3,4]]
            Arguments.of(3, 5, 1),    // size larger than list -> [[1,2,3]]
            Arguments.of(1, 1, 1),    // single element    -> [[1]]
            Arguments.of(6, 3, 2),    // exact multiple, larger
            Arguments.of(7, 3, 3),    // uneven, multi-chunk
            Arguments.of(10, 4, 3)    // uneven, multi-chunk
        );
    }

    @Test
    void unevenLastChunkExactContents() {
        assertEquals(
            Arrays.asList(Arrays.asList(1, 2), Arrays.asList(3, 4), Arrays.asList(5)),
            CollectionUtils.partition(Arrays.asList(1, 2, 3, 4, 5), 2));
    }

    @Test
    void exactMultipleHasNoTrailingPartialChunk() {
        List<List<Integer>> result =
            CollectionUtils.partition(Arrays.asList(1, 2, 3, 4), 2);
        assertAll(
            () -> assertEquals(2, result.size(),
                "exact multiple must produce exactly n/size chunks, no empty trailing chunk"),
            () -> assertEquals(Arrays.asList(1, 2), result.get(0)),
            () -> assertEquals(Arrays.asList(3, 4), result.get(1)),
            () -> assertEquals(2, result.get(result.size() - 1).size(),
                "the last chunk of an exact multiple must be full")
        );
    }

    @Test
    void largerThanListYieldsSingleChunk() {
        assertEquals(
            Arrays.asList(Arrays.asList(1, 2, 3)),
            CollectionUtils.partition(Arrays.asList(1, 2, 3), 5));
    }

    @Test
    void emptyInputYieldsEmptyListOfChunks() {
        List<List<Integer>> result =
            CollectionUtils.partition(Collections.<Integer>emptyList(), 3);
        assertTrue(result.isEmpty(),
            "empty input list must yield an empty list of chunks, was: " + result);
    }

    @Test
    void singleElementYieldsSingleSingletonChunk() {
        assertEquals(
            Arrays.asList(Arrays.asList(1)),
            CollectionUtils.partition(Arrays.asList(1), 1));
    }

    @Test
    void everyElementAppearsExactlyOnceInOrder() {
        List<Integer> input = range(13);
        List<List<Integer>> result = CollectionUtils.partition(input, 4);
        List<Integer> flattened = new ArrayList<>();
        for (List<Integer> chunk : result) {
            flattened.addAll(chunk);
        }
        assertAll(
            () -> assertEquals(input, flattened,
                "round-trip concatenation must equal the original list"),
            () -> assertEquals(input.size(), flattened.size(),
                "no element may be dropped or duplicated"),
            () -> assertEquals(4, result.size(),
                "ceil(13/4) == 4 chunks expected"),
            () -> assertEquals(1, result.get(result.size() - 1).size(),
                "last chunk of 13 elements in groups of 4 has exactly 1 element")
        );
    }

    @Test
    void nullListThrowsPreconditionViolation() {
        PreconditionViolationException ex = assertThrows(
            PreconditionViolationException.class,
            () -> CollectionUtils.partition(null, 2));
        assertTrue(ex.getMessage() != null && !ex.getMessage().isEmpty(),
            "precondition message must be meaningful, was: " + ex.getMessage());
    }

    @Test
    void nonPositiveSizeThrowsPreconditionViolation() {
        // size == 0 and negative size must both be rejected, even for non-empty lists
        assertThrows(PreconditionViolationException.class,
            () -> CollectionUtils.partition(Arrays.asList(1, 2), 0));
        assertThrows(PreconditionViolationException.class,
            () -> CollectionUtils.partition(Arrays.asList(1, 2), -1));
    }

    @Test
    void preconditionCheckedEvenForEmptyList() {
        // a stub that "fast-paths" empty input before validating size must fail this
        assertThrows(PreconditionViolationException.class,
            () -> CollectionUtils.partition(Collections.<Integer>emptyList(), 0));
    }
}
"""


def _write_indep_class():
    src = _INDEP_SOURCE.replace("__INDEP_CLASS__", INDEP_CLASS)
    with open(INDEP_TEST, "w", encoding="utf-8") as fh:
        fh.write(src)


def _remove_indep_class():
    for p in (INDEP_TEST, INDEP_TEST + ".bak"):
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


@pytest.fixture(scope="module", autouse=True)
def _cleanup_indep_class():
    # Ensure no stale copy from a prior run lingers, and remove ours after.
    _remove_indep_class()
    yield
    _remove_indep_class()


class TestJunit5Testing:
    REPO_DIR = "/workspace/junit5"

    # ----------------------------- L1 -----------------------------------

    def test_repo_and_main_source_present(self):
        """L1: the repo, gradle wrapper and CollectionUtils source all exist."""
        assert os.path.isdir(REPO_DIR), f"repo missing at {REPO_DIR}"
        assert os.path.isfile(_gradlew()), "gradlew wrapper missing"
        assert os.path.isfile(MAIN_SRC), f"CollectionUtils.java missing at {MAIN_SRC}"

    def test_partition_signature_present(self):
        """L1: CollectionUtils declares the exact public partition signature
        returning a List of Lists and taking (List, int)."""
        content = _read(MAIN_SRC)
        # exact signature, tolerant of whitespace, the generic <T> param, and
        # of fully-qualified or imported List references.
        pattern = re.compile(
            r"public\s+static\s+<\s*\w+\s*>\s+"
            r"(?:java\.util\.)?List\s*<\s*(?:java\.util\.)?List\s*<\s*\w+\s*>\s*>\s+"
            r"partition\s*\(\s*"
            r"(?:final\s+)?(?:@\w+\s+)?(?:java\.util\.)?List\s*<\s*\w+\s*>\s+\w+\s*,\s*"
            r"(?:final\s+)?int\s+\w+\s*\)"
        )
        assert pattern.search(content), (
            "expected `public static <T> List<List<T>> partition(List<T>, int)` "
            "signature in CollectionUtils.java"
        )

    def test_agent_test_file_exists_in_correct_package(self):
        """L1: CollectionPartitionTests is placed in the required package/dir."""
        assert os.path.isfile(AGENT_TEST), (
            f"expected new test class at {AGENT_TEST}"
        )
        content = _read(AGENT_TEST)
        assert re.search(
            r"package\s+org\.junit\.platform\.commons\.util\s*;", content
        ), "test class must declare package org.junit.platform.commons.util"
        assert "class CollectionPartitionTests" in content, (
            "file must declare class CollectionPartitionTests"
        )

    def test_agent_test_uses_data_driven_and_grouping_constructs(self):
        """L1: agent suite uses a parameterized (data-driven) method and a
        grouped-assertion (assertAll) method, per the requirement doc."""
        content = _read(AGENT_TEST)
        assert "@ParameterizedTest" in content, (
            "chunk-count/content cases must be expressed as a single "
            "data-driven (@ParameterizedTest) method fed by multiple rows"
        )
        assert any(
            tok in content
            for tok in ("@MethodSource", "@CsvSource", "@ArgumentsSource", "@FieldSource")
        ), "data-driven method must be fed by a rows source (e.g. @MethodSource/@CsvSource)"
        assert "assertAll" in content, (
            "at least one grouped-assertion method (assertAll) is required so a "
            "batch of related expectations is all evaluated even when one fails"
        )

    def test_agent_suite_carries_human_readable_descriptions(self):
        """L1: the requirement doc mandates human-readable descriptions for the
        test class and its methods (@DisplayName)."""
        content = _read(AGENT_TEST)
        count = len(re.findall(r"@DisplayName\s*\(", content))
        assert count >= 2, (
            "expected @DisplayName on the class and at least one method "
            f"(found {count} occurrences)"
        )

    def test_agent_suite_covers_precondition_cases_textually(self):
        """L1: the agent suite references the precondition exception type for
        both the null-list and non-positive-size cases (behavior is verified
        dynamically in L2; this guards the deliverable's intent)."""
        content = _read(AGENT_TEST)
        assert "PreconditionViolationException" in content, (
            "agent suite must assert PreconditionViolationException for the "
            "null-list and non-positive-size cases"
        )

    # ----------------------------- L2 -----------------------------------

    def test_agent_suite_passes_with_enough_executions(self):
        """L2: the agent's CollectionPartitionTests compiles, passes, and
        reports at least 10 executed test results (data rows counted)."""
        proc, report = _run_gradle_tests(
            "org.junit.platform.commons.util.CollectionPartitionTests"
        )
        assert report, (
            "no JUnit XML report produced for CollectionPartitionTests.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}\n"
            f"--- gradle stderr (tail) ---\n{proc.stderr[-3000:]}"
        )
        tests, failures, errors, skipped, _ = _report_totals(report)
        assert failures == 0 and errors == 0, (
            f"agent suite had failures={failures} errors={errors}.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        executed = tests - skipped
        assert executed >= 10, (
            f"expected >= 10 executed tests in CollectionPartitionTests, "
            f"got {executed} (tests={tests}, skipped={skipped})"
        )

    def test_independent_chunking_contract(self):
        """L2: independent suite pins chunk count = ceil(n/size), order
        preservation, round-trip concatenation, full intermediate chunks, and
        the exact-multiple / larger-than-list / single-element / empty cases.
        A stub returning the list as one chunk or dropping the partial chunk
        fails."""
        _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, (
            "independent probe produced no report (likely compile failure).\n"
            f"--- gradle stderr (tail) ---\n{proc.stderr[-4000:]}\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-2000:]}"
        )
        tests, failures, errors, skipped, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "independent partition contract probe FAILED -> production "
            "`partition` does not satisfy the chunk-count/order/round-trip "
            "contract.\n"
            f"failures={failures} errors={errors} tests={tests}\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-4000:]}"
        )
        # sanity: the probe really ran its many cases (7 param rows + 9 @Test)
        assert tests - skipped >= 15, (
            f"independent probe executed too few cases ({tests - skipped}); "
            "it may not have run correctly"
        )

    def test_independent_probe_actually_distinguishes_stub(self):
        """L2 (meta): structural guard so the independent probe can never be
        silently weakened - it must keep the chunk-count, round-trip,
        full-intermediate-chunk and precondition assertions on disk."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        src = _read(INDEP_TEST)
        assert "expectedChunks, result.size()" in src, "probe lost chunk-count assertion"
        assert "assertEquals(input, flattened" in src, "probe lost round-trip assertion"
        assert "intermediateChunksFull" in src, (
            "probe lost full-intermediate-chunk assertion"
        )
        assert "exactMultipleHasNoTrailingPartialChunk" in src, (
            "probe lost the exact-multiple (no trailing partial chunk) case"
        )
        assert "PreconditionViolationException" in src, (
            "probe lost precondition assertions"
        )

    def test_empty_and_boundary_cases_via_independent_probe(self):
        """L2: empty input -> [], single element -> [[x]], and larger-than-list
        -> single chunk, all verified by the independent probe having executed
        those named cases without failure."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent boundary verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "empty/boundary contract failed in independent probe.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        for expected_case in (
            "emptyInputYieldsEmptyListOfChunks",
            "singleElementYieldsSingleSingletonChunk",
            "largerThanListYieldsSingleChunk",
        ):
            assert expected_case in joined, (
                f"expected boundary case '{expected_case}' to have executed"
            )

    def test_precondition_failures_via_independent_probe(self):
        """L2: null list and non-positive size both raise
        PreconditionViolationException, and the size precondition is enforced
        even for an empty list (so a stub that fast-paths empty input fails)."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent precondition verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "precondition contract failed in independent probe -> `partition` "
            "skipped or mis-implemented null / non-positive-size checks.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        for expected_case in (
            "nullListThrowsPreconditionViolation",
            "nonPositiveSizeThrowsPreconditionViolation",
            "preconditionCheckedEvenForEmptyList",
        ):
            assert expected_case in joined, (
                f"expected precondition case '{expected_case}' to have executed"
            )
