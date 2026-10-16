"""
Test for 'prisma-schema-patterns' skill (variant ext10) — schema/adapter
consistency checker for the @calcom/prisma package.

The task asks the agent to add a pure module
`packages/prisma/schema-consistency.ts` exporting
`checkSchemaConsistency(provider, connectionString)` plus a Vitest unit test
`packages/prisma/schema-consistency.test.ts`. The checker reports whether a
declared Prisma `provider` agrees with the engine implied by a runtime
connection string's scheme, using a fixed scheme->provider mapping, a special
CockroachDB/postgres-compatibility rule, case-insensitive matching, and
throwing for unrecognized providers / schemes. It must be importable on its
own without pulling in the generated Prisma client, the pg adapter, or pg, and
must be pure (no I/O, equal input -> deep-equal output).

Verification strategy: instead of trusting the agent's own test file, the
grader writes an INDEPENDENT Vitest spec into the prisma package that imports
the agent's `checkSchemaConsistency` and exercises every mapping / consistency
/ CockroachDB / case-insensitivity / throw rule from the requirement doc. It is
executed via the repo's native `yarn vitest run` toolchain.

L1 -> deliverable files exist, are well-formed, export the symbol, and are
structurally self-contained.
L2 -> dynamic execution of the real checker against discriminative cases that a
naive / hardcoded implementation (e.g. one that always returns consistent=true,
ignores the connection string, or never throws) cannot satisfy.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/cal.com"
PRISMA_DIR = os.path.join(REPO_DIR, "packages", "prisma")
CHECKER_TS = os.path.join(PRISMA_DIR, "schema-consistency.ts")
CHECKER_TEST_TS = os.path.join(PRISMA_DIR, "schema-consistency.test.ts")

# A vitest spec the grader owns. It imports the agent's checker from the sibling
# module and asserts the required behaviour. We control its contents so a naive
# checker cannot pass by editing the agent-authored test.
VERIFY_SPEC_NAME = "schema-consistency.benchverify.test.ts"
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
    """Verify the Prisma schema/adapter consistency-checker deliverable."""

    REPO_DIR = "/workspace/cal.com"

    # ------------------------------------------------------------------ #
    # Module / spec lifecycle
    # ------------------------------------------------------------------ #
    @classmethod
    def setup_class(cls):
        """Install the grader-owned verification vitest spec into the prisma package."""
        cls._spec_written = False
        if os.path.isdir(PRISMA_DIR) and os.path.isfile(CHECKER_TS):
            with open(VERIFY_SPEC_PATH, "w") as fh:
                fh.write(cls._verify_spec_source())
            cls._spec_written = True
        cls._vitest_cache = {}

    @classmethod
    def teardown_class(cls):
        """Remove the grader spec so we don't pollute the repo."""
        if getattr(cls, "_spec_written", False):
            try:
                os.remove(VERIFY_SPEC_PATH)
            except OSError:
                pass

    @staticmethod
    def _verify_spec_source():
        return r"""
import { describe, it, expect } from "vitest";
// Import the agent-authored checker. Importing this file alone must not pull in
// the generated prisma client / pg adapter / pg (self-containment contract).
import { checkSchemaConsistency } from "./schema-consistency";

const PG = "postgresql://u:p@localhost:5432/main";
const PG2 = "postgres://u:p@localhost:5432/main";
const MYSQL = "mysql://u:p@localhost:3306/main";
const MSSQL = "sqlserver://localhost:1433;database=main";
const SQLITE = "file:./dev.db";

describe("benchverify checkSchemaConsistency", () => {
  it("[T01] postgresql provider + postgres URL -> consistent, fields populated", () => {
    const r = checkSchemaConsistency("postgresql", PG);
    expect(r.consistent).toBe(true);
    expect(r.declaredProvider).toBe("postgresql");
    expect(r.connectionProvider).toBe("postgresql");
  });

  it("[T02] postgres:// (no -ql) scheme also maps to postgresql provider", () => {
    const r = checkSchemaConsistency("postgresql", PG2);
    expect(r.consistent).toBe(true);
    expect(r.connectionProvider).toBe("postgresql");
  });

  it("[T03] postgresql provider + mysql URL -> INCONSISTENT (no throw)", () => {
    const r = checkSchemaConsistency("postgresql", MYSQL);
    expect(r.consistent).toBe(false);
    expect(r.declaredProvider).toBe("postgresql");
    expect(r.connectionProvider).toBe("mysql");
  });

  it("[T04] mysql provider + mysql URL -> consistent", () => {
    const r = checkSchemaConsistency("mysql", MYSQL);
    expect(r.consistent).toBe(true);
    expect(r.declaredProvider).toBe("mysql");
    expect(r.connectionProvider).toBe("mysql");
  });

  it("[T05] sqlserver provider + sqlserver URL -> consistent", () => {
    const r = checkSchemaConsistency("sqlserver", MSSQL);
    expect(r.consistent).toBe(true);
    expect(r.declaredProvider).toBe("sqlserver");
    expect(r.connectionProvider).toBe("sqlserver");
  });

  it("[T06] sqlite provider + file: URL -> consistent", () => {
    const r = checkSchemaConsistency("sqlite", SQLITE);
    expect(r.consistent).toBe(true);
    expect(r.declaredProvider).toBe("sqlite");
    expect(r.connectionProvider).toBe("sqlite");
  });

  it("[T07] cockroachdb provider + postgres URL -> consistent despite differing names", () => {
    for (const url of [PG, PG2]) {
      const r = checkSchemaConsistency("cockroachdb", url);
      expect(r.consistent).toBe(true);
      expect(r.declaredProvider).toBe("cockroachdb");
      expect(r.connectionProvider).toBe("postgresql");
    }
  });

  it("[T08] cockroachdb provider + mysql URL -> INCONSISTENT (special-case is postgres-only)", () => {
    const r = checkSchemaConsistency("cockroachdb", MYSQL);
    expect(r.consistent).toBe(false);
    expect(r.connectionProvider).toBe("mysql");
  });

  it("[T09] mongodb provider + SQL URL -> INCONSISTENT, must NOT throw", () => {
    let r: any;
    expect(() => {
      r = checkSchemaConsistency("mongodb", PG);
    }).not.toThrow();
    expect(r.consistent).toBe(false);
    expect(r.declaredProvider).toBe("mongodb");
    // mongodb is a recognized provider; a SQL scheme is recognized too.
    const r2 = checkSchemaConsistency("mongodb", MYSQL);
    expect(r2.consistent).toBe(false);
  });

  it("[T10] case-insensitive provider matching (declared)", () => {
    const r = checkSchemaConsistency("POSTGRESQL", PG);
    expect(r.consistent).toBe(true);
    // normalized declared provider is lower-cased
    expect(r.declaredProvider).toBe("postgresql");
  });

  it("[T11] case-insensitive scheme matching (connection)", () => {
    const r = checkSchemaConsistency("postgresql", "POSTGRES://U:P@H:5432/D");
    expect(r.consistent).toBe(true);
    expect(r.connectionProvider).toBe("postgresql");
    const r2 = checkSchemaConsistency("MySQL", "MYSQL://u:p@h:3306/d");
    expect(r2.consistent).toBe(true);
    expect(r2.connectionProvider).toBe("mysql");
  });

  it("[T12] unknown declared provider -> throws naming the unknown provider", () => {
    let msg = "";
    expect(() => checkSchemaConsistency("oracle", PG)).toThrow();
    try {
      checkSchemaConsistency("oracle", PG);
    } catch (e: any) {
      msg = String(e && e.message);
    }
    expect(msg.length).toBeGreaterThan(0);
    expect(/oracle/i.test(msg)).toBe(true);
  });

  it("[T13] unsupported / missing connection scheme -> throws naming the scheme", () => {
    // Unrecognized scheme.
    let msg = "";
    expect(() => checkSchemaConsistency("postgresql", "http://x/y")).toThrow();
    try {
      checkSchemaConsistency("postgresql", "http://x/y");
    } catch (e: any) {
      msg = String(e && e.message);
    }
    expect(msg.length).toBeGreaterThan(0);
    expect(/http|scheme|unsupported/i.test(msg)).toBe(true);
    // Empty / missing connection string also throws.
    expect(() => checkSchemaConsistency("postgresql", "")).toThrow();
  });

  it("[T14] purity: equal inputs -> deep-equal outputs, no env mutation", () => {
    const before = JSON.stringify(process.env);
    const a = checkSchemaConsistency("postgresql", PG);
    const b = checkSchemaConsistency("postgresql", PG);
    const after = JSON.stringify(process.env);
    expect(b).toEqual(a);
    expect(after).toBe(before);
  });

  it("[T15] checker discriminates connection string (not hardcoded consistent=true)", () => {
    // Same declared provider, different schemes -> different consistency.
    const ok = checkSchemaConsistency("postgresql", PG);
    const bad = checkSchemaConsistency("postgresql", MYSQL);
    expect(ok.consistent).toBe(true);
    expect(bad.consistent).toBe(false);
    expect(ok.connectionProvider).not.toBe(bad.connectionProvider);
  });

  it("[T16] file: scheme is sqlite only; mismatched declared provider -> inconsistent", () => {
    const r = checkSchemaConsistency("postgresql", SQLITE);
    expect(r.consistent).toBe(false);
    expect(r.connectionProvider).toBe("sqlite");
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
                "Verification spec was not written — schema-consistency.ts is "
                "missing, so the checker deliverable does not exist."
            )
            self._vitest_cache["verify"] = _run_vitest(VERIFY_SPEC_NAME)
        return self._vitest_cache["verify"]

    def _require_vitest_passed(self):
        proc = self._vitest_verify()
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "grader vitest spec failed (rc=%s).\n--- stdout ---\n%s\n--- stderr ---\n%s"
            % (proc.returncode, proc.stdout[-4000:], proc.stderr[-4000:])
        )
        return combined

    # ------------------------------------------------------------------ #
    # L1 — deliverable files exist and are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_l1_repo_present(self):
        """The prisma package directory must exist in the container."""
        assert os.path.isdir(PRISMA_DIR), f"{PRISMA_DIR} not found"

    def test_l1_checker_module_exists(self):
        """packages/prisma/schema-consistency.ts must be created and non-empty."""
        assert os.path.isfile(CHECKER_TS), "schema-consistency.ts not found"
        assert os.path.getsize(CHECKER_TS) > 0, "schema-consistency.ts is empty"

    def test_l1_exports_checker_symbol(self):
        """schema-consistency.ts must export a `checkSchemaConsistency` function."""
        with open(CHECKER_TS) as fh:
            src = fh.read()
        assert "checkSchemaConsistency" in src, "checkSchemaConsistency not referenced"
        assert re.search(
            r"export\s+(async\s+)?function\s+checkSchemaConsistency|"
            r"export\s+const\s+checkSchemaConsistency\s*=|"
            r"export\s*\{[^}]*\bcheckSchemaConsistency\b",
            src,
        ), "checkSchemaConsistency is not exported from schema-consistency.ts"

    def test_l1_module_is_self_contained(self):
        """Checker must not import the generated client, the pg adapter, or pg.

        Structural guard for the purity / self-containment contract; behavioural
        purity is exercised in L2.
        """
        with open(CHECKER_TS) as fh:
            src = fh.read()
        forbidden = [
            r"""from\s+['"]pg['"]""",
            r"""from\s+['"]@prisma/adapter-pg['"]""",
            r"""from\s+['"]@prisma/client['"]""",
            r"""from\s+['"]\.?/?generated/prisma""",
            r"""from\s+['"]\./generated""",
            r"""from\s+['"]\./index['"]""",
        ]
        for pat in forbidden:
            assert not re.search(pat, src), (
                f"schema-consistency.ts must not import {pat!r}; it must be a pure module"
            )

    def test_l1_agent_test_exists(self):
        """packages/prisma/schema-consistency.test.ts must be created by the agent."""
        assert os.path.isfile(CHECKER_TEST_TS), "schema-consistency.test.ts not found"
        assert os.path.getsize(CHECKER_TEST_TS) > 0, "schema-consistency.test.ts is empty"

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real checker via native vitest
    # ------------------------------------------------------------------ #
    def test_l2_vitest_suite_passes_overall(self):
        """The grader-owned vitest spec for the checker passes end-to-end."""
        combined = self._require_vitest_passed()
        assert "benchverify" in combined or "passed" in combined.lower(), (
            "vitest output does not reference the grader spec; suite may not have run"
        )

    def test_l2_postgres_mapping_and_consistency(self):
        """[T01][T02] postgresql provider + postgres:// / postgresql:// -> consistent."""
        out = self._require_vitest_passed()
        assert "T01" in out and "T02" in out, "postgres mapping cases did not run"

    def test_l2_mismatch_is_inconsistent_no_throw(self):
        """[T03] postgresql provider + mysql URL -> consistent=false, no throw."""
        out = self._require_vitest_passed()
        assert "T03" in out, "provider/connection mismatch case did not run"

    def test_l2_mysql_sqlserver_sqlite_mappings(self):
        """[T04][T05][T06] mysql, sqlserver, and file:->sqlite mappings consistent."""
        out = self._require_vitest_passed()
        assert "T04" in out and "T05" in out and "T06" in out, "engine mapping cases did not run"

    def test_l2_cockroachdb_postgres_compat(self):
        """[T07][T08] cockroachdb consistent with postgres URL, inconsistent otherwise."""
        out = self._require_vitest_passed()
        assert "T07" in out and "T08" in out, "cockroachdb compatibility cases did not run"

    def test_l2_mongodb_no_throw_inconsistent(self):
        """[T09] mongodb provider + SQL URL -> inconsistent and must not throw."""
        out = self._require_vitest_passed()
        assert "T09" in out, "mongodb case did not run"

    def test_l2_case_insensitive_matching(self):
        """[T10][T11] provider and scheme matching are case-insensitive."""
        out = self._require_vitest_passed()
        assert "T10" in out and "T11" in out, "case-insensitivity cases did not run"

    def test_l2_throw_rules(self):
        """[T12][T13] unknown provider and unsupported/missing scheme throw."""
        out = self._require_vitest_passed()
        assert "T12" in out and "T13" in out, "throw-rule cases did not run"

    def test_l2_purity(self):
        """[T14] equal inputs -> deep-equal outputs; process.env untouched."""
        out = self._require_vitest_passed()
        assert "T14" in out, "purity case did not run"

    def test_l2_naive_checker_would_fail(self):
        """Meta-guard: the spec encodes >=16 discriminative cases beyond existence.

        A hardcoded checker (always consistent=true, ignores the connection
        string, or never throws) cannot satisfy the mismatch ([T03][T15][T16]),
        CockroachDB special-case ([T07][T08]), mongodb-no-throw ([T09]), and
        throw ([T12][T13]) assertions simultaneously, so a green vitest run is
        meaningful. We assert all 16 tagged cases executed.
        """
        out = self._require_vitest_passed()
        ran = {t for t in re.findall(r"T\d{2}", out)}
        expected = {f"T{i:02d}" for i in range(1, 17)}
        missing = expected - ran
        assert not missing, f"these checker cases did not appear in vitest output: {sorted(missing)}"
