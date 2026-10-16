"""Tests for the ``viper-configuration`` skill (variant ext10).

The task asks the agent to add a self-contained Output Formats configuration
loader at package ``internal/outputconf`` for Hugo. The loader decodes a
configured set of output formats and a per-page-kind output mapping into typed
structs and string slices:

* ``OutputConfig.Outputs`` is a ``map[string][]string`` keyed ``outputs`` —
  per page kind (``home``, ``page``, ...) to the list of format names.
* ``OutputConfig.Formats`` is a ``[]Format`` keyed ``output_formats`` — custom
  format definitions where ``Format`` carries ``Name`` (key ``name``),
  ``MediaType`` (key ``media_type``) and ``BaseName`` (key ``base_name``).
* A format list may be supplied either as a real list (``["html","rss"]``) or
  as a single comma-separated string (``"html,amp"``); both must decode to the
  equivalent ``[]string``.
* ``Load(opts Options) (*OutputConfig, error)`` builds its config
  independently per call; a missing / absent file is NOT an error and yields an
  empty config; a present-but-unparseable file IS an error.

Verification strategy
---------------------
L1 checks the deliverable files exist, are minimally well-formed, declare the
right package, and that a config dependency was wired into ``go.mod``.

L2 does NOT trust the agent's own ``outputconf_test.go``. Instead each L2
method writes an *independent* Go test into a fresh temp sub-package inside the
repo, imports ``github.com/gohugoio/hugo/internal/outputconf``, calls
``outputconf.Load`` with controlled config files, and asserts the exact
resolved struct values / slices mandated by each requirement scenario. A
stubbed / hardcoded / keyword / list-only (ignoring the comma-string case)
solution therefore cannot pass. The final method drives the native acceptance
command ``go test ./internal/outputconf/``.
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
PKG_DIR = os.path.join(REPO_DIR, "internal", "outputconf")
MODULE = "github.com/gohugoio/hugo"
IMPORT_PATH = MODULE + "/internal/outputconf"


@pytest.fixture(scope="module", autouse=True)
def _prepare_deps():
    """Ensure module dependencies are downloaded once (incl. any new dep the
    loader pulls in)."""
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
    placed in outputconf_test.go, while still living inside the repo module so
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
    '\toutputconf "' + IMPORT_PATH + '"\n'
    ')\n\n'
)


def _write_cfg(tmp_subname, body):
    """Return Go code that writes a config file into a temp dir at runtime.

    The body is the file content. Returns a Go snippet creating variable
    ``cfgPath`` (and the enclosing temp ``dir``).
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
        """L1: the new internal/outputconf package directory exists."""
        assert os.path.isdir(PKG_DIR), f"missing package dir {PKG_DIR}"

    def test_loader_source_file_exists(self):
        """L1: outputconf.go exists, is non-trivial, and declares the package."""
        path = os.path.join(PKG_DIR, "outputconf.go")
        assert os.path.isfile(path), "outputconf.go not created"
        with open(path) as fh:
            content = fh.read()
        assert len(content.strip()) > 100, "outputconf.go looks empty/stub"
        assert "package outputconf" in content, "wrong package declaration"

    def test_agent_test_file_exists(self):
        """L1: the agent's own deterministic unit test file exists."""
        path = os.path.join(PKG_DIR, "outputconf_test.go")
        assert os.path.isfile(path), "outputconf_test.go not created"

    def test_config_dependency_wired_in(self):
        """L1: a decoding/config dependency was added to go.mod (the loader's
        backbone for the list-vs-comma-string + struct decoding)."""
        gomod = os.path.join(REPO_DIR, "go.mod")
        assert os.path.isfile(gomod)
        with open(gomod) as fh:
            mod = fh.read().lower()
        # The doc says "add the dependency required to implement the loader".
        # Viper (and its mapstructure/cast helpers) is the natural backbone for
        # decoding the underscore-named keys and the comma-string slice case.
        assert ("viper" in mod or "mapstructure" in mod), (
            "no config/decoding dependency (viper/mapstructure) present in go.mod"
        )

    def test_package_compiles_and_exports_api(self):
        """L1->L2: package builds and exports OutputConfig, Format, Options and
        Load with the documented signatures (compile-only driver + empty Load)."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tvar _ outputconf.OutputConfig
            \tvar _ outputconf.Format
            \tvar _ outputconf.Options
            \tc, err := outputconf.Load(outputconf.Options{})
            \tif err != nil {
            \t\tt.Fatalf("Load returned error on empty options: %v", err)
            \t}
            \tif c == nil {
            \t\tt.Fatalf("Load returned nil *OutputConfig")
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "package failed to compile / missing exported API "
            "(OutputConfig/Format/Options/Load returning *OutputConfig).\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    # ---------------------------------------------------------------- L2 ----

    def test_empty_when_no_path(self):
        """L2: no path supplied -> Load succeeds, err==nil, and the result is an
        empty config (no formats, no output mappings)."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tc, err := outputconf.Load(outputconf.Options{})
            \tif err != nil {
            \t\tt.Fatalf("empty options must not error, got: %v", err)
            \t}
            \tif len(c.Formats) != 0 {
            \t\tt.Errorf("expected no formats, got %d", len(c.Formats))
            \t}
            \tif len(c.Outputs) != 0 {
            \t\tt.Errorf("expected no outputs, got %d", len(c.Outputs))
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"empty-config scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_outputs_list_decodes(self):
        """L2: outputs.home given as a real list ["html","rss","json"] decodes
        into the equivalent []string in order."""
        cfg = _write_cfg(
            "config.toml",
            '[outputs]\nhome = ["html", "rss", "json"]\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tc, err := outputconf.Load(outputconf.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tgot := c.Outputs["home"]\n'
            '\twant := []string{"html", "rss", "json"}\n'
            '\tif len(got) != len(want) {\n'
            '\t\tt.Fatalf("outputs[home] len: got %v want %v", got, want)\n'
            '\t}\n'
            '\tfor i := range want {\n'
            '\t\tif got[i] != want[i] {\n'
            '\t\t\tt.Errorf("outputs[home][%d]: got %q want %q", i, got[i], want[i])\n'
            '\t\t}\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "outputs-list scenario failed. (Note: Options must expose a "
            "config-file path field; the test uses `ConfigFile`.)\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_outputs_comma_string_decodes_to_slice(self):
        """L2: outputs.page given as a single comma-separated string "html,amp"
        MUST decode to []string{"html","amp"}. A naive list-only loader fails."""
        cfg = _write_cfg(
            "config.toml",
            '[outputs]\npage = "html,amp"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tc, err := outputconf.Load(outputconf.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tgot := c.Outputs["page"]\n'
            '\twant := []string{"html", "amp"}\n'
            '\tif len(got) != len(want) {\n'
            '\t\tt.Fatalf("comma-string must split into a slice: got %#v want %v", got, want)\n'
            '\t}\n'
            '\tfor i := range want {\n'
            '\t\tif got[i] != want[i] {\n'
            '\t\t\tt.Errorf("outputs[page][%d]: got %q want %q", i, got[i], want[i])\n'
            '\t\t}\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "comma-string-to-slice scenario failed (a list-only decoder cannot "
            "pass this).\nstdout={}\nstderr={}".format(proc.stdout, proc.stderr)
        )

    def test_output_formats_underscore_keys_decode(self):
        """L2: an output_formats entry with name/media_type/base_name decodes
        into a Format with all three underscore-named fields populated."""
        cfg = _write_cfg(
            "config.toml",
            '[[output_formats]]\n'
            'name = "bibtex"\n'
            'media_type = "application/x-bibtex"\n'
            'base_name = "index"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tc, err := outputconf.Load(outputconf.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\tif len(c.Formats) != 1 {\n'
            '\t\tt.Fatalf("expected exactly 1 format, got %d (%#v)", len(c.Formats), c.Formats)\n'
            '\t}\n'
            '\tf := c.Formats[0]\n'
            '\tif f.Name != "bibtex" {\n'
            '\t\tt.Errorf("Name: got %q want bibtex", f.Name)\n'
            '\t}\n'
            '\tif f.MediaType != "application/x-bibtex" {\n'
            '\t\tt.Errorf("MediaType (key media_type): got %q want application/x-bibtex", f.MediaType)\n'
            '\t}\n'
            '\tif f.BaseName != "index" {\n'
            '\t\tt.Errorf("BaseName (key base_name): got %q want index", f.BaseName)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            "output_formats underscore-key scenario failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_combined_outputs_and_formats(self):
        """L2: a file mixing a list output, a comma-string output, and a custom
        format decodes every part simultaneously and independently."""
        cfg = _write_cfg(
            "config.toml",
            '[outputs]\n'
            'home = ["html", "rss"]\n'
            'page = "html,json,amp"\n\n'
            '[[output_formats]]\n'
            'name = "calendar"\n'
            'media_type = "text/calendar"\n'
            'base_name = "events"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tc, err := outputconf.Load(outputconf.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load: %v", err)\n'
            '\t}\n'
            '\thome := c.Outputs["home"]\n'
            '\tif len(home) != 2 || home[0] != "html" || home[1] != "rss" {\n'
            '\t\tt.Errorf("outputs[home]: got %#v want [html rss]", home)\n'
            '\t}\n'
            '\tpage := c.Outputs["page"]\n'
            '\tif len(page) != 3 || page[0] != "html" || page[1] != "json" || page[2] != "amp" {\n'
            '\t\tt.Errorf("outputs[page] (comma string): got %#v want [html json amp]", page)\n'
            '\t}\n'
            '\tif len(c.Formats) != 1 {\n'
            '\t\tt.Fatalf("formats len: got %d want 1", len(c.Formats))\n'
            '\t}\n'
            '\tf := c.Formats[0]\n'
            '\tif f.Name != "calendar" || f.MediaType != "text/calendar" || f.BaseName != "events" {\n'
            '\t\tt.Errorf("format: got %#v want {calendar text/calendar events}", f)\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"combined scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_missing_file_is_not_an_error(self):
        """L2: a path to a nonexistent file -> Load succeeds with an empty
        config and a nil error."""
        src = _PREAMBLE + textwrap.dedent(
            '''
            func TestDriver(t *testing.T) {
            \tmissing := filepath.Join(t.TempDir(), "does-not-exist.toml")
            \tc, err := outputconf.Load(outputconf.Options{ConfigFile: missing})
            \tif err != nil {
            \t\tt.Fatalf("missing config file must not error, got: %v", err)
            \t}
            \tif c == nil {
            \t\tt.Fatalf("Load returned nil *OutputConfig")
            \t}
            \tif len(c.Outputs) != 0 || len(c.Formats) != 0 {
            \t\tt.Errorf("missing file must yield empty config, got outputs=%d formats=%d", len(c.Outputs), len(c.Formats))
            \t}
            }
            '''
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"missing-file scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_unparseable_file_errors(self):
        """L2: a present but malformed config file -> Load returns a non-nil
        error (silently swallowing the parse failure must fail this)."""
        cfg = _write_cfg("config.toml", 'outputs = = = "broken [[[\n')
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\t_, err := outputconf.Load(outputconf.Options{ConfigFile: cfgPath})\n'
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
        """L2: two independent Load calls in the same process produce
        independent results and do not contaminate one another. Load a file
        with formats, then Load empty options -> the second must be empty."""
        cfg = _write_cfg(
            "config.toml",
            '[outputs]\nhome = ["html", "rss"]\n\n'
            '[[output_formats]]\nname = "atom"\nmedia_type = "application/atom+xml"\nbase_name = "feed"\n',
        )
        src = _PREAMBLE + (
            'func TestDriver(t *testing.T) {\n'
            + cfg +
            '\tc1, err := outputconf.Load(outputconf.Options{ConfigFile: cfgPath})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load #1: %v", err)\n'
            '\t}\n'
            '\tif len(c1.Formats) != 1 || len(c1.Outputs) != 1 {\n'
            '\t\tt.Fatalf("load #1 unexpected: formats=%d outputs=%d", len(c1.Formats), len(c1.Outputs))\n'
            '\t}\n'
            '\t// A second, independent load with no file must NOT inherit\n'
            '\t// load #1\'s formats/outputs (no shared/global state).\n'
            '\tc2, err := outputconf.Load(outputconf.Options{})\n'
            '\tif err != nil {\n'
            '\t\tt.Fatalf("Load #2: %v", err)\n'
            '\t}\n'
            '\tif len(c2.Formats) != 0 || len(c2.Outputs) != 0 {\n'
            '\t\tt.Errorf("state leaked between Load calls: formats=%d outputs=%d (want 0/0)", len(c2.Formats), len(c2.Outputs))\n'
            '\t}\n'
            '}\n'
        )
        proc = _run_driver(src)
        assert proc.returncode == 0, (
            f"isolation scenario failed.\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )

    def test_native_acceptance_command_passes(self):
        """L2: the exact acceptance command runs green:
        ``go test ./internal/outputconf/`` (the agent's own tests)."""
        proc = subprocess.run(
            ["go", "test", "-count=1", "./internal/outputconf/"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, (
            "acceptance command `go test ./internal/outputconf/` failed.\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
