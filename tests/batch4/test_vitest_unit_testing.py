"""
Test for the 'vitest-unit-testing' skill (variant batch ext4).

Task: add an exported `formatByteSize(bytes: number): string` helper to
packages/vite/src/node/utils.ts that renders a non-negative byte count as a
compact, binary (1024-based) human-readable string, plus a dedicated vitest
spec at packages/vite/src/node/__tests__/formatByteSize.spec.ts.

Required behavior (from the variant requirement doc):
- Values < 1024 -> integer bytes with suffix " B" and no decimals
  (0 -> "0 B", 512 -> "512 B", 1023 -> "1023 B").
- >= 1024 -> divide by 1024 repeatedly, render with the largest unit whose
  quotient is < 1024, using the ladder KB, MB, GB, TB, with EXACTLY two
  decimals (1024 -> "1.00 KB", 1536 -> "1.50 KB", 1048576 -> "1.00 MB").
- Exactly one space between number and unit.
- TB is the largest unit; values >= 1024^5 stay in TB.

Verification strategy:
- L1: the deliverable source/spec files exist and the export + import are
  present and minimally well-formed.
- L2: DYNAMIC EXECUTION via the repo's native toolchain (vitest, run with
  `pnpm exec vitest run ...`). To avoid trusting the agent's own spec, we drop
  INDEPENDENT driver spec files into the repo's __tests__ directory that import
  `formatByteSize` from `../utils` and pin the exact required output strings.
  A naive implementation (decimal 1000-based division, wrong decimal count,
  missing space, "B" used at 1024, or off-by-one boundary handling) makes at
  least one driver spec fail. We also run the agent's delivered spec.
"""

import os
import re
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/vite"
TESTS_DIR = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "__tests__")
UTILS_TS = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "utils.ts")
AGENT_SPEC = os.path.join(TESTS_DIR, "formatByteSize.spec.ts")

# abs paths of driver specs we drop in; filled by _write_spec, removed on teardown.
_DRIVER_FILES = []


def _vitest(rel_spec_path, timeout=600):
    """Run a single spec file via the repo's native vitest from repo root."""
    cmd = ["pnpm", "exec", "vitest", "run", rel_spec_path]
    return subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _write_spec(name, body):
    """Write a driver spec into the repo __tests__ dir; return its repo-rel path."""
    assert os.path.isdir(TESTS_DIR), f"tests dir missing: {TESTS_DIR}"
    fname = name if name.endswith(".spec.ts") else name + ".spec.ts"
    abspath = os.path.join(TESTS_DIR, fname)
    with open(abspath, "w") as f:
        f.write(textwrap.dedent(body).lstrip("\n"))
    rel = os.path.relpath(abspath, REPO_DIR)
    _DRIVER_FILES.append(abspath)
    return rel


@pytest.fixture(scope="module", autouse=True)
def _cleanup_driver_specs():
    """Remove any driver specs we created so we leave the repo clean."""
    yield
    for p in _DRIVER_FILES:
        try:
            os.remove(p)
        except OSError:
            pass


