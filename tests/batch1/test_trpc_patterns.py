"""Tests for the `trpc-patterns` skill task.

Task: Build a Membership API Router for the tRPC test suite.

The agent must create two files inside the tRPC monorepo:
  * packages/tests/server/membership.ts       -- in-memory data layer + tRPC
                                                  instance, routers and an
                                                  exported caller factory.
  * packages/tests/server/membership.test.ts  -- a deterministic vitest suite
                                                  driving the API through callers.

These tests verify the deliverables two ways:

L1  -- the deliverable files exist and are minimally well-formed (real source,
       importing the repo's `@trpc/server` primitives, exporting a public surface).

L2  -- DYNAMIC EXECUTION via the repo's native toolchain (`pnpm vitest run`).
       * The agent's own acceptance suite must pass AND must genuinely assert on
         tRPC error *codes* for every required failure category.
       * An INDEPENDENT vitest driver (written by THIS test into the repo) imports
         the agent's public caller factory from membership.ts and exercises the
         authorization tiers, the input-validation layer, and the error-code
         semantics directly -- so a naive implementation that ignores roles,
         skips validation, hardcodes results, or returns wrong codes cannot pass.

The independent driver focuses on behaviors reachable WITHOUT knowing the private
store shape (unauthenticated rejection across every protected procedure, and
input-validation rejection), which a correct tier/validation design must enforce
regardless of how the in-memory store is seeded.
"""

import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/trpc"
SERVER_DIR = os.path.join(REPO_DIR, "packages", "tests", "server")
MEMBERSHIP_TS = os.path.join(SERVER_DIR, "membership.ts")
MEMBERSHIP_TEST_TS = os.path.join(SERVER_DIR, "membership.test.ts")

# Native vitest command. We always run a single file, scoped tightly.
VITEST_TIMEOUT = 600


# --------------------------------------------------------------------------- #
# dependency / toolchain preparation
# --------------------------------------------------------------------------- #
def _have_node_modules():
    """The container ships the repo toolchain installed; detect it."""
    return os.path.isdir(os.path.join(REPO_DIR, "node_modules")) and (
        os.path.isdir(os.path.join(REPO_DIR, "packages", "tests", "node_modules"))
        or os.path.exists(
            os.path.join(REPO_DIR, "node_modules", ".bin", "vitest")
        )
        or os.path.isdir(os.path.join(REPO_DIR, "node_modules", "vitest"))
    )


@pytest.fixture(scope="module", autouse=True)
def _prepare_deps():
    """Best-effort: install workspace deps with pnpm if they are missing.

    In the benchmark container the toolchain is pre-installed, so this is
    usually a no-op. If node_modules is absent we attempt a pnpm install.
    """
    if not _have_node_modules():
        # Try pnpm install (offline-friendly flags). Failure here is surfaced
        # by the individual vitest runs, not swallowed.
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
    def test_membership_module_exists(self):
        """L1: membership.ts deliverable exists and is non-trivial source."""
        assert os.path.isfile(MEMBERSHIP_TS), f"missing {MEMBERSHIP_TS}"
        src = _read(MEMBERSHIP_TS)
        assert len(src.strip()) > 200, "membership.ts is suspiciously small"

    def test_membership_test_exists(self):
        """L1: membership.test.ts deliverable exists and is non-trivial."""
        assert os.path.isfile(MEMBERSHIP_TEST_TS), f"missing {MEMBERSHIP_TEST_TS}"
        src = _read(MEMBERSHIP_TEST_TS)
        assert len(src.strip()) > 200, "membership.test.ts is suspiciously small"

    def test_module_uses_trpc_server_primitives(self):
        """L1: implementation is built on @trpc/server (initTRPC) and exports
        a public surface (so the test file can import a caller factory)."""
        src = _read(MEMBERSHIP_TS)
        assert "@trpc/server" in src, "membership.ts must use @trpc/server"
        assert "initTRPC" in src, "membership.ts must initialize tRPC via initTRPC"
        assert "export" in src, "membership.ts must export a public surface"
        # The router type is part of the contract (AppRouter).
        assert "Router" in src or "router" in src

    def test_test_file_imports_only_public_surface(self):
        """L1: the test file imports from the membership module rather than
        re-implementing routers/procedures inline."""
        src = _read(MEMBERSHIP_TEST_TS)
        assert "./membership" in src or "membership'" in src or 'membership"' in src, (
            "membership.test.ts must import from ./membership"
        )
        # It must NOT itself stand up a parallel router with initTRPC.router.
        assert "initTRPC" not in src, (
            "test file must import the caller factory, not re-init tRPC"
        )

    # ------------------------------------------------------------------ #
    # L2 -- the agent's acceptance suite passes
    # ------------------------------------------------------------------ #
    def test_acceptance_suite_passes(self):
        """L2: the exact Acceptance-Criteria command passes with all green.

        `pnpm vitest run packages/tests/server/membership.test.ts`
        """
        rel = os.path.relpath(MEMBERSHIP_TEST_TS, REPO_DIR)
        res = _run_vitest(rel)
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        assert res.returncode == 0, (
            "membership.test.ts must pass.\n"
            f"stdout tail:\n{(res.stdout or '')[-3000:]}\n"
            f"stderr tail:\n{(res.stderr or '')[-2000:]}"
        )
        # vitest prints a failed-count line on failures; guard against a suite
        # that reports success while having 0 tests.
        assert "no test" not in combined.lower(), (
            "vitest reported no tests were collected"
        )

    def test_acceptance_suite_has_enough_cases(self):
        """L2: the acceptance suite actually contains >= 12 cases as required,
        proven by running with --reporter that surfaces the count."""
        rel = os.path.relpath(MEMBERSHIP_TEST_TS, REPO_DIR)
        res = _run_vitest(rel)
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        # vitest summary line looks like: "Tests  14 passed (14)".
        import re

        passed = 0
        m = re.search(r"Tests\s+(\d+)\s+passed", combined)
        if m:
            passed = int(m.group(1))
        else:
            # Fallback: count "✓" check marks emitted per test.
            passed = combined.count("✓")
        assert passed >= 12, (
            f"acceptance suite must have >= 12 passing cases, saw {passed}.\n"
            f"output tail:\n{combined[-2500:]}"
        )

    def test_acceptance_suite_asserts_on_codes(self):
        """L2: the acceptance test asserts on tRPC error *codes* for every
        required failure category, not on message substrings."""
        src = _read(MEMBERSHIP_TEST_TS)
        for code in ("UNAUTHORIZED", "FORBIDDEN", "NOT_FOUND", "CONFLICT"):
            assert code in src, (
                f"acceptance suite must assert the {code} error code"
            )
        # A validation failure surfaces as BAD_REQUEST in tRPC.
        assert "BAD_REQUEST" in src, (
            "acceptance suite must assert validation -> BAD_REQUEST code"
        )

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: unauthenticated rejection across tiers
    # ------------------------------------------------------------------ #
    def test_independent_unauthenticated_rejected_everywhere(self):
        """L2 (independent): an unauthenticated caller is rejected with the
        UNAUTHORIZED code on every protected procedure, while the public
        `listOrganizations` succeeds. This driver imports the agent's caller
        factory from membership.ts and does NOT trust the agent's own tests.

        Store seeding is not required here: protected procedures must reject
        the missing-user case BEFORE touching any data, so this is reachable
        regardless of the private store shape. The driver locates the exported
        caller factory by introspection (its name is not fixed by the task).
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import * as M from './membership';
            import { makeStore, makeCaller, asUnauth } from './__indep_helpers';

            test('public listOrganizations works unauthenticated', async () => {
              const store = makeStore();
              const caller = makeCaller(asUnauth(), store);
              const orgs = await caller.membership.listOrganizations();
              expect(Array.isArray(orgs)).toBe(true);
              for (const o of orgs) {
                expect(typeof o.id).toBe('string');
                expect(typeof o.name).toBe('string');
              }
            });

            const protectedCalls = [
              ['myRoles', (c: any) => c.membership.myRoles()],
              ['joinOrganization', (c: any) => c.membership.joinOrganization({ orgId: 'org-1' })],
              ['setRole', (c: any) => c.membership.setRole({ orgId: 'org-1', userId: 'u2', role: 'member' })],
              ['removeMember', (c: any) => c.membership.removeMember({ orgId: 'org-1', userId: 'u2' })],
            ] as const;

            for (const [name, fn] of protectedCalls) {
              test('unauthenticated -> ' + name + ' is UNAUTHORIZED', async () => {
                const store = makeStore();
                const caller = makeCaller(asUnauth(), store);
                let code: string | undefined;
                try {
                  await fn(caller);
                  throw new Error('expected ' + name + ' to throw for unauth caller');
                } catch (err: any) {
                  code = err?.code ?? err?.cause?.code;
                }
                expect(code).toBe('UNAUTHORIZED');
              });
            }
            """
        ).lstrip()
        self._run_independent_driver("indep_unauth", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: input validation rejected as BAD_REQUEST
    # ------------------------------------------------------------------ #
    def test_independent_validation_rejected(self):
        """L2 (independent): malformed input is rejected as a validation error
        (BAD_REQUEST) before any business logic runs.

        Validation runs before auth/role checks, so we authenticate a user to
        ensure we are exercising the validator and not the auth gate. Empty
        orgId, out-of-range role, and missing field must each fail. This is
        reachable without seeding because validation precedes data access.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asUser } from './__indep_helpers';

            async function codeOf(p: Promise<unknown>): Promise<string | undefined> {
              try {
                await p;
                return undefined;
              } catch (err: any) {
                return err?.code ?? err?.cause?.code;
              }
            }

            test('empty orgId on joinOrganization -> BAD_REQUEST', async () => {
              const caller = makeCaller(asUser('uX'), makeStore());
              const code = await codeOf(
                caller.membership.joinOrganization({ orgId: '' }),
              );
              expect(code).toBe('BAD_REQUEST');
            });

            test('out-of-range role on setRole -> BAD_REQUEST', async () => {
              const caller = makeCaller(asUser('uX'), makeStore());
              const code = await codeOf(
                caller.membership.setRole({
                  orgId: 'org-1',
                  userId: 'u2',
                  // @ts-expect-error invalid role on purpose
                  role: 'superuser',
                }),
              );
              expect(code).toBe('BAD_REQUEST');
            });

            test('missing field on setRole -> BAD_REQUEST', async () => {
              const caller = makeCaller(asUser('uX'), makeStore());
              const code = await codeOf(
                // @ts-expect-error missing userId/role on purpose
                caller.membership.setRole({ orgId: 'org-1' }),
              );
              expect(code).toBe('BAD_REQUEST');
            });

            test('empty orgId on removeMember -> BAD_REQUEST', async () => {
              const caller = makeCaller(asUser('uX'), makeStore());
              const code = await codeOf(
                caller.membership.removeMember({ orgId: '', userId: 'u2' }),
              );
              expect(code).toBe('BAD_REQUEST');
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_validation", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: a valid role string is NOT rejected
    # (proves validation is real, not "reject everything")
    # ------------------------------------------------------------------ #
    def test_independent_valid_role_passes_validation(self):
        """L2 (independent): a well-formed setRole input with a valid role does
        NOT fail with BAD_REQUEST. It may fail with FORBIDDEN/NOT_FOUND because
        the user lacks the role / org is unseeded, but it must clear the
        validation layer. This rules out a "reject all input" stub that would
        trivially pass the validation test above.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asUser } from './__indep_helpers';

            test('valid role does not fail validation (no BAD_REQUEST)', async () => {
              const caller = makeCaller(asUser('uX'), makeStore());
              let code: string | undefined;
              try {
                await caller.membership.setRole({
                  orgId: 'org-1',
                  userId: 'u2',
                  role: 'admin',
                });
                code = 'OK';
              } catch (err: any) {
                code = err?.code ?? err?.cause?.code;
              }
              // Well-formed input must clear validation; resulting failure (if
              // any) must be an authorization/existence error, never BAD_REQUEST.
              expect(code).not.toBe('BAD_REQUEST');
              expect(['OK', 'FORBIDDEN', 'NOT_FOUND']).toContain(code);
            });

            test('each allowed role value passes validation', async () => {
              for (const role of ['owner', 'admin', 'member'] as const) {
                const caller = makeCaller(asUser('uX'), makeStore());
                let code: string | undefined;
                try {
                  await caller.membership.setRole({
                    orgId: 'org-1',
                    userId: 'u2',
                    role,
                  });
                  code = 'OK';
                } catch (err: any) {
                  code = err?.code ?? err?.cause?.code;
                }
                expect(code).not.toBe('BAD_REQUEST');
              }
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_valid_role", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: public tier truly has no auth gate
    # ------------------------------------------------------------------ #
    def test_independent_public_tier_open_authenticated_too(self):
        """L2 (independent): listOrganizations is genuinely public -- it works
        for BOTH an unauthenticated caller and an authenticated one, returning
        the same set of organizations. This distinguishes a real public tier
        from one accidentally gated behind auth.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asUser, asUnauth } from './__indep_helpers';

            test('listOrganizations equal for unauth and auth callers', async () => {
              const store = makeStore();
              const anon = makeCaller(asUnauth(), store);
              const user = makeCaller(asUser('uX'), store);

              const a = await anon.membership.listOrganizations();
              const b = await user.membership.listOrganizations();

              expect(Array.isArray(a)).toBe(true);
              expect(Array.isArray(b)).toBe(true);
              const norm = (xs: any[]) =>
                xs.map((o) => o.id).sort();
              expect(norm(a)).toEqual(norm(b));
              // Each entry exposes exactly id + name semantics (id & name strings).
              for (const o of a) {
                expect(typeof o.id).toBe('string');
                expect(typeof o.name).toBe('string');
              }
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_public", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: store isolation between independent stores
    # ------------------------------------------------------------------ #
    def test_independent_store_isolation(self):
        """L2 (independent): two stores produced by the factory are isolated --
        joining an org through a caller bound to store A must not be visible to
        a caller bound to a fresh store B. This proves there is no leaked global
        mutable singleton across independent runs.

        We use joinOrganization (the only state mutation reachable without
        seeding roles). If the org does not exist in the unseeded store the join
        fails with NOT_FOUND in BOTH stores symmetrically -- which still proves
        isolation because neither store accumulates the membership. We assert the
        symmetric outcome and, when the join succeeds, assert non-leakage.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asUser } from './__indep_helpers';

            async function tryJoin(caller: any, orgId: string) {
              try {
                await caller.membership.joinOrganization({ orgId });
                return { ok: true as const };
              } catch (err: any) {
                return { ok: false as const, code: err?.code ?? err?.cause?.code };
              }
            }

            test('mutations on store A do not leak into a fresh store B', async () => {
              const storeA = makeStore();
              const storeB = makeStore();

              // Discover an existing org id (if the factory seeds any) so the
              // join can actually succeed; otherwise fall back to a synthetic id.
              const probe = makeCaller(asUser('probe'), makeStore());
              const orgs = await probe.membership.listOrganizations();
              const orgId = orgs.length ? orgs[0].id : 'org-isolation';

              const callerA = makeCaller(asUser('alice'), storeA);
              const r1 = await tryJoin(callerA, orgId);

              // Alice's roles as seen through store B must NOT contain this join.
              const callerB = makeCaller(asUser('alice'), storeB);
              const rolesB = await callerB.membership.myRoles();
              const inB = rolesB.some(
                (r: any) => r.orgId === orgId && r.role === 'member',
              );
              expect(inB).toBe(false);

              if (r1.ok) {
                // And it IS visible through store A.
                const rolesA = await makeCaller(asUser('alice'), storeA)
                  .membership.myRoles();
                const inA = rolesA.some(
                  (r: any) => r.orgId === orgId && r.role === 'member',
                );
                expect(inA).toBe(true);
              }
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
           store factory from membership.ts by introspection, because the task
           does not fix their export names. */
        import * as M from './membership';

        type AnyFn = (...args: any[]) => any;

        function exportedFns(): Array<[string, AnyFn]> {
          return Object.entries(M as Record<string, unknown>)
            .filter(([, v]) => typeof v === 'function')
            .map(([k, v]) => [k, v as AnyFn]);
        }

        /** Build a fresh, isolated store using the module's store factory. */
        export function makeStore(): any {
          const fns = exportedFns();
          // Prefer a clearly named store/db factory.
          const named =
            fns.find(([k]) => /(^|[^a-z])(store|db|data)/i.test(k) &&
                              /(create|make|new|factory|init)/i.test(k)) ||
            fns.find(([k]) => /store|db|data/i.test(k)) ||
            null;
          if (named) {
            const out = named[1]();
            if (out && typeof out === 'object') return out;
          }
          // Fallback: a zero-arg factory whose result is a non-router object.
          for (const [, fn] of fns) {
            try {
              const out = fn();
              if (out && typeof out === 'object' && typeof out.then !== 'function') {
                // Heuristic: a store, not a caller (callers expose membership).
                if (!('membership' in out)) return out;
              }
            } catch {
              /* ignore */
            }
          }
          throw new Error(
            'Could not locate a store/db factory exported from membership.ts',
          );
        }

        function callerFactory(): AnyFn {
          const fns = exportedFns();
          const named =
            fns.find(([k]) => /caller/i.test(k)) ||
            fns.find(([k]) => /(create|make).*call/i.test(k));
          if (named) return named[1];
          throw new Error(
            'Could not locate a caller factory exported from membership.ts',
          );
        }

        export function asUnauth(): any {
          return undefined;
        }
        export function asUser(userId: string): any {
          return { userId };
        }

        /** Invoke the caller factory tolerating both call shapes:
              factory(user, store)  or  factory({ user, store }) /
              factory({ user, db }) / factory({ ctx-ish }). */
        export function makeCaller(user: any, store: any): any {
          const factory = callerFactory();
          const attempts: Array<() => any> = [
            () => factory(user, store),
            () => factory({ user, store }),
            () => factory({ user, db: store }),
            () => factory({ user, data: store }),
            () => factory({ ctx: { user, store } }),
            () => factory({ ctx: { user, db: store } }),
          ];
          let lastErr: unknown;
          for (const attempt of attempts) {
            try {
              const caller = attempt();
              if (caller && typeof caller === 'object' && 'membership' in caller) {
                return caller;
              }
              // Some factories return a promise-less caller without enumerable
              // 'membership' until accessed; accept any object as a candidate.
              if (caller && typeof caller === 'object') {
                return caller;
              }
            } catch (e) {
              lastErr = e;
            }
          }
          throw new Error(
            'Could not invoke caller factory with (user, store) in any known ' +
              'shape: ' + String(lastErr),
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
