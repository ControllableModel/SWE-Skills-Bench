"""Tests for the `fastify-patterns` skill task: Build an Encapsulated Catalog API Module.

Verifies the agent's work inside REPO_DIR (/workspace/fastify):

  - examples/catalog-api.js exports a no-argument factory that builds and returns
    a configured Fastify instance WITHOUT binding a network port on require.
  - The catalog routes live under the /api/catalog prefix inside an encapsulated
    registered unit (decorators / hooks / errors must not leak to the root).
  - The endpoints honor their input contracts: schema-driven validation (400),
    not-found (404) surfaced through the framework error shape, response shaping
    to exactly the four documented fields, and per-instance isolated seed data.
  - test/catalog-api.test.js exists and the native command
    `node --test test/catalog-api.test.js` passes.

Rather than trusting the agent-authored test file, the L2 cases independently
drive the factory through Fastify's in-process `inject` API using a fresh Node
driver written by THIS test, so a naive / hardcoded implementation fails.
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

# Shared prelude: load the agent's factory, build an instance, and expose a
# small `inject` helper that always returns {status, headers, body, raw}.
_PRELUDE = r"""
'use strict'
const path = require('path')
const factoryPath = path.join(process.cwd(), 'examples', 'catalog-api.js')
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
        """L1: examples/catalog-api.js exists and is a non-empty file."""
        p = os.path.join(REPO_DIR, "examples", "catalog-api.js")
        assert os.path.isfile(p), f"missing deliverable: {p}"
        assert os.path.getsize(p) > 0, "catalog-api.js is empty"

    def test_l1_test_file_exists(self):
        """L1: test/catalog-api.test.js exists and references node:test + inject."""
        p = os.path.join(REPO_DIR, "test", "catalog-api.test.js")
        assert os.path.isfile(p), f"missing deliverable: {p}"
        with open(p) as fh:
            content = fh.read()
        assert os.path.getsize(p) > 0, "test file is empty"
        # sanity (not the discriminating check): must use node:test and inject
        assert "node:test" in content, "test must use the node:test runner"
        assert "inject" in content, "test must drive the instance via inject"

    def test_l1_factory_exports_function_and_no_listen(self):
        """L1: requiring the module yields a function with NO side-effect listen.

        We require the module and build one instance; if requiring it had bound a
        port, a second build / the process would have an open socket. We assert the
        export is callable and that building it does not throw or open a server.
        """
        res = self._run_node(
            """
            const app = factory()
            // building must not auto-listen: server should have no bound address
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

    def test_l2_list_all_items_shape(self):
        """L2: GET /api/catalog/items -> 200 array, each item exactly 4 fields."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/api/catalog/items' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 200, res
        body = res["body"]
        assert isinstance(body, list), f"expected JSON array, got {body!r}"
        assert len(body) >= 3, "factory must seed at least three items"
        for item in body:
            assert set(item.keys()) == {"id", "name", "price", "tags"}, (
                f"item must expose exactly the 4 documented fields, got {item.keys()}"
            )
            assert isinstance(item["id"], str) and item["id"]
            assert isinstance(item["name"], str)
            assert isinstance(item["price"], (int, float)) and item["price"] > 0
            assert isinstance(item["tags"], list)

    def test_l2_routes_live_under_prefix(self):
        """L2: catalog routes are under /api/catalog; root path is NOT registered."""
        res = self._run_node(
            """
            const app = factory()
            const prefixed = await inject(app, { method: 'GET', url: '/api/catalog/items' })
            const unprefixed = await inject(app, { method: 'GET', url: '/items' })
            await app.close()
            out({ prefixed: prefixed.status, unprefixed: unprefixed.status })
            """
        )
        assert res["prefixed"] == 200, "items must be served under /api/catalog"
        assert res["unprefixed"] == 404, (
            "routes must be isolated under the /api/catalog prefix, not the root"
        )

    def test_l2_tag_filter(self):
        """L2: ?tag=<known> returns only items carrying that tag (real filtering)."""
        res = self._run_node(
            """
            const app = factory()
            const all = await inject(app, { method: 'GET', url: '/api/catalog/items' })
            // pick a tag that does NOT appear on every item if possible
            const items = all.body
            const counts = {}
            for (const it of items) for (const t of it.tags) counts[t] = (counts[t]||0)+1
            const tag = Object.keys(counts).sort((a,b)=>counts[a]-counts[b])[0]
            const filtered = await inject(app, { method: 'GET', url: '/api/catalog/items?tag=' + encodeURIComponent(tag) })
            await app.close()
            out({ tag, total: items.length, filtered: filtered.body, status: filtered.status })
            """
        )
        assert res["status"] == 200, res
        tag = res["tag"]
        filtered = res["filtered"]
        assert isinstance(filtered, list) and len(filtered) >= 1
        for item in filtered:
            assert tag in item["tags"], f"item {item['id']} lacks tag {tag}"
        # filtering must actually narrow when the tag isn't universal
        assert len(filtered) <= res["total"]

    def test_l2_empty_tag_rejected_400(self):
        """L2: ?tag= (empty) -> 400 via schema validation with error shape."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/api/catalog/items?tag=' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 400, f"empty tag must be rejected: {res}"
        body = res["body"]
        assert isinstance(body, dict), "error body must be JSON object"
        assert body.get("statusCode") == 400
        assert isinstance(body.get("message"), str) and body["message"]
        assert "json" in res["contentType"], "error must be JSON, not HTML"

    def test_l2_get_single_item(self):
        """L2: GET /api/catalog/items/:id returns the matching item only."""
        res = self._run_node(
            """
            const app = factory()
            const all = await inject(app, { method: 'GET', url: '/api/catalog/items' })
            const target = all.body[1] || all.body[0]
            const r = await inject(app, { method: 'GET', url: '/api/catalog/items/' + encodeURIComponent(target.id) })
            await app.close()
            out({ target, got: r.body, status: r.status })
            """
        )
        assert res["status"] == 200, res
        got = res["got"]
        assert set(got.keys()) == {"id", "name", "price", "tags"}
        assert got["id"] == res["target"]["id"]
        assert got["name"] == res["target"]["name"]

    def test_l2_not_found_404_error_shape(self):
        """L2: unknown id -> 404 with framework error shape (statusCode==404)."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/api/catalog/items/__definitely_missing__' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 404, f"unknown id must 404: {res}"
        body = res["body"]
        assert isinstance(body, dict), "404 body must be a JSON object"
        assert body.get("statusCode") == 404, body
        assert isinstance(body.get("message"), str) and body["message"]
        assert "json" in res["contentType"], "not-found must be JSON, not HTML"

    def test_l2_create_then_retrieve(self):
        """L2: POST valid body -> 201 + created item with new id; then GET it."""
        res = self._run_node(
            """
            const app = factory()
            const payload = { name: 'Widget-XYZ', price: 12.5, tags: ['bench', 'created'] }
            const created = await inject(app, {
              method: 'POST', url: '/api/catalog/items',
              headers: { 'content-type': 'application/json' },
              payload
            })
            let fetched = null
            if (created.body && created.body.id) {
              fetched = await inject(app, { method: 'GET', url: '/api/catalog/items/' + encodeURIComponent(created.body.id) })
            }
            await app.close()
            out({ created, fetched })
            """
        )
        created = res["created"]
        assert created["status"] == 201, f"valid POST must return 201: {created}"
        cb = created["body"]
        assert isinstance(cb, dict)
        assert set(cb.keys()) == {"id", "name", "price", "tags"}, (
            "created item must expose exactly the 4 fields"
        )
        assert isinstance(cb["id"], str) and cb["id"], "server must assign an id"
        assert cb["name"] == "Widget-XYZ"
        assert cb["price"] == 12.5
        assert cb["tags"] == ["bench", "created"]
        fetched = res["fetched"]
        assert fetched is not None, "created id was not retrievable"
        assert fetched["status"] == 200, "created item must be GETtable"
        assert fetched["body"]["id"] == cb["id"]
        assert fetched["body"]["name"] == "Widget-XYZ"

    def test_l2_invalid_body_price_zero_rejected(self):
        """L2: POST price:0 -> 400 and catalog length unchanged (schema bound)."""
        res = self._run_node(
            """
            const app = factory()
            const before = (await inject(app, { method: 'GET', url: '/api/catalog/items' })).body.length
            const r = await inject(app, {
              method: 'POST', url: '/api/catalog/items',
              headers: { 'content-type': 'application/json' },
              payload: { name: 'Cheap', price: 0, tags: ['x'] }
            })
            const after = (await inject(app, { method: 'GET', url: '/api/catalog/items' })).body.length
            await app.close()
            out({ status: r.status, body: r.body, before, after })
            """
        )
        assert res["status"] == 400, f"price:0 must be rejected: {res}"
        assert isinstance(res["body"], dict)
        assert res["body"].get("statusCode") == 400
        assert res["before"] == res["after"], "rejected POST must not mutate catalog"

    def test_l2_invalid_body_missing_field_and_bad_tags(self):
        """L2: missing `name`, empty `name`, and structurally-bad `tags` -> 400.

        These are unambiguous contract violations that the framework's body schema
        must catch regardless of type-coercion settings (a missing required field,
        a minLength violation, and a `tags` value that cannot be coerced to an
        array of strings). The catalog length must be unchanged after all three.
        """
        res = self._run_node(
            """
            const app = factory()
            const before = (await inject(app, { method: 'GET', url: '/api/catalog/items' })).body.length
            const missing = await inject(app, {
              method: 'POST', url: '/api/catalog/items',
              headers: { 'content-type': 'application/json' },
              payload: { price: 5, tags: ['a'] }            // no name
            })
            const emptyName = await inject(app, {
              method: 'POST', url: '/api/catalog/items',
              headers: { 'content-type': 'application/json' },
              payload: { name: '', price: 5, tags: ['a'] }  // violates minLength
            })
            const badTags = await inject(app, {
              method: 'POST', url: '/api/catalog/items',
              headers: { 'content-type': 'application/json' },
              payload: { name: 'Bad', price: 5, tags: { not: 'an array' } }
            })
            const after = (await inject(app, { method: 'GET', url: '/api/catalog/items' })).body.length
            await app.close()
            out({ missing, emptyName, badTags, before, after })
            """
        )
        assert res["missing"]["status"] == 400, f"missing name must 400: {res['missing']}"
        assert res["missing"]["body"].get("statusCode") == 400
        assert res["emptyName"]["status"] == 400, f"empty name must 400: {res['emptyName']}"
        assert res["emptyName"]["body"].get("statusCode") == 400
        assert res["badTags"]["status"] == 400, f"structurally invalid tags must 400: {res['badTags']}"
        assert res["badTags"]["body"].get("statusCode") == 400
        assert res["before"] == res["after"], "invalid POSTs must not mutate catalog"

    def test_l2_response_shaping_hides_internal_fields(self):
        """L2: even if records carry extra internal fields, only the 4 documented
        fields are serialized.

        We POST an item with an extra bogus property; the schema-driven response
        serializer must strip it from every read path.
        """
        res = self._run_node(
            """
            const app = factory()
            const created = await inject(app, {
              method: 'POST', url: '/api/catalog/items',
              headers: { 'content-type': 'application/json' },
              payload: { name: 'Shaped', price: 3, tags: ['t'], secret: 'LEAK', __proto_internal: 1 }
            })
            let single = null
            if (created.body && created.body.id) {
              single = await inject(app, { method: 'GET', url: '/api/catalog/items/' + encodeURIComponent(created.body.id) })
            }
            const list = await inject(app, { method: 'GET', url: '/api/catalog/items' })
            await app.close()
            out({ created, single, list })
            """
        )
        # Successful creation regardless (extra props ignored by validation)
        assert res["created"]["status"] in (201, 400), res["created"]
        if res["created"]["status"] == 201:
            assert "secret" not in res["created"]["body"], "internal field leaked in 201 body"
            assert set(res["created"]["body"].keys()) == {"id", "name", "price", "tags"}
            assert res["single"] is not None and res["single"]["status"] == 200
            assert "secret" not in res["single"]["body"], "internal field leaked in GET :id"
            assert set(res["single"]["body"].keys()) == {"id", "name", "price", "tags"}
        # In all cases, list items expose exactly the 4 fields
        for item in res["list"]["body"]:
            assert set(item.keys()) == {"id", "name", "price", "tags"}, item

    def test_l2_instances_isolated(self):
        """L2: each factory() call is independent; POST to one must not leak."""
        res = self._run_node(
            """
            const a = factory()
            const b = factory()
            const beforeB = (await inject(b, { method: 'GET', url: '/api/catalog/items' })).body.length
            await inject(a, {
              method: 'POST', url: '/api/catalog/items',
              headers: { 'content-type': 'application/json' },
              payload: { name: 'OnlyA', price: 9, tags: ['iso'] }
            })
            const afterA = (await inject(a, { method: 'GET', url: '/api/catalog/items' })).body.length
            const afterB = (await inject(b, { method: 'GET', url: '/api/catalog/items' })).body.length
            await a.close(); await b.close()
            out({ beforeB, afterA, afterB })
            """
        )
        assert res["afterB"] == res["beforeB"], (
            "POST to instance A must not affect instance B (no global singleton)"
        )

    def test_l2_native_node_test_passes(self):
        """L2: the agent's own suite passes via `node --test test/catalog-api.test.js`."""
        test_path = os.path.join(REPO_DIR, "test", "catalog-api.test.js")
        assert os.path.isfile(test_path), f"missing {test_path}"
        proc = subprocess.run(
            ["node", "--test", "test/catalog-api.test.js"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, (
            "native `node --test test/catalog-api.test.js` must pass.\n"
            f"stdout={proc.stdout[-5000:]}\nstderr={proc.stderr[-3000:]}"
        )
        combined = proc.stdout + proc.stderr
        assert "fail 0" in combined.replace("# ", "# "), (
            f"expected zero failures.\n{proc.stdout[-3000:]}"
        )
