"""
Benchmark test for the `valibot-validation` skill (variant ext10).

Skill task: implement a self-contained price/quantity normalization module
(`library/src/lineItem/`) built on Valibot's own public API. The module exports
`normalizeLineItem(input: unknown)` plus its underlying schema. Unlike the ext1
variant, this function returns the NORMALIZED line item DIRECTLY and THROWS on
invalid input (no discriminated `{ ok, ... }` envelope).

Field semantics under test (re-derived from THIS variant's requirement doc):
  * `sku`        - required string, trimmed; must match uppercase alnum groups
                   joined by single hyphens (e.g. `ABC-123`, `A1-B2-C3`).
  * `unitPriceCents` - required number; integer, >= 0, AND a multiple of 5.
                   Any violation throws.
  * `quantity`   - required number; must be an integer, then CLAMPED into [1,99]
                   (out-of-range integers are clamped, NOT rejected; non-integers
                   throw).
  * `discountPercent` - optional number; integer CLAMPED into [0,100]; defaults
                   to 0 when absent; non-integers throw.
  * `lineTotalCents` - derived output:
                   Math.round(unitPriceCents * quantity * (100 - discountPercent)/100)
                   computed from the CLAMPED values.
  * Output shape is EXACTLY {sku, unitPriceCents, quantity, discountPercent,
    lineTotalCents}; unknown keys are stripped.

What this test verifies:
  * L1 - deliverable files exist and are minimally well-formed (the module, its
    barrel re-export, and a test suite with >= 10 cases).
  * L2 - DYNAMIC EXECUTION: we drop our OWN vitest drivers into the repo that
    import the agent's `normalizeLineItem` from `library/src/lineItem/index.ts`
    and exercise every rule (multiple-of-5, integer cents, quantity/discount
    clamping at both ends, default discount, derived total, sku trim+pattern,
    unknown-key stripping, throw-on-invalid). The agent's own test file is NOT
    trusted for behavior; we exercise the real exported function. A naive/stub
    impl (returns a fixed object, ignores clamping, skips multiple-of-5, or never
    throws) MUST fail these drivers.

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
MODULE_DIR = os.path.join(SRC_DIR, "lineItem")
# Temp dir for our own driver vitest files (kept inside src so vite resolves it).
DRIVER_DIR = os.path.join(SRC_DIR, "__benchmark_line_item__")

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
    imports `normalizeLineItem` from the agent's barrel file via a relative path.
    A small `expectThrows` helper is provided so each case can assert that an
    invalid payload throws without aborting the surrounding test.
    """
    path = os.path.join(DRIVER_DIR, test_filename)
    content = textwrap.dedent(
        """
        import {{ describe, expect, test }} from 'vitest';
        import {{ normalizeLineItem }} from '../lineItem/index.ts';

        function expectThrows(fn) {{
          let threw = false;
          try {{ fn(); }} catch (e) {{ threw = true; }}
          expect(threw).toBe(true);
        }}

        describe('lineItem benchmark driver', () => {{
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
    assert "passed" in combined, (
        f"[{label}] vitest produced no passing tests.\n{combined[-2000:]}"
    )


# --------------------------------------------------------------------------- #
# L1 - deliverable files exist and are minimally well-formed
# --------------------------------------------------------------------------- #
class TestValibotValidation:
    REPO_DIR = REPO_DIR

    def test_module_file_exists(self):
        """L1: lineItem.ts exists and is non-trivially sized."""
        path = os.path.join(MODULE_DIR, "lineItem.ts")
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 100, "lineItem.ts is suspiciously small"

    def test_barrel_index_exists(self):
        """L1: index.ts barrel exists and re-exports from the lineItem module."""
        path = os.path.join(MODULE_DIR, "index.ts")
        assert os.path.isfile(path), f"missing barrel: {path}"
        with open(path) as fh:
            text = fh.read()
        assert "lineItem" in text, "index.ts does not re-export the lineItem module"

    def test_agent_test_suite_exists(self):
        """L1: the agent authored a test suite with at least 10 test cases."""
        path = os.path.join(MODULE_DIR, "lineItem.test.ts")
        assert os.path.isfile(path), f"missing test file: {path}"
        with open(path) as fh:
            text = fh.read()
        n = text.count("test(") + text.count("it(")
        assert n >= 10, f"expected >= 10 test cases in suite, found ~{n}"

    # ----------------------------------------------------------------------- #
    # L2 - dynamic execution against the real exported function
    # ----------------------------------------------------------------------- #
    def test_valid_payload_and_derived_total(self):
        """L2: a fully valid payload normalizes and computes lineTotalCents.

        Doc example: {sku:'ABC-123', unitPriceCents:2000, quantity:3,
        discountPercent:10} -> lineTotalCents === round(2000*3*90/100) === 5400.
        A stub that ignores the discount or miscomputes the total fails here.
        """
        _write_driver(
            "valid.test.ts",
            """
            const r = normalizeLineItem({
              sku: 'ABC-123',
              unitPriceCents: 2000,
              quantity: 3,
              discountPercent: 10,
            }) as any;
            expect(r.sku).toBe('ABC-123');
            expect(r.unitPriceCents).toBe(2000);
            expect(r.quantity).toBe(3);
            expect(r.discountPercent).toBe(10);
            expect(r.lineTotalCents).toBe(5400);
            expect(typeof r.lineTotalCents).toBe('number');
            """,
        )
        _assert_vitest_pass(_run_vitest("valid.test.ts"), "valid")

    def test_output_shape_exact_and_unknown_keys_stripped(self):
        """L2: output contains EXACTLY the five fields; unknown keys are stripped."""
        _write_driver(
            "shape.test.ts",
            """
            const r = normalizeLineItem({
              sku: 'ABC-123',
              unitPriceCents: 2000,
              quantity: 3,
              discountPercent: 10,
              evil: 'x',
              isAdmin: true,
              extra: 42,
            }) as any;
            const keys = Object.keys(r).sort();
            expect(keys).toEqual(
              ['discountPercent','lineTotalCents','quantity','sku','unitPriceCents'].sort()
            );
            expect('evil' in r).toBe(false);
            expect('isAdmin' in r).toBe(false);
            expect('extra' in r).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("shape.test.ts"), "shape")

    def test_sku_trim_and_quantity_upper_clamp(self):
        """L2: sku trimmed; quantity above 99 clamps to 99; discount defaults to 0.

        Doc: {sku:'  X1-Y2  ', unitPriceCents:0, quantity:500} ->
        sku 'X1-Y2', quantity 99, discountPercent 0, lineTotalCents 0.
        """
        _write_driver(
            "trim_upper.test.ts",
            """
            const r = normalizeLineItem({
              sku: '  X1-Y2  ',
              unitPriceCents: 0,
              quantity: 500,
            }) as any;
            expect(r.sku).toBe('X1-Y2');
            expect(r.quantity).toBe(99);
            expect(r.discountPercent).toBe(0);
            expect(r.lineTotalCents).toBe(0);
            """,
        )
        _assert_vitest_pass(_run_vitest("trim_upper.test.ts"), "trim_upper")

    def test_quantity_lower_clamp(self):
        """L2: quantity below 1 clamps to 1, affecting the derived total.

        Doc: {sku:'A1', unitPriceCents:100, quantity:0} ->
        quantity 1, lineTotalCents 100.
        """
        _write_driver(
            "lower_clamp.test.ts",
            """
            const r = normalizeLineItem({
              sku: 'A1',
              unitPriceCents: 100,
              quantity: 0,
            }) as any;
            expect(r.quantity).toBe(1);
            expect(r.discountPercent).toBe(0);
            expect(r.lineTotalCents).toBe(100);

            const neg = normalizeLineItem({
              sku: 'A1', unitPriceCents: 100, quantity: -50,
            }) as any;
            expect(neg.quantity).toBe(1);
            expect(neg.lineTotalCents).toBe(100);
            """,
        )
        _assert_vitest_pass(_run_vitest("lower_clamp.test.ts"), "lower_clamp")

    def test_discount_clamp_high_and_total(self):
        """L2: discountPercent above 100 clamps to 100; total then becomes 0.

        Doc: {sku:'A1', unitPriceCents:100, quantity:2, discountPercent:250} ->
        discountPercent 100, lineTotalCents 0.
        """
        _write_driver(
            "discount_high.test.ts",
            """
            const r = normalizeLineItem({
              sku: 'A1',
              unitPriceCents: 100,
              quantity: 2,
              discountPercent: 250,
            }) as any;
            expect(r.discountPercent).toBe(100);
            expect(r.lineTotalCents).toBe(0);

            const low = normalizeLineItem({
              sku: 'A1', unitPriceCents: 100, quantity: 2, discountPercent: -30,
            }) as any;
            expect(low.discountPercent).toBe(0);
            expect(low.lineTotalCents).toBe(200);
            """,
        )
        _assert_vitest_pass(_run_vitest("discount_high.test.ts"), "discount_high")

    def test_discount_default_when_absent(self):
        """L2: omitting discountPercent yields 0 and a no-discount total."""
        _write_driver(
            "discount_default.test.ts",
            """
            const r = normalizeLineItem({
              sku: 'A1-B2-C3',
              unitPriceCents: 500,
              quantity: 4,
            }) as any;
            expect(r.discountPercent).toBe(0);
            expect(r.lineTotalCents).toBe(2000);
            """,
        )
        _assert_vitest_pass(_run_vitest("discount_default.test.ts"), "discount_default")

    def test_unit_price_multiple_of_five_and_integer(self):
        """L2: unitPriceCents must be integer, >= 0 and a multiple of 5; else throws.

        Doc: 1999 (not multiple of 5) throws; 100.5 (non-integer) throws; 103
        (not multiple of 5) throws. Valid multiples of 5 succeed; a stub that
        skips the multiple-of-5 rule fails here.
        """
        _write_driver(
            "unit_price.test.ts",
            """
            // not a multiple of 5
            expectThrows(() => normalizeLineItem({
              sku: 'ABC-123', unitPriceCents: 1999, quantity: 3, discountPercent: 10,
            }));
            // non-integer cents
            expectThrows(() => normalizeLineItem({
              sku: 'A1', unitPriceCents: 100.5, quantity: 1,
            }));
            // not a multiple of 5
            expectThrows(() => normalizeLineItem({
              sku: 'A1', unitPriceCents: 103, quantity: 1,
            }));
            // negative
            expectThrows(() => normalizeLineItem({
              sku: 'A1', unitPriceCents: -5, quantity: 1,
            }));
            // valid multiples of 5 pass
            const ok0 = normalizeLineItem({ sku: 'A1', unitPriceCents: 0, quantity: 1 }) as any;
            expect(ok0.unitPriceCents).toBe(0);
            const ok105 = normalizeLineItem({ sku: 'A1', unitPriceCents: 105, quantity: 1 }) as any;
            expect(ok105.unitPriceCents).toBe(105);
            expect(ok105.lineTotalCents).toBe(105);
            """,
        )
        _assert_vitest_pass(_run_vitest("unit_price.test.ts"), "unit_price")

    def test_non_integer_quantity_and_discount_throw(self):
        """L2: non-integer quantity/discount throw (they are NOT clamped/rounded).

        Doc: {sku:'A1', unitPriceCents:100, quantity:1.5} throws. A fractional
        discountPercent must likewise throw rather than be rounded.
        """
        _write_driver(
            "non_integer.test.ts",
            """
            expectThrows(() => normalizeLineItem({
              sku: 'A1', unitPriceCents: 100, quantity: 1.5,
            }));
            expectThrows(() => normalizeLineItem({
              sku: 'A1', unitPriceCents: 100, quantity: 2, discountPercent: 10.5,
            }));
            // sanity: integer quantity at the boundary is fine
            const ok = normalizeLineItem({
              sku: 'A1', unitPriceCents: 100, quantity: 99,
            }) as any;
            expect(ok.quantity).toBe(99);
            """,
        )
        _assert_vitest_pass(_run_vitest("non_integer.test.ts"), "non_integer")

    def test_sku_pattern_rejection(self):
        """L2: lowercase or malformed skus throw; valid uppercase groups pass.

        Doc: 'abc-123' (lowercase) throws. Patterns must be uppercase alnum
        groups joined by single hyphens.
        """
        _write_driver(
            "sku.test.ts",
            """
            // lowercase rejected
            expectThrows(() => normalizeLineItem({
              sku: 'abc-123', unitPriceCents: 100, quantity: 1,
            }));
            // double hyphen / trailing hyphen malformed
            expectThrows(() => normalizeLineItem({
              sku: 'AB--12', unitPriceCents: 100, quantity: 1,
            }));
            expectThrows(() => normalizeLineItem({
              sku: 'AB-', unitPriceCents: 100, quantity: 1,
            }));
            // illegal characters
            expectThrows(() => normalizeLineItem({
              sku: 'AB_12', unitPriceCents: 100, quantity: 1,
            }));
            // valid single group and multi-group skus accepted (after trim)
            const a = normalizeLineItem({ sku: 'A1', unitPriceCents: 100, quantity: 1 }) as any;
            expect(a.sku).toBe('A1');
            const b = normalizeLineItem({ sku: 'A1-B2-C3', unitPriceCents: 100, quantity: 1 }) as any;
            expect(b.sku).toBe('A1-B2-C3');
            const c = normalizeLineItem({ sku: '  ABC-123  ', unitPriceCents: 100, quantity: 1 }) as any;
            expect(c.sku).toBe('ABC-123');
            """,
        )
        _assert_vitest_pass(_run_vitest("sku.test.ts"), "sku")

    def test_non_object_inputs_throw(self):
        """L2: null, primitives and arrays throw (no silent normalization)."""
        _write_driver(
            "non_object.test.ts",
            """
            for (const input of [null, undefined, 42, 'x', true, []]) {
              expectThrows(() => normalizeLineItem(input as unknown));
            }
            // missing required fields also throws
            expectThrows(() => normalizeLineItem({}));
            expectThrows(() => normalizeLineItem({ sku: 'A1' }));
            """,
        )
        _assert_vitest_pass(_run_vitest("non_object.test.ts"), "non_object")

    def test_rounding_of_derived_total(self):
        """L2: lineTotalCents uses Math.round on the discounted product.

        E.g. unitPriceCents 105, quantity 3, discountPercent 33 ->
        round(105*3*67/100) = round(211.05) = 211. A truncating or
        discount-ignoring impl produces a different value and fails.
        """
        _write_driver(
            "rounding.test.ts",
            """
            const r = normalizeLineItem({
              sku: 'A1', unitPriceCents: 105, quantity: 3, discountPercent: 33,
            }) as any;
            // Math.round(105*3*67/100) = Math.round(211.05) = 211
            expect(r.lineTotalCents).toBe(211);

            const r2 = normalizeLineItem({
              sku: 'A1', unitPriceCents: 995, quantity: 7, discountPercent: 15,
            }) as any;
            // Math.round(995*7*85/100) = Math.round(5920.25) = 5920
            expect(r2.lineTotalCents).toBe(5920);
            """,
        )
        _assert_vitest_pass(_run_vitest("rounding.test.ts"), "rounding")

    def test_agent_own_suite_passes(self):
        """L2: the agent's authored suite passes under the native command."""
        proc = subprocess.run(
            [NPX, "vitest", "run", "--no-coverage", "src/lineItem/lineItem.test.ts"],
            cwd=LIB_DIR,
            capture_output=True,
            text=True,
            timeout=VITEST_TIMEOUT,
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "agent's own lineItem.test.ts suite did not pass.\n"
            f"{combined[-4000:]}"
        )
