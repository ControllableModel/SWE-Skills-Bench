"""
Test for 'axum-web-patterns' skill (variant ext7) — a certificate registry HTTP
API with a single custom domain error type, added to `shuttle-common`.

The task asks the agent to add `common/src/certs_api.rs` exposing

    pub fn router() -> axum::Router;

gated behind the `axum` (and `models`) feature, backed by an in-memory registry
keyed by certificate `subject`. Every handler returns `Result<_, OneDomainError>`
whose `IntoResponse` maps each *cause* to a distinct status (404 / 409 / 400) and
whose body is the crate's standard `ApiError` shape (a JSON object with a
`message` field). Routes:

    POST   /certificates              register a new subject (AddCertificateRequest)
    GET    /certificates              list all, subject-ascending (CertificateListResponse)
    GET    /certificates/{subject}    read one (CertificateResponse)
    DELETE /certificates/{subject}    remove one

Responses use the existing `CertificateResponse` / `CertificateListResponse`
types from `common/src/models/certificate.rs`; the `id`, `serial_hex` and
`not_after` fields are deterministic placeholders derived from the subject.

Verification strategy
---------------------
We do NOT trust the agent's own `common/tests/certs_api.rs`. For the L2
behavioral checks this harness injects an *independent* Rust integration test
(`tests/_certs_api_verify.rs`) that imports the real `router()`, drives it fully
in-process with `tower::ServiceExt::oneshot` (no TCP), and asserts every
acceptance scenario with concrete status codes and JSON fields. We add the
required dev-dependencies ourselves so the checks do not depend on what the agent
put in `Cargo.toml`. Each L2 pytest method runs one named Rust test and asserts
it passes, mapping 1:1 to a requirement. A naive implementation (fixed status,
hardcoded body, no real storage, no conflict/validation handling) fails.

Native command of record:
    cargo test -p shuttle-common --features axum,models --test certs_api
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/shuttle"
COMMON_DIR = os.path.join(REPO_DIR, "common")
CERTS_API_SRC = os.path.join(COMMON_DIR, "src", "certs_api.rs")
LIB_RS = os.path.join(COMMON_DIR, "src", "lib.rs")
AGENT_TEST = os.path.join(COMMON_DIR, "tests", "certs_api.rs")
CARGO_TOML = os.path.join(COMMON_DIR, "Cargo.toml")

VERIFY_TEST_NAME = "_certs_api_verify"
VERIFY_TEST_PATH = os.path.join(COMMON_DIR, "tests", VERIFY_TEST_NAME + ".rs")

# Features under which the new module is compiled. The doc gates certs_api on
# both `axum` and `models` (CertificateResponse lives behind `models`).
FEATURES = "axum,models"

BUILD_TIMEOUT = 900
RUN_TIMEOUT = 900


# ---------------------------------------------------------------------------
# Independent in-process Rust integration test injected into the repo.
# It only depends on the public surface: `shuttle_common::certs_api::router()`
# and the public certificate model types.
# ---------------------------------------------------------------------------
VERIFY_RS = r'''
// AUTO-GENERATED independent verification test for the axum-web-patterns task (ext7).
// Drives `router()` fully in-process (no socket) via tower oneshot.
#![cfg(all(feature = "axum", feature = "models"))]

use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt; // for `oneshot`

use shuttle_common::certs_api::router;

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
    (status, bytes)
}

fn json(bytes: &[u8]) -> Value {
    serde_json::from_slice(bytes).expect("response body must be valid JSON")
}

// ---- Register / Read --------------------------------------------------------

#[tokio::test]
async fn register_then_read() {
    let app = router();
    let (s, b) = call(app.clone(), "POST", "/certificates", Some(r#"{"subject":"example.com"}"#)).await;
    assert_eq!(s, StatusCode::CREATED, "first POST must be 201 Created");
    let v = json(&b);
    assert_eq!(v["subject"], "example.com", "create body must be a CertificateResponse echoing subject");
    // CertificateResponse contract: id / serial_hex / not_after present.
    assert!(v.get("id").is_some(), "response must carry an `id` field");
    assert!(v.get("serial_hex").is_some(), "response must carry a `serial_hex` field");
    assert!(v.get("not_after").is_some(), "response must carry a `not_after` field");

    let (s, b) = call(app.clone(), "GET", "/certificates/example.com", None).await;
    assert_eq!(s, StatusCode::OK, "read of a registered subject must be 200");
    let v = json(&b);
    assert_eq!(v["subject"], "example.com", "read body must echo the registered subject");
    assert!(v.get("id").is_some() && v.get("serial_hex").is_some() && v.get("not_after").is_some());
}

#[tokio::test]
async fn placeholders_are_deterministic_per_subject() {
    // Same subject (across independent registries) must yield identical
    // deterministic placeholder fields -> no clock/randomness.
    let a = router();
    let (sa, ba) = call(a.clone(), "POST", "/certificates", Some(r#"{"subject":"det.example"}"#)).await;
    assert_eq!(sa, StatusCode::CREATED);
    let va = json(&ba);

    let b = router();
    let (sb, bb) = call(b.clone(), "POST", "/certificates", Some(r#"{"subject":"det.example"}"#)).await;
    assert_eq!(sb, StatusCode::CREATED);
    let vb = json(&bb);

    assert_eq!(va["id"], vb["id"], "id placeholder must be deterministic for a given subject");
    assert_eq!(va["serial_hex"], vb["serial_hex"], "serial_hex placeholder must be deterministic");
    assert_eq!(va["not_after"], vb["not_after"], "not_after placeholder must be deterministic");

    // Different subject should generally differ in id (derived from subject).
    let (_, bc) = call(router(), "POST", "/certificates", Some(r#"{"subject":"other.example"}"#)).await;
    let vc = json(&bc);
    assert_ne!(va["id"], vc["id"], "id placeholder must be derived from the subject, not a constant");
}

// ---- Conflict ---------------------------------------------------------------

#[tokio::test]
async fn duplicate_register_is_409_and_keeps_original() {
    let app = router();
    let (s, _) = call(app.clone(), "POST", "/certificates", Some(r#"{"subject":"dup.com"}"#)).await;
    assert_eq!(s, StatusCode::CREATED, "first POST 201");

    let (s, b) = call(app.clone(), "POST", "/certificates", Some(r#"{"subject":"dup.com"}"#)).await;
    assert_eq!(s, StatusCode::CONFLICT, "second POST of same subject must be 409 Conflict");
    let v = json(&b);
    assert!(
        v["message"].as_str().map(|m| !m.is_empty()).unwrap_or(false),
        "409 body must carry a non-empty `message` from the domain error type"
    );

    // Original entry remains intact and listed exactly once.
    let (s, b) = call(app.clone(), "GET", "/certificates", None).await;
    assert_eq!(s, StatusCode::OK);
    let arr = json(&b)["certificates"].as_array().unwrap().clone();
    assert_eq!(arr.len(), 1, "conflict must not duplicate or drop the existing entry");
    assert_eq!(arr[0]["subject"], "dup.com");
}

// ---- Validation -------------------------------------------------------------

#[tokio::test]
async fn empty_subject_is_400_and_stores_nothing() {
    let app = router();
    let (s, b) = call(app.clone(), "POST", "/certificates", Some(r#"{"subject":""}"#)).await;
    assert_eq!(s, StatusCode::BAD_REQUEST, "empty subject -> 400 validation cause");
    let v = json(&b);
    assert!(
        v["message"].as_str().map(|m| !m.is_empty()).unwrap_or(false),
        "400 body must carry a non-empty `message`"
    );

    // Nothing stored: list stays empty and a read 404s.
    let (s, b) = call(app.clone(), "GET", "/certificates", None).await;
    assert_eq!(s, StatusCode::OK);
    assert!(json(&b)["certificates"].as_array().unwrap().is_empty(), "rejected create must store nothing");

    let (s, _) = call(app.clone(), "GET", "/certificates/", None).await;
    let _ = s; // trailing-slash routing is impl-defined; the empty-list check above is authoritative.
}

#[tokio::test]
async fn missing_subject_field_is_400() {
    let app = router();
    let (s, _) = call(app.clone(), "POST", "/certificates", Some(r#"{}"#)).await;
    assert_eq!(s, StatusCode::BAD_REQUEST, "body missing `subject` -> 400");

    // store unchanged
    let (s, b) = call(app.clone(), "GET", "/certificates", None).await;
    assert_eq!(s, StatusCode::OK);
    assert!(json(&b)["certificates"].as_array().unwrap().is_empty(), "rejected create must store nothing");
}

// ---- Not-found read ---------------------------------------------------------

#[tokio::test]
async fn read_missing_is_404_with_message() {
    let app = router();
    let (s, b) = call(app.clone(), "GET", "/certificates/unknown.example", None).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "unknown subject must read 404");
    let v = json(&b);
    assert!(v.get("message").is_some(), "404 body must carry a `message` field (ApiError shape)");
    assert!(
        v["message"].as_str().map(|m| !m.is_empty()).unwrap_or(false),
        "message must be a non-empty human-readable string"
    );
}

// ---- List -------------------------------------------------------------------

#[tokio::test]
async fn list_empty_then_subject_ascending() {
    let app = router();

    let (s, b) = call(app.clone(), "GET", "/certificates", None).await;
    assert_eq!(s, StatusCode::OK, "list must be 200 even when empty");
    let v = json(&b);
    // Must be exactly {"certificates":[]} shape.
    assert!(v.get("certificates").is_some(), "list response must use the `certificates` field");
    assert!(v["certificates"].as_array().unwrap().is_empty(), "empty registry lists []");

    // Insert out of order.
    call(app.clone(), "POST", "/certificates", Some(r#"{"subject":"charlie.example"}"#)).await;
    call(app.clone(), "POST", "/certificates", Some(r#"{"subject":"alpha.example"}"#)).await;
    call(app.clone(), "POST", "/certificates", Some(r#"{"subject":"bravo.example"}"#)).await;

    let (s, b) = call(app.clone(), "GET", "/certificates", None).await;
    assert_eq!(s, StatusCode::OK);
    let arr = json(&b)["certificates"].as_array().unwrap().clone();
    let subjects: Vec<String> = arr.iter().map(|e| e["subject"].as_str().unwrap().to_string()).collect();
    assert_eq!(
        subjects,
        vec!["alpha.example", "bravo.example", "charlie.example"],
        "list must be subject-ascending"
    );
    assert_eq!(arr.len(), 3, "exactly the three registered subjects must be listed");
}

// ---- Delete -----------------------------------------------------------------

#[tokio::test]
async fn delete_existing_then_missing() {
    let app = router();
    call(app.clone(), "POST", "/certificates", Some(r#"{"subject":"del.example"}"#)).await;

    let (s, b) = call(app.clone(), "DELETE", "/certificates/del.example", None).await;
    assert_eq!(s, StatusCode::NO_CONTENT, "delete of existing subject must be 204");
    assert!(b.is_empty(), "204 body must be empty");

    let (s, _) = call(app.clone(), "GET", "/certificates/del.example", None).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "deleted subject must read as 404");

    let (s, b) = call(app.clone(), "DELETE", "/certificates/del.example", None).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "delete of an unregistered subject must be 404");
    let v = json(&b);
    assert!(
        v["message"].as_str().map(|m| !m.is_empty()).unwrap_or(false),
        "404 delete body must carry a non-empty `message`"
    );
}

// ---- Independence -----------------------------------------------------------

#[tokio::test]
async fn instances_are_independent() {
    let a = router();
    let b = router();
    call(a.clone(), "POST", "/certificates", Some(r#"{"subject":"iso.example"}"#)).await;

    // b is a fresh, empty, independent registry.
    let (s, body) = call(b.clone(), "GET", "/certificates", None).await;
    assert_eq!(s, StatusCode::OK);
    assert!(json(&body)["certificates"].as_array().unwrap().is_empty(), "each router() must own an independent empty registry");

    let (s, _) = call(b.clone(), "GET", "/certificates/iso.example", None).await;
    assert_eq!(s, StatusCode::NOT_FOUND, "an entry in registry a must not be visible in registry b");
}

// ---- Cause-driven status mapping (one error type) ---------------------------

#[tokio::test]
async fn distinct_causes_map_to_distinct_statuses() {
    // 400 (validation), 409 (conflict), 404 (not-found) must all be reachable
    // and distinct, all carrying an ApiError-shaped `message`.
    let app = router();

    // validation
    let (s400, b400) = call(app.clone(), "POST", "/certificates", Some(r#"{"subject":""}"#)).await;
    assert_eq!(s400, StatusCode::BAD_REQUEST);
    assert!(json(&b400).get("message").is_some());

    // set up a real entry
    let (s, _) = call(app.clone(), "POST", "/certificates", Some(r#"{"subject":"cause.example"}"#)).await;
    assert_eq!(s, StatusCode::CREATED);

    // conflict
    let (s409, b409) = call(app.clone(), "POST", "/certificates", Some(r#"{"subject":"cause.example"}"#)).await;
    assert_eq!(s409, StatusCode::CONFLICT);
    assert!(json(&b409).get("message").is_some());

    // not-found
    let (s404, b404) = call(app.clone(), "GET", "/certificates/never.example", None).await;
    assert_eq!(s404, StatusCode::NOT_FOUND);
    assert!(json(&b404).get("message").is_some());

    // The three must genuinely differ (a stub returning one fixed status fails here).
    assert_ne!(s400, s409);
    assert_ne!(s409, s404);
    assert_ne!(s400, s404);
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
        "axum": 'axum = { version = "0.8", default-features = false }',
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
    """Verify the certificate registry HTTP API added to shuttle-common."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_certs_api_source_exists(self):
        """common/src/certs_api.rs must exist and be non-trivial."""
        assert os.path.isfile(CERTS_API_SRC), "common/src/certs_api.rs not created"
        assert os.path.getsize(CERTS_API_SRC) > 200, "certs_api.rs is implausibly small"

    def test_router_constructor_declared(self):
        """certs_api.rs must declare a public `fn router() -> ... Router`."""
        with open(CERTS_API_SRC) as f:
            src = f.read()
        assert re.search(r"pub\s+fn\s+router\s*\(", src), "no `pub fn router(` constructor found"
        assert re.search(r"Router", src), "router() must build an axum Router"

    def test_uses_certificate_models(self):
        """Responses must use the existing CertificateResponse/list model types."""
        with open(CERTS_API_SRC) as f:
            src = f.read()
        assert "CertificateResponse" in src, "must reuse the crate's CertificateResponse type"
        assert "CertificateListResponse" in src, "list must reuse CertificateListResponse"

    def test_uses_single_apierror_shape(self):
        """Error bodies must be built on the crate's ApiError shape."""
        with open(CERTS_API_SRC) as f:
            src = f.read()
        assert "ApiError" in src, "error responses must use the crate's ApiError type"

    def test_module_declared_gated_in_lib(self):
        """lib.rs must declare `certs_api` gated behind the axum feature."""
        with open(LIB_RS) as f:
            lib = f.read()
        assert "certs_api" in lib, "lib.rs does not declare the certs_api module"
        m = re.search(r'(#\[cfg\([^\)]*feature\s*=\s*"axum"[^\)]*\)\]\s*)pub\s+mod\s+certs_api', lib)
        assert m is not None, "module `certs_api` must be #[cfg(feature = \"axum\")]-gated"

    def test_agent_integration_test_exists(self):
        """The agent's own in-process integration test must exist and drive router()."""
        assert os.path.isfile(AGENT_TEST), "common/tests/certs_api.rs not created"
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
        """The exact acceptance command must pass: cargo test ... --test certs_api."""
        proc = subprocess.run(
            ["cargo", "test", "-p", "shuttle-common", "--features", FEATURES, "--test", "certs_api"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=RUN_TIMEOUT, env=_cargo_env(),
        )
        out = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, f"acceptance command failed:\n{out[-4000:]}"
        assert "test result: ok." in out, f"acceptance test did not report ok:\n{out[-2000:]}"

    def test_register_then_read(self):
        """POST new -> 201 CertificateResponse(subject); GET -> 200 with full fields."""
        _assert_test_passed(_run_verify("register_then_read"), "register_then_read")

    def test_placeholders_are_deterministic_per_subject(self):
        """id/serial_hex/not_after are deterministic per subject (no clock/randomness)."""
        _assert_test_passed(
            _run_verify("placeholders_are_deterministic_per_subject"),
            "placeholders_are_deterministic_per_subject",
        )

    def test_duplicate_register_is_409(self):
        """Second POST of same subject -> 409, original kept, no duplicate entry."""
        _assert_test_passed(
            _run_verify("duplicate_register_is_409_and_keeps_original"),
            "duplicate_register_is_409_and_keeps_original",
        )

    def test_empty_subject_is_400_and_stores_nothing(self):
        """POST empty subject -> 400 validation cause and nothing stored."""
        _assert_test_passed(
            _run_verify("empty_subject_is_400_and_stores_nothing"),
            "empty_subject_is_400_and_stores_nothing",
        )

    def test_missing_subject_field_is_400(self):
        """POST body missing the `subject` field -> 400 and store unchanged."""
        _assert_test_passed(
            _run_verify("missing_subject_field_is_400"),
            "missing_subject_field_is_400",
        )

    def test_read_missing_is_404_with_message(self):
        """GET unknown subject -> 404 with an ApiError-shaped JSON `message` field."""
        _assert_test_passed(
            _run_verify("read_missing_is_404_with_message"),
            "read_missing_is_404_with_message",
        )

    def test_list_empty_then_subject_ascending(self):
        """List: {"certificates":[]} when empty; subject-ascending array otherwise."""
        _assert_test_passed(
            _run_verify("list_empty_then_subject_ascending"),
            "list_empty_then_subject_ascending",
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

    def test_distinct_causes_map_to_distinct_statuses(self):
        """400/409/404 are all reachable, distinct, and each carries a `message`."""
        _assert_test_passed(
            _run_verify("distinct_causes_map_to_distinct_statuses"),
            "distinct_causes_map_to_distinct_statuses",
        )
