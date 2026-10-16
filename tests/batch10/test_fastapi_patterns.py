"""
Test for the 'fastapi-patterns' skill — Tag-Filtered Item Listing (variant ext10).

The task asks the agent to extend the full-stack-fastapi-template items router
with an AUTHENTICATED tag-filtered listing endpoint. The caller supplies one or
more keyword tokens via a repeatable query parameter (e.g. ?tag=foo&tag=bar);
an item of the CALLER matches only if its title contains EVERY requested token
(case-insensitive, logical AND). The response is a paginated page of matching
items plus a filter-aware total, exposing only the public item field set.

These tests verify the agent's work by EXERCISING the real FastAPI app. Because
the template is hard-wired to Postgres, we cannot rely on a live database. So
each behavioral (L2) test runs a self-contained driver under the backend package
(via the same interpreter that runs pytest) that:
  * builds an in-memory SQLite engine and creates all tables,
  * overrides the `get_db` dependency so the app uses that SQLite session,
  * inserts a known owner + a second user, each with known items,
  * mints a real JWT for the owner via app.core.security.create_access_token,
  * calls the tag-filter endpoint with TestClient + the owner's Bearer token,
  * prints a JSON result that this test deeply validates.

The tag-filter route is DISCOVERED dynamically from the OpenAPI schema (a GET
route on the items router carrying an array-typed `tag` query parameter), so the
exact path the agent chose (e.g. /items/filter) does not matter.

A naive solution must FAIL: one that ignores the tokens, uses OR instead of AND,
matches case-sensitively, returns other users' items, omits a filter-aware
total, leaks owner-internal fields, accepts an empty token set, or accepts
out-of-range pagination will all be caught.
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
# global engine for SQLite, create tables, and override get_db. Provides:
#   _seed(owner_id, specs) -> create items for a user
#   _make_user(email, superuser) -> create a User, return its uuid
#   _auth(uid) -> dict of Authorization header for a real JWT
#   _discover_tag_route() -> the tag-filter path from the OpenAPI schema
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

from sqlmodel import Session, SQLModel, create_engine
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

def _make_user(email, superuser=False):
    uid = uuid.uuid4()
    with Session(_sqlite) as s:
        u = models.User(
            id=uid,
            email=email,
            hashed_password="x",
            is_active=True,
            is_superuser=superuser,
        )
        s.add(u)
        s.commit()
    return uid

def _seed(owner_id, specs):
    """specs: list of (title, description). Returns list of created item dicts."""
    created = []
    with Session(_sqlite) as s:
        for title, desc in specs:
            it = models.Item(title=title, description=desc, owner_id=owner_id)
            s.add(it)
            s.commit()
            s.refresh(it)
            created.append({"id": str(it.id), "title": it.title,
                            "description": it.description})
    return created

def _auth(uid):
    token = security.create_access_token(uid, expires_delta=timedelta(hours=1))
    return {"Authorization": "Bearer %s" % token}

client = TestClient(app)

def _discover_tag_route():
    """Return the tag-filter path discovered from the OpenAPI schema.

    A GET path under the items router (no path params) that exposes a query
    parameter named 'tag' (or 'tags') whose schema is array-typed. This is the
    repeatable token parameter required by the task. Returns the path string or
    None.
    """
    schema = app.openapi()
    for path, methods in schema.get("paths", {}).items():
        spec = methods.get("get")
        if not spec:
            continue
        if "items" not in spec.get("tags", []):
            continue
        if "{" in path:
            continue
        for p in spec.get("parameters", []):
            if p.get("in") != "query":
                continue
            name = p.get("name")
            if name not in ("tag", "tags"):
                continue
            psch = p.get("schema", {})
            # array-typed directly, or nullable array via anyOf
            if psch.get("type") == "array":
                return path, name
            for sub in psch.get("anyOf", []):
                if isinstance(sub, dict) and sub.get("type") == "array":
                    return path, name
    return None, None
'''


def _run_driver(body: str, timeout: int = 300):
    """Write a driver .py under backend/ and run it with this interpreter.

    Runs with cwd=backend so `app` is importable. Returns parsed JSON printed
    by the driver between the RESULT markers.
    """
    if not os.path.isdir(BACKEND_DIR):
        pytest.fail("backend/ directory not found at %s" % BACKEND_DIR)

    driver_path = os.path.join(BACKEND_DIR, "_skilltest_driver_ext10.py")
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
    """Verify the authenticated tag-filtered item listing endpoint."""

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
        """The FastAPI app imports cleanly and exposes items GET routes."""
        body = (
            "schema = app.openapi()\n"
            "item_paths = [p for p, m in schema['paths'].items()\n"
            "              if 'items' in m.get('get', {}).get('tags', [])]\n"
            + _emit("{'item_get_paths': item_paths}")
        )
        res = _run_driver(body)
        assert len(res["item_get_paths"]) >= 1, (
            "no GET routes tagged 'items' found in OpenAPI schema"
        )

    def test_tag_filter_route_discoverable(self):
        """A GET items route carrying an array-typed `tag` query param exists."""
        body = (
            "path, name = _discover_tag_route()\n"
            + _emit("{'path': path, 'param': name}")
        )
        res = _run_driver(body)
        assert res["path"], (
            "no GET items route with a repeatable array `tag` query parameter "
            "was found; the tag-filtered listing endpoint is missing"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavioral validation of the tag-filter endpoint.
    # ------------------------------------------------------------------ #

    def test_single_token_matches_substring(self):
        """?tag=alpha over the caller's items returns the 2 'alpha' titles."""
        body = (
            "owner = _make_user('owner@example.com')\n"
            "_seed(owner, [('alpha beta','a'),('alpha gamma','b'),('delta','c')])\n"
            "path, name = _discover_tag_route()\n"
            "r = client.get(path, params=[(name,'alpha'),('limit',100),('skip',0)], headers=_auth(owner))\n"
            "b = r.json()\n"
            + _emit("{'status': r.status_code, 'count': b.get('count'), "
                    "'titles': sorted(i.get('title') for i in b.get('data',[]))}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["count"] == 2, (
            "?tag=alpha should match 2 of the caller's items, got %s" % res["count"]
        )
        assert res["titles"] == ["alpha beta", "alpha gamma"], res["titles"]

    def test_multi_token_logical_and(self):
        """?tag=alpha&tag=beta matches only the title containing BOTH tokens."""
        body = (
            "owner = _make_user('owner@example.com')\n"
            "_seed(owner, [('alpha beta','a'),('alpha gamma','b'),('delta','c')])\n"
            "path, name = _discover_tag_route()\n"
            "r = client.get(path, params=[(name,'alpha'),(name,'beta'),('limit',100)], headers=_auth(owner))\n"
            "b = r.json()\n"
            + _emit("{'status': r.status_code, 'count': b.get('count'), "
                    "'titles': [i.get('title') for i in b.get('data',[])]}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        # OR would give 2; AND must give exactly 1.
        assert res["count"] == 1, (
            "two tokens must AND-match (only 'alpha beta'); got count %s "
            "(OR-matching or ignored second token)" % res["count"]
        )
        assert res["titles"] == ["alpha beta"], res["titles"]

    def test_token_matching_case_insensitive(self):
        """Tokens match titles case-insensitively for every requested token."""
        body = (
            "owner = _make_user('owner@example.com')\n"
            "_seed(owner, [('Alpha BETA','a'),('the ALPHA beta cat','b'),"
            "('alpha only','c'),('beta only','d')])\n"
            "path, name = _discover_tag_route()\n"
            "r = client.get(path, params=[(name,'alpha'),(name,'beta'),('limit',100)], headers=_auth(owner))\n"
            "b = r.json()\n"
            + _emit("{'status': r.status_code, 'count': b.get('count'), "
                    "'titles': sorted(i.get('title') for i in b.get('data',[]))}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        # 'Alpha BETA' and 'the ALPHA beta cat' contain both tokens regardless of case.
        assert res["count"] == 2, (
            "case-insensitive AND of alpha+beta should match 2, got %s" % res["count"]
        )
        assert res["titles"] == ["Alpha BETA", "the ALPHA beta cat"], res["titles"]

    def test_pagination_with_filter_aware_total(self):
        """skip/limit page the matches while total reflects the full filter."""
        body = (
            "owner = _make_user('owner@example.com')\n"
            "_seed(owner, [('alpha 1','a'),('alpha 2','b'),('alpha 3','c'),('beta','d')])\n"
            "path, name = _discover_tag_route()\n"
            "# full filtered set to derive expected ordering\n"
            "rf = client.get(path, params=[(name,'alpha'),('limit',100),('skip',0)], headers=_auth(owner))\n"
            "bf = rf.json()\n"
            "# page: limit 2, skip 2 over 3 matches -> exactly 1 remaining\n"
            "r = client.get(path, params=[(name,'alpha'),('limit',2),('skip',2)], headers=_auth(owner))\n"
            "b = r.json()\n"
            + _emit("{'status': r.status_code, 'count': b.get('count'), "
                    "'page_len': len(b.get('data',[])), "
                    "'full_titles': [i['title'] for i in bf.get('data',[])], "
                    "'page_titles': [i['title'] for i in b.get('data',[])]}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["count"] == 3, (
            "filter-aware total must stay 3 regardless of paging, got %s" % res["count"]
        )
        assert res["page_len"] == 1, (
            "limit=2 skip=2 over 3 matches must return 1 item, got %s" % res["page_len"]
        )
        assert len(res["full_titles"]) == 3, res
        assert res["page_titles"][0] == res["full_titles"][2], (
            "paged slice inconsistent with full ordering: page=%s full=%s"
            % (res["page_titles"], res["full_titles"])
        )

    def test_empty_token_set_rejected(self):
        """A request with no `tag` parameter is rejected with HTTP 422."""
        body = (
            "owner = _make_user('owner@example.com')\n"
            "_seed(owner, [('alpha','a')])\n"
            "path, name = _discover_tag_route()\n"
            "r = client.get(path, params=[('limit',100)], headers=_auth(owner))\n"
            + _emit("{'status': r.status_code}")
        )
        res = _run_driver(body)
        assert res["status"] == 422, (
            "empty token set must be rejected with 422, got %s" % res["status"]
        )

    def test_invalid_pagination_rejected(self):
        """limit=0, limit>100 and skip<0 are each rejected with HTTP 422."""
        body = (
            "owner = _make_user('owner@example.com')\n"
            "_seed(owner, [('alpha','a')])\n"
            "path, name = _discover_tag_route()\n"
            "h = _auth(owner)\n"
            "r0 = client.get(path, params=[(name,'alpha'),('limit',0)], headers=h)\n"
            "rb = client.get(path, params=[(name,'alpha'),('limit',101)], headers=h)\n"
            "rn = client.get(path, params=[(name,'alpha'),('skip',-1)], headers=h)\n"
            + _emit("{'limit0': r0.status_code, 'limit101': rb.status_code, "
                    "'skipneg': rn.status_code}")
        )
        res = _run_driver(body)
        assert res["limit0"] == 422, "limit=0 must be 422, got %s" % res["limit0"]
        assert res["limit101"] == 422, "limit>100 must be 422, got %s" % res["limit101"]
        assert res["skipneg"] == 422, "skip=-1 must be 422, got %s" % res["skipneg"]

    def test_requires_authentication(self):
        """An unauthenticated request to the tag-filter endpoint is rejected."""
        body = (
            "owner = _make_user('owner@example.com')\n"
            "_seed(owner, [('alpha','a')])\n"
            "path, name = _discover_tag_route()\n"
            "# No Authorization header.\n"
            "r = client.get(path, params=[(name,'alpha'),('limit',100)])\n"
            + _emit("{'status': r.status_code}")
        )
        res = _run_driver(body)
        assert res["status"] in (401, 403), (
            "tag-filter listing must require auth (401/403 w/o token), got %s"
            % res["status"]
        )

    def test_scoped_to_caller_items_only(self):
        """The listing never includes items owned by other users."""
        body = (
            "owner = _make_user('owner@example.com')\n"
            "other = _make_user('other@example.com')\n"
            "_seed(owner, [('alpha mine','a')])\n"
            "_seed(other, [('alpha theirs','b'),('alpha also theirs','c')])\n"
            "path, name = _discover_tag_route()\n"
            "r = client.get(path, params=[(name,'alpha'),('limit',100)], headers=_auth(owner))\n"
            "b = r.json()\n"
            + _emit("{'status': r.status_code, 'count': b.get('count'), "
                    "'titles': sorted(i.get('title') for i in b.get('data',[]))}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["count"] == 1, (
            "only the caller's own matching item should count, got %s" % res["count"]
        )
        assert res["titles"] == ["alpha mine"], (
            "listing leaked another user's items: %s" % res["titles"]
        )

    def test_only_public_fields_exposed(self):
        """Returned item objects expose only the public item field set."""
        body = (
            "owner = _make_user('owner@example.com')\n"
            "_seed(owner, [('alpha public','some desc')])\n"
            "path, name = _discover_tag_route()\n"
            "r = client.get(path, params=[(name,'alpha'),('limit',100)], headers=_auth(owner))\n"
            "b = r.json()\n"
            "item = b['data'][0] if b.get('data') else {}\n"
            + _emit("{'keys': sorted(item.keys()), 'title': item.get('title'), "
                    "'owner_id': item.get('owner_id')}")
        )
        res = _run_driver(body)
        keys = set(res["keys"])
        # ItemPublic = {id, title, description, owner_id, created_at}
        allowed = {"id", "title", "description", "owner_id", "created_at"}
        assert keys.issubset(allowed), (
            "tag-filter item leaked non-public fields: %s" % (keys - allowed)
        )
        for forbidden in ("hashed_password", "owner", "is_superuser",
                          "is_active", "email"):
            assert forbidden not in keys, (
                "tag-filter item must not expose '%s'" % forbidden
            )
        assert res["title"] == "alpha public", res
        assert res["owner_id"], "owner_id should be present in public shape"

    def test_no_match_returns_empty_page_and_zero_total(self):
        """A token set matching nothing yields an empty page and total 0."""
        body = (
            "owner = _make_user('owner@example.com')\n"
            "_seed(owner, [('alpha beta','a'),('gamma','b')])\n"
            "path, name = _discover_tag_route()\n"
            "r = client.get(path, params=[(name,'zzznotpresent'),('limit',100)], headers=_auth(owner))\n"
            "b = r.json()\n"
            + _emit("{'status': r.status_code, 'len': len(b.get('data',[])), "
                    "'count': b.get('count')}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["len"] == 0, "non-matching token should return 0 items"
        assert res["count"] == 0, "non-matching token total should be 0"

    def test_existing_owner_route_intact(self):
        """The original /items/ owner route still requires auth (untouched)."""
        body = (
            "owner = _make_user('owner@example.com')\n"
            "_seed(owner, [('alpha','a')])\n"
            "base = settings.API_V1_STR + '/items/'\n"
            "r = client.get(base)\n"  # no auth header
            + _emit("{'status': r.status_code}")
        )
        res = _run_driver(body)
        assert res["status"] in (401, 403), (
            "existing owner-scoped /items/ must still require auth, got %s"
            % res["status"]
        )
