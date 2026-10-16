"""Tests for the `bats-shell-testing` skill task (variant ext9): a pure-string
subpath-containment helper.

Skill: bats-shell-testing
Task (ext9): Add a `bats_path_is_inside <candidate-path> <base-path>` helper to
`lib/bats-core/common.bash` that decides, purely from the string values, whether
`<candidate-path>` is the same as, or located beneath, `<base-path>` in the path
hierarchy. Containment is by whole path SEGMENTS (so `/foobar` is NOT inside
`/foo`), a path is inside itself, trailing slashes on either argument are ignored,
and root `/` contains every absolute path. The answer is signalled via exit status
(0 = inside, non-zero = not inside). The helper must be self-contained: no
external programs (no `realpath`, `readlink`, `dirname`, `python`), no filesystem
access. A second deliverable is a `@test bats_path_is_inside` block added to
`test/common.bats`. Acceptance command (from repo root): `./bin/bats test/common.bats`.

Verification strategy:
  * L1: the two deliverable files exist; the new function definition and new
    `@test` block are present; the helper body uses no forbidden external tool;
    common.bash sources cleanly and exposes the function.
  * L2: dynamic behavior, driven by sourcing common.bash and invoking the helper
    DIRECTLY in an isolated subshell for every Expected-Functionality scenario
    (segment-boundary, self-containment, trailing slashes, root base, parent is
    not inside, plus filesystem-independence) AND by running the native
    `bin/bats test/common.bats` acceptance suite so the agent's new @test block
    must pass alongside the pre-existing ones.

The direct-execution L2 cases are written INDEPENDENTLY of the agent's own .bats
test, so a stub that merely adds a passing-looking @test, or one that uses a raw
string-prefix compare (which would wrongly call `/foobar` inside `/foo`), will
fail here.
"""

import os
import re
import subprocess

import pytest


