"""
Benchmark test for the `valibot-validation` skill (variant ext5).

Skill task: build a self-contained *query-filter* validation module
(`library/src/queryFilter/`) on top of Valibot's own public API. Unlike the
ext1 signup variant (which returns a `{ ok, errors }` result object), THIS
variant exports `parseQuery(input: unknown)` plus its underlying schema and:

  * RETURNS the normalized query object DIRECTLY on valid input, and
  * THROWS when the input is invalid.

The normalized object contains exactly `page`, `perPage`, `sortBy`, `order`,
and `filters`, with documented defaults applied (page=1, perPage=20,
sortBy="createdAt", order="asc", filters={}). Unknown top-level keys are
stripped. `filters` is an open map of string keys to NON-EMPTY string values;
any non-string or empty value rejects the whole query.

What this test verifies:
  * L1 - the deliverable files exist and are minimally well-formed (the module
    `queryFilter.ts`, its barrel `index.ts`, and a test suite with >= 10 cases).
  * L2 - DYNAMIC EXECUTION: we drop our OWN vitest driver into the repo that
    imports the agent's `parseQuery` from `library/src/queryFilter/index.ts`
    and exercises every field rule, defaulting, unknown-key stripping, the open
    filter-map success/rejection paths, and non-object input handling. We assert
    concrete returned values and that invalid inputs THROW. The agent's own test
    file is NOT trusted for behavior; we exercise the real exported function.
    The final test additionally runs the agent's own native command.

Native acceptance command (run from library/):
    npx vitest run src/queryFilter/queryFilter.test.ts

Run by the harness with:
    python -m pytest /tmp/benchmark_tests/test_valibot_validation.py -v --tb=short
"""

import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/valibot"
LIB_DIR = os.path.join(REPO_DIR, "library")
SRC_DIR = os.path.join(LIB_DIR, "src")
MODULE_DIR = os.path.join(SRC_DIR, "queryFilter")
# Temp dir for our own driver vitest files (kept inside src so vite resolves it).
DRIVER_DIR = os.path.join(SRC_DIR, "__benchmark_queryfilter__")

NPX = "npx"
VITEST_TIMEOUT = 600


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module", autouse=True)
def ensure_deps_and_cleanup():
    """Make sure vitest is runnable and clean up our driver dir afterwards."""
    try:
        from _dependency_utils import ensure_npm_dependencies  # type: ignore

        try:
            ensure_npm_dependencies(LIB_DIR)
        except Exception:
            # Container is expected to already have deps installed; ignore.
            pass
    except Exception:
        pass
    os.makedirs(DRIVER_DIR, exist_ok=True)
    yield
    # Best-effort cleanup of anything we wrote.
    try:
        import shutil

        shutil.rmtree(DRIVER_DIR, ignore_errors=True)
    except Exception:
        pass


def _run_vitest(test_filename):
    """Run a single vitest file (relative to library/) and return CompletedProcess."""
    rel = os.path.relpath(os.path.join(DRIVER_DIR, test_filename), LIB_DIR)
    return subprocess.run(
        [NPX, "vitest", "run", "--no-coverage", rel],
        cwd=LIB_DIR,
        capture_output=True,
        text=True,
        timeout=VITEST_TIMEOUT,
    )


def _write_driver(test_filename, body):
    """Write a vitest driver that imports the agent's module and asserts `body`.

    `body` is TypeScript placed inside a single `test(...)` block. The driver
    imports `parseQuery` from the agent's barrel file via a relative path.
    """
    path = os.path.join(DRIVER_DIR, test_filename)
    content = textwrap.dedent(
        """
        import {{ describe, expect, test }} from 'vitest';
        import {{ parseQuery }} from '../queryFilter/index.ts';

        const FULL = {{
          page: 2,
          perPage: 50,
          sortBy: 'createdAt',
          order: 'desc',
          filters: {{ status: 'active', country: 'us' }},
        }};

        describe('queryFilter benchmark driver', () => {{
          test('case', () => {{
        {body}
          }});
        }});
        """
    ).format(body=textwrap.indent(textwrap.dedent(body), "    "))
    with open(path, "w") as fh:
        fh.write(content)
    return path


def _assert_vitest_pass(proc, label):
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, (
        f"[{label}] vitest run failed (rc={proc.returncode}).\n"
        f"----- stdout/stderr -----\n{combined[-4000:]}"
    )
    # Guard against "0 passed" / no-tests-found situations.
    assert "passed" in combined, (
        f"[{label}] vitest produced no passing tests.\n{combined[-2000:]}"
    )


