"""Tests for the `trpc-patterns` skill task (variant ext8).

Task: Build a Registration Router with Deep Input Schemas for the tRPC suite.

The agent must create two files inside the tRPC monorepo:
  * packages/tests/server/registration.ts       -- in-memory account store, the
                                                    tRPC instance/helpers, a root
                                                    router nesting an `account`
                                                    sub-router, and an exported
                                                    caller factory.
  * packages/tests/server/registration.test.ts  -- a deterministic vitest suite
                                                    driving the API via callers.

The `register` input schema must be layered + refined: it both REJECTS malformed
data (invalid email, password length, password/confirmPassword mismatch, age
bounds + integer-only, tags de-dup/non-empty) and NORMALIZES accepted data
(email trim+lowercase, numeric-string age coerced to a number). The returned
account must never carry `password`/`confirmPassword`. Distinct error categories
surface as distinct tRPC codes (validation -> BAD_REQUEST, duplicate -> CONFLICT,
unknown get -> NOT_FOUND).

Verification strategy:

L1  -- the deliverable files exist and are minimally well-formed (real source,
       built on `@trpc/server` / initTRPC, exporting a public caller factory;
       the test file imports only the public surface, asserts on error CODES).

L2  -- DYNAMIC EXECUTION via the repo's native toolchain (`pnpm vitest run`).
       * The agent's own acceptance suite must pass and must contain the
         required number of cases.
       * An INDEPENDENT vitest driver (written by THIS test into the repo)
         imports the agent's exported caller factory + store factory from
         registration.ts by introspection and exercises -- WITHOUT knowing the
         private store shape -- the full contract:
           - email normalization affecting store key and output;
           - password never present in any returned account;
           - the password/confirmPassword cross-field rule -> BAD_REQUEST;
           - age bounds (12 / 200 / fractional) -> BAD_REQUEST and the
             numeric-string-in-range coercion ("30" -> number 30);
           - tags de-duplication / non-empty rule -> BAD_REQUEST while a valid
             distinct tag list is accepted;
           - duplicate registration (after normalization) -> CONFLICT;
           - get on an unknown normalized email -> NOT_FOUND;
           - a fully valid registration is NOT rejected (rules out a
             "reject everything" stub).
       Because `register` seeds the store itself, the independent driver needs
       no knowledge of the private store internals.

Native acceptance command driven by L2:
    pnpm vitest run packages/tests/server/registration.test.ts
"""

import os
import re
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/trpc"
SERVER_DIR = os.path.join(REPO_DIR, "packages", "tests", "server")
REGISTRATION_TS = os.path.join(SERVER_DIR, "registration.ts")
REGISTRATION_TEST_TS = os.path.join(SERVER_DIR, "registration.test.ts")

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
    def test_registration_module_exists(self):
        """L1: registration.ts deliverable exists and is non-trivial source."""
        assert os.path.isfile(REGISTRATION_TS), f"missing {REGISTRATION_TS}"
        src = _read(REGISTRATION_TS)
        assert len(src.strip()) > 200, "registration.ts is suspiciously small"

    def test_registration_test_exists(self):
        """L1: registration.test.ts deliverable exists and is non-trivial."""
        assert os.path.isfile(REGISTRATION_TEST_TS), f"missing {REGISTRATION_TEST_TS}"
        src = _read(REGISTRATION_TEST_TS)
        assert len(src.strip()) > 200, "registration.test.ts is suspiciously small"

    def test_module_uses_trpc_server_primitives(self):
        """L1: implementation is built on @trpc/server (initTRPC) and exports a
        public surface (so the test file can import a caller factory)."""
        src = _read(REGISTRATION_TS)
        assert "@trpc/server" in src, "registration.ts must use @trpc/server"
        assert "initTRPC" in src, "registration.ts must initialize tRPC via initTRPC"
        assert "export" in src, "registration.ts must export a public surface"
        assert "Router" in src or "router" in src, (
            "registration.ts must build a router"
        )

    def test_test_file_imports_only_public_surface(self):
        """L1: the test file imports from the registration module rather than
        re-implementing routers/procedures inline."""
        src = _read(REGISTRATION_TEST_TS)
        assert (
            "./registration" in src
            or "registration'" in src
            or 'registration"' in src
        ), "registration.test.ts must import from ./registration"
        assert "initTRPC" not in src, (
            "test file must import the caller factory, not re-init tRPC"
        )

    # ------------------------------------------------------------------ #
    # L2 -- the agent's acceptance suite passes
    # ------------------------------------------------------------------ #
    def test_acceptance_suite_passes(self):
        """L2: the exact Acceptance-Criteria command passes with all green.

        `pnpm vitest run packages/tests/server/registration.test.ts`
        """
        rel = os.path.relpath(REGISTRATION_TEST_TS, REPO_DIR)
        res = _run_vitest(rel)
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        assert res.returncode == 0, (
            "registration.test.ts must pass.\n"
            f"stdout tail:\n{(res.stdout or '')[-3000:]}\n"
            f"stderr tail:\n{(res.stderr or '')[-2000:]}"
        )
        assert "no test" not in combined.lower(), (
            "vitest reported no tests were collected"
        )

    def test_acceptance_suite_has_enough_cases(self):
        """L2: the acceptance suite contains >= 12 cases as required, proven by
        parsing vitest's reported passing count."""
        rel = os.path.relpath(REGISTRATION_TEST_TS, REPO_DIR)
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
        """L2: the acceptance suite asserts on tRPC error *codes* for the
        required failure categories, not on message substrings."""
        src = _read(REGISTRATION_TEST_TS)
        # Validation failures surface as BAD_REQUEST; duplicate -> CONFLICT;
        # unknown get -> NOT_FOUND. All three must be asserted as codes.
        for code in ("BAD_REQUEST", "CONFLICT", "NOT_FOUND"):
            assert code in src, (
                f"acceptance suite must assert the {code} error code"
            )

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: normalization + no-password-leak + happy path
    # ------------------------------------------------------------------ #
    def test_independent_normalize_and_no_password_leak(self):
        """L2 (independent): a valid registration with a messy email
        ("  USER@Example.COM ") succeeds; the returned account email is the
        normalized form, contains `age` and `profile` but NEVER `password`
        nor `confirmPassword`; and `exists`/`get` on the normalized email both
        resolve to that account. This rules out a stub that fails to normalize
        or leaks the password into the output."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller } from './__indep_helpers';

            test('register normalizes email and never leaks password', async () => {
              const caller = makeCaller(makeStore());
              const acct = await caller.account.register({
                email: '  USER@Example.COM ',
                password: 'longenough1',
                confirmPassword: 'longenough1',
                age: 30,
                profile: { displayName: 'U', tags: ['x', 'y'] },
              });
              expect(acct.email).toBe('user@example.com');
              expect(acct.age).toBe(30);
              expect('password' in acct).toBe(false);
              expect('confirmPassword' in acct).toBe(false);
              expect(JSON.stringify(acct)).not.toContain('longenough1');
            });

            test('exists/get use the normalized email key', async () => {
              const caller = makeCaller(makeStore());
              await caller.account.register({
                email: '  USER@Example.COM ',
                password: 'longenough1',
                confirmPassword: 'longenough1',
                age: 30,
              });

              const ex = await caller.account.exists({ email: 'user@example.com' });
              expect(ex).toEqual({ exists: true });

              const exUpper = await caller.account.exists({
                email: 'USER@EXAMPLE.COM',
              });
              expect(exUpper.exists).toBe(true);

              const got = await caller.account.get({ email: 'user@example.com' });
              expect(got.email).toBe('user@example.com');
              expect('password' in got).toBe(false);

              const missing = await caller.account.exists({
                email: 'nobody@example.com',
              });
              expect(missing).toEqual({ exists: false });
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_normalize", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: cross-field + email + password validation
    # ------------------------------------------------------------------ #
    def test_independent_crossfield_and_field_validation(self):
        """L2 (independent): the layered/refined schema rejects, with the
        BAD_REQUEST code, a password/confirmPassword mismatch, a too-short
        password, and a syntactically invalid email -- each BEFORE the body
        runs (never an unhandled crash)."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller } from './__indep_helpers';

            async function codeOf(p: Promise<unknown>): Promise<string | undefined> {
              try {
                await p;
                return undefined;
              } catch (err: any) {
                return err?.code ?? err?.cause?.code;
              }
            }

            test('confirmPassword mismatch -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeStore());
              const code = await codeOf(
                caller.account.register({
                  email: 'a@example.com',
                  password: 'longenough1',
                  confirmPassword: 'different99',
                  age: 30,
                }),
              );
              expect(code).toBe('BAD_REQUEST');
            });

            test('short password -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeStore());
              const code = await codeOf(
                caller.account.register({
                  email: 'a@example.com',
                  password: 'short',
                  confirmPassword: 'short',
                  age: 30,
                }),
              );
              expect(code).toBe('BAD_REQUEST');
            });

            test('invalid email -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeStore());
              const code = await codeOf(
                caller.account.register({
                  email: 'not-an-email',
                  password: 'longenough1',
                  confirmPassword: 'longenough1',
                  age: 30,
                }),
              );
              expect(code).toBe('BAD_REQUEST');
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_crossfield", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: age bounds + integer-string coercion
    # ------------------------------------------------------------------ #
    def test_independent_age_bounds_and_coercion(self):
        """L2 (independent): age below 13, above 120, and fractional are each
        rejected as BAD_REQUEST, while a numeric STRING in range ("30") is
        accepted and coerced to the NUMBER 30 in the stored/returned account.
        This rules out a stub that skips range checks or that fails to coerce
        (e.g. stores the string "30")."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller } from './__indep_helpers';

            async function codeOf(p: Promise<unknown>): Promise<string | undefined> {
              try {
                await p;
                return undefined;
              } catch (err: any) {
                return err?.code ?? err?.cause?.code;
              }
            }

            for (const [label, age] of [
              ['too young (12)', 12],
              ['too old (200)', 200],
              ['fractional (30.5)', 30.5],
            ] as const) {
              test('age ' + label + ' -> BAD_REQUEST', async () => {
                const caller = makeCaller(makeStore());
                const code = await codeOf(
                  caller.account.register({
                    email: 'a@example.com',
                    password: 'longenough1',
                    confirmPassword: 'longenough1',
                    age: age as any,
                  }),
                );
                expect(code).toBe('BAD_REQUEST');
              });
            }

            test('numeric string age "30" is coerced to number 30', async () => {
              const caller = makeCaller(makeStore());
              const acct = await caller.account.register({
                email: 'a@example.com',
                password: 'longenough1',
                confirmPassword: 'longenough1',
                age: '30' as any,
              });
              expect(acct.age).toBe(30);
              expect(typeof acct.age).toBe('number');

              const got = await caller.account.get({ email: 'a@example.com' });
              expect(got.age).toBe(30);
              expect(typeof got.age).toBe('number');
            });

            test('out-of-range numeric string age "12" -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeStore());
              const code = await codeOf(
                caller.account.register({
                  email: 'a@example.com',
                  password: 'longenough1',
                  confirmPassword: 'longenough1',
                  age: '12' as any,
                }),
              );
              expect(code).toBe('BAD_REQUEST');
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_age", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: tags de-dup / non-empty rule
    # ------------------------------------------------------------------ #
    def test_independent_tags_dedup_rule(self):
        """L2 (independent): profile.tags with duplicates (after trimming) or
        with empty entries is rejected as BAD_REQUEST, while a distinct,
        non-empty tag list is accepted. This rules out a stub that ignores the
        tags refinement entirely (which would accept duplicates)."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller } from './__indep_helpers';

            async function codeOf(p: Promise<unknown>): Promise<string | undefined> {
              try {
                await p;
                return undefined;
              } catch (err: any) {
                return err?.code ?? err?.cause?.code;
              }
            }

            test('duplicate tags -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeStore());
              const code = await codeOf(
                caller.account.register({
                  email: 'a@example.com',
                  password: 'longenough1',
                  confirmPassword: 'longenough1',
                  age: 30,
                  profile: { tags: ['a', 'a'] },
                }),
              );
              expect(code).toBe('BAD_REQUEST');
            });

            test('empty tag entry -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeStore());
              const code = await codeOf(
                caller.account.register({
                  email: 'a@example.com',
                  password: 'longenough1',
                  confirmPassword: 'longenough1',
                  age: 30,
                  profile: { tags: ['', 'b'] },
                }),
              );
              expect(code).toBe('BAD_REQUEST');
            });

            test('distinct non-empty tags are accepted', async () => {
              const caller = makeCaller(makeStore());
              const acct = await caller.account.register({
                email: 'a@example.com',
                password: 'longenough1',
                confirmPassword: 'longenough1',
                age: 30,
                profile: { tags: ['a', 'b'] },
              });
              expect('password' in acct).toBe(false);
              const got = await caller.account.get({ email: 'a@example.com' });
              expect(Array.isArray(got.profile?.tags)).toBe(true);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_tags", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: distinct error codes (conflict / not-found)
    # ------------------------------------------------------------------ #
    def test_independent_conflict_and_not_found_codes(self):
        """L2 (independent): distinct categories surface distinct tRPC codes --
        a second registration for the SAME normalized email (even spelled with
        different case/whitespace) is a CONFLICT, while `get` on an unknown
        normalized email is NOT_FOUND. This rules out a stub that ignores
        duplicates or returns a generic error for both categories."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller } from './__indep_helpers';

            async function codeOf(p: Promise<unknown>): Promise<string | undefined> {
              try {
                await p;
                return undefined;
              } catch (err: any) {
                return err?.code ?? err?.cause?.code;
              }
            }

            test('duplicate registration (post-normalization) -> CONFLICT', async () => {
              const caller = makeCaller(makeStore());
              await caller.account.register({
                email: 'user@example.com',
                password: 'longenough1',
                confirmPassword: 'longenough1',
                age: 30,
              });
              const code = await codeOf(
                caller.account.register({
                  email: '  USER@Example.COM ',
                  password: 'longenough1',
                  confirmPassword: 'longenough1',
                  age: 40,
                }),
              );
              expect(code).toBe('CONFLICT');
            });

            test('get on unknown normalized email -> NOT_FOUND', async () => {
              const caller = makeCaller(makeStore());
              const code = await codeOf(
                caller.account.get({ email: 'ghost@example.com' }),
              );
              expect(code).toBe('NOT_FOUND');
            });

            test('conflict and not-found are different codes', async () => {
              const caller = makeCaller(makeStore());
              await caller.account.register({
                email: 'dup@example.com',
                password: 'longenough1',
                confirmPassword: 'longenough1',
                age: 30,
              });
              const conflict = await codeOf(
                caller.account.register({
                  email: 'dup@example.com',
                  password: 'longenough1',
                  confirmPassword: 'longenough1',
                  age: 30,
                }),
              );
              const notFound = await codeOf(
                caller.account.get({ email: 'ghost2@example.com' }),
              );
              expect(conflict).toBe('CONFLICT');
              expect(notFound).toBe('NOT_FOUND');
              expect(conflict).not.toBe(notFound);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_codes", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: store isolation across factory instances
    # ------------------------------------------------------------------ #
    def test_independent_store_isolation(self):
        """L2 (independent): two stores produced by the factory are isolated --
        an account registered through a caller bound to store A is NOT visible
        through a caller bound to a fresh store B. This proves the data layer is
        per-store (a fresh store per call) and not a leaked global singleton."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller } from './__indep_helpers';

            test('registration in store A is not visible in fresh store B', async () => {
              const storeA = makeStore();
              const storeB = makeStore();

              const callerA = makeCaller(storeA);
              await callerA.account.register({
                email: 'iso@example.com',
                password: 'longenough1',
                confirmPassword: 'longenough1',
                age: 30,
              });

              const inA = await callerA.account.exists({ email: 'iso@example.com' });
              expect(inA.exists).toBe(true);

              const callerB = makeCaller(storeB);
              const inB = await callerB.account.exists({ email: 'iso@example.com' });
              expect(inB.exists).toBe(false);
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
           store factory from registration.ts by introspection, because the task
           does not fix their export names. Callers are bound to a fresh store so
           every behavior is reachable without knowing the private store shape. */
        import * as M from './registration';

        type AnyFn = (...args: any[]) => any;

        function exportedFns(): Array<[string, AnyFn]> {
          return Object.entries(M as Record<string, unknown>)
            .filter(([, v]) => typeof v === 'function')
            .map(([k, v]) => [k, v as AnyFn]);
        }

        function looksLikeCaller(obj: any): boolean {
          if (!obj || typeof obj !== 'object') return false;
          // The contract nests an `account` sub-router on the root caller.
          if (obj.account && typeof obj.account === 'object') return true;
          return false;
        }

        /** Build a fresh, isolated account store using the module's store
            factory. A store is a zero-arg factory whose result is a plain
            object that is NOT itself a caller (no `account` sub-router). */
        export function makeStore(): any {
          const fns = exportedFns();
          const named =
            fns.find(([k]) => /(store|db|data|account)/i.test(k) &&
                              /(create|make|new|factory|init|fresh)/i.test(k)) ||
            fns.find(([k]) => /(store|db|data)/i.test(k)) ||
            null;
          if (named) {
            try {
              const out = named[1]();
              if (out && typeof out === 'object' && !looksLikeCaller(out)) {
                return out;
              }
            } catch {
              /* fall through to heuristic scan */
            }
          }
          for (const [, fn] of fns) {
            try {
              const out = fn();
              if (
                out &&
                typeof out === 'object' &&
                typeof out.then !== 'function' &&
                !looksLikeCaller(out)
              ) {
                return out;
              }
            } catch {
              /* ignore */
            }
          }
          throw new Error(
            'Could not locate a store/db factory exported from registration.ts',
          );
        }

        function callerFactory(): AnyFn {
          const fns = exportedFns();
          const named =
            fns.find(([k]) => /caller/i.test(k)) ||
            fns.find(([k]) => /(create|make).*call/i.test(k));
          if (named) return named[1];
          throw new Error(
            'Could not locate a caller factory exported from registration.ts',
          );
        }

        /** Invoke the caller factory tolerating several call shapes:
              factory(store) / factory({ store }) / factory({ db }) /
              factory({ data }) / factory({ ctx: { store } }) / factory({ ctx }). */
        export function makeCaller(store: any): any {
          const factory = callerFactory();
          const attempts: Array<() => any> = [
            () => factory(store),
            () => factory({ store }),
            () => factory({ db: store }),
            () => factory({ data: store }),
            () => factory({ accounts: store }),
            () => factory({ ctx: { store } }),
            () => factory({ ctx: { db: store } }),
            () => factory({ ctx: store }),
          ];
          let lastErr: unknown;
          for (const attempt of attempts) {
            try {
              const caller = attempt();
              if (looksLikeCaller(caller)) return caller;
              if (caller && typeof caller === 'object') return caller;
            } catch (e) {
              lastErr = e;
            }
          }
          throw new Error(
            'Could not invoke caller factory with a store in any known shape: ' +
              String(lastErr),
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
