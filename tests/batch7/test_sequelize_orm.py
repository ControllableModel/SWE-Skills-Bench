"""
Test for the 'sequelize-orm' skill (variant ext7) — Build a Product Search Filter.

The agent must create two files inside @sequelize/core's INTEGRATION-test tree:
  - packages/core/test/integration/product-search.ts        (the module)
  - packages/core/test/integration/product-search.test.ts   (its integration test)

The module exports:
  - setupProducts(sequelize)         -> defines & creates the Product table,
                                        returns the Product model.
  - searchProducts(Product, filter)  -> returns the rows matching `filter`,
                                        ordered by price ASC then name ASC.

Product fields: name (text, required), price (integer, required),
category (text, required), inStock (boolean, default true).

Filter keys (each narrows with AND; all optional):
  nameContains (string, case-sensitive substring on name),
  categories (string[], category IN list; [] yields zero rows),
  minPrice (number, price >= value), maxPrice (number, price <= value),
  inStockOnly (boolean, when true keep only inStock===true).
An empty/undefined filter returns ALL products, still ordered by price then name.

Verification strategy
---------------------
L1 cases check the deliverable files exist and are minimally well-formed.

L2 cases DO NOT trust the agent's own test file. Instead we drop our OWN
independent mocha integration spec into the repo that *imports the agent's
product-search module*, builds a fresh Sequelize instance via the repo's
`createSequelizeInstance()` support helper, seeds a FIXED known product set,
and asserts the exact rows / ordering / boundary behaviour returned by
searchProducts() for every filter key, an empty filter, an inclusive price
range (boundary equality), an empty categories array (zero rows), and a
combined AND filter.

Each spec is executed with the repository's native command, run from
packages/core:

    yarn mocha "test/integration/<spec>.test.ts"

A naive implementation that ignores a present filter key, hardcodes output,
skips storage, or returns rows in an unspecified order CANNOT pass these
independent introspective assertions.
"""

import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/sequelize"
CORE_DIR = os.path.join(REPO_DIR, "packages", "core")
INT_DIR = os.path.join(CORE_DIR, "test", "integration")
MODULE_FILE = os.path.join(INT_DIR, "product-search.ts")
AGENT_TEST_FILE = os.path.join(INT_DIR, "product-search.test.ts")

# Basename for the independent specs we drop into the integration dir.
_BENCH_BASENAME = "zzz-bench-product-search"


def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _run_mocha(spec_rel_path, timeout=600):
    """Run one mocha spec from packages/core using the repo's native command."""
    cmd = ["yarn", "mocha", spec_rel_path]
    return subprocess.run(
        cmd,
        cwd=CORE_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _write_spec_and_run(spec_name, spec_body, timeout=600):
    """
    Write a self-contained mocha .test.ts spec into the integration dir, run it,
    then clean it up. Returns the CompletedProcess.
    """
    spec_path = os.path.join(INT_DIR, spec_name)
    rel_path = os.path.join("test", "integration", spec_name)
    with open(spec_path, "w", encoding="utf-8") as fh:
        fh.write(spec_body)
    try:
        return _run_mocha(rel_path, timeout=timeout)
    finally:
        try:
            os.remove(spec_path)
        except OSError:
            pass


def _assert_mocha_passed(result, context=""):
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    assert result.returncode == 0, (
        f"mocha spec failed ({context}).\n"
        f"returncode={result.returncode}\n"
        f"--- stdout (tail) ---\n{(result.stdout or '')[-6000:]}\n"
        f"--- stderr (tail) ---\n{(result.stderr or '')[-3000:]}"
    )
    # Guard against a silent zero-test run being treated as success.
    assert "0 passing" not in combined, (
        f"mocha reported 0 passing tests ({context}); the spec did not run.\n"
        f"{combined[-4000:]}"
    )


# Common TS preamble used by every independent spec.
#
# It builds a fresh Sequelize instance (via the repo's support helper), invokes
# the agent's setupProducts() to create the table, seeds a FIXED known product
# set, and exposes small assertion helpers. We never rely on the agent's own
# test file; we re-derive every expectation from the requirement doc.
#
# Fixed seed (chosen so ordering, boundaries, categories and stock are all
# discriminating):
#
#   name        price  category  inStock
#   ----------------------------------------
#   Pro Mouse     10    toys      true
#   Pro Keyboard  10    toys      false   (price tie with Pro Mouse -> name tie-break)
#   Basic Pen      5    books     true
#   Pro Pen       20    books     true
#   Wonder Toy    20    toys      true    (price tie with Pro Pen -> name tie-break)
#   Cheap Snack    3    food      false
#
_PREAMBLE = textwrap.dedent(
    """\
    import { expect } from 'chai';
    import { createSequelizeInstance } from './support';
    import { setupProducts, searchProducts } from './product-search';

    const SEED = [
      { name: 'Pro Mouse',    price: 10, category: 'toys',  inStock: true },
      { name: 'Pro Keyboard', price: 10, category: 'toys',  inStock: false },
      { name: 'Basic Pen',    price: 5,  category: 'books', inStock: true },
      { name: 'Pro Pen',      price: 20, category: 'books', inStock: true },
      { name: 'Wonder Toy',   price: 20, category: 'toys',  inStock: true },
      { name: 'Cheap Snack',  price: 3,  category: 'food',  inStock: false },
    ];

    async function freshCatalog() {
      const sequelize = createSequelizeInstance();
      const Product = await setupProducts(sequelize as any);
      // setupProducts must define+create the table; be tolerant if it didn't sync.
      try { await (Product as any).sync({ force: true }); } catch (e) { /* already created */ }
      await (Product as any).bulkCreate(SEED);
      return { sequelize, Product };
    }

    function plain(rows: any[]) {
      return rows.map((r: any) => ({
        name: r.name ?? r.get?.('name'),
        price: Number(r.price ?? r.get?.('price')),
        category: r.category ?? r.get?.('category'),
        inStock: Boolean(r.inStock ?? r.get?.('inStock')),
      }));
    }

    function names(rows: any[]) {
      return plain(rows).map((r: any) => r.name);
    }

    // Assert rows are sorted by price ASC, then name ASC (the required ordering).
    function assertOrdered(rows: any[]) {
      const p = plain(rows);
      for (let i = 1; i < p.length; i++) {
        const a = p[i - 1];
        const b = p[i];
        const ok = a.price < b.price || (a.price === b.price && a.name <= b.name);
        expect(ok,
          'rows are not ordered by price asc then name asc: ' +
          JSON.stringify(p.map((x: any) => [x.price, x.name]))).to.equal(true);
      }
    }
    """
)


# ---------------------------------------------------------------------------
# Module-scope dependency guard. Ensure node_modules is present (best-effort)
# so the native `yarn mocha` can resolve mocha/chai/esbuild.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module", autouse=True)
def _ensure_dependencies():
    if not os.path.isdir(os.path.join(REPO_DIR, "node_modules")) and not os.path.isdir(
        os.path.join(CORE_DIR, "node_modules")
    ):
        try:
            subprocess.run(
                ["yarn", "install", "--immutable"],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=1800,
            )
        except Exception:
            pass
    yield


class TestSequelizeOrm:
    """Verify the product-search filter deliverable (ext7)."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """The implementation module product-search.ts must exist."""
        assert os.path.isfile(MODULE_FILE), f"missing module file: {MODULE_FILE}"

    def test_agent_test_file_exists(self):
        """The agent's own integration test product-search.test.ts must exist."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing test file: {AGENT_TEST_FILE}"

    def test_module_exports_required_symbols(self):
        """product-search.ts must export setupProducts and searchProducts."""
        src = _read(MODULE_FILE)
        assert "setupProducts" in src, "setupProducts not found in module"
        assert "searchProducts" in src, "searchProducts not found in module"
        assert "export" in src, "module does not export anything"

    def test_agent_test_imports_module(self):
        """The agent's test must import from the local product-search module."""
        src = _read(AGENT_TEST_FILE)
        assert "product-search" in src, "test does not reference the product-search module"

    # ------------------------------------------------------------------
    # L2 — independent dynamic execution via native `yarn mocha`.
    # Each test writes its own spec, so failures are isolated and specific.
    # ------------------------------------------------------------------

    def test_setup_defines_product_model(self):
        """setupProducts returns a real Product model carrying the four required fields."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('product-search: model shape', () => {
              it('returns a real model with name/price/category/inStock attributes', async () => {
                const { Product } = await freshCatalog();
                expect(typeof (Product as any).getAttributes, 'not a model class').to.equal('function');
                const attrs: any = (Product as any).getAttributes();
                for (const f of ['name', 'price', 'category', 'inStock']) {
                  expect(attrs, 'Product missing attribute ' + f).to.have.property(f);
                }
              });

              it('inStock defaults to true when omitted', async () => {
                const { Product } = await freshCatalog();
                const built: any = (Product as any).build({ name: 'X', price: 1, category: 'c' });
                expect(Boolean(built.inStock)).to.equal(true);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-shape.test.ts", spec)
        _assert_mocha_passed(result, "Product model shape / defaults")

    def test_empty_filter_returns_all_ordered(self):
        """An empty filter returns ALL seeded rows, ordered by price asc then name asc."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('product-search: empty filter', () => {
              it('{} returns every product in price-then-name order', async () => {
                const { Product } = await freshCatalog();
                const rows = await searchProducts(Product as any, {} as any);
                expect(plain(rows).length, 'should return all 6 seeded rows').to.equal(SEED.length);
                assertOrdered(rows);
                // Exact expected order given the fixed seed:
                //  3 Cheap Snack / 5 Basic Pen / 10 Pro Keyboard / 10 Pro Mouse / 20 Pro Pen / 20 Wonder Toy
                expect(names(rows)).to.deep.equal([
                  'Cheap Snack', 'Basic Pen', 'Pro Keyboard', 'Pro Mouse', 'Pro Pen', 'Wonder Toy',
                ]);
              });

              it('undefined filter behaves like an empty filter', async () => {
                const { Product } = await freshCatalog();
                const rows = await searchProducts(Product as any, undefined as any);
                expect(plain(rows).length).to.equal(SEED.length);
                assertOrdered(rows);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-empty.test.ts", spec)
        _assert_mocha_passed(result, "empty/undefined filter returns all ordered")

    def test_price_range_inclusive_boundaries(self):
        """{minPrice,maxPrice} keeps only rows in [min,max], boundaries INCLUDED."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('product-search: price range', () => {
              it('{ minPrice:10, maxPrice:20 } includes boundary rows', async () => {
                const { Product } = await freshCatalog();
                const rows = await searchProducts(Product as any, { minPrice: 10, maxPrice: 20 } as any);
                const got = plain(rows);
                // price 5 and 3 excluded; 10 and 20 boundaries included.
                expect(got.every((r: any) => r.price >= 10 && r.price <= 20),
                  'a row falls outside [10,20]: ' + JSON.stringify(got)).to.equal(true);
                expect(names(rows)).to.deep.equal([
                  'Pro Keyboard', 'Pro Mouse', 'Pro Pen', 'Wonder Toy',
                ]);
                assertOrdered(rows);
              });

              it('minPrice alone keeps price >= value', async () => {
                const { Product } = await freshCatalog();
                const rows = await searchProducts(Product as any, { minPrice: 20 } as any);
                expect(plain(rows).every((r: any) => r.price >= 20)).to.equal(true);
                expect(names(rows)).to.deep.equal(['Pro Pen', 'Wonder Toy']);
              });

              it('maxPrice alone keeps price <= value', async () => {
                const { Product } = await freshCatalog();
                const rows = await searchProducts(Product as any, { maxPrice: 5 } as any);
                expect(plain(rows).every((r: any) => r.price <= 5)).to.equal(true);
                expect(names(rows)).to.deep.equal(['Cheap Snack', 'Basic Pen']);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-price.test.ts", spec)
        _assert_mocha_passed(result, "inclusive price-range boundaries")

    def test_categories_filter_and_empty_array(self):
        """{categories:[...]} keeps only listed categories; [] yields ZERO rows."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('product-search: categories', () => {
              it('{ categories:["books","toys"] } keeps only those categories', async () => {
                const { Product } = await freshCatalog();
                const rows = await searchProducts(Product as any, { categories: ['books', 'toys'] } as any);
                const got = plain(rows);
                expect(got.length).to.be.greaterThan(0);
                expect(got.every((r: any) => r.category === 'books' || r.category === 'toys'),
                  'food row leaked in: ' + JSON.stringify(got)).to.equal(true);
                // 'food' (Cheap Snack) must be excluded.
                expect(names(rows)).to.not.include('Cheap Snack');
                expect(names(rows)).to.deep.equal([
                  'Basic Pen', 'Pro Keyboard', 'Pro Mouse', 'Pro Pen', 'Wonder Toy',
                ]);
                assertOrdered(rows);
              });

              it('a single-category list narrows correctly', async () => {
                const { Product } = await freshCatalog();
                const rows = await searchProducts(Product as any, { categories: ['food'] } as any);
                expect(names(rows)).to.deep.equal(['Cheap Snack']);
              });

              it('{ categories: [] } yields zero rows', async () => {
                const { Product } = await freshCatalog();
                const rows = await searchProducts(Product as any, { categories: [] } as any);
                expect(plain(rows).length,
                  'empty categories array must match nothing').to.equal(0);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-categories.test.ts", spec)
        _assert_mocha_passed(result, "categories filter + empty-array zero rows")

    def test_name_contains_case_sensitive(self):
        """{nameContains} matches a case-sensitive substring of name."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('product-search: nameContains', () => {
              it('{ nameContains:"Pro" } keeps only names containing "Pro"', async () => {
                const { Product } = await freshCatalog();
                const rows = await searchProducts(Product as any, { nameContains: 'Pro' } as any);
                const got = plain(rows);
                expect(got.length).to.be.greaterThan(0);
                expect(got.every((r: any) => String(r.name).includes('Pro')),
                  'a non-Pro name leaked in: ' + JSON.stringify(got)).to.equal(true);
                expect(names(rows)).to.deep.equal(['Pro Keyboard', 'Pro Mouse', 'Pro Pen']);
                assertOrdered(rows);
              });

              it('a substring matching nothing returns zero rows', async () => {
                const { Product } = await freshCatalog();
                const rows = await searchProducts(Product as any, { nameContains: 'ZZZZ' } as any);
                expect(plain(rows).length).to.equal(0);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-name.test.ts", spec)
        _assert_mocha_passed(result, "nameContains substring filter")

    def test_in_stock_only_filter(self):
        """{inStockOnly:true} excludes out-of-stock rows; false/absent does not restrict."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('product-search: inStockOnly', () => {
              it('{ inStockOnly:true } excludes out-of-stock products', async () => {
                const { Product } = await freshCatalog();
                const rows = await searchProducts(Product as any, { inStockOnly: true } as any);
                const got = plain(rows);
                expect(got.every((r: any) => r.inStock === true),
                  'an out-of-stock row leaked in: ' + JSON.stringify(got)).to.equal(true);
                // Out-of-stock: Pro Keyboard, Cheap Snack -> excluded.
                expect(names(rows)).to.not.include('Pro Keyboard');
                expect(names(rows)).to.not.include('Cheap Snack');
                expect(names(rows)).to.deep.equal(['Basic Pen', 'Pro Mouse', 'Pro Pen', 'Wonder Toy']);
                assertOrdered(rows);
              });

              it('{ inStockOnly:false } does NOT restrict on stock', async () => {
                const { Product } = await freshCatalog();
                const rows = await searchProducts(Product as any, { inStockOnly: false } as any);
                expect(plain(rows).length,
                  'inStockOnly:false must keep all rows').to.equal(SEED.length);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-instock.test.ts", spec)
        _assert_mocha_passed(result, "inStockOnly filter semantics")

    def test_combined_filter_anded_with_ordering(self):
        """A combined filter applies every constraint with AND and the required ordering."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('product-search: combined AND filter', () => {
              it('nameContains + categories + price range + inStockOnly all AND together', async () => {
                const { Product } = await freshCatalog();
                const filter = {
                  nameContains: 'Pro',
                  categories: ['toys', 'books'],
                  minPrice: 10,
                  maxPrice: 20,
                  inStockOnly: true,
                };
                const rows = await searchProducts(Product as any, filter as any);
                const got = plain(rows);
                // Apply each constraint independently and confirm AND semantics:
                expect(got.every((r: any) =>
                  String(r.name).includes('Pro') &&
                  (r.category === 'toys' || r.category === 'books') &&
                  r.price >= 10 && r.price <= 20 &&
                  r.inStock === true),
                  'a row violates the combined AND constraints: ' + JSON.stringify(got)
                ).to.equal(true);
                // Expected survivors from the fixed seed:
                //  Pro Mouse (10/toys/inStock)   -> kept
                //  Pro Keyboard (10/toys/!stock) -> dropped by inStockOnly
                //  Pro Pen (20/books/inStock)    -> kept
                expect(names(rows)).to.deep.equal(['Pro Mouse', 'Pro Pen']);
                assertOrdered(rows);
              });

              it('a combined filter that excludes everything returns zero rows', async () => {
                const { Product } = await freshCatalog();
                const rows = await searchProducts(Product as any, {
                  categories: ['food'], inStockOnly: true,
                } as any);
                // The only 'food' row (Cheap Snack) is out of stock -> nothing.
                expect(plain(rows).length).to.equal(0);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-combined.test.ts", spec, timeout=600)
        _assert_mocha_passed(result, "combined AND filter + ordering")

    def test_ordering_tiebreak_on_name(self):
        """Rows with equal price are ordered by name ascending (tie-break)."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('product-search: name tie-break ordering', () => {
              it('equal-price rows come out name-ascending', async () => {
                const { Product } = await freshCatalog();
                // Restrict to the two price-10 rows; they must be name-ordered.
                const rows = await searchProducts(Product as any, { minPrice: 10, maxPrice: 10 } as any);
                expect(names(rows)).to.deep.equal(['Pro Keyboard', 'Pro Mouse']);
                assertOrdered(rows);
              });

              it('the two price-20 rows are also name-ordered', async () => {
                const { Product } = await freshCatalog();
                const rows = await searchProducts(Product as any, { minPrice: 20, maxPrice: 20 } as any);
                expect(names(rows)).to.deep.equal(['Pro Pen', 'Wonder Toy']);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-tiebreak.test.ts", spec)
        _assert_mocha_passed(result, "price-tie name-ascending tie-break")

    def test_agent_supplied_test_passes(self):
        """The agent's own acceptance command must pass: yarn mocha product-search.test.ts."""
        result = _run_mocha(
            os.path.join("test", "integration", "product-search.test.ts"),
            timeout=600,
        )
        _assert_mocha_passed(result, "agent-supplied product-search.test.ts")
