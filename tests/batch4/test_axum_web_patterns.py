"""
Test for 'axum-web-patterns' skill (variant ext4) — API-key gated HTTP API in
shuttle-common.

The task asks the agent to add `common/src/auth_api.rs` exposing
`pub fn router() -> axum::Router`, gated behind the `axum` feature. The router
mixes public and protected routes, where protection is enforced by a *reusable
typed request component* (a type used directly as a handler parameter) that
inspects the `Authorization` header and admits a request only when it is exactly
`Bearer sk-test-key`. Auth failures short-circuit before the handler body and
return the crate's standard `ApiError`-shaped JSON body with status `401`.

Routes:

    GET /public/ping     — no auth, always 200
    GET /private/whoami  — auth required, returns the caller identity (JSON)
    GET /private/data    — auth required, returns a fixed protected payload

Verification strategy
---------------------
We do NOT trust the agent's own `common/tests/auth_api.rs`. For the L2
behavioral checks this harness injects an *independent* Rust integration test
(`tests/_auth_api_verify.rs`) that imports the real `router()`, drives it fully
in-process via `tower::ServiceExt::oneshot` (no TCP / no socket), and asserts
every acceptance scenario — public always-200, protected 200-with-valid-key
(and identity echoed), and 401 for missing / wrong-key / malformed-scheme. We
add the required dev-dependencies ourselves so the checks do not depend on what
the agent wrote into `Cargo.toml`. Each L2 pytest method runs one named Rust
test, mapping 1:1 to a requirement.

A naive implementation that returns 200 for protected routes regardless of the
header, or that hardcodes the caller identity without validating the key, MUST
fail (covered by `wrong_key_*`, `missing_header_*`, `malformed_scheme_*` and the
`whoami` identity / wrong-key contrast cases below).

Native command of record:
    cargo test -p shuttle-common --features axum --test auth_api
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/shuttle"
COMMON_DIR = os.path.join(REPO_DIR, "common")
AUTH_API_SRC = os.path.join(COMMON_DIR, "src", "auth_api.rs")
LIB_RS = os.path.join(COMMON_DIR, "src", "lib.rs")
AGENT_TEST = os.path.join(COMMON_DIR, "tests", "auth_api.rs")
CARGO_TOML = os.path.join(COMMON_DIR, "Cargo.toml")

VERIFY_TEST_NAME = "_auth_api_verify"
VERIFY_TEST_PATH = os.path.join(COMMON_DIR, "tests", VERIFY_TEST_NAME + ".rs")

BUILD_TIMEOUT = 600
RUN_TIMEOUT = 600

VALID_KEY = "sk-test-key"


# ---------------------------------------------------------------------------
# Independent in-process Rust integration test injected into the repo.
# It only depends on the public surface: `shuttle_common::auth_api::router()`.
# ---------------------------------------------------------------------------
VERIFY_RS = r'''
// AUTO-GENERATED independent verification test for the axum-web-patterns task
// (variant ext4). Drives `router()` fully in-process (no socket) via tower
// oneshot, exercising public + API-key-gated routes.
#![cfg(feature = "axum")]

use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt; // for `oneshot`

use shuttle_common::auth_api::router;

const VALID: &str = "Bearer sk-test-key";

/// Issue a GET, optionally with an `Authorization` header. Returns the status
/// and the raw body bytes.
async fn get(app: axum::Router, uri: &str, auth: Option<&str>) -> (StatusCode, Vec<u8>) {
    let mut builder = Request::builder().method("GET").uri(uri);
    if let Some(a) = auth {
        builder = builder.header("authorization", a);
    }
    let req = builder.body(Body::empty()).unwrap();
    let resp = app.oneshot(req).await.unwrap();
    let status = resp.status();
    let bytes = resp.into_body().collect().await.unwrap().to_bytes().to_vec();
    (status, bytes)
}

fn json(bytes: &[u8]) -> Value {
    serde_json::from_slice(bytes).expect("response body must be valid JSON")
}

/// Assert the body is an ApiError-shaped object carrying a non-empty `message`.
fn assert_error_message(bytes: &[u8]) {
    let v = json(bytes);
    assert!(
        v.get("message").is_some(),
        "error body must carry a `message` field, got: {v}"
    );
    assert!(
        v["message"].as_str().map(|m| !m.is_empty()).unwrap_or(false),
        "`message` must be a non-empty human-readable string, got: {v}"
    );
}

// --- public route -------------------------------------------------------

#[tokio::test]
async fn public_ping_ok_without_header() {
    let app = router();
    let (s, b) = get(app, "/public/ping", None).await;
    assert_eq!(s, StatusCode::OK, "public ping must be 200 without any header");
    assert!(!b.is_empty(), "public ping must return a small fixed body");
}

#[tokio::test]
async fn public_ping_unaffected_by_bad_auth() {
    // A wrong key and a missing key must NOT turn the public route into 401.
    let app = router();
    let (s, _) = get(app.clone(), "/public/ping", Some("Bearer wrong")).await;
    assert_eq!(s, StatusCode::OK, "wrong key must not affect the public route");

    let (s, _) = get(app.clone(), "/public/ping", Some("garbage")).await;
    assert_eq!(s, StatusCode::OK, "malformed header must not affect the public route");
}

// --- protected route: happy path ---------------------------------------

#[tokio::test]
async fn whoami_with_valid_key_returns_caller_identity() {
    let app = router();
    let (s, b) = get(app, "/private/whoami", Some(VALID)).await;
    assert_eq!(s, StatusCode::OK, "whoami with valid key must be 200");
    let v = json(&b);
    // The caller identity must be derived from the validated key and must
    // appear *somewhere* as a stable string field in the JSON object. A naive
    // impl that ignores the key cannot produce the key as the identity AND also
    // pass the wrong-key 401 case below.
    let body_str = String::from_utf8_lossy(&b);
    assert!(
        body_str.contains("sk-test-key"),
        "whoami body must carry the caller identity derived from the key, got: {body_str}"
    );
    // It must be a JSON object (not a bare string / array).
    assert!(v.is_object(), "whoami body must be a JSON object, got: {v}");
}

#[tokio::test]
async fn data_with_valid_key_returns_payload() {
    let app = router();
    let (s, b) = get(app, "/private/data", Some(VALID)).await;
    assert_eq!(s, StatusCode::OK, "data with valid key must be 200");
    assert!(!b.is_empty(), "data must return a fixed non-empty payload");
    // Must be valid JSON (handlers return JSON via axum::Json).
    let _ = json(&b);
}

// --- protected route: rejection cases ----------------------------------

#[tokio::test]
async fn whoami_missing_header_is_401() {
    let app = router();
    let (s, b) = get(app, "/private/whoami", None).await;
    assert_eq!(s, StatusCode::UNAUTHORIZED, "missing Authorization must be 401");
    assert_error_message(&b);
    // Must NOT leak the protected identity payload.
    assert!(
        !String::from_utf8_lossy(&b).contains("sk-test-key"),
        "rejected request must not run the protected handler / leak identity"
    );
}

#[tokio::test]
async fn data_missing_header_is_401() {
    let app = router();
    let (s, b) = get(app, "/private/data", None).await;
    assert_eq!(s, StatusCode::UNAUTHORIZED, "missing Authorization must be 401 on /private/data");
    assert_error_message(&b);
}

#[tokio::test]
async fn wrong_key_is_401_on_both_routes() {
    let app = router();
    let (s, b) = get(app.clone(), "/private/whoami", Some("Bearer wrong")).await;
    assert_eq!(s, StatusCode::UNAUTHORIZED, "wrong key must be 401 on whoami");
    assert_error_message(&b);

    let (s, b) = get(app.clone(), "/private/data", Some("Bearer wrong")).await;
    assert_eq!(s, StatusCode::UNAUTHORIZED, "wrong key must be 401 on data");
    assert_error_message(&b);
}

#[tokio::test]
async fn malformed_scheme_is_401() {
    // The raw key with no `Bearer ` scheme must be rejected.
    let app = router();
    let (s, b) = get(app.clone(), "/private/whoami", Some("sk-test-key")).await;
    assert_eq!(s, StatusCode::UNAUTHORIZED, "bare key (no Bearer scheme) must be 401");
    assert_error_message(&b);

    // A different scheme carrying the right value must also be rejected.
    let (s, _) = get(app.clone(), "/private/whoami", Some("Basic sk-test-key")).await;
    assert_eq!(s, StatusCode::UNAUTHORIZED, "wrong scheme must be 401 even with the right value");
}

#[tokio::test]
async fn key_match_is_exact_not_prefix() {
    // A naive `starts_with`/`contains` check would wrongly admit these.
    let app = router();
    let (s, _) = get(app.clone(), "/private/whoami", Some("Bearer sk-test-key-extra")).await;
    assert_eq!(s, StatusCode::UNAUTHORIZED, "a superset key must not be admitted");

    let (s, _) = get(app.clone(), "/private/whoami", Some("Bearer sk-test")).await;
    assert_eq!(s, StatusCode::UNAUTHORIZED, "a prefix of the key must not be admitted");
}

#[tokio::test]
async fn valid_key_admits_both_protected_routes_repeatably() {
    // The reusable component must work uniformly: same valid key admits every
    // protected route, and repeated calls are stable (no one-shot state).
    let app = router();
    for _ in 0..2 {
        let (s, _) = get(app.clone(), "/private/whoami", Some(VALID)).await;
        assert_eq!(s, StatusCode::OK, "valid key must repeatedly admit whoami");
        let (s, _) = get(app.clone(), "/private/data", Some(VALID)).await;
        assert_eq!(s, StatusCode::OK, "valid key must repeatedly admit data");
    }
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
    """Verify the API-key gated HTTP API added to shuttle-common (ext4)."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_auth_api_source_exists(self):
        """common/src/auth_api.rs must exist and be non-trivial."""
        assert os.path.isfile(AUTH_API_SRC), "common/src/auth_api.rs not created"
        assert os.path.getsize(AUTH_API_SRC) > 200, "auth_api.rs is implausibly small"

    def test_router_constructor_declared(self):
        """auth_api.rs must declare a public `fn router() -> ... Router`."""
        with open(AUTH_API_SRC) as f:
            src = f.read()
        assert re.search(r"pub\s+fn\s+router\s*\(", src), "no `pub fn router(` constructor found"
        assert re.search(r"Router", src), "router() must build an axum Router"

    def test_fixed_api_key_constant_present(self):
        """The documented fixed key value must appear in the module source."""
        with open(AUTH_API_SRC) as f:
            src = f.read()
        assert VALID_KEY in src, (
            f"the accepted API key constant `{VALID_KEY}` must be defined in auth_api.rs"
        )

    def test_reusable_extractor_is_handler_param(self):
        """A reusable typed request component (extractor) must exist and the
        protected routes must reference the protected paths.

        We check structurally that the module declares the three documented
        routes; the behavioral 'extractor short-circuits' contract is verified
        dynamically in L2."""
        with open(AUTH_API_SRC) as f:
            src = f.read()
        for path in ("/public/ping", "/private/whoami", "/private/data"):
            assert path in src, f"route `{path}` not wired in auth_api.rs"

    def test_module_declared_gated_in_lib(self):
        """lib.rs must declare `auth_api` gated behind the axum feature."""
        with open(LIB_RS) as f:
            lib = f.read()
        assert "auth_api" in lib, "lib.rs does not declare the auth_api module"
        m = re.search(
            r'(#\[cfg\([^\)]*feature\s*=\s*"axum"[^\)]*\)\]\s*)pub\s+mod\s+auth_api',
            lib,
        )
        assert m is not None, 'module `auth_api` must be #[cfg(feature = "axum")]-gated'

    def test_agent_integration_test_exists(self):
        """The agent's own in-process integration test must exist and drive router()."""
        assert os.path.isfile(AGENT_TEST), "common/tests/auth_api.rs not created"
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
        """The exact acceptance command must pass: cargo test ... --test auth_api."""
        proc = subprocess.run(
            ["cargo", "test", "-p", "shuttle-common", "--features", "axum", "--test", "auth_api"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=RUN_TIMEOUT, env=_cargo_env(),
        )
        out = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, f"acceptance command failed:\n{out[-4000:]}"
        assert "test result: ok." in out, f"acceptance test did not report ok:\n{out[-2000:]}"

    def test_public_ping_ok_without_header(self):
        """GET /public/ping -> 200 with a non-empty body and no auth header."""
        _assert_test_passed(
            _run_verify("public_ping_ok_without_header"),
            "public_ping_ok_without_header",
        )

    def test_public_ping_unaffected_by_bad_auth(self):
        """Wrong / malformed auth must NOT turn the public route into 401."""
        _assert_test_passed(
            _run_verify("public_ping_unaffected_by_bad_auth"),
            "public_ping_unaffected_by_bad_auth",
        )

    def test_whoami_with_valid_key_returns_caller_identity(self):
        """GET /private/whoami + Bearer sk-test-key -> 200 with caller identity."""
        _assert_test_passed(
            _run_verify("whoami_with_valid_key_returns_caller_identity"),
            "whoami_with_valid_key_returns_caller_identity",
        )

    def test_data_with_valid_key_returns_payload(self):
        """GET /private/data + Bearer sk-test-key -> 200 with a fixed JSON payload."""
        _assert_test_passed(
            _run_verify("data_with_valid_key_returns_payload"),
            "data_with_valid_key_returns_payload",
        )

    def test_whoami_missing_header_is_401(self):
        """GET /private/whoami with no Authorization -> 401 ApiError, no leak."""
        _assert_test_passed(
            _run_verify("whoami_missing_header_is_401"),
            "whoami_missing_header_is_401",
        )

    def test_data_missing_header_is_401(self):
        """GET /private/data with no Authorization -> 401 ApiError body."""
        _assert_test_passed(
            _run_verify("data_missing_header_is_401"),
            "data_missing_header_is_401",
        )

    def test_wrong_key_is_401_on_both_routes(self):
        """Bearer wrong -> 401 on both protected routes (naive 200 impl fails)."""
        _assert_test_passed(
            _run_verify("wrong_key_is_401_on_both_routes"),
            "wrong_key_is_401_on_both_routes",
        )

    def test_malformed_scheme_is_401(self):
        """Bare key (no Bearer) and wrong scheme -> 401."""
        _assert_test_passed(
            _run_verify("malformed_scheme_is_401"),
            "malformed_scheme_is_401",
        )

    def test_key_match_is_exact_not_prefix(self):
        """Superset / prefix of the key -> 401 (rejects naive contains/starts_with)."""
        _assert_test_passed(
            _run_verify("key_match_is_exact_not_prefix"),
            "key_match_is_exact_not_prefix",
        )

    def test_valid_key_admits_both_protected_routes_repeatably(self):
        """The reusable component admits every protected route, stably across calls."""
        _assert_test_passed(
            _run_verify("valid_key_admits_both_protected_routes_repeatably"),
            "valid_key_admits_both_protected_routes_repeatably",
        )
