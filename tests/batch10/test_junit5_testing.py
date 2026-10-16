"""Verification suite for the `junit5-testing` skill task (variant ext10).

Task: add a run-length grouping helper

    public static <T> java.util.List<java.util.List<T>> groupConsecutive(java.util.List<T> list)

to `org.junit.platform.commons.util.CollectionUtils` (junit-platform-commons),
plus a data-driven, grouped-assertion JUnit 5 verification suite
`CollectionRunsTests` under the `platform-tests` module, in package
`org.junit.platform.commons.util`.

`groupConsecutive` splits a list into maximal runs of CONSECUTIVE equal
elements, preserving order:
    [1,1,2,3,3,3,1] -> [[1,1],[2],[3,3,3],[1]]   (note: non-adjacent equals split)
    []              -> []
    null            -> PreconditionViolationException

What this file verifies:
  * L1 - the deliverable source files exist and are minimally well-formed
    (CollectionUtils declares the exact groupConsecutive signature; the new
    test class lives in the right package and uses data-driven + grouped
    assertion + @DisplayName constructs).
  * L2 - DYNAMIC EXECUTION via the repo's native Gradle toolchain:
      - the agent's own `CollectionRunsTests` compiles and passes, producing
        at least 10 executed test results (data rows counted), parsed from the
        JUnit XML report.
      - an INDEPENDENT JUnit 5 test class (written by THIS file into the repo)
        exercises `CollectionUtils.groupConsecutive` directly and pins down the
        exact contract.  A naive stub (groups non-adjacent equals, returns a
        single run for the whole list, drops elements, or skips the null
        precondition) FAILS this independent class regardless of what the agent
        wrote in its own test file.

The independent class is the discriminative core: it does not trust any test
file the agent authored.

Native acceptance command this drives:
    ./gradlew :platform-tests:test --tests "org.junit.platform.commons.util.CollectionRunsTests"
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
AGENT_TEST = os.path.join(TEST_DIR, "CollectionRunsTests.java")

# Name chosen to be unlikely to collide with anything the agent created.
INDEP_CLASS = "GroupConsecutiveContractProbeTests"
INDEP_TEST = os.path.join(TEST_DIR, INDEP_CLASS + ".java")

GRADLE_TIMEOUT = 1800

# Java toolchain auto-provisioning is driven by env vars in the repo's
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
    discovered TEST-*.xml file (for the requested class) to
    (tests, failures, errors, skipped, [testcase-names]).
    """
    g = _gradlew()
    results_dir = os.path.join(REPO_DIR, "platform-tests/build/test-results/test")
    simple = test_filter.split(".")[-1]
    # Clean previous results for this specific class to avoid stale reports.
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
# `groupConsecutive` cannot pass it.
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

    // -------- exact value contract, data-driven --------

    @ParameterizedTest
    @MethodSource("integerRows")
    void groupsConsecutiveRunsExactly(List<Integer> input, List<List<Integer>> expected) {
        List<List<Integer>> actual = CollectionUtils.groupConsecutive(input);
        // flatten for round-trip check
        List<Integer> roundTrip = new ArrayList<>();
        for (List<Integer> run : actual) {
            roundTrip.addAll(run);
        }
        assertAll(
            () -> assertEquals(expected, actual, "runs must match exactly for " + input),
            () -> assertEquals(expected.size(), actual.size(),
                    "number of runs must match for " + input),
            () -> assertEquals(input, roundTrip,
                    "concatenation of runs must round-trip to the original list")
        );
    }

    static Stream<Arguments> integerRows() {
        return Stream.of(
            // multiple-runs case, INCLUDING a non-adjacent equal (trailing 1)
            Arguments.of(Arrays.asList(1, 1, 2, 3, 3, 3, 1),
                    Arrays.asList(Arrays.asList(1, 1), Arrays.asList(2),
                            Arrays.asList(3, 3, 3), Arrays.asList(1))),
            // all distinct
            Arguments.of(Arrays.asList(1, 2, 3),
                    Arrays.asList(Arrays.asList(1), Arrays.asList(2), Arrays.asList(3))),
            // all equal -> single run
            Arguments.of(Arrays.asList(5, 5, 5),
                    Arrays.asList(Arrays.asList(5, 5, 5))),
            // single element
            Arguments.of(Arrays.asList(7),
                    Arrays.asList(Arrays.asList(7))),
            // empty -> empty list of runs
            Arguments.of(Collections.<Integer>emptyList(),
                    Collections.<List<Integer>>emptyList()),
            // alternating, non-adjacent equals must split into many runs
            Arguments.of(Arrays.asList(1, 2, 1, 2),
                    Arrays.asList(Arrays.asList(1), Arrays.asList(2),
                            Arrays.asList(1), Arrays.asList(2)))
        );
    }

    // -------- string non-adjacent split, the stub-killer --------

    @Test
    void nonAdjacentEqualsAreSeparateRuns() {
        List<String> input = Arrays.asList("a", "a", "b", "a");
        List<List<String>> actual = CollectionUtils.groupConsecutive(input);
        // a naive grouping that buckets ALL equal elements would yield 2 runs
        // ([a,a,a],[b]); the correct contract yields 3 runs.
        assertAll(
            () -> assertEquals(3, actual.size(),
                    "non-adjacent equal elements must form separate runs"),
            () -> assertEquals(Arrays.asList("a", "a"), actual.get(0)),
            () -> assertEquals(Arrays.asList("b"), actual.get(1)),
            () -> assertEquals(Arrays.asList("a"), actual.get(2))
        );
    }

    @Test
    void everyElementAppearsExactlyOnceInOrder() {
        List<Integer> input = Arrays.asList(4, 4, 9, 9, 9, 4, 1, 1);
        List<List<Integer>> actual = CollectionUtils.groupConsecutive(input);
        List<Integer> flat = new ArrayList<>();
        for (List<Integer> run : actual) {
            flat.addAll(run);
        }
        assertAll(
            () -> assertEquals(input, flat, "round-trip must preserve order and count"),
            () -> assertEquals(4, actual.size(), "expected 4 maximal runs"),
            () -> assertEquals(input.size(), flat.size(), "no element dropped or duplicated")
        );
    }

    @Test
    void emptyInputYieldsEmptyRuns() {
        assertTrue(CollectionUtils.groupConsecutive(Collections.<Integer>emptyList()).isEmpty(),
                "empty input must yield an empty list of runs");
    }

    @Test
    void singleElementYieldsSingleRun() {
        List<List<String>> actual = CollectionUtils.groupConsecutive(Arrays.asList("only"));
        assertAll(
            () -> assertEquals(1, actual.size()),
            () -> assertEquals(Arrays.asList("only"), actual.get(0))
        );
    }

    @Test
    void allEqualYieldsExactlyOneRun() {
        List<List<Integer>> actual = CollectionUtils.groupConsecutive(Arrays.asList(2, 2, 2, 2));
        assertAll(
            () -> assertEquals(1, actual.size(), "all-equal input is one maximal run"),
            () -> assertEquals(Arrays.asList(2, 2, 2, 2), actual.get(0))
        );
    }

    @Test
    void nullListThrowsPreconditionViolation() {
        PreconditionViolationException ex = assertThrows(
            PreconditionViolationException.class,
            () -> CollectionUtils.groupConsecutive(null));
        assertTrue(ex.getMessage() != null && ex.getMessage().toLowerCase().contains("null"),
            "message must mention null, was: " + ex.getMessage());
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

    def test_group_consecutive_signature_present(self):
        """L1: CollectionUtils declares the exact public generic
        groupConsecutive(List) signature."""
        content = _read(MAIN_SRC)
        # public static <T> List<List<T>> groupConsecutive(List<T> ...)
        # tolerant of whitespace, fully-qualified vs imported names, and
        # optional final/annotation modifiers on the parameter.
        pattern = re.compile(
            r"public\s+static\s*<\s*\w+\s*>\s*"
            r"(?:java\.util\.)?List\s*<\s*(?:java\.util\.)?List\s*<\s*\w+\s*>\s*>\s+"
            r"groupConsecutive\s*\(\s*"
            r"(?:final\s+)?(?:@\w+\s+)?(?:java\.util\.)?List\s*<\s*\w+\s*>\s+\w+\s*\)"
        )
        assert pattern.search(content), (
            "expected `public static <T> List<List<T>> groupConsecutive("
            "List<T>)` signature in CollectionUtils.java"
        )

    def test_agent_test_file_exists_in_correct_package(self):
        """L1: CollectionRunsTests is placed in the required package/dir."""
        assert os.path.isfile(AGENT_TEST), (
            f"expected new test class at {AGENT_TEST}"
        )
        content = _read(AGENT_TEST)
        assert re.search(
            r"package\s+org\.junit\.platform\.commons\.util\s*;", content
        ), "test class must declare package org.junit.platform.commons.util"
        assert "class CollectionRunsTests" in content, (
            "file must declare class CollectionRunsTests"
        )

    def test_agent_test_uses_data_driven_and_grouping_constructs(self):
        """L1: agent suite uses a parameterized (data-driven) method and a
        grouped-assertion (assertAll) method, per the requirement doc."""
        content = _read(AGENT_TEST)
        assert "@ParameterizedTest" in content, (
            "value cases must be expressed as a single data-driven "
            "(@ParameterizedTest) method"
        )
        assert any(
            tok in content
            for tok in ("@MethodSource", "@CsvSource", "@ArgumentsSource", "@FieldSource")
        ), "data-driven method must be fed by a rows source (e.g. @MethodSource/@CsvSource)"
        assert "assertAll" in content, (
            "at least one grouped-assertion method (assertAll) is required"
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

    def test_agent_suite_checks_precondition(self):
        """L1: agent suite references the precondition exception type and a
        null input, so the precondition case is actually exercised."""
        content = _read(AGENT_TEST)
        assert "PreconditionViolationException" in content, (
            "agent suite must verify the null-input PreconditionViolationException"
        )
        assert "null" in content, (
            "agent suite must exercise the null-list precondition case"
        )

    # ----------------------------- L2 -----------------------------------

    def test_agent_suite_passes_with_enough_executions(self):
        """L2: the agent's CollectionRunsTests compiles, passes, and reports at
        least 10 executed test results (data rows counted)."""
        proc, report = _run_gradle_tests(
            "org.junit.platform.commons.util.CollectionRunsTests"
        )
        assert report, (
            "no JUnit XML report produced for CollectionRunsTests.\n"
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
            f"expected >= 10 executed tests in CollectionRunsTests, "
            f"got {executed} (tests={tests}, skipped={skipped})"
        )

    def test_independent_exact_runs_contract(self):
        """L2: independent suite pins exact run contents, run count and
        round-trip concatenation. A stub that returns one run, drops elements,
        or mis-splits fails this."""
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
            "independent groupConsecutive contract probe FAILED -> production "
            "`groupConsecutive` does not satisfy the run-grouping / round-trip "
            "contract.\n"
            f"failures={failures} errors={errors} tests={tests}\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-4000:]}"
        )
        # sanity: the parameterized rows + standalone cases all ran
        assert tests - skipped >= 11, (
            f"independent probe executed too few cases ({tests - skipped}); "
            "it may not have run correctly"
        )

    def test_independent_probe_is_discriminative(self):
        """L2 (meta): structural guard so the independent probe can never be
        silently weakened away from the stub-killing assertions (non-adjacent
        split, round-trip, null precondition)."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        src = _read(INDEP_TEST)
        assert "nonAdjacentEqualsAreSeparateRuns" in src, (
            "probe lost non-adjacent-split assertion (the key stub-killer)"
        )
        assert "round-trip" in src or "roundTrip" in src, (
            "probe lost round-trip concatenation assertion"
        )
        assert "PreconditionViolationException" in src, (
            "probe lost null-precondition assertion"
        )
        assert "assertAll" in src, "probe lost grouped assertions"

    def test_non_adjacent_split_via_independent_probe(self):
        """L2: the decisive case -- ["a","a","b","a"] must yield 3 runs, not a
        single bucket of all equal 'a's. A naive grouping that buckets all
        equal elements regardless of adjacency fails here."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent non-adjacent verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "non-adjacent-equals contract failed in independent probe -> "
            "`groupConsecutive` groups non-consecutive equals (naive stub).\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        assert "nonAdjacentEqualsAreSeparateRuns" in joined, (
            "expected the non-adjacent-equals case to have executed"
        )

    def test_roundtrip_and_emptiness_via_independent_probe(self):
        """L2: every element appears exactly once in order (round-trip), the
        empty input yields empty runs, and all-equal yields one run. These
        catch element-dropping / single-run stubs."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent round-trip verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "round-trip / emptiness / all-equal contract failed in probe.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        for expected_case in (
            "everyElementAppearsExactlyOnceInOrder",
            "emptyInputYieldsEmptyRuns",
            "allEqualYieldsExactlyOneRun",
        ):
            assert expected_case in joined, (
                f"expected case '{expected_case}' to have executed"
            )

    def test_null_precondition_via_independent_probe(self):
        """L2: passing null raises PreconditionViolationException with a
        message mentioning null. A stub that skips the precondition check
        (e.g. NPEs or returns []) fails this."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent precondition verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "null-precondition contract failed in independent probe -> "
            "`groupConsecutive` skipped or mis-implemented the null check.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        assert "nullListThrowsPreconditionViolation" in joined, (
            "expected the null-precondition case to have executed"
        )
