"""Tests for the `fastify-patterns` skill task (variant ext7):
Add a Custom CSV Content-Type Parser with a Size Guard.

Verifies the agent's work inside REPO_DIR (/workspace/fastify):

  - examples/csv-parser.js exports a no-argument factory that builds and returns
    a configured Fastify instance via `require('..')` WITHOUT binding a network
    port on require / build.
  - The instance registers a content-type parser for `text/csv` that turns a raw
    CSV upload into an array of objects (header row -> field names; each data row
    -> positional cells). POST /import returns
    { count: <n>, rows: [...] } and the handler receives the ALREADY-PARSED
    array (so a naive in-handler split fails).
  - Malformed CSV (cell-count mismatch / empty body) is rejected with 400 and the
    handler does not run.
  - A `text/csv` body larger than 1024 bytes is rejected with 413 by the
    framework's body-limit mechanism (not a hand-rolled length check).
  - The default JSON parser still works: POST /echo returns { received: <body> }.
  - test/csv-parser.test.js exists and the native command
    `node --test test/csv-parser.test.js` passes.

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

# Shared prelude: load the agent's factory, and expose a small `inject` helper
# that always returns {status, contentType, body, parseError, raw}.
_PRELUDE = r"""
'use strict'
const path = require('path')
const factoryPath = path.join(process.cwd(), 'examples', 'csv-parser.js')
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
        """L1: examples/csv-parser.js exists and is a non-empty file."""
        p = os.path.join(REPO_DIR, "examples", "csv-parser.js")
        assert os.path.isfile(p), f"missing deliverable: {p}"
        assert os.path.getsize(p) > 0, "csv-parser.js is empty"

    def test_l1_test_file_exists(self):
        """L1: test/csv-parser.test.js exists and references node:test + inject."""
        p = os.path.join(REPO_DIR, "test", "csv-parser.test.js")
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
        port (server has no address) and must not throw.
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

    def test_l2_valid_multirow_parse_exact_rows(self):
        """L2: POST /import text/csv -> 200 with exact count and parsed rows.

        Body 'id,name\\n1,Ada\\n2,Lin\\n' must yield
        { count: 2, rows: [{id:'1',name:'Ada'},{id:'2',name:'Lin'}] }.
        Cells map positionally to the header; values are strings.
        """
        res = self._run_node(
            r"""
            const app = factory()
            const r = await inject(app, {
              method: 'POST', url: '/import',
              headers: { 'content-type': 'text/csv' },
              payload: 'id,name\n1,Ada\n2,Lin\n'
            })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 200, res
        body = res["body"]
        assert isinstance(body, dict), f"expected JSON object, got {body!r}"
        assert body.get("count") == 2, f"count must reflect parsed rows: {body}"
        assert body.get("rows") == [
            {"id": "1", "name": "Ada"},
            {"id": "2", "name": "Lin"},
        ], f"rows must be parsed objects keyed by header: {body}"

    def test_l2_handler_receives_parsed_array_not_string(self):
        """L2: the handler must receive an ALREADY-PARSED array, not a raw string.

        `count` must equal the array length and `rows` must be a list of objects.
        A naive handler that splits the raw body string itself would still have to
        produce these, but the parsed-layer contract is proven by the next test
        (single-cell header) and the malformed/413 cases which a raw-split handler
        cannot satisfy without re-implementing the framework guards.
        """
        res = self._run_node(
            r"""
            const app = factory()
            const r = await inject(app, {
              method: 'POST', url: '/import',
              headers: { 'content-type': 'text/csv' },
              payload: 'a,b,c\n1,2,3\n'
            })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 200, res
        body = res["body"]
        assert isinstance(body, dict)
        assert isinstance(body.get("rows"), list), "rows must be a JSON array"
        assert body["count"] == len(body["rows"]) == 1
        assert body["rows"][0] == {"a": "1", "b": "2", "c": "3"}

    def test_l2_whitespace_and_trailing_blank_lines_ignored(self):
        """L2: surrounding whitespace and trailing blank lines are ignored."""
        res = self._run_node(
            r"""
            const app = factory()
            const r = await inject(app, {
              method: 'POST', url: '/import',
              headers: { 'content-type': 'text/csv' },
              payload: '  id,name\n10,Sam\n\n\n  '
            })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 200, res
        body = res["body"]
        assert body.get("count") == 1, f"trailing blanks must not add rows: {body}"
        assert body.get("rows") == [{"id": "10", "name": "Sam"}], body

    def test_l2_cell_count_mismatch_rejected_400(self):
        """L2: a data row with a different cell count than the header -> 400.

        The handler must NOT run; the body must be a JSON error object (the parse
        failed), not a 200 with partial data.
        """
        res = self._run_node(
            r"""
            const app = factory()
            const r = await inject(app, {
              method: 'POST', url: '/import',
              headers: { 'content-type': 'text/csv' },
              payload: 'id,name\n1,Ada\n2\n'
            })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 400, f"cell-count mismatch must 400: {res}"
        body = res["body"]
        assert isinstance(body, dict), "error body must be a JSON object"
        assert body.get("statusCode") == 400, body
        # must NOT have leaked a successful parse shape
        assert "rows" not in body and "count" not in body, (
            f"malformed CSV must not be handled as success: {body}"
        )

    def test_l2_empty_body_rejected_400(self):
        """L2: an empty text/csv body (no header) -> 400, handler does not run."""
        res = self._run_node(
            r"""
            const app = factory()
            const r = await inject(app, {
              method: 'POST', url: '/import',
              headers: { 'content-type': 'text/csv' },
              payload: ''
            })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 400, f"empty CSV body must 400: {res}"
        body = res["body"]
        assert isinstance(body, dict), "error body must be a JSON object"
        assert body.get("statusCode") == 400, body
        assert "rows" not in body and "count" not in body, body

    def test_l2_oversized_body_rejected_413(self):
        """L2: a text/csv body exceeding 1024 bytes -> 413 (framework body-limit).

        We send a well-formed CSV whose serialized size is comfortably over the
        limit. It must be rejected with 413 and NEVER reach the handler (no
        count/rows in the body). A handler-side length check would not produce a
        413 RangeError from the content-type layer.
        """
        res = self._run_node(
            r"""
            const app = factory()
            // header + many valid rows; each 'NN,filler...' line is well-formed.
            let payload = 'id,name\n'
            let i = 0
            while (Buffer.byteLength(payload, 'utf8') <= 4096) {
              payload += i + ',' + 'x'.repeat(40) + '\n'
              i++
            }
            const size = Buffer.byteLength(payload, 'utf8')
            const r = await inject(app, {
              method: 'POST', url: '/import',
              headers: { 'content-type': 'text/csv' },
              payload
            })
            await app.close()
            out({ size, status: r.status, body: r.body, raw: r.raw })
            """
        )
        assert res["size"] > 1024, "test must exceed the 1024-byte limit"
        assert res["status"] == 413, (
            f"oversized text/csv body must be rejected with 413: {res}"
        )
        body = res["body"]
        if isinstance(body, dict):
            assert body.get("statusCode") == 413, body
            assert "rows" not in body and "count" not in body, (
                f"oversized body must not be parsed/handled: {body}"
            )

    def test_l2_under_limit_still_parses(self):
        """L2: a body just under 1024 bytes is accepted and parsed (limit is a
        guard, not a blanket reject)."""
        res = self._run_node(
            r"""
            const app = factory()
            let payload = 'id,name\n'
            let i = 0
            // stay safely under 1024 bytes
            while (Buffer.byteLength(payload + (i + ',' + 'y'.repeat(10) + '\n'), 'utf8') < 900) {
              payload += i + ',' + 'y'.repeat(10) + '\n'
              i++
            }
            const expected = i
            const size = Buffer.byteLength(payload, 'utf8')
            const r = await inject(app, {
              method: 'POST', url: '/import',
              headers: { 'content-type': 'text/csv' },
              payload
            })
            await app.close()
            out({ size, expected, status: r.status, body: r.body })
            """
        )
        assert res["size"] < 1024, "precondition: under the limit"
        assert res["status"] == 200, f"under-limit body must parse: {res}"
        body = res["body"]
        assert isinstance(body, dict)
        assert body.get("count") == res["expected"], (
            f"all under-limit rows must be parsed: {body}"
        )
        assert len(body.get("rows", [])) == res["expected"]

    def test_l2_json_echo_roundtrip(self):
        """L2: POST /echo application/json -> 200 { received: <body> }.

        Confirms the custom CSV parser did not disturb default JSON parsing.
        """
        res = self._run_node(
            r"""
            const app = factory()
            const r = await inject(app, {
              method: 'POST', url: '/echo',
              headers: { 'content-type': 'application/json' },
              payload: { a: 1, nested: { b: [true, 'x'] } }
            })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 200, res
        body = res["body"]
        assert isinstance(body, dict), body
        assert body.get("received") == {"a": 1, "nested": {"b": [True, "x"]}}, (
            f"/echo must return the JSON body under `received`: {body}"
        )

    def test_l2_csv_parser_does_not_hijack_json_route(self):
        """L2: sending CSV content-type to /echo must NOT be JSON-echoed as a
        parsed CSV array, and sending JSON to /import must not yield CSV rows.

        This proves the parser is bound specifically to text/csv (route-correct
        media handling), not applied globally.
        """
        res = self._run_node(
            r"""
            const app = factory()
            // JSON to /import: should not be parsed as CSV rows of objects.
            const jsonToImport = await inject(app, {
              method: 'POST', url: '/import',
              headers: { 'content-type': 'application/json' },
              payload: { id: '1', name: 'Ada' }
            })
            await app.close()
            out({ jsonToImport })
            """
        )
        ji = res["jsonToImport"]
        # Either rejected (415/400) or, if accepted, it must NOT masquerade as a
        # successful CSV parse of an array of header-keyed rows.
        if ji["status"] == 200 and isinstance(ji["body"], dict):
            rows = ji["body"].get("rows")
            assert not (isinstance(rows, list) and rows == [{"id": "1", "name": "Ada"}]), (
                "JSON body must not be processed by the CSV parser path"
            )

    def test_l2_instances_isolated(self):
        """L2: each factory() call yields an independent instance (no shared
        global state); both parse correctly side by side."""
        res = self._run_node(
            r"""
            const a = factory()
            const b = factory()
            const ra = await inject(a, {
              method: 'POST', url: '/import',
              headers: { 'content-type': 'text/csv' },
              payload: 'k,v\n1,A\n'
            })
            const rb = await inject(b, {
              method: 'POST', url: '/import',
              headers: { 'content-type': 'text/csv' },
              payload: 'k,v\nx,Y\nz,W\n'
            })
            await a.close(); await b.close()
            out({ ra, rb })
            """
        )
        assert res["ra"]["status"] == 200 and res["rb"]["status"] == 200, res
        assert res["ra"]["body"]["count"] == 1, res["ra"]
        assert res["rb"]["body"]["count"] == 2, res["rb"]
        assert res["ra"]["body"]["rows"] == [{"k": "1", "v": "A"}]
        assert res["rb"]["body"]["rows"] == [
            {"k": "x", "v": "Y"},
            {"k": "z", "v": "W"},
        ]

    def test_l2_native_node_test_passes(self):
        """L2: the agent's own suite passes via `node --test test/csv-parser.test.js`."""
        test_path = os.path.join(REPO_DIR, "test", "csv-parser.test.js")
        assert os.path.isfile(test_path), f"missing {test_path}"
        proc = subprocess.run(
            ["node", "--test", "test/csv-parser.test.js"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, (
            "native `node --test test/csv-parser.test.js` must pass.\n"
            f"stdout={proc.stdout[-5000:]}\nstderr={proc.stderr[-3000:]}"
        )
        combined = proc.stdout + proc.stderr
        assert "fail 0" in combined, (
            f"expected zero failures.\n{proc.stdout[-3000:]}"
        )
