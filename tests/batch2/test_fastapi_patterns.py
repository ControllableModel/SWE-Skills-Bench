"""
Test for the 'fastapi-patterns' skill — Bulk Item Creation for the Current User.

The ext2 variant asks the agent to extend the full-stack-fastapi-template items
router with an AUTHENTICATED endpoint that accepts a JSON ARRAY of item-creation
payloads and persists all of them for the calling user, returning the created
items together with an accurate count. A response model that bundles the items
plus a count must be added to backend/app/models.py.

Verification strategy
---------------------
The template is hard-wired to Postgres, so we cannot rely on a live database.
Each behavioral (L2) test runs a self-contained driver under the backend package
(same interpreter that runs pytest) that:
  * builds an in-memory SQLite engine and creates all tables,
  * overrides the `get_db` dependency so the app uses that SQLite session,
  * seeds a known active owner directly,
  * mints a real JWT for that owner via app.core.security.create_access_token,
  * calls the bulk endpoint with a TestClient using that Bearer token,
  * prints a JSON result that this test deeply validates.

The bulk-create POST route is DISCOVERED dynamically from the OpenAPI schema (a
POST route on the items router whose requestBody is an ARRAY), so the exact path
the agent chose (e.g. /items/bulk) does not matter. A naive solution that only
edits files, hardcodes the count, ignores the request body, drops items,
trusts a client-supplied owner, fails to validate elements, or leaks internal
fields will fail these tests.
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
# global engine for SQLite, create tables, seed an active owner, mint a JWT, and
# override get_db. OWNER_ID / TOKEN / AUTH let each driver authenticate.
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
from app.core import security
from app.core.config import settings

def _get_db_override():
    with Session(_sqlite) as s:
        yield s

app.dependency_overrides[get_db] = _get_db_override

# Seed one active owner. A second user lets us prove ownership is forced.
OWNER_ID = uuid.uuid4()
OTHER_ID = uuid.uuid4()

def _seed_users():
    with Session(_sqlite) as s:
        owner = models.User(
            id=OWNER_ID,
            email="owner@example.com",
            hashed_password="x",
            is_active=True,
            is_superuser=False,
        )
        other = models.User(
            id=OTHER_ID,
            email="other@example.com",
            hashed_password="x",
            is_active=True,
            is_superuser=False,
        )
        s.add(owner)
        s.add(other)
        s.commit()

# Real JWT for the seeded owner (matches get_current_user decoding).
def _token_for(uid):
    return security.create_access_token(uid, expires_delta=timedelta(hours=1))

TOKEN = None
AUTH = {}

def _login_owner():
    global TOKEN, AUTH
    TOKEN = _token_for(OWNER_ID)
    AUTH = {"Authorization": "Bearer %s" % TOKEN}

client = TestClient(app)

def _db_items():
    """Return all Item rows currently in the DB as dicts."""
    with Session(_sqlite) as s:
        rows = s.exec(select(models.Item)).all()
        return [
            {"id": str(r.id), "title": r.title, "description": r.description,
             "owner_id": str(r.owner_id)}
            for r in rows
        ]

def _db_item_count():
    with Session(_sqlite) as s:
        return int(s.exec(select(func.count()).select_from(models.Item)).one())

def _discover_bulk_route():
    """Return the POST path on the items router whose request body is an array.

    Resolves $ref-wrapped array schemas. Returns None if not found.
    """
    schema = app.openapi()
    comps = schema.get("components", {}).get("schemas", {})

    def _resolve(node):
        # Follow a single $ref into components/schemas.
        if isinstance(node, dict) and "$ref" in node:
            ref = node["$ref"].split("/")[-1]
            return comps.get(ref, {})
        return node

    def _is_array_body(spec):
        rb = spec.get("requestBody")
        if not rb:
            return False
        content = rb.get("content", {})
        media = content.get("application/json", {})
        sch = _resolve(media.get("schema", {}))
        if not isinstance(sch, dict):
            return False
        if sch.get("type") == "array":
            return True
        # Some generators wrap array under allOf/anyOf.
        for key in ("allOf", "anyOf", "oneOf"):
            for sub in sch.get(key, []) or []:
                if _resolve(sub).get("type") == "array":
                    return True
        return False

    best = None
    for path, methods in schema.get("paths", {}).items():
        spec = methods.get("post")
        if not spec:
            continue
        if "items" not in spec.get("tags", []):
            continue
        if "{" in path:
            continue
        if _is_array_body(spec):
            best = path
            break
    return best
'''


def _run_driver(body: str, timeout: int = 300):
    """Write a driver .py under backend/ and run it with this interpreter.

    Runs with cwd=backend so `app` is importable. Returns parsed JSON printed
    by the driver between the RESULT markers.
    """
    if not os.path.isdir(BACKEND_DIR):
        pytest.fail("backend/ directory not found at %s" % BACKEND_DIR)

    driver_path = os.path.join(BACKEND_DIR, "_skilltest_bulk_driver.py")
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


class TestFastapiPatterns:
    """Verify the authenticated bulk item-creation endpoint."""

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
            "posts = [p for p, m in schema['paths'].items()\n"
            "         if 'items' in m.get('post', {}).get('tags', [])]\n"
            + _emit("{'item_post_paths': posts}")
        )
        res = _run_driver(body)
        assert len(res["item_post_paths"]) >= 1, (
            "no POST routes tagged 'items' found in OpenAPI schema"
        )

    def test_bulk_route_discoverable(self):
        """A POST route on the items router taking an ARRAY body must exist."""
        body = (
            "p = _discover_bulk_route()\n"
            + _emit("{'bulk': p}")
        )
        res = _run_driver(body)
        assert res["bulk"], (
            "no POST route on items router accepts a JSON array body "
            "(the bulk-create endpoint was not added)"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavioral validation of the bulk endpoint.
    # ------------------------------------------------------------------ #

    def test_bulk_creates_all_items_with_count(self):
        """Three valid items create exactly 3 rows and report count 3."""
        body = (
            "_seed_users()\n"
            "_login_owner()\n"
            "path = _discover_bulk_route()\n"
            "assert path, 'bulk route not discovered'\n"
            "payload = [\n"
            "    {'title': 'alpha one', 'description': 'a'},\n"
            "    {'title': 'beta two', 'description': None},\n"
            "    {'title': 'gamma three', 'description': 'c'},\n"
            "]\n"
            "r = client.post(path, headers=AUTH, json=payload)\n"
            "b = r.json() if r.headers.get('content-type','').startswith('application/json') else {}\n"
            "data = b.get('data') if isinstance(b, dict) else None\n"
            "if data is None and isinstance(b, list):\n"
            "    data = b\n"
            "titles = sorted(i.get('title') for i in data) if isinstance(data, list) else []\n"
            + _emit("{'status': r.status_code, 'db_count': _db_item_count(), "
                    "'count_field': (b.get('count') if isinstance(b, dict) else None), "
                    "'returned_len': (len(data) if isinstance(data, list) else None), "
                    "'titles': titles}")
        )
        res = _run_driver(body)
        assert res["status"] in (200, 201), (
            "bulk create with 3 valid items should succeed, got %s" % res["status"]
        )
        assert res["db_count"] == 3, (
            "exactly 3 items must be persisted, DB has %s" % res["db_count"]
        )
        assert res["count_field"] == 3, (
            "response must report an accurate count of 3, got %s"
            % res["count_field"]
        )
        assert res["returned_len"] == 3, (
            "response must echo back all 3 created items, got %s"
            % res["returned_len"]
        )
        assert res["titles"] == ["alpha one", "beta two", "gamma three"], res["titles"]

    def test_bulk_persists_distinct_count(self):
        """A different list size (5) persists exactly 5 — count is not hardcoded."""
        body = (
            "_seed_users()\n"
            "_login_owner()\n"
            "path = _discover_bulk_route()\n"
            "assert path, 'bulk route not discovered'\n"
            "payload = [{'title': 'item %d' % n, 'description': None} "
            "for n in range(5)]\n"
            "r = client.post(path, headers=AUTH, json=payload)\n"
            "b = r.json() if r.status_code < 500 else {}\n"
            + _emit("{'status': r.status_code, 'db_count': _db_item_count(), "
                    "'count_field': (b.get('count') if isinstance(b, dict) else None)}")
        )
        res = _run_driver(body)
        assert res["status"] in (200, 201), res
        assert res["db_count"] == 5, (
            "5 items in the body must persist 5 rows, got %s" % res["db_count"]
        )
        assert res["count_field"] == 5, (
            "count must reflect the body size (5), not a fixed value, got %s"
            % res["count_field"]
        )

    def test_bulk_items_owned_by_caller(self):
        """Every created item is owned by the authenticated caller."""
        body = (
            "_seed_users()\n"
            "_login_owner()\n"
            "path = _discover_bulk_route()\n"
            "assert path, 'bulk route not discovered'\n"
            "# Attempt to spoof ownership via an owner_id field in each element.\n"
            "payload = [\n"
            "    {'title': 'owned a', 'description': 'x', 'owner_id': str(OTHER_ID)},\n"
            "    {'title': 'owned b', 'description': 'y', 'owner_id': str(OTHER_ID)},\n"
            "]\n"
            "r = client.post(path, headers=AUTH, json=payload)\n"
            "rows = _db_items()\n"
            "owners = sorted(set(row['owner_id'] for row in rows))\n"
            + _emit("{'status': r.status_code, 'db_count': len(rows), "
                    "'owners': owners, 'owner_id': str(OWNER_ID), "
                    "'other_id': str(OTHER_ID)}")
        )
        res = _run_driver(body)
        assert res["status"] in (200, 201), res
        assert res["db_count"] == 2, res
        assert res["owners"] == [res["owner_id"]], (
            "all bulk-created items must belong to the caller (%s), got owners %s"
            % (res["owner_id"], res["owners"])
        )
        assert res["other_id"] not in res["owners"], (
            "client-supplied owner_id must be ignored; ownership leaked to %s"
            % res["other_id"]
        )

    def test_bulk_empty_array_rejected_422(self):
        """An empty array body is rejected with HTTP 422 and persists nothing."""
        body = (
            "_seed_users()\n"
            "_login_owner()\n"
            "path = _discover_bulk_route()\n"
            "assert path, 'bulk route not discovered'\n"
            "r = client.post(path, headers=AUTH, json=[])\n"
            + _emit("{'status': r.status_code, 'db_count': _db_item_count()}")
        )
        res = _run_driver(body)
        assert res["status"] == 422, (
            "empty array must be rejected with 422, got %s" % res["status"]
        )
        assert res["db_count"] == 0, (
            "no items must be persisted when the body is empty, got %s"
            % res["db_count"]
        )

    def test_bulk_invalid_element_rejected_and_atomic(self):
        """An element with an empty title is rejected (422) and nothing persists."""
        body = (
            "_seed_users()\n"
            "_login_owner()\n"
            "path = _discover_bulk_route()\n"
            "assert path, 'bulk route not discovered'\n"
            "payload = [\n"
            "    {'title': 'valid one', 'description': 'ok'},\n"
            "    {'title': '', 'description': 'bad'},\n"
            "    {'title': 'valid two', 'description': 'ok'},\n"
            "]\n"
            "r = client.post(path, headers=AUTH, json=payload)\n"
            + _emit("{'status': r.status_code, 'db_count': _db_item_count()}")
        )
        res = _run_driver(body)
        assert res["status"] == 422, (
            "an element with an empty title must yield 422, got %s" % res["status"]
        )
        assert res["db_count"] == 0, (
            "a rejected bulk request must persist NOTHING (atomic), DB has %s"
            % res["db_count"]
        )

    def test_bulk_missing_title_rejected(self):
        """An element missing the required `title` field is rejected with 422."""
        body = (
            "_seed_users()\n"
            "_login_owner()\n"
            "path = _discover_bulk_route()\n"
            "assert path, 'bulk route not discovered'\n"
            "payload = [\n"
            "    {'title': 'ok', 'description': 'd'},\n"
            "    {'description': 'no title here'},\n"
            "]\n"
            "r = client.post(path, headers=AUTH, json=payload)\n"
            + _emit("{'status': r.status_code, 'db_count': _db_item_count()}")
        )
        res = _run_driver(body)
        assert res["status"] == 422, (
            "missing required title must yield 422, got %s" % res["status"]
        )
        assert res["db_count"] == 0, res

    def test_bulk_requires_auth(self):
        """An unauthenticated bulk request is rejected (401/403) and persists nothing."""
        body = (
            "_seed_users()\n"
            "path = _discover_bulk_route()\n"
            "assert path, 'bulk route not discovered'\n"
            "payload = [{'title': 'no auth', 'description': 'x'}]\n"
            "# Send NO Authorization header.\n"
            "r = client.post(path, json=payload)\n"
            + _emit("{'status': r.status_code, 'db_count': _db_item_count()}")
        )
        res = _run_driver(body)
        assert res["status"] in (401, 403), (
            "unauthenticated bulk create must be rejected, got %s" % res["status"]
        )
        assert res["db_count"] == 0, (
            "an unauthenticated request must not persist items, got %s"
            % res["db_count"]
        )

    def test_bulk_response_only_public_fields(self):
        """Each returned item exposes only the public item shape, no internals."""
        body = (
            "_seed_users()\n"
            "_login_owner()\n"
            "path = _discover_bulk_route()\n"
            "assert path, 'bulk route not discovered'\n"
            "payload = [{'title': 'pub field', 'description': 'desc'}]\n"
            "r = client.post(path, headers=AUTH, json=payload)\n"
            "b = r.json()\n"
            "data = b.get('data') if isinstance(b, dict) else b\n"
            "item = data[0] if isinstance(data, list) and data else {}\n"
            + _emit("{'status': r.status_code, 'keys': sorted(item.keys()), "
                    "'title': item.get('title'), 'owner_id': item.get('owner_id')}")
        )
        res = _run_driver(body)
        assert res["status"] in (200, 201), res
        keys = set(res["keys"])
        # ItemPublic public shape: id, title, description, owner_id, created_at.
        allowed = {"id", "title", "description", "owner_id", "created_at"}
        assert keys, "returned item carried no fields"
        assert keys.issubset(allowed), (
            "bulk item leaked non-public fields: %s" % (keys - allowed)
        )
        for forbidden in ("hashed_password", "owner", "is_superuser",
                          "is_active", "email", "password"):
            assert forbidden not in keys, (
                "bulk item must not expose '%s'" % forbidden
            )
        assert res["title"] == "pub field"
        assert res["owner_id"], "owner_id must be present in the public shape"

    def test_bulk_reflected_in_get_listing(self):
        """After a bulk create, GET /items/ for the caller lists the new items."""
        body = (
            "_seed_users()\n"
            "_login_owner()\n"
            "path = _discover_bulk_route()\n"
            "assert path, 'bulk route not discovered'\n"
            "payload = [\n"
            "    {'title': 'list a', 'description': '1'},\n"
            "    {'title': 'list b', 'description': '2'},\n"
            "    {'title': 'list c', 'description': '3'},\n"
            "]\n"
            "r = client.post(path, headers=AUTH, json=payload)\n"
            "base = settings.API_V1_STR + '/items/'\n"
            "g = client.get(base, headers=AUTH, params={'limit': 100, 'skip': 0})\n"
            "gb = g.json()\n"
            "titles = sorted(i.get('title') for i in gb.get('data', []))\n"
            + _emit("{'post_status': r.status_code, 'get_status': g.status_code, "
                    "'get_count': gb.get('count'), 'titles': titles}")
        )
        res = _run_driver(body)
        assert res["post_status"] in (200, 201), res
        assert res["get_status"] == 200, res
        assert res["get_count"] == 3, (
            "GET /items/ must reflect the 3 bulk-created items, count=%s"
            % res["get_count"]
        )
        assert res["titles"] == ["list a", "list b", "list c"], res["titles"]

    def test_single_create_route_intact(self):
        """The original single-item POST /items/ still works and is owner-scoped."""
        body = (
            "_seed_users()\n"
            "_login_owner()\n"
            "base = settings.API_V1_STR + '/items/'\n"
            "r = client.post(base, headers=AUTH, "
            "json={'title': 'single', 'description': 'one'})\n"
            "b = r.json()\n"
            "rows = _db_items()\n"
            + _emit("{'status': r.status_code, 'db_count': len(rows), "
                    "'owner_id': (b.get('owner_id') if isinstance(b, dict) else None), "
                    "'expected_owner': str(OWNER_ID), 'title': "
                    "(b.get('title') if isinstance(b, dict) else None)}")
        )
        res = _run_driver(body)
        assert res["status"] in (200, 201), (
            "original single-item create must still work, got %s" % res["status"]
        )
        assert res["db_count"] == 1, res
        assert res["title"] == "single", res
        assert res["owner_id"] == res["expected_owner"], (
            "single create must remain owner-scoped to the caller"
        )
