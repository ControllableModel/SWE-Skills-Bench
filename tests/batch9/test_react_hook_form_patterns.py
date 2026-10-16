"""Tests for the `react-hook-form-patterns` skill (variant ext9).

Skill task: build a NESTED FormProvider "address book" form on top of the
react-hook-form library's own public API. A single `useForm` instance is shared
through context with deeply-nested leaf field components (top form -> Contact/
Address sections -> generic `TextField`s) that obtain registration, per-field
errors and per-field dirty state from CONTEXT, never via prop-drilling. The
agent also adds a deterministic Jest suite.

Deliverables verified (REPO_DIR = /workspace/react-hook-form):
  - src/__tests__/examples/addressBookForm.tsx        (the feature component)
  - src/__tests__/examples/addressBookForm.test.tsx   (the agent's own suite)

What this pytest file does:
  * L1  -- the two deliverable TSX files exist and are minimally well-formed
           (real JSX, imports the library's context primitives, not stubs);
           the agent suite declares >= 6 cases.
  * L2  -- runs the agent's own native suite via the exact required command
           (`TEST_ENV=web pnpm test -- ...addressBookForm.test.tsx`) and asserts
           the specified number of cases pass.
  * L2  -- INDEPENDENT DRIVER: writes our own Jest spec next to the component,
           imports the agent's address-book form, and exercises the
           hard-to-fake behaviors directly through rendered DOM:
             - nested context wiring: typing leaf inputs builds the nested
               { contact, address } submit payload
             - zip 5-digit validation blocks submit and shows a zip-adjacent
               error; a 5-digit zip is accepted
             - per-field required errors appear next to their own input only,
               and filling one clears just that field's error
             - per-field dirty badge flips for the edited field only
             - independent field errors: fixing one invalid field does not
               clear another still-invalid field's error
           A naive impl that prop-drills the form, or that surfaces one shared
           error for all fields, fails the context/independence specs.

All identifiers we query are derived from the requirement document: accessible
labels (firstName/lastName/street/city/zip), the submit button, and the
mandated per-field dirty badge `data-testid="dirty-<name>"` with text
`dirty`/`clean`. A conforming component must expose them.
"""

import json
import os
import shutil
import subprocess

import pytest

REPO_DIR = "/workspace/react-hook-form"
EXAMPLES_DIR = os.path.join(REPO_DIR, "src", "__tests__", "examples")
COMPONENT_FILE = os.path.join(EXAMPLES_DIR, "addressBookForm.tsx")
AGENT_TEST_FILE = os.path.join(EXAMPLES_DIR, "addressBookForm.test.tsx")

# Spec we inject ourselves; cleaned up after the run.
DRIVER_BASENAME = "addressBookFormDriver.zz.test.tsx"
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
# Identifiers used are mandated by the requirement document.
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

import * as Mod from './addressBookForm';

// Resolve the exported address-book form component regardless of its name.
function resolveComponent(): React.ComponentType<any> {
  const m: any = Mod as any;
  if (typeof m.default === 'function') return m.default;
  const named = [
    'AddressBookForm',
    'AddressBook',
    'AddressForm',
    'ContactForm',
    'Form',
  ];
  for (const n of named) {
    if (typeof m[n] === 'function') return m[n];
  }
  for (const k of Object.keys(m)) {
    if (typeof m[k] === 'function') return m[k];
  }
  throw new Error('could not resolve address-book form component from module');
}

const AddressBookForm = resolveComponent();

// ---- field lookup ----------------------------------------------------------
// Fields are addressable by accessible label OR by name attribute on the
// nested path. We try label first, then a name-attribute fallback so we work
// with either `firstName` (leaf path) or `contact.firstName` (full path).
function fieldInput(logical: string): HTMLInputElement {
  const labelRe = new RegExp(logical, 'i');
  const byLabel = screen.queryByLabelText(labelRe) as HTMLInputElement | null;
  if (byLabel) return byLabel;
  const byRole = screen.queryByRole('textbox', {
    name: labelRe,
  }) as HTMLInputElement | null;
  if (byRole) return byRole;
  // name attribute: exact leaf or any path ending with the leaf
  const sel =
    `input[name="${logical}"],` +
    `input[name$=".${logical}"],` +
    `input[name="contact.${logical}"],` +
    `input[name="address.${logical}"]`;
  const byName = document.querySelector(sel) as HTMLInputElement | null;
  if (byName) return byName;
  throw new Error('input not found for field: ' + logical);
}

function setField(logical: string, value: string) {
  const input = fieldInput(logical);
  fireEvent.change(input, { target: { value } });
}

function submitForm() {
  const btn = screen.getByRole('button', { name: /submit/i });
  fireEvent.click(btn);
}

