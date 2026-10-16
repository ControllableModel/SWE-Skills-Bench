"""Tests for the `fastify-patterns` skill task (variant ext5):
Implement a Custom Not-Found Handler with Suggestions.

Verifies the agent's work inside REPO_DIR (/workspace/fastify):

  - examples/not-found-handler.js exports a no-argument factory that builds and
    returns a configured Fastify instance WITHOUT binding a network port on
    require/build.
  - The instance registers a fixed set of known routes (GET /docs, GET /users,
    POST /users), each returning 200 with a small self-identifying JSON body.
  - Every unmatched request is answered by a CUSTOM not-found responder (installed
    via the framework's not-found mechanism, not a wildcard catch-all and not the
    framework default 404 body). The 404 body has EXACTLY four fields:
    statusCode (404), message (non-empty string), requested (requested path),
    available (sorted, de-duplicated array of the registered paths).
  - A method that is NOT registered on a path that IS registered for other methods
    (DELETE /users) resolves to the same custom 404 with requested == "/users".
  - test/not-found-handler.test.js exists and the native command
    `node --test test/not-found-handler.test.js` passes.

Rather than trusting the agent-authored test file, the L2 cases independently
drive the factory through Fastify's in-process `inject` API using a fresh Node
driver written by THIS test. A naive implementation that special-cases a couple
of literal paths, hardcodes `available`, or returns the framework default 404
body must fail these assertions.
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

# Shared prelude: load the agent's factory, expose a small `inject` helper that
# always returns {status, contentType, body, parseError, raw}.
_PRELUDE = r"""
'use strict'
const path = require('path')
const factoryPath = path.join(process.cwd(), 'examples', 'not-found-handler.js')
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
        """L1: examples/not-found-handler.js exists and is a non-empty file."""
        p = os.path.join(REPO_DIR, "examples", "not-found-handler.js")
        assert os.path.isfile(p), f"missing deliverable: {p}"
        assert os.path.getsize(p) > 0, "not-found-handler.js is empty"

    def test_l1_test_file_exists(self):
        """L1: test/not-found-handler.test.js exists and uses node:test + inject."""
        p = os.path.join(REPO_DIR, "test", "not-found-handler.test.js")
        assert os.path.isfile(p), f"missing deliverable: {p}"
        with open(p) as fh:
            content = fh.read()
        assert os.path.getsize(p) > 0, "test file is empty"
        # sanity (not the discriminating check): must use node:test and inject
        assert "node:test" in content, "test must use the node:test runner"
        assert "inject" in content, "test must drive the instance via inject"

    def test_l1_factory_exports_function_and_no_listen(self):
        """L1: requiring the module yields a function with NO side-effect listen.

        We require the module and build one instance; building it must not bind a
        port (server has no bound address) and must not throw.
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

    def test_l2_known_routes_return_200(self):
        """L2: GET /docs, GET /users, POST /users each return 200 + self-id JSON.

        Per the doc, each known route returns 200 with a small JSON body that
        identifies itself (e.g. { route: "GET /docs" }). A stub that returns a
        bare 200 with no/odd body fails here.
        """
        res = self._run_node(
            """
            const app = factory()
            const docs = await inject(app, { method: 'GET', url: '/docs' })
            const usersGet = await inject(app, { method: 'GET', url: '/users' })
            const usersPost = await inject(app, {
              method: 'POST', url: '/users',
              headers: { 'content-type': 'application/json' },
              payload: {}
            })
            await app.close()
            out({ docs, usersGet, usersPost })
            """
        )
        for key, expect_route in (
            ("docs", "GET /docs"),
            ("usersGet", "GET /users"),
            ("usersPost", "POST /users"),
        ):
            r = res[key]
            assert r["status"] == 200, f"{key} must be 200: {r}"
            assert isinstance(r["body"], dict), f"{key} body must be JSON object: {r}"
            assert r["body"].get("route") == expect_route, (
                f"{key} must self-identify as {expect_route!r}, got {r['body']}"
            )

    def test_l2_unknown_path_returns_structured_404(self):
        """L2: GET /nope -> 404 with EXACTLY the four documented fields.

        statusCode==404 (number), message non-empty string, requested=='/nope',
        available is an array of strings. No extra/missing keys. The framework
        default 404 body (which lacks `requested`/`available`) must fail.
        """
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/nope' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 404, f"unknown path must 404: {res}"
        body = res["body"]
        assert isinstance(body, dict), f"404 body must be JSON object: {res}"
        assert set(body.keys()) == {"statusCode", "message", "requested", "available"}, (
            f"404 body must have EXACTLY the four documented fields, got {sorted(body.keys())}"
        )
        assert body["statusCode"] == 404 and isinstance(body["statusCode"], int), body
        assert isinstance(body["message"], str) and body["message"].strip(), body
        assert body["requested"] == "/nope", body
        assert isinstance(body["available"], list), body
        assert all(isinstance(x, str) for x in body["available"]), body
        assert "json" in res["contentType"], "not-found must be JSON, not HTML"

    def test_l2_available_sorted_unique_and_contains_known_paths(self):
        """L2: `available` is sorted ascending, has no duplicates, and lists the
        real registered paths (must include /docs and /users)."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/totally-unknown' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 404, res
        avail = res["body"]["available"]
        assert isinstance(avail, list) and avail, "available must be a non-empty list"
        assert avail == sorted(avail), f"available must be sorted ascending: {avail}"
        assert len(avail) == len(set(avail)), f"available must have no duplicates: {avail}"
        assert "/docs" in avail, f"available must include /docs: {avail}"
        assert "/users" in avail, f"available must include /users: {avail}"

    def test_l2_requested_reflects_actual_path(self):
        """L2: `requested` echoes the actual path of each unmatched request,
        not a hardcoded constant. Two different unknown paths must echo back
        differently."""
        res = self._run_node(
            """
            const app = factory()
            const a = await inject(app, { method: 'GET', url: '/alpha/missing' })
            const b = await inject(app, { method: 'GET', url: '/beta' })
            await app.close()
            out({ a, b })
            """
        )
        assert res["a"]["status"] == 404 and res["b"]["status"] == 404, res
        assert res["a"]["body"]["requested"] == "/alpha/missing", res["a"]["body"]
        assert res["b"]["body"]["requested"] == "/beta", res["b"]["body"]
        assert res["a"]["body"]["requested"] != res["b"]["body"]["requested"], (
            "requested must reflect the real path, not a fixed string"
        )

    def test_l2_unsupported_method_on_known_path(self):
        """L2: DELETE /users (method not registered on a registered path) -> 404
        via the SAME custom responder, with requested == '/users'.

        This distinguishes a real not-found mechanism (Fastify routes unmatched
        methods to the not-found handler) from a wildcard catch-all that only
        matches GET. The structured body proves it went through the custom
        responder, not the framework default."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'DELETE', url: '/users' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 404, f"DELETE /users must 404: {res}"
        body = res["body"]
        assert isinstance(body, dict), body
        assert set(body.keys()) == {"statusCode", "message", "requested", "available"}, (
            f"unsupported-method 404 must use the custom responder shape, got {sorted(body.keys())}"
        )
        assert body["statusCode"] == 404, body
        assert body["requested"] == "/users", (
            f"requested must reflect the known path /users, got {body['requested']!r}"
        )
        assert "/users" in body["available"], body

    def test_l2_available_derived_not_hardcoded(self):
        """L2: `available` is derived from the real route table.

        We register an EXTRA route on a fresh instance built from the same module
        source (via the framework's own route() on the returned instance is not
        possible after ready; instead we assert internal consistency): every path
        in `available` must actually resolve to a non-404 for at least one method,
        and the known paths are present. A hardcoded literal that lists phantom
        paths would expose paths that 404 for every method."""
        res = self._run_node(
            """
            const app = factory()
            const nf = await inject(app, { method: 'GET', url: '/__probe_missing__' })
            const avail = nf.body.available
            // For each advertised path, probe common methods; at least one must
            // be a registered (non-404) route -> proves the list mirrors reality.
            const methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
            const probe = {}
            for (const p of avail) {
              let resolved = false
              for (const m of methods) {
                const rr = await inject(app, { method: m, url: p })
                if (rr.status !== 404) { resolved = true; break }
              }
              probe[p] = resolved
            }
            await app.close()
            out({ avail, probe })
            """
        )
        avail = res["avail"]
        probe = res["probe"]
        assert avail, "available must not be empty"
        for p, resolved in probe.items():
            assert resolved is True, (
                f"advertised path {p!r} resolves to 404 for every method -> "
                "available appears hardcoded / does not mirror the real route table"
            )

    def test_l2_method_not_found_for_truly_unknown_path(self):
        """L2: a non-GET method against a totally unknown path also flows through
        the custom responder (uniform installation), not the default 404."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, {
              method: 'PUT', url: '/no/such/route',
              headers: { 'content-type': 'application/json' },
              payload: {}
            })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 404, res
        body = res["body"]
        assert set(body.keys()) == {"statusCode", "message", "requested", "available"}, (
            f"custom responder must apply uniformly, got {sorted(body.keys())}"
        )
        assert body["requested"] == "/no/such/route", body
        assert body["statusCode"] == 404, body

    def test_l2_known_routes_not_swallowed_by_notfound(self):
        """L2: the not-found responder must NOT swallow registered routes.

        A buggy catch-all wildcard could intercept everything and turn /docs into
        a 404. Assert a known route still returns its 200 self-id body even when
        the not-found machinery is present."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/docs' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 200, f"/docs must remain a real 200 route: {res}"
        assert isinstance(res["body"], dict), res
        assert res["body"].get("route") == "GET /docs", res["body"]
        # And it must NOT carry the not-found shape.
        assert "available" not in res["body"], (
            "a known route must not be answered by the not-found responder"
        )

    def test_l2_instances_independent(self):
        """L2: each factory() call yields an independent instance (no shared
        singleton); both expose the same custom 404 shape independently."""
        res = self._run_node(
            """
            const a = factory()
            const b = factory()
            const ra = await inject(a, { method: 'GET', url: '/missing-a' })
            const rb = await inject(b, { method: 'GET', url: '/missing-b' })
            await a.close(); await b.close()
            out({ ra, rb })
            """
        )
        assert res["ra"]["status"] == 404 and res["rb"]["status"] == 404, res
        assert res["ra"]["body"]["requested"] == "/missing-a", res["ra"]["body"]
        assert res["rb"]["body"]["requested"] == "/missing-b", res["rb"]["body"]
        for key in ("ra", "rb"):
            assert set(res[key]["body"].keys()) == {
                "statusCode", "message", "requested", "available"
            }, res[key]["body"]

    def test_l2_native_node_test_passes(self):
        """L2: the agent's own suite passes via
        `node --test test/not-found-handler.test.js`."""
        test_path = os.path.join(REPO_DIR, "test", "not-found-handler.test.js")
        assert os.path.isfile(test_path), f"missing {test_path}"
        proc = subprocess.run(
            ["node", "--test", "test/not-found-handler.test.js"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, (
            "native `node --test test/not-found-handler.test.js` must pass.\n"
            f"stdout={proc.stdout[-5000:]}\nstderr={proc.stderr[-3000:]}"
        )
        combined = proc.stdout + proc.stderr
        assert "fail 0" in combined, (
            f"expected zero failures.\n{proc.stdout[-3000:]}"
        )
