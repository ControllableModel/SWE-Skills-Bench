"""Tests for the `zod-schema-validation` skill.

Skill task: build a reusable Booking Import Payload Validator in
`packages/lib/bookingImportSchema.ts` of the cal.com monorepo. The deliverable
exports `parseBookingImportRow(input: unknown)` (a never-throwing tagged-result
validator) and a schema-derived `BookingImportRow` type.

What these tests verify
-----------------------
L1 (existence / minimal well-formedness): the two deliverable files exist, the
schema module references zod, exports the public function, and derives the
type from the schema (not a hand-written interface).

L2 (dynamic execution): rather than trusting the agent's own test file, we
write an INDEPENDENT vitest spec into the repo that imports the agent's module
and exercises `parseBookingImportRow` end-to-end (normalization, per-field
error collection, nested error keys, cross-field endTime check, unknown-key
rejection, non-object inputs). We run it with the repo's native vitest. A
naive / hardcoded / keyword-only solution fails these. We also run the agent's
own committed test file via the acceptance command.

Native command (Acceptance Criteria):
    yarn vitest run packages/lib/bookingImportSchema.test.ts
"""

import os
import shutil
import subprocess
import textwrap

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies  # noqa: F401
except Exception:  # pragma: no cover
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/cal.com"
LIB_DIR = os.path.join(REPO_DIR, "packages", "lib")
SCHEMA_TS = os.path.join(LIB_DIR, "bookingImportSchema.ts")
SCHEMA_TEST_TS = os.path.join(LIB_DIR, "bookingImportSchema.test.ts")

# Independent spec we drop into the package so vitest's `packages/**` include
# globs pick it up under the @calcom/lib project.
VERIFY_SPEC = os.path.join(LIB_DIR, "bookingImportSchema.verify.spec.ts")


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
        import { parseBookingImportRow } from "./bookingImportSchema";
        """
    )
    with open(VERIFY_SPEC, "w", encoding="utf-8") as fh:
        fh.write(header + "\n" + body)


@pytest.fixture(scope="module", autouse=True)
def _deps():
    """Ensure node deps are present (container usually pre-installs them)."""
    if not os.path.isdir(REPO_DIR):
        pytest.skip(f"REPO_DIR missing: {REPO_DIR}")
    # cal.com uses yarn; node_modules are normally baked into the image. If a
    # package-lock/npm flow is available the util is a no-op for yarn repos, so
    # we only call it defensively and never fail the suite on it.
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

    def test_module_uses_zod_and_exports_api(self):
        """L1: module imports zod and exports parseBookingImportRow + a type."""
        src = _read(SCHEMA_TS)
        assert 'from "zod"' in src or "from 'zod'" in src, "module must use zod"
        assert "parseBookingImportRow" in src, "must define parseBookingImportRow"
        assert "BookingImportRow" in src, "must export BookingImportRow type"

    def test_type_is_schema_derived(self):
        """L1: BookingImportRow must be inferred from the schema (z.infer),
        not a hand-written interface/type literal duplicating the fields."""
        src = _read(SCHEMA_TS)
        # The type must be derived; reject an interface declaration of the row.
        assert "z.infer" in src or "z.output" in src, (
            "BookingImportRow must be derived via z.infer<typeof ...> / z.output"
        )
        assert "interface BookingImportRow" not in src, (
            "BookingImportRow must not be a hand-written interface"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real behavior (independent spec)
    # ------------------------------------------------------------------ #
    def test_valid_link_row_normalized(self):
        """L2: a fully valid link-type row returns success with normalized
        Date startTime, numeric duration, lowercased email, paid defaulting
        to false when omitted."""
        body = textwrap.dedent(
            """\
            describe("valid link row", () => {
              it("normalizes fields", () => {
                const r = parseBookingImportRow({
                  title: "  Quarterly Sync  ",
                  startTime: "2024-01-15T10:00:00.000Z",
                  durationMinutes: "30",
                  attendee: { name: "  Jane Doe  ", email: "Jane.DOE@Example.COM" },
                  location: { type: "link", url: "https://meet.example.com/abc" },
                });
                expect(r.success).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(d.startTime instanceof Date).toBe(true);
                expect(d.startTime.toISOString()).toBe("2024-01-15T10:00:00.000Z");
                expect(typeof d.durationMinutes).toBe("number");
                expect(d.durationMinutes).toBe(30);
                expect(d.attendee.email).toBe("jane.doe@example.com");
                expect(d.title).toBe("Quarterly Sync");
                expect(d.attendee.name).toBe("Jane Doe");
                expect(d.paid).toBe(false);
                expect(d.location.type).toBe("link");
                expect(d.location.url).toBe("https://meet.example.com/abc");
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "valid link row spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_paid_string_coerced_to_boolean(self):
        """L2: paid arriving as the string "true" is normalized to boolean true."""
        body = textwrap.dedent(
            """\
            describe("paid coercion", () => {
              it("coerces string true/false to boolean", () => {
                const t = parseBookingImportRow({
                  title: "Demo",
                  startTime: "2024-03-01T09:00:00.000Z",
                  durationMinutes: "45",
                  attendee: { name: "A B", email: "a@b.com" },
                  paid: "true",
                  location: { type: "phone", phone: "+15551234567" },
                });
                expect(t.success).toBe(true);
                if (!t.success) throw new Error("expected success");
                expect((t.data as any).paid).toBe(true);

                const f = parseBookingImportRow({
                  title: "Demo",
                  startTime: "2024-03-01T09:00:00.000Z",
                  durationMinutes: "45",
                  attendee: { name: "A B", email: "a@b.com" },
                  paid: "false",
                  location: { type: "phone", phone: "+15551234567" },
                });
                expect(f.success).toBe(true);
                if (!f.success) throw new Error("expected success");
                expect((f.data as any).paid).toBe(false);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "paid coercion spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_inperson_missing_address_fails(self):
        """L2: an inPerson row missing `address` fails with an address-scoped
        error key under errors."""
        body = textwrap.dedent(
            """\
            describe("inPerson missing address", () => {
              it("reports a location.address error", () => {
                const r = parseBookingImportRow({
                  title: "Onsite",
                  startTime: "2024-02-02T12:00:00.000Z",
                  durationMinutes: "60",
                  attendee: { name: "Pat", email: "pat@x.com" },
                  location: { type: "inPerson" },
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                const hit = keys.find((k) => k.includes("address"));
                expect(hit, "expected an address-scoped error, got " + JSON.stringify(keys)).toBeTruthy();
                expect(Array.isArray(r.errors[hit as string])).toBe(true);
                expect((r.errors[hit as string] as string[]).length).toBeGreaterThan(0);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "inPerson missing address spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_unknown_location_type_rejected_on_location_type(self):
        """L2: location.type of "zoom" (not inPerson/link/phone) is rejected
        with an error keyed at location.type."""
        body = textwrap.dedent(
            """\
            describe("unknown location type", () => {
              it("errors at location.type", () => {
                const r = parseBookingImportRow({
                  title: "Call",
                  startTime: "2024-02-02T12:00:00.000Z",
                  durationMinutes: "60",
                  attendee: { name: "Pat", email: "pat@x.com" },
                  location: { type: "zoom", url: "https://zoom.us/j/1" },
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                const hit = keys.find((k) => k === "location.type" || k.endsWith("location.type") || (k.includes("location") && k.includes("type")));
                expect(hit, "expected location.type error, got " + JSON.stringify(keys)).toBeTruthy();
                expect((r.errors[hit as string] as string[]).length).toBeGreaterThan(0);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "unknown location type spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_multiple_violations_collected_together(self):
        """L2: durationMinutes "3" (below 5) and a bad attendee.email yield a
        failure whose errors include BOTH fields (no stop-at-first-error)."""
        body = textwrap.dedent(
            """\
            describe("multi-error collection", () => {
              it("returns all violations together", () => {
                const r = parseBookingImportRow({
                  title: "Bad",
                  startTime: "2024-02-02T12:00:00.000Z",
                  durationMinutes: "3",
                  attendee: { name: "Pat", email: "not-an-email" },
                  location: { type: "link", url: "https://ok.example.com" },
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                const hasDuration = keys.some((k) => k.includes("durationMinutes"));
                const hasEmail = keys.some((k) => k.includes("email"));
                expect(hasDuration, "missing durationMinutes; keys=" + JSON.stringify(keys)).toBe(true);
                expect(hasEmail, "missing attendee.email; keys=" + JSON.stringify(keys)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "multi-violation spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_unknown_top_level_key_rejected(self):
        """L2: an extra top-level key `foo` is rejected (strict), with `foo`
        present in errors rather than silently dropped."""
        body = textwrap.dedent(
            """\
            describe("unknown top-level key", () => {
              it("rejects extra keys with the key name in errors", () => {
                const r = parseBookingImportRow({
                  title: "Has Extra",
                  startTime: "2024-02-02T12:00:00.000Z",
                  durationMinutes: "30",
                  attendee: { name: "Pat", email: "pat@x.com" },
                  location: { type: "phone", phone: "+15551112222" },
                  foo: "surprise",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                const hit = keys.some((k) => k === "foo" || k.includes("foo"));
                expect(hit, "expected foo in errors; keys=" + JSON.stringify(keys)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "unknown key spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_endtime_cross_field_check(self):
        """L2: when endTime is provided it must equal startTime+duration; a
        mismatch fails with an endTime error, while a matching endTime passes
        and an omitted endTime skips the check."""
        body = textwrap.dedent(
            """\
            describe("endTime cross-field", () => {
              const base = {
                title: "Sync",
                startTime: "2024-04-01T10:00:00.000Z",
                durationMinutes: "30",
                attendee: { name: "Pat", email: "pat@x.com" },
                location: { type: "phone", phone: "+15551112222" },
              };
              it("rejects a mismatched endTime on the endTime field", () => {
                const r = parseBookingImportRow({ ...base, endTime: "2024-04-01T11:00:00.000Z" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k.includes("endTime")), "keys=" + JSON.stringify(keys)).toBe(true);
              });
              it("accepts a matching endTime", () => {
                const r = parseBookingImportRow({ ...base, endTime: "2024-04-01T10:30:00.000Z" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
              it("skips the check when endTime omitted", () => {
                const r = parseBookingImportRow({ ...base });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "endTime cross-field spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_nonobject_inputs_never_throw(self):
        """L2: null, a string, and a number all return {success:false} without
        throwing."""
        body = textwrap.dedent(
            """\
            describe("non-object inputs", () => {
              it("never throws on null/string/number", () => {
                for (const bad of [null, "oops", 42, undefined, []]) {
                  let r: any;
                  expect(() => { r = parseBookingImportRow(bad as unknown); }).not.toThrow();
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

    def test_duration_and_title_bounds(self):
        """L2: boundary rules — duration must be an integer 5..1440 and title
        1..200 chars after trim; out-of-range / non-integer values fail, the
        inclusive bounds pass."""
        body = textwrap.dedent(
            """\
            describe("numeric & title bounds", () => {
              const base = {
                startTime: "2024-04-01T10:00:00.000Z",
                attendee: { name: "Pat", email: "pat@x.com" },
                location: { type: "phone", phone: "+15551112222" },
              };
              it("rejects duration above 1440", () => {
                const r = parseBookingImportRow({ ...base, title: "T", durationMinutes: "1441" });
                expect(r.success).toBe(false);
              });
              it("rejects non-integer duration", () => {
                const r = parseBookingImportRow({ ...base, title: "T", durationMinutes: "30.5" });
                expect(r.success).toBe(false);
              });
              it("accepts inclusive lower bound 5", () => {
                const r = parseBookingImportRow({ ...base, title: "T", durationMinutes: "5" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
              it("rejects an empty title after trim", () => {
                const r = parseBookingImportRow({ ...base, title: "   ", durationMinutes: "30" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("title"))).toBe(true);
              });
              it("rejects a title longer than 200 chars", () => {
                const r = parseBookingImportRow({ ...base, title: "x".repeat(201), durationMinutes: "30" });
                expect(r.success).toBe(false);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "bounds spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_link_requires_valid_http_url(self):
        """L2: a link-type location with a non-http(s)/invalid url is rejected
        with a location.url error; a valid https url passes."""
        body = textwrap.dedent(
            """\
            describe("link url validation", () => {
              const base = {
                title: "Sync",
                startTime: "2024-04-01T10:00:00.000Z",
                durationMinutes: "30",
                attendee: { name: "Pat", email: "pat@x.com" },
              };
              it("rejects an invalid url", () => {
                const r = parseBookingImportRow({ ...base, location: { type: "link", url: "not a url" } });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("url")), JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("accepts a valid https url", () => {
                const r = parseBookingImportRow({ ...base, location: { type: "link", url: "https://meet.example.com/x" } });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "link url spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_agents_own_suite_passes(self):
        """L2 (acceptance): the agent's own committed vitest suite passes via
        the exact native command from the Acceptance Criteria."""
        assert os.path.isfile(SCHEMA_TEST_TS), "agent test file missing"
        res = _run_vitest("packages/lib/bookingImportSchema.test.ts", timeout=600)
        assert res.returncode == 0, (
            "agent's own bookingImportSchema.test.ts did not pass\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )
