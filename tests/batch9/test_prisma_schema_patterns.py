"""
Test for 'prisma-schema-patterns' skill (variant ext9) — PostgreSQL
connection-string component parser for the Prisma package.

The ext9 task asks the agent to add a pure module
`packages/prisma/connection-parts.ts` exporting
`parseConnectionString(url: string)` that decomposes a PostgreSQL connection
string into structured components (scheme / user / host / port / database /
params), defaulting the port to 5432, returning null for absent
userinfo/database, never returning the password, and throwing on unsupported
schemes or non-numeric ports. The agent also adds a Vitest spec
`packages/prisma/connection-parts.test.ts`.

These tests verify the deliverable INDEPENDENTLY of the agent's own test file:
we inject our own grader-owned Vitest spec into the prisma package that imports
the agent's `parseConnectionString` and exercises every parsing / default /
purity / password-omission / throw rule from the requirement doc via the repo's
native `yarn vitest run` toolchain.

A naive implementation (hardcoded object, no port default, leaks the password,
never throws on a bad scheme) MUST fail the grader spec.

L1 -> deliverable files exist, are well-formed, export the symbol, and the
      module stays self-contained (no client / adapter / pg import, no I/O).
L2 -> dynamic execution of the real parser via native vitest.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/cal.com"
PRISMA_DIR = os.path.join(REPO_DIR, "packages", "prisma")
PARTS_TS = os.path.join(PRISMA_DIR, "connection-parts.ts")
PARTS_TEST_TS = os.path.join(PRISMA_DIR, "connection-parts.test.ts")

# A vitest spec we (the grader) own. It imports the agent's parser from the
# sibling module and asserts the required behaviour. We control its contents so
# a naive / hardcoded parser cannot pass by editing the agent-authored test.
VERIFY_SPEC_NAME = "connection-parts.benchverify.test.ts"
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
    """Verify the Prisma connection-string component parser deliverable."""

    REPO_DIR = "/workspace/cal.com"

    # ------------------------------------------------------------------ #
    # Grader spec lifecycle
    # ------------------------------------------------------------------ #
    @classmethod
    def setup_class(cls):
        """Install our own verification vitest spec into the prisma package."""
        cls._spec_written = False
        if os.path.isdir(PRISMA_DIR) and os.path.isfile(PARTS_TS):
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
// Import the agent-authored parser. Importing this file alone must not pull in
// the generated prisma client / driver adapter / pg (purity + self-containment).
import { parseConnectionString } from "./connection-parts";

const FULL = "postgresql://alice:s3cr3t@db.example.com:6543/appdb";
const NO_PORT = "postgresql://alice:s3cr3t@db.example.com/appdb";
const NO_DB = "postgresql://alice:s3cr3t@db.example.com:5432";
const NO_USER = "postgresql://db.example.com:5432/appdb";
const WITH_PARAMS =
  "postgresql://u:p@host:5432/db?sslmode=require&connection_limit=10";
const VALUELESS = "postgresql://u:p@host:5432/db?foo&sslmode=require";
const PWD = "postgresql://bob:TOPsecretPASSWORD@h:5432/d";

function hasValueDeep(obj: any, needle: string): boolean {
  if (obj === null || obj === undefined) return false;
  if (typeof obj === "string") return obj.includes(needle);
  if (typeof obj === "number" || typeof obj === "boolean") return false;
  if (Array.isArray(obj)) return obj.some((v) => hasValueDeep(v, needle));
  if (typeof obj === "object")
    return Object.values(obj).some((v) => hasValueDeep(v, needle));
  return false;
}

describe("benchverify parseConnectionString", () => {
  it("[T01] full URL: scheme/user/host/port/database parsed", () => {
    const r = parseConnectionString(FULL);
    expect(r.scheme).toBe("postgresql");
    expect(r.user).toBe("alice");
    expect(r.host).toBe("db.example.com");
    expect(r.port).toBe(6543);
    expect(typeof r.port).toBe("number");
    expect(r.database).toBe("appdb");
  });

  it("[T02] port defaults to 5432 when omitted", () => {
    const r = parseConnectionString(NO_PORT);
    expect(r.port).toBe(5432);
    expect(typeof r.port).toBe("number");
    expect(r.host).toBe("db.example.com");
    expect(r.database).toBe("appdb");
  });

  it("[T03] database is null when path omitted", () => {
    const r = parseConnectionString(NO_DB);
    expect(r.database).toBeNull();
    expect(r.host).toBe("db.example.com");
    expect(r.port).toBe(5432);
  });

  it("[T04] user extracted from userinfo", () => {
    const r = parseConnectionString(FULL);
    expect(r.user).toBe("alice");
  });

  it("[T05] user is null when no userinfo present", () => {
    const r = parseConnectionString(NO_USER);
    expect(r.user).toBeNull();
    expect(r.host).toBe("db.example.com");
    expect(r.database).toBe("appdb");
  });

  it("[T06] password never appears anywhere in the result", () => {
    const r = parseConnectionString(PWD);
    expect(hasValueDeep(r, "TOPsecretPASSWORD")).toBe(false);
    // also for the FULL url's password
    const r2 = parseConnectionString(FULL);
    expect(hasValueDeep(r2, "s3cr3t")).toBe(false);
    // and the user (a non-secret field) is still present, proving it isn't
    // simply dropping userinfo entirely.
    expect(r2.user).toBe("alice");
  });

  it("[T07] query parameters parsed into params as string key/values", () => {
    const r = parseConnectionString(WITH_PARAMS);
    expect(typeof r.params).toBe("object");
    expect(r.params).not.toBeNull();
    expect(r.params.sslmode).toBe("require");
    expect(r.params.connection_limit).toBe("10");
    // database must not absorb the query string
    expect(r.database).toBe("db");
  });

  it("[T08] no query string -> params is an empty object", () => {
    const r = parseConnectionString(FULL);
    expect(typeof r.params).toBe("object");
    expect(r.params).not.toBeNull();
    expect(Object.keys(r.params).length).toBe(0);
  });

  it("[T09] valueless query parameter maps to empty string", () => {
    const r = parseConnectionString(VALUELESS);
    expect(r.params.foo).toBe("");
    expect(r.params.sslmode).toBe("require");
  });

  it("[T10] unsupported scheme throws naming the scheme", () => {
    let msg = "";
    let threw = false;
    try {
      parseConnectionString("mysql://u:p@h:3306/d");
    } catch (e: any) {
      threw = true;
      msg = String(e && e.message);
    }
    expect(threw).toBe(true);
    expect(msg.length).toBeGreaterThan(0);
    expect(/mysql|scheme|unsupported|postgres/i.test(msg)).toBe(true);
  });

  it("[T11] empty string throws", () => {
    expect(() => parseConnectionString("")).toThrow();
  });

  it("[T12] non-numeric explicit port throws indicating invalid port", () => {
    let msg = "";
    let threw = false;
    try {
      parseConnectionString("postgresql://u:p@host:abc/db");
    } catch (e: any) {
      threw = true;
      msg = String(e && e.message);
    }
    expect(threw).toBe(true);
    expect(msg.length).toBeGreaterThan(0);
    expect(/port/i.test(msg)).toBe(true);
  });

  it("[T13] both postgres:// and postgresql:// schemes accepted", () => {
    const a = parseConnectionString("postgres://u:p@h:5432/d");
    const b = parseConnectionString("postgresql://u:p@h:5432/d");
    expect(a.scheme).toBe("postgres");
    expect(b.scheme).toBe("postgresql");
    expect(a.host).toBe("h");
    expect(b.host).toBe("h");
  });

  it("[T14] purity: equal inputs yield deep-equal outputs", () => {
    const r1 = parseConnectionString(WITH_PARAMS);
    const r2 = parseConnectionString(WITH_PARAMS);
    expect(r2).toEqual(r1);
  });

  it("[T15] purity: process.env untouched by parsing", () => {
    const before = JSON.stringify(process.env);
    parseConnectionString(FULL);
    parseConnectionString(WITH_PARAMS);
    const after = JSON.stringify(process.env);
    expect(after).toBe(before);
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
                "Verification spec was not written — connection-parts.ts is "
                "missing, so the parser deliverable does not exist."
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

    def test_l1_connection_parts_exists(self):
        """packages/prisma/connection-parts.ts must be created and non-empty."""
        assert os.path.isfile(PARTS_TS), "connection-parts.ts not found"
        assert os.path.getsize(PARTS_TS) > 0, "connection-parts.ts is empty"

    def test_l1_exports_parser_symbol(self):
        """connection-parts.ts must export a `parseConnectionString` function."""
        with open(PARTS_TS) as fh:
            src = fh.read()
        assert "parseConnectionString" in src, "parseConnectionString not referenced"
        assert re.search(
            r"export\s+(async\s+)?function\s+parseConnectionString|"
            r"export\s+const\s+parseConnectionString\s*=|"
            r"export\s*\{[^}]*\bparseConnectionString\b",
            src,
        ), "parseConnectionString is not exported from connection-parts.ts"

    def test_l1_parser_module_is_self_contained(self):
        """Parser must not import the generated client, the pg-adapter, or pg.

        Structural guard for the purity / self-containment contract; the
        behavioural purity is exercised in L2.
        """
        with open(PARTS_TS) as fh:
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
                f"connection-parts.ts must not import {pat!r}; it must be a pure module"
            )

    def test_l1_parser_does_no_obvious_io(self):
        """The parser must not read the environment or open connections.

        Guards the 'no I/O, no environment reads' contract structurally.
        """
        with open(PARTS_TS) as fh:
            src = fh.read()
        assert "process.env" not in src, (
            "connection-parts.ts reads process.env; the parser must be pure"
        )
        assert "new Pool" not in src, "connection-parts.ts must not open a pg Pool"

    def test_l1_agent_test_exists(self):
        """packages/prisma/connection-parts.test.ts must be created by the agent."""
        assert os.path.isfile(PARTS_TEST_TS), "connection-parts.test.ts not found"
        assert os.path.getsize(PARTS_TEST_TS) > 0, "connection-parts.test.ts is empty"

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real parser via native vitest
    # ------------------------------------------------------------------ #
    def test_l2_vitest_suite_passes_overall(self):
        """The grader-owned vitest spec for the parser passes end-to-end.

        Native acceptance command: `yarn vitest run packages/prisma/...`.
        """
        combined = self._require_vitest_passed()
        assert "benchverify" in combined or "passed" in combined.lower(), (
            "vitest output does not reference the grader spec; suite may not have run"
        )

    def test_l2_full_url_components(self):
        """[T01] Full URL parses scheme/user/host/numeric port/database."""
        out = self._require_vitest_passed()
        assert "T01" in out, "T01 (full URL) case did not run"

    def test_l2_default_port(self):
        """[T02] Port defaults to numeric 5432 when omitted."""
        out = self._require_vitest_passed()
        assert "T02" in out, "T02 (default port) case did not run"

    def test_l2_default_database_null(self):
        """[T03] database === null when the path is omitted."""
        out = self._require_vitest_passed()
        assert "T03" in out, "T03 (null database) case did not run"

    def test_l2_user_extraction_and_absence(self):
        """[T04][T05] user from userinfo; user === null without userinfo."""
        out = self._require_vitest_passed()
        assert "T04" in out and "T05" in out, "user extraction/absence cases did not run"

    def test_l2_password_never_leaked(self):
        """[T06] Password never appears anywhere in the result object."""
        out = self._require_vitest_passed()
        assert "T06" in out, "T06 (password omission) case did not run"

    def test_l2_query_params(self):
        """[T07][T08][T09] params parsed; empty when absent; valueless -> ''."""
        out = self._require_vitest_passed()
        assert "T07" in out and "T08" in out and "T09" in out, (
            "query-parameter cases did not run"
        )

    def test_l2_scheme_and_empty_throws(self):
        """[T10][T11][T13] Unsupported scheme + empty string throw; both pg schemes ok."""
        out = self._require_vitest_passed()
        assert "T10" in out and "T11" in out and "T13" in out, (
            "scheme validation / empty-string cases did not run"
        )

    def test_l2_invalid_port_throws(self):
        """[T12] Non-numeric explicit port throws naming the port."""
        out = self._require_vitest_passed()
        assert "T12" in out, "T12 (invalid port) case did not run"

    def test_l2_purity(self):
        """[T14][T15] Equal inputs -> deep-equal outputs; process.env untouched."""
        out = self._require_vitest_passed()
        assert "T14" in out and "T15" in out, "purity cases did not run"

    def test_l2_naive_parser_would_fail(self):
        """Meta-guard: the grader spec encodes >=15 discriminative cases.

        A hardcoded/stub parser (ignores input, no port default, leaks the
        password, never throws) cannot satisfy the throw + default + omission +
        purity assertions, so a green vitest run is meaningful. Assert every
        tagged case executed.
        """
        out = self._require_vitest_passed()
        ran = {t for t in re.findall(r"T\d{2}", out)}
        expected = {f"T{i:02d}" for i in range(1, 16)}
        missing = expected - ran
        assert not missing, (
            f"these parser cases did not appear in vitest output: {sorted(missing)}"
        )
