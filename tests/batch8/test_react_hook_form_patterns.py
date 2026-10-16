"""Tests for the `react-hook-form-patterns` skill (variant ext8).

Skill task (ext8 -- DISTINCT from ext1): build a self-contained "trip booking"
form on top of the react-hook-form library's own public API, in which the set
of *visible* fields and their *validation rules* depend on the current value of
other fields (dependent fields / conditional validation), plus a deterministic
Jest suite pinning that behavior.

Deliverables verified (REPO_DIR = /workspace/react-hook-form):
  - src/__tests__/examples/bookingForm.tsx       (the feature component)
  - src/__tests__/examples/bookingForm.test.tsx  (the agent's own Jest suite)

Form shape mandated by the requirement doc:
  - tripType        select: 'oneway' | 'roundtrip'
  - departDate      text, always shown
  - returnDate      text, shown ONLY when tripType === 'roundtrip', then required
  - passengers      number, min 1
  - needsAssistance checkbox; when true a required `assistanceNotes` textarea appears

What this pytest file does:
  * L1  -- the two deliverable TSX files exist and are minimally well-formed
           (real JSX/component, imports from the library, uses rhf primitives,
           not stubs).
  * L2  -- runs the agent's own native suite via the exact required command
           (`TEST_ENV=web pnpm test -- ... bookingForm.test.tsx`) and asserts the
           specified number of cases pass.
  * L2  -- INDEPENDENT DRIVER: writes our own Jest spec next to the component,
           imports the agent's bookingForm component, and exercises the
           hard-to-fake behaviors directly through rendered DOM:
             - returnDate hidden for oneway, appears for roundtrip
             - roundtrip + empty returnDate -> field error, onSubmit NOT called
             - needsAssistance toggle reveals/removes required assistanceNotes
             - passengers floor (0/empty -> error & blocked; >=1 accepted)
             - one-way payload omits returnDate/assistanceNotes
             - round-trip + assistance payload includes both
             - switching roundtrip->oneway hides returnDate and its prior value
               does NOT leak into the submitted payload
           A naive implementation that mirrors `tripType` in independent local
           state, or that always submits hidden-field values, fails the
           visibility and payload specs.

The DRIVER deliberately does not trust the agent's own tests: it drives the
agent's component directly through rendered DOM and a test-supplied onSubmit
mock, asserting concrete payload keys/values, error visibility and call counts.
"""

import json
import os
import shutil
import subprocess

import pytest

REPO_DIR = "/workspace/react-hook-form"
EXAMPLES_DIR = os.path.join(REPO_DIR, "src", "__tests__", "examples")
COMPONENT_FILE = os.path.join(EXAMPLES_DIR, "bookingForm.tsx")
AGENT_TEST_FILE = os.path.join(EXAMPLES_DIR, "bookingForm.test.tsx")

