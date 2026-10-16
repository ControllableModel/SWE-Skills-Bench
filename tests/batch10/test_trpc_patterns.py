"""Tests for the `trpc-patterns` skill task (variant ext10).

Task: Build a Context-Backed Rate-Limited Counter API for the tRPC test suite.

The agent must create two files inside the tRPC monorepo:
  * packages/tests/server/quotaCounter.ts       -- in-memory counter store +
                                                   quota tracker, an ASYNC
                                                   context factory, the tRPC
                                                   instance/router, and an
                                                   exported caller factory.
  * packages/tests/server/quotaCounter.test.ts  -- a deterministic vitest suite
                                                   driving the API through the
                                                   exported caller factory only.

Contract highlights re-derived from THIS variant doc (NOT ext1):
  * Root router nests a `counter` sub-router with four procedures:
      - current(  {key} )            public, read-only  -> { key, value }
      - increment({key, by?})        authed, mutating   -> new numeric value
      - reset(    {key} )            authed, mutating   -> { key, value: 0 }
      - remaining()                  authed, read-only  -> { remaining }
  * Per-USER quota of mutating ops (small fixed int, e.g. 3) resolved into the
    request CONTEXT at context-creation time. Each successful mutating call
    consumes one unit; at 0 further mutating calls -> TOO_MANY_REQUESTS.
  * Read-only calls (current, remaining) never consume quota.
  * Anonymous caller on an authed procedure -> UNAUTHORIZED.
  * Malformed input -> BAD_REQUEST, and a validation failure must NOT consume
    quota (validation precedes mutation/consumption).
  * Quota lives per-request/context: a fresh caller-factory call for the same
    user restores the full quota.
  * Shared stores are passed per caller-factory call so independent runs are
    isolated (no global mutable singleton).

Verification strategy:

L1  -- the deliverable files exist and are minimally well-formed (real source,
       async context factory on `@trpc/server`/`initTRPC`, exported public
       surface; the test file imports the public surface rather than re-init'ing
       tRPC).

L2  -- DYNAMIC EXECUTION via the repo's native toolchain (`pnpm vitest run`).
       * The agent's own acceptance suite must pass, contain >= 12 cases, and
         assert on tRPC error *codes* (UNAUTHORIZED / TOO_MANY_REQUESTS /
         BAD_REQUEST).
       * An INDEPENDENT vitest driver (written by THIS test into the repo)
         imports the agent's caller factory from quotaCounter.ts and exercises
         the authorization tiers, quota consumption + the too-many-requests
         boundary, read-only-no-consume, validation-no-consume, per-context
         quota reset, and store isolation directly -- so a naive implementation
         that stores quota globally, decrements on validation failures, lets
         read-only calls consume quota, or ignores the authed tier cannot pass.

The independent driver discovers the agent's exported caller factory by
introspection (the task does not fix its export name) and tolerates several
plausible call shapes for "(actingUser, sharedStores)".
"""

