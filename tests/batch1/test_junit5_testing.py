"""Verification suite for the `junit5-testing` skill task.

Task: add `StringUtils.abbreviate(String, int)` to the
`junit-platform-commons` module plus a data-driven, grouped-assertion JUnit 5
test suite (`StringAbbreviationTests`) under `platform-tests`.

What this file verifies:
  * L1 - the deliverable source files exist and are minimally well-formed
    (correct package, exact `abbreviate` signature present, the new test class
    uses data-driven + grouped-assertion JUnit 5 constructs).
  * L2 - DYNAMIC EXECUTION via the repo's native Gradle toolchain:
      - the agent's own `StringAbbreviationTests` class compiles and passes,
        producing at least 10 executed test results (parsed from the JUnit XML
        report).
      - an INDEPENDENT JUnit 5 test class (written by THIS file into the repo)
        exercises `StringUtils.abbreviate` directly and pins down the exact
        contract from the requirement doc.  A naive stub (returns input
        unchanged, drops the ellipsis, miscounts the retained prefix, or skips
        the precondition checks) fails this independent class regardless of
        what the agent wrote in its own test file.

The independent class is the discriminative core: it does not trust any test
file the agent authored.
"""

import os
import re
import shutil
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
AGENT_TEST = os.path.join(TEST_DIR, "StringAbbreviationTests.java")

# Name chosen to be unlikely to collide with anything the agent created.
INDEP_CLASS = "AbbreviateContractProbeTests"
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
        "-q" if False else "--console=plain",
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
# agent's production code, so a naive `abbreviate` cannot pass it.
# ---------------------------------------------------------------------------

