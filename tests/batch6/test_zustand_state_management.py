"""Benchmark tests for the `zustand-state-management` skill (variant ext6).

Verifies the agent's implementation of a self-contained MULTI-STEP FORM WIZARD
store module built on top of zustand's public vanilla `createStore` API.

Source of truth: tasks/ext6/zustand-state-management.md. The task asks the agent
to create:
  - examples/wizard-store/wizardStore.ts  (factory `createWizardStore` + types)
  - tests/wizardStore.test.ts             (the agent's own Vitest suite)

The wizard models a three-step signup flow:
  step 0 -> { email }, step 1 -> { password }, step 2 -> { displayName }
with `stepIndex`, a `values` object, an `errors` map, and the derived
read-only fields `currentStepValid`, `isComplete`, `stepCount`. Validation:
  - email: non-empty, exactly one '@' with non-empty parts on both sides
  - password: length >= 8
  - displayName: trimmed length in [1, 30]
Actions: setField, next (advances only when currentStepValid), prev (no-op at
step 0, preserves values), reset (back to step 0, clears values + errors).

L1 checks: the deliverable files exist and are minimally well-formed, the module
exports `createWizardStore`, and the agent's own suite passes via
`pnpm vitest run tests/wizardStore.test.ts`.

L2 checks: discriminative DYNAMIC EXECUTION. We DO NOT trust the agent's own
test file. Instead we write INDEPENDENT Vitest drivers into REPO_DIR/tests/ that
import the agent's `createWizardStore` factory directly and exercise real
runtime behavior: per-field error setting/clearing, current-step validity on
each step, next() blocked/advancing/clamped at the last step, prev()
decrement/no-op/value-preservation, isComplete only when all steps valid,
reset() restoring initial state, and a mixed-sequence derived-consistency
invariant recomputed independently. Each driver runs via the repo's native
`pnpm vitest run` and we assert on returncode.

A naive / hardcoded / "always-valid" / "looks related" implementation
(e.g. one that always returns currentStepValid=true, never records errors,
advances past the last step, or drops values on prev()) fails these drivers.

Native acceptance command driven by L2: `pnpm vitest run <driver>`.
"""

import os
import re
import shutil
import subprocess
import uuid

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - helper is present at runtime
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/zustand"
WIZARD_STORE = os.path.join(REPO_DIR, "examples", "wizard-store", "wizardStore.ts")
AGENT_TEST = os.path.join(REPO_DIR, "tests", "wizardStore.test.ts")

# Driver files we create under tests/ so vitest (dir: 'tests') picks them up.
# Each is removed in teardown. Use a unique tag to avoid clobbering anything.
_TAG = uuid.uuid4().hex[:8]
_DRIVER_BASENAME = f"_bench_wizard_driver_{_TAG}.test.ts"
DRIVER_PATH = os.path.join(REPO_DIR, "tests", _DRIVER_BASENAME)

VITEST_TIMEOUT = 600

# Relative import path from a file living in tests/ to the wizard store module.
_IMPORT = "../examples/wizard-store/wizardStore"


def _pnpm_available():
    return shutil.which("pnpm") is not None


@pytest.fixture(scope="module", autouse=True)
def _prepare_deps():
    """Best-effort install of node deps before running native vitest."""
    if ensure_npm_dependencies is not None:
        try:
            ensure_npm_dependencies(REPO_DIR)
        except Exception:
            # The container image typically ships deps preinstalled; if npm
            # install fails (e.g. pnpm-only lockfile) fall back to a pnpm
            # install so the toolchain is usable.
            if _pnpm_available():
                subprocess.run(
                    ["pnpm", "install", "--frozen-lockfile=false"],
                    cwd=REPO_DIR,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )
    yield


def _run_vitest(rel_file):
    """Run `pnpm vitest run <rel_file>` (or npx fallback) from REPO_DIR."""
    if _pnpm_available():
        cmd = ["pnpm", "vitest", "run", rel_file, "--reporter=verbose"]
    else:
        cmd = ["npx", "vitest", "run", rel_file, "--reporter=verbose"]
    return subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=VITEST_TIMEOUT,
    )


