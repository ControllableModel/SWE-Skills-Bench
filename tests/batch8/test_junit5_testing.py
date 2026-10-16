"""Verification suite for the `junit5-testing` skill task (variant ext8).

Variant task: add a LEFT-PADDING helper

    public static String padLeft(String value, int minLength, char padChar)

to `org.junit.platform.commons.util.StringUtils` in the
`junit-platform-commons` module, plus a data-driven, grouped-assertion JUnit 5
test suite `StringPadLeftTests` under the `platform-tests` module (package
`org.junit.platform.commons.util`).

Contract (from the requirement doc):
  * Left-pads `value` with `padChar` until it reaches `minLength` chars.
  * If `value.length() >= minLength`, `value` is returned unchanged.
  * Otherwise the result length is EXACTLY `minLength`, formed by prepending
    `minLength - value.length()` copies of `padChar` to the original `value`,
    with `value` kept intact and on the RIGHT.
  * `value == null` -> `PreconditionViolationException` (message mentions null).
  * `minLength < 0`  -> `PreconditionViolationException` (non-negative message).
  * empty string padded to N -> N copies of padChar.

What this file verifies:
  * L1 - the deliverable source files exist and are minimally well-formed
    (correct package, exact `padLeft` signature, the new test class uses
    data-driven + grouped-assertion + @DisplayName JUnit 5 constructs).
  * L2 - DYNAMIC EXECUTION via the repo's native Gradle toolchain:
      - the agent's own `StringPadLeftTests` class compiles and passes,
        producing at least 10 executed test results (parsed from the JUnit XML
        report).
      - an INDEPENDENT JUnit 5 test class (written by THIS file into the repo)
        exercises `StringUtils.padLeft` directly and pins down the exact
        contract.  A naive stub (pads on the RIGHT, alters/reorders the
        original characters, produces the wrong length, or skips the
        precondition checks) fails this independent class regardless of what
        the agent wrote in its own test file.

The independent class is the discriminative core: it does not trust any test
file the agent authored.

Native acceptance command (per the doc):
    ./gradlew :platform-tests:test \
        --tests "org.junit.platform.commons.util.StringPadLeftTests"
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
AGENT_TEST = os.path.join(TEST_DIR, "StringPadLeftTests.java")

# Name chosen to be unlikely to collide with anything the agent created.
INDEP_CLASS = "PadLeftContractProbeTests"
INDEP_TEST = os.path.join(TEST_DIR, INDEP_CLASS + ".java")

GRADLE_TIMEOUT = 1800

# Java toolchain auto-provisioning is driven by gradle.properties
# (org.gradle.java.installations.fromEnv); keep the daemon off for determinism.
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
# Compiled & run by gradle against the agent's PRODUCTION StringUtils.padLeft,
# so a naive implementation cannot pass it.
# ---------------------------------------------------------------------------

_INDEP_SOURCE = r"""/* Auto-generated by the benchmark verifier. Do not edit. */
package org.junit.platform.commons.util;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.platform.commons.PreconditionViolationException;

class __INDEP_CLASS__ {

    @ParameterizedTest
    @MethodSource("padRows")
    void padsOnLeftToExactLength(String value, int minLength, char padChar, String expected) {
        String actual = StringUtils.padLeft(value, minLength, padChar);
        // Build the expected pad prefix independently for cross-checks.
        int padCount = Math.max(0, minLength - value.length());
        StringBuilder prefix = new StringBuilder();
        for (int i = 0; i < padCount; i++) {
            prefix.append(padChar);
        }
        assertAll(
            () -> assertEquals(expected, actual,
                    "value=" + value + " minLength=" + minLength + " padChar=" + padChar),
            () -> assertEquals(Math.max(value.length(), minLength), actual.length(),
                    "result length must be max(value.length(), minLength)"),
            // original characters preserved, intact, on the RIGHT.
            () -> assertTrue(actual.endsWith(value),
                    "original value must be preserved as the suffix (padding is on the left)"),
            () -> assertEquals(value, actual.substring(actual.length() - value.length()),
                    "the trailing value.length() chars must equal the original value unchanged"),
            // everything before the suffix is exactly the pad characters.
            () -> assertEquals(prefix.toString(),
                    actual.substring(0, actual.length() - value.length()),
                    "the left side must consist solely of padChar copies")
        );
    }

    static Stream<Arguments> padRows() {
        return Stream.of(
            Arguments.of("42", 5, '0', "00042"),
            Arguments.of("7", 4, ' ', "   7"),
            Arguments.of("", 3, '*', "***"),
            Arguments.of("ab", 6, 'x', "xxxxab"),
            Arguments.of("9", 1, '0', "9"),          // already at minLength
            Arguments.of("hello", 3, '0', "hello"),  // longer than minLength
            Arguments.of("42", 2, '0', "42")         // already long enough
        );
    }

    @ParameterizedTest
    @MethodSource("unchangedRows")
    void returnsUnchangedWhenAlreadyLongEnough(String value, int minLength, char padChar) {
        String actual = StringUtils.padLeft(value, minLength, padChar);
        assertAll(
            () -> assertEquals(value, actual, "value at/over minLength must be unchanged"),
            () -> assertEquals(value.length(), actual.length(),
                    "length must be unchanged when already long enough")
        );
    }

    static Stream<Arguments> unchangedRows() {
        return Stream.of(
            Arguments.of("hello", 5, '0'),  // exactly equal to minLength
            Arguments.of("hello", 3, '0'),  // longer than minLength
            Arguments.of("abcdef", 2, '#'),
            Arguments.of("x", 0, ' ')       // minLength 0 -> unchanged
        );
    }

    @Test
    void emptyStringBecomesAllPadChars() {
        assertEquals("***", StringUtils.padLeft("", 3, '*'));
        assertEquals("", StringUtils.padLeft("", 0, '*'));
    }

    @Test
    void zeroAndExactBoundaries() {
        // minLength == value.length() -> unchanged
        assertEquals("42", StringUtils.padLeft("42", 2, '0'));
        // single pad char added on the left
        assertEquals("042", StringUtils.padLeft("42", 3, '0'));
    }

    @Test
    void padCharIsHonoured() {
        // A stub that hardcodes '0' or ' ' must fail this.
        assertEquals("###7", StringUtils.padLeft("7", 4, '#'));
        assertEquals("____a", StringUtils.padLeft("a", 5, '_'));
    }

    @Test
    void nullValueThrowsPreconditionViolation() {
        PreconditionViolationException ex = assertThrows(
            PreconditionViolationException.class,
            () -> StringUtils.padLeft(null, 5, '0'));
        assertTrue(ex.getMessage() != null && ex.getMessage().toLowerCase().contains("null"),
            "message must mention null, was: " + ex.getMessage());
    }

    @Test
    void negativeMinLengthThrowsPreconditionViolation() {
        assertThrows(PreconditionViolationException.class,
            () -> StringUtils.padLeft("42", -1, '0'));
        assertThrows(PreconditionViolationException.class,
            () -> StringUtils.padLeft("", -5, '*'));
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

    def test_padleft_signature_present(self):
        """L1: StringUtils declares the EXACT public padLeft signature
        `public static String padLeft(String, int, char)`."""
        content = _read(MAIN_SRC)
        pattern = re.compile(
            r"public\s+static\s+String\s+padLeft\s*\(\s*"
            r"(?:final\s+)?(?:@\w+\s+)?String\s+\w+\s*,\s*"
            r"(?:final\s+)?int\s+\w+\s*,\s*"
            r"(?:final\s+)?char\s+\w+\s*\)"
        )
        assert pattern.search(content), (
            "expected `public static String padLeft(String, int, char)` "
            "signature in StringUtils.java"
        )

    def test_agent_test_file_exists_in_correct_package(self):
        """L1: StringPadLeftTests is placed in the required package/dir."""
        assert os.path.isfile(AGENT_TEST), (
            f"expected new test class at {AGENT_TEST}"
        )
        content = _read(AGENT_TEST)
        assert re.search(
            r"package\s+org\.junit\.platform\.commons\.util\s*;", content
        ), "test class must declare package org.junit.platform.commons.util"
        assert "class StringPadLeftTests" in content, (
            "file must declare class StringPadLeftTests"
        )

    def test_agent_test_uses_data_driven_and_grouping_constructs(self):
        """L1: agent suite uses a parameterized (data-driven) method fed by a
        rows source AND a grouped-assertion (assertAll) method."""
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
            "at least one grouped-assertion method (assertAll) is required so a "
            "batch of related expectations is evaluated even when one fails"
        )

    def test_agent_suite_checks_both_preconditions(self):
        """L1: the agent suite references both precondition failure cases
        (null value and negative minLength) and the exception type."""
        content = _read(AGENT_TEST)
        assert "PreconditionViolationException" in content, (
            "agent suite must assert PreconditionViolationException for the "
            "precondition cases"
        )
        assert "assertThrows" in content, (
            "agent suite must use assertThrows to verify precondition failures"
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
        """L2: the agent's StringPadLeftTests compiles, passes, and reports at
        least 10 executed test results (data rows counted separately)."""
        proc, report = _run_gradle_tests(
            "org.junit.platform.commons.util.StringPadLeftTests"
        )
        assert report, (
            "no JUnit XML report produced for StringPadLeftTests.\n"
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
            f"expected >= 10 executed tests in StringPadLeftTests, "
            f"got {executed} (tests={tests}, skipped={skipped})"
        )

    def test_independent_padding_contract(self):
        """L2: independent suite pins exact padded output, exact length, that
        the original value is preserved as the suffix, and that the left side
        is solely padChar copies. A stub that pads on the RIGHT, reorders the
        characters, or produces the wrong length FAILS this probe."""
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
            "independent padLeft contract probe FAILED -> production "
            "`padLeft` does not satisfy the left-pad / length / suffix-preserved "
            "contract.\n"
            f"failures={failures} errors={errors} tests={tests}\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-4000:]}"
        )
        # sanity: the probe really ran its many cases
        assert tests - skipped >= 13, (
            f"independent probe executed too few cases ({tests - skipped}); "
            "it may not have run correctly"
        )

    def test_independent_probe_actually_distinguishes_stub(self):
        """L2 (meta): structural guard so the independent probe can never be
        silently weakened. The generated artifact must keep the left-pad,
        exact-length, suffix-preserved and precondition assertions."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        src = _read(INDEP_TEST)
        assert "endsWith(value)" in src, "probe lost suffix-preserved assertion"
        assert "must be max(value.length(), minLength)" in src, (
            "probe lost exact-length assertion"
        )
        assert "left side must consist solely of padChar" in src, (
            "probe lost left-only padding assertion"
        )
        assert "padCharIsHonoured" in src, "probe lost pad-char honoured case"
        assert "PreconditionViolationException" in src, (
            "probe lost precondition assertions"
        )

    def test_unchanged_input_contract_via_independent_probe(self):
        """L2: values already at/over minLength (exactly equal, longer, and
        minLength 0) are returned unchanged. Verified by the independent
        probe's `returnsUnchangedWhenAlreadyLongEnough` case."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent unchanged-input verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "unchanged-input contract failed in independent probe.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        assert "returnsUnchangedWhenAlreadyLongEnough" in joined, (
            "expected the unchanged-input parameterized case to have executed"
        )

    def test_precondition_failures_via_independent_probe(self):
        """L2: null value and negative minLength both raise
        PreconditionViolationException (null message mentions null). A naive
        implementation that skips these checks FAILS this probe."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent precondition verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "precondition contract failed in independent probe -> `padLeft` "
            "skipped or mis-implemented null / negative-minLength checks.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        for expected_case in (
            "nullValueThrowsPreconditionViolation",
            "negativeMinLengthThrowsPreconditionViolation",
        ):
            assert expected_case in joined, (
                f"expected precondition case '{expected_case}' to have executed"
            )

    def test_padchar_and_emptystring_contract_via_independent_probe(self):
        """L2: padChar value is honoured (not hardcoded) and empty string is
        padded to exactly minLength copies of padChar. Verified by the probe's
        `padCharIsHonoured` and `emptyStringBecomesAllPadChars` cases."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent padChar/empty-string verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "padChar/empty-string contract failed in independent probe.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        for expected_case in (
            "padCharIsHonoured",
            "emptyStringBecomesAllPadChars",
        ):
            assert expected_case in joined, (
                f"expected case '{expected_case}' to have executed"
            )