_INDEP_SOURCE = r"""/* Auto-generated by the benchmark verifier. Do not edit. */
package org.junit.platform.commons.util;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
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
    @MethodSource("truncationRows")
    void truncatesWithEllipsisAndExactLength(String input, int limit, String expected) {
        String actual = StringUtils.abbreviate(input, limit);
        assertAll(
            () -> assertEquals(expected, actual, "value=" + input + " limit=" + limit),
            () -> assertEquals(limit, actual.length(), "truncated length must equal limit"),
            () -> assertTrue(actual.endsWith("..."), "truncated result must end with ellipsis"),
            () -> assertEquals(input.substring(0, limit - 3), actual.substring(0, limit - 3),
                    "exactly (limit-3) leading chars retained")
        );
    }

    static Stream<Arguments> truncationRows() {
        return Stream.of(
            Arguments.of("hello", 4, "h..."),
            Arguments.of("hello world", 8, "hello..."),
            Arguments.of("abcdefghij", 7, "abcd..."),
            Arguments.of("0123456789", 6, "012..."),
            Arguments.of("the quick brown fox", 10, "the qu...")
        );
    }

    @ParameterizedTest
    @MethodSource("unchangedRows")
    void returnsUnchangedWhenWithinLimit(String input, int limit) {
        String actual = StringUtils.abbreviate(input, limit);
        assertAll(
            () -> assertEquals(input, actual, "must be returned unchanged"),
            () -> assertTrue(actual.length() <= limit, "unchanged result within limit")
        );
    }

    static Stream<Arguments> unchangedRows() {
        return Stream.of(
            Arguments.of("hello", 5),   // exactly equal to limit
            Arguments.of("hi", 4),      // shorter than limit
            Arguments.of("", 4),        // empty string
            Arguments.of("abcd", 4),    // exactly at min limit
            Arguments.of("a", 10)
        );
    }

    @Test
    void emptyStringNeverGetsEllipsis() {
        assertEquals("", StringUtils.abbreviate("", 4));
    }

    @Test
    void exactLengthIsNotAbbreviated() {
        // length == maxLength must not append an ellipsis
        assertEquals("abcd", StringUtils.abbreviate("abcd", 4));
        assertEquals("hello", StringUtils.abbreviate("hello", 5));
    }

    @Test
    void nullValueThrowsPreconditionViolation() {
        PreconditionViolationException ex = assertThrows(
            PreconditionViolationException.class,
            () -> StringUtils.abbreviate(null, 10));
        assertTrue(ex.getMessage() != null && ex.getMessage().toLowerCase().contains("null"),
            "message must mention null, was: " + ex.getMessage());
    }

    @Test
    void maxLengthBelowMinimumThrowsPreconditionViolation() {
        // below 4 must fail regardless of how short value is
        assertThrows(PreconditionViolationException.class,
            () -> StringUtils.abbreviate("hello", 3));
        assertThrows(PreconditionViolationException.class,
            () -> StringUtils.abbreviate("x", 1));
        assertThrows(PreconditionViolationException.class,
            () -> StringUtils.abbreviate("", 0));
    }

    @Test
    void preconditionCheckedBeforeReturningShortValue() {
        // even when value is already short, maxLength < 4 must still throw
        assertThrows(PreconditionViolationException.class,
            () -> StringUtils.abbreviate("ab", 3));
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

    def test_abbreviate_signature_present(self):
        """L1: StringUtils declares the exact public abbreviate signature."""
        content = _read(MAIN_SRC)
        # exact signature, tolerant only of whitespace between tokens
        pattern = re.compile(
            r"public\s+static\s+String\s+abbreviate\s*\(\s*"
            r"(?:final\s+)?(?:@\w+\s+)?String\s+\w+\s*,\s*"
            r"(?:final\s+)?int\s+\w+\s*\)"
        )
        assert pattern.search(content), (
            "expected `public static String abbreviate(String, int)` "
            "signature in StringUtils.java"
        )

    def test_agent_test_file_exists_in_correct_package(self):
        """L1: StringAbbreviationTests is placed in the required package/dir."""
        assert os.path.isfile(AGENT_TEST), (
            f"expected new test class at {AGENT_TEST}"
        )
        content = _read(AGENT_TEST)
        assert re.search(
            r"package\s+org\.junit\.platform\.commons\.util\s*;", content
        ), "test class must declare package org.junit.platform.commons.util"
        assert "class StringAbbreviationTests" in content, (
            "file must declare class StringAbbreviationTests"
        )

    def test_agent_test_uses_data_driven_and_grouping_constructs(self):
        """L1: agent suite uses a parameterized (data-driven) method and a
        grouped-assertion (assertAll) method, per the requirement doc."""
        content = _read(AGENT_TEST)
        assert "@ParameterizedTest" in content, (
            "truncation cases must be expressed as a single data-driven "
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

    # ----------------------------- L2 -----------------------------------

    def test_agent_suite_passes_with_enough_executions(self):
        """L2: the agent's StringAbbreviationTests compiles, passes, and
        reports at least 10 executed test results (data rows counted)."""
        proc, report = _run_gradle_tests(
            "org.junit.platform.commons.util.StringAbbreviationTests"
        )
        assert report, (
            "no JUnit XML report produced for StringAbbreviationTests.\n"
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
            f"expected >= 10 executed tests in StringAbbreviationTests, "
            f"got {executed} (tests={tests}, skipped={skipped})"
        )

    def test_independent_truncation_contract(self):
        """L2: independent suite pins exact truncation output, length and
        retained prefix. A stub that drops the ellipsis or miscounts fails."""
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
            "independent abbreviate contract probe FAILED -> production "
            "`abbreviate` does not satisfy the truncation/length/prefix "
            "contract.\n"
            f"failures={failures} errors={errors} tests={tests}\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-4000:]}"
        )
        # sanity: the probe really ran its many cases
        assert tests - skipped >= 14, (
            f"independent probe executed too few cases ({tests - skipped}); "
            "it may not have run correctly"
        )

    def test_independent_probe_actually_distinguishes_stub(self):
        """L2 (meta): confirm the independent probe is discriminative by
        running it against a deliberately wrong abbreviate via a private
        in-test shadow is not possible; instead assert the probe contains the
        ellipsis/length/prefix assertions that would reject a stub. This is a
        structural guard so the probe can never be silently weakened."""
        # The probe source is generated by THIS test file, so check the
        # generated artifact on disk reflects the strict assertions.
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        src = _read(INDEP_TEST)
        assert 'endsWith("...")' in src, "probe lost ellipsis assertion"
        assert "assertEquals(limit, actual.length()" in src, (
            "probe lost exact-length assertion"
        )
        assert "limit - 3" in src, "probe lost retained-prefix assertion"
        assert "PreconditionViolationException" in src, (
            "probe lost precondition assertions"
        )

    def test_unchanged_input_contract_via_independent_probe(self):
        """L2: values within the limit (shorter, exactly-equal, empty) are
        returned unchanged. Verified by the independent probe's
        `returnsUnchangedWhenWithinLimit` / empty-string cases."""
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
        assert "returnsUnchangedWhenWithinLimit" in joined, (
            "expected the unchanged-input parameterized case to have executed"
        )

    def test_precondition_failures_via_independent_probe(self):
        """L2: null value and maxLength < 4 both raise
        PreconditionViolationException (null message mentions null). The
        precondition on maxLength is checked even for already-short values."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent precondition verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "precondition contract failed in independent probe -> `abbreviate` "
            "skipped or mis-implemented null / min-length checks.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        for expected_case in (
            "nullValueThrowsPreconditionViolation",
            "maxLengthBelowMinimumThrowsPreconditionViolation",
            "preconditionCheckedBeforeReturningShortValue",
        ):
            assert expected_case in joined, (
                f"expected precondition case '{expected_case}' to have executed"
            )
