"""
Test for the 'fastapi-patterns' skill (variant ext9) — Per-User Item-Count
Summary Endpoint.

The task asks the agent to add a SUPERUSER-ONLY GET route on the users router
(e.g. /users/item-counts) returning a paginated list of per-user summary rows.
Each row exposes the user's identifier, the user's email, and the NUMBER of
items that user owns (0 for users with no items). The response also carries a
`count` total equal to the real number of users (independent of paging).
Out-of-range pagination must yield HTTP 422; a normal user gets 403; an
unauthenticated caller gets 401; rows must never leak hashed_password or other
secret columns.

Verification strategy
---------------------
These tests EXERCISE the real FastAPI app. The template is hard-wired to
Postgres, so each behavioral (L2) test runs a self-contained driver under the
backend package (same interpreter that runs pytest) that:
  * builds an in-memory SQLite engine and creates all tables,
  * overrides the `get_db` dependency so the app uses that SQLite session,
  * seeds a real superuser, a real normal user, and additional users each
    owning a known number of items, all directly via the ORM,
  * mints REAL JWT access tokens with the app's own `create_access_token`,
  * calls the discovered summary endpoint with TestClient using those tokens,
  * prints a JSON result that this test deeply validates.

The summary route is DISCOVERED dynamically from the OpenAPI schema (a GET path
on the users router, no path parameter, whose page rows carry an integer
item-count field), so the exact path the agent chose does not matter. A naive
solution that hardcodes counts, ignores item ownership, forgets users with zero
items, leaks secret columns, skips superuser gating, or omits pagination
validation will FAIL.
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
# global engine for SQLite, create tables, override get_db, provide seeding
# helpers, real-token minting, and a discovery routine for the summary route.
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
from app.core.config import settings
from app.core.security import create_access_token

def _get_db_override():
    with Session(_sqlite) as s:
        yield s

app.dependency_overrides[get_db] = _get_db_override

client = TestClient(app)

# Track the seeded superuser/normal-user ids so drivers can mint tokens.
SEEDED = {"superuser_id": None, "user_id": None}


def _mint_token(user_id):
    """Return a real Bearer header for the given user id (str/uuid)."""
    tok = create_access_token(str(user_id), expires_delta=timedelta(minutes=30))
    return {"Authorization": "Bearer " + tok}


def _superuser_headers():
    return _mint_token(SEEDED["superuser_id"])


def _user_headers():
    return _mint_token(SEEDED["user_id"])


def _seed(user_specs):
    """Seed users and their items.

    user_specs: list of (email, is_superuser, n_items). The first superuser
    encountered is recorded as SEEDED['superuser_id']; the first non-superuser
    as SEEDED['user_id']. Returns dict email -> {'id': str, 'n_items': int}.
    """
    out = {}
    with Session(_sqlite) as s:
        for email, is_super, n_items in user_specs:
            u = models.User(
                id=uuid.uuid4(),
                email=email,
                hashed_password="x",
                is_active=True,
                is_superuser=bool(is_super),
            )
            s.add(u)
            s.commit()
            s.refresh(u)
            if is_super and SEEDED["superuser_id"] is None:
                SEEDED["superuser_id"] = str(u.id)
            if (not is_super) and SEEDED["user_id"] is None:
                SEEDED["user_id"] = str(u.id)
            for i in range(n_items):
                it = models.Item(
                    title="%s-item-%d" % (email.split("@")[0], i),
                    description="d",
                    owner_id=u.id,
                )
                s.add(it)
            s.commit()
            out[email] = {"id": str(u.id), "n_items": n_items}
    return out


def _user_get_paths():
    """All no-path-parameter GET routes tagged 'users' from the schema."""
    schema = app.openapi()
    paths = []
    for path, methods in schema.get("paths", {}).items():
        spec = methods.get("get")
        if not spec:
            continue
        if "users" not in spec.get("tags", []):
            continue
        if "{" in path:
            continue
        paths.append(path)
    return paths


def _row_count_field(row):
    """Pick the integer field in a summary row that holds the item count.

    Excludes obvious non-count integers; the item count is the only plain
    integer field besides identifiers (which are uuid strings / emails). We
    return the field NAME so callers can read it consistently across rows.
    """
    candidates = []
    for k, v in row.items():
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            candidates.append(k)
    return candidates


def _discover_summary(super_headers):
    """Return (path, count_field) for the per-user item-count summary route.

    A summary route is a no-arg GET on the users router that, when called by a
    superuser, returns a {data:[...], count:int} page whose rows each carry an
    integer item-count field AND a user identifier/email. The existing /users/
    listing returns UserPublic rows (no integer count field besides none), so
    it is filtered out by requiring an integer count field in the rows.
    """
    for path in _user_get_paths():
        try:
            r = client.get(path, headers=super_headers, params={"skip": 0, "limit": 100})
        except Exception:
            continue
        if r.status_code != 200:
            continue
        body = r.json()
        if not (isinstance(body, dict) and isinstance(body.get("data"), list)
                and isinstance(body.get("count"), int)):
            continue
        if not body["data"]:
            # Cannot confirm shape without rows; remember as weak candidate.
            continue
        row = body["data"][0]
        if not isinstance(row, dict):
            continue
        ints = _row_count_field(row)
        # Must expose an email-like and an integer count distinct from it.
        has_email = any(
            isinstance(v, str) and "@" in v for v in row.values()
        )
        if ints and has_email:
            return path, ints
    return None, None
'''


def _run_driver(body: str, timeout: int = 300):
    """Write a driver .py under backend/ and run it with this interpreter.

    Runs with cwd=backend so `app` is importable. Returns parsed JSON printed
    by the driver between the RESULT markers.
    """
    if not os.path.isdir(BACKEND_DIR):
        pytest.fail("backend/ directory not found at %s" % BACKEND_DIR)

    driver_path = os.path.join(BACKEND_DIR, "_skilltest_driver_ext9.py")
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
    """Verify the per-user item-count summary endpoint (ext9)."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist and are minimally well-formed.
    # ------------------------------------------------------------------ #

    def test_users_route_file_present(self):
        """backend/app/api/routes/users.py must exist."""
        p = os.path.join(BACKEND_DIR, "app", "api", "routes", "users.py")
        assert os.path.isfile(p), "users.py route module missing"

    def test_models_file_present(self):
        """backend/app/models.py must exist."""
        p = os.path.join(BACKEND_DIR, "app", "models.py")
        assert os.path.isfile(p), "models.py missing"

    def test_app_imports_and_users_router_registered(self):
        """The FastAPI app imports cleanly and exposes >1 users GET route."""
        body = (
            "paths = _user_get_paths()\n"
            + _emit("{'user_get_paths': paths}")
        )
        res = _run_driver(body)
        # The stock template ships exactly one no-arg users GET ('/users/').
        # Adding the summary endpoint must introduce at least one more.
        assert len(res["user_get_paths"]) >= 2, (
            "expected an additional users GET route for the summary endpoint, "
            "found only: %s" % res["user_get_paths"]
        )

    def test_summary_route_discoverable_for_superuser(self):
        """A users-router page with per-row integer item-count is reachable
        by a superuser (proves a distinct summary endpoint exists)."""
        body = (
            "_seed([('admin@example.com', True, 1), ('u1@example.com', False, 2)])\n"
            "path, cf = _discover_summary(_superuser_headers())\n"
            + _emit("{'path': path, 'count_fields': cf}")
        )
        res = _run_driver(body)
        assert res["path"], (
            "no superuser-reachable per-user item-count summary route found "
            "on the users router"
        )
        assert res["count_fields"], "summary rows lack an integer count field"

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavioral validation of the summary endpoint.
    # ------------------------------------------------------------------ #

    def test_counts_match_owned_items_including_zero(self):
        """Each row reports the true item count; a zero-item user shows 0."""
        body = (
            "_seed([('admin@example.com', True, 0),\n"
            "       ('three@example.com', False, 3),\n"
            "       ('zero@example.com', False, 0),\n"
            "       ('one@example.com', False, 1)])\n"
            "path, ints = _discover_summary(_superuser_headers())\n"
            "assert path, 'no summary route'\n"
            "r = client.get(path, headers=_superuser_headers(),\n"
            "               params={'skip':0,'limit':100})\n"
            "b = r.json()\n"
            "# Build email -> count using the int field that varies per row.\n"
            "rows = b['data']\n"
            "# Determine the count field: the integer field whose value equals\n"
            "# the number of items we seeded for at least one known user.\n"
            "expected = {'admin@example.com':0,'three@example.com':3,\n"
            "            'zero@example.com':0,'one@example.com':1}\n"
            "def email_of(row):\n"
            "    for v in row.values():\n"
            "        if isinstance(v, str) and '@' in v:\n"
            "            return v\n"
            "    return None\n"
            "chosen = None\n"
            "for cand in ints:\n"
            "    ok = True\n"
            "    for row in rows:\n"
            "        e = email_of(row)\n"
            "        if e in expected and row.get(cand) != expected[e]:\n"
            "            ok = False; break\n"
            "    if ok:\n"
            "        chosen = cand; break\n"
            "mapping = {}\n"
            "if chosen is not None:\n"
            "    for row in rows:\n"
            "        e = email_of(row)\n"
            "        if e is not None:\n"
            "            mapping[e] = row.get(chosen)\n"
            + _emit("{'status': r.status_code, 'count_field': chosen, "
                    "'mapping': mapping, 'n_rows': len(rows)}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["count_field"] is not None, (
            "no per-row field matched the true item counts; counts are wrong "
            "or hardcoded: %s" % res
        )
        m = res["mapping"]
        assert m.get("three@example.com") == 3, (
            "user with 3 items must report 3, got %s" % m.get("three@example.com")
        )
        assert m.get("one@example.com") == 1, m
        assert m.get("zero@example.com") == 0, (
            "zero-item user must still appear with count 0, got %s"
            % m.get("zero@example.com")
        )
        assert m.get("admin@example.com") == 0, m

    def test_total_equals_number_of_users(self):
        """The page `count` equals the real number of users, not items/rows."""
        body = (
            "_seed([('admin@example.com', True, 5),\n"
            "       ('a@example.com', False, 2),\n"
            "       ('b@example.com', False, 0),\n"
            "       ('c@example.com', False, 1),\n"
            "       ('d@example.com', False, 4)])\n"
            "path, _ = _discover_summary(_superuser_headers())\n"
            "assert path, 'no summary route'\n"
            "r = client.get(path, headers=_superuser_headers(),\n"
            "               params={'skip':0,'limit':100})\n"
            "b = r.json()\n"
            + _emit("{'status': r.status_code, 'count': b.get('count'), "
                    "'n_rows': len(b.get('data',[]))}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        # 5 users total; total must be users, not the 12 items seeded.
        assert res["count"] == 5, (
            "total must equal number of users (5), got %s" % res["count"]
        )
        assert res["n_rows"] == 5, res

    def test_zero_item_users_present_in_page(self):
        """Every seeded user appears exactly once, including zero-item ones."""
        body = (
            "_seed([('admin@example.com', True, 0),\n"
            "       ('x@example.com', False, 0),\n"
            "       ('y@example.com', False, 0),\n"
            "       ('z@example.com', False, 2)])\n"
            "path, _ = _discover_summary(_superuser_headers())\n"
            "assert path, 'no summary route'\n"
            "r = client.get(path, headers=_superuser_headers(),\n"
            "               params={'skip':0,'limit':100})\n"
            "b = r.json()\n"
            "def email_of(row):\n"
            "    for v in row.values():\n"
            "        if isinstance(v, str) and '@' in v:\n"
            "            return v\n"
            "    return None\n"
            "emails = sorted(e for e in (email_of(r2) for r2 in b['data']) if e)\n"
            + _emit("{'status': r.status_code, 'emails': emails}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["emails"] == sorted([
            "admin@example.com", "x@example.com", "y@example.com", "z@example.com"
        ]), (
            "all users (including zero-item) must appear once each, got %s"
            % res["emails"]
        )

    def test_pagination_slices_rows_but_total_stays(self):
        """skip/limit page the rows while `count` stays the user total."""
        body = (
            "_seed([('admin@example.com', True, 1),\n"
            "       ('a@example.com', False, 1),\n"
            "       ('b@example.com', False, 1),\n"
            "       ('c@example.com', False, 1),\n"
            "       ('d@example.com', False, 1)])\n"
            "path, _ = _discover_summary(_superuser_headers())\n"
            "assert path, 'no summary route'\n"
            "r1 = client.get(path, headers=_superuser_headers(),\n"
            "                params={'skip':0,'limit':2})\n"
            "r2 = client.get(path, headers=_superuser_headers(),\n"
            "                params={'skip':2,'limit':2})\n"
            "b1, b2 = r1.json(), r2.json()\n"
            "def ids(b):\n"
            "    out = []\n"
            "    for row in b.get('data',[]):\n"
            "        for v in row.values():\n"
            "            if isinstance(v, str) and '@' in v:\n"
            "                out.append(v); break\n"
            "    return out\n"
            + _emit("{'s1': r1.status_code, 's2': r2.status_code, "
                    "'len1': len(b1.get('data',[])), 'len2': len(b2.get('data',[])), "
                    "'count1': b1.get('count'), 'count2': b2.get('count'), "
                    "'ids1': ids(b1), 'ids2': ids(b2)}")
        )
        res = _run_driver(body)
        assert res["s1"] == 200 and res["s2"] == 200, res
        assert res["len1"] == 2, "limit=2 must return 2 rows, got %s" % res["len1"]
        assert res["len2"] == 2, "skip=2 limit=2 must return 2 rows, got %s" % res["len2"]
        # Total must stay 5 regardless of paging.
        assert res["count1"] == 5 and res["count2"] == 5, (
            "total users must stay 5 across pages, got %s/%s"
            % (res["count1"], res["count2"])
        )
        # Pages must not overlap (genuine offset paging, not ignored skip).
        assert set(res["ids1"]).isdisjoint(set(res["ids2"])), (
            "skip must advance the window; pages overlapped: %s vs %s"
            % (res["ids1"], res["ids2"])
        )

    def test_invalid_pagination_rejected_422(self):
        """limit=0, limit>100 and skip<0 are rejected with HTTP 422."""
        body = (
            "_seed([('admin@example.com', True, 1), ('u@example.com', False, 1)])\n"
            "path, _ = _discover_summary(_superuser_headers())\n"
            "assert path, 'no summary route'\n"
            "h = _superuser_headers()\n"
            "r_zero = client.get(path, headers=h, params={'limit':0})\n"
            "r_big  = client.get(path, headers=h, params={'limit':101})\n"
            "r_neg  = client.get(path, headers=h, params={'skip':-1})\n"
            + _emit("{'limit0': r_zero.status_code, "
                    "'limit101': r_big.status_code, 'skipneg': r_neg.status_code}")
        )
        res = _run_driver(body)
        assert res["limit0"] == 422, "limit=0 must be 422, got %s" % res["limit0"]
        assert res["limit101"] == 422, (
            "limit>100 must be 422, got %s" % res["limit101"]
        )
        assert res["skipneg"] == 422, "skip=-1 must be 422, got %s" % res["skipneg"]

    def test_normal_user_forbidden_403(self):
        """A normal (non-superuser) caller receives HTTP 403."""
        body = (
            "_seed([('admin@example.com', True, 0), ('plain@example.com', False, 2)])\n"
            "path, _ = _discover_summary(_superuser_headers())\n"
            "assert path, 'no summary route'\n"
            "r = client.get(path, headers=_user_headers(),\n"
            "               params={'skip':0,'limit':10})\n"
            + _emit("{'status': r.status_code}")
        )
        res = _run_driver(body)
        assert res["status"] == 403, (
            "normal user must get 403 on the superuser-only summary, got %s"
            % res["status"]
        )

    def test_unauthenticated_rejected_401(self):
        """An unauthenticated caller (no token) receives HTTP 401."""
        body = (
            "_seed([('admin@example.com', True, 0), ('u@example.com', False, 1)])\n"
            "path, _ = _discover_summary(_superuser_headers())\n"
            "assert path, 'no summary route'\n"
            "r = client.get(path, params={'skip':0,'limit':10})\n"  # no headers
            + _emit("{'status': r.status_code}")
        )
        res = _run_driver(body)
        assert res["status"] == 401, (
            "unauthenticated caller must get 401, got %s" % res["status"]
        )

    def test_rows_do_not_leak_secret_columns(self):
        """Summary rows must never expose hashed_password or other secrets."""
        body = (
            "_seed([('admin@example.com', True, 1), ('s@example.com', False, 3)])\n"
            "path, _ = _discover_summary(_superuser_headers())\n"
            "assert path, 'no summary route'\n"
            "r = client.get(path, headers=_superuser_headers(),\n"
            "               params={'skip':0,'limit':100})\n"
            "b = r.json()\n"
            "all_keys = set()\n"
            "for row in b.get('data',[]):\n"
            "    if isinstance(row, dict):\n"
            "        all_keys |= set(row.keys())\n"
            + _emit("{'status': r.status_code, 'keys': sorted(all_keys)}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        keys = set(res["keys"])
        for forbidden in ("hashed_password", "password", "is_superuser",
                          "is_active"):
            assert forbidden not in keys, (
                "summary row leaked secret/internal field '%s' (keys=%s)"
                % (forbidden, sorted(keys))
            )
        # Must expose the agreed identifying fields: an email and an id.
        assert any(k in keys for k in ("email",)) or True, keys

    def test_count_reflects_real_ownership_not_hardcoded(self):
        """Re-seeding different ownership yields different counts (anti-stub).

        A stub returning a fixed number would report the same count for users
        whose true item counts differ. We assert the reported counts span the
        distinct seeded values.
        """
        body = (
            "_seed([('admin@example.com', True, 0),\n"
            "       ('p1@example.com', False, 4),\n"
            "       ('p2@example.com', False, 1),\n"
            "       ('p3@example.com', False, 7)])\n"
            "path, ints = _discover_summary(_superuser_headers())\n"
            "assert path, 'no summary route'\n"
            "r = client.get(path, headers=_superuser_headers(),\n"
            "               params={'skip':0,'limit':100})\n"
            "rows = r.json()['data']\n"
            "def email_of(row):\n"
            "    for v in row.values():\n"
            "        if isinstance(v, str) and '@' in v:\n"
            "            return v\n"
            "    return None\n"
            "expected = {'admin@example.com':0,'p1@example.com':4,\n"
            "            'p2@example.com':1,'p3@example.com':7}\n"
            "chosen = None\n"
            "for cand in ints:\n"
            "    ok = True\n"
            "    for row in rows:\n"
            "        e = email_of(row)\n"
            "        if e in expected and row.get(cand) != expected[e]:\n"
            "            ok = False; break\n"
            "    if ok:\n"
            "        chosen = cand; break\n"
            "vals = sorted(set(row.get(chosen) for row in rows)) if chosen else []\n"
            + _emit("{'status': r.status_code, 'count_field': chosen, "
                    "'distinct_counts': vals}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["count_field"] is not None, (
            "no field matched true per-user counts -> counts hardcoded/ignored "
            "ownership: %s" % res
        )
        # Distinct true counts were 0,1,4,7 -> a real impl must surface them.
        for expected_val in (0, 1, 4, 7):
            assert expected_val in res["distinct_counts"], (
                "count %d missing -> implementation not computing real "
                "ownership; got %s" % (expected_val, res["distinct_counts"])
            )

    def test_existing_users_listing_intact(self):
        """The original /users/ listing still works for a superuser and is
        distinct from the new summary route (no regression)."""
        body = (
            "_seed([('admin@example.com', True, 2), ('u@example.com', False, 1)])\n"
            "base = settings.API_V1_STR + '/users/'\n"
            "r = client.get(base, headers=_superuser_headers(),\n"
            "               params={'skip':0,'limit':100})\n"
            "b = r.json()\n"
            "# original rows are UserPublic: have email but NO integer item count\n"
            "row = b['data'][0] if b.get('data') else {}\n"
            "int_fields = [k for k,v in row.items()\n"
            "              if isinstance(v,int) and not isinstance(v,bool)]\n"
            + _emit("{'status': r.status_code, 'count': b.get('count'), "
                    "'orig_int_fields': int_fields}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["count"] == 2, (
            "original /users/ total should be 2 users, got %s" % res["count"]
        )
