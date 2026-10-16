"""Tests for the ``viper-configuration`` skill (ext2 variant).

The task asks the agent to add a self-contained deploy-target configuration
loader package at ``internal/deployconf`` for Hugo's ``hugo deploy`` command.
The loader reads a deploy configuration -- a list of named targets plus a
default target -- from a config file, environment variables, and programmatic
overrides, and decodes the resolved configuration *tree* into typed structs
(``DeployConfig`` / ``Target``).

Key requirements verified here:
  * Exported API: ``DeployConfig``, ``Target``, ``Options``, ``Load``,
    ``TargetByName``.
  * The result is produced by *decoding* the resolved config tree into the
    structs (nested ``targets`` list + the underscore-named ``cloud_front_id``
    field must decode correctly).
  * Source precedence for ``default``: programmatic override > environment
    variable (``HUGODEPLOY_`` prefix) > config file > zero value.
  * Environment lookups are namespaced under ``HUGODEPLOY_``; a bare
    ``DEFAULT`` env var must be ignored.
  * ``TargetByName`` returns ``(nil, false)`` for an unknown name without
    panicking.
  * Each ``Load`` builds independent state -- no leakage across calls.

Verification strategy
---------------------
L1 checks the deliverable files exist and are minimally well-formed, and that
the underlying config library (viper) was wired into ``go.mod``.

L2 does NOT trust the agent's own ``deployconf_test.go``. Instead each L2
method writes an *independent* Go test into a fresh temp sub-package inside the
repo that imports ``github.com/gohugoio/hugo/internal/deployconf`` and calls
``deployconf.Load`` / ``deployconf.TargetByName`` with controlled overrides /
env / config files, then runs ``go test`` on that driver. The driver asserts
on the exact resolved values mandated by each requirement scenario, so a
stubbed / hardcoded / keyword solution cannot pass. The final method drives the
exact native acceptance command ``go test ./internal/deployconf/``.
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
PKG_DIR = os.path.join(REPO_DIR, "internal", "deployconf")
MODULE = "github.com/gohugoio/hugo"
IMPORT_PATH = MODULE + "/internal/deployconf"


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
    whatever the agent put in deployconf_test.go, while still living inside the
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
    '\t"testing"\n\n'
    '\tdeployconf "' + IMPORT_PATH + '"\n'
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


# A reusable TOML config defining two targets with a default. The staging
# target carries the underscore-named cloud_front_id key.
_TWO_TARGET_TOML = (
    'default = "production"\n\n'
    '[[targets]]\n'
    'name = "production"\n'
    'url = "s3://prod-bucket?region=us-east-1"\n\n'
    '[[targets]]\n'
    'name = "staging"\n'
    'url = "s3://staging-bucket?region=us-west-2"\n'
    'cloud_front_id = "ABC123"\n'
)


class TestViperConfiguration:
    REPO_DIR = _find_repo_dir("/workspace/hugo")

    # ---------------------------------------------------------------- L1 ----

    def test_package_directory_exists(self):
        """L1: the new internal/deployconf package directory exists."""
        assert os.path.isdir(PKG_DIR), f"missing package dir {PKG_DIR}"

    def test_loader_source_file_exists(self):
        """L1: deployconf.go exists, is non-trivial, and is in the right package."""
        path = os.path.join(PKG_DIR, "deployconf.go")
        assert os.path.isfile(path), "deployconf.go not created"
        with open(path) as fh:
            content = fh.read()
        assert len(content.strip()) > 100, "deployconf.go looks empty/stub"
        assert "package deployconf" in content, "wrong package declaration"

    def test_agent_test_file_exists(self):
        """L1: the agent's own deterministic unit test file exists."""
        path = os.path.join(PKG_DIR, "deployconf_test.go")
        assert os.path.isfile(path), "deployconf_test.go not created"

    def test_viper_dependency_wired_in(self):
        """L1: a viper dependency was added to go.mod (the loader's backbone)."""
        gomod = os.path.join(REPO_DIR, "go.mod")
        assert os.path.isfile(gomod)
        with open(gomod) as fh:
            mod = fh.read().lower()
        assert "viper" in mod, "viper dependency not present in go.mod"

    def test_package_compiles_and_exports_api(self):
        """L1->L2: package builds and exports DeployConfig, Target, Options,
        Load, and TargetByName with the documented signatures (compile via a
        tiny driver that also exercises an empty Load)."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tvar _ deployconf.DeployConfig
            \tvar _ deployconf.Target
            \tvar _ deployconf.Options
            \tcfg, err := deployconf.Load(deployconf.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Load returned error on empty options: %v", err)
            \t}
            \tif cfg == nil {
            \t\tt.Fatalf("Load returned nil config")
            \t}
            \t// TargetByName must exist and not panic on an empty config.
            \tif tgt, ok := deployconf.TargetByName(cfg, "nope"); ok || tgt != nil {
            \t\tt.Fatalf("TargetByName on empty cfg: got (%v,%v) want (nil,false)", tgt, ok)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "package failed to compile / missing exported API "
            "(DeployConfig/Target/Options/Load/TargetByName).\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    # ---------------------------------------------------------------- L2 ----

    def test_targets_decode_from_file(self):
        """L2: a config file with two targets + default decodes into the
        structs -- both targets present (by name), Default == production."""
        cfg = _write_cfg("deploy.toml", _TWO_TARGET_TOML)
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tcfg, err := deployconf.Load(deployconf.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tif cfg.Default != "production" {\n'
            '\t\tt.Errorf("default: got %q want production", cfg.Default)\n'
            '\t}\n'
            '\tif len(cfg.Targets) != 2 {\n'
            '\t\tt.Fatalf("targets count: got %d want 2", len(cfg.Targets))\n'
            '\t}\n'
            '\tnames := map[string]bool{}\n'
            '\tfor _, tg := range cfg.Targets {\n'
            '\t\tnames[tg.Name] = true\n'
            '\t}\n'
            '\tif !names["production"] || !names["staging"] {\n'
            '\t\tt.Errorf("target names: got %v want production+staging", names)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "two-target decode scenario failed. (Note: Options must expose a "
            "config-file path field; the test uses `ConfigFile`.)\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_underscore_cloud_front_id_decodes(self):
        """L2: the underscore-named cloud_front_id key decodes into
        Target.CloudFrontID (a naive struct decode without the right key
        mapping fails this)."""
        cfg = _write_cfg("deploy.toml", _TWO_TARGET_TOML)
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tcfg, err := deployconf.Load(deployconf.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tvar staging *deployconf.Target\n'
            '\tfor i := range cfg.Targets {\n'
            '\t\tif cfg.Targets[i].Name == "staging" {\n'
            '\t\t\tstaging = &cfg.Targets[i]\n'
            '\t\t}\n'
            '\t}\n'
            '\tif staging == nil {\n'
            '\t\tt.Fatalf("staging target not decoded")\n'
            '\t}\n'
            '\tif staging.CloudFrontID != "ABC123" {\n'
            '\t\tt.Errorf("cloud_front_id: got %q want ABC123", staging.CloudFrontID)\n'
            '\t}\n'
            '\tif staging.URL != "s3://staging-bucket?region=us-west-2" {\n'
            '\t\tt.Errorf("url: got %q want s3://staging-bucket?region=us-west-2", staging.URL)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"cloud_front_id underscore decode scenario failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_env_namespaced_under_hugodeploy(self):
        """L2: HUGODEPLOY_DEFAULT overrides the file's default; a bare DEFAULT
        env var must be ignored entirely."""
        cfg = _write_cfg("deploy.toml", _TWO_TARGET_TOML)  # file default=production
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tt.Setenv("DEFAULT", "bare-should-be-ignored")\n'
            '\tt.Setenv("HUGODEPLOY_DEFAULT", "staging")\n'
            + cfg +
            '\tcfg, err := deployconf.Load(deployconf.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tif cfg.Default != "staging" {\n'
            '\t\tt.Errorf("HUGODEPLOY_DEFAULT should win over file: got %q want staging", cfg.Default)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"HUGODEPLOY_ namespacing / bare-var-ignored scenario failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_bare_env_var_is_ignored(self):
        """L2: with ONLY a bare DEFAULT set (no HUGODEPLOY_DEFAULT), the
        resolved default comes from the file, not the bare variable."""
        cfg = _write_cfg("deploy.toml", _TWO_TARGET_TOML)  # file default=production
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tt.Setenv("DEFAULT", "bare-value")\n'
            + cfg +
            '\tcfg, err := deployconf.Load(deployconf.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tif cfg.Default != "production" {\n'
            '\t\tt.Errorf("bare DEFAULT must be ignored: got %q want production", cfg.Default)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"bare-env-ignored scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_env_beats_file_for_default(self):
        """L2: file sets default=staging, env sets HUGODEPLOY_DEFAULT=production,
        no override -> env wins (production)."""
        cfg = _write_cfg(
            "deploy.toml",
            'default = "staging"\n\n[[targets]]\nname = "staging"\nurl = "s3://s"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tt.Setenv("HUGODEPLOY_DEFAULT", "production")\n'
            + cfg +
            '\tcfg, err := deployconf.Load(deployconf.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tif cfg.Default != "production" {\n'
            '\t\tt.Errorf("env should beat file: got %q want production", cfg.Default)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"env-beats-file precedence failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_override_beats_env_and_file(self):
        """L2: file sets default=staging, env sets HUGODEPLOY_DEFAULT=production,
        override sets default=qa -> the override wins (qa)."""
        cfg = _write_cfg(
            "deploy.toml",
            'default = "staging"\n\n[[targets]]\nname = "staging"\nurl = "s3://s"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tt.Setenv("HUGODEPLOY_DEFAULT", "production")\n'
            + cfg +
            '\topts := deployconf.Options{ConfigFile: cfgPath}\n'
            '\topts.Overrides = map[string]any{"default": "qa"}\n'
            '\tcfg, err := deployconf.Load(opts)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tif cfg.Default != "qa" {\n'
            '\t\tt.Errorf("override should win: got %q want qa", cfg.Default)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "override-precedence scenario failed. Options must carry a "
            "programmatic override (the test uses `Overrides map[string]any`).\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_target_by_name_found(self):
        """L2: TargetByName returns the matching target and true for a name
        present in the config; the returned target's fields are intact."""
        cfg = _write_cfg("deploy.toml", _TWO_TARGET_TOML)
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tcfg, err := deployconf.Load(deployconf.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\ttgt, ok := deployconf.TargetByName(cfg, "staging")\n'
            '\tif !ok {\n'
            '\t\tt.Fatalf("TargetByName(staging): ok=false want true")\n'
            '\t}\n'
            '\tif tgt == nil {\n'
            '\t\tt.Fatalf("TargetByName(staging): nil target")\n'
            '\t}\n'
            '\tif tgt.Name != "staging" {\n'
            '\t\tt.Errorf("returned wrong target: got %q want staging", tgt.Name)\n'
            '\t}\n'
            '\tif tgt.CloudFrontID != "ABC123" {\n'
            '\t\tt.Errorf("returned target cloud_front_id: got %q want ABC123", tgt.CloudFrontID)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"TargetByName-found scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_target_by_name_missing_no_panic(self):
        """L2: TargetByName for an unknown name returns (nil, false) and does
        not panic (a naive impl that indexes a map/slice would panic)."""
        cfg = _write_cfg("deploy.toml", _TWO_TARGET_TOML)
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tcfg, err := deployconf.Load(deployconf.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\ttgt, ok := deployconf.TargetByName(cfg, "does-not-exist")\n'
            '\tif ok {\n'
            '\t\tt.Errorf("missing name: ok=true want false")\n'
            '\t}\n'
            '\tif tgt != nil {\n'
            '\t\tt.Errorf("missing name: target=%v want nil", tgt)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"TargetByName-missing scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_isolation_between_loads(self):
        """L2: repeated Load calls do not leak state. Load once with an env
        default, then clear the env and Load again in the same process; the
        second result must reflect the file value, not the first call's env."""
        cfg = _write_cfg(
            "deploy.toml",
            'default = "filedefault"\n\n[[targets]]\nname = "t1"\nurl = "s3://t1"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tt.Setenv("HUGODEPLOY_DEFAULT", "envdefault")\n'
            '\tc1, err := deployconf.Load(deployconf.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load #1: %v", err)\n'
            '\t}\n'
            '\tif c1.Default != "envdefault" {\n'
            '\t\tt.Fatalf("load #1 default: got %q want envdefault", c1.Default)\n'
            '\t}\n'
            '\tos.Unsetenv("HUGODEPLOY_DEFAULT")\n'
            '\tc2, err := deployconf.Load(deployconf.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load #2: %v", err)\n'
            '\t}\n'
            '\tif c2.Default != "filedefault" {\n'
            '\t\tt.Errorf("state leaked between Load calls: got %q want filedefault", c2.Default)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"isolation scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_native_acceptance_command_passes(self):
        """L2: the exact acceptance command runs green:
        ``go test ./internal/deployconf/`` (the agent's own tests)."""
        proc = subprocess.run(
            ["go", "test", "-count=1", "./internal/deployconf/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command `go test ./internal/deployconf/` failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
