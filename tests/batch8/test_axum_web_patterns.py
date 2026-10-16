"""
Test for 'axum-web-patterns' skill (variant ext8) — validating project-create
HTTP API in shuttle-common.

The task asks the agent to add `common/src/projects_api.rs` exposing
`pub fn router() -> axum::Router`, gated behind the `axum` feature (and using
`ProjectCreateRequest` from the `models` module). A reusable *validating request
component* parses the JSON body into `ProjectCreateRequest` and enforces the name
rules (`^[a-z0-9-]{1,32}$`) BEFORE the create handler runs; rejections short-circuit
with `400 Bad Request` and the crate's `ApiError`-shaped JSON body. Routes:

    POST /projects            -> 201 Created (validated by the component)
    GET  /projects            -> { "projects": [ "<name>", ... ] }  (name-ascending)
    GET  /projects/{name}     -> 200 if present, 404 (with `message`) if absent

Each `router()` call owns an independent, empty store; duplicate valid name -> 409.

Verification strategy
---------------------
We do NOT trust the agent's own `common/tests/projects_api.rs`. For the L2
behavioral checks this harness injects an *independent* Rust integration test
(`tests/_projects_api_verify.rs`) that imports the real `router()`, drives it
fully in-process with `tower::ServiceExt::oneshot` (no TCP), and asserts every
acceptance scenario. We add the required dev-dependencies ourselves so the checks
do not depend on what the agent put in `Cargo.toml`. Each L2 pytest method runs
one named Rust test and asserts it passes, mapping 1:1 to a requirement. A naive
implementation that accepts any name, hardcodes acceptance, or validates inside
the handler (rather than the component) must fail these checks.

Native command of record:
    cargo test -p shuttle-common --features axum,models --test projects_api
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/shuttle"
COMMON_DIR = os.path.join(REPO_DIR, "common")
PROJECTS_API_SRC = os.path.join(COMMON_DIR, "src", "projects_api.rs")
LIB_RS = os.path.join(COMMON_DIR, "src", "lib.rs")
AGENT_TEST = os.path.join(COMMON_DIR, "tests", "projects_api.rs")
CARGO_TOML = os.path.join(COMMON_DIR, "Cargo.toml")

VERIFY_TEST_NAME = "_projects_api_verify"
VERIFY_TEST_PATH = os.path.join(COMMON_DIR, "tests", VERIFY_TEST_NAME + ".rs")

BUILD_TIMEOUT = 900
RUN_TIMEOUT = 900


# ---------------------------------------------------------------------------
# Independent in-process Rust integration test injected into the repo.
# It only depends on the public surface: `shuttle_common::projects_api::router()`.
# ---------------------------------------------------------------------------
VERIFY_RS = r'''
// AUTO-GENERATED independent verification test for the axum-web-patterns task (ext8).
// Drives `router()` fully in-process (no socket) via tower oneshot.
#![cfg(all(feature = "axum", feature = "models"))]

use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt; // for `oneshot`

use shuttle_common::projects_api::router;

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

// Extract the ascending list of project names from `GET /projects`.
fn names(v: &Value) -> Vec<String> {
    v["projects"]
        .as_array()
        .expect("`projects` must be a JSON array")
        .iter()
        .map(|e| e.as_str().expect("each project entry must be a string").to_string())
        .collect()
}

#[tokio::test]
async fn create_then_read_and_list() {
    let app = router();

    let (s, _) = call(app.clone(), "POST", "/projects", Some(r#"{"name":"my-app-1"}"#)).await;
    assert_eq!(s, StatusCode::CREATED, "valid POST must be 201 Created");

    let (s, _) = call(app.clone(), "GET", "/projects/my-app-1", None).await;
    assert_eq!(s, StatusCode::OK, "existence check of created project must be 200");

    let (s, b) = call(app.clone(), "GET", "/projects", None).await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(names(&json(&b)), vec!["my-app-1"], "list must contain exactly the created name");
}

#[tokio::test]
async fn duplicate_is_409_and_no_double_insert() {
    let app = router();

    let (s, _) = call(app.clone(), "POST", "/projects", Some(r#"{"name":"dup"}"#)).await;
    assert_eq!(s, StatusCode::CREATED, "first create must be 201");

    let (s, _) = call(app.clone(), "POST", "/projects", Some(r#"{"name":"dup"}"#)).await;
    assert_eq!(s, StatusCode::CONFLICT, "second create of same name must be 409 Conflict");

    // Still exactly one entry.
    let (s, b) = call(app.clone(), "GET", "/projects", None).await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(names(&json(&b)), vec!["dup"], "duplicate must not add a second entry");
}

#[tokio::test]
async fn invalid_names_rejected_400_and_no_store() {
    // Each invalid name must yield 400 and store nothing.
    let cases = [
        ("", "empty name"),
        // 33 chars -> over the 32 max
        ("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "over-length name"),
        ("My-App", "uppercase letter"),
        ("app 1", "name with a space"),
        ("app_1", "disallowed underscore"),
        ("app.1", "disallowed dot"),
    ];
    for (name, why) in cases {
        let app = router();
        let body = format!(r#"{{"name":{}}}"#, serde_json::to_string(name).unwrap());
        let (s, _) = call(app.clone(), "POST", "/projects", Some(&body)).await;
        assert_eq!(s, StatusCode::BAD_REQUEST, "invalid name ({why}) must be 400");

        // Store must remain empty: list is [] and existence check for that name is 404.
        let (s, b) = call(app.clone(), "GET", "/projects", None).await;
        assert_eq!(s, StatusCode::OK);
        assert!(
            names(&json(&b)).is_empty(),
            "rejected create ({why}) must not store anything"
        );
    }
}

#[tokio::test]
async fn boundary_lengths_accepted() {
    // 1-char and exactly-32-char names are valid (inclusive bounds).
    let one = "a";
    let thirtytwo = "a".repeat(32);
    for name in [one.to_string(), thirtytwo.clone()] {
        let app = router();
        let body = format!(r#"{{"name":"{}"}}"#, name);
        let (s, _) = call(app.clone(), "POST", "/projects", Some(&body)).await;
        assert_eq!(s, StatusCode::CREATED, "boundary-length name `{name}` must be accepted (201)");
        let uri = format!("/projects/{}", name);
        let (s, _) = call(app.clone(), "GET", &uri, None).await;
        assert_eq!(s, StatusCode::OK, "boundary-length name `{name}` must be readable");
    }
    // 32 ok, 33 not ok already covered; assert exactly-32 length here for clarity.
    assert_eq!(thirtytwo.len(), 32);
}

#[tokio::test]
async fn malformed_body_is_400_and_no_store() {
    // missing field
    {
        let app = router();
        let (s, _) = call(app.clone(), "POST", "/projects", Some(r#"{}"#)).await;
        assert_eq!(s, StatusCode::BAD_REQUEST, "missing `name` -> 400");
        let (s, b) = call(app.clone(), "GET", "/projects", None).await;
        assert_eq!(s, StatusCode::OK);
        assert!(names(&json(&b)).is_empty(), "rejected create must store nothing");
    }
    // wrong type
    {
        let app = router();
        let (s, _) = call(app.clone(), "POST", "/projects", Some(r#"{"name":123}"#)).await;
        assert_eq!(s, StatusCode::BAD_REQUEST, "non-string name -> 400");
        let (s, b) = call(app.clone(), "GET", "/projects", None).await;
        assert!(names(&json(&b)).is_empty());
    }
    // invalid JSON
    {
        let app = router();
        let (s, _) = call(app.clone(), "POST", "/projects", Some(r#"{not json"#)).await;
        assert_eq!(s, StatusCode::BAD_REQUEST, "syntactically invalid JSON -> 400");
        let (s, b) = call(app.clone(), "GET", "/projects", None).await;
        assert!(names(&json(&b)).is_empty());
    }
}

#[tokio::test]
async fn error_bodies_carry_message() {
    // 400 from validation must carry an ApiError-shaped `message`.
    let app = router();
    let (s, b) = call(app.clone(), "POST", "/projects", Some(r#"{"name":"BAD NAME"}"#)).await;
    assert_eq!(s, StatusCode::BAD_REQUEST);
    let v = json(&b);
    assert!(
        v.get("message").and_then(|m| m.as_str()).map(|m| !m.is_empty()).unwrap_or(false),
        "400 body must carry a non-empty `message` field"
    );

    // 404 from a missing existence check must carry a `message` too.
    let (s, b) = call(app.clone(), "GET", "/projects/does-not-exist", None).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "absent project must be 404");
    let v = json(&b);
    assert!(
        v.get("message").and_then(|m| m.as_str()).map(|m| !m.is_empty()).unwrap_or(false),
        "404 body must carry a non-empty `message` field"
    );
}

#[tokio::test]
async fn list_empty_and_ordered() {
    let app = router();

    // Empty store -> {"projects":[]}.
    let (s, b) = call(app.clone(), "GET", "/projects", None).await;
    assert_eq!(s, StatusCode::OK);
    assert!(names(&json(&b)).is_empty(), "empty store must list []");

    // Insert out of lexicographic order.
    for name in ["charlie", "alpha-2", "alpha-1", "bravo"] {
        let body = format!(r#"{{"name":"{}"}}"#, name);
        let (s, _) = call(app.clone(), "POST", "/projects", Some(&body)).await;
        assert_eq!(s, StatusCode::CREATED, "create `{name}` must be 201");
    }

    let (s, b) = call(app.clone(), "GET", "/projects", None).await;
    assert_eq!(s, StatusCode::OK);
    assert_eq!(
        names(&json(&b)),
        vec!["alpha-1", "alpha-2", "bravo", "charlie"],
        "list must be name-ascending"
    );
}

#[tokio::test]
async fn existence_check_present_and_absent() {
    let app = router();
    let (s, _) = call(app.clone(), "POST", "/projects", Some(r#"{"name":"here"}"#)).await;
    assert_eq!(s, StatusCode::CREATED);

    let (s, _) = call(app.clone(), "GET", "/projects/here", None).await;
    assert_eq!(s, StatusCode::OK, "present project -> 200");

    let (s, _) = call(app.clone(), "GET", "/projects/absent", None).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "absent project -> 404");
}

#[tokio::test]
async fn instances_are_independent() {
    let a = router();
    let b = router();
    let (s, _) = call(a.clone(), "POST", "/projects", Some(r#"{"name":"x"}"#)).await;
    assert_eq!(s, StatusCode::CREATED);

    // b is a fresh, empty, independent instance.
    let (s, body) = call(b.clone(), "GET", "/projects", None).await;
    assert_eq!(s, StatusCode::OK);
    assert!(names(&json(&body)).is_empty(), "each router() must own an independent empty store");
    let (s, _) = call(b.clone(), "GET", "/projects/x", None).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "project from instance a must not leak into b");
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
        "--features", "axum,models",
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
    """Verify the validating project-create HTTP API added to shuttle-common."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_projects_api_source_exists(self):
        """common/src/projects_api.rs must exist and be non-trivial."""
        assert os.path.isfile(PROJECTS_API_SRC), "common/src/projects_api.rs not created"
        assert os.path.getsize(PROJECTS_API_SRC) > 200, "projects_api.rs is implausibly small"

    def test_router_constructor_declared(self):
        """projects_api.rs must declare a public `fn router() -> ... Router`."""
        with open(PROJECTS_API_SRC) as f:
            src = f.read()
        assert re.search(r"pub\s+fn\s+router\s*\(", src), "no `pub fn router(` constructor found"
        assert re.search(r"Router", src), "router() must build an axum Router"

    def test_uses_project_create_request(self):
        """The component must parse the body into ProjectCreateRequest from the models module."""
        with open(PROJECTS_API_SRC) as f:
            src = f.read()
        assert "ProjectCreateRequest" in src, (
            "implementation must parse the body into ProjectCreateRequest"
        )

    def test_module_declared_gated_in_lib(self):
        """lib.rs must declare `projects_api` gated behind the axum feature."""
        with open(LIB_RS) as f:
            lib = f.read()
        assert "projects_api" in lib, "lib.rs does not declare the projects_api module"
        # the declaration must be feature-gated on axum (and may also require models)
        m = re.search(
            r'#\[cfg\([^\)]*feature\s*=\s*"axum"[^\)]*\)\]\s*pub\s+mod\s+projects_api',
            lib,
        )
        assert m is not None, 'module `projects_api` must be #[cfg(feature = "axum")]-gated'

    def test_agent_integration_test_exists(self):
        """The agent's own in-process integration test must exist and drive router()."""
        assert os.path.isfile(AGENT_TEST), "common/tests/projects_api.rs not created"
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
        """The exact acceptance command must pass: cargo test ... --features axum,models --test projects_api."""
        proc = subprocess.run(
            ["cargo", "test", "-p", "shuttle-common", "--features", "axum,models",
             "--test", "projects_api"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=RUN_TIMEOUT, env=_cargo_env(),
        )
        out = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, f"acceptance command failed:\n{out[-4000:]}"
        assert "test result: ok." in out, f"acceptance test did not report ok:\n{out[-2000:]}"

    def test_create_then_read_and_list(self):
        """Valid POST -> 201; existence check 200; appears in the list."""
        _assert_test_passed(_run_verify("create_then_read_and_list"), "create_then_read_and_list")

    def test_duplicate_is_409_and_no_double_insert(self):
        """Second POST of same valid name -> 409 and no second entry."""
        _assert_test_passed(
            _run_verify("duplicate_is_409_and_no_double_insert"),
            "duplicate_is_409_and_no_double_insert",
        )

    def test_invalid_names_rejected_400_and_no_store(self):
        """Empty/over-length/uppercase/space/symbol names -> 400 and store nothing."""
        _assert_test_passed(
            _run_verify("invalid_names_rejected_400_and_no_store"),
            "invalid_names_rejected_400_and_no_store",
        )

    def test_boundary_lengths_accepted(self):
        """1-char and exactly-32-char names are accepted (inclusive bounds)."""
        _assert_test_passed(_run_verify("boundary_lengths_accepted"), "boundary_lengths_accepted")

    def test_malformed_body_is_400_and_no_store(self):
        """Missing field / wrong type / invalid JSON -> 400 and store unchanged."""
        _assert_test_passed(
            _run_verify("malformed_body_is_400_and_no_store"),
            "malformed_body_is_400_and_no_store",
        )

    def test_error_bodies_carry_message(self):
        """400 (validation) and 404 (absent) bodies carry an ApiError-shaped `message`."""
        _assert_test_passed(_run_verify("error_bodies_carry_message"), "error_bodies_carry_message")

    def test_list_empty_and_ordered(self):
        """List: {"projects":[]} when empty; name-ascending order otherwise."""
        _assert_test_passed(_run_verify("list_empty_and_ordered"), "list_empty_and_ordered")

    def test_existence_check_present_and_absent(self):
        """GET /projects/{name} -> 200 for present, 404 for absent."""
        _assert_test_passed(
            _run_verify("existence_check_present_and_absent"),
            "existence_check_present_and_absent",
        )

    def test_instances_are_independent(self):
        """Each router() call owns an independent, initially-empty store."""
        _assert_test_passed(_run_verify("instances_are_independent"), "instances_are_independent")
