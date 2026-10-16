"""
Test for 'prisma-schema-patterns' skill (variant ext3) — Prisma driver-adapter selector.

The task asks the agent to introduce a pure, self-contained module
`packages/prisma/adapter-selector.ts` exporting `selectAdapter(connectionString)`
that maps a database connection string's URL *scheme* to a static descriptor
naming the Prisma driver adapter and underlying JS driver package, plus a Vitest
unit test `packages/prisma/adapter-selector.test.ts`.

The selector must:
  - postgres:// | postgresql:// -> provider "postgresql",
        adapterPackage "@prisma/adapter-pg",            driverPackage "pg"
  - mysql://                    -> provider "mysql",
        adapterPackage "@prisma/adapter-mariadb",       driverPackage "mariadb"
  - file:        (SQLite)       -> provider "sqlite",
        adapterPackage "@prisma/adapter-better-sqlite3", driverPackage "better-sqlite3"
  - sqlserver://                -> provider "sqlserver",
        adapterPackage "@prisma/adapter-mssql",          driverPackage "node-mssql"
  - mongodb:// | mongodb+srv:// -> throw (MongoDB has no SQL driver adapter)
  - unknown / empty scheme      -> throw naming the unsupported scheme
  - scheme detection is case-insensitive for the scheme token only
  - it is PURE: no I/O, no env reads, constructs no adapter/connection, and the
    descriptor contains no live connection string or credentials.

Verification strategy:
  L1 -> deliverable files exist, are minimally well-formed, export the symbol,
        and the module is structurally self-contained (no client/adapter/driver
        imports — it must only return static identifiers).
  L2 -> a GRADER-OWNED Vitest spec is injected into the prisma package, imports
        the agent's `selectAdapter`, and dynamically exercises every mapping /
        throw / case-insensitivity / purity rule via the repo's native
        `yarn vitest run` toolchain. We own this spec, so a naive/hardcoded
        implementation cannot pass by editing the agent's own test file.

Native acceptance command driven by L2:
    yarn vitest run packages/prisma/adapter-selector.test.ts
(the grader runs the equivalent on its own injected spec file).
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/cal.com"
PRISMA_DIR = os.path.join(REPO_DIR, "packages", "prisma")
SELECTOR_TS = os.path.join(PRISMA_DIR, "adapter-selector.ts")
SELECTOR_TEST_TS = os.path.join(PRISMA_DIR, "adapter-selector.test.ts")

# A vitest spec the grader owns. It imports the agent's selector from the sibling
# module and asserts the required behaviour. Because we control its contents, a
# hardcoded / stubbed selector cannot pass by editing the agent-authored test.
VERIFY_SPEC_NAME = "adapter-selector.benchverify.test.ts"
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
    """Verify the Prisma driver-adapter selector deliverable (ext3)."""

    REPO_DIR = "/workspace/cal.com"

    # ------------------------------------------------------------------ #
    # Grader-owned spec lifecycle
    # ------------------------------------------------------------------ #
    @classmethod
    def setup_class(cls):
        """Install our own verification vitest spec into the prisma package."""
        cls._spec_written = False
        if os.path.isdir(PRISMA_DIR) and os.path.isfile(SELECTOR_TS):
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
// Import the agent-authored selector. Importing this file alone must not pull
// in the generated prisma client, any adapter, or any driver (purity contract).
import { selectAdapter } from "./adapter-selector";

// Expected static descriptors per the requirement doc.
const EXPECT = {
  postgresql: { provider: "postgresql", adapterPackage: "@prisma/adapter-pg", driverPackage: "pg" },
  mysql: { provider: "mysql", adapterPackage: "@prisma/adapter-mariadb", driverPackage: "mariadb" },
  sqlite: { provider: "sqlite", adapterPackage: "@prisma/adapter-better-sqlite3", driverPackage: "better-sqlite3" },
  sqlserver: { provider: "sqlserver", adapterPackage: "@prisma/adapter-mssql", driverPackage: "node-mssql" },
};

function assertDescriptor(d: any, exp: { provider: string; adapterPackage: string; driverPackage: string }) {
  expect(d).toBeTruthy();
  expect(typeof d).toBe("object");
  expect(d.provider).toBe(exp.provider);
  expect(d.adapterPackage).toBe(exp.adapterPackage);
  expect(d.driverPackage).toBe(exp.driverPackage);
}

describe("benchverify selectAdapter", () => {
  it("[T01] postgres:// -> postgresql / adapter-pg / pg", () => {
    assertDescriptor(selectAdapter("postgres://u:p@localhost:5432/main"), EXPECT.postgresql);
  });

  it("[T02] postgresql:// -> postgresql / adapter-pg / pg", () => {
    assertDescriptor(selectAdapter("postgresql://u:p@db:5432/main"), EXPECT.postgresql);
  });

  it("[T03] mysql:// -> mysql / adapter-mariadb / mariadb", () => {
    assertDescriptor(selectAdapter("mysql://u:p@localhost:3306/db"), EXPECT.mysql);
  });

  it("[T04] file: (SQLite) -> sqlite / adapter-better-sqlite3 / better-sqlite3", () => {
    assertDescriptor(selectAdapter("file:./dev.db"), EXPECT.sqlite);
  });

  it("[T05] sqlserver:// -> sqlserver / adapter-mssql / node-mssql", () => {
    assertDescriptor(selectAdapter("sqlserver://sa:p@localhost:1433;database=main"), EXPECT.sqlserver);
  });

  it("[T06] mongodb:// throws an Error mentioning MongoDB / SQL driver adapter", () => {
    let err: any = undefined;
    try {
      selectAdapter("mongodb://u:p@localhost:27017/db");
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(Error);
    expect(/mongo/i.test(String(err.message))).toBe(true);
  });

  it("[T07] mongodb+srv:// throws an Error mentioning MongoDB", () => {
    let err: any = undefined;
    try {
      selectAdapter("mongodb+srv://u:p@cluster0.example.net/db");
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(Error);
    expect(/mongo/i.test(String(err.message))).toBe(true);
  });

  it("[T08] unknown scheme throws an Error naming the unsupported scheme", () => {
    let err: any = undefined;
    try {
      selectAdapter("oracle://u:p@localhost:1521/db");
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(Error);
    // The message must name the offending scheme so it is diagnosable.
    expect(/oracle/i.test(String(err.message))).toBe(true);
  });

  it("[T09] empty string throws an Error", () => {
    let err: any = undefined;
    try {
      selectAdapter("");
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(Error);
  });

  it("[T10] string with no scheme separator throws an Error", () => {
    let err: any = undefined;
    try {
      selectAdapter("just-a-bare-host-name");
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(Error);
  });

  it("[T11] case-insensitive scheme: POSTGRES:// -> postgresql descriptor", () => {
    assertDescriptor(selectAdapter("POSTGRES://U:P@HOST:5432/MAIN"), EXPECT.postgresql);
  });

  it("[T12] case-insensitive scheme: MySQL:// and FILE: and SqlServer://", () => {
    assertDescriptor(selectAdapter("MySQL://u:p@h:3306/db"), EXPECT.mysql);
    assertDescriptor(selectAdapter("FILE:./dev.db"), EXPECT.sqlite);
    assertDescriptor(selectAdapter("SqlServer://sa:p@h:1433;database=d"), EXPECT.sqlserver);
  });

  it("[T13] provider is normalized to lowercase canonical regardless of input casing", () => {
    const d = selectAdapter("PostgreSQL://u:p@h:5432/d");
    expect(d.provider).toBe("postgresql");
    expect(d.adapterPackage).toBe("@prisma/adapter-pg");
    expect(d.driverPackage).toBe("pg");
  });

  it("[T14] descriptor leaks no credentials / connection string / constructed object", () => {
    const url = "postgresql://secretuser:secretpass@privatehost:5432/secretdb";
    const d = selectAdapter(url);
    const blob = JSON.stringify(d);
    expect(blob.includes("secretuser")).toBe(false);
    expect(blob.includes("secretpass")).toBe(false);
    expect(blob.includes("privatehost")).toBe(false);
    expect(blob.includes("secretdb")).toBe(false);
    // No connection string echoed back anywhere in the descriptor values.
    for (const v of Object.values(d as Record<string, unknown>)) {
      if (typeof v === "string") {
        expect(v.includes("://")).toBe(false);
      } else {
        // Only static string identifiers are allowed in the descriptor.
        expect(["string"]).toContain(typeof v);
      }
    }
  });

  it("[T15] purity: equal input -> deep-equal output, no env reads observable", () => {
    const url = "mysql://u:p@h:3306/db";
    const a = selectAdapter(url);
    const b = selectAdapter(url);
    expect(b).toEqual(a);
    // Distinct calls must not share/mutate a single object reference in a way
    // that lets one caller corrupt another's descriptor.
    (a as any).provider = "__tampered__";
    const c = selectAdapter(url);
    expect(c.provider).toBe("mysql");
  });

  it("[T16] selector ignores ambient process.env entirely (pure of env)", () => {
    const saved = process.env.DATABASE_URL;
    process.env.DATABASE_URL = "mongodb://AMBIENT/db";
    try {
      // Passing an explicit postgres URL must win regardless of env.
      assertDescriptor(selectAdapter("postgres://u:p@h:5432/d"), EXPECT.postgresql);
    } finally {
      if (saved === undefined) delete process.env.DATABASE_URL;
      else process.env.DATABASE_URL = saved;
    }
  });

  it("[T17] mysql is mapped to the mariadb adapter/driver, not adapter-pg/pg", () => {
    const d = selectAdapter("mysql://u:p@h:3306/db");
    expect(d.adapterPackage).not.toBe("@prisma/adapter-pg");
    expect(d.driverPackage).not.toBe("pg");
    expect(d.adapterPackage).toBe("@prisma/adapter-mariadb");
    expect(d.driverPackage).toBe("mariadb");
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
                "Verification spec was not written — adapter-selector.ts is "
                "missing, so the selector deliverable does not exist."
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

    def test_l1_adapter_selector_exists(self):
        """packages/prisma/adapter-selector.ts must be created and non-empty."""
        assert os.path.isfile(SELECTOR_TS), "adapter-selector.ts not found"
        assert os.path.getsize(SELECTOR_TS) > 0, "adapter-selector.ts is empty"

    def test_l1_exports_selector_symbol(self):
        """adapter-selector.ts must export a `selectAdapter` function."""
        with open(SELECTOR_TS) as fh:
            src = fh.read()
        assert "selectAdapter" in src, "selectAdapter not referenced"
        assert re.search(
            r"export\s+(async\s+)?function\s+selectAdapter|"
            r"export\s+const\s+selectAdapter\s*=|"
            r"export\s*\{[^}]*\bselectAdapter\b",
            src,
        ), "selectAdapter is not exported from adapter-selector.ts"

    def test_l1_selector_module_is_self_contained(self):
        """Selector must not import the generated client, any adapter, or any driver.

        It returns only static identifiers, so importing real adapter/driver
        packages would violate the purity / self-containment contract. This is a
        structural guard; behavioural purity is exercised in L2.
        """
        with open(SELECTOR_TS) as fh:
            src = fh.read()
        forbidden = [
            r"""from\s+['"]pg['"]""",
            r"""from\s+['"]mariadb['"]""",
            r"""from\s+['"]better-sqlite3['"]""",
            r"""from\s+['"]@prisma/adapter-pg['"]""",
            r"""from\s+['"]@prisma/adapter-mariadb['"]""",
            r"""from\s+['"]@prisma/adapter-better-sqlite3['"]""",
            r"""from\s+['"]@prisma/adapter-mssql['"]""",
            r"""from\s+['"]\.?/?generated/prisma""",
            r"""from\s+['"]\./generated""",
        ]
        for pat in forbidden:
            assert not re.search(pat, src), (
                f"adapter-selector.ts must not import {pat!r}; it must be a pure descriptor module"
            )

    def test_l1_selector_constructs_no_adapter(self):
        """The module must not instantiate an adapter / pool / driver (`new ...`).

        A descriptor is static data; constructing PrismaPg / Pool / a driver
        client would mean the module is doing I/O-capable work rather than pure
        mapping.
        """
        with open(SELECTOR_TS) as fh:
            src = fh.read()
        for ctor in ["new PrismaPg", "new Pool", "new PrismaMariaDb", "new PrismaMssql"]:
            assert ctor not in src, f"adapter-selector.ts must not construct {ctor!r}"

    def test_l1_agent_test_exists(self):
        """packages/prisma/adapter-selector.test.ts must be created by the agent."""
        assert os.path.isfile(SELECTOR_TEST_TS), "adapter-selector.test.ts not found"
        assert os.path.getsize(SELECTOR_TEST_TS) > 0, "adapter-selector.test.ts is empty"

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real selector via native vitest
    # ------------------------------------------------------------------ #
    def test_l2_vitest_suite_passes_overall(self):
        """The grader-owned vitest spec for the selector passes end-to-end."""
        combined = self._require_vitest_passed()
        assert "benchverify" in combined or "passed" in combined.lower(), (
            "vitest output does not reference the grader spec; suite may not have run"
        )

    def test_l2_postgres_mapping(self):
        """[T01][T02] postgres:// and postgresql:// both map to adapter-pg / pg."""
        out = self._require_vitest_passed()
        assert "T01" in out and "T02" in out, "postgres mapping cases did not run"

    def test_l2_mysql_mapping(self):
        """[T03][T17] mysql:// maps to adapter-mariadb / mariadb (not adapter-pg/pg)."""
        out = self._require_vitest_passed()
        assert "T03" in out and "T17" in out, "mysql mapping cases did not run"

    def test_l2_sqlite_mapping(self):
        """[T04] file: maps to adapter-better-sqlite3 / better-sqlite3."""
        out = self._require_vitest_passed()
        assert "T04" in out, "sqlite mapping case did not run"

    def test_l2_sqlserver_mapping(self):
        """[T05] sqlserver:// maps to adapter-mssql / node-mssql."""
        out = self._require_vitest_passed()
        assert "T05" in out, "sqlserver mapping case did not run"

    def test_l2_mongodb_rejected(self):
        """[T06][T07] mongodb:// and mongodb+srv:// throw a MongoDB-naming Error."""
        out = self._require_vitest_passed()
        assert "T06" in out and "T07" in out, "mongodb rejection cases did not run"

    def test_l2_unsupported_and_empty_scheme_throw(self):
        """[T08][T09][T10] unknown scheme, empty string, and no-scheme all throw."""
        out = self._require_vitest_passed()
        assert "T08" in out and "T09" in out and "T10" in out, "throw cases did not run"

    def test_l2_case_insensitive_scheme(self):
        """[T11][T12][T13] scheme detection is case-insensitive, provider normalized."""
        out = self._require_vitest_passed()
        assert "T11" in out and "T12" in out and "T13" in out, "case-insensitivity cases did not run"

    def test_l2_descriptor_leaks_no_credentials(self):
        """[T14] descriptor contains no connection string / credentials."""
        out = self._require_vitest_passed()
        assert "T14" in out, "credential-leak case did not run"

    def test_l2_purity(self):
        """[T15][T16] equal input -> equal output; ambient process.env is ignored."""
        out = self._require_vitest_passed()
        assert "T15" in out and "T16" in out, "purity cases did not run"

    def test_l2_naive_selector_would_fail(self):
        """Meta-guard: the spec encodes >=17 discriminative cases beyond existence.

        A hardcoded selector (e.g. one that always returns the postgres
        descriptor, never throws, or ignores casing) cannot satisfy the mapping +
        throw + case-insensitivity + leak assertions, so a green vitest run is
        meaningful. We assert all 17 tagged cases executed.
        """
        out = self._require_vitest_passed()
        ran = {t for t in re.findall(r"T\d{2}", out)}
        expected = {f"T{i:02d}" for i in range(1, 18)}
        missing = expected - ran
        assert not missing, f"these selector cases did not appear in vitest output: {sorted(missing)}"
