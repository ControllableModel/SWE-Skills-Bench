"""
Test for 'axum-web-patterns' skill — in-memory secrets HTTP API in shuttle-common.

The task asks the agent to add `common/src/secrets_api.rs` exposing
`pub fn router() -> axum::Router`, gated behind the `axum` feature, backed by an
in-memory store that wraps values in the crate's `Secret` type and produces
`ApiError`-shaped JSON error bodies. Routes:

    GET    /projects/{project}/secrets
    PUT    /projects/{project}/secrets/{key}
    GET    /projects/{project}/secrets/{key}
    DELETE /projects/{project}/secrets/{key}

Verification strategy
---------------------
We do NOT trust the agent's own `common/tests/secrets_api.rs`. Instead, for the
L2 behavioral checks, this harness injects an *independent* Rust integration
test (`tests/_secrets_api_verify.rs`) that imports the real `router()`, drives it
fully in-process with `tower::ServiceExt::oneshot` (no TCP), and asserts every
acceptance scenario. We add the required dev-dependencies ourselves so the checks
do not depend on what the agent put in `Cargo.toml`. Each L2 pytest method runs
one named Rust test and asserts it passes, mapping 1:1 to a requirement.

Native command of record:
    cargo test -p shuttle-common --features axum --test secrets_api
"""

import os
import re
import shutil
import subprocess

import pytest

REPO_DIR = "/workspace/shuttle"
COMMON_DIR = os.path.join(REPO_DIR, "common")
SECRETS_API_SRC = os.path.join(COMMON_DIR, "src", "secrets_api.rs")
LIB_RS = os.path.join(COMMON_DIR, "src", "lib.rs")
AGENT_TEST = os.path.join(COMMON_DIR, "tests", "secrets_api.rs")
CARGO_TOML = os.path.join(COMMON_DIR, "Cargo.toml")

VERIFY_TEST_NAME = "_secrets_api_verify"
VERIFY_TEST_PATH = os.path.join(COMMON_DIR, "tests", VERIFY_TEST_NAME + ".rs")

BUILD_TIMEOUT = 600
RUN_TIMEOUT = 600


