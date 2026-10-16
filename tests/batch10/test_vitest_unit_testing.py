"""
Test for the 'vitest-unit-testing' skill (variant ext10).

Task: add an exported `matchGlob(pattern: string, path: string): boolean`
helper to packages/vite/src/node/utils.ts plus a dedicated vitest spec at
packages/vite/src/node/__tests__/matchGlob.spec.ts. The matcher implements a
simplified, anchored glob grammar over forward-slash paths:
  - `?` matches one non-`/` char
  - `*` matches zero+ non-`/` chars (single segment)
  - `**` crosses `/`; `**/` may match zero segments
  - `[abc]` / `[a-z]` / `[!abc]` character classes (never matching `/`)
  - all other chars (incl. regex specials `.`, `+`, `(`, ...) are literal
  - the WHOLE path must be consumed (full, anchored match)

Verification strategy:
- L1: the deliverable source/spec files exist and the export + spec wiring
  (import from '../utils', table-driven mechanism, >=12 assertions) are present.
- L2: DYNAMIC EXECUTION via the repo's native toolchain (vitest, run with
  `pnpm exec vitest run ...`). To avoid trusting the agent's own spec, we write
  INDEPENDENT driver spec files into the repo's __tests__ directory that import
  `matchGlob` from `../utils` and exercise the precise required behaviors. A
  naive implementation (translating `*` to `.*`, not anchoring, not escaping
  regex-special literals, or letting `*`/`[...]` cross `/`) makes at least one
  driver spec fail. We also run the agent's own delivered spec.
"""

import os
import re
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/vite"
TESTS_DIR = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "__tests__")
UTILS_TS = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "utils.ts")
AGENT_SPEC = os.path.join(TESTS_DIR, "matchGlob.spec.ts")

