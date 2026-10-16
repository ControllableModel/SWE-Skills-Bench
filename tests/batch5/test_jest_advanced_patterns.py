"""Benchmark verification for skill: jest-advanced-patterns (variant ext5).

Task: Add a shallow object-diff utility to the React monorepo's ``shared``
package (``packages/shared/shallowDiff.js``) plus a deterministic Jest suite
(``packages/shared/__tests__/shallowDiff-test.js``).

``shallowDiff(prev, next)`` returns ``{added, removed, changed, unchanged}``
classifying the own-enumerable keys of two plain objects:

  * ``added``     — keys in ``next`` but not in ``prev``.
  * ``removed``   — keys in ``prev`` but not in ``next``.
  * ``changed``   — common keys whose values are NOT the same (``Object.is``).
  * ``unchanged`` — common keys whose values ARE the same (``Object.is``).

with ``Object.is`` semantics (``NaN`` == ``NaN``; ``+0`` != ``-0``), only own
enumerable keys (inherited keys ignored), each array sorted ascending, and a
``TypeError`` for non-object / null inputs.

Strategy
--------
L1 cases assert the two deliverable files exist, are non-empty, and that the
implementation exposes a default export.

L2 cases independently EXERCISE the real utility instead of trusting the agent's
own test file. Each L2 method writes ITS OWN focused Jest probe spec into
``packages/shared/__tests__/`` and runs that single spec through the repo's
native Jest CLI (``yarn test <path>`` -> ``node scripts/jest/jest-cli.js
<path>``, which forwards the path as a testPathPattern). Every probe drives
``shallowDiff`` with fully deterministic plain objects (no timers, network, or
randomness) and deep-validates exactly ONE behavior from the requirement doc:

  * the full structural shape of a mixed diff (added/removed/changed/unchanged)
  * empty-vs-empty -> all four arrays empty
  * identical objects -> all keys in ``unchanged``
  * a value change ``1`` -> ``2`` lands the key in ``changed``
  * ``NaN`` vs ``NaN`` -> ``unchanged`` (Object.is, NOT strict ===)
  * ``+0`` vs ``-0`` -> ``changed`` (Object.is signed-zero)
  * arrays are sorted ascending regardless of insertion order
  * inherited (prototype) keys are excluded
  * no key appears in more than one bucket
  * ``TypeError`` for non-object / null / array? inputs

Because each behavior is its own probe spec and its own pytest method, a
partial / buggy solution (e.g. one that uses strict ``===`` and so mis-buckets
``NaN`` / signed zero, or one that fails to sort, or that leaks inherited keys)
fails the SPECIFIC behavior it got wrong. We also confirm the agent's own suite
runs green via the exact Acceptance-Criteria command.

Module resolution note: this repo resolves ``shared/<name>`` via Jest haste
(``roots: ['<rootDir>/packages', ...]``), so the probe ``require``s
``'shared/shallowDiff'`` exactly like the repo's own shared tests.
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

SRC_REL = "packages/shared/shallowDiff.js"
AGENT_TEST_REL = "packages/shared/__tests__/shallowDiff-test.js"

# Each probe is written under __tests__ (so the repo's testRegex matches it) and
# is removed after the run. Unique names avoid cross-test collisions.
PROBE_DIR_REL = "packages/shared/__tests__"
PROBE_PREFIX = "shallowDiff-probe-"


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


# Shared JS preamble: a tiny loader for the utility under test. No timers,
# network, or randomness — every probe builds plain objects inline.
_PREAMBLE = """\
'use strict';

