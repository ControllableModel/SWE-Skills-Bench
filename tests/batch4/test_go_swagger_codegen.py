"""Benchmark test for skill `go-swagger-codegen` (variant ext4).

Task: make the `@Tags` operation annotation quote-aware in swaggo/swag.
The agent edits `operation.go`'s `ParseTagsComment` (and extends
`operation_test.go`) inside REPO_DIR = /workspace/swag so that:

  - a double-quoted tag is a single tag with the surrounding quotes stripped,
  - a comma *inside* a quoted value does NOT split the value,
  - a comma *outside* quotes still separates tags,
  - leading/trailing whitespace around each tag is trimmed (existing behavior),
  - unquoted input is unchanged (no quotes stripped from a never-quoted value),
  - a quoted empty value `""` yields one empty-string tag,
  - tag order is preserved.

Verification strategy
---------------------
Rather than trust the agent's own test additions, these tests INJECT an
independent in-package Go test driver (package swag) into REPO_DIR and run it
with the repo's native toolchain (`go test`).  The driver constructs a fresh
`NewOperation(nil)`, calls `op.ParseTagsComment(<line>)` directly, and asserts
on the resulting `op.Tags` slice (exact contents, length and order).  This
exercises the real parsing behavior the task requires; a naive comma-split
implementation (the original code) FAILS the quoted cases, and a stub that
hardcodes a fixed slice FAILS the parametric cases.

L1: deliverable files exist and are well-formed; the swag package compiles.
L2: dynamic execution of `go test` over injected drivers covering quoted,
    mixed, comma-in-quotes, empty-quote, unquoted-unchanged, whitespace and
    order cases, plus the repo's own `TestParseTagsComment` (no regression).

Native acceptance command driven by L2:
    go test -run TestParseTagsComment ./...
"""

import os
import subprocess
import textwrap
import uuid

import pytest

REPO_DIR = "/workspace/swag"
GO_TIMEOUT = 420


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _go_env():
    env = dict(os.environ)
    env.setdefault("GOFLAGS", "-mod=mod")
    env["CGO_ENABLED"] = "0"
    return env


def _run_go(args, timeout=GO_TIMEOUT):
    """Run a `go ...` command in REPO_DIR and return CompletedProcess."""
    return subprocess.run(
        ["go", *args],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_go_env(),
    )


def _write_driver(body: str) -> str:
    """Write an in-package Go test file (package swag) into REPO_DIR.

    Returns the absolute path so the caller can remove it afterwards.
    `body` must contain one or more `func TestXxx(t *testing.T) { ... }`.
    """
    fname = f"zz_bench_{uuid.uuid4().hex[:12]}_test.go"
    path = os.path.join(REPO_DIR, fname)
    header = textwrap.dedent(
        """\
        package swag

        import (
        \t"testing"
        )

        """
    )
    with open(path, "w") as fh:
        fh.write(header + textwrap.dedent(body))
    return path


