"""
Test for the 'sequelize-orm' skill (variant ext8) — Assemble a Nested Order Report.

The agent must create two files inside @sequelize/core's *integration*-test tree:
  - packages/core/test/integration/order-report.ts       (the domain module)
  - packages/core/test/integration/order-report.test.ts  (its integration test)

The module exports:
  - setupOrders(sequelize) -> { Customer, Order, LineItem }
        defines three models, wires their relationships (Customer hasMany Order
        under accessor `orders`; Order hasMany LineItem under accessor `items`;
        Order belongsTo Customer under accessor `customer`) and creates their
        tables (sync).
  - loadCustomerOrders(models, options)
        returns every Customer with their `orders` eagerly attached and each
        Order with its `items` eagerly attached, assembled in a SINGLE round of
        loading (no per-parent / per-order follow-up query). When
        options.recentOnly === true, only orders whose placedAt >= options.since
        are attached, but childless customers must still appear with orders: [].

Verification strategy
---------------------
L1 cases check that the deliverable files exist and are minimally well-formed.

L2 cases DO NOT trust the agent's own test file. Instead we drop an independent
mocha spec into the *integration* tree that imports the agent's order-report
module, seeds a fixed dataset through `setupOrders`, and then exercises
`loadCustomerOrders` against the real default test database (in-memory/file
sqlite). We verify concrete behaviour:

  * full nested loading: every customer present, each order carries its `items`,
    the no-order customer has orders: [].
  * SINGLE-ROUND loading: a `beforeQuery` hook counts SELECT statements emitted
    by loadCustomerOrders; an N+1 implementation (one follow-up SELECT per
    customer or per order) emits more queries and FAILS the bound. This is the
    key discriminator the doc calls out.
  * date filtering: with { recentOnly: true, since }, only orders on/after
    `since` are attached, and a customer whose orders are all older still
    appears with orders: [] (childless parents are NOT dropped).

Each spec is run via the repository's native command from packages/core:

    yarn mocha "test/integration/order-report.test.ts"

A naive implementation that loads relations with follow-up queries per parent,
that drops childless parents when filtering, or that ignores the `since` bound
cannot pass these assertions.
"""

import os
import subprocess
import textwrap

import pytest


REPO_DIR = "/workspace/sequelize"
CORE_DIR = os.path.join(REPO_DIR, "packages", "core")
INTEG_DIR = os.path.join(CORE_DIR, "test", "integration")
MODULE_FILE = os.path.join(INTEG_DIR, "order-report.ts")
AGENT_TEST_FILE = os.path.join(INTEG_DIR, "order-report.test.ts")

# Where we drop our own independent specs (relative to CORE_DIR for the mocha glob).
_BENCH_BASENAME = "zzz-bench-order-report"


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
    spec_path = os.path.join(INTEG_DIR, spec_name)
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


