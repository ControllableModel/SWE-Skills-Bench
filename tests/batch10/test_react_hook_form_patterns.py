"""Tests for the `react-hook-form-patterns` skill (variant ext10).

Skill task: build a render-isolated "register" form on top of the
react-hook-form library's own public API whose `username` field is validated
asynchronously against a caller-supplied uniqueness checker, with the
in-flight / availability state surfaced through the form's own validation
machinery. Plus a deterministic Jest suite pinning down the async-validation
lifecycle.

Deliverables verified (REPO_DIR = /workspace/react-hook-form):
  - src/__tests__/examples/registerForm.tsx        (the feature component)
  - src/__tests__/examples/registerForm.test.tsx   (the agent's own Jest suite)

What this pytest file does:
  * L1  -- the two deliverable TSX files exist and are minimally well-formed
           (real JSX/component, imports from the library, uses react-hook-form
           primitives, not stubs).
  * L2  -- runs the agent's own native suite via the exact required command
           (`TEST_ENV=web pnpm jest ... registerForm.test.tsx`) and asserts the
           specified number of cases pass.
  * L2  -- INDEPENDENT DRIVER: writes our own Jest spec next to the component,
           imports the agent's registerForm component, supplies deferred
           `checkUsername` / `onSubmit` mocks the *driver* controls, and
           exercises the hard-to-fake behaviors directly through rendered DOM:
             - sync short-circuit: a 2-char username shows its length error and
               `checkUsername` is NEVER called
             - pending indicator while a deferred check is in-flight; it clears
               once the check settles
             - taken (resolve false): field-level error appears, submit blocked
             - available (resolve true): error cleared, submit allowed
             - STALE-RESPONSE SAFETY: change A->B while A pending, resolve A=false
               then B=true; final UI reflects B (available), not A's stale failure
             - submit gating: onSubmit only fires once sync rules pass AND latest
               username resolved available
           A naive implementation (no stale-guard, or running the async check
           for too-short usernames, or independent local error state) fails the
           stale / short-circuit specs.

All identifiers we query (the texts "Checking...", "Username taken", the
username / password inputs, the submit button) are mandated by the requirement
document, so a conforming component must expose them.
"""

import json
import os
import shutil
import subprocess

import pytest

REPO_DIR = "/workspace/react-hook-form"
EXAMPLES_DIR = os.path.join(REPO_DIR, "src", "__tests__", "examples")
COMPONENT_FILE = os.path.join(EXAMPLES_DIR, "registerForm.tsx")
AGENT_TEST_FILE = os.path.join(EXAMPLES_DIR, "registerForm.test.tsx")

# Spec we inject ourselves; cleaned up after the run.
DRIVER_BASENAME = "registerFormDriver.zz.test.tsx"
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
  act,
} from '@testing-library/react';

import * as Mod from './registerForm';

// Resolve the exported register-form component regardless of its name.
function resolveComponent(): React.ComponentType<any> {
  const m: any = Mod as any;
  if (typeof m.default === 'function') return m.default;
  const named = [
    'RegisterForm',
    'Register',
    'SignupForm',
    'SignUpForm',
    'UsernameForm',
    'Form',
  ];
  for (const n of named) {
    if (typeof m[n] === 'function') return m[n];
  }
  for (const k of Object.keys(m)) {
    if (typeof m[k] === 'function') return m[k];
  }
  throw new Error('could not resolve register form component from module');
}

const RegisterForm = resolveComponent();

// ----- a deferred promise helper so the driver controls resolution order ----
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// ----- DOM affordance helpers leaning on requirement-mandated identifiers ----

function getUsernameInput(): HTMLInputElement {
  const byLabel = screen.queryByLabelText(/username/i) as HTMLInputElement | null;
  if (byLabel) return byLabel;
  const byRole = screen.queryByRole('textbox', {
    name: /username/i,
  }) as HTMLInputElement | null;
  if (byRole) return byRole;
  const byName = document.querySelector(
    'input[name="username"]',
  ) as HTMLInputElement | null;
  if (byName) return byName;
  const byTestId = document.querySelector(
    '[data-testid="username"]',
  ) as HTMLInputElement | null;
  if (byTestId) return byTestId;
  throw new Error('username input not found');
}

function getPasswordInput(): HTMLInputElement {
  const byLabel = screen.queryByLabelText(/password/i) as HTMLInputElement | null;
  if (byLabel) return byLabel;
  const byName = document.querySelector(
    'input[name="password"]',
  ) as HTMLInputElement | null;
  if (byName) return byName;
  const byType = document.querySelector(
    'input[type="password"]',
  ) as HTMLInputElement | null;
  if (byType) return byType;
  const byTestId = document.querySelector(
    '[data-testid="password"]',
  ) as HTMLInputElement | null;
  if (byTestId) return byTestId;
  throw new Error('password input not found');
}

function getSubmit(): HTMLElement {
  return screen.getByRole('button', { name: /submit|register|sign\s?up/i });
}

function setInput(input: HTMLInputElement, value: string) {
  fireEvent.change(input, { target: { value } });
}

function hasChecking(): boolean {
  return screen.queryByText(/checking\.\.\.|checking…|checking\b/i) !== null;
}

function hasTaken(): boolean {
  return screen.queryByText(/username taken|taken|not available|already/i) !== null;
}

async function flush() {
  // let any pending microtasks / state updates settle
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe('registerForm driver (independent)', () => {
  test('sync short-circuit: 2-char username never calls checkUsername', async () => {
    const checkUsername = jest.fn(() => Promise.resolve(true));
    const onSubmit = jest.fn(() => Promise.resolve());
    render(
      <RegisterForm checkUsername={checkUsername} onSubmit={onSubmit} />,
    );
    const username = getUsernameInput();
    setInput(username, 'ab'); // below min length 3
    fireEvent.blur(username);
    await flush();
    // The async uniqueness check must be short-circuited by the sync rule.
    expect(checkUsername).not.toHaveBeenCalled();
    // No pending indicator should be shown for an invalid-length value.
    expect(hasChecking()).toBe(false);
  });

  test('pending indicator shown while deferred check is in-flight', async () => {
    const d = deferred<boolean>();
    const checkUsername = jest.fn(() => d.promise);
    const onSubmit = jest.fn(() => Promise.resolve());
    render(
      <RegisterForm checkUsername={checkUsername} onSubmit={onSubmit} />,
    );
    const username = getUsernameInput();
    setInput(username, 'validname');
    fireEvent.blur(username);
    await waitFor(() => expect(checkUsername).toHaveBeenCalled());
    expect(checkUsername.mock.calls[0][0]).toBe('validname');
    // while pending: a checking indicator is visible
    await waitFor(() => expect(hasChecking()).toBe(true));
    // settle and the indicator must disappear
    await act(async () => {
      d.resolve(true);
      await d.promise;
    });
    await waitFor(() => expect(hasChecking()).toBe(false));
  });

  test('taken: resolving false shows the taken error and blocks submit', async () => {
    const d = deferred<boolean>();
    const checkUsername = jest.fn(() => d.promise);
    const onSubmit = jest.fn(() => Promise.resolve());
    render(
      <RegisterForm checkUsername={checkUsername} onSubmit={onSubmit} />,
    );
    setInput(getUsernameInput(), 'takenuser');
    fireEvent.blur(getUsernameInput());
    setInput(getPasswordInput(), 'longenough1');
    await waitFor(() => expect(checkUsername).toHaveBeenCalled());
    await act(async () => {
      d.resolve(false);
      await d.promise;
    });
    await waitFor(() => expect(hasTaken()).toBe(true));
    // submitting must be blocked: onSubmit not called
    fireEvent.click(getSubmit());
    await flush();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  test('available: resolving true clears error and allows submit', async () => {
    const d = deferred<boolean>();
    const checkUsername = jest.fn(() => d.promise);
    const onSubmit = jest.fn(() => Promise.resolve());
    render(
      <RegisterForm checkUsername={checkUsername} onSubmit={onSubmit} />,
    );
    setInput(getUsernameInput(), 'freshuser');
    fireEvent.blur(getUsernameInput());
    setInput(getPasswordInput(), 'longenough1');
    await waitFor(() => expect(checkUsername).toHaveBeenCalled());
    await act(async () => {
      d.resolve(true);
      await d.promise;
    });
    await waitFor(() => expect(hasChecking()).toBe(false));
    expect(hasTaken()).toBe(false);
    fireEvent.click(getSubmit());
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const values = onSubmit.mock.calls[0][0];
    expect(String(values.username)).toBe('freshuser');
    expect(String(values.password)).toBe('longenough1');
  });

  test('stale response: late A=false must not override final B=true', async () => {
    const dA = deferred<boolean>();
    const dB = deferred<boolean>();
    let call = 0;
    const checkUsername = jest.fn((_name: string) => {
      call += 1;
      return call === 1 ? dA.promise : dB.promise;
    });
    const onSubmit = jest.fn(() => Promise.resolve());
    render(
      <RegisterForm checkUsername={checkUsername} onSubmit={onSubmit} />,
    );
    const username = getUsernameInput();
    setInput(username, 'alphaaa'); // value A
    fireEvent.blur(username);
    await waitFor(() => expect(checkUsername).toHaveBeenCalledTimes(1));
    expect(checkUsername.mock.calls[0][0]).toBe('alphaaa');

    // change to value B before A resolves
    setInput(username, 'betaaaa');
    fireEvent.blur(username);
    await waitFor(() => expect(checkUsername).toHaveBeenCalledTimes(2));
    expect(checkUsername.mock.calls[1][0]).toBe('betaaaa');

    // resolve the STALE A as false first, then the latest B as true
    await act(async () => {
      dA.resolve(false);
      await dA.promise;
    });
    await act(async () => {
      dB.resolve(true);
      await dB.promise;
    });
    await flush();

    // The final UI must reflect B (available), not A's stale "taken".
    await waitFor(() => expect(hasChecking()).toBe(false));
    expect(hasTaken()).toBe(false);

    // and submit (with a valid password) must be allowed
    setInput(getPasswordInput(), 'longenough1');
    fireEvent.click(getSubmit());
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(String(onSubmit.mock.calls[0][0].username)).toBe('betaaaa');
  });

  test('submit gating: onSubmit blocked until sync rules pass and available', async () => {
    const d = deferred<boolean>();
    const checkUsername = jest.fn(() => d.promise);
    const onSubmit = jest.fn(() => Promise.resolve());
    render(
      <RegisterForm checkUsername={checkUsername} onSubmit={onSubmit} />,
    );
    // 1) too-short password blocks submit even with a good username
    setInput(getUsernameInput(), 'gooduser');
    fireEvent.blur(getUsernameInput());
    setInput(getPasswordInput(), 'short'); // < 8
    await waitFor(() => expect(checkUsername).toHaveBeenCalled());
    await act(async () => {
      d.resolve(true);
      await d.promise;
    });
    fireEvent.click(getSubmit());
    await flush();
    expect(onSubmit).not.toHaveBeenCalled();

    // 2) fix the password -> submit now goes through
    setInput(getPasswordInput(), 'longenough1');
    fireEvent.click(getSubmit());
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
  });
});
"""


# --------------------------------------------------------------------------- #
# L1 + L2 test class
# --------------------------------------------------------------------------- #
class TestReactHookFormPatterns:
    REPO_DIR = "/workspace/react-hook-form"

    # ---------------------- L1: deliverables ------------------------------- #
    def test_component_file_exists(self):
        """L1: the register form component file is created at the required path."""
        assert os.path.isfile(COMPONENT_FILE), f"missing {COMPONENT_FILE}"

    def test_agent_test_file_exists(self):
        """L1: the agent's deterministic Jest suite file is created."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing {AGENT_TEST_FILE}"

    def test_component_is_real_tsx(self):
        """L1: component is real TSX -- JSX + library import + rhf primitive, not a stub."""
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        assert len(src) > 300, "component file is suspiciously small"
        # imports from the library's own source (relative ../../ entry points)
        assert "import" in src and ".." in src, "component must import from library source"
        # uses at least one of the form primitives
        assert any(
            tok in src
            for tok in ("useForm", "useController", "Controller", "useWatch", "register")
        ), "component must use react-hook-form primitives"
        # actually renders JSX
        assert "return" in src and ("<" in src and ("/>" in src or "</" in src)), (
            "component must render JSX"
        )

    def test_component_wires_async_check(self):
        """L1: component consumes the checkUsername prop (async uniqueness wiring present)."""
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        assert "checkUsername" in src, (
            "component must use the caller-supplied checkUsername prop"
        )
        assert "onSubmit" in src, "component must use the caller-supplied onSubmit prop"

    def test_agent_suite_has_enough_cases(self):
        """L1: the agent suite declares at least 6 test cases (criteria 1-6)."""
        with open(AGENT_TEST_FILE, encoding="utf-8") as fh:
            src = fh.read()
        n = src.count("it(") + src.count("test(")
        assert n >= 6, f"agent suite must contain >=6 cases, found {n}"

    # ---------------------- L2: agent's own native suite ------------------- #
    def test_agent_native_suite_passes(self):
        """L2: the agent's registerForm.test.tsx passes under the required jest command."""
        rel = os.path.join("src", "__tests__", "examples", "registerForm.test.tsx")
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

    # ---------------------- L2: independent driver ------------------------- #
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

    def test_driver_sync_short_circuit(self):
        """L2(driver): a 2-char username shows length error; checkUsername never called."""
        self._assert_driver_case("sync short-circuit")

    def test_driver_pending_indicator(self):
        """L2(driver): a checking indicator is shown while the deferred check is in-flight."""
        self._assert_driver_case("pending indicator")

    def test_driver_taken_blocks_submit(self):
        """L2(driver): resolving false shows the taken error and blocks submit."""
        self._assert_driver_case("taken: resolving false")

    def test_driver_available_allows_submit(self):
        """L2(driver): resolving true clears the error and allows submit."""
        self._assert_driver_case("available: resolving true")

    def test_driver_stale_response_safety(self):
        """L2(driver): late A=false must not override the latest B=true availability."""
        self._assert_driver_case("stale response")

    def test_driver_submit_gating(self):
        """L2(driver): onSubmit only fires once sync rules pass and latest check is available."""
        self._assert_driver_case("submit gating")
