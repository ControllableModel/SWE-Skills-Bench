"""Tests for the `zod-schema-validation` skill (variant ext4).

Skill task: build a reusable Paid Event-Type Price Validator in
`packages/lib/eventPriceSchema.ts` of the cal.com monorepo. The deliverable
exports `parseEventPrice(input: unknown)` — a never-throwing tagged-result
validator — and a schema-derived `EventPrice` type. The validator normalizes a
money configuration: an ISO-4217 currency restricted to a supported set
(uppercased in the output), a major-unit `amountMajor` string converted to an
integer `amountMinor` honoring zero-decimal currencies (JPY/KRW) vs two-decimal
currencies, plus defaulted `requirePayment` (true) and `paymentOption`
("ON_BOOKING"). Invalid input collects every violation under per-field keys.

What these tests verify
-----------------------
L1 (existence / minimal well-formedness): the two deliverable files exist, the
schema module references zod, exports the public function, and derives the
`EventPrice` type from the schema (z.infer / z.output) rather than a
hand-written interface.

L2 (dynamic execution): instead of trusting the agent's own test file, we write
an INDEPENDENT vitest spec into the repo that imports the agent's module and
exercises `parseEventPrice` end-to-end: currency uppercasing, the major->minor
conversion for both zero- and two-decimal currencies, default injection,
excess-precision rejection, sub-unit rounding-to-zero rejection, unsupported
currency rejection, unknown-key rejection, simultaneous multi-violation
collection, and non-object inputs never throwing. We run it with the repo's
native vitest. A naive / hardcoded / keyword-only solution fails these. We also
run the agent's own committed test file via the acceptance command.

Native command (Acceptance Criteria):
    yarn vitest run packages/lib/eventPriceSchema.test.ts
"""

import os
import subprocess
import textwrap

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies  # noqa: F401
except Exception:  # pragma: no cover
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/cal.com"
LIB_DIR = os.path.join(REPO_DIR, "packages", "lib")
SCHEMA_TS = os.path.join(LIB_DIR, "eventPriceSchema.ts")
SCHEMA_TEST_TS = os.path.join(LIB_DIR, "eventPriceSchema.test.ts")

# Independent spec we drop into the package next to the agent's module so a
# relative `./eventPriceSchema` import resolves and vitest's package include
# globs pick it up under the @calcom/lib project.
VERIFY_SPEC = os.path.join(LIB_DIR, "eventPriceSchema.verify.spec.ts")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _run_vitest(spec_relpath, timeout=600):
    """Run the repo's native vitest scoped to a single spec (relative to repo)."""
    cmd = [
        "yarn",
        "vitest",
        "run",
        spec_relpath,
        "--reporter=verbose",
        "--no-coverage",
    ]
    env = dict(os.environ)
    env["TZ"] = "UTC"
    env["CI"] = "true"
    return subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _write_spec(body):
    """Write an independent vitest spec that imports the agent's module."""
    header = textwrap.dedent(
        """\
        import { describe, expect, it } from "vitest";
        import { parseEventPrice } from "./eventPriceSchema";
        """
    )
    with open(VERIFY_SPEC, "w", encoding="utf-8") as fh:
        fh.write(header + "\n" + body)


@pytest.fixture(scope="module", autouse=True)
def _deps():
    """Ensure node deps are present (container usually pre-installs them)."""
    if not os.path.isdir(REPO_DIR):
        pytest.skip(f"REPO_DIR missing: {REPO_DIR}")
    # cal.com uses yarn; node_modules are normally baked into the image. The
    # util is a defensive no-op for yarn repos, so we never fail on it.
    if ensure_npm_dependencies is not None and os.path.isdir(
        os.path.join(REPO_DIR, "node_modules")
    ) is False:
        try:
            ensure_npm_dependencies(REPO_DIR)
        except Exception:
            pass
    yield
    # cleanup our injected spec
    try:
        if os.path.isfile(VERIFY_SPEC):
            os.remove(VERIFY_SPEC)
    except OSError:
        pass


def _run_independent(body, timeout=600):
    """Write `body` as a spec, run it, return CompletedProcess."""
    _write_spec(body)
    return _run_vitest(os.path.relpath(VERIFY_SPEC, REPO_DIR), timeout=timeout)


class TestZodSchemaValidation:
    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------ #
    # L1 — deliverables exist & are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_schema_module_exists(self):
        """L1: the validator module file is created."""
        assert os.path.isfile(SCHEMA_TS), f"missing deliverable: {SCHEMA_TS}"

    def test_schema_test_file_exists(self):
        """L1: the agent's own vitest suite file is created."""
        assert os.path.isfile(
            SCHEMA_TEST_TS
        ), f"missing test deliverable: {SCHEMA_TEST_TS}"

    def test_module_uses_zod_and_exports_api(self):
        """L1: module imports zod and exports parseEventPrice + EventPrice."""
        src = _read(SCHEMA_TS)
        assert 'from "zod"' in src or "from 'zod'" in src, "module must use zod"
        assert "parseEventPrice" in src, "must define parseEventPrice"
        assert "EventPrice" in src, "must export EventPrice type"

    def test_type_is_schema_derived(self):
        """L1: EventPrice must be inferred from the schema (z.infer / z.output),
        not a hand-written interface/type literal duplicating the fields."""
        src = _read(SCHEMA_TS)
        assert "z.infer" in src or "z.output" in src, (
            "EventPrice must be derived via z.infer<typeof ...> / z.output"
        )
        assert "interface EventPrice" not in src, (
            "EventPrice must not be a hand-written interface"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real behavior (independent spec)
    # ------------------------------------------------------------------ #
    def test_valid_two_decimal_normalized(self):
        """L2: a valid two-decimal price uppercases currency, converts to minor
        units (*100), and injects requirePayment/paymentOption defaults."""
        body = textwrap.dedent(
            """\
            describe("valid two-decimal price", () => {
              it("normalizes currency, minor units, and defaults", () => {
                const r = parseEventPrice({ currency: "usd", amountMajor: "19.99" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(d.currency).toBe("USD");
                expect(typeof d.amountMinor).toBe("number");
                expect(d.amountMinor).toBe(1999);
                expect(d.requirePayment).toBe(true);
                expect(d.paymentOption).toBe("ON_BOOKING");
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "valid two-decimal spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_zero_decimal_currency_minor_equals_amount(self):
        """L2: for a zero-decimal currency (JPY) amountMinor equals the whole
        integer amount (no *100), and currency stays uppercased."""
        body = textwrap.dedent(
            """\
            describe("zero-decimal currency", () => {
              it("keeps amountMinor as the integer amount", () => {
                const r = parseEventPrice({ currency: "JPY", amountMajor: "500" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(d.currency).toBe("JPY");
                expect(typeof d.amountMinor).toBe("number");
                expect(d.amountMinor).toBe(500);

                const krw = parseEventPrice({ currency: "krw", amountMajor: "1200" });
                expect(krw.success, JSON.stringify((krw as any).errors)).toBe(true);
                if (!krw.success) throw new Error("expected success");
                expect((krw.data as any).currency).toBe("KRW");
                expect((krw.data as any).amountMinor).toBe(1200);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "zero-decimal currency spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_defaults_overridable(self):
        """L2: provided requirePayment/paymentOption are honored (not blindly
        defaulted), proving the validator reads the inputs."""
        body = textwrap.dedent(
            """\
            describe("explicit optional fields", () => {
              it("carries provided requirePayment / paymentOption", () => {
                const r = parseEventPrice({
                  currency: "EUR",
                  amountMajor: "5.00",
                  requirePayment: false,
                  paymentOption: "HOLD",
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(d.currency).toBe("EUR");
                expect(d.amountMinor).toBe(500);
                expect(d.requirePayment).toBe(false);
                expect(d.paymentOption).toBe("HOLD");
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "explicit optional fields spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_unsupported_currency_rejected(self):
        """L2: a syntactically valid ISO code outside the supported set (CAD) is
        rejected with an error keyed under `currency`."""
        body = textwrap.dedent(
            """\
            describe("unsupported currency", () => {
              it("rejects CAD on the currency field", () => {
                const r = parseEventPrice({ currency: "CAD", amountMajor: "10" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                const hit = keys.find((k) => k === "currency" || k.includes("currency"));
                expect(hit, "expected currency error; keys=" + JSON.stringify(keys)).toBeTruthy();
                expect(Array.isArray(r.errors[hit as string])).toBe(true);
                expect((r.errors[hit as string] as string[]).length).toBeGreaterThan(0);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "unsupported currency spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_excess_precision_rejected(self):
        """L2: too many decimals for the currency are rejected on amountMajor —
        "1.999" for a two-decimal USD, and "100.5" for zero-decimal JPY."""
        body = textwrap.dedent(
            """\
            describe("excess precision", () => {
              it("rejects >2 decimals for USD", () => {
                const r = parseEventPrice({ currency: "USD", amountMajor: "1.999" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("amountMajor")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("rejects fractional amount for JPY", () => {
                const r = parseEventPrice({ currency: "JPY", amountMajor: "100.5" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("amountMajor")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("accepts exactly 2 decimals for USD", () => {
                const r = parseEventPrice({ currency: "USD", amountMajor: "1.99" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect((r.data as any).amountMinor).toBe(199);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "excess precision spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_subunit_rounding_to_zero_rejected(self):
        """L2: a positive but sub-smallest-unit amount that would round the
        minor value to zero (e.g. "0.004" USD) is rejected on amountMajor, while
        the boundary "0.01" (amountMinor === 1) is accepted."""
        body = textwrap.dedent(
            """\
            describe("rounds-to-zero", () => {
              it("rejects amounts whose minor value is < 1", () => {
                const r = parseEventPrice({ currency: "USD", amountMajor: "0.004" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("amountMajor")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("accepts the minimal 1-minor-unit amount", () => {
                const r = parseEventPrice({ currency: "USD", amountMajor: "0.01" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect((r.data as any).amountMinor).toBe(1);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "rounds-to-zero spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_non_positive_amount_rejected(self):
        """L2: a non-positive amount (zero / negative) is rejected on
        amountMajor; the validator must not silently accept it."""
        body = textwrap.dedent(
            """\
            describe("non-positive amount", () => {
              it("rejects zero and negative amounts", () => {
                for (const a of ["0", "-5", "-0.01"]) {
                  const r = parseEventPrice({ currency: "USD", amountMajor: a });
                  expect(r.success, "amount " + a + " should fail").toBe(false);
                  if (r.success) throw new Error("expected failure for " + a);
                  expect(Object.keys(r.errors).some((k) => k.includes("amountMajor")),
                    a + " keys=" + JSON.stringify(Object.keys(r.errors))).toBe(true);
                }
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "non-positive amount spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_unknown_top_level_key_rejected(self):
        """L2: an extra top-level key is rejected (strict schema) with the key
        name present in errors rather than silently dropped."""
        body = textwrap.dedent(
            """\
            describe("unknown top-level key", () => {
              it("rejects extra keys with the key name in errors", () => {
                const r = parseEventPrice({
                  currency: "USD",
                  amountMajor: "9.99",
                  surprise: "nope",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k === "surprise" || k.includes("surprise")),
                  "expected surprise in errors; keys=" + JSON.stringify(keys)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "unknown key spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_multiple_violations_collected_together(self):
        """L2: an unsupported currency AND an over-precise amount AND an unknown
        key in one payload yield a failure whose errors include all three
        (no stop-at-first-error)."""
        body = textwrap.dedent(
            """\
            describe("multi-error collection", () => {
              it("returns all violations together", () => {
                const r = parseEventPrice({
                  currency: "CAD",
                  amountMajor: "1.999",
                  bogus: 1,
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                const hasCurrency = keys.some((k) => k.includes("currency"));
                const hasAmount = keys.some((k) => k.includes("amountMajor"));
                const hasBogus = keys.some((k) => k.includes("bogus"));
                expect(hasCurrency, "missing currency; keys=" + JSON.stringify(keys)).toBe(true);
                expect(hasAmount, "missing amountMajor; keys=" + JSON.stringify(keys)).toBe(true);
                expect(hasBogus, "missing bogus; keys=" + JSON.stringify(keys)).toBe(true);
                for (const k of keys) {
                  expect(Array.isArray(r.errors[k])).toBe(true);
                  expect((r.errors[k] as string[]).length).toBeGreaterThan(0);
                }
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "multi-violation spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_nonobject_inputs_never_throw(self):
        """L2: null, a string, a number, undefined, and an array all return
        {success:false} without throwing."""
        body = textwrap.dedent(
            """\
            describe("non-object inputs", () => {
              it("never throws on null/string/number/array", () => {
                for (const bad of [null, "oops", 42, undefined, []]) {
                  let r: any;
                  expect(() => { r = parseEventPrice(bad as unknown); }).not.toThrow();
                  expect(r.success).toBe(false);
                  expect(typeof r.errors).toBe("object");
                  expect(r.errors).not.toBeNull();
                }
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "non-object input spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_agents_own_suite_passes(self):
        """L2 (acceptance): the agent's own committed vitest suite passes via the
        exact native command from the Acceptance Criteria."""
        assert os.path.isfile(SCHEMA_TEST_TS), "agent test file missing"
        res = _run_vitest("packages/lib/eventPriceSchema.test.ts", timeout=600)
        assert res.returncode == 0, (
            "agent's own eventPriceSchema.test.ts did not pass\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )
