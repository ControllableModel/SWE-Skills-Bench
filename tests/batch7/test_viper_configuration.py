"""Tests for the ``viper-configuration`` skill (variant ext7).

Variant task
------------
The agent must add a self-contained *optional security policy loader* package
at ``internal/securitypolicy``. It exposes:

  * an exported ``Policy`` struct decoded from a resolved configuration with
      - ``EnableInlineShortcodes bool``    (key ``enable_inline_shortcodes``,
        default ``false``)
      - nested ``Exec.Allow []string``     (key ``exec.allow``,
        default ``["^go$", "^git$"]``)
      - nested ``HTTP.URLs []string``      (key ``http.urls``,
        default ``[".*"]``)
  * ``Load(path string) (*Policy, error)``.

Semantics (re-derived from THIS variant's requirement doc):
  * ``Load("")`` and ``Load("/does/not/exist")`` succeed and return the
    documented defaults (a missing/unspecified file is NOT an error).
  * a present-but-malformed file -> ``Load`` returns a non-nil error.
  * a present, valid file overrides only the keys it specifies; the nested
    ``exec.allow`` / ``http.urls`` slices and the underscore-named top-level
    field decode correctly.
  * each ``Load`` call builds its own config state; repeated calls must not
    leak/share state.

Verification strategy
---------------------
L1 checks the deliverable files exist, are minimally well-formed, and that a
configuration dependency was wired into ``go.mod``.

L2 does NOT trust the agent's own ``securitypolicy_test.go``. Each L2 method
writes an *independent* Go test driver into a fresh temp sub-package inside the
repo, imports ``github.com/gohugoio/hugo/internal/securitypolicy``, calls
``securitypolicy.Load`` with controlled inputs, and asserts the exact resolved
values mandated by each scenario. A stubbed loader (hardcoded defaults that
ignore the file, a file-existence check that errors on missing files, a parser
that never errors on garbage, or one that loses nested-slice decoding) cannot
pass.
"""

import os
import subprocess
import textwrap
import uuid

import pytest

try:
    from _dependency_utils import ensure_go_dependencies
except Exception:  # pragma: no cover - fallback if util not present
    def ensure_go_dependencies(repo_dir):
        subprocess.run(
            ["go", "mod", "download"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=1800,
        )


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
REPO_DIR = _find_repo_dir("/workspace/hugo")
PKG_DIR = os.path.join(REPO_DIR, "internal", "securitypolicy")
MODULE = "github.com/gohugoio/hugo"
IMPORT_PATH = MODULE + "/internal/securitypolicy"


@pytest.fixture(scope="module", autouse=True)
def _prepare_deps():
    """Ensure module dependencies (including the new config lib) are present."""
    ensure_go_dependencies(REPO_DIR)
    # Best-effort download so a freshly added import is fetched.
    subprocess.run(
        ["go", "mod", "download"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=600,
    )
    yield


def _run_driver(test_source, timeout=600):
    """Write an independent *_test.go driver into a fresh sub-package of the
    repo, run ``go test`` on it, and return the CompletedProcess.

    A dedicated directory (its own package) isolates us from whatever the agent
    put in securitypolicy_test.go, while still living inside the repo module so
    the import path resolves.
    """
    unique = "verify_" + uuid.uuid4().hex[:12]
    driver_dir = os.path.join(PKG_DIR, unique)
    os.makedirs(driver_dir, exist_ok=True)
    test_path = os.path.join(driver_dir, "driver_test.go")
    full = "package " + unique + "\n\n" + test_source
    try:
        with open(test_path, "w") as fh:
            fh.write(full)
        proc = subprocess.run(
            ["go", "test", "-count=1", "-run", "TestDriver", "./..."],
            cwd=driver_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc
    finally:
        try:
            for name in os.listdir(driver_dir):
                os.remove(os.path.join(driver_dir, name))
            os.rmdir(driver_dir)
        except OSError:
            pass


# Common preamble imported by every driver.
_PREAMBLE = (
    'import (\n'
    '\t"os"\n'
    '\t"path/filepath"\n'
    '\t"testing"\n\n'
    '\tsecuritypolicy "' + IMPORT_PATH + '"\n'
    ')\n\n'
)


def _write_cfg(tmp_subname, body):
    """Return Go code that writes a config file (``cfgPath``) into a temp dir at
    runtime. ``body`` is the file content; we use the supplied extension so the
    loader can detect the format.
    """
    escaped = body.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return (
        '\tdir := t.TempDir()\n'
        '\tcfgPath := filepath.Join(dir, "' + tmp_subname + '")\n'
        '\tif err := os.WriteFile(cfgPath, []byte("' + escaped + '"), 0o644); err != nil {\n'
        '\t\tt.Fatalf("write cfg: %v", err)\n'
        '\t}\n'
    )


class TestViperConfiguration:
    REPO_DIR = _find_repo_dir("/workspace/hugo")

    # ---------------------------------------------------------------- L1 ----

    def test_package_directory_exists(self):
        """L1: the new internal/securitypolicy package directory exists."""
        assert os.path.isdir(PKG_DIR), f"missing package dir {PKG_DIR}"

    def test_loader_source_file_exists(self):
        """L1: securitypolicy.go exists, is non-trivial, in the right package."""
        path = os.path.join(PKG_DIR, "securitypolicy.go")
        assert os.path.isfile(path), "securitypolicy.go not created"
        with open(path) as fh:
            content = fh.read()
        assert len(content.strip()) > 100, "securitypolicy.go looks empty/stub"
        assert "package securitypolicy" in content, "wrong package declaration"

    def test_agent_test_file_exists(self):
        """L1: the agent's own deterministic unit test file exists."""
        path = os.path.join(PKG_DIR, "securitypolicy_test.go")
        assert os.path.isfile(path), "securitypolicy_test.go not created"

    def test_config_dependency_wired_in(self):
        """L1: a configuration/decoding dependency was added to go.mod.

        The loader must decode a resolved config (viper/koanf/mapstructure or
        similar). We accept any recognised config-decoding library rather than
        hardcoding one, but require at least one to be present so the loader is
        genuinely backed by a real decoder rather than ad-hoc parsing only.
        """
        gomod = os.path.join(REPO_DIR, "go.mod")
        assert os.path.isfile(gomod)
        with open(gomod) as fh:
            mod = fh.read().lower()
        candidates = ("viper", "koanf", "mapstructure", "yaml", "toml")
        assert any(c in mod for c in candidates), (
            "no config-decoding dependency found in go.mod "
            f"(looked for any of {candidates})"
        )

    def test_package_compiles_and_exports_api(self):
        """L1->L2: package builds and exports Policy + Load with the documented
        signature ``Load(path string) (*Policy, error)`` (compile-only driver)."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tvar _ securitypolicy.Policy
            \tp, err := securitypolicy.Load("")
            \tif err != nil {
            \t\tt.Fatalf("Load(\\"\\") returned error: %v", err)
            \t}
            \tif p == nil {
            \t\tt.Fatalf("Load returned nil policy")
            \t}
            \t// Field access proves the documented shape exists & is typed.
            \tvar _ bool = p.EnableInlineShortcodes
            \tvar _ []string = p.Exec.Allow
            \tvar _ []string = p.HTTP.URLs
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "package failed to compile / missing exported API "
            "(Policy{EnableInlineShortcodes, Exec.Allow, HTTP.URLs} / "
            f"Load(string) (*Policy, error)).\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    # ---------------------------------------------------------------- L2 ----

    def test_empty_path_returns_defaults(self):
        """L2: Load("") succeeds and returns every default from the table.

        A naive loader that errors on a missing file, or that returns an
        empty/zero Policy instead of the documented defaults, fails here.
        """
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tp, err := securitypolicy.Load("")
            \tif err != nil {
            \t\tt.Fatalf("Load(\\"\\") must not error: %v", err)
            \t}
            \tif p.EnableInlineShortcodes != false {
            \t\tt.Errorf("enable_inline_shortcodes default: got %v want false", p.EnableInlineShortcodes)
            \t}
            \tif len(p.Exec.Allow) != 2 || p.Exec.Allow[0] != "^go$" || p.Exec.Allow[1] != "^git$" {
            \t\tt.Errorf("exec.allow default: got %v want [^go$ ^git$]", p.Exec.Allow)
            \t}
            \tif len(p.HTTP.URLs) != 1 || p.HTTP.URLs[0] != ".*" {
            \t\tt.Errorf("http.urls default: got %v want [.*]", p.HTTP.URLs)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"empty-path defaults scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_missing_file_returns_defaults_not_error(self):
        """L2: a path to a nonexistent file is NOT an error; Load returns the
        documented defaults.

        A naive os.Stat/os.Open-then-fail implementation is caught here.
        """
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tmissing := filepath.Join(t.TempDir(), "does-not-exist.yaml")
            \tp, err := securitypolicy.Load(missing)
            \tif err != nil {
            \t\tt.Fatalf("missing file must not error, got: %v", err)
            \t}
            \tif p.EnableInlineShortcodes != false {
            \t\tt.Errorf("missing-file default enable_inline_shortcodes: got %v want false", p.EnableInlineShortcodes)
            \t}
            \tif len(p.Exec.Allow) != 2 || p.Exec.Allow[0] != "^go$" || p.Exec.Allow[1] != "^git$" {
            \t\tt.Errorf("missing-file default exec.allow: got %v want [^go$ ^git$]", p.Exec.Allow)
            \t}
            \tif len(p.HTTP.URLs) != 1 || p.HTTP.URLs[0] != ".*" {
            \t\tt.Errorf("missing-file default http.urls: got %v want [.*]", p.HTTP.URLs)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"missing-file-not-error scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_file_overrides_toplevel_underscore_key(self):
        """L2: a present file that sets ``enable_inline_shortcodes: true``
        resolves EnableInlineShortcodes==true while the unspecified exec.allow
        keeps its default (partial override + underscore-name decoding)."""
        cfg = _write_cfg(
            "policy.yaml",
            "enable_inline_shortcodes: true\n",
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tp, err := securitypolicy.Load(cfgPath)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tif p.EnableInlineShortcodes != true {\n'
            '\t\tt.Errorf("enable_inline_shortcodes from file: got %v want true", p.EnableInlineShortcodes)\n'
            '\t}\n'
            '\t// Unspecified key must keep its default.\n'
            '\tif len(p.Exec.Allow) != 2 || p.Exec.Allow[0] != "^go$" || p.Exec.Allow[1] != "^git$" {\n'
            '\t\tt.Errorf("unspecified exec.allow should keep default: got %v want [^go$ ^git$]", p.Exec.Allow)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "toplevel-underscore-override scenario failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_file_overrides_nested_exec_allow(self):
        """L2: a present file that sets ``exec.allow: ["^npm$"]`` resolves
        Exec.Allow==["^npm$"] (nested slice decoding), while http.urls keeps
        its default.

        A loader that hardcodes the default exec.allow and ignores the file is
        caught here.
        """
        cfg = _write_cfg(
            "policy.yaml",
            "exec:\n  allow:\n    - \"^npm$\"\n",
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tp, err := securitypolicy.Load(cfgPath)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tif len(p.Exec.Allow) != 1 || p.Exec.Allow[0] != "^npm$" {\n'
            '\t\tt.Errorf("exec.allow from file: got %v want [^npm$]", p.Exec.Allow)\n'
            '\t}\n'
            '\t// http.urls not set -> keeps default.\n'
            '\tif len(p.HTTP.URLs) != 1 || p.HTTP.URLs[0] != ".*" {\n'
            '\t\tt.Errorf("unspecified http.urls should keep default: got %v want [.*]", p.HTTP.URLs)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "nested-exec-allow-override scenario failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_file_overrides_nested_http_urls(self):
        """L2: a present file that sets ``http.urls`` resolves the nested
        HTTP.URLs slice (multi-element) while exec.allow keeps its default."""
        cfg = _write_cfg(
            "policy.yaml",
            "http:\n  urls:\n    - \"^https://example.com\"\n    - \"^https://hugo.io\"\n",
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tp, err := securitypolicy.Load(cfgPath)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tif len(p.HTTP.URLs) != 2 || p.HTTP.URLs[0] != "^https://example.com" || p.HTTP.URLs[1] != "^https://hugo.io" {\n'
            '\t\tt.Errorf("http.urls from file: got %v want [^https://example.com ^https://hugo.io]", p.HTTP.URLs)\n'
            '\t}\n'
            '\tif len(p.Exec.Allow) != 2 || p.Exec.Allow[0] != "^go$" || p.Exec.Allow[1] != "^git$" {\n'
            '\t\tt.Errorf("unspecified exec.allow should keep default: got %v want [^go$ ^git$]", p.Exec.Allow)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "nested-http-urls-override scenario failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_unparseable_file_errors(self):
        """L2: a present but malformed config file -> Load returns a non-nil
        error (and not the defaults).

        A loader that swallows parse errors and silently returns defaults is
        caught here.
        """
        # Deliberately broken YAML (bad indentation / unterminated flow).
        cfg = _write_cfg(
            "policy.yaml",
            "exec:\n  allow: [ \"^npm$\"\nhttp: : :\n   - bad\n",
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\t_, err := securitypolicy.Load(cfgPath)\n'
            '\tif err == nil {\n'
            '\t\tt.Fatalf("unparseable file must return an error, got nil")\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "unparseable-file scenario failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_isolation_between_loads(self):
        """L2: repeated Load calls do not share/leak state.

        Load a file that overrides exec.allow, then Load("") again in the same
        process; the second result must be the clean default, not the first
        call's overridden value.
        """
        cfg = _write_cfg(
            "policy.yaml",
            "exec:\n  allow:\n    - \"^deno$\"\n",
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tp1, err := securitypolicy.Load(cfgPath)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load #1: %v", err)\n'
            '\t}\n'
            '\tif len(p1.Exec.Allow) != 1 || p1.Exec.Allow[0] != "^deno$" {\n'
            '\t\tt.Fatalf("load #1 exec.allow: got %v want [^deno$]", p1.Exec.Allow)\n'
            '\t}\n'
            '\tp2, err := securitypolicy.Load("")\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load #2: %v", err)\n'
            '\t}\n'
            '\tif len(p2.Exec.Allow) != 2 || p2.Exec.Allow[0] != "^go$" || p2.Exec.Allow[1] != "^git$" {\n'
            '\t\tt.Errorf("state leaked between loads: got %v want default [^go$ ^git$]", p2.Exec.Allow)\n'
            '\t}\n'
            '\t// And the returned pointers must be distinct instances.\n'
            '\tif p1 == p2 {\n'
            '\t\tt.Errorf("Load returned the same *Policy pointer across calls; state is shared")\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"isolation scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_multikey_file_full_override(self):
        """L2: a present file setting all three keys overrides them all at once
        (top-level underscore bool + both nested slices together)."""
        cfg = _write_cfg(
            "policy.yaml",
            "enable_inline_shortcodes: true\n"
            "exec:\n  allow:\n    - \"^cargo$\"\n    - \"^make$\"\n"
            "http:\n  urls:\n    - \"^https://only.example\"\n",
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tp, err := securitypolicy.Load(cfgPath)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tif p.EnableInlineShortcodes != true {\n'
            '\t\tt.Errorf("enable_inline_shortcodes: got %v want true", p.EnableInlineShortcodes)\n'
            '\t}\n'
            '\tif len(p.Exec.Allow) != 2 || p.Exec.Allow[0] != "^cargo$" || p.Exec.Allow[1] != "^make$" {\n'
            '\t\tt.Errorf("exec.allow: got %v want [^cargo$ ^make$]", p.Exec.Allow)\n'
            '\t}\n'
            '\tif len(p.HTTP.URLs) != 1 || p.HTTP.URLs[0] != "^https://only.example" {\n'
            '\t\tt.Errorf("http.urls: got %v want [^https://only.example]", p.HTTP.URLs)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"multikey-full-override scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_native_acceptance_command_passes(self):
        """L2: the exact acceptance command runs green:
        ``go test ./internal/securitypolicy/`` (the agent's own tests)."""
        proc = subprocess.run(
            ["go", "test", "-count=1", "./internal/securitypolicy/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command `go test ./internal/securitypolicy/` failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
