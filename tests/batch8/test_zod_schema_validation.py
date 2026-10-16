"""Tests for the `zod-schema-validation` skill (variant ext8).

Skill task: build a reusable Booking-Question Field Definition Validator in
`packages/lib/bookingFieldSchema.ts` of the cal.com monorepo. The deliverable
exports `parseBookingField(input: unknown)` — a never-throwing tagged-result
validator over a discriminated union of field variants (text / number / select
/ multiselect) — plus a schema-derived `BookingField` type.

What these tests verify
-----------------------
L1 (existence / minimal well-formedness): the two deliverable files exist, the
schema module references zod, exports the public function, and derives the
`BookingField` type from the schema (z.infer / z.output) rather than a
hand-written interface.

L2 (dynamic execution): rather than trusting the agent's own test file, we
write an INDEPENDENT vitest spec into the @calcom/lib package that imports the
agent's module and exercises `parseBookingField` end-to-end:
  - text variant: string `maxLength` normalized to a real number, `required`
    defaulting to false, absent optionals omitted;
  - number variant: string min/max coerced to numbers, and the cross-field
    `max >= min` rule keyed on `max`;
  - select/multiselect: required non-empty options, duplicate `value` reported
    at the offending indexed path (`options.N.value`), value-pattern rule;
  - multiselect: `maxSelections` coercion and the maxSelections<=#options rule;
  - invalid discriminant `type` reported on `type`;
  - unknown keys rejected under their own key name;
  - simultaneous violations all collected;
  - non-object inputs return failure without throwing.
A naive / hardcoded / keyword-only / stop-at-first-error solution fails these.
We also run the agent's own committed test suite via the acceptance command.

Native command (Acceptance Criteria):
    yarn vitest run packages/lib/bookingFieldSchema.test.ts
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
SCHEMA_TS = os.path.join(LIB_DIR, "bookingFieldSchema.ts")
SCHEMA_TEST_TS = os.path.join(LIB_DIR, "bookingFieldSchema.test.ts")

# Independent spec we drop into the package so vitest's `packages/**` include
# globs pick it up under the @calcom/lib project.
VERIFY_SPEC = os.path.join(LIB_DIR, "bookingFieldSchema.verify.spec.ts")


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
        import { parseBookingField } from "./bookingFieldSchema";
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
    # util is a defensive no-op for yarn repos, so we never fail the suite on it.
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
        """L1: module imports zod and exports parseBookingField + the type."""
        src = _read(SCHEMA_TS)
        assert 'from "zod"' in src or "from 'zod'" in src, "module must use zod"
        assert "parseBookingField" in src, "must define parseBookingField"
        assert "BookingField" in src, "must reference the BookingField type"

    def test_type_is_schema_derived(self):
        """L1: BookingField must be inferred from the schema (z.infer/z.output),
        not a hand-written interface/type literal duplicating the variants."""
        src = _read(SCHEMA_TS)
        assert "z.infer" in src or "z.output" in src, (
            "BookingField must be derived via z.infer<typeof ...> / z.output"
        )
        assert "interface BookingField" not in src, (
            "BookingField must not be a hand-written interface"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real behavior (independent spec)
    # ------------------------------------------------------------------ #
    def test_valid_text_field_normalized(self):
        """L2: a valid text field with maxLength:"120" returns success with
        type "text", numeric maxLength === 120, a trimmed label, and
        required defaulting to false when omitted."""
        body = textwrap.dedent(
            """\
            describe("valid text field", () => {
              it("normalizes maxLength to number and defaults required", () => {
                const r = parseBookingField({
                  type: "text",
                  name: "firstName",
                  label: "  Your first name  ",
                  maxLength: "120",
                });
                expect(r.success).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(d.type).toBe("text");
                expect(typeof d.maxLength).toBe("number");
                expect(d.maxLength).toBe(120);
                expect(d.label).toBe("Your first name");
                expect(d.required).toBe(false);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "valid text field spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_absent_optionals_omitted(self):
        """L2: a text field without maxLength omits the key entirely from the
        normalized output (not undefined/null/0)."""
        body = textwrap.dedent(
            """\
            describe("absent optionals omitted", () => {
              it("does not include maxLength when absent", () => {
                const r = parseBookingField({
                  type: "text",
                  name: "note",
                  label: "Note",
                });
                expect(r.success).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(Object.prototype.hasOwnProperty.call(d, "maxLength")).toBe(false);
                expect(d.required).toBe(false);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "absent optionals spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_number_min_max_coercion_and_ordering(self):
        """L2: number variant coerces string min/max to numbers; when min:"5"
        and max:"2" the ordering rule fails with an error keyed on `max`. A
        valid ordering passes and yields numeric min/max."""
        body = textwrap.dedent(
            """\
            describe("number variant", () => {
              it("rejects max < min on the max field", () => {
                const r = parseBookingField({
                  type: "number",
                  name: "age",
                  label: "Age",
                  min: "5",
                  max: "2",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k === "max" || k.endsWith(".max")),
                  "expected a max error, got " + JSON.stringify(keys)).toBe(true);
              });
              it("coerces valid min/max to numbers", () => {
                const r = parseBookingField({
                  type: "number",
                  name: "age",
                  label: "Age",
                  min: "1",
                  max: "120",
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(typeof d.min).toBe("number");
                expect(typeof d.max).toBe("number");
                expect(d.min).toBe(1);
                expect(d.max).toBe(120);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "number min/max spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_select_duplicate_option_value_indexed_path(self):
        """L2: a select field with two options sharing value:"a" fails with an
        error keyed at the SECOND option's value path (options.1.value)."""
        body = textwrap.dedent(
            """\
            describe("select duplicate option values", () => {
              it("reports duplicate at the offending indexed value path", () => {
                const r = parseBookingField({
                  type: "select",
                  name: "color",
                  label: "Color",
                  options: [
                    { label: "Alpha", value: "a" },
                    { label: "Also Alpha", value: "a" },
                  ],
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                const hit = keys.find((k) => k === "options.1.value");
                expect(hit, "expected options.1.value, got " + JSON.stringify(keys)).toBeTruthy();
                expect(Array.isArray(r.errors[hit as string])).toBe(true);
                expect((r.errors[hit as string] as string[]).length).toBeGreaterThan(0);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "select duplicate value spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_select_value_pattern_and_required_options(self):
        """L2: an option value violating ^[a-z0-9_-]+$ is rejected at its
        indexed value path, and a select with an empty options array fails
        with an options error; a valid select passes."""
        body = textwrap.dedent(
            """\
            describe("select option rules", () => {
              it("rejects a value not matching the pattern", () => {
                const r = parseBookingField({
                  type: "select",
                  name: "size",
                  label: "Size",
                  options: [{ label: "Big", value: "Big Value!" }],
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k.includes("options.0.value")),
                  JSON.stringify(keys)).toBe(true);
              });
              it("rejects an empty options array", () => {
                const r = parseBookingField({
                  type: "select",
                  name: "size",
                  label: "Size",
                  options: [],
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("options")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("accepts a valid select", () => {
                const r = parseBookingField({
                  type: "select",
                  name: "size",
                  label: "Size",
                  options: [
                    { label: "Small", value: "s" },
                    { label: "Large", value: "l" },
                  ],
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "select option rules spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_multiselect_maxselections_rules(self):
        """L2: multiselect coerces string maxSelections to a number; when it
        exceeds the number of options it fails with a maxSelections error; a
        valid value passes and is numeric in the output."""
        body = textwrap.dedent(
            """\
            describe("multiselect maxSelections", () => {
              const opts = [
                { label: "One", value: "one" },
                { label: "Two", value: "two" },
              ];
              it("rejects maxSelections exceeding number of options", () => {
                const r = parseBookingField({
                  type: "multiselect",
                  name: "tags",
                  label: "Tags",
                  options: opts,
                  maxSelections: "3",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("maxSelections")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("coerces a valid maxSelections to a number", () => {
                const r = parseBookingField({
                  type: "multiselect",
                  name: "tags",
                  label: "Tags",
                  options: opts,
                  maxSelections: "2",
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(d.type).toBe("multiselect");
                expect(typeof d.maxSelections).toBe("number");
                expect(d.maxSelections).toBe(2);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "multiselect maxSelections spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_invalid_discriminant_type_rejected(self):
        """L2: a field with type:"rating" (not text/number/select/multiselect)
        is rejected with an error keyed on the `type` discriminant."""
        body = textwrap.dedent(
            """\
            describe("invalid discriminant", () => {
              it("errors on the type field", () => {
                const r = parseBookingField({
                  type: "rating",
                  name: "score",
                  label: "Score",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                const hit = keys.find((k) => k === "type" || k.endsWith(".type") || k.includes("type"));
                expect(hit, "expected a type error, got " + JSON.stringify(keys)).toBeTruthy();
                expect((r.errors[hit as string] as string[]).length).toBeGreaterThan(0);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "invalid discriminant spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_name_and_label_bounds(self):
        """L2: name must match ^[a-zA-Z][a-zA-Z0-9_]*$ (1..40) and label is
        1..100 chars after trim; violations fail on the right field while
        valid inclusive values pass."""
        body = textwrap.dedent(
            """\
            describe("name & label bounds", () => {
              it("rejects a name starting with a digit", () => {
                const r = parseBookingField({ type: "text", name: "1bad", label: "L" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("name")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("rejects a name longer than 40 chars", () => {
                const r = parseBookingField({ type: "text", name: "a".repeat(41), label: "L" });
                expect(r.success).toBe(false);
              });
              it("rejects an empty label after trim", () => {
                const r = parseBookingField({ type: "text", name: "ok", label: "   " });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("label")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("accepts valid name and label", () => {
                const r = parseBookingField({ type: "text", name: "field_1", label: "Field One" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "name/label bounds spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_unknown_key_rejected_under_its_name(self):
        """L2: an extra key not allowed for the resolved variant (e.g. a text
        field carrying `options`, plus a stray `foo`) is rejected with the key
        name present in errors rather than silently dropped."""
        body = textwrap.dedent(
            """\
            describe("unknown keys", () => {
              it("rejects stray keys under their own name", () => {
                const r = parseBookingField({
                  type: "text",
                  name: "note",
                  label: "Note",
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
        """L2: a number field with a bad name AND max < min yields a failure
        whose errors include BOTH the name and max fields (no stop-at-first)."""
        body = textwrap.dedent(
            """\
            describe("multi-error collection", () => {
              it("returns all violations together", () => {
                const r = parseBookingField({
                  type: "number",
                  name: "1nope",
                  label: "Age",
                  min: "10",
                  max: "4",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k.includes("name")),
                  "missing name; keys=" + JSON.stringify(keys)).toBe(true);
                expect(keys.some((k) => k === "max" || k.endsWith(".max")),
                  "missing max; keys=" + JSON.stringify(keys)).toBe(true);
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
        """L2: null, undefined, a string, a number and an array all return
        {success:false} with an object `errors` and never throw."""
        body = textwrap.dedent(
            """\
            describe("non-object inputs", () => {
              it("never throws on null/string/number/array/undefined", () => {
                for (const bad of [null, "oops", 42, undefined, []]) {
                  let r: any;
                  expect(() => { r = parseBookingField(bad as unknown); }).not.toThrow();
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
        res = _run_vitest("packages/lib/bookingFieldSchema.test.ts", timeout=600)
        assert res.returncode == 0, (
            "agent's own bookingFieldSchema.test.ts did not pass\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )
