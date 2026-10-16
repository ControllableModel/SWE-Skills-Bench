"""Tests for the `react-hook-form-patterns` skill (variant ext5).

Skill task (ext5): build a multi-step "signup wizard" form on top of the
react-hook-form library's own public API. A single `useForm` instance backs
three steps; the "Next" button is gated on ONLY the current step's validity;
values persist across step navigation; cross-field validation ties
`confirmPassword` to `password`; the final "Submit" is gated on
`acceptedTerms`, and submitting calls `onSubmit(values)` with the full
accumulated payload. The agent also writes a deterministic Jest suite.

Deliverables verified (REPO_DIR = /workspace/react-hook-form):
  - src/__tests__/examples/wizardForm.tsx       (the feature component)
  - src/__tests__/examples/wizardForm.test.tsx  (the agent's own Jest suite)

Verification strategy:
  * L1  -- the two deliverable TSX files exist and are minimally well-formed
           (real JSX/component, imports from the library, uses RHF primitives,
           and the agent suite declares >=6 cases).
  * L2  -- runs the agent's own native suite via the exact required command
           (`TEST_ENV=web pnpm test -- src/__tests__/examples/wizardForm.test.tsx`)
           and asserts the specified number of cases pass with no failures.
  * L2  -- INDEPENDENT DRIVER (the discriminative core): writes our own Jest
           spec next to the component, imports the agent's wizard component,
           supplies a `jest.fn()` onSubmit, and exercises the hard-to-fake
           behaviors through rendered DOM:
             - initial per-step gating (Next disabled on empty step 1, enabled
               once email+username valid) -- a naive whole-form gate fails this
             - advance/back navigation + step indicator
             - value persistence across step navigation -- a remount-and-lose
               implementation fails this
             - cross-field: step-2 Next disabled while confirm != password,
               and re-disabled if password later changed to differ
             - final gating: Submit disabled until acceptedTerms checked
             - submit payload: onSubmit called once with the full accumulated
               { email, username, password, confirmPassword, acceptedTerms }
           A naive implementation that gates "Next" on whole-form validity, or
           that loses values across steps, fails the gating and persistence
           driver cases.

All affordances we query (the labels Next/Back/Submit, the
"Step N of 3" indicator, and the field names) are mandated verbatim by the
requirement document, so a conforming component must expose them.
"""

import json
import os
import shutil
import subprocess

import pytest

REPO_DIR = "/workspace/react-hook-form"
EXAMPLES_DIR = os.path.join(REPO_DIR, "src", "__tests__", "examples")
COMPONENT_FILE = os.path.join(EXAMPLES_DIR, "wizardForm.tsx")
AGENT_TEST_FILE = os.path.join(EXAMPLES_DIR, "wizardForm.test.tsx")

# Spec we inject ourselves; cleaned up after the run.
DRIVER_BASENAME = "wizardFormDriver.zz.test.tsx"
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
# It imports the agent's wizard component and validates the gameable behaviors.
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

import * as Mod from './wizardForm';

// Resolve the exported wizard component regardless of its exact name.
function resolveComponent(): React.ComponentType<any> {
  const m: any = Mod as any;
  if (typeof m.default === 'function') return m.default;
  const named = [
    'WizardForm',
    'Wizard',
    'SignupWizard',
    'SignupForm',
    'MultiStepForm',
    'StepForm',
    'Form',
  ];
  for (const n of named) {
    if (typeof m[n] === 'function') return m[n];
  }
  for (const k of Object.keys(m)) {
    if (typeof m[k] === 'function') return m[k];
  }
  throw new Error('could not resolve wizard form component from module');
}

const WizardForm = resolveComponent();

// ---- helpers that lean only on requirement-mandated, stable affordances ----

function getNext(): HTMLButtonElement {
  return screen.getByRole('button', { name: /next/i }) as HTMLButtonElement;
}

function getBack(): HTMLButtonElement {
  return screen.getByRole('button', { name: /back/i }) as HTMLButtonElement;
}

