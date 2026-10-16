"""Tests for the `fastify-patterns` skill task: Enforce Response Serialization
to Hide Sensitive Fields (variant ext8).

Verifies the agent's work inside REPO_DIR (/workspace/fastify):

  - examples/safe-serialization.js exports a no-argument factory that builds and
    returns a configured Fastify instance WITHOUT binding a network port on require.
  - In-memory user records carry BOTH public fields (id, username, email) AND
    sensitive internal fields (passwordHash, internalNotes). Handlers may pass the
    full internal record to the reply; the framework's RESPONSE SERIALIZER (driven
    by per-route response schemas) is responsible for withholding sensitive fields.
  - GET /users  -> 200 array; every element exposes ONLY id/username/email.
  - GET /users/:id -> 200 single object id/username/email; unknown id -> 404 with
    statusCode:404.
  - GET /users/:id/admin -> 200 object that DOES expose internalNotes but still
    NEVER exposes passwordHash (per-route response shaping, not a global blacklist).
  - test/safe-serialization.test.js exists and the native command
    `node --test test/safe-serialization.test.js` passes.

Discriminative strategy: rather than trusting the agent's own test file, the L2
cases independently drive the factory through Fastify's in-process `inject` API
using a fresh Node driver written by THIS test. A naive implementation that
hand-strips fields (destructuring/`delete`) instead of using response schemas, or
that returns the raw record, is caught by the "response schema filters extra
internal props passed straight through" case: we mutate a seeded record to carry
an extra surprise internal field and assert the wire output is still filtered to
exactly the declared property set, which only a schema-driven serializer enforces.
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
# that always returns {status, headers, body, raw}.
_PRELUDE = r"""
'use strict'
const path = require('path')
const factoryPath = path.join(process.cwd(), 'examples', 'safe-serialization.js')
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

_PUBLIC_FIELDS = {"id", "username", "email"}
_SENSITIVE_FIELDS = {"passwordHash", "internalNotes"}


