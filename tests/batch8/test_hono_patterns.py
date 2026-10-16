"""Tests for the `hono-patterns` skill task (variant ext8): a centralized
error-surfacing module for a banking-style accounts resource.

Verifies the deliverable `src/helper/error-surface/index.ts` (and its colocated
`index.test.ts`) inside the Hono repo at /workspace/hono.

Task summary
------------
The agent must add `src/helper/error-surface/index.ts` exporting a factory
`createAccounts()` that returns a *mountable* sub-application holding its OWN
private in-memory map of accounts (id: string, balance: number starting at 0).
Two calls must be isolated. Every failure must flow through a single centralized
error path (`onError`) plus a dedicated not-found path (`notFound`) and emit the
UNIFORM envelope:

    { "error": { "code": <string>, "message": <string> } }

Routes / behavior:
  * POST /accounts {id}          -> 201 {id, balance:0}; dup id -> 409 "conflict";
                                    missing string id -> 400 "bad_request".
  * POST /accounts/:id/deposit   -> 200 updated; amount<=0 or non-number -> 400
                                    "bad_request"; unknown id -> 404 "not_found".
  * POST /accounts/:id/withdraw  -> 200 updated; over-balance -> 409
                                    "insufficient_funds" (balance UNCHANGED);
                                    unknown id -> 404 "not_found".
  * any unmatched path           -> 404 "not_found".
  * unexpected internal failure  -> 500 "internal" (still uniform envelope).
Failed operations must never mutate the account map / balances.

Verification strategy
----------------------
- L1: deliverable files exist and are minimally well-formed (export the factory,
  wire a centralized error path via `onError`, a not-found path via `notFound`,
  and register the POST routes; ship a colocated vitest suite).
- L2: DYNAMIC EXECUTION. We inject our OWN independent vitest spec into the repo
  that imports the agent's `createAccounts()` and dispatches IN-MEMORY requests
  via `app.request(...)` against BOTH a directly-mounted instance and an instance
  mounted under a non-empty prefix. It asserts concrete status codes, the exact
  `error.code` values, the uniform envelope shape, isolation between instances,
  and the critical no-mutation-on-failure invariants (balance unchanged after an
  over-withdraw, map unchanged after a bad open). A naive implementation
  (hand-built per-handler error bodies, plain-string errors, shared global store,
  or mutating balance on a failed withdraw) fails these named cases.

  The independent spec runs ONCE with vitest's JSON reporter; results are cached
  module-wide and each L2 Python test asserts on one specific named case (and
  that the case actually executed — a missing case is a failure, so a solution
  cannot pass by deleting cases).

- The agent's OWN colocated suite is checked separately: >=10 cases and passes.

Native test command (per task acceptance criteria):
    npx vitest --run src/helper/error-surface/index.test.ts
"""

import json
import os
import subprocess
import textwrap

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - fallback if helper not co-located
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/hono"
MODULE_DIR = os.path.join(REPO_DIR, "src", "helper", "error-surface")
MODULE_TS = os.path.join(MODULE_DIR, "index.ts")
MODULE_TEST_TS = os.path.join(MODULE_DIR, "index.test.ts")

