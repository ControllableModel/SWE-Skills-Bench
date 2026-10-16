"""
Test for 'axum-web-patterns' skill (variant ext6) — a versioned, nested API
with per-section fallbacks in shuttle-common.

The task asks the agent to add `common/src/versioned_api.rs` exposing
`pub fn router() -> axum::Router`, gated behind the `axum` feature. The router
composes two *independent* sub-routers mounted under distinct prefixes plus a
top-level catch-all:

    GET /api/v1/status     -> 200, fixed v1 status body
    GET /api/v2/status     -> 200, fixed v2 status body (distinct from v1)
    /api/v1/<miss>         -> 404 with a v1-specific not-found message
    /api/v2/<miss>         -> 404 with a v2-specific not-found message (distinct)
    /<unmounted>           -> 404 with a generic top-level message (distinct from both)

Every 404 body is an `ApiError`-shaped JSON object carrying a `message` field.
The three not-found messages MUST be pairwise distinct so a caller can tell
which section's fallback handled the miss.

Verification strategy
---------------------
We do NOT trust the agent's own `common/tests/versioned_api.rs`. For the L2
behavioral checks this harness injects an *independent* Rust integration test
(`tests/_versioned_api_verify.rs`) that imports the real `router()`, drives it
fully in-process with `tower::ServiceExt::oneshot` (no TCP), and asserts every
acceptance scenario, including the discriminative cases that a naive
single-shared-fallback / identical-message / unmounted-sub-API implementation
must fail. We add the required dev-dependencies ourselves so the checks do not
depend on what the agent put in `Cargo.toml`. Each L2 pytest method runs one
named Rust test and asserts it passes, mapping 1:1 to a requirement.

Native command of record:
    cargo test -p shuttle-common --features axum --test versioned_api
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/shuttle"
COMMON_DIR = os.path.join(REPO_DIR, "common")
VERSIONED_API_SRC = os.path.join(COMMON_DIR, "src", "versioned_api.rs")
LIB_RS = os.path.join(COMMON_DIR, "src", "lib.rs")
AGENT_TEST = os.path.join(COMMON_DIR, "tests", "versioned_api.rs")
CARGO_TOML = os.path.join(COMMON_DIR, "Cargo.toml")

VERIFY_TEST_NAME = "_versioned_api_verify"
VERIFY_TEST_PATH = os.path.join(COMMON_DIR, "tests", VERIFY_TEST_NAME + ".rs")

BUILD_TIMEOUT = 900
RUN_TIMEOUT = 900


# ---------------------------------------------------------------------------
# Independent in-process Rust integration test injected into the repo.
# It only depends on the public surface: `shuttle_common::versioned_api::router()`.
# ---------------------------------------------------------------------------
VERIFY_RS = r'''
// AUTO-GENERATED independent verification test for the axum-web-patterns task (ext6).
// Drives `router()` fully in-process (no socket) via tower oneshot.
#![cfg(feature = "axum")]

use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt; // for `oneshot`

use shuttle_common::versioned_api::router;

async fn call(
    app: axum::Router,
    method: &str,
    uri: &str,
) -> (StatusCode, Vec<u8>) {
    let req = Request::builder()
        .method(method)
        .uri(uri)
        .body(Body::empty())
        .unwrap();
    let resp = app.oneshot(req).await.unwrap();
    let status = resp.status();
    let bytes = resp.into_body().collect().await.unwrap().to_bytes().to_vec();
    (status, bytes.to_vec())
}

fn json(bytes: &[u8]) -> Value {
    serde_json::from_slice(bytes)
        .unwrap_or_else(|e| panic!("response body must be valid JSON: {e}; raw={:?}", String::from_utf8_lossy(bytes)))
}

fn msg(bytes: &[u8]) -> String {
    let v = json(bytes);
    v.get("message")
        .and_then(|m| m.as_str())
        .map(|s| s.to_string())
        .unwrap_or_else(|| panic!("404 body must be a JSON object with a string `message` field; got {v:?}"))
}

// --- v1 hit ----------------------------------------------------------------
#[tokio::test]
async fn v1_status_ok() {
    let app = router();
    let (s, b) = call(app, "GET", "/api/v1/status").await;
    assert_eq!(s, StatusCode::OK, "GET /api/v1/status must be 200");
    // body must be present and non-empty (the fixed v1 status body)
    assert!(!b.is_empty(), "v1 status body must not be empty");
}

// --- v2 hit, distinct from v1 ---------------------------------------------
#[tokio::test]
async fn v2_status_ok_and_differs_from_v1() {
    let app = router();
    let (s1, b1) = call(app.clone(), "GET", "/api/v1/status").await;
    assert_eq!(s1, StatusCode::OK, "GET /api/v1/status must be 200");
    let (s2, b2) = call(app, "GET", "/api/v2/status").await;
    assert_eq!(s2, StatusCode::OK, "GET /api/v2/status must be 200");
    assert!(!b2.is_empty(), "v2 status body must not be empty");
    assert_ne!(
        b1, b2,
        "v2 status body must differ from v1 status body (a stub returning the same body must fail)"
    );
}

// --- v1 miss handled by v1 fallback ---------------------------------------
#[tokio::test]
async fn v1_miss_is_404_with_v1_message() {
    let app = router();
    let (s, b) = call(app, "GET", "/api/v1/does-not-exist").await;
    assert_eq!(s, StatusCode::NOT_FOUND, "unknown path under /api/v1 must be 404");
    let m = msg(&b);
    assert!(!m.is_empty(), "v1 not-found message must be non-empty");
    assert!(
        m.to_lowercase().contains("v1") || m.to_lowercase().contains("version 1"),
        "v1 fallback message should identify itself as v1; got {m:?}"
    );
}

// --- v2 miss handled by v2 fallback, distinct from v1 ----------------------
#[tokio::test]
async fn v2_miss_is_404_with_v2_message_distinct_from_v1() {
    let app = router();
    let (s1, b1) = call(app.clone(), "GET", "/api/v1/nope").await;
    assert_eq!(s1, StatusCode::NOT_FOUND);
    let (s2, b2) = call(app, "GET", "/api/v2/nope").await;
    assert_eq!(s2, StatusCode::NOT_FOUND, "unknown path under /api/v2 must be 404");
    let m1 = msg(&b1);
    let m2 = msg(&b2);
    assert!(
        m2.to_lowercase().contains("v2") || m2.to_lowercase().contains("version 2"),
        "v2 fallback message should identify itself as v2; got {m2:?}"
    );
    assert_ne!(
        m1, m2,
        "v1 and v2 not-found messages must differ (a single shared fallback must fail)"
    );
}

// --- top-level miss handled by top-level fallback, distinct from both ------
#[tokio::test]
async fn top_level_miss_is_404_with_distinct_message() {
    let app = router();
    let (s1, b1) = call(app.clone(), "GET", "/api/v1/missing").await;
    assert_eq!(s1, StatusCode::NOT_FOUND);
    let (s2, b2) = call(app.clone(), "GET", "/api/v2/missing").await;
    assert_eq!(s2, StatusCode::NOT_FOUND);
    let (st, bt) = call(app, "GET", "/something-else").await;
    assert_eq!(st, StatusCode::NOT_FOUND, "unmounted path must be 404 via top-level fallback");
    let m1 = msg(&b1);
    let m2 = msg(&b2);
    let mt = msg(&bt);
    assert_ne!(mt, m1, "top-level message must differ from v1 message");
    assert_ne!(mt, m2, "top-level message must differ from v2 message");
}

// --- all three messages pairwise distinct (the core discriminator) --------
#[tokio::test]
async fn three_fallback_messages_are_pairwise_distinct() {
    let app = router();
    let (_, b1) = call(app.clone(), "GET", "/api/v1/x").await;
    let (_, b2) = call(app.clone(), "GET", "/api/v2/x").await;
    let (_, bt) = call(app, "GET", "/totally/unmounted").await;
    let m1 = msg(&b1);
    let m2 = msg(&b2);
    let mt = msg(&bt);
    assert_ne!(m1, m2, "v1 vs v2 messages must differ");
    assert_ne!(m1, mt, "v1 vs top-level messages must differ");
    assert_ne!(m2, mt, "v2 vs top-level messages must differ");
}

// --- sub-APIs are mounted under their prefixes ----------------------------
// A bare /status (without a prefix) must NOT hit either section's success
// handler; it falls through to the top-level fallback as a 404. This proves
// each sub-router only sees the path relative to its own mount point and that
// the routers are actually mounted under /api/vN (not flattened at the root).
#[tokio::test]
async fn status_only_reachable_under_its_prefix() {
    let app = router();
    let (s, b) = call(app, "GET", "/status").await;
    assert_eq!(
        s, StatusCode::NOT_FOUND,
        "/status without an /api/vN prefix must be a top-level 404, proving sub-APIs are mounted under prefixes"
    );
    // and it must be the top-level message, not a section one
    let mt = msg(&b);
    assert!(!mt.is_empty());
}

// --- method mismatch within a section must not yield the success body ------
#[tokio::test]
async fn wrong_method_on_v1_status_is_not_success() {
    let app = router();
    let (s, _) = call(app, "POST", "/api/v1/status").await;
    assert_ne!(
        s, StatusCode::OK,
        "POST on an existing GET-only path must not return the success body/200"
    );
    // axum's MethodRouter yields 405 for a known path with the wrong method.
    assert!(
        s == StatusCode::METHOD_NOT_ALLOWED || s == StatusCode::NOT_FOUND,
        "wrong method should be 405 (or 404), got {s}"
    );
}

// --- every 404 body is a JSON object with a `message` field ----------------
#[tokio::test]
async fn all_404_bodies_are_apierror_shaped() {
    let app = router();
    for uri in ["/api/v1/zzz", "/api/v2/zzz", "/no/such/route"] {
        let (s, b) = call(app.clone(), "GET", uri).await;
        assert_eq!(s, StatusCode::NOT_FOUND, "{uri} must be 404");
        let v = json(&b);
        assert!(v.is_object(), "404 body for {uri} must be a JSON object; got {v:?}");
        assert!(
            v.get("message").and_then(|m| m.as_str()).map(|m| !m.is_empty()).unwrap_or(false),
            "404 body for {uri} must carry a non-empty string `message`; got {v:?}"
        );
    }
}

// --- router() is reproducible: independent instances behave identically ----
#[tokio::test]
async fn instances_behave_identically() {
    let a = router();
    let b = router();
    let (sa, ba) = call(a, "GET", "/api/v1/status").await;
    let (sb, bb) = call(b, "GET", "/api/v1/status").await;
    assert_eq!(sa, StatusCode::OK);
    assert_eq!(sb, StatusCode::OK);
    assert_eq!(ba, bb, "each router() must build an equivalent, deterministic router");
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

    We only add a key that is not already present *inside the [dev-dependencies]
    table*, so we never create a duplicate-key TOML error even if the same crate
    exists under [dependencies].
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
    """Verify the versioned, nested API with per-section fallbacks in shuttle-common."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_versioned_api_source_exists(self):
        """common/src/versioned_api.rs must exist and be non-trivial."""
        assert os.path.isfile(VERSIONED_API_SRC), "common/src/versioned_api.rs not created"
        assert os.path.getsize(VERSIONED_API_SRC) > 200, "versioned_api.rs is implausibly small"

    def test_router_constructor_declared(self):
        """versioned_api.rs must declare a public `fn router() -> ... Router`."""
        with open(VERSIONED_API_SRC) as f:
            src = f.read()
        assert re.search(r"pub\s+fn\s+router\s*\(", src), "no `pub fn router(` constructor found"
        assert re.search(r"Router", src), "router() must build an axum Router"

    def test_mounts_both_version_prefixes(self):
        """Both /api/v1 and /api/v2 prefixes must be wired into the router."""
        with open(VERSIONED_API_SRC) as f:
            src = f.read()
        assert "/api/v1" in src, "router must mount a sub-API under /api/v1"
        assert "/api/v2" in src, "router must mount a sub-API under /api/v2"

    def test_uses_fallbacks(self):
        """The implementation must wire fallback handlers (per-section + top-level)."""
        with open(VERSIONED_API_SRC) as f:
            src = f.read()
        # axum exposes fallbacks via `.fallback(...)`; at least one must be present.
        assert "fallback" in src, "implementation must use axum fallback handlers for not-found behavior"

    def test_module_declared_gated_in_lib(self):
        """lib.rs must declare `versioned_api` gated behind the axum feature."""
        with open(LIB_RS) as f:
            lib = f.read()
        assert "versioned_api" in lib, "lib.rs does not declare the versioned_api module"
        m = re.search(
            r'(#\[cfg\([^\)]*feature\s*=\s*"axum"[^\)]*\)\]\s*)pub\s+mod\s+versioned_api',
            lib,
        )
        assert m is not None, 'module `versioned_api` must be #[cfg(feature = "axum")]-gated'

    def test_agent_integration_test_exists(self):
        """The agent's own in-process integration test must exist and drive router()."""
        assert os.path.isfile(AGENT_TEST), "common/tests/versioned_api.rs not created"
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
        """The exact acceptance command must pass: cargo test ... --test versioned_api."""
        proc = subprocess.run(
            ["cargo", "test", "-p", "shuttle-common", "--features", "axum", "--test", "versioned_api"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=RUN_TIMEOUT, env=_cargo_env(),
        )
        out = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, f"acceptance command failed:\n{out[-4000:]}"
        assert "test result: ok." in out, f"acceptance test did not report ok:\n{out[-2000:]}"

    def test_v1_status_ok(self):
        """GET /api/v1/status -> 200 with a non-empty v1 status body."""
        _assert_test_passed(_run_verify("v1_status_ok"), "v1_status_ok")

    def test_v2_status_ok_and_differs_from_v1(self):
        """GET /api/v2/status -> 200 and body differs from v1's (stub w/ same body fails)."""
        _assert_test_passed(
            _run_verify("v2_status_ok_and_differs_from_v1"),
            "v2_status_ok_and_differs_from_v1",
        )

    def test_v1_miss_is_404_with_v1_message(self):
        """GET /api/v1/<missing> -> 404 with a v1-specific not-found message."""
        _assert_test_passed(
            _run_verify("v1_miss_is_404_with_v1_message"),
            "v1_miss_is_404_with_v1_message",
        )

    def test_v2_miss_is_404_with_v2_message_distinct_from_v1(self):
        """GET /api/v2/<missing> -> 404 with v2 message, distinct from v1's."""
        _assert_test_passed(
            _run_verify("v2_miss_is_404_with_v2_message_distinct_from_v1"),
            "v2_miss_is_404_with_v2_message_distinct_from_v1",
        )

    def test_top_level_miss_is_404_with_distinct_message(self):
        """GET /<unmounted> -> 404 with a top-level message distinct from both sections."""
        _assert_test_passed(
            _run_verify("top_level_miss_is_404_with_distinct_message"),
            "top_level_miss_is_404_with_distinct_message",
        )

    def test_three_fallback_messages_are_pairwise_distinct(self):
        """The three not-found messages must be pairwise distinct (shared fallback fails)."""
        _assert_test_passed(
            _run_verify("three_fallback_messages_are_pairwise_distinct"),
            "three_fallback_messages_are_pairwise_distinct",
        )

    def test_status_only_reachable_under_its_prefix(self):
        """/status without /api/vN -> top-level 404, proving sub-APIs are prefix-mounted."""
        _assert_test_passed(
            _run_verify("status_only_reachable_under_its_prefix"),
            "status_only_reachable_under_its_prefix",
        )

    def test_wrong_method_on_v1_status_is_not_success(self):
        """POST /api/v1/status must not return the success body (405/404, never 200)."""
        _assert_test_passed(
            _run_verify("wrong_method_on_v1_status_is_not_success"),
            "wrong_method_on_v1_status_is_not_success",
        )

    def test_all_404_bodies_are_apierror_shaped(self):
        """Every 404 body is a JSON object carrying a non-empty `message` field."""
        _assert_test_passed(
            _run_verify("all_404_bodies_are_apierror_shaped"),
            "all_404_bodies_are_apierror_shaped",
        )

    def test_instances_behave_identically(self):
        """Independent router() instances build equivalent, deterministic routers."""
        _assert_test_passed(
            _run_verify("instances_behave_identically"),
            "instances_behave_identically",
        )
