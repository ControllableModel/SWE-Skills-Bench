"""Tests for the `hono-patterns` skill task (variant ext7): a bindings-driven config module.

Verifies the deliverable `src/helper/config-endpoint/index.ts` (and its colocated
`index.test.ts`) inside the Hono repo at /workspace/hono.

The task asks for a single mountable sub-application VALUE named `configApp` (NOT a
factory) whose behavior is fully determined by per-request environment bindings
supplied at dispatch time (the third argument of `app.request(path, init, env)` which
carries `Bindings`). On every request a request-scoped step must parse the
`FEATURE_FLAGS` binding once into a trimmed, non-empty flag array and expose it to
handlers as a request-scoped variable named `flags`; handlers read that shared
variable rather than re-parsing the binding. The contract must hold both when the app
is used directly and when it is mounted under a non-empty prefix.

Strategy
--------
- L1: the required deliverable files exist and are minimally well-formed (export the
  `configApp` value, register the `/info` and `/flags/:name` routes, ship a colocated
  vitest test file, and NOT smell like a factory function).
- L2: DYNAMIC EXECUTION. We write an *independent* vitest spec into the repo that
  imports the agent's `configApp` and exercises every requirement: parsing/trimming/
  empty-dropping, the `/info` JSON shape, exact (non-substring) flag membership, the
  empty-FEATURE_FLAGS -> [] rule, the missing/empty SERVICE_NAME -> 500 rule, the
  no-binding-leakage isolation guarantee across two dispatches, and identical behavior
  when mounted under a non-empty prefix. It dispatches IN-MEMORY requests via
  `app.request(path, undefined, bindings)` and asserts on the real JSON / status
  codes. A naive implementation (caching bindings in module state, re-parsing flags
  per handler with different semantics, substring flag matching, or skipping the
  SERVICE_NAME requirement) fails these named cases.

  To keep runtime bounded we run that independent spec ONCE with vitest's JSON
  reporter, cache the per-test results module-wide, and have each L2 Python test
  assert on one specific named case (and that the case actually executed — a missing
  case is treated as a failure, so a solution can't pass by making cases disappear).

- The agent's OWN colocated suite is checked separately: it must contain >=10 cases
  and pass, per the acceptance criteria.

Native test command (per task acceptance criteria):
    npx vitest --run src/helper/config-endpoint/index.test.ts
"""

import json
import os
import re
import subprocess
import textwrap

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - fallback if helper not co-located
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/hono"
MODULE_DIR = os.path.join(REPO_DIR, "src", "helper", "config-endpoint")
MODULE_TS = os.path.join(MODULE_DIR, "index.ts")
MODULE_TEST_TS = os.path.join(MODULE_DIR, "index.test.ts")

# Independent verification spec (unique name; never clobbers agent files).
VERIFY_SPEC = os.path.join(MODULE_DIR, "__bench_verify.test.ts")
VERIFY_SPEC_REL = "src/helper/config-endpoint/__bench_verify.test.ts"

NPX = "npx"


@pytest.fixture(scope="module", autouse=True)
def _install_deps():
    """Install repo node deps once before running native vitest."""
    if ensure_npm_dependencies is not None:
        ensure_npm_dependencies(REPO_DIR)
    yield


def _run_vitest(rel_spec, timeout, json_out=None):
    """Run vitest --run on a single spec relative to REPO_DIR.

    Coverage is disabled and the run is scoped to the `main` project to keep
    startup cheap (the repo's default vitest config enables v8 coverage and loads
    several runtime-test projects, which is needlessly slow for one spec).
    """
    cmd = [NPX, "vitest", "--run", "--project", "main", "--coverage.enabled=false"]
    if json_out:
        cmd += ["--reporter=json", f"--outputFile={json_out}"]
    cmd.append(rel_spec)
    result = subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "CI": "true"},
    )
    if result.returncode != 0 and "No test files found" in (result.stdout + result.stderr):
        # Some vitest CLIs reject --project on non-workspace runs; retry plainly.
        cmd = [NPX, "vitest", "--run", "--coverage.enabled=false"]
        if json_out:
            cmd += ["--reporter=json", f"--outputFile={json_out}"]
        cmd.append(rel_spec)
        result = subprocess.run(
            cmd,
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "CI": "true"},
        )
    return result


