"""
Test for the 'vitest-unit-testing' skill (variant batch: ext2).

Task: add an exported `sortObjectKeysDeep<T>(value: T): T` to
packages/vite/src/node/utils.ts that recursively sorts the keys of every
plain object at every nesting depth (ascending, by Object.keys().sort()),
preserves array element order while recursing into elements, returns
primitives (string/number/boolean/null/undefined) unchanged, returns
non-plain objects (Date/RegExp/Map) AS-IS by reference, and is pure (no
input mutation, no shared object/array references in the output). A
dedicated vitest spec is delivered at
packages/vite/src/node/__tests__/sortObjectKeysDeep.spec.ts.

Verification strategy:
- L1: the deliverable source/spec files exist and the export + import are
  present and minimally well-formed (table-driven via test.each/it.each).
- L2: DYNAMIC EXECUTION via the repo's native toolchain (vitest, run with
  `pnpm exec vitest run ...`). To avoid trusting the agent's own spec, we
  write INDEPENDENT driver spec files into the repo's __tests__ directory
  that import `sortObjectKeysDeep` from '../utils' and assert the precise
  required behaviors. A naive implementation (only sorting the top level,
  mutating its input, sharing references with the input, or descending into
  Date/RegExp) makes at least one of these driver specs fail. We also run
  the agent's delivered spec.
"""

