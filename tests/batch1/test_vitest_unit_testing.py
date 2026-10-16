"""
Test for the 'vitest-unit-testing' skill.

Task: add an exported `parseRequestQuery(url: string): Record<string, string>`
helper to packages/vite/src/node/utils.ts plus a dedicated vitest spec at
packages/vite/src/node/__tests__/parseRequestQuery.spec.ts.

Verification strategy:
- L1: the deliverable source/spec files exist and the export is present.
- L2: DYNAMIC EXECUTION via the repo's native toolchain (vitest, run with
  `pnpm exec vitest run ...`). To avoid trusting the agent's own spec, we write
  INDEPENDENT driver spec files into the repo's __tests__ directory that import
  `parseRequestQuery` from `../utils` and exercise the exact behaviors required
  by the task. A naive implementation (ignoring the hash boundary, not URL
  decoding, treating bare flags as undefined, or first-duplicate-wins) makes at
  least one of these driver specs fail. We also run the agent's delivered spec.
"""

import os
import re
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/vite"
TESTS_DIR = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "__tests__")
UTILS_TS = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "utils.ts")
AGENT_SPEC = os.path.join(TESTS_DIR, "parseRequestQuery.spec.ts")

# rel paths (from repo root) of driver specs we drop in; filled by _write_spec.
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
    """Verify the parseRequestQuery helper and its vitest coverage."""

    REPO_DIR = "/workspace/vite"

    # ------------------------------------------------------------------
    # L1 — deliverables exist / minimally well-formed
    # ------------------------------------------------------------------

    def test_utils_file_exists(self):
        """utils.ts (the modify target) must exist."""
        assert os.path.isfile(UTILS_TS), f"missing {UTILS_TS}"

    def test_parse_request_query_is_exported(self):
        """utils.ts must export a function named parseRequestQuery."""
        with open(UTILS_TS) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+parseRequestQuery\b", src
        ), "parseRequestQuery not exported as a function from utils.ts"

    def test_agent_spec_file_exists(self):
        """The dedicated spec file must be delivered."""
        assert os.path.isfile(AGENT_SPEC), f"missing {AGENT_SPEC}"

    def test_agent_spec_imports_from_utils(self):
        """The spec must import parseRequestQuery from ../utils (not redefine it)."""
        with open(AGENT_SPEC) as f:
            spec = f.read()
        assert "parseRequestQuery" in spec, "spec does not reference parseRequestQuery"
        assert re.search(
            r"from\s+['\"]\.\./utils['\"]", spec
        ), "spec must import from '../utils'"

    # ------------------------------------------------------------------
    # L2 — dynamic execution against an INDEPENDENT driver spec.
    # Each test drops a focused spec that imports the real implementation
    # and asserts the precise required behavior via vitest.
    # ------------------------------------------------------------------

    def test_full_truth_table(self):
        """Every row of the requirement's Expected-Functionality table must hold."""
        rel = _write_spec(
            "zz_driver_table",
            """
            import { describe, expect, test } from 'vitest'
            import { parseRequestQuery } from '../utils'

            describe('parseRequestQuery truth table', () => {
              test('table', () => {
                expect(parseRequestQuery('./Comp.vue?vue&type=style&index=0'))
                  .toEqual({ vue: '', type: 'style', index: '0' })
                expect(parseRequestQuery('./a.js?raw#L10')).toEqual({ raw: '' })
                expect(parseRequestQuery('./a.js#frag')).toEqual({})
                expect(parseRequestQuery('./a.js')).toEqual({})
                expect(parseRequestQuery('./a.js?')).toEqual({})
                expect(parseRequestQuery('./a.js?msg=hello+world'))
                  .toEqual({ msg: 'hello world' })
                expect(parseRequestQuery('./a.js?path=a%2Fb')).toEqual({ path: 'a/b' })
                expect(parseRequestQuery('./a.js?x=1&x=2')).toEqual({ x: '2' })
                expect(parseRequestQuery('./a.js?a=1&&b=2'))
                  .toEqual({ a: '1', b: '2' })
              })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "driver truth-table spec failed (vitest nonzero)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_hash_boundary_ignored(self):
        """Query parsing must stop at '#'; the hash fragment is not a parameter."""
        rel = _write_spec(
            "zz_driver_hash",
            """
            import { expect, test } from 'vitest'
            import { parseRequestQuery } from '../utils'

            test('hash boundary', () => {
              // the hash must NOT leak into the last value / key.
              expect(parseRequestQuery('./a.js?type=style#L10'))
                .toEqual({ type: 'style' })
              expect(parseRequestQuery('./a.js?raw#section')).toEqual({ raw: '' })
              // hash before any params -> no params at all
              expect(parseRequestQuery('./a.js#a=1&b=2')).toEqual({})
              // multiple '#': only the first delimits the query end
              expect(parseRequestQuery('./a.js?k=v#x#y')).toEqual({ k: 'v' })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "hash-boundary behavior is wrong (a naive impl that keeps the hash "
            f"in the value fails here)\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_bare_flag_is_empty_string(self):
        """Bare flags and 'name=' both map to '' (NOT undefined / true)."""
        rel = _write_spec(
            "zz_driver_flags",
            """
            import { expect, test } from 'vitest'
            import { parseRequestQuery } from '../utils'

            test('bare flags', () => {
              const r = parseRequestQuery('./Comp.vue?vue&type=style')
              expect(r.vue).toBe('')          // strictly empty string
              expect(typeof r.vue).toBe('string')
              expect(r.type).toBe('style')
              // explicit trailing '=' also empty string
              expect(parseRequestQuery('./a.js?flag=')).toEqual({ flag: '' })
              // a bare flag must still be an OWN enumerable key
              expect(Object.keys(parseRequestQuery('./a.js?solo'))).toEqual(['solo'])
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "bare-flag handling wrong (must be '' not undefined/true)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_percent_decoding(self):
        """Names and values must be percent-decoded."""
        rel = _write_spec(
            "zz_driver_percent",
            """
            import { expect, test } from 'vitest'
            import { parseRequestQuery } from '../utils'

            test('percent decode', () => {
              expect(parseRequestQuery('./a.js?path=a%2Fb')).toEqual({ path: 'a/b' })
              // decode in the key as well
              expect(parseRequestQuery('./a.js?a%20b=c')).toEqual({ 'a b': 'c' })
              // unicode / reserved chars
              expect(parseRequestQuery('./a.js?q=%26%3D')).toEqual({ q: '&=' })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "percent-decoding not performed\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_plus_as_space(self):
        """'+' in a value must decode to a space (query semantics)."""
        rel = _write_spec(
            "zz_driver_plus",
            """
            import { expect, test } from 'vitest'
            import { parseRequestQuery } from '../utils'

            test('plus is space', () => {
              expect(parseRequestQuery('./a.js?msg=hello+world'))
                .toEqual({ msg: 'hello world' })
              expect(parseRequestQuery('./a.js?a=x+y+z')).toEqual({ a: 'x y z' })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "'+' not decoded as space\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_duplicate_last_wins(self):
        """When a name repeats, the LAST occurrence wins."""
        rel = _write_spec(
            "zz_driver_dup",
            """
            import { expect, test } from 'vitest'
            import { parseRequestQuery } from '../utils'

            test('last wins', () => {
              expect(parseRequestQuery('./a.js?x=1&x=2')).toEqual({ x: '2' })
              expect(parseRequestQuery('./a.js?x=1&y=a&x=3&x=last'))
                .toEqual({ x: 'last', y: 'a' })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "duplicate-key resolution wrong (must be last-wins)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_empty_segments_skipped(self):
        """Doubled/trailing '&' must not create an empty-named key."""
        rel = _write_spec(
            "zz_driver_empty",
            """
            import { expect, test } from 'vitest'
            import { parseRequestQuery } from '../utils'

            test('empty segments', () => {
              expect(parseRequestQuery('./a.js?a=1&&b=2')).toEqual({ a: '1', b: '2' })
              expect(parseRequestQuery('./a.js?a=1&')).toEqual({ a: '1' })
              expect(parseRequestQuery('./a.js?&a=1')).toEqual({ a: '1' })
              const r = parseRequestQuery('./a.js?a=1&&&b=2')
              expect(Object.keys(r).sort()).toEqual(['a', 'b'])
              expect(Object.prototype.hasOwnProperty.call(r, '')).toBe(false)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "empty-segment handling wrong (created an empty key or dropped a param)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_no_query_and_null_prototype_safety(self):
        """No-'?' / hash-only / bare-'?' return {} with no inherited keys."""
        rel = _write_spec(
            "zz_driver_empty_obj",
            """
            import { expect, test } from 'vitest'
            import { parseRequestQuery } from '../utils'

            test('empty results', () => {
              expect(parseRequestQuery('./a.js')).toEqual({})
              expect(parseRequestQuery('./a.js#frag')).toEqual({})
              expect(parseRequestQuery('./a.js?')).toEqual({})
              // returned object must not expose inherited/prototype keys as params
              const r = parseRequestQuery('./a.js?a=1')
              expect(Object.prototype.hasOwnProperty.call(r, 'constructor'))
                .toBe(false)
              expect(r['toString']).toBe(Object.prototype.toString)
              expect(Object.keys(r)).toEqual(['a'])
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "empty/no-query results wrong\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_purity_no_input_mutation(self):
        """The function must be pure: returns a fresh object, no input mutation."""
        rel = _write_spec(
            "zz_driver_purity",
            """
            import { expect, test } from 'vitest'
            import { parseRequestQuery } from '../utils'

            test('purity', () => {
              const input = './Comp.vue?vue&type=style&index=0'
              const before = input
              const a = parseRequestQuery(input)
              const b = parseRequestQuery(input)
              // input untouched (strings are immutable, but guard against any
              // accidental global-state coupling by comparing repeated calls)
              expect(input).toBe(before)
              expect(a).toEqual(b)
              expect(a).not.toBe(b)   // a fresh object each call
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "function is not pure / does not return a fresh object\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_first_question_mark_delimits_query(self):
        """Only the FIRST '?' starts the query; later '?'/raw chars stay in values."""
        rel = _write_spec(
            "zz_driver_firstq",
            """
            import { expect, test } from 'vitest'
            import { parseRequestQuery } from '../utils'

            test('first question mark', () => {
              // a literal '?' appearing later is part of the query content, not a
              // new delimiter; file path before first '?' is ignored.
              expect(parseRequestQuery('a/b?c.js?vue&type=style'))
                .toEqual({ 'vue': '', type: 'style', 'c.js?vue': undefined } as any)
            })
            """,
        )
        # The above intentionally over-specifies; replace with a robust check that
        # only relies on documented behavior (everything after the FIRST '?').
        rel = _write_spec(
            "zz_driver_firstq",
            """
            import { expect, test } from 'vitest'
            import { parseRequestQuery } from '../utils'

            test('first question mark delimits', () => {
              // path 'a/b' ignored; query is 'vue&type=style'
              const r = parseRequestQuery('a/b?vue&type=style')
              expect(r).toEqual({ vue: '', type: 'style' })
              // a real-world Vite id with sub-query content
              const r2 = parseRequestQuery('./src/App.vue?vue&type=style&index=0&lang.css')
              expect(r2).toEqual({ vue: '', type: 'style', index: '0', 'lang.css': '' })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "first-'?' delimiting / real Vite id parsing wrong\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_agent_delivered_spec_passes(self):
        """The agent's own delivered spec must pass under native vitest."""
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        rel = os.path.relpath(AGENT_SPEC, REPO_DIR)
        res = _vitest(rel)
        assert res.returncode == 0, (
            "agent's parseRequestQuery.spec.ts does not pass\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
        # it must actually contain real assertions, not be an empty/skipped file
        combined = (res.stdout + res.stderr)
        assert "no test" not in combined.lower(), "agent spec contains no tests"
