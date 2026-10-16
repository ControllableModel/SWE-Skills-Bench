"""
Test for the 'fastapi-patterns' skill — Public Paginated Item Catalog.

The task asks the agent to extend the full-stack-fastapi-template items router
with a PUBLIC (no-auth) paginated catalog listing endpoint plus an aggregate
stats endpoint, exposing only public item fields and rejecting out-of-range
pagination with HTTP 422.

These tests verify the agent's work by EXERCISING the real FastAPI app. Because
the template is hard-wired to Postgres, we cannot rely on a live database. So
each behavioral (L2) test runs a self-contained driver under the backend package
(via the same interpreter that runs pytest) that:
  * builds an in-memory SQLite engine and creates all tables,
  * overrides the `get_db` dependency so the app uses that SQLite session,
  * inserts a known owner + a known set of items directly,
  * calls the public endpoints with a TestClient and NO auth headers,
  * prints a JSON result that this test deeply validates.

The public catalog/stats routes are DISCOVERED dynamically from the OpenAPI
schema (a GET route on the items router, reachable without auth, returning a
{data, count}-shaped page), so the exact path the agent chose (e.g. /catalog)
does not matter. A naive solution that only edits files, reuses the existing
owner-scoped /items/ route, or leaks owner-internal fields will fail.
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
# global engine for SQLite, create tables, seed an owner, and override get_db.
# The dict KNOWN holds owner id + item ids/titles so each driver can assert.
_DRIVER_PREAMBLE = r'''
import json, os, sys, uuid

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

def _get_db_override():
    with Session(_sqlite) as s:
        yield s

app.dependency_overrides[get_db] = _get_db_override

# Seed one owner + the requested items.
OWNER_ID = uuid.uuid4()
SEED_ITEMS = None  # set by each driver below before _seed() is called

def _seed(specs):
    """specs: list of (title, description). Returns list of created item dicts."""
    created = []
    with Session(_sqlite) as s:
        owner = models.User(
            id=OWNER_ID,
            email="owner@example.com",
            hashed_password="x",
            is_active=True,
            is_superuser=False,
        )
        s.add(owner)
        s.commit()
        for title, desc in specs:
            it = models.Item(title=title, description=desc, owner_id=OWNER_ID)
            s.add(it)
            s.commit()
            s.refresh(it)
            created.append({"id": str(it.id), "title": it.title,
                            "description": it.description})
    return created

client = TestClient(app)

def _discover_catalog_and_stats():
    """Return (catalog_path, stats_path) discovered from the OpenAPI schema.

    catalog: a GET path under the items router whose 200 response is a page
             object ({data: [...], count: int}) and that is reachable WITHOUT
             auth. stats: a GET path under items returning an object of integer
             counts reachable without auth. Paths needing auth are skipped.
    """
    schema = app.openapi()
    candidates = []
    for path, methods in schema.get("paths", {}).items():
        spec = methods.get("get")
        if not spec:
            continue
        tags = spec.get("tags", [])
        if "items" not in tags:
            continue
        # Skip path-parameter routes like /items/{id}.
        if "{" in path:
            continue
        candidates.append(path)
    catalog_path = None
    stats_path = None
    for path in candidates:
        try:
            r = client.get(path)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        body = r.json()
        if isinstance(body, dict) and "data" in body and isinstance(body["data"], list) \
                and "count" in body and isinstance(body.get("count"), int):
            # Prefer the public one: existing /items/ requires auth -> 401/403,
            # so anything returning 200 here without headers is the public one.
            catalog_path = path
        elif isinstance(body, dict) and body and all(
                isinstance(v, int) for v in body.values()):
            stats_path = path
    return catalog_path, stats_path
'''


def _run_driver(body: str, timeout: int = 300):
    """Write a driver .py under backend/ and run it with this interpreter.

    Runs with cwd=backend so `app` is importable. Returns parsed JSON printed
    by the driver between the RESULT markers.
    """
    if not os.path.isdir(BACKEND_DIR):
        pytest.fail("backend/ directory not found at %s" % BACKEND_DIR)

    driver_path = os.path.join(BACKEND_DIR, "_skilltest_driver.py")
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
    """Verify the public paginated item catalog + stats endpoints."""

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

    def test_app_imports_and_router_registered(self):
        """The FastAPI app imports cleanly and exposes the items router."""
        body = (
            "schema = app.openapi()\n"
            "item_paths = [p for p, m in schema['paths'].items()\n"
            "              if m.get('get', {}).get('tags', []) == ['items']\n"
            "              or 'items' in m.get('get', {}).get('tags', [])]\n"
            + _emit("{'item_get_paths': item_paths}")
        )
        res = _run_driver(body)
        assert len(res["item_get_paths"]) >= 1, (
            "no GET routes tagged 'items' found in OpenAPI schema"
        )

    def test_public_catalog_route_discoverable(self):
        """A {data,count} page route on the items router is reachable w/o auth."""
        body = (
            "cat, stats = _discover_catalog_and_stats()\n"
            + _emit("{'catalog': cat, 'stats': stats}")
        )
        res = _run_driver(body)
        assert res["catalog"], (
            "no public (no-auth) catalog page route found on items router"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavioral validation of the public endpoints.
    # ------------------------------------------------------------------ #

    def test_catalog_returns_all_items_and_total(self):
        """GET catalog over 3 items returns all 3 and total count 3."""
        body = (
            "_seed([('alpha one','a'),('beta two','b'),('alpha three','c')])\n"
            "cat, _ = _discover_catalog_and_stats()\n"
            "r = client.get(cat, params={'limit':10,'skip':0})\n"
            "b = r.json()\n"
            + _emit("{'status': r.status_code, 'len': len(b.get('data',[])), "
                    "'count': b.get('count'), 'titles': "
                    "[i.get('title') for i in b.get('data',[])]}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["len"] == 3, "expected 3 items, got %s" % res["len"]
        assert res["count"] == 3, "expected total count 3, got %s" % res["count"]
        assert sorted(res["titles"]) == ["alpha one", "alpha three", "beta two"]

    def test_catalog_requires_no_auth(self):
        """The catalog endpoint must answer 200 with NO Authorization header."""
        body = (
            "_seed([('alpha','a')])\n"
            "cat, _ = _discover_catalog_and_stats()\n"
            "# Explicitly send no headers / no token.\n"
            "r = client.get(cat)\n"
            + _emit("{'status': r.status_code}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, (
            "public catalog should not require auth, got %s" % res["status"]
        )

    def test_catalog_case_insensitive_title_filter(self):
        """q filter matches titles case-insensitively and adjusts total."""
        body = (
            "_seed([('Alpha One','a'),('beta two','b'),"
            "('the ALPHA cat','c'),('gamma','d')])\n"
            "cat, _ = _discover_catalog_and_stats()\n"
            "r = client.get(cat, params={'q':'alpha','limit':100,'skip':0})\n"
            "b = r.json()\n"
            + _emit("{'status': r.status_code, 'count': b.get('count'), "
                    "'titles': sorted(i.get('title') for i in b.get('data',[]))}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["count"] == 2, (
            "q=alpha should match 2 items (case-insensitive), got %s" % res["count"]
        )
        assert res["titles"] == ["Alpha One", "the ALPHA cat"], res["titles"]

    def test_catalog_pagination_with_filtered_total(self):
        """skip/limit return the right slice while total reflects full filter."""
        body = (
            "_seed([('alpha 1','a'),('alpha 2','b'),('alpha 3','c'),"
            "('beta','d')])\n"
            "cat, _ = _discover_catalog_and_stats()\n"
            "# 3 'alpha' items; page size 2, skip 2 -> exactly one remaining.\n"
            "r = client.get(cat, params={'q':'alpha','limit':2,'skip':2})\n"
            "b = r.json()\n"
            "# also pull the full filtered set to derive expected ordering\n"
            "rf = client.get(cat, params={'q':'alpha','limit':100,'skip':0})\n"
            "bf = rf.json()\n"
            + _emit("{'status': r.status_code, 'page_len': len(b.get('data',[])), "
                    "'count': b.get('count'), "
                    "'full_titles':[i['title'] for i in bf.get('data',[])], "
                    "'page_titles':[i['title'] for i in b.get('data',[])]}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["count"] == 3, (
            "filtered total must stay 3 regardless of paging, got %s" % res["count"]
        )
        assert res["page_len"] == 1, (
            "limit=2 skip=2 over 3 matches must return 1 item, got %s"
            % res["page_len"]
        )
        # The single returned item must be the 3rd of the full filtered ordering.
        assert res["page_titles"][0] == res["full_titles"][2], (
            "paged slice inconsistent with full ordering: page=%s full=%s"
            % (res["page_titles"], res["full_titles"])
        )

    def test_catalog_rejects_invalid_pagination(self):
        """limit=0, limit>100 and skip<0 are rejected with HTTP 422."""
        body = (
            "_seed([('alpha','a')])\n"
            "cat, _ = _discover_catalog_and_stats()\n"
            "r_zero = client.get(cat, params={'limit':0})\n"
            "r_big  = client.get(cat, params={'limit':101})\n"
            "r_neg  = client.get(cat, params={'skip':-1})\n"
            + _emit("{'limit0': r_zero.status_code, "
                    "'limit101': r_big.status_code, 'skipneg': r_neg.status_code}")
        )
        res = _run_driver(body)
        assert res["limit0"] == 422, "limit=0 must be 422, got %s" % res["limit0"]
        assert res["limit101"] == 422, (
            "limit>100 must be 422, got %s" % res["limit101"]
        )
        assert res["skipneg"] == 422, "skip=-1 must be 422, got %s" % res["skipneg"]

    def test_catalog_only_public_fields(self):
        """Returned item objects expose only id/title/description/owner_id."""
        body = (
            "_seed([('alpha only','some desc')])\n"
            "cat, _ = _discover_catalog_and_stats()\n"
            "r = client.get(cat, params={'limit':10})\n"
            "b = r.json()\n"
            "item = b['data'][0] if b.get('data') else {}\n"
            + _emit("{'keys': sorted(item.keys()), 'owner_id': item.get('owner_id'), "
                    "'title': item.get('title')}")
        )
        res = _run_driver(body)
        keys = set(res["keys"])
        allowed = {"id", "title", "description", "owner_id"}
        # owner_id is part of the public shape per the requirement.
        assert keys.issubset(allowed), (
            "catalog item leaked non-public fields: %s" % (keys - allowed)
        )
        # Must not leak any internal/sensitive attribute.
        for forbidden in ("hashed_password", "owner", "is_superuser",
                          "created_at", "is_active", "email"):
            assert forbidden not in keys, (
                "catalog item must not expose '%s'" % forbidden
            )
        assert res["title"] == "alpha only"
        assert res["owner_id"], "owner_id should be present in public shape"

    def test_stats_endpoint_total_and_filtered(self):
        """Stats reports total and q-filtered counts as integers."""
        body = (
            "_seed([('alpha 1','a'),('alpha 2','b'),('beta','c')])\n"
            "_, stats = _discover_catalog_and_stats()\n"
            + "assert stats, 'no stats route discovered'\n"
            "r_all = client.get(stats)\n"
            "r_q   = client.get(stats, params={'q':'alpha'})\n"
            "ba, bq = r_all.json(), r_q.json()\n"
            + _emit("{'all_status': r_all.status_code, 'q_status': r_q.status_code, "
                    "'all_vals': sorted(v for v in ba.values()), "
                    "'q_vals': sorted(v for v in bq.values())}")
        )
        res = _run_driver(body)
        assert res["all_status"] == 200, res
        assert res["q_status"] == 200, res
        # Total of 3 items must appear among the unfiltered stats values.
        assert 3 in res["all_vals"], (
            "stats total should include 3 total items, got %s" % res["all_vals"]
        )
        # The alpha-filtered matching count (2) must appear in q stats.
        assert 2 in res["q_vals"], (
            "stats q=alpha should report 2 matches, got %s" % res["q_vals"]
        )

    def test_stats_consistent_with_catalog(self):
        """Stats matching count for q equals catalog's total for the same q."""
        body = (
            "_seed([('alpha apple','a'),('ALPHA beta','b'),"
            "('gamma','c'),('delta alpha','d'),('epsilon','e')])\n"
            "cat, stats = _discover_catalog_and_stats()\n"
            "assert stats, 'no stats route discovered'\n"
            "rc = client.get(cat, params={'q':'alpha','limit':100})\n"
            "bc = rc.json()\n"
            "rs = client.get(stats, params={'q':'alpha'})\n"
            "bs = rs.json()\n"
            "# catalog filtered total\n"
            "cat_total = bc.get('count')\n"
            "# the stats matching count is whichever integer value equals cat_total\n"
            + _emit("{'cat_total': cat_total, 'cat_len': len(bc.get('data',[])), "
                    "'stats_vals': sorted(int(v) for v in bs.values())}")
        )
        res = _run_driver(body)
        # 3 items contain 'alpha' (case-insensitive substring).
        assert res["cat_total"] == 3, (
            "catalog q=alpha total should be 3, got %s" % res["cat_total"]
        )
        assert res["cat_len"] == 3, res
        assert res["cat_total"] in res["stats_vals"], (
            "stats values %s must contain the catalog filtered total %s"
            % (res["stats_vals"], res["cat_total"])
        )

    def test_existing_owner_scoped_route_intact(self):
        """The original /items/ owner route still requires auth (untouched)."""
        body = (
            "_seed([('alpha','a')])\n"
            "from app.core.config import settings\n"
            "base = settings.API_V1_STR + '/items/'\n"
            "r = client.get(base)\n"  # no auth header
            + _emit("{'status': r.status_code}")
        )
        res = _run_driver(body)
        # Without a token the protected route must NOT return 200.
        assert res["status"] in (401, 403), (
            "existing owner-scoped /items/ must still require auth, got %s"
            % res["status"]
        )

    def test_empty_filter_returns_zero(self):
        """A q that matches nothing yields an empty page and total 0."""
        body = (
            "_seed([('alpha','a'),('beta','b')])\n"
            "cat, stats = _discover_catalog_and_stats()\n"
            "r = client.get(cat, params={'q':'zzznotpresent','limit':100})\n"
            "b = r.json()\n"
            "sres = client.get(stats, params={'q':'zzznotpresent'}) if stats else None\n"
            "sval = sorted(int(v) for v in sres.json().values()) if sres is not None else []\n"
            + _emit("{'status': r.status_code, 'len': len(b.get('data',[])), "
                    "'count': b.get('count'), 'stats_vals': sval}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["len"] == 0, "non-matching q should return 0 items"
        assert res["count"] == 0, "non-matching q total should be 0"
        if res["stats_vals"]:
            assert 0 in res["stats_vals"], (
                "stats for non-matching q should report a 0 match count"
            )
