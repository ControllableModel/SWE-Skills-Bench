"""
Test for the 'fastapi-patterns' skill — Public Service Info Endpoint (ext6).

The task asks the agent to add a PUBLIC (no-auth) service-info endpoint to the
utils router of the full-stack-fastapi-template. The endpoint must return a
structured object shaped by an EXPLICIT response model containing exactly the
agreed named fields:
  * the project name (read from application Settings),
  * the configured environment name (read from Settings),
  * a boolean "healthy" flag that is always true.
It must require NO authentication, perform NO database access, and must NOT
leak any secret or unrelated settings value.

These tests verify the agent's work by EXERCISING the real FastAPI app. The
template is hard-wired to Postgres, but the info endpoint must not touch the
database, so we deliberately point the global engine at a BROKEN/unreachable
database. If the info endpoint still answers 200, it proves no DB query is
performed (a naive copy of the DB-backed health-check would hang/fail).

The service-info route is DISCOVERED dynamically from the OpenAPI schema (a GET
route tagged "utils", reachable WITHOUT auth, whose 200 body is an object that
carries the project name / environment / healthy flag), so the exact path the
agent chose (e.g. /info, /service-info) does not matter. A naive solution that
only edits files, hardcodes the project name/environment instead of reading
Settings, requires auth, hits the DB, or leaks extra settings keys will fail.
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

# Preamble: make `app` importable, satisfy required Settings env vars, and point
# the global engine at an UNREACHABLE Postgres so any accidental DB access from
# the info endpoint would explode. We deliberately DO NOT create tables or
# override get_db: the info endpoint must work with no DB at all.
#
# We choose distinctive, non-default values for PROJECT_NAME and ENVIRONMENT so
# the test can assert the endpoint reflects *Settings* (not a hardcoded string).
_DRIVER_PREAMBLE = r'''
import json, os, sys

# Distinctive settings values so we can prove the payload reflects Settings.
os.environ["ENVIRONMENT"] = "staging"
os.environ["PROJECT_NAME"] = "SkillCheckSvc-XYZ"
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-default")
os.environ.setdefault("FIRST_SUPERUSER", "admin@example.com")
os.environ.setdefault("FIRST_SUPERUSER_PASSWORD", "supersecret123")
# Point at an unreachable DB host so any DB access from /info would fail.
os.environ.setdefault("POSTGRES_SERVER", "10.255.255.1")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "supersecret123")
os.environ.setdefault("POSTGRES_DB", "app")

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def _discover_info_route():
    """Return the path of the public service-info GET route, or None.

    Criteria: a GET path tagged "utils", with no path parameters, that is NOT
    the existing health-check (which returns a bare boolean), reachable WITHOUT
    auth (200), whose JSON body is a dict carrying the project name and the
    environment plus a boolean flag.
    """
    schema = app.openapi()
    proj = settings.PROJECT_NAME
    env = settings.ENVIRONMENT
    candidates = []
    for path, methods in schema.get("paths", {}).items():
        spec = methods.get("get")
        if not spec:
            continue
        if "utils" not in spec.get("tags", []):
            continue
        if "{" in path:
            continue
        candidates.append(path)

    best = None
    for path in candidates:
        try:
            r = client.get(path)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        try:
            body = r.json()
        except Exception:
            continue
        if not isinstance(body, dict):
            continue
        vals = list(body.values())
        has_proj = proj in vals
        has_env = env in vals
        has_bool_true = any(v is True for v in vals)
        if has_proj and has_env and has_bool_true:
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
    """Verify the public service-info endpoint on the utils router."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist and are minimally well-formed.
    # ------------------------------------------------------------------ #

    def test_utils_route_file_present(self):
        """backend/app/api/routes/utils.py must exist (the router to extend)."""
        p = os.path.join(BACKEND_DIR, "app", "api", "routes", "utils.py")
        assert os.path.isfile(p), "utils.py route module missing"

    def test_models_file_present(self):
        """backend/app/models.py must exist (the response model lives here)."""
        p = os.path.join(BACKEND_DIR, "app", "models.py")
        assert os.path.isfile(p), "models.py missing"

    def test_utils_test_file_present(self):
        """backend/tests/api/routes/test_utils.py must be created by the agent."""
        p = os.path.join(BACKEND_DIR, "tests", "api", "routes", "test_utils.py")
        assert os.path.isfile(p), "tests/api/routes/test_utils.py missing"

    def test_app_imports_and_utils_router_registered(self):
        """The FastAPI app imports cleanly and exposes GET routes tagged utils."""
        body = (
            "schema = app.openapi()\n"
            "utils_get = [p for p, m in schema['paths'].items()\n"
            "             if 'utils' in m.get('get', {}).get('tags', [])]\n"
            + _emit("{'utils_get_paths': sorted(utils_get)}")
        )
        res = _run_driver(body)
        # Original health-check plus the new info route -> at least 2.
        assert len(res["utils_get_paths"]) >= 2, (
            "expected health-check + new info GET routes tagged 'utils', got %s"
            % res["utils_get_paths"]
        )

    def test_info_route_discoverable(self):
        """A public (no-auth) service-info route is discoverable on utils."""
        body = (
            "info = _discover_info_route()\n"
            + _emit("{'info': info}")
        )
        res = _run_driver(body)
        assert res["info"], (
            "no public service-info route (project name + environment + "
            "healthy:true, reachable without auth) found on the utils router"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavioral validation of the info endpoint.
    # ------------------------------------------------------------------ #

    def test_info_returns_settings_values(self):
        """Payload reflects Settings.PROJECT_NAME and ENVIRONMENT, not hardcoded."""
        body = (
            "info = _discover_info_route()\n"
            "assert info, 'no info route discovered'\n"
            "r = client.get(info)\n"
            "b = r.json()\n"
            + _emit("{'status': r.status_code, 'body': b, "
                    "'proj': settings.PROJECT_NAME, 'env': settings.ENVIRONMENT, "
                    "'vals': list(b.values()) if isinstance(b, dict) else None}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert isinstance(res["body"], dict), "info body must be a JSON object"
        # The driver set PROJECT_NAME=SkillCheckSvc-XYZ, ENVIRONMENT=staging.
        assert res["proj"] == "SkillCheckSvc-XYZ", res
        assert res["env"] == "staging", res
        # Endpoint must echo the *Settings* values, proving it reads settings.
        assert res["proj"] in res["vals"], (
            "project name from Settings (%s) not present in info payload %s"
            % (res["proj"], res["body"])
        )
        assert res["env"] in res["vals"], (
            "environment from Settings (%s) not present in info payload %s"
            % (res["env"], res["body"])
        )

    def test_info_healthy_flag_is_true(self):
        """The payload carries a boolean healthy flag whose value is True."""
        body = (
            "info = _discover_info_route()\n"
            "assert info, 'no info route discovered'\n"
            "r = client.get(info)\n"
            "b = r.json()\n"
            "bool_keys = [k for k, v in b.items() if isinstance(v, bool)]\n"
            "true_keys = [k for k, v in b.items() if v is True]\n"
            + _emit("{'status': r.status_code, 'bool_keys': bool_keys, "
                    "'true_keys': true_keys, 'body': b}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, res
        assert res["bool_keys"], (
            "info payload must contain a boolean healthy flag, got %s" % res["body"]
        )
        assert res["true_keys"], (
            "the healthy boolean flag must be True, got %s" % res["body"]
        )

    def test_info_requires_no_auth(self):
        """The info endpoint must answer 200 with NO Authorization header."""
        body = (
            "info = _discover_info_route()\n"
            "assert info, 'no info route discovered'\n"
            "# Explicitly send no headers / no token.\n"
            "r = client.get(info)\n"
            "# Sanity: with a clearly bogus token it must still not be a 401/403\n"
            "r2 = client.get(info, headers={'Authorization': 'Bearer not-a-real-token'})\n"
            + _emit("{'status': r.status_code, 'status_bogus': r2.status_code}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, (
            "public info endpoint should not require auth, got %s" % res["status"]
        )
        # A bogus token must not flip it into an auth-protected 401/403.
        assert res["status_bogus"] not in (401, 403), (
            "info endpoint appears auth-gated (got %s with bogus token)"
            % res["status_bogus"]
        )

    def test_info_does_not_touch_database(self):
        """Info answers 200 even with an UNREACHABLE DB (no DB query performed).

        The driver preamble points POSTGRES_SERVER at a black-hole IP. If the
        endpoint tried any DB access it would hang or raise. A 200 here proves
        it only reflects in-process settings.
        """
        body = (
            "info = _discover_info_route()\n"
            "assert info, 'no info route discovered'\n"
            "r = client.get(info)\n"
            + _emit("{'status': r.status_code}")
        )
        # Short timeout: a DB-hitting impl against a black-hole IP would stall.
        res = _run_driver(body, timeout=120)
        assert res["status"] == 200, (
            "info endpoint must work without a reachable DB, got %s" % res["status"]
        )

    def test_info_exact_field_set_no_extras(self):
        """Response is shaped by a model: exactly the agreed fields, no extras.

        The payload must contain the project name, environment, and a healthy
        boolean — and nothing else. We allow a small, principled superset of
        named fields but cap the total so a naive `return settings` style dump
        (dozens of keys) fails.
        """
        body = (
            "info = _discover_info_route()\n"
            "assert info, 'no info route discovered'\n"
            "r = client.get(info)\n"
            "b = r.json()\n"
            + _emit("{'keys': sorted(b.keys()), 'n': len(b.keys()), 'body': b}")
        )
        res = _run_driver(body)
        keys = res["keys"]
        # Exactly the three agreed pieces of data -> a tightly bounded object.
        assert 3 <= res["n"] <= 4, (
            "info payload should expose exactly the agreed named fields "
            "(project name, environment, healthy flag); got %d keys: %s"
            % (res["n"], keys)
        )

    def test_info_does_not_leak_secrets(self):
        """No secret or unrelated settings value appears in the payload."""
        body = (
            "info = _discover_info_route()\n"
            "assert info, 'no info route discovered'\n"
            "r = client.get(info)\n"
            "b = r.json()\n"
            "# Stringify the whole payload to scan for leaked secret VALUES.\n"
            "blob = json.dumps(b)\n"
            "secret_key = settings.SECRET_KEY\n"
            "pg_pw = settings.POSTGRES_PASSWORD\n"
            "su_pw = settings.FIRST_SUPERUSER_PASSWORD\n"
            "leaked = {\n"
            "  'secret_key': secret_key in blob,\n"
            "  'postgres_password': bool(pg_pw) and pg_pw in blob,\n"
            "  'superuser_password': bool(su_pw) and su_pw in blob,\n"
            "  'db_uri': 'postgresql' in blob.lower(),\n"
            "}\n"
            "leaked_keys = sorted(k for k, v in b.items()\n"
            "    if 'password' in k.lower() or 'secret' in k.lower()\n"
            "    or 'token' in k.lower())\n"
            + _emit("{'leaked': leaked, 'suspicious_keys': leaked_keys, 'body': b}")
        )
        res = _run_driver(body)
        leaked = res["leaked"]
        assert not leaked["secret_key"], "SECRET_KEY value leaked into info payload"
        assert not leaked["postgres_password"], (
            "POSTGRES_PASSWORD value leaked into info payload"
        )
        assert not leaked["superuser_password"], (
            "FIRST_SUPERUSER_PASSWORD value leaked into info payload"
        )
        assert not leaked["db_uri"], "a database URI leaked into info payload"
        assert not res["suspicious_keys"], (
            "info payload exposes secret-like fields: %s" % res["suspicious_keys"]
        )

    def test_info_reflects_changed_settings(self):
        """Changing Settings changes the payload — proves it is not hardcoded.

        Re-run the driver with a DIFFERENT project name + environment and assert
        the payload tracks the new values rather than a baked-in constant.
        """
        body = (
            "# Override the distinctive values BEFORE importing settings would be\n"
            "# too late (already imported in preamble); instead mutate the loaded\n"
            "# settings object the endpoint reads from.\n"
            "settings.PROJECT_NAME = 'AltName-QQ'\n"
            "settings.ENVIRONMENT = 'production'\n"
            "info = _discover_info_route()\n"
            "# discovery used the new values, so a match means the endpoint reads\n"
            "# live settings; fall back to a direct call if discovery missed.\n"
            "if not info:\n"
            "    info = None\n"
            "    schema = app.openapi()\n"
            "    for p, m in schema['paths'].items():\n"
            "        spec = m.get('get')\n"
            "        if spec and 'utils' in spec.get('tags', []) and '{' not in p:\n"
            "            rr = client.get(p)\n"
            "            if rr.status_code == 200 and isinstance(rr.json(), dict):\n"
            "                bb = rr.json()\n"
            "                if 'AltName-QQ' in bb.values():\n"
            "                    info = p\n"
            "                    break\n"
            "r = client.get(info) if info else None\n"
            "b = r.json() if r is not None else {}\n"
            + _emit("{'found': bool(info), 'vals': list(b.values()), 'body': b}")
        )
        res = _run_driver(body)
        assert res["found"], (
            "info route did not reflect changed Settings; payload looks hardcoded"
        )
        assert "AltName-QQ" in res["vals"], (
            "changed project name not reflected in payload: %s" % res["body"]
        )
        assert "production" in res["vals"], (
            "changed environment not reflected in payload: %s" % res["body"]
        )

    def test_existing_health_check_intact(self):
        """The original GET /utils/health-check/ still returns bare true."""
        body = (
            "from app.core.config import settings as s\n"
            "path = s.API_V1_STR + '/utils/health-check/'\n"
            "r = client.get(path)\n"
            + _emit("{'status': r.status_code, 'body': r.json()}")
        )
        res = _run_driver(body)
        assert res["status"] == 200, (
            "existing health-check must remain reachable, got %s" % res["status"]
        )
        assert res["body"] is True, (
            "existing health-check must still return bare true, got %r"
            % (res["body"],)
        )

    def test_test_email_route_still_superuser_only(self):
        """The pre-existing POST /utils/test-email/ stays superuser-gated."""
        body = (
            "from app.core.config import settings as s\n"
            "path = s.API_V1_STR + '/utils/test-email/'\n"
            "r = client.post(path, params={'email_to': 'x@example.com'})\n"
            + _emit("{'status': r.status_code}")
        )
        res = _run_driver(body)
        # No token -> must not be allowed through (401/403).
        assert res["status"] in (401, 403), (
            "existing superuser-only test-email route must stay protected, got %s"
            % res["status"]
        )

    def test_agent_test_file_passes_native(self):
        """The agent's own backend/tests/api/routes/test_utils.py passes.

        Drives the doc's native acceptance command with pytest. We run it with
        the same in-repo conftest and require a clean exit. This is an
        additional, independent signal layered on top of our own harness checks.
        """
        test_rel = os.path.join("tests", "api", "routes", "test_utils.py")
        test_abs = os.path.join(BACKEND_DIR, test_rel)
        if not os.path.isfile(test_abs):
            pytest.fail("agent did not create %s" % test_rel)
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
            [sys.executable, "-m", "pytest", test_rel, "-q",
             "-k", "info or service or Info"],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        combined = proc.stdout + "\n" + proc.stderr
        # Exit code 5 == "no tests collected" by the -k filter: tolerate that,
        # since our own harness already validates the behavior. Any real test
        # failure (exit 1) must fail this case.
        assert proc.returncode in (0, 5), (
            "agent's test_utils.py info tests failed:\n%s" % combined[-4000:]
        )
