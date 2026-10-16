"""Verification suite for the `junit5-testing` skill task (variant ext6).

Task: add a non-overlapping substring counter
`StringUtils.countOccurrences(String value, String token)` to the
`junit-platform-commons` module, plus a data-driven, grouped-assertion JUnit 5
test suite (`StringCountOccurrencesTests`) under `platform-tests`.

What this file verifies:
  * L1 - the deliverable source files exist and are minimally well-formed:
      - `StringUtils.java` declares the exact
        `public static int countOccurrences(String, String)` signature.
      - the new `StringCountOccurrencesTests` class sits in the required
        package and uses the mandated JUnit 5 constructs (a data-driven
        method, a grouped-assertion method, human-readable @DisplayNames).
  * L2 - DYNAMIC EXECUTION via the repo's native Gradle toolchain:
      - the agent's own `StringCountOccurrencesTests` compiles and passes,
        producing at least 10 executed results (parsed from the JUnit XML).
      - an INDEPENDENT JUnit 5 test class (written by THIS file into the repo)
        exercises `StringUtils.countOccurrences` directly and pins the exact
        contract from the requirement doc. A naive stub that counts OVERLAPPING
        matches, ignores case-sensitivity, mis-handles no-match, or skips the
        null/empty-token precondition checks fails this independent class
        regardless of whatever the agent put in its own test file.

The independent probe is the discriminative core: it does not trust any test
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
    "junit-platform-commons/src/main/java/org/junit/platform/commons/util/StringUtils.java",
)
TEST_DIR = os.path.join(
    REPO_DIR,
    "platform-tests/src/test/java/org/junit/platform/commons/util",
)
AGENT_TEST = os.path.join(TEST_DIR, "StringCountOccurrencesTests.java")

# Name chosen to be unlikely to collide with anything the agent created.
INDEP_CLASS = "CountOccurrencesContractProbeTests"
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
    discovered TEST-*.xml file (for the requested class) to
    (tests, failures, errors, skipped, [testcase-names]).
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
# `countOccurrences` cannot pass it.
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

import java.util.stream.Stream;

class __INDEP_CLASS__ {

    @ParameterizedTest
    @MethodSource("countRows")
    void countsNonOverlappingOccurrences(String value, String token, int expected) {
        int actual = StringUtils.countOccurrences(value, token);
        assertEquals(expected, actual,
            "countOccurrences(\"" + value + "\", \"" + token + "\")");
    }

    static Stream<Arguments> countRows() {
        return Stream.of(
            // single-character tokens
            Arguments.of("banana", "a", 3),
            Arguments.of("banana", "n", 2),
            Arguments.of("hello", "l", 2),
            // multi-character, NON-OVERLAPPING (an overlapping stub fails here)
            Arguments.of("aaaa", "aa", 2),
            Arguments.of("aaaaa", "aa", 2),
            Arguments.of("abcabcabc", "abc", 3),
            Arguments.of("aabaab", "aa", 2),
            // no-match cases
            Arguments.of("hello", "z", 0),
            Arguments.of("abc", "xyz", 0),
            // case-sensitivity (a case-insensitive stub fails here)
            Arguments.of("AaAa", "a", 2),
            Arguments.of("AaAa", "A", 2),
            Arguments.of("Mississippi", "ss", 2),
            // token equal to / longer than value
            Arguments.of("ab", "ab", 1),
            Arguments.of("a", "ab", 0)
        );
    }

    @Test
    void nonOverlappingIsTheDistinguishingRule() {
        // The canonical discriminator: overlapping count would be 3.
        assertEquals(2, StringUtils.countOccurrences("aaaa", "aa"));
        // Overlapping count of "aba" in "ababa" would be 2; non-overlapping is 1.
        assertEquals(1, StringUtils.countOccurrences("ababa", "aba"));
    }

    @Test
    void groupedExpectationsAllEvaluated() {
        assertAll(
            () -> assertEquals(3, StringUtils.countOccurrences("banana", "a")),
            () -> assertEquals(2, StringUtils.countOccurrences("aaaa", "aa")),
            () -> assertEquals(0, StringUtils.countOccurrences("hello", "z")),
            () -> assertEquals(3, StringUtils.countOccurrences("abcabcabc", "abc")),
            () -> assertEquals(2, StringUtils.countOccurrences("AaAa", "a"))
        );
    }

    @Test
    void caseSensitiveCountingDoesNotConflateCase() {
        // "A" appears twice, "a" appears twice; a case-insensitive stub would
        // report 4 for either token.
        assertAll(
            () -> assertEquals(2, StringUtils.countOccurrences("AaAa", "a")),
            () -> assertEquals(2, StringUtils.countOccurrences("AaAa", "A")),
            () -> assertEquals(0, StringUtils.countOccurrences("ABC", "abc"))
        );
    }

    @Test
    void nullValueThrowsPreconditionViolation() {
        PreconditionViolationException ex = assertThrows(
            PreconditionViolationException.class,
            () -> StringUtils.countOccurrences(null, "a"));
        assertTrue(ex.getMessage() != null
                && ex.getMessage().toLowerCase().contains("null"),
            "message must mention null, was: " + ex.getMessage());
    }

    @Test
    void nullTokenThrowsPreconditionViolation() {
        PreconditionViolationException ex = assertThrows(
            PreconditionViolationException.class,
            () -> StringUtils.countOccurrences("abc", null));
        assertTrue(ex.getMessage() != null
                && ex.getMessage().toLowerCase().contains("null"),
            "message must mention null, was: " + ex.getMessage());
    }

    @Test
    void emptyTokenThrowsPreconditionViolation() {
        PreconditionViolationException ex = assertThrows(
            PreconditionViolationException.class,
            () -> StringUtils.countOccurrences("abc", ""));
        assertTrue(ex.getMessage() != null
                && ex.getMessage().toLowerCase().contains("empty"),
            "message must convey the token must not be empty, was: "
                + ex.getMessage());
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
        """L1: the repo, gradle wrapper and StringUtils source all exist."""
        assert os.path.isdir(REPO_DIR), f"repo missing at {REPO_DIR}"
        assert os.path.isfile(_gradlew()), "gradlew wrapper missing"
        assert os.path.isfile(MAIN_SRC), f"StringUtils.java missing at {MAIN_SRC}"

    def test_count_occurrences_signature_present(self):
        """L1: StringUtils declares the exact public countOccurrences signature
        `public static int countOccurrences(String, String)`."""
        content = _read(MAIN_SRC)
        pattern = re.compile(
            r"public\s+static\s+int\s+countOccurrences\s*\(\s*"
            r"(?:final\s+)?(?:@\w+\s+)?String\s+\w+\s*,\s*"
            r"(?:final\s+)?(?:@\w+\s+)?String\s+\w+\s*\)"
        )
        assert pattern.search(content), (
            "expected `public static int countOccurrences(String, String)` "
            "signature in StringUtils.java"
        )

    def test_agent_test_file_exists_in_correct_package(self):
        """L1: StringCountOccurrencesTests is placed in the required dir and
        declares the required package and class name."""
        assert os.path.isfile(AGENT_TEST), (
            f"expected new test class at {AGENT_TEST}"
        )
        content = _read(AGENT_TEST)
        assert re.search(
            r"package\s+org\.junit\.platform\.commons\.util\s*;", content
        ), "test class must declare package org.junit.platform.commons.util"
        assert "class StringCountOccurrencesTests" in content, (
            "file must declare class StringCountOccurrencesTests"
        )

    def test_agent_test_uses_data_driven_and_grouping_constructs(self):
        """L1: agent suite expresses the count cases as a single data-driven
        method and uses a grouped-assertion (assertAll) method, per the doc."""
        content = _read(AGENT_TEST)
        assert "@ParameterizedTest" in content, (
            "count cases must be a single data-driven (@ParameterizedTest) "
            "method fed by multiple rows"
        )
        assert any(
            tok in content
            for tok in ("@MethodSource", "@CsvSource", "@ArgumentsSource", "@FieldSource")
        ), "data-driven method must be fed by a rows source (e.g. @MethodSource/@CsvSource)"
        assert "assertAll" in content, (
            "at least one grouped-assertion method (assertAll) is required"
        )

    def test_agent_suite_carries_human_readable_descriptions(self):
        """L1: requirement doc mandates human-readable descriptions for the
        test class and its methods (@DisplayName)."""
        content = _read(AGENT_TEST)
        count = len(re.findall(r"@DisplayName\s*\(", content))
        assert count >= 2, (
            "expected @DisplayName on the class and at least one method "
            f"(found {count} occurrences)"
        )

    def test_agent_suite_references_precondition_exception(self):
        """L1: the agent suite must verify the precondition failures, so it must
        reference PreconditionViolationException for the null/empty cases."""
        content = _read(AGENT_TEST)
        assert "PreconditionViolationException" in content, (
            "agent suite must assert PreconditionViolationException for the "
            "null-value, null-token and empty-token cases"
        )
        # The three forbidden-input cases must all be exercised somewhere.
        assert "assertThrows" in content, (
            "agent suite must use assertThrows for the precondition cases"
        )

    # ----------------------------- L2 -----------------------------------

    def test_agent_suite_passes_with_enough_executions(self):
        """L2: the agent's StringCountOccurrencesTests compiles, passes, and
        reports at least 10 executed test results (data rows counted)."""
        proc, report = _run_gradle_tests(
            "org.junit.platform.commons.util.StringCountOccurrencesTests"
        )
        assert report, (
            "no JUnit XML report produced for StringCountOccurrencesTests.\n"
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
            f"expected >= 10 executed tests in StringCountOccurrencesTests, "
            f"got {executed} (tests={tests}, skipped={skipped})"
        )

    def test_independent_count_contract(self):
        """L2: independent suite pins exact non-overlapping, case-sensitive
        counts. A stub that counts overlapping matches or ignores case fails."""
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
            "independent countOccurrences contract probe FAILED -> production "
            "`countOccurrences` does not satisfy the non-overlapping / "
            "case-sensitive / no-match / precondition contract.\n"
            f"failures={failures} errors={errors} tests={tests}\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-4000:]}"
        )
        # sanity: the probe really ran its many cases (14 rows + 6 @Test)
        assert tests - skipped >= 18, (
            f"independent probe executed too few cases ({tests - skipped}); "
            "it may not have run correctly"
        )

    def test_independent_probe_is_discriminative_structurally(self):
        """L2 (meta): structural guard so the probe can never be silently
        weakened. The generated artifact must keep the non-overlapping,
        case-sensitivity and precondition assertions that reject a stub."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        src = _read(INDEP_TEST)
        # the canonical non-overlapping discriminator
        assert 'countOccurrences("aaaa", "aa")' in src, (
            "probe lost the non-overlapping discriminator (aaaa/aa -> 2)"
        )
        assert "nonOverlappingIsTheDistinguishingRule" in src, (
            "probe lost the dedicated non-overlapping assertion method"
        )
        assert "caseSensitiveCountingDoesNotConflateCase" in src, (
            "probe lost the case-sensitivity assertion method"
        )
        for case in (
            "nullValueThrowsPreconditionViolation",
            "nullTokenThrowsPreconditionViolation",
            "emptyTokenThrowsPreconditionViolation",
        ):
            assert case in src, f"probe lost precondition case {case}"

    def test_non_overlapping_counting_via_independent_probe(self):
        """L2: the non-overlapping rule is enforced. An overlapping-counting
        stub returns 3 for ("aaaa","aa") / 2 for ("ababa","aba") and fails the
        probe's dedicated method."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent non-overlapping verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "non-overlapping contract failed in independent probe -> "
            "`countOccurrences` double-counts overlapping matches.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        assert "nonOverlappingIsTheDistinguishingRule" in joined, (
            "expected the non-overlapping discriminator method to have executed"
        )
        assert "countsNonOverlappingOccurrences" in joined, (
            "expected the data-driven count method to have executed"
        )

    def test_case_sensitivity_and_no_match_via_independent_probe(self):
        """L2: counting is case-sensitive and a missing token yields 0. A
        case-insensitive stub or one that mishandles no-match fails the probe's
        case-sensitivity method and the relevant data rows."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent case-sensitivity verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "case-sensitivity / no-match contract failed in independent probe.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        assert "caseSensitiveCountingDoesNotConflateCase" in joined, (
            "expected the case-sensitivity method to have executed"
        )

    def test_precondition_failures_via_independent_probe(self):
        """L2: null value, null token, and empty token each raise
        PreconditionViolationException with a meaningful message. A stub that
        skips the precondition checks fails these probe methods."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent precondition verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "precondition contract failed in independent probe -> "
            "`countOccurrences` skipped or mis-implemented the null / "
            "empty-token checks.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        for expected_case in (
            "nullValueThrowsPreconditionViolation",
            "nullTokenThrowsPreconditionViolation",
            "emptyTokenThrowsPreconditionViolation",
        ):
            assert expected_case in joined, (
                f"expected precondition case '{expected_case}' to have executed"
            )
