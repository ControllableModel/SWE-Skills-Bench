"""Tests for the `react-hook-form-patterns` skill -- variant ext2.

Skill task (ext2): build an AUTOSAVE-enabled "profile settings" form on top of
the react-hook-form library's own public API, plus a deterministic Jest suite.

A single `useForm` instance models a profile of three fields:
  - displayName (text input)
  - bio         (textarea)
  - theme       (select: light | dark)

The component takes `initialValues` and an `onAutosave(values)` callback. It
must:
  * call `onAutosave` with the FULL current `{displayName, bio, theme}` snapshot
    on every field change -- but NOT on initial mount;
  * show a "Saved" indicator whose text reflects the number of autosaves
    fired (e.g. "Saved (3)");
  * expose a top-level render counter ("Form renders: N") and NOT re-render the
    top-level form body on every keystroke (autosave must use the library's
    value-subscription primitives, not whole-form local state);
  * provide a "Revert" button that restores `initialValues`, and keep the
    autosave snapshot in sync after a revert.

Deliverables verified (REPO_DIR = /workspace/react-hook-form):
  - src/__tests__/examples/profileSettingsForm.tsx       (the feature component)
  - src/__tests__/examples/profileSettingsForm.test.tsx  (the agent's own suite)

Verification strategy:
  * L1  -- the two deliverable TSX files exist and are minimally well-formed
           (real JSX/component, imports from the library source, uses rhf
           primitives, not a stub) and the agent suite declares >= 7 cases.
  * L2  -- run the agent's own native suite via the exact required command
           (`TEST_ENV=web pnpm test -- ... profileSettingsForm.test.tsx`, i.e.
           jest with the repo's web config) and assert it passes with >= 7
           tests, 0 failures.
  * L2  -- INDEPENDENT DRIVER: we write our OWN Jest spec next to the agent's
           component, import the agent's component, and exercise the
           hard-to-fake behaviors directly through rendered DOM:
             - no autosave on mount
             - autosave on edit carries the full latest snapshot
             - multi-field edits fire cumulative snapshots
             - save indicator text reflects the autosave count
             - typing several chars does NOT bump the top-level render count
             - Revert restores initialValues
             - editing after Revert autosaves an initialValues-derived snapshot
           A naive implementation (autosave-on-mount, or whole-form re-render
           per keystroke, or a revert that desyncs the snapshot) fails the
           corresponding driver cases.

All identifiers we rely on (props `initialValues` / `onAutosave`, the texts
"Saved", "Form renders:", the "Revert" button, the field accessible names)
are mandated verbatim by the ext2 requirement document, so a conforming
component must expose them.
"""

import json
import os
import shutil
import subprocess

import pytest

REPO_DIR = "/workspace/react-hook-form"
EXAMPLES_DIR = os.path.join(REPO_DIR, "src", "__tests__", "examples")
COMPONENT_FILE = os.path.join(EXAMPLES_DIR, "profileSettingsForm.tsx")
AGENT_TEST_FILE = os.path.join(EXAMPLES_DIR, "profileSettingsForm.test.tsx")

# Spec we inject ourselves; cleaned up after the run.
DRIVER_BASENAME = "profileSettingsFormDriver.zz.test.tsx"
DRIVER_FILE = os.path.join(EXAMPLES_DIR, DRIVER_BASENAME)

NPM_TIMEOUT = 1800
JEST_TIMEOUT = 600


# --------------------------------------------------------------------------- #
# environment / dependency setup
# --------------------------------------------------------------------------- #
def _have(cmd):
    return shutil.which(cmd) is not None


def _pnpm_cmd():
    """Return a runnable pnpm command prefix, or None."""
    if _have("pnpm"):
        return ["pnpm"]
    if _have("corepack"):
        return ["corepack", "pnpm"]
    return None


