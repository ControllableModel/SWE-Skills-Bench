"""Tests for the `react-hook-form-patterns` skill (variant ext4).

Skill task (ext4 -- "Currency-Input Payment Form with Value Transforms"):
build a self-contained payment form on top of the react-hook-form library's
own public API whose controlled inputs render formatted *display strings* to
the user but commit *typed primitives* to form state:

  - `amount`     -- displayed as a decimal currency string (e.g. "12.50") but
                    stored in form state as an integer number of cents (1250).
  - `cardLast4`  -- stored as a digits-only string of length <= 4; non-digits
                    are stripped and overflow past 4 digits is truncated.
  - `currency`   -- a USD / EUR select.

Deliverables verified (REPO_DIR = /workspace/react-hook-form):
  - src/__tests__/examples/paymentForm.tsx        (the feature component)
  - src/__tests__/examples/paymentForm.test.tsx   (the agent's own Jest suite)

What this pytest file does:
  * L1  -- the two deliverable TSX files exist and are minimally well-formed
           (real JSX/component, imports from the library's own source, uses
           react-hook-form primitives, declares >= 6 cases).
  * L2  -- runs the agent's own native suite via the exact required command
           (`TEST_ENV=web pnpm test -- ... paymentForm.test.tsx`, which the
           repo's package.json maps to jest with scripts/jest/jest.config.js)
           and asserts the required number of cases pass.
  * L2  -- INDEPENDENT DRIVER: writes our OWN jest spec next to the agent's
           component, imports the agent's payment form, and drives the
           display-vs-stored transforms directly through rendered DOM:
             - typing "12.50" -> submitted amount === 1250, input still "12.50"
             - "0.05" -> 5 ; clearing -> 0 (never NaN/undefined)
             - "12a34" -> "1234" ; "123456" -> "1234" (digits-only, <= 4)
             - defaultValues {amount:999, cardLast4:'4242'} display "9.99"/"4242"
             - Reset restores the formatted default & integer-default state
             - submit payload shapes: amount integer, cardLast4 digit string
           A naive implementation that stores the raw display string for
           `amount`, or that lets letters into `cardLast4`, fails these.

The driver leans only on requirement-mandated, stable affordances (an
`amount` input, a `cardLast4` input, a `currency` select, "Submit" and
"Reset" buttons, and the test-supplied `onSubmit` mock), so a conforming
component must satisfy it while a stub cannot.
"""

import json
import os
import shutil
import subprocess

import pytest

REPO_DIR = "/workspace/react-hook-form"
EXAMPLES_DIR = os.path.join(REPO_DIR, "src", "__tests__", "examples")
COMPONENT_FILE = os.path.join(EXAMPLES_DIR, "paymentForm.tsx")
AGENT_TEST_FILE = os.path.join(EXAMPLES_DIR, "paymentForm.test.tsx")