class TestBatsShellTesting:
    REPO_DIR = "/workspace/bats-core"

    COMMON_BASH = os.path.join(REPO_DIR, "lib", "bats-core", "common.bash")
    COMMON_BATS = os.path.join(REPO_DIR, "test", "common.bats")
    BATS_BIN = os.path.join(REPO_DIR, "bin", "bats")

    # ------------------------------------------------------------------ helpers

    def _run_inside(self, *args):
        """Source common.bash and invoke `bats_path_is_inside` in an isolated
        subshell, returning (returncode, stdout, stderr).

        The call is wrapped in a child shell via `( ... )` so an implementation
        that uses `exit` does not kill our harness shell; the child's exit status
        is captured and echoed back via a marker. Each argument is single-quoted
        to survive odd inputs.
        """
        quoted = " ".join("'%s'" % a for a in args)
        script = (
            "set +e\n"
            "source '%s'\n"
            "( bats_path_is_inside %s )\n"
            'echo "__RC__=$?"\n' % (self.COMMON_BASH, quoted)
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        m = re.search(r"__RC__=(-?\d+)", proc.stdout)
        assert m is not None, (
            "could not determine helper exit code; stdout=%r stderr=%r"
            % (proc.stdout, proc.stderr)
        )
        rc = int(m.group(1))
        stdout = re.sub(r"__RC__=-?\d+\n?", "", proc.stdout)
        return rc, stdout, proc.stderr

    def _inside_rc(self, *args):
        return self._run_inside(*args)[0]

    # --------------------------------------------------------------------- L1

    def test_repo_and_files_present(self):
        """L1: REPO_DIR and the two deliverable files (and the bats runner) exist."""
        assert os.path.isdir(self.REPO_DIR), "missing repo dir %s" % self.REPO_DIR
        assert os.path.isfile(self.COMMON_BASH), "missing %s" % self.COMMON_BASH
        assert os.path.isfile(self.COMMON_BATS), "missing %s" % self.COMMON_BATS
        assert os.path.isfile(self.BATS_BIN), "missing bats runner %s" % self.BATS_BIN

    def test_function_defined_in_common_bash(self):
        """L1: a `bats_path_is_inside` function definition was added to common.bash."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        assert re.search(
            r"(?m)^\s*(function\s+)?bats_path_is_inside\s*\(\s*\)",
            content,
        ), "no bats_path_is_inside function definition found in common.bash"

    def test_new_test_block_present(self):
        """L1: a `@test bats_path_is_inside` block was added to common.bats."""
        with open(self.COMMON_BATS) as f:
            content = f.read()
        assert re.search(
            r'@test\s+(bats_path_is_inside\b|"bats_path_is_inside"|'
            r"'bats_path_is_inside')",
            content,
        ), "no `@test bats_path_is_inside` block found in common.bats"

    def test_no_external_or_filesystem_tools(self):
        """L1: the helper is pure-string and self-contained -- no realpath /
        readlink / dirname / python / cd, no actual filesystem access introduced
        in the new function body."""
        with open(self.COMMON_BASH) as f:
            content = f.read()
        m = re.search(
            r"(?ms)^\s*(?:function\s+)?bats_path_is_inside\s*\(\s*\).*?\n\}",
            content,
        )
        assert m is not None, "could not isolate bats_path_is_inside body"
        body = m.group(0)
        for forbidden in (
            "realpath",
            "readlink",
            "dirname",
            "python",
            "perl",
            "awk",
        ):
            assert forbidden not in body, (
                "helper must not use external program %r (must be pure string)"
                % forbidden
            )

    def test_helper_is_sourceable(self):
        """L1/L2 bridge: common.bash sources cleanly and exposes the new function."""
        script = (
            "source '%s'\n"
            "type -t bats_path_is_inside\n" % self.COMMON_BASH
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, "sourcing common.bash failed: %s" % proc.stderr
        assert proc.stdout.strip() == "function", (
            "bats_path_is_inside is not a defined function after sourcing; got %r"
            % proc.stdout
        )

    # --------------------------------------------------------------------- L2

    def test_nested_path_is_inside(self):
        """L2: a straightforward nested path is inside its base (rc 0)."""
        rc = self._inside_rc("/foo/bar", "/foo")
        assert rc == 0, "/foo/bar should be inside /foo, rc=%d" % rc

    def test_path_is_inside_itself(self):
        """L2: a path is inside itself (rc 0)."""
        rc = self._inside_rc("/foo", "/foo")
        assert rc == 0, "/foo should be inside /foo (a path contains itself), rc=%d" % rc

    def test_segment_boundary_not_raw_prefix(self):
        """L2: the killer discriminator -- containment is by whole segments, not by
        raw string prefix. `/foobar` is NOT inside `/foo`, even though "/foo" is a
        literal string prefix of "/foobar". A naive prefix-only implementation fails
        here."""
        rc = self._inside_rc("/foobar", "/foo")
        assert rc != 0, (
            "/foobar must NOT be inside /foo (segment boundary, not raw prefix); rc=%d"
            % rc
        )
        # control: the same base does contain the genuinely-nested sibling
        assert self._inside_rc("/foo/bar", "/foo") == 0, (
            "/foo/bar must be inside /foo (control for the boundary case)"
        )

    def test_trailing_slash_on_candidate_ignored(self):
        """L2: a trailing slash on the candidate must not change the answer."""
        rc = self._inside_rc("/foo/bar/", "/foo")
        assert rc == 0, "/foo/bar/ should be inside /foo (trailing slash ignored), rc=%d" % rc

    def test_trailing_slash_on_base_ignored(self):
        """L2: a trailing slash on the base must not change the answer."""
        rc = self._inside_rc("/foo/bar", "/foo/")
        assert rc == 0, "/foo/bar should be inside /foo/ (trailing slash on base), rc=%d" % rc
        # and the self-case with mismatched trailing slashes still holds
        assert self._inside_rc("/foo/", "/foo") == 0, "/foo/ should be inside /foo"
        assert self._inside_rc("/foo", "/foo/") == 0, "/foo should be inside /foo/"

    def test_root_contains_every_absolute_path(self):
        """L2: the root `/` is a base that contains every absolute path."""
        assert self._inside_rc("/a/b/c", "/") == 0, "/a/b/c must be inside /"
        assert self._inside_rc("/foo", "/") == 0, "/foo must be inside /"
        assert self._inside_rc("/", "/") == 0, "/ must be inside / (itself)"

    def test_parent_is_not_inside_child(self):
        """L2: a candidate that is a strict PARENT of the base is NOT inside it.
        Containment is directional. A stub that ignores argument order, or that
        only checks shared-prefix in either direction, fails here."""
        rc = self._inside_rc("/foo", "/foo/bar")
        assert rc != 0, "/foo (parent) must NOT be inside /foo/bar (child); rc=%d" % rc

    def test_sibling_and_unrelated_paths_not_inside(self):
        """L2: unrelated or sibling paths sharing no segment lineage are not inside.
        These are not in the doc's explicit list but follow directly from the
        segment-containment contract, and catch an over-permissive implementation."""
        assert self._inside_rc("/bar", "/foo") != 0, "/bar must not be inside /foo"
        assert self._inside_rc("/foo/baz", "/foo/bar") != 0, (
            "/foo/baz must not be inside sibling /foo/bar"
        )
        assert self._inside_rc("/a/bb/c", "/a/b") != 0, (
            "/a/bb/c must not be inside /a/b (second segment differs: bb vs b)"
        )

    def test_deeper_nesting_inside(self):
        """L2: containment holds across multiple levels of nesting, not just one."""
        assert self._inside_rc("/foo/bar/baz/qux", "/foo") == 0, (
            "/foo/bar/baz/qux must be inside /foo"
        )
        assert self._inside_rc("/foo/bar/baz/qux", "/foo/bar/baz") == 0, (
            "/foo/bar/baz/qux must be inside /foo/bar/baz"
        )

    def test_decision_is_pure_string_not_filesystem(self):
        """L2: the decision is made purely from string values; non-existent paths
        must still be classified. We run from a temp cwd and use paths that do not
        exist on disk -- a filesystem-touching implementation would behave
        differently or error."""
        # Both paths are clearly non-existent; the answer must still be 'inside'.
        rc_in = self._inside_rc(
            "/nonexistent_zzz/alpha/beta", "/nonexistent_zzz/alpha"
        )
        assert rc_in == 0, (
            "nested non-existent path must still be judged inside (pure string), rc=%d"
            % rc_in
        )
        rc_out = self._inside_rc("/nonexistent_zzz/alphabeta", "/nonexistent_zzz/alpha")
        assert rc_out != 0, (
            "segment-boundary rule must hold for non-existent paths too; "
            "/nonexistent_zzz/alphabeta is NOT inside /nonexistent_zzz/alpha, rc=%d"
            % rc_out
        )

    def test_answer_via_exit_status_not_stdout(self):
        """L2: the helper must signal its yes/no answer through the exit status, not
        by printing 'true'/'false'/'yes'/'no'/'0'/'1' to stdout."""
        rc_yes, out_yes, _e1 = self._run_inside("/foo/bar", "/foo")
        rc_no, out_no, _e2 = self._run_inside("/foobar", "/foo")
        assert rc_yes == 0 and rc_no != 0, (
            "exit status must encode the answer (yes rc=%d, no rc=%d)" % (rc_yes, rc_no)
        )
        for token in ("true", "false", "yes", "no"):
            assert token not in out_yes.strip().lower(), (
                "helper must not print the answer (saw %r in stdout)" % out_yes
            )
            assert token not in out_no.strip().lower(), (
                "helper must not print the answer (saw %r in stdout)" % out_no
            )

    def test_existing_helpers_unchanged(self):
        """L2: pre-existing helpers in common.bash still behave correctly after the
        edit. Spot-check bats_version_lt's documented tri-state (0=lt, 1=gt, 2=eq)
        and bats_approx_realpath's `/./` collapse so a solution that mangles shared
        code in the same file is caught."""
        script = (
            "set +e\n"
            "source '%s'\n"
            "( bats_version_lt 1.0.0 2.0.0 ); echo \"LT=$?\"\n"
            "( bats_version_lt 2.0.0 1.0.0 ); echo \"GT=$?\"\n"
            "( bats_version_lt 1.0.0 1.0.0 ); echo \"EQ=$?\"\n"
            "out=''\n"
            "bats_approx_realpath out /a/./b\n"
            'echo "RP=$out"\n' % self.COMMON_BASH
        )
        proc = subprocess.run(
            ["bash", "-c", script],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert "LT=0" in proc.stdout, "bats_version_lt 1.0.0<2.0.0 must return 0"
        assert "GT=1" in proc.stdout, "bats_version_lt 2.0.0>1.0.0 must return 1"
        assert "EQ=2" in proc.stdout, "bats_version_lt 1.0.0==1.0.0 must return 2"
        assert "RP=/a/b" in proc.stdout, (
            "bats_approx_realpath must still collapse /a/./b -> /a/b; got %r"
            % proc.stdout
        )

    def test_native_new_test_block_passes(self):
        """L2: the agent's new `@test bats_path_is_inside` passes under the real bats
        runner (filtered to just that block)."""
        proc = subprocess.run(
            [self.BATS_BIN, "--filter", "bats_path_is_inside", "test/common.bats"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "native run of `bats --filter bats_path_is_inside test/common.bats` "
            "failed (rc=%d):\n%s" % (proc.returncode, out)
        )
        assert re.search(r"(?m)^ok \d+ bats_path_is_inside\b", out), (
            "new @test bats_path_is_inside did not run/pass under bats:\n%s" % out
        )

    def test_native_full_common_bats_suite_passes(self):
        """L2: the full acceptance command `bin/bats test/common.bats` exits 0 with
        every test (the 9 pre-existing + the new one) passing."""
        proc = subprocess.run(
            [self.BATS_BIN, "test/common.bats"],
            cwd=self.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, (
            "`bin/bats test/common.bats` must exit 0; rc=%d\n%s"
            % (proc.returncode, out)
        )
        assert "bats_path_is_inside" in out, (
            "the new test must appear in the suite output:\n%s" % out
        )
        assert "not ok" not in out, "no test in the suite may fail:\n%s" % out
        oks = re.findall(r"(?m)^ok \d+ ", out)
        assert len(oks) >= 10, (
            "expected >=10 passing tests in common.bats (9 existing + new), saw %d:\n%s"
            % (len(oks), out)
        )
