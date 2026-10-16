"""
Test for 'axum-web-patterns' skill (variant ext2) — in-memory deployments HTTP
API in shuttle-common.

The task asks the agent to add `common/src/deployments_api.rs` exposing
`pub fn router() -> axum::Router`, gated behind the `axum` feature, backed by an
in-memory per-(project, id) registry whose `state` round-trips through the
crate's existing `DeploymentState` enum (serialized lowercase: "pending",
"building", "running", "stopped", ...). Error bodies use the crate's
`ApiError` shape (a JSON object with a `message` field). The five routes are
expressed across exactly two route paths:

    GET    /projects/{project}/deployments          -> list, id-ascending
    POST   /projects/{project}/deployments          -> create (Pending), 201/409
    GET    /projects/{project}/deployments/{id}      -> read one, 200/404
    PATCH  /projects/{project}/deployments/{id}      -> advance state, 200/400/404
    DELETE /projects/{project}/deployments/{id}      -> remove, 204/404

Create body:  {"id": "<string>"}        (new deployment starts Pending)
Update body:  {"state": "<state>"}      (must be a recognized DeploymentState)
Single body:  {"id": "<string>", "state": "<state>"}
List body:    {"deployments": [ {"id":..., "state":...}, ... ]}

Verification strategy
---------------------
We do NOT trust the agent's own `common/tests/deployments_api.rs`. For the L2
behavioral checks, this harness injects an *independent* Rust integration test
(`tests/_deployments_api_verify.rs`) that imports the real
`shuttle_common::deployments_api::router()`, drives it fully in-process with
`tower::ServiceExt::oneshot` (no TCP), and asserts every acceptance scenario
with concrete status codes / JSON fields / ordering. We add the required
dev-dependencies ourselves so the checks do not depend on the agent's
`Cargo.toml`. Each L2 pytest method runs one named Rust test and asserts it
passes, mapping 1:1 to a requirement. A naive implementation that ignores the
project segment, returns a fixed status, hardcodes responses, accepts arbitrary
state strings, or skips storage will fail these.

Native command of record:
    cargo test -p shuttle-common --features axum,models --test deployments_api
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/shuttle"
COMMON_DIR = os.path.join(REPO_DIR, "common")
DEPLOY_API_SRC = os.path.join(COMMON_DIR, "src", "deployments_api.rs")
LIB_RS = os.path.join(COMMON_DIR, "src", "lib.rs")
AGENT_TEST = os.path.join(COMMON_DIR, "tests", "deployments_api.rs")
CARGO_TOML = os.path.join(COMMON_DIR, "Cargo.toml")

VERIFY_TEST_NAME = "_deployments_api_verify"
VERIFY_TEST_PATH = os.path.join(COMMON_DIR, "tests", VERIFY_TEST_NAME + ".rs")

# The module uses DeploymentState (from the `models` feature) and is gated on
# `axum`; both features are required to compile, matching the native command.
FEATURES = "axum,models"

BUILD_TIMEOUT = 900
RUN_TIMEOUT = 900


# ---------------------------------------------------------------------------
# Independent in-process Rust integration test injected into the repo.
# It only depends on the public surface:
#   `shuttle_common::deployments_api::router()`.
# ---------------------------------------------------------------------------
VERIFY_RS = r'''
// AUTO-GENERATED independent verification test for the axum-web-patterns task (ext2).
// Drives `router()` fully in-process (no socket) via tower oneshot.
#![cfg(all(feature = "axum", feature = "models"))]

use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt; // for `oneshot`

use shuttle_common::deployments_api::router;

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
async fn create_starts_pending_then_read() {
    let app = router();
    let (s, b) = call(app.clone(), "POST", "/projects/alpha/deployments", Some(r#"{"id":"d1"}"#)).await;
    assert_eq!(s, StatusCode::CREATED, "first POST must be 201 Created");
    let v = json(&b);
    assert_eq!(v["id"], "d1", "create body must echo id");
    assert_eq!(v["state"], "pending", "a new deployment must start in the pending state");

    let (s, b) = call(app.clone(), "GET", "/projects/alpha/deployments/d1", None).await;
    assert_eq!(s, StatusCode::OK, "read of created deployment must be 200");
    let v = json(&b);
    assert_eq!(v["id"], "d1", "read body must echo id");
    assert_eq!(v["state"], "pending", "read body must reflect persisted state");
}

#[tokio::test]
async fn duplicate_create_is_409_and_no_overwrite() {
    let app = router();
    let (s, _) = call(app.clone(), "POST", "/projects/p/deployments", Some(r#"{"id":"x"}"#)).await;
    assert_eq!(s, StatusCode::CREATED);

    // Advance the existing one so we can detect any accidental overwrite/reset.
    let (s, _) = call(app.clone(), "PATCH", "/projects/p/deployments/x", Some(r#"{"state":"running"}"#)).await;
    assert_eq!(s, StatusCode::OK);

    let (s, _) = call(app.clone(), "POST", "/projects/p/deployments", Some(r#"{"id":"x"}"#)).await;
    assert_eq!(s, StatusCode::CONFLICT, "duplicate id for same project must be 409 Conflict");

    // Conflict must NOT reset the entry back to pending.
    let (s, b) = call(app.clone(), "GET", "/projects/p/deployments/x", None).await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(json(&b)["state"], "running", "a 409 must not mutate the existing deployment");

    // Exactly one entry survived.
    let (s, b) = call(app.clone(), "GET", "/projects/p/deployments", None).await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(json(&b)["deployments"].as_array().unwrap().len(), 1, "duplicate POST must not add a second entry");
}

#[tokio::test]
async fn read_missing_is_404_with_message() {
    let app = router();
    let (s, b) = call(app.clone(), "GET", "/projects/nope/deployments/missing", None).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "unknown id must be 404");
    let v = json(&b);
    assert!(v.get("message").is_some(), "404 body must carry a `message` field (ApiError shape)");
    assert!(
        v["message"].as_str().map(|m| !m.is_empty()).unwrap_or(false),
        "message must be a non-empty human-readable string"
    );
}

#[tokio::test]
async fn project_scoping_on_read() {
    let app = router();
    let (s, _) = call(app.clone(), "POST", "/projects/a/deployments", Some(r#"{"id":"shared"}"#)).await;
    assert_eq!(s, StatusCode::CREATED);

    // Same id, different project -> still missing.
    let (s, _) = call(app.clone(), "GET", "/projects/b/deployments/shared", None).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "id under project a must not leak into project b");

    // Original is still readable under its own project.
    let (s, b) = call(app.clone(), "GET", "/projects/a/deployments/shared", None).await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(json(&b)["id"], "shared");
}

#[tokio::test]
async fn patch_advances_state_and_persists() {
    let app = router();
    call(app.clone(), "POST", "/projects/p/deployments", Some(r#"{"id":"d"}"#)).await;

    let (s, b) = call(app.clone(), "PATCH", "/projects/p/deployments/d", Some(r#"{"state":"running"}"#)).await;
    assert_eq!(s, StatusCode::OK, "valid PATCH must be 200");
    assert_eq!(json(&b)["state"], "running", "PATCH response must reflect the new state");

    let (s, b) = call(app.clone(), "GET", "/projects/p/deployments/d", None).await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(json(&b)["state"], "running", "a subsequent read must reflect the advanced state");

    // Advance again to another valid state to confirm it is not hardcoded.
    let (s, b) = call(app.clone(), "PATCH", "/projects/p/deployments/d", Some(r#"{"state":"stopped"}"#)).await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(json(&b)["state"], "stopped");
    let (_, b) = call(app.clone(), "GET", "/projects/p/deployments/d", None).await;
    assert_eq!(json(&b)["state"], "stopped");
}

#[tokio::test]
async fn patch_invalid_state_is_400_and_no_mutation() {
    let app = router();
    call(app.clone(), "POST", "/projects/p/deployments", Some(r#"{"id":"d"}"#)).await;
    // get it off of pending first so we can prove the bad PATCH does not change it
    call(app.clone(), "PATCH", "/projects/p/deployments/d", Some(r#"{"state":"building"}"#)).await;

    // An unrecognized state string must be rejected before any mutation.
    let (s, _) = call(app.clone(), "PATCH", "/projects/p/deployments/d", Some(r#"{"state":"definitely-not-a-state"}"#)).await;
    assert_eq!(s, StatusCode::BAD_REQUEST, "unrecognized state -> 400 Bad Request");

    let (s, b) = call(app.clone(), "GET", "/projects/p/deployments/d", None).await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(json(&b)["state"], "building", "a rejected PATCH must leave the stored state unchanged");
}

#[tokio::test]
async fn patch_unknown_is_404() {
    let app = router();
    let (s, _) = call(app.clone(), "PATCH", "/projects/p/deployments/ghost", Some(r#"{"state":"running"}"#)).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "PATCH of an unknown deployment must be 404");
}

#[tokio::test]
async fn list_empty_and_ordered_and_scoped() {
    let app = router();

    // Empty project.
    let (s, b) = call(app.clone(), "GET", "/projects/empty/deployments", None).await;
    assert_eq!(s, StatusCode::OK);
    let v = json(&b);
    assert!(v["deployments"].as_array().unwrap().is_empty(), "empty project lists []");

    // Insert out of order; also insert into another project that must not appear.
    call(app.clone(), "POST", "/projects/proj/deployments", Some(r#"{"id":"charlie"}"#)).await;
    call(app.clone(), "POST", "/projects/proj/deployments", Some(r#"{"id":"alpha"}"#)).await;
    call(app.clone(), "POST", "/projects/proj/deployments", Some(r#"{"id":"bravo"}"#)).await;
    call(app.clone(), "POST", "/projects/other/deployments", Some(r#"{"id":"zzz"}"#)).await;

    // Advance one of them so we can assert state travels with the entry.
    call(app.clone(), "PATCH", "/projects/proj/deployments/bravo", Some(r#"{"state":"running"}"#)).await;

    let (s, b) = call(app.clone(), "GET", "/projects/proj/deployments", None).await;
    assert_eq!(s, StatusCode::OK);
    let arr = json(&b)["deployments"].as_array().unwrap().clone();
    let ids: Vec<String> = arr.iter().map(|e| e["id"].as_str().unwrap().to_string()).collect();
    assert_eq!(ids, vec!["alpha", "bravo", "charlie"], "list must be id-ascending and scoped to the project");
    assert_eq!(arr.len(), 3, "deployments from other projects must not appear");
    // states travel with their ids
    assert_eq!(arr[0]["state"], "pending");
    assert_eq!(arr[1]["state"], "running");
    assert_eq!(arr[2]["state"], "pending");
}

#[tokio::test]
async fn delete_existing_then_missing() {
    let app = router();
    call(app.clone(), "POST", "/projects/d/deployments", Some(r#"{"id":"k"}"#)).await;

    let (s, b) = call(app.clone(), "DELETE", "/projects/d/deployments/k", None).await;
    assert_eq!(s, StatusCode::NO_CONTENT, "delete existing must be 204");
    assert!(b.is_empty(), "204 body must be empty");

    let (s, _) = call(app.clone(), "GET", "/projects/d/deployments/k", None).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "deleted deployment must read as 404");

    let (s, _) = call(app.clone(), "DELETE", "/projects/d/deployments/k", None).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "delete of a missing deployment must be 404");
}

#[tokio::test]
async fn instances_are_independent() {
    let a = router();
    let b = router();
    call(a.clone(), "POST", "/projects/p/deployments", Some(r#"{"id":"k"}"#)).await;
    // b is a fresh, empty, independent instance.
    let (s, _) = call(b.clone(), "GET", "/projects/p/deployments/k", None).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "each router() must own an independent empty registry");
    let (s, b2) = call(b.clone(), "GET", "/projects/p/deployments", None).await;
    assert_eq!(s, StatusCode::OK);
    assert!(json(&b2)["deployments"].as_array().unwrap().is_empty(), "fresh instance must list empty");
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

    We only ever add a key that is not already present *inside the
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
    assert "test result: ok." in out, f"cargo did not report ok for `{test_name}`:\n{out[-2000:]}"
    assert "0 passed" not in out, f"the named test `{test_name}` did not actually run:\n{out[-2000:]}"


class TestAxumWebPatterns:
    """Verify the in-memory deployments HTTP API added to shuttle-common (ext2)."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_deployments_api_source_exists(self):
        """common/src/deployments_api.rs must exist and be non-trivial."""
        assert os.path.isfile(DEPLOY_API_SRC), "common/src/deployments_api.rs not created"
        assert os.path.getsize(DEPLOY_API_SRC) > 200, "deployments_api.rs is implausibly small"

    def test_router_constructor_declared(self):
        """deployments_api.rs must declare a public `fn router() -> ... Router`."""
        with open(DEPLOY_API_SRC) as f:
            src = f.read()
        assert re.search(r"pub\s+fn\s+router\s*\(", src), "no `pub fn router(` constructor found"
        assert re.search(r"Router", src), "router() must build an axum Router"

    def test_uses_deployment_state_enum(self):
        """State must round-trip through the crate's DeploymentState enum, not free-form strings."""
        with open(DEPLOY_API_SRC) as f:
            src = f.read()
        assert "DeploymentState" in src, "implementation must reference the crate's DeploymentState enum"

    def test_two_route_paths_only(self):
        """The five routes must be expressed across exactly two route paths."""
        with open(DEPLOY_API_SRC) as f:
            src = f.read()
        routes = re.findall(r'\.route\(\s*"([^"]+)"', src)
        # Normalize to distinct path strings.
        distinct = sorted(set(routes))
        assert len(distinct) == 2, (
            f"router must use exactly two route paths, found {len(distinct)}: {distinct}"
        )
        # One collection path and one per-id path, both project-scoped.
        assert any(p.endswith("/deployments") for p in distinct), \
            "missing the collection route path .../deployments"
        assert any(re.search(r"/deployments/\{[^}]+\}$", p) for p in distinct), \
            "missing the per-id route path .../deployments/{id}"
        assert all("projects" in p for p in distinct), "both route paths must be project-scoped"

    def test_module_declared_gated_in_lib(self):
        """lib.rs must declare `deployments_api` gated behind the axum feature."""
        with open(LIB_RS) as f:
            lib = f.read()
        assert "deployments_api" in lib, "lib.rs does not declare the deployments_api module"
        m = re.search(
            r'(#\[cfg\([^\)]*feature\s*=\s*"axum"[^\)]*\)\]\s*)pub\s+mod\s+deployments_api',
            lib,
        )
        assert m is not None, 'module `deployments_api` must be #[cfg(feature = "axum")]-gated'

    def test_agent_integration_test_exists(self):
        """The agent's own in-process integration test must exist and drive router()."""
        assert os.path.isfile(AGENT_TEST), "common/tests/deployments_api.rs not created"
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
        """The exact acceptance command must pass: cargo test ... --test deployments_api."""
        proc = subprocess.run(
            ["cargo", "test", "-p", "shuttle-common", "--features", FEATURES, "--test", "deployments_api"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=RUN_TIMEOUT, env=_cargo_env(),
        )
        out = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, f"acceptance command failed:\n{out[-4000:]}"
        assert "test result: ok." in out, f"acceptance test did not report ok:\n{out[-2000:]}"

    def test_create_starts_pending_then_read(self):
        """POST new -> 201 with state=pending; GET -> 200 echoing id and state."""
        _assert_test_passed(_run_verify("create_starts_pending_then_read"), "create_starts_pending_then_read")

    def test_duplicate_create_is_409_and_no_overwrite(self):
        """Second POST of same id -> 409 and the existing entry is unchanged (one entry)."""
        _assert_test_passed(
            _run_verify("duplicate_create_is_409_and_no_overwrite"),
            "duplicate_create_is_409_and_no_overwrite",
        )

    def test_read_missing_is_404_with_message(self):
        """GET unknown id -> 404 with an ApiError-shaped JSON `message` field."""
        _assert_test_passed(
            _run_verify("read_missing_is_404_with_message"),
            "read_missing_is_404_with_message",
        )

    def test_project_scoping_on_read(self):
        """An id created under project a must read 404 under project b."""
        _assert_test_passed(_run_verify("project_scoping_on_read"), "project_scoping_on_read")

    def test_patch_advances_state_and_persists(self):
        """PATCH to a valid state -> 200, persisted, and not hardcoded (two distinct states)."""
        _assert_test_passed(
            _run_verify("patch_advances_state_and_persists"),
            "patch_advances_state_and_persists",
        )

    def test_patch_invalid_state_is_400_and_no_mutation(self):
        """PATCH with an unrecognized state -> 400 and the stored state is unchanged."""
        _assert_test_passed(
            _run_verify("patch_invalid_state_is_400_and_no_mutation"),
            "patch_invalid_state_is_400_and_no_mutation",
        )

    def test_patch_unknown_is_404(self):
        """PATCH of an unknown deployment -> 404."""
        _assert_test_passed(_run_verify("patch_unknown_is_404"), "patch_unknown_is_404")

    def test_list_empty_and_ordered_and_scoped(self):
        """List: [] when empty; id-ascending and scoped to one project, states travel with ids."""
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

    def test_instances_are_independent(self):
        """Each router() call owns an independent, initially-empty registry."""
        _assert_test_passed(_run_verify("instances_are_independent"), "instances_are_independent")
