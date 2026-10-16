"""Tests for the ``viper-configuration`` skill.

The task asks the agent to add a self-contained settings-loader package at
``internal/serveconfig`` for the Hugo server runtime. The loader resolves a
fixed set of server settings from four layered sources with a strict
precedence: programmatic override > environment variable (HUGO_ prefix) >
config file > built-in default. Nested (``render.to_disk`` /
``render.cache_dir``) and underscore-named (``live_reload_port``) keys must
resolve correctly, missing config files must not error, and unparseable
present files must error.

Verification strategy
---------------------
L1 checks the deliverable files exist and are minimally well-formed, and that
the viper dependency was wired into ``go.mod``.

L2 does NOT trust the agent's own ``serveconfig_test.go``. Instead each L2
method writes an *independent* Go test (under a fresh temp package directory
inside the repo) that imports ``github.com/gohugoio/hugo/internal/serveconfig``
and calls ``serveconfig.Load`` with controlled overrides / env / config files,
then runs ``go test`` on that driver. The driver asserts on the exact resolved
values mandated by each requirement scenario. A stubbed / hardcoded / keyword
solution therefore cannot pass.
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
PKG_DIR = os.path.join(REPO_DIR, "internal", "serveconfig")
MODULE = "github.com/gohugoio/hugo"
IMPORT_PATH = MODULE + "/internal/serveconfig"


@pytest.fixture(scope="module", autouse=True)
def _prepare_deps():
    """Ensure module dependencies (including viper) are downloaded once."""
    ensure_go_dependencies(REPO_DIR)
    # Best-effort tidy so a freshly added viper import is fetched.
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

    Using a dedicated directory (its own package) keeps us isolated from
    whatever the agent put in serveconfig_test.go, while still living inside
    the repo module so the import path resolves.
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
        # Clean up so repeated runs and the agent's own go test are unaffected.
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
    '\tserveconfig "' + IMPORT_PATH + '"\n'
    ')\n\n'
)


def _write_cfg(tmp_subname, body):
    """Return Go code that writes a config file into a temp dir at runtime.

    The body is the file content; we use a .toml extension which viper
    recognizes. Returns a Go snippet creating variable ``cfgPath``.
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
        """L1: the new internal/serveconfig package directory exists."""
        assert os.path.isdir(PKG_DIR), f"missing package dir {PKG_DIR}"

    def test_loader_source_file_exists(self):
        """L1: serveconfig.go exists, is non-trivial, and is in the right package."""
        path = os.path.join(PKG_DIR, "serveconfig.go")
        assert os.path.isfile(path), "serveconfig.go not created"
        with open(path) as fh:
            content = fh.read()
        assert len(content.strip()) > 100, "serveconfig.go looks empty/stub"
        assert "package serveconfig" in content, "wrong package declaration"

    def test_agent_test_file_exists(self):
        """L1: the agent's own deterministic unit test file exists."""
        path = os.path.join(PKG_DIR, "serveconfig_test.go")
        assert os.path.isfile(path), "serveconfig_test.go not created"

    def test_viper_dependency_wired_in(self):
        """L1: a viper dependency was added to go.mod (the loader's backbone)."""
        gomod = os.path.join(REPO_DIR, "go.mod")
        assert os.path.isfile(gomod)
        with open(gomod) as fh:
            mod = fh.read().lower()
        assert "viper" in mod, "viper dependency not present in go.mod"

    def test_package_compiles_and_exports_api(self):
        """L1->L2: package builds and exports Settings, Options, Load with the
        documented signatures (vet via a tiny compile-only driver)."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tvar _ serveconfig.Settings
            \tvar _ serveconfig.Options
            \ts, err := serveconfig.Load(serveconfig.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Load returned error on empty options: %v", err)
            \t}
            \tif s == nil {
            \t\tt.Fatalf("Load returned nil settings")
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "package failed to compile / missing exported API "
            f"(Settings/Options/Load).\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    # ---------------------------------------------------------------- L2 ----

    def test_defaults_when_nothing_supplied(self):
        """L2: no override / env / file -> every default from the table."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \ts, err := serveconfig.Load(serveconfig.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Load: %v", err)
            \t}
            \tif s.Port != 1313 {
            \t\tt.Errorf("port: got %d want 1313", s.Port)
            \t}
            \tif s.Bind != "127.0.0.1" {
            \t\tt.Errorf("bind: got %q want 127.0.0.1", s.Bind)
            \t}
            \tif s.LiveReloadPort != -1 {
            \t\tt.Errorf("live_reload_port: got %d want -1", s.LiveReloadPort)
            \t}
            \tif s.Environment != "development" {
            \t\tt.Errorf("environment: got %q want development", s.Environment)
            \t}
            \tif s.Render.ToDisk != false {
            \t\tt.Errorf("render.to_disk: got %v want false", s.Render.ToDisk)
            \t}
            \tif s.Render.CacheDir != "" {
            \t\tt.Errorf("render.cache_dir: got %q want empty", s.Render.CacheDir)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"defaults scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_env_namespaced_under_hugo(self):
        """L2: HUGO_PORT / HUGO_BIND override defaults; a bare PORT is ignored."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tt.Setenv("PORT", "9999")           // bare, must be ignored
            \tt.Setenv("HUGO_PORT", "8080")
            \tt.Setenv("HUGO_BIND", "0.0.0.0")
            \ts, err := serveconfig.Load(serveconfig.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Load: %v", err)
            \t}
            \tif s.Port != 8080 {
            \t\tt.Errorf("HUGO_PORT not applied: got %d want 8080", s.Port)
            \t}
            \tif s.Bind != "0.0.0.0" {
            \t\tt.Errorf("HUGO_BIND not applied: got %q want 0.0.0.0", s.Bind)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"env namespacing scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_env_underscore_and_nested_keys(self):
        """L2: HUGO_LIVE_RELOAD_PORT and HUGO_RENDER_TO_DISK reach the
        underscore top-level and nested settings respectively."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tt.Setenv("HUGO_LIVE_RELOAD_PORT", "443")
            \tt.Setenv("HUGO_RENDER_TO_DISK", "true")
            \ts, err := serveconfig.Load(serveconfig.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Load: %v", err)
            \t}
            \tif s.LiveReloadPort != 443 {
            \t\tt.Errorf("live_reload_port via env: got %d want 443", s.LiveReloadPort)
            \t}
            \tif s.Render.ToDisk != true {
            \t\tt.Errorf("render.to_disk via env: got %v want true", s.Render.ToDisk)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"underscore/nested env scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_config_file_only(self):
        """L2: a value supplied only by the config file is used (bind + nested
        render.cache_dir read from a TOML file)."""
        cfg = _write_cfg(
            "config.toml",
            'bind = "10.0.0.5"\n\n[render]\ncache_dir = "/var/hugo-cache"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\ts, err := serveconfig.Load(serveconfig.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tif s.Bind != "10.0.0.5" {\n'
            '\t\tt.Errorf("bind from file: got %q want 10.0.0.5", s.Bind)\n'
            '\t}\n'
            '\tif s.Render.CacheDir != "/var/hugo-cache" {\n'
            '\t\tt.Errorf("render.cache_dir from file: got %q want /var/hugo-cache", s.Render.CacheDir)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "config-file-only scenario failed. (Note: Options must expose a "
            "config-file path field; the test uses `ConfigFile`.)\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_env_beats_file(self):
        """L2: file sets port, env sets HUGO_PORT, no override -> env wins."""
        cfg = _write_cfg("config.toml", "port = 2000\n")
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tt.Setenv("HUGO_PORT", "3000")\n'
            + cfg +
            '\ts, err := serveconfig.Load(serveconfig.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tif s.Port != 3000 {\n'
            '\t\tt.Errorf("env should beat file: got %d want 3000", s.Port)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"env-beats-file precedence failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_override_beats_everything(self):
        """L2: file sets port, env sets HUGO_PORT, override sets port -> the
        override wins for port; render.cache_dir still comes from the file."""
        cfg = _write_cfg(
            "config.toml",
            'port = 2000\n\n[render]\ncache_dir = "/file/cache"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tt.Setenv("HUGO_PORT", "3000")\n'
            + cfg +
            '\topts := serveconfig.Options{ConfigFile: cfgPath}\n'
            '\topts.Overrides = map[string]any{"port": 4000}\n'
            '\ts, err := serveconfig.Load(opts)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tif s.Port != 4000 {\n'
            '\t\tt.Errorf("override should win: got %d want 4000", s.Port)\n'
            '\t}\n'
            '\tif s.Render.CacheDir != "/file/cache" {\n'
            '\t\tt.Errorf("render.cache_dir from file: got %q want /file/cache", s.Render.CacheDir)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        # Overrides field name may vary; if the field is genuinely absent the
        # compile fails. Treat that as a real failure since the requirement
        # mandates a programmatic override layer via Options.
        assert proc.returncode == 0, (
            "override-precedence scenario failed. Options must carry a "
            "programmatic override (the test uses `Overrides map[string]any`).\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_missing_config_file_is_not_an_error(self):
        """L2: a path to a nonexistent file -> Load succeeds with defaults/env."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tt.Setenv("HUGO_BIND", "192.168.1.1")
            \tmissing := filepath.Join(t.TempDir(), "does-not-exist.toml")
            \ts, err := serveconfig.Load(serveconfig.Options{ConfigFile: missing})
            \tif err != nil {
            \t\tt.Fatalf("missing config file must not error, got: %v", err)
            \t}
            \tif s.Port != 1313 {
            \t\tt.Errorf("default port lost: got %d want 1313", s.Port)
            \t}
            \tif s.Bind != "192.168.1.1" {
            \t\tt.Errorf("env still applied: got %q want 192.168.1.1", s.Bind)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"missing-file scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_unparseable_config_file_errors(self):
        """L2: a present but malformed config file -> Load returns non-nil error."""
        # Deliberately broken TOML.
        cfg = _write_cfg("config.toml", 'port = = = "not valid toml [[[\n')
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\t_, err := serveconfig.Load(serveconfig.Options{ConfigFile: cfgPath})\n'
            '\tif err == nil {\n'
            '\t\tt.Fatalf("unparseable config file must return an error, got nil")\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"unparseable-file scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_isolation_between_loads(self):
        """L2: repeated Load calls do not leak state. Set env for one Load,
        clear it for a second Load in the same process and confirm the second
        reflects the new environment (defaults), not the first call's value."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \t// First load with an env override.
            \tt.Setenv("HUGO_PORT", "7777")
            \ts1, err := serveconfig.Load(serveconfig.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Load #1: %v", err)
            \t}
            \tif s1.Port != 7777 {
            \t\tt.Fatalf("load #1 port: got %d want 7777", s1.Port)
            \t}
            \t// Clear the env and load again; must fall back to default, not
            \t// reuse leaked state from load #1.
            \tos.Unsetenv("HUGO_PORT")
            \ts2, err := serveconfig.Load(serveconfig.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Load #2: %v", err)
            \t}
            \tif s2.Port != 1313 {
            \t\tt.Errorf("state leaked between Load calls: got %d want default 1313", s2.Port)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"isolation scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_native_acceptance_command_passes(self):
        """L2: the exact acceptance command runs green:
        ``go test ./internal/serveconfig/`` (the agent's own tests)."""
        proc = subprocess.run(
            ["go", "test", "-count=1", "./internal/serveconfig/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command `go test ./internal/serveconfig/` failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
