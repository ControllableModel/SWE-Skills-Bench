"""
Tests for the `typeorm-patterns` skill task (variant ext4):
"Build a Sales Analytics Query Layer".

The agent must add, under `test/functional/sales-analytics/`, a self-contained
TypeORM functional feature:
  - entity/Order.ts          (id auto-generated, region:string, product:string,
                              amount:decimal(2dp), quantity:int, placedAt:date)
  - analytics-service.ts     (a class/factory built from a DataSource exposing:
                              revenueByRegion / topProductsByQuantity(limit) /
                              averageOrderValue(region) / regionsAboveThreshold(threshold))
  - sales-analytics.test.ts  (functional test wiring the above through
                              createTestingConnections, sqlite-only)

Every reporting method must compute its numbers via DATABASE-SIDE aggregation
(GROUP BY / SUM / AVG / ORDER BY / LIMIT), NOT by loading all orders and
reducing in JavaScript.

This pytest verifies the deliverables two ways:
  1. L1 — the three files exist and are minimally well-formed (decorated entity
     with generated id + the required columns; service exports the four ops;
     test restricts to the sqlite driver family).
  2. L2 — DYNAMIC EXECUTION against the real TypeORM toolchain: it ensures an
     ormconfig.json restricted to the better-sqlite3 driver, compiles the repo
     (`pnpm run compile` -> `gulp clean && tsc`), runs the agent's own compiled
     functional test under mocha, and then runs INDEPENDENT driver scripts
     (written by this test, compiled in place) against the agent's compiled
     Order / AnalyticsService to deep-validate real behavior:
        * revenueByRegion: one summed row per non-empty region, ordered by region
          ascending, totals equal to JS-side per-region sums
        * topProductsByQuantity(limit): GLOBALLY ordered by total quantity desc,
          aggregated per-product, never exceeding `limit`
        * averageOrderValue(region): correct mean for a known region; null for an
          unknown region
        * regionsAboveThreshold(t): grouped aggregate filter — excludes a region
          whose individual orders each exceed `t` but whose TOTAL does not, and
          includes a region whose total exceeds `t`
     To distinguish a real DB aggregate from a JS-side reduce, one probe monkeypatches
     the DataSource so that `getRepository(Order).find()` throws; a correct
     implementation (query builder / raw SQL) still returns correct numbers, a
     "find-all-then-reduce" implementation blows up.

A naive solution (JS-side summing/averaging, per-author ordering, ignoring the
`limit`, applying the threshold per-row instead of per-aggregate) must fail at
least one assertion.

Native acceptance command this L2 drives (from the doc):
    pnpm run compile && npx mocha ./build/compiled/test/functional/sales-analytics/sales-analytics.test.js
"""

import json
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/typeorm"
FEATURE_DIR = os.path.join(REPO_DIR, "test/functional/sales-analytics")
ENTITY_DIR = os.path.join(FEATURE_DIR, "entity")
ORDER_TS = os.path.join(ENTITY_DIR, "Order.ts")
SERVICE_TS = os.path.join(FEATURE_DIR, "analytics-service.ts")
TEST_TS = os.path.join(FEATURE_DIR, "sales-analytics.test.ts")

COMPILED_TEST_JS = os.path.join(
    REPO_DIR,
    "build/compiled/test/functional/sales-analytics/sales-analytics.test.js",
)
COMPILED_FEATURE_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/sales-analytics"
)

# Build/compile is heavy in this repo.
COMPILE_TIMEOUT = 1200
RUN_TIMEOUT = 600

# Dir (under build/compiled feature dir) where this pytest drops + compiles its
# own independent driver scripts, next to the agent's compiled modules so the
# relative `./` imports resolve to real compiled JS.
PROBE_OUT_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/sales-analytics/__probe__"
)


# ---------------------------------------------------------------------------
# module-scope setup: deps + ormconfig(better-sqlite3) + one compile, shared by L2
# ---------------------------------------------------------------------------

_COMPILE_STATE = {"done": False, "ok": False, "stderr": ""}


