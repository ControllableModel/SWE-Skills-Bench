"""
Benchmark test for the `valibot-validation` skill (variant ext7).

Skill task (ext7 - "Field-Error Reporter for a Booking Form"):
implement a self-contained hotel-booking validation module
(`library/src/bookingForm/`) built on Valibot's own public API. The module
exports `validateBooking(input: unknown)` plus its underlying schema and
returns a discriminated result:
  * on success: `{ ok: true, data: <validated booking> }`
  * on failure: `{ ok: false, fieldErrors: <map from DOTTED path to message-array> }`
`validateBooking` must NEVER throw. The `fieldErrors` keys are dotted path
strings derived from the validation issues' path information (e.g.
`"guest.email"`, `"nights"`), and the values are arrays of message strings.
On success `data.guest.name` is trimmed, `data.guest.email` is lower-cased,
and unknown keys (top level and inside `guest`) are stripped.

What this test verifies:
  * L1 - the deliverable files exist and are minimally well-formed (the module,
    its barrel re-export, and an agent-authored test suite with >= 10 cases).
  * L2 - DYNAMIC EXECUTION: we drop our OWN independent vitest driver into the
    repo that imports the agent's `validateBooking` from
    `library/src/bookingForm/index.ts` and exercises every field rule, the
    DOTTED nested-path keying, trimming / lower-casing normalization,
    unknown-key stripping (top level + inside guest), single-field and
    multi-field failures, boundary cases and non-object inputs, then
    deep-validates the returned data structures and exact error-key sets.
    The agent's own test file is NOT trusted for behavior; we exercise the
    real exported function instead.

A naive/stub implementation (e.g. one that hardcodes a flat key list, never
strips unknown keys, returns a fixed result, throws on non-objects, or fails
to build the dotted nested path `guest.email`) MUST fail this test.

Native acceptance command (driven by L2, run from `library/`):
    npx vitest run src/bookingForm/bookingForm.test.ts

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
MODULE_DIR = os.path.join(SRC_DIR, "bookingForm")
# Temp dir for our own driver vitest files (kept inside src so vite resolves it).
DRIVER_DIR = os.path.join(SRC_DIR, "__benchmark_booking__")

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
    imports `validateBooking` from the agent's barrel file via a relative path
    and exposes a `VALID` fixture (the spec's nested booking example).
    """
    path = os.path.join(DRIVER_DIR, test_filename)
    content = textwrap.dedent(
        """
        import {{ describe, expect, test }} from 'vitest';
        import {{ validateBooking }} from '../bookingForm/index.ts';

        // The canonical valid nested payload from the spec.
        const VALID = {{
          guest: {{ name: 'Ada', email: 'ada@host.io' }},
          nights: 3,
          roomType: 'deluxe',
          checkIn: '2025-06-01',
        }};

        describe('bookingForm benchmark driver', () => {{
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
class TestValibotValidation:
    REPO_DIR = REPO_DIR

    # ----------------------------------------------------------------------- #
    # L1 - deliverable files exist and are minimally well-formed
    # ----------------------------------------------------------------------- #
    def test_module_file_exists(self):
        """L1: bookingForm.ts exists and is non-trivially sized."""
        path = os.path.join(MODULE_DIR, "bookingForm.ts")
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 100, "bookingForm.ts is suspiciously small"

    def test_barrel_index_exists(self):
        """L1: index.ts barrel exists and re-exports from the module file."""
        path = os.path.join(MODULE_DIR, "index.ts")
        assert os.path.isfile(path), f"missing barrel: {path}"
        with open(path) as fh:
            text = fh.read()
        assert "bookingForm" in text, (
            "index.ts does not re-export the bookingForm module"
        )

    def test_agent_test_suite_exists(self):
        """L1: the agent authored a test suite with at least 10 test cases."""
        path = os.path.join(MODULE_DIR, "bookingForm.test.ts")
        assert os.path.isfile(path), f"missing test file: {path}"
        with open(path) as fh:
            text = fh.read()
        # Count `test(`/`it(` occurrences as a coarse lower bound.
        n = text.count("test(") + text.count("it(")
        assert n >= 10, f"expected >= 10 test cases in suite, found ~{n}"

    # ----------------------------------------------------------------------- #
    # L2 - dynamic execution against the real exported function
    # ----------------------------------------------------------------------- #
    def test_valid_payload_success(self):
        """L2: the spec's valid nested payload -> ok:true, data echoed, no fieldErrors."""
        _write_driver(
            "valid.test.ts",
            """
            const r = validateBooking(VALID) as any;
            expect(r.ok).toBe(true);
            expect(r.data).toBeTruthy();
            expect(r.data.guest.name).toBe('Ada');
            expect(r.data.guest.email).toBe('ada@host.io');
            expect(r.data.nights).toBe(3);
            expect(r.data.roomType).toBe('deluxe');
            expect(r.data.checkIn).toBe('2025-06-01');
            expect('fieldErrors' in r).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("valid.test.ts"), "valid")

    def test_name_trim_and_email_lowercase(self):
        """L2: guest.name is trimmed and guest.email is lower-cased in the output data."""
        _write_driver(
            "normalize.test.ts",
            """
            const r = validateBooking({
              guest: { name: '  Ada Byron  ', email: 'ADA@HOST.IO' },
              nights: 5,
              roomType: 'suite',
              checkIn: '2025-12-31',
            }) as any;
            expect(r.ok).toBe(true);
            expect(r.data.guest.name).toBe('Ada Byron');
            expect(r.data.guest.email).toBe('ada@host.io');
            // a name that is only valid AFTER trimming (length 2..60) must pass
            const r2 = validateBooking({
              guest: { name: ' Bo ', email: 'bo@host.io' },
              nights: 1, roomType: 'standard', checkIn: '2025-06-01',
            }) as any;
            expect(r2.ok).toBe(true);
            expect(r2.data.guest.name).toBe('Bo');
            """,
        )
        _assert_vitest_pass(_run_vitest("normalize.test.ts"), "normalize")

    def test_unknown_keys_stripped_top_and_nested(self):
        """L2: unknown keys at top level AND inside guest are stripped from data."""
        _write_driver(
            "strip.test.ts",
            """
            const r = validateBooking({
              guest: { name: 'Ada', email: 'ada@host.io', isAdmin: true, role: 'x' },
              nights: 3,
              roomType: 'deluxe',
              checkIn: '2025-06-01',
              evil: 'x',
              extra: 42,
            }) as any;
            expect(r.ok).toBe(true);
            const top = Object.keys(r.data).sort();
            expect(top).toEqual(['checkIn','guest','nights','roomType'].sort());
            expect('evil' in r.data).toBe(false);
            expect('extra' in r.data).toBe(false);
            const guestKeys = Object.keys(r.data.guest).sort();
            expect(guestKeys).toEqual(['email','name'].sort());
            expect('isAdmin' in r.data.guest).toBe(false);
            expect('role' in r.data.guest).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("strip.test.ts"), "strip")

    def test_nested_email_uses_dotted_path_key(self):
        """L2: a sole bad guest.email -> fieldErrors keyed exactly by 'guest.email'."""
        _write_driver(
            "dotted.test.ts",
            """
            const r = validateBooking({
              guest: { name: 'Ada', email: 'BAD' },
              nights: 3,
              roomType: 'suite',
              checkIn: '2025-06-01',
            }) as any;
            expect(r.ok).toBe(false);
            expect(r.fieldErrors).toBeTruthy();
            // The dotted nested path must be the key -- not 'email', not 'guest'.
            expect('guest.email' in r.fieldErrors).toBe(true);
            expect('email' in r.fieldErrors).toBe(false);
            expect('guest' in r.fieldErrors).toBe(false);
            const keys = Object.keys(r.fieldErrors);
            expect(keys).toEqual(['guest.email']);
            expect(Array.isArray(r.fieldErrors['guest.email'])).toBe(true);
            expect(r.fieldErrors['guest.email'].length).toBeGreaterThan(0);
            for (const m of r.fieldErrors['guest.email']) expect(typeof m).toBe('string');
            """,
        )
        _assert_vitest_pass(_run_vitest("dotted.test.ts"), "dotted")

    def test_multi_error_exact_key_set(self):
        """L2: the spec multi-error payload -> exactly the 5 expected dotted keys."""
        _write_driver(
            "multi.test.ts",
            """
            const r = validateBooking({
              guest: { name: 'A', email: 'x' },
              nights: 0,
              roomType: 'loft',
              checkIn: '06/01/2025',
            }) as any;
            expect(r.ok).toBe(false);
            expect(r.fieldErrors).toBeTruthy();
            const keys = Object.keys(r.fieldErrors).sort();
            expect(keys).toEqual(
              ['guest.name','guest.email','nights','roomType','checkIn'].sort()
            );
            // each value must be a non-empty array of strings
            for (const k of keys) {
              expect(Array.isArray(r.fieldErrors[k])).toBe(true);
              expect(r.fieldErrors[k].length).toBeGreaterThan(0);
              for (const m of r.fieldErrors[k]) expect(typeof m).toBe('string');
            }
            """,
        )
        _assert_vitest_pass(_run_vitest("multi.test.ts"), "multi")

    def test_nights_single_field_and_bounds(self):
        """L2: nights range (1..30) and integer rule, single-field error, boundaries accepted."""
        _write_driver(
            "nights.test.ts",
            """
            // out of range high -> only 'nights' flagged
            const high = validateBooking({ ...VALID, nights: 40 }) as any;
            expect(high.ok).toBe(false);
            expect(Object.keys(high.fieldErrors)).toEqual(['nights']);

            // out of range low (0) -> failure under 'nights'
            const low0 = validateBooking({ ...VALID, nights: 0 }) as any;
            expect(low0.ok).toBe(false);
            expect('nights' in low0.fieldErrors).toBe(true);

            // non-integer -> failure under 'nights'
            const frac = validateBooking({ ...VALID, nights: 2.5 }) as any;
            expect(frac.ok).toBe(false);
            expect('nights' in frac.fieldErrors).toBe(true);

            // wrong type -> failure under 'nights'
            const str = validateBooking({ ...VALID, nights: '3' }) as any;
            expect(str.ok).toBe(false);
            expect('nights' in str.fieldErrors).toBe(true);

            // inclusive boundaries 1 and 30 are accepted
            const b1 = validateBooking({ ...VALID, nights: 1 }) as any;
            expect(b1.ok).toBe(true);
            expect(b1.data.nights).toBe(1);
            const b30 = validateBooking({ ...VALID, nights: 30 }) as any;
            expect(b30.ok).toBe(true);
            expect(b30.data.nights).toBe(30);
            """,
        )
        _assert_vitest_pass(_run_vitest("nights.test.ts"), "nights")

    def test_roomtype_picklist(self):
        """L2: roomType accepts only the three allowed values; others fail under 'roomType'."""
        _write_driver(
            "roomtype.test.ts",
            """
            const bad = validateBooking({ ...VALID, roomType: 'loft' }) as any;
            expect(bad.ok).toBe(false);
            expect('roomType' in bad.fieldErrors).toBe(true);
            // only roomType should be flagged (everything else valid)
            expect(Object.keys(bad.fieldErrors)).toEqual(['roomType']);

            for (const roomType of ['standard','deluxe','suite']) {
              const r = validateBooking({ ...VALID, roomType }) as any;
              expect(r.ok).toBe(true);
              expect(r.data.roomType).toBe(roomType);
            }
            """,
        )
        _assert_vitest_pass(_run_vitest("roomtype.test.ts"), "roomtype")

    def test_checkin_iso_date_format(self):
        """L2: checkIn must be ISO YYYY-MM-DD; malformed dates fail under 'checkIn'."""
        _write_driver(
            "checkin.test.ts",
            """
            for (const bad of ['06/01/2025', '2025-6-1', '2025/06/01', 'June 1', '20250601']) {
              const r = validateBooking({ ...VALID, checkIn: bad }) as any;
              expect(r.ok).toBe(false);
              expect('checkIn' in r.fieldErrors).toBe(true);
            }
            const good = validateBooking({ ...VALID, checkIn: '2025-06-01' }) as any;
            expect(good.ok).toBe(true);
            expect(good.data.checkIn).toBe('2025-06-01');
            """,
        )
        _assert_vitest_pass(_run_vitest("checkin.test.ts"), "checkin")

    def test_guest_name_length_bounds(self):
        """L2: guest.name length 2..60 (after trim) enforced, keyed by 'guest.name'."""
        _write_driver(
            "name.test.ts",
            """
            // too short after trim
            const short = validateBooking({
              ...VALID, guest: { name: 'A', email: 'ada@host.io' },
            }) as any;
            expect(short.ok).toBe(false);
            expect('guest.name' in short.fieldErrors).toBe(true);
            expect(Object.keys(short.fieldErrors)).toEqual(['guest.name']);

            // too short because only-whitespace trims to empty
            const blank = validateBooking({
              ...VALID, guest: { name: '   ', email: 'ada@host.io' },
            }) as any;
            expect(blank.ok).toBe(false);
            expect('guest.name' in blank.fieldErrors).toBe(true);

            // too long (> 60 after trim)
            const long = validateBooking({
              ...VALID, guest: { name: 'a'.repeat(61), email: 'ada@host.io' },
            }) as any;
            expect(long.ok).toBe(false);
            expect('guest.name' in long.fieldErrors).toBe(true);

            // exactly 2 chars accepted
            const ok2 = validateBooking({
              ...VALID, guest: { name: 'Bo', email: 'bo@host.io' },
            }) as any;
            expect(ok2.ok).toBe(true);
            expect(ok2.data.guest.name).toBe('Bo');
            """,
        )
        _assert_vitest_pass(_run_vitest("name.test.ts"), "name")

    def test_non_object_inputs_never_throw(self):
        """L2: null, 42, "x", undefined, [], true -> failure with non-empty fieldErrors, no throw."""
        _write_driver(
            "nonobject.test.ts",
            """
            for (const input of [null, 42, 'x', undefined, [], true]) {
              let r: any;
              expect(() => { r = validateBooking(input as unknown); }).not.toThrow();
              expect(r.ok).toBe(false);
              expect(r.fieldErrors).toBeTruthy();
              expect(typeof r.fieldErrors).toBe('object');
              expect(Object.keys(r.fieldErrors).length).toBeGreaterThan(0);
            }
            // an empty object is missing required fields -> failure with >=1 key
            const empty = validateBooking({}) as any;
            expect(empty.ok).toBe(false);
            expect(Object.keys(empty.fieldErrors).length).toBeGreaterThan(0);
            """,
        )
        _assert_vitest_pass(_run_vitest("nonobject.test.ts"), "nonobject")

    def test_valid_fields_omitted_from_errors(self):
        """L2: only-bad nights -> fieldErrors omits every other (valid) field."""
        _write_driver(
            "omit.test.ts",
            """
            const r = validateBooking({
              guest: { name: 'Ada', email: 'ada@host.io' },
              nights: 40,
              roomType: 'suite',
              checkIn: '2025-06-01',
            }) as any;
            expect(r.ok).toBe(false);
            const keys = Object.keys(r.fieldErrors);
            expect(keys).toEqual(['nights']);
            expect('guest.name' in r.fieldErrors).toBe(false);
            expect('guest.email' in r.fieldErrors).toBe(false);
            expect('roomType' in r.fieldErrors).toBe(false);
            expect('checkIn' in r.fieldErrors).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("omit.test.ts"), "omit")

    def test_agent_own_suite_passes(self):
        """L2: the agent's authored suite passes under the native acceptance command."""
        proc = subprocess.run(
            [NPX, "vitest", "run", "--no-coverage", "src/bookingForm/bookingForm.test.ts"],
            cwd=LIB_DIR,
            capture_output=True,
            text=True,
            timeout=VITEST_TIMEOUT,
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "agent's own bookingForm.test.ts suite did not pass.\n"
            f"{combined[-4000:]}"
        )
