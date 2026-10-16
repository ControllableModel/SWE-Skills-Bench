"""Tests for the `fastify-patterns` skill task (ext2): Schema-Validated Paginated Listing Endpoint.

Verifies the agent's work inside REPO_DIR (/workspace/fastify):

  - examples/orders-listing.js exports a no-argument factory that builds and
    returns a configured Fastify instance WITHOUT binding a network port on
    require/build.
  - The factory seeds an in-memory dataset of >= 25 deterministic order records
    (id/customer/total/status) with a known status distribution.
  - GET /orders is a paginated, query-driven listing endpoint whose `page`,
    `limit`, and `status` query params are validated/coerced/defaulted by the
    framework's request lifecycle (a schema), NOT by ad-hoc handler parsing:
      * defaults: page=1, limit=10
      * coercion: page/limit appear as JSON numbers (not strings) in the body
      * filtering by status with an exact `total`, pagination after filtering
      * out-of-bounds / invalid queries rejected with 400 BEFORE the handler
      * item field whitelisting to exactly {id, customer, total, status}
  - test/orders-listing.test.js exists, uses node:test + inject, and the native
    command `node --test test/orders-listing.test.js` passes.

Rather than trusting the agent-authored test file, the L2 cases independently
drive the factory through Fastify's in-process `inject` API using a fresh Node
driver written by THIS test. A naive implementation that reads req.query.page as
a raw string, applies no bounds, skips validation, or filters/paginates wrong
will fail these assertions.
"""

import json
import os
import subprocess
import textwrap

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - utility is provided at runtime
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/fastify"
DRIVER_DIR = os.path.join(REPO_DIR, ".bench_drivers")


@pytest.fixture(scope="module", autouse=True)
def _prepare_repo():
    """Install repo dependencies once so `require('..')` resolves."""
    assert os.path.isdir(REPO_DIR), f"REPO_DIR missing: {REPO_DIR}"
    if ensure_npm_dependencies is not None:
        ensure_npm_dependencies(REPO_DIR)
    os.makedirs(DRIVER_DIR, exist_ok=True)
    yield


# --------------------------------------------------------------------------- #
# Node driver helpers
# --------------------------------------------------------------------------- #

# Shared prelude: load the agent's factory, and expose a small `inject` helper
# that always returns {status, contentType, body, parseError, raw}.
_PRELUDE = r"""
'use strict'
const path = require('path')
const factoryPath = path.join(process.cwd(), 'examples', 'orders-listing.js')
const factory = require(factoryPath)

if (typeof factory !== 'function') {
  console.error('FACTORY_NOT_A_FUNCTION:' + (typeof factory))
  process.exit(3)
}

async function inject (app, opts) {
  const res = await app.inject(opts)
  let body = null
  let parseError = null
  try { body = JSON.parse(res.payload) } catch (e) { parseError = String(e && e.message) }
  return {
    status: res.statusCode,
    contentType: res.headers['content-type'] || '',
    body,
    parseError,
    raw: res.payload
  }
}

function out (obj) {
  process.stdout.write('@@RESULT@@' + JSON.stringify(obj) + '@@END@@\n')
}
"""