# abs paths of driver specs we drop in; filled by _write_spec, removed at teardown.
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
    """Verify the matchGlob helper and its vitest coverage."""

    REPO_DIR = "/workspace/vite"

    # ------------------------------------------------------------------
    # L1 — deliverables exist / minimally well-formed
    # ------------------------------------------------------------------

    def test_utils_file_exists(self):
        """utils.ts (the modify target) must exist."""
        assert os.path.isfile(UTILS_TS), f"missing {UTILS_TS}"

    def test_match_glob_is_exported(self):
        """utils.ts must export a function named matchGlob."""
        with open(UTILS_TS) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+matchGlob\b", src
        ), "matchGlob not exported as a function from utils.ts"

    def test_agent_spec_file_exists(self):
        """The dedicated spec file must be delivered."""
        assert os.path.isfile(AGENT_SPEC), f"missing {AGENT_SPEC}"

    def test_agent_spec_imports_from_utils(self):
        """The spec must import matchGlob from ../utils (not redefine it)."""
        with open(AGENT_SPEC) as f:
            spec = f.read()
        assert "matchGlob" in spec, "spec does not reference matchGlob"
        assert re.search(
            r"from\s+['\"]\.\./utils['\"]", spec
        ), "spec must import from '../utils'"

    def test_agent_spec_is_table_driven_and_dense(self):
        """
        Spec must use a shared table-driven mechanism (test.each / it.each or a
        per-row loop over a fixture array) AND carry many assertions, as the
        requirement mandates >=12 assertions exercising the truth table.
        """
        with open(AGENT_SPEC) as f:
            spec = f.read()
        table_driven = bool(
            re.search(r"\b(test|it|describe)\s*\.\s*each\b", spec)
            or re.search(r"\.forEach\s*\(", spec)
            or re.search(r"\bfor\s*\(", spec)
        )
        assert table_driven, (
            "spec does not appear to use a shared table-driven mechanism "
            "(test.each / it.each / forEach / for-loop over a fixture table)"
        )
        n_assert = len(re.findall(r"\bexpect\s*\(", spec))
        assert n_assert >= 12, (
            f"spec has only {n_assert} expect(...) assertions; "
            "requirement asks for at least 12"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic execution against INDEPENDENT driver specs.
    # Each test drops a focused spec importing the real implementation and
    # asserts a precise required behavior via the repo's native vitest.
    # ------------------------------------------------------------------

    def test_full_truth_table(self):
        """Every row of the requirement's Expected-Functionality table must hold."""
        rel = _write_spec(
            "zz_driver_glob_table",
            """
            import { describe, expect, test } from 'vitest'
            import { matchGlob } from '../utils'

            describe('matchGlob truth table', () => {
              test('table', () => {
                expect(matchGlob('*.ts', 'index.ts')).toBe(true)
                expect(matchGlob('*.ts', 'a/b.ts')).toBe(false)
                expect(matchGlob('src/**/*.ts', 'src/a/b/c.ts')).toBe(true)
                expect(matchGlob('src/**/*.ts', 'src/a.ts')).toBe(true)
                expect(matchGlob('**/a.js', 'a.js')).toBe(true)
                expect(matchGlob('file.?s', 'file.ts')).toBe(true)
                expect(matchGlob('[abc].ts', 'b.ts')).toBe(true)
                expect(matchGlob('[!abc].ts', 'b.ts')).toBe(false)
                expect(matchGlob('a.ts', 'axts')).toBe(false)
              })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "driver truth-table spec failed (vitest nonzero)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_star_does_not_cross_slash(self):
        """`*` (single star) must NOT cross a '/'; it stays in one segment."""
        rel = _write_spec(
            "zz_driver_glob_star",
            """
            import { expect, test } from 'vitest'
            import { matchGlob } from '../utils'

            test('single star does not cross slash', () => {
              expect(matchGlob('src/*.ts', 'src/a/b.ts')).toBe(false)
              expect(matchGlob('src/*.ts', 'src/a.ts')).toBe(true)
              expect(matchGlob('*', 'a')).toBe(true)
              expect(matchGlob('*', 'a/b')).toBe(false)
              // zero-or-more within a segment
              expect(matchGlob('a*c', 'ac')).toBe(true)
              expect(matchGlob('a*c', 'abbbc')).toBe(true)
              expect(matchGlob('a*c', 'ab/c')).toBe(false)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "single '*' wrongly crosses '/' (a naive '*'->'.*' impl fails here)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_globstar_crosses_slash(self):
        """`**` MUST cross '/', and `**/` may match zero segments."""
        rel = _write_spec(
            "zz_driver_glob_globstar",
            """
            import { expect, test } from 'vitest'
            import { matchGlob } from '../utils'

            test('double star crosses slash', () => {
              expect(matchGlob('src/**/*.ts', 'src/a/b/c.ts')).toBe(true)
              expect(matchGlob('src/**/*.ts', 'src/a.ts')).toBe(true)
              // **/ matches zero segments
              expect(matchGlob('**/a.js', 'a.js')).toBe(true)
              expect(matchGlob('**/a.js', 'x/y/a.js')).toBe(true)
              // ** alone matches everything incl. slashes
              expect(matchGlob('**', 'a/b/c')).toBe(true)
              expect(matchGlob('**', '')).toBe(true)
              // anchored: trailing extension still required
              expect(matchGlob('src/**/*.ts', 'src/a/b/c.js')).toBe(false)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "'**' globstar semantics wrong (must cross '/'; '**/' matches zero segs)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_question_mark_single_non_slash(self):
        """`?` matches exactly one character and never a '/'."""
        rel = _write_spec(
            "zz_driver_glob_qmark",
            """
            import { expect, test } from 'vitest'
            import { matchGlob } from '../utils'

            test('question mark', () => {
              expect(matchGlob('file.?s', 'file.ts')).toBe(true)
              expect(matchGlob('?', 'a')).toBe(true)
              // must match exactly one char, not zero, not two
              expect(matchGlob('?', '')).toBe(false)
              expect(matchGlob('?', 'ab')).toBe(false)
              // ? does not match a slash
              expect(matchGlob('a?b', 'a/b')).toBe(false)
              expect(matchGlob('a?b', 'axb')).toBe(true)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "'?' semantics wrong (must be exactly one non-'/' char)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_character_classes(self):
        """`[abc]`, ranges `[a-z]`, and negation `[!abc]` behave correctly."""
        rel = _write_spec(
            "zz_driver_glob_class",
            """
            import { expect, test } from 'vitest'
            import { matchGlob } from '../utils'

            test('character classes', () => {
              expect(matchGlob('[abc].ts', 'b.ts')).toBe(true)
              expect(matchGlob('[abc].ts', 'd.ts')).toBe(false)
              // range
              expect(matchGlob('[a-z].ts', 'm.ts')).toBe(true)
              expect(matchGlob('[a-z].ts', 'M.ts')).toBe(false)
              // negation
              expect(matchGlob('[!abc].ts', 'b.ts')).toBe(false)
              expect(matchGlob('[!abc].ts', 'z.ts')).toBe(true)
              // a class consumes exactly one char
              expect(matchGlob('[abc]', 'ab')).toBe(false)
              // a class never matches '/'
              expect(matchGlob('[a-z/]', '/')).toBe(false)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "character-class handling wrong (set/range/negation/never-slash)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_negated_class_never_matches_slash(self):
        """A negated class `[!...]` must still NOT match '/' even if '/' not listed."""
        rel = _write_spec(
            "zz_driver_glob_negslash",
            """
            import { expect, test } from 'vitest'
            import { matchGlob } from '../utils'

            test('negated class excludes slash', () => {
              // '/' is not in {a,b,c}, but [!abc] must still not match '/'
              expect(matchGlob('a[!abc]b', 'a/b')).toBe(false)
              expect(matchGlob('a[!abc]b', 'axb')).toBe(true)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "negated class wrongly matched '/' (the never-slash rule was dropped)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_regex_special_chars_are_literal(self):
        """Regex-special chars in the pattern must be matched literally, not as regex."""
        rel = _write_spec(
            "zz_driver_glob_literal",
            """
            import { expect, test } from 'vitest'
            import { matchGlob } from '../utils'

            test('regex specials are literal', () => {
              // '.' is literal: must match a real dot only
              expect(matchGlob('a.ts', 'a.ts')).toBe(true)
              expect(matchGlob('a.ts', 'axts')).toBe(false)
              // '+' literal, not 'one-or-more'
              expect(matchGlob('a+b', 'a+b')).toBe(true)
              expect(matchGlob('a+b', 'aaab')).toBe(false)
              // parens / pipe / dollar / caret as literals
              expect(matchGlob('(x)', '(x)')).toBe(true)
              expect(matchGlob('a|b', 'a|b')).toBe(true)
              expect(matchGlob('a$', 'a$')).toBe(true)
              expect(matchGlob('^a', '^a')).toBe(true)
              // a backslash-free literal must not behave like regex grouping
              expect(matchGlob('(x)', 'x')).toBe(false)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "regex-special chars not escaped to literals (naive impl fails here)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_anchored_full_match(self):
        """The match is anchored: the WHOLE path must be consumed (no partials)."""
        rel = _write_spec(
            "zz_driver_glob_anchor",
            """
            import { expect, test } from 'vitest'
            import { matchGlob } from '../utils'

            test('anchored full match', () => {
              // partial prefix/suffix must NOT match
              expect(matchGlob('a.ts', 'a.tsx')).toBe(false)
              expect(matchGlob('a.ts', 'xa.ts')).toBe(false)
              expect(matchGlob('foo', 'foobar')).toBe(false)
              expect(matchGlob('bar', 'foobar')).toBe(false)
              // exact only
              expect(matchGlob('foo', 'foo')).toBe(true)
              // a non-anchored '*' impl would wrongly accept these:
              expect(matchGlob('src/*.ts', 'asrc/x.ts')).toBe(false)
              expect(matchGlob('*.ts', 'a.ts.bak')).toBe(false)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "match is not anchored (a non-full-match impl accepts partials here)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_empty_pattern_and_literal_dot(self):
        """Empty pattern matches only empty path; literal dot only matches a dot."""
        rel = _write_spec(
            "zz_driver_glob_empty",
            """
            import { expect, test } from 'vitest'
            import { matchGlob } from '../utils'

            test('empty pattern + literal dot', () => {
              expect(matchGlob('', '')).toBe(true)
              expect(matchGlob('', 'a')).toBe(false)
              expect(matchGlob('a.ts', 'a.ts')).toBe(true)
              expect(matchGlob('.', '.')).toBe(true)
              expect(matchGlob('.', 'x')).toBe(false)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "empty-pattern / literal-dot edge cases wrong\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_return_type_is_strict_boolean(self):
        """matchGlob must return a strict boolean, not a truthy/falsy value."""
        rel = _write_spec(
            "zz_driver_glob_bool",
            """
            import { expect, test } from 'vitest'
            import { matchGlob } from '../utils'

            test('strict boolean return', () => {
              const yes = matchGlob('*.ts', 'a.ts')
              const no = matchGlob('*.ts', 'a/b.ts')
              expect(yes).toBe(true)
              expect(no).toBe(false)
              expect(typeof yes).toBe('boolean')
              expect(typeof no).toBe('boolean')
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "matchGlob does not return a strict boolean\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_agent_delivered_spec_passes(self):
        """The agent's own delivered spec must pass under native vitest."""
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        rel = os.path.relpath(AGENT_SPEC, REPO_DIR)
        res = _vitest(rel)
        assert res.returncode == 0, (
            "agent's matchGlob.spec.ts does not pass\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
        combined = (res.stdout + res.stderr).lower()
        assert "no test" not in combined, "agent spec contains no tests"
