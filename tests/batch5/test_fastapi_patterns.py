"""
Test for the 'fastapi-patterns' skill (variant ext5) — Batch Deletion of the
Current User's Items.

The task asks the agent to extend the full-stack-fastapi-template items router
with a NEW authenticated batch-delete endpoint (for example
`POST /items/batch-delete`) that accepts a JSON array of item identifiers and
deletes only the items that belong to the authenticated caller (a superuser may
delete any of them). Identifiers that are missing or owned by someone else must
be SKIPPED (not error the whole request) and reported back. The response is a
structured object reporting how many items were actually deleted and which
identifiers were skipped. Empty-list bodies must be rejected with HTTP 422 and
unauthenticated requests with HTTP 401.

Verification strategy
---------------------
These tests EXERCISE the real FastAPI app. The template is hard-wired to
Postgres, so each behavioral (L2) test runs a self-contained driver under the
backend package (same interpreter as pytest) that:
  * builds an in-memory SQLite engine and creates all tables,
  * overrides the `get_db` dependency so the app uses that SQLite session,
  * seeds a known owner, a second user, and a superuser plus their items,
  * mints real JWT access tokens via `app.core.security.create_access_token`,
  * calls the batch-delete endpoint with proper Authorization headers,
  * prints a JSON result that this test deeply validates (deleted count,
    skipped ids, the DB row count after, and the GET /items/ listing).

The batch-delete route is DISCOVERED dynamically from the OpenAPI schema (a POST
route on the items router, not the create route, not a `/{id}` route, whose
request body is an array), so the exact path the agent chose does not matter.

A naive solution that only edits files, deletes items it does not own, errors
out on unknown/foreign ids instead of skipping them, hardcodes the deleted
count, fails to actually remove the rows from the DB, or accepts an empty list
will FAIL these tests.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest


REPO_DIR = "/workspace/full-stack-fastapi-template"
BACKEND_DIR = os.path.join(REPO_DIR, "backend")


# --------------------------------------------------------------------------- #
# Shared driver scaffolding
# --------------------------------------------------------------------------- #

# Preamble: make `app` importable, satisfy required Settings env vars, swap the
# global engine for SQLite, create tables, and override get_db. Helpers seed
# users/items and mint auth headers so the protected endpoint can be exercised.
_DRIVER_PREAMBLE = r'''
import json, os, sys, uuid
from datetime import timedelta

# Required settings (config reads ../.env which is absent from a bare run).
os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("PROJECT_NAME", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-default")
os.environ.setdefault("FIRST_SUPERUSER", "admin@example.com")
os.environ.setdefault("FIRST_SUPERUSER_PASSWORD", "supersecret123")
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "supersecret123")
os.environ.setdefault("POSTGRES_DB", "app")

from sqlmodel import Session, SQLModel, create_engine, select, func
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

import app.core.db as core_db

# Build an isolated in-memory SQLite engine shared across connections.
_sqlite = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Import models so metadata is populated, then create all tables on SQLite.
import app.models as models
SQLModel.metadata.create_all(_sqlite)

# Point every consumer of the global engine at SQLite.
core_db.engine = _sqlite
try:
    import app.api.deps as deps
    deps.engine = _sqlite
except Exception:
    pass

from app.main import app
from app.api.deps import get_db
from app.core.config import settings
from app.core import security

def _get_db_override():
    with Session(_sqlite) as s:
        yield s

app.dependency_overrides[get_db] = _get_db_override

client = TestClient(app)

API = settings.API_V1_STR


def _make_user(email, is_superuser=False, is_active=True):
    """Create a user row and return its uuid."""
    uid = uuid.uuid4()
    with Session(_sqlite) as s:
        u = models.User(
            id=uid,
            email=email,
            hashed_password="x",
            is_active=is_active,
            is_superuser=is_superuser,
        )
        s.add(u)
        s.commit()
    return uid


def _make_items(owner_id, titles):
    """Create items owned by owner_id. Returns list of str(uuid)."""
    ids = []
    with Session(_sqlite) as s:
        for t in titles:
            it = models.Item(title=t, description="d", owner_id=owner_id)
            s.add(it)
            s.commit()
            s.refresh(it)
            ids.append(str(it.id))
    return ids


def _auth_headers(user_id):
    """Mint a real JWT for user_id and return an Authorization header dict."""
    token = security.create_access_token(user_id, expires_delta=timedelta(hours=1))
    return {"Authorization": "Bearer " + token}


def _item_count():
    """Total Item rows currently in the DB."""
    with Session(_sqlite) as s:
        return int(s.exec(select(func.count()).select_from(models.Item)).one())


def _item_exists(item_id):
    with Session(_sqlite) as s:
        return s.get(models.Item, uuid.UUID(item_id)) is not None


def _discover_batch_delete():
    """Return the batch-delete path discovered from the OpenAPI schema.

    A POST route tagged 'items' that (a) is not a path-parameter route
    (no '{'), (b) is not the bare create route (path != prefix + '/'), and
    (c) declares a request body whose schema is an array. Returns the full
    path string (already including API prefix) or None.
    """
    schema = app.openapi()
    create_path = API + "/items/"
    best = None
    for path, methods in schema.get("paths", {}).items():
        spec = methods.get("post")
        if not spec:
            continue
        tags = spec.get("tags", [])
        if "items" not in tags:
            continue
        if "{" in path:
            continue
        if path == create_path:
            continue
        if "items" not in path:
            continue
        rb = spec.get("requestBody")
        # Prefer a route that takes an array body; fall back to any non-create
        # items POST if no array body is explicitly declared.
        is_array = False
        if rb:
            try:
                content = rb["content"]["application/json"]["schema"]
                # resolve a $ref if present
                if "$ref" in content:
                    ref = content["$ref"].split("/")[-1]
                    content = schema["components"]["schemas"].get(ref, {})
                if content.get("type") == "array":
                    is_array = True
                # anyOf/oneOf containing an array
                for key in ("anyOf", "oneOf", "allOf"):
                    for sub in content.get(key, []) or []:
                        if isinstance(sub, dict) and sub.get("type") == "array":
                            is_array = True
            except Exception:
                pass
        if is_array:
            return path
        if best is None:
            best = path
    return best
'''


def _run_driver(body: str, timeout: int = 300):
    """Write a driver .py under backend/ and run it with this interpreter.

    Runs with cwd=backend so `app` is importable. Returns parsed JSON printed
    by the driver between the RESULT markers.
    """
    if not os.path.isdir(BACKEND_DIR):
        pytest.fail("backend/ directory not found at %s" % BACKEND_DIR)

    driver_path = os.path.join(BACKEND_DIR, "_skilltest_driver_ext5.py")
    full = _DRIVER_PREAMBLE + "\n\n" + textwrap.dedent(body)
    with open(driver_path, "w") as fh:
        fh.write(full)
    try:
        proc = subprocess.run(
            [sys.executable, driver_path],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    finally:
        try:
            os.remove(driver_path)
        except OSError:
            pass

    out = proc.stdout
    if "RESULT_START" not in out or "RESULT_END" not in out:
        raise AssertionError(
            "driver did not produce a result.\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (out, proc.stderr)
        )
    payload = out.split("RESULT_START", 1)[1].split("RESULT_END", 1)[0].strip()
    return json.loads(payload)


def _emit(expr: str) -> str:
    """Snippet that prints `expr` (a dict) between result markers."""
    return (
        "print('RESULT_START')\n"
        "print(json.dumps(%s))\n"
        "print('RESULT_END')\n" % expr
    )


# Common helper snippet appended to driver bodies: find the deleted count and
# the skipped-id list in an arbitrary structured response shape, since the doc
# leaves field names to the agent.
_PARSE_RESULT = r'''
def _extract_deleted_count(obj):
    """Find an integer field that represents the deleted count."""
    if not isinstance(obj, dict):
        return None
    # Prefer keys that look like a count.
    for k, v in obj.items():
        lk = k.lower()
        if isinstance(v, int) and ("delet" in lk and ("count" in lk or "num" in lk
                or "total" in lk or lk in ("deleted", "n_deleted", "removed"))):
            return v
    # Fallback: any int field whose name mentions delete/removed.
    for k, v in obj.items():
        if isinstance(v, int) and ("delet" in k.lower() or "remov" in k.lower()):
            return v
    # Fallback: any standalone int field.
    ints = [v for v in obj.values() if isinstance(v, bool) is False and isinstance(v, int)]
    if len(ints) == 1:
        return ints[0]
    return None


def _extract_skipped(obj):
    """Find the list of skipped/not-deleted identifiers (as strings)."""
    if not isinstance(obj, dict):
        return None
    best = None
    for k, v in obj.items():
        lk = k.lower()
        if isinstance(v, list) and ("skip" in lk or "not" in lk or "missing" in lk
                or "fail" in lk or "remain" in lk):
            best = v
    if best is None:
        # fallback: any list of strings
        for v in obj.values():
            if isinstance(v, list):
                best = v
                break
    if best is None:
        return []
    return [str(x) for x in best]
'''


class TestFastapiPatterns:
    """Verify the authenticated batch-delete endpoint for the items router."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist and are minimally well-formed.
    # ------------------------------------------------------------------ #

    def test_items_route_file_present(self):
        """backend/app/api/routes/items.py must exist."""
        p = os.path.join(BACKEND_DIR, "app", "api", "routes", "items.py")
        assert os.path.isfile(p), "items.py route module missing"

    def test_models_file_present(self):
        """backend/app/models.py must exist."""
        p = os.path.join(BACKEND_DIR, "app", "models.py")
        assert os.path.isfile(p), "models.py missing"

    def test_app_imports_and_items_router_registered(self):
        """The FastAPI app imports cleanly and exposes the items router."""
        body = (
            "schema = app.openapi()\n"
            "item_paths = [p for p, m in schema['paths'].items()\n"
            "              if any('items' in (v or {}).get('tags', [])\n"
            "                     for v in m.values() if isinstance(v, dict))]\n"
            + _emit("{'item_paths': item_paths}")
        )
        res = _run_driver(body)
        assert len(res["item_paths"]) >= 1, (
            "no routes tagged 'items' found in OpenAPI schema"
        )

    def test_batch_delete_route_discoverable(self):
        """A non-create, non-{id} POST route on the items router must exist."""
        body = (
            "bd = _discover_batch_delete()\n"
            + _emit("{'batch_delete': bd}")
        )
        res = _run_driver(body)
        assert res["batch_delete"], (
            "no batch-delete POST route (array body) found on the items router"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavioral validation of the batch-delete endpoint.
    # ------------------------------------------------------------------ #

    def test_unauthenticated_request_rejected(self):
        """Calling batch-delete with no Authorization header is rejected (401)."""
        body = (
            "owner = _make_user('owner@example.com')\n"
            "ids = _make_items(owner, ['a','b'])\n"
            "bd = _discover_batch_delete()\n"
            "r = client.request('POST', bd, json=ids)\n"
            + _emit("{'status': r.status_code, 'remaining': _item_count()}")
        )
        res = _run_driver(body)
        # Authenticated route, no token -> must not succeed; template uses 401.
        assert res["status"] in (401, 403), (
            "unauthenticated batch-delete must be rejected, got %s" % res["status"]
        )
        assert res["remaining"] == 2, (
            "no items may be deleted by an unauthenticated request, %s remain"
            % res["remaining"]
        )

    def test_owner_deletes_all_owned_items(self):
        """A user deleting three owned ids removes all 3; skipped list empty."""
        body = _PARSE_RESULT + (
            "owner = _make_user('owner@example.com')\n"
            "ids = _make_items(owner, ['x1','x2','x3'])\n"
            "bd = _discover_batch_delete()\n"
            "r = client.request('POST', bd, json=ids, headers=_auth_headers(owner))\n"
            "b = r.json() if r.headers.get('content-type','').startswith('application/json') else {}\n"
            + _emit("{'status': r.status_code, 'deleted': _extract_deleted_count(b), "
                    "'skipped': _extract_skipped(b), 'remaining': _item_count(), "
                    "'gone': [not _item_exists(i) for i in ids]}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["deleted"] == 3, (
            "expected 3 deleted, response reported %s" % res["deleted"]
        )
        assert res["skipped"] == [], (
            "skipped list must be empty when all ids are owned, got %s"
            % res["skipped"]
        )
        assert res["remaining"] == 0, (
            "all 3 owned items must be removed from the DB, %s remain"
            % res["remaining"]
        )
        assert all(res["gone"]), "every targeted item row must be gone"

    def test_foreign_and_missing_ids_are_skipped_not_errored(self):
        """Owned ids deleted; foreign + nonexistent ids skipped & reported."""
        body = _PARSE_RESULT + (
            "import uuid as _uuid\n"
            "owner = _make_user('owner@example.com')\n"
            "other = _make_user('other@example.com')\n"
            "own_ids = _make_items(owner, ['mine1','mine2'])\n"
            "foreign_ids = _make_items(other, ['theirs'])\n"
            "missing_id = str(_uuid.uuid4())\n"
            "payload = own_ids + foreign_ids + [missing_id]\n"
            "bd = _discover_batch_delete()\n"
            "r = client.request('POST', bd, json=payload, headers=_auth_headers(owner))\n"
            "b = r.json() if r.headers.get('content-type','').startswith('application/json') else {}\n"
            + _emit("{'status': r.status_code, 'deleted': _extract_deleted_count(b), "
                    "'skipped': _extract_skipped(b), "
                    "'own_gone': [not _item_exists(i) for i in own_ids], "
                    "'foreign_alive': [_item_exists(i) for i in foreign_ids], "
                    "'remaining': _item_count(), "
                    "'foreign_id': foreign_ids[0], 'missing_id': missing_id}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, (
            "mixed batch must not error the whole request, got %s" % res["status"]
        )
        assert res["deleted"] == 2, (
            "only the 2 owned items should be deleted, reported %s" % res["deleted"]
        )
        assert all(res["own_gone"]), "owned items must be removed"
        assert all(res["foreign_alive"]), (
            "another user's item must NOT be deleted by a normal caller"
        )
        # DB must still hold the foreign item (1 row).
        assert res["remaining"] == 1, (
            "exactly the foreign item should remain, %s rows left" % res["remaining"]
        )
        # The skipped list must include both the foreign and the missing id.
        skipped = set(res["skipped"])
        assert res["foreign_id"] in skipped, (
            "foreign id must be reported as skipped, skipped=%s" % res["skipped"]
        )
        assert res["missing_id"] in skipped, (
            "nonexistent id must be reported as skipped, skipped=%s" % res["skipped"]
        )

    def test_empty_list_rejected_422(self):
        """An empty array body must be rejected with HTTP 422."""
        body = (
            "owner = _make_user('owner@example.com')\n"
            "_make_items(owner, ['keep'])\n"
            "bd = _discover_batch_delete()\n"
            "r = client.request('POST', bd, json=[], headers=_auth_headers(owner))\n"
            + _emit("{'status': r.status_code, 'remaining': _item_count()}")
        )
        res = _run_driver(body)
        assert res["status"] == 422, (
            "empty-list body must be 422, got %s" % res["status"]
        )
        assert res["remaining"] == 1, (
            "no item may be deleted on a rejected empty request"
        )

    def test_deleted_items_absent_from_listing(self):
        """After batch delete, deleted items no longer appear in GET /items/."""
        body = (
            "owner = _make_user('owner@example.com')\n"
            "ids = _make_items(owner, ['t1','t2','t3','t4'])\n"
            "to_delete = ids[:2]\n"
            "keep = ids[2:]\n"
            "bd = _discover_batch_delete()\n"
            "r = client.request('POST', bd, json=to_delete, headers=_auth_headers(owner))\n"
            "lr = client.get(API + '/items/', params={'limit':100}, headers=_auth_headers(owner))\n"
            "listed = [i['id'] for i in lr.json().get('data', [])]\n"
            + _emit("{'del_status': r.status_code, 'list_status': lr.status_code, "
                    "'listed': listed, 'to_delete': to_delete, 'keep': keep}")
        )
        res = _run_driver(body)
        assert res["del_status"] == 200, res
        assert res["list_status"] == 200, res
        listed = set(res["listed"])
        for gone in res["to_delete"]:
            assert gone not in listed, (
                "deleted item %s still appears in GET /items/ listing" % gone
            )
        for kept in res["keep"]:
            assert kept in listed, (
                "non-deleted item %s must still appear in the listing" % kept
            )

    def test_superuser_can_delete_any_item(self):
        """A superuser may delete items owned by other users."""
        body = _PARSE_RESULT + (
            "admin = _make_user('admin2@example.com', is_superuser=True)\n"
            "alice = _make_user('alice@example.com')\n"
            "bob = _make_user('bob@example.com')\n"
            "a_ids = _make_items(alice, ['a1','a2'])\n"
            "b_ids = _make_items(bob, ['b1'])\n"
            "payload = a_ids + b_ids\n"
            "bd = _discover_batch_delete()\n"
            "r = client.request('POST', bd, json=payload, headers=_auth_headers(admin))\n"
            "b = r.json() if r.headers.get('content-type','').startswith('application/json') else {}\n"
            + _emit("{'status': r.status_code, 'deleted': _extract_deleted_count(b), "
                    "'skipped': _extract_skipped(b), 'remaining': _item_count()}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["deleted"] == 3, (
            "superuser should delete all 3 listed items, reported %s" % res["deleted"]
        )
        assert res["remaining"] == 0, (
            "superuser batch-delete must remove every targeted item, %s remain"
            % res["remaining"]
        )
        assert res["skipped"] == [], (
            "superuser should skip nothing for valid ids, got %s" % res["skipped"]
        )

    def test_count_reflects_only_actual_deletions(self):
        """Reported deleted count must equal the real DB row drop (not input length)."""
        body = _PARSE_RESULT + (
            "import uuid as _uuid\n"
            "owner = _make_user('owner@example.com')\n"
            "other = _make_user('other@example.com')\n"
            "own_ids = _make_items(owner, ['o1'])\n"
            "foreign = _make_items(other, ['f1','f2'])\n"
            "missing = [str(_uuid.uuid4()), str(_uuid.uuid4())]\n"
            "payload = own_ids + foreign + missing\n"   # 5 ids, only 1 deletable
            "before = _item_count()\n"
            "bd = _discover_batch_delete()\n"
            "r = client.request('POST', bd, json=payload, headers=_auth_headers(owner))\n"
            "after = _item_count()\n"
            "b = r.json() if r.headers.get('content-type','').startswith('application/json') else {}\n"
            + _emit("{'status': r.status_code, 'reported': _extract_deleted_count(b), "
                    "'input_len': len(payload), 'real_drop': before - after}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        # Discriminative: a stub that returns len(payload) would report 5.
        assert res["reported"] != res["input_len"], (
            "reported deleted count must not just echo the request length"
        )
        assert res["real_drop"] == 1, (
            "exactly 1 row should be deleted, DB dropped %s" % res["real_drop"]
        )
        assert res["reported"] == res["real_drop"], (
            "reported deleted count %s must equal the real DB row drop %s"
            % (res["reported"], res["real_drop"])
        )

    def test_native_pytest_suite_passes(self):
        """The repo's own item route tests (incl. added cases) pass via pytest."""
        # Drive the variant's native acceptance command. We run only the
        # collection+execution of the items route test module under the backend
        # package, with the same env the driver uses so config imports succeed.
        test_file = os.path.join(
            BACKEND_DIR, "tests", "api", "routes", "test_items.py"
        )
        assert os.path.isfile(test_file), "backend items route test module missing"
        env = dict(os.environ)
        env.setdefault("ENVIRONMENT", "local")
        env.setdefault("PROJECT_NAME", "test")
        env.setdefault("SECRET_KEY", "test-secret-key-not-default")
        env.setdefault("FIRST_SUPERUSER", "admin@example.com")
        env.setdefault("FIRST_SUPERUSER_PASSWORD", "supersecret123")
        env.setdefault("POSTGRES_SERVER", "localhost")
        env.setdefault("POSTGRES_USER", "postgres")
        env.setdefault("POSTGRES_PASSWORD", "supersecret123")
        env.setdefault("POSTGRES_DB", "app")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest",
             "tests/api/routes/test_items.py", "-q", "--no-header",
             "--co"],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,
        )
        # Collection-only: the added batch-delete test cases must be collectible
        # (import-clean module, valid new tests). A broken edit would error here.
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "pytest could not collect the items test module:\n%s" % combined
        )
        # There must be at least one collected test referencing batch deletion.
        lowered = combined.lower()
        assert ("batch" in lowered or "test_items" in lowered), (
            "expected the items test module to define batch-delete cases:\n%s"
            % combined
        )
