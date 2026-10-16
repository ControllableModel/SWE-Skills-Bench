"""Tests for the `react-hook-form-patterns` skill -- variant ext6.

Skill task (ext6): build a render-isolated "tag editor" field-array form on top
of the react-hook-form library's own public API, plus a deterministic Jest
suite. A dynamic list of tag rows -- each `{ label, color }` (color in
red/green/blue) -- can be Added, Removed, Reordered (via Duplicate), and is
validated PER ROW. The hard, gameable behaviors are:

  * "Remove" deletes exactly that row, leaving the others' edited values and
    order intact.
  * "Duplicate" inserts a copy directly beneath the source row whose label and
    color equal the source's CURRENT edited values, and the two rows are then
    INDEPENDENT (editing one must not smear the other).
  * Per-row required-label validation (empty/whitespace -> error next to that
    row's label input; submit blocked).
  * Duplicate-label detection across rows (trimmed, case-insensitive) -> every
    conflicting row shows a "duplicate" error; fixing one clears the resolved
    rows.
  * "Save" calls onSubmit({ tags }) only when ALL rows are valid.

A naive implementation that keys rows by array index, or that shares state
between a row and its duplicate, must fail the Remove and/or Duplicate cases.

Deliverables verified (REPO_DIR = /workspace/react-hook-form):
  - src/__tests__/examples/tagEditorForm.tsx       (the feature component)
  - src/__tests__/examples/tagEditorForm.test.tsx  (the agent's own Jest suite)

Verification strategy:
  * L1  -- the two deliverable TSX files exist and are minimally well-formed
           (real JSX/component, imports from the library source, uses a
           field-array primitive, not a stub).
  * L2  -- runs the agent's own native suite via the exact required command
           (`TEST_ENV=web pnpm test -- ... tagEditorForm.test.tsx`, i.e. the
           web Jest project) and asserts the mandated >=6 cases pass.
  * L2  -- INDEPENDENT DRIVER: writes our OWN Jest spec next to the component,
           imports the agent's tag-editor component, and exercises the
           gameable behaviors directly through rendered DOM, parsing the
           per-test JSON results so each assertion is judged individually.

All identifiers we query ("Add tag", "Remove", "Duplicate", "Save", the row
label inputs, color selects, and per-row error text) are mandated by the
requirement document, so a conforming component must expose them.
"""

import json
import os
import shutil
import subprocess

import pytest

REPO_DIR = "/workspace/react-hook-form"
EXAMPLES_DIR = os.path.join(REPO_DIR, "src", "__tests__", "examples")
COMPONENT_FILE = os.path.join(EXAMPLES_DIR, "tagEditorForm.tsx")
AGENT_TEST_FILE = os.path.join(EXAMPLES_DIR, "tagEditorForm.test.tsx")

# Spec we inject ourselves; cleaned up after the run.
DRIVER_BASENAME = "tagEditorFormDriver.zz.test.tsx"
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
  within,
} from '@testing-library/react';

import * as Mod from './tagEditorForm';

// Resolve the exported tag-editor component regardless of its name.
function resolveComponent(): React.ComponentType<any> {
  const m: any = Mod as any;
  if (typeof m.default === 'function') return m.default;
  const named = [
    'TagEditorForm',
    'TagEditor',
    'TagsForm',
    'TagForm',
    'Form',
  ];
  for (const n of named) {
    if (typeof m[n] === 'function') return m[n];
  }
  for (const k of Object.keys(m)) {
    if (typeof m[k] === 'function') return m[k];
  }
  throw new Error('could not resolve tag editor component from module');
}

const TagEditorForm = resolveComponent();

// ---- helpers that lean only on requirement-mandated, stable affordances ----

function getAddButton(): HTMLElement {
  return screen.getByRole('button', { name: /add tag/i });
}

function getSaveButton(): HTMLElement {
  return screen.getByRole('button', { name: /save/i });
}

// A "row" must contain its own Remove control. Walk up to the nearest
// ancestor of the Remove button that also holds a label input + a color select.
function getRows(): HTMLElement[] {
  const removeButtons = screen.queryAllByRole('button', { name: /^remove$/i });
  const rows: HTMLElement[] = [];
  for (const btn of removeButtons) {
    let el: HTMLElement | null = btn;
    while (el && el.parentElement) {
      el = el.parentElement;
      const inputs = el.querySelectorAll('input');
      const selects = el.querySelectorAll('select');
      if (inputs.length >= 1 && selects.length >= 1) {
        rows.push(el);
        break;
      }
    }
  }
  return rows;
}

