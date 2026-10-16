"""Tests for the `react-hook-form-patterns` skill -- variant ext7.

Skill task (ext7): build a render-isolated "account edit" form on top of the
react-hook-form library's own public API that tracks which fields the user
actually changed, submits ONLY the changed subset, isolates the dirty-state UI
from input re-renders, and re-baselines after a successful save. Plus a
deterministic Jest suite pinning that behavior down.

Deliverables verified (REPO_DIR = /workspace/react-hook-form):
  - src/__tests__/examples/accountEditForm.tsx       (the feature component)
  - src/__tests__/examples/accountEditForm.test.tsx  (the agent's own Jest suite)

What this pytest file does:
  * L1  -- the two deliverable TSX files exist and are minimally well-formed
           (real JSX/component, imports the library's own source, uses RHF
           dirty-state primitives, not a stub).
  * L2  -- runs the agent's own native suite via the exact required command
           (`TEST_ENV=web pnpm test -- ...accountEditForm.test.tsx`, which the
           repo maps to `jest --config ./scripts/jest/jest.config.js`) and
           asserts the mandated number of cases pass.
  * L2  -- INDEPENDENT DRIVER: writes our own Jest spec next to the component,
           imports the agent's accountEditForm component, and exercises the
           hard-to-fake behaviors directly through rendered DOM:
             - initially clean: count 0, no-changes indicator, Save inert
             - becomes dirty: editing two fields -> `Changed: 2`, unsaved UI
             - revert-by-retyping returns the changed count to 0
             - SELECTIVE PAYLOAD: changing only email+newsletter submits
               exactly {email, newsletter}, no other keys (a full-form submit
               fails this)
             - baseline reset after save: dirty count returns to 0 and saved
               values no longer count as changed
             - RENDER ISOLATION: typing into firstName updates the dirty
               indicator but must NOT bump the top-level form render count
               (a whole-form-re-render-per-keystroke impl fails this)

The texts we query ("No changes"/"Unsaved changes", "Changed: N",
"Form renders: N", a "Save" button, the four field controls) are mandated
verbatim by the requirement document, so a conforming component must expose
them. A naive implementation that submits the whole form, or re-renders
everything on each keystroke, must fail the selective-payload and/or
isolation cases.
"""

import json
import os
import shutil
import subprocess

import pytest

REPO_DIR = "/workspace/react-hook-form"
EXAMPLES_DIR = os.path.join(REPO_DIR, "src", "__tests__", "examples")
COMPONENT_FILE = os.path.join(EXAMPLES_DIR, "accountEditForm.tsx")
AGENT_TEST_FILE = os.path.join(EXAMPLES_DIR, "accountEditForm.test.tsx")

