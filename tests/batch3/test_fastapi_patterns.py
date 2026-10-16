"""
Test for the 'fastapi-patterns' skill — Admin-Only Maintenance Sub-Router (ext3).

The task asks the agent to add a NEW router to the full-stack-fastapi-template,
mounted under the `/admin` prefix with the `admin` tag, on which every route is
gated by a single SHARED active-superuser guard (not a per-route repetition).
The router must expose two GET endpoints:

  * a "counts" route returning the total number of users and the total number of
    items as a small structured object with named INTEGER fields, and
  * an "orphan-items" route returning the number of items whose owner no longer
    exists in the users table (0 in normal operation, but computed correctly).

Access control:
  * a superuser may call the routes,
  * a normal authenticated user receives HTTP 403,
  * an unauthenticated caller receives HTTP 401.

VERIFICATION STRATEGY
Because the template is hard-wired to Postgres, we cannot use a live database.
Each behavioral (L2) test runs a self-contained driver under the backend package
(same interpreter that runs pytest) that:
  * builds an in-memory SQLite engine and creates all tables,
  * overrides the `get_db` dependency so the app uses that SQLite session,
  * seeds a known superuser, a known normal user, and a known set of items,
  * mints real HS256 JWTs (via app.core.security.create_access_token) so the
    app's own auth/superuser dependency chain runs unmodified,
  * calls the admin endpoints with the appropriate (or absent) bearer token,
  * prints a JSON result that this test deeply validates.

The two admin routes are DISCOVERED dynamically from the OpenAPI schema (GET
routes tagged 'admin' under the /admin prefix), so the exact final path the
agent chose (e.g. /admin/counts vs /admin/stats) does not matter; the routes
are distinguished by their response shape exercised live with a superuser token.

A naive solution will fail: hardcoding counts (ignoring seeded rows), leaking
extra fields, applying the guard per-route so a future/other route is
unprotected, skipping the orphan computation, or returning non-integers — each
is caught by a concrete behavioral assertion below.
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
# global engine for SQLite, create tables, and expose seed + auth helpers.
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

client = TestClient(app)

# ------------------------------------------------------------------ #
# Seed helpers
# ------------------------------------------------------------------ #
SUPERUSER_ID = uuid.uuid4()
NORMALUSER_ID = uuid.uuid4()

def _seed(n_extra_users=0, item_specs=None, orphan_titles=None):
    """Seed a superuser + a normal user (+ extra normal users) and items.

    item_specs:    list of titles owned by the normal user (valid owner).
    orphan_titles: list of titles whose owner_id points at a user we then
                   delete, producing genuine orphan rows. Returns a dict of
                   the ground-truth counts the endpoints must reproduce.
    Returns: {'n_users': int, 'n_items': int, 'n_orphans': int}
    """
    item_specs = item_specs or []
    orphan_titles = orphan_titles or []
    with Session(_sqlite) as s:
        su = models.User(
            id=SUPERUSER_ID,
            email="admin@example.com",
            hashed_password="x",
            is_active=True,
            is_superuser=True,
        )
        nu = models.User(
            id=NORMALUSER_ID,
            email="user@example.com",
            hashed_password="x",
            is_active=True,
            is_superuser=False,
        )
        s.add(su)
        s.add(nu)
        for i in range(n_extra_users):
            s.add(models.User(
                id=uuid.uuid4(),
                email="extra%d@example.com" % i,
                hashed_password="x",
                is_active=True,
                is_superuser=False,
            ))
        s.commit()

        # Valid items owned by the normal user.
        for title in item_specs:
            s.add(models.Item(title=title, description="d",
                              owner_id=NORMALUSER_ID))
        s.commit()

        n_orphans = 0
        if orphan_titles:
            # Create a soon-to-be-deleted owner, attach items, then delete the
            # owner row directly (bypassing cascade) to leave true orphans.
            ghost_id = uuid.uuid4()
            ghost = models.User(
                id=ghost_id,
                email="ghost@example.com",
                hashed_password="x",
                is_active=True,
                is_superuser=False,
            )
            s.add(ghost)
            s.commit()
            for title in orphan_titles:
                s.add(models.Item(title=title, description="d",
                                  owner_id=ghost_id))
            s.commit()
            # Remove the owner row with a raw delete so FK cascade does not
            # also wipe the items — leaving them genuinely orphaned.
            from sqlalchemy import text
            s.exec(text("DELETE FROM user WHERE id = :i").bindparams(i=str(ghost_id)))
            s.commit()
            n_orphans = len(orphan_titles)

    # Count surviving users / items straight from the DB for ground truth.
    with Session(_sqlite) as s:
        from sqlmodel import select, func
        n_users = s.exec(select(func.count()).select_from(models.User)).one()
        n_items = s.exec(select(func.count()).select_from(models.Item)).one()
    return {"n_users": int(n_users), "n_items": int(n_items),
            "n_orphans": int(n_orphans)}


def _token(user_id):
    """Mint a real access token for the given user id (HS256, app secret)."""
    return security.create_access_token(
        user_id, expires_delta=timedelta(minutes=60)
    )

def _auth(user_id):
    return {"Authorization": "Bearer %s" % _token(user_id)}

SUPER_HDR = property  # placeholder, replaced below by functions

def super_headers():
    return _auth(SUPERUSER_ID)

def normal_headers():
    return _auth(NORMALUSER_ID)

# ------------------------------------------------------------------ #
# Route discovery
# ------------------------------------------------------------------ #
def _admin_get_paths():
    """All GET paths whose route is tagged 'admin' in the OpenAPI schema."""
    schema = app.openapi()
    paths = []
    for path, methods in schema.get("paths", {}).items():
        spec = methods.get("get")
        if not spec:
            continue
        if "admin" in spec.get("tags", []):
            paths.append(path)
    return paths

def _discover_counts_and_orphan():
    """Return (counts_path, orphan_path) among the admin GET routes.

    Both are identified live with a superuser token after seeding 1 user-only
    state: the 'counts' route returns an object with >=2 integer fields whose
    values reproduce the seeded user/item totals; the 'orphan' route returns a
    single-integer-bearing object. To disambiguate without depending on naming,
    we seed a state where (#users, #items) are DISTINCT from #orphans and from
    each other, then match by value. Callers should seed FIRST, then call this.
    """
    candidates = _admin_get_paths()
    counts_path = None
    orphan_path = None
    hdr = super_headers()
    bodies = {}
    for path in candidates:
        if "{" in path:
            continue
        try:
            r = client.get(path, headers=hdr)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        b = r.json()
        if not isinstance(b, dict):
            continue
        ints = [v for v in b.values() if isinstance(v, bool) is False
                and isinstance(v, int)]
        bodies[path] = (b, ints)
    return candidates, bodies
'''


def _run_driver(body: str, timeout: int = 300):
    """Write a driver .py under backend/ and run it with this interpreter.

    Runs with cwd=backend so `app` is importable. Returns parsed JSON printed
    by the driver between the RESULT markers.
    """
    if not os.path.isdir(BACKEND_DIR):
        pytest.fail("backend/ directory not found at %s" % BACKEND_DIR)

    driver_path = os.path.join(BACKEND_DIR, "_skilltest_driver_admin.py")
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
    """Verify the admin-only maintenance sub-router (counts + orphan-items)."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist and are minimally well-formed.
    # ------------------------------------------------------------------ #

    def test_admin_route_file_present(self):
        """backend/app/api/routes/admin.py must exist (the new router module)."""
        p = os.path.join(BACKEND_DIR, "app", "api", "routes", "admin.py")
        assert os.path.isfile(p), "admin.py route module missing"

    def test_app_imports_and_admin_router_registered(self):
        """The app imports cleanly and exposes at least one GET admin route."""
        body = (
            "paths = _admin_get_paths()\n"
            + _emit("{'admin_get_paths': paths}")
        )
        res = _run_driver(body)
        assert len(res["admin_get_paths"]) >= 1, (
            "no GET routes tagged 'admin' found in OpenAPI schema; the new "
            "router does not appear registered"
        )

    def test_admin_routes_mounted_under_admin_prefix(self):
        """Every admin-tagged GET route must live under the /admin prefix."""
        body = (
            "paths = _admin_get_paths()\n"
            + _emit("{'admin_get_paths': paths}")
        )
        res = _run_driver(body)
        paths = res["admin_get_paths"]
        assert paths, "no admin GET routes discovered"
        for p in paths:
            assert "/admin" in p, (
                "admin route %r is not mounted under the /admin prefix" % p
            )

    def test_two_distinct_admin_routes_exist(self):
        """The router exposes at least two distinct non-parametrized GET routes."""
        body = (
            "paths = [p for p in _admin_get_paths() if '{' not in p]\n"
            + _emit("{'paths': sorted(set(paths))}")
        )
        res = _run_driver(body)
        assert len(res["paths"]) >= 2, (
            "expected at least two distinct admin GET routes (counts + "
            "orphan-items), found: %s" % res["paths"]
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavioral validation of access control + values.
    # ------------------------------------------------------------------ #

    def test_unauthenticated_requests_get_401(self):
        """Every admin GET route must reject an unauthenticated caller with 401."""
        body = (
            "_seed(n_extra_users=1, item_specs=['a','b'])\n"
            "paths = [p for p in _admin_get_paths() if '{' not in p]\n"
            "codes = {p: client.get(p).status_code for p in paths}\n"
            + _emit("{'codes': codes}")
        )
        res = _run_driver(body)
        assert res["codes"], "no admin routes to probe"
        for path, code in res["codes"].items():
            assert code == 401, (
                "admin route %s must return 401 for unauthenticated caller, "
                "got %s" % (path, code)
            )

    def test_normal_user_gets_403(self):
        """Every admin GET route must reject a normal authenticated user with 403."""
        body = (
            "_seed(n_extra_users=1, item_specs=['a','b'])\n"
            "paths = [p for p in _admin_get_paths() if '{' not in p]\n"
            "hdr = normal_headers()\n"
            "codes = {p: client.get(p, headers=hdr).status_code for p in paths}\n"
            + _emit("{'codes': codes}")
        )
        res = _run_driver(body)
        assert res["codes"], "no admin routes to probe"
        for path, code in res["codes"].items():
            assert code == 403, (
                "admin route %s must return 403 for a normal user, got %s"
                % (path, code)
            )

    def test_superuser_can_access_all_admin_routes(self):
        """A superuser must be able to reach every admin GET route (200)."""
        body = (
            "_seed(n_extra_users=2, item_specs=['a','b','c'])\n"
            "paths = [p for p in _admin_get_paths() if '{' not in p]\n"
            "hdr = super_headers()\n"
            "codes = {p: client.get(p, headers=hdr).status_code for p in paths}\n"
            + _emit("{'codes': codes}")
        )
        res = _run_driver(body)
        assert res["codes"], "no admin routes to probe"
        for path, code in res["codes"].items():
            assert code == 200, (
                "superuser must reach admin route %s (200), got %s"
                % (path, code)
            )

    def test_counts_route_matches_seeded_user_and_item_totals(self):
        """The counts route reports the EXACT seeded user and item totals."""
        body = (
            # 2 base users (super+normal) + 3 extra = 5 users; 4 items.
            "truth = _seed(n_extra_users=3, item_specs=['i1','i2','i3','i4'])\n"
            "hdr = super_headers()\n"
            "paths = [p for p in _admin_get_paths() if '{' not in p]\n"
            "found = None\n"
            "for p in paths:\n"
            "    r = client.get(p, headers=hdr)\n"
            "    if r.status_code != 200:\n"
            "        continue\n"
            "    b = r.json()\n"
            "    if not isinstance(b, dict):\n"
            "        continue\n"
            "    vals = [v for v in b.values() if isinstance(v, bool) is False and isinstance(v, int)]\n"
            "    # counts route exposes >=2 integer fields covering users & items\n"
            "    if truth['n_users'] in vals and truth['n_items'] in vals and len(b) >= 2:\n"
            "        found = b\n"
            "        break\n"
            + _emit("{'truth': truth, 'found': found}")
        )
        res = _run_driver(body)
        assert res["truth"]["n_users"] == 5, res["truth"]
        assert res["truth"]["n_items"] == 4, res["truth"]
        assert res["found"] is not None, (
            "no admin route returned an object whose integer fields reproduce "
            "the seeded user total (5) AND item total (4); a hardcoded or "
            "stub counts route fails here"
        )
        # The counts object must carry both true values as named integer fields.
        vals = [v for v in res["found"].values()
                if isinstance(v, bool) is False and isinstance(v, int)]
        assert 5 in vals and 4 in vals, res["found"]

    def test_counts_fields_are_named_integers_only(self):
        """Counts response has only named integer fields (no extra/leaked data)."""
        body = (
            "truth = _seed(n_extra_users=1, item_specs=['i1','i2'])\n"
            "hdr = super_headers()\n"
            "paths = [p for p in _admin_get_paths() if '{' not in p]\n"
            "found = None\n"
            "for p in paths:\n"
            "    r = client.get(p, headers=hdr)\n"
            "    if r.status_code != 200:\n"
            "        continue\n"
            "    b = r.json()\n"
            "    if not isinstance(b, dict):\n"
            "        continue\n"
            "    vals = [v for v in b.values() if isinstance(v, bool) is False and isinstance(v, int)]\n"
            "    if truth['n_users'] in vals and truth['n_items'] in vals and len(b) >= 2:\n"
            "        found = b\n"
            "        break\n"
            + _emit("{'truth': truth, 'found': found}")
        )
        res = _run_driver(body)
        b = res["found"]
        assert b is not None, "counts route not found / values incorrect"
        # Every field must be a plain integer (not bool, not nested/extra data).
        for k, v in b.items():
            assert isinstance(v, int) and not isinstance(v, bool), (
                "counts field %r is not a plain integer: %r" % (k, v)
            )
            assert isinstance(k, str) and k, "counts field name must be a non-empty string"
        # No string/list/dict payloads sneaking in.
        assert all(isinstance(v, int) for v in b.values()), (
            "counts response leaked non-integer data: %s" % b
        )

    def test_counts_reflects_changes_not_hardcoded(self):
        """Different seed sizes yield different counts — values are computed."""
        def probe(extra_users, items):
            return (
                "truth = _seed(n_extra_users=%d, item_specs=%r)\n" % (extra_users, items)
                + "hdr = super_headers()\n"
                "paths = [p for p in _admin_get_paths() if '{' not in p]\n"
                "found = None\n"
                "for p in paths:\n"
                "    r = client.get(p, headers=hdr)\n"
                "    if r.status_code != 200:\n"
                "        continue\n"
                "    b = r.json()\n"
                "    if not isinstance(b, dict):\n"
                "        continue\n"
                "    vals = [v for v in b.values() if isinstance(v, bool) is False and isinstance(v, int)]\n"
                "    if truth['n_users'] in vals and truth['n_items'] in vals and len(b) >= 2:\n"
                "        found = b\n"
                "        break\n"
                + _emit("{'truth': truth, 'found': found}")
            )
        small = _run_driver(probe(0, ["x"]))            # 2 users, 1 item
        large = _run_driver(probe(4, ["a", "b", "c"]))  # 6 users, 3 items
        assert small["found"] is not None and large["found"] is not None, (
            "counts route did not resolve for both seed sizes"
        )
        small_vals = sorted(v for v in small["found"].values()
                            if isinstance(v, bool) is False and isinstance(v, int))
        large_vals = sorted(v for v in large["found"].values()
                            if isinstance(v, bool) is False and isinstance(v, int))
        assert 2 in small_vals and 1 in small_vals, small["found"]
        assert 6 in large_vals and 3 in large_vals, large["found"]
        assert small_vals != large_vals, (
            "counts identical across different seeds — values appear hardcoded"
        )

    def test_orphan_items_zero_in_normal_operation(self):
        """With all items having valid owners, the orphan route reports 0."""
        body = (
            "truth = _seed(n_extra_users=1, item_specs=['a','b','c'])\n"
            "hdr = super_headers()\n"
            "paths = [p for p in _admin_get_paths() if '{' not in p]\n"
            "results = []\n"
            "for p in paths:\n"
            "    r = client.get(p, headers=hdr)\n"
            "    if r.status_code != 200:\n"
            "        continue\n"
            "    b = r.json()\n"
            "    if isinstance(b, dict):\n"
            "        ints = [v for v in b.values() if isinstance(v, bool) is False and isinstance(v, int)]\n"
            "        results.append({'path': p, 'body': b, 'ints': ints})\n"
            + _emit("{'truth': truth, 'results': results}")
        )
        res = _run_driver(body)
        assert res["truth"]["n_orphans"] == 0, res["truth"]
        # There must exist an admin route whose integer field(s) are exactly {0}
        # (the orphan route) — i.e. a route reporting 0 orphans in this state.
        zero_route = [
            r for r in res["results"]
            if r["ints"] and all(v == 0 for v in r["ints"])
        ]
        assert zero_route, (
            "no admin route reported 0 (the orphan-items count) when all items "
            "have valid owners; results=%s" % res["results"]
        )

    def test_orphan_items_counts_true_orphans(self):
        """With 2 genuine orphan items, the orphan route reports exactly 2."""
        body = (
            # 3 valid items (owned by normal user) + 2 orphan items.
            "truth = _seed(n_extra_users=1, item_specs=['v1','v2','v3'], "
            "orphan_titles=['o1','o2'])\n"
            "hdr = super_headers()\n"
            "paths = [p for p in _admin_get_paths() if '{' not in p]\n"
            "results = []\n"
            "for p in paths:\n"
            "    r = client.get(p, headers=hdr)\n"
            "    if r.status_code != 200:\n"
            "        continue\n"
            "    b = r.json()\n"
            "    if isinstance(b, dict):\n"
            "        ints = [v for v in b.values() if isinstance(v, bool) is False and isinstance(v, int)]\n"
            "        results.append({'path': p, 'body': b, 'ints': ints})\n"
            + _emit("{'truth': truth, 'results': results}")
        )
        res = _run_driver(body)
        assert res["truth"]["n_orphans"] == 2, res["truth"]
        # truth totals: users = super+normal+1 extra+? (ghost deleted) = 3 users.
        # items = 3 valid + 2 orphan = 5 items. orphans = 2.
        assert res["truth"]["n_users"] == 3, res["truth"]
        assert res["truth"]["n_items"] == 5, res["truth"]
        # Exactly one admin route must report the orphan count 2 as its sole/
        # dominant integer while being DISTINCT from the counts route (which
        # reports 3 and 5). Find a route whose integer fields equal {2}.
        orphan_route = [
            r for r in res["results"]
            if r["ints"] and all(v == 2 for v in r["ints"])
        ]
        assert orphan_route, (
            "no admin route reported the true orphan count of 2; a stub that "
            "returns 0 or ignores orphan computation fails here. results=%s"
            % res["results"]
        )
        # And the counts route (3 users, 5 items) must still be present & correct.
        counts_route = [
            r for r in res["results"]
            if 3 in r["ints"] and 5 in r["ints"]
        ]
        assert counts_route, (
            "counts route must report 3 users and 5 items even with orphans "
            "present; results=%s" % res["results"]
        )

    def test_shared_guard_protects_all_routes_uniformly(self):
        """The superuser guard is shared: ALL admin routes behave identically.

        A normal user must get 403 on every admin route and an unauthenticated
        caller 401 on every admin route. If the guard were applied per-route and
        one route forgot it, that route would answer 200/some-2xx and this test
        catches the inconsistency.
        """
        body = (
            "_seed(n_extra_users=1, item_specs=['a','b'])\n"
            "paths = [p for p in _admin_get_paths() if '{' not in p]\n"
            "anon = {p: client.get(p).status_code for p in paths}\n"
            "norm = {p: client.get(p, headers=normal_headers()).status_code for p in paths}\n"
            "sup  = {p: client.get(p, headers=super_headers()).status_code for p in paths}\n"
            + _emit("{'paths': paths, 'anon': anon, 'norm': norm, 'sup': sup}")
        )
        res = _run_driver(body)
        assert len(res["paths"]) >= 2, (
            "need >=2 admin routes to prove the guard is shared, got %s"
            % res["paths"]
        )
        # Uniform behavior across EVERY route.
        assert set(res["anon"].values()) == {401}, (
            "unauthenticated callers must get 401 on ALL admin routes: %s"
            % res["anon"]
        )
        assert set(res["norm"].values()) == {403}, (
            "normal users must get 403 on ALL admin routes (shared guard): %s"
            % res["norm"]
        )
        assert set(res["sup"].values()) == {200}, (
            "superusers must get 200 on ALL admin routes: %s" % res["sup"]
        )
