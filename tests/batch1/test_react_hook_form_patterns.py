"""Tests for the `react-hook-form-patterns` skill.

Skill task: build a render-isolated invoice line-items form on top of the
react-hook-form library's own public API, plus a deterministic Jest suite.

Deliverables verified (REPO_DIR = /workspace/react-hook-form):
  - src/__tests__/examples/invoiceForm.tsx       (the feature component)
  - src/__tests__/examples/invoiceForm.test.tsx  (the agent's own Jest suite)

What this pytest file does:
  * L1  -- the two deliverable TSX files exist and are minimally well-formed
           (real JSX/component, imports from the library, not stubs).
  * L2  -- runs the agent's own native suite via the exact required command
           (`TEST_ENV=web pnpm jest ... invoiceForm.test.tsx`) and asserts the
           specified number of cases pass.
  * L2  -- INDEPENDENT DRIVER: writes our own Jest spec next to the component,
           imports the agent's invoiceForm component, and exercises the
           hard-to-fake behaviors directly through rendered DOM:
             - empty render / add item / running total
             - remove-middle preserves the other rows' edited values & order
             - move-up preserves per-row identity (no index-as-key smearing)
             - customer keystrokes do NOT re-render the top-level form body
             - async submit success clears the form
             - async submit failure preserves values + shows error, then clears
           A naive implementation (whole-form re-render per keystroke, or
           index-mirrored array state) fails the move/render-isolation specs.

All identifiers we query (the texts "Add item", "Remove", "Move up",
"Total:", "Form renders:", "Submitting..."/aria-busy, "Submission failed")
are mandated verbatim by the requirement document, so a conforming component
must expose them.
"""

import json
import os
import shutil
import subprocess

import pytest

REPO_DIR = "/workspace/react-hook-form"
EXAMPLES_DIR = os.path.join(REPO_DIR, "src", "__tests__", "examples")
COMPONENT_FILE = os.path.join(EXAMPLES_DIR, "invoiceForm.tsx")
AGENT_TEST_FILE = os.path.join(EXAMPLES_DIR, "invoiceForm.test.tsx")

# Spec we inject ourselves; cleaned up after the run.
DRIVER_BASENAME = "invoiceFormDriver.zz.test.tsx"
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
    """Best-effort parse of jest's '--json'-free textual summary -> (passed, failed, total)."""
    blob = (stdout or "") + "\n" + (stderr or "")
    # Look for the 'Tests:' summary line, e.g. 'Tests: 8 passed, 8 total'
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

    # jest prints the JSON to stdout; locate the JSON object.
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
  within,
} from '@testing-library/react';

import * as Mod from './invoiceForm';

// Resolve the exported invoice-form component regardless of its name.
function resolveComponent(): React.ComponentType<any> {
  const m: any = Mod as any;
  if (typeof m.default === 'function') return m.default;
  const named = [
    'InvoiceForm',
    'Invoice',
    'InvoiceLineItemsForm',
    'LineItemsForm',
    'Form',
  ];
  for (const n of named) {
    if (typeof m[n] === 'function') return m[n];
  }
  // Fall back: first function export.
  for (const k of Object.keys(m)) {
    if (typeof m[k] === 'function') return m[k];
  }
  throw new Error('could not resolve invoice form component from module');
}

const InvoiceForm = resolveComponent();

// ---- helpers that lean only on requirement-mandated, stable affordances ----

function getAddButton(): HTMLElement {
  return screen.getByRole('button', { name: /add item/i });
}

function getRows(): HTMLElement[] {
  // A "row" must contain its own Remove control. We group by the Remove
  // buttons' nearest container that also holds three inputs.
  const removeButtons = screen
    .queryAllByRole('button', { name: /remove/i });
  const rows: HTMLElement[] = [];
  for (const btn of removeButtons) {
    let el: HTMLElement | null = btn;
    while (el && el.parentElement) {
      el = el.parentElement;
      const inputs = el.querySelectorAll('input');
      if (inputs.length >= 3) {
        rows.push(el);
        break;
      }
    }
  }
  return rows;
}

function rowInputs(row: HTMLElement): HTMLInputElement[] {
  return Array.from(row.querySelectorAll('input')) as HTMLInputElement[];
}

