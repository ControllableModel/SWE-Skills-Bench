"""Tests for the `zod-schema-validation` skill (variant ext3).

Skill task (ext3): build a reusable Availability Time-Range Validator in
`packages/lib/availabilityRangeSchema.ts` of the cal.com monorepo. The
deliverable exports `parseAvailabilityPayload(input: unknown)` — a
never-throwing tagged-result validator — plus a schema-derived
`AvailabilityPayload` type.

This is a DIFFERENT task from ext1 (which built a Booking-Import-Row
validator). Here the domain is weekly availability slots: a `timeZone`,
a non-empty `slots` array (each with `weekday` 0-6, `start`/`end` "HH:MM"),
and an optional `overrides` array. Cross-field rules: per-slot end>start,
same-weekday overlap rejection on the later slot's `start`, out-of-range
times, and strict unknown-top-level-key rejection.

What these tests verify
-----------------------
L1 (existence / minimal well-formedness): the two deliverable files exist,
the schema module references zod, exports `parseAvailabilityPayload`, and
derives `AvailabilityPayload` from the schema (z.infer / z.output) rather
than a hand-written interface.

L2 (dynamic execution): rather than trusting the agent's own test file, we
write an INDEPENDENT vitest spec into the repo that imports the agent's
module and exercises `parseAvailabilityPayload` end-to-end — normalization
(weekday coerced to number, timeZone trimmed, overrides omitted when
absent), per-field indexed error keys (`slots.0.end`, `slots.1.start`),
the end>start rule, same-weekday overlap detection on the later slot's
`start`, out-of-range "HH:MM" rejection, simultaneous-violation collection,
unknown-top-level-key rejection, and never-throwing non-object inputs. We
run it with the repo's native vitest. A naive / hardcoded / stop-at-first-
error / keyword-only solution fails these. We also run the agent's own
committed test file via the acceptance command.

Native command (Acceptance Criteria):
    yarn vitest run packages/lib/availabilityRangeSchema.test.ts
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
SCHEMA_TS = os.path.join(LIB_DIR, "availabilityRangeSchema.ts")
SCHEMA_TEST_TS = os.path.join(LIB_DIR, "availabilityRangeSchema.test.ts")

# Independent spec we drop into the package so vitest's `packages/**` include
# globs pick it up under the @calcom/lib project.
VERIFY_SPEC = os.path.join(LIB_DIR, "availabilityRangeSchema.verify.spec.ts")


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
        import { parseAvailabilityPayload } from "./availabilityRangeSchema";
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
    # util is a no-op for yarn repos, so we only call it defensively and never
    # fail the suite on it.
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
        """L1: module imports zod and exports parseAvailabilityPayload + the
        AvailabilityPayload type symbol."""
        src = _read(SCHEMA_TS)
        assert 'from "zod"' in src or "from 'zod'" in src, "module must use zod"
        assert (
            "parseAvailabilityPayload" in src
        ), "must define parseAvailabilityPayload"
        assert "AvailabilityPayload" in src, "must export AvailabilityPayload type"

    def test_type_is_schema_derived(self):
        """L1: AvailabilityPayload must be inferred from the schema (z.infer /
        z.output), not a hand-written interface duplicating the fields."""
        src = _read(SCHEMA_TS)
        assert "z.infer" in src or "z.output" in src, (
            "AvailabilityPayload must be derived via z.infer<typeof ...> / z.output"
        )
        assert "interface AvailabilityPayload" not in src, (
            "AvailabilityPayload must not be a hand-written interface"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real behavior (independent spec)
    # ------------------------------------------------------------------ #
    def test_valid_payload_normalized(self):
        """L2: a valid payload with weekday "1" and a string timeZone with
        surrounding whitespace returns success; weekday is normalized to the
        number 1, timeZone is trimmed, and absent overrides is omitted."""
        body = textwrap.dedent(
            """\
            describe("valid payload normalization", () => {
              it("coerces weekday to number, trims timeZone, omits overrides", () => {
                const r = parseAvailabilityPayload({
                  timeZone: "  America/New_York  ",
                  slots: [{ weekday: "1", start: "09:00", end: "17:00" }],
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(d.timeZone).toBe("America/New_York");
                expect(typeof d.slots[0].weekday).toBe("number");
                expect(d.slots[0].weekday).toBe(1);
                expect(d.slots[0].start).toBe("09:00");
                expect(d.slots[0].end).toBe("17:00");
                expect("overrides" in d).toBe(false);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "valid payload normalization spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_overrides_preserved_when_present(self):
        """L2: when overrides are supplied they are validated and kept in the
        output with date string + boolean available; a non-boolean available
        is rejected with an overrides-scoped error key."""
        body = textwrap.dedent(
            """\
            describe("overrides handling", () => {
              it("keeps valid overrides", () => {
                const r = parseAvailabilityPayload({
                  timeZone: "UTC",
                  slots: [{ weekday: 3, start: "08:00", end: "12:00" }],
                  overrides: [{ date: "2024-12-25", available: false }],
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(Array.isArray(d.overrides)).toBe(true);
                expect(d.overrides[0].date).toBe("2024-12-25");
                expect(d.overrides[0].available).toBe(false);
              });
              it("rejects a bad override date with an overrides-scoped key", () => {
                const r = parseAvailabilityPayload({
                  timeZone: "UTC",
                  slots: [{ weekday: 3, start: "08:00", end: "12:00" }],
                  overrides: [{ date: "25-12-2024", available: true }],
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k.includes("overrides") && k.includes("date")),
                  "keys=" + JSON.stringify(keys)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "overrides handling spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_end_before_start_rejected_on_end_field(self):
        """L2: a slot with start "17:00" end "09:00" fails with an error keyed
        at the slot's indexed `end` path (e.g. slots.0.end); a slot where end
        equals start is also rejected (strictly-later rule)."""
        body = textwrap.dedent(
            """\
            describe("end > start rule", () => {
              it("rejects end earlier than start on slots.0.end", () => {
                const r = parseAvailabilityPayload({
                  timeZone: "UTC",
                  slots: [{ weekday: "2", start: "17:00", end: "09:00" }],
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k === "slots.0.end" || (k.includes("slots.0") && k.endsWith("end"))),
                  "expected slots.0.end, keys=" + JSON.stringify(keys)).toBe(true);
              });
              it("rejects end equal to start (must be strictly later)", () => {
                const r = parseAvailabilityPayload({
                  timeZone: "UTC",
                  slots: [{ weekday: "2", start: "09:00", end: "09:00" }],
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k.includes("slots.0") && k.endsWith("end")),
                  "keys=" + JSON.stringify(keys)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "end>start spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_same_weekday_overlap_rejected_on_later_start(self):
        """L2: two weekday-2 slots "09:00"-"12:00" and "11:00"-"13:00" overlap;
        the error must be reported on the SECOND slot's start (slots.1.start).
        A same-weekday pair that does NOT overlap ("09:00"-"11:00" then
        "11:00"-"12:00") must succeed (touching boundaries are not overlap)."""
        body = textwrap.dedent(
            """\
            describe("same-weekday overlap", () => {
              it("rejects overlap on the later slot's start (slots.1.start)", () => {
                const r = parseAvailabilityPayload({
                  timeZone: "UTC",
                  slots: [
                    { weekday: 2, start: "09:00", end: "12:00" },
                    { weekday: 2, start: "11:00", end: "13:00" },
                  ],
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k === "slots.1.start" || (k.includes("slots.1") && k.endsWith("start"))),
                  "expected slots.1.start, keys=" + JSON.stringify(keys)).toBe(true);
              });
              it("allows non-overlapping touching ranges on the same weekday", () => {
                const r = parseAvailabilityPayload({
                  timeZone: "UTC",
                  slots: [
                    { weekday: 2, start: "09:00", end: "11:00" },
                    { weekday: 2, start: "11:00", end: "12:00" },
                  ],
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
              it("allows overlapping ranges on DIFFERENT weekdays", () => {
                const r = parseAvailabilityPayload({
                  timeZone: "UTC",
                  slots: [
                    { weekday: 2, start: "09:00", end: "12:00" },
                    { weekday: 3, start: "11:00", end: "13:00" },
                  ],
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "overlap spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_out_of_range_time_rejected_on_start(self):
        """L2: a slot with start "25:00" (hour out of range) is rejected with
        an error on that slot's start; likewise minutes "09:60" are rejected,
        and a non-HH:MM shape "9:0" is rejected."""
        body = textwrap.dedent(
            """\
            describe("HH:MM range/format", () => {
              it("rejects hour 25 on slots.0.start", () => {
                const r = parseAvailabilityPayload({
                  timeZone: "UTC",
                  slots: [{ weekday: 0, start: "25:00", end: "23:00" }],
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k.includes("slots.0") && k.endsWith("start")),
                  "keys=" + JSON.stringify(keys)).toBe(true);
              });
              it("rejects minutes 60", () => {
                const r = parseAvailabilityPayload({
                  timeZone: "UTC",
                  slots: [{ weekday: 0, start: "09:60", end: "10:00" }],
                });
                expect(r.success).toBe(false);
              });
              it("rejects an unpadded / malformed time", () => {
                const r = parseAvailabilityPayload({
                  timeZone: "UTC",
                  slots: [{ weekday: 0, start: "9:0", end: "10:00" }],
                });
                expect(r.success).toBe(false);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "HH:MM range spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_weekday_bounds_and_coercion(self):
        """L2: weekday must be an integer 0..6 inclusive; "6" and 0 pass and
        become numbers, while "7", -1 and non-integers are rejected with an
        error keyed at the slot's weekday."""
        body = textwrap.dedent(
            """\
            describe("weekday bounds", () => {
              const slot = (weekday: unknown) => ({
                timeZone: "UTC",
                slots: [{ weekday, start: "09:00", end: "10:00" }],
              });
              it("accepts inclusive bound '6' as number 6", () => {
                const r = parseAvailabilityPayload(slot("6"));
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect((r.data as any).slots[0].weekday).toBe(6);
              });
              it("accepts inclusive bound 0", () => {
                const r = parseAvailabilityPayload(slot(0));
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
              it("rejects weekday 7", () => {
                const r = parseAvailabilityPayload(slot("7"));
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k.includes("slots.0") && k.includes("weekday")),
                  "keys=" + JSON.stringify(keys)).toBe(true);
              });
              it("rejects negative weekday", () => {
                const r = parseAvailabilityPayload(slot(-1));
                expect(r.success).toBe(false);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "weekday bounds spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_required_fields_and_empty_collections(self):
        """L2: timeZone must be a non-empty string after trimming and slots
        must be a non-empty array; a whitespace-only timeZone and an empty
        slots array both fail with keys scoped to those fields."""
        body = textwrap.dedent(
            """\
            describe("required fields", () => {
              it("rejects whitespace-only timeZone", () => {
                const r = parseAvailabilityPayload({
                  timeZone: "   ",
                  slots: [{ weekday: 1, start: "09:00", end: "10:00" }],
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("timeZone")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("rejects an empty slots array", () => {
                const r = parseAvailabilityPayload({ timeZone: "UTC", slots: [] });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("slots")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("rejects a missing slots field", () => {
                const r = parseAvailabilityPayload({ timeZone: "UTC" });
                expect(r.success).toBe(false);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "required fields spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_unknown_top_level_key_rejected(self):
        """L2: an extra top-level key `foo` is rejected (strict), with `foo`
        present in the error keys rather than silently dropped."""
        body = textwrap.dedent(
            """\
            describe("unknown top-level key", () => {
              it("rejects extra keys under their own name", () => {
                const r = parseAvailabilityPayload({
                  timeZone: "UTC",
                  slots: [{ weekday: 1, start: "09:00", end: "10:00" }],
                  foo: "surprise",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k === "foo" || k.includes("foo")),
                  "expected foo in errors; keys=" + JSON.stringify(keys)).toBe(true);
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
        """L2: a payload carrying several simultaneous problems — an out-of-
        range start in slot 0, an end<=start in slot 1, and an unknown top-
        level key — must report ALL of them together (no stop-at-first-error).
        A stub that returns on the first failure fails this test."""
        body = textwrap.dedent(
            """\
            describe("collect all violations", () => {
              it("returns every simultaneous violation", () => {
                const r = parseAvailabilityPayload({
                  timeZone: "UTC",
                  slots: [
                    { weekday: 1, start: "25:00", end: "26:00" },
                    { weekday: 2, start: "12:00", end: "09:00" },
                  ],
                  bogus: true,
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                const hasStart0 = keys.some((k) => k.includes("slots.0") && k.endsWith("start"));
                const hasEnd1 = keys.some((k) => k.includes("slots.1") && k.endsWith("end"));
                const hasUnknown = keys.some((k) => k.includes("bogus"));
                expect(hasStart0, "missing slots.0.start; keys=" + JSON.stringify(keys)).toBe(true);
                expect(hasEnd1, "missing slots.1.end; keys=" + JSON.stringify(keys)).toBe(true);
                expect(hasUnknown, "missing unknown key; keys=" + JSON.stringify(keys)).toBe(true);
                // every error value is a non-empty array of messages
                for (const k of keys) {
                  expect(Array.isArray(r.errors[k]), "value for " + k + " not array").toBe(true);
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
        {success:false} with an errors object, without throwing."""
        body = textwrap.dedent(
            """\
            describe("non-object inputs", () => {
              it("never throws on null/string/number/array/undefined", () => {
                for (const bad of [null, "nope", 42, undefined, [], true]) {
                  let r: any;
                  expect(() => { r = parseAvailabilityPayload(bad as unknown); }).not.toThrow();
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
        res = _run_vitest(
            "packages/lib/availabilityRangeSchema.test.ts", timeout=600
        )
        assert res.returncode == 0, (
            "agent's own availabilityRangeSchema.test.ts did not pass\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )
