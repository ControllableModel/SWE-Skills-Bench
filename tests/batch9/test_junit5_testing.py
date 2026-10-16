"""Verification suite for the `junit5-testing` skill task (variant ext9).

Task: add `StringUtils.toTitleCase(String)` to the `junit-platform-commons`
module plus a data-driven, grouped-assertion JUnit 5 test suite
(`StringTitleCaseTests`) under `platform-tests`.

`toTitleCase(value)` upper-cases the first letter of every whitespace-separated
word and lower-cases the remaining letters of each word, preserving the original
whitespace (positions, characters and counts) exactly. A `null` value must raise
`org.junit.platform.commons.PreconditionViolationException`.

What this file verifies:
  * L1 - the deliverable source files exist and are minimally well-formed
    (correct package, exact `toTitleCase` signature present, the new test class
    uses data-driven + grouped-assertion + @DisplayName JUnit 5 constructs).
  * L2 - DYNAMIC EXECUTION via the repo's native Gradle toolchain:
      - the agent's own `StringTitleCaseTests` class compiles and passes,
        producing at least 10 executed test results (parsed from JUnit XML).
      - an INDEPENDENT JUnit 5 test class (written by THIS file into the repo)
        exercises `StringUtils.toTitleCase` directly and pins the exact contract
        from the requirement doc. A naive stub (only capitalizes the very first
        character, collapses or alters whitespace, fails to lower-case the rest
        of each word, or skips the null precondition) fails this independent
        class regardless of what the agent wrote in its own test file.

The independent class is the discriminative core: it does not trust any test
file the agent authored.

Native acceptance command this drives:
  ./gradlew :platform-tests:test --tests
      "org.junit.platform.commons.util.StringTitleCaseTests"
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
AGENT_TEST = os.path.join(TEST_DIR, "StringTitleCaseTests.java")

# Name chosen to be unlikely to collide with anything the agent created.
INDEP_CLASS = "TitleCaseContractProbeTests"
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
# Compiled & run by gradle against the agent's production code, so a naive
# `toTitleCase` cannot pass it.
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
    @MethodSource("titleCaseRows")
    void titleCasesEachWordAndPreservesWhitespace(String input, String expected) {
        String actual = StringUtils.toTitleCase(input);
        assertAll(
            () -> assertEquals(expected, actual, "value=[" + input + "]"),
            () -> assertEquals(input.length(), actual.length(),
                    "length must be preserved (whitespace not collapsed): [" + input + "]"),
            () -> assertEquals(whitespaceMask(input), whitespaceMask(actual),
                    "whitespace positions must be preserved exactly: [" + input + "]")
        );
    }

    static Stream<Arguments> titleCaseRows() {
        return Stream.of(
            // basic two-word
            Arguments.of("hello world", "Hello World"),
            // all-uppercase normalization: rest of each word must be lowered
            Arguments.of("HELLO WORLD", "Hello World"),
            // mixed case
            Arguments.of("java IS fun", "Java Is Fun"),
            // leading/trailing + multiple-internal whitespace preserved as-is
            Arguments.of("  spaced   out ", "  Spaced   Out "),
            // single character
            Arguments.of("a", "A"),
            // empty
            Arguments.of("", ""),
            // tabs and newlines are whitespace too; counts/positions preserved
            Arguments.of("foo\tBAR\nbaz", "Foo\tBar\nBaz"),
            // whitespace-only string returned unchanged
            Arguments.of("   ", "   "),
            // already correctly title-cased input is idempotent
            Arguments.of("Hello World", "Hello World"),
            // word with internal upper letters lowered after first
            Arguments.of("mIxEd CaSe", "Mixed Case")
        );
    }

    // Build a mask that records exactly which positions are whitespace, so two
    // strings with identical whitespace layout map to the same mask.
    static String whitespaceMask(String s) {
        StringBuilder sb = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            sb.append(Character.isWhitespace(c) ? c : 'x');
        }
        return sb.toString();
    }

    @Test
    void firstLetterUpperRestLowerWithinEachWord() {
        // distinguishes a stub that only upper-cases the first char of the
        // whole string (would leave "world" untouched -> "WORLD" lowered fails)
        assertEquals("Hello World", StringUtils.toTitleCase("hELLO wORLD"));
    }

    @Test
    void multipleInternalSpacesNotCollapsed() {
        String in = "a   b";              // 3 spaces between words
        String out = StringUtils.toTitleCase(in);
        assertAll(
            () -> assertEquals("A   B", out),
            () -> assertEquals(in.length(), out.length(),
                    "internal spaces must not be collapsed")
        );
    }

    @Test
    void leadingAndTrailingWhitespacePreserved() {
        String out = StringUtils.toTitleCase("  word ");
        assertAll(
            () -> assertTrue(out.startsWith("  "), "leading whitespace preserved"),
            () -> assertTrue(out.endsWith(" "), "trailing whitespace preserved"),
            () -> assertEquals("  Word ", out)
        );
    }

    @Test
    void emptyStringReturnsEmpty() {
        assertEquals("", StringUtils.toTitleCase(""));
    }

    @Test
    void nullValueThrowsPreconditionViolation() {
        PreconditionViolationException ex = assertThrows(
            PreconditionViolationException.class,
            () -> StringUtils.toTitleCase(null));
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

    def test_to_title_case_signature_present(self):
        """L1: StringUtils declares the exact public toTitleCase signature
        `public static String toTitleCase(String value)`."""
        content = _read(MAIN_SRC)
        pattern = re.compile(
            r"public\s+static\s+String\s+toTitleCase\s*\(\s*"
            r"(?:final\s+)?(?:@\w+\s+)?String\s+\w+\s*\)"
        )
        assert pattern.search(content), (
            "expected `public static String toTitleCase(String)` "
            "signature in StringUtils.java"
        )

    def test_agent_test_file_exists_in_correct_package(self):
        """L1: StringTitleCaseTests is placed in the required package/dir."""
        assert os.path.isfile(AGENT_TEST), (
            f"expected new test class at {AGENT_TEST}"
        )
        content = _read(AGENT_TEST)
        assert re.search(
            r"package\s+org\.junit\.platform\.commons\.util\s*;", content
        ), "test class must declare package org.junit.platform.commons.util"
        assert "class StringTitleCaseTests" in content, (
            "file must declare class StringTitleCaseTests"
        )

    def test_agent_test_uses_data_driven_and_grouping_constructs(self):
        """L1: agent suite uses a parameterized (data-driven) method fed by a
        rows source and a grouped-assertion (assertAll) method, per the doc."""
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
        """L1: agent suite checks the null precondition (asserts the
        PreconditionViolationException type) and carries @DisplayName on the
        class and at least one method."""
        content = _read(AGENT_TEST)
        assert "PreconditionViolationException" in content, (
            "agent suite must assert the null-precondition exception type"
        )
        assert re.search(r"assertThrows\s*\(", content), (
            "agent suite must use assertThrows for the precondition case"
        )
        count = len(re.findall(r"@DisplayName\s*\(", content))
        assert count >= 2, (
            "expected @DisplayName on the class and at least one method "
            f"(found {count} occurrences)"
        )

    # ----------------------------- L2 -----------------------------------

    def test_agent_suite_passes_with_enough_executions(self):
        """L2: the agent's StringTitleCaseTests compiles, passes, and reports
        at least 10 executed test results (data rows counted separately)."""
        proc, report = _run_gradle_tests(
            "org.junit.platform.commons.util.StringTitleCaseTests"
        )
        assert report, (
            "no JUnit XML report produced for StringTitleCaseTests.\n"
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
            f"expected >= 10 executed tests in StringTitleCaseTests, "
            f"got {executed} (tests={tests}, skipped={skipped})"
        )

    def test_independent_title_case_contract(self):
        """L2: independent suite pins exact title-cased output, preserved
        length and preserved whitespace mask across many rows. A stub that
        only capitalizes the first word, collapses whitespace, or fails to
        lower-case the rest of each word fails here."""
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
            "independent toTitleCase contract probe FAILED -> production "
            "`toTitleCase` does not satisfy the casing/whitespace contract.\n"
            f"failures={failures} errors={errors} tests={tests}\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-4000:]}"
        )
        assert tests - skipped >= 14, (
            f"independent probe executed too few cases ({tests - skipped}); "
            "it may not have run correctly"
        )

    def test_independent_probe_actually_distinguishes_stub(self):
        """L2 (meta): structural guard so the independent probe can never be
        silently weakened. The generated artifact on disk must still contain
        the length-preservation, whitespace-mask, per-word casing and
        precondition assertions that reject a naive stub."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        src = _read(INDEP_TEST)
        assert "whitespaceMask(input)" in src, "probe lost whitespace-mask assertion"
        assert "input.length(), actual.length()" in src, (
            "probe lost length-preservation assertion"
        )
        assert 'toTitleCase("hELLO wORLD")' in src, (
            "probe lost per-word casing assertion"
        )
        assert "PreconditionViolationException" in src, (
            "probe lost precondition assertion"
        )

    def test_whitespace_preservation_via_independent_probe(self):
        """L2: whitespace (leading, trailing, multiple internal) is preserved
        exactly. Verified by the independent probe's dedicated whitespace
        cases having executed without failure."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent whitespace verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "whitespace-preservation contract failed in independent probe.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        for expected_case in (
            "multipleInternalSpacesNotCollapsed",
            "leadingAndTrailingWhitespacePreserved",
        ):
            assert expected_case in joined, (
                f"expected whitespace case '{expected_case}' to have executed"
            )

    def test_per_word_casing_via_independent_probe(self):
        """L2: every word is normalized (first upper, rest lower) -- not just
        the first word. Verified by the probe's firstLetterUpperRestLowerWithinEachWord
        and empty-string cases having executed without failure."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent per-word casing verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "per-word casing contract failed in independent probe.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        for expected_case in (
            "firstLetterUpperRestLowerWithinEachWord",
            "emptyStringReturnsEmpty",
        ):
            assert expected_case in joined, (
                f"expected casing case '{expected_case}' to have executed"
            )

    def test_precondition_failure_via_independent_probe(self):
        """L2: a null value raises PreconditionViolationException with a message
        mentioning null. Verified by the independent probe's
        nullValueThrowsPreconditionViolation case having executed cleanly."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent precondition verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "precondition contract failed in independent probe -> `toTitleCase` "
            "skipped or mis-implemented the null check.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        assert "nullValueThrowsPreconditionViolation" in joined, (
            "expected the null-precondition case to have executed"
        )