import os
import re
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/vite"
TESTS_DIR = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "__tests__")
UTILS_TS = os.path.join(REPO_DIR, "packages", "vite", "src", "node", "utils.ts")
AGENT_SPEC = os.path.join(TESTS_DIR, "sortObjectKeysDeep.spec.ts")

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
    """Verify the sortObjectKeysDeep helper and its vitest coverage."""

    REPO_DIR = "/workspace/vite"

    # ------------------------------------------------------------------
    # L1 — deliverables exist / minimally well-formed
    # ------------------------------------------------------------------

    def test_utils_file_exists(self):
        """utils.ts (the modify target) must exist."""
        assert os.path.isfile(UTILS_TS), f"missing {UTILS_TS}"

    def test_sort_deep_is_exported(self):
        """utils.ts must export a function named sortObjectKeysDeep."""
        with open(UTILS_TS) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+sortObjectKeysDeep\b", src
        ), "sortObjectKeysDeep not exported as a function from utils.ts"

    def test_agent_spec_file_exists(self):
        """The dedicated spec file must be delivered."""
        assert os.path.isfile(AGENT_SPEC), f"missing {AGENT_SPEC}"

    def test_agent_spec_imports_and_is_table_driven(self):
        """The spec must import from ../utils and use a test.each/it.each table."""
        with open(AGENT_SPEC) as f:
            spec = f.read()
        assert "sortObjectKeysDeep" in spec, "spec does not reference sortObjectKeysDeep"
        assert re.search(
            r"from\s+['\"]\.\./utils['\"]", spec
        ), "spec must import from '../utils'"
        assert re.search(
            r"\b(test|it)\s*\.\s*each\b", spec
        ), "spec must drive a test.each / it.each table"

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
            import { sortObjectKeysDeep } from '../utils'

            describe('sortObjectKeysDeep truth table', () => {
              test('table', () => {
                // top-level key order
                expect(Object.keys(sortObjectKeysDeep({ b: 1, a: 2 })))
                  .toEqual(['a', 'b'])
                expect(sortObjectKeysDeep({ b: 1, a: 2 })).toEqual({ a: 2, b: 1 })

                // nested keys also sorted
                const r1 = sortObjectKeysDeep({ z: { y: 1, x: 2 } })
                expect(Object.keys(r1)).toEqual(['z'])
                expect(Object.keys((r1 as any).z)).toEqual(['x', 'y'])

                // array of objects: element order kept, keys sorted
                const r2 = sortObjectKeysDeep([{ b: 1, a: 2 }])
                expect(Array.isArray(r2)).toBe(true)
                expect(r2).toHaveLength(1)
                expect(Object.keys((r2 as any)[0])).toEqual(['a', 'b'])
              })
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "driver truth-table spec failed (vitest nonzero)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_recursive_deep_sorting(self):
        """Keys must be sorted at EVERY level, not just the top (kills top-only impl)."""
        rel = _write_spec(
            "zz_driver_deep",
            """
            import { expect, test } from 'vitest'
            import { sortObjectKeysDeep } from '../utils'

            test('deeply nested sorting (3+ levels)', () => {
              const input = {
                b: 2,
                a: { d: 4, c: { f: 6, e: { h: 8, g: 7 } } },
              }
              const r: any = sortObjectKeysDeep(input)
              expect(Object.keys(r)).toEqual(['a', 'b'])
              expect(Object.keys(r.a)).toEqual(['c', 'd'])
              expect(Object.keys(r.a.c)).toEqual(['e', 'f'])
              expect(Object.keys(r.a.c.e)).toEqual(['g', 'h'])
              // values preserved
              expect(r.b).toBe(2)
              expect(r.a.c.e.g).toBe(7)
              expect(r.a.c.e.h).toBe(8)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "deep recursive sorting wrong (a top-level-only impl fails here)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_array_order_preserved_but_elements_recursed(self):
        """Array element ORDER is kept; each element's object keys are still sorted."""
        rel = _write_spec(
            "zz_driver_array",
            """
            import { expect, test } from 'vitest'
            import { sortObjectKeysDeep } from '../utils'

            test('array order preserved, elements recursed', () => {
              const input = [
                { c: 3, b: 2, a: 1 },
                { z: 26, a: 1 },
                5,
                'x',
              ]
              const r: any = sortObjectKeysDeep(input)
              expect(Array.isArray(r)).toBe(true)
              expect(r).toHaveLength(4)
              // element order must NOT change
              expect(Object.keys(r[0])).toEqual(['a', 'b', 'c'])
              expect(Object.keys(r[1])).toEqual(['a', 'z'])
              expect(r[2]).toBe(5)
              expect(r[3]).toBe('x')
              // nested object inside an array element is also sorted
              const nested: any = sortObjectKeysDeep([{ y: { d: 1, c: 2 }, x: 0 }])
              expect(Object.keys(nested[0])).toEqual(['x', 'y'])
              expect(Object.keys(nested[0].y)).toEqual(['c', 'd'])
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "array handling wrong (order changed or elements not recursed)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_primitive_pass_through(self):
        """Primitives (string/number/boolean/null/undefined) returned unchanged."""
        rel = _write_spec(
            "zz_driver_prim",
            """
            import { expect, test } from 'vitest'
            import { sortObjectKeysDeep } from '../utils'

            test('primitive pass-through', () => {
              expect(sortObjectKeysDeep('hello')).toBe('hello')
              expect(sortObjectKeysDeep(42)).toBe(42)
              expect(sortObjectKeysDeep(true)).toBe(true)
              expect(sortObjectKeysDeep(false)).toBe(false)
              expect(sortObjectKeysDeep(null)).toBe(null)
              expect(sortObjectKeysDeep(undefined)).toBe(undefined)
              // null must NOT be treated as an object (would throw / become {})
              const r: any = sortObjectKeysDeep({ a: null, b: undefined })
              expect(r.a).toBe(null)
              expect('b' in r).toBe(true)
              expect(r.b).toBe(undefined)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "primitive / null pass-through wrong\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_empty_object_returns_fresh_empty(self):
        """An empty object returns a NEW empty object (not the same reference)."""
        rel = _write_spec(
            "zz_driver_empty",
            """
            import { expect, test } from 'vitest'
            import { sortObjectKeysDeep } from '../utils'

            test('empty object', () => {
              const input = {}
              const r = sortObjectKeysDeep(input)
              expect(r).toEqual({})
              expect(Object.keys(r as any)).toEqual([])
              expect(r).not.toBe(input)   // fresh object
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "empty-object handling wrong (must be a fresh empty object)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_non_plain_objects_returned_by_reference(self):
        """Date/RegExp/Map must be returned AS-IS (same reference), not descended."""
        rel = _write_spec(
            "zz_driver_nonplain",
            """
            import { expect, test } from 'vitest'
            import { sortObjectKeysDeep } from '../utils'

            test('non-plain objects pass by reference', () => {
              const d = new Date(0)
              const re = /abc/gi
              const m = new Map([['b', 1], ['a', 2]])

              expect(sortObjectKeysDeep(d)).toBe(d)
              expect(sortObjectKeysDeep(re)).toBe(re)
              expect(sortObjectKeysDeep(m)).toBe(m)

              // and the same when nested inside a plain object
              const input = { z: d, y: re, x: m }
              const r: any = sortObjectKeysDeep(input)
              expect(Object.keys(r)).toEqual(['x', 'y', 'z'])  // plain wrapper sorted
              expect(r.z).toBe(d)   // but the Date itself is the same reference
              expect(r.y).toBe(re)
              expect(r.x).toBe(m)
              // RegExp not turned into a plain {} / Date not enumerated
              expect(r.z instanceof Date).toBe(true)
              expect(r.y instanceof RegExp).toBe(true)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "non-plain object handling wrong (Date/RegExp/Map must pass by reference)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_input_immutability(self):
        """The function must not mutate its input at any depth."""
        rel = _write_spec(
            "zz_driver_immut",
            """
            import { expect, test } from 'vitest'
            import { sortObjectKeysDeep } from '../utils'

            test('input not mutated', () => {
              const input = { b: 1, a: { d: 1, c: 2 } }
              // capture the original key order at both levels
              const topBefore = Object.keys(input)
              const nestedBefore = Object.keys(input.a)
              sortObjectKeysDeep(input)
              // original ordering must be UNCHANGED after the call
              expect(Object.keys(input)).toEqual(topBefore)
              expect(Object.keys(input)).toEqual(['b', 'a'])
              expect(Object.keys(input.a)).toEqual(nestedBefore)
              expect(Object.keys(input.a)).toEqual(['d', 'c'])
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "function mutates its input (must be pure)\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_reference_non_sharing(self):
        """The returned structure must not share object/array refs with the input."""
        rel = _write_spec(
            "zz_driver_refs",
            """
            import { expect, test } from 'vitest'
            import { sortObjectKeysDeep } from '../utils'

            test('no shared references with input', () => {
              const inner = { y: 1, x: 2 }
              const arr = [{ b: 1, a: 2 }]
              const input = { a: inner, list: arr }
              const r: any = sortObjectKeysDeep(input)

              // top object is new
              expect(r).not.toBe(input)
              // nested plain object is a fresh copy
              expect(r.a).not.toBe(inner)
              expect(r.a).toEqual({ x: 2, y: 1 })
              // array is a fresh array (same length / element data)
              expect(r.list).not.toBe(arr)
              expect(Array.isArray(r.list)).toBe(true)
              expect(r.list[0]).not.toBe(arr[0])
              expect(r.list[0]).toEqual({ a: 2, b: 1 })

              // mutating the result must NOT affect the original
              r.a.x = 999
              expect(inner.x).toBe(2)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "returned structure shares references with input\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_ordering_matches_object_keys_sort(self):
        """Key ordering must equal Object.keys(obj).sort() exactly, incl. tricky keys."""
        rel = _write_spec(
            "zz_driver_order",
            """
            import { expect, test } from 'vitest'
            import { sortObjectKeysDeep } from '../utils'

            test('ordering equals Object.keys().sort()', () => {
              // numeric-string keys: JS auto-orders integer-like keys numerically
              // on insertion, but the contract is Object.keys(obj).sort() (lexical),
              // so '10' sorts before '2'. Use clearly non-integer keys to assert the
              // documented default string sort deterministically.
              const input = { B: 1, a: 2, A: 3, b: 4, _z: 5, '1x': 6 }
              const expected = Object.keys(input).sort()
              const r = sortObjectKeysDeep(input)
              expect(Object.keys(r as any)).toEqual(expected)
              // sanity: uppercase sorts before lowercase under default string sort
              expect(expected.indexOf('A')).toBeLessThan(expected.indexOf('a'))
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "key ordering does not match Object.keys().sort()\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_complex_mixed_structure(self):
        """A realistic mixed config object is fully and deterministically sorted."""
        rel = _write_spec(
            "zz_driver_mixed",
            """
            import { expect, test } from 'vitest'
            import { sortObjectKeysDeep } from '../utils'

            test('mixed config-like structure', () => {
              const input = {
                server: { port: 3000, host: 'localhost', proxy: { '/b': 1, '/a': 2 } },
                build: { target: 'es2020', minify: true },
                plugins: [
                  { name: 'b', enforce: 'pre' },
                  { name: 'a' },
                ],
                root: '.',
              }
              const r: any = sortObjectKeysDeep(input)
              expect(Object.keys(r)).toEqual(['build', 'plugins', 'root', 'server'])
              expect(Object.keys(r.server)).toEqual(['host', 'port', 'proxy'])
              expect(Object.keys(r.server.proxy)).toEqual(['/a', '/b'])
              expect(Object.keys(r.build)).toEqual(['minify', 'target'])
              // plugin array order preserved
              expect(r.plugins[0].name).toBe('b')
              expect(r.plugins[1].name).toBe('a')
              // plugin object keys sorted
              expect(Object.keys(r.plugins[0])).toEqual(['enforce', 'name'])
              // a value-equivalent structure deep-equals regardless of input order
              const reordered = {
                root: '.',
                plugins: [
                  { enforce: 'pre', name: 'b' },
                  { name: 'a' },
                ],
                build: { minify: true, target: 'es2020' },
                server: { proxy: { '/a': 2, '/b': 1 }, host: 'localhost', port: 3000 },
              }
              expect(sortObjectKeysDeep(reordered)).toEqual(r)
            })
            """,
        )
        res = _vitest(rel)
        assert res.returncode == 0, (
            "mixed config structure not fully/deterministically sorted\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    def test_agent_delivered_spec_passes(self):
        """The agent's own delivered spec must pass under native vitest."""
        assert os.path.isfile(AGENT_SPEC), "agent spec missing"
        rel = os.path.relpath(AGENT_SPEC, REPO_DIR)
        res = _vitest(rel)
        assert res.returncode == 0, (
            "agent's sortObjectKeysDeep.spec.ts does not pass\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )
        combined = (res.stdout + res.stderr).lower()
        assert "no test" not in combined, "agent spec contains no tests"
