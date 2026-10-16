"""Tests for the `zod-schema-validation` skill (variant ext10).

Skill task: build a reusable Public Booking-Page Query Validator in
`packages/lib/bookingPageQuerySchema.ts` of the cal.com monorepo. The
deliverable exports `parseBookingPageQuery(input: unknown)` (a never-throwing
tagged-result validator that validates + normalizes a raw URL query object)
and a schema-derived `BookingPageQuery` type.

What these tests verify
-----------------------
L1 (existence / minimal well-formedness): the two deliverable files exist, the
schema module references zod, exports the public function, and derives the
`BookingPageQuery` type from the schema (z.infer/z.output) rather than a
hand-written interface.

L2 (dynamic execution): rather than trusting the agent's own test file, we
write an INDEPENDENT vitest spec into the repo that imports the agent's module
and exercises `parseBookingPageQuery` end-to-end. We assert concrete normalized
values and error keys: duration string -> number with 5..480 bounds, locale
uppercase -> lowercase + "en" default, layout default "month_view", email
lowercasing, guests dedup/lowercasing/omission, month "YYYY-MM" format with
01..12 month part, the month/date cross-field check reported on `date`,
invalid guest emails reported on `guests`, unknown-key rejection, multi-error
collection, and never-throwing behavior on non-object inputs. A naive /
hardcoded / keyword-only solution fails these. We also run the agent's own
committed test file via the exact native acceptance command.

Native command (Acceptance Criteria):
    yarn vitest run packages/lib/bookingPageQuerySchema.test.ts
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
SCHEMA_TS = os.path.join(LIB_DIR, "bookingPageQuerySchema.ts")
SCHEMA_TEST_TS = os.path.join(LIB_DIR, "bookingPageQuerySchema.test.ts")

# Independent spec we drop into the package so vitest's `packages/**` include
# globs pick it up under the @calcom/lib project.
VERIFY_SPEC = os.path.join(LIB_DIR, "bookingPageQuerySchema.verify.spec.ts")


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
        import { parseBookingPageQuery } from "./bookingPageQuerySchema";
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
        """L1: module imports zod and exports parseBookingPageQuery + a type."""
        src = _read(SCHEMA_TS)
        assert 'from "zod"' in src or "from 'zod'" in src, "module must use zod"
        assert "parseBookingPageQuery" in src, "must define parseBookingPageQuery"
        assert "BookingPageQuery" in src, "must reference BookingPageQuery type"

    def test_type_is_schema_derived(self):
        """L1: BookingPageQuery must be inferred from the schema (z.infer /
        z.output), not a hand-written interface/type literal duplicating the
        fields."""
        src = _read(SCHEMA_TS)
        assert "z.infer" in src or "z.output" in src, (
            "BookingPageQuery must be derived via z.infer<typeof ...> / z.output"
        )
        assert "interface BookingPageQuery" not in src, (
            "BookingPageQuery must not be a hand-written interface"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real behavior (independent spec)
    # ------------------------------------------------------------------ #
    def test_valid_query_normalized(self):
        """L2: the doc's canonical valid case — duration "45" becomes the
        number 45, locale "EN" lowercases to "en", layout defaults to
        "month_view", and guests are lowercased + deduplicated to ["a@x.com"]."""
        body = textwrap.dedent(
            """\
            describe("valid query normalization", () => {
              it("normalizes per the doc's canonical example", () => {
                const r = parseBookingPageQuery({
                  duration: "45",
                  locale: "EN",
                  guests: ["a@x.com", "A@X.com"],
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(typeof d.duration).toBe("number");
                expect(d.duration).toBe(45);
                expect(d.locale).toBe("en");
                expect(d.layout).toBe("month_view");
                expect(Array.isArray(d.guests)).toBe(true);
                expect(d.guests).toEqual(["a@x.com"]);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "valid query normalization spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_defaults_and_omitted_optionals(self):
        """L2: an empty query yields success with layout defaulting to
        "month_view", locale defaulting to "en", and all genuinely optional
        fields (month/date/duration/email/guests) OMITTED from the output (a
        stub that hardcodes them present must fail)."""
        body = textwrap.dedent(
            """\
            describe("defaults & omitted optionals", () => {
              it("applies defaults and omits absent optionals", () => {
                const r = parseBookingPageQuery({});
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(d.layout).toBe("month_view");
                expect(d.locale).toBe("en");
                for (const k of ["month", "date", "duration", "email", "guests"]) {
                  expect(Object.prototype.hasOwnProperty.call(d, k), `expected ${k} omitted`).toBe(false);
                }
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "defaults/omitted spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_duration_bounds_and_type(self):
        """L2: duration must parse to an integer in [5, 480] inclusive — "2"
        (doc example) and "481" fail; "5" and "480" pass and surface as the
        number type; a non-integer "30.5" fails."""
        body = textwrap.dedent(
            """\
            describe("duration bounds", () => {
              it("rejects below-min duration 2", () => {
                const r = parseBookingPageQuery({ duration: "2" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("duration")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("rejects above-max duration 481", () => {
                const r = parseBookingPageQuery({ duration: "481" });
                expect(r.success).toBe(false);
              });
              it("rejects non-integer duration", () => {
                const r = parseBookingPageQuery({ duration: "30.5" });
                expect(r.success).toBe(false);
              });
              it("accepts inclusive bound 5 as a number", () => {
                const r = parseBookingPageQuery({ duration: "5" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect((r.data as any).duration).toBe(5);
                expect(typeof (r.data as any).duration).toBe("number");
              });
              it("accepts inclusive bound 480", () => {
                const r = parseBookingPageQuery({ duration: "480" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                expect((r.data as any).duration).toBe(480);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "duration bounds spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_layout_enum(self):
        """L2: layout accepts the three allowed values verbatim and rejects
        anything else with an error keyed at `layout`."""
        body = textwrap.dedent(
            """\
            describe("layout enum", () => {
              it("accepts each allowed layout", () => {
                for (const v of ["month_view", "week_view", "column_view"]) {
                  const r = parseBookingPageQuery({ layout: v });
                  expect(r.success, `${v}: ` + JSON.stringify((r as any).errors)).toBe(true);
                  if (!r.success) throw new Error("expected success");
                  expect((r.data as any).layout).toBe(v);
                }
              });
              it("rejects an unknown layout on the layout field", () => {
                const r = parseBookingPageQuery({ layout: "agenda_view" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("layout")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "layout enum spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_locale_format_and_lowercasing(self):
        """L2: locale must be two letters (^[a-z]{2}$ after lowercasing);
        uppercase "FR" lowercases to "fr", an invalid "english" / "e" fails on
        `locale`."""
        body = textwrap.dedent(
            """\
            describe("locale format", () => {
              it("lowercases a 2-letter locale", () => {
                const r = parseBookingPageQuery({ locale: "FR" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect((r.data as any).locale).toBe("fr");
              });
              it("rejects a non-2-letter locale", () => {
                const r = parseBookingPageQuery({ locale: "english" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("locale")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("rejects a single-letter locale", () => {
                const r = parseBookingPageQuery({ locale: "e" });
                expect(r.success).toBe(false);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "locale format spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_email_lowercased_and_validated(self):
        """L2: a present email must be valid and is lowercased; an invalid
        email fails on `email`."""
        body = textwrap.dedent(
            """\
            describe("email field", () => {
              it("lowercases a valid email", () => {
                const r = parseBookingPageQuery({ email: "Person.NAME@Example.COM" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect((r.data as any).email).toBe("person.name@example.com");
              });
              it("rejects an invalid email on the email field", () => {
                const r = parseBookingPageQuery({ email: "not-an-email" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("email")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "email spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_guests_single_string_array_dedup_and_invalid(self):
        """L2: guests may arrive as a single string (coerced to a 1-element
        array) or an array; output is lowercased, deduped (first-seen order),
        an empty incoming array is omitted, and any invalid guest email fails
        on `guests` (doc example)."""
        body = textwrap.dedent(
            """\
            describe("guests handling", () => {
              it("coerces a single string guest into a lowercased array", () => {
                const r = parseBookingPageQuery({ guests: "ONE@X.com" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect((r.data as any).guests).toEqual(["one@x.com"]);
              });
              it("dedupes preserving first-seen order", () => {
                const r = parseBookingPageQuery({ guests: ["b@x.com", "a@x.com", "B@X.com"] });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect((r.data as any).guests).toEqual(["b@x.com", "a@x.com"]);
              });
              it("omits guests when the incoming array is empty", () => {
                const r = parseBookingPageQuery({ guests: [] });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect(Object.prototype.hasOwnProperty.call(r.data as any, "guests")).toBe(false);
              });
              it("reports invalid guest emails on guests", () => {
                const r = parseBookingPageQuery({ guests: ["ok@x.com", "not-an-email"] });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("guests")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "guests spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_month_format_and_range(self):
        """L2: month must be "YYYY-MM" with the month part 01..12; a valid
        "2030-02" passes (and round-trips), while "2030-13" and a malformed
        "2030/02" fail on `month`."""
        body = textwrap.dedent(
            """\
            describe("month format", () => {
              it("accepts a valid YYYY-MM", () => {
                const r = parseBookingPageQuery({ month: "2030-02" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect((r.data as any).month).toBe("2030-02");
              });
              it("rejects month part 13", () => {
                const r = parseBookingPageQuery({ month: "2030-13" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("month")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("rejects a malformed month string", () => {
                const r = parseBookingPageQuery({ month: "2030/02" });
                expect(r.success).toBe(false);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "month format spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_month_date_cross_field(self):
        """L2: when both month and date are present, the date must fall within
        that month; a mismatch (month 2030-02 vs date 2030-03-01, doc example)
        is reported on `date`, while a date inside the month passes."""
        body = textwrap.dedent(
            """\
            describe("month/date cross-field", () => {
              it("rejects a date outside the given month on date", () => {
                const r = parseBookingPageQuery({ month: "2030-02", date: "2030-03-01" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("date")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("accepts a date within the given month", () => {
                const r = parseBookingPageQuery({ month: "2030-02", date: "2030-02-15" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "month/date cross-field spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_unknown_key_and_multi_error_collection(self):
        """L2: an unknown top-level key is rejected under its own name, and
        multiple simultaneous violations (bad duration + invalid month +
        unknown key) are all collected together rather than stopping at the
        first error."""
        body = textwrap.dedent(
            """\
            describe("unknown keys & multi-error", () => {
              it("rejects an unknown top-level key under its own name", () => {
                const r = parseBookingPageQuery({ surprise: "x" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("surprise")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("collects all violations together", () => {
                const r = parseBookingPageQuery({
                  duration: "2",
                  month: "2030-13",
                  bogus: "y",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k.includes("duration")), JSON.stringify(keys)).toBe(true);
                expect(keys.some((k) => k.includes("month")), JSON.stringify(keys)).toBe(true);
                expect(keys.some((k) => k.includes("bogus")), JSON.stringify(keys)).toBe(true);
                for (const v of Object.values(r.errors)) {
                  expect(Array.isArray(v)).toBe(true);
                  expect((v as string[]).length).toBeGreaterThan(0);
                }
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "unknown/multi-error spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_nonobject_inputs_never_throw(self):
        """L2: null, undefined, a string, a number and an array all return
        {success:false} without throwing, with an object `errors` map."""
        body = textwrap.dedent(
            """\
            describe("non-object inputs", () => {
              it("never throws on null/undefined/string/number/array", () => {
                for (const bad of [null, undefined, "oops", 42, []]) {
                  let r: any;
                  expect(() => { r = parseBookingPageQuery(bad as unknown); }).not.toThrow();
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
        res = _run_vitest("packages/lib/bookingPageQuerySchema.test.ts", timeout=600)
        assert res.returncode == 0, (
            "agent's own bookingPageQuerySchema.test.ts did not pass\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )
