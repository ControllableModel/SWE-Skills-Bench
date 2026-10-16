"""Tests for the ``viper-configuration`` skill (variant ext8).

The task asks the agent to add a self-contained cache-TTL configuration
loader package at ``internal/cachettl`` for Hugo. The loader reads per-cache
settings keyed under ``caches`` and decodes human-readable duration strings
(``"10m"``, ``"1h30m"``, ``"24h"``, ``"-1"``) into typed ``time.Duration``
values. Concretely it must expose:

  - ``CacheConfig`` with field ``Caches map[string]CacheEntry`` (key ``caches``)
  - ``CacheEntry`` with ``MaxAge time.Duration`` (key ``max_age``) and
    ``Dir string`` (key ``dir``)
  - ``Options`` carrying at least an optional config-file path
  - ``Load(opts Options) (*CacheConfig, error)``

Required semantics:
  - duration strings decode to the matching ``time.Duration``; ``"-1"`` ->
    ``time.Duration(-1)``; ``"0"`` -> zero duration.
  - per-cache env overrides resolve under the ``HUGOCACHE_`` prefix, e.g.
    ``HUGOCACHE_CACHES_ASSETS_MAX_AGE``.
  - a missing/absent config file is NOT an error (empty cache set returned);
    a present-but-unparseable file IS an error.
  - each ``Load`` builds its own state; calls do not leak between each other.

Verification strategy
---------------------
L1 checks the deliverable files exist, are minimally well-formed, are in the
right package, and that a config-decoding dependency was wired into ``go.mod``.

L2 does NOT trust the agent's own ``cachettl_test.go``. Each L2 method writes
an *independent* Go test driver into a fresh temporary sub-package inside the
repo, imports ``github.com/gohugoio/hugo/internal/cachettl``, calls
``cachettl.Load`` with controlled config files / env, and asserts on the exact
resolved ``time.Duration`` / ``Dir`` values mandated by each requirement
scenario. A stubbed / hardcoded / keyword-matching solution cannot pass:
e.g. a loader that ignores ``max_age``, fails to decode duration strings, does
not special-case ``"-1"``, or ignores the ``HUGOCACHE_`` env prefix will be
caught by a discriminative scenario. The final method runs the exact native
acceptance command ``go test ./internal/cachettl/``.
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
PKG_DIR = os.path.join(REPO_DIR, "internal", "cachettl")
MODULE = "github.com/gohugoio/hugo"
IMPORT_PATH = MODULE + "/internal/cachettl"


@pytest.fixture(scope="module", autouse=True)
def _prepare_deps():
    """Ensure module dependencies (including the config lib) are downloaded."""
    ensure_go_dependencies(REPO_DIR)
    # Best-effort tidy so a freshly added import is fetched.
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
    whatever the agent put in cachettl_test.go, while still living inside the
    repo module so the import path resolves.
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
    '\t"testing"\n'
    '\t"time"\n\n'
    '\tcachettl "' + IMPORT_PATH + '"\n'
    ')\n\n'
    '// silence unused imports across drivers that do not use them all.\n'
    'var _ = os.Getenv\n'
    'var _ = filepath.Join\n'
    'var _ = time.Second\n\n'
)


def _write_cfg(filename, body):
    """Return Go code that writes a config file into a temp dir at runtime.

    The body is the file content; a ``.toml`` extension is used which config
    decoders recognize. Produces variable ``cfgPath``.
    """
    escaped = body.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return (
        '\tdir := t.TempDir()\n'
        '\tcfgPath := filepath.Join(dir, "' + filename + '")\n'
        '\tif err := os.WriteFile(cfgPath, []byte("' + escaped + '"), 0o644); err != nil {\n'
        '\t\tt.Fatalf("write cfg: %v", err)\n'
        '\t}\n'
    )


class TestViperConfiguration:
    REPO_DIR = _find_repo_dir("/workspace/hugo")

    # ---------------------------------------------------------------- L1 ----

    def test_package_directory_exists(self):
        """L1: the new internal/cachettl package directory exists."""
        assert os.path.isdir(PKG_DIR), f"missing package dir {PKG_DIR}"

    def test_loader_source_file_exists(self):
        """L1: cachettl.go exists, is non-trivial, and is in the right package."""
        path = os.path.join(PKG_DIR, "cachettl.go")
        assert os.path.isfile(path), "cachettl.go not created"
        with open(path) as fh:
            content = fh.read()
        assert len(content.strip()) > 100, "cachettl.go looks empty/stub"
        assert "package cachettl" in content, "wrong package declaration"

    def test_agent_test_file_exists(self):
        """L1: the agent's own deterministic unit test file exists."""
        path = os.path.join(PKG_DIR, "cachettl_test.go")
        assert os.path.isfile(path), "cachettl_test.go not created"

    def test_config_dependency_wired_in(self):
        """L1: a config/decoding dependency was added to go.mod.

        The loader must decode duration strings into time.Duration; that is
        commonly backed by viper / mapstructure. Accept either signal so the
        test does not over-constrain the implementation choice, but require at
        least one config-decoding backbone to be present.
        """
        gomod = os.path.join(REPO_DIR, "go.mod")
        assert os.path.isfile(gomod)
        with open(gomod) as fh:
            mod = fh.read().lower()
        assert ("viper" in mod) or ("mapstructure" in mod), (
            "no config-decoding dependency (viper/mapstructure) found in go.mod"
        )

    def test_package_compiles_and_exports_api(self):
        """L1->L2: package builds and exports CacheConfig, CacheEntry, Options,
        Load with the documented signatures (compile-only driver)."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tvar _ cachettl.CacheConfig
            \tvar _ cachettl.CacheEntry
            \tvar _ cachettl.Options
            \tcfg, err := cachettl.Load(cachettl.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Load returned error on empty options: %v", err)
            \t}
            \tif cfg == nil {
            \t\tt.Fatalf("Load returned nil config")
            \t}
            \t// CacheEntry shape: MaxAge time.Duration, Dir string.
            \tvar e cachettl.CacheEntry
            \tvar _ time.Duration = e.MaxAge
            \tvar _ string = e.Dir
            \t// CacheConfig shape: Caches map[string]CacheEntry.
            \tvar _ map[string]cachettl.CacheEntry = cfg.Caches
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "package failed to compile / missing exported API "
            "(CacheConfig{Caches map[string]CacheEntry}, "
            "CacheEntry{MaxAge time.Duration, Dir string}, Options, Load).\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    # ---------------------------------------------------------------- L2 ----

    def test_empty_when_nothing_supplied(self):
        """L2: no file / no env -> Load succeeds with an empty cache set."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tcfg, err := cachettl.Load(cachettl.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Load: %v", err)
            \t}
            \tif len(cfg.Caches) != 0 {
            \t\tt.Errorf("expected empty cache set, got %d entries: %v", len(cfg.Caches), cfg.Caches)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"empty-config scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_duration_string_minutes(self):
        """L2: caches.assets.max_age "10m" -> MaxAge == 10*time.Minute.

        A naive loader that treats max_age as an integer count, drops it, or
        hardcodes a value cannot satisfy this exact Duration.
        """
        cfg = _write_cfg(
            "cache.toml",
            '[caches]\n[caches.assets]\nmax_age = "10m"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tc, err := cachettl.Load(cachettl.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tgot := c.Caches["assets"].MaxAge\n'
            '\tif got != 10*time.Minute {\n'
            '\t\tt.Errorf("assets max_age: got %v want %v", got, 10*time.Minute)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "10m duration decoding failed. (Note: Options must expose a "
            "config-file path field; the test uses `ConfigFile`.)\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_duration_string_compound(self):
        """L2: caches.images.max_age "1h30m" -> 90*time.Minute (compound dur)."""
        cfg = _write_cfg(
            "cache.toml",
            '[caches]\n[caches.images]\nmax_age = "1h30m"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tc, err := cachettl.Load(cachettl.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tgot := c.Caches["images"].MaxAge\n'
            '\tif got != 90*time.Minute {\n'
            '\t\tt.Errorf("images max_age: got %v want %v", got, 90*time.Minute)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"1h30m compound duration decoding failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_never_expire_minus_one(self):
        """L2: caches.getjson.max_age "-1" -> MaxAge == time.Duration(-1).

        This is the discriminating "never expire" sentinel: a loader that
        decodes "-1" as a generic duration parse would error (Go's
        time.ParseDuration rejects a bare "-1"), so the implementation must
        special-case the sentinel exactly as the requirement mandates.
        """
        cfg = _write_cfg(
            "cache.toml",
            '[caches]\n[caches.getjson]\nmax_age = "-1"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tc, err := cachettl.Load(cachettl.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tgot := c.Caches["getjson"].MaxAge\n'
            '\tif got != time.Duration(-1) {\n'
            '\t\tt.Errorf("getjson max_age (-1 never-expire): got %v want %v", got, time.Duration(-1))\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"-1 never-expire sentinel decoding failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_zero_duration(self):
        """L2: caches.x.max_age "0" -> zero duration (not the -1 sentinel)."""
        cfg = _write_cfg(
            "cache.toml",
            '[caches]\n[caches.misc]\nmax_age = "0"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tc, err := cachettl.Load(cachettl.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tgot := c.Caches["misc"].MaxAge\n'
            '\tif got != time.Duration(0) {\n'
            '\t\tt.Errorf("misc max_age (0): got %v want 0", got)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"zero-duration decoding failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_dir_field_from_file(self):
        """L2: caches.assets.dir "/tmp/a" -> CacheEntry.Dir == "/tmp/a".

        Confirms the Dir string field is wired with the ``dir`` key, separate
        from max_age decoding.
        """
        cfg = _write_cfg(
            "cache.toml",
            '[caches]\n[caches.assets]\nmax_age = "10m"\ndir = "/tmp/a"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tc, err := cachettl.Load(cachettl.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tentry := c.Caches["assets"]\n'
            '\tif entry.Dir != "/tmp/a" {\n'
            '\t\tt.Errorf("assets dir: got %q want /tmp/a", entry.Dir)\n'
            '\t}\n'
            '\tif entry.MaxAge != 10*time.Minute {\n'
            '\t\tt.Errorf("assets max_age alongside dir: got %v want 10m", entry.MaxAge)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"dir-field scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_env_override_hugocache_prefix(self):
        """L2: HUGOCACHE_CACHES_ASSETS_MAX_AGE=5m with no file -> assets MaxAge
        == 5*time.Minute. A bare CACHES_ASSETS_MAX_AGE must be ignored."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tt.Setenv("CACHES_ASSETS_MAX_AGE", "99h")          // bare -> ignored
            \tt.Setenv("HUGOCACHE_CACHES_ASSETS_MAX_AGE", "5m")
            \tc, err := cachettl.Load(cachettl.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Load: %v", err)
            \t}
            \tgot := c.Caches["assets"].MaxAge
            \tif got != 5*time.Minute {
            \t\tt.Errorf("env-override assets max_age: got %v want %v", got, 5*time.Minute)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "HUGOCACHE_ env-prefix override scenario failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_missing_config_file_is_not_an_error(self):
        """L2: a path to a nonexistent file -> Load succeeds, empty cache set."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tmissing := filepath.Join(t.TempDir(), "does-not-exist.toml")
            \tc, err := cachettl.Load(cachettl.Options{ConfigFile: missing})
            \tif err != nil {
            \t\tt.Fatalf("missing config file must not error, got: %v", err)
            \t}
            \tif len(c.Caches) != 0 {
            \t\tt.Errorf("missing file should yield empty cache set, got %d entries", len(c.Caches))
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
        cfg = _write_cfg("cache.toml", '[caches = = = broken [[[\nmax_age "10m\n')
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\t_, err := cachettl.Load(cachettl.Options{ConfigFile: cfgPath})\n'
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
        """L2: repeated Load calls do not leak state. Load once with an env
        override present, then again with it cleared; the second must reflect
        the new (empty) environment, not the first call's leaked entry."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tt.Setenv("HUGOCACHE_CACHES_ASSETS_MAX_AGE", "7m")
            \tc1, err := cachettl.Load(cachettl.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Load #1: %v", err)
            \t}
            \tif c1.Caches["assets"].MaxAge != 7*time.Minute {
            \t\tt.Fatalf("load #1 assets max_age: got %v want 7m", c1.Caches["assets"].MaxAge)
            \t}
            \tos.Unsetenv("HUGOCACHE_CACHES_ASSETS_MAX_AGE")
            \tc2, err := cachettl.Load(cachettl.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Load #2: %v", err)
            \t}
            \tif _, ok := c2.Caches["assets"]; ok {
            \t\tt.Errorf("state leaked between Load calls: assets still present with %v", c2.Caches["assets"].MaxAge)
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
        ``go test ./internal/cachettl/`` (the agent's own tests)."""
        proc = subprocess.run(
            ["go", "test", "-count=1", "./internal/cachettl/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command `go test ./internal/cachettl/` failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