# ---------------------------------------------------------------------------
# Independent in-process Rust integration test injected into the repo.
# It only depends on the public surface: `shuttle_common::secrets_api::router()`.
# ---------------------------------------------------------------------------
VERIFY_RS = r'''
// AUTO-GENERATED independent verification test for the axum-web-patterns task.
// Drives `router()` fully in-process (no socket) via tower oneshot.
#![cfg(feature = "axum")]

use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt; // for `oneshot`

use shuttle_common::secrets_api::router;

async fn call(
    app: axum::Router,
    method: &str,
    uri: &str,
    body: Option<&str>,
) -> (StatusCode, Vec<u8>) {
    let mut builder = Request::builder().method(method).uri(uri);
    let req = if let Some(b) = body {
        builder = builder.header("content-type", "application/json");
        builder.body(Body::from(b.to_owned())).unwrap()
    } else {
        builder.body(Body::empty()).unwrap()
    };
    let resp = app.oneshot(req).await.unwrap();
    let status = resp.status();
    let bytes = resp.into_body().collect().await.unwrap().to_bytes().to_vec();
    (status, bytes.to_vec())
}

fn json(bytes: &[u8]) -> Value {
    serde_json::from_slice(bytes).expect("response body must be valid JSON")
}

#[tokio::test]
async fn create_then_read() {
    let app = router();
    let (s, _) = call(app.clone(), "PUT", "/projects/alpha/secrets/TOKEN", Some(r#"{"value":"abc"}"#)).await;
    assert_eq!(s, StatusCode::CREATED, "first PUT must be 201 Created");

    let (s, b) = call(app.clone(), "GET", "/projects/alpha/secrets/TOKEN", None).await;
    assert_eq!(s, StatusCode::OK, "read of created secret must be 200");
    let v = json(&b);
    assert_eq!(v["key"], "TOKEN", "read body must echo key");
    assert_eq!(v["value"], "abc", "read body must echo value");
    // Exactly the two fields, nothing extra structural that breaks the contract.
    assert!(v.get("key").is_some() && v.get("value").is_some());
}

#[tokio::test]
async fn replace_updates_value_and_status() {
    let app = router();
    let (s, _) = call(app.clone(), "PUT", "/projects/p/secrets/K", Some(r#"{"value":"v1"}"#)).await;
    assert_eq!(s, StatusCode::CREATED, "first PUT 201");

    let (s, _) = call(app.clone(), "PUT", "/projects/p/secrets/K", Some(r#"{"value":"v2"}"#)).await;
    assert_eq!(s, StatusCode::OK, "second PUT (replace) must be 200, not 201");

    let (s, b) = call(app.clone(), "GET", "/projects/p/secrets/K", None).await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(json(&b)["value"], "v2", "read must reflect replaced value");

    // Still exactly one entry for that pair -> list has length 1.
    let (s, b) = call(app.clone(), "GET", "/projects/p/secrets", None).await;
    assert_eq!(s, StatusCode::OK);
    let arr = json(&b)["secrets"].as_array().unwrap().clone();
    assert_eq!(arr.len(), 1, "replace must not duplicate the entry");
    assert_eq!(arr[0]["key"], "K");
    assert_eq!(arr[0]["value"], "v2");
}

#[tokio::test]
async fn read_missing_is_404_with_message() {
    let app = router();
    let (s, b) = call(app.clone(), "GET", "/projects/nope/secrets/MISSING", None).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "unknown key must be 404");
    let v = json(&b);
    assert!(v.get("message").is_some(), "404 body must carry a `message` field");
    assert!(
        v["message"].as_str().map(|m| !m.is_empty()).unwrap_or(false),
        "message must be a non-empty human-readable string"
    );
}

#[tokio::test]
async fn project_scoping_on_read() {
    let app = router();
    let (s, _) = call(app.clone(), "PUT", "/projects/a/secrets/SHARED", Some(r#"{"value":"x"}"#)).await;
    assert_eq!(s, StatusCode::CREATED);

    // Same key, different project -> still missing.
    let (s, _) = call(app.clone(), "GET", "/projects/b/secrets/SHARED", None).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "key under project a must not leak into project b");

    // Original is still readable.
    let (s, b) = call(app.clone(), "GET", "/projects/a/secrets/SHARED", None).await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(json(&b)["value"], "x");
}

#[tokio::test]
async fn list_empty_and_ordered_and_scoped() {
    let app = router();

    // Empty project.
    let (s, b) = call(app.clone(), "GET", "/projects/empty/secrets", None).await;
    assert_eq!(s, StatusCode::OK);
    let v = json(&b);
    assert!(v["secrets"].as_array().unwrap().is_empty(), "empty project lists []");

    // Insert out of order; also insert into another project that must not appear.
    call(app.clone(), "PUT", "/projects/proj/secrets/charlie", Some(r#"{"value":"3"}"#)).await;
    call(app.clone(), "PUT", "/projects/proj/secrets/alpha", Some(r#"{"value":"1"}"#)).await;
    call(app.clone(), "PUT", "/projects/proj/secrets/bravo", Some(r#"{"value":"2"}"#)).await;
    call(app.clone(), "PUT", "/projects/other/secrets/zzz", Some(r#"{"value":"9"}"#)).await;

    let (s, b) = call(app.clone(), "GET", "/projects/proj/secrets", None).await;
    assert_eq!(s, StatusCode::OK);
    let arr = json(&b)["secrets"].as_array().unwrap().clone();
    let keys: Vec<String> = arr.iter().map(|e| e["key"].as_str().unwrap().to_string()).collect();
    assert_eq!(keys, vec!["alpha", "bravo", "charlie"], "list must be key-ascending and scoped to project");
    assert_eq!(arr.len(), 3, "secrets from other projects must not appear");
    // values travel with their keys
    assert_eq!(arr[0]["value"], "1");
    assert_eq!(arr[1]["value"], "2");
    assert_eq!(arr[2]["value"], "3");
}

#[tokio::test]
async fn delete_existing_then_missing() {
    let app = router();
    call(app.clone(), "PUT", "/projects/d/secrets/K", Some(r#"{"value":"v"}"#)).await;

    let (s, b) = call(app.clone(), "DELETE", "/projects/d/secrets/K", None).await;
    assert_eq!(s, StatusCode::NO_CONTENT, "delete existing must be 204");
    assert!(b.is_empty(), "204 body must be empty");

    let (s, _) = call(app.clone(), "GET", "/projects/d/secrets/K", None).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "deleted secret must read as 404");

    let (s, _) = call(app.clone(), "DELETE", "/projects/d/secrets/K", None).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "delete of missing secret must be 404");
}

#[tokio::test]
async fn malformed_body_is_400_and_no_mutation() {
    // missing field
    {
        let app = router();
        let (s, _) = call(app.clone(), "PUT", "/projects/m/secrets/K", Some(r#"{}"#)).await;
        assert_eq!(s, StatusCode::BAD_REQUEST, "missing `value` -> 400");
        let (s, _) = call(app.clone(), "GET", "/projects/m/secrets/K", None).await;
        assert_eq!(s, StatusCode::NOT_FOUND, "rejected create must not have stored anything");
    }
    // wrong type
    {
        let app = router();
        let (s, _) = call(app.clone(), "PUT", "/projects/m/secrets/K", Some(r#"{"value":123}"#)).await;
        assert_eq!(s, StatusCode::BAD_REQUEST, "non-string value -> 400");
        let (s, _) = call(app.clone(), "GET", "/projects/m/secrets/K", None).await;
        assert_eq!(s, StatusCode::NOT_FOUND);
    }
    // invalid JSON
    {
        let app = router();
        let (s, _) = call(app.clone(), "PUT", "/projects/m/secrets/K", Some(r#"{not json"#)).await;
        assert_eq!(s, StatusCode::BAD_REQUEST, "syntactically invalid JSON -> 400");
        let (s, _) = call(app.clone(), "GET", "/projects/m/secrets/K", None).await;
        assert_eq!(s, StatusCode::NOT_FOUND);
    }
}

#[tokio::test]
async fn instances_are_independent() {
    let a = router();
    let b = router();
    call(a.clone(), "PUT", "/projects/p/secrets/K", Some(r#"{"value":"v"}"#)).await;
    // b is a fresh, empty, independent instance.
    let (s, _) = call(b.clone(), "GET", "/projects/p/secrets/K", None).await;
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
        "--features", "axum",
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
    """Verify the in-memory secrets HTTP API added to shuttle-common."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_secrets_api_source_exists(self):
        """common/src/secrets_api.rs must exist and be non-trivial."""
        assert os.path.isfile(SECRETS_API_SRC), "common/src/secrets_api.rs not created"
        assert os.path.getsize(SECRETS_API_SRC) > 200, "secrets_api.rs is implausibly small"

    def test_router_constructor_declared(self):
        """secrets_api.rs must declare a public `fn router() -> ... Router`."""
        with open(SECRETS_API_SRC) as f:
            src = f.read()
        assert re.search(r"pub\s+fn\s+router\s*\(", src), "no `pub fn router(` constructor found"
        assert re.search(r"Router", src), "router() must build an axum Router"

    def test_uses_secret_wrapper(self):
        """Stored values must use the crate's Secret wrapper, not bare String."""
        with open(SECRETS_API_SRC) as f:
            src = f.read()
        assert "Secret" in src, "implementation must reference the crate's Secret type"

    def test_module_declared_gated_in_lib(self):
        """lib.rs must declare `secrets_api` gated behind the axum feature."""
        with open(LIB_RS) as f:
            lib = f.read()
        assert "secrets_api" in lib, "lib.rs does not declare the secrets_api module"
        # the declaration must be feature-gated on axum
        m = re.search(r'(#\[cfg\([^\)]*feature\s*=\s*"axum"[^\)]*\)\]\s*)pub\s+mod\s+secrets_api', lib)
        assert m is not None, "module `secrets_api` must be #[cfg(feature = \"axum\")]-gated"

    def test_agent_integration_test_exists(self):
        """The agent's own in-process integration test must exist."""
        assert os.path.isfile(AGENT_TEST), "common/tests/secrets_api.rs not created"
        with open(AGENT_TEST) as f:
            t = f.read()
        assert "router" in t, "agent test does not appear to drive router()"

    # ------------------------------------------------------------------
    # L2: feature gating builds + independent behavioral verification
    # ------------------------------------------------------------------

    def test_builds_without_axum_feature(self):
        """The crate must still build with the axum feature OFF (no leaked deps)."""
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
        """The exact acceptance command must pass: cargo test ... --test secrets_api."""
        proc = subprocess.run(
            ["cargo", "test", "-p", "shuttle-common", "--features", "axum", "--test", "secrets_api"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=RUN_TIMEOUT, env=_cargo_env(),
        )
        out = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, f"acceptance command failed:\n{out[-4000:]}"
        assert "test result: ok." in out, f"acceptance test did not report ok:\n{out[-2000:]}"

    def test_create_then_read(self):
        """PUT new -> 201; GET -> 200 with {key,value} echoing the written data."""
        _assert_test_passed(_run_verify("create_then_read"), "create_then_read")

    def test_replace_updates_value_and_status(self):
        """Second PUT to same path -> 200 (not 201), updates value, no duplicate entry."""
        _assert_test_passed(
            _run_verify("replace_updates_value_and_status"),
            "replace_updates_value_and_status",
        )

    def test_read_missing_is_404_with_message(self):
        """GET unknown key -> 404 with an ApiError-shaped JSON `message` field."""
        _assert_test_passed(
            _run_verify("read_missing_is_404_with_message"),
            "read_missing_is_404_with_message",
        )

    def test_project_scoping_on_read(self):
        """A key created under project a must read 404 under project b."""
        _assert_test_passed(_run_verify("project_scoping_on_read"), "project_scoping_on_read")

    def test_list_empty_and_ordered_and_scoped(self):
        """List: [] when empty; key-ascending and scoped to one project otherwise."""
        _assert_test_passed(
            _run_verify("list_empty_and_ordered_and_scoped"),
            "list_empty_and_ordered_and_scoped",
        )

    def test_delete_existing_then_missing(self):
        """DELETE existing -> 204 empty body, then read 404; DELETE missing -> 404."""
        _assert_test_passed(
            _run_verify("delete_existing_then_missing"),
            "delete_existing_then_missing",
        )

    def test_malformed_body_is_400_and_no_mutation(self):
        """Bad create bodies (missing/wrong-type/invalid) -> 400 and store unchanged."""
        _assert_test_passed(
            _run_verify("malformed_body_is_400_and_no_mutation"),
            "malformed_body_is_400_and_no_mutation",
        )

    def test_instances_are_independent(self):
        """Each router() call owns an independent, initially-empty store."""
        _assert_test_passed(_run_verify("instances_are_independent"), "instances_are_independent")