// The error for a field must live ADJACENT to that field's input. We assert
// adjacency by walking up to a small container that holds this input and
// checking the error text lives inside it (and NOT inside a sibling field's
// container).
function fieldContainer(input: HTMLInputElement): HTMLElement {
  let el: HTMLElement | null = input;
  // climb until we reach a container that holds exactly one input (the field
  // wrapper) but stop before the form root.
  let candidate: HTMLElement = input;
  let depth = 0;
  while (el && el.parentElement && depth < 6) {
    el = el.parentElement;
    const inputs = el.querySelectorAll('input');
    if (inputs.length === 1) {
      candidate = el;
    } else {
      break;
    }
    depth += 1;
  }
  return candidate;
}

function fieldHasError(logical: string): boolean {
  const input = fieldInput(logical);
  const box = fieldContainer(input);
  const txt = (box.textContent || '').toLowerCase();
  // an error container should carry message-like text beyond the value itself
  return /error|required|invalid|must|digit|5|zip/.test(txt) &&
    box.querySelector('input') === input;
}

function dirtyBadge(logical: string): HTMLElement {
  // mandated indicator: data-testid="dirty-<name>" with text dirty/clean.
  const candidates = [
    `dirty-${logical}`,
    `dirty-contact.${logical}`,
    `dirty-address.${logical}`,
  ];
  for (const id of candidates) {
    const el = screen.queryByTestId(id);
    if (el) return el as HTMLElement;
  }
  // fall back: a badge inside this field's container
  const box = fieldContainer(fieldInput(logical));
  const el = box.querySelector('[data-testid^="dirty"]') as HTMLElement | null;
  if (el) return el;
  throw new Error('dirty badge not found for field: ' + logical);
}

function dirtyState(logical: string): string {
  return (dirtyBadge(logical).textContent || '').trim().toLowerCase();
}

function fillValidExcept(skip: string[] = []) {
  const values: Record<string, string> = {
    firstName: 'Ada',
    lastName: 'Lovelace',
    street: '12 Analytical Ave',
    city: 'London',
    zip: '90210',
  };
  for (const k of Object.keys(values)) {
    if (skip.indexOf(k) === -1) setField(k, values[k]);
  }
}

describe('addressBookForm driver (independent)', () => {
  test('nested context wiring: leaf inputs build nested submit payload', async () => {
    const onSubmit = jest.fn();
    render(<AddressBookForm onSubmit={onSubmit} />);
    // all leaves obtain register from context (no props threaded down)
    fillValidExcept();
    submitForm();
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const values = onSubmit.mock.calls[0][0];
    expect(values).toBeTruthy();
    expect(values.contact).toBeTruthy();
    expect(values.address).toBeTruthy();
    expect(values.contact.firstName).toBe('Ada');
    expect(values.contact.lastName).toBe('Lovelace');
    expect(values.address.street).toBe('12 Analytical Ave');
    expect(values.address.city).toBe('London');
    expect(String(values.address.zip)).toBe('90210');
  });

  test('zip validation: non-5-digit blocks submit with zip-adjacent error', async () => {
    const onSubmit = jest.fn();
    render(<AddressBookForm onSubmit={onSubmit} />);
    fillValidExcept(['zip']);
    setField('zip', '123'); // too short
    submitForm();
    await waitFor(() => {
      expect(fieldHasError('zip')).toBe(true);
    });
    // submit must be blocked while zip is invalid
    expect(onSubmit).not.toHaveBeenCalled();
    // the error must NOT have leaked to an unrelated valid field's container
    expect(fieldHasError('city')).toBe(false);

    // now make zip valid -> submit accepted
    setField('zip', '54321');
    submitForm();
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const values = onSubmit.mock.calls[0][0];
    expect(String(values.address.zip)).toBe('54321');
  });

  test('per-field required errors appear next to their own input only', async () => {
    const onSubmit = jest.fn();
    render(<AddressBookForm onSubmit={onSubmit} />);
    // leave firstName and street empty, fill the rest validly
    fillValidExcept(['firstName', 'street']);
    submitForm();
    await waitFor(() => {
      expect(fieldHasError('firstName')).toBe(true);
    });
    expect(fieldHasError('street')).toBe(true);
    // a field that was filled validly must not show a required error
    expect(fieldHasError('city')).toBe(false);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  test('filling one required field clears only its own error', async () => {
    const onSubmit = jest.fn();
    render(<AddressBookForm onSubmit={onSubmit} />);
    fillValidExcept(['firstName', 'street']);
    submitForm();
    await waitFor(() => expect(fieldHasError('firstName')).toBe(true));
    expect(fieldHasError('street')).toBe(true);

    // fix only firstName
    setField('firstName', 'Grace');
    await waitFor(() => expect(fieldHasError('firstName')).toBe(false));
    // street's error must persist (independent per-field error state)
    expect(fieldHasError('street')).toBe(true);
  });

  test('per-field dirty badge flips for the edited field only', async () => {
    render(<AddressBookForm onSubmit={jest.fn()} />);
    // initially every field is clean
    expect(dirtyState('city')).toBe('clean');
    expect(dirtyState('firstName')).toBe('clean');
    expect(dirtyState('zip')).toBe('clean');

    // edit only city
    setField('city', 'Paris');
    await waitFor(() => expect(dirtyState('city')).toBe('dirty'));
    // other fields stay clean -> per-field state, not whole-form subscription
    expect(dirtyState('firstName')).toBe('clean');
    expect(dirtyState('zip')).toBe('clean');
    expect(dirtyState('street')).toBe('clean');
  });

  test('independent field errors: fixing one invalid field keeps another error', async () => {
    const onSubmit = jest.fn();
    render(<AddressBookForm onSubmit={onSubmit} />);
    // make firstName empty (required) AND zip invalid; fill the rest
    fillValidExcept(['firstName', 'zip']);
    setField('zip', '12'); // invalid zip
    submitForm();
    await waitFor(() => expect(fieldHasError('firstName')).toBe(true));
    expect(fieldHasError('zip')).toBe(true);
    expect(onSubmit).not.toHaveBeenCalled();

    // fix zip only
    setField('zip', '99999');
    await waitFor(() => expect(fieldHasError('zip')).toBe(false));
    // firstName must still be in error -> errors are per-field, not shared
    expect(fieldHasError('firstName')).toBe(true);
  });
});
"""


# --------------------------------------------------------------------------- #
# L1: deliverable files exist and are minimally well-formed
# --------------------------------------------------------------------------- #
class TestReactHookFormPatterns:
    REPO_DIR = "/workspace/react-hook-form"

    def test_component_file_exists(self):
        """L1: the address-book form component file exists at the required path."""
        assert os.path.isfile(COMPONENT_FILE), f"missing {COMPONENT_FILE}"

    def test_agent_test_file_exists(self):
        """L1: the agent's deterministic Jest suite file is created."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing {AGENT_TEST_FILE}"

    def test_component_is_real_tsx(self):
        """L1: component is real TSX -- JSX, imports library context primitives, not a stub."""
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        assert len(src) > 300, "component file is suspiciously small"
        assert "import" in src and ".." in src, (
            "component must import from the library's own source entry points"
        )
        # the task is fundamentally about context sharing: the component must
        # use FormProvider/useFormContext (or useController/useFormState which
        # read the shared control) rather than prop-drilling.
        assert "FormProvider" in src or "useFormContext" in src, (
            "component must share the form via context (FormProvider/useFormContext)"
        )
        assert any(
            tok in src
            for tok in ("useController", "useFormContext", "useFormState", "register")
        ), "leaf fields must connect to the form through context primitives"
        # actually renders JSX
        assert "return" in src and ("/>" in src or "</" in src), (
            "component must render JSX"
        )

    def test_component_does_not_prop_drill_form(self):
        """L1: heuristic guard -- the form/control is shared via context, not threaded down.

        A correct implementation provides the form through <FormProvider> and the
        leaves pull it with useFormContext/useController. We require the provider
        wiring to be present; an implementation that only passes `control=`/`form=`
        props to children without any context provider is the naive prop-drill
        the doc says must fail.
        """
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        uses_provider = "FormProvider" in src or "useFormContext" in src
        assert uses_provider, (
            "no FormProvider/useFormContext found -- the doc forbids prop-drilling "
            "the form object to the leaf field components"
        )

    def test_agent_suite_has_enough_cases(self):
        """L1: the agent suite declares at least 6 cases (criteria 1-6)."""
        with open(AGENT_TEST_FILE, encoding="utf-8") as fh:
            src = fh.read()
        n = src.count("it(") + src.count("test(")
        assert n >= 6, f"agent suite must contain >=6 cases, found {n}"

    # ----------------------------------------------------------------------- #
    # L2: run the agent's own native suite (the exact required command).
    # ----------------------------------------------------------------------- #
    def test_agent_native_suite_passes(self):
        """L2: addressBookForm.test.tsx passes under the required jest/web command."""
        rel = os.path.join("src", "__tests__", "examples", "addressBookForm.test.tsx")
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

    def test_driver_nested_context_wiring(self):
        """L2(driver): leaf inputs (form via context) build the nested submit payload."""
        self._assert_driver_case("nested context wiring")

    def test_driver_zip_validation(self):
        """L2(driver): non-5-digit zip blocks submit with a zip-adjacent error; 5 digits ok."""
        self._assert_driver_case("zip validation")

    def test_driver_per_field_required_errors(self):
        """L2(driver): required errors appear next to their own input only."""
        self._assert_driver_case("per-field required errors appear next to their own input only")

    def test_driver_filling_clears_only_own_error(self):
        """L2(driver): filling one required field clears just its own error."""
        self._assert_driver_case("filling one required field clears only its own error")

    def test_driver_per_field_dirty_badge(self):
        """L2(driver): editing only one field flips just its dirty badge."""
        self._assert_driver_case("per-field dirty badge flips for the edited field only")

    def test_driver_independent_field_errors(self):
        """L2(driver): fixing one invalid field does not clear another's error."""
        self._assert_driver_case("independent field errors")
