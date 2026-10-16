"""Tests for the `zod-schema-validation` skill (variant ext5).

Skill task: build a reusable Recurring-Event Rule Validator in
`packages/lib/recurringRuleSchema.ts` of the cal.com monorepo. The deliverable
exports `parseRecurringRule(input: unknown)` (a never-throwing tagged-result
validator) and a schema-derived `RecurringRule` type.

Variant task summary (re-derived from tasks/ext5/zod-schema-validation.md)
--------------------------------------------------------------------------
A recurrence rule arrives from a settings form where `interval` and `count`
are strings. `parseRecurringRule` validates + normalizes it:

  - `freq`: required; one of DAILY/WEEKLY/MONTHLY; lowercase input is
    uppercased in the output.
  - `interval`: string -> integer 1..12 inclusive, emitted as a number.
  - `count`: string -> integer 1..24 inclusive, emitted as a number.
  - `byWeekday`: optional array of MO/TU/WE/TH/FR/SA/SU; duplicates collapsed
    (first-seen order preserved); omitted when absent.
  - cross-field: `interval * count` must not exceed 365 -> error reported on
    the `count` field.
  - `byWeekday` only meaningful when `freq === "WEEKLY"`; present-but-not-weekly
    -> error on `byWeekday`.
  - unknown top-level keys rejected under their own key name.
  - all violations collected together; never throws on non-object input.

What these tests verify
-----------------------
L1 (existence / minimal well-formedness): the two deliverable files exist, the
schema module references zod, exports the public function, and derives the type
from the schema (z.infer / z.output) rather than a hand-written interface.

L2 (dynamic execution): rather than trusting the agent's own test file, we
write an INDEPENDENT vitest spec into the repo that imports the agent's module
and exercises `parseRecurringRule` end-to-end (uppercasing, numeric coercion,
byWeekday dedupe + omission, the interval*count > 365 span violation on
`count`, byWeekday-without-WEEKLY, unknown-key rejection, multi-error
collection, non-object inputs). We run it with the repo's native vitest. A
naive / hardcoded / keyword-only solution fails these. We also run the agent's
own committed test file via the acceptance command.

Native command (Acceptance Criteria):
    yarn vitest run packages/lib/recurringRuleSchema.test.ts
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
SCHEMA_TS = os.path.join(LIB_DIR, "recurringRuleSchema.ts")
SCHEMA_TEST_TS = os.path.join(LIB_DIR, "recurringRuleSchema.test.ts")

# Independent spec we drop into the package so vitest's default `**/*.spec.ts`
# include glob picks it up under the @calcom/lib project.
VERIFY_SPEC = os.path.join(LIB_DIR, "recurringRuleSchema.verify.spec.ts")


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
        import { parseRecurringRule } from "./recurringRuleSchema";
        """
    )
    with open(VERIFY_SPEC, "w", encoding="utf-8") as fh:
        fh.write(header + "\n" + body)


