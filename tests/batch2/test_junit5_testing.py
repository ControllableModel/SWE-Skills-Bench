"""Verification suite for the `junit5-testing` skill task (variant ext2).

Task: add `StringUtils.commonPrefix(String, String)` to the
`junit-platform-commons` module plus a data-driven, grouped-assertion JUnit 5
test suite (`StringCommonPrefixTests`) under `platform-tests`.

`commonPrefix(first, second)` returns the longest leading run of characters
shared by both arguments (case-sensitive, by `char`). It returns `""` when
there is no shared leading character or when either argument is empty, returns
the shorter argument when one is a prefix of the other, and raises
`org.junit.platform.commons.PreconditionViolationException` when either
argument is `null` (message must mention `null`).

What this file verifies:
  * L1 - the deliverable source files exist and are minimally well-formed
    (correct package, exact `commonPrefix` signature present, the new test
    class uses data-driven + grouped-assertion JUnit 5 constructs plus
    human-readable @DisplayName descriptions).
  * L2 - DYNAMIC EXECUTION via the repo's native Gradle toolchain:
      - the agent's own `StringCommonPrefixTests` class compiles and passes,
        producing at least 10 executed test results (parsed from JUnit XML).
      - an INDEPENDENT JUnit 5 test class (written by THIS file into the repo)
        exercises `StringUtils.commonPrefix` directly and pins down the exact
        contract from the requirement doc.  A naive stub (returns an input
        unchanged, ignores case-sensitivity, returns more than the shorter
        argument, or skips the null precondition checks) fails this independent
        class regardless of what the agent wrote in its own test file.

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
    "junit-platform-commons/src/main/java/org/junit/platform/commons/util/StringUtils.java",
)
TEST_DIR = os.path.join(
    REPO_DIR,
    "platform-tests/src/test/java/org/junit/platform/commons/util",
)
AGENT_TEST = os.path.join(TEST_DIR, "StringCommonPrefixTests.java")

# Name chosen to be unlikely to collide with anything the agent created.
INDEP_CLASS = "CommonPrefixContractProbeTests"
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
# agent's production code, so a naive `commonPrefix` cannot pass it.
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
    @MethodSource("prefixRows")
    void computesLongestCommonPrefix(String first, String second, String expected) {
        String actual = StringUtils.commonPrefix(first, second);
        assertAll(
            () -> assertEquals(expected, actual,
                    "commonPrefix(\"" + first + "\",\"" + second + "\")"),
            // result must itself be a prefix of BOTH arguments
            () -> assertTrue(first.startsWith(actual),
                    "result must be a prefix of first"),
            () -> assertTrue(second.startsWith(actual),
                    "result must be a prefix of second"),
            // result may not exceed the shorter argument's length
            () -> assertTrue(actual.length() <= Math.min(first.length(), second.length()),
                    "result must not exceed the shorter argument")
        );
    }

    static Stream<Arguments> prefixRows() {
        return Stream.of(
            // shared, then divergent
            Arguments.of("foobar", "foobaz", "fooba"),
            // identical strings -> whole string
            Arguments.of("abc", "abc", "abc"),
            // one is a prefix of the other -> the shorter, in full
            Arguments.of("abc", "abcdef", "abc"),
            Arguments.of("abcdef", "abc", "abc"),
            // no overlap at all
            Arguments.of("xyz", "abc", ""),
            // first character already differs
            Arguments.of("zebra", "ant", ""),
            // empty input -> empty result
            Arguments.of("", "abc", ""),
            Arguments.of("abc", "", ""),
            // both empty
            Arguments.of("", "", ""),
            // single shared leading char then divergence
            Arguments.of("apple", "apricot", "ap"),
            // divergence at the very first position with a long tail
            Arguments.of("Hello", "Goodbye", "")
        );
    }

    @Test
    void comparisonIsCaseSensitive() {
        // "Abc" vs "abc" share no leading char because 'A' != 'a'.
        assertEquals("", StringUtils.commonPrefix("Abc", "abc"));
        // case differs only after a shared run
        assertEquals("ab", StringUtils.commonPrefix("abC", "abc"));
    }

    @Test
    void differingCharIsExcluded() {
        // the differing character at the divergence point is NOT included
        assertEquals("fooba", StringUtils.commonPrefix("foobar", "foobaz"));
        assertEquals("a", StringUtils.commonPrefix("ax", "ay"));
    }

    @Test
    void resultNeverExceedsShorterArgument() {
        String r = StringUtils.commonPrefix("abc", "abcdefghij");
        assertAll(
            () -> assertEquals("abc", r),
            () -> assertEquals(3, r.length(),
                    "must not return more than the shorter argument"),
            () -> assertTrue(r.length() <= 3)
        );
    }

    @Test
    void nullFirstThrowsPreconditionViolation() {
        PreconditionViolationException ex = assertThrows(
            PreconditionViolationException.class,
            () -> StringUtils.commonPrefix(null, "abc"));
        assertTrue(ex.getMessage() != null && ex.getMessage().toLowerCase().contains("null"),
            "message must mention null, was: " + ex.getMessage());
    }

    @Test
    void nullSecondThrowsPreconditionViolation() {
        PreconditionViolationException ex = assertThrows(
            PreconditionViolationException.class,
            () -> StringUtils.commonPrefix("abc", null));
        assertTrue(ex.getMessage() != null && ex.getMessage().toLowerCase().contains("null"),
            "message must mention null, was: " + ex.getMessage());
    }

    @Test
    void nullCheckedEvenWhenOtherArgumentEmpty() {
        // a stub that short-circuits on an empty arg must still reject null
        assertThrows(PreconditionViolationException.class,
            () -> StringUtils.commonPrefix("", null));
        assertThrows(PreconditionViolationException.class,
            () -> StringUtils.commonPrefix(null, ""));
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

    def test_common_prefix_signature_present(self):
        """L1: StringUtils declares the exact public commonPrefix signature
        `public static String commonPrefix(String, String)`."""
        content = _read(MAIN_SRC)
        # exact signature, tolerant only of whitespace / nullability annotations
        pattern = re.compile(
            r"public\s+static\s+String\s+commonPrefix\s*\(\s*"
            r"(?:final\s+)?(?:@\w+\s+)?String\s+\w+\s*,\s*"
            r"(?:final\s+)?(?:@\w+\s+)?String\s+\w+\s*\)"
        )
        assert pattern.search(content), (
            "expected `public static String commonPrefix(String, String)` "
            "signature in StringUtils.java"
        )

    def test_agent_test_file_exists_in_correct_package(self):
        """L1: StringCommonPrefixTests is placed in the required package/dir."""
        assert os.path.isfile(AGENT_TEST), (
            f"expected new test class at {AGENT_TEST}"
        )
        content = _read(AGENT_TEST)
        assert re.search(
            r"package\s+org\.junit\.platform\.commons\.util\s*;", content
        ), "test class must declare package org.junit.platform.commons.util"
        assert "class StringCommonPrefixTests" in content, (
            "file must declare class StringCommonPrefixTests"
        )

    def test_agent_test_uses_data_driven_and_grouping_constructs(self):
        """L1: agent suite uses a parameterized (data-driven) method and a
        grouped-assertion (assertAll) method, per the requirement doc."""
        content = _read(AGENT_TEST)
        assert "@ParameterizedTest" in content, (
            "value cases must be expressed as a single data-driven "
            "(@ParameterizedTest) method"
        )
        # a value source for the parameterized rows
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
        # at least two @DisplayName annotations: class-level + method-level.
        count = len(re.findall(r"@DisplayName\s*\(", content))
        assert count >= 2, (
            "expected @DisplayName on the class and at least one method "
            f"(found {count} occurrences)"
        )

    def test_agent_suite_verifies_both_precondition_failures(self):
        """L1: agent suite must reference PreconditionViolationException and
        both null arguments (the doc requires verifying both failures)."""
        content = _read(AGENT_TEST)
        assert "PreconditionViolationException" in content, (
            "agent suite must verify the PreconditionViolationException contract"
        )
        assert "null" in content, (
            "agent suite must verify the null-argument precondition cases"
        )

    # ----------------------------- L2 -----------------------------------

    def test_agent_suite_passes_with_enough_executions(self):
        """L2: the agent's StringCommonPrefixTests compiles, passes, and
        reports at least 10 executed test results (data rows counted)."""
        proc, report = _run_gradle_tests(
            "org.junit.platform.commons.util.StringCommonPrefixTests"
        )
        assert report, (
            "no JUnit XML report produced for StringCommonPrefixTests.\n"
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
            f"expected >= 10 executed tests in StringCommonPrefixTests, "
            f"got {executed} (tests={tests}, skipped={skipped})"
        )

    def test_independent_common_prefix_contract(self):
        """L2: independent suite pins the exact longest-common-prefix value for
        shared, prefix-of-other, no-overlap and empty-input rows, and asserts
        the result is a true prefix of both inputs. A stub that returns an input
        unchanged or over-returns fails."""
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
            "independent commonPrefix contract probe FAILED -> production "
            "`commonPrefix` does not satisfy the value/prefix/length contract.\n"
            f"failures={failures} errors={errors} tests={tests}\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-4000:]}"
        )
        # sanity: the probe really ran its many cases (11 rows + extra @Tests)
        assert tests - skipped >= 16, (
            f"independent probe executed too few cases ({tests - skipped}); "
            "it may not have run correctly"
        )

    def test_independent_probe_actually_distinguishes_stub(self):
        """L2 (meta): structural guard ensuring the independent probe keeps its
        discriminative assertions (case-sensitivity, divergence exclusion,
        length bound, both null preconditions) so it can never be silently
        weakened to accept a naive stub."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        src = _read(INDEP_TEST)
        assert 'commonPrefix("Abc", "abc")' in src, (
            "probe lost case-sensitivity assertion"
        )
        assert "Math.min(first.length(), second.length())" in src, (
            "probe lost length-bound assertion"
        )
        assert "first.startsWith(actual)" in src and "second.startsWith(actual)" in src, (
            "probe lost the 'result is a prefix of both inputs' assertion"
        )
        assert "PreconditionViolationException" in src, (
            "probe lost precondition assertions"
        )
        assert src.count("null") >= 3, "probe lost null-argument coverage"

    def test_case_sensitivity_and_divergence_via_independent_probe(self):
        """L2: case-sensitive comparison and exclusion of the first differing
        character are verified by the independent probe's dedicated methods."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for case-sensitivity verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "case-sensitivity / divergence contract failed in independent probe.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        assert "comparisonIsCaseSensitive" in joined, (
            "expected the case-sensitivity case to have executed"
        )
        assert "differingCharIsExcluded" in joined, (
            "expected the divergence-exclusion case to have executed"
        )

    def test_precondition_failures_via_independent_probe(self):
        """L2: null first and null second both raise
        PreconditionViolationException (message mentions null), and the null
        check is performed even when the other argument is empty."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent precondition verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "precondition contract failed in independent probe -> `commonPrefix` "
            "skipped or mis-implemented the null checks.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        for expected_case in (
            "nullFirstThrowsPreconditionViolation",
            "nullSecondThrowsPreconditionViolation",
            "nullCheckedEvenWhenOtherArgumentEmpty",
        ):
            assert expected_case in joined, (
                f"expected precondition case '{expected_case}' to have executed"
            )
