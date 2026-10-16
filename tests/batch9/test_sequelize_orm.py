"""
Test for the 'sequelize-orm' skill (variant ext9) — Compute Sales Aggregates by Region.

The agent must create two files inside @sequelize/core's *integration*-test tree:
  - packages/core/test/integration/sales-summary.ts        (the domain module)
  - packages/core/test/integration/sales-summary.test.ts   (its integration test)

The module exports:
  - setupSales(sequelize)  -> defines and returns the `Sale` model and creates
                              its table. Sale has fields region (text, required),
                              amount (integer, required), completed (boolean,
                              default true).
  - regionSummary(Sale)    -> per-region aggregates over COMPLETED rows only.
                              Each entry: { region, count, total, max, min }.
                              Ordered by total DESC, region ASC as tie-break.
                              Numeric fields must be JS numbers (not strings).
                              Regions with no completed sales are excluded.
                              No completed sales at all -> [].

Verification strategy
---------------------
L1 cases check the deliverable files exist and are minimally well-formed
(correct directory, exported symbols, the test imports the module).

L2 cases DO NOT trust the agent's own test file. Instead we drop an independent
mocha integration spec into the repo that *imports the agent's sales-summary
module*, seeds a fixed deterministic dataset (including non-completed rows and a
deliberate tie in totals) against the default in-process test database, and
asserts the exact aggregate values, numeric (non-string) typing, the
total-desc / region-asc ordering, exclusion of all-incomplete regions, and the
empty-array case. Each spec is run via the repository's native command:

    yarn mocha "test/integration/<spec>.test.ts"

A naive implementation that counts all rows (ignores `completed`), returns
aggregates as strings, or omits the ordering MUST fail these assertions.
"""

import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/sequelize"
CORE_DIR = os.path.join(REPO_DIR, "packages", "core")
INT_DIR = os.path.join(CORE_DIR, "test", "integration")
MODULE_FILE = os.path.join(INT_DIR, "sales-summary.ts")
AGENT_TEST_FILE = os.path.join(INT_DIR, "sales-summary.test.ts")

# Basename for our own independently injected specs (relative to CORE_DIR glob).
_BENCH_BASENAME = "zzz-bench-sales-summary"


def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _run_mocha(spec_rel_path, timeout=900):
    """Run one mocha spec from packages/core using the repo's native command."""
    cmd = ["yarn", "mocha", spec_rel_path]
    return subprocess.run(
        cmd,
        cwd=CORE_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _write_spec_and_run(spec_name, spec_body, timeout=900):
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


# Common TS preamble used by every independent integration spec.
#
# It pulls a fresh, auto-disposed Sequelize from the integration support module,
# imports the agent's factory, and provides a seeding helper that:
#   * calls setupSales(sequelize) to get the Sale model + create its table,
#   * bulk-inserts a deterministic dataset, and
#   * returns the Sale model so each spec can call regionSummary(Sale).
#
# Seed dataset (chosen to exercise every requirement):
#   east:  completed 100, 50, 30  + an incomplete 9999  -> count 3 total 180 max 100 min 30
#   west:  completed 120, 60      + an incomplete 8888  -> count 2 total 180 max 120 min 60
#   north: incomplete 70 ONLY                            -> excluded entirely
# east.total == west.total == 180  -> TIE, must order region ASC => east before west.
_PREAMBLE = textwrap.dedent(
    """\
    import { expect } from 'chai';
    import { createSingleTestSequelizeInstance } from './support';
    import { setupSales, regionSummary } from './sales-summary';

    async function seedDefault() {
      const sequelize = createSingleTestSequelizeInstance();
      const Sale = await setupSales(sequelize as any);
      await (Sale as any).bulkCreate([
        { region: 'east',  amount: 100, completed: true },
        { region: 'east',  amount: 50,  completed: true },
        { region: 'east',  amount: 30,  completed: true },
        { region: 'east',  amount: 9999, completed: false },
        { region: 'west',  amount: 120, completed: true },
        { region: 'west',  amount: 60,  completed: true },
        { region: 'west',  amount: 8888, completed: false },
        { region: 'north', amount: 70,  completed: false },
      ]);
      return { sequelize, Sale };
    }

    function byRegion(rows: any[]): Record<string, any> {
      const out: Record<string, any> = {};
      for (const r of rows) out[r.region] = r;
      return out;
    }
    """
)


# ---------------------------------------------------------------------------
# Module-scope dependency guard. Ensure node_modules is present (best-effort)
# so the native `yarn mocha` command can resolve mocha/chai/esbuild + dialect.
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
            # If install fails, the native test calls below surface a clear error.
            pass
    yield


class TestSequelizeOrm:
    """Verify the sales-aggregates-by-region deliverable (variant ext9)."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """The domain module sales-summary.ts must exist in the integration tree."""
        assert os.path.isfile(MODULE_FILE), f"missing module file: {MODULE_FILE}"

    def test_agent_test_file_exists(self):
        """The agent's own integration test sales-summary.test.ts must exist."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing test file: {AGENT_TEST_FILE}"

    def test_module_exports_required_symbols(self):
        """sales-summary.ts must export both `setupSales` and `regionSummary`."""
        src = _read(MODULE_FILE)
        assert "export" in src, "module does not export anything"
        assert "setupSales" in src, "setupSales not found in module"
        assert "regionSummary" in src, "regionSummary not found in module"

    def test_agent_test_imports_module(self):
        """The agent's test must import from the local sales-summary module."""
        src = _read(AGENT_TEST_FILE)
        assert "sales-summary" in src, "test does not reference the sales-summary module"
        # It must actually exercise the summary, not just define a model.
        assert "regionSummary" in src, "agent test does not call regionSummary"

    # ------------------------------------------------------------------
    # L2 — independent dynamic execution via native `yarn mocha`.
    # Each test writes its own spec so failures are isolated and specific.
    # All assertions run against the default in-process test database.
    # ------------------------------------------------------------------

    def test_setup_returns_sale_model_with_fields(self):
        """setupSales returns a real Sale model carrying region/amount/completed columns."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('sales-summary: model shape', () => {
              it('returns a Sale model with the required attributes', async () => {
                const sequelize = createSingleTestSequelizeInstance();
                const Sale: any = await setupSales(sequelize as any);
                expect(Sale, 'setupSales returned nothing').to.exist;
                expect(typeof Sale.bulkCreate, 'not a Sequelize model').to.equal('function');
                expect(typeof Sale.findAll, 'not a Sequelize model').to.equal('function');
                const attrs: any = Sale.getAttributes();
                expect(attrs, 'Sale missing region column').to.have.property('region');
                expect(attrs, 'Sale missing amount column').to.have.property('amount');
                expect(attrs, 'Sale missing completed column').to.have.property('completed');
              });

              it('defaults completed to true when omitted', async () => {
                const sequelize = createSingleTestSequelizeInstance();
                const Sale: any = await setupSales(sequelize as any);
                const row: any = await Sale.create({ region: 'east', amount: 5 });
                expect(row.completed, 'completed should default to true').to.equal(true);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-shape.test.ts", spec)
        _assert_mocha_passed(result, "Sale model shape / completed default")

    def test_excludes_incomplete_rows_from_counts(self):
        """regionSummary counts only completed rows; incomplete amounts never inflate totals."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('sales-summary: completed-only aggregation', () => {
              it('ignores completed=false rows in count/total/max/min', async () => {
                const { Sale } = await seedDefault();
                const result: any[] = await regionSummary(Sale);
                const m = byRegion(result);

                expect(m.east, 'east entry missing').to.exist;
                expect(m.west, 'west entry missing').to.exist;

                // east completed: 100, 50, 30  (the 9999 incomplete must be ignored)
                expect(m.east.count, 'east count must exclude incomplete').to.equal(3);
                expect(m.east.total, 'east total must exclude incomplete').to.equal(180);
                expect(m.east.max, 'east max must exclude the 9999 incomplete').to.equal(100);
                expect(m.east.min).to.equal(30);

                // west completed: 120, 60  (the 8888 incomplete must be ignored)
                expect(m.west.count).to.equal(2);
                expect(m.west.total).to.equal(180);
                expect(m.west.max, 'west max must exclude the 8888 incomplete').to.equal(120);
                expect(m.west.min).to.equal(60);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-completed.test.ts", spec)
        _assert_mocha_passed(result, "completed-only aggregation")

    def test_all_incomplete_region_is_excluded(self):
        """A region whose only sales are completed=false must NOT appear in the result."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('sales-summary: all-incomplete region excluded', () => {
              it('drops north (only completed=false rows)', async () => {
                const { Sale } = await seedDefault();
                const result: any[] = await regionSummary(Sale);
                const regions = result.map((r: any) => r.region);
                expect(regions, 'north must not appear').to.not.include('north');
                // Exactly the two regions that have completed sales.
                expect(regions.slice().sort()).to.deep.equal(['east', 'west']);
                expect(result.length, 'exactly two qualifying regions').to.equal(2);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-exclude.test.ts", spec)
        _assert_mocha_passed(result, "all-incomplete region excluded")

    def test_numeric_aggregates_are_numbers_not_strings(self):
        """count/total/max/min must be JS numbers, never strings."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('sales-summary: numeric typing', () => {
              it('returns count/total/max/min as numbers', async () => {
                const { Sale } = await seedDefault();
                const result: any[] = await regionSummary(Sale);
                expect(result.length).to.be.greaterThan(0);
                for (const row of result) {
                  for (const field of ['count', 'total', 'max', 'min']) {
                    expect(typeof row[field],
                      `field ${field} for region ${row.region} must be a number, got ` +
                      typeof row[field] + ' (' + JSON.stringify(row[field]) + ')')
                      .to.equal('number');
                    expect(Number.isNaN(row[field]),
                      `field ${field} is NaN for region ${row.region}`).to.equal(false);
                  }
                }
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-numeric.test.ts", spec)
        _assert_mocha_passed(result, "numeric (non-string) aggregate typing")

    def test_ordering_total_desc_with_region_tie_break(self):
        """Results ordered by total DESC; equal totals tie-break by region ASC (east before west)."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('sales-summary: ordering + tie-break', () => {
              it('orders by total desc then region asc on a tie (east==west==180)', async () => {
                const { Sale } = await seedDefault();
                const result: any[] = await regionSummary(Sale);

                // Totals are non-increasing.
                for (let i = 1; i < result.length; i++) {
                  expect(result[i - 1].total,
                    'totals must be non-increasing: ' +
                    JSON.stringify(result.map((r: any) => [r.region, r.total])))
                    .to.be.at.least(result[i].total);
                }

                // east and west both total 180; the tie must resolve region-ascending.
                const eastIdx = result.findIndex((r: any) => r.region === 'east');
                const westIdx = result.findIndex((r: any) => r.region === 'west');
                expect(eastIdx).to.be.greaterThan(-1);
                expect(westIdx).to.be.greaterThan(-1);
                expect(result[eastIdx].total).to.equal(result[westIdx].total);
                expect(eastIdx,
                  'on a total tie, east (region asc) must precede west')
                  .to.be.lessThan(westIdx);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-order.test.ts", spec)
        _assert_mocha_passed(result, "total-desc / region-asc ordering")

    def test_strict_total_desc_ordering_without_tie(self):
        """With distinct totals, the higher-total region comes first regardless of region name."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('sales-summary: strict total-desc ordering', () => {
              it('puts the higher-total region first (alpha-late region wins)', async () => {
                const sequelize = createSingleTestSequelizeInstance();
                const Sale: any = await setupSales(sequelize as any);
                // 'zeta' has a larger total than 'alpha' -> zeta must sort first
                // even though its name is alphabetically last. This kills any
                // implementation that orders by region instead of by total.
                await Sale.bulkCreate([
                  { region: 'alpha', amount: 10, completed: true },
                  { region: 'alpha', amount: 10, completed: true },
                  { region: 'zeta',  amount: 500, completed: true },
                ]);
                const result: any[] = await regionSummary(Sale);
                expect(result.length).to.equal(2);
                expect(result[0].region, 'higher total must come first').to.equal('zeta');
                expect(result[0].total).to.equal(500);
                expect(result[1].region).to.equal('alpha');
                expect(result[1].total).to.equal(20);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-strictorder.test.ts", spec)
        _assert_mocha_passed(result, "strict total-desc ordering (no tie)")

    def test_per_region_min_max_correctness(self):
        """max/min are the true completed extremes per region, not the first/last seen."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('sales-summary: min/max correctness', () => {
              it('computes true completed min and max per region', async () => {
                const sequelize = createSingleTestSequelizeInstance();
                const Sale: any = await setupSales(sequelize as any);
                // Insert out of order with an incomplete outlier on both ends.
                await Sale.bulkCreate([
                  { region: 'r', amount: 40, completed: true },
                  { region: 'r', amount: 99999, completed: false }, // high outlier, ignore
                  { region: 'r', amount: 5,  completed: true },
                  { region: 'r', amount: 1,  completed: false },     // low outlier, ignore
                  { region: 'r', amount: 70, completed: true },
                ]);
                const result: any[] = await regionSummary(Sale);
                expect(result.length).to.equal(1);
                const r = result[0];
                expect(r.region).to.equal('r');
                expect(r.count).to.equal(3);            // 40, 5, 70
                expect(r.total).to.equal(115);
                expect(r.max, 'max must be 70 (ignoring 99999 incomplete)').to.equal(70);
                expect(r.min, 'min must be 5 (ignoring 1 incomplete)').to.equal(5);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-minmax.test.ts", spec)
        _assert_mocha_passed(result, "per-region min/max correctness")

    def test_empty_result_when_no_completed_sales(self):
        """With zero completed sales (only incomplete rows), regionSummary returns []."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('sales-summary: empty result', () => {
              it('returns an empty array when no completed sales exist', async () => {
                const sequelize = createSingleTestSequelizeInstance();
                const Sale: any = await setupSales(sequelize as any);
                await Sale.bulkCreate([
                  { region: 'east', amount: 10, completed: false },
                  { region: 'west', amount: 20, completed: false },
                ]);
                const result: any[] = await regionSummary(Sale);
                expect(Array.isArray(result), 'must return an array').to.equal(true);
                expect(result.length, 'must be empty with no completed sales').to.equal(0);
              });

              it('returns [] on a completely empty table', async () => {
                const sequelize = createSingleTestSequelizeInstance();
                const Sale: any = await setupSales(sequelize as any);
                const result: any[] = await regionSummary(Sale);
                expect(Array.isArray(result)).to.equal(true);
                expect(result.length).to.equal(0);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-empty.test.ts", spec)
        _assert_mocha_passed(result, "empty result when no completed sales")

    def test_single_completed_region_full_aggregate(self):
        """One region with one completed row yields count=1 and total=max=min=amount."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('sales-summary: single completed row', () => {
              it('reports identical total/max/min for a singleton region', async () => {
                const sequelize = createSingleTestSequelizeInstance();
                const Sale: any = await setupSales(sequelize as any);
                await Sale.bulkCreate([
                  { region: 'solo', amount: 42, completed: true },
                  { region: 'solo', amount: 7,  completed: false }, // ignored
                ]);
                const result: any[] = await regionSummary(Sale);
                expect(result.length).to.equal(1);
                const r = result[0];
                expect(r.region).to.equal('solo');
                expect(r.count).to.equal(1);
                expect(r.total).to.equal(42);
                expect(r.max).to.equal(42);
                expect(r.min).to.equal(42);
                expect(typeof r.total).to.equal('number');
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-single.test.ts", spec)
        _assert_mocha_passed(result, "single completed row aggregate")

    def test_agent_supplied_test_passes(self):
        """The agent's own acceptance command must pass: yarn mocha sales-summary.test.ts."""
        result = _run_mocha(
            os.path.join("test", "integration", "sales-summary.test.ts"),
            timeout=900,
        )
        _assert_mocha_passed(result, "agent-supplied sales-summary.test.ts")