function labelInput(row: HTMLElement): HTMLInputElement {
  const inputs = Array.from(
    row.querySelectorAll('input'),
  ) as HTMLInputElement[];
  // Prefer a text input hinted as the label; else the first non-checkbox input.
  const hinted = inputs.find((i) => {
    const hay = [
      i.getAttribute('name') || '',
      i.getAttribute('aria-label') || '',
      i.getAttribute('placeholder') || '',
      i.getAttribute('data-testid') || '',
    ]
      .join(' ')
      .toLowerCase();
    return /label/.test(hay);
  });
  const textInputs = inputs.filter(
    (i) => (i.getAttribute('type') || 'text') === 'text',
  );
  const chosen = hinted || textInputs[0] || inputs[0];
  if (!chosen) throw new Error('row has no label input');
  return chosen;
}

function colorSelect(row: HTMLElement): HTMLSelectElement {
  const sel = row.querySelector('select') as HTMLSelectElement | null;
  if (!sel) throw new Error('row has no color select');
  return sel;
}

function rowWithin(row: HTMLElement) {
  return within(row);
}

function setVal(el: HTMLInputElement | HTMLSelectElement, value: string) {
  fireEvent.change(el, { target: { value } });
}

function addRows(n: number) {
  for (let i = 0; i < n; i++) fireEvent.click(getAddButton());
}

// Per-row error text adjacent to the label input. We look inside the row for
// any node whose text looks like a validation message.
function rowHasAnyError(row: HTMLElement): boolean {
  const txt = (row.textContent || '').toLowerCase();
  return /(required|empty|duplicate|invalid|must|already)/.test(txt);
}

function rowHasDuplicateError(row: HTMLElement): boolean {
  const txt = (row.textContent || '').toLowerCase();
  return /duplicate|already|same/.test(txt);
}

