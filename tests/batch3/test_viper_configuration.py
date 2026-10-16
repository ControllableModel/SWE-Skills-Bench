"""Tests for the ``viper-configuration`` skill (variant ext3).

The ext3 task asks the agent to add a self-contained *layered module
configuration merger* at ``internal/moduleconf`` for Hugo's module system.

Unlike ext1 (a four-source server settings loader keyed on
precedence/env), ext3 is a two-file MERGE: ``Merge(basePath, overridePath)``
reads a base config file, then overlays an override config file on top so
that keys present in the override win while base-only keys are preserved.
The merged tree decodes into an exported ``ModuleConfig`` struct holding a
``Path string``, a ``Replacements []string`` slice, and a nested
``Mounts []Mount`` list; ``Mount`` carries ``Source``/``Target`` plus an
underscore-named ``ExcludeFiles`` (key ``exclude_files``). Missing/empty
base or override files must NOT error (the other file alone is used; both
absent -> a zero-valued config); a file that IS present but unparseable MUST
return a non-nil error.

Verification strategy
---------------------
L1 confirms the deliverable files exist, are minimally well-formed, declare
``package moduleconf``, and that a viper dependency was wired into go.mod.

L2 does NOT trust the agent's own ``moduleconf_test.go``. Each L2 method
writes an *independent* Go test into a fresh temp sub-package living inside
the repo module (so the import path ``github.com/gohugoio/hugo/internal/
moduleconf`` resolves), and runs ``go test`` on that driver. The driver calls
``moduleconf.Merge`` with controlled base/override files written at runtime
and asserts on the exact resolved field values mandated by each requirement
scenario. A stub that ignores the override, hardcodes a struct, skips nested
decoding, or fails to read the second file therefore cannot pass. The final
method runs the doc's native acceptance command verbatim.
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
PKG_DIR = os.path.join(REPO_DIR, "internal", "moduleconf")
MODULE = "github.com/gohugoio/hugo"
IMPORT_PATH = MODULE + "/internal/moduleconf"


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

    A dedicated directory (its own package) isolates us from whatever the
    agent put in moduleconf_test.go, while still living inside the repo module
    so the ``internal/moduleconf`` import path resolves.
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
    '\tmoduleconf "' + IMPORT_PATH + '"\n'
    ')\n\n'
)


def _write_file_snippet(varname, subname, body):
    """Return Go code writing ``body`` into ``<tempdir>/<subname>`` at runtime,
    binding the resulting path to Go variable ``varname``.

    A shared ``dir := t.TempDir()`` is assumed to already exist in scope.
    """
    escaped = body.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return (
        '\t' + varname + ' := filepath.Join(dir, "' + subname + '")\n'
        '\tif err := os.WriteFile(' + varname + ', []byte("' + escaped + '"), 0o644); err != nil {\n'
        '\t\tt.Fatalf("write ' + subname + ': %v", err)\n'
        '\t}\n'
    )


class TestViperConfiguration:
    REPO_DIR = _find_repo_dir("/workspace/hugo")

    # ---------------------------------------------------------------- L1 ----

    def test_package_directory_exists(self):
        """L1: the new internal/moduleconf package directory exists."""
        assert os.path.isdir(PKG_DIR), f"missing package dir {PKG_DIR}"

    def test_merger_source_file_exists(self):
        """L1: moduleconf.go exists, is non-trivial, and is in the right package."""
        path = os.path.join(PKG_DIR, "moduleconf.go")
        assert os.path.isfile(path), "moduleconf.go not created"
        with open(path) as fh:
            content = fh.read()
        assert len(content.strip()) > 100, "moduleconf.go looks empty/stub"
        assert "package moduleconf" in content, "wrong package declaration"

    def test_agent_test_file_exists(self):
        """L1: the agent's own deterministic unit test file exists."""
        path = os.path.join(PKG_DIR, "moduleconf_test.go")
        assert os.path.isfile(path), "moduleconf_test.go not created"

    def test_viper_dependency_wired_in(self):
        """L1: a viper dependency was added to go.mod (the merger's backbone)."""
        gomod = os.path.join(REPO_DIR, "go.mod")
        assert os.path.isfile(gomod)
        with open(gomod) as fh:
            mod = fh.read().lower()
        assert "viper" in mod, "viper dependency not present in go.mod"

    def test_package_compiles_and_exports_api(self):
        """L1->L2: package builds and exports ModuleConfig, Mount, Merge with
        the documented signatures (vet via a tiny compile-only driver)."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tvar cfg moduleconf.ModuleConfig
            \t_ = cfg.Path
            \t_ = cfg.Replacements
            \t_ = cfg.Mounts
            \tvar m moduleconf.Mount
            \t_ = m.Source
            \t_ = m.Target
            \t_ = m.ExcludeFiles
            \tres, err := moduleconf.Merge("", "")
            \tif err != nil {
            \t\tt.Fatalf("Merge(\\"\\", \\"\\") returned error: %v", err)
            \t}
            \tif res == nil {
            \t\tt.Fatalf("Merge returned nil config")
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "package failed to compile / missing exported API "
            "(ModuleConfig{Path,Replacements,Mounts} / Mount{Source,Target,"
            "ExcludeFiles} / Merge).\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    # ---------------------------------------------------------------- L2 ----

    def test_empty_paths_yield_zero_config(self):
        """L2: both paths empty -> Merge succeeds, returns a zero-valued config
        (empty Path, no mounts), no error."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tcfg, err := moduleconf.Merge("", "")
            \tif err != nil {
            \t\tt.Fatalf("Merge with two empty paths must not error: %v", err)
            \t}
            \tif cfg == nil {
            \t\tt.Fatalf("Merge returned nil config")
            \t}
            \tif cfg.Path != "" {
            \t\tt.Errorf("zero config Path: got %q want empty", cfg.Path)
            \t}
            \tif len(cfg.Mounts) != 0 {
            \t\tt.Errorf("zero config Mounts: got %d entries want 0", len(cfg.Mounts))
            \t}
            \tif len(cfg.Replacements) != 0 {
            \t\tt.Errorf("zero config Replacements: got %d entries want 0", len(cfg.Replacements))
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"empty-paths scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_base_only_decoded(self):
        """L2: base file alone (override empty) decodes Path and a mount, incl.
        the underscore-named exclude_files key into Mount.ExcludeFiles."""
        base = _write_file_snippet(
            "basePath",
            "base.toml",
            'path = "github.com/x/base"\n'
            'replacements = ["a -> b"]\n\n'
            '[[mounts]]\n'
            'source = "content"\n'
            'target = "static"\n'
            'exclude_files = ["*.tmp", "*.bak"]\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            + base +
            '\tcfg, err := moduleconf.Merge(basePath, "")\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Merge base-only: %v", err)\n'
            '\t}\n'
            '\tif cfg.Path != "github.com/x/base" {\n'
            '\t\tt.Errorf("Path: got %q want github.com/x/base", cfg.Path)\n'
            '\t}\n'
            '\tif len(cfg.Replacements) != 1 || cfg.Replacements[0] != "a -> b" {\n'
            '\t\tt.Errorf("Replacements: got %#v want [a -> b]", cfg.Replacements)\n'
            '\t}\n'
            '\tif len(cfg.Mounts) != 1 {\n'
            '\t\tt.Fatalf("Mounts: got %d entries want 1", len(cfg.Mounts))\n'
            '\t}\n'
            '\tm := cfg.Mounts[0]\n'
            '\tif m.Source != "content" || m.Target != "static" {\n'
            '\t\tt.Errorf("mount src/target: got %q/%q want content/static", m.Source, m.Target)\n'
            '\t}\n'
            '\tif len(m.ExcludeFiles) != 2 || m.ExcludeFiles[0] != "*.tmp" || m.ExcludeFiles[1] != "*.bak" {\n'
            '\t\tt.Errorf("exclude_files did not decode: got %#v want [*.tmp *.bak]", m.ExcludeFiles)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"base-only decode scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_override_scalar_wins(self):
        """L2: base sets path: a, override sets path: b -> merged Path == "b"."""
        base = _write_file_snippet("basePath", "base.toml", 'path = "a"\n')
        override = _write_file_snippet("overridePath", "override.toml", 'path = "b"\n')
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            + base + override +
            '\tcfg, err := moduleconf.Merge(basePath, overridePath)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Merge: %v", err)\n'
            '\t}\n'
            '\tif cfg.Path != "b" {\n'
            '\t\tt.Errorf("override should win for path: got %q want b", cfg.Path)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"override-scalar-wins scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_base_only_keys_preserved_under_override(self):
        """L2: base sets path + a mount; override sets only a different key
        (replacements). Merged config keeps the base's path AND mount while
        gaining the override's replacements. (Naive 'return override' fails.)"""
        base = _write_file_snippet(
            "basePath",
            "base.toml",
            'path = "github.com/x/base"\n\n'
            '[[mounts]]\n'
            'source = "s1"\n'
            'target = "t1"\n',
        )
        override = _write_file_snippet(
            "overridePath",
            "override.toml",
            'replacements = ["old -> new"]\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            + base + override +
            '\tcfg, err := moduleconf.Merge(basePath, overridePath)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Merge: %v", err)\n'
            '\t}\n'
            '\tif cfg.Path != "github.com/x/base" {\n'
            '\t\tt.Errorf("base-only Path not preserved: got %q want github.com/x/base", cfg.Path)\n'
            '\t}\n'
            '\tif len(cfg.Mounts) != 1 || cfg.Mounts[0].Source != "s1" || cfg.Mounts[0].Target != "t1" {\n'
            '\t\tt.Errorf("base-only mount not preserved: got %#v", cfg.Mounts)\n'
            '\t}\n'
            '\tif len(cfg.Replacements) != 1 || cfg.Replacements[0] != "old -> new" {\n'
            '\t\tt.Errorf("override replacements not applied: got %#v want [old -> new]", cfg.Replacements)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"base-keys-preserved scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_override_value_wins_on_shared_key(self):
        """L2: both base and override set the same scalar AND a nested mount's
        target; the override's value wins where both set the same key."""
        base = _write_file_snippet(
            "basePath",
            "base.toml",
            'path = "base/path"\n\n'
            '[[mounts]]\n'
            'source = "src"\n'
            'target = "base-target"\n',
        )
        override = _write_file_snippet(
            "overridePath",
            "override.toml",
            'path = "override/path"\n\n'
            '[[mounts]]\n'
            'source = "src"\n'
            'target = "override-target"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            + base + override +
            '\tcfg, err := moduleconf.Merge(basePath, overridePath)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Merge: %v", err)\n'
            '\t}\n'
            '\tif cfg.Path != "override/path" {\n'
            '\t\tt.Errorf("shared scalar: override should win, got %q want override/path", cfg.Path)\n'
            '\t}\n'
            '\tif len(cfg.Mounts) == 0 {\n'
            '\t\tt.Fatalf("mounts empty after merge")\n'
            '\t}\n'
            '\tfoundOverride := false\n'
            '\tfoundBaseTarget := false\n'
            '\tfor _, m := range cfg.Mounts {\n'
            '\t\tif m.Target == "override-target" {\n'
            '\t\t\tfoundOverride = true\n'
            '\t\t}\n'
            '\t\tif m.Target == "base-target" {\n'
            '\t\t\tfoundBaseTarget = true\n'
            '\t\t}\n'
            '\t}\n'
            '\tif !foundOverride {\n'
            '\t\tt.Errorf("override mount target missing: mounts=%#v", cfg.Mounts)\n'
            '\t}\n'
            '\tif foundBaseTarget {\n'
            '\t\tt.Errorf("override should win for mounts key: stale base-target present: %#v", cfg.Mounts)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"override-value-wins scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_missing_base_uses_override(self):
        """L2: basePath points to a nonexistent file but overridePath exists ->
        Merge succeeds drawing config from the override alone."""
        override = _write_file_snippet(
            "overridePath",
            "override.toml",
            'path = "only/override"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            + override +
            '\tmissing := filepath.Join(dir, "no-such-base.toml")\n'
            '\tcfg, err := moduleconf.Merge(missing, overridePath)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("missing base must not error: %v", err)\n'
            '\t}\n'
            '\tif cfg.Path != "only/override" {\n'
            '\t\tt.Errorf("override-only Path: got %q want only/override", cfg.Path)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"missing-base scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_missing_override_uses_base(self):
        """L2: overridePath nonexistent but basePath exists -> base alone used,
        no error."""
        base = _write_file_snippet(
            "basePath",
            "base.toml",
            'path = "only/base"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            + base +
            '\tmissing := filepath.Join(dir, "no-such-override.toml")\n'
            '\tcfg, err := moduleconf.Merge(basePath, missing)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("missing override must not error: %v", err)\n'
            '\t}\n'
            '\tif cfg.Path != "only/base" {\n'
            '\t\tt.Errorf("base-only Path: got %q want only/base", cfg.Path)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"missing-override scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_unparseable_override_errors(self):
        """L2: overridePath is present but malformed -> Merge returns non-nil
        error (a stub that swallows all errors fails here)."""
        base = _write_file_snippet("basePath", "base.toml", 'path = "ok"\n')
        bad = _write_file_snippet(
            "overridePath",
            "override.toml",
            'path = = = "broken toml [[[\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            + base + bad +
            '\t_, err := moduleconf.Merge(basePath, overridePath)\n'
            '\tif err == nil {\n'
            '\t\tt.Fatalf("unparseable override must return an error, got nil")\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"unparseable-override scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_isolation_between_merges(self):
        """L2: repeated Merge calls do not leak/share state. A first merge with
        a base path, then a second merge with two empty paths in the same
        process, must NOT inherit the first call's values."""
        base = _write_file_snippet(
            "basePath",
            "base.toml",
            'path = "first/call"\n\n'
            '[[mounts]]\n'
            'source = "s"\n'
            'target = "t"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            + base +
            '\tc1, err := moduleconf.Merge(basePath, "")\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Merge #1: %v", err)\n'
            '\t}\n'
            '\tif c1.Path != "first/call" || len(c1.Mounts) != 1 {\n'
            '\t\tt.Fatalf("Merge #1 unexpected: path=%q mounts=%d", c1.Path, len(c1.Mounts))\n'
            '\t}\n'
            '\tc2, err := moduleconf.Merge("", "")\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Merge #2: %v", err)\n'
            '\t}\n'
            '\tif c2.Path != "" {\n'
            '\t\tt.Errorf("state leaked between Merge calls: Path got %q want empty", c2.Path)\n'
            '\t}\n'
            '\tif len(c2.Mounts) != 0 {\n'
            '\t\tt.Errorf("state leaked between Merge calls: Mounts got %d want 0", len(c2.Mounts))\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"isolation scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_native_acceptance_command_passes(self):
        """L2: the exact acceptance command runs green:
        ``go test ./internal/moduleconf/`` (the agent's own tests)."""
        proc = subprocess.run(
            ["go", "test", "-count=1", "./internal/moduleconf/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command `go test ./internal/moduleconf/` failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
