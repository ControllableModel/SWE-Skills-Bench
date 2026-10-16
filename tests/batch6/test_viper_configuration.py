"""Tests for the ``viper-configuration`` skill (ext6 variant).

The ext6 task asks the agent to add a self-contained, hot-reloading config
watcher package at ``internal/configwatch`` for Hugo's server runtime. The
package watches a single sidecar settings file and re-applies a subset of
runtime settings whenever the file's bytes change on disk.

Required API (from the requirement doc):

* exported struct ``Settings`` with fields
    - ``LogLevel string``           (key ``log_level``,  default ``"info"``)
    - ``DisableFastRender bool``     (key ``disable_fast_render``, default false)
* ``New(path string) (*Watcher, error)`` -- loads the file at ``path`` and
  returns a watcher whose ``Current()`` already reflects the file.
* ``(*Watcher).Current() Settings`` -- snapshot, safe to call during a reload.
* ``(*Watcher).Start() error``    -- begins watching; on-disk content change
  reloads the file and updates ``Current()``.
* ``(*Watcher).OnChange(fn func(Settings))`` -- callback fired with the new
  settings after each successful reload.
* ``(*Watcher).Stop()``           -- stops watching and releases resources.

Reload semantics:
  - a content change after ``Start()`` must update ``Current()`` AND fire each
    registered ``OnChange`` callback with the new value (within a bounded wait);
  - a malformed reload must leave the last-good ``Current()`` intact and must
    NOT deliver corrupted data to the callback;
  - after ``Stop()`` further changes are ignored;
  - each watcher owns isolated state.

Verification strategy
---------------------
L1 checks the deliverable files exist, are minimally well-formed, live in the
right package, and that a watching dependency (fsnotify) is wired in go.mod.

L2 does NOT trust the agent's own ``configwatch_test.go``. Each L2 method
writes an *independent* Go test into a fresh temp sub-package inside the repo
module, imports ``github.com/gohugoio/hugo/internal/configwatch``, drives the
watcher by rewriting the watched file's bytes on disk, and asserts on exact
resolved values with bounded polling (no fixed unconditional sleeps used as the
sole synchronization). A stub that hardcodes settings, ignores file changes,
delivers corrupted data, or never stops watching therefore fails.

The final method runs the doc's native acceptance command
``go test ./internal/configwatch/``.
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
PKG_DIR = os.path.join(REPO_DIR, "internal", "configwatch")
MODULE = "github.com/gohugoio/hugo"
IMPORT_PATH = MODULE + "/internal/configwatch"


@pytest.fixture(scope="module", autouse=True)
def _prepare_deps():
    """Ensure module dependencies are downloaded once before any driver runs."""
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
    """Write an independent ``*_test.go`` driver into a fresh sub-package of the
    repo, run ``go test`` on it, and return the CompletedProcess.

    A dedicated directory (its own package) keeps us isolated from whatever the
    agent put in ``configwatch_test.go``, while still living inside the repo
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


# Common preamble imported by every driver. ``time`` and ``sync`` are needed
# for bounded polling and callback synchronization.
_PREAMBLE = (
    'import (\n'
    '\t"os"\n'
    '\t"path/filepath"\n'
    '\t"sync"\n'
    '\t"sync/atomic"\n'
    '\t"testing"\n'
    '\t"time"\n\n'
    '\tconfigwatch "' + IMPORT_PATH + '"\n'
    ')\n\n'
    '// _ keep imports referenced even if a driver omits some.\n'
    'var _ = sync.Mutex{}\n'
    'var _ = atomic.Int32{}\n'
    'var _ = time.Millisecond\n'
    'var _ = os.WriteFile\n'
    'var _ = filepath.Join\n\n'
)


def _write_file_go(var_path, var_content):
    """Return Go code that (re)writes ``var_path`` with the bytes in
    ``var_content`` Go variable, failing the test on error."""
    return (
        '\tif err := os.WriteFile(' + var_path + ', []byte(' + var_content + '), 0o644); err != nil {\n'
        '\t\tt.Fatalf("write file: %v", err)\n'
        '\t}\n'
    )