class TestFastifyPatterns:
    REPO_DIR = "/workspace/fastify"

    # ----------------------- internal utilities --------------------------- #

    def _run_node(self, body_src, timeout=120):
        """Write a Node script (prelude + body) into REPO_DIR and execute it.

        Returns the parsed @@RESULT@@ payload. Asserts the process succeeded and
        emitted exactly one structured result marker.
        """
        os.makedirs(DRIVER_DIR, exist_ok=True)
        # The body uses `await`; CommonJS has no top-level await, so wrap it in
        # an async IIFE that surfaces failures with a non-zero exit code.
        wrapped = (
            "\n;(async () => {\n"
            + textwrap.indent(textwrap.dedent(body_src), "  ")
            + "\n})().catch((e) => { console.error(e && e.stack ? e.stack : e); process.exit(1) })\n"
        )
        script = _PRELUDE + "\n" + wrapped
        # unique-ish name so concurrent runs don't clobber each other
        name = f"driver_{abs(hash(body_src)) % (10 ** 8)}.js"
        script_path = os.path.join(DRIVER_DIR, name)
        with open(script_path, "w") as fh:
            fh.write(script)
        try:
            proc = subprocess.run(
                ["node", script_path],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        finally:
            try:
                os.remove(script_path)
            except OSError:
                pass

        assert proc.returncode == 0, (
            "Node driver failed.\n"
            f"returncode={proc.returncode}\n"
            f"stdout={proc.stdout[-4000:]}\n"
            f"stderr={proc.stderr[-4000:]}"
        )
        marker = "@@RESULT@@"
        assert marker in proc.stdout, (
            "Driver produced no @@RESULT@@ marker.\n"
            f"stdout={proc.stdout[-4000:]}\nstderr={proc.stderr[-4000:]}"
        )
        chunk = proc.stdout.split(marker, 1)[1]
        chunk = chunk.split("@@END@@", 1)[0]
        return json.loads(chunk)

    # ============================== L1 =================================== #

    def test_l1_factory_module_exists(self):
        """L1: examples/orders-listing.js exists and is a non-empty file."""
        p = os.path.join(REPO_DIR, "examples", "orders-listing.js")
        assert os.path.isfile(p), f"missing deliverable: {p}"
        assert os.path.getsize(p) > 0, "orders-listing.js is empty"

    def test_l1_test_file_exists(self):
        """L1: test/orders-listing.test.js exists and references node:test + inject."""
        p = os.path.join(REPO_DIR, "test", "orders-listing.test.js")
        assert os.path.isfile(p), f"missing deliverable: {p}"
        with open(p) as fh:
            content = fh.read()
        assert os.path.getsize(p) > 0, "test file is empty"
        # sanity (not the discriminating check): must use node:test and inject
        assert "node:test" in content, "test must use the node:test runner"
        assert "inject" in content, "test must drive the instance via inject"

    def test_l1_factory_exports_function_and_no_listen(self):
        """L1: requiring the module yields a function with NO side-effect listen.

        We build one instance; if requiring/building it had bound a port, the
        server would report a bound address. We assert the export is callable and
        that building it neither throws nor opens a server.
        """
        res = self._run_node(
            """
            const app = factory()
            let addr = null
            try { addr = app.server && app.server.address ? app.server.address() : null } catch (e) {}
            await app.ready()
            out({ isFn: typeof factory === 'function', listening: !!(addr) })
            await app.close()
            """
        )
        assert res["isFn"] is True, "module.exports must be a factory function"
        assert res["listening"] is False, (
            "factory/require must not bind a network port"
        )

    # ============================== L2 =================================== #

    def test_l2_default_page(self):
        """L2: GET /orders (no query) -> 200, page=1, limit=10, 10 items, total=25(+)."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/orders' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 200, res
        body = res["body"]
        assert isinstance(body, dict), f"expected JSON object, got {body!r}"
        assert body.get("page") == 1, body
        assert body.get("limit") == 10, body
        # total is the count across ALL pages of the unfiltered dataset (>= 25)
        assert isinstance(body.get("total"), (int, float))
        assert body["total"] >= 25, f"dataset must seed >= 25 records: {body}"
        items = body.get("items")
        assert isinstance(items, list), "items must be an array"
        assert len(items) == 10, f"default page must return 10 items: {len(items)}"

    def test_l2_page_and_limit_are_json_numbers(self):
        """L2: page/limit in the body are JSON numbers, not strings (coercion).

        A naive handler that echoes req.query.page as a raw string fails here.
        We inspect the raw JSON text so a Python int/float round-trip cannot mask
        a stringified value.
        """
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/orders?page=2&limit=5' })
            const b = r.body
            out({
              status: r.status,
              pageType: typeof b.page,
              limitType: typeof b.limit,
              page: b.page,
              limit: b.limit,
              raw: r.raw
            })
            await app.close()
            """
        )
        assert res["status"] == 200, res
        assert res["pageType"] == "number", f"page must be a JSON number: {res}"
        assert res["limitType"] == "number", f"limit must be a JSON number: {res}"
        assert res["page"] == 2 and res["limit"] == 5, res
        # raw payload must not contain quoted numeric values for page/limit
        assert '"page":"2"' not in res["raw"], f"page serialized as string: {res['raw']}"
        assert '"limit":"5"' not in res["raw"], f"limit serialized as string: {res['raw']}"
        assert '"page":2' in res["raw"].replace(" ", ""), res["raw"]
        assert '"limit":5' in res["raw"].replace(" ", ""), res["raw"]

    def test_l2_item_field_whitelisting(self):
        """L2: each item exposes EXACTLY {id, customer, total, status}."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/orders' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 200, res
        items = res["body"]["items"]
        assert isinstance(items, list) and len(items) == 10
        allowed = {"id", "customer", "total", "status"}
        valid_status = {"open", "paid", "cancelled"}
        for it in items:
            assert set(it.keys()) == allowed, (
                f"item must expose exactly the 4 documented fields, got {sorted(it.keys())}"
            )
            assert isinstance(it["id"], str) and it["id"]
            assert isinstance(it["customer"], str)
            assert isinstance(it["total"], (int, float))
            assert it["status"] in valid_status, f"unexpected status: {it['status']}"

    def test_l2_last_page_partial(self):
        """L2: paging to the end returns a partial page; pagination math is real.

        With total T and limit L, the last page index is ceil(T/L); its size is
        T - (last-1)*L. We compute it from the observed total and assert the
        endpoint returns exactly that count (a stub that always returns `limit`
        items, or ignores `page`, fails).
        """
        res = self._run_node(
            """
            const app = factory()
            const base = await inject(app, { method: 'GET', url: '/orders?limit=10' })
            const total = base.body.total
            const limit = 10
            const lastPage = Math.ceil(total / limit)
            const last = await inject(app, { method: 'GET', url: '/orders?page=' + lastPage + '&limit=' + limit })
            const beyond = await inject(app, { method: 'GET', url: '/orders?page=' + (lastPage + 1) + '&limit=' + limit })
            await app.close()
            out({ total, lastPage, last: last.body, lastStatus: last.status, beyond: beyond.body, beyondStatus: beyond.status })
            """
        )
        total = res["total"]
        last_page = res["lastPage"]
        assert res["lastStatus"] == 200, res
        expected_last = total - (last_page - 1) * 10
        got_last = len(res["last"]["items"])
        assert got_last == expected_last, (
            f"last page must hold {expected_last} items (total={total}), got {got_last}"
        )
        assert res["last"]["page"] == last_page
        # A page past the end must be valid (>=1) and simply yield zero items.
        assert res["beyondStatus"] == 200, res
        assert len(res["beyond"]["items"]) == 0, "page past the end must be empty"

    def test_l2_pages_partition_dataset(self):
        """L2: consecutive pages cover distinct, non-overlapping records.

        Concatenating page 1..N (limit=10) must reproduce `total` records with no
        duplicate ids and no gaps. A handler that ignores `page` (always returns
        the first slice) is caught by the duplicate-id check.
        """
        res = self._run_node(
            """
            const app = factory()
            const first = await inject(app, { method: 'GET', url: '/orders?limit=10' })
            const total = first.body.total
            const limit = 10
            const pages = Math.ceil(total / limit)
            const ids = []
            for (let p = 1; p <= pages; p++) {
              const r = await inject(app, { method: 'GET', url: '/orders?page=' + p + '&limit=' + limit })
              for (const it of r.body.items) ids.push(it.id)
            }
            await app.close()
            const uniq = new Set(ids)
            out({ total, collected: ids.length, unique: uniq.size })
            """
        )
        assert res["collected"] == res["total"], (
            f"paging through all pages must yield total records: {res}"
        )
        assert res["unique"] == res["total"], (
            f"pages must not overlap (duplicate ids): {res}"
        )

    def test_l2_status_filter_exact_total(self):
        """L2: ?status=paid -> total == seeded paid count; every item is paid.

        We compute the true paid count by walking the FULL unfiltered dataset,
        then assert the filtered endpoint's `total` matches exactly and that
        every returned item carries status 'paid'. Pagination is applied after
        filtering, so filtered total must be <= unfiltered total.
        """
        res = self._run_node(
            """
            const app = factory()
            const all = await inject(app, { method: 'GET', url: '/orders?limit=50' })
            const fullTotal = all.body.total
            // Walk every page of the full dataset to count 'paid' independently.
            let paidCount = 0
            const pages = Math.ceil(fullTotal / 50)
            for (let p = 1; p <= pages; p++) {
              const r = await inject(app, { method: 'GET', url: '/orders?page=' + p + '&limit=50' })
              for (const it of r.body.items) if (it.status === 'paid') paidCount++
            }
            const filtered = await inject(app, { method: 'GET', url: '/orders?status=paid&limit=50' })
            await app.close()
            out({
              fullTotal,
              paidCount,
              filteredTotal: filtered.body.total,
              filteredStatuses: filtered.body.items.map(x => x.status),
              status: filtered.status
            })
            """
        )
        assert res["status"] == 200, res
        assert res["paidCount"] > 0, "dataset must seed at least one paid order"
        assert res["filteredTotal"] == res["paidCount"], (
            f"filtered total must equal seeded paid count: {res}"
        )
        assert res["filteredTotal"] <= res["fullTotal"]
        assert all(s == "paid" for s in res["filteredStatuses"]), (
            f"every filtered item must be paid: {res['filteredStatuses']}"
        )

    def test_l2_status_filter_then_paginate(self):
        """L2: status filter narrows the set AND pagination applies after filtering."""
        res = self._run_node(
            """
            const app = factory()
            const open1 = await inject(app, { method: 'GET', url: '/orders?status=open&limit=3&page=1' })
            const openAll = await inject(app, { method: 'GET', url: '/orders?status=open&limit=50' })
            await app.close()
            out({
              status: open1.status,
              page1Items: open1.body.items,
              page1Total: open1.body.total,
              page1Limit: open1.body.limit,
              allTotal: openAll.body.total,
              allStatuses: openAll.body.items.map(x => x.status)
            })
            """
        )
        assert res["status"] == 200, res
        # All filtered items are 'open'.
        assert all(s == "open" for s in res["allStatuses"]), res
        # total is consistent between a small-limit page and a large-limit page.
        assert res["page1Total"] == res["allTotal"], (
            "total must reflect the filtered set regardless of limit/page"
        )
        # Page is bounded by the requested limit.
        assert len(res["page1Items"]) <= 3, "limit=3 must cap the page size"
        assert all(it["status"] == "open" for it in res["page1Items"]), res

    def test_l2_invalid_queries_rejected_400(self):
        """L2: page=0, limit=0, limit=51, non-integer page, bad status -> 400.

        These are schema-level violations the framework must reject BEFORE the
        handler runs. A naive handler with no bounds/validation returns 200.
        """
        res = self._run_node(
            """
            const app = factory()
            const cases = {
              page0:    await inject(app, { method: 'GET', url: '/orders?page=0' }),
              limit0:   await inject(app, { method: 'GET', url: '/orders?limit=0' }),
              limit51:  await inject(app, { method: 'GET', url: '/orders?limit=51' }),
              pageFloat: await inject(app, { method: 'GET', url: '/orders?page=1.5' }),
              pageWord: await inject(app, { method: 'GET', url: '/orders?page=abc' }),
              badStatus: await inject(app, { method: 'GET', url: '/orders?status=bogus' }),
            }
            await app.close()
            const o = {}
            for (const k of Object.keys(cases)) {
              o[k] = { status: cases[k].status, statusCode: cases[k].body && cases[k].body.statusCode, ct: cases[k].contentType }
            }
            out(o)
            """
        )
        for key in ("page0", "limit0", "limit51", "pageFloat", "pageWord", "badStatus"):
            assert res[key]["status"] == 400, f"{key} must be rejected with 400: {res[key]}"
            assert res[key]["statusCode"] == 400, (
                f"{key} error body must carry statusCode 400: {res[key]}"
            )
            assert "json" in res[key]["ct"], f"{key} error must be JSON, not HTML"

    def test_l2_valid_status_values_accepted(self):
        """L2: the full closed set {open, paid, cancelled} is accepted (200).

        Guards against an over-strict implementation that only allows a subset.
        """
        res = self._run_node(
            """
            const app = factory()
            const o = {}
            for (const s of ['open', 'paid', 'cancelled']) {
              const r = await inject(app, { method: 'GET', url: '/orders?status=' + s })
              o[s] = { status: r.status, total: r.body && r.body.total, statuses: (r.body && r.body.items || []).map(x => x.status) }
            }
            await app.close()
            out(o)
            """
        )
        for s in ("open", "paid", "cancelled"):
            assert res[s]["status"] == 200, f"status={s} must be accepted: {res[s]}"
            assert isinstance(res[s]["total"], (int, float))
            assert all(x == s for x in res[s]["statuses"]), (
                f"status={s} filter leaked other statuses: {res[s]['statuses']}"
            )

    def test_l2_rejection_does_not_touch_dataset(self):
        """L2: a rejected request returns the framework error shape, not data.

        An invalid query must not leak any `items`/`total` payload; the response
        body is the standard Fastify error object.
        """
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/orders?limit=999' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 400, res
        body = res["body"]
        assert isinstance(body, dict), "error body must be a JSON object"
        assert body.get("statusCode") == 400, body
        assert isinstance(body.get("message"), str) and body["message"], body
        assert "items" not in body, "rejection must not return dataset items"
        assert "total" not in body, "rejection must not return a total"

    def test_l2_instances_isolated(self):
        """L2: each factory() call builds an independent instance/dataset."""
        res = self._run_node(
            """
            const a = factory()
            const b = factory()
            const ra = await inject(a, { method: 'GET', url: '/orders' })
            const rb = await inject(b, { method: 'GET', url: '/orders' })
            await a.close(); await b.close()
            out({ aTotal: ra.body.total, bTotal: rb.body.total, aStatus: ra.status, bStatus: rb.status })
            """
        )
        assert res["aStatus"] == 200 and res["bStatus"] == 200, res
        # Deterministic seeds => identical totals across independent instances.
        assert res["aTotal"] == res["bTotal"], (
            "deterministic seed must produce identical totals per instance"
        )
        assert res["aTotal"] >= 25

    def test_l2_native_node_test_passes(self):
        """L2: the agent's own suite passes via `node --test test/orders-listing.test.js`."""
        test_path = os.path.join(REPO_DIR, "test", "orders-listing.test.js")
        assert os.path.isfile(test_path), f"missing {test_path}"
        proc = subprocess.run(
            ["node", "--test", "test/orders-listing.test.js"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, (
            "native `node --test test/orders-listing.test.js` must pass.\n"
            f"stdout={proc.stdout[-5000:]}\nstderr={proc.stderr[-3000:]}"
        )
        combined = proc.stdout + proc.stderr
        assert "fail 0" in combined, (
            f"expected zero failures.\n{proc.stdout[-3000:]}"
        )
