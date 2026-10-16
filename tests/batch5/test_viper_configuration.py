"""Tests for the ``viper-configuration`` skill (variant ext5).

The task asks the agent to add a self-contained, **flag-bound** build-settings
resolver package at ``internal/buildsettings`` for Hugo. Unlike the ext1
variant (a server-config ``Load`` with a programmatic-override layer), this
variant exposes:

    Resolve(flags *pflag.FlagSet, opts Options) (*BuildSettings, error)

The caller supplies a ``*pflag.FlagSet`` defining the dash-named flags
``minify`` / ``base-url`` / ``gc`` / ``cache-dir``. The resolver binds those
flags to the underscore/short setting keys ``minify`` / ``base_url`` / ``gc``
/ ``cache_dir`` and resolves each setting with the strict precedence:

    explicitly-set flag > env var (HUGOBUILD_ prefix) > config file > default

A flag that was NOT explicitly set must NOT override env/file. Environment
lookups are namespaced under ``HUGOBUILD_`` (a bare ``MINIFY`` is ignored).
Each call must build its own state — no leakage between calls.

Verification strategy
---------------------
L1 checks the deliverable files exist and are minimally well-formed, and that
the resolver dependency (viper) was wired into ``go.mod``.

L2 does NOT trust the agent's own ``buildsettings_test.go``. Instead each L2
method writes an *independent* Go driver (in a fresh temp sub-package inside
the repo module) that imports
``github.com/gohugoio/hugo/internal/buildsettings`` plus ``spf13/pflag``,
constructs its own flag set, sets env via ``t.Setenv``, optionally writes a
config file, calls ``buildsettings.Resolve`` and asserts the exact resolved
values mandated by each requirement scenario. A stubbed / hardcoded /
flag-ignoring / precedence-broken solution therefore cannot pass.
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
PKG_DIR = os.path.join(REPO_DIR, "internal", "buildsettings")
MODULE = "github.com/gohugoio/hugo"
IMPORT_PATH = MODULE + "/internal/buildsettings"


@pytest.fixture(scope="module", autouse=True)
def _prepare_deps():
    """Ensure module dependencies (including viper/pflag) are downloaded once."""
    ensure_go_dependencies(REPO_DIR)
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
    put in buildsettings_test.go, while still living inside the repo module so
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


# Common preamble imported by every driver. We build our own flag sets so we
# fully control which flags are "explicitly set".
_PREAMBLE = (
    'import (\n'
    '\t"os"\n'
    '\t"path/filepath"\n'
    '\t"testing"\n\n'
    '\t"github.com/spf13/pflag"\n'
    '\tbuildsettings "' + IMPORT_PATH + '"\n'
    ')\n\n'
    '// newFlags returns a fresh FlagSet defining the four build flags with\n'
    '// their default values. Nothing is marked as "changed" until Set is\n'
    '// explicitly called by the test.\n'
    'func newFlags() *pflag.FlagSet {\n'
    '\tfs := pflag.NewFlagSet("build", pflag.ContinueOnError)\n'
    '\tfs.Bool("minify", false, "")\n'
    '\tfs.String("base-url", "", "")\n'
    '\tfs.Bool("gc", false, "")\n'
    '\tfs.String("cache-dir", "", "")\n'
    '\treturn fs\n'
    '}\n\n'
)


def _write_cfg(tmp_subname, body):
    """Return Go code that writes a config file into a temp dir at runtime."""
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
        """L1: the new internal/buildsettings package directory exists."""
        assert os.path.isdir(PKG_DIR), f"missing package dir {PKG_DIR}"

    def test_resolver_source_file_exists(self):
        """L1: buildsettings.go exists, is non-trivial, in the right package."""
        path = os.path.join(PKG_DIR, "buildsettings.go")
        assert os.path.isfile(path), "buildsettings.go not created"
        with open(path) as fh:
            content = fh.read()
        assert len(content.strip()) > 100, "buildsettings.go looks empty/stub"
        assert "package buildsettings" in content, "wrong package declaration"

    def test_agent_test_file_exists(self):
        """L1: the agent's own deterministic unit test file exists."""
        path = os.path.join(PKG_DIR, "buildsettings_test.go")
        assert os.path.isfile(path), "buildsettings_test.go not created"

    def test_resolver_dependency_wired_in(self):
        """L1: a viper dependency was added to go.mod (the resolver backbone)."""
        gomod = os.path.join(REPO_DIR, "go.mod")
        assert os.path.isfile(gomod)
        with open(gomod) as fh:
            mod = fh.read().lower()
        assert "viper" in mod, "viper dependency not present in go.mod"

    def test_package_compiles_and_exports_api(self):
        """L1->L2: package builds and exports BuildSettings, Options, and a
        Resolve(*pflag.FlagSet, Options) (*BuildSettings, error) with the
        documented signature. Driven via a tiny compile+run driver."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tvar _ buildsettings.BuildSettings
            \tvar _ buildsettings.Options
            \tfs := newFlags()
            \ts, err := buildsettings.Resolve(fs, buildsettings.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Resolve returned error on empty options: %v", err)
            \t}
            \tif s == nil {
            \t\tt.Fatalf("Resolve returned nil settings")
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "package failed to compile / missing exported API "
            "(BuildSettings/Options/Resolve with the *pflag.FlagSet signature)."
            f"\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    # ---------------------------------------------------------------- L2 ----

    def test_defaults_when_nothing_supplied(self):
        """L2: default flag values, no env, no file -> every default from the
        table (Minify=false, BaseURL="", GC=false, CacheDir="")."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tfs := newFlags()
            \ts, err := buildsettings.Resolve(fs, buildsettings.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Resolve: %v", err)
            \t}
            \tif s.Minify != false {
            \t\tt.Errorf("minify default: got %v want false", s.Minify)
            \t}
            \tif s.BaseURL != "" {
            \t\tt.Errorf("base_url default: got %q want empty", s.BaseURL)
            \t}
            \tif s.GC != false {
            \t\tt.Errorf("gc default: got %v want false", s.GC)
            \t}
            \tif s.CacheDir != "" {
            \t\tt.Errorf("cache_dir default: got %q want empty", s.CacheDir)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"defaults scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_explicit_flag_overrides_env(self):
        """L2: --minify explicitly set true while HUGOBUILD_MINIFY=false ->
        flag wins (Minify == true). A naive impl that reads env first, or never
        binds the flag, fails here."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tt.Setenv("HUGOBUILD_MINIFY", "false")
            \tfs := newFlags()
            \tif err := fs.Set("minify", "true"); err != nil {
            \t\tt.Fatalf("set minify: %v", err)
            \t}
            \ts, err := buildsettings.Resolve(fs, buildsettings.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Resolve: %v", err)
            \t}
            \tif s.Minify != true {
            \t\tt.Errorf("explicit flag must beat env: got %v want true", s.Minify)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"flag>env precedence failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_unset_flag_does_not_override_env(self):
        """L2: --base-url NOT explicitly set, HUGOBUILD_BASE_URL set, file sets
        base_url -> env beats file AND the un-set flag's zero default must not
        clobber it (BaseURL == env value). Catches the common bug of always
        binding the flag's current value even when unchanged."""
        cfg = _write_cfg("settings.toml", 'base_url = "https://file.example"\n')
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tt.Setenv("HUGOBUILD_BASE_URL", "https://env.example")\n'
            + cfg +
            '\tfs := newFlags() // base-url left at default, NOT Set\n'
            '\ts, err := buildsettings.Resolve(fs, buildsettings.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Resolve: %v", err)\n'
            '\t}\n'
            '\tif s.BaseURL != "https://env.example" {\n'
            '\t\tt.Errorf("env should beat file and unset flag must not override: got %q want https://env.example", s.BaseURL)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "unset-flag / env>file precedence failed. (Note: Options must "
            "expose a config-file path field; the test uses `ConfigFile`.)\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_file_only_value_is_used(self):
        """L2: --base-url not set, no env, file sets base_url -> BaseURL comes
        from the file (file beats default)."""
        cfg = _write_cfg("settings.toml", 'base_url = "https://file.example"\n')
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tfs := newFlags()\n'
            '\ts, err := buildsettings.Resolve(fs, buildsettings.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Resolve: %v", err)\n'
            '\t}\n'
            '\tif s.BaseURL != "https://file.example" {\n'
            '\t\tt.Errorf("base_url from file: got %q want https://file.example", s.BaseURL)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"file-only scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_dash_flag_maps_to_underscore_key_cache_dir(self):
        """L2: --cache-dir explicitly set -> CacheDir resolved regardless of
        env/file. Verifies the dash-named flag (cache-dir) maps to the
        underscore key (cache_dir) and that the flag wins over both layers."""
        cfg = _write_cfg("settings.toml", 'cache_dir = "/file/cache"\n')
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tt.Setenv("HUGOBUILD_CACHE_DIR", "/env/cache")\n'
            + cfg +
            '\tfs := newFlags()\n'
            '\tif err := fs.Set("cache-dir", "/tmp/c"); err != nil {\n'
            '\t\tt.Fatalf("set cache-dir: %v", err)\n'
            '\t}\n'
            '\ts, err := buildsettings.Resolve(fs, buildsettings.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Resolve: %v", err)\n'
            '\t}\n'
            '\tif s.CacheDir != "/tmp/c" {\n'
            '\t\tt.Errorf("cache-dir flag should map to cache_dir and win: got %q want /tmp/c", s.CacheDir)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"dash->underscore mapping / flag-precedence failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_env_namespaced_under_hugobuild(self):
        """L2: HUGOBUILD_BASE_URL is honored but a bare MINIFY must be ignored.
        Catches resolvers that don't set the HUGOBUILD env prefix."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tt.Setenv("MINIFY", "true")                       // bare, must be ignored
            \tt.Setenv("HUGOBUILD_BASE_URL", "https://ns.example")
            \tfs := newFlags()
            \ts, err := buildsettings.Resolve(fs, buildsettings.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Resolve: %v", err)
            \t}
            \tif s.BaseURL != "https://ns.example" {
            \t\tt.Errorf("HUGOBUILD_BASE_URL not applied: got %q want https://ns.example", s.BaseURL)
            \t}
            \tif s.Minify != false {
            \t\tt.Errorf("bare MINIFY must be ignored: got %v want false", s.Minify)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"env-namespacing scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_env_beats_file_for_bool_gc(self):
        """L2: file sets gc=false, env HUGOBUILD_GC=true, flag not set -> env
        wins (GC == true). Exercises the bool path of env>file precedence."""
        cfg = _write_cfg("settings.toml", "gc = false\n")
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tt.Setenv("HUGOBUILD_GC", "true")\n'
            + cfg +
            '\tfs := newFlags()\n'
            '\ts, err := buildsettings.Resolve(fs, buildsettings.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Resolve: %v", err)\n'
            '\t}\n'
            '\tif s.GC != true {\n'
            '\t\tt.Errorf("env should beat file for gc: got %v want true", s.GC)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"env-beats-file (gc) scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_full_precedence_chain_independent_settings(self):
        """L2: in one Resolve, drive each layer for a different setting:
        flag(minify) > env(base_url) > file(cache_dir) > default(gc). Confirms
        the four layers coexist correctly and don't bleed across keys."""
        cfg = _write_cfg(
            "settings.toml",
            'cache_dir = "/file/cache"\nbase_url = "https://file.example"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tt.Setenv("HUGOBUILD_BASE_URL", "https://env.example")\n'
            + cfg +
            '\tfs := newFlags()\n'
            '\tif err := fs.Set("minify", "true"); err != nil {\n'
            '\t\tt.Fatalf("set minify: %v", err)\n'
            '\t}\n'
            '\ts, err := buildsettings.Resolve(fs, buildsettings.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Resolve: %v", err)\n'
            '\t}\n'
            '\tif s.Minify != true {\n'
            '\t\tt.Errorf("minify (flag layer): got %v want true", s.Minify)\n'
            '\t}\n'
            '\tif s.BaseURL != "https://env.example" {\n'
            '\t\tt.Errorf("base_url (env layer beats file): got %q want https://env.example", s.BaseURL)\n'
            '\t}\n'
            '\tif s.CacheDir != "/file/cache" {\n'
            '\t\tt.Errorf("cache_dir (file layer): got %q want /file/cache", s.CacheDir)\n'
            '\t}\n'
            '\tif s.GC != false {\n'
            '\t\tt.Errorf("gc (default layer): got %v want false", s.GC)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"full precedence-chain scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_isolation_between_resolves(self):
        """L2: each call builds its own state. Resolve once with --minify set,
        then again with a fresh unset flag set and the env cleared; the second
        must fall back to default (false), proving no leaked viper/global
        state between calls."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \t// First resolve with the flag explicitly set true.
            \tfs1 := newFlags()
            \tif err := fs1.Set("minify", "true"); err != nil {
            \t\tt.Fatalf("set minify: %v", err)
            \t}
            \ts1, err := buildsettings.Resolve(fs1, buildsettings.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Resolve #1: %v", err)
            \t}
            \tif s1.Minify != true {
            \t\tt.Fatalf("resolve #1 minify: got %v want true", s1.Minify)
            \t}
            \t// Second resolve with a brand-new, untouched flag set.
            \tfs2 := newFlags()
            \ts2, err := buildsettings.Resolve(fs2, buildsettings.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Resolve #2: %v", err)
            \t}
            \tif s2.Minify != false {
            \t\tt.Errorf("state leaked between Resolve calls: got %v want default false", s2.Minify)
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
        ``go test ./internal/buildsettings/`` (the agent's own tests)."""
        proc = subprocess.run(
            ["go", "test", "-count=1", "./internal/buildsettings/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command `go test ./internal/buildsettings/` failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