# The watched file uses YAML, matching the doc's scenario notation
# (``log_level: debug``). Underscore keys map to the struct fields.
_CFG_INFO = '"log_level: info\\ndisable_fast_render: false\\n"'
_CFG_DEBUG = '"log_level: debug\\ndisable_fast_render: false\\n"'
_CFG_WARN = '"log_level: warn\\ndisable_fast_render: false\\n"'
_CFG_DISABLE = '"log_level: info\\ndisable_fast_render: true\\n"'
# Deliberately broken YAML/mapping content.
_CFG_BROKEN = '"log_level: [unterminated\\n\\tbad: : :\\n  - : malformed"'


class TestViperConfiguration:
    REPO_DIR = _find_repo_dir("/workspace/hugo")

    # ---------------------------------------------------------------- L1 ----

    def test_package_directory_exists(self):
        """L1: the new internal/configwatch package directory exists."""
        assert os.path.isdir(PKG_DIR), f"missing package dir {PKG_DIR}"

    def test_watcher_source_file_exists(self):
        """L1: configwatch.go exists, is non-trivial, in package configwatch."""
        path = os.path.join(PKG_DIR, "configwatch.go")
        assert os.path.isfile(path), "configwatch.go not created"
        with open(path) as fh:
            content = fh.read()
        assert len(content.strip()) > 100, "configwatch.go looks empty/stub"
        assert "package configwatch" in content, "wrong package declaration"

    def test_agent_test_file_exists(self):
        """L1: the agent's own deterministic unit test file exists."""
        path = os.path.join(PKG_DIR, "configwatch_test.go")
        assert os.path.isfile(path), "configwatch_test.go not created"

    def test_watch_dependency_wired_in(self):
        """L1: a filesystem-watch dependency (fsnotify) is present in go.mod.

        The watcher needs to observe on-disk changes; fsnotify is Hugo's
        established watch backend. (Existence-only L1 check on go.mod text.)
        """
        gomod = os.path.join(REPO_DIR, "go.mod")
        assert os.path.isfile(gomod)
        with open(gomod) as fh:
            mod = fh.read().lower()
        assert "fsnotify" in mod or "viper" in mod, (
            "no file-watching dependency (fsnotify/viper) found in go.mod"
        )

    def test_package_compiles_and_exports_api(self):
        """L1->L2: the package builds and exports Settings, Watcher, New and the
        documented methods (compile-only driver referencing each symbol)."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tdir := t.TempDir()
            \tp := filepath.Join(dir, "settings.yaml")
            \tif err := os.WriteFile(p, []byte("log_level: info\\n"), 0o644); err != nil {
            \t\tt.Fatalf("seed: %v", err)
            \t}
            \tw, err := configwatch.New(p)
            \tif err != nil {
            \t\tt.Fatalf("New returned error: %v", err)
            \t}
            \tif w == nil {
            \t\tt.Fatalf("New returned nil watcher")
            \t}
            \tvar _ configwatch.Settings = w.Current()
            \tw.OnChange(func(s configwatch.Settings) { _ = s })
            \tif err := w.Start(); err != nil {
            \t\tt.Fatalf("Start returned error: %v", err)
            \t}
            \tw.Stop()
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "package failed to compile / missing exported API "
            "(Settings/Watcher/New/Current/Start/OnChange/Stop).\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    # ---------------------------------------------------------------- L2 ----

    def test_new_loads_initial_settings(self):
        """L2: New reads the file -> Current() reflects log_level: debug from it
        (a stub that returns hardcoded defaults fails)."""
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            '\tp := filepath.Join(dir, "settings.yaml")\n'
            + _write_file_go("p", _CFG_DEBUG) +
            '\tw, err := configwatch.New(p)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("New: %v", err)\n'
            '\t}\n'
            '\tdefer w.Stop()\n'
            '\tif got := w.Current().LogLevel; got != "debug" {\n'
            '\t\tt.Errorf("initial LogLevel: got %q want debug", got)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"initial-load scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_defaults_applied(self):
        """L2: a file that omits a key -> that field takes the documented
        default (log_level default "info" when only disable_fast_render set)."""
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            '\tp := filepath.Join(dir, "settings.yaml")\n'
            + _write_file_go("p", '"disable_fast_render: true\\n"') +
            '\tw, err := configwatch.New(p)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("New: %v", err)\n'
            '\t}\n'
            '\tdefer w.Stop()\n'
            '\tcur := w.Current()\n'
            '\tif cur.LogLevel != "info" {\n'
            '\t\tt.Errorf("default LogLevel: got %q want info", cur.LogLevel)\n'
            '\t}\n'
            '\tif cur.DisableFastRender != true {\n'
            '\t\tt.Errorf("DisableFastRender: got %v want true", cur.DisableFastRender)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"defaults scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_bool_field_decodes(self):
        """L2: disable_fast_render: true decodes into DisableFastRender bool
        (a stub ignoring the bool key, or treating it as a string, fails)."""
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            '\tp := filepath.Join(dir, "settings.yaml")\n'
            + _write_file_go("p", _CFG_DISABLE) +
            '\tw, err := configwatch.New(p)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("New: %v", err)\n'
            '\t}\n'
            '\tdefer w.Stop()\n'
            '\tif w.Current().DisableFastRender != true {\n'
            '\t\tt.Errorf("DisableFastRender: got %v want true", w.Current().DisableFastRender)\n'
            '\t}\n'
            '\tif w.Current().LogLevel != "info" {\n'
            '\t\tt.Errorf("LogLevel: got %q want info", w.Current().LogLevel)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"bool-decode scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_reload_updates_current_after_start(self):
        """L2: after Start(), rewriting the file on disk (info -> warn) makes
        Current() reflect "warn" within a bounded poll. A watcher that never
        reloads (ignores file changes) fails.
        """
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            '\tp := filepath.Join(dir, "settings.yaml")\n'
            + _write_file_go("p", _CFG_INFO) +
            '\tw, err := configwatch.New(p)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("New: %v", err)\n'
            '\t}\n'
            '\tdefer w.Stop()\n'
            '\tif w.Current().LogLevel != "info" {\n'
            '\t\tt.Fatalf("precondition LogLevel: got %q want info", w.Current().LogLevel)\n'
            '\t}\n'
            '\tif err := w.Start(); err != nil {\n'
            '\t\tt.Fatalf("Start: %v", err)\n'
            '\t}\n'
            '\t// change the bytes on disk\n'
            + _write_file_go("p", _CFG_WARN) +
            '\tdeadline := time.Now().Add(8 * time.Second)\n'
            '\tfor time.Now().Before(deadline) {\n'
            '\t\tif w.Current().LogLevel == "warn" {\n'
            '\t\t\treturn\n'
            '\t\t}\n'
            '\t\ttime.Sleep(20 * time.Millisecond)\n'
            '\t}\n'
            '\tt.Fatalf("reload did not update Current(): LogLevel still %q want warn", w.Current().LogLevel)\n'
            '}\n'
        )
        proc = _run_driver(src, timeout=600)
        assert proc.returncode == 0, (
            f"reload-updates-current scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_onchange_callback_fires_with_new_settings(self):
        """L2: after Start(), a content change fires the registered OnChange
        callback with the NEW settings (warn). A stub that never invokes the
        callback, or invokes it with stale data, fails.
        """
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            '\tp := filepath.Join(dir, "settings.yaml")\n'
            + _write_file_go("p", _CFG_INFO) +
            '\tw, err := configwatch.New(p)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("New: %v", err)\n'
            '\t}\n'
            '\tdefer w.Stop()\n'
            '\tvar mu sync.Mutex\n'
            '\tvar lastLevel string\n'
            '\tvar calls int32\n'
            '\tw.OnChange(func(s configwatch.Settings) {\n'
            '\t\tatomic.AddInt32(&calls, 1)\n'
            '\t\tmu.Lock()\n'
            '\t\tlastLevel = s.LogLevel\n'
            '\t\tmu.Unlock()\n'
            '\t})\n'
            '\tif err := w.Start(); err != nil {\n'
            '\t\tt.Fatalf("Start: %v", err)\n'
            '\t}\n'
            + _write_file_go("p", _CFG_WARN) +
            '\tdeadline := time.Now().Add(8 * time.Second)\n'
            '\tfor time.Now().Before(deadline) {\n'
            '\t\tmu.Lock()\n'
            '\t\tll := lastLevel\n'
            '\t\tmu.Unlock()\n'
            '\t\tif atomic.LoadInt32(&calls) > 0 && ll == "warn" {\n'
            '\t\t\treturn\n'
            '\t\t}\n'
            '\t\ttime.Sleep(20 * time.Millisecond)\n'
            '\t}\n'
            '\tmu.Lock()\n'
            '\tll := lastLevel\n'
            '\tmu.Unlock()\n'
            '\tt.Fatalf("OnChange not fired with new settings: calls=%d lastLevel=%q want warn", atomic.LoadInt32(&calls), ll)\n'
            '}\n'
        )
        proc = _run_driver(src, timeout=600)
        assert proc.returncode == 0, (
            f"onchange-callback scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_malformed_reload_preserves_last_good(self):
        """L2: after a good load (warn) and Start(), rewriting with malformed
        content must leave Current() == warn (last good) and must NOT deliver
        corrupted data to the callback. A naive reloader that blindly overwrites
        settings, or fires the callback on parse error, fails.
        """
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            '\tp := filepath.Join(dir, "settings.yaml")\n'
            + _write_file_go("p", _CFG_WARN) +
            '\tw, err := configwatch.New(p)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("New: %v", err)\n'
            '\t}\n'
            '\tdefer w.Stop()\n'
            '\tif w.Current().LogLevel != "warn" {\n'
            '\t\tt.Fatalf("precondition: got %q want warn", w.Current().LogLevel)\n'
            '\t}\n'
            '\tvar mu sync.Mutex\n'
            '\tvar badDelivered bool\n'
            '\tw.OnChange(func(s configwatch.Settings) {\n'
            '\t\tmu.Lock()\n'
            '\t\tif s.LogLevel != "warn" {\n'
            '\t\t\tbadDelivered = true\n'
            '\t\t}\n'
            '\t\tmu.Unlock()\n'
            '\t})\n'
            '\tif err := w.Start(); err != nil {\n'
            '\t\tt.Fatalf("Start: %v", err)\n'
            '\t}\n'
            + _write_file_go("p", _CFG_BROKEN) +
            '\t// Give the watcher time to observe and attempt the bad reload.\n'
            '\tdeadline := time.Now().Add(3 * time.Second)\n'
            '\tfor time.Now().Before(deadline) {\n'
            '\t\ttime.Sleep(50 * time.Millisecond)\n'
            '\t}\n'
            '\tif lvl := w.Current().LogLevel; lvl != "warn" {\n'
            '\t\tt.Fatalf("malformed reload clobbered Current(): got %q want warn (last good)", lvl)\n'
            '\t}\n'
            '\tmu.Lock()\n'
            '\tbd := badDelivered\n'
            '\tmu.Unlock()\n'
            '\tif bd {\n'
            '\t\tt.Fatalf("OnChange delivered corrupted (non-warn) settings on malformed reload")\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src, timeout=600)
        assert proc.returncode == 0, (
            f"malformed-preserves-last-good scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_recovers_after_malformed_then_good(self):
        """L2: malformed reload preserved warn; a subsequent good rewrite
        (debug) must then take effect -- the watcher keeps watching after an
        error rather than wedging."""
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            '\tp := filepath.Join(dir, "settings.yaml")\n'
            + _write_file_go("p", _CFG_WARN) +
            '\tw, err := configwatch.New(p)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("New: %v", err)\n'
            '\t}\n'
            '\tdefer w.Stop()\n'
            '\tif err := w.Start(); err != nil {\n'
            '\t\tt.Fatalf("Start: %v", err)\n'
            '\t}\n'
            + _write_file_go("p", _CFG_BROKEN) +
            '\ttime.Sleep(500 * time.Millisecond)\n'
            + _write_file_go("p", _CFG_DEBUG) +
            '\tdeadline := time.Now().Add(8 * time.Second)\n'
            '\tfor time.Now().Before(deadline) {\n'
            '\t\tif w.Current().LogLevel == "debug" {\n'
            '\t\t\treturn\n'
            '\t\t}\n'
            '\t\ttime.Sleep(20 * time.Millisecond)\n'
            '\t}\n'
            '\tt.Fatalf("watcher did not recover after malformed reload: LogLevel %q want debug", w.Current().LogLevel)\n'
            '}\n'
        )
        proc = _run_driver(src, timeout=600)
        assert proc.returncode == 0, (
            f"recover-after-malformed scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_stop_ignores_further_changes(self):
        """L2: after Stop(), changing the file's bytes must NOT change
        Current(). A watcher that never actually stops fails."""
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            '\tp := filepath.Join(dir, "settings.yaml")\n'
            + _write_file_go("p", _CFG_INFO) +
            '\tw, err := configwatch.New(p)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("New: %v", err)\n'
            '\t}\n'
            '\tif err := w.Start(); err != nil {\n'
            '\t\tt.Fatalf("Start: %v", err)\n'
            '\t}\n'
            '\t// Confirm watching works first (info -> warn), then stop.\n'
            + _write_file_go("p", _CFG_WARN) +
            '\tdeadline := time.Now().Add(8 * time.Second)\n'
            '\tfor time.Now().Before(deadline) && w.Current().LogLevel != "warn" {\n'
            '\t\ttime.Sleep(20 * time.Millisecond)\n'
            '\t}\n'
            '\tif w.Current().LogLevel != "warn" {\n'
            '\t\tt.Fatalf("watcher never picked up first change; cannot test Stop")\n'
            '\t}\n'
            '\tw.Stop()\n'
            '\t// Now change again; Current() must stay warn.\n'
            + _write_file_go("p", _CFG_DEBUG) +
            '\tend := time.Now().Add(3 * time.Second)\n'
            '\tfor time.Now().Before(end) {\n'
            '\t\tif w.Current().LogLevel == "debug" {\n'
            '\t\t\tt.Fatalf("Current() changed to debug after Stop(); watcher still active")\n'
            '\t\t}\n'
            '\t\ttime.Sleep(50 * time.Millisecond)\n'
            '\t}\n'
            '\tif w.Current().LogLevel != "warn" {\n'
            '\t\tt.Fatalf("post-Stop Current(): got %q want warn", w.Current().LogLevel)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src, timeout=600)
        assert proc.returncode == 0, (
            f"stop-ignores-changes scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_watchers_have_isolated_state(self):
        """L2: two watchers over two different files keep independent settings;
        changing one does not affect the other (no shared/global config)."""
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            '\tdir := t.TempDir()\n'
            '\tpA := filepath.Join(dir, "a.yaml")\n'
            '\tpB := filepath.Join(dir, "b.yaml")\n'
            + _write_file_go("pA", _CFG_INFO)
            + _write_file_go("pB", _CFG_DEBUG) +
            '\twA, err := configwatch.New(pA)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("New A: %v", err)\n'
            '\t}\n'
            '\tdefer wA.Stop()\n'
            '\twB, err := configwatch.New(pB)\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("New B: %v", err)\n'
            '\t}\n'
            '\tdefer wB.Stop()\n'
            '\tif wA.Current().LogLevel != "info" {\n'
            '\t\tt.Errorf("A initial: got %q want info", wA.Current().LogLevel)\n'
            '\t}\n'
            '\tif wB.Current().LogLevel != "debug" {\n'
            '\t\tt.Errorf("B initial: got %q want debug", wB.Current().LogLevel)\n'
            '\t}\n'
            '\tif err := wA.Start(); err != nil {\n'
            '\t\tt.Fatalf("Start A: %v", err)\n'
            '\t}\n'
            '\tif err := wB.Start(); err != nil {\n'
            '\t\tt.Fatalf("Start B: %v", err)\n'
            '\t}\n'
            '\t// Change only A -> warn; B must stay debug.\n'
            + _write_file_go("pA", _CFG_WARN) +
            '\tdeadline := time.Now().Add(8 * time.Second)\n'
            '\tfor time.Now().Before(deadline) && wA.Current().LogLevel != "warn" {\n'
            '\t\ttime.Sleep(20 * time.Millisecond)\n'
            '\t}\n'
            '\tif wA.Current().LogLevel != "warn" {\n'
            '\t\tt.Fatalf("A did not reload: got %q want warn", wA.Current().LogLevel)\n'
            '\t}\n'
            '\tif wB.Current().LogLevel != "debug" {\n'
            '\t\tt.Fatalf("B leaked state from A: got %q want debug", wB.Current().LogLevel)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src, timeout=600)
        assert proc.returncode == 0, (
            f"isolated-state scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_native_acceptance_command_passes(self):
        """L2: the exact doc acceptance command runs green:
        ``go test ./internal/configwatch/`` (the agent's own tests)."""
        proc = subprocess.run(
            ["go", "test", "-count=1", "./internal/configwatch/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=900,
        )
        assert proc.returncode == 0, (
            "acceptance command `go test ./internal/configwatch/` failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
