"""
Benchmark test for the `valibot-validation` skill.

Skill task: implement a self-contained signup-payload validation module
(`library/src/signupForm/`) built on Valibot's own public API. The module
exports `validateSignup(input: unknown)` plus its underlying schema and returns
a discriminated result: `{ ok: true, data }` on success or
`{ ok: false, errors }` on failure (a field-keyed map of message arrays).

What this test verifies:
  * L1 - the deliverable files exist and are minimally well-formed (the module,
    its barrel re-export, and a test suite with >= 10 cases).
  * L2 - DYNAMIC EXECUTION: we drop our own vitest driver into the repo that
    imports the agent's `validateSignup` from `library/src/signupForm/index.ts`
    and exercises every field rule, normalization step, defaulting, unknown-key
    stripping, cross-field mismatch routing and non-object input handling, then
    deep-validates the returned data structures. The agent's own test file is
    NOT trusted for behavior; we exercise the real exported function instead.

Run by the harness with:
    python -m pytest /tmp/benchmark_tests/test_valibot_validation.py -v --tb=short
"""

import json
import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/valibot"
LIB_DIR = os.path.join(REPO_DIR, "library")
SRC_DIR = os.path.join(LIB_DIR, "src")
MODULE_DIR = os.path.join(SRC_DIR, "signupForm")
# Temp dir for our own driver vitest files (kept inside src so vite resolves it).
DRIVER_DIR = os.path.join(SRC_DIR, "__benchmark_signup__")

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


def _write_driver(test_filename, body):
    """Write a vitest driver that imports the agent's module and asserts `body`.

    `body` is TypeScript placed inside a single `test(...)` block. The driver
    imports `validateSignup` from the agent's barrel file via a relative path.
    """
    path = os.path.join(DRIVER_DIR, test_filename)
    content = textwrap.dedent(
        """
        import {{ describe, expect, test }} from 'vitest';
        import {{ validateSignup }} from '../signupForm/index.ts';

        const VALID = {{
          username: 'Ada_99',
          email: 'a@b.io',
          age: '20',
          role: 'editor',
          password: 'Abcdefghi9',
          confirmPassword: 'Abcdefghi9',
          tags: ['math'],
        }};

        describe('signupForm benchmark driver', () => {{
          test('case', () => {{
        {body}
          }});
        }});
        """
    ).format(body=textwrap.indent(textwrap.dedent(body), "    "))
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
    assert "1 passed" in combined or "passed" in combined, (
        f"[{label}] vitest produced no passing tests.\n{combined[-2000:]}"
    )


# --------------------------------------------------------------------------- #
# L1 - deliverable files exist and are minimally well-formed
# --------------------------------------------------------------------------- #
class TestValibotValidation:
    REPO_DIR = REPO_DIR

    def test_module_file_exists(self):
        """L1: signupForm.ts exists and is non-trivially sized."""
        path = os.path.join(MODULE_DIR, "signupForm.ts")
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 100, "signupForm.ts is suspiciously small"

    def test_barrel_index_exists(self):
        """L1: index.ts barrel exists and re-exports from the module file."""
        path = os.path.join(MODULE_DIR, "index.ts")
        assert os.path.isfile(path), f"missing barrel: {path}"
        with open(path) as fh:
            text = fh.read()
        assert "signupForm" in text, "index.ts does not re-export the signupForm module"

    def test_agent_test_suite_exists(self):
        """L1: the agent authored a test suite with at least 10 test cases."""
        path = os.path.join(MODULE_DIR, "signupForm.test.ts")
        assert os.path.isfile(path), f"missing test file: {path}"
        with open(path) as fh:
            text = fh.read()
        # Count `test(`/`it(` occurrences as a coarse lower bound.
        n = text.count("test(") + text.count("it(")
        assert n >= 10, f"expected >= 10 test cases in suite, found ~{n}"

    # ----------------------------------------------------------------------- #
    # L2 - dynamic execution against the real exported function
    # ----------------------------------------------------------------------- #
    def test_valid_payload_success_and_normalization(self):
        """L2: a fully valid payload -> ok:true with normalized typed data."""
        _write_driver(
            "valid.test.ts",
            """
            const r = validateSignup(VALID) as any;
            expect(r.ok).toBe(true);
            expect(r.data.username).toBe('Ada_99');
            expect(r.data.email).toBe('a@b.io');
            expect(r.data.age).toBe(20);
            expect(typeof r.data.age).toBe('number');
            expect(r.data.role).toBe('editor');
            expect(r.data.password).toBe('Abcdefghi9');
            expect(r.data.confirmPassword).toBe('Abcdefghi9');
            expect(r.data.tags).toEqual(['math']);
            expect('errors' in r).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("valid.test.ts"), "valid")

    def test_trim_lowercase_and_age_conversion(self):
        """L2: username trimmed, email trimmed+lowercased, age string->number."""
        _write_driver(
            "normalize.test.ts",
            """
            const r = validateSignup({
              username: '  bob  ',
              email: 'B@X.io',
              age: '20',
              password: 'Abcdefghi9',
              confirmPassword: 'Abcdefghi9',
            }) as any;
            expect(r.ok).toBe(true);
            expect(r.data.username).toBe('bob');
            expect(r.data.email).toBe('b@x.io');
            expect(r.data.age).toBe(20);
            expect(typeof r.data.age).toBe('number');
            """,
        )
        _assert_vitest_pass(_run_vitest("normalize.test.ts"), "normalize")

    def test_role_and_tags_defaults(self):
        """L2: omitting role/tags yields role 'viewer' and tags []."""
        _write_driver(
            "defaults.test.ts",
            """
            const r = validateSignup({
              username: 'bob',
              email: 'b@x.io',
              age: '20',
              password: 'Abcdefghi9',
              confirmPassword: 'Abcdefghi9',
            }) as any;
            expect(r.ok).toBe(true);
            expect(r.data.role).toBe('viewer');
            expect(r.data.tags).toEqual([]);
            """,
        )
        _assert_vitest_pass(_run_vitest("defaults.test.ts"), "defaults")

    def test_unknown_keys_stripped(self):
        """L2: unknown extra keys must not appear in normalized data."""
        _write_driver(
            "strip.test.ts",
            """
            const r = validateSignup({
              ...VALID,
              evil: 'x',
              isAdmin: true,
              __proto__nope: 1,
            }) as any;
            expect(r.ok).toBe(true);
            const keys = Object.keys(r.data).sort();
            expect(keys).toEqual(
              ['age','confirmPassword','email','password','role','tags','username'].sort()
            );
            expect('evil' in r.data).toBe(false);
            expect('isAdmin' in r.data).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("strip.test.ts"), "strip")

    def test_example_payload_reports_password_uppercase(self):
        """L2: the spec example (no uppercase in password) -> only `password` errors."""
        _write_driver(
            "example.test.ts",
            """
            const r = validateSignup({
              username: '  Ada_Lovelace  ',
              email: 'ADA@Example.COM ',
              age: '37',
              role: 'admin',
              password: 'hunter2hunter2',
              confirmPassword: 'hunter2hunter2',
              tags: ['math', 'engineering'],
            }) as any;
            expect(r.ok).toBe(false);
            expect(r.errors).toBeTruthy();
            expect('password' in r.errors).toBe(true);
            expect(Array.isArray(r.errors.password)).toBe(true);
            expect(r.errors.password.length).toBeGreaterThan(0);
            // every message is a string
            for (const m of r.errors.password) expect(typeof m).toBe('string');
            // no other field should be flagged (all others are valid)
            const offending = Object.keys(r.errors);
            expect(offending).toEqual(['password']);
            """,
        )
        _assert_vitest_pass(_run_vitest("example.test.ts"), "example")

    def test_age_range_and_type_rejection(self):
        """L2: out-of-range / non-numeric / fractional ages are rejected under `age`."""
        _write_driver(
            "age.test.ts",
            """
            const tooYoung = validateSignup({ ...VALID, age: '9' }) as any;
            expect(tooYoung.ok).toBe(false);
            expect('age' in tooYoung.errors).toBe(true);

            const tooOld = validateSignup({ ...VALID, age: '200' }) as any;
            expect(tooOld.ok).toBe(false);
            expect('age' in tooOld.errors).toBe(true);

            const nonNumeric = validateSignup({ ...VALID, age: 'abc' }) as any;
            expect(nonNumeric.ok).toBe(false);
            expect('age' in nonNumeric.errors).toBe(true);

            const fractional = validateSignup({ ...VALID, age: '20.5' }) as any;
            expect(fractional.ok).toBe(false);
            expect('age' in fractional.errors).toBe(true);

            // boundary values are accepted
            const low = validateSignup({ ...VALID, age: '13' }) as any;
            expect(low.ok).toBe(true);
            expect(low.data.age).toBe(13);
            const high = validateSignup({ ...VALID, age: '120' }) as any;
            expect(high.ok).toBe(true);
            expect(high.data.age).toBe(120);
            """,
        )
        _assert_vitest_pass(_run_vitest("age.test.ts"), "age")

    def test_username_rules(self):
        """L2: username length bounds and allowed-character set are enforced."""
        _write_driver(
            "username.test.ts",
            """
            const short = validateSignup({ ...VALID, username: 'ab' }) as any;
            expect(short.ok).toBe(false);
            expect('username' in short.errors).toBe(true);

            const long = validateSignup({ ...VALID, username: 'a'.repeat(21) }) as any;
            expect(long.ok).toBe(false);
            expect('username' in long.errors).toBe(true);

            const bad = validateSignup({ ...VALID, username: 'bad name!' }) as any;
            expect(bad.ok).toBe(false);
            expect('username' in bad.errors).toBe(true);

            // exactly 3 chars with underscores/digits is accepted
            const ok3 = validateSignup({ ...VALID, username: 'a_9' }) as any;
            expect(ok3.ok).toBe(true);
            expect(ok3.data.username).toBe('a_9');
            """,
        )
        _assert_vitest_pass(_run_vitest("username.test.ts"), "username")

    def test_email_validity(self):
        """L2: malformed email rejected; normalization happens before validation."""
        _write_driver(
            "email.test.ts",
            """
            const bad = validateSignup({ ...VALID, email: 'not-an-email' }) as any;
            expect(bad.ok).toBe(false);
            expect('email' in bad.errors).toBe(true);

            // surrounding whitespace + uppercase should still validate after normalize
            const ok = validateSignup({ ...VALID, email: '  USER@Domain.IO  ' }) as any;
            expect(ok.ok).toBe(true);
            expect(ok.data.email).toBe('user@domain.io');
            """,
        )
        _assert_vitest_pass(_run_vitest("email.test.ts"), "email")

    def test_password_rules_and_mismatch_routing(self):
        """L2: password complexity rules + mismatch routed to confirmPassword."""
        _write_driver(
            "password.test.ts",
            """
            // too short
            const short = validateSignup({
              ...VALID, password: 'Ab9', confirmPassword: 'Ab9',
            }) as any;
            expect(short.ok).toBe(false);
            expect('password' in short.errors).toBe(true);

            // missing uppercase
            const noUpper = validateSignup({
              ...VALID, password: 'abcdefghi9', confirmPassword: 'abcdefghi9',
            }) as any;
            expect(noUpper.ok).toBe(false);
            expect('password' in noUpper.errors).toBe(true);

            // missing digit
            const noDigit = validateSignup({
              ...VALID, password: 'Abcdefghij', confirmPassword: 'Abcdefghij',
            }) as any;
            expect(noDigit.ok).toBe(false);
            expect('password' in noDigit.errors).toBe(true);

            // mismatch: routed to confirmPassword, NOT password
            const mismatch = validateSignup({
              ...VALID, password: 'Abcdefghi9', confirmPassword: 'Different99X',
            }) as any;
            expect(mismatch.ok).toBe(false);
            expect('confirmPassword' in mismatch.errors).toBe(true);
            expect('password' in mismatch.errors).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("password.test.ts"), "password")

    def test_role_and_tags_validation_failures(self):
        """L2: invalid role rejected under `role`; oversized tags rejected under `tags`."""
        _write_driver(
            "role_tags.test.ts",
            """
            const badRole = validateSignup({ ...VALID, role: 'superuser' }) as any;
            expect(badRole.ok).toBe(false);
            expect('role' in badRole.errors).toBe(true);
            expect('username' in badRole.errors).toBe(false);

            const manyTags = validateSignup({
              ...VALID, tags: ['a','b','c','d','e','f'],
            }) as any;
            expect(manyTags.ok).toBe(false);
            expect('tags' in manyTags.errors).toBe(true);

            const badTagType = validateSignup({ ...VALID, tags: [1, 2] }) as any;
            expect(badTagType.ok).toBe(false);
            expect('tags' in badTagType.errors).toBe(true);

            // each of the three allowed roles is accepted
            for (const role of ['admin','editor','viewer']) {
              const r = validateSignup({ ...VALID, role }) as any;
              expect(r.ok).toBe(true);
              expect(r.data.role).toBe(role);
            }
            """,
        )
        _assert_vitest_pass(_run_vitest("role_tags.test.ts"), "role_tags")

    def test_non_object_inputs_never_throw(self):
        """L2: 42, null, "hello", undefined and {} -> failure with non-empty error map, no throw."""
        _write_driver(
            "nonobject.test.ts",
            """
            for (const input of [42, null, 'hello', undefined, [], true]) {
              let r: any;
              expect(() => { r = validateSignup(input as unknown); }).not.toThrow();
              expect(r.ok).toBe(false);
              expect(r.errors).toBeTruthy();
              expect(typeof r.errors).toBe('object');
              expect(Object.keys(r.errors).length).toBeGreaterThan(0);
            }

            // an empty object is missing required fields -> failure with multiple keys
            const empty = validateSignup({}) as any;
            expect(empty.ok).toBe(false);
            expect(Object.keys(empty.errors).length).toBeGreaterThan(0);
            """,
        )
        _assert_vitest_pass(_run_vitest("nonobject.test.ts"), "nonobject")

    def test_agent_own_suite_passes(self):
        """L2: the agent's authored suite passes under the native command."""
        proc = subprocess.run(
            [NPX, "vitest", "run", "--no-coverage", "src/signupForm/signupForm.test.ts"],
            cwd=LIB_DIR,
            capture_output=True,
            text=True,
            timeout=VITEST_TIMEOUT,
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "agent's own signupForm.test.ts suite did not pass.\n"
            f"{combined[-4000:]}"
        )
