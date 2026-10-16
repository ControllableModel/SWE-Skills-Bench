"""
Test for 'prisma-schema-patterns' skill — read-replica routing resolver (ext7 variant).

The ext7 task asks the agent to extract the inlined `readonlyPrisma` routing
decision in `packages/prisma/index.ts` into a pure, self-contained resolver
module `packages/prisma/replica-routing.ts` that exports
`resolveReplicaRouting(env)` and to add a Vitest unit test
`packages/prisma/replica-routing.test.ts`.

The resolver returns a plain object with at least:
  - `primaryUrl`          — writable connection string (from DATABASE_URL)
  - `readonlyUrl`         — connection string the read-only client should use
  - `hasDedicatedReplica` — boolean, whether a *distinct* replica is configured

Routing / validation rules (from the requirement doc):
  - primaryUrl = DATABASE_URL; missing/empty/whitespace-only DATABASE_URL throws.
  - INSIGHTS_DATABASE_URL present & non-empty (trimmed) -> readonlyUrl = that,
    hasDedicatedReplica = true.
  - INSIGHTS_DATABASE_URL absent/empty/whitespace -> readonlyUrl = primaryUrl,
    hasDedicatedReplica = false.
  - A replica URL byte-for-byte equal to the primary -> NOT dedicated:
    readonlyUrl = primaryUrl, hasDedicatedReplica = false.
  - Both primary and any *configured* (non-empty) replica URL must use a
    postgres scheme (`postgres://` / `postgresql://`), else throw naming it.
    The replica is only validated when configured (fallback isn't re-validated).
  - Pure: no process.env read/mutation; equal input -> deep-equal output.

Verification strategy: this grader OWNS an independent Vitest spec that imports
the agent's `resolveReplicaRouting` and exercises every rule via the repo's
native `yarn vitest run` toolchain. The agent cannot pass by editing its own
test, and a naive/hardcoded resolver (ignores env, never throws, treats the
same-URL replica as dedicated) fails the discriminative cases.

L1 -> deliverable files exist + minimally well-formed / self-contained.
L2 -> dynamic execution of the real resolver behaviour via native vitest.
"""

import os
import re
import subprocess

import pytest

REPO_DIR = "/workspace/cal.com"
PRISMA_DIR = os.path.join(REPO_DIR, "packages", "prisma")
ROUTING_TS = os.path.join(PRISMA_DIR, "replica-routing.ts")
ROUTING_TEST_TS = os.path.join(PRISMA_DIR, "replica-routing.test.ts")
INDEX_TS = os.path.join(PRISMA_DIR, "index.ts")

# A vitest spec we (the grader) own. It imports the agent's resolver from the
# sibling module and asserts the required behaviour. We control its contents so
# a naive / hardcoded resolver cannot pass by editing the agent-authored test.
VERIFY_SPEC_NAME = "replica-routing.benchverify.test.ts"
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
    """Verify the Prisma read-replica routing resolver deliverable (ext7)."""

    REPO_DIR = "/workspace/cal.com"

    # ------------------------------------------------------------------ #
    # Spec lifecycle
    # ------------------------------------------------------------------ #
    @classmethod
    def setup_class(cls):
        """Install our own verification vitest spec into the prisma package."""
        cls._spec_written = False
        if os.path.isdir(PRISMA_DIR) and os.path.isfile(ROUTING_TS):
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
// Import the agent-authored resolver. Importing this file alone must not pull
// in the generated prisma client / driver adapter / pg (self-containment).
import { resolveReplicaRouting } from "./replica-routing";

const PG = "postgresql://u:p@localhost:5432/main";
const PG_RO = "postgres://u:p@replica:5432/ro";
const PG2 = "postgresql://u:p@localhost:5432/main"; // byte-for-byte equal to PG

describe("benchverify resolveReplicaRouting", () => {
  it("[T01] DATABASE_URL set, no INSIGHTS -> primaryUrl resolved, no dedicated replica, readonly falls back", () => {
    const r = resolveReplicaRouting({ DATABASE_URL: PG });
    expect(r.primaryUrl).toBe(PG);
    expect(r.readonlyUrl).toBe(PG);
    expect(r.hasDedicatedReplica).toBe(false);
  });

  it("[T02] distinct INSIGHTS_DATABASE_URL -> dedicated replica, readonly differs from primary", () => {
    const r = resolveReplicaRouting({ DATABASE_URL: PG, INSIGHTS_DATABASE_URL: PG_RO });
    expect(r.primaryUrl).toBe(PG);
    expect(r.readonlyUrl).toBe(PG_RO);
    expect(r.readonlyUrl).not.toBe(r.primaryUrl);
    expect(r.hasDedicatedReplica).toBe(true);
  });

  it("[T03] absent INSIGHTS_DATABASE_URL -> readonly falls back to primary, not dedicated", () => {
    const r = resolveReplicaRouting({ DATABASE_URL: PG });
    expect(r.readonlyUrl).toBe(PG);
    expect(r.hasDedicatedReplica).toBe(false);
  });

  it("[T04] empty-string INSIGHTS_DATABASE_URL -> fallback to primary, not dedicated", () => {
    const r = resolveReplicaRouting({ DATABASE_URL: PG, INSIGHTS_DATABASE_URL: "" });
    expect(r.readonlyUrl).toBe(PG);
    expect(r.hasDedicatedReplica).toBe(false);
  });

  it("[T05] whitespace-only INSIGHTS_DATABASE_URL -> fallback to primary, not dedicated", () => {
    for (const v of ["   ", "\t", " \n "]) {
      const r = resolveReplicaRouting({ DATABASE_URL: PG, INSIGHTS_DATABASE_URL: v });
      expect(r.readonlyUrl).toBe(PG);
      expect(r.hasDedicatedReplica).toBe(false);
    }
  });

  it("[T06] replica URL byte-for-byte equal to primary -> NOT a dedicated replica", () => {
    const r = resolveReplicaRouting({ DATABASE_URL: PG, INSIGHTS_DATABASE_URL: PG2 });
    expect(PG2).toBe(PG); // sanity: the two strings are equal
    expect(r.readonlyUrl).toBe(PG);
    expect(r.hasDedicatedReplica).toBe(false);
  });

  it("[T07] missing DATABASE_URL -> throws naming the primary url", () => {
    expect(() => resolveReplicaRouting({})).toThrow();
    let msg = "";
    try {
      resolveReplicaRouting({});
    } catch (e: any) {
      msg = String(e && e.message);
    }
    expect(msg.length).toBeGreaterThan(0);
    expect(/database_url|database url|primary/i.test(msg)).toBe(true);
  });

  it("[T08] empty / whitespace-only DATABASE_URL -> throws (treated as missing)", () => {
    expect(() => resolveReplicaRouting({ DATABASE_URL: "" })).toThrow();
    expect(() => resolveReplicaRouting({ DATABASE_URL: "   " })).toThrow();
  });

  it("[T09] wrong-scheme primary DATABASE_URL -> throws naming the invalid url", () => {
    let msg = "";
    try {
      resolveReplicaRouting({ DATABASE_URL: "mysql://u:p@localhost:3306/db" });
    } catch (e: any) {
      msg = String(e && e.message);
    }
    expect(msg.length).toBeGreaterThan(0);
    expect(/database_url|url|scheme|postgres|primary/i.test(msg)).toBe(true);
  });

  it("[T10] wrong-scheme configured replica INSIGHTS_DATABASE_URL -> throws", () => {
    expect(() =>
      resolveReplicaRouting({ DATABASE_URL: PG, INSIGHTS_DATABASE_URL: "mysql://x/y" })
    ).toThrow();
    expect(() =>
      resolveReplicaRouting({ DATABASE_URL: PG, INSIGHTS_DATABASE_URL: "http://x/y" })
    ).toThrow();
  });

  it("[T11] replica is only validated when configured -> empty/whitespace replica does NOT throw on scheme", () => {
    // Fallback path: replica is not configured, so no separate scheme validation.
    expect(() => resolveReplicaRouting({ DATABASE_URL: PG, INSIGHTS_DATABASE_URL: "" })).not.toThrow();
    expect(() => resolveReplicaRouting({ DATABASE_URL: PG, INSIGHTS_DATABASE_URL: "   " })).not.toThrow();
  });

  it("[T12] both postgres:// and postgresql:// schemes accepted for primary and replica", () => {
    const a = resolveReplicaRouting({ DATABASE_URL: "postgres://u:p@h:5432/d" });
    expect(a.primaryUrl).toBe("postgres://u:p@h:5432/d");
    const b = resolveReplicaRouting({
      DATABASE_URL: "postgresql://u:p@h:5432/d",
      INSIGHTS_DATABASE_URL: "postgres://u:p@ro:5432/r",
    });
    expect(b.primaryUrl).toBe("postgresql://u:p@h:5432/d");
    expect(b.readonlyUrl).toBe("postgres://u:p@ro:5432/r");
    expect(b.hasDedicatedReplica).toBe(true);
  });

  it("[T13] hasDedicatedReplica is consistent with the routing decision", () => {
    const dedicated = resolveReplicaRouting({ DATABASE_URL: PG, INSIGHTS_DATABASE_URL: PG_RO });
    expect(dedicated.hasDedicatedReplica).toBe(true);
    expect(dedicated.readonlyUrl).not.toBe(dedicated.primaryUrl);

    const fallback = resolveReplicaRouting({ DATABASE_URL: PG });
    expect(fallback.hasDedicatedReplica).toBe(false);
    expect(fallback.readonlyUrl).toBe(fallback.primaryUrl);
  });

  it("[T14] purity: equal inputs -> deep-equal outputs, process.env untouched", () => {
    const input = { DATABASE_URL: PG, INSIGHTS_DATABASE_URL: PG_RO };
    const before = JSON.stringify(process.env);
    const r1 = resolveReplicaRouting({ ...input });
    const r2 = resolveReplicaRouting({ ...input });
    const after = JSON.stringify(process.env);
    expect(r2).toEqual(r1);
    expect(after).toBe(before);
  });

  it("[T15] purity: resolver ignores ambient process.env", () => {
    const savedDb = process.env.DATABASE_URL;
    const savedRo = process.env.INSIGHTS_DATABASE_URL;
    process.env.DATABASE_URL = "postgresql://AMBIENT:p@h:5432/ambient";
    process.env.INSIGHTS_DATABASE_URL = "postgresql://AMBIENT:p@h:5432/ambient-ro";
    try {
      const r = resolveReplicaRouting({ DATABASE_URL: PG });
      expect(r.primaryUrl).toBe(PG);
      expect(r.readonlyUrl).toBe(PG);
      expect(r.hasDedicatedReplica).toBe(false);
    } finally {
      if (savedDb === undefined) delete process.env.DATABASE_URL;
      else process.env.DATABASE_URL = savedDb;
      if (savedRo === undefined) delete process.env.INSIGHTS_DATABASE_URL;
      else process.env.INSIGHTS_DATABASE_URL = savedRo;
    }
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
                "Verification spec was not written — replica-routing.ts is "
                "missing, so the resolver deliverable does not exist."
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

    def test_l1_replica_routing_exists(self):
        """packages/prisma/replica-routing.ts must be created and non-empty."""
        assert os.path.isfile(ROUTING_TS), "replica-routing.ts not found"
        assert os.path.getsize(ROUTING_TS) > 0, "replica-routing.ts is empty"

    def test_l1_exports_resolver_symbol(self):
        """replica-routing.ts must export a `resolveReplicaRouting` function."""
        with open(ROUTING_TS) as fh:
            src = fh.read()
        assert "resolveReplicaRouting" in src, "resolveReplicaRouting not referenced"
        assert re.search(
            r"export\s+(async\s+)?function\s+resolveReplicaRouting|"
            r"export\s+const\s+resolveReplicaRouting\s*=|"
            r"export\s*\{[^}]*\bresolveReplicaRouting\b",
            src,
        ), "resolveReplicaRouting is not exported from replica-routing.ts"

    def test_l1_resolver_module_is_self_contained(self):
        """Resolver must not import the generated client, the pg adapter, or pg.

        Structural guard for the purity / self-containment contract; the
        behavioural purity is exercised in L2.
        """
        with open(ROUTING_TS) as fh:
            src = fh.read()
        forbidden = [
            r"""from\s+['"]pg['"]""",
            r"""from\s+['"]@prisma/adapter-pg['"]""",
            r"""from\s+['"]@prisma/client['"]""",
            r"""from\s+['"]\.?/?generated/prisma""",
            r"""from\s+['"]\./generated""",
        ]
        for pat in forbidden:
            assert not re.search(pat, src), (
                f"replica-routing.ts must not import {pat!r}; it must be a pure module"
            )

    def test_l1_resolver_does_not_read_process_env(self):
        """The pure resolver must take an env argument, not read ambient process.env.

        Structural sanity check; the behavioural purity guarantee is verified
        dynamically in L2 ([T14]/[T15]).
        """
        with open(ROUTING_TS) as fh:
            src = fh.read()
        assert "resolveReplicaRouting" in src
        # The resolver function itself must accept a parameter (the env map).
        assert re.search(
            r"resolveReplicaRouting\s*(=\s*)?(\(|<|function)", src
        ), "resolveReplicaRouting must be a function taking an env argument"

    def test_l1_agent_test_exists(self):
        """packages/prisma/replica-routing.test.ts must be created by the agent."""
        assert os.path.isfile(ROUTING_TEST_TS), "replica-routing.test.ts not found"
        assert os.path.getsize(ROUTING_TEST_TS) > 0, "replica-routing.test.ts is empty"

    def test_l1_agent_test_imports_resolver(self):
        """The agent's test must actually import/exercise resolveReplicaRouting."""
        with open(ROUTING_TEST_TS) as fh:
            src = fh.read()
        assert "resolveReplicaRouting" in src, (
            "replica-routing.test.ts must import and exercise resolveReplicaRouting"
        )

    # ------------------------------------------------------------------ #
    # L2 — dynamic execution of the real resolver via native vitest
    # ------------------------------------------------------------------ #
    def test_l2_vitest_suite_passes_overall(self):
        """The grader-owned vitest spec for the resolver passes end-to-end."""
        combined = self._require_vitest_passed()
        assert "benchverify" in combined or "passed" in combined.lower(), (
            "vitest output does not reference the grader spec; suite may not have run"
        )

    def test_l2_default_no_replica_fallback(self):
        """[T01][T03] No INSIGHTS -> primary resolved, readonly falls back, not dedicated."""
        out = self._require_vitest_passed()
        assert "T01" in out and "T03" in out, "default / fallback cases did not run"

    def test_l2_dedicated_replica(self):
        """[T02] Distinct INSIGHTS_DATABASE_URL -> dedicated replica, readonly differs."""
        out = self._require_vitest_passed()
        assert "T02" in out, "dedicated-replica case did not run"

    def test_l2_empty_and_whitespace_replica_fallback(self):
        """[T04][T05] Empty / whitespace-only INSIGHTS -> fallback, not dedicated."""
        out = self._require_vitest_passed()
        assert "T04" in out and "T05" in out, "empty/whitespace replica cases did not run"

    def test_l2_same_url_as_primary_not_dedicated(self):
        """[T06] Replica byte-for-byte equal to primary -> NOT a dedicated replica.

        This is the key discriminator: a naive resolver that flips
        hasDedicatedReplica solely on INSIGHTS_DATABASE_URL presence fails here.
        """
        out = self._require_vitest_passed()
        assert "T06" in out, "same-URL-as-primary case did not run"

    def test_l2_missing_database_url_throws(self):
        """[T07][T08] Absent/empty/whitespace DATABASE_URL throws naming the primary."""
        out = self._require_vitest_passed()
        assert "T07" in out and "T08" in out, "missing-DATABASE_URL throw cases did not run"

    def test_l2_scheme_validation(self):
        """[T09][T10][T12] Non-postgres primary/replica throw; both pg schemes accepted."""
        out = self._require_vitest_passed()
        assert "T09" in out and "T10" in out and "T12" in out, "scheme validation cases did not run"

    def test_l2_replica_validated_only_when_configured(self):
        """[T11] Empty/whitespace replica (fallback path) is NOT scheme-validated."""
        out = self._require_vitest_passed()
        assert "T11" in out, "configured-only replica validation case did not run"

    def test_l2_has_dedicated_replica_consistency(self):
        """[T13] hasDedicatedReplica is consistent with readonlyUrl vs primaryUrl."""
        out = self._require_vitest_passed()
        assert "T13" in out, "hasDedicatedReplica consistency case did not run"

    def test_l2_purity_deep_equal_and_env_untouched(self):
        """[T14][T15] Equal inputs -> deep-equal outputs; process.env ignored/untouched."""
        out = self._require_vitest_passed()
        assert "T14" in out and "T15" in out, "purity cases did not run"

    def test_l2_naive_resolver_would_fail(self):
        """Meta-guard: the spec encodes >=15 discriminative cases beyond existence.

        A hardcoded resolver (ignores env, never throws, or treats the
        same-URL replica as dedicated) cannot satisfy the throw + override +
        same-URL + purity assertions, so a green vitest run is meaningful. We
        assert all 15 tagged cases executed.
        """
        out = self._require_vitest_passed()
        ran = {t for t in re.findall(r"T\d{2}", out)}
        expected = {f"T{i:02d}" for i in range(1, 16)}
        missing = expected - ran
        assert not missing, f"these resolver cases did not appear in vitest output: {sorted(missing)}"
