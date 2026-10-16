"""
Test for the 'vitest-unit-testing' skill  (variant batch: ext5).

Task: add an exported pure parser

    export function parseEnvLine(line: string): { key: string; value: string } | null

to packages/vite/src/node/utils.ts, plus a dedicated vitest spec at
packages/vite/src/node/__tests__/parseEnvLine.spec.ts.

`parseEnvLine` parses one dotenv-style `KEY=VALUE` line with quoting and inline
comment semantics:
  - key = text before first '=', trimmed; value = everything after first '='.
  - raw value is trimmed of surrounding whitespace before processing.
  - matching double/single quotes around the value are stripped (inner text
    verbatim, no inner trim).
  - for UNQUOTED values, an inline comment introduced by ' #' (a '#' preceded by
    whitespace) and everything after it is discarded, remaining value right-trimmed.
    A '#' with no preceding whitespace is part of the value.
  - inside quotes, '#' is literal (never a comment).
  - inside DOUBLE quotes, the escape '\\n' becomes a real newline; single-quoted
    values are literal (no escape processing).
  - blank / whitespace-only / full-line-comment ('#' first non-ws) / no-'=' -> null.
  - `KEY=` -> { key: "KEY", value: "" }.
  - value may itself contain '=' (everything after the FIRST '=' kept).

Verification strategy:
  - L1: the deliverable source/spec files exist, the export is present, and the
    agent spec imports from '../utils'.
  - L2: DYNAMIC EXECUTION via the repo's native toolchain (vitest, run with
    `pnpm exec vitest run ...`). To avoid trusting the agent's own spec, we write
    INDEPENDENT driver spec files into the repo's __tests__ directory that import
    `parseEnvLine` from '../utils' and assert the exact required behaviors. A naive
    implementation (splitting on every '=', stripping all '#', ignoring quotes, or
    not decoding '\\n' inside double quotes) makes at least one driver spec fail.
    We also run the agent's delivered spec.
"""

import os
import re
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/vite"
TESTS_DIR = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "__tests__")
UTILS_TS = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "utils.ts")
AGENT_SPEC = os.path.join(TESTS_DIR, "parseEnvLine.spec.ts")

# rel paths (abs paths actually) of driver specs we drop in; filled by _write_spec.
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
    """Verify the parseEnvLine helper and its vitest coverage."""

    REPO_DIR = "/workspace/vite"

    # ------------------------------------------------------------------
    # L1 — deliverables exist / minimally well-formed
    # ------------------------------------------------------------------

    def test_utils_file_exists(self):
        """utils.ts (the modify target) must exist."""
        assert os.path.isfile(UTILS_TS), f"missing {UTILS_TS}"

    def test_parse_env_line_is_exported(self):
        """utils.ts must export a function named parseEnvLine."""
        with open(UTILS_TS) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+parseEnvLine\b", src
        ), "parseEnvLine not exported as a function from utils.ts"

    def test_agent_spec_file_exists(self):
        """The dedicated spec file must be delivered."""
        assert os.path.isfile(AGENT_SPEC), f"missing {AGENT_SPEC}"

    def test_agent_spec_imports_from_utils(self):
        """The spec must import parseEnvLine from ../utils (not redefine it)."""
        with open(AGENT_SPEC) as f:
            spec = f.read()
        assert "parseEnvLine" in spec, "spec does not reference parseEnvLine"
        assert re.search(
            r"from\s+['\"]\.\./utils['\"]", spec
        ), "spec must import from '../utils'"

    # ------------------------------------------------------------------
    # L2 — dynamic execution against INDEPENDENT driver specs.
    # Each test drops a focused spec that imports the real implementation
    # and asserts the precise required behavior via vitest.
    # ------------------------------------------------------------------

    def test_full_truth_table(self):
        """Every row of the requirement's Expected-Functionality table must hold."""
        rel = _write_spec(
            "zz_driver_envline_table",
            r"""
            import { describe, expect, test } from 'vitest'
            import { parseEnvLine } from '../utils'

            describe('parseEnvLine truth table', () => {
              test('table', () => {
                expect(parseEnvLine('FOO=bar')).toEqual({ key: 'FOO', value: 'bar' })
                expect(parseEnvLine('  FOO = bar ')).toEqual({ key: 'FOO', value: 'bar' })
                expect(parseEnvLine('FOO="bar baz"')).toEqual({ key: 'FOO', value: 'bar baz' })
                expect(parseEnvLine('FOO=bar # comment')).toEqual({ key: 'FOO', value: 'bar' })
                expect(parseEnvLine('FOO="a # b"')).toEqual({ key: 'FOO', value: 'a # b' })
                expect(parseEnvLine('FOO="line\\nbreak"')).toEqual({ key: 'FOO', value: 'line\nbreak' })
                expect(parseEnvLine('FOO=')).toEqual({ key: 'FOO', value: '' })
                expect(parseEnvLine('# whole line')).toBeNull()
                expect(parseEnvLine('noequals')).toBeNull()
              })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "driver truth-table spec failed (vitest nonzero)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_key_and_value_trimming(self):
        """Key is trimmed; raw value surrounding whitespace is trimmed before processing."""
        rel = _write_spec(
            "zz_driver_envline_trim",
            r"""
            import { expect, test } from 'vitest'
            import { parseEnvLine } from '../utils'

            test('trimming', () => {
              expect(parseEnvLine('  KEY = value')).toEqual({ key: 'KEY', value: 'value' })
              expect(parseEnvLine('KEY=   spaced   ')).toEqual({ key: 'KEY', value: 'spaced' })
              expect(parseEnvLine('\tKEY\t=\tval\t')).toEqual({ key: 'KEY', value: 'val' })
              // a key with internal spacing keeps only surrounding trim
              expect(parseEnvLine('MY_KEY=1')).toEqual({ key: 'MY_KEY', value: '1' })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "key/value trimming wrong\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_empty_and_null_cases(self):
        """Blank / whitespace-only / full-line-comment / no-'=' return null; KEY= -> ''."""
        rel = _write_spec(
            "zz_driver_envline_null",
            r"""
            import { expect, test } from 'vitest'
            import { parseEnvLine } from '../utils'

            test('null and empty', () => {
              expect(parseEnvLine('')).toBeNull()
              expect(parseEnvLine('    ')).toBeNull()
              expect(parseEnvLine('\t  \t')).toBeNull()
              expect(parseEnvLine('# a full comment')).toBeNull()
              expect(parseEnvLine('   # indented comment')).toBeNull()
              expect(parseEnvLine('plainword')).toBeNull()
              // empty value is NOT null
              expect(parseEnvLine('KEY=')).toEqual({ key: 'KEY', value: '' })
              expect(parseEnvLine('KEY=   ')).toEqual({ key: 'KEY', value: '' })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "null / empty-value handling wrong\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_first_equals_splits(self):
        """Only the FIRST '=' splits key from value; later '=' stays in the value."""
        rel = _write_spec(
            "zz_driver_envline_firsteq",
            r"""
            import { expect, test } from 'vitest'
            import { parseEnvLine } from '../utils'

            test('first equals splits', () => {
              expect(parseEnvLine('KEY=a=b')).toEqual({ key: 'KEY', value: 'a=b' })
              expect(parseEnvLine('DB_URL=postgres://u:p@h/db?x=1'))
                .toEqual({ key: 'DB_URL', value: 'postgres://u:p@h/db?x=1' })
              expect(parseEnvLine('K====')).toEqual({ key: 'K', value: '===' })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "first-'=' splitting wrong (a naive split('=') impl fails here)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_double_quote_stripping(self):
        """Matching double quotes are stripped; inner text verbatim (no inner trim)."""
        rel = _write_spec(
            "zz_driver_envline_dq",
            r"""
            import { expect, test } from 'vitest'
            import { parseEnvLine } from '../utils'

            test('double quotes', () => {
              expect(parseEnvLine('FOO="bar baz"')).toEqual({ key: 'FOO', value: 'bar baz' })
              // inner whitespace preserved verbatim
              expect(parseEnvLine('FOO="  padded  "')).toEqual({ key: 'FOO', value: '  padded  ' })
              // surrounding whitespace OUTSIDE the quotes is trimmed first
              expect(parseEnvLine('FOO=  "quoted"  ')).toEqual({ key: 'FOO', value: 'quoted' })
              // empty quoted value
              expect(parseEnvLine('FOO=""')).toEqual({ key: 'FOO', value: '' })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "double-quote stripping wrong\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_single_quote_literal(self):
        """Single-quoted values are stripped of quotes and taken literally (no escapes)."""
        rel = _write_spec(
            "zz_driver_envline_sq",
            r"""
            import { expect, test } from 'vitest'
            import { parseEnvLine } from '../utils'

            test('single quotes literal', () => {
              expect(parseEnvLine("FOO='bar baz'")).toEqual({ key: 'FOO', value: 'bar baz' })
              // a '#' inside single quotes is literal, not a comment
              expect(parseEnvLine("FOO='a # b'")).toEqual({ key: 'FOO', value: 'a # b' })
              // backslash-n stays literal in single quotes (NOT a real newline)
              expect(parseEnvLine("FOO='line\\nbreak'")).toEqual({ key: 'FOO', value: 'line\\nbreak' })
              // inner whitespace preserved
              expect(parseEnvLine("FOO='  x  '")).toEqual({ key: 'FOO', value: '  x  ' })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "single-quote literal handling wrong\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_inline_comment_unquoted(self):
        """Unquoted inline comment ' #' is stripped; '#' without leading ws is kept."""
        rel = _write_spec(
            "zz_driver_envline_comment",
            r"""
            import { expect, test } from 'vitest'
            import { parseEnvLine } from '../utils'

            test('inline comments', () => {
              expect(parseEnvLine('FOO=bar # comment')).toEqual({ key: 'FOO', value: 'bar' })
              // remaining value right-trimmed after comment removal
              expect(parseEnvLine('FOO=bar   # trailing')).toEqual({ key: 'FOO', value: 'bar' })
              // '#' with NO preceding whitespace is part of the value
              expect(parseEnvLine('FOO=ab#cd')).toEqual({ key: 'FOO', value: 'ab#cd' })
              expect(parseEnvLine('FOO=#anchor')).toEqual({ key: 'FOO', value: '#anchor' })
              // tab before '#' also counts as whitespace -> comment
              expect(parseEnvLine('FOO=val\t# note')).toEqual({ key: 'FOO', value: 'val' })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "inline-comment handling wrong (naive '#'-strip impl fails here)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_hash_literal_in_quotes(self):
        """A '#' inside quotes is literal even with leading whitespace inside."""
        rel = _write_spec(
            "zz_driver_envline_hashquote",
            r"""
            import { expect, test } from 'vitest'
            import { parseEnvLine } from '../utils'

            test('hash inside quotes is literal', () => {
              expect(parseEnvLine('FOO="a # b"')).toEqual({ key: 'FOO', value: 'a # b' })
              expect(parseEnvLine('FOO="#leading"')).toEqual({ key: 'FOO', value: '#leading' })
              expect(parseEnvLine("FOO='c # d'")).toEqual({ key: 'FOO', value: 'c # d' })
              // trailing text after a closing quote is NOT re-parsed as a quoted value:
              // the whole value '"x" # y' has its comment after the quote stripped only
              // if impl supports it; we assert the documented quoted-then-comment is safe
              expect(parseEnvLine('FOO="x # y"')).toEqual({ key: 'FOO', value: 'x # y' })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "'#'-inside-quotes handling wrong\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_double_quote_newline_escape(self):
        """Inside double quotes, '\\n' decodes to a real newline; single quotes do not."""
        rel = _write_spec(
            "zz_driver_envline_escape",
            r"""
            import { expect, test } from 'vitest'
            import { parseEnvLine } from '../utils'

            test('newline escape in double quotes', () => {
              const r = parseEnvLine('FOO="line\\nbreak"')
              expect(r).not.toBeNull()
              expect(r!.value).toBe('line\nbreak')
              expect(r!.value).toContain('\n')          // a real newline char
              expect(r!.value.length).toBe('linebreak'.length + 1)
              // multiple escapes
              expect(parseEnvLine('FOO="a\\nb\\nc"')).toEqual({ key: 'FOO', value: 'a\nb\nc' })
              // single-quoted: backslash-n stays literal (two chars)
              const s = parseEnvLine("FOO='line\\nbreak'")
              expect(s!.value).toBe('line\\nbreak')
              expect(s!.value).not.toContain('\n')
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "double-quote '\\n' escape decoding wrong (naive impl fails here)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_return_shape_and_no_extra_keys(self):
        """Result is exactly {key, value} (string fields) or null; no extra props."""
        rel = _write_spec(
            "zz_driver_envline_shape",
            r"""
            import { expect, test } from 'vitest'
            import { parseEnvLine } from '../utils'

            test('return shape', () => {
              const r = parseEnvLine('FOO=bar')
              expect(r).not.toBeNull()
              expect(Object.keys(r!).sort()).toEqual(['key', 'value'])
              expect(typeof r!.key).toBe('string')
              expect(typeof r!.value).toBe('string')
              // null path really returns null (not undefined / {})
              expect(parseEnvLine('# x')).toBeNull()
              expect(parseEnvLine('noeq')).toBeNull()
              // fresh object each call
              expect(parseEnvLine('A=1')).not.toBe(parseEnvLine('A=1'))
              expect(parseEnvLine('A=1')).toEqual(parseEnvLine('A=1'))
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "return shape / extra-key check failed\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_agent_delivered_spec_passes(self):
        """The agent's own delivered spec must pass under native vitest."""
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        rel = os.path.relpath(AGENT_SPEC, REPO_DIR)
        res = _vitest(rel)
        assert res.returncode == 0, (
            "agent's parseEnvLine.spec.ts does not pass\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
        # it must actually contain real assertions, not be an empty/skipped file
        combined = (res.stdout + res.stderr).lower()
        assert "no test" not in combined, "agent spec contains no tests"