# Independent verification spec (unique name; never clobbers agent files).
VERIFY_SPEC = os.path.join(MODULE_DIR, "__bench_verify.test.ts")

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
# It exercises the contract against BOTH a directly-mounted instance (prefix '')
# and an instance mounted under a non-empty prefix ('/bank'), so a solution that
# only works at the app root fails.
# ---------------------------------------------------------------------------
_VERIFY_SPEC_SRC = textwrap.dedent(
    """
    import { describe, it, expect } from 'vitest'
    import { Hono } from '../../hono'
    import { createAccounts } from '.'

    const BASE = 'http://localhost'

    // Build a parent app with the accounts resource mounted under `prefix`.
    // prefix === '' mounts at the root ('/'); a non-empty prefix exercises the
    // mounted-under-a-prefix contract.
    const mount = (prefix) => {
      const app = new Hono()
      app.route(prefix === '' ? '/' : prefix, createAccounts())
      return { app, prefix }
    }

    const J = { 'Content-Type': 'application/json' }

    const open = (m, body) =>
      m.app.request(BASE + m.prefix + '/accounts', {
        method: 'POST',
        headers: J,
        body: JSON.stringify(body),
      })
    const deposit = (m, id, body) =>
      m.app.request(BASE + m.prefix + '/accounts/' + id + '/deposit', {
        method: 'POST',
        headers: J,
        body: JSON.stringify(body),
      })
    const withdraw = (m, id, body) =>
      m.app.request(BASE + m.prefix + '/accounts/' + id + '/withdraw', {
        method: 'POST',
        headers: J,
        body: JSON.stringify(body),
      })

    // Assert the uniform error envelope { error: { code, message } } and code.
    const expectEnvelope = async (res, code) => {
      const body = await res.json()
      expect(body).toBeTruthy()
      expect(typeof body).toBe('object')
      expect(body.error).toBeTruthy()
      expect(typeof body.error).toBe('object')
      expect(typeof body.error.code).toBe('string')
      expect(typeof body.error.message).toBe('string')
      expect(body.error.code).toBe(code)
      // The error body must NOT be a plain string or a flat { error: '...' }.
      expect(typeof body.error).not.toBe('string')
    }

    // Run each behavioral block twice: directly mounted and under a prefix.
    const VARIANTS = [['root', ''], ['prefixed', '/bank']]

    describe('error-surface verification', () => {
      it('open_account_201_zero_balance', async () => {
        for (const [, prefix] of VARIANTS) {
          const m = mount(prefix)
          const res = await open(m, { id: 'a' })
          expect(res.status).toBe(201)
          const acct = await res.json()
          expect(acct.id).toBe('a')
          expect(acct.balance).toBe(0)
          expect(acct.error).toBeUndefined()
        }
      })

      it('duplicate_open_409_conflict', async () => {
        for (const [, prefix] of VARIANTS) {
          const m = mount(prefix)
          expect((await open(m, { id: 'a' })).status).toBe(201)
          const dup = await open(m, { id: 'a' })
          expect(dup.status).toBe(409)
          await expectEnvelope(dup, 'conflict')
        }
      })

      it('open_missing_string_id_400_bad_request', async () => {
        for (const [, prefix] of VARIANTS) {
          const m = mount(prefix)
          const noId = await open(m, {})
          expect(noId.status).toBe(400)
          await expectEnvelope(noId, 'bad_request')
          const numId = await open(m, { id: 123 })
          expect(numId.status).toBe(400)
          await expectEnvelope(numId, 'bad_request')
        }
      })

      it('deposit_increases_balance_200', async () => {
        for (const [, prefix] of VARIANTS) {
          const m = mount(prefix)
          await open(m, { id: 'a' })
          const d1 = await deposit(m, 'a', { amount: 50 })
          expect(d1.status).toBe(200)
          expect((await d1.json()).balance).toBe(50)
          const d2 = await deposit(m, 'a', { amount: 25 })
          expect(d2.status).toBe(200)
          const acct = await d2.json()
          expect(acct.id).toBe('a')
          expect(acct.balance).toBe(75)
        }
      })

      it('deposit_non_positive_or_non_number_400', async () => {
        for (const [, prefix] of VARIANTS) {
          const m = mount(prefix)
          await open(m, { id: 'a' })
          await deposit(m, 'a', { amount: 50 })
          const neg = await deposit(m, 'a', { amount: -5 })
          expect(neg.status).toBe(400)
          await expectEnvelope(neg, 'bad_request')
          const zero = await deposit(m, 'a', { amount: 0 })
          expect(zero.status).toBe(400)
          await expectEnvelope(zero, 'bad_request')
          const str = await deposit(m, 'a', { amount: 'ten' })
          expect(str.status).toBe(400)
          await expectEnvelope(str, 'bad_request')
          // None of the rejected deposits may have changed the balance.
          await open(m, { id: 'a' }).catch(() => {})
          const check = await deposit(m, 'a', { amount: 0.000001 })
          // a positive tiny amount is valid; balance should now be 50 + tiny
          const bal = (await check.json()).balance
          expect(bal).toBeCloseTo(50.000001, 5)
        }
      })

      it('withdraw_decreases_balance_200', async () => {
        for (const [, prefix] of VARIANTS) {
          const m = mount(prefix)
          await open(m, { id: 'a' })
          await deposit(m, 'a', { amount: 100 })
          const w = await withdraw(m, 'a', { amount: 30 })
          expect(w.status).toBe(200)
          const acct = await w.json()
          expect(acct.id).toBe('a')
          expect(acct.balance).toBe(70)
        }
      })

      it('overdraw_409_insufficient_funds_balance_unchanged', async () => {
        for (const [, prefix] of VARIANTS) {
          const m = mount(prefix)
          await open(m, { id: 'a' })
          await deposit(m, 'a', { amount: 50 })
          const over = await withdraw(m, 'a', { amount: 70 })
          expect(over.status).toBe(409)
          await expectEnvelope(over, 'insufficient_funds')
          // The failed withdraw MUST NOT have mutated the balance.
          const after = await withdraw(m, 'a', { amount: 50 })
          expect(after.status).toBe(200)
          expect((await after.json()).balance).toBe(0)
        }
      })

      it('operation_on_unknown_id_404_not_found', async () => {
        for (const [, prefix] of VARIANTS) {
          const m = mount(prefix)
          const dep = await deposit(m, 'ghost', { amount: 10 })
          expect(dep.status).toBe(404)
          await expectEnvelope(dep, 'not_found')
          const wd = await withdraw(m, 'ghost', { amount: 10 })
          expect(wd.status).toBe(404)
          await expectEnvelope(wd, 'not_found')
        }
      })

      it('unmatched_route_404_not_found', async () => {
        for (const [, prefix] of VARIANTS) {
          const m = mount(prefix)
          const res = await m.app.request(BASE + m.prefix + '/nope')
          expect(res.status).toBe(404)
          await expectEnvelope(res, 'not_found')
          // A defined resource but undefined sub-path is also not found.
          const res2 = await m.app.request(BASE + m.prefix + '/accounts/a/transfer', {
            method: 'POST',
            headers: J,
            body: JSON.stringify({ amount: 1 }),
          })
          expect(res2.status).toBe(404)
          await expectEnvelope(res2, 'not_found')
        }
      })

      it('instances_are_isolated', async () => {
        const a = new Hono(); a.route('/', createAccounts())
        const b = new Hono(); b.route('/', createAccounts())
        const ma = { app: a, prefix: '' }
        const mb = { app: b, prefix: '' }
        expect((await open(ma, { id: 'a' })).status).toBe(201)
        await deposit(ma, 'a', { amount: 99 })
        // The same id must be openable on the other instance (separate map)...
        expect((await open(mb, { id: 'a' })).status).toBe(201)
        // ...and its balance must be a fresh 0, not 99.
        const wd = await withdraw(mb, 'a', { amount: 1 })
        expect(wd.status).toBe(409)
        await expectEnvelope(wd, 'insufficient_funds')
      })

      it('all_error_bodies_share_uniform_envelope', async () => {
        // Collect one of each error status and assert every body is the SAME
        // shape (object .error with string code+message), never a plain string.
        const m = mount('/bank')
        await open(m, { id: 'a' })
        await deposit(m, 'a', { amount: 10 })
        const samples = [
          [await open(m, { id: 'a' }), 409, 'conflict'],
          [await open(m, {}), 400, 'bad_request'],
          [await withdraw(m, 'a', { amount: 999 }), 409, 'insufficient_funds'],
          [await deposit(m, 'ghost', { amount: 1 }), 404, 'not_found'],
          [await m.app.request(BASE + '/bank/whatever'), 404, 'not_found'],
        ]
        for (const [res, status, code] of samples) {
          expect(res.status).toBe(status)
          const body = await res.json()
          expect(typeof body).toBe('object')
          expect(body.error).toBeTruthy()
          expect(typeof body.error).toBe('object')
          expect(Object.keys(body.error).sort()).toEqual(['code', 'message'])
          expect(typeof body.error.code).toBe('string')
          expect(typeof body.error.message).toBe('string')
          expect(body.error.code).toBe(code)
        }
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
    json_path = os.path.join(REPO_DIR, "__bench_verify_report_ext8.json")
    try:
        proc = _run_vitest(
            "src/helper/error-surface/__bench_verify.test.ts",
            timeout=600,
            json_out=json_path,
        )
        assert os.path.isfile(json_path), (
            "vitest produced no JSON report; the independent verification spec "
            "failed to run (likely a compile/import error in the module).\n"
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
        """L1: the error-surface module file is present."""
        assert os.path.isfile(MODULE_TS), f"missing deliverable {MODULE_TS}"

    def test_module_exports_factory(self):
        """L1: module source exports a `createAccounts` factory."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert "createAccounts" in src, "createAccounts not found"
        assert "export" in src, "factory not exported"

    def test_module_wires_centralized_error_and_notfound_paths(self):
        """L1: module wires a centralized error path and a dedicated not-found path.

        The task mandates failures flow through a single centralized error path
        (`onError`) plus a `notFound` handler, rather than per-handler bodies.
        """
        with open(MODULE_TS) as f:
            src = f.read()
        assert ".onError(" in src, "module does not register a centralized onError path"
        assert ".notFound(" in src, "module does not register a notFound path"

    def test_module_registers_post_routes(self):
        """L1: module registers the POST routes for open/deposit/withdraw."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert ".post(" in src, "module registers no POST route"
        assert "deposit" in src, "no deposit route present"
        assert "withdraw" in src, "no withdraw route present"

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
        result = _run_vitest("src/helper/error-surface/index.test.ts", timeout=600)
        assert result.returncode == 0, (
            "agent's colocated vitest suite failed:\n"
            f"STDOUT:\n{result.stdout[-4000:]}\nSTDERR:\n{result.stderr[-3000:]}"
        )

    # ------------------------------------------------------------- L2 ----
    # Each maps to one task requirement, verified by the independent spec that
    # dispatches in-memory requests against both a root and a prefixed mount.

    def test_open_account_201_zero_balance(self):
        """L2: POST /accounts {id} -> 201 with the created account at balance 0."""
        _assert_case("open_account_201_zero_balance")

    def test_duplicate_open_409_conflict(self):
        """L2: re-opening an existing id -> 409 envelope with code 'conflict'."""
        _assert_case("duplicate_open_409_conflict")

    def test_open_missing_string_id_400_bad_request(self):
        """L2: missing/non-string id -> 400 envelope with code 'bad_request'."""
        _assert_case("open_missing_string_id_400_bad_request")

    def test_deposit_increases_balance_200(self):
        """L2: deposits accumulate and return 200 with the updated balance."""
        _assert_case("deposit_increases_balance_200")

    def test_deposit_non_positive_or_non_number_400(self):
        """L2: non-positive / non-numeric deposit amount -> 400 'bad_request'."""
        _assert_case("deposit_non_positive_or_non_number_400")

    def test_withdraw_decreases_balance_200(self):
        """L2: a valid withdraw returns 200 with the decreased balance."""
        _assert_case("withdraw_decreases_balance_200")

    def test_overdraw_409_insufficient_funds_balance_unchanged(self):
        """L2: over-withdraw -> 409 'insufficient_funds' AND balance is unchanged."""
        _assert_case("overdraw_409_insufficient_funds_balance_unchanged")

    def test_operation_on_unknown_id_404_not_found(self):
        """L2: deposit/withdraw on an unknown id -> 404 'not_found' envelope."""
        _assert_case("operation_on_unknown_id_404_not_found")

    def test_unmatched_route_404_not_found(self):
        """L2: any undefined route -> 404 'not_found' via the not-found path."""
        _assert_case("unmatched_route_404_not_found")

    def test_instances_are_isolated(self):
        """L2: two createAccounts() instances hold independent account maps."""
        _assert_case("instances_are_isolated")

    def test_all_error_bodies_share_uniform_envelope(self):
        """L2: every error (400/404/409) carries the SAME {error:{code,message}} shape."""
        _assert_case("all_error_bodies_share_uniform_envelope")