# Spec we inject ourselves; cleaned up after the run.
DRIVER_BASENAME = "paymentFormDriver.zz.test.tsx"
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
# It imports the agent's component and validates the gameable behaviors:
# the display-vs-stored value transforms at the controlled-input boundary.
# --------------------------------------------------------------------------- #
DRIVER_SPEC = r"""
import * as React from 'react';
import {
  render,
  screen,
  fireEvent,
  waitFor,
} from '@testing-library/react';

import * as Mod from './paymentForm';

// Resolve the exported payment-form component regardless of its name.
function resolveComponent(): React.ComponentType<any> {
  const m: any = Mod as any;
  if (typeof m.default === 'function') return m.default;
  const named = ['PaymentForm', 'Payment', 'CurrencyForm', 'CheckoutForm', 'Form'];
  for (const n of named) {
    if (typeof m[n] === 'function') return m[n];
  }
  for (const k of Object.keys(m)) {
    if (typeof m[k] === 'function') return m[k];
  }
  throw new Error('could not resolve payment form component from module');
}

const PaymentForm = resolveComponent();

// ---- field resolvers using stable, requirement-mandated affordances ----

function fieldByHints(hintRe: RegExp): HTMLInputElement {
  // Try accessible name, then name attr, then placeholder/testid.
  const byLabel = screen.queryByLabelText(hintRe) as HTMLInputElement | null;
  if (byLabel) return byLabel;
  const all = Array.from(
    document.querySelectorAll('input,select'),
  ) as HTMLInputElement[];
  const hit = all.find((el) => {
    const hay = [
      el.getAttribute('name') || '',
      el.getAttribute('aria-label') || '',
      el.getAttribute('placeholder') || '',
      el.getAttribute('data-testid') || '',
      el.id || '',
    ]
      .join(' ')
      .toLowerCase();
    return hintRe.test(hay);
  });
  if (hit) return hit;
  throw new Error('field not found for hint ' + hintRe);
}

function amountInput(): HTMLInputElement {
  return fieldByHints(/amount/);
}

function cardInput(): HTMLInputElement {
  return fieldByHints(/card|last4|last_4|cardlast4/);
}

function currencySelect(): HTMLSelectElement | null {
  const all = Array.from(
    document.querySelectorAll('select'),
  ) as HTMLSelectElement[];
  return (
    all.find((el) => {
      const hay = [
        el.getAttribute('name') || '',
        el.getAttribute('aria-label') || '',
        el.getAttribute('data-testid') || '',
        el.id || '',
      ]
        .join(' ')
        .toLowerCase();
      return /currency/.test(hay);
    }) || null
  );
}

function submitButton(): HTMLElement {
  return screen.getByRole('button', { name: /submit|pay/i });
}

function resetButton(): HTMLElement {
  return screen.getByRole('button', { name: /reset/i });
}

function setInput(el: HTMLInputElement, value: string) {
  fireEvent.change(el, { target: { value } });
}

// Submit and return the values object captured by the onSubmit mock.
async function submitAndCapture(onSubmit: jest.Mock): Promise<any> {
  const calls = onSubmit.mock.calls.length;
  fireEvent.click(submitButton());
  await waitFor(() => {
    expect(onSubmit.mock.calls.length).toBeGreaterThan(calls);
  });
  return onSubmit.mock.calls[onSubmit.mock.calls.length - 1][0];
}

describe('paymentForm driver (independent)', () => {
  test('amount transform: typing 12.50 stores 1250 and still displays 12.50', async () => {
    const onSubmit = jest.fn().mockResolvedValue(undefined);
    render(<PaymentForm onSubmit={onSubmit} />);
    const amount = amountInput();
    setInput(amount, '12.50');
    // displayed value is the formatted decimal string, not the raw cents
    expect(amount.value).toBe('12.50');
    const values = await submitAndCapture(onSubmit);
    expect(typeof values.amount).toBe('number');
    expect(values.amount).toBe(1250);
    // visible input unchanged by submission
    expect(amountInput().value).toBe('12.50');
  });

  test('amount edge cases: 0.05 -> 5, and clearing -> 0 (never NaN/undefined)', async () => {
    const onSubmit = jest.fn().mockResolvedValue(undefined);
    render(<PaymentForm onSubmit={onSubmit} />);
    const amount = amountInput();

    setInput(amount, '0.05');
    let values = await submitAndCapture(onSubmit);
    expect(values.amount).toBe(5);

    setInput(amount, '');
    values = await submitAndCapture(onSubmit);
    expect(values.amount).toBe(0);
    expect(Number.isNaN(values.amount)).toBe(false);
    expect(values.amount).not.toBeUndefined();
  });

  test('card sanitization: 12a34 stores 1234 (letters stripped)', async () => {
    const onSubmit = jest.fn().mockResolvedValue(undefined);
    render(<PaymentForm onSubmit={onSubmit} />);
    setInput(cardInput(), '12a34');
    const values = await submitAndCapture(onSubmit);
    expect(typeof values.cardLast4).toBe('string');
    expect(values.cardLast4).toBe('1234');
    expect(/[^0-9]/.test(values.cardLast4)).toBe(false);
  });

  test('card truncation: 123456 stores 1234 (first four digits only)', async () => {
    const onSubmit = jest.fn().mockResolvedValue(undefined);
    render(<PaymentForm onSubmit={onSubmit} />);
    setInput(cardInput(), '123456');
    const values = await submitAndCapture(onSubmit);
    expect(values.cardLast4).toBe('1234');
    expect(values.cardLast4.length).toBeLessThanOrEqual(4);
  });

  test('default formatting: defaults {amount:999, cardLast4:"4242"} display 9.99 / 4242', () => {
    const onSubmit = jest.fn().mockResolvedValue(undefined);
    render(
      <PaymentForm
        onSubmit={onSubmit}
        defaultValues={{ amount: 999, cardLast4: '4242', currency: 'USD' }}
      />,
    );
    expect(amountInput().value).toBe('9.99');
    expect(cardInput().value).toBe('4242');
  });

  test('reset restores formatted default display and integer-default state', async () => {
    const onSubmit = jest.fn().mockResolvedValue(undefined);
    render(
      <PaymentForm
        onSubmit={onSubmit}
        defaultValues={{ amount: 999, cardLast4: '4242', currency: 'USD' }}
      />,
    );
    const amount = amountInput();
    const card = cardInput();
    // edit away from the defaults
    setInput(amount, '50.00');
    setInput(card, '8888');
    expect(amount.value).toBe('50.00');

    let values = await submitAndCapture(onSubmit);
    expect(values.amount).toBe(5000);

    // reset restores the formatted default in the visible input
    fireEvent.click(resetButton());
    await waitFor(() => {
      expect(amountInput().value).toBe('9.99');
    });
    expect(cardInput().value).toBe('4242');

    // and the stored value is back to the integer default
    values = await submitAndCapture(onSubmit);
    expect(values.amount).toBe(999);
    expect(values.cardLast4).toBe('4242');
  });

  test('submit shapes: amount is an integer number, cardLast4 a digits-only string <= 4', async () => {
    const onSubmit = jest.fn().mockResolvedValue(undefined);
    render(<PaymentForm onSubmit={onSubmit} />);
    setInput(amountInput(), '7.30');
    setInput(cardInput(), '90a12b');
    const values = await submitAndCapture(onSubmit);
    expect(typeof values.amount).toBe('number');
    expect(Number.isInteger(values.amount)).toBe(true);
    expect(values.amount).toBe(730);
    expect(typeof values.cardLast4).toBe('string');
    expect(values.cardLast4).toBe('9012');
    expect(values.cardLast4.length).toBeLessThanOrEqual(4);
    expect(/^[0-9]{0,4}$/.test(values.cardLast4)).toBe(true);
  });

  test('form state never transiently holds the raw display string for amount', async () => {
    // Distinguishes a real cents transform from a naive string store: a
    // component that stored the raw "3.14" string would submit a string, not 314.
    const onSubmit = jest.fn().mockResolvedValue(undefined);
    render(<PaymentForm onSubmit={onSubmit} />);
    const amount = amountInput();
    setInput(amount, '3.1');
    setInput(amount, '3.14');
    expect(amount.value).toBe('3.14');
    const values = await submitAndCapture(onSubmit);
    expect(values.amount).toBe(314);
    expect(typeof values.amount).not.toBe('string');
  });

  test('currency select exposes USD/EUR and is included in the submitted payload', async () => {
    const onSubmit = jest.fn().mockResolvedValue(undefined);
    render(
      <PaymentForm
        onSubmit={onSubmit}
        defaultValues={{ amount: 100, cardLast4: '1111', currency: 'USD' }}
      />,
    );
    const sel = currencySelect();
    expect(sel).not.toBeNull();
    const optionValues = Array.from((sel as HTMLSelectElement).options).map(
      (o) => o.value,
    );
    expect(optionValues).toEqual(expect.arrayContaining(['USD', 'EUR']));
    fireEvent.change(sel as HTMLSelectElement, { target: { value: 'EUR' } });
    const values = await submitAndCapture(onSubmit);
    expect(values.currency).toBe('EUR');
  });
});
"""