@pytest.fixture(scope="module", autouse=True)
def _deps():
    """Ensure node deps are present (container usually pre-installs them)."""
    if not os.path.isdir(REPO_DIR):
        pytest.skip(f"REPO_DIR missing: {REPO_DIR}")
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
        """L1: module imports zod and exports parseRecurringRule + the type name."""
        src = _read(SCHEMA_TS)
        assert 'from "zod"' in src or "from 'zod'" in src, "module must use zod"
        assert "parseRecurringRule" in src, "must define parseRecurringRule"
        assert "RecurringRule" in src, "must export RecurringRule type"

    def test_type_is_schema_derived(self):
        """L1: RecurringRule must be inferred from the schema (z.infer / z.output),
        not a hand-written interface/type literal duplicating the fields."""
        src = _read(SCHEMA_TS)
        assert "z.infer" in src or "z.output" in src, (
            "RecurringRule must be derived via z.infer<typeof ...> / z.output"
        )
        assert "interface RecurringRule" not in src, (
            "RecurringRule must not be a hand-written interface"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real behavior (independent spec)
    # ------------------------------------------------------------------ #
    def test_valid_rule_normalized(self):
        """L2: a fully valid lowercase weekly rule returns success with freq
        uppercased, interval/count as numbers, and byWeekday deduplicated in
        first-seen order."""
        body = textwrap.dedent(
            """\
            describe("valid rule normalization", () => {
              it("uppercases freq, coerces numbers, dedupes byWeekday", () => {
                const r = parseRecurringRule({
                  freq: "weekly",
                  interval: "1",
                  count: "5",
                  byWeekday: ["MO", "MO", "WE"],
                });
                expect(r.success).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(d.freq).toBe("WEEKLY");
                expect(d.interval).toBe(1);
                expect(typeof d.interval).toBe("number");
                expect(d.count).toBe(5);
                expect(typeof d.count).toBe("number");
                expect(d.byWeekday).toEqual(["MO", "WE"]);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "valid rule normalization spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_byweekday_omitted_when_absent(self):
        """L2: when byWeekday is absent the normalized output must OMIT the key
        entirely (a naive impl that defaults it to [] or null fails)."""
        body = textwrap.dedent(
            """\
            describe("byWeekday omission", () => {
              it("omits byWeekday when absent", () => {
                const r = parseRecurringRule({
                  freq: "DAILY",
                  interval: "2",
                  count: "3",
                });
                expect(r.success).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect("byWeekday" in d).toBe(false);
                expect(d.freq).toBe("DAILY");
                expect(d.interval).toBe(2);
                expect(d.count).toBe(3);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "byWeekday omission spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_span_violation_reported_on_count(self):
        """L2: interval*count > 365 fails, with the error reported on the
        `count` field. interval "30" * count "20" = 600 > 365."""
        body = textwrap.dedent(
            """\
            describe("span violation", () => {
              it("reports interval*count>365 on count", () => {
                const r = parseRecurringRule({
                  freq: "DAILY",
                  interval: "30",
                  count: "20",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(
                  keys.includes("count"),
                  "expected a count error; keys=" + JSON.stringify(keys)
                ).toBe(true);
                expect(Array.isArray(r.errors["count"])).toBe(true);
                expect((r.errors["count"] as string[]).length).toBeGreaterThan(0);
              });
              it("accepts a product exactly at the boundary 365", () => {
                // interval 5 * count 24 = 120 <= 365 (both within their own ranges)
                const ok = parseRecurringRule({
                  freq: "WEEKLY",
                  interval: "5",
                  count: "24",
                });
                expect(ok.success, JSON.stringify((ok as any).errors)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "span violation spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_byweekday_requires_weekly(self):
        """L2: byWeekday present while freq is not WEEKLY is rejected with the
        error reported on the `byWeekday` field; the same shape with WEEKLY
        passes."""
        body = textwrap.dedent(
            """\
            describe("byWeekday requires WEEKLY", () => {
              it("rejects byWeekday on a DAILY rule, error on byWeekday", () => {
                const r = parseRecurringRule({
                  freq: "DAILY",
                  interval: "1",
                  count: "5",
                  byWeekday: ["MO"],
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(
                  keys.some((k) => k.includes("byWeekday")),
                  "expected byWeekday error; keys=" + JSON.stringify(keys)
                ).toBe(true);
              });
              it("accepts byWeekday on a WEEKLY rule", () => {
                const r = parseRecurringRule({
                  freq: "WEEKLY",
                  interval: "1",
                  count: "5",
                  byWeekday: ["MO"],
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "byWeekday-requires-WEEKLY spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_invalid_freq_rejected(self):
        """L2: an out-of-set freq ("yearly") is rejected with an error on the
        `freq` field."""
        body = textwrap.dedent(
            """\
            describe("invalid freq", () => {
              it("rejects yearly with a freq error", () => {
                const r = parseRecurringRule({
                  freq: "yearly",
                  interval: "1",
                  count: "5",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(
                  keys.some((k) => k.includes("freq")),
                  "expected freq error; keys=" + JSON.stringify(keys)
                ).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "invalid freq spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_interval_and_count_bounds(self):
        """L2: interval must be an integer 1..12 and count an integer 1..24;
        out-of-range and non-integer string values fail, inclusive bounds pass."""
        body = textwrap.dedent(
            """\
            describe("numeric bounds", () => {
              it("rejects interval above 12", () => {
                const r = parseRecurringRule({ freq: "DAILY", interval: "13", count: "2" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("interval"))).toBe(true);
              });
              it("rejects interval below 1", () => {
                const r = parseRecurringRule({ freq: "DAILY", interval: "0", count: "2" });
                expect(r.success).toBe(false);
              });
              it("rejects count above 24", () => {
                const r = parseRecurringRule({ freq: "DAILY", interval: "1", count: "25" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("count"))).toBe(true);
              });
              it("rejects a non-integer interval string", () => {
                const r = parseRecurringRule({ freq: "DAILY", interval: "2.5", count: "2" });
                expect(r.success).toBe(false);
              });
              it("rejects a non-numeric interval string", () => {
                const r = parseRecurringRule({ freq: "DAILY", interval: "abc", count: "2" });
                expect(r.success).toBe(false);
              });
              it("accepts inclusive bounds interval 12 / count 24", () => {
                // product 12*24=288 <= 365 so the span rule does not interfere
                const r = parseRecurringRule({ freq: "MONTHLY", interval: "12", count: "24" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect((r.data as any).interval).toBe(12);
                expect((r.data as any).count).toBe(24);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "numeric bounds spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_invalid_byweekday_value_rejected(self):
        """L2: a byWeekday entry outside MO..SU on a WEEKLY rule is rejected
        with a byWeekday-scoped error (so the enum is really enforced)."""
        body = textwrap.dedent(
            """\
            describe("byWeekday value enum", () => {
              it("rejects an unknown weekday token", () => {
                const r = parseRecurringRule({
                  freq: "WEEKLY",
                  interval: "1",
                  count: "3",
                  byWeekday: ["MO", "XX"],
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(
                  Object.keys(r.errors).some((k) => k.includes("byWeekday")),
                  "keys=" + JSON.stringify(Object.keys(r.errors))
                ).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "byWeekday enum spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_unknown_top_level_key_rejected(self):
        """L2: an extra top-level key `foo` is rejected (strict), with `foo`
        present in errors rather than silently dropped."""
        body = textwrap.dedent(
            """\
            describe("unknown top-level key", () => {
              it("rejects extra keys under their own key name", () => {
                const r = parseRecurringRule({
                  freq: "DAILY",
                  interval: "1",
                  count: "5",
                  foo: "surprise",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(
                  keys.some((k) => k === "foo" || k.includes("foo")),
                  "expected foo in errors; keys=" + JSON.stringify(keys)
                ).toBe(true);
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
        """L2: a payload with several simultaneous violations (bad freq,
        out-of-range interval, span overflow) returns ALL of them together,
        never stopping at the first error."""
        body = textwrap.dedent(
            """\
            describe("multi-error collection", () => {
              it("returns all violations together", () => {
                const r = parseRecurringRule({
                  freq: "yearly",      // invalid freq
                  interval: "20",      // > 12
                  count: "30",         // > 24 (and product overflows too)
                  bar: 1,              // unknown key
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k.includes("freq")), "freq missing; " + JSON.stringify(keys)).toBe(true);
                expect(keys.some((k) => k.includes("interval")), "interval missing; " + JSON.stringify(keys)).toBe(true);
                expect(keys.some((k) => k.includes("count")), "count missing; " + JSON.stringify(keys)).toBe(true);
                expect(keys.some((k) => k.includes("bar")), "bar missing; " + JSON.stringify(keys)).toBe(true);
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
        """L2: null, a string, a number, undefined and an array all return
        {success:false} with an object `errors`, never throwing."""
        body = textwrap.dedent(
            """\
            describe("non-object inputs", () => {
              it("never throws on null/string/number/undefined/array", () => {
                for (const bad of [null, "oops", 42, undefined, []]) {
                  let r: any;
                  expect(() => { r = parseRecurringRule(bad as unknown); }).not.toThrow();
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
        """L2 (acceptance): the agent's own committed vitest suite passes via
        the exact native command from the Acceptance Criteria."""
        assert os.path.isfile(SCHEMA_TEST_TS), "agent test file missing"
        res = _run_vitest("packages/lib/recurringRuleSchema.test.ts", timeout=600)
        assert res.returncode == 0, (
            "agent's own recurringRuleSchema.test.ts did not pass\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )
