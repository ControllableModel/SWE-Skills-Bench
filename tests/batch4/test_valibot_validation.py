"""
Benchmark test for the `valibot-validation` skill (variant ext4).

Skill task (ext4): implement a self-contained *webhook event* validation
module (`library/src/webhookEvent/`) built on Valibot's own public API. The
module exports `parseEvent(input: unknown)` plus the underlying schema. Every
event is an object whose discriminating `type` field selects which other
fields are required (a discriminated/variant union):

  * "user.created"      -> userId (non-empty string) + email (valid email)
  * "user.deleted"      -> userId (non-empty string)
  * "payment.succeeded" -> amount (integer > 0, cents) + currency in {usd,eur,gbp}
  * "payment.failed"    -> amount (integer > 0) + reason (non-empty string)

`parseEvent` returns a discriminated result and must NEVER throw:
  * success -> { ok: true,  event:  <validated event, extra keys stripped> }
  * failure -> { ok: false, issues: <non-empty array of issue objects>      }

What this test verifies:
  * L1 - the deliverable files exist and are minimally well-formed (the module,
    its barrel re-export, and an authored test suite with >= 10 cases).
  * L2 - DYNAMIC EXECUTION: we drop our OWN vitest driver into the repo that
    imports the agent's `parseEvent` from `library/src/webhookEvent/index.ts`
    and exercises every variant's success path, payload violations, the
    integer-and-positive `amount` constraint, the currency picklist, the email
    rule, unknown-`type` rejection, unknown-key stripping and non-object input
    handling, deep-validating the returned `event` / `issues` structures. The
    agent's own test file is NOT trusted for behavior; we exercise the real
    exported function instead. (We additionally run the agent's own suite once.)

Native acceptance command (driven from library/):
    npx vitest run src/webhookEvent/webhookEvent.test.ts

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
MODULE_DIR = os.path.join(SRC_DIR, "webhookEvent")
# Temp dir for our own driver vitest files (kept inside src so vite resolves it).
DRIVER_DIR = os.path.join(SRC_DIR, "__benchmark_webhook__")

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
    imports `parseEvent` from the agent's barrel file via a relative path.
    """
    path = os.path.join(DRIVER_DIR, test_filename)
    content = textwrap.dedent(
        """
        import {{ describe, expect, test }} from 'vitest';
        import {{ parseEvent }} from '../webhookEvent/index.ts';

        describe('webhookEvent benchmark driver', () => {{
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
        """L1: webhookEvent.ts exists and is non-trivially sized."""
        path = os.path.join(MODULE_DIR, "webhookEvent.ts")
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 100, "webhookEvent.ts is suspiciously small"

    def test_barrel_index_exists(self):
        """L1: index.ts barrel exists and re-exports from the module file."""
        path = os.path.join(MODULE_DIR, "index.ts")
        assert os.path.isfile(path), f"missing barrel: {path}"
        with open(path) as fh:
            text = fh.read()
        assert "webhookEvent" in text, (
            "index.ts does not re-export the webhookEvent module"
        )

    def test_agent_test_suite_exists(self):
        """L1: the agent authored a test suite with at least 10 test cases."""
        path = os.path.join(MODULE_DIR, "webhookEvent.test.ts")
        assert os.path.isfile(path), f"missing test file: {path}"
        with open(path) as fh:
            text = fh.read()
        # Count `test(`/`it(` occurrences as a coarse lower bound.
        n = text.count("test(") + text.count("it(")
        assert n >= 10, f"expected >= 10 test cases in suite, found ~{n}"

    # ----------------------------------------------------------------------- #
    # L2 - dynamic execution against the real exported function
    # ----------------------------------------------------------------------- #
    def test_user_created_success(self):
        """L2: a valid user.created event -> ok:true with the validated event."""
        _write_driver(
            "user_created_ok.test.ts",
            """
            const r = parseEvent({
              type: 'user.created', userId: 'u1', email: 'a@b.io',
            }) as any;
            expect(r.ok).toBe(true);
            expect(r.event.type).toBe('user.created');
            expect(r.event.userId).toBe('u1');
            expect(r.event.email).toBe('a@b.io');
            expect('issues' in r).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("user_created_ok.test.ts"), "user_created_ok")

    def test_all_four_variants_succeed(self):
        """L2: each of the four event types has a working success path with correct values."""
        _write_driver(
            "all_variants.test.ts",
            """
            const created = parseEvent({
              type: 'user.created', userId: 'u1', email: 'x@y.io',
            }) as any;
            expect(created.ok).toBe(true);
            expect(created.event.type).toBe('user.created');

            const deleted = parseEvent({ type: 'user.deleted', userId: 'u9' }) as any;
            expect(deleted.ok).toBe(true);
            expect(deleted.event.type).toBe('user.deleted');
            expect(deleted.event.userId).toBe('u9');

            const succeeded = parseEvent({
              type: 'payment.succeeded', amount: 500, currency: 'usd',
            }) as any;
            expect(succeeded.ok).toBe(true);
            expect(succeeded.event.type).toBe('payment.succeeded');
            expect(succeeded.event.amount).toBe(500);
            expect(succeeded.event.currency).toBe('usd');

            const failed = parseEvent({
              type: 'payment.failed', amount: 100, reason: 'card_declined',
            }) as any;
            expect(failed.ok).toBe(true);
            expect(failed.event.type).toBe('payment.failed');
            expect(failed.event.amount).toBe(100);
            expect(failed.event.reason).toBe('card_declined');
            """,
        )
        _assert_vitest_pass(_run_vitest("all_variants.test.ts"), "all_variants")

    def test_missing_required_fields_rejected(self):
        """L2: an object missing its variant's required fields is rejected per type."""
        _write_driver(
            "missing_fields.test.ts",
            """
            // user.created missing email
            const noEmail = parseEvent({ type: 'user.created', userId: 'u1' }) as any;
            expect(noEmail.ok).toBe(false);
            expect(Array.isArray(noEmail.issues)).toBe(true);
            expect(noEmail.issues.length).toBeGreaterThan(0);

            // user.deleted missing userId
            const noUserId = parseEvent({ type: 'user.deleted' }) as any;
            expect(noUserId.ok).toBe(false);
            expect(noUserId.issues.length).toBeGreaterThan(0);

            // payment.succeeded missing currency
            const noCurrency = parseEvent({
              type: 'payment.succeeded', amount: 500,
            }) as any;
            expect(noCurrency.ok).toBe(false);
            expect(noCurrency.issues.length).toBeGreaterThan(0);

            // payment.failed missing reason
            const noReason = parseEvent({
              type: 'payment.failed', amount: 100,
            }) as any;
            expect(noReason.ok).toBe(false);
            expect(noReason.issues.length).toBeGreaterThan(0);
            """,
        )
        _assert_vitest_pass(_run_vitest("missing_fields.test.ts"), "missing_fields")

    def test_email_and_nonempty_string_rules(self):
        """L2: invalid email and empty userId are rejected; valid ones accepted."""
        _write_driver(
            "string_rules.test.ts",
            """
            const badEmail = parseEvent({
              type: 'user.created', userId: 'u1', email: 'not-an-email',
            }) as any;
            expect(badEmail.ok).toBe(false);
            expect(badEmail.issues.length).toBeGreaterThan(0);

            // empty userId must be rejected (non-empty string rule)
            const emptyId = parseEvent({
              type: 'user.created', userId: '', email: 'a@b.io',
            }) as any;
            expect(emptyId.ok).toBe(false);

            const emptyDel = parseEvent({ type: 'user.deleted', userId: '' }) as any;
            expect(emptyDel.ok).toBe(false);

            // empty reason rejected
            const emptyReason = parseEvent({
              type: 'payment.failed', amount: 100, reason: '',
            }) as any;
            expect(emptyReason.ok).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("string_rules.test.ts"), "string_rules")

    def test_amount_integer_and_positive_constraint(self):
        """L2: amount must be an integer strictly > 0 (cents) across both payment variants."""
        _write_driver(
            "amount.test.ts",
            """
            // fractional amount rejected
            const frac = parseEvent({
              type: 'payment.succeeded', amount: 5.5, currency: 'usd',
            }) as any;
            expect(frac.ok).toBe(false);
            expect(frac.issues.length).toBeGreaterThan(0);

            // zero rejected
            const zero = parseEvent({
              type: 'payment.succeeded', amount: 0, currency: 'usd',
            }) as any;
            expect(zero.ok).toBe(false);

            // negative rejected
            const neg = parseEvent({
              type: 'payment.succeeded', amount: -10, currency: 'usd',
            }) as any;
            expect(neg.ok).toBe(false);

            // fractional on payment.failed too
            const fracFailed = parseEvent({
              type: 'payment.failed', amount: 1.25, reason: 'x',
            }) as any;
            expect(fracFailed.ok).toBe(false);

            // smallest valid integer amount accepted
            const one = parseEvent({
              type: 'payment.succeeded', amount: 1, currency: 'eur',
            }) as any;
            expect(one.ok).toBe(true);
            expect(one.event.amount).toBe(1);
            """,
        )
        _assert_vitest_pass(_run_vitest("amount.test.ts"), "amount")

    def test_currency_picklist(self):
        """L2: currency must be one of usd/eur/gbp; anything else rejected."""
        _write_driver(
            "currency.test.ts",
            """
            // each allowed currency accepted
            for (const currency of ['usd', 'eur', 'gbp']) {
              const r = parseEvent({
                type: 'payment.succeeded', amount: 500, currency,
              }) as any;
              expect(r.ok).toBe(true);
              expect(r.event.currency).toBe(currency);
            }

            // disallowed currency rejected
            const yen = parseEvent({
              type: 'payment.succeeded', amount: 500, currency: 'yen',
            }) as any;
            expect(yen.ok).toBe(false);
            expect(yen.issues.length).toBeGreaterThan(0);

            // wrong-case currency rejected (picklist is exact)
            const upper = parseEvent({
              type: 'payment.succeeded', amount: 500, currency: 'USD',
            }) as any;
            expect(upper.ok).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("currency.test.ts"), "currency")

    def test_unknown_type_rejected(self):
        """L2: an event whose `type` is not one of the four known types is rejected."""
        _write_driver(
            "unknown_type.test.ts",
            """
            const sub = parseEvent({ type: 'subscription.renewed', userId: 'u1' }) as any;
            expect(sub.ok).toBe(false);
            expect(Array.isArray(sub.issues)).toBe(true);
            expect(sub.issues.length).toBeGreaterThan(0);

            // also reject when type is missing entirely
            const noType = parseEvent({ userId: 'u1', email: 'a@b.io' }) as any;
            expect(noType.ok).toBe(false);

            // a plausible-but-wrong type string is rejected
            const typo = parseEvent({
              type: 'user.create', userId: 'u1', email: 'a@b.io',
            }) as any;
            expect(typo.ok).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("unknown_type.test.ts"), "unknown_type")

    def test_unknown_keys_stripped(self):
        """L2: validated event contains exactly its variant's fields; extras stripped."""
        _write_driver(
            "strip.test.ts",
            """
            const r = parseEvent({
              type: 'user.created', userId: 'u1', email: 'a@b.io',
              extra: 1, isAdmin: true, nested: { a: 1 },
            }) as any;
            expect(r.ok).toBe(true);
            expect('extra' in r.event).toBe(false);
            expect('isAdmin' in r.event).toBe(false);
            expect('nested' in r.event).toBe(false);
            const keys = Object.keys(r.event).sort();
            expect(keys).toEqual(['email', 'type', 'userId'].sort());

            // payment.succeeded strips extras too
            const p = parseEvent({
              type: 'payment.succeeded', amount: 500, currency: 'usd', note: 'x',
            }) as any;
            expect(p.ok).toBe(true);
            expect('note' in p.event).toBe(false);
            expect(Object.keys(p.event).sort()).toEqual(
              ['amount', 'currency', 'type'].sort()
            );
            """,
        )
        _assert_vitest_pass(_run_vitest("strip.test.ts"), "strip")

    def test_non_object_inputs_never_throw(self):
        """L2: null, 42, "x", undefined, [], {} -> failure with non-empty issues, no throw."""
        _write_driver(
            "nonobject.test.ts",
            """
            for (const input of [null, 42, 'x', undefined, [], true]) {
              let r: any;
              expect(() => { r = parseEvent(input as unknown); }).not.toThrow();
              expect(r.ok).toBe(false);
              expect(Array.isArray(r.issues)).toBe(true);
              expect(r.issues.length).toBeGreaterThan(0);
              expect('event' in r).toBe(false);
            }

            // an empty object has no valid discriminator -> failure
            const empty = parseEvent({}) as any;
            expect(empty.ok).toBe(false);
            expect(empty.issues.length).toBeGreaterThan(0);
            """,
        )
        _assert_vitest_pass(_run_vitest("nonobject.test.ts"), "nonobject")

    def test_wrong_field_types_rejected(self):
        """L2: correct type but wrong field value-types are rejected (discriminative)."""
        _write_driver(
            "wrong_types.test.ts",
            """
            // userId as a number, not a string
            const numId = parseEvent({
              type: 'user.deleted', userId: 123,
            }) as any;
            expect(numId.ok).toBe(false);

            // amount as a string, not a number
            const strAmount = parseEvent({
              type: 'payment.succeeded', amount: '500', currency: 'usd',
            }) as any;
            expect(strAmount.ok).toBe(false);

            // email as a number
            const numEmail = parseEvent({
              type: 'user.created', userId: 'u1', email: 42,
            }) as any;
            expect(numEmail.ok).toBe(false);

            // a valid baseline still passes (guards against an always-fail stub)
            const ok = parseEvent({ type: 'user.deleted', userId: 'u9' }) as any;
            expect(ok.ok).toBe(true);
            """,
        )
        _assert_vitest_pass(_run_vitest("wrong_types.test.ts"), "wrong_types")

    def test_agent_own_suite_passes(self):
        """L2: the agent's authored suite passes under the native command."""
        proc = subprocess.run(
            [
                NPX,
                "vitest",
                "run",
                "--no-coverage",
                "src/webhookEvent/webhookEvent.test.ts",
            ],
            cwd=LIB_DIR,
            capture_output=True,
            text=True,
            timeout=VITEST_TIMEOUT,
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "agent's own webhookEvent.test.ts suite did not pass.\n"
            f"{combined[-4000:]}"
        )
