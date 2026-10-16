"""
Benchmark test for the `valibot-validation` skill (variant ext8).

Skill task: build a *profile schema family with derived views* in a
self-contained module (`library/src/accountSchemas/`) using Valibot's own
public API. One canonical base object schema `AccountSchema` defines:
  id (integer >= 1), username (string len 3..20), email (valid email),
  password (string len >= 8), bio (string len <= 200).
Four derived schemas MUST be obtained from the base (via pick/omit/partial/
extend-style composition), not re-declared field-by-field:
  * PublicAccountSchema   -> only { id, username }
  * SafeAccountSchema     -> every field EXCEPT password
  * AccountPatchSchema    -> same fields as Safe, but every field optional
                             ({} is a valid patch; id also optional)
  * ExtendedAccountSchema -> every base field + required ISO date-time createdAt
Plus parse helpers parsePublic / parsePatch / parseExtended that validate and
throw on failure, and every schema strips unknown keys.

What this test verifies:
  * L1 - the deliverable files exist and are minimally well-formed (the module,
    its barrel re-export, and an agent test suite with >= 10 cases).
  * L2 - DYNAMIC EXECUTION: we drop our OWN vitest drivers into the repo that
    import the agent's exports from `library/src/accountSchemas/index.ts` and
    exercise: each derived schema's accepted shape, the omission of password /
    email in the safe / public outputs, the empty-patch acceptance, a present-
    but-invalid patch field, the `id >= 1` rule surviving into derived views,
    the required ISO `createdAt` on the extended view, and unknown-key
    stripping. The agent's own test file is NOT trusted for behavior; we drive
    the real exported schemas + functions instead. A naive stub (e.g. a Public
    schema that still carries email, a patch that rejects {}, an extended view
    that accepts a malformed createdAt, or schemas that fail to drop password)
    is caught by these assertions.

Native acceptance command (run from library/):
    npx vitest run src/accountSchemas/accountSchemas.test.ts

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
MODULE_DIR = os.path.join(SRC_DIR, "accountSchemas")
# Temp dir for our own driver vitest files (kept inside src so vite resolves it).
DRIVER_DIR = os.path.join(SRC_DIR, "__benchmark_accounts__")

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
    imports the parse helpers from the agent's barrel file. The base + derived
    schemas are imported too so we can validate object keys directly via
    `v.parse(SafeAccountSchema, ...)` etc.
    """
    path = os.path.join(DRIVER_DIR, test_filename)
    content = textwrap.dedent(
        """
        import {{ describe, expect, test }} from 'vitest';
        import * as v from '../index.ts';
        import {{
          AccountSchema,
          PublicAccountSchema,
          SafeAccountSchema,
          AccountPatchSchema,
          ExtendedAccountSchema,
          parsePublic,
          parsePatch,
          parseExtended,
        }} from '../accountSchemas/index.ts';

        // A fully valid base account (every base rule satisfied).
        const FULL = {{
          id: 1,
          username: 'ada',
          email: 'a@b.io',
          password: 'longenough',
          bio: '',
        }};
        const CREATED_AT = '2025-01-01T00:00:00.000Z';

        describe('accountSchemas benchmark driver', () => {{
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
    assert "passed" in combined, (
        f"[{label}] vitest produced no passing tests.\n{combined[-2000:]}"
    )


# --------------------------------------------------------------------------- #
# L1 - deliverable files exist and are minimally well-formed
# --------------------------------------------------------------------------- #
class TestValibotValidation:
    REPO_DIR = REPO_DIR

    def test_module_file_exists(self):
        """L1: accountSchemas.ts exists and is non-trivially sized."""
        path = os.path.join(MODULE_DIR, "accountSchemas.ts")
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 100, "accountSchemas.ts is suspiciously small"

    def test_barrel_index_exists(self):
        """L1: index.ts barrel exists and re-exports from the module file."""
        path = os.path.join(MODULE_DIR, "index.ts")
        assert os.path.isfile(path), f"missing barrel: {path}"
        with open(path) as fh:
            text = fh.read()
        assert "accountSchemas" in text, (
            "index.ts does not re-export the accountSchemas module"
        )

    def test_agent_test_suite_exists(self):
        """L1: the agent authored a test suite with at least 10 test cases."""
        path = os.path.join(MODULE_DIR, "accountSchemas.test.ts")
        assert os.path.isfile(path), f"missing test file: {path}"
        with open(path) as fh:
            text = fh.read()
        # Count `test(`/`it(` occurrences as a coarse lower bound.
        n = text.count("test(") + text.count("it(")
        assert n >= 10, f"expected >= 10 test cases in suite, found ~{n}"

    # ----------------------------------------------------------------------- #
    # L2 - dynamic execution against the real exported schemas + functions
    # ----------------------------------------------------------------------- #
    def test_public_view_shape_and_email_omission(self):
        """L2: PublicAccountSchema yields exactly {id, username}; email dropped."""
        _write_driver(
            "public_shape.test.ts",
            """
            const a = parsePublic({ id: 1, username: 'ada' });
            expect(a).toEqual({ id: 1, username: 'ada' });

            // Extra base fields are stripped, not carried into the public output.
            const b = parsePublic({ id: 1, username: 'ada', email: 'a@b.io' }) as any;
            expect(b).toEqual({ id: 1, username: 'ada' });
            expect('email' in b).toBe(false);
            expect(Object.keys(b).sort()).toEqual(['id', 'username']);
            """,
        )
        _assert_vitest_pass(_run_vitest("public_shape.test.ts"), "public_shape")

    def test_public_id_minimum_rule_survives(self):
        """L2: the base `id >= 1` rule survives into the derived public view."""
        _write_driver(
            "public_id.test.ts",
            """
            expect(() => parsePublic({ id: 0, username: 'ada' })).toThrow();
            expect(() => parsePublic({ id: -5, username: 'ada' })).toThrow();
            // username min-length (3) also survives.
            expect(() => parsePublic({ id: 1, username: 'ab' })).toThrow();
            // valid boundary id = 1 accepted.
            const ok = parsePublic({ id: 1, username: 'ada' }) as any;
            expect(ok.id).toBe(1);
            """,
        )
        _assert_vitest_pass(_run_vitest("public_id.test.ts"), "public_id")

    def test_safe_view_omits_password_keeps_rest(self):
        """L2: SafeAccountSchema carries every base field except password."""
        _write_driver(
            "safe_shape.test.ts",
            """
            const r = v.parse(SafeAccountSchema, {
              id: 7, username: 'ada', email: 'a@b.io',
              password: 'longenough', bio: 'hi',
            }) as any;
            expect('password' in r).toBe(false);
            expect(Object.keys(r).sort()).toEqual(
              ['bio', 'email', 'id', 'username'].sort()
            );
            expect(r.id).toBe(7);
            expect(r.username).toBe('ada');
            expect(r.email).toBe('a@b.io');
            expect(r.bio).toBe('hi');
            // Base rules still enforced (bad email rejected under safe view).
            expect(() => v.parse(SafeAccountSchema, {
              id: 7, username: 'ada', email: 'nope', bio: '',
            })).toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("safe_shape.test.ts"), "safe_shape")

    def test_patch_accepts_empty_object(self):
        """L2: AccountPatchSchema accepts {} (all fields optional, incl. id)."""
        _write_driver(
            "patch_empty.test.ts",
            """
            const empty = parsePatch({});
            expect(empty).toEqual({});

            // A single-field patch validates that field and carries only it.
            const one = parsePatch({ username: 'newname' }) as any;
            expect(one).toEqual({ username: 'newname' });
            expect('id' in one).toBe(false);
            expect('email' in one).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("patch_empty.test.ts"), "patch_empty")

    def test_patch_present_field_still_validated(self):
        """L2: a present patch field is validated against the base rules."""
        _write_driver(
            "patch_invalid.test.ts",
            """
            // username present but below min length -> throws.
            expect(() => parsePatch({ username: 'x' })).toThrow();
            // id present but below 1 -> throws (id rule survives into patch).
            expect(() => parsePatch({ id: 0 })).toThrow();
            // email present but malformed -> throws.
            expect(() => parsePatch({ email: 'not-an-email' })).toThrow();
            // patch never carries password (omitted view); supplying it is stripped.
            const r = parsePatch({ username: 'newname', password: 'longenough' }) as any;
            expect('password' in r).toBe(false);
            expect(r.username).toBe('newname');
            """,
        )
        _assert_vitest_pass(_run_vitest("patch_invalid.test.ts"), "patch_invalid")

    def test_extended_view_requires_iso_created_at(self):
        """L2: ExtendedAccountSchema needs a valid ISO date-time createdAt."""
        _write_driver(
            "extended.test.ts",
            """
            const ok = parseExtended({ ...FULL, createdAt: CREATED_AT }) as any;
            expect(ok.createdAt).toBe(CREATED_AT);
            expect(ok.id).toBe(1);
            expect(ok.username).toBe('ada');
            expect(ok.email).toBe('a@b.io');
            expect(ok.password).toBe('longenough');
            expect('createdAt' in ok).toBe(true);

            // Missing createdAt -> throws.
            expect(() => parseExtended({ ...FULL })).toThrow();
            // Malformed createdAt -> throws.
            expect(() => parseExtended({ ...FULL, createdAt: 'yesterday' })).toThrow();
            expect(() => parseExtended({ ...FULL, createdAt: '2025-13-40' })).toThrow();
            expect(() => parseExtended({ ...FULL, createdAt: 12345 })).toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("extended.test.ts"), "extended")

    def test_extended_keeps_password_and_base_rules(self):
        """L2: extended view retains password and enforces base validators."""
        _write_driver(
            "extended_full.test.ts",
            """
            const r = v.parse(ExtendedAccountSchema, {
              ...FULL, createdAt: CREATED_AT,
            }) as any;
            // Extended = all base fields + createdAt.
            expect(Object.keys(r).sort()).toEqual(
              ['bio', 'createdAt', 'email', 'id', 'password', 'username'].sort()
            );
            expect('password' in r).toBe(true);

            // Base rules still enforced under the extended view.
            expect(() => v.parse(ExtendedAccountSchema, {
              ...FULL, password: 'short', createdAt: CREATED_AT,
            })).toThrow();
            expect(() => v.parse(ExtendedAccountSchema, {
              ...FULL, id: 0, createdAt: CREATED_AT,
            })).toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("extended_full.test.ts"), "extended_full")

    def test_unknown_keys_stripped_across_views(self):
        """L2: every schema strips unknown keys from its output."""
        _write_driver(
            "strip.test.ts",
            """
            const pub = parsePublic({
              id: 1, username: 'ada', evil: 'x', isAdmin: true,
            }) as any;
            expect('evil' in pub).toBe(false);
            expect('isAdmin' in pub).toBe(false);
            expect(Object.keys(pub).sort()).toEqual(['id', 'username']);

            const safe = v.parse(SafeAccountSchema, {
              id: 1, username: 'ada', email: 'a@b.io', bio: '',
              password: 'longenough', surprise: 99,
            }) as any;
            expect('surprise' in safe).toBe(false);
            expect('password' in safe).toBe(false);

            const ext = parseExtended({
              ...FULL, createdAt: CREATED_AT, extra: 'nope',
            }) as any;
            expect('extra' in ext).toBe(false);

            const patch = parsePatch({ username: 'newname', junk: 1 }) as any;
            expect('junk' in patch).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("strip.test.ts"), "strip")

    def test_base_schema_field_rules(self):
        """L2: base AccountSchema enforces each documented field rule."""
        _write_driver(
            "base_rules.test.ts",
            """
            // valid base account parses cleanly.
            const ok = v.parse(AccountSchema, FULL) as any;
            expect(ok.id).toBe(1);
            expect(Object.keys(ok).sort()).toEqual(
              ['bio', 'email', 'id', 'password', 'username'].sort()
            );

            // id must be an integer >= 1.
            expect(() => v.parse(AccountSchema, { ...FULL, id: 0 })).toThrow();
            expect(() => v.parse(AccountSchema, { ...FULL, id: 1.5 })).toThrow();
            // username length 3..20.
            expect(() => v.parse(AccountSchema, { ...FULL, username: 'ab' })).toThrow();
            expect(() => v.parse(AccountSchema, { ...FULL, username: 'a'.repeat(21) })).toThrow();
            // email validity.
            expect(() => v.parse(AccountSchema, { ...FULL, email: 'bad' })).toThrow();
            // password min length 8.
            expect(() => v.parse(AccountSchema, { ...FULL, password: 'short' })).toThrow();
            // bio max length 200.
            expect(() => v.parse(AccountSchema, { ...FULL, bio: 'b'.repeat(201) })).toThrow();
            // bio boundary 200 accepted.
            const okBio = v.parse(AccountSchema, { ...FULL, bio: 'b'.repeat(200) }) as any;
            expect(okBio.bio.length).toBe(200);
            """,
        )
        _assert_vitest_pass(_run_vitest("base_rules.test.ts"), "base_rules")

    def test_derived_distinct_from_base_keysets(self):
        """L2: the four derived views have the documented, distinct key sets.

        This is the discriminative core: a stub that simply re-exports the base
        schema for every view (or a Public view that still carries email) fails.
        """
        _write_driver(
            "keysets.test.ts",
            """
            const base = v.parse(AccountSchema, FULL) as any;
            expect(Object.keys(base).sort()).toEqual(
              ['bio', 'email', 'id', 'password', 'username'].sort()
            );

            const pub = v.parse(PublicAccountSchema, FULL) as any;
            expect(Object.keys(pub).sort()).toEqual(['id', 'username']);

            const safe = v.parse(SafeAccountSchema, FULL) as any;
            expect(Object.keys(safe).sort()).toEqual(
              ['bio', 'email', 'id', 'username'].sort()
            );
            expect('password' in safe).toBe(false);

            // Patch is all-optional: {} valid, and a full input keeps all safe keys.
            expect(v.parse(AccountPatchSchema, {})).toEqual({});
            const patchFull = v.parse(AccountPatchSchema, FULL) as any;
            expect('password' in patchFull).toBe(false);
            expect(Object.keys(patchFull).sort()).toEqual(
              ['bio', 'email', 'id', 'username'].sort()
            );

            const ext = v.parse(ExtendedAccountSchema, { ...FULL, createdAt: CREATED_AT }) as any;
            expect(Object.keys(ext).sort()).toEqual(
              ['bio', 'createdAt', 'email', 'id', 'password', 'username'].sort()
            );
            """,
        )
        _assert_vitest_pass(_run_vitest("keysets.test.ts"), "keysets")

    def test_agent_own_suite_passes(self):
        """L2: the agent's authored suite passes under the native command."""
        proc = subprocess.run(
            [
                NPX,
                "vitest",
                "run",
                "--no-coverage",
                "src/accountSchemas/accountSchemas.test.ts",
            ],
            cwd=LIB_DIR,
            capture_output=True,
            text=True,
            timeout=VITEST_TIMEOUT,
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "agent's own accountSchemas.test.ts suite did not pass.\n"
            f"{combined[-4000:]}"
        )
