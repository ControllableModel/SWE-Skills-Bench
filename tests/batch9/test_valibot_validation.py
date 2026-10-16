"""
Benchmark test for the `valibot-validation` skill (variant ext9).

Skill task (ext9): implement a self-contained ASYNCHRONOUS username-reservation
validator module (`library/src/usernameReservation/`) built on Valibot's own
public API. The module exports:

  * `buildUsernameSchema(isAvailable: (name: string) => Promise<boolean>)`
    -> a schema that incorporates the injected async availability check.
  * `reserveUsername(input: unknown, isAvailable)` -> an async function that
    ALWAYS resolves (never rejects) to a discriminated result:
        success -> { ok: true,  username: <normalized name> }
        failure -> { ok: false, messages: <non-empty array of strings> }

Validation rules (applied in order):
  - input must be a string; surrounding whitespace trimmed + value lower-cased
    before any further check and in the output;
  - normalized length must be 3..20 inclusive;
  - only ASCII lowercase letters, digits, and underscores allowed;
  - finally the normalized name must be reported available by the injected
    async `isAvailable`; that async check runs ONLY after the sync rules pass.

What this test verifies:
  * L1 - the deliverable files exist and are minimally well-formed (the module,
    its barrel re-export, and an authored test suite with >= 10 cases).
  * L2 - DYNAMIC EXECUTION: we drop our OWN vitest drivers into the repo that
    import the agent's `reserveUsername` / `buildUsernameSchema` from
    `library/src/usernameReservation/index.ts` and exercise normalization,
    every length/charset/availability rule, the never-throws contract on
    non-string input, the discriminated result shapes, AND the ordering
    guarantee that the injected async check is only consulted once the
    synchronous rules pass (we count invocations of our injected spy). The
    agent's own test file is NOT trusted for behavior; we exercise the real
    exported function instead. A naive/stub implementation (ignoring the
    injected check, not normalizing, throwing on bad input, or returning a
    fixed shape) MUST fail these drivers.

Run by the harness with:
    python -m pytest /tmp/benchmark_tests/test_valibot_validation.py -v --tb=short
"""

import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/valibot"
LIB_DIR = os.path.join(REPO_DIR, "library")
SRC_DIR = os.path.join(LIB_DIR, "src")
MODULE_DIR = os.path.join(SRC_DIR, "usernameReservation")
# Temp dir for our own driver vitest files (kept inside src so vite resolves it).
DRIVER_DIR = os.path.join(SRC_DIR, "__benchmark_username__")

NPX = "npx"
VITEST_TIMEOUT = 600


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module", autouse=True)
def ensure_deps_and_cleanup():
    """Make sure vitest is runnable and clean up our driver dir afterwards."""
    try:
        from _dependency_utils import ensure_npm_dependencies  # type: ignore

        try:
            ensure_npm_dependencies(LIB_DIR)
        except Exception:
            # Container is expected to already have deps installed; ignore.
            pass
    except Exception:
        pass
    os.makedirs(DRIVER_DIR, exist_ok=True)
    yield
    # Best-effort cleanup of anything we wrote.
    try:
        import shutil

        shutil.rmtree(DRIVER_DIR, ignore_errors=True)
    except Exception:
        pass


def _run_vitest(test_filename):
    """Run a single vitest file (relative to library/) and return CompletedProcess."""
    rel = os.path.relpath(os.path.join(DRIVER_DIR, test_filename), LIB_DIR)
    return subprocess.run(
        [NPX, "vitest", "run", "--no-coverage", rel],
        cwd=LIB_DIR,
        capture_output=True,
        text=True,
        timeout=VITEST_TIMEOUT,
    )


# A deterministic in-memory availability spy reused by most drivers. It is
# AVAILABLE for every name except "taken", and records every name it is asked
# about so a driver can assert the async-gating ordering guarantee.
_SPY_PRELUDE = """
import { describe, expect, test, vi } from 'vitest';
import { reserveUsername, buildUsernameSchema } from '../usernameReservation/index.ts';

function makeSpy(unavailable: string[] = ['taken']) {
  const asked: string[] = [];
  const fn = vi.fn(async (name: string) => {
    asked.push(name);
    return !unavailable.includes(name);
  });
  return { fn, asked };
}
"""


def _write_driver(test_filename, body):
    """Write a vitest driver that imports the agent's module and asserts `body`.

    `body` is TypeScript placed inside a single async `test(...)` block. The
    driver imports the agent's public surface from the barrel via a relative
    path and exposes a `makeSpy()` helper that builds a deterministic injected
    availability function.
    """
    path = os.path.join(DRIVER_DIR, test_filename)
    content = (
        _SPY_PRELUDE
        + "\n"
        + "describe('usernameReservation benchmark driver', () => {\n"
        + "  test('case', async () => {\n"
        + textwrap.indent(textwrap.dedent(body), "    ")
        + "\n  });\n"
        + "});\n"
    )
    with open(path, "w") as fh:
        fh.write(content)
    return path


def _assert_vitest_pass(proc, label):
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, (
        f"[{label}] vitest run failed (rc={proc.returncode}).\n"
        f"----- stdout/stderr -----\n{combined[-4000:]}"
    )
    # Guard against "0 passed" / no-tests-found situations.
    assert "passed" in combined and "0 passed" not in combined, (
        f"[{label}] vitest produced no passing tests.\n{combined[-2000:]}"
    )


# --------------------------------------------------------------------------- #
# L1 - deliverable files exist and are minimally well-formed
# --------------------------------------------------------------------------- #
class TestValibotValidation:
    REPO_DIR = REPO_DIR

    def test_module_file_exists(self):
        """L1: usernameReservation.ts exists and is non-trivially sized."""
        path = os.path.join(MODULE_DIR, "usernameReservation.ts")
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 100, "usernameReservation.ts is suspiciously small"

    def test_barrel_index_exists(self):
        """L1: index.ts barrel exists and re-exports from the module file."""
        path = os.path.join(MODULE_DIR, "index.ts")
        assert os.path.isfile(path), f"missing barrel: {path}"
        with open(path) as fh:
            text = fh.read()
        assert "usernameReservation" in text, (
            "index.ts does not re-export the usernameReservation module"
        )

    def test_agent_test_suite_exists(self):
        """L1: the agent authored a test suite with at least 10 test cases."""
        path = os.path.join(MODULE_DIR, "usernameReservation.test.ts")
        assert os.path.isfile(path), f"missing test file: {path}"
        with open(path) as fh:
            text = fh.read()
        # Count `test(`/`it(` occurrences as a coarse lower bound.
        n = text.count("test(") + text.count("it(")
        assert n >= 10, f"expected >= 10 test cases in suite, found ~{n}"

    # ----------------------------------------------------------------------- #
    # L2 - dynamic execution against the real exported function
    # ----------------------------------------------------------------------- #
    def test_valid_reservation_success_shape(self):
        """L2: a valid available name -> {ok:true, username} with no `messages` key."""
        _write_driver(
            "valid.test.ts",
            """
            const { fn } = makeSpy();
            const r: any = await reserveUsername('ada_99', fn);
            expect(r.ok).toBe(true);
            expect(r.username).toBe('ada_99');
            expect('messages' in r).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("valid.test.ts"), "valid")

    def test_trim_and_lowercase_normalization(self):
        """L2: surrounding whitespace trimmed and value lower-cased in the output."""
        _write_driver(
            "normalize.test.ts",
            """
            const { fn, asked } = makeSpy();
            const r: any = await reserveUsername('  Ada_99  ', fn);
            expect(r.ok).toBe(true);
            expect(r.username).toBe('ada_99');
            // the availability check must be asked about the NORMALIZED name
            expect(asked).toContain('ada_99');
            expect(asked).not.toContain('  Ada_99  ');
            """,
        )
        _assert_vitest_pass(_run_vitest("normalize.test.ts"), "normalize")

    def test_too_short_rejected_and_async_not_consulted(self):
        """L2: a too-short name fails on a sync rule; the async check is NOT consulted."""
        _write_driver(
            "short.test.ts",
            """
            const { fn, asked } = makeSpy();
            const r: any = await reserveUsername('ab', fn);
            expect(r.ok).toBe(false);
            expect(Array.isArray(r.messages)).toBe(true);
            expect(r.messages.length).toBeGreaterThan(0);
            for (const m of r.messages) expect(typeof m).toBe('string');
            // async availability check must NOT run when a sync rule already failed
            expect(fn).not.toHaveBeenCalled();
            expect(asked.length).toBe(0);
            """,
        )
        _assert_vitest_pass(_run_vitest("short.test.ts"), "short")

    def test_too_long_rejected(self):
        """L2: a 21-char name is rejected; a 20-char available name is accepted."""
        _write_driver(
            "long.test.ts",
            """
            const { fn } = makeSpy();
            const tooLong: any = await reserveUsername('a'.repeat(21), fn);
            expect(tooLong.ok).toBe(false);
            expect(Array.isArray(tooLong.messages)).toBe(true);
            expect(tooLong.messages.length).toBeGreaterThan(0);

            // boundary: exactly 20 chars, all legal, available -> success
            const at20 = 'a'.repeat(20);
            const ok: any = await reserveUsername(at20, fn);
            expect(ok.ok).toBe(true);
            expect(ok.username).toBe(at20);
            """,
        )
        _assert_vitest_pass(_run_vitest("long.test.ts"), "long")

    def test_min_length_boundary_accepted(self):
        """L2: exactly 3 chars with digits/underscores is accepted (lower bound)."""
        _write_driver(
            "min.test.ts",
            """
            const { fn } = makeSpy();
            const r: any = await reserveUsername('a_9', fn);
            expect(r.ok).toBe(true);
            expect(r.username).toBe('a_9');
            """,
        )
        _assert_vitest_pass(_run_vitest("min.test.ts"), "min")

    def test_illegal_characters_rejected(self):
        """L2: spaces / punctuation / uppercase-only-after-trim violations rejected."""
        _write_driver(
            "charset.test.ts",
            """
            const { fn } = makeSpy();
            for (const bad of ['has space', 'bad!name', 'dash-name', 'dot.name', 'tab\\tname']) {
              const r: any = await reserveUsername(bad, fn);
              expect(r.ok).toBe(false);
              expect(Array.isArray(r.messages)).toBe(true);
              expect(r.messages.length).toBeGreaterThan(0);
            }
            // internal whitespace is illegal even though the result is long enough
            const r2: any = await reserveUsername('ab cd', fn);
            expect(r2.ok).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("charset.test.ts"), "charset")

    def test_unavailable_name_rejected_after_normalization(self):
        """L2: a name that passes all sync rules but is unavailable (async-false) fails.

        Uses 'Taken' which normalizes to 'taken'; the injected spy reports
        'taken' as unavailable, so the failure is driven SOLELY by the injected
        async check operating on the normalized value.
        """
        _write_driver(
            "unavailable.test.ts",
            """
            const { fn, asked } = makeSpy(); // 'taken' is unavailable
            const r: any = await reserveUsername('Taken', fn);
            expect(r.ok).toBe(false);
            expect(Array.isArray(r.messages)).toBe(true);
            expect(r.messages.length).toBeGreaterThan(0);
            // the async check WAS consulted, on the normalized name
            expect(fn).toHaveBeenCalled();
            expect(asked).toContain('taken');

            // same name but now reported AVAILABLE -> success, proving the
            // decision is driven by the injected function (not hardcoded).
            const { fn: fn2 } = makeSpy([]); // nothing unavailable
            const r2: any = await reserveUsername('Taken', fn2);
            expect(r2.ok).toBe(true);
            expect(r2.username).toBe('taken');
            """,
        )
        _assert_vitest_pass(_run_vitest("unavailable.test.ts"), "unavailable")

    def test_non_string_input_never_throws(self):
        """L2: non-string inputs -> {ok:false, messages:[...]} and never reject/throw."""
        _write_driver(
            "nonstring.test.ts",
            """
            const { fn } = makeSpy();
            for (const input of [42, null, undefined, {}, [], true, Symbol('x') as any]) {
              let r: any;
              await expect(
                (async () => { r = await reserveUsername(input as unknown, fn); })()
              ).resolves.not.toThrow?.();
              // regardless, awaiting must have produced a failure result
              r = await reserveUsername(input as unknown, fn);
              expect(r.ok).toBe(false);
              expect(Array.isArray(r.messages)).toBe(true);
              expect(r.messages.length).toBeGreaterThan(0);
            }
            // a non-string never reaches the availability check
            expect(fn).not.toHaveBeenCalled();
            """,
        )
        _assert_vitest_pass(_run_vitest("nonstring.test.ts"), "nonstring")

    def test_promise_is_returned_and_resolves(self):
        """L2: reserveUsername returns a thenable that resolves (never rejects)."""
        _write_driver(
            "async.test.ts",
            """
            const { fn } = makeSpy();
            const p = reserveUsername('ada_99', fn);
            expect(typeof (p as any).then).toBe('function');
            await expect(p).resolves.toBeTruthy();
            const r: any = await p;
            expect(r.ok).toBe(true);

            // a rejecting result path must still resolve to a failure object
            const bad = reserveUsername(123 as unknown, fn);
            await expect(bad).resolves.toMatchObject({ ok: false });
            """,
        )
        _assert_vitest_pass(_run_vitest("async.test.ts"), "async")

    def test_build_username_schema_is_async_and_uses_injection(self):
        """L2: buildUsernameSchema returns a schema usable with v.safeParseAsync,
        whose availability decision comes from the injected function.
        """
        path = os.path.join(DRIVER_DIR, "schema.test.ts")
        content = textwrap.dedent(
            """
            import { describe, expect, test, vi } from 'vitest';
            import * as v from '../index.ts';
            import { buildUsernameSchema } from '../usernameReservation/index.ts';

            describe('buildUsernameSchema driver', () => {
              test('schema honors injected availability via safeParseAsync', async () => {
                const askedAvail: string[] = [];
                const available = vi.fn(async (name: string) => {
                  askedAvail.push(name);
                  return true;
                });
                const schemaOk = buildUsernameSchema(available);
                const okRes: any = await v.safeParseAsync(schemaOk, '  Ada_99  ');
                expect(okRes.success).toBe(true);
                expect(okRes.output).toBe('ada_99');
                expect(askedAvail).toContain('ada_99');

                // when injection reports unavailable, an otherwise-valid name fails
                const unavailable = vi.fn(async () => false);
                const schemaNo = buildUsernameSchema(unavailable);
                const noRes: any = await v.safeParseAsync(schemaNo, 'ada_99');
                expect(noRes.success).toBe(false);
                expect(Array.isArray(noRes.issues)).toBe(true);
                expect(noRes.issues.length).toBeGreaterThan(0);
                expect(unavailable).toHaveBeenCalled();
              });
            });
            """
        )
        with open(path, "w") as fh:
            fh.write(content)
        _assert_vitest_pass(_run_vitest("schema.test.ts"), "schema")

    def test_async_check_only_after_sync_rules(self):
        """L2: the injected async check is consulted for valid sync input but
        skipped for every sync-rule violation -> proves correct ordering.
        """
        _write_driver(
            "ordering.test.ts",
            """
            // valid input: async check IS consulted exactly once, on normalized name
            const { fn: good, asked: askedGood } = makeSpy([]);
            const okRes: any = await reserveUsername('  GoodName_1  ', good);
            expect(okRes.ok).toBe(true);
            expect(good).toHaveBeenCalledTimes(1);
            expect(askedGood).toEqual(['goodname_1']);

            // each of these violates a sync rule -> async check NEVER consulted
            const syncBad = ['ab', 'a'.repeat(21), 'has space', 'BAD!', 42 as any, null as any];
            for (const input of syncBad) {
              const { fn, asked } = makeSpy([]);
              const r: any = await reserveUsername(input as unknown, fn);
              expect(r.ok).toBe(false);
              expect(fn).not.toHaveBeenCalled();
              expect(asked.length).toBe(0);
            }
            """,
        )
        _assert_vitest_pass(_run_vitest("ordering.test.ts"), "ordering")

    def test_agent_own_suite_passes(self):
        """L2: the agent's authored suite passes under the native command."""
        proc = subprocess.run(
            [
                NPX,
                "vitest",
                "run",
                "--no-coverage",
                "src/usernameReservation/usernameReservation.test.ts",
            ],
            cwd=LIB_DIR,
            capture_output=True,
            text=True,
            timeout=VITEST_TIMEOUT,
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "agent's own usernameReservation.test.ts suite did not pass.\n"
            f"{combined[-4000:]}"
        )
