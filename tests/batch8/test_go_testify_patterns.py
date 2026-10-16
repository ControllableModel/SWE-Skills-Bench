"""
Test for 'go-testify-patterns' skill (variant ext8) — a deterministic
"group provider hashes by scheme" helper for hashicorp/terraform.

Variant task summary
--------------------
The agent must add a self-contained, network-free helper to the existing
`internal/getproviders` package:

    func GroupHashesByScheme(raw []string) (groups map[string][]string, invalid []string)

Behavior mandated by the requirement doc:
  - Each raw entry is parsed with ParseHash. On success its Value() (the part
    after the "scheme:" prefix) is appended to groups keyed by its scheme NAME
    (the example shows groups["zh"] / groups["h1"], i.e. WITHOUT the trailing
    colon that Hash.Scheme() carries).
  - Entries ParseHash rejects (no scheme prefix / empty / leading colon) go to
    `invalid` as their original raw string.
  - Within each group, values are sorted ascending AND de-duplicated. `invalid`
    is likewise sorted ascending and de-duplicated.
  - Both return values are non-nil even when empty. A scheme with no valid
    entries must NOT appear as an empty key.
  - Unrecognized-but-well-formed schemes (any "xx:" prefix) are still grouped,
    never invalid (consistent with ParseHash accepting future schemes).
  - The function is deterministic and order-independent: shuffling `raw` yields
    identical groups and invalid.

Deliverables:
  - internal/getproviders/hash_group.go          (new helper, package getproviders)
  - internal/getproviders/hash_group_test.go     (agent's testify test)

Verification strategy (discriminative power)
-------------------------------------------
Rather than trusting the agent's own testify test, the bulk of the L2 cases
inject an INDEPENDENT Go test file (`zz_bench_hashgroup_test.go`) into the
getproviders package that calls `GroupHashesByScheme` directly with stdlib only
(no testify needed) and deep-validates real behavior: grouping by scheme name,
ascending sort, de-duplication, invalid collection, non-nil empties, future
schemes, and order-independence. That file is removed in teardown. A naive
implementation (returns nil maps, skips sorting, skips de-dup, mis-keys with the
colon, or drops the invalid list) cannot pass these checks.

A separate L2 case drives the doc's MANDATED native command, which runs the
agent's own testify suite:

    go test ./internal/getproviders/ -run TestGroupHashesByScheme -v
"""

import os
import shutil
import subprocess

import pytest


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------
def _find_repo_dir(_fallback):
    """Repo clones to /workspace/<repo-name>, not /workspace/<skill-id>. Prefer the
    harness-provided SWE_REPO_DIR (authoritative); else discover the single real repo
    dir under /workspace; else the known fallback. Reading SWE_REPO_DIR avoids picking
    the wrong repo when a job's rootfs accumulated several repos."""
    _env = os.environ.get("SWE_REPO_DIR")
    if _env and os.path.isdir(_env):
        return _env
    import glob as _glob
    _skip = {"tests", "benchmark_tests", "lost+found"}
    _c = [d for d in sorted(_glob.glob("/workspace/*"))
          if os.path.isdir(d) and os.path.basename(d) not in _skip]
    _git = [d for d in _c if os.path.isdir(os.path.join(d, ".git"))]
    if len(_git) == 1:
        return _git[0]
    if len(_c) == 1:
        return _c[0]
    return _fallback
REPO_DIR = _find_repo_dir("/workspace/terraform")
GP_REL = os.path.join("internal", "getproviders")
GP_DIR = os.path.join(REPO_DIR, GP_REL)

# Sorts last + obviously a benchmark artifact.
DRIVER_BASENAME = "zz_bench_hashgroup_test.go"
DRIVER_PATH = os.path.join(GP_DIR, DRIVER_BASENAME)


def _go_bin():
    """Locate the go binary (PYTHONPATH cleared; PATH may be minimal)."""
    found = shutil.which("go")
    if found:
        return found
    for cand in (
        "/usr/local/go/bin/go",
        "/usr/lib/go/bin/go",
        os.path.expanduser("~/go-sdk/go/bin/go"),
        "/root/go-sdk/go/bin/go",
    ):
        if os.path.isfile(cand):
            return cand
    return "go"


GO = _go_bin()


def _run_go(args, timeout=600, cwd=GP_DIR):
    env = dict(os.environ)
    gobin_dir = os.path.dirname(GO)
    env["PATH"] = gobin_dir + os.pathsep + env.get("PATH", "")
    # -mod=mod lets the toolchain add testify (only transitively in go.sum) so
    # the agent's testify test can resolve.
    env.setdefault("GOFLAGS", "-mod=mod")
    env.setdefault("GOCACHE", "/tmp/go-cache-benchmark")
    env.setdefault("CGO_ENABLED", "0")
    return subprocess.run(
        [GO] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


# ---------------------------------------------------------------------------
# Independent driver: stdlib-only Go test that hammers GroupHashesByScheme.
# Each sub-test prints a unique OK marker the python layer asserts on. No
# testify dependency here so module resolution can't block independent checks.
# ---------------------------------------------------------------------------
DRIVER_SOURCE = r'''// Code generated by the benchmark harness. DO NOT EDIT. Removed after the run.
package getproviders

import (
	"fmt"
	"sort"
	"testing"
)

// isSortedUniqueAsc reports whether s is strictly ascending (sorted + no dups).
func benchSortedUnique(s []string) bool {
	for i := 1; i < len(s); i++ {
		if s[i-1] >= s[i] {
			return false
		}
	}
	return true
}

func benchEqualStrs(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func TestBenchMultiSchemeGrouping(t *testing.T) {
	groups, invalid := GroupHashesByScheme([]string{"zh:abc", "h1:xyz", "zh:def"})
	if groups == nil {
		t.Fatalf("groups must be non-nil")
	}
	if invalid == nil {
		t.Fatalf("invalid must be non-nil")
	}
	if len(invalid) != 0 {
		t.Fatalf("expected no invalid entries, got %v", invalid)
	}
	// Doc example: keyed by scheme NAME without trailing colon.
	zh, ok := groups["zh"]
	if !ok {
		t.Fatalf("missing group key \"zh\"; keys=%v", keysOf(groups))
	}
	if !benchEqualStrs(zh, []string{"abc", "def"}) {
		t.Fatalf("groups[\"zh\"] = %v, want [abc def]", zh)
	}
	h1, ok := groups["h1"]
	if !ok {
		t.Fatalf("missing group key \"h1\"; keys=%v", keysOf(groups))
	}
	if !benchEqualStrs(h1, []string{"xyz"}) {
		t.Fatalf("groups[\"h1\"] = %v, want [xyz]", h1)
	}
	if len(groups) != 2 {
		t.Fatalf("expected exactly 2 groups, got %d (%v)", len(groups), keysOf(groups))
	}
	fmt.Println("BENCH_OK_multi_scheme")
}

func keysOf(m map[string][]string) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func TestBenchValuesSortedDeduped(t *testing.T) {
	// Unsorted + duplicate values within a scheme.
	groups, _ := GroupHashesByScheme([]string{
		"h1:ccc", "h1:aaa", "h1:bbb", "h1:aaa", "h1:bbb",
	})
	vals, ok := groups["h1"]
	if !ok {
		t.Fatalf("missing group \"h1\"")
	}
	want := []string{"aaa", "bbb", "ccc"}
	if !benchEqualStrs(vals, want) {
		t.Fatalf("groups[\"h1\"] = %v, want %v (sorted+deduped)", vals, want)
	}
	if !benchSortedUnique(vals) {
		t.Fatalf("values not strictly ascending/unique: %v", vals)
	}
	fmt.Println("BENCH_OK_sorted_deduped")
}

func TestBenchDuplicateScalarDeduped(t *testing.T) {
	// Identical scheme:value listed twice contributes ONE value.
	groups, _ := GroupHashesByScheme([]string{"h1:xyz", "h1:xyz"})
	vals := groups["h1"]
	if len(vals) != 1 || vals[0] != "xyz" {
		t.Fatalf("duplicate h1:xyz must collapse to single [xyz], got %v", vals)
	}
	fmt.Println("BENCH_OK_dup_scalar")
}

func TestBenchInvalidCollected(t *testing.T) {
	// "" (empty), "nocolon" (no scheme), ":leading" (zero-len scheme) are all
	// rejected by ParseHash. Verify they land in invalid (sorted+deduped) and
	// in NO group; valid entries still grouped.
	raw := []string{
		"nocolon", "h1:keep", ":leading", "nocolon", "zh:keep", "",
	}
	groups, invalid := GroupHashesByScheme(raw)

	// invalid: sorted ascending, de-duplicated. "nocolon" appears twice -> once.
	want := []string{"", ":leading", "nocolon"}
	if !benchEqualStrs(invalid, want) {
		t.Fatalf("invalid = %v, want %v", invalid, want)
	}
	if !benchSortedUnique(invalid) {
		t.Fatalf("invalid not strictly ascending/unique: %v", invalid)
	}
	// Malformed entries must not contaminate any group.
	for k, vs := range groups {
		for _, v := range vs {
			if v == "nocolon" || v == ":leading" || v == "" {
				t.Fatalf("invalid value %q leaked into group %q", v, k)
			}
		}
	}
	// Valid ones still present.
	if len(groups["h1"]) != 1 || groups["h1"][0] != "keep" {
		t.Fatalf("groups[\"h1\"] = %v, want [keep]", groups["h1"])
	}
	if len(groups["zh"]) != 1 || groups["zh"][0] != "keep" {
		t.Fatalf("groups[\"zh\"] = %v, want [keep]", groups["zh"])
	}
	fmt.Println("BENCH_OK_invalid_collected")
}

func TestBenchEmptyInputNonNil(t *testing.T) {
	groups, invalid := GroupHashesByScheme([]string{})
	if groups == nil {
		t.Fatalf("groups must be non-nil even for empty input")
	}
	if invalid == nil {
		t.Fatalf("invalid must be non-nil even for empty input")
	}
	if len(groups) != 0 {
		t.Fatalf("groups must be empty for empty input, got %v", groups)
	}
	if len(invalid) != 0 {
		t.Fatalf("invalid must be empty for empty input, got %v", invalid)
	}
	// nil input should behave the same.
	g2, i2 := GroupHashesByScheme(nil)
	if g2 == nil || i2 == nil {
		t.Fatalf("nil input must still yield non-nil groups and invalid")
	}
	fmt.Println("BENCH_OK_empty_nonnil")
}

func TestBenchNoEmptyGroupKeys(t *testing.T) {
	// All entries invalid -> NO group keys at all (no empty-slice keys).
	groups, invalid := GroupHashesByScheme([]string{"bad", "alsobad"})
	if len(groups) != 0 {
		t.Fatalf("a scheme with no valid entries must not appear; groups=%v", keysOf(groups))
	}
	for k, vs := range groups {
		if len(vs) == 0 {
			t.Fatalf("empty-slice group key present: %q", k)
		}
	}
	if !benchEqualStrs(invalid, []string{"alsobad", "bad"}) {
		t.Fatalf("invalid = %v, want [alsobad bad]", invalid)
	}
	fmt.Println("BENCH_OK_no_empty_keys")
}

func TestBenchFutureSchemeGrouped(t *testing.T) {
	// A scheme this Terraform version does not know ("future99:") is still
	// well-formed for ParseHash, so it MUST be grouped, not invalid.
	groups, invalid := GroupHashesByScheme([]string{"future99:val", "h1:a"})
	if len(invalid) != 0 {
		t.Fatalf("well-formed future scheme must not be invalid, got %v", invalid)
	}
	fv, ok := groups["future99"]
	if !ok {
		t.Fatalf("future scheme group \"future99\" missing; keys=%v", keysOf(groups))
	}
	if !benchEqualStrs(fv, []string{"val"}) {
		t.Fatalf("groups[\"future99\"] = %v, want [val]", fv)
	}
	fmt.Println("BENCH_OK_future_scheme")
}

func TestBenchSchemeKeyHasNoColon(t *testing.T) {
	// Discriminative: a stub that keys by Hash.Scheme() directly would produce
	// "zh:" / "h1:" keys (with colon). The doc example mandates "zh" / "h1".
	groups, _ := GroupHashesByScheme([]string{"zh:x", "h1:y"})
	for k := range groups {
		if len(k) == 0 {
			t.Fatalf("empty scheme key")
		}
		if k[len(k)-1] == ':' {
			t.Fatalf("scheme key %q must NOT include the trailing colon", k)
		}
	}
	if _, ok := groups["zh"]; !ok {
		t.Fatalf("expected key \"zh\" (no colon); keys=%v", keysOf(groups))
	}
	if _, ok := groups["h1"]; !ok {
		t.Fatalf("expected key \"h1\" (no colon); keys=%v", keysOf(groups))
	}
	fmt.Println("BENCH_OK_key_no_colon")
}

func TestBenchValueAfterScheme(t *testing.T) {
	// Value must be the part AFTER the scheme prefix, even when the value
	// itself contains a colon (only the FIRST colon splits scheme/value).
	groups, _ := GroupHashesByScheme([]string{"h1:aa:bb"})
	vals := groups["h1"]
	if len(vals) != 1 || vals[0] != "aa:bb" {
		t.Fatalf("value must be everything after first colon; got %v, want [aa:bb]", vals)
	}
	fmt.Println("BENCH_OK_value_after_scheme")
}

func TestBenchOrderIndependent(t *testing.T) {
	base := []string{
		"zh:def", "h1:xyz", "zh:abc", "bad1", "h1:aaa", "bad0", "zh:abc",
	}
	shuffled := []string{
		"h1:aaa", "zh:abc", "bad0", "zh:def", "zh:abc", "h1:xyz", "bad1",
	}
	g1, i1 := GroupHashesByScheme(base)
	g2, i2 := GroupHashesByScheme(shuffled)

	if !benchEqualStrs(i1, i2) {
		t.Fatalf("invalid differs by input order: %v vs %v", i1, i2)
	}
	if len(g1) != len(g2) {
		t.Fatalf("group count differs by input order: %v vs %v", keysOf(g1), keysOf(g2))
	}
	for _, k := range keysOf(g1) {
		if !benchEqualStrs(g1[k], g2[k]) {
			t.Fatalf("group %q differs by input order: %v vs %v", k, g1[k], g2[k])
		}
	}
	// And concrete expected content.
	if !benchEqualStrs(g1["zh"], []string{"abc", "def"}) {
		t.Fatalf("groups[\"zh\"] = %v, want [abc def]", g1["zh"])
	}
	if !benchEqualStrs(g1["h1"], []string{"aaa", "xyz"}) {
		t.Fatalf("groups[\"h1\"] = %v, want [aaa xyz]", g1["h1"])
	}
	if !benchEqualStrs(i1, []string{"bad0", "bad1"}) {
		t.Fatalf("invalid = %v, want [bad0 bad1]", i1)
	}
	fmt.Println("BENCH_OK_order_independent")
}
'''


def _write_driver():
    with open(DRIVER_PATH, "w") as f:
        f.write(DRIVER_SOURCE)


def _remove_driver():
    try:
        os.remove(DRIVER_PATH)
    except OSError:
        pass


@pytest.fixture(scope="module", autouse=True)
def _warmup_go_modules():
    """Pre-fetch module deps once so per-test native commands don't re-download."""
    if os.path.isdir(GP_DIR):
        try:
            _run_go(["mod", "download"], timeout=600)
        except Exception:
            pass
    yield


@pytest.fixture(scope="module")
def driver_run():
    """
    Build & run the independent benchmark driver once for the module.
    Returns the CompletedProcess so individual tests can assert on markers.
    """
    assert os.path.isdir(GP_DIR), f"getproviders package dir missing: {GP_DIR}"
    helper = os.path.join(GP_DIR, "hash_group.go")
    assert os.path.isfile(helper), "hash_group.go was not created by the agent"

    _write_driver()
    try:
        proc = _run_go(
            ["test", "-run", "TestBench", "-v", "-count=1", "-timeout=120s", "./"],
            timeout=600,
        )
    finally:
        _remove_driver()
    return proc


def _assert_marker(proc, marker):
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, (
        f"benchmark driver `go test` failed (rc={proc.returncode}).\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert marker in combined, (
        f"expected marker {marker!r} not found in driver output.\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


class TestGoTestifyPatterns:
    """Verify the GroupHashesByScheme helper and its testify test."""

    REPO_DIR = _find_repo_dir("/workspace/terraform")

    # ------------------------------------------------------------------
    # L1: deliverable files exist and are minimally well-formed
    # ------------------------------------------------------------------
    def test_hash_group_source_exists(self):
        """hash_group.go must exist in the getproviders package and declare it."""
        p = os.path.join(GP_DIR, "hash_group.go")
        assert os.path.isfile(p), f"missing deliverable {p}"
        with open(p) as f:
            content = f.read()
        assert "package getproviders" in content, (
            "hash_group.go must be in package getproviders"
        )
        assert "func GroupHashesByScheme" in content, (
            "hash_group.go must define GroupHashesByScheme"
        )

    def test_hash_group_test_exists(self):
        """hash_group_test.go (agent's testify test) must exist & use testify."""
        p = os.path.join(GP_DIR, "hash_group_test.go")
        assert os.path.isfile(p), f"missing deliverable {p}"
        with open(p) as f:
            content = f.read()
        assert "package getproviders" in content, (
            "hash_group_test.go must be in package getproviders"
        )
        assert "stretchr/testify" in content, (
            "the mandated test must exercise GroupHashesByScheme via testify"
        )
        assert "TestGroupHashesByScheme" in content, (
            "test file must contain the TestGroupHashesByScheme entry point"
        )

    def test_package_compiles(self):
        """The getproviders package must still build with the new file added."""
        proc = _run_go(["build", "./"], timeout=600)
        assert proc.returncode == 0, (
            f"`go build ./` failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    # ------------------------------------------------------------------
    # L2: independent dynamic execution of GroupHashesByScheme
    # ------------------------------------------------------------------
    def test_multi_scheme_grouping(self, driver_run):
        """zh:abc,h1:xyz,zh:def -> groups[zh]=[abc,def], groups[h1]=[xyz], no invalid."""
        _assert_marker(driver_run, "BENCH_OK_multi_scheme")

    def test_values_sorted_deduped(self, driver_run):
        """within a scheme, values are sorted ascending and de-duplicated."""
        _assert_marker(driver_run, "BENCH_OK_sorted_deduped")

    def test_duplicate_scalar_deduped(self, driver_run):
        """the same scheme:value listed twice contributes exactly one value."""
        _assert_marker(driver_run, "BENCH_OK_dup_scalar")

    def test_invalid_collected(self, driver_run):
        """malformed entries land in invalid (sorted+deduped), never in a group."""
        _assert_marker(driver_run, "BENCH_OK_invalid_collected")

    def test_empty_input_non_nil(self, driver_run):
        """empty/nil input yields non-nil empty groups and invalid."""
        _assert_marker(driver_run, "BENCH_OK_empty_nonnil")

    def test_no_empty_group_keys(self, driver_run):
        """a scheme with no valid entries must not appear as an empty key."""
        _assert_marker(driver_run, "BENCH_OK_no_empty_keys")

    def test_future_scheme_grouped(self, driver_run):
        """unrecognized but well-formed schemes are grouped, not invalid."""
        _assert_marker(driver_run, "BENCH_OK_future_scheme")

    def test_scheme_key_has_no_colon(self, driver_run):
        """group keys are scheme NAMES without the trailing colon (zh, not zh:)."""
        _assert_marker(driver_run, "BENCH_OK_key_no_colon")

    def test_value_after_scheme(self, driver_run):
        """value is everything after the first colon (split on first colon only)."""
        _assert_marker(driver_run, "BENCH_OK_value_after_scheme")

    def test_order_independent(self, driver_run):
        """shuffling raw input yields identical groups and invalid."""
        _assert_marker(driver_run, "BENCH_OK_order_independent")

    # ------------------------------------------------------------------
    # L2: the agent's own testify test must pass under the mandated command
    # ------------------------------------------------------------------
    def test_agent_testify_command_passes(self):
        """`go test ./internal/getproviders/ -run TestGroupHashesByScheme -v` must pass.

        Driven from the repo root exactly as the doc's Acceptance Criteria
        specifies, so module resolution of the package path is identical.
        """
        proc = _run_go(
            [
                "test",
                "./internal/getproviders/",
                "-run",
                "TestGroupHashesByScheme",
                "-v",
                "-count=1",
                "-timeout=120s",
            ],
            timeout=600,
            cwd=REPO_DIR,
        )
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "mandated testify command failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "TestGroupHashesByScheme" in out, (
            "TestGroupHashesByScheme did not run; output:\n" + out
        )
        assert "no tests to run" not in out, (
            "TestGroupHashesByScheme matched nothing:\n" + out
        )
        assert "PASS" in out or "ok" in out, "mandated test did not pass:\n" + out