# ---------------------------------------------------------------------------
# The single comprehensive independent verification spec. Each `it(<name>, ...)`
# maps to one task requirement; the Python L2 tests below assert on these names.
#
# Bindings are supplied PER REQUEST through the third argument of app.request(),
# which Hono surfaces as `c.env`. We never rely on module-level state.
# ---------------------------------------------------------------------------
_VERIFY_SPEC_SRC = textwrap.dedent(
    """
    import { describe, it, expect } from 'vitest'
    import { Hono } from '../../hono'
    import { configApp } from '.'

    const base = 'http://localhost'

    // Use configApp directly (it is itself a Hono sub-application value).
    const direct = (path, bindings) => configApp.request(base + path, undefined, bindings)

    // Mount the SAME value under a non-empty prefix in a fresh parent each call,
    // and dispatch through the parent so env propagates down to the sub-app.
    const mounted = (path, bindings, prefix = '/cfg') => {
      const app = new Hono()
      app.route(prefix, configApp)
      return app.request(base + prefix + path, undefined, bindings)
    }

    const SVC = { SERVICE_NAME: 'svc', FEATURE_FLAGS: 'a, b ,,c,' }

    describe('config-endpoint verification', () => {
      it('info_returns_service_and_parsed_flags', async () => {
        const res = await direct('/info', SVC)
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body.service).toBe('svc')
        expect(Array.isArray(body.flags)).toBe(true)
        // trimmed, empties dropped, order preserved
        expect(body.flags).toEqual(['a', 'b', 'c'])
      })

      it('info_works_identically_when_mounted_under_prefix', async () => {
        const res = await mounted('/info', SVC)
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body.service).toBe('svc')
        expect(body.flags).toEqual(['a', 'b', 'c'])
      })

      it('empty_feature_flags_yields_empty_array', async () => {
        const empty = await direct('/info', { SERVICE_NAME: 'svc', FEATURE_FLAGS: '' })
        expect(empty.status).toBe(200)
        expect((await empty.json()).flags).toEqual([])
        // separators / whitespace only must also collapse to []
        const seps = await direct('/info', { SERVICE_NAME: 'svc', FEATURE_FLAGS: '  , , ,' })
        expect(seps.status).toBe(200)
        expect((await seps.json()).flags).toEqual([])
      })

      it('flags_missing_feature_flags_binding_is_empty', async () => {
        // FEATURE_FLAGS entirely absent -> flags is an empty array, not an error.
        const res = await direct('/info', { SERVICE_NAME: 'svc' })
        expect(res.status).toBe(200)
        expect((await res.json()).flags).toEqual([])
      })

      it('flag_check_true_for_member', async () => {
        const res = await direct('/flags/b', SVC)
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body.name).toBe('b')
        expect(body.enabled).toBe(true)
      })

      it('flag_check_false_for_non_member', async () => {
        const res = await direct('/flags/x', SVC)
        expect(res.status).toBe(200)
        const body = await res.json()
        expect(body.name).toBe('x')
        expect(body.enabled).toBe(false)
      })

      it('flag_membership_is_exact_not_substring', async () => {
        const bindings = { SERVICE_NAME: 'svc', FEATURE_FLAGS: 'alpha,beta' }
        // 'alph' is a substring of 'alpha' but is NOT a member.
        const sub = await direct('/flags/alph', bindings)
        expect((await sub.json()).enabled).toBe(false)
        // 'alphabeta' contains members as substrings but is not itself a member.
        const sup = await direct('/flags/alphabeta', bindings)
        expect((await sup.json()).enabled).toBe(false)
        // exact member still true
        const exact = await direct('/flags/alpha', bindings)
        expect((await exact.json()).enabled).toBe(true)
      })

      it('flag_check_uses_trimmed_parsed_values', async () => {
        // Spaces around the entry must be trimmed before membership is tested.
        const bindings = { SERVICE_NAME: 'svc', FEATURE_FLAGS: ' spaced ,other' }
        const hit = await direct('/flags/spaced', bindings)
        expect((await hit.json()).enabled).toBe(true)
        // The untrimmed form (with surrounding spaces) is NOT a member.
        const miss = await direct('/flags/' + encodeURIComponent(' spaced '), bindings)
        expect((await miss.json()).enabled).toBe(false)
      })

      it('missing_service_name_yields_500', async () => {
        const res = await direct('/info', { FEATURE_FLAGS: 'a,b' })
        expect(res.status).toBe(500)
        const body = await res.json()
        expect(typeof body.error).toBe('string')
        expect(body.error.length).toBeGreaterThan(0)
        // The 500 rule applies to every route, not just /info.
        const onFlags = await direct('/flags/a', { FEATURE_FLAGS: 'a,b' })
        expect(onFlags.status).toBe(500)
        expect(typeof (await onFlags.json()).error).toBe('string')
      })

      it('empty_service_name_yields_500', async () => {
        const res = await direct('/info', { SERVICE_NAME: '', FEATURE_FLAGS: 'a' })
        expect(res.status).toBe(500)
        expect(typeof (await res.json()).error).toBe('string')
      })

      it('no_binding_leakage_between_dispatches', async () => {
        // Two dispatches of the SAME value with different SERVICE_NAME values must
        // each reflect only their own bindings (no caching in module state).
        const r1 = await direct('/info', { SERVICE_NAME: 'one', FEATURE_FLAGS: 'p' })
        const r2 = await direct('/info', { SERVICE_NAME: 'two', FEATURE_FLAGS: 'q' })
        const b1 = await r1.json()
        const b2 = await r2.json()
        expect(b1.service).toBe('one')
        expect(b1.flags).toEqual(['p'])
        expect(b2.service).toBe('two')
        expect(b2.flags).toEqual(['q'])
        // Re-dispatch the first set AGAIN — still 'one', proving no mutation/caching.
        const r3 = await direct('/info', { SERVICE_NAME: 'one', FEATURE_FLAGS: 'p' })
        expect((await r3.json()).service).toBe('one')
      })

      it('handlers_share_parsed_flags_variable_consistently', async () => {
        // /info and /flags must agree on the parsed flag set for the same bindings,
        // demonstrating both read the single shared request-scoped `flags` value.
        const bindings = { SERVICE_NAME: 'svc', FEATURE_FLAGS: ' x , y ,, z ' }
        const info = await direct('/info', bindings)
        const flags = (await info.json()).flags
        expect(flags).toEqual(['x', 'y', 'z'])
        for (const f of flags) {
          const res = await direct('/flags/' + f, bindings)
          expect((await res.json()).enabled).toBe(true)
        }
        const nope = await direct('/flags/w', bindings)
        expect((await nope.json()).enabled).toBe(false)
      })
    })
    """
)


