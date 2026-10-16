"""Tests for the `react-hook-form-patterns` skill (variant batch: ext3).

Skill task (DISTINCT from ext1): build a render-isolated "survey submission"
form on top of the react-hook-form library's own public API, whose submit
lifecycle surfaces *server-side* errors -- both field-level and form-level --
through the form's own error state, plus a deterministic Jest suite.

Deliverables verified (REPO_DIR = /workspace/react-hook-form):
  - src/__tests__/examples/surveyForm.tsx       (the feature component)
  - src/__tests__/examples/surveyForm.test.tsx  (the agent's own Jest suite)

The survey form models a single `useForm` with:
  - email   (text input)
  - rating  (number select, values 1..5)
  - comment (optional textarea)
and accepts an async `onSubmit(values)` prop.

What this pytest file does:
  * L1  -- the two deliverable TSX files exist and are minimally well-formed
           (real JSX/component, imports from the library, uses RHF primitives,
           not stubs), and the agent suite declares >= 6 cases.
  * L2  -- runs the agent's own native suite via the exact required command
           (`TEST_ENV=web pnpm test -- src/__tests__/examples/surveyForm.test.tsx`,
           i.e. jest with the repo's web project) and asserts no failures and
           the mandated >=6 cases ran.
  * L2  -- INDEPENDENT DRIVER: writes our OWN Jest spec next to the component,
           imports the agent's surveyForm component, and exercises the
           hard-to-fake server-error behaviors directly through rendered DOM:
             - submit calls onSubmit with the exact {email, rating, comment}
             - pending indicator appears while the submit promise is open,
               then clears on resolve
             - field-level server errors are surfaced ADJACENT to their own
               fields, with form values preserved
             - form-level server error renders a single root alert,
               values preserved
             - a follow-up successful submit clears ALL prior server errors
             - a second failure REPLACES the prior error set (no duplicates /
               no stale accumulation)
           A naive implementation that never clears prior server errors, that
           loses form values on rejection, or that hardcodes / ignores the
           rejection payload fails these specs.

All identifiers we depend on (the field accessible names email/rating/comment,
the pending text "Submitting..." or aria-busy, role="alert" for form-level
errors, per-field adjacent error text) are mandated by the requirement
document, so a conforming component must expose them.
"""

import json
import os
import shutil
import subprocess

import pytest

REPO_DIR = "/workspace/react-hook-form"
EXAMPLES_DIR = os.path.join(REPO_DIR, "src", "__tests__", "examples")
COMPONENT_FILE = os.path.join(EXAMPLES_DIR, "surveyForm.tsx")
AGENT_TEST_FILE = os.path.join(EXAMPLES_DIR, "surveyForm.test.tsx")

