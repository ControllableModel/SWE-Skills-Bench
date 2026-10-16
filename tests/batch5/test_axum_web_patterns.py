"""
Test for 'axum-web-patterns' skill (variant ext5) — request-id middleware router
in shuttle-common.

Variant task
------------
The agent must add `common/src/request_id_api.rs` exposing
`pub fn router() -> axum::Router`, gated behind the `axum` feature. Every request
to the router passes through a middleware layer that determines a per-request id:

  * if an incoming `x-request-id` header is present and non-empty, that value is used;
  * otherwise the deterministic fallback constant `"generated"` is used (no clock,
    no randomness).

The chosen id is injected into request-scoped data (an extension), read by the
handlers from that injected value (NOT by re-reading the header), and echoed on
the `x-request-id` response header of *every* route — including the error route.

Routes:
    GET /echo  -> 200, JSON body that reports the request id the handler saw,
                  e.g. {"request_id": "..."}.
    GET /fail  -> a 5xx error built from the crate's `ApiError` type, whose body
                  is a JSON object with a `message` field — and which still
                  carries the `x-request-id` response header.

Verification strategy
---------------------
We do NOT trust the agent's own `common/tests/request_id_api.rs`. For the L2
behavioral checks we inject an *independent* Rust integration test
(`tests/_request_id_api_verify.rs`) that imports the real public `router()`,
drives it fully in-process with `tower::ServiceExt::oneshot` (no TCP port), and
asserts each acceptance scenario with concrete values: status codes, the exact
`x-request-id` response header bytes, the JSON `request_id`/`message` fields, the
deterministic `"generated"` fallback, the empty-header fallback, and the
header/body agreement invariant. We add the dev-dependencies ourselves so the
checks never depend on what the agent wrote into Cargo.toml.

A naive implementation that omits the response header, ignores the incoming
header, hardcodes a single id, or lets the handler read the header directly
(instead of the middleware-injected value) MUST fail these checks.

Native command of record:
    cargo test -p shuttle-common --features axum --test request_id_api
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/shuttle"
COMMON_DIR = os.path.join(REPO_DIR, "common")
REQUEST_ID_API_SRC = os.path.join(COMMON_DIR, "src", "request_id_api.rs")
LIB_RS = os.path.join(COMMON_DIR, "src", "lib.rs")
AGENT_TEST = os.path.join(COMMON_DIR, "tests", "request_id_api.rs")
CARGO_TOML = os.path.join(COMMON_DIR, "Cargo.toml")

VERIFY_TEST_NAME = "_request_id_api_verify"
VERIFY_TEST_PATH = os.path.join(COMMON_DIR, "tests", VERIFY_TEST_NAME + ".rs")

BUILD_TIMEOUT = 900
RUN_TIMEOUT = 900


# ---------------------------------------------------------------------------
# Independent in-process Rust integration test injected into the repo.
# It only depends on the public surface: `shuttle_common::request_id_api::router()`
# and the HTTP-level behavior (headers, status, JSON). It does not import any of
# the agent's private items, so it cannot be fooled by the agent's own tests.
# ---------------------------------------------------------------------------
VERIFY_RS = r'''
// AUTO-GENERATED independent verification test for the axum-web-patterns task (ext5).
// Drives `router()` fully in-process (no socket) via tower oneshot.
#![cfg(feature = "axum")]

use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt; // for `oneshot`

use shuttle_common::request_id_api::router;

/// Issue one request. `header` is an optional value for the `x-request-id` header
/// (Some("") drives the empty-header case; None omits the header entirely).
/// Returns (status, response-header-x-request-id-or-None, body-bytes).
async fn call(
    app: axum::Router,
    method: &str,
    uri: &str,
    header: Option<&str>,
) -> (StatusCode, Option<String>, Vec<u8>) {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(h) = header {
        builder = builder.header("x-request-id", h);
    }
    let req = builder.body(Body::empty()).unwrap();
    let resp = app.oneshot(req).await.unwrap();
    let status = resp.status();
    let hdr = resp
        .headers()
        .get("x-request-id")
        .map(|v| v.to_str().unwrap().to_string());
    let bytes = resp.into_body().collect().await.unwrap().to_bytes().to_vec();
    (status, hdr, bytes)
}

fn json(bytes: &[u8]) -> Value {
    serde_json::from_slice(bytes).expect("response body must be valid JSON")
}

/// Pull the body's request id out of whatever reasonable field name the impl used.
/// The doc's example is {"request_id": "..."}; accept a couple of synonyms so the
/// test is robust to field naming while still requiring the *value* to be right.
fn body_id(v: &Value) -> String {
    for k in ["request_id", "requestId", "id", "request-id"] {
        if let Some(s) = v.get(k).and_then(|x| x.as_str()) {
            return s.to_string();
        }
    }
    panic!("echo body must report the request id in a string field (e.g. `request_id`): {v}");
}

#[tokio::test]
async fn echo_with_header_echoes_value() {
    let app = router();
    let (s, hdr, b) = call(app.clone(), "GET", "/echo", Some("abc123")).await;
    assert_eq!(s, StatusCode::OK, "/echo with header must be 200");
    assert_eq!(
        hdr.as_deref(),
        Some("abc123"),
        "response must carry x-request-id equal to the provided header"
    );
    let v = json(&b);
    assert_eq!(body_id(&v), "abc123", "handler must observe the provided id");
}

#[tokio::test]
async fn echo_without_header_uses_generated_fallback() {
    let app = router();
    let (s, hdr, b) = call(app.clone(), "GET", "/echo", None).await;
    assert_eq!(s, StatusCode::OK, "/echo without header must be 200");
    assert_eq!(
        hdr.as_deref(),
        Some("generated"),
        "missing header must fall back to the constant `generated` on the response header"
    );
    assert_eq!(
        body_id(&json(&b)),
        "generated",
        "missing header must report `generated` in the body too"
    );
}

#[tokio::test]
async fn echo_with_empty_header_uses_generated_fallback() {
    let app = router();
    let (s, hdr, b) = call(app.clone(), "GET", "/echo", Some("")).await;
    assert_eq!(s, StatusCode::OK, "/echo with empty header must be 200");
    assert_eq!(
        hdr.as_deref(),
        Some("generated"),
        "an empty x-request-id value must fall back to `generated`"
    );
    assert_eq!(
        body_id(&json(&b)),
        "generated",
        "empty header must report `generated` in the body"
    );
}

#[tokio::test]
async fn header_is_not_a_hardcoded_constant() {
    // Two different provided ids must both be reflected verbatim. A stub that
    // hardcodes a single value (or always returns `generated`) fails here.
    let app = router();
    let (_, h1, b1) = call(app.clone(), "GET", "/echo", Some("one-AA")).await;
    let (_, h2, b2) = call(app.clone(), "GET", "/echo", Some("two-BB")).await;
    assert_eq!(h1.as_deref(), Some("one-AA"));
    assert_eq!(h2.as_deref(), Some("two-BB"));
    assert_eq!(body_id(&json(&b1)), "one-AA");
    assert_eq!(body_id(&json(&b2)), "two-BB");
    assert_ne!(h1, h2, "distinct incoming ids must produce distinct response ids");
}

#[tokio::test]
async fn fail_route_is_5xx_with_message_and_keeps_id() {
    let app = router();
    let (s, hdr, b) = call(app.clone(), "GET", "/fail", Some("zzz")).await;
    assert!(
        s.is_server_error(),
        "/fail must return a 5xx status, got {s}"
    );
    assert_eq!(
        hdr.as_deref(),
        Some("zzz"),
        "the middleware must set x-request-id even on the error response"
    );
    let v = json(&b);
    assert!(
        v.get("message").and_then(|m| m.as_str()).map(|m| !m.is_empty()).unwrap_or(false),
        "error body must be the crate's ApiError shape with a non-empty `message`: {v}"
    );
}

#[tokio::test]
async fn fail_route_carries_generated_when_no_header() {
    // Even on the error path the deterministic fallback must apply to the header.
    let app = router();
    let (s, hdr, b) = call(app.clone(), "GET", "/fail", None).await;
    assert!(s.is_server_error(), "/fail must be 5xx, got {s}");
    assert_eq!(
        hdr.as_deref(),
        Some("generated"),
        "error path with no incoming header must still emit the `generated` fallback header"
    );
    let v = json(&b);
    assert!(v.get("message").is_some(), "error body must have a `message` field: {v}");
}

#[tokio::test]
async fn body_id_always_equals_response_header_id() {
    // Invariant across several inputs: the id the handler saw == the id the layer
    // wrote to the response header. This is what proves handler and middleware
    // agree on the *injected* value rather than each reading the header on its own.
    let app = router();
    for h in [Some("agree-1"), Some("agree-2"), None, Some("")] {
        let (s, hdr, b) = call(app.clone(), "GET", "/echo", h).await;
        assert_eq!(s, StatusCode::OK);
        let header_id = hdr.expect("every /echo response must carry x-request-id");
        let body = body_id(&json(&b));
        assert_eq!(
            body, header_id,
            "body request_id ({body}) must equal response header x-request-id ({header_id})"
        );
    }
}
'''


# ---------------------------------------------------------------------------
# Helpers: deterministic env, dev-dep injection, single-test runner.
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
    assert "test result: ok." in out, f"cargo did not report ok for `{test_name}`:\n{out[-2000:]}"
    assert "0 passed" not in out, f"the named test `{test_name}` did not actually run:\n{out[-2000:]}"


class TestAxumWebPatterns:
    """Verify the request-id middleware router added to shuttle-common."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_request_id_api_source_exists(self):
        """common/src/request_id_api.rs must exist and be non-trivial."""
        assert os.path.isfile(REQUEST_ID_API_SRC), "common/src/request_id_api.rs not created"
        assert os.path.getsize(REQUEST_ID_API_SRC) > 200, "request_id_api.rs is implausibly small"

    def test_router_constructor_declared(self):
        """request_id_api.rs must declare a public `fn router() -> ... Router`."""
        with open(REQUEST_ID_API_SRC) as f:
            src = f.read()
        assert re.search(r"pub\s+fn\s+router\s*\(", src), "no `pub fn router(` constructor found"
        assert re.search(r"Router", src), "router() must build an axum Router"

    def test_generated_constant_present(self):
        """The deterministic fallback literal `generated` must appear in the source."""
        with open(REQUEST_ID_API_SRC) as f:
            src = f.read()
        assert '"generated"' in src, (
            'the documented deterministic fallback constant "generated" must be present'
        )

    def test_no_randomness_or_clock(self):
        """The fallback must be deterministic: no rand/uuid/SystemTime/Instant usage."""
        with open(REQUEST_ID_API_SRC) as f:
            src = f.read()
        for banned in ("rand", "uuid", "Uuid", "SystemTime", "Instant", "thread_rng"):
            assert banned not in src, (
                f"request id must be deterministic; found forbidden `{banned}` "
                "(no clock/randomness allowed)"
            )

    def test_uses_middleware_and_extension(self):
        """Id must be injected via middleware and read from request-scoped data."""
        with open(REQUEST_ID_API_SRC) as f:
            src = f.read()
        # axum middleware: from_fn / from_fn_with_state / a Layer applied to routes.
        assert re.search(r"from_fn|middleware::|\.layer\(", src), (
            "router() must attach a middleware layer (e.g. axum::middleware::from_fn / .layer)"
        )
        # injection + extraction of request-scoped data, not header re-reading.
        assert ("Extension" in src) or ("extensions" in src), (
            "the handler must read the id from request-scoped data (an Extension), "
            "not by re-parsing the header"
        )

    def test_module_declared_gated_in_lib(self):
        """lib.rs must declare `request_id_api` gated behind the axum feature."""
        with open(LIB_RS) as f:
            lib = f.read()
        assert "request_id_api" in lib, "lib.rs does not declare the request_id_api module"
        m = re.search(
            r'(#\[cfg\([^\)]*feature\s*=\s*"axum"[^\)]*\)\]\s*)pub\s+mod\s+request_id_api',
            lib,
        )
        assert m is not None, 'module `request_id_api` must be #[cfg(feature = "axum")]-gated'

    def test_agent_integration_test_exists(self):
        """The agent's own in-process integration test must exist and drive router()."""
        assert os.path.isfile(AGENT_TEST), "common/tests/request_id_api.rs not created"
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
        """The exact acceptance command must pass: cargo test ... --test request_id_api."""
        proc = subprocess.run(
            ["cargo", "test", "-p", "shuttle-common", "--features", "axum",
             "--test", "request_id_api"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=RUN_TIMEOUT, env=_cargo_env(),
        )
        out = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, f"acceptance command failed:\n{out[-4000:]}"
        assert "test result: ok." in out, f"acceptance test did not report ok:\n{out[-2000:]}"

    def test_echo_with_header_echoes_value(self):
        """GET /echo with x-request-id:abc123 -> 200, header & body both abc123."""
        _assert_test_passed(
            _run_verify("echo_with_header_echoes_value"),
            "echo_with_header_echoes_value",
        )

    def test_echo_without_header_uses_generated_fallback(self):
        """GET /echo with no header -> 200, header & body both `generated`."""
        _assert_test_passed(
            _run_verify("echo_without_header_uses_generated_fallback"),
            "echo_without_header_uses_generated_fallback",
        )

    def test_echo_with_empty_header_uses_generated_fallback(self):
        """GET /echo with an empty x-request-id value -> falls back to `generated`."""
        _assert_test_passed(
            _run_verify("echo_with_empty_header_uses_generated_fallback"),
            "echo_with_empty_header_uses_generated_fallback",
        )

    def test_header_is_not_a_hardcoded_constant(self):
        """Distinct incoming ids must each be reflected verbatim (no hardcoding)."""
        _assert_test_passed(
            _run_verify("header_is_not_a_hardcoded_constant"),
            "header_is_not_a_hardcoded_constant",
        )

    def test_fail_route_is_5xx_with_message_and_keeps_id(self):
        """GET /fail with id zzz -> 5xx ApiError {message:...} carrying x-request-id:zzz."""
        _assert_test_passed(
            _run_verify("fail_route_is_5xx_with_message_and_keeps_id"),
            "fail_route_is_5xx_with_message_and_keeps_id",
        )

    def test_fail_route_carries_generated_when_no_header(self):
        """GET /fail with no header -> 5xx error still carrying the `generated` fallback header."""
        _assert_test_passed(
            _run_verify("fail_route_carries_generated_when_no_header"),
            "fail_route_carries_generated_when_no_header",
        )

    def test_body_id_always_equals_response_header_id(self):
        """Invariant: the handler-observed id always equals the response header id."""
        _assert_test_passed(
            _run_verify("body_id_always_equals_response_header_id"),
            "body_id_always_equals_response_header_id",
        )