# Spec we inject ourselves; cleaned up after the run.
DRIVER_BASENAME = "accountEditFormDriver.zz.test.tsx"
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

    Mirrors the repo's native command `TEST_ENV=web pnpm test -- <path>`,
    where `test` == `jest --config ./scripts/jest/jest.config.js`.
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
# Identifiers used are all mandated by the requirement document.
# --------------------------------------------------------------------------- #
DRIVER_SPEC = r"""
import * as React from 'react';
import {
  render,
  screen,
  fireEvent,
  waitFor,
} from '@testing-library/react';

import * as Mod from './accountEditForm';

// Resolve the exported account-edit-form component regardless of its name.
function resolveComponent(): React.ComponentType<any> {
  const m: any = Mod as any;
  if (typeof m.default === 'function') return m.default;
  const named = [
    'AccountEditForm',
    'AccountForm',
    'EditForm',
    'AccountEdit',
    'Form',
  ];
  for (const n of named) {
    if (typeof m[n] === 'function') return m[n];
  }
  for (const k of Object.keys(m)) {
    if (typeof m[k] === 'function') return m[k];
  }
  throw new Error('could not resolve account edit form component from module');
}

const AccountEditForm = resolveComponent();

const DEFAULTS = {
  firstName: 'Ada',
  lastName: 'Lovelace',
  email: 'ada@example.com',
  newsletter: false,
};

// ---------- locators leaning only on mandated, stable affordances ----------

function findField(re: RegExp): HTMLInputElement {
  // Prefer accessible label / role; fall back to name attribute.
  const byLabel = screen.queryByLabelText(re) as HTMLInputElement | null;
  if (byLabel) return byLabel;
  const byName = document.querySelector(
    `input[name="${re.source.replace(/[^a-zA-Z]/g, '')}"]`,
  ) as HTMLInputElement | null;
  if (byName) return byName;
  // last resort: scan inputs by associated text / placeholder / name
  const inputs = Array.from(
    document.querySelectorAll('input'),
  ) as HTMLInputElement[];
  const hit = inputs.find((i) => {
    const hay = [
      i.getAttribute('name') || '',
      i.getAttribute('aria-label') || '',
      i.getAttribute('placeholder') || '',
      i.getAttribute('data-testid') || '',
    ]
      .join(' ')
      .toLowerCase();
    return re.test(hay);
  });
  if (hit) return hit;
  throw new Error('field not found for ' + re);
}

function firstName() {
  return findField(/firstname/i);
}
function lastName() {
  return findField(/lastname/i);
}
function emailField() {
  return findField(/email/i);
}
function newsletter(): HTMLInputElement {
  const byLabel = screen.queryByLabelText(/newsletter/i) as HTMLInputElement | null;
  if (byLabel) return byLabel;
  const checks = Array.from(
    document.querySelectorAll('input[type="checkbox"]'),
  ) as HTMLInputElement[];
  if (checks.length) return checks[0];
  throw new Error('newsletter checkbox not found');
}

function saveButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: /save/i }) as HTMLButtonElement;
}

function readChangedCount(): number {
  // Requirement: dirty indicator shows count, e.g. "Changed: 2".
  const node = screen.getByText(/changed:\s*\d+/i);
  const m = (node.textContent || '').match(/changed:\s*(\d+)/i);
  if (!m) throw new Error('changed count text not found: ' + node.textContent);
  return Number(m[1]);
}

function hasUnsavedIndicator(): boolean {
  return !!screen.queryByText(/unsaved changes/i);
}

function hasNoChangesIndicator(): boolean {
  return !!screen.queryByText(/no changes/i);
}

function readFormRenders(): number {
  // Requirement: top-level component renders "Form renders: N".
  const node = screen.getByText(/form renders:\s*\d+/i);
  const m = (node.textContent || '').match(/form renders:\s*(\d+)/i);
  if (!m) throw new Error('render counter not found: ' + node.textContent);
  return Number(m[1]);
}

function setText(input: HTMLInputElement, value: string) {
  fireEvent.change(input, { target: { value } });
}

function toggleCheckbox(box: HTMLInputElement) {
  fireEvent.click(box);
}

describe('accountEditForm driver (independent)', () => {
  test('initially clean: count 0, no-changes indicator, save inert', () => {
    const onSubmit = jest.fn();
    render(<AccountEditForm defaultValues={DEFAULTS} onSubmit={onSubmit} />);
    // controls reflect defaults
    expect(firstName().value).toBe('Ada');
    expect(emailField().value).toBe('ada@example.com');
    expect(newsletter().checked).toBe(false);
    // clean state
    expect(readChangedCount()).toBe(0);
    expect(hasNoChangesIndicator()).toBe(true);
    expect(hasUnsavedIndicator()).toBe(false);
    // Save while clean must not invoke onSubmit (disabled OR inert)
    const btn = saveButton();
    if (!btn.disabled) {
      fireEvent.click(btn);
    }
    expect(onSubmit).not.toHaveBeenCalled();
  });

  test('becomes dirty: editing two fields shows Changed: 2 + unsaved', () => {
    render(<AccountEditForm defaultValues={DEFAULTS} onSubmit={jest.fn()} />);
    expect(readChangedCount()).toBe(0);
    setText(firstName(), 'Grace');
    expect(readChangedCount()).toBe(1);
    setText(lastName(), 'Hopper');
    expect(readChangedCount()).toBe(2);
    expect(hasUnsavedIndicator()).toBe(true);
    expect(hasNoChangesIndicator()).toBe(false);
  });

  test('revert-by-retyping returns the changed count to 0', () => {
    render(<AccountEditForm defaultValues={DEFAULTS} onSubmit={jest.fn()} />);
    setText(firstName(), 'Grace');
    expect(readChangedCount()).toBe(1);
    // type the original value back
    setText(firstName(), 'Ada');
    expect(readChangedCount()).toBe(0);
    expect(hasNoChangesIndicator()).toBe(true);
  });

  test('selective payload: changing only email+newsletter submits exactly those', () => {
    const onSubmit = jest.fn();
    render(<AccountEditForm defaultValues={DEFAULTS} onSubmit={onSubmit} />);
    setText(emailField(), 'grace@navy.mil');
    toggleCheckbox(newsletter());
    expect(readChangedCount()).toBe(2);
    fireEvent.click(saveButton());
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const payload = onSubmit.mock.calls[0][0];
    // exactly the changed subset, nothing else
    const keys = Object.keys(payload).sort();
    expect(keys).toEqual(['email', 'newsletter']);
    expect(payload.email).toBe('grace@navy.mil');
    expect(payload.newsletter).toBe(true);
    // unchanged fields must NOT be present in the payload
    expect('firstName' in payload).toBe(false);
    expect('lastName' in payload).toBe(false);
  });

  test('baseline reset after save: saved values no longer count as changed', () => {
    const onSubmit = jest.fn();
    render(<AccountEditForm defaultValues={DEFAULTS} onSubmit={onSubmit} />);
    setText(firstName(), 'Grace');
    setText(emailField(), 'grace@navy.mil');
    expect(readChangedCount()).toBe(2);
    fireEvent.click(saveButton());
    expect(onSubmit).toHaveBeenCalledTimes(1);
    // After save the just-saved values become the new baseline.
    expect(readChangedCount()).toBe(0);
    expect(hasNoChangesIndicator()).toBe(true);
    // The saved values are still in the inputs but no longer "changed".
    expect(firstName().value).toBe('Grace');
    expect(emailField().value).toBe('grace@navy.mil');
    // A clean Save after baseline reset must not submit again.
    const btn = saveButton();
    if (!btn.disabled) {
      fireEvent.click(btn);
    }
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  test('render isolation: firstName keystrokes do not bump top-level renders', () => {
    render(<AccountEditForm defaultValues={DEFAULTS} onSubmit={jest.fn()} />);
    const before = readFormRenders();
    const fn = firstName();
    for (const v of ['G', 'Gr', 'Gra', 'Grac', 'Grace']) {
      setText(fn, v);
    }
    // dirty indicator DID react ...
    expect(readChangedCount()).toBe(1);
    expect(hasUnsavedIndicator()).toBe(true);
    // ... but the top-level form body did NOT re-render per keystroke.
    const after = readFormRenders();
    expect(fn.value).toBe('Grace');
    expect(after).toBe(before);
  });
});
"""


class TestReactHookFormPatterns:
    REPO_DIR = "/workspace/react-hook-form"

    # ----------------------------------------------------------------------- #
    # L1: deliverable files exist and are minimally well-formed
    # ----------------------------------------------------------------------- #
    def test_component_file_exists(self):
        """L1: the account edit form component file is created at the required path."""
        assert os.path.isfile(COMPONENT_FILE), f"missing {COMPONENT_FILE}"

    def test_agent_test_file_exists(self):
        """L1: the agent's deterministic Jest suite file is created."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing {AGENT_TEST_FILE}"

    def test_component_is_real_tsx(self):
        """L1: component is real TSX -- JSX, imports the library, uses RHF, not a stub."""
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        assert len(src) > 300, "component file is suspiciously small"
        # imports from the library's own source (relative ../../ entry points)
        assert "import" in src and ".." in src, "component must import from library source"
        # uses react-hook-form form/state primitives
        assert any(
            tok in src
            for tok in ("useForm", "useFormState", "useController", "useWatch", "Controller")
        ), "component must use react-hook-form primitives"
        # actually renders JSX
        assert "return" in src and ("<" in src and ("/>" in src or "</" in src)), (
            "component must render JSX"
        )

    def test_component_uses_dirty_tracking_not_handrolled(self):
        """L1: component relies on RHF's own dirty-state tracking (dirtyFields / isDirty / reset).

        The doc forbids a hand-rolled per-field diff mirrored in local React
        state, and requires baseline reset after save -- both point at the
        library's dirty-state API.
        """
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        assert "dirtyFields" in src or "isDirty" in src, (
            "component must use the form's own dirty-state tracking (dirtyFields/isDirty)"
        )
        # baseline reset after save requires reset(...) (keepValues-style re-baseline)
        assert "reset" in src, (
            "component must re-baseline after save via the form's reset()"
        )

    def test_agent_suite_has_enough_cases(self):
        """L1: the agent suite declares at least 6 test cases (criteria 1-6)."""
        with open(AGENT_TEST_FILE, encoding="utf-8") as fh:
            src = fh.read()
        n = src.count("it(") + src.count("test(")
        assert n >= 6, f"agent suite must contain >=6 cases, found {n}"

    # ----------------------------------------------------------------------- #
    # L2: run the agent's own native suite (the exact required command).
    # ----------------------------------------------------------------------- #
    def test_agent_native_suite_passes(self):
        """L2: accountEditForm.test.tsx passes under the required jest command."""
        rel = os.path.join("src", "__tests__", "examples", "accountEditForm.test.tsx")
        proc = _run_jest(rel)
        passed, failed, total = _jest_summary(proc.stdout, proc.stderr)
        assert proc.returncode == 0, (
            "agent native suite failed.\n"
            f"summary passed={passed} failed={failed} total={total}\n"
            f"STDOUT(tail):\n{proc.stdout[-3000:]}\n"
            f"STDERR(tail):\n{proc.stderr[-3000:]}"
        )
        assert total is not None and total >= 6, (
            f"expected >=6 tests in agent suite, parsed total={total}\n{proc.stderr[-1500:]}"
        )
        assert failed in (0, None), f"agent suite reported failures: {failed}"

    # ----------------------------------------------------------------------- #
    # L2: independent driver suite -- the discriminative core.
    # ----------------------------------------------------------------------- #
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
        matches = {t: s for t, s in byname.items() if title_substr.lower() in t.lower()}
        assert matches, (
            f"driver case matching '{title_substr}' not found among "
            f"{list(byname.keys())}\nSTDERR(tail):\n{proc.stderr[-1500:]}"
        )
        for title, status in matches.items():
            assert status == "passed", (
                f"driver case '{title}' status={status}\n"
                f"STDERR(tail):\n{proc.stderr[-2500:]}"
            )

    def test_driver_initially_clean(self):
        """L2(driver): fresh form is clean -- count 0, no-changes UI, Save inert."""
        self._assert_driver_case("initially clean")

    def test_driver_becomes_dirty(self):
        """L2(driver): editing two fields shows `Changed: 2` and unsaved-changes UI."""
        self._assert_driver_case("becomes dirty")

    def test_driver_revert_by_retyping(self):
        """L2(driver): restoring a field's original value returns the changed count to 0."""
        self._assert_driver_case("revert-by-retyping")

    def test_driver_selective_payload(self):
        """L2(driver): saving submits exactly the changed subset {email, newsletter}."""
        self._assert_driver_case("selective payload")

    def test_driver_baseline_reset_after_save(self):
        """L2(driver): after save, saved values become the new baseline (count 0)."""
        self._assert_driver_case("baseline reset after save")

    def test_driver_render_isolation(self):
        """L2(driver): firstName keystrokes update dirty UI but not the top-level renders."""
        self._assert_driver_case("render isolation")
