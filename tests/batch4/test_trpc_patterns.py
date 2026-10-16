"""Tests for the `trpc-patterns` skill task (variant ext4).

Task: Build a Permission-Metadata Document Router inside the tRPC monorepo.

The agent must create two files under packages/tests/server/:
  * docPerms.ts       -- an in-memory document store, a metadata-typed tRPC
                         instance (initTRPC.meta<...>()), a SINGLE central
                         enforcement step that reads `requiredPermission` from
                         each procedure's metadata, the docs router, and an
                         exported caller factory.
  * docPerms.test.ts  -- a deterministic vitest suite (>= 12 cases) importing
                         only the public surface from docPerms.ts and asserting
                         on tRPC error *codes*.

Verification strategy
=====================
L1 -- the deliverable files exist, are real source, are built on @trpc/server
      with a metadata-typed instance, and the test imports the public surface
      rather than re-initialising tRPC.

L2 -- DYNAMIC EXECUTION via the repo's native toolchain `pnpm vitest run`.
      * The agent's own acceptance suite must pass AND genuinely assert on the
        UNAUTHORIZED / FORBIDDEN / NOT_FOUND / BAD_REQUEST codes.
      * An INDEPENDENT vitest driver (written by THIS test into the repo)
        imports the agent's caller factory + store factory from docPerms.ts by
        introspection (export names are not fixed by the task) and exercises the
        permission matrix directly. This is the discriminative core of the task:
          - the no-permission `ping` works for an anonymous caller;
          - an anonymous caller hitting a gated procedure is UNAUTHORIZED;
          - an AUTHENTICATED caller lacking the permission is FORBIDDEN
            (the unauthorized-vs-forbidden distinction, which a naive impl that
             treats every rejection the same cannot satisfy);
          - the declared permission per procedure is honoured (read-only grant
            unlocks get/list but not upsert/remove; a write grant makes the
            write observable through a read; a delete grant lets remove succeed
            and a second remove returns NOT_FOUND);
          - validation (empty id) fails as BAD_REQUEST before business logic.

      A naive implementation that hardcodes per-procedure checks while ignoring
      the metadata, that fails to distinguish anonymous (UNAUTHORIZED) from an
      under-privileged authenticated principal (FORBIDDEN), that skips storage,
      or that skips validation, cannot pass the independent driver.
"""

import os
import re
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/trpc"
SERVER_DIR = os.path.join(REPO_DIR, "packages", "tests", "server")
DOCPERMS_TS = os.path.join(SERVER_DIR, "docPerms.ts")
DOCPERMS_TEST_TS = os.path.join(SERVER_DIR, "docPerms.test.ts")

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
    usually a no-op. If node_modules is absent we attempt a pnpm install;
    failures are surfaced by the individual vitest runs, not swallowed.
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
    def test_docperms_module_exists(self):
        """L1: docPerms.ts deliverable exists and is non-trivial source."""
        assert os.path.isfile(DOCPERMS_TS), f"missing {DOCPERMS_TS}"
        src = _read(DOCPERMS_TS)
        assert len(src.strip()) > 200, "docPerms.ts is suspiciously small"

    def test_docperms_test_exists(self):
        """L1: docPerms.test.ts deliverable exists and is non-trivial."""
        assert os.path.isfile(DOCPERMS_TEST_TS), f"missing {DOCPERMS_TEST_TS}"
        src = _read(DOCPERMS_TEST_TS)
        assert len(src.strip()) > 200, "docPerms.test.ts is suspiciously small"

    def test_module_uses_metadata_typed_trpc(self):
        """L1: implementation is built on @trpc/server with a *metadata-typed*
        tRPC instance (initTRPC.meta<...>()) and exports a public surface so
        the test file can import a caller factory."""
        src = _read(DOCPERMS_TS)
        assert "@trpc/server" in src, "docPerms.ts must use @trpc/server"
        assert "initTRPC" in src, "docPerms.ts must initialize tRPC via initTRPC"
        # The metadata type must be wired into the instance: initTRPC.meta<...>.
        assert re.search(r"initTRPC\s*\.\s*meta\s*<", src), (
            "docPerms.ts must wire the metadata type via initTRPC.meta<...>()"
        )
        assert "export" in src, "docPerms.ts must export a public surface"

    def test_module_declares_permission_metadata_on_procedures(self):
        """L1: procedures declare their required permission through `.meta(...)`
        rather than via inline per-procedure permission checks, and the three
        permission strings from the task appear in the module."""
        src = _read(DOCPERMS_TS)
        assert ".meta(" in src, (
            "procedures must tag their required permission via .meta(...)"
        )
        for perm in ("doc:read", "doc:write", "doc:delete"):
            assert perm in src, f"module must reference the permission '{perm}'"

    def test_test_file_imports_only_public_surface(self):
        """L1: the test file imports from the docPerms module rather than
        re-implementing the router/enforcement inline (no parallel initTRPC)."""
        src = _read(DOCPERMS_TEST_TS)
        assert (
            "./docPerms" in src or "docPerms'" in src or 'docPerms"' in src
        ), "docPerms.test.ts must import from ./docPerms"
        assert "initTRPC" not in src, (
            "test file must import the caller factory, not re-init tRPC"
        )

    # ------------------------------------------------------------------ #
    # L2 -- the agent's acceptance suite passes
    # ------------------------------------------------------------------ #
    def test_acceptance_suite_passes(self):
        """L2: the exact Acceptance-Criteria command passes with all green.

        `pnpm vitest run packages/tests/server/docPerms.test.ts`
        """
        rel = os.path.relpath(DOCPERMS_TEST_TS, REPO_DIR)
        res = _run_vitest(rel)
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        assert res.returncode == 0, (
            "docPerms.test.ts must pass.\n"
            f"stdout tail:\n{(res.stdout or '')[-3000:]}\n"
            f"stderr tail:\n{(res.stderr or '')[-2000:]}"
        )
        assert "no test" not in combined.lower(), (
            "vitest reported no tests were collected"
        )

    def test_acceptance_suite_has_enough_cases(self):
        """L2: the acceptance suite actually contains >= 12 passing cases as the
        task requires, proven by parsing the vitest summary."""
        rel = os.path.relpath(DOCPERMS_TEST_TS, REPO_DIR)
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
        """L2: the acceptance test asserts on tRPC error *codes* for every
        required failure category, not on message substrings."""
        src = _read(DOCPERMS_TEST_TS)
        for code in ("UNAUTHORIZED", "FORBIDDEN", "NOT_FOUND", "BAD_REQUEST"):
            assert code in src, (
                f"acceptance suite must assert the {code} error code"
            )

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: the no-permission procedure is open
    # ------------------------------------------------------------------ #
    def test_independent_ping_open_to_anonymous(self):
        """L2 (independent): `ping` declares no required permission, so an
        anonymous caller must succeed and get { ok: true }. This proves the
        enforcement allows a procedure that declares no permission rather than
        blocking everything that is unauthenticated."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asAnon } from './__indep_helpers';

            test('anonymous -> ping succeeds with { ok: true }', async () => {
              const caller = makeCaller(asAnon(), makeStore());
              const res = await caller.docs.ping();
              expect(res).toEqual({ ok: true });
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_ping", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: anonymous on a gated procedure -> UNAUTHORIZED
    # ------------------------------------------------------------------ #
    def test_independent_anonymous_gated_is_unauthorized(self):
        """L2 (independent): an anonymous caller hitting any permission-gated
        procedure is rejected with UNAUTHORIZED (not FORBIDDEN, not NOT_FOUND).
        Rejection happens before any document lookup, so it is reachable on an
        unseeded store."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asAnon } from './__indep_helpers';

            const gated: Array<[string, (c: any) => Promise<unknown>]> = [
              ['get', (c) => c.docs.get({ id: 'd1' })],
              ['list', (c) => c.docs.list()],
              ['upsert', (c) => c.docs.upsert({ id: 'd1', title: 'T', body: 'B' })],
              ['remove', (c) => c.docs.remove({ id: 'd1' })],
            ];

            for (const [name, fn] of gated) {
              test('anonymous -> ' + name + ' is UNAUTHORIZED', async () => {
                const caller = makeCaller(asAnon(), makeStore());
                let code: string | undefined;
                try {
                  await fn(caller);
                  throw new Error('expected ' + name + ' to throw for anon');
                } catch (err: any) {
                  code = err?.code ?? err?.cause?.code;
                }
                expect(code).toBe('UNAUTHORIZED');
              });
            }
            """
        ).lstrip()
        self._run_independent_driver("indep_anon", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: read-grant unlocks reads, forbids writes
    # (the UNAUTHORIZED-vs-FORBIDDEN discriminator)
    # ------------------------------------------------------------------ #
    def test_independent_read_grant_matrix(self):
        """L2 (independent): a principal granted ONLY ["doc:read"] can call the
        read-tagged procedures (get/list) but is FORBIDDEN (authenticated,
        under-privileged -- NOT unauthorized) on the write/delete-tagged ones.

        This is the core discriminator: an implementation that does not read the
        declared metadata, or that collapses anonymous and under-privileged into
        a single rejection code, fails here."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asPrincipal } from './__indep_helpers';

            async function codeOf(p: Promise<unknown>): Promise<string | undefined> {
              try { await p; return undefined; }
              catch (err: any) { return err?.code ?? err?.cause?.code; }
            }

            test('read grant: list succeeds and returns an array', async () => {
              const caller = makeCaller(asPrincipal(['doc:read']), makeStore());
              const out = await caller.docs.list();
              expect(Array.isArray(out)).toBe(true);
            });

            test('read grant: get on unknown id is NOT_FOUND (passes enforcement)', async () => {
              // The read permission is satisfied, so failure must come from the
              // missing document -- NOT_FOUND -- proving enforcement let it through.
              const caller = makeCaller(asPrincipal(['doc:read']), makeStore());
              const code = await codeOf(caller.docs.get({ id: 'does-not-exist' }));
              expect(code).toBe('NOT_FOUND');
            });

            test('read grant: upsert is FORBIDDEN (authenticated, lacks doc:write)', async () => {
              const caller = makeCaller(asPrincipal(['doc:read']), makeStore());
              const code = await codeOf(
                caller.docs.upsert({ id: 'd1', title: 'T', body: 'B' }),
              );
              expect(code).toBe('FORBIDDEN');
            });

            test('read grant: remove is FORBIDDEN (authenticated, lacks doc:delete)', async () => {
              const caller = makeCaller(asPrincipal(['doc:read']), makeStore());
              const code = await codeOf(caller.docs.remove({ id: 'd1' }));
              expect(code).toBe('FORBIDDEN');
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_read_grant", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: write becomes observable through a read
    # ------------------------------------------------------------------ #
    def test_independent_write_then_read_observable(self):
        """L2 (independent): a principal granted ["doc:read","doc:write"] can
        upsert a document, and that stored document is observable through a
        subsequent get against the SAME store -- proving real storage, not a
        hardcoded return. remove (doc:delete) is still FORBIDDEN for this set."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asPrincipal } from './__indep_helpers';

            async function codeOf(p: Promise<unknown>): Promise<string | undefined> {
              try { await p; return undefined; }
              catch (err: any) { return err?.code ?? err?.cause?.code; }
            }

            test('write grant: upsert is stored and readable via get', async () => {
              const store = makeStore();
              const caller = makeCaller(asPrincipal(['doc:read', 'doc:write']), store);

              const created = await caller.docs.upsert({
                id: 'doc-42',
                title: 'Hello',
                body: 'World',
              });
              expect(created).toMatchObject({ id: 'doc-42', title: 'Hello', body: 'World' });

              // Observable through a read on the same store.
              const fetched = await caller.docs.get({ id: 'doc-42' });
              expect(fetched).toMatchObject({ id: 'doc-42', title: 'Hello', body: 'World' });

              // Replacing the same id updates the stored value (upsert semantics).
              await caller.docs.upsert({ id: 'doc-42', title: 'Hi', body: 'Again' });
              const updated = await caller.docs.get({ id: 'doc-42' });
              expect(updated).toMatchObject({ id: 'doc-42', title: 'Hi', body: 'Again' });
            });

            test('write grant still cannot remove (FORBIDDEN, lacks doc:delete)', async () => {
              const store = makeStore();
              const caller = makeCaller(asPrincipal(['doc:read', 'doc:write']), store);
              await caller.docs.upsert({ id: 'doc-9', title: 'T', body: 'B' });
              const code = await codeOf(caller.docs.remove({ id: 'doc-9' }));
              expect(code).toBe('FORBIDDEN');
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_write_read", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: delete grant + NOT_FOUND on second delete
    # ------------------------------------------------------------------ #
    def test_independent_delete_then_notfound(self):
        """L2 (independent): a principal granted ["doc:delete","doc:read"] (plus
        doc:write to seed) can remove a stored document -> { removed: true }, and
        a SECOND remove of the same id returns NOT_FOUND -- proving the delete
        actually mutated the store rather than returning a canned success."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asPrincipal } from './__indep_helpers';

            async function codeOf(p: Promise<unknown>): Promise<string | undefined> {
              try { await p; return undefined; }
              catch (err: any) { return err?.code ?? err?.cause?.code; }
            }

            test('delete grant: remove succeeds then second remove is NOT_FOUND', async () => {
              const store = makeStore();
              const writer = makeCaller(asPrincipal(['doc:write', 'doc:read']), store);
              await writer.docs.upsert({ id: 'del-1', title: 'T', body: 'B' });

              const deleter = makeCaller(
                asPrincipal(['doc:delete', 'doc:read']),
                store,
              );
              const removed = await deleter.docs.remove({ id: 'del-1' });
              expect(removed).toEqual({ removed: true });

              // Document is really gone: a read now fails with NOT_FOUND.
              const getCode = await codeOf(deleter.docs.get({ id: 'del-1' }));
              expect(getCode).toBe('NOT_FOUND');

              // A second remove of the same id is NOT_FOUND.
              const code = await codeOf(deleter.docs.remove({ id: 'del-1' }));
              expect(code).toBe('NOT_FOUND');
            });

            test('remove of a never-existing id is NOT_FOUND', async () => {
              const caller = makeCaller(asPrincipal(['doc:delete']), makeStore());
              const code = await codeOf(caller.docs.remove({ id: 'ghost' }));
              expect(code).toBe('NOT_FOUND');
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_delete", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: validation precedes business logic
    # ------------------------------------------------------------------ #
    def test_independent_validation_before_logic(self):
        """L2 (independent): malformed input is rejected as BAD_REQUEST. We use a
        principal that HOLDS the relevant permission so the rejection cannot be
        the auth gate -- it must be the validator running first. A well-formed
        input with the same permission must NOT be BAD_REQUEST, ruling out a
        "reject everything" stub."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, asPrincipal } from './__indep_helpers';

            async function codeOf(p: Promise<unknown>): Promise<string | undefined> {
              try { await p; return undefined; }
              catch (err: any) { return err?.code ?? err?.cause?.code; }
            }

            test('upsert with empty id -> BAD_REQUEST (validation, not auth)', async () => {
              const caller = makeCaller(asPrincipal(['doc:write', 'doc:read']), makeStore());
              const code = await codeOf(
                caller.docs.upsert({ id: '', title: 'T', body: 'B' }),
              );
              expect(code).toBe('BAD_REQUEST');
            });

            test('upsert with empty title -> BAD_REQUEST', async () => {
              const caller = makeCaller(asPrincipal(['doc:write', 'doc:read']), makeStore());
              const code = await codeOf(
                caller.docs.upsert({ id: 'd1', title: '', body: 'B' }),
              );
              expect(code).toBe('BAD_REQUEST');
            });

            test('get with empty id -> BAD_REQUEST', async () => {
              const caller = makeCaller(asPrincipal(['doc:read']), makeStore());
              const code = await codeOf(caller.docs.get({ id: '' }));
              expect(code).toBe('BAD_REQUEST');
            });

            test('well-formed upsert clears validation (never BAD_REQUEST)', async () => {
              const caller = makeCaller(asPrincipal(['doc:write', 'doc:read']), makeStore());
              let code: string | undefined;
              try {
                await caller.docs.upsert({ id: 'okid', title: 'T', body: 'B' });
                code = 'OK';
              } catch (err: any) {
                code = err?.code ?? err?.cause?.code;
              }
              expect(code).not.toBe('BAD_REQUEST');
              expect(code).toBe('OK');
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_validation", driver)

    # ------------------------------------------------------------------ #
    # helper: introspection-based bridge + driver runner
    # ------------------------------------------------------------------ #
    _HELPERS_TS = textwrap.dedent(
        r"""
        /* Independent test bridge for the docPerms permission router. Locates the
           agent's public caller factory and store factory from docPerms.ts by
           introspection, because the task does not fix their export names. The
           acting principal is modelled as { permissions: string[] } for an
           authenticated caller and `undefined` for an anonymous one -- matching
           the task's "granted permission strings (possibly empty, or absent for
           anonymous callers)". */
        import * as M from './docPerms';

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
            'Could not locate a caller factory exported from docPerms.ts',
          );
        }

        /** Build a fresh, isolated document store using the module's store
            factory. Prefer a clearly named store/db/docs factory; otherwise fall
            back to a zero-arg factory whose result is a non-caller object. */
        export function makeStore(): any {
          const fns = exportedFns();
          const isCaller = callerFactory();
          const named =
            fns.find(
              ([k]) =>
                /(store|db|data|docs|document)/i.test(k) &&
                /(create|make|new|factory|init|empty)/i.test(k),
            ) ||
            fns.find(
              ([k, v]) => v !== isCaller && /store|db|data|document/i.test(k),
            ) ||
            null;
          if (named) {
            try {
              const out = named[1]();
              if (out && typeof out === 'object') return out;
            } catch {
              /* fall through to heuristic */
            }
          }
          for (const [, fn] of fns) {
            if (fn === isCaller) continue;
            try {
              const out = fn();
              if (
                out &&
                typeof out === 'object' &&
                typeof out.then !== 'function' &&
                !('docs' in out)
              ) {
                return out;
              }
            } catch {
              /* ignore */
            }
          }
          throw new Error(
            'Could not locate a store/db factory exported from docPerms.ts',
          );
        }

        /** Anonymous principal: absent acting principal. */
        export function asAnon(): any {
          return undefined;
        }

        /** Authenticated principal carrying a set of granted permission strings. */
        export function asPrincipal(permissions: string[]): any {
          return { permissions };
        }

        /** Invoke the caller factory tolerating common call shapes:
              factory(principal, store) or factory({ principal, store }) etc. */
        export function makeCaller(principal: any, store: any): any {
          const factory = callerFactory();
          const attempts: Array<() => any> = [
            () => factory(principal, store),
            () => factory({ principal, store }),
            () => factory({ user: principal, store }),
            () => factory({ principal, db: store }),
            () => factory({ principal, docs: store }),
            () => factory({ ctx: { principal, store } }),
            () => factory({ ctx: { user: principal, store } }),
            () => factory(store, principal),
          ];
          let lastErr: unknown;
          for (const attempt of attempts) {
            try {
              const caller = attempt();
              if (caller && typeof caller === 'object' && 'docs' in caller) {
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
            'Could not invoke the caller factory with (principal, store) in any '
              + 'known shape: ' + String(lastErr),
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