@pytest.fixture(scope="module", autouse=True)
def ensure_dependencies():
    """Make sure node_modules is present so the native Jest run can resolve deps."""
    assert os.path.isdir(REPO_DIR), f"REPO_DIR missing: {REPO_DIR}"
    node_modules = os.path.join(REPO_DIR, "node_modules")
    jest_bin = os.path.join(node_modules, ".bin", "jest")
    if os.path.isdir(node_modules) and os.path.exists(jest_bin):
        return  # already installed in the container image

    pnpm = _pnpm_cmd()
    install_attempts = []
    if pnpm is not None:
        install_attempts.append(pnpm + ["install", "--frozen-lockfile"])
        install_attempts.append(pnpm + ["install"])
    if _have("npm"):
        install_attempts.append(["npm", "install", "--legacy-peer-deps"])

    last = None
    for cmd in install_attempts:
        try:
            r = subprocess.run(
                cmd, cwd=REPO_DIR, capture_output=True, text=True, timeout=NPM_TIMEOUT
            )
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            continue
        if r.returncode == 0 and os.path.exists(jest_bin):
            return
        last = f"cmd={' '.join(cmd)} rc={r.returncode}\n{r.stderr[-3000:]}"
    if not os.path.exists(jest_bin):
        pytest.fail(f"could not install JS dependencies; last attempt:\n{last}")


def _run_jest(spec_rel_path, timeout=JEST_TIMEOUT):
    """Run the web Jest project for a single spec file. Returns CompletedProcess.

    Mirrors the repo's native command: `TEST_ENV=web pnpm test -- <path>`, where
    `pnpm test` == `jest --config ./scripts/jest/jest.config.js`.
    """
    env = dict(os.environ)
    env["TEST_ENV"] = "web"
    env["CI"] = "true"
    config = os.path.join("scripts", "jest", "jest.config.js")

    pnpm = _pnpm_cmd()
    candidates = []
    if pnpm is not None:
        candidates.append(
            pnpm + ["jest", "--config", config, "--runTestsByPath", spec_rel_path]
        )
    # direct local jest binary as a robust fallback
    candidates.append(
        [
            os.path.join("node_modules", ".bin", "jest"),
            "--config",
            config,
            "--runTestsByPath",
            spec_rel_path,
        ]
    )
    if _have("npx"):
        candidates.append(
            ["npx", "jest", "--config", config, "--runTestsByPath", spec_rel_path]
        )

    last = None
    for cmd in candidates:
        if cmd[0].endswith("jest") and cmd[0].startswith("node_modules"):
            if not os.path.exists(os.path.join(REPO_DIR, cmd[0])):
                continue
        try:
            last = subprocess.run(
                cmd,
                cwd=REPO_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return last
        except FileNotFoundError:
            continue
    if last is None:
        pytest.fail("no usable jest runner found")
    return last


def _jest_summary(stdout, stderr):
    """Best-effort parse of jest's textual summary -> (passed, failed, total)."""
    blob = (stdout or "") + "\n" + (stderr or "")
    passed = failed = total = None
    for line in blob.splitlines():
        s = line.strip()
        if s.startswith("Tests:"):
            for part in s.replace("Tests:", "").split(","):
                p = part.strip()
                if p.endswith("passed"):
                    passed = int(p.split()[0])
                elif p.endswith("failed"):
                    failed = int(p.split()[0])
                elif p.endswith("total"):
                    total = int(p.split()[0])
    return passed, failed, total


def _run_jest_json(spec_rel_path, timeout=JEST_TIMEOUT):
    """Run jest with --json and parse the structured result for deep assertions."""
    env = dict(os.environ)
    env["TEST_ENV"] = "web"
    env["CI"] = "true"
    config = os.path.join("scripts", "jest", "jest.config.js")

    base = ["--config", config, "--runTestsByPath", spec_rel_path, "--json"]
    pnpm = _pnpm_cmd()
    candidates = []
    if pnpm is not None:
        candidates.append(pnpm + ["jest"] + base)
    candidates.append([os.path.join("node_modules", ".bin", "jest")] + base)
    if _have("npx"):
        candidates.append(["npx", "jest"] + base)

    proc = None
    for cmd in candidates:
        if cmd[0].startswith("node_modules") and not os.path.exists(
            os.path.join(REPO_DIR, cmd[0])
        ):
            continue
        try:
            proc = subprocess.run(
                cmd,
                cwd=REPO_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            break
        except FileNotFoundError:
            continue
    if proc is None:
        pytest.fail("no usable jest runner found")

    out = proc.stdout or ""
    start = out.find("{")
    end = out.rfind("}")
    parsed = None
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(out[start : end + 1])
        except json.JSONDecodeError:
            parsed = None
    return proc, parsed


# --------------------------------------------------------------------------- #
# Our independent driver spec.
# It imports the agent's component and validates the gameable behaviors.
# Identifiers used are all mandated by the ext2 requirement document.
# --------------------------------------------------------------------------- #
DRIVER_SPEC = r"""
import * as React from 'react';
import {
  render,
  screen,
  fireEvent,
  waitFor,
} from '@testing-library/react';

import * as Mod from './profileSettingsForm';

// Resolve the exported profile-form component regardless of its name.
function resolveComponent(): React.ComponentType<any> {
  const m: any = Mod as any;
  if (typeof m.default === 'function') return m.default;
  const named = [
    'ProfileSettingsForm',
    'ProfileForm',
    'ProfileSettings',
    'SettingsForm',
    'Form',
  ];
  for (const n of named) {
    if (typeof m[n] === 'function') return m[n];
  }
  for (const k of Object.keys(m)) {
    if (typeof m[k] === 'function') return m[k];
  }
  throw new Error('could not resolve profile settings form component from module');
}

const ProfileForm = resolveComponent();

const INITIAL = { displayName: 'Ada', bio: 'hello world', theme: 'light' };

// ---- field resolvers leaning only on requirement-mandated affordances ----
// Fields must be queryable by accessible name / data-testid / role+name.

function findField(reList: RegExp[]): HTMLElement {
  // try label, then role textbox/combobox, then name/testid attribute.
  for (const re of reList) {
    const byLabel = screen.queryByLabelText(re);
    if (byLabel) return byLabel as HTMLElement;
  }
  for (const re of reList) {
    const byTb = screen.queryByRole('textbox', { name: re });
    if (byTb) return byTb as HTMLElement;
  }
  for (const re of reList) {
    const byCb = screen.queryByRole('combobox', { name: re });
    if (byCb) return byCb as HTMLElement;
  }
  for (const re of reList) {
    const el = Array.from(
      document.querySelectorAll('input, textarea, select'),
    ).find((node) => {
      const hay = [
        node.getAttribute('name') || '',
        node.getAttribute('aria-label') || '',
        node.getAttribute('data-testid') || '',
        node.getAttribute('placeholder') || '',
      ]
        .join(' ')
        .toLowerCase();
      return re.test(hay);
    });
    if (el) return el as HTMLElement;
  }
  throw new Error('field not found for ' + reList.map((r) => r.source).join('|'));
}

function getDisplayName(): HTMLInputElement {
  return findField([/display\s*name/i, /^name$/i, /displayname/i]) as HTMLInputElement;
}
function getBio(): HTMLTextAreaElement {
  return findField([/bio/i]) as HTMLTextAreaElement;
}
function getTheme(): HTMLSelectElement {
  return findField([/theme/i]) as HTMLSelectElement;
}

function fieldValue(el: HTMLElement): string {
  return (el as HTMLInputElement).value;
}

function setText(el: HTMLElement, value: string) {
  fireEvent.change(el, { target: { value } });
}

function readFormRenders(): number {
  const node = screen.getByText(/form renders:/i);
  const m = (node.textContent || '').match(/form renders:\s*(\d+)/i);
  if (!m) throw new Error('render counter not found: ' + node.textContent);
  return Number(m[1]);
}

// last value-snapshot the component passed to onAutosave.
function lastSnapshot(mock: jest.Mock): any {
  const calls = mock.mock.calls;
  return calls[calls.length - 1][0];
}

function makeOnAutosave(): jest.Mock {
  return jest.fn();
}

describe('profileSettingsForm driver (independent)', () => {
  test('no autosave on mount', () => {
    const onAutosave = makeOnAutosave();
    render(<ProfileForm initialValues={INITIAL} onAutosave={onAutosave} />);
    // Initial render must NOT fire autosave before any user edit.
    expect(onAutosave).not.toHaveBeenCalled();
    // Initial values must be reflected in the controls.
    expect(fieldValue(getDisplayName())).toBe('Ada');
    expect(fieldValue(getBio())).toBe('hello world');
    expect(fieldValue(getTheme())).toBe('light');
  });

  test('autosave on edit carries the full latest snapshot', async () => {
    const onAutosave = makeOnAutosave();
    render(<ProfileForm initialValues={INITIAL} onAutosave={onAutosave} />);
    setText(getDisplayName(), 'Grace');
    await waitFor(() => expect(onAutosave).toHaveBeenCalled());
    const snap = lastSnapshot(onAutosave);
    // full snapshot: edited field plus the untouched ones.
    expect(snap.displayName).toBe('Grace');
    expect(snap.bio).toBe('hello world');
    expect(snap.theme).toBe('light');
  });

  test('multiple fields fire cumulative snapshots', async () => {
    const onAutosave = makeOnAutosave();
    render(<ProfileForm initialValues={INITIAL} onAutosave={onAutosave} />);

    setText(getBio(), 'new bio');
    await waitFor(() => {
      const s = lastSnapshot(onAutosave);
      expect(s.bio).toBe('new bio');
    });
    let snap = lastSnapshot(onAutosave);
    expect(snap.displayName).toBe('Ada');
    expect(snap.bio).toBe('new bio');
    expect(snap.theme).toBe('light');

    setText(getTheme(), 'dark');
    await waitFor(() => {
      const s = lastSnapshot(onAutosave);
      expect(s.theme).toBe('dark');
    });
    snap = lastSnapshot(onAutosave);
    // cumulative: the earlier bio edit must still be present.
    expect(snap.displayName).toBe('Ada');
    expect(snap.bio).toBe('new bio');
    expect(snap.theme).toBe('dark');
  });

  test('save indicator reflects the autosave count', async () => {
    const onAutosave = makeOnAutosave();
    render(<ProfileForm initialValues={INITIAL} onAutosave={onAutosave} />);
    // edit three distinct times.
    setText(getDisplayName(), 'A');
    setText(getDisplayName(), 'Ab');
    setText(getBio(), 'changed');
    await waitFor(() => {
      // the visible status text must encode how many saves fired.
      const status = screen.getByText(/saved/i);
      expect(status).toBeInTheDocument();
    });
    const callCount = onAutosave.mock.calls.length;
    expect(callCount).toBeGreaterThanOrEqual(3);
    // the status text must contain the same count the callback was invoked with.
    const status = screen.getByText(/saved/i);
    const m = (status.textContent || '').match(/(\d+)/);
    expect(m).not.toBeNull();
    expect(Number((m as RegExpMatchArray)[1])).toBe(callCount);
  });

  test('typing several chars does not bump the top-level render count', () => {
    const onAutosave = makeOnAutosave();
    render(<ProfileForm initialValues={INITIAL} onAutosave={onAutosave} />);
    const before = readFormRenders();
    const dn = getDisplayName();
    for (const v of ['Ada1', 'Ada12', 'Ada123', 'Ada1234']) {
      setText(dn, v);
    }
    // value updated + autosave fired ...
    expect(fieldValue(dn)).toBe('Ada1234');
    expect(onAutosave.mock.calls.length).toBeGreaterThanOrEqual(4);
    // ... but the top-level form body must NOT re-render per keystroke.
    const after = readFormRenders();
    expect(after).toBe(before);
  });

  test('Revert restores initialValues', () => {
    const onAutosave = makeOnAutosave();
    render(<ProfileForm initialValues={INITIAL} onAutosave={onAutosave} />);
    setText(getDisplayName(), 'Edited');
    setText(getBio(), 'edited bio');
    setText(getTheme(), 'dark');
    expect(fieldValue(getDisplayName())).toBe('Edited');

    const revert = screen.getByRole('button', { name: /revert/i });
    fireEvent.click(revert);

    expect(fieldValue(getDisplayName())).toBe('Ada');
    expect(fieldValue(getBio())).toBe('hello world');
    expect(fieldValue(getTheme())).toBe('light');
  });

  test('editing after Revert autosaves an initialValues-derived snapshot', async () => {
    const onAutosave = makeOnAutosave();
    render(<ProfileForm initialValues={INITIAL} onAutosave={onAutosave} />);
    // make edits then revert.
    setText(getDisplayName(), 'Throwaway');
    setText(getBio(), 'throwaway bio');
    const revert = screen.getByRole('button', { name: /revert/i });
    fireEvent.click(revert);

    onAutosave.mockClear();

    // a new edit must autosave a snapshot derived from initialValues, not the
    // discarded edits (revert must not desync the autosave snapshot).
    setText(getDisplayName(), 'Linus');
    await waitFor(() => expect(onAutosave).toHaveBeenCalled());
    const snap = lastSnapshot(onAutosave);
    expect(snap.displayName).toBe('Linus');
    expect(snap.bio).toBe('hello world'); // reverted, not 'throwaway bio'
    expect(snap.theme).toBe('light');
  });
});
"""


# --------------------------------------------------------------------------- #
# Test class
# --------------------------------------------------------------------------- #
class TestReactHookFormPatterns:
    REPO_DIR = "/workspace/react-hook-form"

    # ----------------------- L1: deliverables exist ----------------------- #
    def test_component_file_exists(self):
        """L1: the profile settings form component file is created at the required path."""
        assert os.path.isfile(COMPONENT_FILE), f"missing {COMPONENT_FILE}"

    def test_agent_test_file_exists(self):
        """L1: the agent's deterministic Jest suite file is created."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing {AGENT_TEST_FILE}"

    def test_component_is_real_tsx(self):
        """L1: component is real TSX -- JSX, imports the library source, uses rhf, not a stub."""
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        assert len(src) > 300, "component file is suspiciously small"
        # imports from the library's own source (relative ../../ entry points)
        assert "import" in src and ".." in src, (
            "component must import from library source"
        )
        # autosave must use the library's value-subscription primitives, not
        # whole-form local state -- so a real solution references one of these.
        assert any(
            tok in src
            for tok in ("useWatch", "useForm", "useController", "Controller", "watch")
        ), "component must use react-hook-form primitives"
        # actually renders JSX
        assert "return" in src and ("<" in src and ("/>" in src or "</" in src)), (
            "component must render JSX"
        )

    def test_component_models_three_fields(self):
        """L1: component references the three required field names + the onAutosave prop."""
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        for field in ("displayName", "bio", "theme"):
            assert field in src, f"component must model the '{field}' field"
        assert "onAutosave" in src, "component must accept an onAutosave callback prop"
        assert "initialValues" in src, "component must accept an initialValues prop"

    def test_agent_suite_has_enough_cases(self):
        """L1: the agent suite declares at least 7 test cases (criteria 1-7)."""
        with open(AGENT_TEST_FILE, encoding="utf-8") as fh:
            src = fh.read()
        n = src.count("it(") + src.count("test(")
        assert n >= 7, f"agent suite must contain >=7 cases, found {n}"

    # ------------- L2: run the agent's own native suite ------------------- #
    def test_agent_native_suite_passes(self):
        """L2: the agent's profileSettingsForm.test.tsx passes under the required command.

        Mirrors `TEST_ENV=web pnpm test -- src/__tests__/examples/profileSettingsForm.test.tsx`.
        """
        rel = os.path.join(
            "src", "__tests__", "examples", "profileSettingsForm.test.tsx"
        )
        proc = _run_jest(rel)
        passed, failed, total = _jest_summary(proc.stdout, proc.stderr)
        assert proc.returncode == 0, (
            "agent native suite failed.\n"
            f"summary passed={passed} failed={failed} total={total}\n"
            f"STDOUT(tail):\n{proc.stdout[-3000:]}\n"
            f"STDERR(tail):\n{proc.stderr[-3000:]}"
        )
        assert total is not None and total >= 7, (
            f"expected >=7 tests in agent suite, parsed total={total}\n"
            f"{proc.stderr[-1500:]}"
        )
        assert failed in (0, None), f"agent suite reported failures: {failed}"

    # ------------- L2: independent driver (discriminative core) ----------- #
    def _ensure_driver(self):
        assert os.path.isdir(EXAMPLES_DIR), f"examples dir missing: {EXAMPLES_DIR}"
        with open(DRIVER_FILE, "w", encoding="utf-8") as fh:
            fh.write(DRIVER_SPEC)

    def _run_driver_once(self):
        """Run the independent driver once, cache parsed per-test results on the class."""
        if getattr(self.__class__, "_driver_results", None) is not None:
            return self.__class__._driver_results
        self._ensure_driver()
        rel = os.path.join("src", "__tests__", "examples", DRIVER_BASENAME)
        try:
            proc, parsed = _run_jest_json(rel)
        finally:
            try:
                os.remove(DRIVER_FILE)
            except OSError:
                pass
        results = {}
        if parsed and isinstance(parsed.get("testResults"), list):
            for fileres in parsed["testResults"]:
                for assertion in fileres.get("assertionResults", []):
                    results[assertion.get("title", "")] = assertion.get("status")
        self.__class__._driver_results = {
            "proc": proc,
            "parsed": parsed,
            "byname": results,
        }
        return self.__class__._driver_results

    def _assert_driver_case(self, title_substr):
        data = self._run_driver_once()
        byname = data["byname"]
        proc = data["proc"]
        # If JSON parsing failed entirely, fall back to overall returncode.
        if not byname:
            assert proc.returncode == 0, (
                "driver suite did not produce parseable results and failed.\n"
                f"STDOUT(tail):\n{proc.stdout[-3000:]}\n"
                f"STDERR(tail):\n{proc.stderr[-3000:]}"
            )
            return
        matches = {
            t: s for t, s in byname.items() if title_substr.lower() in t.lower()
        }
        assert matches, (
            f"driver case matching '{title_substr}' not found among "
            f"{list(byname.keys())}\nSTDERR(tail):\n{proc.stderr[-1500:]}"
        )
        for title, status in matches.items():
            assert status == "passed", (
                f"driver case '{title}' status={status}\n"
                f"STDERR(tail):\n{proc.stderr[-2500:]}"
            )

    def test_driver_no_autosave_on_mount(self):
        """L2(driver): rendering with initialValues must NOT call onAutosave."""
        self._assert_driver_case("no autosave on mount")

    def test_driver_autosave_full_snapshot(self):
        """L2(driver): editing displayName autosaves the full latest snapshot."""
        self._assert_driver_case("autosave on edit carries the full latest snapshot")

    def test_driver_multiple_fields_cumulative(self):
        """L2(driver): editing bio then theme fires cumulative snapshots."""
        self._assert_driver_case("multiple fields fire cumulative snapshots")

    def test_driver_save_indicator_count(self):
        """L2(driver): the visible save indicator text reflects the autosave count."""
        self._assert_driver_case("save indicator reflects the autosave count")

    def test_driver_render_isolation(self):
        """L2(driver): typing several chars must NOT bump the top-level render count."""
        self._assert_driver_case("does not bump the top-level render count")

    def test_driver_revert_restores_initial(self):
        """L2(driver): clicking Revert restores all fields to initialValues."""
        self._assert_driver_case("Revert restores initialValues")

    def test_driver_autosave_consistent_after_revert(self):
        """L2(driver): editing after Revert autosaves an initialValues-derived snapshot."""
        self._assert_driver_case("editing after Revert autosaves")
