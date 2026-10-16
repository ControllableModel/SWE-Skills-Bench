"""
Test for 'tanstack-query-patterns' skill (variant ext6) — Placeholder-Data
Resolver for Pagination.

Verifies the agent added a pure `resolveDisplayData(input): { data, isPlaceholderData }`
utility plus its `ResolveDisplayInput` type to `@tanstack/query-core`
(packages/query-core/src/placeholder.ts), re-exported both from the package
entry point (src/index.ts), and that the resolution semantics match the
requirement doc EXACTLY:

  - defined `data` always wins -> { data, isPlaceholderData: false } regardless
    of placeholder (including falsy-but-defined data: 0, '', false, []).
  - undefined `data` + function placeholder -> placeholder(previousData), flagged
    placeholder UNLESS it resolves to undefined.
  - undefined `data` + value placeholder -> that value, flagged placeholder
    (UNLESS the value is undefined).
  - undefined `data` + no placeholder -> { data: undefined, isPlaceholderData: false }.
  - the placeholder function is invoked at most once and only when data is
    undefined; inputs are never mutated.

Strategy: rather than trusting the agent's own test file, this suite injects its
OWN vitest probe specs into packages/query-core/src/__tests__/ and runs them with
the repo's NATIVE vitest — the exact command family the Acceptance Criteria
specifies:

    pnpm --filter @tanstack/query-core exec vitest run src/__tests__/<probe>

Each probe imports `resolveDisplayData` from the package index (`..`) and asserts
concrete return values / call-count side effects, so a stub (e.g. always returns
{ data, isPlaceholderData: false }, ignores the placeholder, calls placeholder
unconditionally, or mislabels a resolved-undefined placeholder) MUST fail.
"""

import json
import os
import subprocess

import pytest


REPO_DIR = "/workspace/query"
CORE_DIR = os.path.join(REPO_DIR, "packages", "query-core")
SRC_DIR = os.path.join(CORE_DIR, "src")
TESTS_SUBDIR = os.path.join(SRC_DIR, "__tests__")

# Probe specs we inject live under src/__tests__ so the package's vitest
# config (test.dir === './src') picks them up. Distinct name to avoid clobber.
PROBE_BASENAME = "zzPlaceholderResolverProbe.gen.test.tsx"
PROBE_PATH = os.path.join(TESTS_SUBDIR, PROBE_BASENAME)

INSTALL_TIMEOUT = 1800
VITEST_TIMEOUT = 600


def _pnpm_env():
    env = dict(os.environ)
    env.setdefault("CI", "")
    env.setdefault("npm_config_yes", "true")
    return env


