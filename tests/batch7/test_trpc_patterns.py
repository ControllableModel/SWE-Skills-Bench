"""Tests for the `trpc-patterns` skill task (variant ext7).

Task: Build a Streaming Metrics Feed Procedure in the tRPC monorepo.

The agent must create two files inside the tRPC monorepo:
  * packages/tests/server/metricsFeed.ts      -- an in-memory ordered metrics
                                                 source, the tRPC instance, a
                                                 `record`/`count` pair plus an
                                                 async-generator `stream`
                                                 procedure with a declared
                                                 per-item output shape, a router
                                                 nesting a `metrics` sub-router,
                                                 and an exported caller factory.
  * packages/tests/server/metricsFeed.test.ts -- a deterministic vitest suite
                                                 driving the API through callers,
                                                 collecting the async iterable
                                                 into an array.

Verification strategy:

L1 -- the deliverable files exist and are minimally well-formed (real source,
      importing the repo's `@trpc/server` primitives, building an async-generator
      procedure with a declared per-item output shape via zAsyncIterable, and
      exporting a public surface the test file can import).

L2 -- DYNAMIC EXECUTION via the repo's native toolchain (`pnpm vitest run`):
      * The agent's own acceptance suite must pass and must genuinely contain
        >= 12 cases and assert on the tRPC validation error *code*.
      * An INDEPENDENT vitest driver (written by THIS test into the repo) imports
        the agent's public caller factory from metricsFeed.ts and exercises the
        streaming contract directly -- full-range streaming, windowed
        streaming (fromSeq/limit), the empty-but-valid stream, the single-item
        case, strict seq ordering, out-of-range validation -> BAD_REQUEST, and
        source isolation across separate factory calls. The driver collects the
        async iterable into an array and asserts concrete seq/valueCents values,
        so a naive implementation that returns a single array from a normal
        query, ignores fromSeq/limit, yields out of order, or skips validation
        cannot pass.

The independent driver discovers the agent's caller factory and source factory
by introspection (their export names are not fixed by the task) and feeds the
source through the caller's context, then records samples through the public
`record` procedure -- so it does not depend on the private store shape.
"""

import os
import re
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/trpc"
SERVER_DIR = os.path.join(REPO_DIR, "packages", "tests", "server")
FEED_TS = os.path.join(SERVER_DIR, "metricsFeed.ts")
FEED_TEST_TS = os.path.join(SERVER_DIR, "metricsFeed.test.ts")

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
    def test_feed_module_exists(self):
        """L1: metricsFeed.ts deliverable exists and is non-trivial source."""
        assert os.path.isfile(FEED_TS), f"missing {FEED_TS}"
        src = _read(FEED_TS)
        assert len(src.strip()) > 200, "metricsFeed.ts is suspiciously small"

    def test_feed_test_exists(self):
        """L1: metricsFeed.test.ts deliverable exists and is non-trivial."""
        assert os.path.isfile(FEED_TEST_TS), f"missing {FEED_TEST_TS}"
        src = _read(FEED_TEST_TS)
        assert len(src.strip()) > 200, "metricsFeed.test.ts is suspiciously small"

    def test_module_uses_trpc_server_primitives(self):
        """L1: implementation is built on @trpc/server (initTRPC), exports a
        public surface, and nests a `metrics` sub-router."""
        src = _read(FEED_TS)
        assert "@trpc/server" in src, "metricsFeed.ts must use @trpc/server"
        assert "initTRPC" in src, "metricsFeed.ts must initialize tRPC via initTRPC"
        assert "export" in src, "metricsFeed.ts must export a public surface"
        assert "metrics" in src, "metricsFeed.ts must expose a `metrics` sub-router"

    def test_module_declares_async_generator_stream(self):
        """L1: the streaming procedure is a real async generator with a declared
        per-item output shape (zAsyncIterable), not a plain query returning an
        array. This distinguishes the streaming design the task demands from a
        naive single-array query."""
        src = _read(FEED_TS)
        assert "async function*" in src or "async *" in src, (
            "stream must be implemented as an async generator (`async function*`)"
        )
        assert "zAsyncIterable" in src, (
            "stream must declare a per-item output shape via zAsyncIterable"
        )

    def test_test_file_imports_only_public_surface(self):
        """L1: the test file imports from the metricsFeed module rather than
        re-implementing routers/procedures inline."""
        src = _read(FEED_TEST_TS)
        assert (
            "./metricsFeed" in src
            or "metricsFeed'" in src
            or 'metricsFeed"' in src
        ), "metricsFeed.test.ts must import from ./metricsFeed"
        assert "initTRPC" not in src, (
            "test file must import the caller factory, not re-init tRPC"
        )

    # ------------------------------------------------------------------ #
    # L2 -- the agent's acceptance suite passes
    # ------------------------------------------------------------------ #
    def test_acceptance_suite_passes(self):
        """L2: the exact Acceptance-Criteria command passes with all green.

        `pnpm vitest run packages/tests/server/metricsFeed.test.ts`
        """
        rel = os.path.relpath(FEED_TEST_TS, REPO_DIR)
        res = _run_vitest(rel)
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        assert res.returncode == 0, (
            "metricsFeed.test.ts must pass.\n"
            f"stdout tail:\n{(res.stdout or '')[-3000:]}\n"
            f"stderr tail:\n{(res.stderr or '')[-2000:]}"
        )
        assert "no test" not in combined.lower(), (
            "vitest reported no tests were collected"
        )

    def test_acceptance_suite_has_enough_cases(self):
        """L2: the acceptance suite actually contains >= 12 cases as required,
        proven by running and counting passing cases."""
        rel = os.path.relpath(FEED_TEST_TS, REPO_DIR)
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

    def test_acceptance_suite_asserts_on_validation_code(self):
        """L2: the acceptance suite asserts on the tRPC validation error *code*
        (BAD_REQUEST) for the out-of-range / malformed input cases, not on
        message substrings."""
        src = _read(FEED_TEST_TS)
        assert "BAD_REQUEST" in src, (
            "acceptance suite must assert validation -> BAD_REQUEST code"
        )

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: full-range + windowed + ordering
    # ------------------------------------------------------------------ #
    def test_independent_full_range_window_and_ordering(self):
        """L2 (independent): record several samples through the public `record`
        procedure, then drive the async-generator `stream` directly.

        Asserts concrete values:
          * stream({fromSeq:1, limit:N}) yields all N in strict seq order with
            the recorded valueCents, proving it is not ignoring the data layer;
          * stream({fromSeq:3, limit:2}) yields exactly seq 3 and 4 (windowing),
            so a naive impl that ignores fromSeq/limit fails;
          * count() reflects the number recorded.
        Collects the async iterable into an array before asserting.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeSource, makeCaller, collect } from './__indep_helpers';

            test('full-range streaming yields all samples in seq order', async () => {
              const source = makeSource();
              const caller = makeCaller(source);
              const values = [11, 22, 33, 44];
              for (const valueCents of values) {
                await caller.metrics.record({ valueCents });
              }
              expect(await caller.metrics.count()).toBe(4);

              const got = await collect(
                await caller.metrics.stream({ fromSeq: 1, limit: 4 }),
              );
              expect(got.map((s: any) => s.seq)).toEqual([1, 2, 3, 4]);
              expect(got.map((s: any) => s.valueCents)).toEqual(values);
              // strictly increasing
              for (let i = 1; i < got.length; i++) {
                expect(got[i].seq).toBeGreaterThan(got[i - 1].seq);
              }
            });

            test('windowed streaming respects fromSeq and limit', async () => {
              const source = makeSource();
              const caller = makeCaller(source);
              for (const valueCents of [10, 20, 30, 40]) {
                await caller.metrics.record({ valueCents });
              }
              const got = await collect(
                await caller.metrics.stream({ fromSeq: 3, limit: 2 }),
              );
              expect(got.map((s: any) => s.seq)).toEqual([3, 4]);
              expect(got.map((s: any) => s.valueCents)).toEqual([30, 40]);
            });

            test('limit caps the number of yielded items below available', async () => {
              const source = makeSource();
              const caller = makeCaller(source);
              for (const valueCents of [1, 2, 3, 4, 5]) {
                await caller.metrics.record({ valueCents });
              }
              const got = await collect(
                await caller.metrics.stream({ fromSeq: 1, limit: 2 }),
              );
              expect(got.length).toBe(2);
              expect(got.map((s: any) => s.seq)).toEqual([1, 2]);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_window", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: empty-but-valid + single item
    # ------------------------------------------------------------------ #
    def test_independent_empty_and_single(self):
        """L2 (independent): boundary cases for the streaming contract.

          * stream({fromSeq:99, limit:5}) when only a few samples exist yields
            ZERO items and completes cleanly (no error, no hang);
          * stream({fromSeq:1, limit:1}) yields exactly one item.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeSource, makeCaller, collect } from './__indep_helpers';

            test('out-of-range fromSeq yields an empty, clean stream', async () => {
              const source = makeSource();
              const caller = makeCaller(source);
              for (const valueCents of [5, 6, 7]) {
                await caller.metrics.record({ valueCents });
              }
              const got = await collect(
                await caller.metrics.stream({ fromSeq: 99, limit: 5 }),
              );
              expect(got).toEqual([]);
            });

            test('limit 1 yields exactly one item', async () => {
              const source = makeSource();
              const caller = makeCaller(source);
              for (const valueCents of [100, 200, 300]) {
                await caller.metrics.record({ valueCents });
              }
              const got = await collect(
                await caller.metrics.stream({ fromSeq: 1, limit: 1 }),
              );
              expect(got.length).toBe(1);
              expect(got[0].seq).toBe(1);
              expect(got[0].valueCents).toBe(100);
            });

            test('stream from middle yields remaining when limit exceeds', async () => {
              const source = makeSource();
              const caller = makeCaller(source);
              for (const valueCents of [9, 8, 7, 6]) {
                await caller.metrics.record({ valueCents });
              }
              const got = await collect(
                await caller.metrics.stream({ fromSeq: 3, limit: 10 }),
              );
              expect(got.map((s: any) => s.seq)).toEqual([3, 4]);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_empty_single", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: input validation -> BAD_REQUEST
    # ------------------------------------------------------------------ #
    def test_independent_validation_rejected(self):
        """L2 (independent): malformed/out-of-range input is rejected as a tRPC
        validation error (BAD_REQUEST) before streaming begins.

          * fromSeq: 0      -> BAD_REQUEST (must be >= 1)
          * limit: 0        -> BAD_REQUEST (must be >= 1)
          * non-integer valueCents on record -> BAD_REQUEST
        A naive impl that skips validation cannot produce these codes.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeSource, makeCaller, codeOf } from './__indep_helpers';

            test('fromSeq 0 -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeSource());
              const code = await codeOf(async () => {
                const it = await caller.metrics.stream({ fromSeq: 0, limit: 5 });
                // Force consumption in case validation is lazy on first pull.
                for await (const _ of it) { /* drain */ }
              });
              expect(code).toBe('BAD_REQUEST');
            });

            test('limit 0 -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeSource());
              const code = await codeOf(async () => {
                const it = await caller.metrics.stream({ fromSeq: 1, limit: 0 });
                for await (const _ of it) { /* drain */ }
              });
              expect(code).toBe('BAD_REQUEST');
            });

            test('non-integer valueCents on record -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeSource());
              const code = await codeOf(async () => {
                // @ts-expect-error non-integer on purpose
                await caller.metrics.record({ valueCents: 1.5 });
              });
              expect(code).toBe('BAD_REQUEST');
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_validation", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: valid input is NOT rejected
    # (proves validation is real, not "reject everything")
    # ------------------------------------------------------------------ #
    def test_independent_valid_input_passes_validation(self):
        """L2 (independent): well-formed input clears the validation layer.

        A `record` with an integer valueCents and a `stream` with fromSeq>=1 and
        limit>=1 must succeed (never BAD_REQUEST), ruling out a "reject all
        input" stub that would trivially pass the validation test above.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeSource, makeCaller, codeOf, collect } from './__indep_helpers';

            test('valid record + stream do not fail validation', async () => {
              const caller = makeCaller(makeSource());
              const recCode = await codeOf(async () => {
                await caller.metrics.record({ valueCents: 42 });
              });
              expect(recCode).toBeUndefined();

              const streamCode = await codeOf(async () => {
                const got = await collect(
                  await caller.metrics.stream({ fromSeq: 1, limit: 1 }),
                );
                expect(got.length).toBe(1);
                expect(got[0].valueCents).toBe(42);
              });
              expect(streamCode).toBeUndefined();
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_valid_input", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: source isolation across factory calls
    # ------------------------------------------------------------------ #
    def test_independent_source_isolation(self):
        """L2 (independent): two sources produced by the factory are isolated --
        recording through a caller bound to source A must not be visible to a
        caller bound to a fresh source B. Proves there is no leaked global
        mutable singleton.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeSource, makeCaller, collect } from './__indep_helpers';

            test('records on source A are invisible to a fresh source B', async () => {
              const sourceA = makeSource();
              const sourceB = makeSource();
              const callerA = makeCaller(sourceA);
              const callerB = makeCaller(sourceB);

              for (const valueCents of [7, 8, 9]) {
                await callerA.metrics.record({ valueCents });
              }

              expect(await callerA.metrics.count()).toBe(3);
              expect(await callerB.metrics.count()).toBe(0);

              const fromB = await collect(
                await callerB.metrics.stream({ fromSeq: 1, limit: 10 }),
              );
              expect(fromB).toEqual([]);

              const fromA = await collect(
                await callerA.metrics.stream({ fromSeq: 1, limit: 10 }),
              );
              expect(fromA.map((s: any) => s.valueCents)).toEqual([7, 8, 9]);
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_isolation", driver)

    # ------------------------------------------------------------------ #
    # helper: introspection-based bridge + driver runner
    # ------------------------------------------------------------------ #
    _HELPERS_TS = textwrap.dedent(
        r"""
        /* Independent test bridge. Locates the agent's caller factory and source
           factory exported from metricsFeed.ts by introspection, because the
           task does not fix their export names. */
        import * as M from './metricsFeed';

        type AnyFn = (...args: any[]) => any;

        function exportedFns(): Array<[string, AnyFn]> {
          return Object.entries(M as Record<string, unknown>)
            .filter(([, v]) => typeof v === 'function')
            .map(([k, v]) => [k, v as AnyFn]);
        }

        /** Build a fresh, isolated metrics source using the module's factory. */
        export function makeSource(): any {
          const fns = exportedFns();
          // Prefer a clearly named source/store factory.
          const named =
            fns.find(([k]) => /(source|store|metrics|feed|db|data)/i.test(k) &&
                              /(create|make|new|factory|init)/i.test(k)) ||
            fns.find(([k]) => /(source|store|feed)/i.test(k)) ||
            null;
          if (named) {
            try {
              const out = named[1]();
              if (out && typeof out === 'object' && typeof out.then !== 'function') {
                if (!('metrics' in out)) return out;
              }
            } catch {
              /* fall through */
            }
          }
          // Fallback: a zero-arg factory whose result is a non-caller object.
          for (const [, fn] of fns) {
            try {
              const out = fn();
              if (out && typeof out === 'object' && typeof out.then !== 'function') {
                // Heuristic: a source, not a caller (callers expose `metrics`).
                if (!('metrics' in out)) return out;
              }
            } catch {
              /* ignore */
            }
          }
          throw new Error(
            'Could not locate a source/store factory exported from metricsFeed.ts',
          );
        }

        function callerFactory(): AnyFn {
          const fns = exportedFns();
          const named =
            fns.find(([k]) => /caller/i.test(k)) ||
            fns.find(([k]) => /(create|make).*call/i.test(k));
          if (named) return named[1];
          throw new Error(
            'Could not locate a caller factory exported from metricsFeed.ts',
          );
        }

        /** Invoke the caller factory tolerating both call shapes:
              factory(source)        or  factory({ source }) /
              factory({ store }) / factory({ db }) / factory({ ctx: {...} }). */
        export function makeCaller(source: any): any {
          const factory = callerFactory();
          const attempts: Array<() => any> = [
            () => factory(source),
            () => factory({ source }),
            () => factory({ store: source }),
            () => factory({ db: source }),
            () => factory({ data: source }),
            () => factory({ metrics: source }),
            () => factory({ ctx: { source } }),
            () => factory({ ctx: { store: source } }),
            () => factory({ ctx: { db: source } }),
          ];
          let lastErr: unknown;
          for (const attempt of attempts) {
            try {
              const caller = attempt();
              if (caller && typeof caller === 'object' && 'metrics' in caller) {
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
            'Could not invoke caller factory with (source) in any known shape: ' +
              String(lastErr),
          );
        }

        /** Collect an async iterable returned by the stream procedure into an
            array of its yielded items. */
        export async function collect<T = any>(it: any): Promise<T[]> {
          const out: T[] = [];
          for await (const item of it) {
            out.push(item as T);
          }
          return out;
        }

        /** Run a thunk and return the tRPC error code it throws (or undefined on
            success). Handles both the direct TRPCError and a wrapped cause. */
        export async function codeOf(
          thunk: () => Promise<unknown>,
        ): Promise<string | undefined> {
          try {
            await thunk();
            return undefined;
          } catch (err: any) {
            return err?.code ?? err?.cause?.code;
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
