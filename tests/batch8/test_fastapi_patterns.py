"""
Test for the 'fastapi-patterns' skill (variant ext8) — Reusable Pagination
Dependency Applied to Item Listing.

The task asks the agent to add a single, reusable, *validated* pagination
dependency in `backend/app/api/deps.py` (carrying `skip` and `limit`, with
`skip >= 0` and `1 <= limit <= 100`, out-of-range -> HTTP 422) plus an
importable type alias for it, and to rewire the EXISTING authenticated
item-listing endpoint `GET {API_V1_STR}/items/` to obtain its pagination
through that shared dependency — while keeping the same auth requirement,
owner-scoping, `{data, count}` response shape, and `created_at DESC` ordering.

Verification strategy
---------------------
These tests EXERCISE the real FastAPI app rather than reading source text. The
template is hard-wired to Postgres, so each behavioral (L2) test runs a
self-contained driver under the backend package (via the same interpreter that
runs pytest) that:
  * builds an in-memory SQLite engine and creates all tables,
  * overrides the `get_db` dependency so the app uses that SQLite session,
  * seeds a known owner + a second unrelated user + a known set of items,
  * mints a REAL JWT via app.core.security.create_access_token for the owner,
  * calls the authenticated /items/ endpoint with that bearer token,
  * prints a JSON result that this test deeply validates.

Because the listing route is authenticated, the tests verify the route still
*requires* auth (no token -> 401/403), still scopes to the caller's items, and
preserves created_at-descending ordering. Pagination bounds are exercised end
to end: `limit=0`, `limit=101`, and `skip=-1` must yield 422. A naive solution
that inlines bare `skip: int = 0, limit: int = 100` (no validation), drops the
auth/owner-scoping, or changes the response shape/ordering will FAIL.

The pagination DEPENDENCY itself is also unit-tested directly: it is discovered
from `app.api.deps` (a callable whose validated query params are skip+limit) and
invoked through a throwaway endpoint to confirm the 422 bounds live in the
shared dependency, not merely re-declared inline on the route.
"""

import json
import os
import re
import subprocess
import sys
import textwrap

import pytest


REPO_DIR = "/workspace/full-stack-fastapi-template"
BACKEND_DIR = os.path.join(REPO_DIR, "backend")
DEPS_PATH = os.path.join(BACKEND_DIR, "app", "api", "deps.py")
ITEMS_PATH = os.path.join(BACKEND_DIR, "app", "api", "routes", "items.py")


# --------------------------------------------------------------------------- #
# Shared driver scaffolding
# --------------------------------------------------------------------------- #

# Preamble: make `app` importable, satisfy required Settings env vars, swap the
# global engine for SQLite, create tables, and override get_db. Provides helpers
# to seed users/items and to mint a real bearer token for a seeded user.
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
    import app.api.deps as deps_mod
    deps_mod.engine = _sqlite
except Exception:
    pass

from app.main import app
from app.api.deps import get_db
from app.core.config import settings
from app.core.security import create_access_token

ITEMS_URL = settings.API_V1_STR + "/items/"

def _get_db_override():
    with Session(_sqlite) as s:
        yield s

app.dependency_overrides[get_db] = _get_db_override

OWNER_ID = uuid.uuid4()
OTHER_ID = uuid.uuid4()

def _make_user(s, uid, email, superuser=False):
    u = models.User(
        id=uid,
        email=email,
        hashed_password="x",
        is_active=True,
        is_superuser=superuser,
    )
    s.add(u)
    s.commit()
    return u

def _seed(owner_specs, other_specs=None):
    """owner_specs/other_specs: list of (title, description).

    Inserts items in list order so SQLite autoincrement / created_at default
    ordering is deterministic. Returns list of created owner item dicts in
    INSERTION order.
    """
    other_specs = other_specs or []
    created = []
    with Session(_sqlite) as s:
        _make_user(s, OWNER_ID, "owner@example.com")
        if other_specs:
            _make_user(s, OTHER_ID, "other@example.com")
        for title, desc in owner_specs:
            it = models.Item(title=title, description=desc, owner_id=OWNER_ID)
            s.add(it)
            s.commit()
            s.refresh(it)
            created.append({"id": str(it.id), "title": it.title,
                            "description": it.description})
        for title, desc in other_specs:
            it = models.Item(title=title, description=desc, owner_id=OTHER_ID)
            s.add(it)
            s.commit()
            s.refresh(it)
    return created

def _owner_headers():
    token = create_access_token(OWNER_ID, expires_delta=timedelta(minutes=60))
    return {"Authorization": "Bearer " + token}

