"""Verification suite for the `junit5-testing` skill task (variant ext7).

Task: add an order-preserving de-duplication helper
`CollectionUtils.distinct(List<T>)` to the `junit-platform-commons` module
plus a data-driven, grouped-assertion JUnit 5 verification suite
(`CollectionDistinctTests`) under `platform-tests`.

What this file verifies:
  * L1 - the deliverable source files exist and are minimally well-formed
    (correct package, exact `distinct` signature present, the new test class
    uses data-driven + grouped-assertion JUnit 5 constructs, human-readable
    descriptions).
  * L2 - DYNAMIC EXECUTION via the repo's native Gradle toolchain:
      - the agent's own `CollectionDistinctTests` class compiles and passes,
        producing at least 10 executed test results (parsed from the JUnit XML
        report).
      - an INDEPENDENT JUnit 5 test class (written by THIS file into the repo)
        exercises `CollectionUtils.distinct` directly and pins down the exact
        contract from the requirement doc. A naive stub (returns the input
        unchanged, sorts instead of preserving first-occurrence order, keeps
        last occurrences, mutates the input, or skips the precondition check)
        fails this independent class regardless of what the agent wrote in its
        own test file.

The independent class is the discriminative core: it does not trust any test
file the agent authored.

Native acceptance command driven by L2:
    ./gradlew :platform-tests:test --tests \
        "org.junit.platform.commons.util.CollectionDistinctTests"
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
AGENT_TEST = os.path.join(TEST_DIR, "CollectionDistinctTests.java")

# Name chosen to be unlikely to collide with anything the agent created.
INDEP_CLASS = "DistinctContractProbeTests"
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
    # Clean previous results for this specific class to avoid stale reports.
    results_dir = os.path.join(REPO_DIR, "platform-tests/build/test-results/test")
    if os.path.isdir(results_dir):
        for fn in os.listdir(results_dir):
            if test_filter.split(".")[-1] in fn:
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
    report = _parse_reports(results_dir, test_filter.split(".")[-1])
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
# This is OUR contract probe; it is compiled & run by gradle against the
# agent's production code, so a naive `distinct` cannot pass it.
# ---------------------------------------------------------------------------

_INDEP_SOURCE = r"""/* Auto-generated by the benchmark verifier. Do not edit. */
package org.junit.platform.commons.util;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertIterableEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
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

    @ParameterizedTest
    @MethodSource("distinctRows")
    void preservesFirstOccurrenceOrder(List<Object> input, List<Object> expected) {
        // snapshot a defensive copy to detect input mutation
        List<Object> before = new ArrayList<>(input);
        List<Object> actual = CollectionUtils.distinct(input);
        assertAll(
            () -> assertIterableEquals(expected, actual,
                    "distinct(" + before + ") must equal " + expected),
            () -> assertEquals(expected.size(), actual.size(),
                    "result size must match expected distinct count"),
            () -> assertIterableEquals(before, input,
                    "input list must not be mutated")
        );
    }

    static Stream<Arguments> distinctRows() {
        return Stream.of(
            // duplicates removed, first-occurrence order preserved
            Arguments.of(intList(1, 2, 1, 3, 2), intList(1, 2, 3)),
            // all identical -> single element
            Arguments.of(intList(3, 3, 3), intList(3)),
            // already distinct -> unchanged content/order
            Arguments.of(intList(1, 2, 3), intList(1, 2, 3)),
            // empty -> empty
            Arguments.of(new ArrayList<Object>(), new ArrayList<Object>()),
            // string first-occurrence order: "b","a","b","c","a" -> "b","a","c"
            Arguments.of(strList("b", "a", "b", "c", "a"), strList("b", "a", "c")),
            // distinguishes "keep first" from "keep last": [a,b,a] -> [a,b] not [b,a]
            Arguments.of(strList("a", "b", "a"), strList("a", "b")),
            // distinguishes "preserve order" from "sort": [3,1,2,1] -> [3,1,2]
            Arguments.of(intList(3, 1, 2, 1), intList(3, 1, 2)),
            // single element
            Arguments.of(intList(7), intList(7)),
            // interleaved duplicates
            Arguments.of(strList("x", "y", "x", "y", "z"), strList("x", "y", "z"))
        );
    }

    @Test
    void resultIsADistinctInstanceFromInput() {
        List<Integer> input = intList(1, 2, 3);
        List<Object> result = CollectionUtils.distinct(input);
        // a new list instance must be returned, never the same reference
        assertNotSame(input, result, "distinct must return a NEW list instance");
        assertIterableEquals(input, result, "already-distinct content preserved");
    }

    @Test
    void inputWithDuplicatesIsNotMutated() {
        List<Integer> input = new ArrayList<>(Arrays.asList(1, 2, 1, 3, 2));
        CollectionUtils.distinct(input);
        assertIterableEquals(Arrays.asList(1, 2, 1, 3, 2), input,
            "the original input list must remain unchanged after distinct()");
    }

    @Test
    void keepsFirstNotLastOccurrence() {
        // [a, b, c, a, b] -> [a, b, c]; a stub that keeps last would give [c,a,b]
        List<Object> result = CollectionUtils.distinct(strList("a", "b", "c", "a", "b"));
        assertIterableEquals(strList("a", "b", "c"), result);
    }

    @Test
    void doesNotSortElements() {
        // [5, 3, 5, 1] -> [5, 3, 1]; a sorting stub would give [1, 3, 5]
        List<Object> result = CollectionUtils.distinct(intList(5, 3, 5, 1));
        assertIterableEquals(intList(5, 3, 1), result);
    }

    @Test
    void emptyInputYieldsEmptyList() {
        List<Object> result = CollectionUtils.distinct(new ArrayList<Object>());
        assertTrue(result.isEmpty(), "empty input must yield an empty result");
    }

    @Test
    void nullListThrowsPreconditionViolation() {
        PreconditionViolationException ex = assertThrows(
            PreconditionViolationException.class,
            () -> CollectionUtils.distinct(null));
        assertTrue(ex.getMessage() != null && ex.getMessage().toLowerCase().contains("null"),
            "message must mention null, was: " + ex.getMessage());
    }

    // ---- helpers (typed as List<Object> for uniform Arguments rows) ----

    private static List<Object> intList(Object... values) {
        List<Object> l = new ArrayList<>();
        Collections.addAll(l, values);
        return l;
    }

    private static List<Object> strList(Object... values) {
        List<Object> l = new ArrayList<>();
        Collections.addAll(l, values);
        return l;
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

    def test_distinct_signature_present(self):
        """L1: CollectionUtils declares the exact public distinct signature
        `public static <T> List<T> distinct(List<T> list)` (whitespace and the
        optional `java.util.` qualifier tolerated)."""
        content = _read(MAIN_SRC)
        pattern = re.compile(
            r"public\s+static\s+<\s*T\s*>\s+"
            r"(?:java\.util\.)?List\s*<\s*T\s*>\s+distinct\s*\(\s*"
            r"(?:final\s+)?(?:@\w+\s+)?(?:java\.util\.)?List\s*<\s*T\s*>\s+\w+\s*\)"
        )
        assert pattern.search(content), (
            "expected `public static <T> List<T> distinct(List<T>)` signature "
            "in CollectionUtils.java"
        )

    def test_agent_test_file_exists_in_correct_package(self):
        """L1: CollectionDistinctTests is placed in the required package/dir."""
        assert os.path.isfile(AGENT_TEST), (
            f"expected new test class at {AGENT_TEST}"
        )
        content = _read(AGENT_TEST)
        assert re.search(
            r"package\s+org\.junit\.platform\.commons\.util\s*;", content
        ), "test class must declare package org.junit.platform.commons.util"
        assert "class CollectionDistinctTests" in content, (
            "file must declare class CollectionDistinctTests"
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

    def test_agent_suite_verifies_precondition_and_descriptions(self):
        """L1: agent suite asserts the PreconditionViolationException for the
        null case and carries human-readable descriptions (@DisplayName) on the
        class and at least one method."""
        content = _read(AGENT_TEST)
        assert "PreconditionViolationException" in content, (
            "agent suite must verify the null-list precondition failure type"
        )
        count = len(re.findall(r"@DisplayName\s*\(", content))
        assert count >= 2, (
            "expected @DisplayName on the class and at least one method "
            f"(found {count} occurrences)"
        )

    # ----------------------------- L2 -----------------------------------

    def test_agent_suite_passes_with_enough_executions(self):
        """L2: the agent's CollectionDistinctTests compiles, passes, and
        reports at least 10 executed test results (data rows counted)."""
        proc, report = _run_gradle_tests(
            "org.junit.platform.commons.util.CollectionDistinctTests"
        )
        assert report, (
            "no JUnit XML report produced for CollectionDistinctTests.\n"
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
            f"expected >= 10 executed tests in CollectionDistinctTests, "
            f"got {executed} (tests={tests}, skipped={skipped})"
        )

    def test_independent_order_preserving_contract(self):
        """L2: independent suite pins exact first-occurrence ordering, distinct
        content, result size and input-immutability. A stub that sorts, keeps
        last occurrences, or returns the input unchanged fails."""
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
            "independent distinct contract probe FAILED -> production "
            "`distinct` does not satisfy the first-occurrence/order/immutability "
            "contract.\n"
            f"failures={failures} errors={errors} tests={tests}\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-4000:]}"
        )
        # sanity: the probe really ran its many cases (9 rows + 6 @Test methods)
        assert tests - skipped >= 14, (
            f"independent probe executed too few cases ({tests - skipped}); "
            "it may not have run correctly"
        )

    def test_independent_probe_actually_distinguishes_stub(self):
        """L2 (meta): structural guard so the independent probe can never be
        silently weakened. Confirms the on-disk probe keeps the assertions that
        reject a sort/keep-last/return-input/mutate-input stub."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        src = _read(INDEP_TEST)
        assert "keepsFirstNotLastOccurrence" in src, "probe lost keep-first case"
        assert "doesNotSortElements" in src, "probe lost no-sort case"
        assert "assertNotSame(input, result" in src, (
            "probe lost new-instance assertion"
        )
        assert "input list must not be mutated" in src, (
            "probe lost input-immutability assertion"
        )
        assert "PreconditionViolationException" in src, (
            "probe lost null precondition assertion"
        )

    def test_keep_first_and_no_sort_via_independent_probe(self):
        """L2: explicitly verifies the keep-first and no-sort discriminators ran
        and passed in the independent probe (these reject the two most common
        naive stubs)."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent keep-first/no-sort verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "keep-first / no-sort contract failed in independent probe.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        for expected_case in ("keepsFirstNotLastOccurrence", "doesNotSortElements"):
            assert expected_case in joined, (
                f"expected discriminator case '{expected_case}' to have executed"
            )

    def test_immutability_and_new_instance_via_independent_probe(self):
        """L2: the input is not mutated and a NEW list instance is returned.
        Verified by the independent probe's immutability/new-instance cases."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent immutability verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "immutability / new-instance contract failed in independent probe.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        for expected_case in (
            "resultIsADistinctInstanceFromInput",
            "inputWithDuplicatesIsNotMutated",
        ):
            assert expected_case in joined, (
                f"expected immutability case '{expected_case}' to have executed"
            )

    def test_precondition_failure_via_independent_probe(self):
        """L2: a null list raises PreconditionViolationException whose message
        mentions null. The independent probe's null case must have run and
        passed; a stub that skips the precondition check fails here."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent precondition verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "precondition contract failed in independent probe -> `distinct` "
            "skipped or mis-implemented the null-list check.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        assert "nullListThrowsPreconditionViolation" in joined, (
            "expected the null precondition case to have executed"
        )
