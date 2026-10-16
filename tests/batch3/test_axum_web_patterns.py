"""
Test for 'axum-web-patterns' skill (variant ext3) — paginated, filterable logs
query endpoint in shuttle-common.

The task asks the agent to add `common/src/logs_api.rs` exposing
`pub fn router() -> axum::Router`, gated behind the `axum` feature (and using the
`models` types `LogItem` / `LogsResponse`). The router serves a single route:

    GET /logs

over a FIXED in-code seed of exactly 5 `LogItem`s (>= 2 "build", >= 2 "runtime",
in a stable documented order). Query parameters drive the result entirely:

    source  — optional exact filter on LogItem.source
    offset  — number of eligible lines to skip (default 0)
    limit   — max lines to return after offset (default: all remaining)

Response body is `LogsResponse` = `{"logs": [ <LogItem>, ... ]}` preserving seed
order of the filtered slice. A non-numeric offset/limit yields a 400 with the
crate's `ApiError`-shaped JSON body (object with a `message` field). limit=0 ->
empty; large offset -> empty; large limit -> all remaining.

Verification strategy
---------------------
We do NOT trust the agent's own `common/tests/logs_api.rs`. For the L2 behavioral
checks this harness injects an *independent* Rust integration test
(`tests/_logs_api_verify.rs`) that imports the real `router()`, drives it fully
in-process with `tower::ServiceExt::oneshot` (no TCP), and asserts every
acceptance scenario with concrete counts / order / status codes. We add the
required dev-dependencies ourselves (pinned to versions in the workspace
Cargo.lock) so the checks do not depend on what the agent put in Cargo.toml. Each
L2 pytest method runs one named Rust test and asserts it passes, mapping 1:1 to a
requirement. A naive impl that ignores the query string or returns a fixed slice
fails the filter/pagination/error cases.

Native command of record:
    cargo test -p shuttle-common --features axum,models --test logs_api
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/shuttle"
COMMON_DIR = os.path.join(REPO_DIR, "common")
LOGS_API_SRC = os.path.join(COMMON_DIR, "src", "logs_api.rs")
LIB_RS = os.path.join(COMMON_DIR, "src", "lib.rs")
AGENT_TEST = os.path.join(COMMON_DIR, "tests", "logs_api.rs")
CARGO_TOML = os.path.join(COMMON_DIR, "Cargo.toml")

VERIFY_TEST_NAME = "_logs_api_verify"
VERIFY_TEST_PATH = os.path.join(COMMON_DIR, "tests", VERIFY_TEST_NAME + ".rs")

# The module needs both `axum` (gate) and `models` (LogItem/LogsResponse).
FEATURES = "axum,models"

BUILD_TIMEOUT = 900
RUN_TIMEOUT = 900


# ---------------------------------------------------------------------------
# Independent in-process Rust integration test injected into the repo.
# It only depends on the public surface: `shuttle_common::logs_api::router()`
# and the deterministic 5-line seed described in the requirement doc.
# ---------------------------------------------------------------------------
VERIFY_RS = r'''
// AUTO-GENERATED independent verification test for the axum-web-patterns task
// (ext3 variant: paginated/filterable /logs endpoint).
// Drives `router()` fully in-process (no socket) via tower oneshot.
#![cfg(all(feature = "axum", feature = "models"))]

use axum::body::Body;
use axum::http::{Request, StatusCode};
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt; // for `oneshot`

use shuttle_common::logs_api::router;

async fn get(app: axum::Router, uri: &str) -> (StatusCode, Vec<u8>) {
    let req = Request::builder()
        .method("GET")
        .uri(uri)
        .body(Body::empty())
        .unwrap();
    let resp = app.oneshot(req).await.unwrap();
    let status = resp.status();
    let bytes = resp.into_body().collect().await.unwrap().to_bytes().to_vec();
    (status, bytes)
}

fn json(bytes: &[u8]) -> Value {
    serde_json::from_slice(bytes).expect("response body must be valid JSON")
}

/// Pull the `logs` array out of a LogsResponse body, asserting it is present.
fn logs(v: &Value) -> Vec<Value> {
    v.get("logs")
        .and_then(|l| l.as_array())
        .cloned()
        .expect("body must be a LogsResponse object with a `logs` array")
}

fn sources(arr: &[Value]) -> Vec<String> {
    arr.iter()
        .map(|e| {
            e.get("source")
                .and_then(|s| s.as_str())
                .expect("each log entry must have a string `source`")
                .to_string()
        })
        .collect()
}

fn lines(arr: &[Value]) -> Vec<String> {
    arr.iter()
        .map(|e| {
            e.get("line")
                .and_then(|s| s.as_str())
                .expect("each log entry must have a string `line`")
                .to_string()
        })
        .collect()
}

// ---- Seed shape -----------------------------------------------------------

#[tokio::test]
async fn no_params_returns_all_five_in_order() {
    let app = router();
    let (s, b) = get(app, "/logs").await;
    assert_eq!(s, StatusCode::OK, "GET /logs with no params must be 200");
    let v = json(&b);
    let arr = logs(&v);
    assert_eq!(arr.len(), 5, "seed must contain exactly 5 log lines");
    // each entry must carry the LogItem fields
    for e in &arr {
        assert!(e.get("source").is_some(), "entry must have `source`");
        assert!(e.get("line").is_some(), "entry must have `line`");
        assert!(e.get("timestamp").is_some(), "entry must have `timestamp`");
    }
    // sources are only build/runtime, with at least two of each
    let src = sources(&arr);
    for s in &src {
        assert!(s == "build" || s == "runtime", "source must be build|runtime, got {s}");
    }
    let n_build = src.iter().filter(|s| *s == "build").count();
    let n_runtime = src.iter().filter(|s| *s == "runtime").count();
    assert!(n_build >= 2, "seed must have >= 2 build lines, got {n_build}");
    assert!(n_runtime >= 2, "seed must have >= 2 runtime lines, got {n_runtime}");
}

#[tokio::test]
async fn seed_is_deterministic_across_calls() {
    // Two independent router()s must serve byte-identical /logs payloads:
    // no clock, no randomness.
    let (s1, b1) = get(router(), "/logs").await;
    let (s2, b2) = get(router(), "/logs").await;
    assert_eq!(s1, StatusCode::OK);
    assert_eq!(s2, StatusCode::OK);
    assert_eq!(
        json(&b1),
        json(&b2),
        "seed dataset must be identical on every call (deterministic, no clock/rng)"
    );
    // And stable within a single router across repeated requests.
    let app = router();
    let (_, ba) = get(app.clone(), "/logs").await;
    let (_, bb) = get(app, "/logs").await;
    assert_eq!(json(&ba), json(&bb), "repeated requests must return the same set");
}

// ---- Filtering ------------------------------------------------------------

#[tokio::test]
async fn filter_by_source_build() {
    let app = router();
    // full set to know the expected build subset/order
    let (_, full) = get(app.clone(), "/logs").await;
    let full_arr = logs(&json(&full));
    let expected: Vec<String> = full_arr
        .iter()
        .filter(|e| e["source"].as_str() == Some("build"))
        .map(|e| e["line"].as_str().unwrap().to_string())
        .collect();
    assert!(expected.len() >= 2, "precondition: >= 2 build lines");

    let (s, b) = get(app, "/logs?source=build").await;
    assert_eq!(s, StatusCode::OK);
    let arr = logs(&json(&b));
    assert_eq!(
        sources(&arr),
        vec!["build"; arr.len()],
        "source=build must return only build lines"
    );
    assert_eq!(lines(&arr), expected, "build subset must preserve seed order");
    assert_eq!(arr.len(), expected.len());
}

#[tokio::test]
async fn filter_by_source_runtime() {
    let app = router();
    let (_, full) = get(app.clone(), "/logs").await;
    let full_arr = logs(&json(&full));
    let expected: Vec<String> = full_arr
        .iter()
        .filter(|e| e["source"].as_str() == Some("runtime"))
        .map(|e| e["line"].as_str().unwrap().to_string())
        .collect();
    assert!(expected.len() >= 2, "precondition: >= 2 runtime lines");

    let (s, b) = get(app, "/logs?source=runtime").await;
    assert_eq!(s, StatusCode::OK);
    let arr = logs(&json(&b));
    assert_eq!(
        sources(&arr),
        vec!["runtime"; arr.len()],
        "source=runtime must return only runtime lines"
    );
    assert_eq!(lines(&arr), expected, "runtime subset must preserve seed order");
}

#[tokio::test]
async fn unknown_source_returns_empty_200() {
    let app = router();
    let (s, b) = get(app, "/logs?source=nope").await;
    assert_eq!(s, StatusCode::OK, "unknown source is not an error");
    let arr = logs(&json(&b));
    assert!(arr.is_empty(), "unknown source must yield {{\"logs\":[]}}");
}

// ---- Pagination -----------------------------------------------------------

#[tokio::test]
async fn offset_and_limit_slice_correctly() {
    let app = router();
    let (_, full) = get(app.clone(), "/logs").await;
    let all = lines(&logs(&json(&full)));
    assert_eq!(all.len(), 5);

    // offset=1&limit=2 -> exactly the 2nd and 3rd lines.
    let (s, b) = get(app.clone(), "/logs?offset=1&limit=2").await;
    assert_eq!(s, StatusCode::OK);
    let got = lines(&logs(&json(&b)));
    assert_eq!(got, vec![all[1].clone(), all[2].clone()], "offset/limit must select the right slice");

    // limit larger than remaining -> all remaining.
    let (s, b) = get(app.clone(), "/logs?offset=3&limit=100").await;
    assert_eq!(s, StatusCode::OK);
    let got = lines(&logs(&json(&b)));
    assert_eq!(got, vec![all[3].clone(), all[4].clone()], "limit > remaining returns all remaining");

    // offset only -> skip from front, keep the rest.
    let (s, b) = get(app, "/logs?offset=2").await;
    assert_eq!(s, StatusCode::OK);
    let got = lines(&logs(&json(&b)));
    assert_eq!(got, vec![all[2].clone(), all[3].clone(), all[4].clone()]);
}

#[tokio::test]
async fn limit_zero_and_large_offset_are_empty() {
    let app = router();

    // limit=0 -> empty, distinct from omitting limit.
    let (s, b) = get(app.clone(), "/logs?limit=0").await;
    assert_eq!(s, StatusCode::OK);
    assert!(logs(&json(&b)).is_empty(), "limit=0 must return zero lines");

    // sanity: omitting limit returns the full 5.
    let (_, full) = get(app.clone(), "/logs").await;
    assert_eq!(logs(&json(&full)).len(), 5, "omitting limit returns all (distinct from limit=0)");

    // offset at/beyond eligible count -> empty.
    let (s, b) = get(app.clone(), "/logs?offset=5").await;
    assert_eq!(s, StatusCode::OK);
    assert!(logs(&json(&b)).is_empty(), "offset == count must be empty");

    let (s, b) = get(app, "/logs?offset=999").await;
    assert_eq!(s, StatusCode::OK);
    assert!(logs(&json(&b)).is_empty(), "offset beyond count must be empty");
}

#[tokio::test]
async fn filter_then_paginate_compose() {
    let app = router();
    // Establish the runtime subset order.
    let (_, rt) = get(app.clone(), "/logs?source=runtime").await;
    let runtime_lines = lines(&logs(&json(&rt)));
    assert!(runtime_lines.len() >= 2);

    // source=runtime&offset=1 -> drop the first runtime line, keep the rest.
    let (s, b) = get(app, "/logs?source=runtime&offset=1").await;
    assert_eq!(s, StatusCode::OK);
    let got = lines(&logs(&json(&b)));
    let expected: Vec<String> = runtime_lines[1..].to_vec();
    assert_eq!(got, expected, "filter then offset must compose over the filtered set");
    // And every returned line is still a runtime line.
    let (_, b2) = get(router(), "/logs?source=runtime&offset=1").await;
    assert_eq!(
        sources(&logs(&json(&b2))),
        vec!["runtime"; expected.len()],
        "composed result must remain source-filtered"
    );
}

// ---- Error handling -------------------------------------------------------

#[tokio::test]
async fn non_numeric_offset_is_400_with_message() {
    let app = router();
    let (s, b) = get(app, "/logs?offset=abc").await;
    assert_eq!(s, StatusCode::BAD_REQUEST, "non-numeric offset must be 400");
    let v = json(&b);
    let msg = v.get("message").and_then(|m| m.as_str());
    assert!(
        msg.map(|m| !m.is_empty()).unwrap_or(false),
        "400 body must carry a non-empty `message` (ApiError shape); got {v:?}"
    );
    assert!(v.get("logs").is_none(), "error response must not carry a logs array");
}

#[tokio::test]
async fn non_numeric_limit_is_400_with_message() {
    let app = router();
    let (s, b) = get(app, "/logs?limit=xyz").await;
    assert_eq!(s, StatusCode::BAD_REQUEST, "non-numeric limit must be 400");
    let v = json(&b);
    let msg = v.get("message").and_then(|m| m.as_str());
    assert!(
        msg.map(|m| !m.is_empty()).unwrap_or(false),
        "400 body must carry a non-empty `message` (ApiError shape); got {v:?}"
    );
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
    assert "test result: ok." in out, f"cargo did not report ok for `{test_name}`:\n{out[-2000:]}"
    assert "0 passed" not in out, f"the named test `{test_name}` did not actually run:\n{out[-2000:]}"


class TestAxumWebPatterns:
    """Verify the paginated, filterable /logs HTTP API added to shuttle-common."""

    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------
    # L1: deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------

    def test_logs_api_source_exists(self):
        """common/src/logs_api.rs must exist and be non-trivial."""
        assert os.path.isfile(LOGS_API_SRC), "common/src/logs_api.rs not created"
        assert os.path.getsize(LOGS_API_SRC) > 200, "logs_api.rs is implausibly small"

    def test_router_constructor_declared(self):
        """logs_api.rs must declare a public `fn router() -> ... Router`."""
        with open(LOGS_API_SRC) as f:
            src = f.read()
        assert re.search(r"pub\s+fn\s+router\s*\(", src), "no `pub fn router(` constructor found"
        assert re.search(r"Router", src), "router() must build an axum Router"

    def test_uses_logs_models(self):
        """Handler must use the crate's LogItem / LogsResponse model types."""
        with open(LOGS_API_SRC) as f:
            src = f.read()
        assert "LogItem" in src, "implementation must reference LogItem"
        assert "LogsResponse" in src, "implementation must reference LogsResponse"

    def test_serves_logs_route(self):
        """The router must register a `/logs` route."""
        with open(LOGS_API_SRC) as f:
            src = f.read()
        assert "/logs" in src, "router must serve the /logs path"

    def test_module_declared_gated_in_lib(self):
        """lib.rs must declare `logs_api` gated behind the axum feature."""
        with open(LIB_RS) as f:
            lib = f.read()
        assert "logs_api" in lib, "lib.rs does not declare the logs_api module"
        m = re.search(
            r'(#\[cfg\([^\)]*feature\s*=\s*"axum"[^\)]*\)\]\s*)pub\s+mod\s+logs_api',
            lib,
        )
        assert m is not None, 'module `logs_api` must be feature-gated on "axum"'

    def test_agent_integration_test_exists(self):
        """The agent's own in-process integration test must exist and drive router()."""
        assert os.path.isfile(AGENT_TEST), "common/tests/logs_api.rs not created"
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
        """The exact acceptance command must pass: cargo test ... --test logs_api."""
        proc = subprocess.run(
            ["cargo", "test", "-p", "shuttle-common", "--features", FEATURES, "--test", "logs_api"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=RUN_TIMEOUT, env=_cargo_env(),
        )
        out = proc.stdout + "\n" + proc.stderr
        assert proc.returncode == 0, f"acceptance command failed:\n{out[-4000:]}"
        assert "test result: ok." in out, f"acceptance test did not report ok:\n{out[-2000:]}"

    def test_no_params_returns_all_five_in_order(self):
        """GET /logs (no params) -> 200 with exactly 5 build/runtime seed lines."""
        _assert_test_passed(
            _run_verify("no_params_returns_all_five_in_order"),
            "no_params_returns_all_five_in_order",
        )

    def test_seed_is_deterministic_across_calls(self):
        """Two router()s serve byte-identical /logs (no clock/randomness)."""
        _assert_test_passed(
            _run_verify("seed_is_deterministic_across_calls"),
            "seed_is_deterministic_across_calls",
        )

    def test_filter_by_source_build(self):
        """source=build -> only build lines, in seed order, correct count."""
        _assert_test_passed(_run_verify("filter_by_source_build"), "filter_by_source_build")

    def test_filter_by_source_runtime(self):
        """source=runtime -> only runtime lines, in seed order, correct count."""
        _assert_test_passed(_run_verify("filter_by_source_runtime"), "filter_by_source_runtime")

    def test_unknown_source_returns_empty_200(self):
        """source=<unknown> -> 200 with {"logs":[]} (not an error)."""
        _assert_test_passed(
            _run_verify("unknown_source_returns_empty_200"),
            "unknown_source_returns_empty_200",
        )

    def test_offset_and_limit_slice_correctly(self):
        """offset/limit select the right slice; limit>remaining returns the rest."""
        _assert_test_passed(
            _run_verify("offset_and_limit_slice_correctly"),
            "offset_and_limit_slice_correctly",
        )

    def test_limit_zero_and_large_offset_are_empty(self):
        """limit=0 -> empty (distinct from omitting); offset >= count -> empty."""
        _assert_test_passed(
            _run_verify("limit_zero_and_large_offset_are_empty"),
            "limit_zero_and_large_offset_are_empty",
        )

    def test_filter_then_paginate_compose(self):
        """source=runtime&offset=1 composes filter then pagination over the subset."""
        _assert_test_passed(
            _run_verify("filter_then_paginate_compose"),
            "filter_then_paginate_compose",
        )

    def test_non_numeric_offset_is_400_with_message(self):
        """offset=abc -> 400 with ApiError-shaped JSON `message`, no logs array."""
        _assert_test_passed(
            _run_verify("non_numeric_offset_is_400_with_message"),
            "non_numeric_offset_is_400_with_message",
        )

    def test_non_numeric_limit_is_400_with_message(self):
        """limit=xyz -> 400 with ApiError-shaped JSON `message`."""
        _assert_test_passed(
            _run_verify("non_numeric_limit_is_400_with_message"),
            "non_numeric_limit_is_400_with_message",
        )