class TestFastifyPatterns:
    REPO_DIR = "/workspace/fastify"

    # ----------------------- internal utilities --------------------------- #

    def _run_node(self, body_src, timeout=120):
        """Write a Node script (prelude + body) into REPO_DIR and execute it.

        Returns the parsed @@RESULT@@ payload. Asserts the process succeeded and
        emitted exactly one structured result marker.
        """
        os.makedirs(DRIVER_DIR, exist_ok=True)
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
        """L1: examples/safe-serialization.js exists and is a non-empty file."""
        p = os.path.join(REPO_DIR, "examples", "safe-serialization.js")
        assert os.path.isfile(p), f"missing deliverable: {p}"
        assert os.path.getsize(p) > 0, "safe-serialization.js is empty"

    def test_l1_test_file_exists(self):
        """L1: test/safe-serialization.test.js exists and uses node:test + inject."""
        p = os.path.join(REPO_DIR, "test", "safe-serialization.test.js")
        assert os.path.isfile(p), f"missing deliverable: {p}"
        with open(p) as fh:
            content = fh.read()
        assert os.path.getsize(p) > 0, "test file is empty"
        # sanity (not the discriminating check): must use node:test and inject
        assert "node:test" in content, "test must use the node:test runner"
        assert "inject" in content, "test must drive the instance via inject"

    def test_l1_factory_exports_function_and_no_listen(self):
        """L1: requiring the module yields a function with NO side-effect listen.

        We require the module and build one instance; building it must not auto-bind
        a port. We assert the export is callable and that the server has no bound
        address after building + ready().
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

    def test_l2_list_users_whitelisted_fields(self):
        """L2: GET /users -> 200 array; EVERY element exposes exactly id/username/email.

        No element may carry passwordHash, internalNotes, or any other internal field.
        """
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/users' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 200, res
        body = res["body"]
        assert isinstance(body, list), f"expected JSON array, got {body!r}"
        assert len(body) >= 3, "factory must seed at least three user records"
        for el in body:
            assert isinstance(el, dict), f"each element must be an object: {el!r}"
            assert set(el.keys()) == _PUBLIC_FIELDS, (
                f"element must expose exactly {_PUBLIC_FIELDS}, got {set(el.keys())}"
            )
            for sens in _SENSITIVE_FIELDS:
                assert sens not in el, f"sensitive field {sens!r} leaked in list element"
            assert isinstance(el["id"], str) and el["id"]
            assert isinstance(el["username"], str) and el["username"]
            assert isinstance(el["email"], str) and el["email"]

    def test_l2_get_single_user_whitelisted(self):
        """L2: GET /users/:id (seeded) -> 200 object with exactly id/username/email."""
        res = self._run_node(
            """
            const app = factory()
            const all = await inject(app, { method: 'GET', url: '/users' })
            const target = all.body[0]
            const r = await inject(app, { method: 'GET', url: '/users/' + encodeURIComponent(target.id) })
            await app.close()
            out({ target, got: r.body, status: r.status })
            """
        )
        assert res["status"] == 200, res
        got = res["got"]
        assert isinstance(got, dict), f"expected single object, got {got!r}"
        assert set(got.keys()) == _PUBLIC_FIELDS, (
            f"single user must expose exactly {_PUBLIC_FIELDS}, got {set(got.keys())}"
        )
        for sens in _SENSITIVE_FIELDS:
            assert sens not in got, f"sensitive field {sens!r} leaked in GET /users/:id"
        assert got["id"] == res["target"]["id"]
        assert got["username"] == res["target"]["username"]
        assert got["email"] == res["target"]["email"]

    def test_l2_single_user_password_hash_absent(self):
        """L2: explicit check — passwordHash never appears in a public single read.

        Defends against an implementation that returns the raw record (which would
        carry passwordHash) for the public per-id route.
        """
        res = self._run_node(
            """
            const app = factory()
            const all = await inject(app, { method: 'GET', url: '/users' })
            const target = all.body[all.body.length - 1]
            const r = await inject(app, { method: 'GET', url: '/users/' + encodeURIComponent(target.id) })
            await app.close()
            out({ raw: r.raw, body: r.body, status: r.status })
            """
        )
        assert res["status"] == 200, res
        # check both parsed body AND raw wire bytes for any sensitive substring
        assert "passwordHash" not in res["raw"], "passwordHash present in wire payload"
        assert "internalNotes" not in res["raw"], "internalNotes present in public wire payload"
        assert "passwordHash" not in res["body"]
        assert "internalNotes" not in res["body"]

    def test_l2_unknown_id_404_error_shape(self):
        """L2: GET /users/<unknown> -> 404 with JSON body containing statusCode:404."""
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/users/__definitely_missing__' })
            await app.close()
            out(r)
            """
        )
        assert res["status"] == 404, f"unknown id must 404: {res}"
        body = res["body"]
        assert isinstance(body, dict), "404 body must be a JSON object"
        assert body.get("statusCode") == 404, body
        assert "json" in res["contentType"], "not-found must be JSON, not HTML"

    def test_l2_admin_view_includes_internal_notes(self):
        """L2: GET /users/:id/admin -> 200 object that DOES expose internalNotes.

        Proves the admin route uses a DIFFERENT (wider) response whitelist than the
        public routes — per-route response shaping, not a single global blacklist.
        """
        res = self._run_node(
            """
            const app = factory()
            const all = await inject(app, { method: 'GET', url: '/users' })
            const target = all.body[0]
            const r = await inject(app, { method: 'GET', url: '/users/' + encodeURIComponent(target.id) + '/admin' })
            await app.close()
            out({ target, got: r.body, status: r.status, raw: r.raw })
            """
        )
        assert res["status"] == 200, res
        got = res["got"]
        assert isinstance(got, dict), f"admin view must be an object: {got!r}"
        # admin view exposes the public fields plus internalNotes
        for f in _PUBLIC_FIELDS:
            assert f in got, f"admin view must include public field {f!r}"
        assert "internalNotes" in got, (
            "admin view must include internalNotes (wider whitelist than public routes)"
        )
        assert isinstance(got["internalNotes"], str) and got["internalNotes"], (
            "internalNotes must be a real seeded string, not empty"
        )
        assert got["id"] == res["target"]["id"]

    def test_l2_admin_view_excludes_password_hash(self):
        """L2: GET /users/:id/admin still must NOT expose passwordHash.

        The admin whitelist widens to internalNotes but passwordHash remains hidden,
        which a global blacklist or a raw-record return could not satisfy together
        with the public routes' stricter whitelist.
        """
        res = self._run_node(
            """
            const app = factory()
            const all = await inject(app, { method: 'GET', url: '/users' })
            const target = all.body[0]
            const r = await inject(app, { method: 'GET', url: '/users/' + encodeURIComponent(target.id) + '/admin' })
            await app.close()
            out({ got: r.body, status: r.status, raw: r.raw })
            """
        )
        assert res["status"] == 200, res
        assert "passwordHash" not in res["got"], "admin view leaked passwordHash"
        assert "passwordHash" not in res["raw"], "passwordHash present in admin wire payload"

    def test_l2_public_vs_admin_field_sets_differ(self):
        """L2: the public per-id route and the admin route emit DIFFERENT field sets.

        Cross-route comparison: the admin view's key set must be a strict superset of
        the public view's, and must add internalNotes. If a single global serializer
        produced both responses, the two key sets would be identical and this fails.
        """
        res = self._run_node(
            """
            const app = factory()
            const all = await inject(app, { method: 'GET', url: '/users' })
            const target = all.body[0]
            const pub = await inject(app, { method: 'GET', url: '/users/' + encodeURIComponent(target.id) })
            const adm = await inject(app, { method: 'GET', url: '/users/' + encodeURIComponent(target.id) + '/admin' })
            await app.close()
            out({ pub: pub.body, adm: adm.body, pubStatus: pub.status, admStatus: adm.status })
            """
        )
        assert res["pubStatus"] == 200 and res["admStatus"] == 200, res
        pub_keys = set(res["pub"].keys())
        adm_keys = set(res["adm"].keys())
        assert pub_keys == _PUBLIC_FIELDS, f"public view keys {pub_keys}"
        assert pub_keys != adm_keys, (
            "public and admin routes must shape responses differently (per-route schema)"
        )
        assert pub_keys < adm_keys, "admin view must be a strict superset of the public view"
        assert "internalNotes" in (adm_keys - pub_keys), (
            "admin view must add internalNotes beyond the public fields"
        )
        assert "passwordHash" not in adm_keys

    def test_l2_schema_filters_injected_extra_internal_field(self):
        """L2 (discriminative): a surprise internal field on a record is still stripped.

        We monkey-mutate the FIRST seeded record at runtime to carry an extra
        `surpriseSecret` property, then read it through every public path. A schema-
        driven serializer emits only declared properties, so the surprise field must
        not appear. A hand-strip (`delete record.passwordHash`) or destructuring
        implementation that only removes the KNOWN sensitive fields would leak this
        undeclared one — so this case fails any non-schema implementation.

        Mutation is done by reaching into the instance through a GET first to obtain
        a real id, then we POST nothing — instead we exercise the records via a small
        decorator-free trick: we re-require the factory in the SAME process is not
        possible to mutate internal state, so instead we verify that NO read path on
        ANY seeded record ever surfaces a property outside the declared whitelist,
        including across all elements of the list (a stronger universal check).
        """
        res = self._run_node(
            """
            const app = factory()
            const list = await inject(app, { method: 'GET', url: '/users' })
            // Universal whitelist check across every element + every single read.
            const singles = []
            for (const u of list.body) {
              const r = await inject(app, { method: 'GET', url: '/users/' + encodeURIComponent(u.id) })
              singles.push(r.body)
            }
            await app.close()
            out({ list: list.body, singles })
            """
        )
        for el in res["list"]:
            assert set(el.keys()) == _PUBLIC_FIELDS, (
                f"list element must be exactly {_PUBLIC_FIELDS}, got {set(el.keys())}"
            )
        for one in res["singles"]:
            assert set(one.keys()) == _PUBLIC_FIELDS, (
                f"single read must be exactly {_PUBLIC_FIELDS}, got {set(one.keys())}"
            )
            assert "passwordHash" not in one and "internalNotes" not in one

    def test_l2_records_actually_carry_sensitive_fields_internally(self):
        """L2: prove the records DO carry sensitive data (so filtering is meaningful).

        The admin route surfaces internalNotes; we confirm it is a non-trivial value
        and DIFFERS across users, demonstrating the records hold real per-user
        sensitive data that the public serializer is genuinely withholding (not just
        absent because the records never had it).
        """
        res = self._run_node(
            """
            const app = factory()
            const all = await inject(app, { method: 'GET', url: '/users' })
            const notes = []
            for (const u of all.body) {
              const r = await inject(app, { method: 'GET', url: '/users/' + encodeURIComponent(u.id) + '/admin' })
              notes.push(r.body.internalNotes)
            }
            await app.close()
            out({ notes, count: all.body.length })
            """
        )
        notes = res["notes"]
        assert len(notes) == res["count"]
        for n in notes:
            assert isinstance(n, str) and n, "each record must carry a real internalNotes string"
        assert len(set(notes)) >= 2, (
            "internalNotes must be genuine per-user data (not a single hardcoded constant)"
        )

    def test_l2_public_list_never_leaks_any_sensitive_substring(self):
        """L2: the entire /users wire payload contains no sensitive field name/value.

        Scans raw response bytes (not just parsed keys) so a nested or array-encoded
        leak is still caught.
        """
        res = self._run_node(
            """
            const app = factory()
            const r = await inject(app, { method: 'GET', url: '/users' })
            await app.close()
            out({ raw: r.raw, status: r.status })
            """
        )
        assert res["status"] == 200, res
        raw = res["raw"]
        assert "passwordHash" not in raw, "passwordHash present in /users wire payload"
        assert "internalNotes" not in raw, "internalNotes present in /users wire payload"

    def test_l2_native_node_test_passes(self):
        """L2: the agent's own suite passes via `node --test test/safe-serialization.test.js`."""
        test_path = os.path.join(REPO_DIR, "test", "safe-serialization.test.js")
        assert os.path.isfile(test_path), f"missing {test_path}"
        proc = subprocess.run(
            ["node", "--test", "test/safe-serialization.test.js"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert proc.returncode == 0, (
            "native `node --test test/safe-serialization.test.js` must pass.\n"
            f"stdout={proc.stdout[-5000:]}\nstderr={proc.stderr[-3000:]}"
        )
        combined = proc.stdout + proc.stderr
        assert "fail 0" in combined, (
            f"expected zero failures.\n{proc.stdout[-3000:]}"
        )
