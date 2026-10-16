"""Tests for the `zod-schema-validation` skill (variant ext7).

Skill task: build a reusable Organization Branding Config Validator in
`packages/lib/orgBrandingSchema.ts` of the cal.com monorepo. The deliverable
exports `parseOrgBranding(input: unknown)` -- a never-throwing tagged-result
validator that normalizes name/slug/theme colors and applies flag defaults --
plus a schema-derived `OrgBranding` type.

What these tests verify
-----------------------
L1 (existence / minimal well-formedness): the two deliverable files
(`orgBrandingSchema.ts` + `orgBrandingSchema.test.ts`) exist, the schema
module references zod, exports the public `parseOrgBranding` function and the
`OrgBranding` symbol, and derives the type from the schema (z.infer / z.output)
rather than hand-writing an `interface OrgBranding`.

L2 (dynamic execution): rather than trusting the agent's own test file, we
write an INDEPENDENT vitest spec into the package that imports the agent's
module and exercises `parseOrgBranding` end-to-end:
  * full valid-input normalization (name trimmed, slug lowercased, colors
    lowercased, logoUrl omitted when absent, flags defaulted),
  * partial-flags default fallback,
  * slug pattern rejection (leading/trailing dash) reported on `slug`,
  * equal light/dark colors reported on `theme.darkBrandColor`,
  * invalid hex color reported on `theme.lightBrandColor`,
  * required-field and bad-logoUrl errors,
  * unknown top-level key rejected under its own name,
  * all simultaneous violations collected together,
  * non-object inputs returning {success:false} without throwing.
A naive / hardcoded / keyword-only solution (fixed return value, no
normalization, stop-at-first-error, throws on bad input) fails these. We also
run the agent's own committed test file via the exact acceptance command.

Native command (Acceptance Criteria):
    yarn vitest run packages/lib/orgBrandingSchema.test.ts
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
SCHEMA_TS = os.path.join(LIB_DIR, "orgBrandingSchema.ts")
SCHEMA_TEST_TS = os.path.join(LIB_DIR, "orgBrandingSchema.test.ts")

# Independent spec we drop into the package so vitest's `packages/**` include
# globs pick it up under the @calcom/lib project.
VERIFY_SPEC = os.path.join(LIB_DIR, "orgBrandingSchema.verify.spec.ts")


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
        import { parseOrgBranding } from "./orgBrandingSchema";
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
    # util is a defensive no-op for yarn repos, so never fail the suite on it.
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
        """L1: module imports zod and exports parseOrgBranding + an OrgBranding
        symbol."""
        src = _read(SCHEMA_TS)
        assert 'from "zod"' in src or "from 'zod'" in src, "module must use zod"
        assert "parseOrgBranding" in src, "must define parseOrgBranding"
        assert "OrgBranding" in src, "must export OrgBranding type"

    def test_type_is_schema_derived(self):
        """L1: OrgBranding must be inferred from the schema (z.infer / z.output),
        not a hand-written interface duplicating the fields."""
        src = _read(SCHEMA_TS)
        assert "z.infer" in src or "z.output" in src, (
            "OrgBranding must be derived via z.infer<typeof ...> / z.output"
        )
        assert "interface OrgBranding" not in src, (
            "OrgBranding must not be a hand-written interface"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real behavior (independent spec)
    # ------------------------------------------------------------------ #
    def test_valid_input_normalized_with_flag_defaults(self):
        """L2: a fully valid input returns success with name trimmed, slug
        lowercased, both colors lowercased, logoUrl omitted (absent), and flags
        defaulted to {hideBranding:false, allowSEOIndexing:true}."""
        body = textwrap.dedent(
            """\
            describe("valid normalization", () => {
              it("trims/lowercases and applies flag defaults", () => {
                const r = parseOrgBranding({
                  name: "  Acme  ",
                  slug: "  Acme-Co  ",
                  theme: { lightBrandColor: "#FFFFFF", darkBrandColor: "#111111" },
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(d.name).toBe("Acme");
                expect(d.slug).toBe("acme-co");
                expect(d.theme.lightBrandColor).toBe("#ffffff");
                expect(d.theme.darkBrandColor).toBe("#111111");
                expect("logoUrl" in d).toBe(false);
                expect(d.flags).toEqual({ hideBranding: false, allowSEOIndexing: true });
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "valid normalization spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_partial_flags_fall_back_to_defaults(self):
        """L2: when `flags` is provided with only one key, the missing key
        falls back to its documented default and the provided one is kept."""
        body = textwrap.dedent(
            """\
            describe("partial flags", () => {
              it("fills missing flag keys with defaults", () => {
                const r = parseOrgBranding({
                  name: "Org",
                  slug: "org",
                  theme: { lightBrandColor: "#abcdef", darkBrandColor: "#123456" },
                  flags: { hideBranding: true },
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(d.flags.hideBranding).toBe(true);
                expect(d.flags.allowSEOIndexing).toBe(true);

                const r2 = parseOrgBranding({
                  name: "Org",
                  slug: "org",
                  theme: { lightBrandColor: "#abcdef", darkBrandColor: "#123456" },
                  flags: { allowSEOIndexing: false },
                });
                expect(r2.success, JSON.stringify((r2 as any).errors)).toBe(true);
                if (!r2.success) throw new Error("expected success");
                const d2 = r2.data as any;
                expect(d2.flags.allowSEOIndexing).toBe(false);
                expect(d2.flags.hideBranding).toBe(false);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "partial flags spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_logo_url_kept_when_valid_https(self):
        """L2: a valid https logoUrl is kept in the output; a non-https or
        malformed logoUrl is rejected on the `logoUrl` field."""
        body = textwrap.dedent(
            """\
            describe("logoUrl handling", () => {
              const base = {
                name: "Org",
                slug: "org",
                theme: { lightBrandColor: "#abcdef", darkBrandColor: "#123456" },
              };
              it("keeps a valid https logoUrl", () => {
                const r = parseOrgBranding({ ...base, logoUrl: "https://cdn.example.com/logo.png" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect((r.data as any).logoUrl).toBe("https://cdn.example.com/logo.png");
              });
              it("rejects a non-https logoUrl on the logoUrl field", () => {
                const r = parseOrgBranding({ ...base, logoUrl: "http://cdn.example.com/logo.png" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("logoUrl")),
                  "keys=" + JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("rejects a malformed logoUrl", () => {
                const r = parseOrgBranding({ ...base, logoUrl: "not a url" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("logoUrl"))).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "logoUrl spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_slug_pattern_rejected_on_slug_field(self):
        """L2: a slug that normalizes to a leading/trailing-dash value (or has
        consecutive dashes) is rejected with an error keyed at `slug`."""
        body = textwrap.dedent(
            """\
            describe("slug pattern", () => {
              const base = {
                name: "Org",
                theme: { lightBrandColor: "#abcdef", darkBrandColor: "#123456" },
              };
              it("rejects a leading/trailing dash slug on slug", () => {
                const r = parseOrgBranding({ ...base, slug: "-bad-" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k === "slug" || k.includes("slug")),
                  "keys=" + JSON.stringify(keys)).toBe(true);
                const hit = keys.find((k) => k === "slug" || k.includes("slug"));
                expect(Array.isArray(r.errors[hit as string])).toBe(true);
                expect((r.errors[hit as string] as string[]).length).toBeGreaterThan(0);
              });
              it("rejects consecutive dashes", () => {
                const r = parseOrgBranding({ ...base, slug: "a--b" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("slug"))).toBe(true);
              });
              it("rejects a slug that becomes empty / non-alnum after normalization", () => {
                const r = parseOrgBranding({ ...base, slug: "***" });
                expect(r.success).toBe(false);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "slug pattern spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_equal_colors_rejected_on_dark_brand_color(self):
        """L2: when lightBrandColor and darkBrandColor are equal (after
        normalization) the violation is reported on `theme.darkBrandColor`."""
        body = textwrap.dedent(
            """\
            describe("equal colors cross-field", () => {
              it("reports equality on theme.darkBrandColor", () => {
                const r = parseOrgBranding({
                  name: "Org",
                  slug: "org",
                  theme: { lightBrandColor: "#abcabc", darkBrandColor: "#abcabc" },
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.includes("theme.darkBrandColor"),
                  "expected theme.darkBrandColor key, got " + JSON.stringify(keys)).toBe(true);
                expect((r.errors["theme.darkBrandColor"] as string[]).length).toBeGreaterThan(0);
              });
              it("treats colors differing only in case as equal", () => {
                const r = parseOrgBranding({
                  name: "Org",
                  slug: "org",
                  theme: { lightBrandColor: "#ABCABC", darkBrandColor: "#abcabc" },
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).includes("theme.darkBrandColor")).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "equal colors spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_invalid_hex_color_rejected_on_light_brand_color(self):
        """L2: a non-hex lightBrandColor like "blue" (or a 3-digit hex) is
        rejected with an error keyed at `theme.lightBrandColor`."""
        body = textwrap.dedent(
            """\
            describe("invalid hex color", () => {
              const base = { name: "Org", slug: "org" };
              it("rejects a named color on theme.lightBrandColor", () => {
                const r = parseOrgBranding({
                  ...base,
                  theme: { lightBrandColor: "blue", darkBrandColor: "#111111" },
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.includes("theme.lightBrandColor"),
                  "keys=" + JSON.stringify(keys)).toBe(true);
              });
              it("rejects a 3-digit hex shorthand", () => {
                const r = parseOrgBranding({
                  ...base,
                  theme: { lightBrandColor: "#fff", darkBrandColor: "#111111" },
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("lightBrandColor"))).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "invalid hex spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_required_fields_reported(self):
        """L2: missing required fields (name, slug, theme colors) and an
        over-long name (>50 after trim) are reported under their own keys."""
        body = textwrap.dedent(
            """\
            describe("required fields & bounds", () => {
              it("reports missing name and slug", () => {
                const r = parseOrgBranding({
                  theme: { lightBrandColor: "#abcdef", darkBrandColor: "#123456" },
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k.includes("name")), "keys=" + JSON.stringify(keys)).toBe(true);
                expect(keys.some((k) => k.includes("slug")), "keys=" + JSON.stringify(keys)).toBe(true);
              });
              it("reports a missing theme color", () => {
                const r = parseOrgBranding({
                  name: "Org",
                  slug: "org",
                  theme: { lightBrandColor: "#abcdef" },
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("darkBrandColor"))).toBe(true);
              });
              it("rejects a name longer than 50 chars after trim", () => {
                const r = parseOrgBranding({
                  name: "x".repeat(51),
                  slug: "org",
                  theme: { lightBrandColor: "#abcdef", darkBrandColor: "#123456" },
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("name"))).toBe(true);
              });
              it("rejects an empty name after trim", () => {
                const r = parseOrgBranding({
                  name: "   ",
                  slug: "org",
                  theme: { lightBrandColor: "#abcdef", darkBrandColor: "#123456" },
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("name"))).toBe(true);
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
        present under its own key in errors rather than silently dropped."""
        body = textwrap.dedent(
            """\
            describe("unknown top-level key", () => {
              it("rejects extra keys with the key name in errors", () => {
                const r = parseOrgBranding({
                  name: "Org",
                  slug: "org",
                  theme: { lightBrandColor: "#abcdef", darkBrandColor: "#123456" },
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
        """L2: an input with several simultaneous problems (bad slug, equal
        colors, invalid logoUrl, unknown key) returns ALL of them together,
        proving no stop-at-first-error."""
        body = textwrap.dedent(
            """\
            describe("multi-error collection", () => {
              it("returns all violations together", () => {
                const r = parseOrgBranding({
                  name: "Org",
                  slug: "-bad-",
                  theme: { lightBrandColor: "#abcabc", darkBrandColor: "#abcabc" },
                  logoUrl: "ftp://x",
                  foo: 1,
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k.includes("slug")), "slug missing: " + JSON.stringify(keys)).toBe(true);
                expect(keys.includes("theme.darkBrandColor"), "dark missing: " + JSON.stringify(keys)).toBe(true);
                expect(keys.some((k) => k.includes("logoUrl")), "logoUrl missing: " + JSON.stringify(keys)).toBe(true);
                expect(keys.some((k) => k.includes("foo")), "foo missing: " + JSON.stringify(keys)).toBe(true);
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
        {success:false} with an errors object, without throwing."""
        body = textwrap.dedent(
            """\
            describe("non-object inputs", () => {
              it("never throws on null/string/number/array", () => {
                for (const bad of [null, "nope", 42, undefined, []]) {
                  let r: any;
                  expect(() => { r = parseOrgBranding(bad as unknown); }).not.toThrow();
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
        res = _run_vitest("packages/lib/orgBrandingSchema.test.ts", timeout=600)
        assert res.returncode == 0, (
            "agent's own orgBrandingSchema.test.ts did not pass\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )
