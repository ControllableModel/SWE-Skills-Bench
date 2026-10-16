"""Benchmark verification for skill: jest-advanced-patterns (variant ext9).

Task: Add a colon-style route **path matcher** to the React monorepo's
``shared`` package (``packages/shared/createPathMatcher.js``) plus a
deterministic Jest suite
(``packages/shared/__tests__/createPathMatcher-test.js``).

The factory ``createPathMatcher(pattern)`` compiles a pattern such as
``'/users/:userId/posts/:postId'`` and returns a matcher object exposing:

  * ``match(path) -> { params } | null``
  * ``paramNames() -> string[]``

Strategy
--------
L1 cases assert the two deliverable files exist, that the implementation
exposes a default export, and the hard structural constraint that the matcher
module imports/requires no other module.

L2 cases independently EXERCISE the real matcher rather than trusting the
agent's own test file. Each L2 method writes ITS OWN focused Jest probe spec
into ``packages/shared/__tests__/`` and runs only that one spec through the
repo's native Jest CLI (``yarn test <path>`` -> ``node scripts/jest/jest-cli.js
<path>``, which forwards the path as a testPathPattern). Each probe deep-checks
exactly ONE behavior from the requirement doc:

  * single-parameter capture returns the raw segment value
  * segment-count mismatch (too few / too many) -> null
  * literal-segment mismatch -> null
  * no-parameter pattern yields ``params: {}`` and trailing slash -> null
  * trailing slash on a parameterized path -> null (segment count differs)
  * empty parameter segment -> null
  * multi-parameter capture maps every name to its raw value
  * paramNames() preserves declaration order (and is [] when none)
  * captured values are NOT URL-decoded (raw text)
  * factory throws TypeError when pattern is not a string
  * factory throws Error when a parameter name is duplicated

A naive/stub implementation (e.g. one that ignores segment count, hardcodes a
match, decodes values, or skips validation) fails the specific probe it got
wrong. We also confirm the agent's own suite runs green via the exact
Acceptance-Criteria command and that it contains multiple independent cases.

Module resolution note: this repo resolves ``shared/<name>`` via Jest haste
(``roots`` includes ``<rootDir>/packages``), so probes ``require``
``'shared/createPathMatcher'`` exactly like the repo's own shared tests.
"""

import os
import re
import subprocess
import textwrap

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies  # noqa: F401
except Exception:  # pragma: no cover - utils may be absent locally
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/react"

SRC_REL = "packages/shared/createPathMatcher.js"
AGENT_TEST_REL = "packages/shared/__tests__/createPathMatcher-test.js"

# Each probe is written under __tests__ (so the repo's testRegex matches it) and
# is removed after the run. Unique names avoid cross-test collisions.
PROBE_DIR_REL = "packages/shared/__tests__"
PROBE_PREFIX = "createPathMatcher-probe-"


def _src_path():
    return os.path.join(REPO_DIR, SRC_REL)


def _agent_test_path():
    return os.path.join(REPO_DIR, AGENT_TEST_REL)


def _probe_rel(name):
    return os.path.join(PROBE_DIR_REL, PROBE_PREFIX + name + ".bench-test.js")


def _probe_abs(name):
    return os.path.join(REPO_DIR, _probe_rel(name))


def _read_src():
    with open(_src_path()) as fh:
        return fh.read()


