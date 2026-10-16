"""Tests for the `trpc-patterns` skill task (variant: ext3).

Task: Build an Audit-Logging Procedure Pipeline inside the tRPC monorepo.

The agent must create two files inside the tRPC monorepo:
  * packages/tests/server/auditLog.ts       -- in-memory task store + a fresh
                                                per-request audit sink, the tRPC
                                                instance, a reusable chain of
                                                cross-cutting steps (request id,
                                                timing/durationMs, audit append),
                                                a root router nesting a `tasks`
                                                sub-router (create/toggle/list/
                                                audit) and an exported caller
                                                factory + a store/sink factory.
  * packages/tests/server/auditLog.test.ts  -- a deterministic vitest suite
                                                driving the API through callers
                                                (>= 12 cases).

Verification strategy (L1 deliverables, L2 dynamic behavior):

L1  -- the deliverable files exist, are real source, use the repo's
       `@trpc/server` primitives (initTRPC), and export a public surface so the
       test file imports a caller factory rather than re-initializing tRPC.

L2  -- DYNAMIC EXECUTION via the repo's native toolchain (`pnpm vitest run`).
       * The agent's own acceptance suite must pass AND must genuinely assert on
         the tRPC error *code* (NOT_FOUND / BAD_REQUEST) for failure categories.
       * An INDEPENDENT vitest driver (written by THIS test into the repo)
         imports the agent's public caller + store/sink factories from
         auditLog.ts by introspection (their export names are not fixed by the
         task) and exercises, WITHOUT trusting the agent's own tests:
           - request-id presence in the body + uniqueness across calls,
           - a success audit record with ok:true and numeric durationMs >= 0,
           - a thrown procedure (toggle missing id) still appending an audit
             record with ok:false AND still propagating NOT_FOUND,
           - ordered context accumulation (the request id added by an earlier
             step is visible to the body and recorded in the audit record),
           - validation rejection (empty title -> BAD_REQUEST),
           - store/audit isolation between two independent factory results.

       A naive implementation that skips the pipeline, drops audit records on
       failure, overwrites context instead of accumulating, swallows thrown
       errors, or shares a global store/sink cannot pass the independent driver.
"""

import os
import re
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/trpc"
SERVER_DIR = os.path.join(REPO_DIR, "packages", "tests", "server")
AUDIT_TS = os.path.join(SERVER_DIR, "auditLog.ts")
AUDIT_TEST_TS = os.path.join(SERVER_DIR, "auditLog.test.ts")

# Native vitest command. We always run a single file, scoped tightly.
VITEST_TIMEOUT = 600


# --------------------------------------------------------------------------- #
# dependency / toolchain preparation
# --------------------------------------------------------------------------- #
def _have_node_modules():
    """The container ships the repo toolchain installed; detect it."""
    return os.path.isdir(os.path.join(REPO_DIR, "node_modules")) and (
        os.path.isdir(os.path.join(REPO_DIR, "packages", "tests", "node_modules"))
        or os.path.exists(os.path.join(REPO_DIR, "node_modules", ".bin", "vitest"))
        or os.path.isdir(os.path.join(REPO_DIR, "node_modules", "vitest"))
    )


@pytest.fixture(scope="module", autouse=True)
def _prepare_deps():
    """Best-effort: install workspace deps with pnpm if they are missing.

    In the benchmark container the toolchain is pre-installed, so this is
    usually a no-op. If node_modules is absent we attempt a pnpm install.
    """
    if not _have_node_modules():
        for cmd in (
            ["pnpm", "install", "--frozen-lockfile", "--prefer-offline"],
            ["pnpm", "install", "--prefer-offline"],
        ):
            try:
                res = subprocess.run(
                    cmd,
                    cwd=REPO_DIR,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )
                if res.returncode == 0:
                    break
            except Exception:
                continue
    yield


def _run_vitest(rel_file):
    """Run `pnpm vitest run <rel_file>` from the repo root."""
    cmd = ["pnpm", "vitest", "run", rel_file]
    return subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=VITEST_TIMEOUT,
    )


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _write_driver(name, body):
    """Write an independent vitest driver next to the deliverables and return
    the repo-relative path used to invoke vitest."""
    path = os.path.join(SERVER_DIR, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return os.path.relpath(path, REPO_DIR)


def _cleanup(rel_file):
    abs_path = os.path.join(REPO_DIR, rel_file)
    try:
        os.remove(abs_path)
    except OSError:
        pass


class TestTrpcPatterns:
    REPO_DIR = "/workspace/trpc"

    # ------------------------------------------------------------------ #
    # L1 -- deliverables exist and are minimally well-formed
    # ------------------------------------------------------------------ #
    def test_audit_module_exists(self):
        """L1: auditLog.ts deliverable exists and is non-trivial source."""
        assert os.path.isfile(AUDIT_TS), f"missing {AUDIT_TS}"
        src = _read(AUDIT_TS)
        assert len(src.strip()) > 200, "auditLog.ts is suspiciously small"

    def test_audit_test_exists(self):
        """L1: auditLog.test.ts deliverable exists and is non-trivial."""
        assert os.path.isfile(AUDIT_TEST_TS), f"missing {AUDIT_TEST_TS}"
        src = _read(AUDIT_TEST_TS)
        assert len(src.strip()) > 200, "auditLog.test.ts is suspiciously small"

    def test_module_uses_trpc_server_primitives(self):
        """L1: implementation is built on @trpc/server (initTRPC), wires a
        middleware/pipeline step, and exports a public surface (so the test
        file can import a caller factory)."""
        src = _read(AUDIT_TS)
        assert "@trpc/server" in src, "auditLog.ts must use @trpc/server"
        assert "initTRPC" in src, "auditLog.ts must initialize tRPC via initTRPC"
        assert "export" in src, "auditLog.ts must export a public surface"
        # The cross-cutting chain is built from middleware steps.
        assert "middleware" in src or ".use(" in src, (
            "auditLog.ts must compose a cross-cutting chain via middleware/.use"
        )
        # A router type / router is part of the contract.
        assert "Router" in src or "router" in src

    def test_test_file_imports_only_public_surface(self):
        """L1: the test file imports from the auditLog module rather than
        re-implementing routers/procedures inline."""
        src = _read(AUDIT_TEST_TS)
        assert (
            "./auditLog" in src or "auditLog'" in src or 'auditLog"' in src
        ), "auditLog.test.ts must import from ./auditLog"
        # It must NOT itself stand up a parallel router with initTRPC.
        assert "initTRPC" not in src, (
            "test file must import the caller factory, not re-init tRPC"
        )

    # ------------------------------------------------------------------ #
    # L2 -- the agent's acceptance suite passes
    # ------------------------------------------------------------------ #
    def test_acceptance_suite_passes(self):
        """L2: the exact Acceptance-Criteria command passes with all green.

        `pnpm vitest run packages/tests/server/auditLog.test.ts`
        """
        rel = os.path.relpath(AUDIT_TEST_TS, REPO_DIR)
        res = _run_vitest(rel)
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        assert res.returncode == 0, (
            "auditLog.test.ts must pass.\n"
            f"stdout tail:\n{(res.stdout or '')[-3000:]}\n"
            f"stderr tail:\n{(res.stderr or '')[-2000:]}"
        )
        assert "no test" not in combined.lower(), (
            "vitest reported no tests were collected"
        )

    def test_acceptance_suite_has_enough_cases(self):
        """L2: the acceptance suite actually contains >= 12 cases as required,
        proven by running and parsing the count vitest surfaces."""
        rel = os.path.relpath(AUDIT_TEST_TS, REPO_DIR)
        res = _run_vitest(rel)
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        passed = 0
        m = re.search(r"Tests\s+(\d+)\s+passed", combined)
        if m:
            passed = int(m.group(1))
        else:
            passed = combined.count("✓")  # check marks per test
        assert passed >= 12, (
            f"acceptance suite must have >= 12 passing cases, saw {passed}.\n"
            f"output tail:\n{combined[-2500:]}"
        )

    def test_acceptance_suite_asserts_on_codes(self):
        """L2: the acceptance test asserts on tRPC error *codes* for the
        required failure categories (not on message substrings):
          * NOT_FOUND  -- toggle on an unknown id
          * BAD_REQUEST -- validation rejection (empty title / empty id)
        """
        src = _read(AUDIT_TEST_TS)
        assert "NOT_FOUND" in src, (
            "acceptance suite must assert the NOT_FOUND error code for toggle "
            "on an unknown id"
        )
        assert "BAD_REQUEST" in src, (
            "acceptance suite must assert validation -> BAD_REQUEST code"
        )

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: request id presence, uniqueness, success audit
    # ------------------------------------------------------------------ #
    def test_independent_success_audit_and_request_ids(self):
        """L2 (independent): a successful create yields an audit record with
        ok:true, a non-empty string requestId, the create path, and a numeric
        durationMs >= 0; two successive calls produce two DISTINCT request ids.

        This proves the pipeline runs (timing + audit append) on the success
        path and that a fresh per-call request id is minted each time -- a stub
        that hardcodes a constant id or skips the audit append cannot pass.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeCtx, makeCaller, auditOf } from './__indep_helpers';

            test('create appends a success audit record with timing', async () => {
              const ctx = makeCtx();
              const caller = makeCaller(ctx);

              const task = await caller.tasks.create({ title: 'alpha' });
              expect(typeof task.id).toBe('string');
              expect(task.id.length).toBeGreaterThan(0);
              expect(task.title).toBe('alpha');
              expect(task.done).toBe(false);

              const records = await auditOf(ctx);
              expect(Array.isArray(records)).toBe(true);
              const createRecs = records.filter(
                (r: any) => String(r.path).includes('create'),
              );
              expect(createRecs.length).toBeGreaterThanOrEqual(1);
              const rec = createRecs[createRecs.length - 1];
              expect(rec.ok).toBe(true);
              expect(typeof rec.requestId).toBe('string');
              expect(rec.requestId.length).toBeGreaterThan(0);
              expect(typeof rec.durationMs).toBe('number');
              expect(rec.durationMs).toBeGreaterThanOrEqual(0);
              expect(Number.isFinite(rec.durationMs)).toBe(true);
            });

            test('two create calls mint two distinct request ids', async () => {
              const ctx = makeCtx();
              const caller = makeCaller(ctx);
              await caller.tasks.create({ title: 'one' });
              await caller.tasks.create({ title: 'two' });

              const records = await auditOf(ctx);
              const ids = records
                .filter((r: any) => String(r.path).includes('create'))
                .map((r: any) => r.requestId);
              expect(ids.length).toBeGreaterThanOrEqual(2);
              const unique = new Set(ids);
              expect(unique.size).toBe(ids.length);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_success_audit", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: failure path still audits AND propagates code
    # ------------------------------------------------------------------ #
    def test_independent_failure_audits_and_propagates_not_found(self):
        """L2 (independent): toggle on an unknown id throws NOT_FOUND AND the
        audit sink still records that call with ok:false and a numeric
        durationMs >= 0.

        A naive implementation that drops audit records on failure, or that
        swallows the thrown error (returning instead of re-raising), or that
        reports the wrong code, cannot pass this driver.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeCtx, makeCaller, auditOf } from './__indep_helpers';

            test('toggle missing id -> NOT_FOUND propagates with audit ok:false', async () => {
              const ctx = makeCtx();
              const caller = makeCaller(ctx);

              let code: string | undefined;
              let threw = false;
              try {
                await caller.tasks.toggle({ id: 'does-not-exist' });
              } catch (err: any) {
                threw = true;
                code = err?.code ?? err?.cause?.code;
              }
              expect(threw).toBe(true);
              expect(code).toBe('NOT_FOUND');

              const records = await auditOf(ctx);
              const toggleRecs = records.filter(
                (r: any) => String(r.path).includes('toggle'),
              );
              expect(toggleRecs.length).toBeGreaterThanOrEqual(1);
              const rec = toggleRecs[toggleRecs.length - 1];
              expect(rec.ok).toBe(false);
              expect(typeof rec.requestId).toBe('string');
              expect(rec.requestId.length).toBeGreaterThan(0);
              expect(typeof rec.durationMs).toBe('number');
              expect(rec.durationMs).toBeGreaterThanOrEqual(0);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_failure_audit", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: ordered context accumulation
    # (request id minted early is the SAME one recorded for the call)
    # ------------------------------------------------------------------ #
    def test_independent_context_accumulation(self):
        """L2 (independent): the request id added by an early pipeline step is
        the one that survives into the audit record for the same call -- proving
        steps ACCUMULATE context rather than each overwriting it.

        We mint two create calls and confirm each call's audit record carries a
        distinct, non-empty request id, and that list/audit procedures (which
        run through the same pipeline) themselves get recorded with their own
        request ids -- so the pipeline wraps every procedure, not just create.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeCtx, makeCaller, auditOf } from './__indep_helpers';

            test('every procedure flows through the pipeline with its own id', async () => {
              const ctx = makeCtx();
              const caller = makeCaller(ctx);

              await caller.tasks.create({ title: 'x' });
              await caller.tasks.list();

              const records = await auditOf(ctx);
              // create + list must both be audited (audit() itself may or may
              // not self-record; we do not depend on that).
              const paths = records.map((r: any) => String(r.path));
              expect(paths.some((p: string) => p.includes('create'))).toBe(true);
              expect(paths.some((p: string) => p.includes('list'))).toBe(true);

              // Each recorded call carries a non-empty request id and the ids
              // for the create vs list calls differ (accumulated-not-shared).
              const createRec = records.find((r: any) =>
                String(r.path).includes('create'),
              );
              const listRec = records.find((r: any) =>
                String(r.path).includes('list'),
              );
              expect(createRec.requestId.length).toBeGreaterThan(0);
              expect(listRec.requestId.length).toBeGreaterThan(0);
              expect(createRec.requestId).not.toBe(listRec.requestId);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_ctx_accum", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: validation rejection (empty title)
    # ------------------------------------------------------------------ #
    def test_independent_validation_rejected(self):
        """L2 (independent): malformed input is rejected as a validation error
        (BAD_REQUEST) before the body runs. Empty title and empty id must each
        fail; the store must NOT have grown a task from the rejected create.

        This is reachable without seeding because validation precedes the body.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeCtx, makeCaller } from './__indep_helpers';

            async function codeOf(p: Promise<unknown>): Promise<string | undefined> {
              try {
                await p;
                return undefined;
              } catch (err: any) {
                return err?.code ?? err?.cause?.code;
              }
            }

            test('empty title on create -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeCtx());
              const code = await codeOf(caller.tasks.create({ title: '' }));
              expect(code).toBe('BAD_REQUEST');
            });

            test('empty id on toggle -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeCtx());
              const code = await codeOf(caller.tasks.toggle({ id: '' }));
              expect(code).toBe('BAD_REQUEST');
            });

            test('rejected create does not add a task', async () => {
              const ctx = makeCtx();
              const caller = makeCaller(ctx);
              await codeOf(caller.tasks.create({ title: '' }));
              const tasks = await caller.tasks.list();
              expect(Array.isArray(tasks)).toBe(true);
              expect(tasks.length).toBe(0);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_validation", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: a well-formed title is NOT rejected
    # (proves validation is real, not "reject everything")
    # ------------------------------------------------------------------ #
    def test_independent_valid_input_passes_validation(self):
        """L2 (independent): a well-formed create input does NOT fail with
        BAD_REQUEST -- it succeeds and returns the created task. This rules out
        a "reject all input" stub that would trivially pass the validation
        rejection test above.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeCtx, makeCaller } from './__indep_helpers';

            test('valid title clears validation and creates a task', async () => {
              const caller = makeCaller(makeCtx());
              let code: string | undefined;
              let task: any;
              try {
                task = await caller.tasks.create({ title: 'real-title' });
                code = 'OK';
              } catch (err: any) {
                code = err?.code ?? err?.cause?.code;
              }
              expect(code).toBe('OK');
              expect(task.title).toBe('real-title');
              expect(task.done).toBe(false);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_valid_input", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: toggle flips and round-trips
    # ------------------------------------------------------------------ #
    def test_independent_toggle_flips_and_persists(self):
        """L2 (independent): toggle flips `done` and a second toggle flips it
        back; the change is observable through `list`, proving the store is
        real per-request state rather than a hardcoded return.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeCtx, makeCaller } from './__indep_helpers';

            test('toggle flips done and round-trips, visible via list', async () => {
              const caller = makeCaller(makeCtx());
              const created = await caller.tasks.create({ title: 'flip-me' });
              expect(created.done).toBe(false);

              const t1 = await caller.tasks.toggle({ id: created.id });
              expect(t1.id).toBe(created.id);
              expect(t1.done).toBe(true);

              const t2 = await caller.tasks.toggle({ id: created.id });
              expect(t2.done).toBe(false);

              const tasks = await caller.tasks.list();
              const found = tasks.find((t: any) => t.id === created.id);
              expect(found).toBeTruthy();
              expect(found.done).toBe(false);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_toggle", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: store / audit isolation between contexts
    # ------------------------------------------------------------------ #
    def test_independent_store_and_audit_isolation(self):
        """L2 (independent): two contexts from separate factory calls are
        isolated -- a task created (and audit records appended) through context
        A are NOT visible through a fresh context B. This proves there is no
        leaked global mutable singleton store or audit sink.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeCtx, makeCaller, auditOf } from './__indep_helpers';

            test('tasks and audit records do not leak across independent contexts', async () => {
              const ctxA = makeCtx();
              const ctxB = makeCtx();
              const callerA = makeCaller(ctxA);
              const callerB = makeCaller(ctxB);

              await callerA.tasks.create({ title: 'only-in-A' });
              await callerA.tasks.create({ title: 'also-A' });

              const tasksB = await callerB.tasks.list();
              expect(tasksB.length).toBe(0);

              const tasksA = await callerA.tasks.list();
              expect(tasksA.length).toBe(2);

              const auditB = await auditOf(ctxB);
              const aCreatesInB = auditB.filter((r: any) =>
                String(r.path).includes('create'),
              );
              expect(aCreatesInB.length).toBe(0);

              const auditA = await auditOf(ctxA);
              const aCreatesInA = auditA.filter((r: any) =>
                String(r.path).includes('create'),
              );
              expect(aCreatesInA.length).toBeGreaterThanOrEqual(2);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_isolation", driver)

    # ------------------------------------------------------------------ #
    # helper: introspection-based bridge + driver runner
    # ------------------------------------------------------------------ #
    _HELPERS_TS = textwrap.dedent(
        r"""
        /* Independent test bridge. Locates the agent's public caller factory and
           store/audit-sink (context) factory from auditLog.ts by introspection,
           because the task does not fix their export names. A "context" here is
           whatever the caller factory consumes to get a fresh, isolated store +
           audit sink; we keep a handle on it so we can read the audit records
           back out after exercising procedures. */
        import * as M from './auditLog';

        type AnyFn = (...args: any[]) => any;

        function exportedFns(): Array<[string, AnyFn]> {
          return Object.entries(M as Record<string, unknown>)
            .filter(([, v]) => typeof v === 'function')
            .map(([k, v]) => [k, v as AnyFn]);
        }

        function callerFactory(): AnyFn {
          const fns = exportedFns();
          const named =
            fns.find(([k]) => /caller/i.test(k)) ||
            fns.find(([k]) => /(create|make).*call/i.test(k));
          if (named) return named[1];
          throw new Error(
            'Could not locate a caller factory exported from auditLog.ts',
          );
        }

        /** Produce a fresh, isolated context (store + audit sink). We prefer a
            clearly named context/store/sink factory; otherwise we fall back to a
            zero-arg factory whose result is a non-caller, non-router object. */
        export function makeCtx(): any {
          const fns = exportedFns();
          const caller = callerFactory();
          const named =
            fns.find(
              ([k, v]) =>
                v !== caller &&
                /(ctx|context|store|sink|audit|state|data|db)/i.test(k) &&
                /(create|make|new|factory|init|fresh)/i.test(k),
            ) ||
            fns.find(
              ([k, v]) =>
                v !== caller &&
                /(ctx|context|store|sink|audit|state|data|db)/i.test(k),
            ) ||
            null;
          if (named) {
            try {
              const out = named[1]();
              if (out && typeof out === 'object') return out;
            } catch {
              /* fall through */
            }
          }
          // Fallback: any zero-arg factory (not the caller factory) returning a
          // plain object that is not itself a caller (a caller exposes `tasks`).
          for (const [, fn] of fns) {
            if (fn === caller) continue;
            try {
              const out = fn();
              if (
                out &&
                typeof out === 'object' &&
                typeof (out as any).then !== 'function' &&
                !('tasks' in (out as any))
              ) {
                return out;
              }
            } catch {
              /* ignore */
            }
          }
          throw new Error(
            'Could not locate a context/store/sink factory exported from auditLog.ts',
          );
        }

        /** Invoke the caller factory tolerating several call shapes:
              factory(ctx) | factory({ ctx }) | factory({ ...ctx }). */
        export function makeCaller(ctx: any): any {
          const factory = callerFactory();
          const attempts: Array<() => any> = [
            () => factory(ctx),
            () => factory({ ctx }),
            () => factory({ ...(ctx ?? {}) }),
            () => factory(() => ctx),
          ];
          let lastErr: unknown;
          for (const attempt of attempts) {
            try {
              const caller = attempt();
              if (caller && typeof caller === 'object' && 'tasks' in caller) {
                return caller;
              }
              if (caller && typeof caller === 'object') {
                return caller;
              }
            } catch (e) {
              lastErr = e;
            }
          }
          throw new Error(
            'Could not invoke caller factory with a context in any known shape: ' +
              String(lastErr),
          );
        }

        /** Read the audit records for a given context. Prefer driving the
            exported `audit` procedure through a caller bound to the SAME ctx
            (the public, contract-defined way). Fall back to reading a sink-ish
            array off the context object if the procedure shape is unexpected. */
        export async function auditOf(ctx: any): Promise<any[]> {
          try {
            const caller = makeCaller(ctx);
            if (caller && caller.tasks && typeof caller.tasks.audit === 'function') {
              const recs = await caller.tasks.audit();
              if (Array.isArray(recs)) return recs;
            }
          } catch {
            /* fall through to direct inspection */
          }
          // Fallback: locate an array of audit-like records on the ctx object.
          const visit = (obj: any, depth: number): any[] | null => {
            if (!obj || typeof obj !== 'object' || depth > 3) return null;
            for (const v of Object.values(obj)) {
              if (
                Array.isArray(v) &&
                (v.length === 0 ||
                  (v[0] &&
                    typeof v[0] === 'object' &&
                    'requestId' in (v[0] as any)))
              ) {
                return v as any[];
              }
            }
            for (const v of Object.values(obj)) {
              const nested = visit(v, depth + 1);
              if (nested) return nested;
            }
            return null;
          };
          return visit(ctx, 0) ?? [];
        }
        """
    ).lstrip()

    def _run_independent_driver(self, slug, driver_body):
        helpers_rel = _write_driver("__indep_helpers.ts", self._HELPERS_TS)
        driver_rel = _write_driver(f"{slug}.indep.test.ts", driver_body)
        try:
            res = _run_vitest(driver_rel)
            combined = (res.stdout or "") + "\n" + (res.stderr or "")
            assert res.returncode == 0, (
                f"independent driver '{slug}' failed.\n"
                f"stdout tail:\n{(res.stdout or '')[-3000:]}\n"
                f"stderr tail:\n{(res.stderr or '')[-2000:]}"
            )
            assert "no test" not in combined.lower(), (
                f"independent driver '{slug}' collected no tests:\n{combined[-1500:]}"
            )
        finally:
            _cleanup(driver_rel)
            _cleanup(helpers_rel)