# Spec we inject ourselves; cleaned up after the run.
DRIVER_BASENAME = "surveyFormDriver.zz.test.tsx"
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
    """Run the web Jest project for a single spec file. Returns CompletedProcess."""
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
# It imports the agent's surveyForm component and validates the
# hard-to-fake submit-lifecycle / server-error behaviors. Every affordance
# we query is mandated by the requirement document.
# --------------------------------------------------------------------------- #
DRIVER_SPEC = r"""
import * as React from 'react';
import {
  render,
  screen,
  fireEvent,
  waitFor,
  within,
} from '@testing-library/react';

import * as Mod from './surveyForm';

// Resolve the exported survey-form component regardless of its name.
function resolveComponent(): React.ComponentType<any> {
  const m: any = Mod as any;
  if (typeof m.default === 'function') return m.default;
  const named = ['SurveyForm', 'Survey', 'Form'];
  for (const n of named) {
    if (typeof m[n] === 'function') return m[n];
  }
  for (const k of Object.keys(m)) {
    if (typeof m[k] === 'function') return m[k];
  }
  throw new Error('could not resolve survey form component from module');
}

const SurveyForm = resolveComponent();

// ---- helpers leaning only on requirement-mandated, stable affordances ----

function getEmailInput(): HTMLInputElement {
  const byLabel = screen.queryByLabelText(/email/i) as HTMLInputElement | null;
  if (byLabel) return byLabel;
  const byRole = screen.queryByRole('textbox', {
    name: /email/i,
  }) as HTMLInputElement | null;
  if (byRole) return byRole;
  const byName = document.querySelector(
    'input[name="email"]',
  ) as HTMLInputElement | null;
  if (byName) return byName;
  throw new Error('email input not found');
}

function getRatingControl(): HTMLSelectElement | HTMLInputElement {
  const byLabel = screen.queryByLabelText(/rating/i) as
    | HTMLSelectElement
    | HTMLInputElement
    | null;
  if (byLabel) return byLabel;
  const byRoleSel = screen.queryByRole('combobox', { name: /rating/i }) as
    | HTMLSelectElement
    | null;
  if (byRoleSel) return byRoleSel;
  const byName = document.querySelector('[name="rating"]') as
    | HTMLSelectElement
    | HTMLInputElement
    | null;
  if (byName) return byName;
  throw new Error('rating control not found');
}

function getCommentControl(): HTMLTextAreaElement | HTMLInputElement {
  const byLabel = screen.queryByLabelText(/comment/i) as
    | HTMLTextAreaElement
    | HTMLInputElement
    | null;
  if (byLabel) return byLabel;
  const byName = document.querySelector('[name="comment"]') as
    | HTMLTextAreaElement
    | HTMLInputElement
    | null;
  if (byName) return byName;
  throw new Error('comment control not found');
}

function getSubmit(): HTMLElement {
  return screen.getByRole('button', { name: /submit/i });
}

function setVal(el: HTMLElement, value: string) {
  fireEvent.change(el, { target: { value } });
}

function pendingPresent(): boolean {
  const txt = screen.queryByText(/submitting/i);
  const busy = document.querySelector('[aria-busy="true"]');
  return Boolean(txt || busy);
}

// Find the error text shown *adjacent* to a given field's control.
// We walk up from the control's nearest ancestor that scopes a single field
// and look for text matching `expected` within that ancestor only -- so an
// error rendered next to a different field, or a single global blob, won't
// satisfy a per-field lookup.
function fieldHasAdjacentError(
  control: HTMLElement,
  expected: string | RegExp,
): boolean {
  const re =
    typeof expected === 'string'
      ? new RegExp(expected.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i')
      : expected;
  let el: HTMLElement | null = control;
  // climb a few levels to the field's wrapper, checking scoped text each time
  for (let depth = 0; el && depth < 4; depth++) {
    const parent = el.parentElement;
    if (!parent) break;
    // Only accept the error if this scope does NOT also contain the *other*
    // fields' controls -- i.e. it is a per-field region, not the whole form.
    const inputs = parent.querySelectorAll('input, select, textarea');
    if (inputs.length <= 2) {
      const txt = parent.textContent || '';
      if (re.test(txt)) return true;
    }
    el = parent;
  }
  return false;
}

function fillValid() {
  setVal(getEmailInput(), 'user@example.com');
  setVal(getRatingControl(), '4');
  setVal(getCommentControl(), 'nice survey');
}

describe('surveyForm driver (independent)', () => {
  test('submit calls onSubmit with the exact current values', async () => {
    let resolveFn: (v?: unknown) => void = () => {};
    const onSubmit = jest.fn(
      () => new Promise<void>((res) => (resolveFn = res)),
    );
    render(<SurveyForm onSubmit={onSubmit} />);
    fillValid();
    fireEvent.click(getSubmit());
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const values = onSubmit.mock.calls[0][0];
    expect(String(values.email)).toBe('user@example.com');
    expect(Number(values.rating)).toBe(4);
    expect(String(values.comment)).toBe('nice survey');
    resolveFn();
  });

  test('pending indicator shows while submit is open, clears on resolve', async () => {
    let resolveFn: (v?: unknown) => void = () => {};
    const onSubmit = jest.fn(
      () => new Promise<void>((res) => (resolveFn = res)),
    );
    render(<SurveyForm onSubmit={onSubmit} />);
    fillValid();
    expect(pendingPresent()).toBe(false);
    fireEvent.click(getSubmit());
    await waitFor(() => expect(pendingPresent()).toBe(true));
    resolveFn();
    await waitFor(() => expect(pendingPresent()).toBe(false));
  });

  test('field-level server errors surface next to their own field, values preserved', async () => {
    let rejectFn: (e?: unknown) => void = () => {};
    const onSubmit = jest.fn(
      () => new Promise<void>((_res, rej) => (rejectFn = rej)),
    );
    render(<SurveyForm onSubmit={onSubmit} />);
    fillValid();
    fireEvent.click(getSubmit());
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    rejectFn({ fieldErrors: { email: 'taken', rating: 'invalid' } });

    await waitFor(() => {
      expect(fieldHasAdjacentError(getEmailInput(), 'taken')).toBe(true);
    });
    expect(fieldHasAdjacentError(getRatingControl(), 'invalid')).toBe(true);
    // the email-only message must NOT be attached to the rating field, and
    // vice versa (catches a single global error blob masquerading as per-field)
    expect(fieldHasAdjacentError(getRatingControl(), 'taken')).toBe(false);
    expect(fieldHasAdjacentError(getEmailInput(), 'invalid')).toBe(false);
    // values preserved across the rejection
    expect(getEmailInput().value).toBe('user@example.com');
    expect(String((getRatingControl() as HTMLInputElement).value)).toBe('4');
    expect((getCommentControl() as HTMLInputElement).value).toBe('nice survey');
    // pending ended
    await waitFor(() => expect(pendingPresent()).toBe(false));
  });

  test('form-level server error renders a single root alert, values preserved', async () => {
    let rejectFn: (e?: unknown) => void = () => {};
    const onSubmit = jest.fn(
      () => new Promise<void>((_res, rej) => (rejectFn = rej)),
    );
    render(<SurveyForm onSubmit={onSubmit} />);
    fillValid();
    fireEvent.click(getSubmit());
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    rejectFn({ formError: 'service down' });

    await waitFor(() => {
      const alerts = screen.getAllByRole('alert');
      expect(alerts.length).toBeGreaterThanOrEqual(1);
      const matching = alerts.filter((a) =>
        /service down/i.test(a.textContent || ''),
      );
      expect(matching.length).toBe(1);
    });
    // no spurious field-level errors for a form-level rejection
    expect(fieldHasAdjacentError(getEmailInput(), /service down/i)).toBe(false);
    expect(getEmailInput().value).toBe('user@example.com');
    await waitFor(() => expect(pendingPresent()).toBe(false));
  });

  test('successful submit after a failure clears all prior server errors', async () => {
    let phase = 0;
    let rejectFn: (e?: unknown) => void = () => {};
    let resolveFn: (v?: unknown) => void = () => {};
    const onSubmit = jest.fn(() => {
      if (phase === 0) {
        return new Promise<void>((_res, rej) => (rejectFn = rej));
      }
      return new Promise<void>((res) => (resolveFn = res));
    });
    render(<SurveyForm onSubmit={onSubmit} />);
    fillValid();
    fireEvent.click(getSubmit());
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    rejectFn({ fieldErrors: { email: 'taken' }, formError: 'service down' });
    await waitFor(() =>
      expect(fieldHasAdjacentError(getEmailInput(), 'taken')).toBe(true),
    );
    expect(screen.getByText(/service down/i)).toBeInTheDocument();

    // now succeed
    phase = 1;
    fireEvent.click(getSubmit());
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2));
    resolveFn();
    await waitFor(() => {
      expect(screen.queryByText(/service down/i)).toBeNull();
    });
    expect(fieldHasAdjacentError(getEmailInput(), 'taken')).toBe(false);
    await waitFor(() => expect(pendingPresent()).toBe(false));
  });

  test('a second failure replaces the prior error set (no stale duplicates)', async () => {
    let phase = 0;
    let reject1: (e?: unknown) => void = () => {};
    let reject2: (e?: unknown) => void = () => {};
    const onSubmit = jest.fn(() => {
      if (phase === 0) {
        return new Promise<void>((_res, rej) => (reject1 = rej));
      }
      return new Promise<void>((_res, rej) => (reject2 = rej));
    });
    render(<SurveyForm onSubmit={onSubmit} />);
    fillValid();
    fireEvent.click(getSubmit());
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    reject1({ fieldErrors: { email: 'taken' } });
    await waitFor(() =>
      expect(fieldHasAdjacentError(getEmailInput(), 'taken')).toBe(true),
    );

    // second submit fails with a DIFFERENT email error
    phase = 1;
    fireEvent.click(getSubmit());
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2));
    reject2({ fieldErrors: { email: 'blocked' } });

    await waitFor(() =>
      expect(fieldHasAdjacentError(getEmailInput(), 'blocked')).toBe(true),
    );
    // the stale 'taken' message must be gone (replaced, not accumulated)
    expect(fieldHasAdjacentError(getEmailInput(), 'taken')).toBe(false);
    // and only one error is shown adjacent to email -> count occurrences
    const blob = (getEmailInput().closest('form')?.textContent || document.body.textContent || '');
    const occBlocked = (blob.match(/blocked/gi) || []).length;
    expect(occBlocked).toBe(1);
  });
});
"""


# --------------------------------------------------------------------------- #
# L1: deliverable files exist and are minimally well-formed
# --------------------------------------------------------------------------- #
class TestReactHookFormPatterns:
    REPO_DIR = "/workspace/react-hook-form"

    def test_component_file_exists(self):
        """L1: the survey form component file is created at the required path."""
        assert os.path.isfile(COMPONENT_FILE), f"missing {COMPONENT_FILE}"

    def test_agent_test_file_exists(self):
        """L1: the agent's deterministic Jest suite file is created."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing {AGENT_TEST_FILE}"

    def test_component_is_real_tsx(self):
        """L1: component is real TSX -- JSX + imports the library + RHF primitives, not a stub."""
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        assert len(src) > 300, "component file is suspiciously small"
        # imports from the library's own source (relative ../../ entry points)
        assert "import" in src and ".." in src, (
            "component must import from library source"
        )
        # uses the form primitive(s)
        assert "useForm" in src, "component must use react-hook-form's useForm"
        assert any(
            tok in src
            for tok in ("setError", "handleSubmit", "formState", "register", "Controller")
        ), "component must use react-hook-form's submit/error primitives"
        # actually renders JSX
        assert "return" in src and ("<" in src and ("/>" in src or "</" in src)), (
            "component must render JSX"
        )

    def test_component_surfaces_server_errors_via_form_state(self):
        """L1: server errors are routed through the form's error state, not ad-hoc local state.

        The requirement forbids ad-hoc local React state holding error strings;
        a conforming impl pushes server errors into RHF (e.g. setError / setError
        with 'root') so they live in formState.errors.
        """
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        assert "setError" in src, (
            "server errors must be surfaced through the form's own error state "
            "(expected setError usage), not ad-hoc local state"
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
        """L2: the agent's surveyForm.test.tsx passes under the required jest command."""
        rel = os.path.join("src", "__tests__", "examples", "surveyForm.test.tsx")
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
    # L2: independent driver suite -- this is the discriminative core.
    # We write our own spec, run it, parse per-test JSON results, and assert
    # each targeted behavior individually.
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

    def test_driver_submit_passes_exact_values(self):
        """L2(driver): submit calls onSubmit with the exact {email, rating, comment}."""
        self._assert_driver_case("submit calls onSubmit with the exact current values")

    def test_driver_pending_indicator(self):
        """L2(driver): pending indicator shows while submit is open, clears on resolve."""
        self._assert_driver_case("pending indicator shows while submit is open")

    def test_driver_field_level_errors(self):
        """L2(driver): field-level server errors surface adjacent to their own field."""
        self._assert_driver_case("field-level server errors surface next to their own field")

    def test_driver_form_level_error(self):
        """L2(driver): form-level server error renders a single root alert, values preserved."""
        self._assert_driver_case("form-level server error renders a single root alert")

    def test_driver_success_clears_errors(self):
        """L2(driver): a follow-up successful submit clears all prior server errors."""
        self._assert_driver_case("successful submit after a failure clears all prior server errors")

    def test_driver_resubmit_replaces_errors(self):
        """L2(driver): a second failure replaces the prior error set (no stale duplicates)."""
        self._assert_driver_case("a second failure replaces the prior error set")
