"""Tests for the `zod-schema-validation` skill (variant ext9).

Skill task: build a reusable Workflow Reminder Step Validator in
`packages/lib/workflowStepSchema.ts` of the cal.com monorepo. The deliverable
exports `parseWorkflowStep(input: unknown)` — a never-throwing, tagged-result
validator over a discriminated union (`action: "EMAIL" | "SMS"`) — plus a
schema-derived `WorkflowStep` type.

What these tests verify
-----------------------
L1 (existence / minimal well-formedness): the two deliverable files exist, the
schema module exports `parseWorkflowStep`, exposes a `WorkflowStep` type that is
derived from a schema (`z.infer`/`z.output`) rather than a hand-written
interface, and references the discriminant `action`.

L2 (dynamic execution): rather than trusting the agent's own test file, we drop
an INDEPENDENT vitest spec into `packages/lib` that imports the agent's module
and exercises `parseWorkflowStep` end-to-end against THIS variant's rules:
  * EMAIL happy path: timing.value coerced string->number, sendTo defaults to
    "ATTENDEE", subject/body trimmed, action discriminant narrows.
  * 30-day cap reported on `timing.value`.
  * SMS 5-minute floor reported on `timing.value`.
  * invalid `action` discriminant ("PUSH") reported on `action`.
  * unknown keys rejected under their own key name.
  * all simultaneous violations collected together.
  * non-object inputs return failure without throwing.
A naive / hardcoded / stop-at-first-error / keyword-only solution fails these.
We also run the agent's own committed suite via the acceptance command.

Native command (Acceptance Criteria):
    yarn vitest run packages/lib/workflowStepSchema.test.ts
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
SCHEMA_TS = os.path.join(LIB_DIR, "workflowStepSchema.ts")
SCHEMA_TEST_TS = os.path.join(LIB_DIR, "workflowStepSchema.test.ts")

# Independent spec we drop into the package so vitest's `packages/**` include
# globs pick it up under the @calcom/lib project.
VERIFY_SPEC = os.path.join(LIB_DIR, "workflowStepSchema.verify.spec.ts")


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
        import { parseWorkflowStep } from "./workflowStepSchema";
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
    return _run_vitest(
        os.path.relpath(VERIFY_SPEC, REPO_DIR), timeout=timeout
    )


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

    def test_module_exports_api_and_discriminant(self):
        """L1: module exports parseWorkflowStep, a WorkflowStep type, and
        references the `action` discriminant (EMAIL/SMS union)."""
        src = _read(SCHEMA_TS)
        assert "parseWorkflowStep" in src, "must define parseWorkflowStep"
        assert "WorkflowStep" in src, "must export WorkflowStep type"
        assert "action" in src, "must reference the `action` discriminant"
        assert "EMAIL" in src and "SMS" in src, (
            "must model both EMAIL and SMS variants"
        )

    def test_type_is_schema_derived(self):
        """L1: WorkflowStep must be inferred from the schema (z.infer/z.output),
        not a hand-written interface/type literal duplicating the fields."""
        src = _read(SCHEMA_TS)
        assert "z.infer" in src or "z.output" in src, (
            "WorkflowStep must be derived via z.infer<typeof ...> / z.output"
        )
        assert "interface WorkflowStep" not in src, (
            "WorkflowStep must not be a hand-written interface"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real behavior (independent spec)
    # ------------------------------------------------------------------ #
    def test_valid_email_step_normalized(self):
        """L2: a valid EMAIL step normalizes timing.value (string->number),
        defaults sendTo to "ATTENDEE", trims subject/body, and narrows action."""
        body = textwrap.dedent(
            """\
            describe("valid email step", () => {
              it("normalizes fields", () => {
                const r = parseWorkflowStep({
                  action: "EMAIL",
                  timing: { when: "BEFORE", unit: "HOUR", value: "2" },
                  subject: "  Reminder  ",
                  body: "  See you soon  ",
                });
                expect(r.success).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(d.action).toBe("EMAIL");
                expect(typeof d.timing.value).toBe("number");
                expect(d.timing.value).toBe(2);
                expect(d.timing.when).toBe("BEFORE");
                expect(d.timing.unit).toBe("HOUR");
                expect(d.sendTo).toBe("ATTENDEE");
                expect(d.subject).toBe("Reminder");
                expect(d.body).toBe("See you soon");
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "valid email step spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_sendto_respected_when_provided(self):
        """L2: an explicit sendTo of "ORGANIZER" is preserved (not overwritten
        by the "ATTENDEE" default), and a valid SMS body is trimmed."""
        body = textwrap.dedent(
            """\
            describe("sendTo override + sms", () => {
              it("keeps explicit sendTo and trims sms body", () => {
                const r = parseWorkflowStep({
                  action: "SMS",
                  timing: { when: "AFTER", unit: "HOUR", value: "1" },
                  body: "  txt  ",
                  sendTo: "ORGANIZER",
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(d.action).toBe("SMS");
                expect(d.sendTo).toBe("ORGANIZER");
                expect(d.body).toBe("txt");
                expect(d.subject).toBeUndefined();
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "sendTo override spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_thirty_day_cap_on_timing_value(self):
        """L2: a 40-day offset (unit DAY, value 40) exceeds the 30-day cap and
        is reported on `timing.value`; exactly 30 days is accepted."""
        body = textwrap.dedent(
            """\
            describe("30-day cap", () => {
              it("rejects > 30 days on timing.value", () => {
                const r = parseWorkflowStep({
                  action: "EMAIL",
                  timing: { when: "BEFORE", unit: "DAY", value: "40" },
                  subject: "S",
                  body: "B",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.includes("timing.value"), "keys=" + JSON.stringify(keys)).toBe(true);
                expect((r.errors["timing.value"] as string[]).length).toBeGreaterThan(0);
              });
              it("accepts exactly 30 days", () => {
                const r = parseWorkflowStep({
                  action: "EMAIL",
                  timing: { when: "BEFORE", unit: "DAY", value: "30" },
                  subject: "S",
                  body: "B",
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "30-day cap spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_sms_five_minute_floor_on_timing_value(self):
        """L2: an SMS step under 5 minutes (unit MINUTE, value 1) is rejected on
        `timing.value`; 5 minutes is accepted. The EMAIL variant has no floor."""
        body = textwrap.dedent(
            """\
            describe("sms 5-minute floor", () => {
              it("rejects sms under 5 minutes on timing.value", () => {
                const r = parseWorkflowStep({
                  action: "SMS",
                  timing: { unit: "MINUTE", value: "1", when: "BEFORE" },
                  body: "hi",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.includes("timing.value"), "keys=" + JSON.stringify(keys)).toBe(true);
              });
              it("accepts sms at exactly 5 minutes", () => {
                const r = parseWorkflowStep({
                  action: "SMS",
                  timing: { unit: "MINUTE", value: "5", when: "BEFORE" },
                  body: "hi",
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
              it("allows email at 1 minute (no sms floor)", () => {
                const r = parseWorkflowStep({
                  action: "EMAIL",
                  timing: { unit: "MINUTE", value: "1", when: "BEFORE" },
                  subject: "S",
                  body: "B",
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "sms floor spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_invalid_action_reported_on_action(self):
        """L2: an unknown action ("PUSH") is rejected with an error keyed at
        `action`."""
        body = textwrap.dedent(
            """\
            describe("invalid action discriminant", () => {
              it("errors on action for an unknown variant", () => {
                const r = parseWorkflowStep({
                  action: "PUSH",
                  timing: { when: "BEFORE", unit: "HOUR", value: "2" },
                  body: "B",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                const hit = keys.find((k) => k === "action" || k.endsWith("action"));
                expect(hit, "expected an action error, got " + JSON.stringify(keys)).toBeTruthy();
                expect((r.errors[hit as string] as string[]).length).toBeGreaterThan(0);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "invalid action spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_value_must_be_positive_integer(self):
        """L2: timing.value must be an integer >= 1: "0", a negative, and a
        non-integer "2.5" all fail; "1" passes."""
        body = textwrap.dedent(
            """\
            describe("timing.value integer >= 1", () => {
              const mk = (value: string) => ({
                action: "EMAIL",
                timing: { when: "BEFORE", unit: "HOUR", value },
                subject: "S",
                body: "B",
              });
              it("rejects 0", () => {
                expect(parseWorkflowStep(mk("0")).success).toBe(false);
              });
              it("rejects negative", () => {
                expect(parseWorkflowStep(mk("-3")).success).toBe(false);
              });
              it("rejects non-integer", () => {
                expect(parseWorkflowStep(mk("2.5")).success).toBe(false);
              });
              it("accepts 1", () => {
                const r = parseWorkflowStep(mk("1"));
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "value integer spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_subject_and_body_length_bounds(self):
        """L2: EMAIL subject 1..120 and body 1..2000 (after trim); SMS body
        1..320 (after trim). Out-of-range fails on the offending field, the
        inclusive bound passes."""
        body = textwrap.dedent(
            """\
            describe("string length bounds", () => {
              const email = (subject: string, b: string) => ({
                action: "EMAIL",
                timing: { when: "BEFORE", unit: "HOUR", value: "2" },
                subject,
                body: b,
              });
              it("rejects empty subject after trim", () => {
                const r = parseWorkflowStep(email("   ", "B"));
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("subject"))).toBe(true);
              });
              it("rejects subject over 120 chars", () => {
                expect(parseWorkflowStep(email("x".repeat(121), "B")).success).toBe(false);
              });
              it("accepts subject at 120 chars", () => {
                const r = parseWorkflowStep(email("x".repeat(120), "B"));
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
              it("rejects email body over 2000 chars", () => {
                expect(parseWorkflowStep(email("S", "x".repeat(2001))).success).toBe(false);
              });
              it("rejects sms body over 320 chars", () => {
                const r = parseWorkflowStep({
                  action: "SMS",
                  timing: { when: "AFTER", unit: "HOUR", value: "1" },
                  body: "x".repeat(321),
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("body"))).toBe(true);
              });
              it("accepts sms body at 320 chars", () => {
                const r = parseWorkflowStep({
                  action: "SMS",
                  timing: { when: "AFTER", unit: "HOUR", value: "1" },
                  body: "x".repeat(320),
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "length bounds spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_unknown_key_rejected_under_its_name(self):
        """L2: an extra key beyond the resolved variant (e.g. `subject` on an
        SMS step, or a stray `foo`) is rejected under its own key name."""
        body = textwrap.dedent(
            """\
            describe("unknown keys", () => {
              it("rejects a stray top-level key", () => {
                const r = parseWorkflowStep({
                  action: "EMAIL",
                  timing: { when: "BEFORE", unit: "HOUR", value: "2" },
                  subject: "S",
                  body: "B",
                  foo: "surprise",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("foo")),
                  "keys=" + JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("rejects subject on an SMS variant", () => {
                const r = parseWorkflowStep({
                  action: "SMS",
                  timing: { when: "AFTER", unit: "HOUR", value: "1" },
                  body: "B",
                  subject: "not allowed here",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("subject")),
                  "keys=" + JSON.stringify(Object.keys(r.errors))).toBe(true);
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
        """L2: an EMAIL step that simultaneously exceeds the 30-day cap and has
        an empty body collects BOTH errors (no stop-at-first-error)."""
        body = textwrap.dedent(
            """\
            describe("multi-error collection", () => {
              it("returns all violations together", () => {
                const r = parseWorkflowStep({
                  action: "EMAIL",
                  timing: { when: "BEFORE", unit: "DAY", value: "40" },
                  subject: "S",
                  body: "   ",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                const hasTiming = keys.some((k) => k.includes("timing.value") || k.includes("value"));
                const hasBody = keys.some((k) => k.includes("body"));
                expect(hasTiming, "missing timing.value; keys=" + JSON.stringify(keys)).toBe(true);
                expect(hasBody, "missing body; keys=" + JSON.stringify(keys)).toBe(true);
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
        {success:false} without throwing, with an object-typed errors map."""
        body = textwrap.dedent(
            """\
            describe("non-object inputs", () => {
              it("never throws on null/string/number/undefined/array", () => {
                for (const bad of [null, "oops", 42, undefined, []]) {
                  let r: any;
                  expect(() => { r = parseWorkflowStep(bad as unknown); }).not.toThrow();
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
        res = _run_vitest("packages/lib/workflowStepSchema.test.ts", timeout=600)
        assert res.returncode == 0, (
            "agent's own workflowStepSchema.test.ts did not pass\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )
