"""Tests for the `trpc-patterns` skill task -- variant ext6.

Task: Build a Calendar Router with a rich-type data transformer.

The agent must create two files inside the tRPC monorepo:
  * packages/tests/server/calendar.ts       -- an in-memory event store, a
        transformer-configured tRPC instance + router, an exported router (and
        its type), a store factory, and a helper that builds a real
        server+client resource over the router.
  * packages/tests/server/calendar.test.ts  -- a deterministic vitest suite that
        consumes only calendar.ts's public surface and drives procedures through
        the client so values cross the serialization boundary.

Domain contract (re-derived from tasks/ext6/trpc-patterns.md):
  * The tRPC instance is created with a data transformer (e.g. superjson) applied
    consistently on BOTH server and client, so `Date`, `Map`, and `Set` survive a
    round trip with identity + type intact.
  * Events: { id: string; title: string; startsAt: Date; attendees: Set<string> }.
  * Procedures:
      add({ title, startsAt, attendees:string[] })  -> stored event w/ Date + Set
      get({ id })                                    -> event, or NOT_FOUND
      between({ from:Date, to:Date })                -> events in inclusive window;
                                                        from > to -> validation fail
      summary()                                      -> Map<id, attendeeCount>
  * Input validation: empty title, non-Date date fields, non-string attendees ->
    BAD_REQUEST; get on unknown id -> NOT_FOUND (distinct code).

Verification strategy:

L1  -- the deliverable files exist, are non-trivial real source, build on
       @trpc/server (initTRPC) + a transformer, export a public surface, and the
       test file imports only that surface (does not re-init tRPC itself).

L2  -- DYNAMIC EXECUTION via the repo's native toolchain (`pnpm vitest run`).
       * The agent's own acceptance suite must pass AND must genuinely assert on
         `instanceof` (Date/Set/Map) and on tRPC error *codes*.
       * An INDEPENDENT vitest driver (written by THIS test into the repo) imports
         the agent's exported resource helper from calendar.ts and exercises the
         real client/server serialization boundary directly -- so a naive impl
         that drops the transformer (dates arrive as strings / sets as arrays),
         returns a plain object instead of a Map, or ignores the window bounds
         cannot pass.

The independent driver discovers the agent's resource helper by introspection
(its export name is not fixed by the task): it calls candidate factories and
keeps the one that yields an object exposing a `client` with the four calendar
procedures. It then drives Date/Set/Map round-trips, the inclusive `between`
boundaries, the `from > to` rejection, NOT_FOUND vs BAD_REQUEST, and isolation
between two independent resources -- all reachable without knowing the private
store shape.
"""

import os
import re
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/trpc"
SERVER_DIR = os.path.join(REPO_DIR, "packages", "tests", "server")
CALENDAR_TS = os.path.join(SERVER_DIR, "calendar.ts")
CALENDAR_TEST_TS = os.path.join(SERVER_DIR, "calendar.test.ts")