function diff() {
  return require('shared/shallowDiff').default;
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
    def test_diff_source_exists(self):
        """L1: the shallowDiff module file exists and is non-empty."""
        path = _src_path()
        assert os.path.isfile(path), f"missing deliverable: {SRC_REL}"
        assert os.path.getsize(path) > 0, "shallowDiff source is empty"

    def test_agent_test_file_exists(self):
        """L1: the agent's Jest test suite file exists and is non-empty."""
        path = _agent_test_path()
        assert os.path.isfile(path), f"missing deliverable: {AGENT_TEST_REL}"
        assert os.path.getsize(path) > 0, "agent test file is empty"

    def test_diff_has_default_export(self):
        """L1: the module exposes a default export (the diff function)."""
        src = _read_src()
        assert "export default" in src or "module.exports" in src, (
            "shallowDiff must export the function by default"
        )

    # -----------------------------------------------------------------------
    # L2 — each behavior gets its OWN independent probe spec run via Jest.
    # -----------------------------------------------------------------------
    def test_mixed_diff_full_shape(self):
        """L2: a mixed diff returns the exact {added,removed,changed,unchanged} shape.

        ``shallowDiff({a:1,b:2}, {b:2,c:3})`` must classify ``c`` added, ``a``
        removed, nothing changed, ``b`` unchanged — validated against a captured
        expected snapshot of the WHOLE structure, not a single field.
        """
        result = _run_probe(
            "mixed-shape",
            """
            it('mixed diff returns the full structural shape', () => {
              const shallowDiff = diff();
              const result = shallowDiff({a: 1, b: 2}, {b: 2, c: 3});
              const expected = {
                added: ['c'],
                removed: ['a'],
                changed: [],
                unchanged: ['b'],
              };
              expect(result).toEqual(expected);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"mixed-shape probe failed:\n{out[-4000:]}"

    def test_empty_objects_all_arrays_empty(self):
        """L2: diffing two empty objects yields four empty arrays.

        A naive impl that returns hardcoded buckets would fail this exact-shape
        assertion.
        """
        result = _run_probe(
            "empty",
            """
            it('two empty objects -> all arrays empty', () => {
              const shallowDiff = diff();
              expect(shallowDiff({}, {})).toEqual({
                added: [],
                removed: [],
                changed: [],
                unchanged: [],
              });
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"empty probe failed:\n{out[-4000:]}"

    def test_identical_objects_all_unchanged(self):
        """L2: identical objects place every key in ``unchanged`` (others empty)."""
        result = _run_probe(
            "identical",
            """
            it('identical objects -> every key unchanged', () => {
              const shallowDiff = diff();
              const obj = {x: 1, y: 'a', z: true};
              expect(shallowDiff({x: 1, y: 'a', z: true}, obj)).toEqual({
                added: [],
                removed: [],
                changed: [],
                unchanged: ['x', 'y', 'z'],
              });
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"identical probe failed:\n{out[-4000:]}"

    def test_value_change_lands_in_changed(self):
        """L2: a common key whose value changes 1 -> 2 belongs to ``changed``.

        A stub that always reports ``unchanged`` for shared keys fails here.
        """
        result = _run_probe(
            "changed",
            """
            it('a common key with a changed value -> changed', () => {
              const shallowDiff = diff();
              const result = shallowDiff({a: 1, b: 9}, {a: 2, b: 9});
              expect(result).toEqual({
                added: [],
                removed: [],
                changed: ['a'],
                unchanged: ['b'],
              });
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"changed probe failed:\n{out[-4000:]}"

    def test_nan_is_unchanged_object_is_semantics(self):
        """L2: ``NaN`` in both -> ``unchanged`` (Object.is, not strict ===).

        Discriminative: an implementation that compares with ``===`` would put
        ``n`` in ``changed`` because ``NaN === NaN`` is false; this probe pins
        the correct Object.is behavior.
        """
        result = _run_probe(
            "nan",
            """
            it('NaN vs NaN -> unchanged (Object.is)', () => {
              const shallowDiff = diff();
              const result = shallowDiff({n: NaN, k: 1}, {n: NaN, k: 1});
              expect(result).toEqual({
                added: [],
                removed: [],
                changed: [],
                unchanged: ['k', 'n'],
              });
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"NaN probe failed:\n{out[-4000:]}"

    def test_signed_zero_is_changed_object_is_semantics(self):
        """L2: ``+0`` vs ``-0`` -> ``changed`` (Object.is signed-zero).

        Discriminative: ``+0 === -0`` is true, so a ``===``-based impl would
        wrongly mark it ``unchanged``; Object.is distinguishes them.
        """
        result = _run_probe(
            "signed-zero",
            """
            it('+0 vs -0 -> changed (Object.is signed zero)', () => {
              const shallowDiff = diff();
              const result = shallowDiff({z: +0, k: 1}, {z: -0, k: 1});
              expect(result).toEqual({
                added: [],
                removed: [],
                changed: ['z'],
                unchanged: ['k'],
              });
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"signed-zero probe failed:\n{out[-4000:]}"

    def test_arrays_are_sorted_ascending(self):
        """L2: every output array is sorted ascending regardless of insertion order.

        Keys are inserted in deliberately non-sorted order; the result arrays
        must each be lexicographically ascending.
        """
        result = _run_probe(
            "sorted",
            """
            it('output arrays are sorted ascending regardless of order', () => {
              const shallowDiff = diff();
              const prev = {d: 1, b: 1, z: 1, a: 1};   // a,b shared; d removed
              const next = {b: 2, a: 1, m: 1, c: 1};   // a unchanged; b changed; c,m added
              const result = shallowDiff(prev, next);
              expect(result).toEqual({
                added: ['c', 'm'],
                removed: ['d', 'z'],
                changed: ['b'],
                unchanged: ['a'],
              });
              // explicit sortedness checks (independent of toEqual ordering)
              for (const bucket of ['added', 'removed', 'changed', 'unchanged']) {
                const arr = result[bucket];
                const copy = arr.slice().sort();
                expect(arr).toEqual(copy);
              }
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"sorted probe failed:\n{out[-4000:]}"

    def test_inherited_keys_excluded(self):
        """L2: only own enumerable keys participate; inherited keys are ignored.

        Objects created with a prototype carrying an enumerable key must not
        contribute that key to any bucket.
        """
        result = _run_probe(
            "inherited",
            """
            it('inherited (prototype) keys are excluded', () => {
              const shallowDiff = diff();
              const proto = {inheritedKey: 'p'};
              const prev = Object.create(proto);
              prev.own = 1;
              const next = Object.create(proto);
              next.own = 1;
              const result = shallowDiff(prev, next);
              expect(result).toEqual({
                added: [],
                removed: [],
                changed: [],
                unchanged: ['own'],
              });
              const all = []
                .concat(result.added, result.removed, result.changed, result.unchanged);
              expect(all).not.toContain('inheritedKey');
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"inherited probe failed:\n{out[-4000:]}"

    def test_no_key_in_more_than_one_bucket(self):
        """L2: a key never appears in more than one of the four arrays.

        Over a rich mixed diff, the concatenation of all four buckets must have
        no duplicate keys.
        """
        result = _run_probe(
            "disjoint",
            """
            it('no key appears in more than one bucket', () => {
              const shallowDiff = diff();
              const prev = {a: 1, b: 2, c: 3, d: NaN};
              const next = {a: 1, b: 99, e: 5, d: NaN};
              const result = shallowDiff(prev, next);
              const all = []
                .concat(result.added, result.removed, result.changed, result.unchanged);
              const unique = new Set(all);
              expect(unique.size).toBe(all.length);
              // sanity: every present key is accounted for exactly once
              expect(all.slice().sort()).toEqual(['a', 'b', 'c', 'd', 'e']);
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"disjoint probe failed:\n{out[-4000:]}"

    def test_typeerror_for_non_object_inputs(self):
        """L2: non-object / null inputs throw a ``TypeError``.

        ``null``, a number, a string, and ``undefined`` for either argument must
        each raise a TypeError; a valid object pair must NOT throw.
        """
        result = _run_probe(
            "typeerror",
            """
            it('non-object / null inputs throw TypeError', () => {
              const shallowDiff = diff();
              expect(() => shallowDiff(null, {})).toThrow(TypeError);
              expect(() => shallowDiff({}, null)).toThrow(TypeError);
              expect(() => shallowDiff(1, {})).toThrow(TypeError);
              expect(() => shallowDiff({}, 'x')).toThrow(TypeError);
              expect(() => shallowDiff(undefined, {})).toThrow(TypeError);
              // a valid pair must not throw
              expect(() => shallowDiff({}, {})).not.toThrow();
            });
            """,
        )
        ok, out = _jest_passed(result)
        assert ok, f"TypeError probe failed:\n{out[-4000:]}"

    # -----------------------------------------------------------------------
    # L2 — the agent's own suite must pass via the spec'd command.
    # -----------------------------------------------------------------------
    def test_agent_suite_passes(self):
        """L2: the agent's own Jest suite passes via the Acceptance command.

        Mirrors the Acceptance Criteria command exactly:
        ``yarn test packages/shared/__tests__/shallowDiff-test.js``.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        ok, out = _jest_passed(result)
        assert ok, f"agent suite did not pass green:\n{out[-4000:]}"

    def test_agent_suite_has_multiple_independent_cases(self):
        """L2: the agent suite must contain several independent passing cases.

        The requirement mandates per-behavior independent cases, so a single
        trivial test would not satisfy it; require a multi-case green run.
        """
        result = _yarn_test(AGENT_TEST_REL, timeout=300)
        out = (result.stdout or "") + "\n" + (result.stderr or "")
        assert result.returncode == 0, f"agent suite nonzero rc:\n{out[-3000:]}"
        m = re.search(r"Tests:\s+(\d+) passed", out)
        assert m is not None, f"no passing summary in agent run:\n{out[-3000:]}"
        assert int(m.group(1)) >= 5, (
            f"agent suite should have multiple cases, saw {m.group(1)}"
        )