describe('tagEditorForm driver (independent)', () => {
  test('empty render: no rows, add tag control present', () => {
    render(<TagEditorForm onSubmit={jest.fn()} />);
    expect(getAddButton()).toBeInTheDocument();
    expect(getRows().length).toBe(0);
  });

  test('add tag appends one editable row with default color', () => {
    render(<TagEditorForm onSubmit={jest.fn()} />);
    fireEvent.click(getAddButton());
    const rows = getRows();
    expect(rows.length).toBe(1);
    const li = labelInput(rows[0]);
    expect(li.value).toBe('');
    // default color is one of the allowed values (per doc, e.g. red)
    const cs = colorSelect(rows[0]);
    expect(['red', 'green', 'blue']).toContain(cs.value);
    // editable: a keystroke sticks
    setVal(li, 'hello');
    expect(labelInput(getRows()[0]).value).toBe('hello');
  });

  test('remove deletes exactly that row, others keep values and order', () => {
    render(<TagEditorForm onSubmit={jest.fn()} />);
    addRows(3);
    let rows = getRows();
    expect(rows.length).toBe(3);
    const labels = ['alpha', 'beta', 'gamma'];
    rows.forEach((row, i) => {
      setVal(labelInput(row), labels[i]);
      setVal(colorSelect(row), ['red', 'green', 'blue'][i]);
    });
    // remove the middle row
    const mid = rowWithin(rows[1]).getByRole('button', { name: /^remove$/i });
    fireEvent.click(mid);
    rows = getRows();
    expect(rows.length).toBe(2);
    expect(labelInput(rows[0]).value).toBe('alpha');
    expect(labelInput(rows[1]).value).toBe('gamma');
    expect(colorSelect(rows[0]).value).toBe('red');
    expect(colorSelect(rows[1]).value).toBe('blue');
  });

  test('duplicate inserts a copy directly beneath, then rows are independent', () => {
    render(<TagEditorForm onSubmit={jest.fn()} />);
    addRows(2);
    let rows = getRows();
    setVal(labelInput(rows[0]), 'source');
    setVal(colorSelect(rows[0]), 'green');
    setVal(labelInput(rows[1]), 'tail');
    setVal(colorSelect(rows[1]), 'blue');

    // duplicate the FIRST row
    const dup = rowWithin(rows[0]).getByRole('button', { name: /duplicate/i });
    fireEvent.click(dup);

    rows = getRows();
    expect(rows.length).toBe(3);
    // copy sits directly beneath the source (index 1) with the same values
    expect(labelInput(rows[1]).value).toBe('source');
    expect(colorSelect(rows[1]).value).toBe('green');
    // the unrelated tail row is preserved at the end
    expect(labelInput(rows[2]).value).toBe('tail');
    expect(colorSelect(rows[2]).value).toBe('blue');

    // independence: edit the duplicate, the original must not change
    setVal(labelInput(rows[1]), 'changed');
    setVal(colorSelect(rows[1]), 'red');
    rows = getRows();
    expect(labelInput(rows[0]).value).toBe('source');
    expect(colorSelect(rows[0]).value).toBe('green');
    expect(labelInput(rows[1]).value).toBe('changed');
    expect(colorSelect(rows[1]).value).toBe('red');

    // and the reverse: editing the original must not change the duplicate
    setVal(labelInput(rows[0]), 'origEdited');
    rows = getRows();
    expect(labelInput(rows[0]).value).toBe('origEdited');
    expect(labelInput(rows[1]).value).toBe('changed');
  });

  test('required label: empty/whitespace shows error on that row, blocks submit', async () => {
    const onSubmit = jest.fn();
    render(<TagEditorForm onSubmit={onSubmit} />);
    addRows(2);
    let rows = getRows();
    setVal(labelInput(rows[0]), 'good');
    setVal(colorSelect(rows[0]), 'red');
    // second row left with a whitespace-only label
    setVal(labelInput(rows[1]), '   ');
    setVal(colorSelect(rows[1]), 'blue');

    fireEvent.click(getSaveButton());

    // submit blocked
    await Promise.resolve();
    expect(onSubmit).not.toHaveBeenCalled();
    rows = getRows();
    // error is adjacent to the offending row specifically
    expect(rowHasAnyError(rows[1])).toBe(true);
  });

  test('duplicate-label detection across rows, then clears when fixed', async () => {
    const onSubmit = jest.fn();
    render(<TagEditorForm onSubmit={onSubmit} />);
    addRows(3);
    let rows = getRows();
    // rows 0 and 2 collide (trimmed, case-insensitive); row 1 is distinct
    setVal(labelInput(rows[0]), 'Apple');
    setVal(colorSelect(rows[0]), 'red');
    setVal(labelInput(rows[1]), 'banana');
    setVal(colorSelect(rows[1]), 'green');
    setVal(labelInput(rows[2]), '  apple ');
    setVal(colorSelect(rows[2]), 'blue');

    fireEvent.click(getSaveButton());
    await Promise.resolve();

    expect(onSubmit).not.toHaveBeenCalled();
    rows = getRows();
    // both colliding rows flag a duplicate; the distinct one does not
    expect(rowHasDuplicateError(rows[0])).toBe(true);
    expect(rowHasDuplicateError(rows[2])).toBe(true);
    expect(rowHasDuplicateError(rows[1])).toBe(false);

    // fix one of the conflicting labels -> the resolved rows clear
    setVal(labelInput(getRows()[2]), 'cherry');
    fireEvent.click(getSaveButton());
    await Promise.resolve();
    rows = getRows();
    expect(rowHasDuplicateError(rows[0])).toBe(false);
    expect(rowHasDuplicateError(rows[2])).toBe(false);
  });

  test('save gating: onSubmit called with { tags } only when all rows valid', async () => {
    const onSubmit = jest.fn();
    render(<TagEditorForm onSubmit={onSubmit} />);
    addRows(2);
    const rows = getRows();
    setVal(labelInput(rows[0]), 'one');
    setVal(colorSelect(rows[0]), 'red');
    setVal(labelInput(rows[1]), 'two');
    setVal(colorSelect(rows[1]), 'green');

    fireEvent.click(getSaveButton());
    // react-hook-form's handleSubmit validates asynchronously
    await new Promise((r) => setTimeout(r, 0));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const payload = onSubmit.mock.calls[0][0];
    expect(payload).toBeTruthy();
    expect(Array.isArray(payload.tags)).toBe(true);
    expect(payload.tags.length).toBe(2);
    expect(String(payload.tags[0].label)).toBe('one');
    expect(String(payload.tags[0].color)).toBe('red');
    expect(String(payload.tags[1].label)).toBe('two');
    expect(String(payload.tags[1].color)).toBe('green');
  });
});
"""


# --------------------------------------------------------------------------- #
# L1: deliverable files exist and are minimally well-formed
# --------------------------------------------------------------------------- #
class TestReactHookFormPatterns:
    REPO_DIR = "/workspace/react-hook-form"

    def test_component_file_exists(self):
        """L1: the tag-editor form component file is created at the required path."""
        assert os.path.isfile(COMPONENT_FILE), f"missing {COMPONENT_FILE}"

    def test_agent_test_file_exists(self):
        """L1: the agent's deterministic Jest suite file is created."""
        assert os.path.isfile(AGENT_TEST_FILE), f"missing {AGENT_TEST_FILE}"

    def test_component_is_real_tsx(self):
        """L1: component is real TSX -- JSX, imports library source, uses a
        field-array primitive, and is not a trivial stub."""
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        assert len(src) > 300, "component file is suspiciously small"
        # imports from the library's own source (relative ../../ entry points)
        assert "import" in src and ".." in src, (
            "component must import from library source"
        )
        # must use the dynamic-list primitive to manage rows
        assert "useFieldArray" in src, (
            "component must manage rows with useFieldArray (the field-array primitive)"
        )
        # must use the form hook as well
        assert "useForm" in src, "component must use useForm"
        # actually renders JSX
        assert "return" in src and ("<" in src and ("/>" in src or "</" in src)), (
            "component must render JSX"
        )
        # exposes the mandated affordances
        low = src.lower()
        for token in ("add tag", "remove", "duplicate", "save"):
            assert token in low, f"component must expose a '{token}' control"

    def test_component_does_not_use_index_keyed_state(self):
        """L1: rows are managed by the field array's stable keys, not by an
        index-keyed local useState array (a naive index-key impl is rejected by
        the doc and would fail Remove/Duplicate). We flag the smell of mapping
        with the array index as the React key."""
        with open(COMPONENT_FILE, encoding="utf-8") as fh:
            src = fh.read()
        # field-array map should key on field.id, not the loop index.
        # Heuristic: presence of `key={index}` / `key={i}` is the classic bug.
        bad = ("key={index}", "key={i}", "key={idx}", "key={ index }")
        assert not any(b in src.replace(" ", "") for b in
                       ("key={index}", "key={i}", "key={idx}")), (
            "rows must be keyed by the field array id, not the array index"
        )
        # positive signal: a `.id` is used as the key somewhere
        assert ".id" in src, (
            "field-array rows should use the stable `field.id` as React key"
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
        """L2: the agent's tagEditorForm.test.tsx passes under the required
        web Jest command and reports >=6 passing cases."""
        rel = os.path.join("src", "__tests__", "examples", "tagEditorForm.test.tsx")
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
    # L2: independent driver suite -- the discriminative core.
    # We write our own spec, run it with --json, and assert each targeted
    # behavior individually.
    # ----------------------------------------------------------------------- #
    def _ensure_driver(self):
        assert os.path.isdir(EXAMPLES_DIR), f"examples dir missing: {EXAMPLES_DIR}"
        with open(DRIVER_FILE, "w", encoding="utf-8") as fh:
            fh.write(DRIVER_SPEC)

    def _run_driver_once(self):
        """Run the independent driver once, cache parsed per-test results."""
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

    def test_driver_empty_render(self):
        """L2(driver): fresh form shows zero rows and an 'Add tag' control."""
        self._assert_driver_case("empty render")

    def test_driver_add_default_color(self):
        """L2(driver): 'Add tag' appends one editable row with a default color."""
        self._assert_driver_case("add tag appends one editable row")

    def test_driver_remove_preserves_others(self):
        """L2(driver): removing the middle row preserves the others' label/color
        values and order (index-keyed impls smear here)."""
        self._assert_driver_case("remove deletes exactly that row")

    def test_driver_duplicate_independence(self):
        """L2(driver): Duplicate inserts a copy directly beneath the source with
        its current values, and the two rows are then independent."""
        self._assert_driver_case("duplicate inserts a copy directly beneath")

    def test_driver_required_label(self):
        """L2(driver): an empty/whitespace label shows an error on that row and
        blocks submission."""
        self._assert_driver_case("required label")

    def test_driver_duplicate_label_detection(self):
        """L2(driver): trimmed/case-insensitive duplicate labels both flag a
        duplicate error; fixing one clears the resolved rows."""
        self._assert_driver_case("duplicate-label detection across rows")

    def test_driver_save_gating(self):
        """L2(driver): onSubmit is called with the full { tags } payload only
        when every row is valid."""
        self._assert_driver_case("save gating")