# Native vitest command. We always run a single file, scoped tightly. A real
# server+client resource spins up an http server per case, so allow headroom.
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
    def test_calendar_module_exists(self):
        """L1: calendar.ts deliverable exists and is non-trivial source."""
        assert os.path.isfile(CALENDAR_TS), f"missing {CALENDAR_TS}"
        src = _read(CALENDAR_TS)
        assert len(src.strip()) > 200, "calendar.ts is suspiciously small"

    def test_calendar_test_exists(self):
        """L1: calendar.test.ts deliverable exists and is non-trivial."""
        assert os.path.isfile(CALENDAR_TEST_TS), f"missing {CALENDAR_TEST_TS}"
        src = _read(CALENDAR_TEST_TS)
        assert len(src.strip()) > 200, "calendar.test.ts is suspiciously small"

    def test_module_uses_trpc_and_transformer(self):
        """L1: calendar.ts builds on @trpc/server (initTRPC), configures a data
        transformer, references the rich types it must round-trip, and exports a
        public surface (router + resource helper + store factory)."""
        src = _read(CALENDAR_TS)
        assert "@trpc/server" in src, "calendar.ts must use @trpc/server"
        assert "initTRPC" in src, "calendar.ts must initialize tRPC via initTRPC"
        # A data transformer must be configured (the whole point of the task).
        assert "transformer" in src, (
            "calendar.ts must configure a data transformer on the tRPC instance"
        )
        # The module must export a public surface for the test to consume.
        assert "export" in src, "calendar.ts must export a public surface"
        assert "router" in src.lower(), "calendar.ts must export a router"
        # The rich types the task is about should appear in the module.
        for token in ("Set", "Map", "Date"):
            assert token in src, f"calendar.ts must work with {token} values"

    def test_module_builds_a_client_resource(self):
        """L1: calendar.ts wires a real server+client resource (so values cross
        the serialization boundary) rather than only a local caller. We accept
        either the repo's resource helper or a hand-rolled createTRPCClient."""
        src = _read(CALENDAR_TS)
        wires_resource = (
            "testServerAndClientResource" in src
            or "routerToServerAndClientNew" in src
            or "createTRPCClient" in src
            or "@trpc/client" in src
        )
        assert wires_resource, (
            "calendar.ts must build a server+client resource over the router so "
            "Date/Set/Map cross the real serialization boundary"
        )

    def test_test_file_imports_only_public_surface(self):
        """L1: calendar.test.ts imports from the calendar module rather than
        re-implementing the router/transformer inline."""
        src = _read(CALENDAR_TEST_TS)
        assert "./calendar" in src or "calendar'" in src or 'calendar"' in src, (
            "calendar.test.ts must import from ./calendar"
        )
        # It must NOT itself stand up a parallel router with initTRPC.
        assert "initTRPC" not in src, (
            "test file must consume the exported router/resource helper, not "
            "re-init tRPC"
        )

    # ------------------------------------------------------------------ #
    # L2 -- the agent's acceptance suite passes
    # ------------------------------------------------------------------ #
    def test_acceptance_suite_passes(self):
        """L2: the exact Acceptance-Criteria command passes with all green.

        `pnpm vitest run packages/tests/server/calendar.test.ts`
        """
        rel = os.path.relpath(CALENDAR_TEST_TS, REPO_DIR)
        res = _run_vitest(rel)
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        assert res.returncode == 0, (
            "calendar.test.ts must pass.\n"
            f"stdout tail:\n{(res.stdout or '')[-3000:]}\n"
            f"stderr tail:\n{(res.stderr or '')[-2000:]}"
        )
        assert "no test" not in combined.lower(), (
            "vitest reported no tests were collected"
        )

    def test_acceptance_suite_has_enough_cases(self):
        """L2: the acceptance suite actually contains >= 12 cases as required,
        proven by running it and reading vitest's passed-count."""
        rel = os.path.relpath(CALENDAR_TEST_TS, REPO_DIR)
        res = _run_vitest(rel)
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        passed = 0
        m = re.search(r"Tests\s+(\d+)\s+passed", combined)
        if m:
            passed = int(m.group(1))
        else:
            passed = combined.count("✓")  # check marks
        assert passed >= 12, (
            f"acceptance suite must have >= 12 passing cases, saw {passed}.\n"
            f"output tail:\n{combined[-2500:]}"
        )

    def test_acceptance_suite_asserts_rich_type_identity(self):
        """L2: the acceptance suite asserts that received values are *actual*
        Date/Set/Map instances (via instanceof), not merely structurally similar,
        and asserts on tRPC error codes for the failure cases. This guards the
        core anti-naive requirement at the source level (behavior is also checked
        independently below)."""
        src = _read(CALENDAR_TEST_TS)
        for inst in ("instanceof Date", "instanceof Set", "instanceof Map"):
            assert inst in src, (
                f"acceptance suite must assert `{inst}` on round-tripped values"
            )
        # Error codes must be asserted, not message substrings.
        assert "NOT_FOUND" in src, "acceptance suite must assert NOT_FOUND code"
        assert "BAD_REQUEST" in src, (
            "acceptance suite must assert validation -> BAD_REQUEST code"
        )

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: Date + Set round-trip identity (add/get)
    # ------------------------------------------------------------------ #
    def test_independent_date_and_set_roundtrip(self):
        """L2 (independent): driving `add` then `get` through the agent's client
        resource, the returned `startsAt` is a real Date equal to the input
        instant, and `attendees` is a real Set whose membership equals the input
        list deduplicated. A naive impl that drops the transformer yields a string
        date / array attendees and fails the `instanceof` assertions."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeResource, codeOf } from './__indep_helpers';

            test('add+get: Date stays Date, Set stays Set (deduped)', async () => {
              await using r = await makeResource();
              const client = r.client;
              const startsAt = new Date('2026-03-14T09:30:00.000Z');

              const added: any = await client.add.mutate({
                title: 'Standup',
                startsAt,
                attendees: ['alice', 'bob', 'alice'],
              });

              expect(added.startsAt instanceof Date).toBe(true);
              expect((added.startsAt as Date).getTime()).toBe(startsAt.getTime());
              expect(added.attendees instanceof Set).toBe(true);
              const aSet = added.attendees as Set<string>;
              expect(aSet.has('alice')).toBe(true);
              expect(aSet.has('bob')).toBe(true);
              expect(aSet.size).toBe(2); // deduplicated

              const fetched: any = await client.get.query({ id: added.id });
              expect(fetched.startsAt instanceof Date).toBe(true);
              expect((fetched.startsAt as Date).getTime()).toBe(startsAt.getTime());
              expect(fetched.attendees instanceof Set).toBe(true);
              expect((fetched.attendees as Set<string>).has('bob')).toBe(true);
              expect(fetched.title).toBe('Standup');
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_roundtrip", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: summary() returns a real Map
    # ------------------------------------------------------------------ #
    def test_independent_summary_returns_map(self):
        """L2 (independent): `summary` returns a real `Map` (not a plain object)
        from event id -> attendee count. A naive impl returning a POJO fails the
        `instanceof Map` assertion; one ignoring attendees fails the count."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeResource } from './__indep_helpers';

            test('summary returns a Map of id -> attendee count', async () => {
              await using r = await makeResource();
              const client = r.client;

              const e1: any = await client.add.mutate({
                title: 'A',
                startsAt: new Date('2026-01-01T00:00:00.000Z'),
                attendees: ['x', 'y', 'x'], // 2 unique
              });
              const e2: any = await client.add.mutate({
                title: 'B',
                startsAt: new Date('2026-01-02T00:00:00.000Z'),
                attendees: ['p', 'q', 'r'], // 3 unique
              });

              const summary: any = await client.summary.query();
              expect(summary instanceof Map).toBe(true);
              const m = summary as Map<string, number>;
              expect(m.get(e1.id)).toBe(2);
              expect(m.get(e2.id)).toBe(3);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_summary", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: inclusive `between` window boundaries
    # ------------------------------------------------------------------ #
    def test_independent_between_inclusive_window(self):
        """L2 (independent): `between` filters by real Date comparison and the
        window is inclusive at both ends. We seed three events, then query a
        window whose endpoints coincide exactly with the first and third events,
        and assert exactly the in-window ids are returned (and an out-of-window
        event is excluded). A naive impl that ignores the window returns all
        events and fails; an exclusive one drops the boundary events and fails."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeResource } from './__indep_helpers';

            test('between is inclusive and filters by real Date comparison', async () => {
              await using r = await makeResource();
              const client = r.client;

              const tEarly = new Date('2026-05-01T00:00:00.000Z');
              const tMid = new Date('2026-05-10T00:00:00.000Z');
              const tLate = new Date('2026-05-20T00:00:00.000Z');
              const tOut = new Date('2026-06-01T00:00:00.000Z');

              const early: any = await client.add.mutate({
                title: 'early', startsAt: tEarly, attendees: ['a'],
              });
              const mid: any = await client.add.mutate({
                title: 'mid', startsAt: tMid, attendees: ['b'],
              });
              const late: any = await client.add.mutate({
                title: 'late', startsAt: tLate, attendees: ['c'],
              });
              const out: any = await client.add.mutate({
                title: 'out', startsAt: tOut, attendees: ['d'],
              });

              // Window endpoints coincide exactly with early & late => inclusive
              // must include BOTH boundary events plus mid, and exclude `out`.
              const res: any[] = await client.between.query({
                from: tEarly,
                to: tLate,
              });
              expect(Array.isArray(res)).toBe(true);
              const ids = new Set(res.map((e: any) => e.id));
              expect(ids.has(early.id)).toBe(true);   // inclusive lower bound
              expect(ids.has(mid.id)).toBe(true);
              expect(ids.has(late.id)).toBe(true);    // inclusive upper bound
              expect(ids.has(out.id)).toBe(false);    // outside window
              expect(res.length).toBe(3);

              // Round-tripped dates remain Date instances.
              for (const e of res) {
                expect(e.startsAt instanceof Date).toBe(true);
              }

              // A narrow window strictly between events returns only mid.
              const narrow: any[] = await client.between.query({
                from: new Date('2026-05-05T00:00:00.000Z'),
                to: new Date('2026-05-15T00:00:00.000Z'),
              });
              const narrowIds = new Set(narrow.map((e: any) => e.id));
              expect(narrowIds.has(mid.id)).toBe(true);
              expect(narrowIds.has(early.id)).toBe(false);
              expect(narrowIds.has(late.id)).toBe(false);
              expect(narrow.length).toBe(1);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_between", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: error semantics (NOT_FOUND vs BAD_REQUEST)
    # ------------------------------------------------------------------ #
    def test_independent_error_semantics(self):
        """L2 (independent): unknown id -> NOT_FOUND; malformed inputs and a
        `from > to` window -> a validation/precondition failure with a DISTINCT
        code (BAD_REQUEST), never NOT_FOUND. This proves the error taxonomy is
        real and that `between` does not silently return everything when the
        window is inverted."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeResource, codeOf } from './__indep_helpers';

            test('get unknown id -> NOT_FOUND', async () => {
              await using r = await makeResource();
              const code = await codeOf(
                r.client.get.query({ id: 'does-not-exist' }),
              );
              expect(code).toBe('NOT_FOUND');
            });

            test('empty title on add -> BAD_REQUEST (distinct from NOT_FOUND)', async () => {
              await using r = await makeResource();
              const code = await codeOf(
                r.client.add.mutate({
                  title: '',
                  startsAt: new Date('2026-01-01T00:00:00.000Z'),
                  attendees: ['a'],
                }),
              );
              expect(code).toBe('BAD_REQUEST');
              expect(code).not.toBe('NOT_FOUND');
            });

            test('non-Date startsAt on add -> BAD_REQUEST', async () => {
              await using r = await makeResource();
              const code = await codeOf(
                r.client.add.mutate({
                  title: 'bad date',
                  // @ts-expect-error wrong type on purpose
                  startsAt: 'not-a-date',
                  attendees: ['a'],
                }),
              );
              expect(code).toBe('BAD_REQUEST');
            });

            test('attendees with empty string -> BAD_REQUEST', async () => {
              await using r = await makeResource();
              const code = await codeOf(
                r.client.add.mutate({
                  title: 'bad attendees',
                  startsAt: new Date('2026-01-01T00:00:00.000Z'),
                  attendees: ['ok', ''],
                }),
              );
              expect(code).toBe('BAD_REQUEST');
            });

            test('between with from > to -> validation/precondition failure', async () => {
              await using r = await makeResource();
              const code = await codeOf(
                r.client.between.query({
                  from: new Date('2026-12-31T00:00:00.000Z'),
                  to: new Date('2026-01-01T00:00:00.000Z'),
                }),
              );
              // Must be rejected (not undefined) and must NOT be NOT_FOUND.
              expect(code).toBeDefined();
              expect(code).not.toBe('NOT_FOUND');
              expect(code).toBe('BAD_REQUEST');
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_errors", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: a well-formed add is NOT rejected
    # (proves validation is real, not "reject everything")
    # ------------------------------------------------------------------ #
    def test_independent_valid_add_passes(self):
        """L2 (independent): a fully well-formed `add` succeeds and returns a
        stored event. This rules out a "reject all input" stub that would
        trivially pass the BAD_REQUEST cases above."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeResource } from './__indep_helpers';

            test('well-formed add succeeds with a real Date + Set event', async () => {
              await using r = await makeResource();
              const startsAt = new Date('2026-07-04T12:00:00.000Z');
              const ev: any = await r.client.add.mutate({
                title: 'Picnic',
                startsAt,
                attendees: ['sam'],
              });
              expect(typeof ev.id).toBe('string');
              expect(ev.id.length).toBeGreaterThan(0);
              expect(ev.title).toBe('Picnic');
              expect(ev.startsAt instanceof Date).toBe(true);
              expect((ev.startsAt as Date).getTime()).toBe(startsAt.getTime());
              expect(ev.attendees instanceof Set).toBe(true);
              expect((ev.attendees as Set<string>).has('sam')).toBe(true);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_valid_add", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: isolation between independent resources
    # ------------------------------------------------------------------ #
    def test_independent_resource_isolation(self):
        """L2 (independent): two resources built by the helper own independent
        stores -- an event added through resource A is NOT visible through a
        fresh resource B's `get`/`summary`. This proves there is no leaked global
        mutable singleton across independent runs."""
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeResource, codeOf } from './__indep_helpers';

            test('events do not leak between independent resources', async () => {
              await using rA = await makeResource();
              await using rB = await makeResource();

              const ev: any = await rA.client.add.mutate({
                title: 'A-only',
                startsAt: new Date('2026-02-02T00:00:00.000Z'),
                attendees: ['z'],
              });

              // Visible in A.
              const inA: any = await rA.client.get.query({ id: ev.id });
              expect(inA.title).toBe('A-only');

              // NOT visible in B: get must be NOT_FOUND and summary empty of it.
              const codeB = await codeOf(rB.client.get.query({ id: ev.id }));
              expect(codeB).toBe('NOT_FOUND');

              const summaryB: any = await rB.client.summary.query();
              expect(summaryB instanceof Map).toBe(true);
              expect((summaryB as Map<string, number>).has(ev.id)).toBe(false);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_isolation", driver)

    # ------------------------------------------------------------------ #
    # helper: introspection-based bridge + driver runner
    # ------------------------------------------------------------------ #
    _HELPERS_TS = textwrap.dedent(
        r"""
        /* Independent test bridge. Locates the agent's exported server+client
           resource helper from calendar.ts by introspection, because the task
           does not fix its export name. We accept any exported (possibly async)
           function that, when invoked with no/ a benign option arg, yields an
           object exposing a `client` with the four calendar procedures. */
        import * as M from './calendar';

        type AnyFn = (...args: any[]) => any;
        const PROCS = ['add', 'get', 'between', 'summary'] as const;

        function exportedFns(): Array<[string, AnyFn]> {
          return Object.entries(M as Record<string, unknown>)
            .filter(([, v]) => typeof v === 'function')
            .map(([k, v]) => [k, v as AnyFn]);
        }

        function looksLikeResource(out: any): boolean {
          if (!out || typeof out !== 'object') return false;
          const client = out.client;
          if (!client || typeof client !== 'object') return false;
          // Every required procedure must be reachable on the client.
          return PROCS.every((p) => (client as any)[p] != null);
        }

        async function tryInvoke(fn: AnyFn): Promise<any | undefined> {
          const argShapes: any[][] = [[], [{}], [undefined]];
          for (const args of argShapes) {
            try {
              let out = fn(...args);
              if (out && typeof out.then === 'function') out = await out;
              if (looksLikeResource(out)) return out;
            } catch {
              /* try the next shape */
            }
          }
          return undefined;
        }

        /** Build a fresh server+client resource via the agent's exported helper.
            Returns the resource object (which exposes `.client`). The object may
            implement async-dispose; callers use `await using`. */
        export async function makeResource(): Promise<any> {
          const fns = exportedFns();
          // Prefer a clearly named resource/client helper first.
          const ordered = [
            ...fns.filter(([k]) =>
              /resource|server.*client|client.*server|harness|testServer|setup/i.test(k),
            ),
            ...fns.filter(
              ([k]) =>
                !/resource|server.*client|client.*server|harness|testServer|setup/i.test(k),
            ),
          ];
          for (const [, fn] of ordered) {
            const out = await tryInvoke(fn);
            if (out) return out;
          }
          throw new Error(
            'Could not locate a server+client resource helper exporting a ' +
              'client with { add, get, between, summary } from calendar.ts',
          );
        }

        /** Resolve the tRPC error code from a rejected client promise. On the
            client side a TRPCClientError exposes the code at err.data?.code; we
            also tolerate err.code / err.cause?.code / err.shape?.data?.code. */
        export async function codeOf(
          p: Promise<unknown>,
        ): Promise<string | undefined> {
          try {
            await p;
            return undefined;
          } catch (err: any) {
            return (
              err?.data?.code ??
              err?.shape?.data?.code ??
              err?.code ??
              err?.cause?.code
            );
          }
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
