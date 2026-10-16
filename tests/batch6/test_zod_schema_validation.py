"""Tests for the `zod-schema-validation` skill (variant ext6).

Skill task: build a reusable API Key Creation Request Validator in
`packages/lib/apiKeyRequestSchema.ts` of the cal.com monorepo. The deliverable
exports `parseApiKeyRequest(input: unknown)` (a never-throwing tagged-result
validator) and a schema-derived `ApiKeyRequest` type.

Domain rules (from the variant requirement doc):
  - `note`: optional string, 1..80 chars after trimming, trimmed in output,
    omitted when absent.
  - `neverExpires`: optional boolean, defaults to `false` in output.
  - `expiresAt`: optional ISO-8601 datetime string, normalized to a `Date`.
  - `scopes`: required, non-empty array of
    "booking:read" | "booking:write" | "event-type:read" | "event-type:write";
    duplicates collapsed (first-seen order preserved); empty array rejected.
  - Mutual-exclusion: exactly one of (`neverExpires === true`) or a provided
    `expiresAt`. neverExpires true + expiresAt -> error on `expiresAt`.
    falsy/absent neverExpires + no expiresAt -> error on `expiresAt`.
  - Any `*:write` scope requires the matching `*:read` scope; missing read is
    reported on `scopes`.
  - Unknown top-level keys are rejected under their own key name.
  - All violations collected together; never throws on non-object input.

What these tests verify
-----------------------
L1 (existence / minimal well-formedness): the two deliverable files exist, the
schema module references zod, exports `parseApiKeyRequest`, and derives the
`ApiKeyRequest` type from the schema (z.infer/z.output, not a hand-written
interface).

L2 (dynamic execution): rather than trusting the agent's own test file, we
write an INDEPENDENT vitest spec into the package that imports the agent's
module and exercises `parseApiKeyRequest` end-to-end (scope dedup, Date
normalization, neverExpires default, note trim/omit, mutual-exclusion,
write-without-read, empty scopes, unknown keys, multi-error collection,
non-object inputs). We run it with the repo's native vitest. A naive /
hardcoded / keyword-only solution fails these. We also run the agent's own
committed test file via the acceptance command.

Native command (Acceptance Criteria):
    yarn vitest run packages/lib/apiKeyRequestSchema.test.ts
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
SCHEMA_TS = os.path.join(LIB_DIR, "apiKeyRequestSchema.ts")
SCHEMA_TEST_TS = os.path.join(LIB_DIR, "apiKeyRequestSchema.test.ts")

# Independent spec we drop into the package so vitest's `packages/**` include
# globs pick it up under the @calcom/lib project.
VERIFY_SPEC = os.path.join(LIB_DIR, "apiKeyRequestSchema.verify.spec.ts")


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
        import { parseApiKeyRequest } from "./apiKeyRequestSchema";
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
    # util is a no-op for yarn repos, so call it defensively and never fail the
    # suite on it.
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
        """L1: module imports zod and exports parseApiKeyRequest + the type."""
        src = _read(SCHEMA_TS)
        assert 'from "zod"' in src or "from 'zod'" in src, "module must use zod"
        assert "parseApiKeyRequest" in src, "must define parseApiKeyRequest"
        assert "ApiKeyRequest" in src, "must export ApiKeyRequest type"

    def test_type_is_schema_derived(self):
        """L1: ApiKeyRequest must be inferred from the schema (z.infer/z.output),
        not a hand-written interface/type literal duplicating the fields."""
        src = _read(SCHEMA_TS)
        assert "z.infer" in src or "z.output" in src, (
            "ApiKeyRequest must be derived via z.infer<typeof ...> / z.output"
        )
        assert "interface ApiKeyRequest" not in src, (
            "ApiKeyRequest must not be a hand-written interface"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real behavior (independent spec)
    # ------------------------------------------------------------------ #
    def test_valid_neverexpires_dedup_normalized(self):
        """L2: scopes dedup (first-seen order preserved), neverExpires true
        passes with expiresAt absent, and neverExpires surfaces as boolean true.
        A stub that ignores dedup or hardcodes success would fail the exact
        array assertion."""
        body = textwrap.dedent(
            """\
            describe("valid neverExpires + dedup", () => {
              it("dedups scopes and keeps neverExpires true", () => {
                const r = parseApiKeyRequest({
                  scopes: ["booking:read", "booking:write", "booking:read"],
                  neverExpires: true,
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(d.scopes).toEqual(["booking:read", "booking:write"]);
                expect(d.neverExpires).toBe(true);
                expect(d.expiresAt).toBeUndefined();
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "valid neverExpires/dedup spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_valid_expiresat_to_date_and_default_neverexpires(self):
        """L2: expiresAt string is normalized to a real Date with the correct
        instant, and neverExpires defaults to false when omitted."""
        body = textwrap.dedent(
            """\
            describe("valid expiresAt -> Date", () => {
              it("normalizes expiresAt and defaults neverExpires", () => {
                const r = parseApiKeyRequest({
                  scopes: ["event-type:read"],
                  expiresAt: "2030-01-01T00:00:00Z",
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(d.expiresAt instanceof Date).toBe(true);
                expect(d.expiresAt.toISOString()).toBe("2030-01-01T00:00:00.000Z");
                expect(d.neverExpires).toBe(false);
                expect(d.scopes).toEqual(["event-type:read"]);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "valid expiresAt spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_note_trimmed_and_omitted(self):
        """L2: a present note is trimmed in the output; an absent note is
        omitted (not present as empty string / null)."""
        body = textwrap.dedent(
            """\
            describe("note handling", () => {
              it("trims a present note", () => {
                const r = parseApiKeyRequest({
                  scopes: ["booking:read"],
                  neverExpires: true,
                  note: "  my key  ",
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect((r.data as any).note).toBe("my key");
              });
              it("omits an absent note", () => {
                const r = parseApiKeyRequest({
                  scopes: ["booking:read"],
                  neverExpires: true,
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect("note" in (r.data as any)).toBe(false);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "note handling spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_note_length_bounds(self):
        """L2: note must be 1..80 chars after trimming — a whitespace-only note
        and an 81-char note are rejected with a `note` error; an 80-char note
        and a 1-char note pass."""
        body = textwrap.dedent(
            """\
            describe("note length bounds", () => {
              const base = { scopes: ["booking:read"], neverExpires: true };
              it("rejects a whitespace-only note", () => {
                const r = parseApiKeyRequest({ ...base, note: "   " });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("note"))).toBe(true);
              });
              it("rejects a note longer than 80 chars", () => {
                const r = parseApiKeyRequest({ ...base, note: "x".repeat(81) });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("note"))).toBe(true);
              });
              it("accepts an 80-char note and a 1-char note", () => {
                const a = parseApiKeyRequest({ ...base, note: "y".repeat(80) });
                expect(a.success, JSON.stringify((a as any).errors)).toBe(true);
                const b = parseApiKeyRequest({ ...base, note: "z" });
                expect(b.success, JSON.stringify((b as any).errors)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "note bounds spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_write_without_read_rejected_on_scopes(self):
        """L2: a `*:write` scope without its matching `*:read` is rejected with
        the error reported on `scopes`. Mirrors the doc example
        {scopes:["booking:write"], expiresAt:...} -> error on scopes."""
        body = textwrap.dedent(
            """\
            describe("write requires read", () => {
              it("errors on scopes when read is missing", () => {
                const r = parseApiKeyRequest({
                  scopes: ["booking:write"],
                  expiresAt: "2030-01-01T00:00:00Z",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k === "scopes" || k.includes("scopes")),
                  "expected scopes error, got " + JSON.stringify(keys)).toBe(true);
              });
              it("accepts write when the matching read is present", () => {
                const r = parseApiKeyRequest({
                  scopes: ["event-type:read", "event-type:write"],
                  neverExpires: true,
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "write-without-read spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_mutual_exclusion_expiresat(self):
        """L2: neverExpires true + a provided expiresAt -> error on `expiresAt`;
        falsy/absent neverExpires with no expiresAt -> error on `expiresAt`."""
        body = textwrap.dedent(
            """\
            describe("neverExpires / expiresAt mutual exclusion", () => {
              it("rejects neverExpires true together with expiresAt", () => {
                const r = parseApiKeyRequest({
                  scopes: ["booking:read"],
                  neverExpires: true,
                  expiresAt: "2030-01-01T00:00:00Z",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("expiresAt")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("requires expiresAt when neverExpires is falsy/absent", () => {
                const r = parseApiKeyRequest({ scopes: ["booking:read"] });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("expiresAt")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "mutual-exclusion spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_empty_scopes_and_missing_expiry_both_reported(self):
        """L2: {scopes: []} fails with errors on BOTH scopes (empty) and
        expiresAt (required), proving violations are collected, not stopped at
        the first error."""
        body = textwrap.dedent(
            """\
            describe("empty scopes + missing expiry", () => {
              it("reports both scopes and expiresAt", () => {
                const r = parseApiKeyRequest({ scopes: [] });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k.includes("scopes")),
                  "missing scopes; keys=" + JSON.stringify(keys)).toBe(true);
                expect(keys.some((k) => k.includes("expiresAt")),
                  "missing expiresAt; keys=" + JSON.stringify(keys)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "empty scopes spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_invalid_scope_value_rejected(self):
        """L2: an out-of-enum scope value (e.g. "admin:all") is rejected with a
        scopes error; the valid enum values are accepted."""
        body = textwrap.dedent(
            """\
            describe("scope enum validation", () => {
              it("rejects an unknown scope literal", () => {
                const r = parseApiKeyRequest({
                  scopes: ["admin:all"],
                  neverExpires: true,
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("scopes")),
                  JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("accepts all four valid scope literals", () => {
                const r = parseApiKeyRequest({
                  scopes: ["booking:read", "booking:write", "event-type:read", "event-type:write"],
                  neverExpires: true,
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "scope enum spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_unknown_top_level_key_rejected(self):
        """L2: an extra top-level key `foo` is rejected (strict), with `foo`
        present in errors rather than silently dropped."""
        body = textwrap.dedent(
            """\
            describe("unknown top-level key", () => {
              it("rejects extra keys with the key name in errors", () => {
                const r = parseApiKeyRequest({
                  scopes: ["booking:read"],
                  neverExpires: true,
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

    def test_nonobject_inputs_never_throw(self):
        """L2: null, a string, a number, undefined, and an array all return
        {success:false} with an errors object, without throwing."""
        body = textwrap.dedent(
            """\
            describe("non-object inputs", () => {
              it("never throws on null/string/number/undefined/array", () => {
                for (const bad of [null, "oops", 42, undefined, []]) {
                  let r: any;
                  expect(() => { r = parseApiKeyRequest(bad as unknown); }).not.toThrow();
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

    def test_error_values_are_nonempty_string_arrays(self):
        """L2: on failure, every error entry is a non-empty array of string
        messages (the doc mandates Record<string, string[]> with non-empty
        arrays). A stub returning {} or {field: true} fails this."""
        body = textwrap.dedent(
            """\
            describe("error value shape", () => {
              it("maps each field to a non-empty string[]", () => {
                const r = parseApiKeyRequest({ scopes: [] });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const entries = Object.entries(r.errors);
                expect(entries.length).toBeGreaterThan(0);
                for (const [k, v] of entries) {
                  expect(Array.isArray(v), "value for " + k + " not array").toBe(true);
                  const arr = v as unknown[];
                  expect(arr.length, "empty array for " + k).toBeGreaterThan(0);
                  for (const m of arr) {
                    expect(typeof m).toBe("string");
                  }
                }
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "error shape spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_agents_own_suite_passes(self):
        """L2 (acceptance): the agent's own committed vitest suite passes via
        the exact native command from the Acceptance Criteria."""
        assert os.path.isfile(SCHEMA_TEST_TS), "agent test file missing"
        res = _run_vitest("packages/lib/apiKeyRequestSchema.test.ts", timeout=600)
        assert res.returncode == 0, (
            "agent's own apiKeyRequestSchema.test.ts did not pass\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )
