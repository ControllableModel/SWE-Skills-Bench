"""
Test for 'drizzle-orm-patterns' skill (variant ext4) — In-Memory Webhook Delivery Ledger
(dub monorepo).

Verifies that the Agent built a self-contained, in-process webhook delivery ledger under
apps/web/lib/webhook/delivery-store/ backed by an embedded better-sqlite3 (":memory:")
database and queried through drizzle-orm. The module must expose:

    schema.ts  — webhooks + deliveries tables, a one-to-many relation, and row types
                 INFERRED from the table definitions; payload surfaces as a typed
                 { event: string; data: Record<string, unknown> } object; status is
                 constrained to "pending" | "success" | "failed".
    store.ts   — a DeliveryLedger backed by ":memory:" with a public API:
                 registerWebhook / enqueueDelivery / recordSuccess / recordFailure /
                 getDeliveries / getFailureCounts / getDisabledWebhooks.
    index.ts   — re-exports the ledger, factory (createDeliveryLedger), and public types.

Strategy
--------
L1 checks verify the deliverable files exist, are minimally well-formed, that
package.json declares drizzle-orm, and that index.ts surfaces the factory.

L2 checks DO NOT trust the agent's own test file. Instead we drop an independent
TypeScript probe spec into apps/web/tests/webhooks/ (vitest's configured `dir`),
import the ledger from "@/lib/webhook/delivery-store", seed deterministic data, and
run the repo's native command:

    cd apps/web && pnpm vitest run tests/webhooks/<probe>.test.ts

asserting on the ledger's *real* behavior:
  - typed JSON payload round-tripping (payload.event / payload.data, not a raw string)
  - getDeliveries ordering by attemptedAt ascending
  - atomic recordFailure: increments parent webhook consecutiveFailures
  - failure-threshold auto-disable at exactly 5 (and appearance in getDisabledWebhooks)
  - recordSuccess resets consecutiveFailures to 0 and flips delivery status
  - getFailureCounts including a never-failed webhook with count 0
  - getDisabledWebhooks ordered by id
  - enqueueDelivery for a missing webhook throws and inserts nothing
  - recordSuccess/recordFailure for an unknown delivery id throws and changes nothing
  - ledger isolation between factory instances

A hardcoded or shallow solution (returns fixed values, ignores inputs, skips storage,
does non-atomic updates) cannot pass these because the probe drives the public API with
novel data and inspects concrete numeric/string outcomes. The agent's own suite is also
run separately for the documented acceptance command.
"""

import json
import os
import subprocess

import pytest


class TestDrizzleOrmPatterns:
    """Verify the in-memory webhook delivery ledger built with drizzle-orm + better-sqlite3."""

    REPO_DIR = "/workspace/dub"
    WEB_DIR = os.path.join(REPO_DIR, "apps", "web")
    STORE_DIR = os.path.join(WEB_DIR, "lib", "webhook", "delivery-store")
    PROBE_NAME = "zz_delivery_ledger_probe.test.ts"
    PROBE_PATH = os.path.join(WEB_DIR, "tests", "webhooks", PROBE_NAME)

    _deps_ready = False

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @classmethod
    def _ensure_deps(cls):
        """Install the pnpm workspace dependencies once (idempotent)."""
        if cls._deps_ready:
            return
        if os.path.isdir(os.path.join(cls.WEB_DIR, "node_modules", "drizzle-orm")) and \
           os.path.isdir(os.path.join(cls.WEB_DIR, "node_modules", "better-sqlite3")):
            cls._deps_ready = True
            return
        # Install at the monorepo root so the pnpm workspace is fully linked.
        result = subprocess.run(
            ["pnpm", "install", "--frozen-lockfile=false"],
            cwd=cls.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "pnpm install failed:\n"
                f"stdout={result.stdout[-3000:]}\nstderr={result.stderr[-3000:]}"
            )
        cls._deps_ready = True

    def _write_probe(self, body: str):
        """Write an independent vitest probe spec into the configured tests dir."""
        os.makedirs(os.path.dirname(self.PROBE_PATH), exist_ok=True)
        with open(self.PROBE_PATH, "w") as f:
            f.write(body)

    def _run_probe(self, timeout=420):
        """Run the probe via the repo's native vitest command and return CompletedProcess."""
        return subprocess.run(
            ["pnpm", "vitest", "run", f"tests/webhooks/{self.PROBE_NAME}"],
            cwd=self.WEB_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _drive(self, assertions_ts: str, timeout=420):
        """
        Build a probe that imports the ledger, provides a deterministic `seed()` helper,
        runs the provided TS assertion body inside a single `it(...)`, executes it
        natively, and returns the CompletedProcess. Assertions use vitest `expect`.

        seed() lays down a fixed graph:
          wh1 (https://a.example/hook)  — receives d1,d2,d3 (attemptedAt 300,100,200)
          wh2 (https://b.example/hook)  — receives d4 (attemptedAt 400)
          wh3 (https://c.example/hook)  — never used (zero deliveries / zero failures)
        Payloads carry a typed { event, data } object so round-tripping is observable.
        """
        probe = (
            'import { describe, it, expect } from "vitest";\n'
            'import { createDeliveryLedger } from "@/lib/webhook/delivery-store";\n'
            '\n'
            'function seed() {\n'
            '  const s = createDeliveryLedger();\n'
            '  s.registerWebhook({ id: "wh1", url: "https://a.example/hook" });\n'
            '  s.registerWebhook({ id: "wh2", url: "https://b.example/hook" });\n'
            '  s.registerWebhook({ id: "wh3", url: "https://c.example/hook" });\n'
            '  s.enqueueDelivery({\n'
            '    id: "d1", webhookId: "wh1", event: "link.created",\n'
            '    payload: { event: "link.created", data: { id: "lnk_1", clicks: 7 } },\n'
            '    attemptedAt: 300,\n'
            '  });\n'
            '  s.enqueueDelivery({\n'
            '    id: "d2", webhookId: "wh1", event: "link.updated",\n'
            '    payload: { event: "link.updated", data: { id: "lnk_1" } },\n'
            '    attemptedAt: 100,\n'
            '  });\n'
            '  s.enqueueDelivery({\n'
            '    id: "d3", webhookId: "wh1", event: "link.deleted",\n'
            '    payload: { event: "link.deleted", data: { id: "lnk_1" } },\n'
            '    attemptedAt: 200,\n'
            '  });\n'
            '  s.enqueueDelivery({\n'
            '    id: "d4", webhookId: "wh2", event: "lead.created",\n'
            '    payload: { event: "lead.created", data: { email: "x@y.z" } },\n'
            '    attemptedAt: 400,\n'
            '  });\n'
            '  return s;\n'
            '}\n'
            '\n'
            'describe("delivery-ledger probe", () => {\n'
            '  it("behaves as specified", () => {\n'
            + assertions_ts
            + '\n  });\n'
            '});\n'
        )
        self._write_probe(probe)
        return self._run_probe(timeout=timeout)

    def _assert_passed(self, result, ctx=""):
        ok = result.returncode == 0
        assert ok, (
            f"vitest probe failed{(' (' + ctx + ')') if ctx else ''}:\n"
            f"--- stdout ---\n{result.stdout[-4000:]}\n"
            f"--- stderr ---\n{result.stderr[-2000:]}"
        )

    def teardown_method(self, method):
        try:
            if os.path.isfile(self.PROBE_PATH):
                os.remove(self.PROBE_PATH)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # L1 — deliverables exist & are minimally well-formed
    # ------------------------------------------------------------------

    def test_l1_store_dir_and_files_exist(self):
        """schema.ts, store.ts and index.ts must exist under lib/webhook/delivery-store/."""
        for fname in ("schema.ts", "store.ts", "index.ts"):
            fpath = os.path.join(self.STORE_DIR, fname)
            assert os.path.isfile(fpath), f"missing deliverable: {fpath}"
            assert os.path.getsize(fpath) > 0, f"empty deliverable: {fpath}"

    def test_l1_package_declares_drizzle_orm(self):
        """apps/web/package.json must declare drizzle-orm as a (dev)dependency."""
        with open(os.path.join(self.WEB_DIR, "package.json")) as f:
            pkg = json.load(f)
        deps = {}
        for sect in ("dependencies", "devDependencies", "peerDependencies"):
            deps.update(pkg.get(sect) or {})
        assert "drizzle-orm" in deps, "drizzle-orm not declared in apps/web/package.json"

    def test_l1_agent_test_file_present(self):
        """The agent's vitest suite for the delivery store must exist."""
        fpath = os.path.join(self.WEB_DIR, "tests", "webhooks", "delivery-store.test.ts")
        assert os.path.isfile(fpath), "expected tests/webhooks/delivery-store.test.ts"
        assert os.path.getsize(fpath) > 0, "delivery-store.test.ts is empty"

    def test_l1_index_reexports_factory(self):
        """index.ts must re-export the factory so the module is importable from the package root."""
        with open(os.path.join(self.STORE_DIR, "index.ts")) as f:
            content = f.read()
        assert "createDeliveryLedger" in content, (
            "index.ts must surface createDeliveryLedger"
        )

    def test_l1_schema_defines_both_tables(self):
        """schema.ts must define both the webhooks and deliveries tables (drizzle table builders)."""
        with open(os.path.join(self.STORE_DIR, "schema.ts")) as f:
            content = f.read()
        # Minimal well-formedness: both entities and a drizzle table constructor are present.
        assert "webhooks" in content and "deliveries" in content, (
            "schema.ts must reference both 'webhooks' and 'deliveries' entities"
        )
        assert "sqliteTable" in content or "Table(" in content, (
            "schema.ts must use a drizzle table builder (e.g. sqliteTable)"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic behavior via independent native probe
    # ------------------------------------------------------------------

    def test_l2_module_importable_and_factory_returns_ledger(self):
        """Module must build & import from @/lib/webhook/delivery-store and expose the API."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createDeliveryLedger();\n'
            '    expect(typeof s.registerWebhook).toBe("function");\n'
            '    expect(typeof s.enqueueDelivery).toBe("function");\n'
            '    expect(typeof s.recordSuccess).toBe("function");\n'
            '    expect(typeof s.recordFailure).toBe("function");\n'
            '    expect(typeof s.getDeliveries).toBe("function");\n'
            '    expect(typeof s.getFailureCounts).toBe("function");\n'
            '    expect(typeof s.getDisabledWebhooks).toBe("function");\n'
        )
        self._assert_passed(result, "import/factory")

    def test_l2_register_webhook_defaults(self):
        """registerWebhook returns the webhook with consecutiveFailures=0 and disabled=false."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createDeliveryLedger();\n'
            '    const wh = s.registerWebhook({ id: "w", url: "https://e.example/h" });\n'
            '    expect(wh.id).toBe("w");\n'
            '    expect(wh.url).toBe("https://e.example/h");\n'
            '    expect(Number(wh.consecutiveFailures)).toBe(0);\n'
            '    // disabled defaults to false (accept boolean or 0/1 representation)\n'
            '    expect(Boolean(wh.disabled)).toBe(false);\n'
        )
        self._assert_passed(result, "register-defaults")

    def test_l2_typed_payload_round_trip(self):
        """A read-back delivery exposes payload.event and payload.data as a typed object, not a string."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const ds = s.getDeliveries("wh1");\n'
            '    const d1 = ds.find((d:any) => d.id === "d1") as any;\n'
            '    expect(d1).toBeDefined();\n'
            '    // payload must be a structured object, never a raw JSON string\n'
            '    expect(typeof d1.payload).toBe("object");\n'
            '    expect(d1.payload).not.toBeNull();\n'
            '    expect(d1.payload.event).toBe("link.created");\n'
            '    expect(typeof d1.payload.data).toBe("object");\n'
            '    expect(d1.payload.data.id).toBe("lnk_1");\n'
            '    expect(Number(d1.payload.data.clicks)).toBe(7);\n'
            '    expect(d1.status).toBe("pending");\n'
        )
        self._assert_passed(result, "typed-payload-roundtrip")

    def test_l2_get_deliveries_ordered_ascending(self):
        """getDeliveries(wh1) returns d2,d3,d1 — ordered by attemptedAt ascending (100,200,300)."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    const ids = s.getDeliveries("wh1").map((d:any) => d.id);\n'
            '    expect(ids).toEqual(["d2", "d3", "d1"]);\n'
            '    const at = s.getDeliveries("wh1").map((d:any) => Number(d.attemptedAt));\n'
            '    expect(at).toEqual([100, 200, 300]);\n'
            '    // wh1 deliveries never leak wh2 rows\n'
            '    expect(ids).not.toContain("d4");\n'
        )
        self._assert_passed(result, "get-deliveries-order")

    def test_l2_record_failure_increments_parent(self):
        """recordFailure flips the delivery to 'failed' AND increments the webhook's consecutiveFailures."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    s.recordFailure("d1");\n'
            '    const d1 = s.getDeliveries("wh1").find((d:any) => d.id === "d1") as any;\n'
            '    expect(d1.status).toBe("failed");\n'
            '    s.recordFailure("d2");\n'
            '    // two distinct failed deliveries -> consecutiveFailures should be 2\n'
            '    const fc = s.getFailureCounts().find((r:any) => r.id === "wh1") as any;\n'
            '    expect(Number(fc.failedCount ?? (fc as any).count ?? (fc as any).failures)).toBe(2);\n'
            '    // it is NOT disabled yet (threshold is 5)\n'
            '    const disabled = s.getDisabledWebhooks().map((w:any) => w.id);\n'
            '    expect(disabled).not.toContain("wh1");\n'
        )
        self._assert_passed(result, "record-failure-parent")

    def test_l2_auto_disable_at_five(self):
        """Five consecutive recordFailure calls -> consecutiveFailures=5, disabled=true, listed in getDisabledWebhooks."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createDeliveryLedger();\n'
            '    s.registerWebhook({ id: "wd", url: "https://d.example/h" });\n'
            '    for (let i = 0; i < 5; i++) {\n'
            '      s.enqueueDelivery({\n'
            '        id: "f" + i, webhookId: "wd", event: "e",\n'
            '        payload: { event: "e", data: {} }, attemptedAt: i + 1,\n'
            '      });\n'
            '    }\n'
            '    // before the 5th failure the webhook must NOT be disabled\n'
            '    for (let i = 0; i < 4; i++) s.recordFailure("f" + i);\n'
            '    expect(s.getDisabledWebhooks().map((w:any)=>w.id)).not.toContain("wd");\n'
            '    // the 5th failure crosses the threshold\n'
            '    s.recordFailure("f4");\n'
            '    const disabled = s.getDisabledWebhooks();\n'
            '    const ids = disabled.map((w:any) => w.id);\n'
            '    expect(ids).toContain("wd");\n'
            '    const fc = s.getFailureCounts().find((r:any) => r.id === "wd") as any;\n'
            '    expect(Number(fc.failedCount ?? fc.count ?? fc.failures)).toBe(5);\n'
        )
        self._assert_passed(result, "auto-disable-at-5")

    def test_l2_record_success_resets_counter(self):
        """recordSuccess after failures flips status to 'success' and resets consecutiveFailures to 0."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createDeliveryLedger();\n'
            '    s.registerWebhook({ id: "wr", url: "https://r.example/h" });\n'
            '    s.enqueueDelivery({ id: "a", webhookId: "wr", event: "e", payload: { event: "e", data: {} }, attemptedAt: 1 });\n'
            '    s.enqueueDelivery({ id: "b", webhookId: "wr", event: "e", payload: { event: "e", data: {} }, attemptedAt: 2 });\n'
            '    s.enqueueDelivery({ id: "c", webhookId: "wr", event: "e", payload: { event: "e", data: {} }, attemptedAt: 3 });\n'
            '    s.recordFailure("a");\n'
            '    s.recordFailure("b");\n'
            '    let fc = s.getFailureCounts().find((r:any) => r.id === "wr") as any;\n'
            '    expect(Number(fc.failedCount ?? fc.count ?? fc.failures)).toBe(2);\n'
            '    s.recordSuccess("c");\n'
            '    const c = s.getDeliveries("wr").find((d:any) => d.id === "c") as any;\n'
            '    expect(c.status).toBe("success");\n'
            '    // the two failed deliveries still count as failed history...\n'
            '    fc = s.getFailureCounts().find((r:any) => r.id === "wr") as any;\n'
            '    expect(Number(fc.failedCount ?? fc.count ?? fc.failures)).toBe(2);\n'
            '    // ...but the consecutive-failure streak was reset, so it is not disabled\n'
            '    expect(s.getDisabledWebhooks().map((w:any)=>w.id)).not.toContain("wr");\n'
            '    // another failure now starts the streak fresh (would need 5 more to disable)\n'
            '    s.recordFailure("a");\n'
            '    expect(s.getDisabledWebhooks().map((w:any)=>w.id)).not.toContain("wr");\n'
        )
        self._assert_passed(result, "record-success-reset")

    def test_l2_failure_counts_include_zero(self):
        """getFailureCounts includes every webhook, with id+url, including a never-failed one at count 0."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    s.recordFailure("d1");\n'
            '    const rows = s.getFailureCounts();\n'
            '    const m: Record<string, number> = {};\n'
            '    const urls: Record<string, string> = {};\n'
            '    for (const r of rows as any[]) {\n'
            '      m[r.id] = Number(r.failedCount ?? r.count ?? r.failures);\n'
            '      urls[r.id] = r.url;\n'
            '    }\n'
            '    expect(m["wh1"]).toBe(1);\n'
            '    expect(m["wh2"]).toBe(0);\n'
            '    // wh3 never received any delivery yet must still appear with count 0\n'
            '    expect(m["wh3"]).toBe(0);\n'
            '    expect(urls["wh3"]).toBe("https://c.example/hook");\n'
            '    expect(urls["wh1"]).toBe("https://a.example/hook");\n'
        )
        self._assert_passed(result, "failure-counts-zero")

    def test_l2_disabled_webhooks_ordered_by_id(self):
        """getDisabledWebhooks returns only disabled webhooks, ordered by id ascending."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createDeliveryLedger();\n'
            '    // create two webhooks out of id order; disable both by 5 failures each\n'
            '    for (const id of ["wB", "wA"]) {\n'
            '      s.registerWebhook({ id, url: "https://" + id + ".example/h" });\n'
            '      for (let i = 0; i < 5; i++) {\n'
            '        const did = id + "_" + i;\n'
            '        s.enqueueDelivery({ id: did, webhookId: id, event: "e", payload: { event: "e", data: {} }, attemptedAt: i + 1 });\n'
            '        s.recordFailure(did);\n'
            '      }\n'
            '    }\n'
            '    // a third webhook stays healthy and must NOT appear\n'
            '    s.registerWebhook({ id: "wC", url: "https://wC.example/h" });\n'
            '    const ids = s.getDisabledWebhooks().map((w:any) => w.id);\n'
            '    expect(ids).toEqual(["wA", "wB"]);\n'
        )
        self._assert_passed(result, "disabled-ordered-by-id")

    def test_l2_enqueue_for_missing_webhook_throws(self):
        """enqueueDelivery for a non-existent webhook throws and inserts no delivery."""
        self._ensure_deps()
        result = self._drive(
            '    const s = createDeliveryLedger();\n'
            '    s.registerWebhook({ id: "w", url: "https://e.example/h" });\n'
            '    let threw = false;\n'
            '    try {\n'
            '      s.enqueueDelivery({\n'
            '        id: "ghost", webhookId: "nope", event: "e",\n'
            '        payload: { event: "e", data: {} }, attemptedAt: 1,\n'
            '      });\n'
            '    } catch (e) { threw = true; }\n'
            '    expect(threw).toBe(true);\n'
            '    // nothing got inserted for the missing webhook\n'
            '    expect(s.getDeliveries("nope")).toEqual([]);\n'
            '    // and the valid webhook is unaffected\n'
            '    expect(s.getDeliveries("w")).toEqual([]);\n'
        )
        self._assert_passed(result, "enqueue-missing-webhook")

    def test_l2_unknown_delivery_id_atomic_no_change(self):
        """recordSuccess/recordFailure for an unknown delivery id throws and changes nothing (atomic)."""
        self._ensure_deps()
        result = self._drive(
            '    const s = seed();\n'
            '    // capture baseline failure counts\n'
            '    const before = s.getFailureCounts().find((r:any)=>r.id==="wh1") as any;\n'
            '    const beforeN = Number(before.failedCount ?? before.count ?? before.failures);\n'
            '    let threwF = false, threwS = false;\n'
            '    try { s.recordFailure("does-not-exist"); } catch (e) { threwF = true; }\n'
            '    try { s.recordSuccess("does-not-exist"); } catch (e) { threwS = true; }\n'
            '    expect(threwF).toBe(true);\n'
            '    expect(threwS).toBe(true);\n'
            '    // no partial update: the parent webhook bookkeeping is untouched\n'
            '    const after = s.getFailureCounts().find((r:any)=>r.id==="wh1") as any;\n'
            '    expect(Number(after.failedCount ?? after.count ?? after.failures)).toBe(beforeN);\n'
            '    // and no webhook got disabled as a side effect\n'
            '    expect(s.getDisabledWebhooks()).toEqual([]);\n'
            '    // existing deliveries remain "pending"\n'
            '    const d1 = s.getDeliveries("wh1").find((d:any)=>d.id==="d1") as any;\n'
            '    expect(d1.status).toBe("pending");\n'
        )
        self._assert_passed(result, "unknown-delivery-atomic")

    def test_l2_ledger_isolation_between_instances(self):
        """Two factory-created ledgers are fully isolated: data in one is invisible to the other."""
        self._ensure_deps()
        result = self._drive(
            '    const a = createDeliveryLedger();\n'
            '    const b = createDeliveryLedger();\n'
            '    a.registerWebhook({ id: "w", url: "https://a.example/h" });\n'
            '    a.enqueueDelivery({ id: "d", webhookId: "w", event: "e", payload: { event: "e", data: {} }, attemptedAt: 1 });\n'
            '    a.recordFailure("d");\n'
            '    // b knows nothing of w\n'
            '    expect(b.getDeliveries("w")).toEqual([]);\n'
            '    expect(b.getFailureCounts().find((r:any)=>r.id==="w")).toBeUndefined();\n'
            '    expect(b.getDisabledWebhooks()).toEqual([]);\n'
            '    // a still intact\n'
            '    expect(a.getDeliveries("w").length).toBe(1);\n'
            '    const fc = a.getFailureCounts().find((r:any)=>r.id==="w") as any;\n'
            '    expect(Number(fc.failedCount ?? fc.count ?? fc.failures)).toBe(1);\n'
        )
        self._assert_passed(result, "isolation")

    def test_l2_agent_acceptance_suite_passes(self):
        """The acceptance command must pass: pnpm vitest run tests/webhooks/delivery-store.test.ts."""
        self._ensure_deps()
        agent_test = os.path.join(self.WEB_DIR, "tests", "webhooks", "delivery-store.test.ts")
        assert os.path.isfile(agent_test), "agent delivery-store.test.ts missing"
        result = subprocess.run(
            ["pnpm", "vitest", "run", "tests/webhooks/delivery-store.test.ts"],
            cwd=self.WEB_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert result.returncode == 0, (
            "agent's vitest suite failed:\n"
            f"--- stdout ---\n{result.stdout[-4000:]}\n"
            f"--- stderr ---\n{result.stderr[-2000:]}"
        )
        # Guard against an empty/no-test pass.
        combined = (result.stdout + result.stderr).lower()
        assert "no test files found" not in combined, "vitest found no test files"