# Common TS preamble used by every independent spec. It builds a fresh Sequelize
# (default test dialect), invokes the agent's setupOrders to define + sync the
# models, and seeds a FIXED dataset:
#
#   Customer "Alice"  -> Order "A-OLD"  placedAt 2020-01-01  items: 2
#                     -> Order "A-NEW"  placedAt 2024-06-01  items: 1
#   Customer "Bob"    -> Order "B-OLD"  placedAt 2019-12-31  items: 1   (all old)
#   Customer "Carol"  -> (no orders)
#
# `SINCE` = 2023-01-01. With recentOnly, only A-NEW qualifies; Bob and Carol must
# appear with orders: [].
#
# It also installs a `beforeQuery` SELECT counter so individual specs can assert
# single-round loading.
_PREAMBLE = textwrap.dedent(
    """\
    import { expect } from 'chai';
    import { createSequelizeInstance } from '../support';
    import { setupOrders, loadCustomerOrders } from './order-report';

    const SINCE = new Date('2023-01-01T00:00:00.000Z');
    const A_OLD = new Date('2020-01-01T00:00:00.000Z');
    const A_NEW = new Date('2024-06-01T00:00:00.000Z');
    const B_OLD = new Date('2019-12-31T00:00:00.000Z');

    async function seed() {
      const sequelize = createSequelizeInstance();
      const models: any = await setupOrders(sequelize as any);
      const { Customer, Order, LineItem } = models;
      expect(Customer, 'setupOrders did not return Customer').to.exist;
      expect(Order, 'setupOrders did not return Order').to.exist;
      expect(LineItem, 'setupOrders did not return LineItem').to.exist;

      const alice = await Customer.create({ name: 'Alice' });
      const bob = await Customer.create({ name: 'Bob' });
      const carol = await Customer.create({ name: 'Carol' });

      const aOld = await Order.create({ reference: 'A-OLD', placedAt: A_OLD, customerId: alice.id });
      const aNew = await Order.create({ reference: 'A-NEW', placedAt: A_NEW, customerId: alice.id });
      const bOld = await Order.create({ reference: 'B-OLD', placedAt: B_OLD, customerId: bob.id });

      await LineItem.create({ description: 'widget',  quantity: 2, orderId: aOld.id });
      await LineItem.create({ description: 'gadget',  quantity: 5, orderId: aOld.id });
      await LineItem.create({ description: 'sprocket', quantity: 1, orderId: aNew.id });
      await LineItem.create({ description: 'gizmo',   quantity: 7, orderId: bOld.id });

      return { sequelize, models };
    }

    // Returns { result, selectCount } where selectCount counts ONLY the SELECT
    // statements emitted during the loadCustomerOrders call.
    async function loadWithSelectCount(sequelize: any, models: any, options?: any) {
      let count = 0;
      const listener = (_opts: any, query: any) => {
        const sql = String((query && (query.sql || query.uuid && query.options && query.options.sql)) || '');
        if (/^\\s*select/i.test(sql)) {
          count++;
        }
      };
      sequelize.hooks.addListener('beforeQuery', listener);
      let result: any;
      try {
        result = await loadCustomerOrders(models, options);
      } finally {
        sequelize.hooks.removeListener('beforeQuery', listener);
      }
      return { result, selectCount: count };
    }

    function byName(rows: any[]) {
      const m: any = {};
      for (const r of rows) {
        m[r.name ?? (r.get && r.get('name'))] = r;
      }
      return m;
    }

    function ordersOf(customer: any): any[] {
      const v = customer.orders ?? (customer.get && customer.get('orders'));
      return v || [];
    }

    function itemsOf(order: any): any[] {
      const v = order.items ?? (order.get && order.get('items'));
      return v || [];
    }

    function refOf(order: any): string {
      return order.reference ?? (order.get && order.get('reference'));
    }
    """
)


# ---------------------------------------------------------------------------
# Module-scope dependency guard. The container already has the toolchain that
# runs `yarn mocha`; we make sure node_modules is present (best-effort) so the
# native command can resolve mocha/chai/esbuild.
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
    """Verify the nested order-report deliverable (ext8 variant)."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_module_file_exists(self):
        """The domain module order-report.ts must exist."""
        assert os.path.isfile(MODULE_FILE), f"missing module file: {MODULE_FILE}"

    def test_agent_test_file_exists(self):
        """The agent's own integration test order-report.test.ts must exist."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing test file: {AGENT_TEST_FILE}"

    def test_module_exports_required_functions(self):
        """order-report.ts must export both `setupOrders` and `loadCustomerOrders`."""
        src = _read(MODULE_FILE)
        assert "setupOrders" in src, "setupOrders not found in module"
        assert "loadCustomerOrders" in src, "loadCustomerOrders not found in module"
        assert "export" in src, "module does not export anything"

    def test_agent_test_imports_module(self):
        """The agent's test must import from the local order-report module."""
        src = _read(AGENT_TEST_FILE)
        assert "order-report" in src, "test does not reference the order-report module"
        assert (
            "loadCustomerOrders" in src
        ), "agent test does not exercise loadCustomerOrders"

    # ------------------------------------------------------------------
    # L2 — independent dynamic execution via native `yarn mocha`.
    # Each test writes its own spec, so failures are isolated and specific.
    # ------------------------------------------------------------------

    def test_setup_returns_three_models_with_associations(self):
        """setupOrders returns Customer/Order/LineItem and wires orders/items/customer accessors."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('order-report: setup shape & associations', () => {
              it('returns three distinct real models', async () => {
                const { models } = await seed();
                const { Customer, Order, LineItem } = models;
                for (const m of [Customer, Order, LineItem]) {
                  expect(typeof m.getAttributes, 'not a model class').to.equal('function');
                  expect(typeof m.build, 'not a model class').to.equal('function');
                }
                expect(Customer).to.not.equal(Order);
                expect(Order).to.not.equal(LineItem);
              });

              it('wires Customer.orders, Order.items and Order.customer accessors', async () => {
                const { models } = await seed();
                const { Customer, Order, LineItem } = models;

                const ordersAssoc = Customer.associations.orders;
                expect(ordersAssoc, 'Customer.associations.orders missing').to.exist;
                expect(ordersAssoc.target, 'orders should target Order').to.equal(Order);

                const itemsAssoc = Order.associations.items;
                expect(itemsAssoc, 'Order.associations.items missing').to.exist;
                expect(itemsAssoc.target, 'items should target LineItem').to.equal(LineItem);

                const customerAssoc = Order.associations.customer;
                expect(customerAssoc, 'Order.associations.customer missing').to.exist;
                expect(customerAssoc.target, 'customer should target Customer').to.equal(Customer);
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-shape.test.ts", spec)
        _assert_mocha_passed(result, "setup shape & associations")

    def test_full_load_returns_every_customer(self):
        """loadCustomerOrders() returns all 3 seeded customers (including the childless one)."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('order-report: full load returns every customer', () => {
              it('returns Alice, Bob and Carol', async () => {
                const { sequelize, models } = await seed();
                const rows = await loadCustomerOrders(models);
                expect(Array.isArray(rows), 'result is not an array').to.equal(true);
                const names = rows.map((r: any) => r.name ?? (r.get && r.get('name'))).sort();
                expect(names).to.deep.equal(['Alice', 'Bob', 'Carol']);
                await sequelize.close();
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-allcustomers.test.ts", spec)
        _assert_mocha_passed(result, "full load returns every customer")

    def test_childless_customer_has_empty_orders(self):
        """Carol (zero orders) appears with orders === [] under a full load."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('order-report: childless customer present', () => {
              it('Carol has an empty orders array', async () => {
                const { sequelize, models } = await seed();
                const rows = await loadCustomerOrders(models);
                const map = byName(rows);
                expect(map.Carol, 'Carol missing from result').to.exist;
                const carolOrders = ordersOf(map.Carol);
                expect(Array.isArray(carolOrders), 'Carol.orders is not an array').to.equal(true);
                expect(carolOrders.length, 'Carol should have no orders').to.equal(0);
                await sequelize.close();
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-childless.test.ts", spec)
        _assert_mocha_passed(result, "childless customer has empty orders")

    def test_nested_orders_and_items_attached(self):
        """Each customer's orders and each order's line items are eagerly attached."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('order-report: nested orders + items attached', () => {
              it('Alice has 2 orders and the correct item counts', async () => {
                const { sequelize, models } = await seed();
                const rows = await loadCustomerOrders(models);
                const map = byName(rows);

                const aliceOrders = ordersOf(map.Alice);
                const aliceRefs = aliceOrders.map(refOf).sort();
                expect(aliceRefs).to.deep.equal(['A-NEW', 'A-OLD']);

                const ordersByRef: any = {};
                for (const o of aliceOrders) ordersByRef[refOf(o)] = o;

                // Items must be attached to the returned order instances.
                expect(itemsOf(ordersByRef['A-OLD']).length,
                  'A-OLD should carry 2 line items').to.equal(2);
                expect(itemsOf(ordersByRef['A-NEW']).length,
                  'A-NEW should carry 1 line item').to.equal(1);

                // Item content is real (not stubbed).
                const oldDescs = itemsOf(ordersByRef['A-OLD'])
                  .map((i: any) => i.description ?? (i.get && i.get('description'))).sort();
                expect(oldDescs).to.deep.equal(['gadget', 'widget']);

                const bobOrders = ordersOf(map.Bob);
                expect(bobOrders.map(refOf)).to.deep.equal(['B-OLD']);
                expect(itemsOf(bobOrders[0]).length, 'B-OLD should carry 1 item').to.equal(1);

                await sequelize.close();
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-nested.test.ts", spec)
        _assert_mocha_passed(result, "nested orders + items attached")

    def test_single_round_loading_no_n_plus_one(self):
        """loadCustomerOrders assembles the nested tree without per-parent follow-up SELECTs.

        An N+1 implementation that re-queries orders per customer (3 customers) and
        items per order (3 orders) would emit ~7 SELECTs; the eager single-round
        approach emits a small constant number. We bound the SELECT count well
        below the N+1 count so a naive loader fails.
        """
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('order-report: single-round loading', () => {
              it('emits a small constant number of SELECTs (no N+1)', async () => {
                const { sequelize, models } = await seed();
                const { result, selectCount } = await loadWithSelectCount(sequelize, models);

                // Sanity: the load still produced the full nested tree.
                const map = byName(result);
                expect(Object.keys(map).sort()).to.deep.equal(['Alice', 'Bob', 'Carol']);
                expect(itemsOf(ordersOf(map.Alice).find((o: any) => refOf(o) === 'A-OLD')).length)
                  .to.equal(2);

                // 3 customers + 3 orders would make an N+1 loader emit >= 7 SELECTs.
                // A single eager include emits 1; a per-level eager strategy emits a
                // few. Bound at <= 4 to reject any per-parent follow-up querying.
                expect(selectCount, 'too many SELECTs -> looks like an N+1 loader (got '
                  + selectCount + ')').to.be.at.most(4);
                expect(selectCount, 'expected at least one SELECT').to.be.at.least(1);

                await sequelize.close();
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-singleround.test.ts", spec)
        _assert_mocha_passed(result, "single-round loading (no N+1)")

    def test_recent_only_filters_old_orders(self):
        """recentOnly + since attaches only orders on/after `since`."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('order-report: recentOnly date filtering', () => {
              it('only A-NEW survives for Alice; Alice keeps exactly one order', async () => {
                const { sequelize, models } = await seed();
                const rows = await loadCustomerOrders(models, { recentOnly: true, since: SINCE });
                const map = byName(rows);

                const aliceOrders = ordersOf(map.Alice);
                expect(aliceOrders.map(refOf), 'only A-NEW (>= since) should remain')
                  .to.deep.equal(['A-NEW']);

                // The surviving order still carries its items.
                expect(itemsOf(aliceOrders[0]).length, 'A-NEW should keep its 1 item').to.equal(1);
                await sequelize.close();
              });

              it('a boundary order placed exactly on `since` is retained', async () => {
                const { sequelize, models } = await seed();
                const { Customer, Order } = models;
                const dan = await Customer.create({ name: 'Dan' });
                await Order.create({ reference: 'D-EDGE', placedAt: SINCE, customerId: dan.id });
                const rows = await loadCustomerOrders(models, { recentOnly: true, since: SINCE });
                const map = byName(rows);
                expect(ordersOf(map.Dan).map(refOf), 'order on `since` must be inclusive')
                  .to.deep.equal(['D-EDGE']);
                await sequelize.close();
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-recent.test.ts", spec)
        _assert_mocha_passed(result, "recentOnly date filtering")

    def test_recent_only_keeps_childless_customers(self):
        """Filtering must NOT drop customers whose orders are all older than `since`."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('order-report: recentOnly retains childless customers', () => {
              it('Bob (all-old) and Carol (no orders) survive with orders: []', async () => {
                const { sequelize, models } = await seed();
                const rows = await loadCustomerOrders(models, { recentOnly: true, since: SINCE });
                const map = byName(rows);

                // All three customers must still be present.
                expect(Object.keys(map).sort()).to.deep.equal(['Alice', 'Bob', 'Carol']);

                // Bob's only order (B-OLD) is older than `since` -> empty orders, not dropped.
                expect(map.Bob, 'Bob dropped by the date filter').to.exist;
                expect(ordersOf(map.Bob).length, 'Bob should have orders: []').to.equal(0);

                // Carol still has no orders.
                expect(map.Carol, 'Carol dropped by the date filter').to.exist;
                expect(ordersOf(map.Carol).length, 'Carol should have orders: []').to.equal(0);

                await sequelize.close();
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-recentchildless.test.ts", spec)
        _assert_mocha_passed(result, "recentOnly retains childless customers")

    def test_default_load_ignores_date(self):
        """Without recentOnly, all orders are attached regardless of date (old + new)."""
        spec = _PREAMBLE + textwrap.dedent(
            """
            describe('order-report: default load ignores date', () => {
              it('Alice keeps both A-OLD and A-NEW; Bob keeps B-OLD', async () => {
                const { sequelize, models } = await seed();

                // Explicit recentOnly:false must behave like the no-options case.
                const rows = await loadCustomerOrders(models, { recentOnly: false, since: SINCE });
                const map = byName(rows);
                expect(ordersOf(map.Alice).map(refOf).sort()).to.deep.equal(['A-NEW', 'A-OLD']);
                expect(ordersOf(map.Bob).map(refOf)).to.deep.equal(['B-OLD']);
                await sequelize.close();
              });
            });
            """
        )
        result = _write_spec_and_run(f"{_BENCH_BASENAME}-default.test.ts", spec)
        _assert_mocha_passed(result, "default load ignores date")

    def test_agent_supplied_test_passes(self):
        """The agent's own acceptance command must pass: yarn mocha order-report.test.ts."""
        result = _run_mocha(
            os.path.join("test", "integration", "order-report.test.ts"),
            timeout=900,
        )
        _assert_mocha_passed(result, "agent-supplied order-report.test.ts")