client = TestClient(app)
'''


def _run_driver(body: str, timeout: int = 300):
    """Write a driver .py under backend/ and run it with this interpreter."""
    if not os.path.isdir(BACKEND_DIR):
        pytest.fail("backend/ directory not found at %s" % BACKEND_DIR)

    driver_path = os.path.join(BACKEND_DIR, "_skilltest_driver_ext8.py")
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
    """Verify the reusable pagination dependency applied to /items/ listing."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist and are minimally well-formed.
    # ------------------------------------------------------------------ #

    def test_deps_file_present(self):
        """backend/app/api/deps.py must exist (the shared dependency lives here)."""
        assert os.path.isfile(DEPS_PATH), "deps.py missing at %s" % DEPS_PATH

    def test_items_route_file_present(self):
        """backend/app/api/routes/items.py must exist."""
        assert os.path.isfile(ITEMS_PATH), "items.py route module missing"

    def test_app_imports_and_items_route_registered(self):
        """The app imports cleanly and still exposes GET on the items router."""
        body = (
            "schema = app.openapi()\n"
            "paths = [p for p, m in schema['paths'].items()\n"
            "         if 'items' in m.get('get', {}).get('tags', [])]\n"
            "# The listing endpoint must be present and declare skip+limit query params.\n"
            "listing = settings.API_V1_STR + '/items/'\n"
            "params = [q.get('name') for q in\n"
            "          schema['paths'].get(listing, {}).get('get', {}).get('parameters', [])]\n"
            + _emit("{'item_get_paths': paths, 'listing_present': listing in schema['paths'], "
                    "'listing_params': params}")
        )
        res = _run_driver(body)
        assert len(res["item_get_paths"]) >= 1, (
            "no GET routes tagged 'items' found in OpenAPI schema"
        )
        assert res["listing_present"], "GET /items/ listing endpoint missing"
        # The shared dependency must still surface skip + limit as query params.
        params = set(res["listing_params"])
        assert "skip" in params, "listing endpoint must expose a 'skip' query param"
        assert "limit" in params, "listing endpoint must expose a 'limit' query param"

    def test_reusable_pagination_symbol_exposed(self):
        """A reusable pagination dependency + type alias is importable from deps.

        We discover, from app.api.deps, a *callable* dependency whose resolved
        query parameters are exactly {skip, limit} (a pagination dependency),
        and at least one Annotated type alias built on Depends() referencing it.
        This proves a single shared dependency exists rather than the route
        re-declaring skip/limit inline.
        """
        body = (
            "import inspect, typing\n"
            "import app.api.deps as d\n"
            "from fastapi import Depends\n"
            "# Find dependency callables whose signature params are a subset of {skip,limit}\n"
            "dep_callables = []\n"
            "for name in dir(d):\n"
            "    obj = getattr(d, name)\n"
            "    if not callable(obj) or inspect.isclass(obj):\n"
            "        # classes are allowed as Pydantic-style param models; handle below\n"
            "        pass\n"
            "    try:\n"
            "        sig = inspect.signature(obj)\n"
            "    except (TypeError, ValueError):\n"
            "        continue\n"
            "    pnames = set(sig.parameters.keys())\n"
            "    if pnames and pnames <= {'skip', 'limit'} and {'skip','limit'} & pnames:\n"
            "        dep_callables.append(name)\n"
            "# Find Annotated aliases that wire a Depends() (the reusable type alias).\n"
            "alias_names = []\n"
            "for name in dir(d):\n"
            "    obj = getattr(d, name)\n"
            "    if typing.get_origin(obj) is not None and hasattr(obj, '__metadata__'):\n"
            "        meta = getattr(obj, '__metadata__', ())\n"
            "        if any(isinstance(m, type(Depends(lambda: None))) for m in meta):\n"
            "            alias_names.append(name)\n"
            + _emit("{'dep_callables': dep_callables, 'alias_names': alias_names}")
        )
        res = _run_driver(body)
        assert res["dep_callables"], (
            "no reusable pagination dependency (callable resolving skip/limit) "
            "found in app.api.deps"
        )
        assert res["alias_names"], (
            "no Annotated[...] Depends type alias exported from app.api.deps"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavioral validation of the authenticated listing.
    # ------------------------------------------------------------------ #

    def test_listing_requires_auth(self):
        """GET /items/ must still reject an unauthenticated request (401/403)."""
        body = (
            "_seed([('alpha','a')])\n"
            "r = client.get(ITEMS_URL)\n"  # no Authorization header
            + _emit("{'status': r.status_code}")
        )
        res = _run_driver(body)
        assert res["status"] in (401, 403), (
            "authenticated /items/ must require auth, got %s" % res["status"]
        )

    def test_listing_returns_owner_items_and_count(self):
        """Authenticated listing returns the caller's items with {data,count}."""
        body = (
            "_seed([('alpha one','a'),('beta two','b'),('alpha three','c')])\n"
            "r = client.get(ITEMS_URL, headers=_owner_headers(),\n"
            "               params={'skip':0,'limit':100})\n"
            "b = r.json()\n"
            + _emit("{'status': r.status_code, 'len': len(b.get('data',[])), "
                    "'count': b.get('count'), 'keys': sorted(b.keys()), "
                    "'titles': sorted(i.get('title') for i in b.get('data',[]))}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert set(res["keys"]) >= {"data", "count"}, (
            "response must keep {data, count} shape, got keys %s" % res["keys"]
        )
        assert res["len"] == 3, "expected 3 owner items, got %s" % res["len"]
        assert res["count"] == 3, "expected total count 3, got %s" % res["count"]
        assert res["titles"] == ["alpha one", "alpha three", "beta two"]

    def test_listing_is_owner_scoped(self):
        """Listing returns ONLY the caller's items, not another user's."""
        body = (
            "_seed([('mine 1','a'),('mine 2','b')],\n"
            "      other_specs=[('theirs 1','x'),('theirs 2','y'),('theirs 3','z')])\n"
            "r = client.get(ITEMS_URL, headers=_owner_headers(),\n"
            "               params={'skip':0,'limit':100})\n"
            "b = r.json()\n"
            + _emit("{'status': r.status_code, 'count': b.get('count'), "
                    "'titles': sorted(i.get('title') for i in b.get('data',[]))}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        # Only the owner's two items must be visible; the other user's must not.
        assert res["count"] == 2, (
            "owner-scoping broken: count should be 2, got %s" % res["count"]
        )
        assert res["titles"] == ["mine 1", "mine 2"], (
            "listing leaked another user's items: %s" % res["titles"]
        )

    def test_listing_preserves_created_at_desc_ordering(self):
        """Items are ordered by created_at DESC (most recent insert first)."""
        body = (
            "# Force distinct, increasing created_at so DESC order is unambiguous.\n"
            "import uuid as _uuid\n"
            "from datetime import datetime, timedelta\n"
            "from sqlmodel import Session as _S\n"
            "with _S(_sqlite) as s:\n"
            "    _make_user(s, OWNER_ID, 'owner@example.com')\n"
            "    base = datetime(2020, 1, 1, 0, 0, 0)\n"
            "    for i, title in enumerate(['first','second','third','fourth']):\n"
            "        it = models.Item(title=title, description='d', owner_id=OWNER_ID,\n"
            "                          created_at=base + timedelta(days=i))\n"
            "        s.add(it); s.commit()\n"
            "r = client.get(ITEMS_URL, headers=_owner_headers(),\n"
            "               params={'skip':0,'limit':100})\n"
            "b = r.json()\n"
            + _emit("{'status': r.status_code, "
                    "'titles': [i.get('title') for i in b.get('data',[])]}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        # Newest (fourth) first -> created_at DESC.
        assert res["titles"] == ["fourth", "third", "second", "first"], (
            "ordering must be created_at DESC, got %s" % res["titles"]
        )

    def test_listing_pagination_slice(self):
        """skip/limit return the correct slice of the owner-scoped ordered set."""
        body = (
            "import uuid as _uuid\n"
            "from datetime import datetime, timedelta\n"
            "from sqlmodel import Session as _S\n"
            "with _S(_sqlite) as s:\n"
            "    _make_user(s, OWNER_ID, 'owner@example.com')\n"
            "    base = datetime(2020, 1, 1)\n"
            "    for i, title in enumerate(['t0','t1','t2','t3','t4']):\n"
            "        it = models.Item(title=title, description='d', owner_id=OWNER_ID,\n"
            "                          created_at=base + timedelta(days=i))\n"
            "        s.add(it); s.commit()\n"
            "full = client.get(ITEMS_URL, headers=_owner_headers(),\n"
            "                  params={'skip':0,'limit':100}).json()\n"
            "page = client.get(ITEMS_URL, headers=_owner_headers(),\n"
            "                  params={'skip':1,'limit':2}).json()\n"
            + _emit("{'full': [i['title'] for i in full.get('data',[])], "
                    "'page': [i['title'] for i in page.get('data',[])], "
                    "'count': page.get('count')}")
        )
        res = _run_driver(body)
        # Total count must reflect the whole owner set, independent of paging.
        assert res["count"] == 5, (
            "count must be the full owner total (5), got %s" % res["count"]
        )
        assert len(res["page"]) == 2, (
            "skip=1 limit=2 must return exactly 2 items, got %s" % res["page"]
        )
        # The page must be the slice [1:3] of the full ordered listing.
        assert res["page"] == res["full"][1:3], (
            "paged slice inconsistent with full ordering: page=%s full=%s"
            % (res["page"], res["full"])
        )

    def test_listing_rejects_invalid_pagination(self):
        """limit=0, limit>100 and skip<0 are rejected with HTTP 422."""
        body = (
            "_seed([('alpha','a')])\n"
            "h = _owner_headers()\n"
            "r_zero = client.get(ITEMS_URL, headers=h, params={'limit':0})\n"
            "r_big  = client.get(ITEMS_URL, headers=h, params={'limit':101})\n"
            "r_neg  = client.get(ITEMS_URL, headers=h, params={'skip':-1})\n"
            + _emit("{'limit0': r_zero.status_code, "
                    "'limit101': r_big.status_code, 'skipneg': r_neg.status_code}")
        )
        res = _run_driver(body)
        assert res["limit0"] == 422, "limit=0 must be 422, got %s" % res["limit0"]
        assert res["limit101"] == 422, (
            "limit>100 must be 422, got %s" % res["limit101"]
        )
        assert res["skipneg"] == 422, "skip=-1 must be 422, got %s" % res["skipneg"]

    def test_listing_accepts_boundary_pagination(self):
        """Boundary values skip=0, limit=1 and limit=100 are accepted (200)."""
        body = (
            "_seed([('alpha','a'),('beta','b')])\n"
            "h = _owner_headers()\n"
            "r_min = client.get(ITEMS_URL, headers=h, params={'skip':0,'limit':1})\n"
            "r_max = client.get(ITEMS_URL, headers=h, params={'skip':0,'limit':100})\n"
            "bmin = r_min.json()\n"
            + _emit("{'min_status': r_min.status_code, 'max_status': r_max.status_code, "
                    "'min_len': len(bmin.get('data',[])), 'min_count': bmin.get('count')}")
        )
        res = _run_driver(body)
        assert res["min_status"] == 200, (
            "limit=1 must be accepted, got %s" % res["min_status"]
        )
        assert res["max_status"] == 200, (
            "limit=100 must be accepted, got %s" % res["max_status"]
        )
        # limit=1 returns a single item but reports the full total of 2.
        assert res["min_len"] == 1, "limit=1 must cap page to 1, got %s" % res["min_len"]
        assert res["min_count"] == 2, (
            "count must stay full total (2) regardless of limit, got %s"
            % res["min_count"]
        )

    def test_default_pagination_no_params(self):
        """No query parameters still works and returns the caller's items."""
        body = (
            "_seed([('alpha','a'),('beta','b'),('gamma','c')])\n"
            "r = client.get(ITEMS_URL, headers=_owner_headers())\n"
            "b = r.json()\n"
            + _emit("{'status': r.status_code, 'len': len(b.get('data',[])), "
                    "'count': b.get('count')}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["len"] == 3, "default listing should return all 3, got %s" % res["len"]
        assert res["count"] == 3, "default count should be 3, got %s" % res["count"]

    def test_pagination_dependency_enforces_bounds_in_isolation(self):
        """The reusable dependency itself enforces bounds, not the route inline.

        Mount a throwaway endpoint that depends on the discovered pagination
        type alias / dependency from app.api.deps. Calling it with out-of-range
        skip/limit must 422 even though the route is brand new — proving the
        validation lives in the shared dependency, reusable by any endpoint.
        A naive impl that only validates inside read_items would fail here.
        """
        body = (
            "import inspect, typing\n"
            "from fastapi import APIRouter, FastAPI, Depends\n"
            "from fastapi.testclient import TestClient as _TC\n"
            "import app.api.deps as d\n"
            "from fastapi import Depends as _Dep\n"
            "DepType = type(_Dep(lambda: None))\n"
            "# Prefer an Annotated alias that wires Depends(); else the raw callable.\n"
            "chosen = None\n"
            "for name in dir(d):\n"
            "    obj = getattr(d, name)\n"
            "    if typing.get_origin(obj) is not None and hasattr(obj, '__metadata__'):\n"
            "        if any(isinstance(m, DepType) for m in getattr(obj,'__metadata__',())):\n"
            "            # confirm its underlying dependency resolves skip/limit\n"
            "            dep = next((m.dependency for m in obj.__metadata__ if isinstance(m, DepType)), None)\n"
            "            try:\n"
            "                pn = set(inspect.signature(dep).parameters.keys()) if dep else set()\n"
            "            except (TypeError, ValueError):\n"
            "                pn = set()\n"
            "            if pn and pn <= {'skip','limit'} and {'skip','limit'} & pn:\n"
            "                chosen = ('alias', name); break\n"
            "if chosen is None:\n"
            "    for name in dir(d):\n"
            "        obj = getattr(d, name)\n"
            "        try:\n"
            "            pn = set(inspect.signature(obj).parameters.keys())\n"
            "        except (TypeError, ValueError):\n"
            "            continue\n"
            "        if pn and pn <= {'skip','limit'} and {'skip','limit'} & pn:\n"
            "            chosen = ('callable', name); break\n"
            "assert chosen, 'could not locate reusable pagination dependency in deps'\n"
            "kind, nm = chosen\n"
            "obj = getattr(d, nm)\n"
            "probe = FastAPI()\n"
            "if kind == 'alias':\n"
            "    def _ep(pg: obj):\n"
            "        return {'ok': True}\n"
            "else:\n"
            "    def _ep(pg=Depends(obj)):\n"
            "        return {'ok': True}\n"
            "probe.add_api_route('/probe', _ep, methods=['GET'])\n"
            "pc = _TC(probe)\n"
            "ok   = pc.get('/probe', params={'skip':0,'limit':10})\n"
            "z    = pc.get('/probe', params={'limit':0})\n"
            "big  = pc.get('/probe', params={'limit':101})\n"
            "neg  = pc.get('/probe', params={'skip':-1})\n"
            + _emit("{'chosen': nm, 'ok': ok.status_code, 'limit0': z.status_code, "
                    "'limit101': big.status_code, 'skipneg': neg.status_code}")
        )
        res = _run_driver(body)
        assert res["ok"] == 200, (
            "valid pagination through the shared dependency must pass, got %s"
            % res["ok"]
        )
        assert res["limit0"] == 422, (
            "shared dependency must reject limit=0, got %s" % res["limit0"]
        )
        assert res["limit101"] == 422, (
            "shared dependency must reject limit=101, got %s" % res["limit101"]
        )
        assert res["skipneg"] == 422, (
            "shared dependency must reject skip=-1, got %s" % res["skipneg"]
        )

    def test_route_consumes_shared_pagination_dependency(self):
        """read_items must obtain pagination from the shared deps symbol.

        The route signature must NOT re-declare bare `skip`/`limit` as plain
        int parameters; instead it should annotate a single pagination param
        whose type/default references the shared dependency from app.api.deps.
        We inspect the actual function object (not source text) to confirm the
        route delegates to the shared dependency rather than inlining it.
        """
        body = (
            "import inspect, typing\n"
            "from fastapi import Depends as _Dep\n"
            "DepType = type(_Dep(lambda: None))\n"
            "from app.api.routes import items as it\n"
            "import app.api.deps as d\n"
            "# Resolve the listing handler (the GET '/' on the items router).\n"
            "fn = None\n"
            "for r in it.router.routes:\n"
            "    if getattr(r, 'path', None) == '/' and 'GET' in getattr(r, 'methods', set()):\n"
            "        fn = r.endpoint\n"
            "assert fn is not None, 'could not find GET / listing handler'\n"
            "sig = inspect.signature(fn)\n"
            "param_names = list(sig.parameters.keys())\n"
            "# Does any parameter wire a Depends() (Annotated metadata or default)?\n"
            "uses_dep = False\n"
            "for p in sig.parameters.values():\n"
            "    if isinstance(p.default, DepType):\n"
            "        uses_dep = True\n"
            "    ann = p.annotation\n"
            "    if typing.get_origin(ann) is not None and hasattr(ann, '__metadata__'):\n"
            "        if any(isinstance(m, DepType) for m in ann.__metadata__):\n"
            "            uses_dep = True\n"
            "# A plain inline impl exposes BOTH skip and limit as top-level fn params.\n"
            "inline_both = ('skip' in param_names and 'limit' in param_names)\n"
            + _emit("{'param_names': param_names, 'uses_dep': uses_dep, "
                    "'inline_both': inline_both}")
        )
        res = _run_driver(body)
        # The handler must declare a Depends-wired pagination parameter ...
        assert res["uses_dep"], (
            "read_items does not wire any Depends() pagination param; signature=%s"
            % res["param_names"]
        )
        # ... and must NOT keep bare inline skip+limit ints on the signature.
        assert not res["inline_both"], (
            "read_items still declares inline skip+limit instead of the shared "
            "pagination dependency; signature=%s" % res["param_names"]
        )