import os
import re
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/trpc"
SERVER_DIR = os.path.join(REPO_DIR, "packages", "tests", "server")
QUOTA_TS = os.path.join(SERVER_DIR, "quotaCounter.ts")
QUOTA_TEST_TS = os.path.join(SERVER_DIR, "quotaCounter.test.ts")

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
    def test_quota_module_exists(self):
        """L1: quotaCounter.ts deliverable exists and is non-trivial source."""
        assert os.path.isfile(QUOTA_TS), f"missing {QUOTA_TS}"
        src = _read(QUOTA_TS)
        assert len(src.strip()) > 200, "quotaCounter.ts is suspiciously small"

    def test_quota_test_exists(self):
        """L1: quotaCounter.test.ts deliverable exists and is non-trivial."""
        assert os.path.isfile(QUOTA_TEST_TS), f"missing {QUOTA_TEST_TS}"
        src = _read(QUOTA_TEST_TS)
        assert len(src.strip()) > 200, "quotaCounter.test.ts is suspiciously small"

    def test_module_uses_trpc_server_primitives(self):
        """L1: implementation is built on @trpc/server (initTRPC), exports a
        public surface (so the test file can import a caller factory), and
        references an asynchronous context factory (async function feeding the
        request context)."""
        src = _read(QUOTA_TS)
        assert "@trpc/server" in src, "quotaCounter.ts must use @trpc/server"
        assert "initTRPC" in src, "quotaCounter.ts must initialize tRPC via initTRPC"
        assert "export" in src, "quotaCounter.ts must export a public surface"
        assert "Router" in src or "router" in src, "must define a router"
        # An asynchronous context factory is a hard requirement of this variant.
        assert "async" in src, (
            "quotaCounter.ts must define an asynchronous context factory"
        )

    def test_test_file_imports_only_public_surface(self):
        """L1: the test file imports from the quotaCounter module rather than
        re-implementing routers/procedures inline."""
        src = _read(QUOTA_TEST_TS)
        assert (
            "./quotaCounter" in src
            or "quotaCounter'" in src
            or 'quotaCounter"' in src
        ), "quotaCounter.test.ts must import from ./quotaCounter"
        assert "initTRPC" not in src, (
            "test file must import the caller factory, not re-init tRPC"
        )

    # ------------------------------------------------------------------ #
    # L2 -- the agent's acceptance suite passes
    # ------------------------------------------------------------------ #
    def test_acceptance_suite_passes(self):
        """L2: the exact Acceptance-Criteria command passes with all green.

        `pnpm vitest run packages/tests/server/quotaCounter.test.ts`
        """
        rel = os.path.relpath(QUOTA_TEST_TS, REPO_DIR)
        res = _run_vitest(rel)
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        assert res.returncode == 0, (
            "quotaCounter.test.ts must pass.\n"
            f"stdout tail:\n{(res.stdout or '')[-3000:]}\n"
            f"stderr tail:\n{(res.stderr or '')[-2000:]}"
        )
        assert "no test" not in combined.lower(), (
            "vitest reported no tests were collected"
        )

    def test_acceptance_suite_has_enough_cases(self):
        """L2: the acceptance suite actually contains >= 12 cases as required,
        proven by running and parsing the vitest summary."""
        rel = os.path.relpath(QUOTA_TEST_TS, REPO_DIR)
        res = _run_vitest(rel)
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        passed = 0
        m = re.search(r"Tests\s+(\d+)\s+passed", combined)
        if m:
            passed = int(m.group(1))
        else:
            passed = combined.count("✓")
        assert passed >= 12, (
            f"acceptance suite must have >= 12 passing cases, saw {passed}.\n"
            f"output tail:\n{combined[-2500:]}"
        )

    def test_acceptance_suite_asserts_on_codes(self):
        """L2: the acceptance suite asserts on tRPC error *codes* for every
        required failure category, not on message substrings.

        Required categories for THIS variant:
          anonymous-on-authed -> UNAUTHORIZED
          quota exceeded       -> TOO_MANY_REQUESTS
          invalid input        -> BAD_REQUEST
        """
        src = _read(QUOTA_TEST_TS)
        for code in ("UNAUTHORIZED", "TOO_MANY_REQUESTS", "BAD_REQUEST"):
            assert code in src, (
                f"acceptance suite must assert the {code} error code"
            )

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: authorization tiers
    # ------------------------------------------------------------------ #
    def test_independent_auth_tiers(self):
        """L2 (independent): the public `current` is callable anonymously and
        returns the default value 0 for an unset key, while every authed
        procedure (increment/reset/remaining) rejects an anonymous caller with
        UNAUTHORIZED. Imports the agent's caller factory; does not trust the
        agent's own tests.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asUnauth, codeOf } from './__indep_helpers';

            test('anonymous current({key}) -> { key, value: 0 } for unset key', async () => {
              const caller = await makeCaller(asUnauth(), makeStore());
              const out = await caller.counter.current({ key: 'k-anon' });
              expect(out.key).toBe('k-anon');
              expect(out.value).toBe(0);
            });

            const authed: Array<[string, (c: any) => Promise<unknown>]> = [
              ['increment', (c) => c.counter.increment({ key: 'k', by: 1 })],
              ['reset', (c) => c.counter.reset({ key: 'k' })],
              ['remaining', (c) => c.counter.remaining()],
            ];

            for (const [name, fn] of authed) {
              test('anonymous -> ' + name + ' is UNAUTHORIZED', async () => {
                const caller = await makeCaller(asUnauth(), makeStore());
                const code = await codeOf(fn(caller));
                expect(code).toBe('UNAUTHORIZED');
              });
            }
            """
        ).lstrip()
        self._run_independent_driver("indep_tiers", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: increment actually mutates + reads back
    # ------------------------------------------------------------------ #
    def test_independent_increment_and_readback(self):
        """L2 (independent): an authenticated increment by N changes the stored
        value, and the public `current` reads back exactly that value. This
        rules out a stub that hardcodes a return value or ignores `by` / `key`.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asUser, asUnauth } from './__indep_helpers';

            test('increment by 5 -> value 5, current reads back 5', async () => {
              const store = makeStore();
              const user = await makeCaller(asUser('u1'), store);
              const ret = await user.counter.increment({ key: 'kc', by: 5 });
              const val = typeof ret === 'number' ? ret : (ret as any).value;
              expect(val).toBe(5);

              // Read back via the public tier, possibly with a fresh anon caller
              // bound to the SAME shared store.
              const anon = await makeCaller(asUnauth(), store);
              const cur = await anon.counter.current({ key: 'kc' });
              expect(cur.key).toBe('kc');
              expect(cur.value).toBe(5);
            });

            test('default by is 1 and distinct keys are independent', async () => {
              const store = makeStore();
              const user = await makeCaller(asUser('u2'), store);
              await user.counter.increment({ key: 'a' });          // +1 -> 1
              const anon = await makeCaller(asUnauth(), store);
              expect((await anon.counter.current({ key: 'a' })).value).toBe(1);
              // Untouched key stays at default 0.
              expect((await anon.counter.current({ key: 'b' })).value).toBe(0);
            });

            test('reset sets the key to 0', async () => {
              const store = makeStore();
              const user = await makeCaller(asUser('u3'), store);
              await user.counter.increment({ key: 'r', by: 7 });
              const fresh = await makeCaller(asUser('u3'), store);
              const out = await fresh.counter.reset({ key: 'r' });
              expect(out.key).toBe('r');
              expect(out.value).toBe(0);
              const anon = await makeCaller(asUnauth(), store);
              expect((await anon.counter.current({ key: 'r' })).value).toBe(0);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_increment", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: quota boundary at the per-context limit
    # ------------------------------------------------------------------ #
    def test_independent_quota_boundary(self):
        """L2 (independent): within ONE context, mutating calls consume quota.
        The Nth+1 mutating call (after the quota is exhausted) fails with
        TOO_MANY_REQUESTS, and `remaining` reflects 0 without itself erroring.

        We do not hardcode the quota size; we discover it by issuing increments
        until one is rejected, then assert the rejection code and the residual
        `remaining`. A correct impl must reject at some finite limit >= 1; a
        global/no-op quota would either never reject or reject the very first
        authed call (both ruled out below).
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asUser, codeOf } from './__indep_helpers';

            test('mutating calls exhaust a finite per-context quota -> TOO_MANY_REQUESTS', async () => {
              const store = makeStore();
              const caller = await makeCaller(asUser('q1'), store);

              // remaining is a read-only probe; it must work and be a number > 0.
              const r0 = await caller.counter.remaining();
              const start = (r0 as any).remaining;
              expect(typeof start).toBe('number');
              expect(start).toBeGreaterThan(0);

              let consumed = 0;
              let rejectCode: string | undefined;
              // Bound the loop generously; the quota is a small fixed integer.
              for (let i = 0; i < 50; i++) {
                const code = await codeOf(
                  caller.counter.increment({ key: 'q', by: 1 }),
                );
                if (code === undefined) {
                  consumed++;
                  continue;
                }
                rejectCode = code;
                break;
              }

              // The first mutating call must have SUCCEEDED (not gated wrongly).
              expect(consumed).toBeGreaterThanOrEqual(1);
              // Quota is finite: we eventually got rejected.
              expect(rejectCode).toBe('TOO_MANY_REQUESTS');
              // We consumed exactly the starting quota before being rejected.
              expect(consumed).toBe(start);

              // remaining must now reflect 0 and must NOT itself throw.
              const r1 = await caller.counter.remaining();
              expect((r1 as any).remaining).toBe(0);

              // A further reset (also mutating) is likewise rejected.
              const resetCode = await codeOf(caller.counter.reset({ key: 'q' }));
              expect(resetCode).toBe('TOO_MANY_REQUESTS');
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_quota", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: read-only calls never consume quota
    # ------------------------------------------------------------------ #
    def test_independent_readonly_no_consume(self):
        """L2 (independent): repeated `current` and `remaining` calls do NOT
        decrement the quota. After many read-only calls the full quota must
        still be available for mutating calls. Rules out a naive impl that
        consumes quota on every procedure.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asUser, asUnauth } from './__indep_helpers';

            test('current/remaining do not consume quota', async () => {
              const store = makeStore();
              const caller = await makeCaller(asUser('ro'), store);

              const start = (await caller.counter.remaining()).remaining as number;
              expect(start).toBeGreaterThan(0);

              // Hammer the read-only procedures.
              const anon = await makeCaller(asUnauth(), store);
              for (let i = 0; i < 10; i++) {
                await anon.counter.current({ key: 'ro' });
                await caller.counter.remaining();
              }

              // Quota must be untouched.
              const after = (await caller.counter.remaining()).remaining as number;
              expect(after).toBe(start);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_readonly", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: validation failures don't consume quota
    # ------------------------------------------------------------------ #
    def test_independent_validation_no_consume(self):
        """L2 (independent): malformed input on a mutating procedure is rejected
        as BAD_REQUEST *before* any quota consumption -- the remaining quota is
        unchanged after a validation failure. Also asserts a non-integer `by`
        and an empty `key` are both BAD_REQUEST, while a valid call clears
        validation (proving the validator is real, not "reject everything").
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asUser, codeOf } from './__indep_helpers';

            test('empty key -> BAD_REQUEST and quota untouched', async () => {
              const store = makeStore();
              const caller = await makeCaller(asUser('v1'), store);
              const start = (await caller.counter.remaining()).remaining as number;

              const code = await codeOf(caller.counter.increment({ key: '', by: 1 }));
              expect(code).toBe('BAD_REQUEST');

              const after = (await caller.counter.remaining()).remaining as number;
              expect(after).toBe(start);
            });

            test('non-integer by -> BAD_REQUEST and quota untouched', async () => {
              const store = makeStore();
              const caller = await makeCaller(asUser('v2'), store);
              const start = (await caller.counter.remaining()).remaining as number;

              const code = await codeOf(
                // @ts-expect-error fractional by on purpose
                caller.counter.increment({ key: 'k', by: 1.5 }),
              );
              expect(code).toBe('BAD_REQUEST');

              const after = (await caller.counter.remaining()).remaining as number;
              expect(after).toBe(start);
            });

            test('valid increment clears validation (no BAD_REQUEST) and consumes one', async () => {
              const store = makeStore();
              const caller = await makeCaller(asUser('v3'), store);
              const start = (await caller.counter.remaining()).remaining as number;

              const code = await codeOf(caller.counter.increment({ key: 'k', by: -2 }));
              // Negative integer `by` is allowed by the doc -> must NOT be BAD_REQUEST.
              expect(code).not.toBe('BAD_REQUEST');
              expect(code).toBeUndefined();

              const after = (await caller.counter.remaining()).remaining as number;
              expect(after).toBe(start - 1);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_validation", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: quota is per-context, not global
    # ------------------------------------------------------------------ #
    def test_independent_quota_per_context_reset(self):
        """L2 (independent): a FRESH caller-factory call for the SAME user (and
        same shared store) restores the full quota. This proves quota lives per
        request/context and is NOT a leaked global counter. A naive impl storing
        quota globally fails: the second context would start already-depleted.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asUser, codeOf } from './__indep_helpers';

            test('fresh context for same user restores full quota', async () => {
              const store = makeStore();

              // Context A: drain the quota fully.
              const a = await makeCaller(asUser('same'), store);
              const start = (await a.counter.remaining()).remaining as number;
              expect(start).toBeGreaterThan(0);
              for (let i = 0; i < start; i++) {
                const code = await codeOf(a.counter.increment({ key: 'pc', by: 1 }));
                expect(code).toBeUndefined();
              }
              // A is now exhausted.
              expect((await a.counter.remaining()).remaining).toBe(0);
              expect(await codeOf(a.counter.increment({ key: 'pc' }))).toBe(
                'TOO_MANY_REQUESTS',
              );

              // Context B: brand-new caller for the SAME user -> quota restored.
              const b = await makeCaller(asUser('same'), store);
              expect((await b.counter.remaining()).remaining).toBe(start);
              // And B can mutate again right away.
              expect(await codeOf(b.counter.increment({ key: 'pc', by: 1 }))).toBe(
                undefined,
              );
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_per_context", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: store isolation across independent stores
    # ------------------------------------------------------------------ #
    def test_independent_store_isolation(self):
        """L2 (independent): two stores produced by the factory are isolated --
        incrementing a key through a caller bound to store A is invisible to a
        caller bound to a fresh store B. Proves there is no leaked global
        mutable counter singleton across independent runs.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asUser, asUnauth } from './__indep_helpers';

            test('counter mutations on store A do not leak into a fresh store B', async () => {
              const storeA = makeStore();
              const storeB = makeStore();

              const userA = await makeCaller(asUser('alice'), storeA);
              await userA.counter.increment({ key: 'iso', by: 9 });

              // Through store A the value is 9 ...
              const anonA = await makeCaller(asUnauth(), storeA);
              expect((await anonA.counter.current({ key: 'iso' })).value).toBe(9);

              // ... but a fresh store B never saw the mutation: still default 0.
              const anonB = await makeCaller(asUnauth(), storeB);
              expect((await anonB.counter.current({ key: 'iso' })).value).toBe(0);
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
           shared-store factory from quotaCounter.ts by introspection, because
           the task does not fix their export names. The caller factory takes the
           acting user (optional userId) plus the shared stores, and (per the
           async-context-factory requirement) MAY be async -- so makeCaller is
           awaited at every call site. */
        import * as M from './quotaCounter';

        type AnyFn = (...args: any[]) => any;

        function exportedFns(): Array<[string, AnyFn]> {
          return Object.entries(M as Record<string, unknown>)
            .filter(([, v]) => typeof v === 'function')
            .map(([k, v]) => [k, v as AnyFn]);
        }

        /** Extract a tRPC-ish error code from a rejected promise. */
        export async function codeOf(p: Promise<unknown>): Promise<string | undefined> {
          try {
            await p;
            return undefined;
          } catch (err: any) {
            return err?.code ?? err?.cause?.code;
          }
        }

        /** Build a fresh, isolated store using the module's store factory. */
        export function makeStore(): any {
          const fns = exportedFns();
          const named =
            fns.find(([k]) => /(store|db|data|counter)/i.test(k) &&
                              /(create|make|new|factory|init)/i.test(k)) ||
            fns.find(([k]) => /(store|db|data)/i.test(k) && !/call/i.test(k)) ||
            null;
          if (named) {
            try {
              const out = named[1]();
              if (out && typeof out === 'object') return out;
            } catch {
              /* fall through */
            }
          }
          // Fallback: a zero-arg factory whose result is a plain object that is
          // not itself a caller (callers expose a `counter` sub-router).
          for (const [k, fn] of fns) {
            if (/call/i.test(k)) continue;
            try {
              const out = fn();
              if (
                out &&
                typeof out === 'object' &&
                typeof (out as any).then !== 'function' &&
                !('counter' in out)
              ) {
                return out;
              }
            } catch {
              /* ignore */
            }
          }
          throw new Error(
            'Could not locate a store factory exported from quotaCounter.ts',
          );
        }

        function callerFactory(): AnyFn {
          const fns = exportedFns();
          const named =
            fns.find(([k]) => /caller/i.test(k)) ||
            fns.find(([k]) => /(create|make).*call/i.test(k));
          if (named) return named[1];
          throw new Error(
            'Could not locate a caller factory exported from quotaCounter.ts',
          );
        }

        export function asUnauth(): any {
          return undefined;
        }
        export function asUser(userId: string): any {
          return { userId };
        }

        function looksLikeCaller(c: any): boolean {
          return !!c && typeof c === 'object' && 'counter' in c;
        }

        /** Invoke the caller factory tolerating both the positional shape
              factory(actingUser, store)  and several object shapes, AND a
              possibly-async factory (async context factory). Always returns a
              resolved caller object. */
        export async function makeCaller(user: any, store: any): Promise<any> {
          const factory = callerFactory();
          const attempts: Array<() => any> = [
            () => factory(user, store),
            () => factory({ user, store }),
            () => factory({ user, db: store }),
            () => factory({ user, data: store }),
            () => factory({ user, stores: store }),
            () => factory({ ctx: { user, store } }),
            () => factory({ ctx: { user, db: store } }),
            () => factory(store, user),
          ];
          let lastErr: unknown;
          for (const attempt of attempts) {
            try {
              let caller = attempt();
              if (caller && typeof caller.then === 'function') {
                caller = await caller;
              }
              if (looksLikeCaller(caller)) return caller;
              if (caller && typeof caller === 'object') {
                // Accept any object candidate; sub-router access happens lazily.
                return caller;
              }
            } catch (e) {
              lastErr = e;
            }
          }
          throw new Error(
            'Could not invoke caller factory with (actingUser, store) in any ' +
              'known shape: ' + String(lastErr),
          );
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
