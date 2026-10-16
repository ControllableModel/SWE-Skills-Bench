"""Tests for the `fastify-patterns` skill task (variant ext6):
Build a Request Lifecycle Audit and Normalization Pipeline.

Verifies the agent's work inside REPO_DIR (/workspace/fastify):

  - examples/audit-pipeline.js exports a no-argument factory that builds and
    returns a configured Fastify instance WITHOUT binding a network port on
    require, and exposes a readable in-memory audit trail (e.g.
    `app.auditTrail()` returning the recorded array).
  - POST /signup has a body schema requiring `email` and `name` (strings). A
    lifecycle step running AFTER schema validation and BEFORE the handler
    normalizes the validated body: `email` lowercased + trimmed, `name`
    trimmed. The handler echoes the already-clean `{ email, name }` with 200.
  - A body that fails the schema (missing email / wrong type) -> 400 BEFORE
    normalization and BEFORE the handler, and is NOT appended to the trail.
  - A lifecycle step running AFTER the response appends exactly one record
    { method, url, statusCode } per finished request, in request order. The
    trail starts empty and persists across requests; each factory() call has
    its own independent trail.
  - GET /audit -> 200 returns the current trail as a JSON array.
  - test/audit-pipeline.test.js exists and the native command
    `node --test test/audit-pipeline.test.js` passes.

Discriminative strategy: rather than trusting the agent-authored test file,
the L2 cases independently drive the factory through Fastify's in-process
`inject` API using a fresh Node driver written by THIS test. A naive
implementation that normalizes inside the handler, records rejected requests,
records in the wrong order, shares a global trail across instances, or omits
the after-response recording will fail these cases. The agent's own
`node --test` suite is also executed as a final gate.
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

# Shared prelude: load the agent's factory, expose helpers to inject requests
# (always returning {status, headers, body, raw}) and to read the audit trail
# via whichever accessor shape the agent chose (method or property).
_PRELUDE = r"""
'use strict'
const path = require('path')
const factoryPath = path.join(process.cwd(), 'examples', 'audit-pipeline.js')
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

