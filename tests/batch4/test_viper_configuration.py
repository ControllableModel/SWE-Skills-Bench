"""Tests for the ``viper-configuration`` skill (variant ext4).

The task asks the agent to add a self-contained runtime-environment resolver
package at ``internal/runtimeenv`` for the Hugo runtime. Unlike the ext1
variant (a four-layer server settings loader), this variant resolves a fixed
family of *runtime tuning* values **only from HUGO_-prefixed environment
variables layered over built-in defaults** -- there is no config file and no
programmatic override layer. The resolver must:

  * expose an exported struct ``RuntimeEnv`` with fields
    Environment(string, default "production"), NumWorkerMultiplier(int, 0),
    MemoryLimit(int, 0), and a nested ``Cache`` struct with
    Dir(string, "") and MaxAge(int, 0);
  * expose ``Resolve() (*RuntimeEnv, error)``;
  * read every value from a ``HUGO_``-prefixed env var, with underscore
    top-level keys (``num_worker_multiplier`` <- ``HUGO_NUM_WORKER_MULTIPLIER``)
    and nested keys (``cache.dir`` <- ``HUGO_CACHE_DIR``) resolving from their
    flattened forms;
  * ignore bare unprefixed variables (a plain ``ENVIRONMENT`` must NOT count);
  * fall back to the table default for any unset key;
  * build configuration independently on each call (no leaked state).

Verification strategy
---------------------
L1 checks the deliverable files exist and are minimally well-formed, and that
a viper dependency was wired into ``go.mod`` (the env-binding backbone).

L2 does NOT trust the agent's own ``runtimeenv_test.go``. Instead each L2
method writes an *independent* Go test into a fresh temp sub-package inside the
repo that imports ``github.com/gohugoio/hugo/internal/runtimeenv`` and calls
``runtimeenv.Resolve()`` under controlled ``t.Setenv`` conditions, then runs
``go test`` on that driver. The driver asserts on the exact resolved values
mandated by each requirement scenario. A stubbed / hardcoded / env-ignoring /
unprefixed-leaking solution therefore cannot pass. The final method drives the
exact native acceptance command ``go test ./internal/runtimeenv/``.
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
PKG_DIR = os.path.join(REPO_DIR, "internal", "runtimeenv")
MODULE = "github.com/gohugoio/hugo"
IMPORT_PATH = MODULE + "/internal/runtimeenv"


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
    whatever the agent put in runtimeenv_test.go, while still living inside the
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


# Common preamble imported by every driver. We clear any HUGO_-prefixed env
# vars inherited from the surrounding process at the start of each driver so
# scenarios are hermetic, then set only the ones the scenario needs.
_PREAMBLE = (
    'import (\n'
    '\t"os"\n'
    '\t"strings"\n'
    '\t"testing"\n\n'
    '\truntimeenv "' + IMPORT_PATH + '"\n'
    ')\n\n'
    'func clearHugoEnv(t *testing.T) {\n'
    '\tfor _, kv := range os.Environ() {\n'
    '\t\tk := kv[:strings.IndexByte(kv, \'=\')]\n'
    '\t\tif strings.HasPrefix(k, "HUGO_") {\n'
    '\t\t\tt.Setenv(k, "")\n'
    '\t\t\tos.Unsetenv(k)\n'
    '\t\t}\n'
    '\t}\n'
    '}\n\n'
)


class TestViperConfiguration:
    REPO_DIR = _find_repo_dir("/workspace/hugo")

    # ---------------------------------------------------------------- L1 ----

    def test_package_directory_exists(self):
        """L1: the new internal/runtimeenv package directory exists."""
        assert os.path.isdir(PKG_DIR), f"missing package dir {PKG_DIR}"

    def test_resolver_source_file_exists(self):
        """L1: runtimeenv.go exists, is non-trivial, and is in the right package."""
        path = os.path.join(PKG_DIR, "runtimeenv.go")
        assert os.path.isfile(path), "runtimeenv.go not created"
        with open(path) as fh:
            content = fh.read()
        assert len(content.strip()) > 100, "runtimeenv.go looks empty/stub"
        assert "package runtimeenv" in content, "wrong package declaration"

    def test_agent_test_file_exists(self):
        """L1: the agent's own deterministic unit test file exists."""
        path = os.path.join(PKG_DIR, "runtimeenv_test.go")
        assert os.path.isfile(path), "runtimeenv_test.go not created"

    def test_viper_dependency_wired_in(self):
        """L1: a viper dependency was added to go.mod (the env-binding backbone)."""
        gomod = os.path.join(REPO_DIR, "go.mod")
        assert os.path.isfile(gomod)
        with open(gomod) as fh:
            mod = fh.read().lower()
        assert "viper" in mod, "viper dependency not present in go.mod"

    def test_package_compiles_and_exports_api(self):
        """L1->L2: package builds and exports RuntimeEnv (with nested Cache) and
        Resolve with the documented signature (compile-only driver)."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tclearHugoEnv(t)
            \tvar re runtimeenv.RuntimeEnv
            \t// Field access proves the documented shape exists.
            \t_ = re.Environment
            \t_ = re.NumWorkerMultiplier
            \t_ = re.MemoryLimit
            \t_ = re.Cache.Dir
            \t_ = re.Cache.MaxAge
            \tgot, err := runtimeenv.Resolve()
            \tif err != nil {
            \t\tt.Fatalf("Resolve returned error: %v", err)
            \t}
            \tif got == nil {
            \t\tt.Fatalf("Resolve returned nil *RuntimeEnv")
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "package failed to compile / missing exported API "
            "(RuntimeEnv{Environment,NumWorkerMultiplier,MemoryLimit,"
            "Cache{Dir,MaxAge}} / Resolve).\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    # ---------------------------------------------------------------- L2 ----

    def test_defaults_when_nothing_set(self):
        """L2: no HUGO_ env vars -> every default from the table."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tclearHugoEnv(t)
            \tre, err := runtimeenv.Resolve()
            \tif err != nil {
            \t\tt.Fatalf("Resolve: %v", err)
            \t}
            \tif re.Environment != "production" {
            \t\tt.Errorf("environment default: got %q want production", re.Environment)
            \t}
            \tif re.NumWorkerMultiplier != 0 {
            \t\tt.Errorf("num_worker_multiplier default: got %d want 0", re.NumWorkerMultiplier)
            \t}
            \tif re.MemoryLimit != 0 {
            \t\tt.Errorf("memory_limit default: got %d want 0", re.MemoryLimit)
            \t}
            \tif re.Cache.Dir != "" {
            \t\tt.Errorf("cache.dir default: got %q want empty", re.Cache.Dir)
            \t}
            \tif re.Cache.MaxAge != 0 {
            \t\tt.Errorf("cache.max_age default: got %d want 0", re.Cache.MaxAge)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"defaults scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_environment_from_hugo_prefix(self):
        """L2: HUGO_ENVIRONMENT=development overrides the production default."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tclearHugoEnv(t)
            \tt.Setenv("HUGO_ENVIRONMENT", "development")
            \tre, err := runtimeenv.Resolve()
            \tif err != nil {
            \t\tt.Fatalf("Resolve: %v", err)
            \t}
            \tif re.Environment != "development" {
            \t\tt.Errorf("HUGO_ENVIRONMENT not applied: got %q want development", re.Environment)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"HUGO_ENVIRONMENT scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_underscore_top_level_keys(self):
        """L2: HUGO_NUM_WORKER_MULTIPLIER and HUGO_MEMORY_LIMIT reach the
        underscore-named top-level int fields and are parsed as integers."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tclearHugoEnv(t)
            \tt.Setenv("HUGO_NUM_WORKER_MULTIPLIER", "4")
            \tt.Setenv("HUGO_MEMORY_LIMIT", "8")
            \tre, err := runtimeenv.Resolve()
            \tif err != nil {
            \t\tt.Fatalf("Resolve: %v", err)
            \t}
            \tif re.NumWorkerMultiplier != 4 {
            \t\tt.Errorf("num_worker_multiplier: got %d want 4", re.NumWorkerMultiplier)
            \t}
            \tif re.MemoryLimit != 8 {
            \t\tt.Errorf("memory_limit: got %d want 8", re.MemoryLimit)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"underscore top-level scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_nested_cache_keys(self):
        """L2: HUGO_CACHE_DIR and HUGO_CACHE_MAX_AGE reach the nested Cache
        struct (cache.dir / cache.max_age) from their flattened forms."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tclearHugoEnv(t)
            \tt.Setenv("HUGO_CACHE_DIR", "/var/cache/hugo")
            \tt.Setenv("HUGO_CACHE_MAX_AGE", "3600")
            \tre, err := runtimeenv.Resolve()
            \tif err != nil {
            \t\tt.Fatalf("Resolve: %v", err)
            \t}
            \tif re.Cache.Dir != "/var/cache/hugo" {
            \t\tt.Errorf("cache.dir: got %q want /var/cache/hugo", re.Cache.Dir)
            \t}
            \tif re.Cache.MaxAge != 3600 {
            \t\tt.Errorf("cache.max_age: got %d want 3600", re.Cache.MaxAge)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"nested cache scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_bare_unprefixed_variable_is_ignored(self):
        """L2: a bare ENVIRONMENT=staging (no HUGO_ prefix) must NOT influence
        the result -> Environment stays at the production default.

        This is the key discriminator: a naive implementation that reads
        os.Getenv("ENVIRONMENT") or enables global AutomaticEnv without a
        prefix would wrongly pick this up.
        """
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tclearHugoEnv(t)
            \tt.Setenv("ENVIRONMENT", "staging")   // bare, must be ignored
            \tre, err := runtimeenv.Resolve()
            \tif err != nil {
            \t\tt.Fatalf("Resolve: %v", err)
            \t}
            \tif re.Environment != "production" {
            \t\tt.Errorf("bare ENVIRONMENT leaked in: got %q want production", re.Environment)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"bare-variable-ignored scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_partial_set_keeps_other_defaults(self):
        """L2: setting only one key must leave every other field at its default,
        proving the resolver does not clobber unspecified values."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tclearHugoEnv(t)
            \tt.Setenv("HUGO_CACHE_DIR", "/only/cache")
            \tre, err := runtimeenv.Resolve()
            \tif err != nil {
            \t\tt.Fatalf("Resolve: %v", err)
            \t}
            \tif re.Cache.Dir != "/only/cache" {
            \t\tt.Errorf("cache.dir: got %q want /only/cache", re.Cache.Dir)
            \t}
            \tif re.Environment != "production" {
            \t\tt.Errorf("environment should stay default: got %q want production", re.Environment)
            \t}
            \tif re.NumWorkerMultiplier != 0 {
            \t\tt.Errorf("num_worker_multiplier should stay default: got %d want 0", re.NumWorkerMultiplier)
            \t}
            \tif re.Cache.MaxAge != 0 {
            \t\tt.Errorf("cache.max_age should stay default: got %d want 0", re.Cache.MaxAge)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"partial-set scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_isolation_between_resolve_calls(self):
        """L2: repeated Resolve calls must not leak state. Resolve once with an
        env override, clear it, Resolve again in the same process, and confirm
        the second call reflects the cleared environment (default), not the
        first call's value."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tclearHugoEnv(t)
            \tt.Setenv("HUGO_NUM_WORKER_MULTIPLIER", "9")
            \tr1, err := runtimeenv.Resolve()
            \tif err != nil {
            \t\tt.Fatalf("Resolve #1: %v", err)
            \t}
            \tif r1.NumWorkerMultiplier != 9 {
            \t\tt.Fatalf("resolve #1: got %d want 9", r1.NumWorkerMultiplier)
            \t}
            \tos.Unsetenv("HUGO_NUM_WORKER_MULTIPLIER")
            \tr2, err := runtimeenv.Resolve()
            \tif err != nil {
            \t\tt.Fatalf("Resolve #2: %v", err)
            \t}
            \tif r2.NumWorkerMultiplier != 0 {
            \t\tt.Errorf("state leaked between Resolve calls: got %d want default 0", r2.NumWorkerMultiplier)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"isolation scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_all_keys_together(self):
        """L2: every HUGO_ key set at once resolves to its own value, with no
        cross-talk between the top-level and nested namespaces."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tclearHugoEnv(t)
            \tt.Setenv("HUGO_ENVIRONMENT", "development")
            \tt.Setenv("HUGO_NUM_WORKER_MULTIPLIER", "3")
            \tt.Setenv("HUGO_MEMORY_LIMIT", "16")
            \tt.Setenv("HUGO_CACHE_DIR", "/srv/cache")
            \tt.Setenv("HUGO_CACHE_MAX_AGE", "120")
            \tre, err := runtimeenv.Resolve()
            \tif err != nil {
            \t\tt.Fatalf("Resolve: %v", err)
            \t}
            \tif re.Environment != "development" {
            \t\tt.Errorf("environment: got %q want development", re.Environment)
            \t}
            \tif re.NumWorkerMultiplier != 3 {
            \t\tt.Errorf("num_worker_multiplier: got %d want 3", re.NumWorkerMultiplier)
            \t}
            \tif re.MemoryLimit != 16 {
            \t\tt.Errorf("memory_limit: got %d want 16", re.MemoryLimit)
            \t}
            \tif re.Cache.Dir != "/srv/cache" {
            \t\tt.Errorf("cache.dir: got %q want /srv/cache", re.Cache.Dir)
            \t}
            \tif re.Cache.MaxAge != 120 {
            \t\tt.Errorf("cache.max_age: got %d want 120", re.Cache.MaxAge)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"all-keys scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_native_acceptance_command_passes(self):
        """L2: the exact acceptance command runs green:
        ``go test ./internal/runtimeenv/`` (the agent's own tests)."""
        proc = subprocess.run(
            ["go", "test", "-count=1", "./internal/runtimeenv/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command `go test ./internal/runtimeenv/` failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
