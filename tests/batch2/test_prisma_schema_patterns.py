"""
Test for 'prisma-schema-patterns' skill (variant ext2) — Prisma connection-string
redactor for logging.

The task asks the agent to introduce a pure, self-contained helper module
`packages/prisma/connection-redact.ts` exporting
`redactConnectionString(url: string): string`, plus a Vitest unit test. The
function masks the password segment of a PostgreSQL connection string with the
fixed literal mask `****` while preserving scheme, username, host, port,
database name, and query parameters. It is pure: no I/O, no env reads, and it
must not pull in the generated Prisma client, the driver adapter, or `pg`.

These tests verify the deliverable INDEPENDENTLY of the agent's own test file:
they install a grader-owned Vitest spec into the prisma package that imports the
agent's `redactConnectionString` and exercises every masking / scheme-acceptance
/ throw / preservation / purity rule from the requirement doc via the repo's
native `yarn vitest run` toolchain. Because the grader owns the spec, a naive /
hardcoded redactor (one that returns a fixed string, ignores input, never
throws, or only masks one fixed shape) cannot pass by editing the agent test.

L1 -> deliverable files exist + minimally well-formed + structurally pure.
L2 -> dynamic execution against the real redactor behaviour.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/cal.com"
PRISMA_DIR = os.path.join(REPO_DIR, "packages", "prisma")
REDACT_TS = os.path.join(PRISMA_DIR, "connection-redact.ts")
REDACT_TEST_TS = os.path.join(PRISMA_DIR, "connection-redact.test.ts")

# A vitest spec we (the grader) own. It imports the agent's redactor from the
# sibling module and asserts the required behaviour. We control its contents so
# a naive / hardcoded redactor cannot pass by editing the agent-authored test.
VERIFY_SPEC_NAME = "connection-redact.benchverify.test.ts"
VERIFY_SPEC_PATH = os.path.join(PRISMA_DIR, VERIFY_SPEC_NAME)


def _run_vitest(spec_filename, timeout=600):
    """Run a single vitest spec scoped to the prisma package; return CompletedProcess."""
    rel = os.path.join("packages", "prisma", spec_filename)
    env = dict(os.environ)
    env["TZ"] = "UTC"
    env.pop("PYTHONPATH", None)
    cmd = ["yarn", "vitest", "run", rel]
    return subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


class TestPrismaSchemaPatterns:
    """Verify the Prisma connection-string redactor deliverable."""

    REPO_DIR = "/workspace/cal.com"

    # ------------------------------------------------------------------ #
    # Module / spec lifecycle
    # ------------------------------------------------------------------ #
    @classmethod
    def setup_class(cls):
        """Install our own verification vitest spec into the prisma package."""
        cls._spec_written = False
        if os.path.isdir(PRISMA_DIR) and os.path.isfile(REDACT_TS):
            with open(VERIFY_SPEC_PATH, "w") as fh:
                fh.write(cls._verify_spec_source())
            cls._spec_written = True
        cls._vitest_cache = {}

    @classmethod
    def teardown_class(cls):
        """Remove our verification spec so we don't pollute the repo."""
        if getattr(cls, "_spec_written", False):
            try:
                os.remove(VERIFY_SPEC_PATH)
            except OSError:
                pass

    @staticmethod
    def _verify_spec_source():
        return r"""
import { describe, it, expect } from "vitest";
// Import the agent-authored redactor. Importing this file alone must not pull
// in the generated prisma client / driver adapter / pg (purity / self-
// containment contract). If it did, vitest resolution would also drag those in.
import { redactConnectionString } from "./connection-redact";

const MASK = "****";

describe("benchverify redactConnectionString", () => {
  it("[T01] masks password on postgres:// scheme, preserving everything else", () => {
    const out = redactConnectionString("postgres://user:secret@localhost:5432/maindb");
    expect(out).toBe("postgres://user:****@localhost:5432/maindb");
    // password literal must be gone
    expect(out.includes("secret")).toBe(false);
  });

  it("[T02] masks password on postgresql:// scheme, preserving everything else", () => {
    const out = redactConnectionString("postgresql://admin:p4ssw0rd@db.internal:5432/app");
    expect(out).toBe("postgresql://admin:****@db.internal:5432/app");
    expect(out.includes("p4ssw0rd")).toBe(false);
  });

  it("[T03] preserves scheme exactly (no normalization between the two pg schemes)", () => {
    expect(redactConnectionString("postgres://u:p@h:5432/d").startsWith("postgres://")).toBe(true);
    expect(redactConnectionString("postgresql://u:p@h:5432/d").startsWith("postgresql://")).toBe(true);
    // must not turn postgres:// into postgresql:// or vice versa
    expect(redactConnectionString("postgres://u:p@h:5432/d").startsWith("postgresql://")).toBe(false);
  });

  it("[T04] preserves username exactly, masks only the password", () => {
    const out = redactConnectionString("postgresql://Alice_42:topsecret@host:5432/db");
    expect(out).toBe("postgresql://Alice_42:****@host:5432/db");
    expect(out.includes("Alice_42")).toBe(true);
    expect(out.includes("topsecret")).toBe(false);
  });

  it("[T05] no-password userinfo (user@host) is left unchanged", () => {
    const url = "postgresql://postgres@localhost:5432/db";
    expect(redactConnectionString(url)).toBe(url);
  });

  it("[T06] no-userinfo URL is left unchanged", () => {
    const url = "postgresql://localhost:5432/db";
    expect(redactConnectionString(url)).toBe(url);
    const url2 = "postgres://db-host:5432/main";
    expect(redactConnectionString(url2)).toBe(url2);
  });

  it("[T07] query parameters after ? are preserved verbatim", () => {
    const out = redactConnectionString(
      "postgresql://u:secret@h:5432/db?sslmode=require&connection_limit=5"
    );
    expect(out).toBe(
      "postgresql://u:****@h:5432/db?sslmode=require&connection_limit=5"
    );
    expect(out.includes("sslmode=require")).toBe(true);
    expect(out.includes("connection_limit=5")).toBe(true);
    expect(out.includes("secret")).toBe(false);
  });

  it("[T08] a query value that resembles a password is NOT masked", () => {
    // Only the userinfo password is masked; query content is preserved verbatim
    // even when it looks like 'password=...'. Here there is no userinfo password.
    const url = "postgresql://postgres@h:5432/db?password=lookslikeapw&sslmode=require";
    expect(redactConnectionString(url)).toBe(url);
    expect(redactConnectionString(url).includes("lookslikeapw")).toBe(true);
  });

  it("[T09] password with URL-encoded characters (%40) is fully masked", () => {
    const out = redactConnectionString("postgresql://u:pa%40ss%21word@h:5432/db");
    expect(out).toBe("postgresql://u:****@h:5432/db");
    expect(out.includes("%40")).toBe(false);
    expect(out.includes("pa")).toBe(true); // 'pa' only survives inside host/user? ensure not from pw
  });

  it("[T10] password containing a colon is masked entirely up to '@'", () => {
    const out = redactConnectionString("postgresql://user:pa:ss:word@host:5432/db");
    expect(out).toBe("postgresql://user:****@host:5432/db");
    // none of the colon-laden password fragments may survive
    expect(out.includes("pa:ss")).toBe(false);
    expect(out.includes("ss:word")).toBe(false);
    // host:port colon is untouched
    expect(out.includes("host:5432")).toBe(true);
  });

  it("[T11] host and port are never altered", () => {
    const out = redactConnectionString("postgresql://u:secret@my-replica.db.svc:6543/analytics");
    expect(out.includes("my-replica.db.svc:6543")).toBe(true);
    expect(out).toBe("postgresql://u:****@my-replica.db.svc:6543/analytics");
  });

  it("[T12] database name is preserved", () => {
    const out = redactConnectionString("postgres://u:secret@h:5432/very_specific_db_name");
    expect(out.endsWith("/very_specific_db_name")).toBe(true);
  });

  it("[T13] unsupported scheme throws an Error naming the scheme", () => {
    let msg = "";
    let threw = false;
    try {
      redactConnectionString("mysql://u:p@h:3306/db");
    } catch (e: any) {
      threw = true;
      msg = String(e && e.message);
    }
    expect(threw).toBe(true);
    expect(msg.length).toBeGreaterThan(0);
    // message must name the unsupported scheme (or at least signal scheme/postgres)
    expect(/mysql|scheme|postgres/i.test(msg)).toBe(true);
  });

  it("[T14] a second unsupported scheme also throws", () => {
    expect(() => redactConnectionString("http://u:p@h:80/db")).toThrow();
    expect(() => redactConnectionString("redis://u:p@h:6379/0")).toThrow();
  });

  it("[T15] empty-string input throws an Error", () => {
    expect(() => redactConnectionString("")).toThrow();
  });

  it("[T16] purity: equal input -> equal output, and process.env untouched", () => {
    const url = "postgresql://u:secret@h:5432/db?sslmode=require";
    const before = JSON.stringify(process.env);
    const a = redactConnectionString(url);
    const b = redactConnectionString(url);
    const after = JSON.stringify(process.env);
    expect(a).toBe(b);
    expect(after).toBe(before);
  });

  it("[T17] purity: redactor ignores ambient process.env (no env reads)", () => {
    const saved = process.env.DATABASE_URL;
    process.env.DATABASE_URL = "postgresql://AMBIENT:AMBIENTPW@ambient:5432/ambient";
    try {
      const out = redactConnectionString("postgresql://u:realsecret@h:5432/db");
      expect(out).toBe("postgresql://u:****@h:5432/db");
      expect(out.includes("AMBIENT")).toBe(false);
      expect(out.includes("realsecret")).toBe(false);
    } finally {
      if (saved === undefined) delete process.env.DATABASE_URL;
      else process.env.DATABASE_URL = saved;
    }
  });

  it("[T18] mask is exactly '****' (fixed literal, not the original length)", () => {
    const out = redactConnectionString(
      "postgresql://u:averyveryveryverylongpassword12345@h:5432/db"
    );
    expect(out).toBe("postgresql://u:****@h:5432/db");
    // The masked region is exactly 4 stars regardless of original length.
    const m = out.match(/:([*]+)@/);
    expect(m).not.toBeNull();
    expect((m as RegExpMatchArray)[1]).toBe(MASK);
  });
});
"""

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _vitest_verify(self):
        """Run the grader-owned spec once; cache the CompletedProcess."""
        if "verify" not in self._vitest_cache:
            assert getattr(type(self), "_spec_written", False), (
                "Verification spec was not written — connection-redact.ts is "
                "missing, so the redactor deliverable does not exist."
            )
            self._vitest_cache["verify"] = _run_vitest(VERIFY_SPEC_NAME)
        return self._vitest_cache["verify"]

    def _require_vitest_passed(self):
        proc = self._vitest_verify()
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "grader vitest spec failed (rc=%s).\n--- stdout ---\n%s\n--- stderr ---\n%s"
            % (proc.returncode, (proc.stdout or "")[-4000:], (proc.stderr or "")[-4000:])
        )
        return combined

    # ------------------------------------------------------------------ #
    # L1 — deliverable files exist and are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_l1_repo_present(self):
        """The prisma package directory must exist in the container."""
        assert os.path.isdir(PRISMA_DIR), f"{PRISMA_DIR} not found"

    def test_l1_connection_redact_exists(self):
        """packages/prisma/connection-redact.ts must be created and non-empty."""
        assert os.path.isfile(REDACT_TS), "connection-redact.ts not found"
        assert os.path.getsize(REDACT_TS) > 0, "connection-redact.ts is empty"

    def test_l1_exports_redactor_symbol(self):
        """connection-redact.ts must export a `redactConnectionString` function."""
        with open(REDACT_TS) as fh:
            src = fh.read()
        assert "redactConnectionString" in src, "redactConnectionString not referenced"
        assert re.search(
            r"export\s+(async\s+)?function\s+redactConnectionString|"
            r"export\s+const\s+redactConnectionString\s*=|"
            r"export\s*\{[^}]*\bredactConnectionString\b",
            src,
        ), "redactConnectionString is not exported from connection-redact.ts"

    def test_l1_redactor_module_is_self_contained(self):
        """Redactor must not import the generated client, the pg adapter, or pg.

        Structural guard for the purity / self-containment contract; behavioural
        purity is exercised in L2.
        """
        with open(REDACT_TS) as fh:
            src = fh.read()
        forbidden = [
            r"""from\s+['"]pg['"]""",
            r"""from\s+['"]@prisma/adapter-pg['"]""",
            r"""from\s+['"]\.?/?generated/prisma""",
            r"""from\s+['"]\./generated""",
            r"""from\s+['"]\./client['"]""",
        ]
        for pat in forbidden:
            assert not re.search(pat, src), (
                f"connection-redact.ts must not import {pat!r}; it must be a pure module"
            )

    def test_l1_redactor_does_not_read_env(self):
        """A pure redactor must not read process.env (structural sanity for purity)."""
        with open(REDACT_TS) as fh:
            src = fh.read()
        assert "process.env" not in src, (
            "connection-redact.ts must be pure and must not read process.env"
        )

    def test_l1_agent_test_exists(self):
        """packages/prisma/connection-redact.test.ts must be created by the agent."""
        assert os.path.isfile(REDACT_TEST_TS), "connection-redact.test.ts not found"
        assert os.path.getsize(REDACT_TEST_TS) > 0, "connection-redact.test.ts is empty"

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real redactor via native vitest
    # ------------------------------------------------------------------ #
    def test_l2_vitest_suite_passes_overall(self):
        """The grader-owned vitest spec for the redactor passes end-to-end."""
        combined = self._require_vitest_passed()
        assert "benchverify" in combined or "passed" in combined.lower(), (
            "vitest output does not reference the grader spec; suite may not have run"
        )

    def test_l2_masks_both_pg_schemes(self):
        """[T01][T02][T03] Password masked on both postgres:// and postgresql://; scheme preserved."""
        out = self._require_vitest_passed()
        assert "T01" in out and "T02" in out and "T03" in out, "scheme-masking cases did not run"

    def test_l2_preserves_username_and_no_password_userinfo(self):
        """[T04][T05] Username preserved; user-only (no password) userinfo unchanged."""
        out = self._require_vitest_passed()
        assert "T04" in out and "T05" in out, "username/no-password cases did not run"

    def test_l2_no_userinfo_unchanged(self):
        """[T06] URLs with no userinfo are returned unchanged."""
        out = self._require_vitest_passed()
        assert "T06" in out, "no-userinfo case did not run"

    def test_l2_query_params_preserved(self):
        """[T07][T08] Query params preserved verbatim; password-like query value not masked."""
        out = self._require_vitest_passed()
        assert "T07" in out and "T08" in out, "query-param preservation cases did not run"

    def test_l2_encoded_and_colon_passwords_masked(self):
        """[T09][T10] Encoded (%40) and colon-bearing passwords are fully masked."""
        out = self._require_vitest_passed()
        assert "T09" in out and "T10" in out, "encoded/colon password cases did not run"

    def test_l2_host_port_db_preserved(self):
        """[T11][T12] Host, port, and database name are never altered."""
        out = self._require_vitest_passed()
        assert "T11" in out and "T12" in out, "host/port/db preservation cases did not run"

    def test_l2_unsupported_scheme_throws(self):
        """[T13][T14] Non-postgres schemes throw an Error (named in T13)."""
        out = self._require_vitest_passed()
        assert "T13" in out and "T14" in out, "unsupported-scheme throw cases did not run"

    def test_l2_empty_string_throws(self):
        """[T15] Empty-string input throws an Error."""
        out = self._require_vitest_passed()
        assert "T15" in out, "empty-string throw case did not run"

    def test_l2_purity_and_env_isolation(self):
        """[T16][T17] Equal input -> equal output, env untouched, ambient env ignored."""
        out = self._require_vitest_passed()
        assert "T16" in out and "T17" in out, "purity cases did not run"

    def test_l2_mask_is_fixed_literal(self):
        """[T18] The mask is exactly '****' regardless of original password length."""
        out = self._require_vitest_passed()
        assert "T18" in out, "fixed-mask case did not run"

    def test_l2_naive_redactor_would_fail(self):
        """Meta-guard: the spec encodes >=18 discriminative cases beyond existence.

        A hardcoded redactor (one that returns a fixed string, ignores input,
        never throws, or only handles one URL shape) cannot satisfy the masking +
        preservation + throw + purity assertions, so a green vitest run is
        meaningful. We assert all 18 tagged cases executed.
        """
        out = self._require_vitest_passed()
        ran = {t for t in re.findall(r"T\d{2}", out)}
        expected = {f"T{i:02d}" for i in range(1, 19)}
        missing = expected - ran
        assert not missing, f"these redactor cases did not appear in vitest output: {sorted(missing)}"
