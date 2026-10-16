"""Tests for the `fastify-patterns` skill task (variant ext4):
Centralize Error Handling with a Stable Error Envelope.

Verifies the agent's work inside REPO_DIR (/workspace/fastify):

  - examples/error-envelope.js exports a no-argument factory that builds and
    returns a configured Fastify instance WITHOUT binding a network port on
    require.
  - Every error produced anywhere in the instance shares ONE stable JSON
    envelope: exactly the three top-level fields {statusCode, code, message},
    with statusCode equal to the HTTP status on the wire.
  - Distinct failure paths funnel through a CENTRAL handler (Fastify's
    setErrorHandler / setNotFoundHandler), not ad-hoc per-route JSON:
        GET  /boom     -> 500 code=INTERNAL, generic leak-free message
        GET  /teapot   -> 418 code=TEAPOT
        POST /validate -> 400 code=VALIDATION_FAILED on schema violation
        POST /validate -> 200 {ok:true} on a valid body
        any unknown route -> 404 code=NOT_FOUND
  - The framework's default error body / stack trace must NEVER leak.
  - test/error-envelope.test.js exists and the native command
    `node --test test/error-envelope.test.js` passes.

Rather than trusting the agent-authored test file, the L2 cases independently
drive the factory through Fastify's in-process `inject` API using a fresh Node
driver written by THIS test. A naive implementation that hand-builds different
ad-hoc JSON per route, leaks the thrown error's internal text, or returns the
framework default body therefore fails.
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
const factoryPath = path.join(process.cwd(), 'examples', 'error-envelope.js')
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

    @staticmethod
    def _assert_envelope(body, status, code):
        """Assert `body` is the stable envelope: exactly 3 fields, matching values."""
        assert isinstance(body, dict), f"error body must be a JSON object, got {body!r}"
        assert set(body.keys()) == {"statusCode", "code", "message"}, (
            f"envelope must have EXACTLY the three fields "
            f"{{statusCode, code, message}}, got {sorted(body.keys())}"
        )
        assert body["statusCode"] == status, (
            f"statusCode field {body.get('statusCode')!r} must equal wire status {status}"
        )
        assert body["code"] == code, f"expected code {code!r}, got {body.get('code')!r}"
        assert isinstance(body["message"], str) and body["message"].strip(), (
            f"message must be a non-empty string, got {body.get('message')!r}"
        )

    # ============================== L1 =================================== #

    def test_l1_factory_module_exists(self):
        """L1: examples/error-envelope.js exists and is a non-empty file."""
        p = os.path.join(REPO_DIR, "examples", "error-envelope.js")
        assert os.path.isfile(p), f"missing deliverable: {p}"
        assert os.path.getsize(p) > 0, "error-envelope.js is empty"

    def test_l1_test_file_exists(self):
        """L1: test/error-envelope.test.js exists and uses node:test + inject."""
        p = os.path.join(REPO_DIR, "test", "error-envelope.test.js")
        assert os.path.isfile(p), f"missing deliverable: {p}"
        with open(p) as fh:
            content = fh.read()
        assert os.path.getsize(p) > 0, "test file is empty"
        # sanity (not the discriminating check): node:test runner + in-process inject
        assert "node:test" in content, "test must use the node:test runner"
        assert "inject" in content, "test must drive the instance via inject"

    def test_l1_factory_exports_function_and_no_listen(self):
        """L1: requiring the module yields a function and building it does NOT listen.

        We build one instance; if requiring/building had bound a port, the server
        would expose a non-null address. We assert the export is callable and that
        building it opens no socket.
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

    def test_l2_boom_500_internal_code(self):
        """L2: GET /boom -> 500 with the stable envelope and code=INTERNAL."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/boom' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 500, f"GET /boom must be 500: {res}"
        assert "json" in res["contentType"], "error must be JSON, not HTML"
        self._assert_envelope(res["body"], 500, "INTERNAL")

    def test_l2_boom_message_does_not_leak_internal_detail(self):
        """L2: GET /boom must not echo the thrown error's internal text or a stack.

        The driver overrides the global error path indirectly is not possible, so
        instead we assert the response body for the real /boom route is free of any
        stack-trace / raw-error fingerprints and of any internal detail substring.
        A handler that simply forwards `err.message` or the default Fastify error
        body would leak and fail here.
        """
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/boom' })
            await app.close()
            out(r)
            """,
        )
        assert res["status"] == 500, res
        raw = res["raw"] or ""
        body = res["body"]
        self._assert_envelope(body, 500, "INTERNAL")
        # No stack-trace fingerprints anywhere in the wire body.
        for needle in ("at Object.", "at Server.", ".js:", "Error:", "stack"):
            assert needle not in raw, (
                f"500 response leaks internal detail {needle!r}: {raw[:500]}"
            )
        # The default Fastify error envelope uses an `error` field; ours must not.
        assert "error" not in body, "must not return the framework default error body"

    def test_l2_teapot_418_code(self):
        """L2: GET /teapot -> 418 with the stable envelope and code=TEAPOT."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/teapot' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 418, f"GET /teapot must be 418: {res}"
        assert "json" in res["contentType"], "error must be JSON, not HTML"
        self._assert_envelope(res["body"], 418, "TEAPOT")

    def test_l2_validate_happy_path_200(self):
        """L2: POST /validate with a fully valid body -> 200 {ok:true}."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, {
              method: 'POST', url: '/validate',
              headers: { 'content-type': 'application/json' },
              payload: { email: 'a@b.c', age: 30 }
            })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 200, f"valid body must be 200: {res}"
        assert res["body"] == {"ok": True}, (
            f"valid /validate must return exactly {{ok:true}}, got {res['body']!r}"
        )

    def test_l2_validate_wrong_type_email_400(self):
        """L2: POST /validate with email of wrong type -> 400 VALIDATION_FAILED.

        `email` is declared a string; sending a number violates the schema, which
        the central handler must translate into the envelope (not a default 400).
        """
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, {
              method: 'POST', url: '/validate',
              headers: { 'content-type': 'application/json' },
              payload: { email: 123, age: 30 }
            })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 400, f"wrong-type email must 400: {res}"
        assert "json" in res["contentType"], "validation error must be JSON"
        self._assert_envelope(res["body"], 400, "VALIDATION_FAILED")

    def test_l2_validate_missing_age_400(self):
        """L2: POST /validate missing required `age` -> 400 VALIDATION_FAILED.

        A distinct validation failure (missing required field) must produce the
        SAME envelope/code as the wrong-type case, proving central translation.
        """
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, {
              method: 'POST', url: '/validate',
              headers: { 'content-type': 'application/json' },
              payload: { email: 'a@b.c' }
            })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 400, f"missing age must 400: {res}"
        self._assert_envelope(res["body"], 400, "VALIDATION_FAILED")

    def test_l2_validate_negative_age_400(self):
        """L2: POST /validate with age below the minimum (negative) -> 400.

        `age` requires integer minimum 0; -1 must be rejected as VALIDATION_FAILED,
        confirming the numeric bound is actually enforced (not just presence).
        """
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, {
              method: 'POST', url: '/validate',
              headers: { 'content-type': 'application/json' },
              payload: { email: 'a@b.c', age: -1 }
            })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 400, f"negative age must 400: {res}"
        self._assert_envelope(res["body"], 400, "VALIDATION_FAILED")

    def test_l2_not_found_404_code(self):
        """L2: an unregistered route -> 404 with the envelope and code=NOT_FOUND."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/no-such-route-xyz' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 404, f"unknown route must 404: {res}"
        assert "json" in res["contentType"], "not-found must be JSON, not HTML"
        self._assert_envelope(res["body"], 404, "NOT_FOUND")

    def test_l2_all_error_paths_share_one_envelope_shape(self):
        """L2: every error path emits the SAME three-field envelope with matching
        statusCode, and the four codes are the documented, distinct ones.

        This is the central discriminator: a naive per-route ad-hoc JSON builder
        would diverge in field set or status/statusCode agreement across paths.
        """
        res = self._run_node(
            """
            const app = factory()
            const boom = await inject(app, { method: 'GET', url: '/boom' })
            const teapot = await inject(app, { method: 'GET', url: '/teapot' })
            const valWrong = await inject(app, {
              method: 'POST', url: '/validate',
              headers: { 'content-type': 'application/json' },
              payload: { email: 123 }
            })
            const notFound = await inject(app, { method: 'GET', url: '/totally-absent' })
            await app.close()
            out({ boom, teapot, valWrong, notFound })
            """
        )
        expected = {
            "boom": (500, "INTERNAL"),
            "teapot": (418, "TEAPOT"),
            "valWrong": (400, "VALIDATION_FAILED"),
            "notFound": (404, "NOT_FOUND"),
        }
        seen_codes = set()
        for key, (status, code) in expected.items():
            entry = res[key]
            assert entry["status"] == status, f"{key}: wire status {entry['status']} != {status}"
            self._assert_envelope(entry["body"], status, code)
            seen_codes.add(entry["body"]["code"])
        assert seen_codes == {"INTERNAL", "TEAPOT", "VALIDATION_FAILED", "NOT_FOUND"}, (
            f"the four error paths must use four distinct documented codes, got {seen_codes}"
        )

    def test_l2_status_and_statuscode_always_agree(self):
        """L2: across a mix of failing and succeeding requests, the wire status and
        the body's statusCode field never disagree (and success has no envelope).

        A stub that hardcodes statusCode (e.g. always 500 in the body) is caught.
        """
        res = self._run_node(
            """
            const app = factory()
            const cases = []
            cases.push(['boom', await inject(app, { method: 'GET', url: '/boom' })])
            cases.push(['teapot', await inject(app, { method: 'GET', url: '/teapot' })])
            cases.push(['nf', await inject(app, { method: 'GET', url: '/nope' })])
            cases.push(['bad', await inject(app, {
              method: 'POST', url: '/validate',
              headers: { 'content-type': 'application/json' }, payload: {}
            })])
            const ok = await inject(app, {
              method: 'POST', url: '/validate',
              headers: { 'content-type': 'application/json' },
              payload: { email: 'x@y.z', age: 0 }
            })
            await app.close()
            out({ cases, ok })
            """
        )
        for name, entry in res["cases"]:
            assert entry["status"] >= 400, f"{name} expected an error status"
            assert isinstance(entry["body"], dict), f"{name} body must be JSON object"
            assert entry["body"].get("statusCode") == entry["status"], (
                f"{name}: statusCode {entry['body'].get('statusCode')} != wire {entry['status']}"
            )
        # boundary: age == 0 (the documented minimum) is valid -> 200, no envelope
        ok = res["ok"]
        assert ok["status"] == 200, f"age:0 is the inclusive minimum, must pass: {ok}"
        assert ok["body"] == {"ok": True}, ok

    def test_l2_native_node_test_passes(self):
        """L2: the agent's own suite passes via `node --test test/error-envelope.test.js`."""
        test_path = os.path.join(REPO_DIR, "test", "error-envelope.test.js")
        assert os.path.isfile(test_path), f"missing {test_path}"
        proc = subprocess.run(
            ["node", "--test", "test/error-envelope.test.js"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, (
            "native `node --test test/error-envelope.test.js` must pass.\n"
            f"stdout={proc.stdout[-5000:]}\nstderr={proc.stderr[-3000:]}"
        )
        combined = proc.stdout + proc.stderr
        assert "fail 0" in combined, f"expected zero failures.\n{proc.stdout[-3000:]}"
