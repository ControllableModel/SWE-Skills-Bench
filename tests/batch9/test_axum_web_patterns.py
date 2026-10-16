"""
Test for 'axum-web-patterns' skill (variant ext9) — shared-state metrics
endpoint in shuttle-common.

The task asks the agent to add `common/src/metrics_api.rs` exposing
`pub fn router() -> axum::Router`, gated behind the `axum` feature, backed by
concurrency-safe shared application state that keeps independent per-route hit
counters. Routes:

    GET /hit/a    -> increments counter A, responds 200 OK
    GET /hit/b    -> increments counter B, responds 200 OK
    GET /metrics  -> reports {"a":<N>,"b":<M>} as JSON, does NOT increment;
                     response is hand-built with status 200, header
                     content-type: application/json, and a custom header
                     x-metrics-source: <documented constant>.

Verification strategy
---------------------
We do NOT trust the agent's own `common/tests/metrics_api.rs`. For the L2
behavioral checks this harness injects an *independent* Rust integration test
(`tests/_metrics_api_verify.rs`) that imports the real `router()`, drives it
fully in-process with `tower::ServiceExt::oneshot` (no TCP socket), and asserts
every acceptance scenario:

  * fresh router reports {"a":0,"b":0} with the two required headers;
  * N hits to /hit/a and M to /hit/b yield exactly a==N, b==M;
  * /metrics never mutates the counters (repeated reads are stable);
  * a second router() instance is independent and starts at {"a":0,"b":0};
  * the custom x-metrics-source header is present and non-empty.

A naive implementation that hardcodes counts, increments on /metrics, shares a
process-global counter across instances, or omits the custom header MUST fail
at least one of these named Rust tests. We add the required dev-dependencies
ourselves so the checks do not depend on what the agent put in Cargo.toml.

Native command of record:
    cargo test -p shuttle-common --features axum --test metrics_api
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/shuttle"
COMMON_DIR = os.path.join(REPO_DIR, "common")
METRICS_API_SRC = os.path.join(COMMON_DIR, "src", "metrics_api.rs")
LIB_RS = os.path.join(COMMON_DIR, "src", "lib.rs")
AGENT_TEST = os.path.join(COMMON_DIR, "tests", "metrics_api.rs")
CARGO_TOML = os.path.join(COMMON_DIR, "Cargo.toml")

VERIFY_TEST_NAME = "_metrics_api_verify"
VERIFY_TEST_PATH = os.path.join(COMMON_DIR, "tests", VERIFY_TEST_NAME + ".rs")

BUILD_TIMEOUT = 900
RUN_TIMEOUT = 900


# ---------------------------------------------------------------------------
# Independent in-process Rust integration test injected into the repo.
# It only depends on the public surface: `shuttle_common::metrics_api::router()`.
# ---------------------------------------------------------------------------
VERIFY_RS = r'''
// AUTO-GENERATED independent verification test for the axum-web-patterns task
// (variant ext9). Drives `router()` fully in-process (no socket) via tower
// oneshot, asserting concrete status codes, headers and JSON counter values.
#![cfg(feature = "axum")]

use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt; // for `oneshot`

use shuttle_common::metrics_api::router;

struct Resp {
    status: StatusCode,
    content_type: Option<String>,
    metrics_source: Option<String>,
    body: Vec<u8>,
}

async fn get(app: axum::Router, uri: &str) -> Resp {
    let req = Request::builder()
        .method("GET")
        .uri(uri)
        .body(Body::empty())
        .unwrap();
    let resp = app.oneshot(req).await.unwrap();
    let status = resp.status();
    let headers = resp.headers().clone();
    let content_type = headers
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string());
    let metrics_source = headers
        .get("x-metrics-source")
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string());
    let body = resp
        .into_body()
        .collect()
        .await
        .unwrap()
        .to_bytes()
        .to_vec();
    Resp {
        status,
        content_type,
        metrics_source,
        body,
    }
}

fn json(bytes: &[u8]) -> Value {
    serde_json::from_slice(bytes).expect("/metrics body must be valid JSON")
}

// Read counters via /metrics and return (a, b). Asserts the response shape too.
async fn read_metrics(app: axum::Router) -> (i64, i64) {
    let r = get(app, "/metrics").await;
    assert_eq!(r.status, StatusCode::OK, "/metrics must respond 200 OK");
    let v = json(&r.body);
    let a = v["a"].as_i64().expect("/metrics body must have integer field `a`");
    let b = v["b"].as_i64().expect("/metrics body must have integer field `b`");
    (a, b)
}

#[tokio::test]
async fn fresh_router_reports_zero_with_headers() {
    let app = router();
    let r = get(app.clone(), "/metrics").await;
    assert_eq!(r.status, StatusCode::OK, "fresh /metrics must be 200 OK");

    // Custom hand-built response headers.
    let ct = r.content_type.expect("/metrics must set a content-type header");
    assert!(
        ct.starts_with("application/json"),
        "content-type must be application/json, got `{ct}`"
    );
    let src = r
        .metrics_source
        .expect("/metrics must set the custom x-metrics-source header");
    assert!(
        !src.is_empty(),
        "x-metrics-source must carry a non-empty documented constant"
    );

    // Initial counters are exactly zero.
    let v = json(&r.body);
    assert_eq!(v["a"].as_i64(), Some(0), "initial counter a must be 0");
    assert_eq!(v["b"].as_i64(), Some(0), "initial counter b must be 0");
}

#[tokio::test]
async fn hits_are_counted_exactly() {
    let app = router();
    // 3 hits to A, 5 hits to B, interleaved.
    let plan = ["a", "b", "a", "b", "b", "a", "b", "b"];
    let mut expect_a = 0i64;
    let mut expect_b = 0i64;
    for route in plan {
        let r = get(app.clone(), &format!("/hit/{route}")).await;
        assert_eq!(r.status, StatusCode::OK, "/hit/{route} must respond 200 OK");
        if route == "a" {
            expect_a += 1;
        } else {
            expect_b += 1;
        }
    }
    assert_eq!(expect_a, 3);
    assert_eq!(expect_b, 5);

    let (a, b) = read_metrics(app.clone()).await;
    assert_eq!(a, expect_a, "counter a must equal number of /hit/a calls");
    assert_eq!(b, expect_b, "counter b must equal number of /hit/b calls");
}

#[tokio::test]
async fn counters_are_independent_per_route() {
    let app = router();
    // Only hit A; B must stay at zero (a naive single shared counter fails).
    for _ in 0..4 {
        let r = get(app.clone(), "/hit/a").await;
        assert_eq!(r.status, StatusCode::OK);
    }
    let (a, b) = read_metrics(app.clone()).await;
    assert_eq!(a, 4, "only /hit/a was called four times");
    assert_eq!(b, 0, "/hit/b was never called; counter b must remain 0");
}

#[tokio::test]
async fn metrics_does_not_mutate_counters() {
    let app = router();
    get(app.clone(), "/hit/a").await;
    get(app.clone(), "/hit/b").await;
    get(app.clone(), "/hit/b").await;

    // Read /metrics several times; the numbers must not move.
    let first = read_metrics(app.clone()).await;
    assert_eq!(first, (1, 2), "after 1xA + 2xB the counters must be (1,2)");
    for _ in 0..5 {
        let again = read_metrics(app.clone()).await;
        assert_eq!(
            again, first,
            "repeated GET /metrics must not change the counters"
        );
    }
}

#[tokio::test]
async fn instances_are_independent() {
    let a = router();
    let b = router();

    for _ in 0..7 {
        get(a.clone(), "/hit/a").await;
    }
    // Instance A advanced; instance B must still be pristine.
    let (ba, bb) = read_metrics(b.clone()).await;
    assert_eq!(
        (ba, bb),
        (0, 0),
        "a separate router() instance must not share counters (no process-global state)"
    );

    // And A really did count.
    let (aa, ab) = read_metrics(a.clone()).await;
    assert_eq!((aa, ab), (7, 0));
}

#[tokio::test]
async fn metrics_header_constant_is_stable() {
    // The documented x-metrics-source constant must be identical across reads
    // and across instances (it is a fixed documented constant, not random).
    let app1 = router();
    let app2 = router();
    let r1 = get(app1, "/metrics").await;
    let r2 = get(app2, "/metrics").await;
    let s1 = r1.metrics_source.expect("x-metrics-source must be set");
    let s2 = r2.metrics_source.expect("x-metrics-source must be set");
    assert_eq!(s1, s2, "x-metrics-source must be a stable documented constant");
    assert!(!s1.is_empty());
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

    We pin versions already present in the workspace so resolution works
    offline. We only add a key not already present *inside the
    [dev-dependencies] table*, so we never create a duplicate-key TOML error
    even if the same crate exists under [dependencies].
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
    """Verify the shared-state metrics HTTP API added to shuttle-common."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_metrics_api_source_exists(self):
        """common/src/metrics_api.rs must exist and be non-trivial."""
        assert os.path.isfile(METRICS_API_SRC), "common/src/metrics_api.rs not created"
        assert os.path.getsize(METRICS_API_SRC) > 200, "metrics_api.rs is implausibly small"

    def test_router_constructor_declared(self):
        """metrics_api.rs must declare a public `fn router() -> ... Router`."""
        with open(METRICS_API_SRC) as f:
            src = f.read()
        assert re.search(r"pub\s+fn\s+router\s*\(", src), "no `pub fn router(` constructor found"
        assert re.search(r"Router", src), "router() must build an axum Router"

    def test_routes_and_custom_header_referenced(self):
        """Source must wire the three routes and the custom metrics header."""
        with open(METRICS_API_SRC) as f:
            src = f.read()
        assert "/hit/a" in src, "/hit/a route not wired"
        assert "/hit/b" in src, "/hit/b route not wired"
        assert "/metrics" in src, "/metrics route not wired"
        assert "x-metrics-source" in src.lower(), (
            "the custom x-metrics-source header must be set by the /metrics handler"
        )

    def test_uses_shared_state_not_global(self):
        """Counters must live in router-attached state, not a process-global.

        We require an axum state mechanism (with_state/State) and a
        concurrency-safe container, and forbid the obvious global escape hatches
        (static AtomicUsize / lazy_static / once_cell global counters).
        """
        with open(METRICS_API_SRC) as f:
            src = f.read()
        assert "with_state" in src or "State" in src, (
            "counters must be attached via the router's state mechanism"
        )
        # A static mutable/atomic global counter is the naive shortcut the doc forbids.
        assert not re.search(r"static\s+\w+\s*:\s*Atomic", src), (
            "counters must not be a process-global `static ... : Atomic...`"
        )
        assert "lazy_static" not in src, "counters must not use a lazy_static global"

    def test_module_declared_gated_in_lib(self):
        """lib.rs must declare `metrics_api` gated behind the axum feature."""
        with open(LIB_RS) as f:
            lib = f.read()
        assert "metrics_api" in lib, "lib.rs does not declare the metrics_api module"
        m = re.search(
            r'(#\[cfg\([^\)]*feature\s*=\s*"axum"[^\)]*\)\]\s*)pub\s+mod\s+metrics_api',
            lib,
        )
        assert m is not None, 'module `metrics_api` must be #[cfg(feature = "axum")]-gated'

    def test_agent_integration_test_exists(self):
        """The agent's own in-process integration test must exist."""
        assert os.path.isfile(AGENT_TEST), "common/tests/metrics_api.rs not created"
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
        """The exact acceptance command must pass: cargo test ... --test metrics_api."""
        proc = subprocess.run(
            ["cargo", "test", "-p", "shuttle-common", "--features", "axum", "--test", "metrics_api"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=RUN_TIMEOUT, env=_cargo_env(),
        )
        out = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, f"acceptance command failed:\n{out[-4000:]}"
        assert "test result: ok." in out, f"acceptance test did not report ok:\n{out[-2000:]}"

    def test_fresh_router_reports_zero_with_headers(self):
        """Fresh /metrics -> 200, {"a":0,"b":0}, application/json + x-metrics-source."""
        _assert_test_passed(
            _run_verify("fresh_router_reports_zero_with_headers"),
            "fresh_router_reports_zero_with_headers",
        )

    def test_hits_are_counted_exactly(self):
        """After N x /hit/a and M x /hit/b, /metrics reports exactly a==N, b==M."""
        _assert_test_passed(_run_verify("hits_are_counted_exactly"), "hits_are_counted_exactly")

    def test_counters_are_independent_per_route(self):
        """Hitting only /hit/a leaves counter b at 0 (separate counters)."""
        _assert_test_passed(
            _run_verify("counters_are_independent_per_route"),
            "counters_are_independent_per_route",
        )

    def test_metrics_does_not_mutate_counters(self):
        """Repeated GET /metrics must not change the counters."""
        _assert_test_passed(
            _run_verify("metrics_does_not_mutate_counters"),
            "metrics_does_not_mutate_counters",
        )

    def test_instances_are_independent(self):
        """Each router() owns an independent counter state; no shared global."""
        _assert_test_passed(_run_verify("instances_are_independent"), "instances_are_independent")

    def test_metrics_header_constant_is_stable(self):
        """x-metrics-source is a fixed documented constant, stable across instances."""
        _assert_test_passed(
            _run_verify("metrics_header_constant_is_stable"),
            "metrics_header_constant_is_stable",
        )