// The doc suggests `app.auditTrail()` but allows "an instance accessor such
// as". Resolve the trail array tolerantly: a method named auditTrail, or a
// property/decorator holding the array. We never fall back to GET /audit here
// (that path is tested separately), so the *decorator* contract is exercised.
function trail (app) {
  if (typeof app.auditTrail === 'function') return app.auditTrail()
  if (Array.isArray(app.auditTrail)) return app.auditTrail
  if (typeof app.getAuditTrail === 'function') return app.getAuditTrail()
  if (Array.isArray(app.auditTrail)) return app.auditTrail
  throw new Error('NO_AUDIT_TRAIL_ACCESSOR')
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
        """L1: examples/audit-pipeline.js exists and is a non-empty file."""
        p = os.path.join(REPO_DIR, "examples", "audit-pipeline.js")
        assert os.path.isfile(p), f"missing deliverable: {p}"
        assert os.path.getsize(p) > 0, "audit-pipeline.js is empty"

    def test_l1_test_file_exists(self):
        """L1: test/audit-pipeline.test.js exists and uses node:test + inject."""
        p = os.path.join(REPO_DIR, "test", "audit-pipeline.test.js")
        assert os.path.isfile(p), f"missing deliverable: {p}"
        assert os.path.getsize(p) > 0, "test file is empty"
        with open(p) as fh:
            content = fh.read()
        # sanity (not the discriminating check): must use node:test and inject
        assert "node:test" in content, "test must use the node:test runner"
        assert "inject" in content, "test must drive the instance via inject"

    def test_l1_factory_exports_function_and_no_listen(self):
        """L1: requiring the module yields a callable factory with NO side-effect
        listen, and the built instance exposes a readable (empty) audit trail."""
        res = self._run_node(
            """
            const app = factory()
            let addr = null
            try { addr = app.server && app.server.address ? app.server.address() : null } catch (e) {}
            await app.ready()
            const t = trail(app)
            out({
              isFn: typeof factory === 'function',
              listening: !!(addr),
              trailIsArray: Array.isArray(t),
              trailLen: Array.isArray(t) ? t.length : -1
            })
            await app.close()
            """
        )
        assert res["isFn"] is True, "module.exports must be a factory function"
        assert res["listening"] is False, "factory/require must not bind a network port"
        assert res["trailIsArray"] is True, "instance must expose a readable audit trail array"
        assert res["trailLen"] == 0, "audit trail must start empty"

    # ============================== L2 =================================== #

    def test_l2_signup_normalizes_email_and_name(self):
        """L2: POST /signup normalizes email (lower+trim) and name (trim) -> 200."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, {
              method: 'POST', url: '/signup',
              headers: { 'content-type': 'application/json' },
              payload: { email: '  USER@Example.COM ', name: '  Ada  ' }
            })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 200, f"valid signup must return 200: {res}"
        body = res["body"]
        assert isinstance(body, dict), f"expected JSON object, got {body!r}"
        assert body.get("email") == "user@example.com", (
            f"email must be lowercased and trimmed, got {body.get('email')!r}"
        )
        assert body.get("name") == "Ada", (
            f"name must be trimmed (not lowercased), got {body.get('name')!r}"
        )

    def test_l2_normalization_happens_before_handler(self):
        """L2: handler must receive ALREADY normalized data, not raw input.

        Discriminates a handler that simply echoes raw body from one where a
        pre-handler lifecycle step normalized it: an internal-uppercase email
        with surrounding whitespace must come back clean, and the raw value
        must NOT appear verbatim anywhere in the response payload.
        """
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, {
              method: 'POST', url: '/signup',
              headers: { 'content-type': 'application/json' },
              payload: { email: '\tMixed.Case@Domain.IO   ', name: '\t  Grace Hopper \t' }
            })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 200, res
        body = res["body"]
        assert body.get("email") == "mixed.case@domain.io"
        assert body.get("name") == "Grace Hopper"
        # raw, un-normalized values must not survive into the response
        assert "Mixed.Case@Domain.IO" not in res["raw"], "email was not normalized pre-handler"
        assert "MIXED" not in res["raw"].upper().replace("MIXED.CASE@DOMAIN.IO", ""), res["raw"]

    def test_l2_invalid_body_missing_email_400(self):
        """L2: missing `email` -> 400 (schema rejection, JSON error shape)."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, {
              method: 'POST', url: '/signup',
              headers: { 'content-type': 'application/json' },
              payload: { name: 'NoEmail' }
            })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 400, f"missing email must be rejected: {res}"
        body = res["body"]
        assert isinstance(body, dict), "error body must be a JSON object"
        assert body.get("statusCode") == 400, body
        assert "json" in res["contentType"], "validation error must be JSON, not HTML"

    def test_l2_invalid_body_wrong_type_400(self):
        """L2: `email` of wrong type (number) -> 400 via schema validation."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, {
              method: 'POST', url: '/signup',
              headers: { 'content-type': 'application/json' },
              payload: { email: 12345, name: 'Typed' }
            })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 400, f"non-string email must be rejected: {res}"
        assert isinstance(res["body"], dict)
        assert res["body"].get("statusCode") == 400

    def test_l2_rejected_request_not_recorded(self):
        """L2: a schema-rejected POST must NOT append to the audit trail.

        A naive implementation that records every request (including pre-handler
        rejections) fails here. We compare trail length around a 400.
        """
        res = self._run_node(
            """
            const app = factory()
            const before = trail(app).length
            const bad = await inject(app, {
              method: 'POST', url: '/signup',
              headers: { 'content-type': 'application/json' },
              payload: { name: 'OnlyName' }   // missing email -> 400
            })
            const after = trail(app).length
            await app.close()
            out({ badStatus: bad.status, before, after })
            """
        )
        assert res["badStatus"] == 400, res
        assert res["after"] == res["before"], (
            "a request rejected before the handler must NOT be recorded in the audit trail"
        )

    def test_l2_audit_records_in_order_for_successes(self):
        """L2: two successful POST /signup -> exactly two ordered records.

        Each record must be { method:'POST', url:'/signup', statusCode:200 } and
        appended in request order. Discriminates missing after-response hook,
        wrong field names, or wrong status capture.
        """
        res = self._run_node(
            """
            const app = factory()
            await inject(app, {
              method: 'POST', url: '/signup',
              headers: { 'content-type': 'application/json' },
              payload: { email: 'A@B.COM', name: 'First' }
            })
            await inject(app, {
              method: 'POST', url: '/signup',
              headers: { 'content-type': 'application/json' },
              payload: { email: 'C@D.COM', name: 'Second' }
            })
            const recs = trail(app).slice()
            await app.close()
            out({ recs })
            """
        )
        recs = res["recs"]
        assert isinstance(recs, list), recs
        assert len(recs) == 2, f"expected exactly two audit records, got {recs}"
        for rec in recs:
            assert isinstance(rec, dict), rec
            assert rec.get("method") == "POST", rec
            assert rec.get("url") == "/signup", rec
            assert rec.get("statusCode") == 200, rec
            assert isinstance(rec.get("statusCode"), int) and not isinstance(
                rec.get("statusCode"), bool
            ), f"statusCode must be a number, got {rec.get('statusCode')!r}"

    def test_l2_rejected_then_success_only_records_success(self):
        """L2: interleaved 400 then 200 -> trail holds only the success record.

        Strong discriminator combining ordering + selective recording: after a
        rejected request followed by an accepted one, the trail length must be
        exactly 1 and describe the 200, not the 400.
        """
        res = self._run_node(
            """
            const app = factory()
            await inject(app, {
              method: 'POST', url: '/signup',
              headers: { 'content-type': 'application/json' },
              payload: { name: 'NoEmail' }   // 400
            })
            await inject(app, {
              method: 'POST', url: '/signup',
              headers: { 'content-type': 'application/json' },
              payload: { email: 'OK@OK.COM', name: 'Good' }   // 200
            })
            const recs = trail(app).slice()
            await app.close()
            out({ recs })
            """
        )
        recs = res["recs"]
        # The 400 must be absent. Depending on whether the design also records
        # non-/signup successes, the success record must be present and be a 200.
        signup_recs = [r for r in recs if r.get("url") == "/signup"]
        assert len(signup_recs) == 1, f"only the accepted /signup should be recorded: {recs}"
        assert signup_recs[0].get("method") == "POST"
        assert signup_recs[0].get("statusCode") == 200, signup_recs
        assert all(r.get("statusCode") != 400 for r in recs), (
            f"a 400-rejected request must never be recorded: {recs}"
        )

    def test_l2_get_audit_returns_array_and_reflects_history(self):
        """L2: GET /audit -> 200 JSON array reflecting prior recorded requests.

        We perform one successful POST, then GET /audit. The body must be an
        array containing the POST /signup 200 record. (The GET itself is also
        recorded per the doc; ordering: the POST precedes the GET, and the GET's
        own record may or may not appear in the body it returns depending on
        when the after-response hook fires, so we assert on the POST record's
        presence and array-ness rather than exact length.)
        """
        res = self._run_node(
            """
            const app = factory()
            await inject(app, {
              method: 'POST', url: '/signup',
              headers: { 'content-type': 'application/json' },
              payload: { email: 'H@H.COM', name: 'Hist' }
            })
            const r = await inject(app, { method: 'GET', url: '/audit' })
            // also read the decorator trail to cross-check the GET body
            const direct = trail(app).slice()
            await app.close()
            out({ status: r.status, contentType: r.contentType, body: r.body, direct })
            """
        )
        assert res["status"] == 200, f"GET /audit must return 200: {res}"
        assert "json" in res["contentType"], "GET /audit must serve JSON"
        body = res["body"]
        assert isinstance(body, list), f"GET /audit body must be a JSON array, got {body!r}"
        post_records = [
            r
            for r in body
            if isinstance(r, dict)
            and r.get("method") == "POST"
            and r.get("url") == "/signup"
            and r.get("statusCode") == 200
        ]
        assert len(post_records) == 1, (
            f"GET /audit must reflect the prior successful POST /signup record: {body}"
        )
        # The GET endpoint must derive from the SAME trail the decorator exposes
        # (the direct trail, read after the GET completed, must contain a /audit
        # record once the after-response hook for the GET has fired).
        assert any(r.get("url") == "/audit" for r in res["direct"]), (
            f"the GET /audit request itself must eventually be recorded: {res['direct']}"
        )

    def test_l2_instances_have_independent_trails(self):
        """L2: each factory() call yields its own independent trail (no global).

        A naive module-level array shared across instances fails: a POST to
        instance A must not appear in instance B's trail.
        """
        res = self._run_node(
            """
            const a = factory()
            const b = factory()
            const beforeB = trail(b).length
            await inject(a, {
              method: 'POST', url: '/signup',
              headers: { 'content-type': 'application/json' },
              payload: { email: 'ONLY@A.COM', name: 'OnlyA' }
            })
            const afterA = trail(a).length
            const afterB = trail(b).length
            await a.close(); await b.close()
            out({ beforeB, afterA, afterB })
            """
        )
        assert res["afterA"] >= res["beforeB"] + 1, "instance A should have recorded its POST"
        assert res["afterB"] == res["beforeB"], (
            "POST to instance A must not appear in instance B's trail (no shared global trail)"
        )

    def test_l2_trail_persists_across_requests(self):
        """L2: the trail accumulates (persists) across multiple requests in one
        instance rather than resetting each request."""
        res = self._run_node(
            """
            const app = factory()
            const lengths = []
            for (const nm of ['One', 'Two', 'Three']) {
              await inject(app, {
                method: 'POST', url: '/signup',
                headers: { 'content-type': 'application/json' },
                payload: { email: nm + '@X.COM', name: nm }
              })
              lengths.push(trail(app).length)
            }
            await app.close()
            out({ lengths })
            """
        )
        assert res["lengths"] == [1, 2, 3], (
            f"trail must monotonically accumulate across requests, got {res['lengths']}"
        )

    def test_l2_native_node_test_passes(self):
        """L2: the agent's own suite passes via `node --test test/audit-pipeline.test.js`."""
        test_path = os.path.join(REPO_DIR, "test", "audit-pipeline.test.js")
        assert os.path.isfile(test_path), f"missing {test_path}"
        proc = subprocess.run(
            ["node", "--test", "test/audit-pipeline.test.js"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, (
            "native `node --test test/audit-pipeline.test.js` must pass.\n"
            f"stdout={proc.stdout[-5000:]}\nstderr={proc.stderr[-3000:]}"
        )
        combined = proc.stdout + proc.stderr
        assert "fail 0" in combined, f"expected zero failures.\n{proc.stdout[-3000:]}"
