"""Tests for the ``viper-configuration`` skill (variant ext9).

The task asks the agent to add a self-contained *services* config loader at
``internal/svcconfig`` for Hugo. The loader reads the whole ``services`` block
from a config file and hands out a scoped, isolated view of a single named
service's sub-tree on demand.

Required surface (per the requirement doc):
  * ``Load(path string) (*Services, error)`` — builds configuration
    independently on every call; an empty / nonexistent path is NOT an error
    and yields a handle with no services; a present-but-unparseable file IS an
    error.
  * ``(*Services) Service(name string) (*ServiceView, bool)`` — scoped view of
    ``services.<name>`` and ``true`` when present, else ``(nil, false)`` and no
    panic.
  * ``(*ServiceView) GetString(key string) string`` / ``GetBool(key string) bool``
    — read keys *within that service's sub-tree only*.
  * ``(*ServiceView) Decode(dst any) error`` — decode that single service's
    sub-tree into a struct, honoring mapstructure tags including underscore
    names (e.g. ``tracking_id``).

Verification strategy
---------------------
L1 checks the deliverable files exist, are minimally well-formed, are in the
right package, and that the loader dependency was wired into ``go.mod``.

L2 does NOT trust the agent's own ``svcconfig_test.go``. Each L2 method writes
an *independent* Go test into a fresh temp sub-package inside the repo (so the
``github.com/gohugoio/hugo/internal/svcconfig`` import path resolves), feeds it
controlled config files, and asserts on exact resolved values mandated by each
scenario. A stubbed / hardcoded / sub-tree-ignoring / panicking-on-missing
implementation therefore cannot pass.
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
PKG_DIR = os.path.join(REPO_DIR, "internal", "svcconfig")
MODULE = "github.com/gohugoio/hugo"
IMPORT_PATH = MODULE + "/internal/svcconfig"


@pytest.fixture(scope="module", autouse=True)
def _prepare_deps():
    """Ensure module dependencies (including the loader's lib) are downloaded once."""
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
    """Write an independent ``*_test.go`` driver into a fresh sub-package of
    the repo, run ``go test`` on it, and return the CompletedProcess.

    A dedicated directory (its own package) keeps us isolated from whatever the
    agent put in ``svcconfig_test.go`` while still living inside the repo
    module so the import path resolves.
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
    '\tsvcconfig "' + IMPORT_PATH + '"\n'
    ')\n\n'
)


def _write_cfg(tmp_subname, body):
    """Return Go code that writes a config file into ``t.TempDir()`` at runtime.

    Returns a Go snippet creating variable ``cfgPath``. We use a recognizable
    extension (e.g. .toml / .yaml) so the loader's format detection applies.
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
        """L1: the new internal/svcconfig package directory exists."""
        assert os.path.isdir(PKG_DIR), f"missing package dir {PKG_DIR}"

    def test_loader_source_file_exists(self):
        """L1: svcconfig.go exists, is non-trivial, and is in the right package."""
        path = os.path.join(PKG_DIR, "svcconfig.go")
        assert os.path.isfile(path), "svcconfig.go not created"
        with open(path) as fh:
            content = fh.read()
        assert len(content.strip()) > 100, "svcconfig.go looks empty/stub"
        assert "package svcconfig" in content, "wrong package declaration"

    def test_agent_test_file_exists(self):
        """L1: the agent's own deterministic unit test file exists."""
        path = os.path.join(PKG_DIR, "svcconfig_test.go")
        assert os.path.isfile(path), "svcconfig_test.go not created"

    def test_loader_dependency_wired_in(self):
        """L1: a config-loading dependency (viper) was added to go.mod."""
        gomod = os.path.join(REPO_DIR, "go.mod")
        assert os.path.isfile(gomod)
        with open(gomod) as fh:
            mod = fh.read().lower()
        assert "viper" in mod, "viper dependency not present in go.mod"

    def test_package_compiles_and_exports_api(self):
        """L1->L2: package builds and exports Services, ServiceView, Load with
        the documented signatures (compile-only smoke driver)."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tvar _ *svcconfig.Services
            \tvar _ *svcconfig.ServiceView
            \ts, err := svcconfig.Load("")
            \tif err != nil {
            \t\tt.Fatalf("Load(\\"\\") returned error: %v", err)
            \t}
            \tif s == nil {
            \t\tt.Fatalf("Load returned nil *Services for empty path")
            \t}
            \t// Service / view methods must exist with the documented signatures.
            \tview, ok := s.Service("anything")
            \tif ok {
            \t\tt.Fatalf("empty-path handle reported service present")
            \t}
            \tif view != nil {
            \t\tt.Fatalf("missing service must yield nil view")
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "package failed to compile / missing exported API "
            "(Services/ServiceView/Load/Service).\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    # ---------------------------------------------------------------- L2 ----

    def test_existing_service_view_and_getstring(self):
        """L2: services.disqus.shortname=myforum -> Service("disqus") returns a
        view and true; view.GetString("shortname") == "myforum"."""
        cfg = _write_cfg(
            "config.toml",
            '[services]\n[services.disqus]\nshortname = "myforum"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\ts, err := svcconfig.Load(cfgPath)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tview, ok := s.Service("disqus")\n'
            '\tif !ok {\n'
            '\t\tt.Fatalf("disqus service must be present, ok=false")\n'
            '\t}\n'
            '\tif view == nil {\n'
            '\t\tt.Fatalf("disqus view must be non-nil")\n'
            '\t}\n'
            '\tif got := view.GetString("shortname"); got != "myforum" {\n'
            '\t\tt.Errorf("shortname: got %q want myforum", got)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"existing-service scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_missing_service_returns_nil_false_no_panic(self):
        """L2: Service("nonexistent") -> (nil, false), no panic, even when
        other services are present."""
        cfg = _write_cfg(
            "config.toml",
            '[services]\n[services.disqus]\nshortname = "myforum"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\ts, err := svcconfig.Load(cfgPath)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tview, ok := s.Service("nonexistent")\n'
            '\tif ok {\n'
            '\t\tt.Errorf("nonexistent service reported present (ok=true)")\n'
            '\t}\n'
            '\tif view != nil {\n'
            '\t\tt.Errorf("nonexistent service must yield nil view")\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"missing-service scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_decode_underscore_tag(self):
        """L2: services.googleAnalytics.tracking_id=G-XYZ -> Decode into a
        struct field tagged ``tracking_id`` yields "G-XYZ" (underscore mapping
        and sub-tree scoping both exercised)."""
        cfg = _write_cfg(
            "config.toml",
            '[services]\n[services.googleAnalytics]\ntracking_id = "G-XYZ"\n',
        )
        src = _PREAMBLE + (
            'type gaCfg struct {\n'
            '\tTrackingID string `mapstructure:"tracking_id"`\n'
            '}\n\n'
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\ts, err := svcconfig.Load(cfgPath)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tview, ok := s.Service("googleAnalytics")\n'
            '\tif !ok || view == nil {\n'
            '\t\tt.Fatalf("googleAnalytics service must be present")\n'
            '\t}\n'
            '\tvar dst gaCfg\n'
            '\tif err := view.Decode(&dst); err != nil {\n'
            '\t\tt.Fatalf("Decode: %v", err)\n'
            '\t}\n'
            '\tif dst.TrackingID != "G-XYZ" {\n'
            '\t\tt.Errorf("tracking_id decoded: got %q want G-XYZ", dst.TrackingID)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"decode-underscore scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_view_reads_only_its_own_subtree(self):
        """L2: a view scoped to one service must NOT see another service's keys.
        rss view reading ``services.disqus.shortname`` (or even ``shortname``)
        must not return the disqus value; reading its own ``limit`` works."""
        cfg = _write_cfg(
            "config.toml",
            '[services]\n[services.disqus]\nshortname = "myforum"\n'
            '[services.rss]\nlimit = "20"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\ts, err := svcconfig.Load(cfgPath)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\trss, ok := s.Service("rss")\n'
            '\tif !ok || rss == nil {\n'
            '\t\tt.Fatalf("rss service must be present")\n'
            '\t}\n'
            '\t// Within-subtree read works.\n'
            '\tif got := rss.GetString("limit"); got != "20" {\n'
            '\t\tt.Errorf("rss.limit: got %q want 20", got)\n'
            '\t}\n'
            '\t// Cross-service leakage must NOT happen: rss view has no shortname,\n'
            '\t// and certainly no services.disqus.shortname.\n'
            '\tif got := rss.GetString("shortname"); got != "" {\n'
            '\t\tt.Errorf("rss view leaked shortname: got %q want empty", got)\n'
            '\t}\n'
            '\tif got := rss.GetString("services.disqus.shortname"); got == "myforum" {\n'
            '\t\tt.Errorf("rss view resolved another service full path: got %q", got)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"subtree-isolation scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_getbool_within_subtree(self):
        """L2: GetBool reads a boolean key within the service's own sub-tree."""
        cfg = _write_cfg(
            "config.toml",
            '[services]\n[services.disqus]\nenabled = true\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\ts, err := svcconfig.Load(cfgPath)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tview, ok := s.Service("disqus")\n'
            '\tif !ok || view == nil {\n'
            '\t\tt.Fatalf("disqus service must be present")\n'
            '\t}\n'
            '\tif !view.GetBool("enabled") {\n'
            '\t\tt.Errorf("GetBool(enabled): got false want true")\n'
            '\t}\n'
            '\t// A bool key absent in this sub-tree is false, not leaked.\n'
            '\tif view.GetBool("nope") {\n'
            '\t\tt.Errorf("GetBool(nope): got true want false")\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"getbool scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_empty_path_yields_no_services(self):
        """L2: empty path -> Load succeeds and every Service(...) is (nil,false)."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \ts, err := svcconfig.Load("")
            \tif err != nil {
            \t\tt.Fatalf("empty path must not error, got: %v", err)
            \t}
            \tfor _, name := range []string{"disqus", "googleAnalytics", "rss"} {
            \t\tview, ok := s.Service(name)
            \t\tif ok || view != nil {
            \t\t\tt.Errorf("empty-path Service(%q): got (view=%v, ok=%v) want (nil,false)", name, view, ok)
            \t\t}
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"empty-path scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_nonexistent_file_is_not_an_error(self):
        """L2: a path naming a nonexistent file -> Load succeeds, no services."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tmissing := filepath.Join(t.TempDir(), "does-not-exist.toml")
            \ts, err := svcconfig.Load(missing)
            \tif err != nil {
            \t\tt.Fatalf("nonexistent file must not error, got: %v", err)
            \t}
            \tif view, ok := s.Service("disqus"); ok || view != nil {
            \t\tt.Errorf("missing-file Service: got (view=%v, ok=%v) want (nil,false)", view, ok)
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"nonexistent-file scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_unparseable_file_errors(self):
        """L2: a present but malformed config file -> Load returns non-nil error."""
        cfg = _write_cfg("config.toml", '[services\nshortname = = = "broken [[[\n')
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\t_, err := svcconfig.Load(cfgPath)\n'
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
        """L2: each Load builds its own state. Loading a file with disqus, then
        a second file without it, must NOT leak the first call's disqus into the
        second handle."""
        cfg1 = _write_cfg(
            "first.toml",
            '[services]\n[services.disqus]\nshortname = "myforum"\n',
        )
        # Build the second config path explicitly to avoid clobbering cfgPath.
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg1 +
            '\ts1, err := svcconfig.Load(cfgPath)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load #1: %v", err)\n'
            '\t}\n'
            '\tif v, ok := s1.Service("disqus"); !ok || v == nil {\n'
            '\t\tt.Fatalf("load #1 must see disqus")\n'
            '\t}\n'
            '\t// Second config: a different service, no disqus.\n'
            '\tcfg2 := filepath.Join(dir, "second.toml")\n'
            '\tif err := os.WriteFile(cfg2, []byte("[services]\\n[services.rss]\\nlimit = \\"5\\"\\n"), 0o644); err != nil {\n'
            '\t\tt.Fatalf("write cfg2: %v", err)\n'
            '\t}\n'
            '\ts2, err := svcconfig.Load(cfg2)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load #2: %v", err)\n'
            '\t}\n'
            '\tif v, ok := s2.Service("disqus"); ok || v != nil {\n'
            '\t\tt.Errorf("state leaked between Load calls: load #2 saw disqus (view=%v, ok=%v)", v, ok)\n'
            '\t}\n'
            '\tif v, ok := s2.Service("rss"); !ok || v == nil {\n'
            '\t\tt.Fatalf("load #2 must see its own rss service")\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"isolation scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_native_acceptance_command_passes(self):
        """L2: the exact acceptance command runs green:
        ``go test ./internal/svcconfig/`` (the agent's own tests)."""
        proc = subprocess.run(
            ["go", "test", "-count=1", "./internal/svcconfig/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command `go test ./internal/svcconfig/` failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