def _collect_assertion_results(json_path):
    """Parse vitest JSON output into {test_title: 'passed'|'failed'|...}."""
    with open(json_path) as f:
        report = json.load(f)
    results = {}
    for suite in report.get("testResults", []):
        for assertion in suite.get("assertionResults", []):
            results[assertion.get("title")] = assertion.get("status")
    return results


# Module-scoped cache so the independent spec runs exactly once.
_VERIFY_CACHE = {}


def _verify_results():
    if _VERIFY_CACHE:
        return _VERIFY_CACHE["results"]
    os.makedirs(MODULE_DIR, exist_ok=True)
    with open(VERIFY_SPEC, "w") as f:
        f.write(_VERIFY_SPEC_SRC)
    json_path = os.path.join(REPO_DIR, "__bench_verify_report.json")
    try:
        proc = _run_vitest(VERIFY_SPEC_REL, timeout=600, json_out=json_path)
        assert os.path.isfile(json_path), (
            "vitest produced no JSON report; the independent verification spec "
            "failed to run (likely a compile/import error in the module, or "
            "`configApp` was not exported as a mountable Hono value).\n"
            f"STDOUT:\n{proc.stdout[-4000:]}\nSTDERR:\n{proc.stderr[-3000:]}"
        )
        results = _collect_assertion_results(json_path)
    finally:
        for p in (VERIFY_SPEC, json_path):
            try:
                os.remove(p)
            except OSError:
                pass
    _VERIFY_CACHE["results"] = results
    _VERIFY_CACHE["proc"] = proc
    return results


def _assert_case(name):
    """Assert a named verification case ran and passed."""
    results = _verify_results()
    status = results.get(name)
    assert status is not None, (
        f"verification case {name!r} did not run; available cases: "
        f"{sorted(results.keys())}\nvitest stderr:\n"
        f"{_VERIFY_CACHE.get('proc').stderr[-2000:] if _VERIFY_CACHE.get('proc') else ''}"
    )
    assert status == "passed", f"verification case {name!r} status={status} (expected passed)"


class TestHonoPatterns:
    REPO_DIR = "/workspace/hono"

    # ------------------------------------------------------------- L1 ----

    def test_module_file_exists(self):
        """L1: the config-endpoint module file is present."""
        assert os.path.isfile(MODULE_TS), f"missing deliverable {MODULE_TS}"

    def test_module_exports_config_app_value(self):
        """L1: module source exports a `configApp` value (not a factory)."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert "configApp" in src, "configApp not found in module"
        # It must be exported. Accept `export const configApp`, `export { configApp }`,
        # or `export default` re-exporting configApp.
        exported = bool(
            re.search(r"export\s+(const|let|var)\s+configApp\b", src)
            or re.search(r"export\s*\{[^}]*\bconfigApp\b", src)
        )
        assert exported, "configApp is not exported as a value"
        # Discriminate against a factory: there must be no exported function that
        # is the configApp surface (the task explicitly wants a value, not a factory).
        assert not re.search(
            r"export\s+function\s+configApp\b", src
        ), "configApp must be a value, not a function/factory"
        assert not re.search(
            r"export\s+(const|let|var)\s+configApp\s*=\s*\([^)]*\)\s*=>", src
        ), "configApp must be a mountable value, not an arrow factory"

    def test_module_registers_required_routes(self):
        """L1: module registers the `/info` and `/flags/:name` GET routes."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert ".get(" in src, "module registers no GET route"
        assert "/info" in src, "module does not reference the /info route"
        assert re.search(r"/flags/:\w+", src), "module does not declare a /flags/:name route"

    def test_module_reads_bindings_not_module_state(self):
        """L1: handlers read per-request env bindings (c.env), grounding the bindings-driven design."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert "SERVICE_NAME" in src, "module never references the SERVICE_NAME binding"
        assert "FEATURE_FLAGS" in src, "module never references the FEATURE_FLAGS binding"
        assert "c.env" in src or ".env" in src, "module does not read per-request env bindings"

    def test_colocated_test_file_exists(self):
        """L1: the colocated deterministic test file exists."""
        assert os.path.isfile(MODULE_TEST_TS), f"missing {MODULE_TEST_TS}"

    def test_agent_suite_has_min_cases_and_passes(self):
        """L2/acceptance: agent's colocated suite has >=10 cases and passes via vitest."""
        with open(MODULE_TEST_TS) as f:
            test_src = f.read()
        case_count = test_src.count("it(") + test_src.count("test(")
        assert case_count >= 10, (
            f"colocated suite has only {case_count} cases; task requires >=10"
        )
        result = _run_vitest("src/helper/config-endpoint/index.test.ts", timeout=600)
        assert result.returncode == 0, (
            "agent's colocated vitest suite failed:\n"
            f"STDOUT:\n{result.stdout[-4000:]}\nSTDERR:\n{result.stderr[-3000:]}"
        )

    # ------------------------------------------------------------- L2 ----
    # Each maps to one task requirement, verified by the independent spec.

    def test_info_returns_service_and_parsed_flags(self):
        """L2: GET /info -> 200 {service, flags} with trimmed, empties-dropped flag array."""
        _assert_case("info_returns_service_and_parsed_flags")

    def test_info_works_identically_when_mounted_under_prefix(self):
        """L2: the SAME configApp value mounted under a non-empty prefix behaves identically."""
        _assert_case("info_works_identically_when_mounted_under_prefix")

    def test_empty_feature_flags_yields_empty_array(self):
        """L2: empty or separator-only FEATURE_FLAGS -> flags is []."""
        _assert_case("empty_feature_flags_yields_empty_array")

    def test_flags_missing_feature_flags_binding_is_empty(self):
        """L2: FEATURE_FLAGS absent -> flags is [] (not an error)."""
        _assert_case("flags_missing_feature_flags_binding_is_empty")

    def test_flag_check_true_for_member(self):
        """L2: GET /flags/:name -> enabled true for an exact member."""
        _assert_case("flag_check_true_for_member")

    def test_flag_check_false_for_non_member(self):
        """L2: GET /flags/:name -> enabled false for a non-member."""
        _assert_case("flag_check_false_for_non_member")

    def test_flag_membership_is_exact_not_substring(self):
        """L2: flag membership is exact — substrings/superstrings are not members."""
        _assert_case("flag_membership_is_exact_not_substring")

    def test_flag_check_uses_trimmed_parsed_values(self):
        """L2: membership tests the trimmed parsed flag values, not raw split tokens."""
        _assert_case("flag_check_uses_trimmed_parsed_values")

    def test_missing_service_name_yields_500(self):
        """L2: absent SERVICE_NAME on any route -> 500 {error}."""
        _assert_case("missing_service_name_yields_500")

    def test_empty_service_name_yields_500(self):
        """L2: empty-string SERVICE_NAME -> 500 {error}."""
        _assert_case("empty_service_name_yields_500")

    def test_no_binding_leakage_between_dispatches(self):
        """L2: distinct dispatches of the same value never leak bindings (no module-state caching)."""
        _assert_case("no_binding_leakage_between_dispatches")

    def test_handlers_share_parsed_flags_variable_consistently(self):
        """L2: /info and /flags agree on the parsed flags, evidencing a shared request-scoped variable."""
        _assert_case("handlers_share_parsed_flags_variable_consistently")
