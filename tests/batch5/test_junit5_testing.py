"""Verification suite for the `junit5-testing` skill task (variant ext5).

Task: add `CollectionUtils.frequencies(Collection<T>)` to the
`junit-platform-commons` module plus a data-driven, grouped-assertion JUnit 5
test suite (`CollectionFrequencyTests`) under `platform-tests`.

The new method must return a Map<T, Integer> mapping each distinct element of
the input collection to its occurrence count, with these contractual edges:
  * sum of all counts == collection.size()
  * every distinct element is exactly one key; counts are always >= 1
  * empty input -> empty map
  * null input -> org.junit.platform.commons.PreconditionViolationException
    (message mentions null), using the module's Preconditions mechanism
  * input collection is NOT mutated

What this file verifies:
  * L1 - deliverables exist and are minimally well-formed: the production
    source has the exact public static `frequencies(Collection)` signature
    in the right package; the new test class is in the required package/dir
    and uses data-driven (@ParameterizedTest + a rows source) plus
    grouped-assertion (assertAll) constructs and @DisplayName descriptions.
  * L2 - DYNAMIC EXECUTION via the repo's native Gradle toolchain:
      - the agent's own `CollectionFrequencyTests` compiles, passes, and
        reports at least 10 executed test results (data rows counted), parsed
        from the JUnit XML report.
      - an INDEPENDENT JUnit 5 test class (written by THIS file into the repo)
        exercises `CollectionUtils.frequencies` directly and pins down the
        exact contract.  A naive stub (always reports count 1, drops repeated
        elements, mutates input, or skips the precondition check) fails this
        independent class regardless of what the agent wrote in its own test.

The independent class is the discriminative core: it does not trust any test
file the agent authored.

Native acceptance command this drives:
  ./gradlew :platform-tests:test --tests \
      "org.junit.platform.commons.util.CollectionFrequencyTests"
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
AGENT_TEST = os.path.join(TEST_DIR, "CollectionFrequencyTests.java")

# Name chosen to be unlikely to collide with anything the agent created.
INDEP_CLASS = "FrequenciesContractProbeTests"
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
# This is OUR contract probe; it is compiled & run by gradle against the
# agent's production code, so a naive `frequencies` cannot pass it.
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
import java.util.Collection;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

class __INDEP_CLASS__ {

    // --- repeated-element case: {a=3, b=1, c=1} -----------------------------
    @Test
    void repeatedElementsCountedExactly() {
        List<String> input = Arrays.asList("a", "b", "a", "c", "a");
        Map<String, Integer> freq = CollectionUtils.frequencies(input);
        assertAll(
            () -> assertEquals(3, freq.size(), "three distinct keys"),
            () -> assertEquals(Integer.valueOf(3), freq.get("a"), "a occurs 3x"),
            () -> assertEquals(Integer.valueOf(1), freq.get("b"), "b occurs 1x"),
            () -> assertEquals(Integer.valueOf(1), freq.get("c"), "c occurs 1x"),
            () -> assertEquals(input.size(),
                    freq.values().stream().mapToInt(Integer::intValue).sum(),
                    "sum of counts equals input size")
        );
    }

    // --- all-identical case: {x=4} -----------------------------------------
    @Test
    void allIdenticalCollapsesToSingleKeyWithFullCount() {
        List<String> input = Arrays.asList("x", "x", "x", "x");
        Map<String, Integer> freq = CollectionUtils.frequencies(input);
        assertAll(
            () -> assertEquals(1, freq.size(), "one distinct key"),
            () -> assertEquals(Integer.valueOf(4), freq.get("x"), "x occurs 4x")
        );
    }

    // --- single-element case -----------------------------------------------
    @Test
    void singleElementHasCountOne() {
        Map<String, Integer> freq = CollectionUtils.frequencies(Arrays.asList("only"));
        assertAll(
            () -> assertEquals(1, freq.size()),
            () -> assertEquals(Integer.valueOf(1), freq.get("only"))
        );
    }

    // --- all-distinct case: every count == 1, sum == size ------------------
    @Test
    void allDistinctEachCountedOnce() {
        List<Integer> input = Arrays.asList(1, 2, 3, 4, 5);
        Map<Integer, Integer> freq = CollectionUtils.frequencies(input);
        assertAll(
            () -> assertEquals(5, freq.size(), "five distinct keys"),
            () -> assertTrue(freq.values().stream().allMatch(c -> c == 1),
                    "every count must be exactly 1"),
            () -> assertEquals(5,
                    freq.values().stream().mapToInt(Integer::intValue).sum(),
                    "sum of counts equals input size")
        );
    }

    // --- empty case: empty map ---------------------------------------------
    @Test
    void emptyCollectionYieldsEmptyMap() {
        Map<Object, Integer> freq = CollectionUtils.frequencies(Collections.emptyList());
        assertAll(
            () -> assertTrue(freq.isEmpty(), "empty input -> empty map"),
            () -> assertEquals(0, freq.size())
        );
    }

    // --- data-driven invariants over a battery of inputs -------------------
    @ParameterizedTest
    @MethodSource("invariantRows")
    void invariantsHoldForEachInput(Collection<Object> input,
                                    int expectedDistinct, int expectedSum) {
        Map<Object, Integer> freq = CollectionUtils.frequencies(input);
        assertAll(
            () -> assertEquals(expectedDistinct, freq.size(),
                    "distinct-key count for " + input),
            () -> assertEquals(expectedSum,
                    freq.values().stream().mapToInt(Integer::intValue).sum(),
                    "sum of counts must equal input size for " + input),
            () -> assertEquals(input.size(), expectedSum,
                    "row self-consistency"),
            () -> assertTrue(freq.values().stream().allMatch(c -> c != null && c >= 1),
                    "no key may have a count < 1"),
            () -> assertTrue(freq.values().stream().noneMatch(c -> c == 0),
                    "no key may have a count of 0")
        );
    }

    static Stream<Arguments> invariantRows() {
        return Stream.of(
            // input, expectedDistinct, expectedSum(==size)
            Arguments.of(Arrays.asList("a", "b", "a", "c", "a"), 3, 5),
            Arguments.of(Arrays.asList("x"), 1, 1),
            Arguments.of(Arrays.asList(1, 1, 1), 1, 3),
            Arguments.of(Arrays.asList(1, 2, 3), 3, 3),
            Arguments.of(Arrays.asList("p", "p", "q", "q", "q", "r"), 3, 6),
            Arguments.of(Collections.emptyList(), 0, 0)
        );
    }

    // --- input must not be mutated -----------------------------------------
    @Test
    void inputCollectionIsNotMutated() {
        List<String> input = new ArrayList<>(Arrays.asList("a", "a", "b"));
        List<String> snapshot = new ArrayList<>(input);
        CollectionUtils.frequencies(input);
        assertEquals(snapshot, input, "input collection must not be mutated");
    }

    // --- null precondition --------------------------------------------------
    @Test
    void nullCollectionThrowsPreconditionViolation() {
        PreconditionViolationException ex = assertThrows(
            PreconditionViolationException.class,
            () -> CollectionUtils.frequencies(null));
        assertTrue(ex.getMessage() != null
                   && ex.getMessage().toLowerCase().contains("null"),
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

    def test_frequencies_signature_present(self):
        """L1: CollectionUtils declares the exact public static frequencies
        signature returning a Map and accepting a Collection."""
        content = _read(MAIN_SRC)
        # public static <T> Map<T, Integer> frequencies(Collection<T> ...)
        # Tolerant of whitespace, optional fully-qualified type names, and the
        # `final`/annotation modifiers on the parameter.
        pattern = re.compile(
            r"public\s+static\s+<\s*T\s*>\s+"
            r"(?:java\.util\.)?Map\s*<\s*T\s*,\s*Integer\s*>\s+"
            r"frequencies\s*\(\s*"
            r"(?:final\s+)?(?:@\w+\s+)?(?:java\.util\.)?Collection\s*<\s*T\s*>\s+\w+\s*\)"
        )
        assert pattern.search(content), (
            "expected `public static <T> Map<T, Integer> "
            "frequencies(Collection<T>)` signature in CollectionUtils.java"
        )

    def test_agent_test_file_exists_in_correct_package(self):
        """L1: CollectionFrequencyTests is placed in the required package/dir."""
        assert os.path.isfile(AGENT_TEST), (
            f"expected new test class at {AGENT_TEST}"
        )
        content = _read(AGENT_TEST)
        assert re.search(
            r"package\s+org\.junit\.platform\.commons\.util\s*;", content
        ), "test class must declare package org.junit.platform.commons.util"
        assert "class CollectionFrequencyTests" in content, (
            "file must declare class CollectionFrequencyTests"
        )

    def test_agent_test_uses_data_driven_and_grouping_constructs(self):
        """L1: agent suite uses a parameterized (data-driven) method and a
        grouped-assertion (assertAll) method, per the requirement doc."""
        content = _read(AGENT_TEST)
        assert "@ParameterizedTest" in content, (
            "count cases must be expressed as a single data-driven "
            "(@ParameterizedTest) method"
        )
        assert any(
            tok in content
            for tok in ("@MethodSource", "@CsvSource", "@ArgumentsSource", "@FieldSource")
        ), "data-driven method must be fed by a rows source (e.g. @MethodSource/@CsvSource)"
        assert "assertAll" in content, (
            "at least one grouped-assertion method (assertAll) is required"
        )

    def test_agent_test_covers_precondition_case(self):
        """L1: the agent suite must reference the null-precondition contract
        (PreconditionViolationException) and the assertThrows construct."""
        content = _read(AGENT_TEST)
        assert "PreconditionViolationException" in content, (
            "agent suite must verify the null-collection precondition failure"
        )
        assert "assertThrows" in content, (
            "the precondition case must be expressed via assertThrows"
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

    # ----------------------------- L2 -----------------------------------

    def test_agent_suite_passes_with_enough_executions(self):
        """L2: the agent's CollectionFrequencyTests compiles, passes, and
        reports at least 10 executed test results (data rows counted)."""
        proc, report = _run_gradle_tests(
            "org.junit.platform.commons.util.CollectionFrequencyTests"
        )
        assert report, (
            "no JUnit XML report produced for CollectionFrequencyTests.\n"
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
            f"expected >= 10 executed tests in CollectionFrequencyTests, "
            f"got {executed} (tests={tests}, skipped={skipped})"
        )

    def test_independent_count_contract(self):
        """L2: independent suite pins exact counts, distinct-key counts and the
        sum==size invariant. A stub that always reports 1 or drops repeated
        elements fails this regardless of the agent's own tests."""
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
            "independent frequencies contract probe FAILED -> production "
            "`frequencies` does not satisfy the count / distinct-key / "
            "sum-equals-size contract.\n"
            f"failures={failures} errors={errors} tests={tests}\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-4000:]}"
        )
        # sanity: the probe really ran its many cases (5 @Test + 6 param rows +
        # mutation + null == 13 executions).
        assert tests - skipped >= 12, (
            f"independent probe executed too few cases ({tests - skipped}); "
            "it may not have run correctly"
        )

    def test_independent_probe_actually_distinguishes_stub(self):
        """L2 (meta): structural guard so the independent probe can never be
        silently weakened -- it must retain the count, sum-equals-size,
        non-mutation and precondition assertions that reject a naive stub."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        src = _read(INDEP_TEST)
        assert 'assertEquals(Integer.valueOf(3), freq.get("a")' in src, (
            "probe lost the repeated-element exact-count assertion"
        )
        assert "sum of counts must equal input size" in src, (
            "probe lost the sum-equals-size invariant"
        )
        assert "input collection must not be mutated" in src, (
            "probe lost the non-mutation assertion"
        )
        assert "PreconditionViolationException" in src, (
            "probe lost the null-precondition assertion"
        )
        assert "noneMatch(c -> c == 0)" in src, (
            "probe lost the no-zero-count assertion"
        )

    def test_repeated_and_identical_cases_via_independent_probe(self):
        """L2: the repeated-element ({a=3,b=1,c=1}) and all-identical ({x=4})
        cases pass in the independent probe -- a stub that drops duplicates or
        reports 1 for every key cannot satisfy these."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent repeated/identical verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "repeated/identical count contract failed in independent probe.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        for expected_case in (
            "repeatedElementsCountedExactly",
            "allIdenticalCollapsesToSingleKeyWithFullCount",
        ):
            assert expected_case in joined, (
                f"expected case '{expected_case}' to have executed"
            )

    def test_non_mutation_via_independent_probe(self):
        """L2: the input collection is not mutated by frequencies(). Verified by
        the independent probe's inputCollectionIsNotMutated case."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent non-mutation verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "non-mutation contract failed in independent probe -> frequencies "
            "mutated its input collection.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        assert "inputCollectionIsNotMutated" in " ".join(names), (
            "expected the non-mutation case to have executed"
        )

    def test_precondition_failure_via_independent_probe(self):
        """L2: a null collection raises PreconditionViolationException whose
        message mentions null. Verified by the independent probe."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent precondition verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "precondition contract failed in independent probe -> frequencies "
            "skipped or mis-implemented the null check.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        assert "nullCollectionThrowsPreconditionViolation" in " ".join(names), (
            "expected the null-precondition case to have executed"
        )
