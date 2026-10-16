"""
Benchmark test for the `valibot-validation` skill (variant ext3).

Skill task: build a self-contained CSV-row coercion module under
`library/src/csvRow/` using Valibot's own public API. The module exports a
function `parseRow(cells: unknown)` (plus the underlying schema). Given a
fixed-shape positional row `[id, name, price, inStock, category]` of raw
string cells, `parseRow` returns a typed object
`{ id, name, price, inStock, category }` directly, coercing each column:

  * `id`       -> number, must be a whole number >= 1 (else throws)
  * `name`     -> string, trimmed, must be non-empty after trim (else throws)
  * `price`    -> number, finite & >= 0; UNPARSEABLE cells RECOVER to 0 (never throws)
  * `inStock`  -> boolean from exact "true"/"false" (else throws)
  * `category` -> one of "tools"/"food"/"books"/"other"; UNKNOWN values
                  RECOVER to "other" (never throws)

Unrecoverable input (wrong arity, bad id, empty name, invalid inStock,
non-array input) must THROW. The `price` and `category` columns must never
cause a throw — they recover via their fallbacks.

Verification strategy:
  * L1 - the deliverable files exist and are minimally well-formed (the
    module, its barrel re-export, and an agent test suite with >= 10 cases).
  * L2 - DYNAMIC EXECUTION: we drop our OWN vitest drivers into the repo that
    import the agent's real `parseRow` from `library/src/csvRow/index.ts` and
    exercise: a fully valid row, each per-column coercion (string->number,
    string->boolean), name trimming, the price-fallback path, the
    category-fallback path, and every throwing case (bad id incl. boundary 0,
    empty name, invalid inStock, wrong arity, non-array). The agent's own test
    file is NOT trusted for behavior; we drive the real exported function.

A naive/stub implementation (e.g. returns a fixed object, ignores cells,
never coerces, never throws, or always throws) fails these assertions.

Native acceptance command driven by L2 (run from `library/`):
    npx vitest run src/csvRow/csvRow.test.ts

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
MODULE_DIR = os.path.join(SRC_DIR, "csvRow")
# Temp dir for our own driver vitest files (kept inside src so vite resolves it).
DRIVER_DIR = os.path.join(SRC_DIR, "__benchmark_csvrow__")

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
    """Write a vitest driver that imports the agent's `parseRow` and asserts `body`.

    `body` is TypeScript placed inside a single `test(...)` block. The driver
    imports `parseRow` from the agent's barrel file via a relative path.
    """
    path = os.path.join(DRIVER_DIR, test_filename)
    content = textwrap.dedent(
        """
        import {{ describe, expect, test }} from 'vitest';
        import {{ parseRow }} from '../csvRow/index.ts';

        // A fully valid 5-cell row used as a baseline; tests override cells.
        const VALID = ['1042', 'Widget', '19.99', 'true', 'tools'];

        describe('csvRow benchmark driver', () => {{
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
        """L1: csvRow.ts exists and is non-trivially sized."""
        path = os.path.join(MODULE_DIR, "csvRow.ts")
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 100, "csvRow.ts is suspiciously small"

    def test_barrel_index_exists(self):
        """L1: index.ts barrel exists and re-exports from the module file."""
        path = os.path.join(MODULE_DIR, "index.ts")
        assert os.path.isfile(path), f"missing barrel: {path}"
        with open(path) as fh:
            text = fh.read()
        assert "csvRow" in text, "index.ts does not re-export the csvRow module"

    def test_agent_test_suite_exists(self):
        """L1: the agent authored a test suite with at least 10 test cases."""
        path = os.path.join(MODULE_DIR, "csvRow.test.ts")
        assert os.path.isfile(path), f"missing test file: {path}"
        with open(path) as fh:
            text = fh.read()
        # Count `test(`/`it(` occurrences as a coarse lower bound.
        n = text.count("test(") + text.count("it(")
        assert n >= 10, f"expected >= 10 test cases in suite, found ~{n}"

    # ----------------------------------------------------------------------- #
    # L2 - dynamic execution against the real exported function
    # ----------------------------------------------------------------------- #
    def test_valid_row_full_coercion(self):
        """L2: a fully valid row -> typed object with every column coerced."""
        _write_driver(
            "valid.test.ts",
            """
            const r = parseRow(VALID) as any;
            // returns the object directly (not a wrapper); has exactly the 5 keys
            expect(Object.keys(r).sort()).toEqual(
              ['category', 'id', 'inStock', 'name', 'price'].sort()
            );
            expect(r.id).toBe(1042);
            expect(typeof r.id).toBe('number');
            expect(r.name).toBe('Widget');
            expect(r.price).toBe(19.99);
            expect(typeof r.price).toBe('number');
            expect(r.inStock).toBe(true);
            expect(typeof r.inStock).toBe('boolean');
            expect(r.category).toBe('tools');
            """,
        )
        _assert_vitest_pass(_run_vitest("valid.test.ts"), "valid")

    def test_spec_recovery_example(self):
        """L2: the spec recovery example -> price->0, category->'other', name trimmed."""
        _write_driver(
            "recover_example.test.ts",
            """
            const r = parseRow(['7', '  Gadget  ', 'abc', 'false', 'gadgets']) as any;
            expect(r.id).toBe(7);
            expect(r.name).toBe('Gadget');        // trimmed
            expect(r.price).toBe(0);              // unparseable -> fallback 0
            expect(r.inStock).toBe(false);
            expect(r.category).toBe('other');     // unknown -> fallback 'other'
            """,
        )
        _assert_vitest_pass(_run_vitest("recover_example.test.ts"), "recover_example")

    def test_id_coercion_and_boundary(self):
        """L2: id coerces to a whole number; >=1 accepted, <1 / non-integer / non-numeric throw."""
        _write_driver(
            "id.test.ts",
            """
            // minimum accepted boundary
            const one = parseRow(['1', 'X', '1', 'true', 'tools']) as any;
            expect(one.id).toBe(1);
            expect(typeof one.id).toBe('number');

            const big = parseRow(['999999', 'X', '1', 'true', 'tools']) as any;
            expect(big.id).toBe(999999);

            // id of 0 is below the minimum -> throws
            expect(() => parseRow(['0', 'X', '1', 'true', 'tools'])).toThrow();
            // negative id -> throws
            expect(() => parseRow(['-3', 'X', '1', 'true', 'tools'])).toThrow();
            // non-numeric id -> throws
            expect(() => parseRow(['abc', 'X', '1', 'true', 'tools'])).toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("id.test.ts"), "id")

    def test_name_trimming_and_empty(self):
        """L2: name is trimmed; empty-after-trim throws; whitespace-only throws."""
        _write_driver(
            "name.test.ts",
            """
            const r = parseRow(['1', '   Hello World   ', '1', 'true', 'tools']) as any;
            expect(r.name).toBe('Hello World');

            // empty string -> throws
            expect(() => parseRow(['1', '', '1', 'true', 'tools'])).toThrow();
            // whitespace-only -> throws (empty after trim)
            expect(() => parseRow(['1', '   ', '1', 'true', 'tools'])).toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("name.test.ts"), "name")

    def test_price_valid_coercion(self):
        """L2: valid price strings coerce to the exact finite number; 0 accepted."""
        _write_driver(
            "price_valid.test.ts",
            """
            const a = parseRow(['1', 'X', '0', 'true', 'tools']) as any;
            expect(a.price).toBe(0);
            expect(typeof a.price).toBe('number');

            const b = parseRow(['1', 'X', '12.5', 'true', 'tools']) as any;
            expect(b.price).toBe(12.5);

            const c = parseRow(['1', 'X', '100', 'true', 'tools']) as any;
            expect(c.price).toBe(100);
            """,
        )
        _assert_vitest_pass(_run_vitest("price_valid.test.ts"), "price_valid")

    def test_price_fallback_to_zero(self):
        """L2: unparseable / negative / non-finite price recovers to 0 WITHOUT throwing."""
        _write_driver(
            "price_fallback.test.ts",
            """
            // unparseable string -> fallback 0, no throw, rest of row intact
            let r = parseRow(['5', 'X', 'not-a-number', 'true', 'tools']) as any;
            expect(r.price).toBe(0);
            expect(r.id).toBe(5);
            expect(r.inStock).toBe(true);
            expect(r.category).toBe('tools');

            // negative price is not a valid non-negative number -> fallback 0
            r = parseRow(['5', 'X', '-9.99', 'true', 'tools']) as any;
            expect(r.price).toBe(0);

            // empty price cell -> fallback 0
            r = parseRow(['5', 'X', '', 'true', 'tools']) as any;
            expect(r.price).toBe(0);

            // a bad price must NEVER cause a throw
            expect(() => parseRow(['5', 'X', 'xyz', 'true', 'tools'])).not.toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("price_fallback.test.ts"), "price_fallback")

    def test_instock_boolean_coercion(self):
        """L2: exact 'true'/'false' coerce to booleans; anything else throws."""
        _write_driver(
            "instock.test.ts",
            """
            const t = parseRow(['1', 'X', '1', 'true', 'tools']) as any;
            expect(t.inStock).toBe(true);
            expect(typeof t.inStock).toBe('boolean');

            const f = parseRow(['1', 'X', '1', 'false', 'tools']) as any;
            expect(f.inStock).toBe(false);
            expect(typeof f.inStock).toBe('boolean');

            // case-sensitive: 'True' is NOT accepted -> throws
            expect(() => parseRow(['1', 'X', '1', 'True', 'tools'])).toThrow();
            // arbitrary value -> throws
            expect(() => parseRow(['1', 'X', '1', 'maybe', 'tools'])).toThrow();
            // empty -> throws
            expect(() => parseRow(['1', 'X', '1', '', 'tools'])).toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("instock.test.ts"), "instock")

    def test_category_enum_and_fallback(self):
        """L2: each known category passes through; unknown values recover to 'other' (no throw)."""
        _write_driver(
            "category.test.ts",
            """
            for (const cat of ['tools', 'food', 'books', 'other']) {
              const r = parseRow(['1', 'X', '1', 'true', cat]) as any;
              expect(r.category).toBe(cat);
            }

            // unknown categories -> fallback 'other', never throws
            for (const cat of ['gadgets', 'TOOLS', '', 'misc']) {
              let r: any;
              expect(() => { r = parseRow(['1', 'X', '1', 'true', cat]); }).not.toThrow();
              expect(r.category).toBe('other');
            }
            """,
        )
        _assert_vitest_pass(_run_vitest("category.test.ts"), "category")

    def test_wrong_arity_throws(self):
        """L2: rows whose length is not exactly 5 throw (fixed positional shape)."""
        _write_driver(
            "arity.test.ts",
            """
            // 4 cells -> throws
            expect(() => parseRow(['1', 'X', '1', 'true'])).toThrow();
            // 6 cells -> throws
            expect(() => parseRow(['1', 'X', '1', 'true', 'tools', 'extra'])).toThrow();
            // empty array -> throws
            expect(() => parseRow([])).toThrow();
            // exactly 5 valid cells -> does NOT throw
            expect(() => parseRow(['1', 'X', '1', 'true', 'tools'])).not.toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("arity.test.ts"), "arity")

    def test_non_array_input_throws(self):
        """L2: non-array inputs (string, number, null, object, undefined) throw."""
        _write_driver(
            "nonarray.test.ts",
            """
            expect(() => parseRow('not an array' as unknown)).toThrow();
            expect(() => parseRow(42 as unknown)).toThrow();
            expect(() => parseRow(null as unknown)).toThrow();
            expect(() => parseRow(undefined as unknown)).toThrow();
            expect(() => parseRow({} as unknown)).toThrow();
            expect(() => parseRow(true as unknown)).toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("nonarray.test.ts"), "nonarray")

    def test_recoverable_columns_never_throw_under_failure(self):
        """L2: when ONLY price+category are bad, the row still parses (recovery, no throw)."""
        _write_driver(
            "recover_isolation.test.ts",
            """
            // everything else valid, price+category both bad -> recovers, no throw
            let r: any;
            expect(() => {
              r = parseRow(['12', '  Item  ', 'NaNish', 'false', 'weapons']);
            }).not.toThrow();
            expect(r.id).toBe(12);
            expect(r.name).toBe('Item');
            expect(r.price).toBe(0);
            expect(r.inStock).toBe(false);
            expect(r.category).toBe('other');

            // but a bad id alongside recoverable price/category STILL throws
            expect(() => parseRow(['0', 'Item', 'bad', 'false', 'weapons'])).toThrow();
            // and an invalid inStock alongside recoverable cells STILL throws
            expect(() => parseRow(['12', 'Item', 'bad', 'nope', 'weapons'])).toThrow();
            """,
        )
        _assert_vitest_pass(
            _run_vitest("recover_isolation.test.ts"), "recover_isolation"
        )

    def test_agent_own_suite_passes(self):
        """L2: the agent's authored suite passes under the native command."""
        proc = subprocess.run(
            [NPX, "vitest", "run", "--no-coverage", "src/csvRow/csvRow.test.ts"],
            cwd=LIB_DIR,
            capture_output=True,
            text=True,
            timeout=VITEST_TIMEOUT,
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "agent's own csvRow.test.ts suite did not pass.\n"
            f"{combined[-4000:]}"
        )
