"""
Test for the 'fastapi-patterns' skill — Item Ownership Transfer (variant ext7).

The task asks the agent to add a SUPERUSER-ONLY endpoint to the items router of
the full-stack-fastapi-template that reassigns a single existing item to a
different existing user (an "ownership transfer"). The item is identified by a
UUID path parameter; the target owner identifier is supplied somewhere in the
request (path / query / body — the agent's choice) and must be validated as a
UUID. The required behavior:

  * superuser transfers an existing item to a different existing user -> 200,
    the returned item shows the NEW owner_id and only the public item shape;
  * item not found                      -> 404
  * target owner user not found         -> 404
  * target owner == current owner       -> 400
  * malformed item id in the path       -> 422
  * normal (non-super) user             -> 403
  * unauthenticated caller              -> 401

Verification strategy
---------------------
The template is hard-wired to Postgres, so we cannot use a live DB. Each
behavioral (L2) test runs a self-contained driver under the backend package
(same interpreter as pytest) that:
  * builds an in-memory SQLite engine and creates all tables,
  * overrides `get_db` so the app uses that SQLite session,
  * seeds known users (a superuser, a normal user, plus owners/targets) and a
    known item directly in the DB,
  * controls the *acting* user by overriding `get_current_user` (so we can be a
    superuser, a normal user, or — by NOT overriding and sending no token — an
    unauthenticated caller),
  * invokes the transfer route discovered dynamically from the OpenAPI schema,
  * prints a JSON result this test deeply validates.

The transfer route is DISCOVERED from the OpenAPI schema (a non-GET route on the
items router that takes the item id as a UUID path parameter and is not one of
the stock create/update/delete routes), so the exact path/verb the agent chose
does not matter. A naive solution that only edits files, never updates owner_id,
ignores the same-owner / not-found cases, or skips the superuser guard will fail.
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
# global engine for SQLite, create tables, and provide helpers to seed users +
# items and to act as a specific user. Drivers below append their own logic.
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
from app.api.deps import get_db, get_current_user

def _get_db_override():
    with Session(_sqlite) as s:
        yield s

app.dependency_overrides[get_db] = _get_db_override


def _make_user(email, is_superuser):
    """Insert a user; return its uuid."""
    uid = uuid.uuid4()
    with Session(_sqlite) as s:
        u = models.User(
            id=uid,
            email=email,
            hashed_password="x",
            is_active=True,
            is_superuser=is_superuser,
        )
        s.add(u)
        s.commit()
    return uid


def _make_item(title, owner_id, desc=None):
    """Insert an item owned by owner_id; return its uuid."""
    iid = uuid.uuid4()
    with Session(_sqlite) as s:
        it = models.Item(id=iid, title=title, description=desc, owner_id=owner_id)
        s.add(it)
        s.commit()
    return iid


def _act_as(user_id):
    """Override get_current_user so the app treats requests as this user."""
    def _override():
        with Session(_sqlite) as s:
            return s.get(models.User, user_id)
    app.dependency_overrides[get_current_user] = _override


def _act_anonymous():
    """Remove any auth override; the real OAuth2 guard then requires a token."""
    app.dependency_overrides.pop(get_current_user, None)


def _item_owner(item_id):
    """Read the current owner_id of an item straight from the DB."""
    with Session(_sqlite) as s:
        it = s.get(models.Item, item_id)
        return str(it.owner_id) if it is not None else None


client = TestClient(app)


def _discover_transfer_route():
    """Return (method, path_template) of the ownership-transfer route.

    Heuristics over the OpenAPI schema:
      * the route must be tagged 'items',
      * it must take the item id as a path parameter (a single '{...}' segment
        whose schema is a uuid-format string),
      * it must NOT be a stock route: exclude GET (read), and exclude the plain
        PUT/DELETE on '/{id}' which are the existing update/delete operations,
        UNLESS that operation references a *target owner* (extra path param,
        a query param, or a non-ItemUpdate request body) — i.e. a transfer.
    Returns (None, None) if nothing plausible is found.
    """
    schema = app.openapi()

    def _is_uuid_param(p):
        sch = p.get("schema", {})
        if sch.get("format") == "uuid":
            return True
        # anyOf wrappers, or plain string with uuid in name
        for sub in sch.get("anyOf", []) or []:
            if sub.get("format") == "uuid":
                return True
        return False

    best = None
    for path, methods in schema.get("paths", {}).items():
        for verb, spec in methods.items():
            if verb not in ("get", "post", "put", "patch", "delete"):
                continue
            if "items" not in (spec.get("tags") or []):
                continue
            params = spec.get("parameters", []) or []
            path_params = [p for p in params if p.get("in") == "path"]
            query_params = [p for p in params if p.get("in") == "query"]
            uuid_path = [p for p in path_params if _is_uuid_param(p)]
            # Must address a single item by uuid path param.
            if not uuid_path:
                continue
            # The operation summary / id / path often mentions transfer/owner.
            blob = " ".join([
                path,
                spec.get("operationId", "") or "",
                spec.get("summary", "") or "",
                (spec.get("description", "") or ""),
            ]).lower()
            mentions_transfer = (
                "transfer" in blob or "owner" in blob or "reassign" in blob
            )
            # Signals that a *target owner* is supplied beyond the item id:
            has_request_body = bool(spec.get("requestBody"))
            extra_path = len(uuid_path) >= 2 or len(path_params) >= 2
            has_query = len(query_params) >= 1
            target_signal = has_request_body or extra_path or has_query

            score = 0
            if mentions_transfer:
                score += 3
            if verb in ("post", "patch"):
                score += 1  # transfer is most naturally a new POST/PATCH
            if target_signal:
                score += 2
            # The stock PUT/DELETE on /items/{id} (update/delete) only touch the
            # item itself; without transfer wording or a target signal they are
            # not the route we want.
            if verb in ("put", "delete") and not mentions_transfer and not target_signal:
                continue
            if verb == "get":
                continue
            cand = (score, verb.upper(), path)
            if best is None or cand[0] > best[0]:
                best = cand
    if best is None:
        return None, None
    return best[1], best[2]


def _fill_path(path_template, item_id, target_id):
    """Substitute path params. The item-id param may be named id/item_id/...;
    a second path param (if any) is treated as the target user."""
    import re
    names = re.findall(r"\{([^}]+)\}", path_template)
    out = path_template
    used_item = False
    for n in names:
        low = n.lower()
        if (("user" in low or "owner" in low or "target" in low or "new" in low)
                and used_item):
            out = out.replace("{%s}" % n, str(target_id))
        elif not used_item:
            out = out.replace("{%s}" % n, str(item_id))
            used_item = True
        else:
            out = out.replace("{%s}" % n, str(target_id))
    return out


def _call_transfer(method, path_template, item_id, target_id,
                   force_raw_item=None):
    """Invoke the transfer route trying the several ways the agent might accept
    the target owner (extra path segment, query param, or JSON body).

    `force_raw_item` lets us inject a malformed item id (e.g. 'not-a-uuid').
    Returns (status_code, json_body_or_None).
    """
    item_token = force_raw_item if force_raw_item is not None else item_id
    base = _fill_path(path_template, item_token, target_id)

    # Candidate request shapes for the target owner.
    target = str(target_id)
    query_variants = [
        {"new_owner_id": target},
        {"target_owner_id": target},
        {"owner_id": target},
        {"user_id": target},
        {"new_owner": target},
    ]
    body_variants = [
        {"new_owner_id": target},
        {"owner_id": target},
        {"target_owner_id": target},
        {"user_id": target},
        {"new_owner": target},
    ]

    fn = getattr(client, method.lower())

    # If the path already embedded the target (>=2 path params), call directly.
    import re
    if len(re.findall(r"\{", path_template)) >= 2:
        r = fn(base)
        return r.status_code, _safe_json(r)

    attempts = []
    # 1) query params
    for q in query_variants:
        attempts.append(lambda q=q: fn(base, params=q))
    # 2) json body (for POST/PUT/PATCH)
    if method.upper() in ("POST", "PUT", "PATCH"):
        for b in body_variants:
            attempts.append(lambda b=b: fn(base, json=b))
    # 3) bare call (target maybe inferred) — last resort
    attempts.append(lambda: fn(base))

    last = None
    for attempt in attempts:
        try:
            r = attempt()
        except Exception:
            continue
        last = (r.status_code, _safe_json(r))
        # A 2xx, or a 422 specifically caused by a malformed item id, is a
        # definitive answer; a 422 from "wrong field name" means try next shape.
        if r.status_code < 300:
            return last
        if force_raw_item is not None and r.status_code == 422:
            return last
        if r.status_code in (400, 401, 403, 404):
            return last
    return last if last is not None else (None, None)


def _safe_json(r):
    try:
        return r.json()
    except Exception:
        return None
'''


def _run_driver(body: str, timeout: int = 300):
    """Write a driver .py under backend/ and run it with this interpreter.

    Runs with cwd=backend so `app` is importable. Returns parsed JSON printed
    by the driver between the RESULT markers.
    """
    if not os.path.isdir(BACKEND_DIR):
        pytest.fail("backend/ directory not found at %s" % BACKEND_DIR)

    driver_path = os.path.join(BACKEND_DIR, "_skilltest_xfer_driver.py")
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
    """Verify the superuser-only item ownership-transfer endpoint."""

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
            "item_ops = []\n"
            "for p, methods in schema['paths'].items():\n"
            "    for verb, spec in methods.items():\n"
            "        if 'items' in (spec.get('tags') or []):\n"
            "            item_ops.append(verb.upper()+' '+p)\n"
            + _emit("{'item_ops': item_ops}")
        )
        res = _run_driver(body)
        assert len(res["item_ops"]) >= 1, (
            "no operations tagged 'items' found in OpenAPI schema"
        )

    def test_transfer_route_discoverable(self):
        """A non-GET items route addressing an item by UUID + a target owner."""
        body = (
            "m, p = _discover_transfer_route()\n"
            + _emit("{'method': m, 'path': p}")
        )
        res = _run_driver(body)
        assert res["method"], (
            "could not discover an ownership-transfer route on the items router"
        )
        assert res["path"], "transfer route path missing"

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavioral validation of the transfer endpoint.
    # ------------------------------------------------------------------ #

    def test_superuser_transfer_succeeds_and_updates_owner(self):
        """Superuser transfer to a different existing user -> 200, owner updated."""
        body = (
            "su = _make_user('admin@example.com', True)\n"
            "owner = _make_user('owner@example.com', False)\n"
            "target = _make_user('target@example.com', False)\n"
            "item = _make_item('widget', owner)\n"
            "_act_as(su)\n"
            "m, p = _discover_transfer_route()\n"
            "status, body = _call_transfer(m, p, item, target)\n"
            "db_owner = _item_owner(item)\n"
            + _emit("{'status': status, 'body': body, 'db_owner': db_owner, "
                    "'target': str(target), 'orig_owner': str(owner)}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, (
            "superuser transfer should succeed (200), got %s body=%s"
            % (res["status"], res["body"])
        )
        # The item's owner in the DB must actually be the new target.
        assert res["db_owner"] == res["target"], (
            "owner_id not persisted to target: db=%s target=%s"
            % (res["db_owner"], res["target"])
        )
        assert res["db_owner"] != res["orig_owner"], (
            "owner_id unchanged — a naive no-op implementation must fail"
        )
        # The returned body must expose the new owner.
        body = res["body"] or {}
        assert body.get("owner_id") == res["target"], (
            "response owner_id should reflect the new owner: %s" % body
        )

    def test_transfer_response_only_public_fields(self):
        """The success response is limited to the public item shape."""
        body = (
            "su = _make_user('admin@example.com', True)\n"
            "owner = _make_user('owner@example.com', False)\n"
            "target = _make_user('target@example.com', False)\n"
            "item = _make_item('gadget', owner, 'a description')\n"
            "_act_as(su)\n"
            "m, p = _discover_transfer_route()\n"
            "status, b = _call_transfer(m, p, item, target)\n"
            + _emit("{'status': status, 'keys': sorted((b or {}).keys()), "
                    "'title': (b or {}).get('title')}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        keys = set(res["keys"])
        allowed = {"id", "title", "description", "owner_id", "created_at"}
        assert keys.issubset(allowed), (
            "transfer response leaked non-public fields: %s" % (keys - allowed)
        )
        for forbidden in ("hashed_password", "owner", "is_superuser",
                          "is_active", "email", "password"):
            assert forbidden not in keys, (
                "transfer response must not expose '%s'" % forbidden
            )
        assert res["title"] == "gadget"

    def test_transfer_nonexistent_item_404(self):
        """Transferring an item that does not exist yields 404."""
        body = (
            "su = _make_user('admin@example.com', True)\n"
            "target = _make_user('target@example.com', False)\n"
            "_act_as(su)\n"
            "m, p = _discover_transfer_route()\n"
            "missing = uuid.uuid4()\n"
            "status, b = _call_transfer(m, p, missing, target)\n"
            + _emit("{'status': status, 'body': b}")
        )
        res = _run_driver(body)
        assert res["status"] == 404, (
            "transfer of a missing item must be 404, got %s body=%s"
            % (res["status"], res["body"])
        )

    def test_transfer_nonexistent_target_404(self):
        """Transferring to a target user that does not exist yields 404."""
        body = (
            "su = _make_user('admin@example.com', True)\n"
            "owner = _make_user('owner@example.com', False)\n"
            "item = _make_item('thing', owner)\n"
            "_act_as(su)\n"
            "m, p = _discover_transfer_route()\n"
            "missing_target = uuid.uuid4()\n"
            "status, b = _call_transfer(m, p, item, missing_target)\n"
            "db_owner = _item_owner(item)\n"
            + _emit("{'status': status, 'body': b, 'db_owner': db_owner, "
                    "'orig': str(owner)}")
        )
        res = _run_driver(body)
        assert res["status"] == 404, (
            "transfer to a missing target user must be 404, got %s body=%s"
            % (res["status"], res["body"])
        )
        # Owner must be untouched on the failure path.
        assert res["db_owner"] == res["orig"], (
            "failed transfer must not change owner_id: db=%s orig=%s"
            % (res["db_owner"], res["orig"])
        )

    def test_transfer_to_same_owner_400(self):
        """Transferring an item to its current owner yields 400."""
        body = (
            "su = _make_user('admin@example.com', True)\n"
            "owner = _make_user('owner@example.com', False)\n"
            "item = _make_item('selfsame', owner)\n"
            "_act_as(su)\n"
            "m, p = _discover_transfer_route()\n"
            "status, b = _call_transfer(m, p, item, owner)\n"
            "db_owner = _item_owner(item)\n"
            + _emit("{'status': status, 'body': b, 'db_owner': db_owner, "
                    "'orig': str(owner)}")
        )
        res = _run_driver(body)
        assert res["status"] == 400, (
            "transfer to the current owner must be 400, got %s body=%s"
            % (res["status"], res["body"])
        )
        assert res["db_owner"] == res["orig"], (
            "same-owner transfer must leave owner_id unchanged"
        )

    def test_transfer_malformed_item_id_422(self):
        """A malformed (non-UUID) item id in the path yields 422."""
        body = (
            "su = _make_user('admin@example.com', True)\n"
            "owner = _make_user('owner@example.com', False)\n"
            "target = _make_user('target@example.com', False)\n"
            "item = _make_item('valid', owner)\n"
            "_act_as(su)\n"
            "m, p = _discover_transfer_route()\n"
            "status, b = _call_transfer(m, p, item, target, "
            "force_raw_item='not-a-valid-uuid')\n"
            + _emit("{'status': status, 'body': b}")
        )
        res = _run_driver(body)
        assert res["status"] == 422, (
            "malformed item id must yield 422 (UUID validation), got %s body=%s"
            % (res["status"], res["body"])
        )

    def test_transfer_forbidden_for_normal_user_403(self):
        """A normal (non-superuser) caller receives 403."""
        body = (
            "normal = _make_user('normal@example.com', False)\n"
            "owner = _make_user('owner@example.com', False)\n"
            "target = _make_user('target@example.com', False)\n"
            "item = _make_item('protected', owner)\n"
            "_act_as(normal)\n"
            "m, p = _discover_transfer_route()\n"
            "status, b = _call_transfer(m, p, item, target)\n"
            "db_owner = _item_owner(item)\n"
            + _emit("{'status': status, 'body': b, 'db_owner': db_owner, "
                    "'orig': str(owner)}")
        )
        res = _run_driver(body)
        assert res["status"] == 403, (
            "a normal user must be forbidden (403), got %s body=%s"
            % (res["status"], res["body"])
        )
        # The transfer must not have happened.
        assert res["db_owner"] == res["orig"], (
            "a forbidden transfer must not change owner_id"
        )

    def test_transfer_unauthenticated_401(self):
        """An unauthenticated caller (no token) receives 401."""
        body = (
            "owner = _make_user('owner@example.com', False)\n"
            "target = _make_user('target@example.com', False)\n"
            "item = _make_item('locked', owner)\n"
            "_act_anonymous()\n"
            "m, p = _discover_transfer_route()\n"
            "status, b = _call_transfer(m, p, item, target)\n"
            + _emit("{'status': status, 'body': b}")
        )
        res = _run_driver(body)
        assert res["status"] == 401, (
            "an unauthenticated caller must get 401, got %s body=%s"
            % (res["status"], res["body"])
        )

    def test_existing_owner_scoped_route_intact(self):
        """The original GET /items/ owner route still requires auth (untouched)."""
        body = (
            "from app.core.config import settings\n"
            "base = settings.API_V1_STR + '/items/'\n"
            "_act_anonymous()\n"
            "r = client.get(base)\n"  # no auth header / no override
            + _emit("{'status': r.status_code}")
        )
        res = _run_driver(body)
        assert res["status"] in (401, 403), (
            "existing owner-scoped GET /items/ must still require auth, got %s"
            % res["status"]
        )

    def test_native_item_tests_pass(self):
        """The repo's own item route tests pass after the agent's changes.

        Drives the doc's native acceptance command. We cannot run the full
        Postgres-backed suite here, so we collect the item-route test module to
        ensure it imports and the agent's added cases are at least valid,
        well-formed tests (collection failures surface broken edits / imports).
        """
        test_file = os.path.join(
            BACKEND_DIR, "tests", "api", "routes", "test_items.py"
        )
        assert os.path.isfile(test_file), "test_items.py missing"
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
             "tests/api/routes/test_items.py",
             "--collect-only", "-q"],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        assert proc.returncode == 0, (
            "collection of test_items.py failed (broken edits/imports?):\n%s"
            % out
        )
        # The agent must have ADDED a transfer-related test case.
        low = out.lower()
        assert "transfer" in low or "owner" in low, (
            "no transfer/owner test case appears in test_items.py collection:\n%s"
            % out
        )
