"""
Tests for the `typeorm-patterns` skill task (variant ext7):
"Build a Customer Profile Layer with Embedded Address".

The agent must add, under `test/functional/customer-profile/`, a self-contained
TypeORM functional feature:
  - entity/Address.ts          (reusable EMBEDDED value type: street, city, postalCode;
                                NOT an independent table)
  - entity/Customer.ts         (id auto-generated, name, billingAddress + shippingAddress,
                                each an embedded Address distinguished by a column prefix
                                so the two addresses never collide into shared columns)
  - profile-service.ts         (createCustomer / getCustomer / updateShipping / findByCity)
                                built on a DataSource
  - customer-profile.test.ts   (functional test wiring the above through
                                createTestingConnections, sqlite-only)

This pytest verifies the deliverables two ways:
  1. L1 — the four files exist and are minimally well-formed (embedded Address,
     two prefixed embeds, sqlite-only testing connections, the four service ops).
  2. L2 — DYNAMIC EXECUTION against the real TypeORM toolchain: it ensures an
     ormconfig.json restricted to the better-sqlite3 driver, compiles the repo
     (`pnpm run compile`), runs the agent's own compiled functional test, and then
     runs INDEPENDENT driver scripts (written by this test) against the agent's
     compiled Address/Customer/ProfileService to deep-validate real behavior:
        * billing and shipping addresses round-trip INDEPENDENTLY (no conflation)
        * NO separate `address` table exists; both addresses materialize as
          PREFIXED columns on the single customer row
        * updateShipping replaces only shipping, leaving billing untouched
        * findByCity filters on the embedded BILLING city via SQL (a single query),
          ordered by id asc, and excludes customers who only match on shipping city
        * getCustomer(missing) returns null

A naive solution (separate address table, addresses colliding into shared columns,
JS-side city filtering after loading everything, or filtering on shipping city)
must fail at least one assertion.
"""

import json
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/typeorm"
FEATURE_DIR = os.path.join(REPO_DIR, "test/functional/customer-profile")
ENTITY_DIR = os.path.join(FEATURE_DIR, "entity")
ADDRESS_TS = os.path.join(ENTITY_DIR, "Address.ts")
CUSTOMER_TS = os.path.join(ENTITY_DIR, "Customer.ts")
SERVICE_TS = os.path.join(FEATURE_DIR, "profile-service.ts")
TEST_TS = os.path.join(FEATURE_DIR, "customer-profile.test.ts")

COMPILED_TEST_JS = os.path.join(
    REPO_DIR,
    "build/compiled/test/functional/customer-profile/customer-profile.test.js",
)
COMPILED_FEATURE_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/customer-profile"
)

# Build/compile is heavy in this repo.
COMPILE_TIMEOUT = 1200
RUN_TIMEOUT = 600