def _write_driver(body):
    """Write an independent vitest driver file under tests/ and return basename."""
    os.makedirs(os.path.dirname(DRIVER_PATH), exist_ok=True)
    with open(DRIVER_PATH, "w") as fh:
        fh.write(body)
    return _DRIVER_BASENAME


def _cleanup_driver():
    try:
        if os.path.exists(DRIVER_PATH):
            os.remove(DRIVER_PATH)
    except OSError:
        pass


def _run_driver(body):
    """Helper: write a driver, run it, clean up, return CompletedProcess."""
    rel = _write_driver(body)
    try:
        return _run_vitest(rel)
    finally:
        _cleanup_driver()


def _assert_passed(proc, scenario):
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, (
        f"vitest driver for '{scenario}' failed (rc={proc.returncode}).\n"
        f"{combined[-4000:]}"
    )


# A reusable JS helper, injected into drivers, that independently recomputes the
# expected derived state from `values`/`stepIndex` so we never trust the store's
# own bookkeeping.
_RECOMPUTE_HELPER = r"""
function emailValid(v: string): boolean {
  if (!v) return false
  const parts = v.split('@')
  return parts.length === 2 && parts[0].length > 0 && parts[1].length > 0
}
function passwordValid(v: string): boolean {
  return typeof v === 'string' && v.length >= 8
}
function displayNameValid(v: string): boolean {
  const t = (v ?? '').trim()
  return t.length >= 1 && t.length <= 30
}
function fieldValid(field: string, v: string): boolean {
  if (field === 'email') return emailValid(v)
  if (field === 'password') return passwordValid(v)
  if (field === 'displayName') return displayNameValid(v)
  return false
}
const STEP_FIELD: Record<number, string> = { 0: 'email', 1: 'password', 2: 'displayName' }
function stepValid(values: any, stepIndex: number): boolean {
  return fieldValid(STEP_FIELD[stepIndex], values[STEP_FIELD[stepIndex]] ?? '')
}
function allComplete(values: any): boolean {
  return emailValid(values.email ?? '') && passwordValid(values.password ?? '') && displayNameValid(values.displayName ?? '')
}
"""