function getSubmit(): HTMLButtonElement {
  return screen.getByRole('button', { name: /submit/i }) as HTMLButtonElement;
}

// find a field input by name/aria-label/placeholder/testid hints
function fieldInput(re: RegExp): HTMLInputElement {
  const inputs = Array.from(
    document.querySelectorAll('input'),
  ) as HTMLInputElement[];
  const found = inputs.find((i) => {
    const hay = [
      i.getAttribute('name') || '',
      i.getAttribute('aria-label') || '',
      i.getAttribute('placeholder') || '',
      i.getAttribute('data-testid') || '',
      i.id || '',
    ]
      .join(' ')
      .toLowerCase();
    return re.test(hay);
  });
  if (!found) throw new Error('input not found for ' + re);
  return found;
}

function maybeFieldInput(re: RegExp): HTMLInputElement | null {
  try {
    return fieldInput(re);
  } catch {
    return null;
  }
}

function setInput(input: HTMLInputElement, value: string) {
  fireEvent.change(input, { target: { value } });
}

function stepIndicatorText(): string {
  const node = screen.getByText(/step\s*\d+\s*of\s*3/i);
  return node.textContent || '';
}

function currentStepNumber(): number {
  const m = stepIndicatorText().match(/step\s*(\d+)\s*of\s*3/i);
  if (!m) throw new Error('step indicator not parseable: ' + stepIndicatorText());
  return Number(m[1]);
}

// fill a valid step 1 (email with @, username >=3) and advance.
function fillStep1AndAdvance(email = 'a@b.com', username = 'alice') {
  setInput(fieldInput(/^email$|email/), email);
  setInput(fieldInput(/user/), username);
  fireEvent.click(getNext());
}

// fill a valid step 2 (password >=8, confirm == password) and advance.
function fillStep2AndAdvance(pw = 'password1', confirm = 'password1') {
  // password vs confirmPassword: confirm matches /confirm/, the other is password.
  const confirmInput = fieldInput(/confirm/);
  const pwInput = (() => {
    const inputs = Array.from(
      document.querySelectorAll('input[type="password"], input'),
    ) as HTMLInputElement[];
    const cand = inputs.find((i) => {
      const hay = [
        i.getAttribute('name') || '',
        i.getAttribute('aria-label') || '',
        i.getAttribute('placeholder') || '',
        i.getAttribute('data-testid') || '',
        i.id || '',
      ]
        .join(' ')
        .toLowerCase();
      return /pass/.test(hay) && !/confirm/.test(hay);
    });
    if (!cand) throw new Error('password input not found');
    return cand;
  })();
  setInput(pwInput, pw);
  setInput(confirmInput, confirm);
  fireEvent.click(getNext());
  return { pwInput, confirmInput };
}