class TestVitestUnitTesting:
    """Verify the formatByteSize helper and its vitest coverage."""

    REPO_DIR = "/workspace/vite"

    # ------------------------------------------------------------------
    # L1 — deliverables exist / minimally well-formed
    # ------------------------------------------------------------------

    def test_utils_file_exists(self):
        """utils.ts (the modify target) must exist."""
        assert os.path.isfile(UTILS_TS), f"missing {UTILS_TS}"

    def test_format_byte_size_is_exported(self):
        """utils.ts must export a function named formatByteSize taking one param."""
        with open(UTILS_TS) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+formatByteSize\s*\(", src
        ), "formatByteSize not exported as a function from utils.ts"

    def test_agent_spec_file_exists(self):
        """The dedicated spec file must be delivered."""
        assert os.path.isfile(AGENT_SPEC), f"missing {AGENT_SPEC}"

    def test_agent_spec_imports_from_utils(self):
        """The spec must import formatByteSize from ../utils (not redefine it)."""
        with open(AGENT_SPEC) as f:
            spec = f.read()
        assert "formatByteSize" in spec, "spec does not reference formatByteSize"
        assert re.search(
            r"from\s+['\"]\.\./utils['\"]", spec
        ), "spec must import from '../utils'"

    def test_agent_spec_uses_each_table_and_snapshot(self):
        """Doc requires a test.each/it.each table and an inline snapshot assertion."""
        with open(AGENT_SPEC) as f:
            spec = f.read()
        assert re.search(
            r"\b(test|it)\.each\b", spec
        ), "spec must use test.each / it.each over a table"
        assert "toMatchInlineSnapshot" in spec, (
            "spec must contain at least one inline snapshot assertion "
            "(toMatchInlineSnapshot)"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic execution against INDEPENDENT driver specs.
    # Each test drops a focused spec that imports the real implementation
    # and pins the precise required output via vitest.
    # ------------------------------------------------------------------

    def test_full_truth_table(self):
        """Every row of the requirement's Expected-Functionality table must hold."""
        rel = _write_spec(
            "zz_driver_table",
            """
            import { describe, expect, test } from 'vitest'
            import { formatByteSize } from '../utils'

            describe('formatByteSize truth table', () => {
              test('table', () => {
                expect(formatByteSize(0)).toBe('0 B')
                expect(formatByteSize(512)).toBe('512 B')
                expect(formatByteSize(1023)).toBe('1023 B')
                expect(formatByteSize(1024)).toBe('1.00 KB')
                expect(formatByteSize(1536)).toBe('1.50 KB')
                expect(formatByteSize(1048576)).toBe('1.00 MB')
                expect(formatByteSize(1073741824)).toBe('1.00 GB')
                expect(formatByteSize(1099511627776)).toBe('1.00 TB')
              })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "driver truth-table spec failed (vitest nonzero)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_bytes_branch_no_decimals(self):
        """Below 1024: integer bytes, suffix ' B', NO decimals."""
        rel = _write_spec(
            "zz_driver_bytes",
            """
            import { expect, test } from 'vitest'
            import { formatByteSize } from '../utils'

            test('bytes branch', () => {
              expect(formatByteSize(0)).toBe('0 B')
              expect(formatByteSize(1)).toBe('1 B')
              expect(formatByteSize(512)).toBe('512 B')
              expect(formatByteSize(1023)).toBe('1023 B')
              // must not append decimals in the bytes branch
              expect(formatByteSize(512)).not.toMatch(/\\./)
              expect(formatByteSize(1023)).not.toMatch(/KB|MB/)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "bytes-branch formatting wrong (decimals/unit leaked, or wrong number)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_kb_boundary_exact_1024(self):
        """1023 stays in B; exactly 1024 flips to '1.00 KB' (not '1024.00 B')."""
        rel = _write_spec(
            "zz_driver_kb_boundary",
            """
            import { expect, test } from 'vitest'
            import { formatByteSize } from '../utils'

            test('KB boundary', () => {
              expect(formatByteSize(1023)).toBe('1023 B')
              expect(formatByteSize(1024)).toBe('1.00 KB')
              // a naive impl that keeps bytes at 1024 would produce '1024 B'
              expect(formatByteSize(1024)).not.toBe('1024 B')
              expect(formatByteSize(1024)).not.toBe('1024.00 B')
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "1024 boundary wrong (must be '1.00 KB', not bytes)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_exactly_two_decimals(self):
        """Non-byte units render with EXACTLY two decimal places."""
        rel = _write_spec(
            "zz_driver_decimals",
            """
            import { expect, test } from 'vitest'
            import { formatByteSize } from '../utils'

            test('two decimals', () => {
              expect(formatByteSize(1024)).toBe('1.00 KB')
              expect(formatByteSize(1536)).toBe('1.50 KB')
              // 1.25 KB
              expect(formatByteSize(1280)).toBe('1.25 KB')
              // every non-byte result has exactly two digits after the dot
              for (const v of [1024, 1536, 1280, 1048576, 1073741824]) {
                expect(formatByteSize(v)).toMatch(/^\\d+\\.\\d{2} (KB|MB|GB|TB)$/)
              }
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "decimal formatting wrong (must be exactly two decimals on units)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_single_space_separator(self):
        """There must be exactly one space between number and unit, in all branches."""
        rel = _write_spec(
            "zz_driver_space",
            """
            import { expect, test } from 'vitest'
            import { formatByteSize } from '../utils'

            test('single space', () => {
              for (const v of [0, 512, 1023, 1024, 1536, 1048576, 1073741824,
                               1099511627776]) {
                const s = formatByteSize(v)
                const parts = s.split(' ')
                expect(parts.length).toBe(2)          // exactly one space
                expect(parts[0].length).toBeGreaterThan(0)
                expect(['B', 'KB', 'MB', 'GB', 'TB']).toContain(parts[1])
                expect(s).not.toMatch(/  /)           // no double space
                expect(s).not.toMatch(/^\\s|\\s$/)      // no leading/trailing space
              }
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "spacing wrong (must be exactly one space between number and unit)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_binary_not_decimal_division(self):
        """Units are 1024-based, NOT 1000-based; a decimal impl must fail here."""
        rel = _write_spec(
            "zz_driver_binary",
            """
            import { expect, test } from 'vitest'
            import { formatByteSize } from '../utils'

            test('binary base 1024', () => {
              // 1000 bytes is still in the bytes branch under base-1024.
              expect(formatByteSize(1000)).toBe('1000 B')
              // 1 MiB == 1048576 bytes -> exactly 1.00 MB (base-1024).
              expect(formatByteSize(1048576)).toBe('1.00 MB')
              // base-1000 impl would call 1048576 about '1.05 MB' and 2048 '2.05 KB';
              // base-1024 gives 2048 -> '2.00 KB'.
              expect(formatByteSize(2048)).toBe('2.00 KB')
              // 1500000 bytes -> 1.43 MB under base-1024 (1500000/1048576).
              expect(formatByteSize(1500000)).toBe('1.43 MB')
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "division base wrong (must be binary 1024-based, not decimal 1000)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_unit_boundaries_off_by_one(self):
        """A value one below a unit boundary stays in the smaller unit."""
        rel = _write_spec(
            "zz_driver_offbyone",
            """
            import { expect, test } from 'vitest'
            import { formatByteSize } from '../utils'

            test('off by one boundaries', () => {
              // 1048575 = 1MiB - 1 -> still KB, not MB.
              expect(formatByteSize(1048575)).toMatch(/ KB$/)
              expect(formatByteSize(1048576)).toBe('1.00 MB')
              // 1073741823 = 1GiB - 1 -> still MB.
              expect(formatByteSize(1073741823)).toMatch(/ MB$/)
              expect(formatByteSize(1073741824)).toBe('1.00 GB')
              // 1099511627775 = 1TiB - 1 -> still GB.
              expect(formatByteSize(1099511627775)).toMatch(/ GB$/)
              expect(formatByteSize(1099511627776)).toBe('1.00 TB')
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "unit-boundary selection wrong (largest unit with quotient < 1024)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_each_unit_ladder_rung(self):
        """Each rung of the KB/MB/GB/TB ladder is reachable with a clean 1.00."""
        rel = _write_spec(
            "zz_driver_ladder",
            """
            import { expect, test } from 'vitest'
            import { formatByteSize } from '../utils'

            test('ladder rungs', () => {
              expect(formatByteSize(1024)).toBe('1.00 KB')
              expect(formatByteSize(1024 ** 2)).toBe('1.00 MB')
              expect(formatByteSize(1024 ** 3)).toBe('1.00 GB')
              expect(formatByteSize(1024 ** 4)).toBe('1.00 TB')
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "unit ladder wrong (KB/MB/GB/TB not all correct)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_tb_is_largest_unit(self):
        """TB is the ceiling: values at/beyond 1024^5 stay expressed in TB."""
        rel = _write_spec(
            "zz_driver_tb_cap",
            """
            import { expect, test } from 'vitest'
            import { formatByteSize } from '../utils'

            test('TB cap', () => {
              // 1024^5 bytes = 1024 TiB -> must remain in TB (ladder stops at TB).
              const petabyte = 1024 ** 5
              expect(formatByteSize(petabyte)).toMatch(/ TB$/)
              // value should be 1024.00 TB, never a 'PB'/'EB' unit.
              expect(formatByteSize(petabyte)).toBe('1024.00 TB')
              expect(formatByteSize(1024 ** 6)).toMatch(/ TB$/)
              expect(formatByteSize(petabyte)).not.toMatch(/PB|EB/)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "TB cap wrong (ladder must not extend past TB)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_return_type_is_string(self):
        """Result is always a string ending in a valid unit token."""
        rel = _write_spec(
            "zz_driver_type",
            """
            import { expect, test } from 'vitest'
            import { formatByteSize } from '../utils'

            test('return type', () => {
              for (const v of [0, 1, 512, 1024, 1048576, 1073741824,
                               1099511627776]) {
                const s = formatByteSize(v)
                expect(typeof s).toBe('string')
                expect(s).toMatch(/ (B|KB|MB|GB|TB)$/)
              }
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "return value not a well-formed string\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_agent_delivered_spec_passes(self):
        """The agent's own delivered spec must pass under native vitest."""
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        rel = os.path.relpath(AGENT_SPEC, REPO_DIR)
        res = _vitest(rel)
        assert res.returncode == 0, (
            "agent's formatByteSize.spec.ts does not pass\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
        combined = (res.stdout + res.stderr).lower()
        assert "no test" not in combined, "agent spec contains no tests"