# --------------------------------------------------------------------------- #
# L1 - deliverable files exist and are minimally well-formed
# --------------------------------------------------------------------------- #
class TestValibotValidation:
    REPO_DIR = REPO_DIR

    def test_module_file_exists(self):
        """L1: queryFilter.ts exists and is non-trivially sized."""
        path = os.path.join(MODULE_DIR, "queryFilter.ts")
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 100, "queryFilter.ts is suspiciously small"

    def test_module_exports_parsequery(self):
        """L1: the module source declares an exported `parseQuery`."""
        path = os.path.join(MODULE_DIR, "queryFilter.ts")
        with open(path) as fh:
            text = fh.read()
        assert "parseQuery" in text, "queryFilter.ts does not mention parseQuery"
        # It must build on the library's own public API, not a 3rd-party dep.
        assert "from '../index.ts'" in text or 'from "../index.ts"' in text or (
            "../index" in text
        ), "module does not import from the library's public API root"

    def test_barrel_index_exists(self):
        """L1: index.ts barrel exists and re-exports from the module file."""
        path = os.path.join(MODULE_DIR, "index.ts")
        assert os.path.isfile(path), f"missing barrel: {path}"
        with open(path) as fh:
            text = fh.read()
        assert "queryFilter" in text, "index.ts does not re-export the queryFilter module"

    def test_agent_test_suite_exists(self):
        """L1: the agent authored a test suite with at least 10 test cases."""
        path = os.path.join(MODULE_DIR, "queryFilter.test.ts")
        assert os.path.isfile(path), f"missing test file: {path}"
        with open(path) as fh:
            text = fh.read()
        # Count `test(`/`it(` occurrences as a coarse lower bound.
        n = text.count("test(") + text.count("it(")
        assert n >= 10, f"expected >= 10 test cases in suite, found ~{n}"

    # ----------------------------------------------------------------------- #
    # L2 - dynamic execution against the real exported function
    # ----------------------------------------------------------------------- #
    def test_full_payload_returned_normalized(self):
        """L2: the full example payload -> returned directly, unchanged & complete."""
        _write_driver(
            "full.test.ts",
            """
            const r = parseQuery(FULL) as any;
            // parseQuery RETURNS the object directly (not a { ok, data } wrapper).
            expect(r.page).toBe(2);
            expect(r.perPage).toBe(50);
            expect(r.sortBy).toBe('createdAt');
            expect(r.order).toBe('desc');
            expect(r.filters).toEqual({ status: 'active', country: 'us' });
            // exactly the five documented keys, nothing more.
            const keys = Object.keys(r).sort();
            expect(keys).toEqual(
              ['filters', 'order', 'page', 'perPage', 'sortBy'].sort()
            );
            expect('ok' in r).toBe(false);
            expect('data' in r).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("full.test.ts"), "full")

    def test_all_defaults_on_empty_object(self):
        """L2: `{}` -> every field defaulted exactly as specified."""
        _write_driver(
            "defaults.test.ts",
            """
            const r = parseQuery({}) as any;
            expect(r.page).toBe(1);
            expect(r.perPage).toBe(20);
            expect(r.sortBy).toBe('createdAt');
            expect(r.order).toBe('asc');
            expect(r.filters).toEqual({});
            const keys = Object.keys(r).sort();
            expect(keys).toEqual(
              ['filters', 'order', 'page', 'perPage', 'sortBy'].sort()
            );
            """,
        )
        _assert_vitest_pass(_run_vitest("defaults.test.ts"), "defaults")

    def test_partial_input_defaults_rest(self):
        """L2: a partial input keeps given fields and defaults the rest."""
        _write_driver(
            "partial.test.ts",
            """
            const r = parseQuery({ perPage: 5 }) as any;
            expect(r.perPage).toBe(5);
            expect(r.page).toBe(1);
            expect(r.sortBy).toBe('createdAt');
            expect(r.order).toBe('asc');
            expect(r.filters).toEqual({});

            const r2 = parseQuery({ sortBy: 'name', order: 'desc' }) as any;
            expect(r2.sortBy).toBe('name');
            expect(r2.order).toBe('desc');
            expect(r2.page).toBe(1);
            expect(r2.perPage).toBe(20);
            """,
        )
        _assert_vitest_pass(_run_vitest("partial.test.ts"), "partial")

    def test_unknown_top_level_keys_stripped(self):
        """L2: unknown top-level keys must be stripped, not retained or rejected."""
        _write_driver(
            "strip.test.ts",
            """
            const r = parseQuery({ page: 1, junk: true, isAdmin: 1, extra: 'x' }) as any;
            expect(r.page).toBe(1);
            expect('junk' in r).toBe(false);
            expect('isAdmin' in r).toBe(false);
            expect('extra' in r).toBe(false);
            const keys = Object.keys(r).sort();
            expect(keys).toEqual(
              ['filters', 'order', 'page', 'perPage', 'sortBy'].sort()
            );
            """,
        )
        _assert_vitest_pass(_run_vitest("strip.test.ts"), "strip")

    def test_page_lower_bound(self):
        """L2: page must be an integer >= 1; 0 and negatives throw, boundary 1 ok."""
        _write_driver(
            "page.test.ts",
            """
            expect(() => parseQuery({ page: 0 })).toThrow();
            expect(() => parseQuery({ page: -3 })).toThrow();
            expect(() => parseQuery({ page: 1.5 })).toThrow();

            const ok = parseQuery({ page: 1 }) as any;
            expect(ok.page).toBe(1);
            const big = parseQuery({ page: 999 }) as any;
            expect(big.page).toBe(999);
            """,
        )
        _assert_vitest_pass(_run_vitest("page.test.ts"), "page")

    def test_perpage_range(self):
        """L2: perPage must be an integer in [1, 100]; out-of-range throws, bounds ok."""
        _write_driver(
            "perpage.test.ts",
            """
            expect(() => parseQuery({ perPage: 0 })).toThrow();
            expect(() => parseQuery({ perPage: 101 })).toThrow();
            expect(() => parseQuery({ perPage: 250 })).toThrow();
            expect(() => parseQuery({ perPage: 50.5 })).toThrow();

            const low = parseQuery({ perPage: 1 }) as any;
            expect(low.perPage).toBe(1);
            const high = parseQuery({ perPage: 100 }) as any;
            expect(high.perPage).toBe(100);
            """,
        )
        _assert_vitest_pass(_run_vitest("perpage.test.ts"), "perpage")

    def test_sortby_picklist(self):
        """L2: sortBy restricted to the three allowed fields; others throw."""
        _write_driver(
            "sortby.test.ts",
            """
            expect(() => parseQuery({ sortBy: 'color' })).toThrow();
            expect(() => parseQuery({ sortBy: 'id' })).toThrow();
            expect(() => parseQuery({ sortBy: '' })).toThrow();

            for (const f of ['createdAt', 'updatedAt', 'name']) {
              const r = parseQuery({ sortBy: f }) as any;
              expect(r.sortBy).toBe(f);
            }
            """,
        )
        _assert_vitest_pass(_run_vitest("sortby.test.ts"), "sortby")

    def test_order_picklist(self):
        """L2: order restricted to asc/desc; anything else throws."""
        _write_driver(
            "order.test.ts",
            """
            expect(() => parseQuery({ order: 'sideways' })).toThrow();
            expect(() => parseQuery({ order: 'ASC' })).toThrow();
            expect(() => parseQuery({ order: '' })).toThrow();

            const a = parseQuery({ order: 'asc' }) as any;
            expect(a.order).toBe('asc');
            const d = parseQuery({ order: 'desc' }) as any;
            expect(d.order).toBe('desc');
            """,
        )
        _assert_vitest_pass(_run_vitest("order.test.ts"), "order")

    def test_filters_open_map_success(self):
        """L2: filters is an OPEN map - arbitrary keys preserved when values are non-empty strings."""
        _write_driver(
            "filters_ok.test.ts",
            """
            const r = parseQuery({ filters: { a: '1', b: '2', c: '3' } }) as any;
            expect(r.filters).toEqual({ a: '1', b: '2', c: '3' });
            expect(Object.keys(r.filters).sort()).toEqual(['a', 'b', 'c']);

            // a single arbitrary key not seen in the spec also passes through
            const r2 = parseQuery({ filters: { somethingElse: 'value' } }) as any;
            expect(r2.filters.somethingElse).toBe('value');

            // empty filters object is valid and preserved as {}
            const r3 = parseQuery({ filters: {} }) as any;
            expect(r3.filters).toEqual({});
            """,
        )
        _assert_vitest_pass(_run_vitest("filters_ok.test.ts"), "filters_ok")

    def test_filters_reject_empty_and_nonstring_values(self):
        """L2: an empty-string or non-string filter value rejects the whole query."""
        _write_driver(
            "filters_bad.test.ts",
            """
            // empty string value -> throws
            expect(() => parseQuery({ filters: { status: '' } })).toThrow();
            // non-string value -> throws
            expect(() => parseQuery({ filters: { status: 5 } })).toThrow();
            expect(() => parseQuery({ filters: { status: true } })).toThrow();
            expect(() => parseQuery({ filters: { status: null } })).toThrow();
            // one good + one bad still rejects the whole input
            expect(() =>
              parseQuery({ filters: { ok: 'yes', bad: '' } })
            ).toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("filters_bad.test.ts"), "filters_bad")

    def test_non_object_inputs_throw(self):
        """L2: primitive / null / array inputs throw (parseQuery never silently passes)."""
        _write_driver(
            "nonobject.test.ts",
            """
            expect(() => parseQuery('hello' as unknown)).toThrow();
            expect(() => parseQuery(null as unknown)).toThrow();
            expect(() => parseQuery(42 as unknown)).toThrow();
            expect(() => parseQuery(true as unknown)).toThrow();
            // a valid empty object, by contrast, must NOT throw
            expect(() => parseQuery({})).not.toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("nonobject.test.ts"), "nonobject")

    def test_agent_own_suite_passes(self):
        """L2: the agent's authored suite passes under the native acceptance command."""
        proc = subprocess.run(
            [NPX, "vitest", "run", "--no-coverage", "src/queryFilter/queryFilter.test.ts"],
            cwd=LIB_DIR,
            capture_output=True,
            text=True,
            timeout=VITEST_TIMEOUT,
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "agent's own queryFilter.test.ts suite did not pass.\n"
            f"{combined[-4000:]}"
        )