@pytest.fixture(scope="module", autouse=True)
def _ensure_repo_dependencies():
    """Install workspace deps once so native vitest can run."""
    assert os.path.isdir(REPO_DIR), f"repo not found: {REPO_DIR}"
    assert os.path.isdir(CORE_DIR), f"query-core package not found: {CORE_DIR}"
    node_modules = os.path.join(REPO_DIR, "node_modules")
    if not os.path.isdir(node_modules):
        result = subprocess.run(
            ["pnpm", "install", "--frozen-lockfile", "--prefer-offline"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT,
            env=_pnpm_env(),
        )
        if result.returncode != 0:
            result = subprocess.run(
                ["pnpm", "install", "--prefer-offline"],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=INSTALL_TIMEOUT,
                env=_pnpm_env(),
            )
        assert result.returncode == 0, (
            "pnpm install failed:\n"
            f"stdout={result.stdout[-3000:]}\nstderr={result.stderr[-3000:]}"
        )
    yield
    try:
        if os.path.isfile(PROBE_PATH):
            os.remove(PROBE_PATH)
    except OSError:
        pass


def _run_vitest_on_probe(probe_source):
    """Write `probe_source` into src/__tests__, run native vitest on just that
    file, and return (CompletedProcess, combined_output)."""
    os.makedirs(TESTS_SUBDIR, exist_ok=True)
    with open(PROBE_PATH, "w", encoding="utf-8") as fh:
        fh.write(probe_source)
    try:
        result = subprocess.run(
            [
                "pnpm",
                "--filter",
                "@tanstack/query-core",
                "exec",
                "vitest",
                "run",
                f"src/__tests__/{PROBE_BASENAME}",
            ],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=VITEST_TIMEOUT,
            env=_pnpm_env(),
        )
    finally:
        try:
            os.remove(PROBE_PATH)
        except OSError:
            pass
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    return result, combined


def _assert_vitest_passed(result, combined):
    assert result.returncode == 0, (
        "native vitest run did not pass:\n"
        f"stdout={result.stdout[-4000:]}\nstderr={result.stderr[-4000:]}"
    )
    lowered = combined.lower()
    assert "no test files found" not in lowered, (
        "vitest collected no tests:\n" + combined[-3000:]
    )


# A small TS preamble (re)used by probes: a typed helper that asserts a
# resolveDisplayData result deeply equals the expected { data, isPlaceholderData }.
_PROBE_HEADER = (
    "import { describe, expect, it, vi } from 'vitest'\n"
    "import { resolveDisplayData } from '..'\n"
)


class TestTanstackQueryPatterns:
    """Verify the resolveDisplayData placeholder-data resolver."""

    REPO_DIR = "/workspace/query"

    # ------------------------------------------------------------------
    # L1: deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_placeholder_source_file_exists(self):
        """packages/query-core/src/placeholder.ts must exist and define the
        resolver + its input type (not an empty stub)."""
        path = os.path.join(SRC_DIR, "placeholder.ts")
        assert os.path.isfile(path), "placeholder.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "resolveDisplayData" in content, (
            "resolveDisplayData not defined in placeholder.ts"
        )
        assert "ResolveDisplayInput" in content, (
            "ResolveDisplayInput type not present in placeholder.ts"
        )
        assert len(content.strip()) > 120, "placeholder.ts looks empty/stub"

    def test_index_reexports_resolver_and_type(self):
        """index.ts must re-export resolveDisplayData and the
        ResolveDisplayInput type."""
        path = os.path.join(SRC_DIR, "index.ts")
        assert os.path.isfile(path), "index.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "resolveDisplayData" in content, (
            "index.ts does not re-export resolveDisplayData"
        )
        assert "ResolveDisplayInput" in content, (
            "index.ts does not re-export ResolveDisplayInput"
        )

    def test_agent_test_suite_exists(self):
        """The required vitest suite file must exist."""
        path = os.path.join(TESTS_SUBDIR, "placeholder.test.tsx")
        assert os.path.isfile(path), "placeholder.test.tsx not found"

    # ------------------------------------------------------------------
    # L2: dynamic execution via the repo's native vitest toolchain.
    # Each method injects its own focused probe importing resolveDisplayData
    # from the package index, so the agent's own test file is not trusted.
    # ------------------------------------------------------------------

    def test_documented_expected_functionality_scenarios(self):
        """All six documented Expected-Functionality examples resolve to the
        exact { data, isPlaceholderData } the requirement specifies."""
        probe = (
            _PROBE_HEADER
            + "describe('resolveDisplayData documented', () => {\n"
            "  it('matches every documented example', () => {\n"
            "    expect(resolveDisplayData({ data: ['new'], previousData: ['old'] }))\n"
            "      .toEqual({ data: ['new'], isPlaceholderData: false })\n"
            "    expect(resolveDisplayData({ data: undefined, previousData: ['old'], placeholder: (p) => p }))\n"
            "      .toEqual({ data: ['old'], isPlaceholderData: true })\n"
            "    expect(resolveDisplayData({ data: undefined, previousData: undefined, placeholder: (p) => p }))\n"
            "      .toEqual({ data: undefined, isPlaceholderData: false })\n"
            "    expect(resolveDisplayData({ data: undefined, previousData: undefined, placeholder: ['seed'] }))\n"
            "      .toEqual({ data: ['seed'], isPlaceholderData: true })\n"
            "    expect(resolveDisplayData({ data: 0 as any, previousData: undefined }))\n"
            "      .toEqual({ data: 0, isPlaceholderData: false })\n"
            "    expect(resolveDisplayData({ data: undefined, previousData: undefined }))\n"
            "      .toEqual({ data: undefined, isPlaceholderData: false })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_defined_data_wins_over_placeholder(self):
        """When `data` is defined it MUST be returned with
        isPlaceholderData:false regardless of any placeholder (function OR
        value). A stub that prefers the placeholder fails here."""
        probe = (
            _PROBE_HEADER
            + "describe('resolveDisplayData data precedence', () => {\n"
            "  it('defined data always wins over placeholder', () => {\n"
            "    expect(resolveDisplayData({ data: ['real'], previousData: ['old'], placeholder: ['seed'] }))\n"
            "      .toEqual({ data: ['real'], isPlaceholderData: false })\n"
            "    expect(resolveDisplayData({ data: ['real'], previousData: ['old'], placeholder: () => ['seed'] }))\n"
            "      .toEqual({ data: ['real'], isPlaceholderData: false })\n"
            "    // even when placeholder would resolve to the same value, flag stays false\n"
            "    expect(resolveDisplayData({ data: ['x'], previousData: ['x'], placeholder: (p) => p }))\n"
            "      .toEqual({ data: ['x'], isPlaceholderData: false })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_falsy_but_defined_data_is_real(self):
        """Falsy-but-defined data (0, '', false, [], NaN, null) is still
        'defined' and MUST be returned as real data with
        isPlaceholderData:false — NOT treated as missing. A truthiness check
        (`if (data)`) instead of an undefined check fails here."""
        cases = [
            ("0", "0"),
            ("''", "''"),
            ("false", "false"),
            ("[]", "[]"),
            ("null", "null"),
        ]
        body = "\n".join(
            f"    expect(resolveDisplayData({{ data: {val} as any, previousData: ['old'], placeholder: ['seed'] }}))\n"
            f"      .toEqual({{ data: {expected}, isPlaceholderData: false }})"
            for val, expected in cases
        )
        probe = (
            _PROBE_HEADER
            + "describe('resolveDisplayData falsy-but-defined', () => {\n"
            "  it('falsy defined values are real data', () => {\n"
            f"{body}\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_function_placeholder_receives_previous_and_is_placeholder(self):
        """A function placeholder is called with previousData and its return
        value becomes the displayed (placeholder) data when data is
        undefined."""
        probe = (
            _PROBE_HEADER
            + "describe('resolveDisplayData function placeholder', () => {\n"
            "  it('keep-previous-data pattern', () => {\n"
            "    const res = resolveDisplayData({ data: undefined, previousData: ['p1'], placeholder: (p) => p })\n"
            "    expect(res).toEqual({ data: ['p1'], isPlaceholderData: true })\n"
            "    // arbitrary transform of previous\n"
            "    const res2 = resolveDisplayData({ data: undefined, previousData: 3 as any, placeholder: (p: any) => (p ?? 0) + 10 })\n"
            "    expect(res2).toEqual({ data: 13, isPlaceholderData: true })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_value_placeholder_is_placeholder(self):
        """A non-function placeholder value is returned verbatim and flagged as
        a placeholder when data is undefined."""
        probe = (
            _PROBE_HEADER
            + "describe('resolveDisplayData value placeholder', () => {\n"
            "  it('static value placeholder', () => {\n"
            "    expect(resolveDisplayData({ data: undefined, previousData: undefined, placeholder: ['seed'] }))\n"
            "      .toEqual({ data: ['seed'], isPlaceholderData: true })\n"
            "    // a falsy-but-defined static placeholder value is still a placeholder\n"
            "    expect(resolveDisplayData({ data: undefined, previousData: undefined, placeholder: 0 as any }))\n"
            "      .toEqual({ data: 0, isPlaceholderData: true })\n"
            "    expect(resolveDisplayData({ data: undefined, previousData: undefined, placeholder: '' as any }))\n"
            "      .toEqual({ data: '', isPlaceholderData: true })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_resolved_undefined_placeholder_is_not_a_placeholder(self):
        """If the placeholder (function or value) resolves to undefined there is
        nothing to show, so isPlaceholderData MUST be false. This is the key
        discriminator the doc calls out — a naive `isPlaceholderData = true`
        whenever a placeholder is provided MUST fail here."""
        probe = (
            _PROBE_HEADER
            + "describe('resolveDisplayData resolved-undefined', () => {\n"
            "  it('undefined placeholder result is not flagged', () => {\n"
            "    // function returns previousData which is undefined\n"
            "    expect(resolveDisplayData({ data: undefined, previousData: undefined, placeholder: (p) => p }))\n"
            "      .toEqual({ data: undefined, isPlaceholderData: false })\n"
            "    // function explicitly returns undefined despite a previous\n"
            "    expect(resolveDisplayData({ data: undefined, previousData: ['old'], placeholder: () => undefined }))\n"
            "      .toEqual({ data: undefined, isPlaceholderData: false })\n"
            "    // explicit undefined value placeholder\n"
            "    expect(resolveDisplayData({ data: undefined, previousData: ['old'], placeholder: undefined }))\n"
            "      .toEqual({ data: undefined, isPlaceholderData: false })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_no_placeholder_no_data(self):
        """undefined data + no placeholder -> { data: undefined,
        isPlaceholderData: false }, independent of previousData."""
        probe = (
            _PROBE_HEADER
            + "describe('resolveDisplayData no placeholder', () => {\n"
            "  it('nothing to show without placeholder', () => {\n"
            "    expect(resolveDisplayData({ data: undefined, previousData: undefined }))\n"
            "      .toEqual({ data: undefined, isPlaceholderData: false })\n"
            "    // previousData must NOT leak through without a placeholder\n"
            "    expect(resolveDisplayData({ data: undefined, previousData: ['old'] }))\n"
            "      .toEqual({ data: undefined, isPlaceholderData: false })\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_placeholder_invoked_at_most_once_and_only_when_needed(self):
        """The placeholder function is invoked AT MOST ONCE, and ONLY when data
        is undefined. A spy verifies call counts: 0 when data is defined,
        exactly 1 when data is undefined."""
        probe = (
            _PROBE_HEADER
            + "describe('resolveDisplayData call semantics', () => {\n"
            "  it('not called when data defined', () => {\n"
            "    const spy = vi.fn((p: any) => p)\n"
            "    resolveDisplayData({ data: ['real'], previousData: ['old'], placeholder: spy })\n"
            "    expect(spy).toHaveBeenCalledTimes(0)\n"
            "  })\n"
            "  it('called exactly once when data undefined', () => {\n"
            "    const spy = vi.fn((p: any) => p)\n"
            "    resolveDisplayData({ data: undefined, previousData: ['old'], placeholder: spy })\n"
            "    expect(spy).toHaveBeenCalledTimes(1)\n"
            "    expect(spy).toHaveBeenCalledWith(['old'])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_purity_no_mutation_of_inputs(self):
        """Calling resolveDisplayData MUST NOT mutate its inputs (data,
        previousData, or a value placeholder). Snapshot via JSON before/after."""
        probe = (
            _PROBE_HEADER
            + "describe('resolveDisplayData purity', () => {\n"
            "  it('does not mutate inputs', () => {\n"
            "    const previousData = [{ id: 1 }, { id: 2 }]\n"
            "    const placeholder = ['seed']\n"
            "    const sPrev = JSON.stringify(previousData)\n"
            "    const sPh = JSON.stringify(placeholder)\n"
            "    resolveDisplayData({ data: undefined, previousData, placeholder })\n"
            "    resolveDisplayData({ data: undefined, previousData, placeholder: (p) => p })\n"
            "    resolveDisplayData({ data: ['real'], previousData, placeholder })\n"
            "    expect(JSON.stringify(previousData)).toBe(sPrev)\n"
            "    expect(JSON.stringify(placeholder)).toBe(sPh)\n"
            "    expect(previousData.length).toBe(2)\n"
            "    expect(placeholder.length).toBe(1)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_result_shape_invariants(self):
        """Over a representative grid the result is ALWAYS an object with exactly
        keys {data, isPlaceholderData}, isPlaceholderData is a boolean, and
        isPlaceholderData is true ONLY when data is undefined-input yet the
        returned data is not undefined (i.e. it never lies about real data)."""
        probe = (
            _PROBE_HEADER
            + "const fnPrev = (p: any) => p\n"
            "const fnUndef = () => undefined\n"
            "const grid: Array<any> = [\n"
            "  { data: ['new'], previousData: ['old'] },\n"
            "  { data: 0 as any, previousData: undefined },\n"
            "  { data: undefined, previousData: ['old'], placeholder: fnPrev },\n"
            "  { data: undefined, previousData: undefined, placeholder: fnPrev },\n"
            "  { data: undefined, previousData: undefined, placeholder: ['seed'] },\n"
            "  { data: undefined, previousData: ['old'], placeholder: fnUndef },\n"
            "  { data: undefined, previousData: undefined },\n"
            "  { data: ['real'], previousData: ['old'], placeholder: ['seed'] },\n"
            "]\n"
            "describe('resolveDisplayData shape invariants', () => {\n"
            "  it('returns a well-formed result everywhere', () => {\n"
            "    for (const input of grid) {\n"
            "      const r = resolveDisplayData(input)\n"
            "      expect(Object.keys(r).sort()).toEqual(['data', 'isPlaceholderData'])\n"
            "      expect(typeof r.isPlaceholderData).toBe('boolean')\n"
            "      // a placeholder flag implies displayed data is actually present\n"
            "      if (r.isPlaceholderData) {\n"
            "        expect(r.data).not.toBe(undefined)\n"
            "        // and the underlying data input must have been undefined\n"
            "        expect(input.data).toBe(undefined)\n"
            "      }\n"
            "      // defined input data is echoed back verbatim and never a placeholder\n"
            "      if (input.data !== undefined) {\n"
            "        expect(r.data).toBe(input.data)\n"
            "        expect(r.isPlaceholderData).toBe(false)\n"
            "      }\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)