# Directory (under REPO_DIR, picked up by tsc include "test") where this pytest drops
# its own independent driver scripts so they get compiled alongside the agent's code.
PROBE_OUT_DIR = os.path.join(
    REPO_DIR, "build/compiled/test/functional/customer-profile/__probe__"
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
    """Write a TS probe under the compiled-friendly probe dir and return its .js path.

    We compile probes with a standalone tsc invocation (decorators enabled) that
    emits next to the agent's already-compiled Address/Customer/ProfileService so the
    relative `./` imports in the probe resolve to real compiled modules.
    """
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
    """Relative imports (from the probe's compiled location) to the agent modules."""
    # Probe sits at build/compiled/test/functional/customer-profile/__probe__/X.js
    # Agent compiled modules sit one dir up.
    return {
        "address": "../entity/Address",
        "customer": "../entity/Customer",
        "service": "../profile-service",
        "datasource": "../../../../../src",  # build/compiled/src
    }


_DRIVER_PREAMBLE = """
"use strict";
const {{ DataSource }} = require("{datasource}");
const AddressMod = require("{address}");
const CustomerMod = require("{customer}");
const ServiceMod = require("{service}");

function pickClass(mod, names) {{
    for (const n of names) if (mod[n]) return mod[n];
    for (const k of Object.keys(mod)) {{
        if (typeof mod[k] === "function") return mod[k];
    }}
    if (mod.default) return mod.default;
    throw new Error("could not locate export in module");
}}

const Address = pickClass(AddressMod, ["Address", "default"]);
const Customer = pickClass(CustomerMod, ["Customer", "default"]);
const ServiceExport = pickClass(
    ServiceMod, ["ProfileService", "CustomerProfileService", "Profile", "default"]);

function makeService(ds) {{
    // Support both `new Class(ds)` and a factory `fn(ds)`.
    try {{
        return new ServiceExport(ds);
    }} catch (e) {{
        return ServiceExport(ds);
    }}
}}

async function newDataSource(extra) {{
    const opts = Object.assign({{
        type: "better-sqlite3",
        database: ":memory:",
        entities: [Customer, Address],
        synchronize: true,
        dropSchema: true,
    }}, extra || {{}});
    const ds = new DataSource(opts);
    await ds.initialize();
    return ds;
}}

function addr(street, city, postalCode) {{
    return {{ street: street, city: city, postalCode: postalCode }};
}}

function out(obj) {{ process.stdout.write("RESULT_JSON:" + JSON.stringify(obj) + "\\n"); }}
"""


def _driver(body):
    paths = _import_paths()
    preamble = _DRIVER_PREAMBLE.format(
        datasource=paths["datasource"],
        address=paths["address"],
        customer=paths["customer"],
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


# ===========================================================================
# Tests
# ===========================================================================


class TestTypeormPatterns:
    REPO_DIR = "/workspace/typeorm"

    # ---- L1 -------------------------------------------------------------

    def test_l1_feature_files_exist(self):
        """All four required deliverable files exist under customer-profile/."""
        for p in (ADDRESS_TS, CUSTOMER_TS, SERVICE_TS, TEST_TS):
            assert os.path.isfile(p), f"missing required deliverable file: {p}"

    def test_l1_address_is_embedded_value_not_entity(self):
        """Address is a reusable embedded value type (street/city/postalCode), NOT a table."""
        src = _read(ADDRESS_TS)
        # An embedded value type must NOT be decorated as its own @Entity / table.
        assert "@Entity" not in src, (
            "Address must be an EMBEDDED value type, not an independent @Entity/table"
        )
        for field in ("street", "city", "postalCode"):
            assert field in src, f"Address does not declare the `{field}` field"
        # Its fields are persisted via @Column (so they materialize on the owner row).
        assert "@Column" in src, "Address fields must be persisted via @Column"

    def test_l1_customer_embeds_two_prefixed_addresses(self):
        """Customer has a generated id, name, and two prefixed embedded Address columns."""
        src = _read(CUSTOMER_TS)
        assert "@Entity" in src, "Customer is not annotated with @Entity"
        assert (
            "@PrimaryGeneratedColumn" in src
        ), "Customer lacks a database-generated primary key"
        assert "name" in src, "Customer does not declare a `name` field"
        assert "billingAddress" in src, "Customer does not declare `billingAddress`"
        assert "shippingAddress" in src, "Customer does not declare `shippingAddress`"
        # Embedded columns: @Column(() => Address, ...). Two embeds must be declared.
        assert src.count("() => Address") >= 2 or src.count("()=>Address") >= 2, (
            "Customer must embed Address TWICE via @Column(() => Address, ...)"
        )
        # Prefixing is required so the two addresses do not collide into shared columns.
        assert "prefix" in src, (
            "the two embedded addresses must use a column-name `prefix` so billing "
            "and shipping never collide into shared columns"
        )

    def test_l1_service_exports_required_operations(self):
        """profile-service.ts exports the four named profile operations."""
        src = _read(SERVICE_TS)
        for op in ("createCustomer", "getCustomer", "updateShipping", "findByCity"):
            assert op in src, f"profile-service.ts does not define `{op}`"

    def test_l1_test_uses_sqlite_only_testing_connections(self):
        """The functional test restricts testing connections to the SQLite driver family."""
        src = _read(TEST_TS)
        assert "createTestingConnections" in src, (
            "customer-profile.test.ts must use createTestingConnections from "
            "../../utils/test-utils"
        )
        assert "enabledDrivers" in src, (
            "customer-profile.test.ts must restrict to SQLite-based driver(s) via "
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
        for fname in ("entity/Address.js", "entity/Customer.js", "profile-service.js"):
            p = os.path.join(COMPILED_FEATURE_DIR, fname)
            assert os.path.isfile(p), f"expected compiled deliverable {p}"

    def test_l2_agent_functional_test_passes(self):
        """The agent's own customer-profile.test.ts passes under mocha (no failures/leaks)."""
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

    def test_l2_no_separate_address_table(self):
        """No `address` table exists; both addresses live as columns on the customer row."""
        _require_compiled()
        js = _write_probe(
            "probe_schema",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const tables = await ds.query(
                        "SELECT name FROM sqlite_master WHERE type='table'");
                    const names = tables.map((t) => String(t.name).toLowerCase());
                    const cols = await ds.query("PRAGMA table_info(customer)");
                    const colNames = cols.map((c) => String(c.name));
                    out({
                        tables: names,
                        hasAddressTable: names.includes("address"),
                        customerCols: colNames,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["hasAddressTable"] is False, (
            "an embedded Address must NOT create a separate `address` table: "
            + json.dumps(res)
        )
        # The customer table must carry BOTH addresses' columns (6 address-ish columns).
        cols_lower = [c.lower() for c in res["customerCols"]]
        street_like = [c for c in cols_lower if "street" in c]
        city_like = [c for c in cols_lower if "city" in c]
        postal_like = [c for c in cols_lower if "postal" in c]
        assert len(street_like) >= 2, (
            "customer row must carry two distinct street columns (billing+shipping): "
            + json.dumps(res)
        )
        assert len(city_like) >= 2, (
            "customer row must carry two distinct city columns (billing+shipping): "
            + json.dumps(res)
        )
        assert len(postal_like) >= 2, (
            "customer row must carry two distinct postalCode columns: " + json.dumps(res)
        )
        # The two city columns must be distinct names (prefix prevents collision).
        assert len(set(city_like)) == len(city_like), (
            "billing and shipping addresses collided into shared columns: "
            + json.dumps(res)
        )

    def test_l2_addresses_round_trip_independently(self):
        """createCustomer + getCustomer round-trips billing and shipping as distinct values."""
        _require_compiled()
        js = _write_probe(
            "probe_roundtrip",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const created = await svc.createCustomer(
                        "Alice",
                        addr("1 Bill St", "Billville", "B100"),
                        addr("2 Ship Rd", "Shiptown", "S200"));
                    const got = await svc.getCustomer(created.id);
                    out({
                        createdId: created.id,
                        gotId: got ? got.id : -1,
                        name: got ? got.name : null,
                        billCity: got && got.billingAddress ? got.billingAddress.city : null,
                        billStreet: got && got.billingAddress ? got.billingAddress.street : null,
                        billPostal: got && got.billingAddress ? got.billingAddress.postalCode : null,
                        shipCity: got && got.shippingAddress ? got.shippingAddress.city : null,
                        shipStreet: got && got.shippingAddress ? got.shippingAddress.street : null,
                        shipPostal: got && got.shippingAddress ? got.shippingAddress.postalCode : null,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert isinstance(res["createdId"], int) and res["createdId"] > 0, res
        assert res["gotId"] == res["createdId"], res
        assert res["name"] == "Alice", res
        # Billing and shipping must NOT be conflated.
        assert res["billCity"] == "Billville", res
        assert res["billStreet"] == "1 Bill St", res
        assert res["billPostal"] == "B100", res
        assert res["shipCity"] == "Shiptown", res
        assert res["shipStreet"] == "2 Ship Rd", res
        assert res["shipPostal"] == "S200", res

    def test_l2_get_missing_customer_returns_null(self):
        """getCustomer(<missing id>) returns null rather than throwing or returning a row."""
        _require_compiled()
        js = _write_probe(
            "probe_missing",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    await svc.createCustomer("Real",
                        addr("x", "Xcity", "X1"), addr("y", "Ycity", "Y1"));
                    const missing = await svc.getCustomer(987654);
                    out({ isNull: missing === null || missing === undefined,
                          type: missing === null ? "null" : typeof missing });
                    await ds.destroy();
                })().catch((e) => { console.error("THREW", e); process.exit(2); });
                """
            ),
        )
        proc = _run_node(js)
        assert proc.returncode == 0, (
            "getCustomer(missing) threw instead of returning null:\n"
            + proc.stdout
            + "\n"
            + proc.stderr
        )
        res = _parse_result(proc)
        assert res["isNull"] is True, (
            "getCustomer(missing) must return null: " + json.dumps(res)
        )

    def test_l2_update_shipping_leaves_billing_untouched(self):
        """updateShipping replaces only the shipping address; billing stays exactly as it was."""
        _require_compiled()
        js = _write_probe(
            "probe_update",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    const c = await svc.createCustomer(
                        "Bob",
                        addr("10 Bill Ave", "OldBillCity", "BB1"),
                        addr("20 Ship Ave", "OldShipCity", "SS1"));
                    await svc.updateShipping(c.id, addr("99 New Ship", "NewShipCity", "NS9"));
                    // Re-read directly from the DB (bypass the service) to be sure.
                    const got = await svc.getCustomer(c.id);
                    const cols = await ds.query("PRAGMA table_info(customer)");
                    const colNames = cols.map((r) => r.name);
                    const rawRows = await ds.query(
                        "SELECT * FROM customer WHERE id = " + c.id);
                    const raw = rawRows[0] || {};
                    // Collect every value containing a known city marker for cross-check.
                    const rawVals = Object.values(raw).map((v) => String(v));
                    out({
                        billCity: got && got.billingAddress ? got.billingAddress.city : null,
                        billStreet: got && got.billingAddress ? got.billingAddress.street : null,
                        billPostal: got && got.billingAddress ? got.billingAddress.postalCode : null,
                        shipCity: got && got.shippingAddress ? got.shippingAddress.city : null,
                        shipStreet: got && got.shippingAddress ? got.shippingAddress.street : null,
                        rawHasOldBill: rawVals.includes("OldBillCity"),
                        rawHasNewShip: rawVals.includes("NewShipCity"),
                        rawHasOldShip: rawVals.includes("OldShipCity"),
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        # Billing must be exactly unchanged.
        assert res["billCity"] == "OldBillCity", res
        assert res["billStreet"] == "10 Bill Ave", res
        assert res["billPostal"] == "BB1", res
        # Shipping must be the new value.
        assert res["shipCity"] == "NewShipCity", res
        assert res["shipStreet"] == "99 New Ship", res
        # Raw DB confirms billing preserved, shipping replaced (old shipping gone).
        assert res["rawHasOldBill"] is True, (
            "updateShipping clobbered the billing address: " + json.dumps(res)
        )
        assert res["rawHasNewShip"] is True, res
        assert res["rawHasOldShip"] is False, (
            "old shipping city still present; updateShipping did not replace it: "
            + json.dumps(res)
        )

    def test_l2_find_by_city_filters_on_billing_in_sql(self):
        """findByCity matches customers whose BILLING city equals the arg, ordered by id asc."""
        _require_compiled()
        js = _write_probe(
            "probe_find_city",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    // Two customers bill in Paris (ids will be ascending in insert order).
                    const p1 = await svc.createCustomer("Bp1",
                        addr("1", "Paris", "P1"), addr("a", "Lyon", "L1"));
                    const other = await svc.createCustomer("Other",
                        addr("2", "Berlin", "DE1"), addr("b", "Paris", "P9"));
                    const p2 = await svc.createCustomer("Bp2",
                        addr("3", "Paris", "P2"), addr("c", "Nice", "N1"));
                    const found = await svc.findByCity("Paris");
                    out({
                        names: found.map((c) => c.name),
                        ids: found.map((c) => c.id),
                        billCities: found.map((c) =>
                            c.billingAddress ? c.billingAddress.city : null),
                        p1Id: p1.id, p2Id: p2.id, otherId: other.id,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        # Only the two customers whose BILLING city is Paris -> excludes "Other"
        # (which only ships to Paris). A shipping-city match must NOT be returned.
        assert res["names"] == ["Bp1", "Bp2"], (
            "findByCity must match billing city only (exclude shipping-only matches), "
            "ordered by id asc: " + json.dumps(res)
        )
        assert res["ids"] == sorted(res["ids"]), (
            "findByCity results must be ordered by id ascending: " + json.dumps(res)
        )
        assert res["ids"] == [res["p1Id"], res["p2Id"]], res
        assert all(c == "Paris" for c in res["billCities"]), res

    def test_l2_find_by_city_no_match_returns_empty(self):
        """findByCity returns an empty list when no billing city matches."""
        _require_compiled()
        js = _write_probe(
            "probe_find_empty",
            _driver(
                """
                (async () => {
                    const ds = await newDataSource();
                    const svc = makeService(ds);
                    await svc.createCustomer("A",
                        addr("1", "Tokyo", "T1"), addr("a", "Osaka", "O1"));
                    const found = await svc.findByCity("Nowhere");
                    out({ len: Array.isArray(found) ? found.length : -1 });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["len"] == 0, (
            "findByCity with no matching billing city must return an empty list: "
            + json.dumps(res)
        )

    def test_l2_find_by_city_filters_in_a_single_query(self):
        """findByCity pushes the filter into ONE SQL query (not JS-side over all rows)."""
        _require_compiled()
        # Instrument the DataSource logger: count SELECTs against the customer table and
        # how many of them actually carry a WHERE filter. A JS-side filter would SELECT
        # all customers (no WHERE) then filter in JS; an SQL-pushed filter issues a
        # single WHERE-bearing query and never materializes the whole table.
        js = _write_probe(
            "probe_single_query",
            _driver(
                """
                (async () => {
                    const queries = [];
                    const ds = await newDataSource({
                        logging: ["query"],
                        logger: {
                            logQuery(q) { queries.push(String(q || "")); },
                            logQueryError() {},
                            logQuerySlow() {},
                            logSchemaBuild() {},
                            logMigration() {},
                            log() {},
                        },
                    });
                    const svc = makeService(ds);
                    // Seed a mix; only some bill in Madrid.
                    for (let i = 0; i < 6; i++) {
                        const city = (i % 2 === 0) ? "Madrid" : "Rome";
                        await svc.createCustomer("c" + i,
                            addr("s" + i, city, "P" + i),
                            addr("ss" + i, "ShipCity", "SP" + i));
                    }
                    queries.length = 0; // count only the read phase
                    const found = await svc.findByCity("Madrid");
                    const sel = queries.filter((q) => /^\\s*select/i.test(q));
                    const custSel = sel.filter((q) => /from\\s+["'`]?customer/i.test(q));
                    const whereSel = custSel.filter((q) => /\\bwhere\\b/i.test(q));
                    const cityInSql = custSel.some((q) => /madrid/i.test(q));
                    out({
                        found: found.length,
                        customerSelects: custSel.length,
                        whereSelects: whereSel.length,
                        cityFilterInSql: cityInSql,
                        queries: custSel,
                    });
                    await ds.destroy();
                })().catch((e) => { console.error(e); process.exit(1); });
                """
            ),
        )
        res = _parse_result(_run_node(js))
        assert res["found"] == 3, (
            "expected 3 Madrid-billing customers: " + json.dumps(res)
        )
        # A JS-side filter would issue zero WHERE-bearing customer SELECTs (it loads all
        # then filters in JS). The SQL-pushed approach issues at least one WHERE query.
        assert res["whereSelects"] >= 1, (
            "findByCity does not push the city filter into SQL (no WHERE-bearing "
            "customer SELECT — looks like JS-side filtering): " + json.dumps(res)
        )
        # Exactly one read query against customer (single query requirement).
        assert res["customerSelects"] == 1, (
            "findByCity must retrieve matches with a SINGLE query against customer: "
            + json.dumps(res)
        )
        # The filtered city value/param must actually reach SQL (bound param shows in log).
        # better-sqlite3 logs parameters, so the literal should be present.
        assert res["cityFilterInSql"] is True, (
            "the filtered city does not appear in the executed SQL; filtering may be "
            "happening in JavaScript: " + json.dumps(res)
        )