// classify the three inputs of a row into description/quantity/unitPrice
// using type/value heuristics; description is the text input.
function classifyRow(row: HTMLElement) {
  const inputs = rowInputs(row);
  // Prefer name/aria/placeholder hints.
  const find = (re: RegExp) =>
    inputs.find((i) => {
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
  const description =
    find(/desc/) ||
    inputs.find((i) => (i.getAttribute('type') || 'text') === 'text');
  const quantity = find(/qty|quantity/);
  const unitPrice = find(/price|unit/);
  const numeric = inputs.filter((i) => i !== description);
  return {
    description: description || inputs[0],
    quantity: quantity || numeric[0],
    unitPrice: unitPrice || numeric[1],
    all: inputs,
  };
}

function readTotal(): number {
  // Requirement: a running total rendered as plain number, e.g. "Total: 42".
  const node = screen.getByText(/total:/i);
  const m = (node.textContent || '').match(/total:\s*(-?\d+(?:\.\d+)?)/i);
  if (!m) throw new Error('total text not in expected form: ' + node.textContent);
  return Number(m[1]);
}

function readFormRenders(): number {
  // Requirement: top-level component renders "Form renders: N".
  const node = screen.getByText(/form renders:/i);
  const m = (node.textContent || '').match(/form renders:\s*(\d+)/i);
  if (!m) throw new Error('render counter not found: ' + node.textContent);
  return Number(m[1]);
}

function getCustomerInput(): HTMLInputElement {
  // top-level customer text input, by accessible name or name attr.
  const byLabel = screen.queryByLabelText(/customer/i) as HTMLInputElement | null;
  if (byLabel) return byLabel;
  const byRole = screen.queryByRole('textbox', {
    name: /customer/i,
  }) as HTMLInputElement | null;
  if (byRole) return byRole;
  const byName = document.querySelector(
    'input[name="customer"]',
  ) as HTMLInputElement | null;
  if (byName) return byName;
  throw new Error('customer input not found');
}

function setInput(input: HTMLInputElement, value: string) {
  fireEvent.change(input, { target: { value } });
}

describe('invoiceForm driver (independent)', () => {
  test('empty render: customer input present, no rows, total 0', () => {
    render(<InvoiceForm onSubmit={jest.fn().mockResolvedValue(undefined)} />);
    expect(getCustomerInput()).toBeInTheDocument();
    expect(getRows().length).toBe(0);
    expect(readTotal()).toBe(0);
  });

  test('add item creates editable rows', () => {
    render(<InvoiceForm onSubmit={jest.fn().mockResolvedValue(undefined)} />);
    fireEvent.click(getAddButton());
    expect(getRows().length).toBe(1);
    fireEvent.click(getAddButton());
    expect(getRows().length).toBe(2);
    // each fresh row has exactly three inputs, all empty/zero (not undefined)
    for (const row of getRows()) {
      const inputs = rowInputs(row);
      expect(inputs.length).toBeGreaterThanOrEqual(3);
      for (const i of inputs) {
        expect(i.value === '' || i.value === '0').toBe(true);
      }
    }
  });

  test('running total = sum of quantity*unitPrice', () => {
    render(<InvoiceForm onSubmit={jest.fn().mockResolvedValue(undefined)} />);
    fireEvent.click(getAddButton());
    fireEvent.click(getAddButton());
    const rows = getRows();
    const r0 = classifyRow(rows[0]);
    const r1 = classifyRow(rows[1]);
    setInput(r0.quantity, '3');
    setInput(r0.unitPrice, '4');
    setInput(r1.quantity, '2');
    setInput(r1.unitPrice, '5');
    expect(readTotal()).toBe(22);
    // change one and confirm it recomputes
    setInput(r1.quantity, '4');
    expect(readTotal()).toBe(32);
  });

  test('remove middle row preserves other rows values and order', () => {
    render(<InvoiceForm onSubmit={jest.fn().mockResolvedValue(undefined)} />);
    fireEvent.click(getAddButton());
    fireEvent.click(getAddButton());
    fireEvent.click(getAddButton());
    let rows = getRows();
    expect(rows.length).toBe(3);
    const descs = ['alpha', 'beta', 'gamma'];
    rows.forEach((row, idx) => {
      setInput(classifyRow(row).description, descs[idx]);
    });
    // remove the middle row
    const middleRemove = within(rows[1]).getByRole('button', {
      name: /remove/i,
    });
    fireEvent.click(middleRemove);
    rows = getRows();
    expect(rows.length).toBe(2);
    expect(classifyRow(rows[0]).description.value).toBe('alpha');
    expect(classifyRow(rows[1]).description.value).toBe('gamma');
  });

  test('move up preserves per-row identity (no index smearing)', () => {
    render(<InvoiceForm onSubmit={jest.fn().mockResolvedValue(undefined)} />);
    fireEvent.click(getAddButton());
    fireEvent.click(getAddButton());
    let rows = getRows();
    const r0 = classifyRow(rows[0]);
    const r1 = classifyRow(rows[1]);
    setInput(r0.description, 'first');
    setInput(r0.quantity, '2');
    setInput(r0.unitPrice, '3');
    setInput(r1.description, 'second');
    setInput(r1.quantity, '5');
    setInput(r1.unitPrice, '7');
    expect(readTotal()).toBe(2 * 3 + 5 * 7);
    // move the second row up
    const moveUp = within(rows[1]).getByRole('button', { name: /move up/i });
    fireEvent.click(moveUp);
    rows = getRows();
    const n0 = classifyRow(rows[0]);
    const n1 = classifyRow(rows[1]);
    // values must travel with their logical row
    expect(n0.description.value).toBe('second');
    expect(n0.quantity.value).toBe('5');
    expect(n0.unitPrice.value).toBe('7');
    expect(n1.description.value).toBe('first');
    expect(n1.quantity.value).toBe('2');
    expect(n1.unitPrice.value).toBe('3');
    // total unchanged by a pure reorder
    expect(readTotal()).toBe(2 * 3 + 5 * 7);
  });

  test('customer keystrokes do not re-render the top-level form body', () => {
    render(<InvoiceForm onSubmit={jest.fn().mockResolvedValue(undefined)} />);
    // add a row so there is structural content whose re-render we could detect
    fireEvent.click(getAddButton());
    const before = readFormRenders();
    const customer = getCustomerInput();
    for (const ch of ['A', 'Ac', 'Acm', 'Acme']) {
      setInput(customer, ch);
    }
    const after = readFormRenders();
    expect(customer.value).toBe('Acme');
    // The top-level form body must NOT re-render per keystroke.
    expect(after).toBe(before);
  });

  test('async submit success clears the form', async () => {
    let resolveFn: (v?: unknown) => void = () => {};
    const onSubmit = jest.fn(
      () =>
        new Promise<void>((res) => {
          resolveFn = res;
        }),
    );
    render(<InvoiceForm onSubmit={onSubmit} />);
    setInput(getCustomerInput(), 'Globex');
    fireEvent.click(getAddButton());
    const row = classifyRow(getRows()[0]);
    setInput(row.description, 'widget');
    setInput(row.quantity, '2');
    setInput(row.unitPrice, '9');

    const submit = screen.getByRole('button', { name: /submit/i });
    fireEvent.click(submit);

    // pending indicator while the promise is unresolved
    await waitFor(() => {
      const pending =
        screen.queryByText(/submitting/i) ||
        document.querySelector('[aria-busy="true"]');
      expect(pending).toBeTruthy();
    });
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const submittedValues = onSubmit.mock.calls[0][0];
    expect(submittedValues.customer).toBe('Globex');
    expect(Array.isArray(submittedValues.items)).toBe(true);
    expect(submittedValues.items.length).toBe(1);
    expect(String(submittedValues.items[0].description)).toBe('widget');
    expect(Number(submittedValues.items[0].quantity)).toBe(2);
    expect(Number(submittedValues.items[0].unitPrice)).toBe(9);

    resolveFn();
    await waitFor(() => {
      expect(getRows().length).toBe(0);
    });
    expect(getCustomerInput().value).toBe('');
    expect(readTotal()).toBe(0);
  });

  test('async submit failure preserves values, shows error, then recovers', async () => {
    let rejectFn: (e?: unknown) => void = () => {};
    let resolveFn: (v?: unknown) => void = () => {};
    let phase = 0;
    const onSubmit = jest.fn(() => {
      if (phase === 0) {
        return new Promise<void>((_res, rej) => {
          rejectFn = rej;
        });
      }
      return new Promise<void>((res) => {
        resolveFn = res;
      });
    });
    render(<InvoiceForm onSubmit={onSubmit} />);
    setInput(getCustomerInput(), 'Initech');
    fireEvent.click(getAddButton());
    const row = classifyRow(getRows()[0]);
    setInput(row.description, 'gizmo');
    setInput(row.quantity, '3');
    setInput(row.unitPrice, '4');

    const submit = screen.getByRole('button', { name: /submit/i });
    fireEvent.click(submit);
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));

    // reject the submission
    rejectFn(new Error('boom'));

    // error message appears, values preserved, pending ended
    await waitFor(() => {
      expect(screen.getByText(/submission failed/i)).toBeInTheDocument();
    });
    expect(getRows().length).toBe(1);
    expect(getCustomerInput().value).toBe('Initech');
    const stillThere = classifyRow(getRows()[0]);
    expect(stillThere.description.value).toBe('gizmo');
    // not stuck pending
    await waitFor(() => {
      const pending =
        screen.queryByText(/submitting/i) ||
        document.querySelector('[aria-busy="true"]');
      expect(pending).toBeFalsy();
    });

    // a subsequent successful submit clears the error and the form
    phase = 1;
    fireEvent.click(screen.getByRole('button', { name: /submit/i }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2));
    resolveFn();
    await waitFor(() => {
      expect(screen.queryByText(/submission failed/i)).toBeNull();
    });
    await waitFor(() => {
      expect(getRows().length).toBe(0);
    });
    expect(getCustomerInput().value).toBe('');
  });
});
"""


# --------------------------------------------------------------------------- #
# L1: deliverable files exist and are minimally well-formed
# --------------------------------------------------------------------------- #
class TestReactHookFormPatterns:
    REPO_DIR = "/workspace/react-hook-form"

    def test_component_file_exists(self):
        """L1: the invoice form component file is created at the required path."""
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
        assert "import" in src and ".." in src, "component must import from library source"
        # uses at least one of the field-array / form primitives
        assert any(
            tok in src
            for tok in ("useFieldArray", "useForm", "useController", "useWatch", "Controller")
        ), "component must use react-hook-form primitives"
        # actually renders JSX
        assert "return" in src and ("<" in src and "/>" in src or "</" in src), (
            "component must render JSX"
        )

    def test_agent_suite_has_enough_cases(self):
        """L1: the agent suite declares at least 8 test cases (criteria 1-8)."""
        with open(AGENT_TEST_FILE, encoding="utf-8") as fh:
            src = fh.read()
        n = src.count("it(") + src.count("test(")
        assert n >= 8, f"agent suite must contain >=8 cases, found {n}"

    # ----------------------------------------------------------------------- #
    # L2: run the agent's own native suite (the exact required command).
    # ----------------------------------------------------------------------- #
    def test_agent_native_suite_passes(self):
        """L2: the agent's invoiceForm.test.tsx passes under the required jest command."""
        rel = os.path.join("src", "__tests__", "examples", "invoiceForm.test.tsx")
        proc = _run_jest(rel)
        passed, failed, total = _jest_summary(proc.stdout, proc.stderr)
        assert proc.returncode == 0, (
            "agent native suite failed.\n"
            f"summary passed={passed} failed={failed} total={total}\n"
            f"STDOUT(tail):\n{proc.stdout[-3000:]}\n"
            f"STDERR(tail):\n{proc.stderr[-3000:]}"
        )
        assert total is not None and total >= 8, (
            f"expected >=8 tests in agent suite, parsed total={total}\n{proc.stderr[-1500:]}"
        )
        assert failed in (0, None), f"agent suite reported failures: {failed}"

    # ----------------------------------------------------------------------- #
    # L2: independent driver suite -- this is the discriminative core.
    # We write our own spec, run it, parse the per-test JSON results, and
    # assert each targeted behavior individually.
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

    def test_driver_empty_render(self):
        """L2(driver): fresh form shows customer input, zero rows, total 0."""
        self._assert_driver_case("empty render")

    def test_driver_add_item(self):
        """L2(driver): 'Add item' appends fully-formed editable rows."""
        self._assert_driver_case("add item creates editable rows")

    def test_driver_running_total(self):
        """L2(driver): total equals sum of quantity*unitPrice and recomputes live."""
        self._assert_driver_case("running total")

    def test_driver_remove_preserves_others(self):
        """L2(driver): removing the middle row preserves the other rows' values/order."""
        self._assert_driver_case("remove middle row preserves")

    def test_driver_move_preserves_identity(self):
        """L2(driver): move-up swaps rows with values intact (no index-as-key smearing)."""
        self._assert_driver_case("move up preserves per-row identity")

    def test_driver_customer_keystrokes_isolated(self):
        """L2(driver): customer keystrokes must not bump the top-level form render count."""
        self._assert_driver_case("customer keystrokes do not re-render")

    def test_driver_async_submit_success(self):
        """L2(driver): async submit shows pending, calls onSubmit once, then clears form."""
        self._assert_driver_case("async submit success clears the form")

    def test_driver_async_submit_failure(self):
        """L2(driver): rejected submit preserves values + shows error, then recovers."""
        self._assert_driver_case("async submit failure preserves values")