def _run_driver(test_name: str, body: str):
    """Inject driver, run `go test -run <test_name>`, clean up.

    Returns the CompletedProcess from `go test`.
    """
    path = _write_driver(body)
    try:
        return _run_go(
            ["test", "-run", f"^{test_name}$", "-v", "-count=1", "."]
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _purge_stale_drivers():
    """Remove any leftover injected driver files (defensive, e.g. on NFS)."""
    try:
        for name in os.listdir(REPO_DIR):
            if name.startswith("zz_bench_") and name.endswith("_test.go"):
                try:
                    os.remove(os.path.join(REPO_DIR, name))
                except OSError:
                    pass
    except OSError:
        pass


# A reusable Go helper that asserts op.Tags equals an expected slice exactly
# (length + order + contents). Embedded into each driver body.
_ASSERT_HELPER = r'''
func zzAssertTags(t *testing.T, line string, want []string) {
	t.Helper()
	op := NewOperation(nil)
	op.ParseTagsComment(line)
	got := op.Tags
	if len(got) != len(want) {
		t.Fatalf("ParseTagsComment(%q): len(Tags)=%d %v, want %d %v",
			line, len(got), got, len(want), want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("ParseTagsComment(%q): Tags[%d]=%q, want %q (full got=%v want=%v)",
				line, i, got[i], want[i], got, want)
		}
	}
}
'''


@pytest.fixture(scope="module", autouse=True)
def _ensure_build():
    assert os.path.isdir(REPO_DIR), f"REPO_DIR missing: {REPO_DIR}"
    _purge_stale_drivers()
    # `go build ./...` warms the module cache and proves the agent's edit
    # compiles before any behavioral driver runs. It does not compile *_test.go,
    # so it is immune to injected driver files.
    proc = _run_go(["build", "./..."], timeout=GO_TIMEOUT)
    assert proc.returncode == 0, (
        "repository does not build after the change:\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    yield
    _purge_stale_drivers()


class TestGoSwaggerCodegen:
    REPO_DIR = "/workspace/swag"

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist and are well-formed.
    # ------------------------------------------------------------------ #
    def test_operation_source_exists(self):
        """L1: operation.go (the file to modify) exists and is non-trivial."""
        path = os.path.join(self.REPO_DIR, "operation.go")
        assert os.path.isfile(path), f"missing {path}"
        assert os.path.getsize(path) > 1000, "operation.go unexpectedly small"

    def test_parse_tags_comment_present(self):
        """L1: ParseTagsComment is still defined on *Operation in operation.go."""
        path = os.path.join(self.REPO_DIR, "operation.go")
        with open(path) as fh:
            content = fh.read()
        assert "func (operation *Operation) ParseTagsComment(" in content, (
            "ParseTagsComment method must remain defined on *Operation"
        )

    def test_operation_test_source_exists(self):
        """L1: operation_test.go exists and keeps TestParseTagsComment."""
        path = os.path.join(self.REPO_DIR, "operation_test.go")
        assert os.path.isfile(path), f"missing {path}"
        with open(path) as fh:
            content = fh.read()
        assert "func TestParseTagsComment(" in content, (
            "TestParseTagsComment function must remain in operation_test.go"
        )

    def test_package_compiles(self):
        """L1: the swag package and its commands compile after the change."""
        _purge_stale_drivers()
        proc = _run_go(["build", "./..."], timeout=GO_TIMEOUT)
        assert proc.returncode == 0, (
            f"go build ./... failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic behavior via injected drivers.
    # ------------------------------------------------------------------ #
    def test_unquoted_unchanged_basic(self):
        """L2: plain comma-separated unquoted input is unchanged (regression)."""
        body = _ASSERT_HELPER + r'''
        func TestZZUnquotedBasic(t *testing.T) {
        	zzAssertTags(t, `pets, store`, []string{"pets", "store"})
        	zzAssertTags(t, `pets`, []string{"pets"})
        }
        '''
        proc = _run_driver("TestZZUnquotedBasic", body)
        assert proc.returncode == 0, (
            "unquoted comma-separated tags must be unchanged:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_single_quoted_multiword_tag(self):
        """L2: `"user accounts"` -> one tag with quotes stripped, space kept."""
        body = _ASSERT_HELPER + r'''
        func TestZZSingleQuoted(t *testing.T) {
        	zzAssertTags(t, `"user accounts"`, []string{"user accounts"})
        }
        '''
        proc = _run_driver("TestZZSingleQuoted", body)
        assert proc.returncode == 0, (
            "single quoted multi-word tag must become one unquoted tag:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_mixed_quoted_and_unquoted(self):
        """L2: `"user accounts", store` -> ["user accounts", "store"]."""
        body = _ASSERT_HELPER + r'''
        func TestZZMixed(t *testing.T) {
        	zzAssertTags(t, `"user accounts", store`,
        		[]string{"user accounts", "store"})
        }
        '''
        proc = _run_driver("TestZZMixed", body)
        assert proc.returncode == 0, (
            "mixed quoted + unquoted input mis-parsed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_comma_inside_quotes_not_split(self):
        """L2: `"a, b", c` -> ["a, b", "c"] (comma inside quotes preserved)."""
        body = _ASSERT_HELPER + r'''
        func TestZZCommaInQuotes(t *testing.T) {
        	zzAssertTags(t, `"a, b", c`, []string{"a, b", "c"})
        }
        '''
        proc = _run_driver("TestZZCommaInQuotes", body)
        assert proc.returncode == 0, (
            "comma inside double quotes must not split the value:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_quoted_empty_value_one_empty_tag(self):
        """L2: `""` -> exactly one empty-string tag (quotes stripped)."""
        body = _ASSERT_HELPER + r'''
        func TestZZQuotedEmpty(t *testing.T) {
        	zzAssertTags(t, `""`, []string{""})
        }
        '''
        proc = _run_driver("TestZZQuotedEmpty", body)
        assert proc.returncode == 0, (
            "quoted empty value must yield a single empty-string tag:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_whitespace_trimmed_around_tags(self):
        """L2: surrounding ASCII whitespace around each tag is trimmed."""
        body = _ASSERT_HELPER + r'''
        func TestZZWhitespace(t *testing.T) {
        	zzAssertTags(t, `  pets ,  store  `, []string{"pets", "store"})
        	// Whitespace outside the quotes is trimmed; the quoted interior
        	// (which itself has no leading/trailing space here) is preserved.
        	zzAssertTags(t, `  "user accounts" ,  store `,
        		[]string{"user accounts", "store"})
        }
        '''
        proc = _run_driver("TestZZWhitespace", body)
        assert proc.returncode == 0, (
            "whitespace around tags must be trimmed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_quotes_not_stripped_from_unquoted_value(self):
        """L2: a value that was never wrapped in quotes keeps its characters.

        Guards against a naive `strings.ReplaceAll(x, "\"", "")` style fix that
        would strip stray quotes from unquoted tokens. A bare `pets` must stay
        `pets`, and an unquoted token is not altered.
        """
        body = _ASSERT_HELPER + r'''
        func TestZZUnquotedNotStripped(t *testing.T) {
        	zzAssertTags(t, `pets`, []string{"pets"})
        	zzAssertTags(t, `pet, store, user`, []string{"pet", "store", "user"})
        }
        '''
        proc = _run_driver("TestZZUnquotedNotStripped", body)
        assert proc.returncode == 0, (
            "unquoted tokens must not be altered:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_order_preserved_three_tags(self):
        """L2: tag order is preserved across quoted/unquoted mixes."""
        body = _ASSERT_HELPER + r'''
        func TestZZOrder(t *testing.T) {
        	zzAssertTags(t, `alpha, "b, c", delta`,
        		[]string{"alpha", "b, c", "delta"})
        	zzAssertTags(t, `"x y", z, "p, q"`,
        		[]string{"x y", "z", "p, q"})
        }
        '''
        proc = _run_driver("TestZZOrder", body)
        assert proc.returncode == 0, (
            "tag order must be preserved:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_acceptance_examples_full_table(self):
        """L2: every row of the doc's Expected-Functionality table, in one driver.

        A stub that hardcodes any single answer fails the others; the original
        naive comma-split fails all quoted rows.
        """
        body = _ASSERT_HELPER + r'''
        func TestZZAcceptanceTable(t *testing.T) {
        	zzAssertTags(t, `pets, store`, []string{"pets", "store"})
        	zzAssertTags(t, `"user accounts"`, []string{"user accounts"})
        	zzAssertTags(t, `"user accounts", store`, []string{"user accounts", "store"})
        	zzAssertTags(t, `"a, b", c`, []string{"a, b", "c"})
        	zzAssertTags(t, `pets`, []string{"pets"})
        }
        '''
        proc = _run_driver("TestZZAcceptanceTable", body)
        assert proc.returncode == 0, (
            "acceptance-criteria table not fully satisfied:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout

    def test_repo_native_parsetags_suite_passes(self):
        """L2: the repo's own `go test -run TestParseTagsComment ./...` passes.

        This is the doc's native acceptance command. It runs the agent's own
        (extended) TestParseTagsComment plus the pre-existing assertions.
        """
        _purge_stale_drivers()
        proc = _run_go(
            ["test", "-run", "TestParseTagsComment", "-count=1", "./..."]
        )
        assert proc.returncode == 0, (
            "native TestParseTagsComment suite failed:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "ok" in proc.stdout, (
            f"expected a passing package line:\nSTDOUT:\n{proc.stdout}"
        )

    def test_consecutive_quoted_tags(self):
        """L2: two adjacent quoted tags separated by a comma each strip quotes."""
        body = _ASSERT_HELPER + r'''
        func TestZZConsecutiveQuoted(t *testing.T) {
        	zzAssertTags(t, `"first one", "second two"`,
        		[]string{"first one", "second two"})
        }
        '''
        proc = _run_driver("TestZZConsecutiveQuoted", body)
        assert proc.returncode == 0, (
            "consecutive quoted tags must both be unquoted:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "PASS" in proc.stdout
