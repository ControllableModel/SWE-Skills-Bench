"""Verification suite for the `junit5-testing` skill task (variant ext4).

Task: add `StringUtils.center(String value, int width, char padChar)` to the
`junit-platform-commons` module plus a data-driven, grouped-assertion JUnit 5
test suite (`StringCenterTests`) under `platform-tests`.

Contract under test (from the variant requirement doc):
  * If `value.length() >= width`, `value` is returned unchanged.
  * Otherwise the result length is exactly `width`; total padding is
    `width - value.length()` copies of `padChar`, split between sides with the
    EXTRA pad (odd total) going on the RIGHT
    (left = floor(total/2), right = ceil(total/2)).
  * The empty string centered in `width` becomes `width` copies of `padChar`.
  * `null` value -> PreconditionViolationException (message mentions null).
  * negative `width` -> PreconditionViolationException (non-negative message).

What this file verifies:
  * L1 - the deliverable source files exist and are minimally well-formed
    (correct package, exact `center(String, int, char)` signature present, the
    new test class uses data-driven + grouped-assertion JUnit 5 constructs and
    carries human-readable descriptions).
  * L2 - DYNAMIC EXECUTION via the repo's native Gradle toolchain:
      - the agent's own `StringCenterTests` class compiles and passes,
        producing at least 10 executed test results (parsed from the JUnit XML
        report).
      - an INDEPENDENT JUnit 5 test class (written by THIS file into the repo)
        exercises `StringUtils.center` directly and pins down the exact
        contract.  A naive stub (pads only one side, puts the extra pad on the
        wrong side, miscounts the split, returns wrong length, or skips the
        precondition checks) FAILS this independent class regardless of what
        the agent wrote in its own test file.

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
AGENT_TEST = os.path.join(TEST_DIR, "StringCenterTests.java")

# Name chosen to be unlikely to collide with anything the agent created.
INDEP_CLASS = "CenterContractProbeTests"
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
    simple = test_filter.split(".")[-1]
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
# agent's production code, so a naive `center` cannot pass it.
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

    // Exact-output rows from the requirement doc plus extra even/odd cases.
    @ParameterizedTest
    @MethodSource("exactRows")
    void centersToExactOutput(String value, int width, char pad, String expected) {
        String actual = StringUtils.center(value, width, pad);
        assertAll(
            () -> assertEquals(expected, actual,
                    "center(" + value + "," + width + ",'" + pad + "')"),
            () -> assertEquals(expected.length(), actual.length(),
                    "result length")
        );
    }

    static Stream<Arguments> exactRows() {
        return Stream.of(
            // even padding -> symmetric
            Arguments.of("ab", 6, '*', "**ab**"),
            // odd padding -> extra pad on the RIGHT
            Arguments.of("ab", 5, '*', "*ab**"),
            // single char, odd padding (3 -> left 1 right 2)
            Arguments.of("x", 4, '.', ".x.."),
            // empty string -> width copies of pad
            Arguments.of("", 3, '-', "---"),
            Arguments.of("", 4, '#', "####"),
            // larger even
            Arguments.of("ab", 8, '+', "+++ab+++"),
            // larger odd (total 5 -> left 2 right 3)
            Arguments.of("ab", 7, '=', "==ab==="),
            // single pad total on right (total 1 -> left 0 right 1)
            Arguments.of("ab", 3, '*', "ab*")
        );
    }

    // Total padding split: left=floor(total/2), right=ceil(total/2).
    @ParameterizedTest
    @MethodSource("splitRows")
    void splitsPaddingWithExtraOnRight(String value, int width, char pad) {
        String actual = StringUtils.center(value, width, pad);
        int total = width - value.length();
        int left = total / 2;
        int right = total - left;
        // Verify the precise left/right boundaries: a one-sided pad or an
        // extra-on-left implementation fails here.
        assertAll(
            () -> assertEquals(width, actual.length(), "length must equal width"),
            () -> assertEquals(padRun(left, pad), actual.substring(0, left),
                    "left padding (floor) must be " + left + " pads"),
            () -> assertEquals(value, actual.substring(left, left + value.length()),
                    "value must sit between the pads"),
            () -> assertEquals(padRun(right, pad),
                    actual.substring(left + value.length()),
                    "right padding (ceil) must be " + right + " pads"),
            () -> assertTrue(right >= left,
                    "right side never has fewer pads than left")
        );
    }

    static Stream<Arguments> splitRows() {
        return Stream.of(
            Arguments.of("ab", 5, '*'),   // total 3 -> 1 / 2
            Arguments.of("ab", 6, '*'),   // total 4 -> 2 / 2
            Arguments.of("x", 4, '.'),    // total 3 -> 1 / 2
            Arguments.of("hi", 9, 'o'),   // total 7 -> 3 / 4
            Arguments.of("", 5, '-')      // total 5 -> 2 / 3
        );
    }

    private static String padRun(int n, char pad) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < n; i++) {
            sb.append(pad);
        }
        return sb.toString();
    }

    // value already wide enough (>= width) -> returned unchanged.
    @ParameterizedTest
    @MethodSource("unchangedRows")
    void returnsUnchangedWhenAlreadyWideEnough(String value, int width) {
        String actual = StringUtils.center(value, width, '*');
        assertAll(
            () -> assertEquals(value, actual, "must be returned unchanged"),
            () -> assertEquals(value.length(), actual.length(),
                    "unchanged length")
        );
    }

    static Stream<Arguments> unchangedRows() {
        return Stream.of(
            Arguments.of("abc", 3),       // exactly equal to width
            Arguments.of("abcdef", 4),    // longer than width
            Arguments.of("hello", 0),     // width 0
            Arguments.of("x", 1)          // single char exactly at width
        );
    }

    @Test
    void emptyStringBecomesAllPad() {
        assertEquals("-----", StringUtils.center("", 5, '-'));
        assertEquals("", StringUtils.center("", 0, '-'));
    }

    @Test
    void nullValueThrowsPreconditionViolation() {
        PreconditionViolationException ex = assertThrows(
            PreconditionViolationException.class,
            () -> StringUtils.center(null, 5, '*'));
        assertTrue(ex.getMessage() != null
                && ex.getMessage().toLowerCase().contains("null"),
            "message must mention null, was: " + ex.getMessage());
    }

    @Test
    void negativeWidthThrowsPreconditionViolation() {
        assertThrows(PreconditionViolationException.class,
            () -> StringUtils.center("ab", -1, '*'));
        assertThrows(PreconditionViolationException.class,
            () -> StringUtils.center("", -5, '*'));
    }

    @Test
    void preconditionCheckedRegardlessOfValueWidthRelation() {
        // negative width must throw even when value would otherwise be
        // "already wide enough" relative to a smaller field.
        assertThrows(PreconditionViolationException.class,
            () -> StringUtils.center("alreadylong", -1, '*'));
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

    def test_center_signature_present(self):
        """L1: StringUtils declares the exact public center signature
        `public static String center(String, int, char)`."""
        content = _read(MAIN_SRC)
        # exact signature, tolerant only of whitespace / annotations between
        # tokens.
        pattern = re.compile(
            r"public\s+static\s+String\s+center\s*\(\s*"
            r"(?:final\s+)?(?:@\w+\s+)?String\s+\w+\s*,\s*"
            r"(?:final\s+)?int\s+\w+\s*,\s*"
            r"(?:final\s+)?char\s+\w+\s*\)"
        )
        assert pattern.search(content), (
            "expected `public static String center(String, int, char)` "
            "signature in StringUtils.java"
        )

    def test_agent_test_file_exists_in_correct_package(self):
        """L1: StringCenterTests is placed in the required package/dir."""
        assert os.path.isfile(AGENT_TEST), (
            f"expected new test class at {AGENT_TEST}"
        )
        content = _read(AGENT_TEST)
        assert re.search(
            r"package\s+org\.junit\.platform\.commons\.util\s*;", content
        ), "test class must declare package org.junit.platform.commons.util"
        assert "class StringCenterTests" in content, (
            "file must declare class StringCenterTests"
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

    # ----------------------------- L2 -----------------------------------

    def test_agent_suite_passes_with_enough_executions(self):
        """L2: the agent's StringCenterTests compiles, passes, and reports at
        least 10 executed test results (data rows counted)."""
        proc, report = _run_gradle_tests(
            "org.junit.platform.commons.util.StringCenterTests"
        )
        assert report, (
            "no JUnit XML report produced for StringCenterTests.\n"
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
            f"expected >= 10 executed tests in StringCenterTests, "
            f"got {executed} (tests={tests}, skipped={skipped})"
        )

    def test_independent_exact_output_contract(self):
        """L2: independent suite pins the exact centered output and length for
        the doc's rows (even, odd-on-right, empty, single char). A stub that
        pads one side, mislocates the odd pad, or returns the wrong length
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
            "independent center contract probe FAILED -> production `center` "
            "does not satisfy the exact-output / split / precondition "
            "contract.\n"
            f"failures={failures} errors={errors} tests={tests}\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-4000:]}"
        )
        # sanity: the probe really ran its many cases (8 exact + 5 split +
        # 4 unchanged + 4 single-method tests = 21 executions).
        assert tests - skipped >= 18, (
            f"independent probe executed too few cases ({tests - skipped}); "
            "it may not have run correctly"
        )

    def test_independent_probe_actually_distinguishes_stub(self):
        """L2 (meta): structural guard ensuring the independent probe keeps the
        assertions that reject a naive stub (exact output, left/right split,
        extra-on-right, precondition checks). The probe can never be silently
        weakened without this failing."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        src = _read(INDEP_TEST)
        assert "centersToExactOutput" in src, "probe lost exact-output method"
        assert "splitsPaddingWithExtraOnRight" in src, (
            "probe lost the floor/ceil split assertion"
        )
        assert "actual.substring(0, left)" in src, (
            "probe lost the left-padding boundary assertion"
        )
        assert "actual.substring(left + value.length())" in src, (
            "probe lost the right-padding boundary assertion"
        )
        assert "right >= left" in src, "probe lost extra-on-right invariant"
        assert "PreconditionViolationException" in src, (
            "probe lost precondition assertions"
        )

    def test_split_and_unchanged_contract_via_independent_probe(self):
        """L2: floor/ceil padding split (extra on right) and already-wide
        (returned unchanged) cases pass in the independent probe."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent split/unchanged verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "split / unchanged contract failed in independent probe.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        assert "splitsPaddingWithExtraOnRight" in joined, (
            "expected the padding-split parameterized case to have executed"
        )
        assert "returnsUnchangedWhenAlreadyWideEnough" in joined, (
            "expected the already-wide unchanged case to have executed"
        )

    def test_precondition_failures_via_independent_probe(self):
        """L2: null value and negative width both raise
        PreconditionViolationException (null message mentions null). The width
        precondition is checked even when the value is 'already wide enough'."""
        if not os.path.exists(INDEP_TEST):
            _write_indep_class()
        proc, report = _run_gradle_tests(
            f"org.junit.platform.commons.util.{INDEP_CLASS}"
        )
        assert report, "no report for independent precondition verification"
        _, failures, errors, _, names = _report_totals(report)
        assert failures == 0 and errors == 0, (
            "precondition contract failed in independent probe -> `center` "
            "skipped or mis-implemented null / negative-width checks.\n"
            f"--- gradle stdout (tail) ---\n{proc.stdout[-3000:]}"
        )
        joined = " ".join(names)
        for expected_case in (
            "nullValueThrowsPreconditionViolation",
            "negativeWidthThrowsPreconditionViolation",
            "preconditionCheckedRegardlessOfValueWidthRelation",
        ):
            assert expected_case in joined, (
                f"expected precondition case '{expected_case}' to have executed"
            )
