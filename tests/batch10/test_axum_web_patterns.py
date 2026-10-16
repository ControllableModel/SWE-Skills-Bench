"""
Test for 'axum-web-patterns' skill (variant ext10) — team-invite HTTP API in
shuttle-common that accepts FORM bodies on create and returns JSON on read.

The task asks the agent to add `common/src/invites_api.rs` exposing
`pub fn router() -> axum::Router`, gated behind the `axum` feature (and using the
`models` feature's `TeamRole`). The store keeps at most one invite per
`(team, email)` pair and produces `ApiError`-shaped JSON error bodies. Routes:

    POST /teams/{team}/invites          (application/x-www-form-urlencoded)
    GET  /teams/{team}/invites          -> {"invites":[{"email","role"},...]}  (email asc)
    GET  /teams/{team}/invites/{email}  -> {"email","role"}

Distinctive contract points (vs. the ext1 secrets task):
  * create consumes a FORM body (email, role); raw JSON for create must be 400
  * `role` must round-trip through the real `TeamRole` enum; unknown role -> 400
  * create-new -> 201; replace same (team,email) -> 200 and no duplicate entry
  * team scoping: an email under team `a` must read 404 under team `b`
  * list is email-ascending, scoped to one team, [] when empty

Verification strategy
---------------------
We do NOT trust the agent's own `common/tests/invites_api.rs`. For the L2
behavioral checks, this harness injects an *independent* Rust integration test
(`tests/_invites_api_verify.rs`) that imports the real `router()`, drives it
fully in-process with `tower::ServiceExt::oneshot` (no TCP), sends real
form-encoded / JSON bodies, and asserts every acceptance scenario with concrete
status codes and JSON fields. We add the required dev-dependencies ourselves so
the checks do not depend on what the agent wrote into Cargo.toml. Each L2 pytest
method runs one named Rust test and asserts it passes, mapping 1:1 to a
requirement.

Native command of record:
    cargo test -p shuttle-common --features axum,models --test invites_api
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/shuttle"
COMMON_DIR = os.path.join(REPO_DIR, "common")
INVITES_API_SRC = os.path.join(COMMON_DIR, "src", "invites_api.rs")
LIB_RS = os.path.join(COMMON_DIR, "src", "lib.rs")
AGENT_TEST = os.path.join(COMMON_DIR, "tests", "invites_api.rs")
CARGO_TOML = os.path.join(COMMON_DIR, "Cargo.toml")

VERIFY_TEST_NAME = "_invites_api_verify"
VERIFY_TEST_PATH = os.path.join(COMMON_DIR, "tests", VERIFY_TEST_NAME + ".rs")

# Both features are required: the module is gated on `axum` and uses `TeamRole`
# from the `models` feature.
FEATURES = "axum,models"

BUILD_TIMEOUT = 900
RUN_TIMEOUT = 900


# ---------------------------------------------------------------------------
# Independent in-process Rust integration test injected into the repo.
# It only depends on the public surface: `shuttle_common::invites_api::router()`.
# It builds requests by hand (no axum::Form needed in the test crate itself),
# sending form-encoded and JSON bodies via tower oneshot.
# ---------------------------------------------------------------------------
VERIFY_RS = r'''
// AUTO-GENERATED independent verification test for the axum-web-patterns task
// (ext10 variant: team-invite form API). Drives `router()` fully in-process
// (no socket) via tower oneshot.
#![cfg(all(feature = "axum", feature = "models"))]

use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt; // for `oneshot`

use shuttle_common::invites_api::router;

/// Send a request. `ctype` selects the Content-Type header (None -> no body).
async fn send(
    app: axum::Router,
    method: &str,
    uri: &str,
    ctype: Option<&str>,
    body: Option<&str>,
) -> (StatusCode, Vec<u8>) {
    let mut builder = Request::builder().method(method).uri(uri);
    let req = match body {
        Some(b) => {
            if let Some(ct) = ctype {
                builder = builder.header("content-type", ct);
            }
            builder.body(Body::from(b.to_owned())).unwrap()
        }
        None => builder.body(Body::empty()).unwrap(),
    };
    let resp = app.oneshot(req).await.unwrap();
    let status = resp.status();
    let bytes = resp.into_body().collect().await.unwrap().to_bytes().to_vec();
    (status, bytes)
}

/// POST a urlencoded form body.
async fn post_form(app: axum::Router, uri: &str, form: &str) -> (StatusCode, Vec<u8>) {
    send(
        app,
        "POST",
        uri,
        Some("application/x-www-form-urlencoded"),
        Some(form),
    )
    .await
}

async fn get(app: axum::Router, uri: &str) -> (StatusCode, Vec<u8>) {
    send(app, "GET", uri, None, None).await
}

fn json(bytes: &[u8]) -> Value {
    serde_json::from_slice(bytes).expect("response body must be valid JSON")
}

#[tokio::test]
async fn create_from_form_then_read() {
    let app = router();
    let (s, _) = post_form(app.clone(), "/teams/acme/invites", "email=a@x.com&role=admin").await;
    assert_eq!(s, StatusCode::CREATED, "first form POST with valid role must be 201 Created");

    let (s, b) = get(app.clone(), "/teams/acme/invites/a@x.com").await;
    assert_eq!(s, StatusCode::OK, "read of created invite must be 200");
    let v = json(&b);
    assert_eq!(v["email"], "a@x.com", "read body must echo the email");
    assert_eq!(v["role"], "admin", "read body must echo the role lowercase");
    assert!(v.get("email").is_some() && v.get("role").is_some());
}

#[tokio::test]
async fn replace_updates_role_and_status() {
    let app = router();
    let (s, _) = post_form(app.clone(), "/teams/t/invites", "email=u@x.com&role=member").await;
    assert_eq!(s, StatusCode::CREATED, "first POST 201");

    // Second POST to same (team, email) with a different valid role.
    let (s, _) = post_form(app.clone(), "/teams/t/invites", "email=u@x.com&role=owner").await;
    assert_eq!(s, StatusCode::OK, "replace must be 200, not 201");

    let (s, b) = get(app.clone(), "/teams/t/invites/u@x.com").await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(json(&b)["role"], "owner", "read must reflect the replaced role");

    // Exactly one entry for that pair -> list length 1.
    let (s, b) = get(app.clone(), "/teams/t/invites").await;
    assert_eq!(s, StatusCode::OK);
    let arr = json(&b)["invites"].as_array().unwrap().clone();
    assert_eq!(arr.len(), 1, "replace must not duplicate the (team,email) entry");
    assert_eq!(arr[0]["email"], "u@x.com");
    assert_eq!(arr[0]["role"], "owner");
}

#[tokio::test]
async fn invalid_role_is_400_and_no_mutation() {
    let app = router();
    let (s, _) = post_form(app.clone(), "/teams/t/invites", "email=u@x.com&role=superuser").await;
    assert_eq!(s, StatusCode::BAD_REQUEST, "an unknown TeamRole must be rejected with 400");

    // Nothing must have been stored.
    let (s, _) = get(app.clone(), "/teams/t/invites/u@x.com").await;
    assert_eq!(s, StatusCode::NOT_FOUND, "an invalid role must store nothing");

    let (s, b) = get(app.clone(), "/teams/t/invites").await;
    assert_eq!(s, StatusCode::OK);
    assert!(
        json(&b)["invites"].as_array().unwrap().is_empty(),
        "list must stay empty after a rejected create"
    );
}

#[tokio::test]
async fn missing_field_is_400_and_no_mutation() {
    // Missing role.
    {
        let app = router();
        let (s, _) = post_form(app.clone(), "/teams/t/invites", "email=u@x.com").await;
        assert_eq!(s, StatusCode::BAD_REQUEST, "missing `role` -> 400");
        let (s, _) = get(app.clone(), "/teams/t/invites/u@x.com").await;
        assert_eq!(s, StatusCode::NOT_FOUND, "rejected create must store nothing");
    }
    // Missing email.
    {
        let app = router();
        let (s, _) = post_form(app.clone(), "/teams/t/invites", "role=admin").await;
        assert_eq!(s, StatusCode::BAD_REQUEST, "missing `email` -> 400");
        let (s, b) = get(app.clone(), "/teams/t/invites").await;
        assert_eq!(s, StatusCode::OK);
        assert!(json(&b)["invites"].as_array().unwrap().is_empty());
    }
}

#[tokio::test]
async fn json_create_is_rejected() {
    // The create handler must consume a FORM body; raw JSON must be rejected.
    let app = router();
    let (s, _) = send(
        app.clone(),
        "POST",
        "/teams/t/invites",
        Some("application/json"),
        Some(r#"{"email":"u@x.com","role":"admin"}"#),
    )
    .await;
    assert_eq!(
        s,
        StatusCode::BAD_REQUEST,
        "a create sent as JSON (not form-encoded) must be rejected with 400"
    );
    // And it must not have stored anything.
    let (s, _) = get(app.clone(), "/teams/t/invites/u@x.com").await;
    assert_eq!(s, StatusCode::NOT_FOUND, "JSON create must store nothing");
}

#[tokio::test]
async fn read_missing_is_404_with_message() {
    let app = router();
    let (s, b) = get(app.clone(), "/teams/nope/invites/ghost@x.com").await;
    assert_eq!(s, StatusCode::NOT_FOUND, "unknown (team,email) must be 404");
    let v = json(&b);
    assert!(v.get("message").is_some(), "404 body must carry a `message` field (ApiError shape)");
    assert!(
        v["message"].as_str().map(|m| !m.is_empty()).unwrap_or(false),
        "message must be a non-empty human-readable string"
    );
}

#[tokio::test]
async fn team_scoping_on_read() {
    let app = router();
    let (s, _) = post_form(app.clone(), "/teams/a/invites", "email=shared@x.com&role=member").await;
    assert_eq!(s, StatusCode::CREATED);

    // Same email, different team -> still missing.
    let (s, _) = get(app.clone(), "/teams/b/invites/shared@x.com").await;
    assert_eq!(s, StatusCode::NOT_FOUND, "invite under team a must not leak into team b");

    // Original still readable under its own team.
    let (s, b) = get(app.clone(), "/teams/a/invites/shared@x.com").await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(json(&b)["role"], "member");
}

#[tokio::test]
async fn list_empty_ordered_and_scoped() {
    let app = router();

    // Empty team.
    let (s, b) = get(app.clone(), "/teams/empty/invites").await;
    assert_eq!(s, StatusCode::OK);
    assert!(
        json(&b)["invites"].as_array().unwrap().is_empty(),
        "an empty team must list {{\"invites\":[]}}"
    );

    // Insert out of email order; also insert into another team that must not appear.
    post_form(app.clone(), "/teams/team1/invites", "email=charlie@x.com&role=member").await;
    post_form(app.clone(), "/teams/team1/invites", "email=alice@x.com&role=admin").await;
    post_form(app.clone(), "/teams/team1/invites", "email=bob@x.com&role=owner").await;
    post_form(app.clone(), "/teams/other/invites", "email=zzz@x.com&role=member").await;

    let (s, b) = get(app.clone(), "/teams/team1/invites").await;
    assert_eq!(s, StatusCode::OK);
    let arr = json(&b)["invites"].as_array().unwrap().clone();
    let emails: Vec<String> = arr
        .iter()
        .map(|e| e["email"].as_str().unwrap().to_string())
        .collect();
    assert_eq!(
        emails,
        vec!["alice@x.com", "bob@x.com", "charlie@x.com"],
        "list must be email-ascending and scoped to the team"
    );
    assert_eq!(arr.len(), 3, "invites from other teams must not appear");
    // roles travel with their emails
    assert_eq!(arr[0]["role"], "admin");
    assert_eq!(arr[1]["role"], "owner");
    assert_eq!(arr[2]["role"], "member");
}

#[tokio::test]
async fn instances_are_independent() {
    let a = router();
    let b = router();
    post_form(a.clone(), "/teams/p/invites", "email=u@x.com&role=member").await;
    // b is a fresh, empty, independent instance.
    let (s, _) = get(b.clone(), "/teams/p/invites/u@x.com").await;
    assert_eq!(s, StatusCode::NOT_FOUND, "each router() must own an independent empty store");
}
'''


# ---------------------------------------------------------------------------
# Fixtures: inject the verification test + dev-deps once for the module.
# ---------------------------------------------------------------------------
def _cargo_env():
    env = dict(os.environ)
    env["CARGO_TERM_COLOR"] = "never"
    return env


def _dev_dependencies_block(content):
    """Return (start_idx, end_idx) of the body of the [dev-dependencies] table,
    or (None, None) if absent. The body excludes the header line itself."""
    m = re.search(r"(?m)^\[dev-dependencies\]\s*$", content)
    if not m:
        return None, None
    body_start = m.end()
    nxt = re.search(r"(?m)^\[", content[body_start:])
    body_end = body_start + nxt.start() if nxt else len(content)
    return body_start, body_end


def _ensure_dev_deps():
    """Add dev-deps needed by the injected verification test, idempotently.

    We pin versions already present in the workspace Cargo.lock so resolution
    works offline. We only ever add a key that is not already present *inside the
    [dev-dependencies] table*, so we never create a duplicate-key TOML error even
    if the same crate exists under [dependencies].
    """
    with open(CARGO_TOML, "r") as f:
        content = f.read()

    needed = {
        "tower": 'tower = { version = "0.5", features = ["util"] }',
        "http-body-util": 'http-body-util = "0.1"',
        "tokio": 'tokio = { version = "1", features = ["macros", "rt"] }',
        "serde_json": 'serde_json = "1"',
    }

    body_start, body_end = _dev_dependencies_block(content)
    dev_body = content[body_start:body_end] if body_start is not None else ""

    additions = []
    for name, line in needed.items():
        present = re.search(r"(?m)^\s*" + re.escape(name) + r"\s*=", dev_body)
        if not present:
            additions.append(line)

    if not additions:
        return

    block = "\n".join(additions) + "\n"
    if body_start is not None:
        content = content[:body_start] + "\n" + block + content[body_start:]
    else:
        content = content.rstrip() + "\n\n[dev-dependencies]\n" + block

    with open(CARGO_TOML, "w") as f:
        f.write(content)


@pytest.fixture(scope="module", autouse=True)
def _setup_verification():
    assert os.path.isdir(REPO_DIR), f"repo not found at {REPO_DIR}"
    assert os.path.isdir(COMMON_DIR), f"common crate not found at {COMMON_DIR}"
    os.makedirs(os.path.join(COMMON_DIR, "tests"), exist_ok=True)
    _ensure_dev_deps()
    with open(VERIFY_TEST_PATH, "w") as f:
        f.write(VERIFY_RS)
    yield
    # best-effort cleanup of injected test file
    try:
        os.remove(VERIFY_TEST_PATH)
    except OSError:
        pass


def _run_verify(test_name):
    """Compile + run one named test from the injected verification harness."""
    cmd = [
        "cargo", "test",
        "-p", "shuttle-common",
        "--features", FEATURES,
        "--test", VERIFY_TEST_NAME,
        "--", "--exact", test_name,
    ]
    proc = subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT,
        env=_cargo_env(),
    )
    return proc


def _assert_test_passed(proc, test_name):
    out = proc.stdout + "\n" + proc.stderr
    assert proc.returncode == 0, (
        f"verification test `{test_name}` did not pass.\n"
        f"--- cargo output (tail) ---\n{out[-4000:]}"
    )
    # cargo prints "test result: ok. 1 passed" when the named test ran & passed
    assert "test result: ok." in out, f"cargo did not report ok for `{test_name}`:\n{out[-2000:]}"
    assert "0 passed" not in out, f"the named test `{test_name}` did not actually run:\n{out[-2000:]}"


class TestAxumWebPatterns:
    """Verify the in-memory team-invite (form-create / JSON-read) API in shuttle-common."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_invites_api_source_exists(self):
        """common/src/invites_api.rs must exist and be non-trivial."""
        assert os.path.isfile(INVITES_API_SRC), "common/src/invites_api.rs not created"
        assert os.path.getsize(INVITES_API_SRC) > 200, "invites_api.rs is implausibly small"

    def test_router_constructor_declared(self):
        """invites_api.rs must declare a public `fn router() -> ... Router`."""
        with open(INVITES_API_SRC) as f:
            src = f.read()
        assert re.search(r"pub\s+fn\s+router\s*\(", src), "no `pub fn router(` constructor found"
        assert re.search(r"Router", src), "router() must build an axum Router"

    def test_uses_team_role(self):
        """The role must round-trip through the existing TeamRole enum."""
        with open(INVITES_API_SRC) as f:
            src = f.read()
        assert "TeamRole" in src, "implementation must use the crate's TeamRole enum for the role"

    def test_module_declared_gated_in_lib(self):
        """lib.rs must declare `invites_api` gated behind the axum feature."""
        with open(LIB_RS) as f:
            lib = f.read()
        assert "invites_api" in lib, "lib.rs does not declare the invites_api module"
        # the declaration must be feature-gated; at minimum it must reference the axum feature.
        m = re.search(
            r'#\[cfg\([^\)]*feature\s*=\s*"axum"[^\)]*\)\]\s*pub\s+mod\s+invites_api',
            lib,
        )
        assert m is not None, 'module `invites_api` must be #[cfg(... feature = "axum" ...)]-gated'

    def test_agent_integration_test_exists(self):
        """The agent's own in-process integration test must exist and drive router()."""
        assert os.path.isfile(AGENT_TEST), "common/tests/invites_api.rs not created"
        with open(AGENT_TEST) as f:
            t = f.read()
        assert "router" in t, "agent test does not appear to drive router()"

    # ------------------------------------------------------------------
    # L2: feature gating builds + independent behavioral verification
    # ------------------------------------------------------------------

    def test_builds_without_axum_feature(self):
        """The crate must still build with the axum feature OFF (module fully gated)."""
        proc = subprocess.run(
            ["cargo", "build", "-p", "shuttle-common", "--no-default-features"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=BUILD_TIMEOUT, env=_cargo_env(),
        )
        out = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, (
            "shuttle-common must compile without the axum feature; the new module "
            f"must be fully gated.\n{out[-3000:]}"
        )

    def test_agent_native_test_command_passes(self):
        """The exact acceptance command must pass: cargo test ... --test invites_api."""
        proc = subprocess.run(
            ["cargo", "test", "-p", "shuttle-common", "--features", FEATURES, "--test", "invites_api"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=RUN_TIMEOUT, env=_cargo_env(),
        )
        out = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, f"acceptance command failed:\n{out[-4000:]}"
        assert "test result: ok." in out, f"acceptance test did not report ok:\n{out[-2000:]}"

    def test_create_from_form_then_read(self):
        """Form POST valid role -> 201; GET -> 200 with {email,role} echoing the form."""
        _assert_test_passed(_run_verify("create_from_form_then_read"), "create_from_form_then_read")

    def test_replace_updates_role_and_status(self):
        """Second form POST to same (team,email) -> 200 (not 201), role updated, no duplicate."""
        _assert_test_passed(
            _run_verify("replace_updates_role_and_status"),
            "replace_updates_role_and_status",
        )

    def test_invalid_role_is_400_and_no_mutation(self):
        """A role that is not a valid TeamRole -> 400 and nothing is stored."""
        _assert_test_passed(
            _run_verify("invalid_role_is_400_and_no_mutation"),
            "invalid_role_is_400_and_no_mutation",
        )

    def test_missing_field_is_400_and_no_mutation(self):
        """A form POST missing email or role -> 400 and nothing is stored."""
        _assert_test_passed(
            _run_verify("missing_field_is_400_and_no_mutation"),
            "missing_field_is_400_and_no_mutation",
        )

    def test_json_create_is_rejected(self):
        """A create sent as raw JSON instead of form-encoding -> 400, stores nothing."""
        _assert_test_passed(_run_verify("json_create_is_rejected"), "json_create_is_rejected")

    def test_read_missing_is_404_with_message(self):
        """GET unknown (team,email) -> 404 with an ApiError-shaped JSON `message` field."""
        _assert_test_passed(
            _run_verify("read_missing_is_404_with_message"),
            "read_missing_is_404_with_message",
        )

    def test_team_scoping_on_read(self):
        """An invite created under team a must read 404 under team b."""
        _assert_test_passed(_run_verify("team_scoping_on_read"), "team_scoping_on_read")

    def test_list_empty_ordered_and_scoped(self):
        """List: {"invites":[]} when empty; email-ascending and scoped to one team otherwise."""
        _assert_test_passed(
            _run_verify("list_empty_ordered_and_scoped"),
            "list_empty_ordered_and_scoped",
        )

    def test_instances_are_independent(self):
        """Each router() call owns an independent, initially-empty store."""
        _assert_test_passed(_run_verify("instances_are_independent"), "instances_are_independent")
