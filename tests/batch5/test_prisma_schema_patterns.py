"""
Test for 'prisma-schema-patterns' skill (variant ext5) — Prisma datasource-block parser.

The ext5 task asks the agent to add a pure parser module
`packages/prisma/schema-datasource.ts` exporting `parseDatasource(schemaText)`
plus a Vitest unit test `packages/prisma/schema-datasource.test.ts`. The parser
extracts the `datasource <name> { ... }` block from raw Prisma schema text and
returns at least:

    { provider, urlEnv, directUrlEnv }

where `provider` is the unquoted provider literal, and `urlEnv` / `directUrlEnv`
are the inner env-variable name when `url` / `directUrl` are `env("NAME")` calls
(else `null`). It must be pure (no I/O, no env reads), tolerate whitespace,
ignore `//` comment lines, only parse the FIRST datasource block, accept any
datasource block name, and throw on a missing block or a missing `provider` key.

Verification strategy (independent of the agent's own test file):
- L1 -> the deliverable module + agent test exist, export the symbol, and are
  structurally self-contained (no engine/client/pg/file-IO imports).
- L2 -> we inject our OWN grader-owned Vitest spec
  (`schema-datasource.benchverify.test.ts`) that imports the agent's
  `parseDatasource` and exercises every extraction / env-handling /
  comment-skipping / whitespace / first-block-only / throw rule from the doc,
  then drive it via the repo's native `yarn vitest run` toolchain. Because the
  grader owns the spec, a naive/stubbed parser (hardcoded provider, ignored
  input, never-throws) cannot pass by editing the agent-authored test.

Native acceptance command driven by L2:
    yarn vitest run packages/prisma/schema-datasource.benchverify.test.ts
(the doc's acceptance command is the analogous
    yarn vitest run packages/prisma/schema-datasource.test.ts)
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/cal.com"
PRISMA_DIR = os.path.join(REPO_DIR, "packages", "prisma")
PARSER_TS = os.path.join(PRISMA_DIR, "schema-datasource.ts")
PARSER_TEST_TS = os.path.join(PRISMA_DIR, "schema-datasource.test.ts")

# A vitest spec the grader owns. It imports the agent's parser from the sibling
# module and asserts the required behaviour. We control its contents so a naive
# / hardcoded parser cannot pass by editing the agent-authored test.
VERIFY_SPEC_NAME = "schema-datasource.benchverify.test.ts"
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
    """Verify the Prisma datasource-block parser deliverable (ext5)."""

    REPO_DIR = "/workspace/cal.com"

    # ------------------------------------------------------------------ #
    # Module / spec lifecycle
    # ------------------------------------------------------------------ #
    @classmethod
    def setup_class(cls):
        """Install our own verification vitest spec into the prisma package."""
        cls._spec_written = False
        if os.path.isdir(PRISMA_DIR) and os.path.isfile(PARSER_TS):
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
// the generated prisma client / driver adapter / pg / node:fs (purity contract).
import { parseDatasource } from "./schema-datasource";

const CANONICAL = `
// This is your Prisma Schema file
datasource db {
  provider  = "postgresql"
  url       = env("DATABASE_URL")
  directUrl = env("DATABASE_DIRECT_URL")
}

generator client {
  provider = "prisma-client"
}
`;

describe("benchverify parseDatasource", () => {
  it("[T01] extracts the provider literal with quotes stripped", () => {
    const d = parseDatasource(CANONICAL);
    expect(d.provider).toBe("postgresql");
  });

  it("[T02] extracts urlEnv from env(\"DATABASE_URL\")", () => {
    const d = parseDatasource(CANONICAL);
    expect(d.urlEnv).toBe("DATABASE_URL");
  });

  it("[T03] extracts directUrlEnv from env(\"DATABASE_DIRECT_URL\")", () => {
    const d = parseDatasource(CANONICAL);
    expect(d.directUrlEnv).toBe("DATABASE_DIRECT_URL");
  });

  it("[T04] a plain (non-env) url literal yields urlEnv === null", () => {
    const text = `
datasource db {
  provider = "postgresql"
  url      = "postgresql://u:p@localhost:5432/db"
}
`;
    const d = parseDatasource(text);
    expect(d.provider).toBe("postgresql");
    expect(d.urlEnv).toBeNull();
  });

  it("[T05] an absent directUrl yields directUrlEnv === null", () => {
    const text = `
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}
`;
    const d = parseDatasource(text);
    expect(d.urlEnv).toBe("DATABASE_URL");
    expect(d.directUrlEnv).toBeNull();
  });

  it("[T06] tolerant to extra/irregular whitespace around = and env()", () => {
    const text = `
datasource    db    {
        provider      =     "postgresql"
   url=env(   "DATABASE_URL"   )
    directUrl   =   env("DATABASE_DIRECT_URL")
}
`;
    const d = parseDatasource(text);
    expect(d.provider).toBe("postgresql");
    expect(d.urlEnv).toBe("DATABASE_URL");
    expect(d.directUrlEnv).toBe("DATABASE_DIRECT_URL");
  });

  it("[T07] // comment lines inside the block are ignored, not parsed as keys", () => {
    const text = `
datasource db {
  // provider = "mysql"
  provider = "postgresql"
  // url = env("WRONG_URL")
  url = env("DATABASE_URL")
}
`;
    const d = parseDatasource(text);
    expect(d.provider).toBe("postgresql");
    expect(d.urlEnv).toBe("DATABASE_URL");
  });

  it("[T08] accepts an arbitrary datasource block name (not just 'db')", () => {
    const text = `
datasource mycustomDS {
  provider = "postgresql"
  url      = env("PG_URL")
}
`;
    const d = parseDatasource(text);
    expect(d.provider).toBe("postgresql");
    expect(d.urlEnv).toBe("PG_URL");
  });

  it("[T09] only the FIRST datasource block is parsed; later blocks ignored", () => {
    const text = `
datasource db {
  provider = "postgresql"
  url      = env("PRIMARY_URL")
}

datasource other {
  provider = "mysql"
  url      = env("SECONDARY_URL")
}
`;
    const d = parseDatasource(text);
    expect(d.provider).toBe("postgresql");
    expect(d.urlEnv).toBe("PRIMARY_URL");
  });

  it("[T10] no datasource block -> throws an Error mentioning datasource", () => {
    const text = `
generator client {
  provider = "prisma-client"
}
`;
    expect(() => parseDatasource(text)).toThrow();
    let msg = "";
    try {
      parseDatasource(text);
    } catch (e) {
      msg = String((e && e.message) || e);
    }
    expect(msg.length).toBeGreaterThan(0);
    expect(/datasource/i.test(msg)).toBe(true);
  });

  it("[T11] missing provider key -> throws an Error naming provider", () => {
    const text = `
datasource db {
  url = env("DATABASE_URL")
}
`;
    expect(() => parseDatasource(text)).toThrow();
    let msg = "";
    try {
      parseDatasource(text);
    } catch (e) {
      msg = String((e && e.message) || e);
    }
    expect(msg.length).toBeGreaterThan(0);
    expect(/provider/i.test(msg)).toBe(true);
  });

  it("[T12] purity: equal inputs -> deep-equal outputs", () => {
    const a = parseDatasource(CANONICAL);
    const b = parseDatasource(CANONICAL);
    expect(b).toEqual(a);
  });

  it("[T13] purity: process.env is untouched by parsing", () => {
    const before = JSON.stringify(process.env);
    parseDatasource(CANONICAL);
    const after = JSON.stringify(process.env);
    expect(after).toBe(before);
  });

  it("[T14] parser is value-driven, not hardcoded (different env names round-trip)", () => {
    const text = `
datasource db {
  provider  = "postgresql"
  url       = env("CUSTOM_PRIMARY")
  directUrl = env("CUSTOM_DIRECT")
}
`;
    const d = parseDatasource(text);
    expect(d.urlEnv).toBe("CUSTOM_PRIMARY");
    expect(d.directUrlEnv).toBe("CUSTOM_DIRECT");
    // And it must NOT just echo the canonical names back.
    expect(d.urlEnv).not.toBe("DATABASE_URL");
  });

  it("[T15] non-postgresql provider value is returned verbatim (not coerced)", () => {
    const text = `
datasource db {
  provider = "sqlite"
  url      = env("FILE_URL")
}
`;
    const d = parseDatasource(text);
    expect(d.provider).toBe("sqlite");
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
                "Verification spec was not written — schema-datasource.ts is "
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

    def test_l1_parser_module_exists(self):
        """packages/prisma/schema-datasource.ts must be created and non-empty."""
        assert os.path.isfile(PARSER_TS), "schema-datasource.ts not found"
        assert os.path.getsize(PARSER_TS) > 0, "schema-datasource.ts is empty"

    def test_l1_exports_parser_symbol(self):
        """schema-datasource.ts must export a `parseDatasource` function."""
        with open(PARSER_TS) as fh:
            src = fh.read()
        assert "parseDatasource" in src, "parseDatasource not referenced"
        assert re.search(
            r"export\s+(async\s+)?function\s+parseDatasource|"
            r"export\s+const\s+parseDatasource\s*=|"
            r"export\s*\{[^}]*\bparseDatasource\b",
            src,
        ), "parseDatasource is not exported from schema-datasource.ts"

    def test_l1_parser_module_is_self_contained(self):
        """Parser must not import the generated client, the adapter, pg, or do file I/O.

        Structural guard for the purity / self-containment contract from the
        doc; behavioural purity is exercised in L2.
        """
        with open(PARSER_TS) as fh:
            src = fh.read()
        forbidden = [
            r"""from\s+['"]pg['"]""",
            r"""from\s+['"]@prisma/adapter-pg['"]""",
            r"""from\s+['"]\.?/?generated/prisma""",
            r"""from\s+['"]\./generated""",
            r"""from\s+['"]@prisma/client['"]""",
            r"""from\s+['"]node:fs['"]""",
            r"""from\s+['"]fs['"]""",
            r"""require\(\s*['"]fs['"]\s*\)""",
        ]
        for pat in forbidden:
            assert not re.search(pat, src), (
                f"schema-datasource.ts must not import/use {pat!r}; it must be a "
                f"pure, file-IO-free module that receives schema text as a string"
            )

    def test_l1_agent_test_exists(self):
        """packages/prisma/schema-datasource.test.ts must be created by the agent."""
        assert os.path.isfile(PARSER_TEST_TS), "schema-datasource.test.ts not found"
        assert os.path.getsize(PARSER_TEST_TS) > 0, "schema-datasource.test.ts is empty"

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real parser via native vitest
    # ------------------------------------------------------------------ #
    def test_l2_vitest_suite_passes_overall(self):
        """The grader-owned vitest spec for the parser passes end-to-end."""
        combined = self._require_vitest_passed()
        assert "benchverify" in combined or "passed" in combined.lower(), (
            "vitest output does not reference the grader spec; suite may not have run"
        )

    def test_l2_extracts_provider_and_env_names(self):
        """[T01][T02][T03] provider stripped of quotes; url/directUrl env names extracted."""
        out = self._require_vitest_passed()
        assert "T01" in out and "T02" in out and "T03" in out, (
            "core extraction cases did not run"
        )

    def test_l2_plain_url_and_absent_directurl_null(self):
        """[T04][T05] plain (non-env) url -> null; absent directUrl -> null."""
        out = self._require_vitest_passed()
        assert "T04" in out and "T05" in out, "null-handling cases did not run"

    def test_l2_whitespace_and_comment_tolerance(self):
        """[T06][T07] irregular whitespace tolerated; // comment lines ignored."""
        out = self._require_vitest_passed()
        assert "T06" in out and "T07" in out, "whitespace/comment cases did not run"

    def test_l2_arbitrary_name_and_first_block_only(self):
        """[T08][T09] any datasource block name accepted; only the first block parsed."""
        out = self._require_vitest_passed()
        assert "T08" in out and "T09" in out, "block-name/first-block cases did not run"

    def test_l2_throw_no_datasource_and_missing_provider(self):
        """[T10][T11] no-datasource and missing-provider both throw with informative messages."""
        out = self._require_vitest_passed()
        assert "T10" in out and "T11" in out, "throw cases did not run"

    def test_l2_purity_deep_equal_and_env_untouched(self):
        """[T12][T13] equal inputs -> deep-equal outputs; process.env untouched."""
        out = self._require_vitest_passed()
        assert "T12" in out and "T13" in out, "purity cases did not run"

    def test_l2_value_driven_not_hardcoded(self):
        """[T14][T15] custom env names round-trip; non-postgres provider returned verbatim.

        Discriminative guard: a stub that always returns DATABASE_URL /
        postgresql cannot satisfy these.
        """
        out = self._require_vitest_passed()
        assert "T14" in out and "T15" in out, "value-driven discrimination cases did not run"

    def test_l2_naive_parser_would_fail(self):
        """Meta-guard: the spec encodes >=15 discriminative cases beyond existence.

        A hardcoded parser (returns fixed provider/env names, ignores input, or
        never throws) cannot satisfy the throw + first-block-only + value-driven
        + purity assertions, so a green vitest run is meaningful. We assert all
        15 tagged cases executed.
        """
        out = self._require_vitest_passed()
        ran = {t for t in re.findall(r"T\d{2}", out)}
        expected = {f"T{i:02d}" for i in range(1, 16)}
        missing = expected - ran
        assert not missing, (
            f"these parser cases did not appear in vitest output: {sorted(missing)}"
        )