# --------------------------------------------------------------------------- #
# L1: deliverable files exist and are minimally well-formed
# --------------------------------------------------------------------------- #
class TestReactHookFormPatterns:
    REPO_DIR = "/workspace/react-hook-form"

    def test_component_file_exists(self):
        """L1: the payment form component file is created at the required path."""
        assert os.path.isfile(COMPONENT_FILE), f"missing {COMPONENT_FILE}"

    def test_agent_test_file_exists(self):
        """L1: the agent's deterministic Jest suite file is created."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing {AGENT_TEST_FILE}"

    def test_component_is_real_tsx(self):
        """L1: component is real TSX -- has JSX, imports library source, not a stub."""
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        assert len(src) > 300, "component file is suspiciously small"
        # imports from the library's own source (relative ../../ entry points)
        assert "import" in src and ".." in src, (
            "component must import from library source"
        )
        # uses at least one of the form / controlled-input primitives that
        # bridge the displayed string and the stored value
        assert any(
            tok in src
            for tok in ("useController", "Controller", "useForm", "register", "setValue")
        ), "component must use react-hook-form primitives"
        # actually renders JSX
        assert "return" in src and ("<" in src and "/>" in src or "</" in src), (
            "component must render JSX"
        )

    def test_agent_suite_has_enough_cases(self):
        """L1: the agent suite declares at least 6 test cases (criteria 1-6)."""
        with open(AGENT_TEST_FILE, encoding="utf-8") as fh:
            src = fh.read()
        n = src.count("it(") + src.count("test(")
        assert n >= 6, f"agent suite must contain >=6 cases, found {n}"

    # ----------------------------------------------------------------------- #
    # L2: run the agent's own native suite (the exact required command).
    # `TEST_ENV=web pnpm test -- <spec>` resolves to jest with the repo config.
    # ----------------------------------------------------------------------- #
    def test_agent_native_suite_passes(self):
        """L2: the agent's paymentForm.test.tsx passes under the required jest command."""
        rel = os.path.join("src", "__tests__", "examples", "paymentForm.test.tsx")
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
    # We write our own spec, run it, parse per-test JSON, and assert each
    # targeted transform behavior individually.
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

    def test_driver_amount_transform(self):
        """L2(driver): typing 12.50 stores 1250 while the input still shows 12.50."""
        self._assert_driver_case("typing 12.50 stores 1250")

    def test_driver_amount_edge_cases(self):
        """L2(driver): 0.05 -> 5 and clearing -> 0 (never NaN/undefined)."""
        self._assert_driver_case("amount edge cases")

    def test_driver_card_sanitization(self):
        """L2(driver): typing 12a34 stores the digits-only string 1234."""
        self._assert_driver_case("card sanitization")

    def test_driver_card_truncation(self):
        """L2(driver): typing 123456 stores only the first four digits, 1234."""
        self._assert_driver_case("card truncation")

    def test_driver_default_formatting(self):
        """L2(driver): integer defaults render as their formatted display strings."""
        self._assert_driver_case("default formatting")

    def test_driver_reset_restores_defaults(self):
        """L2(driver): Reset restores formatted display and integer-default state."""
        self._assert_driver_case("reset restores formatted default")

    def test_driver_submit_shapes(self):
        """L2(driver): submit payload has integer amount and digits-only cardLast4 <=4."""
        self._assert_driver_case("submit shapes")

    def test_driver_no_transient_raw_string(self):
        """L2(driver): form state never holds the raw display string for amount."""
        self._assert_driver_case("never transiently holds the raw display string")

    def test_driver_currency_select(self):
        """L2(driver): currency select offers USD/EUR and is in the submitted payload."""
        self._assert_driver_case("currency select exposes")