class TestZustandStateManagement:
    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------ L1
    def test_wizard_store_module_exists(self):
        """L1: examples/wizard-store/wizardStore.ts exists and is non-trivial."""
        assert os.path.isfile(WIZARD_STORE), f"missing {WIZARD_STORE}"
        size = os.path.getsize(WIZARD_STORE)
        assert size > 200, f"wizardStore.ts suspiciously small ({size} bytes)"

    def test_module_exports_factory(self):
        """L1: module declares an exported `createWizardStore`."""
        with open(WIZARD_STORE) as fh:
            src = fh.read()
        assert re.search(r"export\b.*\bcreateWizardStore\b", src) or re.search(
            r"\bcreateWizardStore\b", src
        ), "createWizardStore not found in wizardStore.ts"

    def test_agent_test_suite_exists(self):
        """L1: the agent's own Vitest suite file exists and is non-trivial."""
        assert os.path.isfile(AGENT_TEST), f"missing {AGENT_TEST}"
        assert os.path.getsize(AGENT_TEST) > 200

    def test_agent_suite_passes(self):
        """L1/L2: the agent's own `tests/wizardStore.test.ts` suite passes.

        The task requires at least 10 cases; verify vitest actually ran a
        healthy number of tests rather than a single rubber-stamp.
        """
        proc = _run_vitest("tests/wizardStore.test.ts")
        _assert_passed(proc, "agent wizardStore.test.ts suite")
        combined = (proc.stdout or "") + (proc.stderr or "")
        m = re.search(r"Tests\s+(\d+)\s+passed", combined)
        if m:
            assert int(m.group(1)) >= 10, (
                f"expected >=10 passing tests, parsed {m.group(1)}\n"
                f"{combined[-2000:]}"
            )

    # ------------------------------------------------------------------ L2
    def test_initial_state_shape(self):
        """L2: fresh store starts at step 0, empty values, no errors, derived ok."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createWizardStore }} from '{_IMPORT}'

describe('bench-initial', () => {{
  it('exposes vanilla handles and a clean initial state', () => {{
    const store = createWizardStore()
    expect(typeof store.getState).toBe('function')
    expect(typeof store.setState).toBe('function')
    expect(typeof store.subscribe).toBe('function')
    const s = store.getState()
    expect(s.stepIndex).toBe(0)
    expect(s.stepCount).toBe(3)
    expect(s.values.email).toBe('')
    expect(s.values.password).toBe('')
    expect(s.values.displayName).toBe('')
    // no values entered yet -> current (email) step is not valid
    expect(s.currentStepValid).toBe(false)
    expect(s.isComplete).toBe(false)
    // errors map has no truthy entries initially
    const errVals = Object.values(s.errors as Record<string, string>)
    expect(errVals.filter((e) => !!e).length).toBe(0)
  }})
}})
"""
        _assert_passed(_run_driver(body), "initial state shape")

    def test_setfield_sets_and_clears_error_email(self):
        """L2: setField('email', ...) toggles errors.email on invalid/valid input."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createWizardStore }} from '{_IMPORT}'

describe('bench-setfield-email', () => {{
  it('records an email error when invalid and clears it when valid', () => {{
    const store = createWizardStore()
    store.getState().setField('email', 'not-an-email')
    let s = store.getState()
    expect(s.values.email).toBe('not-an-email')
    expect(typeof s.errors.email).toBe('string')
    expect((s.errors.email as string).length).toBeGreaterThan(0)
    expect(s.currentStepValid).toBe(false)
    // two @ -> still invalid
    store.getState().setField('email', 'a@@b')
    s = store.getState()
    expect(!!s.errors.email).toBe(true)
    // empty local part -> invalid
    store.getState().setField('email', '@b.com')
    s = store.getState()
    expect(!!s.errors.email).toBe(true)
    // now a valid email clears the error and validates the step
    store.getState().setField('email', 'user@example.com')
    s = store.getState()
    expect(s.values.email).toBe('user@example.com')
    expect(!!s.errors.email).toBe(false)
    expect(s.currentStepValid).toBe(true)
  }})
}})
"""
        _assert_passed(_run_driver(body), "setField email error toggle")

    def test_setfield_password_and_displayname_rules(self):
        """L2: password length>=8 and displayName trimmed length in [1,30]."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createWizardStore }} from '{_IMPORT}'

describe('bench-setfield-rules', () => {{
  it('applies the password and displayName validation rules', () => {{
    const store = createWizardStore()
    // password too short
    store.getState().setField('password', 'short')
    let s = store.getState()
    expect(!!s.errors.password).toBe(true)
    // exactly 8 chars -> valid
    store.getState().setField('password', '12345678')
    s = store.getState()
    expect(!!s.errors.password).toBe(false)
    // displayName: empty after trim -> invalid
    store.getState().setField('displayName', '   ')
    s = store.getState()
    expect(!!s.errors.displayName).toBe(true)
    // 30 chars -> valid (boundary)
    store.getState().setField('displayName', 'x'.repeat(30))
    s = store.getState()
    expect(!!s.errors.displayName).toBe(false)
    // 31 chars -> invalid (boundary)
    store.getState().setField('displayName', 'x'.repeat(31))
    s = store.getState()
    expect(!!s.errors.displayName).toBe(true)
    // trimmed length counts: leading/trailing spaces around a single char -> valid
    store.getState().setField('displayName', '   a   ')
    s = store.getState()
    expect(!!s.errors.displayName).toBe(false)
  }})
}})
"""
        _assert_passed(_run_driver(body), "password + displayName rules")

    def test_currentstepvalid_tracks_active_step_only(self):
        """L2: currentStepValid reflects ONLY the field of the active step."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createWizardStore }} from '{_IMPORT}'

describe('bench-current-step', () => {{
  it('currentStepValid depends on the active step field only', () => {{
    const store = createWizardStore()
    // step 0 needs a valid email; a valid password alone does NOT validate step 0
    store.getState().setField('password', 'longenough')
    expect(store.getState().currentStepValid).toBe(false)
    store.getState().setField('email', 'a@b.co')
    expect(store.getState().currentStepValid).toBe(true)
    // advance to step 1 (password) which we already filled -> valid
    store.getState().next()
    expect(store.getState().stepIndex).toBe(1)
    expect(store.getState().currentStepValid).toBe(true)
    // advance to step 2 (displayName) which is empty -> invalid
    store.getState().next()
    expect(store.getState().stepIndex).toBe(2)
    expect(store.getState().currentStepValid).toBe(false)
  }})
}})
"""
        _assert_passed(_run_driver(body), "currentStepValid active step only")

    def test_next_blocked_on_invalid_step_records_error(self):
        """L2: next() is a no-op on an invalid step and records the step error."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createWizardStore }} from '{_IMPORT}'

describe('bench-next-blocked', () => {{
  it('does not advance and records an error when current step invalid', () => {{
    const store = createWizardStore()
    // step 0 with no/invalid email
    store.getState().setField('email', 'bad')
    store.getState().next()
    let s = store.getState()
    expect(s.stepIndex).toBe(0)
    expect(!!s.errors.email).toBe(true)
    // even with a totally empty email, next stays put and records an error
    const store2 = createWizardStore()
    store2.getState().next()
    s = store2.getState()
    expect(s.stepIndex).toBe(0)
    expect(!!s.errors.email).toBe(true)
  }})
}})
"""
        _assert_passed(_run_driver(body), "next blocked records error")

    def test_next_advances_on_valid_step(self):
        """L2: next() advances stepIndex by one when current step is valid."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createWizardStore }} from '{_IMPORT}'

describe('bench-next-advance', () => {{
  it('advances exactly one step when current step valid', () => {{
    const store = createWizardStore()
    store.getState().setField('email', 'user@example.com')
    expect(store.getState().currentStepValid).toBe(true)
    store.getState().next()
    expect(store.getState().stepIndex).toBe(1)
    store.getState().setField('password', 'supersecret')
    store.getState().next()
    expect(store.getState().stepIndex).toBe(2)
  }})
}})
"""
        _assert_passed(_run_driver(body), "next advances on valid step")

    def test_next_never_advances_past_last_step(self):
        """L2: next() at the last step is clamped and never overflows."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createWizardStore }} from '{_IMPORT}'

describe('bench-next-clamp', () => {{
  it('cannot advance past the last step even when valid', () => {{
    const store = createWizardStore()
    store.getState().setField('email', 'u@e.io')
    store.getState().next()
    store.getState().setField('password', 'passw0rd!')
    store.getState().next()
    store.getState().setField('displayName', 'Ada')
    expect(store.getState().stepIndex).toBe(2)
    expect(store.getState().currentStepValid).toBe(true)
    // extra next() calls must stay clamped at the final step index (2)
    store.getState().next()
    expect(store.getState().stepIndex).toBe(2)
    store.getState().next()
    store.getState().next()
    expect(store.getState().stepIndex).toBe(2)
    expect(store.getState().stepIndex).toBeLessThan(store.getState().stepCount)
  }})
}})
"""
        _assert_passed(_run_driver(body), "next clamped at last step")

    def test_prev_decrements_noop_at_zero_and_preserves_values(self):
        """L2: prev() decrements, is a no-op at step 0, and never clears values."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createWizardStore }} from '{_IMPORT}'

describe('bench-prev', () => {{
  it('prev decrements, no-ops at 0, and preserves entered values', () => {{
    const store = createWizardStore()
    // no-op at step 0
    store.getState().prev()
    expect(store.getState().stepIndex).toBe(0)
    // walk forward to step 2
    store.getState().setField('email', 'user@example.com')
    store.getState().next()
    store.getState().setField('password', 'longpass123')
    store.getState().next()
    expect(store.getState().stepIndex).toBe(2)
    // going back preserves already-entered values
    store.getState().prev()
    let s = store.getState()
    expect(s.stepIndex).toBe(1)
    expect(s.values.email).toBe('user@example.com')
    expect(s.values.password).toBe('longpass123')
    store.getState().prev()
    s = store.getState()
    expect(s.stepIndex).toBe(0)
    expect(s.values.email).toBe('user@example.com')
    // already at 0 -> stays at 0, values intact
    store.getState().prev()
    s = store.getState()
    expect(s.stepIndex).toBe(0)
    expect(s.values.email).toBe('user@example.com')
    expect(s.values.password).toBe('longpass123')
  }})
}})
"""
        _assert_passed(_run_driver(body), "prev decrement/noop/preserve")

    def test_iscomplete_only_when_all_steps_valid(self):
        """L2: isComplete is true only once every field passes validation."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createWizardStore }} from '{_IMPORT}'

describe('bench-iscomplete', () => {{
  it('isComplete flips true only when email, password, displayName all valid', () => {{
    const store = createWizardStore()
    store.getState().setField('email', 'user@example.com')
    expect(store.getState().isComplete).toBe(false)
    store.getState().setField('password', 'longpass123')
    expect(store.getState().isComplete).toBe(false)
    store.getState().setField('displayName', 'Ada')
    expect(store.getState().isComplete).toBe(true)
    // break one field -> isComplete must drop back to false
    store.getState().setField('password', 'short')
    expect(store.getState().isComplete).toBe(false)
  }})
}})
"""
        _assert_passed(_run_driver(body), "isComplete all-steps-valid")

    def test_reset_restores_initial_state(self):
        """L2: reset() returns to step 0, clears all values and all errors."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createWizardStore }} from '{_IMPORT}'

describe('bench-reset', () => {{
  it('reset clears values, errors, and returns to step 0', () => {{
    const store = createWizardStore()
    store.getState().setField('email', 'user@example.com')
    store.getState().next()
    store.getState().setField('password', 'badpw')   // invalid -> records an error
    store.getState().next()                          // blocked, stays at step 1
    let s = store.getState()
    expect(s.stepIndex).toBe(1)
    expect(!!s.errors.password).toBe(true)
    store.getState().reset()
    s = store.getState()
    expect(s.stepIndex).toBe(0)
    expect(s.values.email).toBe('')
    expect(s.values.password).toBe('')
    expect(s.values.displayName).toBe('')
    const errVals = Object.values(s.errors as Record<string, string>)
    expect(errVals.filter((e) => !!e).length).toBe(0)
    expect(s.isComplete).toBe(false)
    expect(s.currentStepValid).toBe(false)
  }})
}})
"""
        _assert_passed(_run_driver(body), "reset restores initial state")

    def test_derived_consistency_across_mixed_sequence(self):
        """L2: derived fields never drift from an independent recompute."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createWizardStore }} from '{_IMPORT}'

{_RECOMPUTE_HELPER}

describe('bench-no-drift', () => {{
  it('currentStepValid/isComplete/errors match an independent recompute', () => {{
    const store = createWizardStore()
    const ops: Array<() => void> = [
      () => store.getState().setField('email', 'bad'),
      () => store.getState().next(),
      () => store.getState().setField('email', 'user@example.com'),
      () => store.getState().next(),
      () => store.getState().setField('password', 'short'),
      () => store.getState().next(),
      () => store.getState().setField('password', 'longenough1'),
      () => store.getState().next(),
      () => store.getState().setField('displayName', '   '),
      () => store.getState().prev(),
      () => store.getState().setField('displayName', 'Ada Lovelace'),
      () => store.getState().reset(),
      () => store.getState().setField('email', 'x@y.zz'),
    ]
    for (const op of ops) {{
      op()
      const s = store.getState()
      // derived fields must equal an independent recompute from values/stepIndex
      expect(s.currentStepValid).toBe(stepValid(s.values, s.stepIndex))
      expect(s.isComplete).toBe(allComplete(s.values))
      // every recorded (truthy) error must correspond to an actually-invalid field
      for (const field of ['email', 'password', 'displayName']) {{
        const v = (s.values as any)[field] ?? ''
        if (fieldValid(field, v)) {{
          expect(!!(s.errors as any)[field]).toBe(false)
        }}
      }}
      // stepIndex stays in range at all times
      expect(s.stepIndex).toBeGreaterThanOrEqual(0)
      expect(s.stepIndex).toBeLessThan(s.stepCount)
    }}
  }})
}})
"""
        _assert_passed(_run_driver(body), "derived consistency mixed sequence")
