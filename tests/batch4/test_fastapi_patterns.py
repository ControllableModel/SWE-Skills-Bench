"""
Test for the 'fastapi-patterns' skill — Superuser User-Search Endpoint (ext4).

The task asks the agent to add a SUPERUSER-ONLY user search endpoint to the
users router of the full-stack-fastapi-template. The endpoint returns a
filtered, paginated page of users plus a filter-aware total count, supporting:
  * an optional case-insensitive `email` substring filter,
  * an optional boolean `is_active` filter (the two combine with logical AND),
  * `skip` (offset, must be >= 0) and `limit` (page size, must be in 1..100),
  * HTTP 422 on out-of-range pagination (limit=0, limit>100, skip<0),
  * HTTP 403 for normal users, HTTP 401/403 for unauthenticated callers,
  * a response that NEVER leaks `hashed_password` or other secret columns.

Verification strategy
---------------------
Like the ext1 harness, these tests EXERCISE the real FastAPI app. The template
is hard-wired to Postgres, so each behavioral (L2) test runs a self-contained
driver under the backend package (same interpreter as pytest) that:
  * builds an in-memory SQLite engine and creates all tables,
  * overrides the `get_db` dependency so the app uses that SQLite session,
  * seeds a known set of users (a superuser, a normal active user, and an
    inactive user) directly,
  * mints real JWT access tokens via app.core.security.create_access_token so
    requests authenticate exactly as the app expects,
  * calls the search endpoint with a TestClient and asserts concrete values.

The search route is DISCOVERED dynamically from the OpenAPI schema (a GET route
on the users router, distinct from `/users/`, `/users/me`, `/users/{id}`, that
returns a {data, count}-shaped page for a superuser), so the exact path the
agent chose (e.g. /users/search) does not matter. A naive solution that only
edits files, reuses the unfiltered `/users/` listing, ignores a filter, clamps
out-of-range pagination instead of rejecting it, or leaks hashed_password will
FAIL these tests.
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
# global engine for SQLite, create tables, seed users, mint JWT tokens, and
# override get_db. KNOWN_USERS holds the seeded emails/ids/states so each
# driver can assert. Helper `_discover_search_route` finds the new endpoint.
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

API = settings.API_V1_STR


def _get_db_override():
    with Session(_sqlite) as s:
        yield s

app.dependency_overrides[get_db] = _get_db_override

# Registry of seeded users, populated by _seed_users().
SEEDED = {}  # email -> {"id": str, "is_active": bool, "is_superuser": bool}


def _seed_users(specs):
    """specs: list of (email, is_active, is_superuser).

    Always also seeds a baseline superuser 'root@example.com' (active) so a
    valid superuser token is available regardless of the test's own specs.
    Returns the auth token for that root superuser.
    """
    full = [("root@example.com", True, True)] + list(specs)
    with Session(_sqlite) as s:
        for email, is_active, is_super in full:
            uid = uuid.uuid4()
            u = models.User(
                id=uid,
                email=email,
                hashed_password="not-a-real-hash",
                is_active=is_active,
                is_superuser=is_super,
            )
            s.add(u)
            s.commit()
            SEEDED[email] = {
                "id": str(uid),
                "is_active": is_active,
                "is_superuser": is_super,
            }
    return _token_for("root@example.com")


def _token_for(email):
    uid = SEEDED[email]["id"]
    tok = create_access_token(uid, expires_delta=timedelta(minutes=30))
    return tok


def _auth(email):
    return {"Authorization": "Bearer %s" % _token_for(email)}


client = TestClient(app)


def _user_get_paths():
    """All GET paths tagged 'users' in the OpenAPI schema."""
    schema = app.openapi()
    out = []
    for path, methods in schema.get("paths", {}).items():
        spec = methods.get("get")
        if not spec:
            continue
        if "users" not in spec.get("tags", []):
            continue
        out.append(path)
    return out


def _discover_search_route(super_token):
    """Return the path of the new superuser search endpoint, or None.

    Candidate = a GET route tagged 'users', NOT a path-parameter route
    ({...}), NOT exactly the bare '/users/' listing, NOT '/users/me', that,
    when called by a superuser with NO extra query params, returns a 200
    {data: [...], count: int} page. We prefer a path containing 'search' but
    fall back to any non-baseline page route.
    """
    headers = {"Authorization": "Bearer %s" % super_token}
    candidates = []
    for path in _user_get_paths():
        if "{" in path:
            continue
        if path.rstrip("/").endswith("/me"):
            continue
        # Skip the bare existing listing '/users/'.
        if path.rstrip("/").endswith("/users"):
            # Only skip if it's literally the users listing (no extra segment).
            seg = path.rstrip("/").split("/")[-1]
            if seg == "users":
                continue
        candidates.append(path)
    # Probe candidates; the search route returns a page object for a superuser.
    chosen = None
    for path in candidates:
        try:
            r = client.get(path, headers=headers)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        try:
            body = r.json()
        except Exception:
            continue
        if (
            isinstance(body, dict)
            and isinstance(body.get("data"), list)
            and isinstance(body.get("count"), int)
        ):
            if "search" in path.lower():
                return path
            if chosen is None:
                chosen = path
    return chosen
'''


def _run_driver(body: str, timeout: int = 300):
    """Write a driver .py under backend/ and run it with this interpreter.

    Runs with cwd=backend so `app` is importable. Returns parsed JSON printed
    by the driver between the RESULT markers.
    """
    if not os.path.isdir(BACKEND_DIR):
        pytest.fail("backend/ directory not found at %s" % BACKEND_DIR)

    driver_path = os.path.join(BACKEND_DIR, "_skilltest_search_driver.py")
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
    """Verify the superuser user-search endpoint (filters + pagination)."""

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
        """The FastAPI app imports cleanly and exposes GET routes on users."""
        body = (
            "paths = _user_get_paths()\n"
            + _emit("{'user_get_paths': paths}")
        )
        res = _run_driver(body)
        assert len(res["user_get_paths"]) >= 1, (
            "no GET routes tagged 'users' found in OpenAPI schema"
        )

    def test_search_route_discoverable(self):
        """A new {data,count} page route (not /users/, /me, /{id}) exists."""
        body = (
            "tok = _seed_users([])\n"
            "path = _discover_search_route(tok)\n"
            + _emit("{'search_path': path, 'all_paths': _user_get_paths()}")
        )
        res = _run_driver(body)
        assert res["search_path"], (
            "no superuser search page route discovered on the users router; "
            "GET paths seen: %s" % res["all_paths"]
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavioral validation of the search endpoint.
    # ------------------------------------------------------------------ #

    def test_search_no_filter_returns_all_with_total(self):
        """Search with no filter returns every user and an accurate total."""
        body = (
            "tok = _seed_users([\n"
            "    ('admin.one@example.com', True, False),\n"
            "    ('bob@example.com', True, False),\n"
            "    ('carol@example.com', False, False),\n"
            "])\n"
            "path = _discover_search_route(tok)\n"
            "assert path, 'search route not found'\n"
            "r = client.get(path, headers=_auth('root@example.com'),\n"
            "               params={'skip': 0, 'limit': 100})\n"
            "b = r.json()\n"
            "emails = sorted(u.get('email') for u in b.get('data', []))\n"
            + _emit("{'status': r.status_code, 'count': b.get('count'), "
                    "'len': len(b.get('data', [])), 'emails': emails}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        # root + 3 seeded = 4 total users, unfiltered.
        assert res["count"] == 4, "unfiltered total should be 4, got %s" % res["count"]
        assert res["len"] == 4, "unfiltered page should hold 4 users, got %s" % res["len"]
        assert "root@example.com" in res["emails"]
        assert "carol@example.com" in res["emails"]

    def test_search_email_substring_case_insensitive(self):
        """email=admin matches only emails containing 'admin' (any case)."""
        body = (
            "tok = _seed_users([\n"
            "    ('ADMIN.alice@example.com', True, True),\n"
            "    ('the.Admin.bob@example.com', True, False),\n"
            "    ('carol@example.com', True, False),\n"
            "    ('dave@example.com', False, False),\n"
            "])\n"
            "path = _discover_search_route(tok)\n"
            "assert path, 'search route not found'\n"
            "r = client.get(path, headers=_auth('root@example.com'),\n"
            "               params={'email': 'admin', 'limit': 100})\n"
            "b = r.json()\n"
            "emails = sorted(u.get('email') for u in b.get('data', []))\n"
            + _emit("{'status': r.status_code, 'count': b.get('count'), "
                    "'emails': emails}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["emails"] == [
            "ADMIN.alice@example.com",
            "the.Admin.bob@example.com",
        ], "email=admin must match case-insensitively: %s" % res["emails"]
        assert res["count"] == 2, (
            "filter-aware total for email=admin should be 2, got %s" % res["count"]
        )

    def test_search_is_active_filter(self):
        """is_active=false returns only inactive users."""
        body = (
            "tok = _seed_users([\n"
            "    ('act1@example.com', True, False),\n"
            "    ('act2@example.com', True, False),\n"
            "    ('inact1@example.com', False, False),\n"
            "    ('inact2@example.com', False, False),\n"
            "])\n"
            "path = _discover_search_route(tok)\n"
            "assert path, 'search route not found'\n"
            "r = client.get(path, headers=_auth('root@example.com'),\n"
            "               params={'is_active': 'false', 'limit': 100})\n"
            "b = r.json()\n"
            "emails = sorted(u.get('email') for u in b.get('data', []))\n"
            "actives = [u.get('is_active') for u in b.get('data', [])]\n"
            + _emit("{'status': r.status_code, 'count': b.get('count'), "
                    "'emails': emails, 'actives': actives}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["emails"] == ["inact1@example.com", "inact2@example.com"], (
            "is_active=false should return only inactive users, got %s" % res["emails"]
        )
        assert res["count"] == 2, (
            "is_active=false total should be 2, got %s" % res["count"]
        )
        assert all(v is False for v in res["actives"]), (
            "every returned user must be inactive, got is_active=%s" % res["actives"]
        )

    def test_search_combined_filters_logical_and(self):
        """email + is_active combine with logical AND."""
        body = (
            "tok = _seed_users([\n"
            # 'x' in email AND active -> should match
            "    ('xavier.active@example.com', True, False),\n"
            "    ('max.active@example.com', True, False),\n"
            # 'x' in email but inactive -> excluded by is_active=true
            "    ('xena.inactive@example.com', False, False),\n"
            # active but no 'x' in email -> excluded by email filter
            "    ('bob.active@example.com', True, False),\n"
            "])\n"
            "path = _discover_search_route(tok)\n"
            "assert path, 'search route not found'\n"
            "r = client.get(path, headers=_auth('root@example.com'),\n"
            "               params={'email': 'x', 'is_active': 'true', 'limit': 100})\n"
            "b = r.json()\n"
            "emails = sorted(u.get('email') for u in b.get('data', []))\n"
            + _emit("{'status': r.status_code, 'count': b.get('count'), "
                    "'emails': emails}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["emails"] == [
            "max.active@example.com",
            "xavier.active@example.com",
        ], "email=x & is_active=true must AND-combine: %s" % res["emails"]
        assert res["count"] == 2, (
            "combined-filter total should be 2, got %s" % res["count"]
        )

    def test_search_pagination_slice_with_filtered_total(self):
        """skip/limit return the right slice while total reflects the filter."""
        body = (
            "tok = _seed_users([\n"
            "    ('user.a@example.com', True, False),\n"
            "    ('user.b@example.com', True, False),\n"
            "    ('user.c@example.com', True, False),\n"
            "    ('other@example.com', True, False),\n"
            "])\n"
            "path = _discover_search_route(tok)\n"
            "assert path, 'search route not found'\n"
            "# 3 'user.' emails match; full filtered set first to learn ordering.\n"
            "rf = client.get(path, headers=_auth('root@example.com'),\n"
            "                params={'email': 'user.', 'limit': 100, 'skip': 0})\n"
            "bf = rf.json()\n"
            "# Page of size 2 skipping 2 -> exactly the 3rd match.\n"
            "rp = client.get(path, headers=_auth('root@example.com'),\n"
            "                params={'email': 'user.', 'limit': 2, 'skip': 2})\n"
            "bp = rp.json()\n"
            + _emit("{'status': rp.status_code, 'count': bp.get('count'), "
                    "'page_len': len(bp.get('data', [])), "
                    "'full_emails': [u['email'] for u in bf.get('data', [])], "
                    "'page_emails': [u['email'] for u in bp.get('data', [])]}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["count"] == 3, (
            "filtered total must stay 3 regardless of paging, got %s" % res["count"]
        )
        assert res["page_len"] == 1, (
            "limit=2 skip=2 over 3 matches must return 1 user, got %s" % res["page_len"]
        )
        assert len(res["full_emails"]) == 3, res
        # The single paged item must be the 3rd of the full filtered ordering.
        assert res["page_emails"][0] == res["full_emails"][2], (
            "paged slice inconsistent with full ordering: page=%s full=%s"
            % (res["page_emails"], res["full_emails"])
        )

    def test_search_rejects_out_of_range_pagination(self):
        """limit=0, limit>100 and skip<0 are rejected with HTTP 422."""
        body = (
            "tok = _seed_users([('u1@example.com', True, False)])\n"
            "path = _discover_search_route(tok)\n"
            "assert path, 'search route not found'\n"
            "h = _auth('root@example.com')\n"
            "r_zero = client.get(path, headers=h, params={'limit': 0})\n"
            "r_big  = client.get(path, headers=h, params={'limit': 101})\n"
            "r_neg  = client.get(path, headers=h, params={'skip': -1})\n"
            + _emit("{'limit0': r_zero.status_code, "
                    "'limit101': r_big.status_code, 'skipneg': r_neg.status_code}")
        )
        res = _run_driver(body)
        assert res["limit0"] == 422, "limit=0 must be 422, got %s" % res["limit0"]
        assert res["limit101"] == 422, "limit>100 must be 422, got %s" % res["limit101"]
        assert res["skipneg"] == 422, "skip=-1 must be 422, got %s" % res["skipneg"]

    def test_search_never_leaks_secret_fields(self):
        """No returned user object exposes hashed_password or other secrets."""
        body = (
            "tok = _seed_users([('secret.user@example.com', True, False)])\n"
            "path = _discover_search_route(tok)\n"
            "assert path, 'search route not found'\n"
            "r = client.get(path, headers=_auth('root@example.com'),\n"
            "               params={'email': 'secret.user', 'limit': 10})\n"
            "b = r.json()\n"
            "item = b['data'][0] if b.get('data') else {}\n"
            + _emit("{'status': r.status_code, 'keys': sorted(item.keys()), "
                    "'email': item.get('email')}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        keys = set(res["keys"])
        for forbidden in ("hashed_password", "password", "hashedPassword"):
            assert forbidden not in keys, (
                "search response leaked secret field '%s' (keys=%s)"
                % (forbidden, sorted(keys))
            )
        # Sanity: the public, non-sensitive identity must still be present.
        assert "email" in keys and "id" in keys, (
            "public user shape must include id+email, got keys=%s" % sorted(keys)
        )
        assert res["email"] == "secret.user@example.com"

    def test_search_requires_superuser(self):
        """A normal user gets 403; an unauthenticated caller gets 401/403."""
        body = (
            "tok = _seed_users([('normal@example.com', True, False)])\n"
            "path = _discover_search_route(tok)\n"
            "assert path, 'search route not found'\n"
            "r_normal = client.get(path, headers=_auth('normal@example.com'))\n"
            "r_anon = client.get(path)\n"  # no Authorization header
            + _emit("{'normal': r_normal.status_code, 'anon': r_anon.status_code}")
        )
        res = _run_driver(body)
        assert res["normal"] == 403, (
            "a normal user must receive 403 from the search route, got %s"
            % res["normal"]
        )
        assert res["anon"] in (401, 403), (
            "an unauthenticated caller must receive 401/403, got %s" % res["anon"]
        )

    def test_search_empty_match_returns_zero(self):
        """An email filter matching nothing yields an empty page and total 0."""
        body = (
            "tok = _seed_users([\n"
            "    ('alice@example.com', True, False),\n"
            "    ('bob@example.com', True, False),\n"
            "])\n"
            "path = _discover_search_route(tok)\n"
            "assert path, 'search route not found'\n"
            "r = client.get(path, headers=_auth('root@example.com'),\n"
            "               params={'email': 'zzz-nomatch', 'limit': 100})\n"
            "b = r.json()\n"
            + _emit("{'status': r.status_code, 'len': len(b.get('data', [])), "
                    "'count': b.get('count')}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["len"] == 0, "non-matching email filter should return 0 users"
        assert res["count"] == 0, "non-matching email filter total should be 0"

    def test_existing_users_listing_intact(self):
        """The original GET /users/ still requires auth and lists all users."""
        body = (
            "tok = _seed_users([('extra@example.com', True, False)])\n"
            "base = API + '/users/'\n"
            "r_anon = client.get(base)\n"  # no auth header
            "r_super = client.get(base, headers=_auth('root@example.com'),\n"
            "                     params={'limit': 100})\n"
            "bs = r_super.json()\n"
            + _emit("{'anon': r_anon.status_code, 'super': r_super.status_code, "
                    "'count': bs.get('count')}")
        )
        res = _run_driver(body)
        assert res["anon"] in (401, 403), (
            "existing /users/ must still require auth, got %s" % res["anon"]
        )
        assert res["super"] == 200, (
            "superuser must still read /users/, got %s" % res["super"]
        )
        # root + extra = 2 users.
        assert res["count"] == 2, (
            "existing /users/ count should be 2, got %s" % res["count"]
        )

    def test_search_native_pytest_suite_passes(self):
        """The repo's native acceptance command for this task passes.

        Drives exactly the doc's acceptance command:
            pytest backend/tests/api/routes/test_users.py
        We seed nothing here; this delegates to the agent-extended test file
        (run with the repo's own fixtures) to confirm the added cases pass.
        """
        target = os.path.join(
            BACKEND_DIR, "tests", "api", "routes", "test_users.py"
        )
        assert os.path.isfile(target), "backend tests/api/routes/test_users.py missing"
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
            [
                sys.executable, "-m", "pytest",
                os.path.join("tests", "api", "routes", "test_users.py"),
                "-q", "--no-header", "-p", "no:cacheprovider",
            ],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            env=env,
            timeout=900,
        )
        # If the suite cannot run at all because a live Postgres is required
        # (collection/connection error), don't penalize: skip rather than fail.
        combined = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            db_signals = (
                "could not connect to server",
                "Connection refused",
                "psycopg",
                "OperationalError",
                "could not translate host name",
            )
            if any(sig in combined for sig in db_signals):
                pytest.skip(
                    "native suite needs a live Postgres unavailable here:\n%s"
                    % combined[-2000:]
                )
        assert proc.returncode == 0, (
            "native `pytest backend/tests/api/routes/test_users.py` failed:\n%s"
            % combined[-4000:]
        )