# Spec we inject ourselves; cleaned up after the run.
DRIVER_BASENAME = "bookingFormDriver.zz.test.tsx"
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
# conditional visibility, conditional validation, and payload shaping.
# All affordances we query are mandated by the requirement document.
# --------------------------------------------------------------------------- #
DRIVER_SPEC = r"""
import * as React from 'react';
import {
  render,
  screen,
  fireEvent,
  waitFor,
} from '@testing-library/react';

import * as Mod from './bookingForm';

// Resolve the exported booking-form component regardless of its name.
function resolveComponent(): React.ComponentType<any> {
  const m: any = Mod as any;
  if (typeof m.default === 'function') return m.default;
  const named = [
    'BookingForm',
    'Booking',
    'TripBookingForm',
    'TripForm',
    'Form',
  ];
  for (const n of named) {
    if (typeof m[n] === 'function') return m[n];
  }
  for (const k of Object.keys(m)) {
    if (typeof m[k] === 'function') return m[k];
  }
  throw new Error('could not resolve booking form component from module');
}

const BookingForm = resolveComponent();

// ----------------------- field accessors (robust) ------------------------ //
// Each control is located by name attribute first (the form registers fields
// by name), falling back to accessible name / label / role.

function byName<T extends HTMLElement = HTMLElement>(name: string): T | null {
  return document.querySelector(`[name="${name}"]`) as T | null;
}

function getTripType(): HTMLSelectElement {
  const el =
    (byName<HTMLSelectElement>('tripType')) ||
    (screen.queryByLabelText(/trip ?type/i) as HTMLSelectElement | null) ||
    (screen.queryByRole('combobox') as HTMLSelectElement | null);
  if (!el) throw new Error('tripType control not found');
  return el;
}

function queryReturnDate(): HTMLInputElement | null {
  return (
    byName<HTMLInputElement>('returnDate') ||
    (screen.queryByLabelText(/return ?date/i) as HTMLInputElement | null)
  );
}

function getDepartDate(): HTMLInputElement {
  const el =
    byName<HTMLInputElement>('departDate') ||
    (screen.queryByLabelText(/depart/i) as HTMLInputElement | null);
  if (!el) throw new Error('departDate control not found');
  return el;
}

function getPassengers(): HTMLInputElement {
  const el =
    byName<HTMLInputElement>('passengers') ||
    (screen.queryByLabelText(/passenger/i) as HTMLInputElement | null);
  if (!el) throw new Error('passengers control not found');
  return el;
}

function getNeedsAssistance(): HTMLInputElement {
  const el =
    byName<HTMLInputElement>('needsAssistance') ||
    (screen.queryByLabelText(/assist/i) as HTMLInputElement | null) ||
    (screen.queryByRole('checkbox') as HTMLInputElement | null);
  if (!el) throw new Error('needsAssistance control not found');
  return el;
}

function queryAssistanceNotes(): HTMLElement | null {
  return (
    byName('assistanceNotes') ||
    (screen.queryByLabelText(/assistance ?notes|notes/i) as HTMLElement | null)
  );
}

function getSubmit(): HTMLElement {
  return screen.getByRole('button', { name: /submit|book/i });
}

function setValue(el: HTMLElement, value: string) {
  fireEvent.input(el as HTMLInputElement, { target: { value } });
  fireEvent.change(el as HTMLInputElement, { target: { value } });
}

function selectTripType(value: 'oneway' | 'roundtrip') {
  const sel = getTripType();
  fireEvent.change(sel, { target: { value } });
}

function makeOnSubmit() {
  return jest.fn().mockResolvedValue(undefined);
}

// react-hook-form runs validation asynchronously; submit then settle.
async function submitForm() {
  fireEvent.click(getSubmit());
}

describe('bookingForm driver (independent)', () => {
  test('conditional visibility: returnDate hidden for oneway, shown for roundtrip', async () => {
    render(<BookingForm onSubmit={makeOnSubmit()} />);
    // default should be oneway -> returnDate not rendered
    selectTripType('oneway');
    await waitFor(() => {
      expect(queryReturnDate()).toBeNull();
    });
    // switch to roundtrip -> returnDate appears
    selectTripType('roundtrip');
    await waitFor(() => {
      expect(queryReturnDate()).not.toBeNull();
    });
    // and switching back hides it again
    selectTripType('oneway');
    await waitFor(() => {
      expect(queryReturnDate()).toBeNull();
    });
  });

  test('conditional requirement: roundtrip with empty returnDate blocks submit', async () => {
    const onSubmit = makeOnSubmit();
    render(<BookingForm onSubmit={onSubmit} />);
    selectTripType('roundtrip');
    await waitFor(() => expect(queryReturnDate()).not.toBeNull());
    // fill the always-valid fields so only returnDate is missing
    setValue(getDepartDate(), '2026-01-01');
    setValue(getPassengers(), '2');
    // leave returnDate empty and submit
    await submitForm();
    // onSubmit must NOT be called; an error must surface
    await waitFor(() => {
      expect(onSubmit).not.toHaveBeenCalled();
    });
    // now fill returnDate -> submit succeeds
    setValue(queryReturnDate() as HTMLInputElement, '2026-01-10');
    await submitForm();
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
  });

  test('assistance toggle: reveals required assistanceNotes; unchecking removes it', async () => {
    const onSubmit = makeOnSubmit();
    render(<BookingForm onSubmit={onSubmit} />);
    selectTripType('oneway');
    setValue(getDepartDate(), '2026-02-02');
    setValue(getPassengers(), '1');
    // initially unchecked -> notes absent
    expect(queryAssistanceNotes()).toBeNull();
    // check -> notes appears
    fireEvent.click(getNeedsAssistance());
    await waitFor(() => {
      expect(queryAssistanceNotes()).not.toBeNull();
    });
    // submit with empty required notes -> blocked
    await submitForm();
    await waitFor(() => expect(onSubmit).not.toHaveBeenCalled());
    // uncheck -> notes removed and requirement gone -> submit succeeds
    fireEvent.click(getNeedsAssistance());
    await waitFor(() => {
      expect(queryAssistanceNotes()).toBeNull();
    });
    await submitForm();
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
  });

  test('passengers floor: 0/empty blocks submit, >=1 accepted', async () => {
    const onSubmit = makeOnSubmit();
    render(<BookingForm onSubmit={onSubmit} />);
    selectTripType('oneway');
    setValue(getDepartDate(), '2026-03-03');
    // 0 passengers -> blocked
    setValue(getPassengers(), '0');
    await submitForm();
    await waitFor(() => expect(onSubmit).not.toHaveBeenCalled());
    // empty -> blocked
    setValue(getPassengers(), '');
    await submitForm();
    await waitFor(() => expect(onSubmit).not.toHaveBeenCalled());
    // 1 -> accepted
    setValue(getPassengers(), '1');
    await submitForm();
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
  });

  test('one-way payload omits returnDate / assistanceNotes', async () => {
    const onSubmit = makeOnSubmit();
    render(<BookingForm onSubmit={onSubmit} />);
    selectTripType('oneway');
    setValue(getDepartDate(), '2026-04-04');
    setValue(getPassengers(), '3');
    await submitForm();
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const values = onSubmit.mock.calls[0][0];
    // core fields present
    expect(String(values.tripType)).toBe('oneway');
    expect(String(values.departDate)).toBe('2026-04-04');
    expect(Number(values.passengers)).toBe(3);
    // hidden fields must NOT carry meaningful values
    const rd = values.returnDate;
    expect(rd === undefined || rd === null || rd === '').toBe(true);
    const notes = values.assistanceNotes;
    expect(notes === undefined || notes === null || notes === '').toBe(true);
  });

  test('round-trip with assistance payload includes returnDate and assistanceNotes', async () => {
    const onSubmit = makeOnSubmit();
    render(<BookingForm onSubmit={onSubmit} />);
    selectTripType('roundtrip');
    await waitFor(() => expect(queryReturnDate()).not.toBeNull());
    setValue(getDepartDate(), '2026-05-05');
    setValue(queryReturnDate() as HTMLInputElement, '2026-05-12');
    setValue(getPassengers(), '2');
    fireEvent.click(getNeedsAssistance());
    await waitFor(() => expect(queryAssistanceNotes()).not.toBeNull());
    setValue(queryAssistanceNotes() as HTMLElement, 'wheelchair please');
    await submitForm();
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const values = onSubmit.mock.calls[0][0];
    expect(String(values.tripType)).toBe('roundtrip');
    expect(String(values.departDate)).toBe('2026-05-05');
    expect(String(values.returnDate)).toBe('2026-05-12');
    expect(Number(values.passengers)).toBe(2);
    expect(String(values.assistanceNotes)).toBe('wheelchair please');
  });

  test('switching roundtrip->oneway does not leak prior returnDate into payload', async () => {
    const onSubmit = makeOnSubmit();
    render(<BookingForm onSubmit={onSubmit} />);
    // set roundtrip and a returnDate value
    selectTripType('roundtrip');
    await waitFor(() => expect(queryReturnDate()).not.toBeNull());
    setValue(getDepartDate(), '2026-06-06');
    setValue(queryReturnDate() as HTMLInputElement, '2026-06-20');
    setValue(getPassengers(), '1');
    // now switch back to oneway -> returnDate must hide
    selectTripType('oneway');
    await waitFor(() => expect(queryReturnDate()).toBeNull());
    await submitForm();
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const values = onSubmit.mock.calls[0][0];
    expect(String(values.tripType)).toBe('oneway');
    // prior returnDate value must not survive into the one-way payload
    const rd = values.returnDate;
    expect(rd === undefined || rd === null || rd === '').toBe(true);
  });
});
"""


