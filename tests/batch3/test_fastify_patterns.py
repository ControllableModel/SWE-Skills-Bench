"""Tests for the `fastify-patterns` skill task (variant ext3):
Assemble Two Independently Encapsulated API Versions.

Verifies the agent's work inside REPO_DIR (/workspace/fastify):

  - examples/versioned-api.js exports a no-argument factory that builds and
    returns a configured Fastify instance via `require('..')` WITHOUT binding a
    network port when imported/built.
  - The instance mounts TWO independently encapsulated registered units, one
    under the URL prefix /api/v1 and one under /api/v2. Each unit privately
    attaches a per-group version value ("v1" / "v2") that is visible only inside
    its own unit and is NOT reachable from the other unit or from the root
    instance once `ready()` has resolved.
  - Endpoint contracts:
      GET /api/v1/info -> 200 { version: "v1", fields: ["id","name"] }
      GET /api/v2/info -> 200 { version: "v2", fields: ["id","name","email"] }
      GET /api/v1/ping and /api/v2/ping -> 200 { pong: true }
      GET /api/v3/info (unknown prefix) -> 404
  - test/versioned-api.test.js exists, uses node:test + inject, and the native
    command `node --test test/versioned-api.test.js` passes.

Rather than trusting the agent-authored test file, the L2 cases independently
drive the factory through Fastify's in-process `inject` API using a fresh Node
driver written by THIS test. A flat implementation that registers both route
groups on the root and reads a single shared variable (so the root DOES expose
the private version value, or the two groups share one value) MUST fail the
isolation cases below.
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
const factoryPath = path.join(process.cwd(), 'examples', 'versioned-api.js')
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
        # CommonJS has no top-level await; wrap the body in an async IIFE that
        # surfaces failures with a non-zero exit code.
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
        """L1: examples/versioned-api.js exists and is a non-empty file."""
        p = os.path.join(REPO_DIR, "examples", "versioned-api.js")
        assert os.path.isfile(p), f"missing deliverable: {p}"
        assert os.path.getsize(p) > 0, "versioned-api.js is empty"

    def test_l1_test_file_exists(self):
        """L1: test/versioned-api.test.js exists and references node:test + inject."""
        p = os.path.join(REPO_DIR, "test", "versioned-api.test.js")
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
        server would carry a bound address. We assert the export is callable and
        that building it does not throw or open a server.
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
        assert res["listening"] is False, "factory/require must not bind a network port"

    # ============================== L2 =================================== #

    def test_l2_v1_info_body(self):
        """L2: GET /api/v1/info -> 200, exact body {version:"v1", fields:["id","name"]}."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/api/v1/info' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 200, res
        body = res["body"]
        assert isinstance(body, dict), f"expected JSON object, got {body!r}"
        assert body.get("version") == "v1", f"v1 version wrong: {body}"
        assert body.get("fields") == ["id", "name"], f"v1 fields wrong: {body}"
        assert "json" in res["contentType"], "response must be JSON"

    def test_l2_v2_info_body(self):
        """L2: GET /api/v2/info -> 200, exact body {version:"v2", fields:["id","name","email"]}."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/api/v2/info' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 200, res
        body = res["body"]
        assert isinstance(body, dict), f"expected JSON object, got {body!r}"
        assert body.get("version") == "v2", f"v2 version wrong: {body}"
        assert body.get("fields") == ["id", "name", "email"], f"v2 fields wrong: {body}"
        assert "json" in res["contentType"], "response must be JSON"

    def test_l2_versions_distinct(self):
        """L2: the two /info endpoints differ in BOTH version and fields.

        A naive impl that duplicates one literal across both handlers (ignoring
        per-group encapsulation) tends to make these collapse; this case fails
        unless the two groups are genuinely distinct.
        """
        res = self._run_node(
            """
            const app = factory()
            const v1 = await inject(app, { method: 'GET', url: '/api/v1/info' })
            const v2 = await inject(app, { method: 'GET', url: '/api/v2/info' })
            await app.close()
            out({ v1: v1.body, v2: v2.body })
            """
        )
        v1, v2 = res["v1"], res["v2"]
        assert v1["version"] == "v1" and v2["version"] == "v2"
        assert v1["version"] != v2["version"], "versions must differ between groups"
        assert v1["fields"] != v2["fields"], "fields must differ between v1 and v2"
        assert "email" not in v1["fields"], "v1 must not expose v2's email field"
        assert "email" in v2["fields"], "v2 must expose the email field"

    def test_l2_both_ping(self):
        """L2: GET /api/v1/ping and /api/v2/ping -> 200, body {pong:true} each."""
        res = self._run_node(
            """
            const app = factory()
            const p1 = await inject(app, { method: 'GET', url: '/api/v1/ping' })
            const p2 = await inject(app, { method: 'GET', url: '/api/v2/ping' })
            await app.close()
            out({ p1, p2 })
            """
        )
        for key in ("p1", "p2"):
            r = res[key]
            assert r["status"] == 200, f"{key} must be 200: {r}"
            assert isinstance(r["body"], dict), f"{key} body must be object: {r}"
            assert r["body"].get("pong") is True, f"{key} body must be {{pong:true}}: {r}"

    def test_l2_unknown_prefix_404(self):
        """L2: GET /api/v3/info (unregistered prefix) -> 404 JSON error shape."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/api/v3/info' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 404, f"unknown prefix must 404: {res}"
        body = res["body"]
        assert isinstance(body, dict), "404 body must be JSON object"
        assert body.get("statusCode") == 404, body
        assert "json" in res["contentType"], "not-found must be JSON, not HTML"

    def test_l2_routes_only_under_prefixes(self):
        """L2: /info and /ping are served ONLY under the version prefixes.

        Hitting the bare /info or /ping at the root must 404 — proving routes
        live inside encapsulated prefixed units, not flat on the root.
        """
        res = self._run_node(
            """
            const app = factory()
            const rootInfo = await inject(app, { method: 'GET', url: '/info' })
            const rootPing = await inject(app, { method: 'GET', url: '/ping' })
            const v1 = await inject(app, { method: 'GET', url: '/api/v1/info' })
            await app.close()
            out({ rootInfo: rootInfo.status, rootPing: rootPing.status, v1: v1.status })
            """
        )
        assert res["v1"] == 200, "prefixed route must resolve"
        assert res["rootInfo"] == 404, "/info must NOT be registered on the root"
        assert res["rootPing"] == 404, "/ping must NOT be registered on the root"

    def test_l2_version_value_not_on_root(self):
        """L2: ISOLATION — the per-group private version value is NOT on the root.

        We probe a broad set of plausible decorator/property names for the
        private per-version value and assert NONE of them are present on the
        root instance after ready(), and that no root property equals the string
        "v1" or "v2". A flat implementation that decorates the root (or reads a
        shared root-level variable) MUST fail here.
        """
        res = self._run_node(
            """
            const app = factory()
            await app.ready()
            const candidates = [
              'version', 'apiVersion', 'versionTag', 'tag', 'versionValue',
              'v', 'groupVersion', 'currentVersion', 'name'
            ]
            const hasDecorator = {}
            const values = {}
            for (const c of candidates) {
              let h = false
              try { h = typeof app.hasDecorator === 'function' ? app.hasDecorator(c) : (c in app) } catch (e) { h = false }
              hasDecorator[c] = h
              try { values[c] = (c in app) ? app[c] : undefined } catch (e) { values[c] = undefined }
            }
            // collect any own enumerable root prop whose value is exactly 'v1'/'v2'
            let leakedString = false
            try {
              for (const k of Object.keys(app)) {
                const val = app[k]
                if (val === 'v1' || val === 'v2') { leakedString = true; break }
              }
            } catch (e) {}
            await app.close()
            out({ hasDecorator, values, leakedString })
            """
        )
        hd = res["hasDecorator"]
        vals = res["values"]
        # The dedicated decorator-style names must not be present on the root.
        for name in ("apiVersion", "versionTag", "versionValue", "groupVersion", "currentVersion"):
            assert hd.get(name) is False, (
                f"root must NOT expose the private per-version decorator '{name}' (leak/flat impl)"
            )
        # No probed root property may carry a version string value.
        for name, v in vals.items():
            assert v not in ("v1", "v2"), (
                f"root property '{name}' leaks a private version value {v!r}"
            )
        assert res["leakedString"] is False, (
            "no root-level property may equal 'v1'/'v2' after ready() (encapsulation broken)"
        )

    def test_l2_version_value_not_cross_group(self):
        """L2: ISOLATION — v1's body must never carry v2's version and vice versa.

        Repeated/interleaved requests must always return the correct per-group
        version, proving each handler reads ITS OWN encapsulated value rather
        than a single shared mutable variable that could bleed across groups.
        """
        res = self._run_node(
            """
            const app = factory()
            const seq = []
            for (let i = 0; i < 4; i++) {
              const a = await inject(app, { method: 'GET', url: '/api/v1/info' })
              const b = await inject(app, { method: 'GET', url: '/api/v2/info' })
              seq.push([a.body && a.body.version, b.body && b.body.version])
            }
            // fire both concurrently too, to catch shared-mutable-state bleed
            const [c, d] = await Promise.all([
              inject(app, { method: 'GET', url: '/api/v1/info' }),
              inject(app, { method: 'GET', url: '/api/v2/info' })
            ])
            await app.close()
            out({ seq, concurrent: [c.body.version, d.body.version] })
            """
        )
        for pair in res["seq"]:
            assert pair == ["v1", "v2"], f"per-group version bled across requests: {pair}"
        assert res["concurrent"] == ["v1", "v2"], (
            f"concurrent requests show shared-state bleed: {res['concurrent']}"
        )

    def test_l2_info_version_derived_from_group_value(self):
        """L2: the /info `version` matches the group's own prefix, not a duplicate.

        v1 endpoint must report "v1" and v2 must report "v2"; swapping/sharing a
        single literal would make at least one of these wrong.
        """
        res = self._run_node(
            """
            const app = factory()
            const v1 = await inject(app, { method: 'GET', url: '/api/v1/info' })
            const v2 = await inject(app, { method: 'GET', url: '/api/v2/info' })
            await app.close()
            out({ v1: v1.body.version, v2: v2.body.version })
            """
        )
        assert res["v1"] == "v1", f"v1 group must report its own version: {res}"
        assert res["v2"] == "v2", f"v2 group must report its own version: {res}"

    def test_l2_instances_independent(self):
        """L2: each factory() call yields an independent instance (no global singleton)."""
        res = self._run_node(
            """
            const a = factory()
            const b = factory()
            const ra = await inject(a, { method: 'GET', url: '/api/v1/info' })
            const rb = await inject(b, { method: 'GET', url: '/api/v2/info' })
            const sameRef = (a === b)
            await a.close(); await b.close()
            out({ a: ra.body, b: rb.body, sameRef })
            """
        )
        assert res["sameRef"] is False, "factory() must build a fresh instance each call"
        assert res["a"]["version"] == "v1"
        assert res["b"]["version"] == "v2"

    def test_l2_native_node_test_passes(self):
        """L2: the agent's own suite passes via `node --test test/versioned-api.test.js`."""
        test_path = os.path.join(REPO_DIR, "test", "versioned-api.test.js")
        assert os.path.isfile(test_path), f"missing {test_path}"
        proc = subprocess.run(
            ["node", "--test", "test/versioned-api.test.js"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, (
            "native `node --test test/versioned-api.test.js` must pass.\n"
            f"stdout={proc.stdout[-5000:]}\nstderr={proc.stderr[-3000:]}"
        )
        combined = proc.stdout + proc.stderr
        assert "fail 0" in combined, f"expected zero failures.\n{proc.stdout[-3000:]}"
