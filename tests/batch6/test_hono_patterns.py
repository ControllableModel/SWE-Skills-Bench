"""Tests for the `hono-patterns` skill task (variant ext6): a paginated catalog query module.

Verifies the deliverable `src/helper/catalog/index.ts` (and its colocated
`index.test.ts`) inside the Hono repo at /workspace/hono.

The task: export a factory `createCatalog(items)` accepting an array of products
`{ id, name, price, category }` and returning a fresh, mountable Hono sub-application
that serves a single read-only listing route at the collection root. That route reads
query parameters to FILTER (`category` exact/case-sensitive, `maxPrice` <=), SORT
(`price` ascending, `-price` descending; original order when absent), and PAGINATE
(`page` default 1, `pageSize` default 10, 1-based slicing). The JSON body shape is
`{ items, total, page, pageSize }` where `total` is the filtered count BEFORE pagination.
Non-positive-integer `page`/`pageSize` -> 400 `{ error }`. Two `createCatalog()` calls
hold independent item sets. The contract must hold both directly and when mounted under
a non-empty prefix.

Strategy
--------
- L1: the required deliverable files exist and are minimally well-formed (export the
  `createCatalog` factory, register a GET listing route, ship a colocated vitest test).
- L2: DYNAMIC EXECUTION. We write an *independent* vitest spec into the repo that imports
  the agent's `createCatalog()` and exercises every requirement by dispatching IN-MEMORY
  requests via `app.request(...)` against BOTH a directly-used and a mounted-under-a-prefix
  instance, asserting on the real JSON / status codes the module returns:
  default pagination, explicit page/pageSize slicing (1-based), total = filtered count,
  category filter (exact, case-sensitive), maxPrice filter (<=, boundary), combined
  filters, ascending/descending sort applied before pagination, sort-absent stable order,
  page-beyond-results empty slice with correct total, 400 validation for non-positive /
  non-integer page & pageSize, and instance isolation.

  A naive implementation (ignoring pagination, returning the page-slice length as `total`,
  dropping filters, mis-ordering sort, skipping validation, or sharing a global store)
  fails one or more named cases.

  To keep runtime bounded we run the independent spec ONCE with vitest's JSON reporter,
  cache the per-test results module-wide, and have each L2 Python test assert on one
  specific named case (and that the case actually executed — a missing case is treated as
  a failure, so a solution can't pass by making cases disappear).

- The agent's OWN colocated suite is checked separately: it must contain >=10 cases and
  pass, per the acceptance criteria.

Native test command (per task acceptance criteria):
    npx vitest --run src/helper/catalog/index.test.ts
"""

import json
import os
import subprocess
import textwrap

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - fallback if helper not co-located
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/hono"
MODULE_DIR = os.path.join(REPO_DIR, "src", "helper", "catalog")
MODULE_TS = os.path.join(MODULE_DIR, "index.ts")
MODULE_TEST_TS = os.path.join(MODULE_DIR, "index.test.ts")

# Independent verification spec (unique name; never clobbers agent files).
VERIFY_SPEC = os.path.join(MODULE_DIR, "__bench_verify.test.ts")

NPX = "npx"


@pytest.fixture(scope="module", autouse=True)
def _install_deps():
    """Install repo node deps once before running native vitest."""
    if ensure_npm_dependencies is not None:
        ensure_npm_dependencies(REPO_DIR)
    yield


def _run_vitest(rel_spec, timeout, json_out=None):
    """Run vitest --run on a single spec relative to REPO_DIR.

    Coverage is disabled and the run is scoped to the `main` project to keep
    startup cheap (the repo's default vitest config enables v8 coverage and loads
    several runtime-test projects, which is needlessly slow for one spec).
    """
    cmd = [NPX, "vitest", "--run", "--project", "main", "--coverage.enabled=false"]
    if json_out:
        cmd += ["--reporter=json", f"--outputFile={json_out}"]
    cmd.append(rel_spec)
    result = subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "CI": "true"},
    )
    if result.returncode != 0 and "No test files found" in (result.stdout + result.stderr):
        # Some vitest CLIs reject --project on non-workspace runs; retry plainly.
        cmd = [NPX, "vitest", "--run", "--coverage.enabled=false"]
        if json_out:
            cmd += ["--reporter=json", f"--outputFile={json_out}"]
        cmd.append(rel_spec)
        result = subprocess.run(
            cmd,
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "CI": "true"},
        )
    return result


# ---------------------------------------------------------------------------
# The single comprehensive independent verification spec. Each `it(<name>, ...)`
# maps to one task requirement; the Python L2 tests below assert on these names.
#
# A fixed, deterministic catalog of 5 products is used throughout. Original input
# order: A,B,C,D,E so that sort/order checks are unambiguous.
#   A widget   12  tools
#   B gadget    5  tools
#   C novel    10  books
#   D atlas     8  books
#   E manual   20  books
# ---------------------------------------------------------------------------
_VERIFY_SPEC_SRC = textwrap.dedent(
    """
    import { describe, it, expect } from 'vitest'
    import { Hono } from '../../hono'
    import { createCatalog } from '.'

    const base = 'http://localhost'

    const ITEMS = [
      { id: 'A', name: 'widget', price: 12, category: 'tools' },
      { id: 'B', name: 'gadget', price: 5,  category: 'tools' },
      { id: 'C', name: 'novel',  price: 10, category: 'books' },
      { id: 'D', name: 'atlas',  price: 8,  category: 'books' },
      { id: 'E', name: 'manual', price: 20, category: 'books' },
    ]

    const PREFIX = '/api/catalog'

    // Resource mounted under a non-empty prefix.
    const mounted = (items = ITEMS) => {
      const app = new Hono()
      app.route(PREFIX, createCatalog(items))
      return app
    }
    // Same resource used DIRECTLY (no prefix) at its own root.
    const direct = (items = ITEMS) => createCatalog(items)

    const getMounted = (app, qs = '') => app.request(base + PREFIX + qs)
    const getDirect = (app, qs = '') => app.request(base + '/' + qs)

    const ids = (arr) => arr.map((x) => x.id)

    describe('catalog verification', () => {
      it('default_listing_shape_and_defaults', async () => {
        const app = mounted()
        const res = await getMounted(app)
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(Array.isArray(body.items)).toBe(true)
        expect(body.total).toBe(5)
        expect(body.page).toBe(1)
        expect(body.pageSize).toBe(10)
        // all 5 fit on the default page, preserving input order
        expect(ids(body.items)).toEqual(['A', 'B', 'C', 'D', 'E'])
      })

      it('pagination_one_based_slice', async () => {
        const app = mounted()
        // page=2, pageSize=2 -> zero-based indices 2 and 3 of filtered result
        const res = await getMounted(app, '?pageSize=2&page=2')
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body.page).toBe(2)
        expect(body.pageSize).toBe(2)
        expect(body.total).toBe(5)
        expect(ids(body.items)).toEqual(['C', 'D'])
      })

      it('total_is_filtered_count_not_slice_length', async () => {
        const app = mounted()
        const res = await getMounted(app, '?pageSize=2&page=1')
        const body = await res.json()
        // slice length is 2 but total must report the full (filtered) count = 5
        expect(body.items.length).toBe(2)
        expect(body.total).toBe(5)
      })

      it('page_beyond_results_empty_with_total', async () => {
        const app = mounted()
        const res = await getMounted(app, '?pageSize=2&page=99')
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body.items).toEqual([])
        expect(body.total).toBe(5)
        expect(body.page).toBe(99)
        expect(body.pageSize).toBe(2)
      })

      it('category_filter_exact', async () => {
        const app = mounted()
        const res = await getMounted(app, '?category=books')
        const body = await res.json()
        expect(body.total).toBe(3)
        expect(ids(body.items).sort()).toEqual(['C', 'D', 'E'])
        body.items.forEach((x) => expect(x.category).toBe('books'))
      })

      it('category_filter_case_sensitive_no_match', async () => {
        const app = mounted()
        // exact, case-sensitive: 'Books' must match nothing
        const res = await getMounted(app, '?category=Books')
        const body = await res.json()
        expect(body.total).toBe(0)
        expect(body.items).toEqual([])
      })

      it('maxprice_filter_inclusive_boundary', async () => {
        const app = mounted()
        // price <= 10 -> B(5), D(8), C(10) ; excludes A(12), E(20)
        const res = await getMounted(app, '?maxPrice=10')
        const body = await res.json()
        expect(body.total).toBe(3)
        expect(ids(body.items).sort()).toEqual(['B', 'C', 'D'])
        body.items.forEach((x) => expect(x.price).toBeLessThanOrEqual(10))
      })

      it('combined_category_and_maxprice', async () => {
        const app = mounted()
        // books AND price<=10 -> C(10,books), D(8,books) ; E(20) excluded, tools excluded
        const res = await getMounted(app, '?maxPrice=10&category=books')
        const body = await res.json()
        expect(body.total).toBe(2)
        expect(ids(body.items).sort()).toEqual(['C', 'D'])
      })

      it('sort_ascending_price', async () => {
        const app = mounted()
        const res = await getMounted(app, '?sort=price&pageSize=10')
        const body = await res.json()
        expect(body.total).toBe(5)
        // ascending by price: B5, D8, C10, A12, E20
        expect(ids(body.items)).toEqual(['B', 'D', 'C', 'A', 'E'])
        const prices = body.items.map((x) => x.price)
        expect(prices).toEqual([...prices].sort((a, b) => a - b))
      })

      it('sort_descending_price', async () => {
        const app = mounted()
        const res = await getMounted(app, '?sort=-price&pageSize=10')
        const body = await res.json()
        // descending by price: E20, A12, C10, D8, B5
        expect(ids(body.items)).toEqual(['E', 'A', 'C', 'D', 'B'])
      })

      it('sort_applied_before_pagination', async () => {
        const app = mounted()
        // descending sort then page 2 of pageSize 2 -> 3rd & 4th of E,A,C,D,B = C,D
        const res = await getMounted(app, '?sort=-price&pageSize=2&page=2')
        const body = await res.json()
        expect(body.total).toBe(5)
        expect(ids(body.items)).toEqual(['C', 'D'])
      })

      it('sort_absent_preserves_input_order', async () => {
        const app = mounted()
        const res = await getMounted(app, '?pageSize=10')
        const body = await res.json()
        expect(ids(body.items)).toEqual(['A', 'B', 'C', 'D', 'E'])
      })

      it('validation_page_zero_400', async () => {
        const app = mounted()
        const res = await getMounted(app, '?page=0')
        expect(res.status).toBe(400)
        const body = await res.json()
        expect(typeof body.error).toBe('string')
      })

      it('validation_negative_and_noninteger_400', async () => {
        const app = mounted()
        const neg = await getMounted(app, '?page=-1')
        expect(neg.status).toBe(400)
        const frac = await getMounted(app, '?pageSize=2.5')
        expect(frac.status).toBe(400)
        const nan = await getMounted(app, '?pageSize=abc')
        expect(nan.status).toBe(400)
        const zeroSize = await getMounted(app, '?pageSize=0')
        expect(zeroSize.status).toBe(400)
        for (const r of [neg, frac, nan, zeroSize]) {
          expect(typeof (await r.json()).error).toBe('string')
        }
      })

      it('direct_use_matches_mounted', async () => {
        // The contract must hold when the sub-app is used directly at its own root.
        const app = direct()
        const res = await getDirect(app, '?category=books&sort=price')
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body.total).toBe(3)
        // ascending books by price: D8, C10, E20
        expect(ids(body.items)).toEqual(['D', 'C', 'E'])
      })

      it('instances_are_isolated', async () => {
        const a = createCatalog([{ id: 'X', name: 'x', price: 1, category: 'c' }])
        const b = createCatalog([])
        const ra = await a.request(base + '/')
        const rb = await b.request(base + '/')
        const ba = await ra.json()
        const bb = await rb.json()
        expect(ba.total).toBe(1)
        expect(ids(ba.items)).toEqual(['X'])
        expect(bb.total).toBe(0)
        expect(bb.items).toEqual([])
      })
    })
    """
)


def _collect_assertion_results(json_path):
    """Parse vitest JSON output into {test_title: 'passed'|'failed'|...}."""
    with open(json_path) as f:
        report = json.load(f)
    results = {}
    for suite in report.get("testResults", []):
        for assertion in suite.get("assertionResults", []):
            results[assertion.get("title")] = assertion.get("status")
    return results


# Module-scoped cache so the independent spec runs exactly once.
_VERIFY_CACHE = {}


def _verify_results():
    if _VERIFY_CACHE:
        return _VERIFY_CACHE["results"]
    os.makedirs(MODULE_DIR, exist_ok=True)
    with open(VERIFY_SPEC, "w") as f:
        f.write(_VERIFY_SPEC_SRC)
    json_path = os.path.join(REPO_DIR, "__bench_verify_report.json")
    try:
        proc = _run_vitest(
            "src/helper/catalog/__bench_verify.test.ts", timeout=600, json_out=json_path
        )
        assert os.path.isfile(json_path), (
            "vitest produced no JSON report; the independent verification spec "
            "failed to run (likely a compile/import error in the module).\n"
            f"STDOUT:\n{proc.stdout[-4000:]}\nSTDERR:\n{proc.stderr[-3000:]}"
        )
        results = _collect_assertion_results(json_path)
    finally:
        for p in (VERIFY_SPEC, json_path):
            try:
                os.remove(p)
            except OSError:
                pass
    _VERIFY_CACHE["results"] = results
    _VERIFY_CACHE["proc"] = proc
    return results


def _assert_case(name):
    """Assert a named verification case ran and passed."""
    results = _verify_results()
    status = results.get(name)
    assert status is not None, (
        f"verification case {name!r} did not run; available cases: "
        f"{sorted(results.keys())}\nvitest stderr:\n"
        f"{_VERIFY_CACHE.get('proc').stderr[-2000:] if _VERIFY_CACHE.get('proc') else ''}"
    )
    assert status == "passed", f"verification case {name!r} status={status} (expected passed)"


class TestHonoPatterns:
    REPO_DIR = "/workspace/hono"

    # ------------------------------------------------------------- L1 ----

    def test_module_file_exists(self):
        """L1: the catalog module file is present."""
        assert os.path.isfile(MODULE_TS), f"missing deliverable {MODULE_TS}"

    def test_module_exports_factory(self):
        """L1: module source exports a `createCatalog` factory."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert "createCatalog" in src, "createCatalog not found"
        assert "export" in src, "factory not exported"

    def test_module_registers_get_listing_route(self):
        """L1: module registers a GET route for the read-only listing."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert ".get(" in src, "module does not register a GET listing route"

    def test_colocated_test_file_exists(self):
        """L1: the colocated deterministic test file exists."""
        assert os.path.isfile(MODULE_TEST_TS), f"missing {MODULE_TEST_TS}"

    def test_agent_suite_has_min_cases_and_passes(self):
        """L2/acceptance: agent's colocated suite has >=10 cases and passes via vitest."""
        with open(MODULE_TEST_TS) as f:
            test_src = f.read()
        case_count = test_src.count("it(") + test_src.count("test(")
        assert case_count >= 10, (
            f"colocated suite has only {case_count} cases; task requires >=10"
        )
        result = _run_vitest("src/helper/catalog/index.test.ts", timeout=600)
        assert result.returncode == 0, (
            "agent's colocated vitest suite failed:\n"
            f"STDOUT:\n{result.stdout[-4000:]}\nSTDERR:\n{result.stderr[-3000:]}"
        )

    # ------------------------------------------------------------- L2 ----
    # Each maps to one task requirement, verified by the independent spec.

    def test_default_listing_shape_and_defaults(self):
        """L2: GET root -> 200 {items,total,page,pageSize}; page/pageSize default 1/10."""
        _assert_case("default_listing_shape_and_defaults")

    def test_pagination_one_based_slice(self):
        """L2: page=2,pageSize=2 returns the 1-based 3rd & 4th filtered items."""
        _assert_case("pagination_one_based_slice")

    def test_total_is_filtered_count_not_slice_length(self):
        """L2: `total` reports the full filtered count, not the page-slice length."""
        _assert_case("total_is_filtered_count_not_slice_length")

    def test_page_beyond_results_empty_with_total(self):
        """L2: a page past the end returns 200, empty items, and the correct total."""
        _assert_case("page_beyond_results_empty_with_total")

    def test_category_filter_exact(self):
        """L2: ?category restricts to exactly-matching items; total reflects the filter."""
        _assert_case("category_filter_exact")

    def test_category_filter_case_sensitive_no_match(self):
        """L2: category matching is case-sensitive (wrong case yields zero results)."""
        _assert_case("category_filter_case_sensitive_no_match")

    def test_maxprice_filter_inclusive_boundary(self):
        """L2: ?maxPrice keeps items with price <= value, inclusive of the boundary."""
        _assert_case("maxprice_filter_inclusive_boundary")

    def test_combined_category_and_maxprice(self):
        """L2: both filters present -> only items satisfying BOTH are returned."""
        _assert_case("combined_category_and_maxprice")

    def test_sort_ascending_price(self):
        """L2: sort=price orders filtered items by ascending price before pagination."""
        _assert_case("sort_ascending_price")

    def test_sort_descending_price(self):
        """L2: sort=-price orders filtered items by descending price."""
        _assert_case("sort_descending_price")

    def test_sort_applied_before_pagination(self):
        """L2: sorting happens before slicing (sorted then paginated page is correct)."""
        _assert_case("sort_applied_before_pagination")

    def test_sort_absent_preserves_input_order(self):
        """L2: with no sort param the original input order is preserved."""
        _assert_case("sort_absent_preserves_input_order")

    def test_validation_page_zero_400(self):
        """L2: page=0 (non-positive) -> 400 {error}."""
        _assert_case("validation_page_zero_400")

    def test_validation_negative_and_noninteger_400(self):
        """L2: negative / fractional / non-numeric / zero page & pageSize -> 400 {error}."""
        _assert_case("validation_negative_and_noninteger_400")

    def test_direct_use_matches_mounted(self):
        """L2: the contract holds when the sub-app is used directly at its own root."""
        _assert_case("direct_use_matches_mounted")

    def test_instances_are_isolated(self):
        """L2: two createCatalog() calls hold independent item sets."""
        _assert_case("instances_are_isolated")