# --------------------------------------------------------------------------- #
# L1: deliverable files exist and are minimally well-formed
# --------------------------------------------------------------------------- #
class TestReactHookFormPatterns:
    REPO_DIR = "/workspace/react-hook-form"

    def test_component_file_exists(self):
        """L1: the booking form component file is created at the required path."""
        assert os.path.isfile(COMPONENT_FILE), f"missing {COMPONENT_FILE}"

    def test_agent_test_file_exists(self):
        """L1: the agent's deterministic Jest suite file is created."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing {AGENT_TEST_FILE}"

    def test_component_is_real_tsx(self):
        """L1: component is real TSX -- JSX, imports the library, uses rhf primitives."""
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        assert len(src) > 300, "component file is suspiciously small"
        # imports from the library's own source (relative ../../ entry points)
        assert "import" in src and ".." in src, (
            "component must import from library source"
        )
        # uses at least one of the form / value-subscription primitives. The doc
        # mandates reading dependent values through the library's subscription
        # primitives (useWatch / watch / useController), not local mirror state.
        assert any(
            tok in src
            for tok in ("useForm", "useWatch", "watch", "useController", "Controller")
        ), "component must use react-hook-form primitives"
        # actually renders JSX
        assert "return" in src and ("<" in src and "/>" in src or "</" in src), (
            "component must render JSX"
        )

    def test_component_subscribes_to_controlling_fields(self):
        """L1: dependent fields are driven via the form's value subscription.

        The requirement forbids mirroring tripType/needsAssistance in independent
        local state; the conditional UI must read controlling values through the
        library (useWatch/watch). Assert at least one such subscription reads a
        controlling field name.
        """
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        assert ("useWatch" in src) or ("watch(" in src) or (".watch" in src), (
            "component must subscribe to controlling values via useWatch/watch"
        )
        assert "tripType" in src, "component must reference the tripType field"
        assert "needsAssistance" in src, (
            "component must reference the needsAssistance field"
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
        """L2: the agent's bookingForm.test.tsx passes under the required jest command.

        Native acceptance command (doc): TEST_ENV=web pnpm test -- \
            src/__tests__/examples/bookingForm.test.tsx
        """
        rel = os.path.join("src", "__tests__", "examples", "bookingForm.test.tsx")
        proc = _run_jest(rel)
        passed, failed, total = _jest_summary(proc.stdout, proc.stderr)
        assert proc.returncode == 0, (
            "agent native suite failed.\n"
            f"summary passed={passed} failed={failed} total={total}\n"
            f"STDOUT(tail):\n{proc.stdout[-3000:]}\n"
            f"STDERR(tail):\n{proc.stderr[-3000:]}"
        )
        assert total is not None and total >= 6, (
            f"expected >=6 tests in agent suite, parsed total={total}\n"
            f"{proc.stderr[-1500:]}"
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

    def test_driver_conditional_visibility(self):
        """L2(driver): returnDate hidden for oneway, appears for roundtrip, hides again."""
        self._assert_driver_case("conditional visibility")

    def test_driver_conditional_requirement(self):
        """L2(driver): roundtrip + empty returnDate blocks submit; filling it unblocks."""
        self._assert_driver_case("conditional requirement")

    def test_driver_assistance_toggle(self):
        """L2(driver): needsAssistance reveals a required assistanceNotes, unchecking removes it."""
        self._assert_driver_case("assistance toggle")

    def test_driver_passengers_floor(self):
        """L2(driver): passengers 0/empty blocks submit; >=1 is accepted."""
        self._assert_driver_case("passengers floor")

    def test_driver_oneway_payload(self):
        """L2(driver): valid one-way submit omits returnDate/assistanceNotes from payload."""
        self._assert_driver_case("one-way payload")

    def test_driver_roundtrip_payload(self):
        """L2(driver): round-trip with assistance includes returnDate and assistanceNotes."""
        self._assert_driver_case("round-trip with assistance payload")

    def test_driver_no_returndate_leak(self):
        """L2(driver): switching roundtrip->oneway must not leak prior returnDate into payload."""
        self._assert_driver_case("does not leak prior returnDate")