def _have(cmd):
    return (
        subprocess.run(
            ["bash", "-lc", f"command -v {cmd}"],
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def _ensure_deps():
    """Install node_modules if missing (prefer pnpm, the repo's package manager)."""
    if os.path.isdir(os.path.join(REPO_DIR, "node_modules", "chai")) and os.path.isdir(
        os.path.join(REPO_DIR, "node_modules", "better-sqlite3")
    ):
        return
    try:
        from _dependency_utils import ensure_npm_dependencies  # type: ignore

        ensure_npm_dependencies(REPO_DIR)
    except Exception:
        pass
    if os.path.isdir(os.path.join(REPO_DIR, "node_modules", "better-sqlite3")):
        return
    if _have("pnpm"):
        installer = "pnpm install --frozen-lockfile || pnpm install"
    elif _have("yarn"):
        installer = "yarn install"
    else:
        installer = "npm install"
    subprocess.run(
        ["bash", "-lc", installer],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=COMPILE_TIMEOUT,
    )


def _ensure_ormconfig():
    """Create ormconfig.json restricted to the better-sqlite3 driver (CI pattern)."""
    sample = os.path.join(REPO_DIR, "ormconfig.sample.json")
    target = os.path.join(REPO_DIR, "ormconfig.json")
    with open(sample) as f:
        data = json.load(f)
    sqlite_like = {"better-sqlite3", "sqlite", "sqljs"}
    filtered = [c for c in data if c.get("type") in sqlite_like]
    bsq = [c for c in filtered if c.get("type") == "better-sqlite3"]
    chosen = bsq if bsq else filtered
    assert chosen, "ormconfig.sample.json has no sqlite-family driver entry"
    with open(target, "w") as f:
        json.dump(chosen, f, indent=2)


def _compile():
    if _COMPILE_STATE["done"]:
        return
    _COMPILE_STATE["done"] = True
    _ensure_deps()
    _ensure_ormconfig()
    if _have("pnpm"):
        cmd = "pnpm run compile"
    else:
        cmd = "npx gulp clean && npx tsc"
    proc = subprocess.run(
        ["bash", "-lc", cmd],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=COMPILE_TIMEOUT,
    )
    _COMPILE_STATE["ok"] = proc.returncode == 0
    _COMPILE_STATE["stderr"] = (proc.stdout or "") + "\n" + (proc.stderr or "")


@pytest.fixture(scope="module", autouse=True)
def _module_setup():
    try:
        _compile()
    except Exception as exc:  # pragma: no cover
        _COMPILE_STATE["ok"] = False
        _COMPILE_STATE["stderr"] = f"compile raised: {exc!r}"
    yield


def _require_compiled():
    assert _COMPILE_STATE["done"], "compile step did not run"
    assert _COMPILE_STATE["ok"], (
        "`pnpm run compile` (gulp clean && tsc) failed; the deliverables must "
        "compile cleanly:\n" + _COMPILE_STATE["stderr"][-4000:]
    )


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Helpers to build & run an independent node driver against the compiled code
# ---------------------------------------------------------------------------

def _write_probe(rel_name, ts_source):
    """Write a TS probe next to the compiled deliverables and return its .js path."""
    os.makedirs(PROBE_OUT_DIR, exist_ok=True)
    ts_path = os.path.join(PROBE_OUT_DIR, rel_name + ".ts")
    with open(ts_path, "w", encoding="utf-8") as f:
        f.write(ts_source)
    tsc = (
        "npx tsc "
        + ts_path
        + " --module commonjs --target ES2021 --experimentalDecorators "
        "--emitDecoratorMetadata --moduleResolution node "
        "--esModuleInterop --skipLibCheck --resolveJsonModule "
        "--strict false --noImplicitAny false"
    )
    proc = subprocess.run(
        ["bash", "-lc", tsc],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=COMPILE_TIMEOUT,
    )
    js_path = os.path.join(PROBE_OUT_DIR, rel_name + ".js")
    assert proc.returncode == 0 and os.path.isfile(js_path), (
        "failed to compile probe driver:\n" + proc.stdout + "\n" + proc.stderr
    )
    return js_path


def _run_node(js_path):
    proc = subprocess.run(
        ["bash", "-lc", "node " + js_path],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
    )
    return proc


def _import_paths():
    """Relative imports from the probe's compiled location to the agent modules.

    Probe sits at build/compiled/test/functional/sales-analytics/__probe__/X.js
    Agent compiled modules sit one dir up; the ORM `src` is 5 levels up.
    """
    return {
        "order": "../entity/Order",
        "service": "../analytics-service",
        "datasource": "../../../../../src",  # build/compiled/src
    }


_DRIVER_PREAMBLE = """
"use strict";
const { DataSource } = require("{datasource}");
const OrderMod = require("{order}");
const ServiceMod = require("{service}");

function pickClass(mod, names) {{
    for (const n of names) if (mod[n]) return mod[n];
    for (const k of Object.keys(mod)) {{
        if (typeof mod[k] === "function") return mod[k];
    }}
    if (mod.default) return mod.default;
    throw new Error("could not locate export in module");
}}

const Order = pickClass(OrderMod, ["Order", "default"]);
const ServiceExport = pickClass(
    ServiceMod,
    ["AnalyticsService", "SalesAnalyticsService", "SalesAnalytics", "Analytics", "default"]
);

function makeService(ds) {{
    // Support both `new Class(ds)` and a factory `fn(ds)`.
    try {{
        return new ServiceExport(ds);
    }} catch (e) {{
        return ServiceExport(ds);
    }}
}}

function buildDataSource(extra) {{
    return new DataSource(Object.assign({{
        type: "better-sqlite3",
        database: ":memory:",
        entities: [Order],
        synchronize: true,
        dropSchema: true,
    }}, extra || {{}}));
}}

async function newDataSource(extra) {{
    const ds = buildDataSource(extra);
    await ds.initialize();
    return ds;
}}

// Insert orders directly via the repository so service-side write helpers are not
// required by the contract; the analytics methods are what we exercise.
async function seed(ds, rows) {{
    const repo = ds.getRepository(Order);
    for (const r of rows) {{
        const e = repo.create(r);
        await repo.save(e);
    }}
}}

function out(obj) {{ process.stdout.write("RESULT_JSON:" + JSON.stringify(obj) + "\\n"); }}
"""


def _driver(body):
    paths = _import_paths()
    preamble = _DRIVER_PREAMBLE.format(
        datasource=paths["datasource"],
        order=paths["order"],
        service=paths["service"],
    )
    return preamble + "\n" + textwrap.dedent(body) + "\n"


def _parse_result(proc):
    assert proc.returncode == 0, (
        "driver script exited non-zero:\nSTDOUT:\n"
        + proc.stdout
        + "\nSTDERR:\n"
        + proc.stderr
    )
    line = None
    for ln in proc.stdout.splitlines():
        if ln.startswith("RESULT_JSON:"):
            line = ln[len("RESULT_JSON:") :]
    assert line is not None, (
        "driver did not emit RESULT_JSON line:\nSTDOUT:\n"
        + proc.stdout
        + "\nSTDERR:\n"
        + proc.stderr
    )
    return json.loads(line)


# A shared dataset across THREE regions used by several probes. Per-region amount
# totals: north = 100 + 50 + 25 = 175 ; south = 300 ; west = 10 + 20 = 30.
_SEED_ROWS = """
                    const SEED = [
                        { region: "north", product: "widget", amount: 100.00, quantity: 3, placedAt: new Date("2021-01-01") },
                        { region: "north", product: "gadget", amount: 50.00, quantity: 5, placedAt: new Date("2021-01-02") },
                        { region: "north", product: "widget", amount: 25.00, quantity: 2, placedAt: new Date("2021-01-03") },
                        { region: "south", product: "gizmo", amount: 300.00, quantity: 1, placedAt: new Date("2021-02-01") },
                        { region: "west", product: "widget", amount: 10.00, quantity: 4, placedAt: new Date("2021-03-01") },
                        { region: "west", product: "gadget", amount: 20.00, quantity: 6, placedAt: new Date("2021-03-02") },
                    ];
"""


# ===========================================================================
# L1 — deliverable files exist and are minimally well-formed
# ===========================================================================


class TestTypeormPatterns:
    REPO_DIR = "/workspace/typeorm"

    # ---- L1 -------------------------------------------------------------

    def test_l1_feature_files_exist(self):
        """The three required deliverable files exist under sales-analytics/."""
        for p in (ORDER_TS, SERVICE_TS, TEST_TS):
            assert os.path.isfile(p), f"missing required deliverable file: {p}"

    def test_l1_order_is_typeorm_entity_with_required_columns(self):
        """Order is a decorated TypeORM entity with a generated id and the domain columns."""
        order = _read(ORDER_TS)
        assert "@Entity" in order, "Order is not annotated with @Entity"
        assert (
            "@PrimaryGeneratedColumn" in order
        ), "Order lacks a database-generated primary key"
        for field in ("region", "product", "amount", "quantity", "placedAt"):
            assert field in order, f"Order entity does not declare a `{field}` field"
        # amount is a two-decimal monetary value -> a decimal/numeric column type.
        low = order.lower()
        assert (
            "decimal" in low or "numeric" in low
        ), "Order.amount must be a decimal/numeric (monetary, 2dp) column"

    def test_l1_service_exports_required_operations(self):
        """analytics-service.ts defines the four named reporting operations."""
        src = _read(SERVICE_TS)
        for op in (
            "revenueByRegion",
            "topProductsByQuantity",
            "averageOrderValue",
            "regionsAboveThreshold",
        ):
            assert op in src, f"analytics-service.ts does not define `{op}`"

    def test_l1_service_uses_db_aggregation_not_js_reduce(self):
        """The service computes reports via DB aggregation (query builder / SUM / GROUP BY)."""
        src = _read(SERVICE_TS)
        low = src.lower()
        # Must show signs of a DB-side aggregate, not a JS .reduce over find().
        aggregate_signals = (
            "createquerybuilder",
            "groupby",
            ".sum(",
            "sum(",
            "avg(",
            ".query(",
        )
        assert any(sig in low for sig in aggregate_signals), (
            "analytics-service.ts shows no sign of database-side aggregation "
            "(expected a QueryBuilder / GROUP BY / SUM / AVG / raw query)"
        )

    def test_l1_test_uses_sqlite_only_testing_connections(self):
        """The functional test restricts testing connections to the SQLite driver family."""
        src = _read(TEST_TS)
        assert "createTestingConnections" in src, (
            "sales-analytics.test.ts must use createTestingConnections from "
            "../../utils/test-utils"
        )
        assert "enabledDrivers" in src, (
            "sales-analytics.test.ts must restrict to SQLite-based driver(s) via "
            "enabledDrivers"
        )
        assert (
            "sqlite" in src or "sqljs" in src
        ), "enabledDrivers must name a sqlite-family driver (better-sqlite3/sqlite/sqljs)"

    # ---- L2: build & agent's own test -----------------------------------

    def test_l2_repo_compiles(self):
        """`pnpm run compile` succeeds with the deliverables in place (tsc, strict)."""
        _require_compiled()
        assert os.path.isfile(COMPILED_TEST_JS), (
            "expected compiled functional test at "
            + COMPILED_TEST_JS
            + " (compile succeeded but the test file was not emitted)"
        )
        for fname in ("entity/Order.js", "analytics-service.js"):
            p = os.path.join(COMPILED_FEATURE_DIR, fname)
            assert os.path.isfile(p), f"expected compiled deliverable {p}"

    def test_l2_agent_functional_test_passes(self):
        """The agent's own sales-analytics.test.ts passes under mocha (no failures/leaks)."""
        _require_compiled()
        setup = "build/compiled/test/utils/test-setup.js"
        cmd = (
            "npx mocha --require " + setup + " --check-leaks --exit "
            "--timeout 90000 " + COMPILED_TEST_JS
        )
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
        )
        combined = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "agent's mocha functional test failed:\n" + combined[-4000:]
        )
        assert "passing" in combined, (
            "mocha reported no passing tests:\n" + combined[-2000:]
        )
        assert " 0 passing" not in combined, (
            "mocha collected zero passing tests:\n" + combined[-2000:]
        )

    # ---- L2: independent driver probes against the compiled code --------

    def test_l2_revenue_by_region_sums_and_orders(self):
        """revenueByRegion() returns one summed row per region, ordered by region asc, totals = JS sums."""
        _require_compiled()
        js = _write_probe(
            "probe_revenue",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    """
                + _SEED_ROWS
                + """
                    await seed(ds, SEED);
                    const svc = makeService(ds);
                    const rows = await svc.revenueByRegion();
                    // Normalize each row to {region, total} accepting varied field names.
                    const norm = rows.map((r) => {
                        const region = r.region !== undefined ? r.region
                            : (r.name !== undefined ? r.name : Object.values(r)[0]);
                        let total = r.total;
                        if (total === undefined) total = r.revenue;
                        if (total === undefined) total = r.sum;
                        if (total === undefined) total = r.totalAmount;
                        if (total === undefined) {
                            const vals = Object.values(r);
                            total = vals[vals.length - 1];
                        }
                        return { region: region, total: Number(total) };
                    });
                    const expected = {};
                    for (const o of SEED) expected[o.region] = (expected[o.region] || 0) + o.amount;
                    out({
                        order: norm.map((r) => r.region),
                        totals: Object.fromEntries(norm.map((r) => [r.region, r.total])),
                        expected: expected,
                        rowCount: norm.length,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["rowCount"] == 3, (
            "revenueByRegion must return exactly one row per non-empty region: "
            + json.dumps(res)
        )
        # Ordered by region name ascending.
        assert res["order"] == ["north", "south", "west"], (
            "revenueByRegion rows are not ordered by region name ascending: "
            + json.dumps(res)
        )
        # Totals equal JS-side per-region sums (north=175, south=300, west=30).
        assert res["totals"]["north"] == 175, res
        assert res["totals"]["south"] == 300, res
        assert res["totals"]["west"] == 30, res
        for region, exp in res["expected"].items():
            assert res["totals"][region] == exp, (
                "DB sum != JS sum for region " + region + ": " + json.dumps(res)
            )

    def test_l2_revenue_excludes_empty_regions(self):
        """A region present in no order never appears in revenueByRegion()."""
        _require_compiled()
        js = _write_probe(
            "probe_revenue_empty",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    await seed(ds, [
                        { region: "only", product: "p", amount: 42.00, quantity: 1, placedAt: new Date("2021-01-01") },
                    ]);
                    const svc = makeService(ds);
                    const rows = await svc.revenueByRegion();
                    const regions = rows.map((r) =>
                        r.region !== undefined ? r.region : Object.values(r)[0]);
                    out({ regions: regions });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["regions"] == ["only"], res

    def test_l2_top_products_globally_ordered_and_bounded(self):
        """topProductsByQuantity(limit) aggregates per product, globally orders desc, bounds by limit."""
        _require_compiled()
        # Four products. Total quantity per product across ALL regions:
        #   widget = 3 + 2 + 4 = 9 ; gadget = 5 + 6 = 11 ; gizmo = 1 ; sprocket = 20
        js = _write_probe(
            "probe_top",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    """
                + _SEED_ROWS
                + """
                    await seed(ds, SEED);
                    await seed(ds, [
                        { region: "east", product: "sprocket", amount: 5.00, quantity: 20, placedAt: new Date("2021-04-01") },
                    ]);
                    const svc = makeService(ds);
                    const top2 = await svc.topProductsByQuantity(2);
                    const norm = top2.map((r) => {
                        const product = r.product !== undefined ? r.product
                            : (r.name !== undefined ? r.name : Object.values(r)[0]);
                        let qty = r.quantity;
                        if (qty === undefined) qty = r.totalQuantity;
                        if (qty === undefined) qty = r.total;
                        if (qty === undefined) qty = r.sum;
                        if (qty === undefined) {
                            const vals = Object.values(r);
                            qty = vals[vals.length - 1];
                        }
                        return { product: product, qty: Number(qty) };
                    });
                    out({
                        len: top2.length,
                        products: norm.map((r) => r.product),
                        quantities: norm.map((r) => r.qty),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["len"] == 2, (
            "topProductsByQuantity(2) must return at most 2 rows: " + json.dumps(res)
        )
        # Globally highest two totals are sprocket (20) then gadget (11).
        assert res["products"] == ["sprocket", "gadget"], (
            "topProductsByQuantity is not aggregated per-product / globally ordered desc: "
            + json.dumps(res)
        )
        assert res["quantities"] == [20, 11], (
            "topProductsByQuantity totals are not DB-aggregated sums: " + json.dumps(res)
        )

    def test_l2_top_products_respects_smaller_limit(self):
        """topProductsByQuantity(limit) never returns more rows than `limit`."""
        _require_compiled()
        js = _write_probe(
            "probe_top_limit",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    await seed(ds, [
                        { region: "r", product: "p1", amount: 1.00, quantity: 1, placedAt: new Date("2021-01-01") },
                        { region: "r", product: "p2", amount: 1.00, quantity: 2, placedAt: new Date("2021-01-02") },
                        { region: "r", product: "p3", amount: 1.00, quantity: 3, placedAt: new Date("2021-01-03") },
                        { region: "r", product: "p4", amount: 1.00, quantity: 4, placedAt: new Date("2021-01-04") },
                    ]);
                    const svc = makeService(ds);
                    const three = await svc.topProductsByQuantity(3);
                    const one = await svc.topProductsByQuantity(1);
                    const prod = (rows) => rows.map((r) =>
                        r.product !== undefined ? r.product : Object.values(r)[0]);
                    out({
                        threeLen: three.length,
                        threeProducts: prod(three),
                        oneLen: one.length,
                        oneProducts: prod(one),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["threeLen"] == 3, res
        assert res["threeProducts"] == ["p4", "p3", "p2"], res
        assert res["oneLen"] == 1 and res["oneProducts"] == ["p4"], res

    def test_l2_average_order_value_known_region(self):
        """averageOrderValue(region) returns the correct DB-computed mean for a known region."""
        _require_compiled()
        # north orders: 100, 50, 25 -> mean = 58.333...
        js = _write_probe(
            "probe_avg",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    """
                + _SEED_ROWS
                + """
                    await seed(ds, SEED);
                    const svc = makeService(ds);
                    const north = await svc.averageOrderValue("north");
                    const south = await svc.averageOrderValue("south");
                    const west = await svc.averageOrderValue("west");
                    out({
                        north: north === null ? null : Number(north),
                        south: south === null ? null : Number(south),
                        west: west === null ? null : Number(west),
                        northType: typeof north,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        # mean of north = (100+50+25)/3 = 58.3333...
        assert res["north"] is not None, res
        assert abs(res["north"] - (175.0 / 3.0)) < 1e-6, (
            "averageOrderValue('north') is not the correct mean: " + json.dumps(res)
        )
        # south has a single order -> mean == that order's amount.
        assert abs(res["south"] - 300.0) < 1e-6, res
        # west = (10+20)/2 = 15.
        assert abs(res["west"] - 15.0) < 1e-6, res
        assert res["northType"] == "number", (
            "averageOrderValue must return a numeric value, not a string/row: "
            + json.dumps(res)
        )

    def test_l2_average_order_value_unknown_region_is_null(self):
        """averageOrderValue(region) returns null when the region has no orders."""
        _require_compiled()
        js = _write_probe(
            "probe_avg_null",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    await seed(ds, [
                        { region: "north", product: "p", amount: 10.00, quantity: 1, placedAt: new Date("2021-01-01") },
                    ]);
                    const svc = makeService(ds);
                    const missing = await svc.averageOrderValue("atlantis");
                    out({ isNull: missing === null || missing === undefined,
                          value: missing === null ? "null" : missing });
                    await ds.destroy();
                })().catch((e) => { console.error("THREW", e); process.exit(2); });
                """
            ),
        )
        proc = _run_node(js)
        assert proc.returncode == 0, (
            "averageOrderValue(unknown) threw instead of returning null:\n"
            + proc.stdout
            + "\n"
            + proc.stderr
        )
        res = _parse_result(proc)
        assert res["isNull"] is True, (
            "averageOrderValue(unknown region) must return null: " + json.dumps(res)
        )

    def test_l2_regions_above_threshold_uses_aggregate_filter(self):
        """regionsAboveThreshold(t) filters on the SUMMED region revenue, not per-row amounts."""
        _require_compiled()
        # Construct a discriminating dataset:
        #   alpha: 2 orders of 60 each  -> total 120  (each row > 100, total > 100)
        #   beta : 3 orders of 60 each  -> total 180  (total > 100)
        #   gamma: 2 orders of 90 each  -> total 180  -- NOTE chosen below
        # The discriminator: a region whose INDIVIDUAL orders each exceed t but whose
        # TOTAL does not. Use threshold 100 with region "solo": one order of 150
        # (row 150 > 100) but total 150 > 100 would still pass... so instead make the
        # discriminating region have a single order of 80 (< 100) repeated? We need:
        #   per-row each > t, but total <= t  -> impossible with positive amounts.
        # The doc's discriminator is the OTHER way: a region whose individual orders
        # are each <= t (so a per-row filter would EXCLUDE it) but whose TOTAL > t (so
        # the aggregate filter INCLUDES it). That distinguishes aggregate vs per-row.
        #   small: 3 orders of 40 each -> each 40 <= 100, total 120 > 100  => INCLUDED
        #   big  : 1 order of 150      -> row 150 > 100, total 150 > 100   => INCLUDED
        #   tiny : 1 order of 30       -> total 30 <= 100                  => EXCLUDED
        js = _write_probe(
            "probe_threshold",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    await seed(ds, [
                        { region: "small", product: "p", amount: 40.00, quantity: 1, placedAt: new Date("2021-01-01") },
                        { region: "small", product: "p", amount: 40.00, quantity: 1, placedAt: new Date("2021-01-02") },
                        { region: "small", product: "p", amount: 40.00, quantity: 1, placedAt: new Date("2021-01-03") },
                        { region: "big",   product: "p", amount: 150.00, quantity: 1, placedAt: new Date("2021-01-04") },
                        { region: "tiny",  product: "p", amount: 30.00, quantity: 1, placedAt: new Date("2021-01-05") },
                    ]);
                    const svc = makeService(ds);
                    const result = await svc.regionsAboveThreshold(100);
                    // Accept either an array of strings or array of row objects.
                    const names = (result || []).map((r) =>
                        typeof r === "string" ? r
                            : (r.region !== undefined ? r.region : Object.values(r)[0]));
                    out({ names: names.slice().sort() });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        # Aggregate filter: small (120) and big (150) exceed 100; tiny (30) does not.
        # A naive per-ROW filter would EXCLUDE "small" (no single 40 row > 100) and
        # thus return ["big"] only -> that must fail this assertion.
        assert res["names"] == ["big", "small"], (
            "regionsAboveThreshold must apply the threshold to the GROUPED aggregate "
            "(small totals 120>100 even though no single order exceeds 100): "
            + json.dumps(res)
        )

    def test_l2_aggregation_is_db_side_not_js_reduce(self):
        """Reports are computed in the DB: they still work when find()/find-all is disabled.

        We monkeypatch the Order repository so a bulk `find()` (the JS-side
        "load everything then reduce" approach) throws. A correct, DB-aggregating
        implementation (query builder / raw SQL) is unaffected and still returns the
        right revenueByRegion totals; a JS-reduce implementation blows up.
        """
        _require_compiled()
        js = _write_probe(
            "probe_dbside",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    """
                + _SEED_ROWS
                + """
                    await seed(ds, SEED);
                    const svc = makeService(ds);
                    // Sabotage the "load all rows then reduce in JS" path: a bulk find()
                    // with no/empty options must throw. A real DB aggregate uses the
                    // query builder / raw query and is unaffected.
                    const repo = ds.getRepository(Order);
                    const realFind = repo.find.bind(repo);
                    repo.find = function (opts) {
                        const hasWhere = opts && opts.where && Object.keys(opts.where).length > 0;
                        if (!hasWhere) {
                            throw new Error("JS-side find-all is forbidden; aggregate in the DB");
                        }
                        return realFind(opts);
                    };
                    let threw = false;
                    let totals = null;
                    try {
                        const rows = await svc.revenueByRegion();
                        totals = {};
                        for (const r of rows) {
                            const region = r.region !== undefined ? r.region : Object.values(r)[0];
                            let total = r.total;
                            if (total === undefined) total = r.revenue;
                            if (total === undefined) total = r.sum;
                            if (total === undefined) {
                                const vals = Object.values(r);
                                total = vals[vals.length - 1];
                            }
                            totals[region] = Number(total);
                        }
                    } catch (e) {
                        threw = true;
                    }
                    out({ threw: threw, totals: totals });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["threw"] is False, (
            "revenueByRegion appears to load all rows via find() and reduce in JS "
            "(a database-side aggregate must not depend on a bulk find-all): "
            + json.dumps(res)
        )
        assert res["totals"] is not None, res
        assert res["totals"].get("north") == 175, res
        assert res["totals"].get("south") == 300, res
        assert res["totals"].get("west") == 30, res