def _yarn_test(path_rel, timeout=300):
    """Run the repo's native Jest CLI scoped to a single test file.

    ``yarn test <path>`` invokes ``node ./scripts/jest/jest-cli.js <path>``;
    the trailing path is forwarded to Jest as a testPathPattern so only that
    one spec executes.
    """
    return subprocess.run(
        ["yarn", "test", path_rel],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _jest_passed(result):
    """Require real test execution plus an explicit green summary."""
    out = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.returncode != 0:
        return False, out
    if re.search(r"No tests found", out):
        return False, out
    if re.search(r"Tests:\s+.*\bfailed", out):
        return False, out
    if not re.search(r"Tests:\s+\d+ passed", out) and not re.search(r"PASS\b", out):
        return False, out
    return True, out


# Shared JS preamble: a tiny helper to load the matcher factory. The matcher is
# pure/synchronous, so no timers, network, or randomness are ever involved.
_PREAMBLE = """\
'use strict';

function load() {
  return require('shared/createPathMatcher').default;
}
"""


def _make_probe(body):
    """Wrap a single-behavior ``it(...)`` body in the shared preamble."""
    return _PREAMBLE + "\n" + textwrap.dedent(body) + "\n"


def _run_probe(name, body, timeout=300):
    """Write a one-behavior probe spec, run it via native Jest, clean up."""
    rel = _probe_rel(name)
    abs_path = _probe_abs(name)
    with open(abs_path, "w") as fh:
        fh.write(_make_probe(body))
    try:
        result = _yarn_test(rel, timeout=timeout)
    finally:
        try:
            os.remove(abs_path)
        except OSError:
            pass
    return result


@pytest.fixture(scope="module", autouse=True)
def _deps():
    """Ensure JS toolchain deps are present, and sweep stray probe files."""
    node_modules = os.path.join(REPO_DIR, "node_modules")
    jest_marker = os.path.join(node_modules, "chalk")
    if not os.path.isdir(jest_marker):
        try:
            subprocess.run(
                ["yarn", "install", "--frozen-lockfile"],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=1800,
            )
        except Exception:
            pass
        if not os.path.isdir(jest_marker) and ensure_npm_dependencies is not None:
            try:
                ensure_npm_dependencies(REPO_DIR)
            except Exception:
                pass
    yield
    probe_dir = os.path.join(REPO_DIR, PROBE_DIR_REL)
    try:
        for fname in os.listdir(probe_dir):
            if fname.startswith(PROBE_PREFIX):
                try:
                    os.remove(os.path.join(probe_dir, fname))
                except OSError:
                    pass
    except OSError:
        pass


class TestJestAdvancedPatterns:
    REPO_DIR = REPO_DIR

    # -----------------------------------------------------------------------
    # L1 — deliverables exist and respect the structural constraints.
    # -----------------------------------------------------------------------
    def test_matcher_source_exists(self):
        """L1: the path-matcher module file exists and is non-empty."""
        path = _src_path()
        assert os.path.isfile(path), f"missing deliverable: {SRC_REL}"
        assert os.path.getsize(path) > 0, "matcher source is empty"

    def test_agent_test_file_exists(self):
        """L1: the agent's Jest test suite file exists and is non-empty."""
        path = _agent_test_path()
        assert os.path.isfile(path), f"missing deliverable: {AGENT_TEST_REL}"
        assert os.path.getsize(path) > 0, "agent test file is empty"

    def test_matcher_has_default_export(self):
        """L1: the matcher exposes a default export (the factory)."""
        src = _read_src()
        assert "export default" in src or "module.exports" in src, (
            "matcher must export the factory by default"
        )

    def test_matcher_imports_no_other_module(self):
        """L1: hard constraint — the module imports/requires no other module."""
        src = _read_src()
        no_block = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
        no_line = re.sub(r"//[^\n]*", "", no_block)
        assert not re.search(r"^\s*import\s", no_line, flags=re.MULTILINE), (
            "matcher must contain no `import` statement"
        )
        assert not re.search(r"\brequire\s*\(", no_line), (
            "matcher must not `require` any other module"
        )

    # -----------------------------------------------------------------------
    # L2 — each behavior gets its OWN independent probe spec run via Jest.
    # -----------------------------------------------------------------------
    def test_single_parameter_capture(self):
        """L2: '/users/:id' against '/users/42' captures the raw value '42'.

        A correct matcher returns ``{ params: { id: '42' } }``; a stub that
        hardcodes empty params or a wrong value fails here.
        """
        result = _run_probe(
            "single-capture",
            """
            it('single parameter captures the raw segment value', () => {
              const m = load()('/users/:id');
              const r = m.match('/users/42');
              expect(r).not.toBeNull();
              expect(r).toEqual({params: {id: '42'}});
              expect(r.params.id).toBe('42');
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"single-capture probe failed:\n{out[-4000:]}"

    def test_segment_count_mismatch_returns_null(self):
        """L2: differing segment counts (too few / too many) -> null.

        '/users/:id' must NOT match '/users' (too few) nor '/users/42/extra'
        (too many). A naive prefix matcher would wrongly accept these.
        """
        result = _run_probe(
            "segment-count",
            """
            it('segment-count mismatch returns null', () => {
              const m = load()('/users/:id');
              expect(m.match('/users')).toBeNull();
              expect(m.match('/users/42/extra')).toBeNull();
              expect(m.match('/users/42')).not.toBeNull();
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"segment-count probe failed:\n{out[-4000:]}"

    def test_literal_segment_must_match(self):
        """L2: a differing literal segment -> null.

        '/users/:id' must reject '/people/42' because the literal 'users'
        differs, even though segment counts agree. A matcher that ignores
        literals would wrongly accept it.
        """
        result = _run_probe(
            "literal-mismatch",
            """
            it('literal segment mismatch returns null', () => {
              const m = load()('/users/:id');
              expect(m.match('/people/42')).toBeNull();
              expect(m.match('/users/42')).not.toBeNull();
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"literal-mismatch probe failed:\n{out[-4000:]}"

    def test_no_parameter_pattern_yields_empty_params(self):
        """L2: '/about' against '/about' -> { params: {} }; '/about/' -> null.

        A pattern with no parameters matches its exact path with an empty params
        object, and the trailing slash variant must not match.
        """
        result = _run_probe(
            "no-params",
            """
            it('no-parameter pattern yields empty params; trailing slash null', () => {
              const m = load()('/about');
              expect(m.match('/about')).toEqual({params: {}});
              expect(m.match('/about/')).toBeNull();
              expect(m.match('/contact')).toBeNull();
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"no-params probe failed:\n{out[-4000:]}"

    def test_trailing_slash_on_param_path_returns_null(self):
        """L2: a trailing slash changes segment count, so it must not match.

        '/users/:id' must reject '/users/42/' (trailing slash introduces an
        extra, empty segment).
        """
        result = _run_probe(
            "trailing-slash",
            """
            it('trailing slash on a parameterized path returns null', () => {
              const m = load()('/users/:id');
              expect(m.match('/users/42/')).toBeNull();
              expect(m.match('/users/42')).toEqual({params: {id: '42'}});
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"trailing-slash probe failed:\n{out[-4000:]}"

    def test_empty_parameter_segment_returns_null(self):
        """L2: an empty parameter segment -> null.

        '/users/:id' against '/users/' must return null because the parameter
        segment would be empty (segment counts also differ here).
        """
        result = _run_probe(
            "empty-param",
            """
            it('empty parameter segment returns null', () => {
              const m = load()('/users/:id');
              expect(m.match('/users/')).toBeNull();
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"empty-param probe failed:\n{out[-4000:]}"

    def test_multi_parameter_capture(self):
        """L2: multi-parameter pattern maps every name to its raw segment.

        '/users/:userId/posts/:postId' against '/users/7/posts/99' returns
        ``{ params: { userId: '7', postId: '99' } }`` with literals matched.
        """
        result = _run_probe(
            "multi-capture",
            """
            it('multi-parameter capture maps each name to its raw value', () => {
              const m = load()('/users/:userId/posts/:postId');
              const r = m.match('/users/7/posts/99');
              expect(r).toEqual({params: {userId: '7', postId: '99'}});
              expect(m.match('/users/7/comments/99')).toBeNull();
              expect(m.match('/users/7/posts')).toBeNull();
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"multi-capture probe failed:\n{out[-4000:]}"

    def test_param_names_ordering(self):
        """L2: paramNames() returns names in declaration order; [] when none.

        Order must follow the pattern left-to-right, independent of any sorting.
        """
        result = _run_probe(
            "param-names",
            """
            it('paramNames preserves declaration order', () => {
              const m = load()('/users/:userId/posts/:postId');
              expect(m.paramNames()).toEqual(['userId', 'postId']);
              // a pattern whose names would sort differently than declared
              const m2 = load()('/:zeta/:alpha');
              expect(m2.paramNames()).toEqual(['zeta', 'alpha']);
              const m3 = load()('/about');
              expect(m3.paramNames()).toEqual([]);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"param-names probe failed:\n{out[-4000:]}"

    def test_captured_values_are_not_decoded(self):
        """L2: captured parameter values are the RAW segment text (no decoding).

        '/files/:name' against '/files/a%2Fb' must capture the literal
        'a%2Fb', not a URL-decoded 'a/b'. A matcher that decodeURIComponent's
        the value fails this probe.
        """
        result = _run_probe(
            "no-decode",
            """
            it('captured values are raw (not URL-decoded)', () => {
              const m = load()('/files/:name');
              const r = m.match('/files/a%2Fb');
              expect(r).not.toBeNull();
              expect(r.params.name).toBe('a%2Fb');
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"no-decode probe failed:\n{out[-4000:]}"

    def test_factory_throws_typeerror_for_non_string_pattern(self):
        """L2: the factory throws a TypeError when pattern is not a string.

        undefined, a number, and an object must each cause createPathMatcher to
        throw a TypeError at construction time.
        """
        result = _run_probe(
            "typeerror",
            """
            it('factory throws TypeError for a non-string pattern', () => {
              const factory = load();
              expect(() => factory(undefined)).toThrow(TypeError);
              expect(() => factory(123)).toThrow(TypeError);
              expect(() => factory({})).toThrow(TypeError);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"TypeError-guard probe failed:\n{out[-4000:]}"

    def test_factory_throws_on_duplicate_param_name(self):
        """L2: a pattern declaring the same parameter name twice throws an Error.

        '/users/:id/items/:id' must throw at construction. A matcher that
        silently overwrites the duplicate fails this probe.
        """
        result = _run_probe(
            "duplicate-name",
            """
            it('factory throws Error on duplicate parameter name', () => {
              const factory = load();
              expect(() => factory('/users/:id/items/:id')).toThrow(Error);
              // a non-duplicate multi-param pattern must NOT throw
              expect(() => factory('/users/:id/items/:itemId')).not.toThrow();
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"duplicate-name probe failed:\n{out[-4000:]}"

    # -----------------------------------------------------------------------
    # L2 — the agent's own suite must pass via the spec'd command.
    # -----------------------------------------------------------------------
    def test_agent_suite_passes(self):
        """L2: the agent's own Jest suite passes via the Acceptance command.

        Mirrors the Acceptance Criteria command exactly:
        ``yarn test packages/shared/__tests__/createPathMatcher-test.js``.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        ok, out = _jest_passed(result)
        assert ok, f"agent suite did not pass green:\n{out[-4000:]}"

    def test_agent_suite_has_multiple_independent_cases(self):
        """L2: the agent suite must contain several independent passing cases.

        The requirement mandates independent cases for every behavior, so a
        single trivial test would not satisfy it; require a multi-case green run.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        out = (result.stdout or "") + "\n" + (result.stderr or "")
        assert result.returncode == 0, f"agent suite nonzero rc:\n{out[-3000:]}"
        m = re.search(r"Tests:\s+(\d+) passed", out)
        assert m is not None, f"no passing summary in agent run:\n{out[-3000:]}"
        assert int(m.group(1)) >= 5, (
            f"agent suite should have multiple cases, saw {m.group(1)}"
        )