describe('wizardForm driver (independent)', () => {
  test('initial gating: Next disabled empty, enabled when step1 valid', () => {
    render(<WizardForm onSubmit={jest.fn()} />);
    expect(currentStepNumber()).toBe(1);
    // empty -> Next disabled
    expect(getNext()).toBeDisabled();
    // partial (email only) -> still disabled
    setInput(fieldInput(/^email$|email/), 'a@b.com');
    expect(getNext()).toBeDisabled();
    // username too short -> still disabled
    setInput(fieldInput(/user/), 'ab');
    expect(getNext()).toBeDisabled();
    // valid email + username>=3 -> enabled
    setInput(fieldInput(/user/), 'alice');
    expect(getNext()).toBeEnabled();
  });

  test('email must contain @ to enable Next', () => {
    render(<WizardForm onSubmit={jest.fn()} />);
    setInput(fieldInput(/^email$|email/), 'not-an-email');
    setInput(fieldInput(/user/), 'alice');
    expect(getNext()).toBeDisabled();
    setInput(fieldInput(/^email$|email/), 'good@x.com');
    expect(getNext()).toBeEnabled();
  });

  test('advance to step 2 and Back returns to step 1', () => {
    render(<WizardForm onSubmit={jest.fn()} />);
    fillStep1AndAdvance();
    expect(currentStepNumber()).toBe(2);
    fireEvent.click(getBack());
    expect(currentStepNumber()).toBe(1);
  });

  test('value persistence: email survives navigating to step 2 and back', () => {
    render(<WizardForm onSubmit={jest.fn()} />);
    fillStep1AndAdvance('persist@me.com', 'bobby');
    expect(currentStepNumber()).toBe(2);
    fireEvent.click(getBack());
    expect(currentStepNumber()).toBe(1);
    expect(fieldInput(/^email$|email/).value).toBe('persist@me.com');
    expect(fieldInput(/user/).value).toBe('bobby');
  });

  test('cross-field: step2 Next gated on confirm == password', () => {
    render(<WizardForm onSubmit={jest.fn()} />);
    fillStep1AndAdvance();
    expect(currentStepNumber()).toBe(2);
    const confirmInput = fieldInput(/confirm/);
    const pwInput = (() => {
      const inputs = Array.from(
        document.querySelectorAll('input'),
      ) as HTMLInputElement[];
      const cand = inputs.find((i) => {
        const hay = [
          i.getAttribute('name') || '',
          i.getAttribute('aria-label') || '',
          i.getAttribute('placeholder') || '',
          i.id || '',
        ]
          .join(' ')
          .toLowerCase();
        return /pass/.test(hay) && !/confirm/.test(hay);
      });
      if (!cand) throw new Error('password input not found');
      return cand;
    })();
    // mismatched -> Next disabled
    setInput(pwInput, 'password1');
    setInput(confirmInput, 'password2');
    expect(getNext()).toBeDisabled();
    // matched -> enabled
    setInput(confirmInput, 'password1');
    expect(getNext()).toBeEnabled();
    // editing password to differ re-disables
    setInput(pwInput, 'passwordX');
    expect(getNext()).toBeDisabled();
  });

  test('password min-length (>=8) gates step 2', () => {
    render(<WizardForm onSubmit={jest.fn()} />);
    fillStep1AndAdvance();
    const confirmInput = fieldInput(/confirm/);
    const pwInput = (() => {
      const inputs = Array.from(
        document.querySelectorAll('input'),
      ) as HTMLInputElement[];
      const cand = inputs.find((i) => {
        const hay = [
          i.getAttribute('name') || '',
          i.getAttribute('aria-label') || '',
          i.getAttribute('placeholder') || '',
          i.id || '',
        ]
          .join(' ')
          .toLowerCase();
        return /pass/.test(hay) && !/confirm/.test(hay);
      });
      if (!cand) throw new Error('password input not found');
      return cand;
    })();
    setInput(pwInput, 'short');
    setInput(confirmInput, 'short');
    expect(getNext()).toBeDisabled();
    setInput(pwInput, 'longenough');
    setInput(confirmInput, 'longenough');
    expect(getNext()).toBeEnabled();
  });

  test('final gating: Submit disabled until acceptedTerms checked', () => {
    render(<WizardForm onSubmit={jest.fn()} />);
    fillStep1AndAdvance();
    fillStep2AndAdvance();
    expect(currentStepNumber()).toBe(3);
    const submit = getSubmit();
    expect(submit).toBeDisabled();
    const terms = fieldInput(/accept|terms/);
    fireEvent.click(terms);
    expect(getSubmit()).toBeEnabled();
  });

  test('submit payload: onSubmit called once with full accumulated values', async () => {
    const onSubmit = jest.fn();
    render(<WizardForm onSubmit={onSubmit} />);
    fillStep1AndAdvance('zed@x.com', 'zelda');
    fillStep2AndAdvance('password1', 'password1');
    expect(currentStepNumber()).toBe(3);
    const terms = fieldInput(/accept|terms/);
    fireEvent.click(terms);
    fireEvent.click(getSubmit());
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const values = onSubmit.mock.calls[0][0];
    expect(values.email).toBe('zed@x.com');
    expect(values.username).toBe('zelda');
    expect(values.password).toBe('password1');
    expect(values.confirmPassword).toBe('password1');
    expect(values.acceptedTerms).toBe(true);
  });

  test('next-step fields do not gate the current step', () => {
    // On step 1, the (still-empty) password/terms must NOT block Next; a
    // whole-form gate would keep Next disabled here.
    render(<WizardForm onSubmit={jest.fn()} />);
    setInput(fieldInput(/^email$|email/), 'a@b.com');
    setInput(fieldInput(/user/), 'alice');
    expect(getNext()).toBeEnabled();
  });
});
"""


# --------------------------------------------------------------------------- #
# L1: deliverable files exist and are minimally well-formed
# --------------------------------------------------------------------------- #
class TestReactHookFormPatterns:
    REPO_DIR = "/workspace/react-hook-form"

    def test_component_file_exists(self):
        """L1: the wizard form component file is created at the required path."""
        assert os.path.isfile(COMPONENT_FILE), f"missing {COMPONENT_FILE}"

    def test_agent_test_file_exists(self):
        """L1: the agent's deterministic Jest suite file is created."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing {AGENT_TEST_FILE}"

    def test_component_is_real_tsx(self):
        """L1: component is real TSX -- contains JSX, imports the library, not a stub."""
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        assert len(src) > 300, "component file is suspiciously small"
        # imports from the library's own source (relative ../../ entry points)
        assert "import" in src and ".." in src, (
            "component must import from library source"
        )
        # uses at least one react-hook-form form primitive
        assert any(
            tok in src
            for tok in ("useForm", "useController", "useWatch", "Controller", "register")
        ), "component must use react-hook-form primitives"
        # actually renders JSX
        assert "return" in src and ("<" in src and "/>" in src or "</" in src), (
            "component must render JSX"
        )

    def test_component_declares_all_wizard_fields(self):
        """L1: the component references every required field across the three steps."""
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        for field in (
            "email",
            "username",
            "password",
            "confirmPassword",
            "acceptedTerms",
        ):
            assert field in src, f"component must reference required field '{field}'"

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
        """L2: the agent's wizardForm.test.tsx passes under the required jest command.

        Mirrors `TEST_ENV=web pnpm test -- src/__tests__/examples/wizardForm.test.tsx`.
        """
        rel = os.path.join("src", "__tests__", "examples", "wizardForm.test.tsx")
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

    def test_driver_initial_gating(self):
        """L2(driver): step-1 Next disabled empty, enabled only when email+username valid."""
        self._assert_driver_case("initial gating")

    def test_driver_email_requires_at(self):
        """L2(driver): an email without '@' keeps Next disabled."""
        self._assert_driver_case("email must contain @")

    def test_driver_advance_and_back(self):
        """L2(driver): Next reaches 'Step 2 of 3' and Back returns to step 1."""
        self._assert_driver_case("advance to step 2 and Back returns")

    def test_driver_value_persistence(self):
        """L2(driver): values typed on step 1 survive navigating to step 2 and back."""
        self._assert_driver_case("value persistence")

    def test_driver_cross_field_confirm(self):
        """L2(driver): step-2 Next gated on confirmPassword == password (re-disables on edit)."""
        self._assert_driver_case("cross-field")

    def test_driver_password_min_length(self):
        """L2(driver): password shorter than 8 chars keeps step 2 gated."""
        self._assert_driver_case("password min-length")

    def test_driver_final_gating(self):
        """L2(driver): final Submit disabled until acceptedTerms is checked."""
        self._assert_driver_case("final gating")

    def test_driver_submit_payload(self):
        """L2(driver): submit calls onSubmit once with the full accumulated values."""
        self._assert_driver_case("submit payload")

    def test_driver_per_step_isolation(self):
        """L2(driver): not-yet-visited steps' fields must not gate the current step's Next."""
        self._assert_driver_case("next-step fields do not gate the current step")
