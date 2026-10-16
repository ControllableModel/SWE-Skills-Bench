"""Tests for the `zod-schema-validation` skill (variant ext2).

Skill task (ext2): build a reusable Webhook Subscription Payload Validator in
`packages/lib/webhookSubscriptionSchema.ts` of the cal.com monorepo. The
deliverable exports `parseWebhookSubscription(input: unknown)` — a
never-throwing tagged-result validator — and a schema-derived
`WebhookSubscription` type.

This is a DISTINCT task from ext1 (which built a Booking Import Row validator):
different deliverable files, different public function, different field rules,
and different behavioral assertions. Every assertion below is re-derived from
the ext2 requirement doc.

What these tests verify
-----------------------
L1 (existence / minimal well-formedness): the two deliverable files exist, the
schema module references zod, exports the public function, and derives the
`WebhookSubscription` type from the schema (z.infer/z.output), not a
hand-written interface.

L2 (dynamic execution): rather than trusting the agent's own test file, we
write an INDEPENDENT vitest spec into the @calcom/lib package that imports the
agent's module and exercises `parseWebhookSubscription` end-to-end:
  - valid subscription normalization (trimmed url, deduped triggers preserving
    first-seen order, `active` defaulting to true, absent optionals omitted);
  - https-only subscriberUrl rejection of plain http;
  - the cross-field rule that MEETING_ENDED requires a payloadTemplate, with the
    error reported on `payloadTemplate`;
  - nested error keys (`payloadTemplate.format`);
  - secret length bounds (8..128);
  - unknown top-level key rejection (strict) reported under that key;
  - empty eventTriggers rejection and multi-violation collection;
  - non-object inputs never throwing.
We run each via the repo's native vitest. A naive / hardcoded / keyword-only
solution fails these. We also run the agent's own committed test file via the
exact acceptance command.

Native command (Acceptance Criteria):
    yarn vitest run packages/lib/webhookSubscriptionSchema.test.ts
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
SCHEMA_TS = os.path.join(LIB_DIR, "webhookSubscriptionSchema.ts")
SCHEMA_TEST_TS = os.path.join(LIB_DIR, "webhookSubscriptionSchema.test.ts")

# Independent spec we drop into the package so vitest's `packages/**` include
# globs pick it up under the @calcom/lib project.
VERIFY_SPEC = os.path.join(LIB_DIR, "webhookSubscriptionSchema.verify.spec.ts")


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
        import { parseWebhookSubscription } from "./webhookSubscriptionSchema";
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
        """L1: module imports zod and exports parseWebhookSubscription + the
        WebhookSubscription type."""
        src = _read(SCHEMA_TS)
        assert 'from "zod"' in src or "from 'zod'" in src, "module must use zod"
        assert (
            "parseWebhookSubscription" in src
        ), "must define parseWebhookSubscription"
        assert "WebhookSubscription" in src, "must export WebhookSubscription type"

    def test_type_is_schema_derived(self):
        """L1: WebhookSubscription must be inferred from the schema (z.infer /
        z.output), not a hand-written interface duplicating the fields."""
        src = _read(SCHEMA_TS)
        assert "z.infer" in src or "z.output" in src, (
            "WebhookSubscription must be derived via z.infer<typeof ...> / z.output"
        )
        assert "interface WebhookSubscription" not in src, (
            "WebhookSubscription must not be a hand-written interface"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real behavior (independent spec)
    # ------------------------------------------------------------------ #
    def test_valid_subscription_normalized(self):
        """L2: a valid subscription returns success with a trimmed
        subscriberUrl, deduplicated eventTriggers preserving first-seen order,
        `active` defaulting to true when omitted, and absent optionals
        (secret/payloadTemplate) omitted from data."""
        body = textwrap.dedent(
            """\
            describe("valid subscription", () => {
              it("normalizes & dedupes & defaults", () => {
                const r = parseWebhookSubscription({
                  subscriberUrl: "  https://hooks.example.com/wh  ",
                  eventTriggers: ["BOOKING_CREATED", "BOOKING_CREATED", "BOOKING_CANCELLED"],
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                const d = r.data as any;
                expect(d.subscriberUrl).toBe("https://hooks.example.com/wh");
                expect(d.eventTriggers).toEqual(["BOOKING_CREATED", "BOOKING_CANCELLED"]);
                expect(d.active).toBe(true);
                expect("secret" in d).toBe(false);
                expect("payloadTemplate" in d).toBe(false);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "valid subscription spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_http_subscriber_url_rejected(self):
        """L2: a plain http:// subscriberUrl is rejected with an error keyed on
        subscriberUrl; a https:// url is accepted."""
        body = textwrap.dedent(
            """\
            describe("https-only subscriberUrl", () => {
              it("rejects http and accepts https", () => {
                const bad = parseWebhookSubscription({
                  subscriberUrl: "http://x.test/hook",
                  eventTriggers: ["BOOKING_CREATED"],
                });
                expect(bad.success).toBe(false);
                if (bad.success) throw new Error("expected failure");
                const keys = Object.keys(bad.errors);
                expect(keys.some((k) => k.includes("subscriberUrl")), JSON.stringify(keys)).toBe(true);
                expect((bad.errors[keys.find((k) => k.includes("subscriberUrl")) as string] as string[]).length).toBeGreaterThan(0);

                const ok = parseWebhookSubscription({
                  subscriberUrl: "https://x.test/hook",
                  eventTriggers: ["BOOKING_CREATED"],
                });
                expect(ok.success, JSON.stringify((ok as any).errors)).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "http rejection spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_empty_event_triggers_rejected(self):
        """L2: an empty eventTriggers array is rejected with an error keyed on
        eventTriggers; an unknown trigger value is also rejected."""
        body = textwrap.dedent(
            """\
            describe("eventTriggers validation", () => {
              it("rejects empty array", () => {
                const r = parseWebhookSubscription({
                  subscriberUrl: "https://x.test/hook",
                  eventTriggers: [],
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("eventTriggers")), JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("rejects an unknown trigger enum value", () => {
                const r = parseWebhookSubscription({
                  subscriberUrl: "https://x.test/hook",
                  eventTriggers: ["BOOKING_CREATED", "NOT_A_TRIGGER"],
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("eventTriggers")), JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "eventTriggers spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_meeting_ended_requires_payload_template(self):
        """L2 (cross-field): when eventTriggers contains MEETING_ENDED, a
        payloadTemplate is required — omitting it fails with an error reported
        on `payloadTemplate`; providing a valid one passes."""
        body = textwrap.dedent(
            """\
            describe("MEETING_ENDED requires payloadTemplate", () => {
              it("fails on payloadTemplate when omitted", () => {
                const r = parseWebhookSubscription({
                  subscriberUrl: "https://x.test/hook",
                  eventTriggers: ["BOOKING_CREATED", "MEETING_ENDED"],
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                const hit = keys.find((k) => k === "payloadTemplate" || k.includes("payloadTemplate"));
                expect(hit, "expected payloadTemplate error, keys=" + JSON.stringify(keys)).toBeTruthy();
                expect((r.errors[hit as string] as string[]).length).toBeGreaterThan(0);
              });
              it("passes when a valid payloadTemplate is supplied", () => {
                const r = parseWebhookSubscription({
                  subscriberUrl: "https://x.test/hook",
                  eventTriggers: ["MEETING_ENDED"],
                  payloadTemplate: { format: "json", body: "{\\"x\\":1}" },
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect((r.data as any).payloadTemplate.format).toBe("json");
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "MEETING_ENDED cross-field spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_payload_template_nested_error_key(self):
        """L2: a present payloadTemplate with an invalid `format` is rejected
        with a nested error key `payloadTemplate.format`; an empty/whitespace
        `body` is also rejected."""
        body = textwrap.dedent(
            """\
            describe("payloadTemplate nested validation", () => {
              it("reports payloadTemplate.format on a bad format", () => {
                const r = parseWebhookSubscription({
                  subscriberUrl: "https://x.test/hook",
                  eventTriggers: ["BOOKING_CREATED"],
                  payloadTemplate: { format: "xml", body: "hello" },
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                const hit = keys.find((k) => k === "payloadTemplate.format" || (k.includes("payloadTemplate") && k.includes("format")));
                expect(hit, "expected payloadTemplate.format error, keys=" + JSON.stringify(keys)).toBeTruthy();
                expect((r.errors[hit as string] as string[]).length).toBeGreaterThan(0);
              });
              it("rejects an empty body after trim", () => {
                const r = parseWebhookSubscription({
                  subscriberUrl: "https://x.test/hook",
                  eventTriggers: ["BOOKING_CREATED"],
                  payloadTemplate: { format: "text", body: "   " },
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("payloadTemplate") && k.includes("body")), JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "payloadTemplate nested spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_secret_length_bounds(self):
        """L2: when present, secret must be 8..128 chars — too short and too
        long fail (with a secret-keyed error), an in-range value passes and is
        preserved, and an absent secret is omitted (not null)."""
        body = textwrap.dedent(
            """\
            describe("secret bounds", () => {
              const base = {
                subscriberUrl: "https://x.test/hook",
                eventTriggers: ["BOOKING_CREATED"],
              };
              it("rejects a too-short secret", () => {
                const r = parseWebhookSubscription({ ...base, secret: "short" });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                expect(Object.keys(r.errors).some((k) => k.includes("secret")), JSON.stringify(Object.keys(r.errors))).toBe(true);
              });
              it("rejects a too-long secret", () => {
                const r = parseWebhookSubscription({ ...base, secret: "x".repeat(129) });
                expect(r.success).toBe(false);
              });
              it("accepts and preserves an in-range secret", () => {
                const r = parseWebhookSubscription({ ...base, secret: "abcd1234" });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect((r.data as any).secret).toBe("abcd1234");
              });
              it("omits absent secret rather than setting null", () => {
                const r = parseWebhookSubscription({ ...base });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect("secret" in (r.data as any)).toBe(false);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "secret bounds spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_active_default_and_explicit(self):
        """L2: `active` defaults to true when omitted but an explicit false is
        preserved (a naive impl that hardcodes true would fail the explicit
        case)."""
        body = textwrap.dedent(
            """\
            describe("active default vs explicit", () => {
              it("defaults to true when omitted", () => {
                const r = parseWebhookSubscription({
                  subscriberUrl: "https://x.test/hook",
                  eventTriggers: ["BOOKING_CREATED"],
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect((r.data as any).active).toBe(true);
              });
              it("preserves an explicit false", () => {
                const r = parseWebhookSubscription({
                  subscriberUrl: "https://x.test/hook",
                  eventTriggers: ["BOOKING_CREATED"],
                  active: false,
                });
                expect(r.success, JSON.stringify((r as any).errors)).toBe(true);
                if (!r.success) throw new Error("expected success");
                expect((r.data as any).active).toBe(false);
              });
            });
            """
        )
        res = _run_independent(body)
        assert res.returncode == 0, (
            "active default spec failed\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )

    def test_unknown_top_level_key_rejected(self):
        """L2: an extra top-level key `foo` is rejected (strict), with `foo`
        present in errors rather than silently dropped."""
        body = textwrap.dedent(
            """\
            describe("unknown top-level key", () => {
              it("rejects extra keys with the key name in errors", () => {
                const r = parseWebhookSubscription({
                  subscriberUrl: "https://x.test/hook",
                  eventTriggers: ["BOOKING_CREATED"],
                  foo: "surprise",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                expect(keys.some((k) => k === "foo" || k.includes("foo")), "expected foo in errors; keys=" + JSON.stringify(keys)).toBe(true);
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
        """L2: an input with an unknown `foo` key AND an empty eventTriggers
        array yields a failure whose errors include BOTH `foo` and
        `eventTriggers` (no stop-at-first-error)."""
        body = textwrap.dedent(
            """\
            describe("multi-error collection", () => {
              it("returns all violations together", () => {
                const r = parseWebhookSubscription({
                  subscriberUrl: "https://x.test/hook",
                  eventTriggers: [],
                  foo: "surprise",
                });
                expect(r.success).toBe(false);
                if (r.success) throw new Error("expected failure");
                const keys = Object.keys(r.errors);
                const hasFoo = keys.some((k) => k.includes("foo"));
                const hasTriggers = keys.some((k) => k.includes("eventTriggers"));
                expect(hasFoo, "missing foo; keys=" + JSON.stringify(keys)).toBe(true);
                expect(hasTriggers, "missing eventTriggers; keys=" + JSON.stringify(keys)).toBe(true);
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
        {success:false} without throwing, with an object `errors` map."""
        body = textwrap.dedent(
            """\
            describe("non-object inputs", () => {
              it("never throws on null/string/number/array", () => {
                for (const bad of [null, "oops", 42, undefined, []]) {
                  let r: any;
                  expect(() => { r = parseWebhookSubscription(bad as unknown); }).not.toThrow();
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
            "packages/lib/webhookSubscriptionSchema.test.ts", timeout=600
        )
        assert res.returncode == 0, (
            "agent's own webhookSubscriptionSchema.test.ts did not pass\n"
            f"STDOUT:\n{res.stdout[-4000:]}\nSTDERR:\n{res.stderr[-3000:]}"
        )
