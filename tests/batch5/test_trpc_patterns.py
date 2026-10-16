"""Tests for the `trpc-patterns` skill task -- VARIANT ext5.

Task: Compose a Workspace API from Feature Routers (tRPC monorepo).

The agent must create two files inside the tRPC monorepo:
  * packages/tests/server/workspace.ts       -- an in-memory store factory, the
                                                 tRPC instance, AT LEAST THREE
                                                 separately defined feature
                                                 routers (projects / members /
                                                 tags) combined under distinct
                                                 namespaces into one root router,
                                                 plus an exported caller factory
                                                 and the AppRouter type.
  * packages/tests/server/workspace.test.ts  -- a deterministic vitest suite
                                                 driving the API through callers,
                                                 importing only the public surface.

This pytest verifies the deliverables two ways:

L1  -- the deliverable files exist and are minimally well-formed (real source,
       built on the repo's `@trpc/server` primitives, exporting a public surface;
       the API is genuinely composed from >= 3 *separately defined* routers
       nested under the `projects.` / `members.` / `tags.` namespaces, not one
       monolithic flat router).

L2  -- DYNAMIC EXECUTION via the repo's native toolchain (`pnpm vitest run`).
       * The agent's own acceptance suite (workspace.test.ts) must pass, must
         contain >= 12 cases, and must assert on tRPC error *codes* (NOT_FOUND /
         CONFLICT / BAD_REQUEST) rather than message substrings.
       * An INDEPENDENT vitest driver (written by THIS test into the repo) imports
         the agent's public caller + store factories from workspace.ts by
         introspection and exercises the contract directly -- namespace addressing
         (projects.* / members.* / tags.*), cross-namespace associations
         (member<->project, tag<->project), not-found / conflict / validation
         error codes, namespace independence (a member assignment must NOT surface
         as a tag attachment), and store isolation between factory calls.

By driving the public caller factory (not the agent's own tests) the independent
driver makes a naive implementation fail: collapsing everything into one flat
router, mixing up associations, ignoring duplicate/missing-reference checks,
skipping validation, or leaking a global singleton store cannot pass.
"""

import os
import re
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/trpc"
SERVER_DIR = os.path.join(REPO_DIR, "packages", "tests", "server")
WORKSPACE_TS = os.path.join(SERVER_DIR, "workspace.ts")
WORKSPACE_TEST_TS = os.path.join(SERVER_DIR, "workspace.test.ts")

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
    usually a no-op. Failure here is surfaced by the individual vitest runs.
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
    def test_workspace_module_exists(self):
        """L1: workspace.ts deliverable exists and is non-trivial source."""
        assert os.path.isfile(WORKSPACE_TS), f"missing {WORKSPACE_TS}"
        src = _read(WORKSPACE_TS)
        assert len(src.strip()) > 200, "workspace.ts is suspiciously small"

    def test_workspace_test_exists(self):
        """L1: workspace.test.ts deliverable exists and is non-trivial."""
        assert os.path.isfile(WORKSPACE_TEST_TS), f"missing {WORKSPACE_TEST_TS}"
        src = _read(WORKSPACE_TEST_TS)
        assert len(src.strip()) > 200, "workspace.test.ts is suspiciously small"

    def test_module_uses_trpc_server_primitives(self):
        """L1: implementation is built on @trpc/server (initTRPC) and exports a
        public surface so the test file can import a caller factory + AppRouter
        type."""
        src = _read(WORKSPACE_TS)
        assert "@trpc/server" in src, "workspace.ts must use @trpc/server"
        assert "initTRPC" in src, "workspace.ts must initialize tRPC via initTRPC"
        assert "export" in src, "workspace.ts must export a public surface"
        assert "router" in src or "Router" in src, "workspace.ts must build a router"

    def test_module_composes_three_named_feature_routers(self):
        """L1: the API is composed from >= 3 *separately defined* feature routers
        nested under the projects./members./tags. namespaces -- not one flat
        monolithic router.

        We require all three namespace keys to appear AND that each feature's
        procedures are nested (so calls are addressed as `projects.*` etc.). A
        single flat router that inlines `create`, `add`, `attachToProject` at the
        top level (no namespace keys) fails this check.
        """
        src = _read(WORKSPACE_TS)
        for ns in ("projects", "members", "tags"):
            assert ns in src, f"workspace.ts must define a `{ns}` namespace/router"
        # The composition must nest sub-routers under namespace keys. Accept
        # either object-literal nesting (`projects:`) or a merge call referencing
        # the names. Require at least the three namespace keys as object props.
        ns_keys = sum(
            1
            for ns in ("projects", "members", "tags")
            if re.search(rf"\b{ns}\s*:", src)
        )
        assert ns_keys >= 3, (
            "workspace.ts must nest projects/members/tags as distinct namespaces "
            "in the root router (saw fewer than 3 `<ns>:` keys)"
        )
        # Each required cross-feature procedure name must appear somewhere.
        for proc in ("assignToProject", "ofProject", "attachToProject"):
            assert proc in src, f"workspace.ts must define a `{proc}` procedure"

    def test_test_file_imports_only_public_surface(self):
        """L1: the test file imports from the workspace module rather than
        re-implementing routers/procedures inline (it must not stand up its own
        tRPC instance)."""
        src = _read(WORKSPACE_TEST_TS)
        assert (
            "./workspace" in src or "workspace'" in src or 'workspace"' in src
        ), "workspace.test.ts must import from ./workspace"
        assert "initTRPC" not in src, (
            "test file must consume the exported caller factory, not re-init tRPC"
        )

    # ------------------------------------------------------------------ #
    # L2 -- the agent's acceptance suite passes
    # ------------------------------------------------------------------ #
    def test_acceptance_suite_passes(self):
        """L2: the exact Acceptance-Criteria command passes with all green.

        `pnpm vitest run packages/tests/server/workspace.test.ts`
        """
        rel = os.path.relpath(WORKSPACE_TEST_TS, REPO_DIR)
        res = _run_vitest(rel)
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        assert res.returncode == 0, (
            "workspace.test.ts must pass.\n"
            f"stdout tail:\n{(res.stdout or '')[-3000:]}\n"
            f"stderr tail:\n{(res.stderr or '')[-2000:]}"
        )
        assert "no test" not in combined.lower(), (
            "vitest reported no tests were collected"
        )

    def test_acceptance_suite_has_enough_cases(self):
        """L2: the acceptance suite actually contains >= 12 cases as required,
        proven by parsing the vitest summary line."""
        rel = os.path.relpath(WORKSPACE_TEST_TS, REPO_DIR)
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
        """L2: the acceptance test asserts on tRPC error *codes* for the required
        failure categories (not-found + conflict + validation), not on message
        substrings."""
        src = _read(WORKSPACE_TEST_TS)
        for code in ("NOT_FOUND", "CONFLICT", "BAD_REQUEST"):
            assert code in src, (
                f"acceptance suite must assert the {code} error code"
            )

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: namespace addressing + happy paths
    # ------------------------------------------------------------------ #
    def test_independent_namespaces_and_happy_paths(self):
        """L2 (independent): drive the agent's caller factory directly to prove
        each feature namespace is reachable and the basic create/list flows work.

        projects.create then projects.list -> the project appears (by id+name).
        members.add returns the member. tags.create returns the tag. This proves
        the three routers are genuinely nested under their namespaces and not a
        stub returning a constant.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller } from './__indep_helpers';

            test('projects.create then projects.list surfaces the project', async () => {
              const caller = makeCaller(makeStore());
              const created = await caller.projects.create({ name: 'Apollo' });
              expect(typeof created.id).toBe('string');
              expect(created.name).toBe('Apollo');

              const list = await caller.projects.list();
              expect(Array.isArray(list)).toBe(true);
              const found = list.find((p: any) => p.id === created.id);
              expect(found).toBeDefined();
              expect(found.name).toBe('Apollo');
            });

            test('members.add returns the new member', async () => {
              const caller = makeCaller(makeStore());
              const m = await caller.members.add({ userId: 'u1', displayName: 'Ada' });
              expect(m.userId).toBe('u1');
              expect(m.displayName).toBe('Ada');
            });

            test('tags.create returns the new tag', async () => {
              const caller = makeCaller(makeStore());
              const t = await caller.tags.create({ label: 'urgent' });
              expect(typeof t.id).toBe('string');
              expect(t.label).toBe('urgent');
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_namespaces", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: cross-namespace association round-trips
    # ------------------------------------------------------------------ #
    def test_independent_cross_namespace_associations(self):
        """L2 (independent): an association created via the members namespace is
        observable via members.ofProject, and a tag attached via tags namespace
        is observable via tags.ofProject -- both round-tripping through the SAME
        shared context store.

        A naive impl that drops the association, or that returns success without
        recording it, fails because the readback list would not contain the id.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller } from './__indep_helpers';

            test('member assignment round-trips through members.ofProject', async () => {
              const caller = makeCaller(makeStore());
              const proj = await caller.projects.create({ name: 'Gemini' });
              await caller.members.add({ userId: 'u9', displayName: 'Grace' });

              const res = await caller.members.assignToProject({
                userId: 'u9',
                projectId: proj.id,
              });
              expect(res).toMatchObject({ assigned: true });

              const members = await caller.members.ofProject({ projectId: proj.id });
              expect(Array.isArray(members)).toBe(true);
              const ids = members.map((m: any) => m.userId);
              expect(ids).toContain('u9');
            });

            test('tag attachment round-trips through tags.ofProject', async () => {
              const caller = makeCaller(makeStore());
              const proj = await caller.projects.create({ name: 'Mercury' });
              const tag = await caller.tags.create({ label: 'p0' });

              const res = await caller.tags.attachToProject({
                tagId: tag.id,
                projectId: proj.id,
              });
              expect(res).toMatchObject({ attached: true });

              const tags = await caller.tags.ofProject({ projectId: proj.id });
              expect(Array.isArray(tags)).toBe(true);
              const ids = tags.map((t: any) => t.id);
              expect(ids).toContain(tag.id);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_assoc", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: namespace independence (no bleed-through)
    # ------------------------------------------------------------------ #
    def test_independent_namespace_independence(self):
        """L2 (independent): an assignment created under the `members` namespace
        must NOT appear under `tags.ofProject`, and a tag attachment must NOT
        appear under `members.ofProject` -- the namespaces stay independent while
        sharing one context store.

        This catches an implementation that conflates the two association tables
        (the classic "mixes up the associations" naive failure mode).
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller } from './__indep_helpers';

            test('member assignment does not leak into tags.ofProject', async () => {
              const caller = makeCaller(makeStore());
              const proj = await caller.projects.create({ name: 'Saturn' });
              await caller.members.add({ userId: 'um', displayName: 'Mae' });
              await caller.members.assignToProject({ userId: 'um', projectId: proj.id });

              const tags = await caller.tags.ofProject({ projectId: proj.id });
              expect(Array.isArray(tags)).toBe(true);
              // No tag was ever created/attached, so the tag list must be empty
              // and must NOT echo the member id.
              const ids = tags.map((t: any) => t.id ?? t.userId);
              expect(ids).not.toContain('um');
              expect(tags.length).toBe(0);
            });

            test('tag attachment does not leak into members.ofProject', async () => {
              const caller = makeCaller(makeStore());
              const proj = await caller.projects.create({ name: 'Neptune' });
              const tag = await caller.tags.create({ label: 'tracked' });
              await caller.tags.attachToProject({ tagId: tag.id, projectId: proj.id });

              const members = await caller.members.ofProject({ projectId: proj.id });
              expect(Array.isArray(members)).toBe(true);
              expect(members.length).toBe(0);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_independence", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: not-found error codes
    # ------------------------------------------------------------------ #
    def test_independent_not_found_codes(self):
        """L2 (independent): referencing a non-existent project / member / tag
        yields the NOT_FOUND tRPC code -- asserted on the code, never a message.

        members.assignToProject with an unknown projectId -> NOT_FOUND.
        members.assignToProject with an unknown userId    -> NOT_FOUND.
        tags.attachToProject with an unknown tagId         -> NOT_FOUND.
        """
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

            test('assign to unknown projectId -> NOT_FOUND', async () => {
              const caller = makeCaller(makeStore());
              await caller.members.add({ userId: 'u1', displayName: 'Ada' });
              const code = await codeOf(
                caller.members.assignToProject({ userId: 'u1', projectId: 'nope' }),
              );
              expect(code).toBe('NOT_FOUND');
            });

            test('assign unknown member -> NOT_FOUND', async () => {
              const caller = makeCaller(makeStore());
              const proj = await caller.projects.create({ name: 'Pluto' });
              const code = await codeOf(
                caller.members.assignToProject({ userId: 'ghost', projectId: proj.id }),
              );
              expect(code).toBe('NOT_FOUND');
            });

            test('attach unknown tag -> NOT_FOUND', async () => {
              const caller = makeCaller(makeStore());
              const proj = await caller.projects.create({ name: 'Ceres' });
              const code = await codeOf(
                caller.tags.attachToProject({ tagId: 'nope', projectId: proj.id }),
              );
              expect(code).toBe('NOT_FOUND');
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_notfound", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: conflict error codes on duplicates
    # ------------------------------------------------------------------ #
    def test_independent_conflict_codes(self):
        """L2 (independent): creating a duplicate association yields the CONFLICT
        tRPC code, distinct from NOT_FOUND.

        A repeated members.assignToProject of the same (member, project) pair ->
        CONFLICT. A repeated tags.attachToProject of the same (tag, project) ->
        CONFLICT. The FIRST call must succeed (proving the conflict is about
        duplication, not a blanket rejection).
        """
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

            test('duplicate member assignment -> CONFLICT (first succeeds)', async () => {
              const caller = makeCaller(makeStore());
              const proj = await caller.projects.create({ name: 'Vesta' });
              await caller.members.add({ userId: 'u1', displayName: 'Ada' });

              const first = await codeOf(
                caller.members.assignToProject({ userId: 'u1', projectId: proj.id }),
              );
              expect(first).toBeUndefined();

              const dup = await codeOf(
                caller.members.assignToProject({ userId: 'u1', projectId: proj.id }),
              );
              expect(dup).toBe('CONFLICT');
            });

            test('duplicate tag attachment -> CONFLICT (first succeeds)', async () => {
              const caller = makeCaller(makeStore());
              const proj = await caller.projects.create({ name: 'Juno' });
              const tag = await caller.tags.create({ label: 'dup' });

              const first = await codeOf(
                caller.tags.attachToProject({ tagId: tag.id, projectId: proj.id }),
              );
              expect(first).toBeUndefined();

              const dup = await codeOf(
                caller.tags.attachToProject({ tagId: tag.id, projectId: proj.id }),
              );
              expect(dup).toBe('CONFLICT');
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_conflict", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: validation rejects empty strings
    # ------------------------------------------------------------------ #
    def test_independent_validation_codes(self):
        """L2 (independent): empty-string input on any procedure is rejected as a
        validation failure (BAD_REQUEST) BEFORE any cross-feature lookup runs.

        We also assert a well-formed create succeeds, ruling out a stub that
        rejects everything to trivially pass the validation cases.
        """
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

            test('empty project name -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeStore());
              const code = await codeOf(caller.projects.create({ name: '' }));
              expect(code).toBe('BAD_REQUEST');
            });

            test('empty member displayName -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeStore());
              const code = await codeOf(
                caller.members.add({ userId: 'u1', displayName: '' }),
              );
              expect(code).toBe('BAD_REQUEST');
            });

            test('empty tag label -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeStore());
              const code = await codeOf(caller.tags.create({ label: '' }));
              expect(code).toBe('BAD_REQUEST');
            });

            test('empty projectId on assignToProject -> BAD_REQUEST (before lookup)', async () => {
              const caller = makeCaller(makeStore());
              await caller.members.add({ userId: 'u1', displayName: 'Ada' });
              const code = await codeOf(
                caller.members.assignToProject({ userId: 'u1', projectId: '' }),
              );
              expect(code).toBe('BAD_REQUEST');
            });

            test('well-formed create does NOT fail validation', async () => {
              const caller = makeCaller(makeStore());
              const code = await codeOf(caller.projects.create({ name: 'Real' }));
              expect(code).toBeUndefined();
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_validation", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: store isolation between factory calls
    # ------------------------------------------------------------------ #
    def test_independent_store_isolation(self):
        """L2 (independent): two stores produced by the factory are isolated --
        a project created through a caller bound to store A must NOT be visible
        through a caller bound to a fresh store B. This proves the store factory
        produces fresh state per call and there is no leaked global singleton.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller } from './__indep_helpers';

            test('project created in store A is absent from a fresh store B', async () => {
              const storeA = makeStore();
              const storeB = makeStore();

              const callerA = makeCaller(storeA);
              const created = await callerA.projects.create({ name: 'IsolatedOne' });

              // Visible through store A.
              const listA = await makeCaller(storeA).projects.list();
              expect(listA.some((p: any) => p.id === created.id)).toBe(true);

              // NOT visible through an independent store B.
              const listB = await makeCaller(storeB).projects.list();
              expect(listB.some((p: any) => p.id === created.id)).toBe(false);
              expect(listB.some((p: any) => p.name === 'IsolatedOne')).toBe(false);
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
           store factory from workspace.ts by introspection, because the task does
           not fix their export names. */
        import * as M from './workspace';

        type AnyFn = (...args: any[]) => any;

        const NAMESPACES = ['projects', 'members', 'tags'];

        function exportedFns(): Array<[string, AnyFn]> {
          return Object.entries(M as Record<string, unknown>)
            .filter(([, v]) => typeof v === 'function')
            .map(([k, v]) => [k, v as AnyFn]);
        }

        function looksLikeCaller(obj: any): boolean {
          if (!obj || typeof obj !== 'object') return false;
          // A composed caller exposes the three feature namespaces as properties.
          return NAMESPACES.every((ns) => ns in obj);
        }

        /** Build a fresh, isolated store using the module's store factory. */
        export function makeStore(): any {
          const fns = exportedFns();
          // Prefer a clearly named store/db/data factory.
          const named =
            fns.find(([k]) => /(store|db|data|state)/i.test(k) &&
                              /(create|make|new|factory|init)/i.test(k)) ||
            fns.find(([k]) => /(store|db|data|state)/i.test(k)) ||
            null;
          if (named) {
            try {
              const out = named[1]();
              if (out && typeof out === 'object' && !looksLikeCaller(out)) return out;
            } catch {
              /* fall through */
            }
          }
          // Fallback: any zero-arg factory whose result is a plain object that is
          // NOT itself a caller.
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
            'Could not locate a store/db factory exported from workspace.ts',
          );
        }

        function callerFactory(): AnyFn {
          const fns = exportedFns();
          const named =
            fns.find(([k]) => /caller/i.test(k)) ||
            fns.find(([k]) => /(create|make).*call/i.test(k));
          if (named) return named[1];
          throw new Error(
            'Could not locate a caller factory exported from workspace.ts',
          );
        }

        /** Invoke the caller factory tolerating several call shapes:
              factory(store) / factory({ store }) / factory({ db }) /
              factory({ data }) / factory({ ctx: { store } }) / factory(). */
        export function makeCaller(store: any): any {
          const factory = callerFactory();
          const attempts: Array<() => any> = [
            () => factory(store),
            () => factory({ store }),
            () => factory({ db: store }),
            () => factory({ data: store }),
            () => factory({ ctx: { store } }),
            () => factory({ ctx: { db: store } }),
            () => factory({ ctx: store }),
            () => factory(),
          ];
          let lastErr: unknown;
          for (const attempt of attempts) {
            try {
              const caller = attempt();
              if (looksLikeCaller(caller)) return caller;
              // Accept any object as a candidate; namespace props may be lazy.
              if (caller && typeof caller === 'object') {
                return caller;
              }
            } catch (e) {
              lastErr = e;
            }
          }
          throw new Error(
            'Could not invoke caller factory with (store) in any known shape: ' +
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
