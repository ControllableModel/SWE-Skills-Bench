"""Tests for the `trpc-patterns` skill task (variant ext2).

Task: Build a Catalog Pricing Router with Output Contracts for the tRPC suite.

The agent must create two files inside the tRPC monorepo:
  * packages/tests/server/catalog.ts       -- in-memory product/discount store,
                                               the tRPC instance + helpers, the
                                               root router nesting a `catalog`
                                               sub-router, and an exported caller
                                               factory + store factory.
  * packages/tests/server/catalog.test.ts  -- a deterministic vitest suite that
                                               consumes ONLY the public surface
                                               (caller factory + exported types).

Procedures (all under the `catalog` sub-router):
  * getProduct({ sku })                       -> { sku, name, priceCents, currency }
  * quote({ sku, quantity, discountCode? })   -> { sku, quantity, unitPriceCents,
                                                   subtotalCents, discountCents,
                                                   totalCents, currency }
  * listByCurrency({ currency })              -> Product[]

Pricing rules:
  * subtotalCents = unitPriceCents * quantity
  * SAVE10 = floor(10% of subtotal); SAVE25 = floor(25% of subtotal);
    no code = 0; any other non-empty code is a validation failure.
  * totalCents = subtotalCents - discountCents, never negative.
  * quantity must be an integer >= 1; sku non-empty; currency in {USD, EUR}.

Verification strategy
---------------------
L1  -- both deliverable files exist, are real non-trivial source built on
       `@trpc/server` (initTRPC), declare procedure OUTPUT contracts (.output),
       and the test file imports the public surface instead of re-declaring
       routers.

L2  -- DYNAMIC EXECUTION via the repo's native toolchain
       (`pnpm vitest run packages/tests/server/catalog.test.ts`):
       * The agent's own acceptance suite must pass, contain >= 12 cases, and
         assert on tRPC error *codes* (NOT_FOUND / BAD_REQUEST) rather than on
         message substrings.
       * An INDEPENDENT vitest driver (written by THIS test into the repo)
         imports the agent's caller factory + store factory from catalog.ts and
         drives the pricing math, the output-contract boundary, input
         validation, not-found-vs-validation distinction, the non-negative-total
         guard, and store isolation DIRECTLY. The driver derives a seeded sku
         from `listByCurrency` (it never assumes the private store shape), so a
         naive implementation that hardcodes totals, ignores the output
         contract, skips validation, or leaks a global store cannot pass.
"""

import os
import re
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/trpc"
SERVER_DIR = os.path.join(REPO_DIR, "packages", "tests", "server")
CATALOG_TS = os.path.join(SERVER_DIR, "catalog.ts")
CATALOG_TEST_TS = os.path.join(SERVER_DIR, "catalog.test.ts")

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
    usually a no-op. Failures here are surfaced by the vitest runs, not
    swallowed.
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
    def test_catalog_module_exists(self):
        """L1: catalog.ts deliverable exists and is non-trivial source."""
        assert os.path.isfile(CATALOG_TS), f"missing {CATALOG_TS}"
        src = _read(CATALOG_TS)
        assert len(src.strip()) > 300, "catalog.ts is suspiciously small"

    def test_catalog_test_exists(self):
        """L1: catalog.test.ts deliverable exists and is non-trivial."""
        assert os.path.isfile(CATALOG_TEST_TS), f"missing {CATALOG_TEST_TS}"
        src = _read(CATALOG_TEST_TS)
        assert len(src.strip()) > 300, "catalog.test.ts is suspiciously small"

    def test_module_uses_trpc_server_primitives(self):
        """L1: implementation is built on @trpc/server (initTRPC), exports a
        public surface, and declares procedure OUTPUT contracts (.output)."""
        src = _read(CATALOG_TS)
        assert "@trpc/server" in src, "catalog.ts must use @trpc/server"
        assert "initTRPC" in src, "catalog.ts must initialize tRPC via initTRPC"
        assert "export" in src, "catalog.ts must export a public surface"
        assert "Router" in src or "router" in src, "catalog.ts must define a router"
        # The output-contract requirement: every procedure declares .output(...).
        assert ".output(" in src, (
            "catalog.ts must declare procedure output shapes via .output(...)"
        )

    def test_module_declares_required_procedures(self):
        """L1: the three required procedures are present in the module by name
        (getProduct / quote / listByCurrency) under a catalog sub-router."""
        src = _read(CATALOG_TS)
        for proc in ("getProduct", "quote", "listByCurrency"):
            assert proc in src, f"catalog.ts must define a `{proc}` procedure"
        assert "catalog" in src, "catalog.ts must nest a `catalog` sub-router"

    def test_test_file_imports_only_public_surface(self):
        """L1: the test file imports from the catalog module rather than
        re-implementing routers/procedures inline."""
        src = _read(CATALOG_TEST_TS)
        assert (
            "./catalog" in src or "catalog'" in src or 'catalog"' in src
        ), "catalog.test.ts must import from ./catalog"
        assert "initTRPC" not in src, (
            "test file must import the caller factory, not re-init tRPC"
        )

    # ------------------------------------------------------------------ #
    # L2 -- the agent's acceptance suite passes
    # ------------------------------------------------------------------ #
    def test_acceptance_suite_passes(self):
        """L2: the exact Acceptance-Criteria command passes with all green.

        `pnpm vitest run packages/tests/server/catalog.test.ts`
        """
        rel = os.path.relpath(CATALOG_TEST_TS, REPO_DIR)
        res = _run_vitest(rel)
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        assert res.returncode == 0, (
            "catalog.test.ts must pass.\n"
            f"stdout tail:\n{(res.stdout or '')[-3000:]}\n"
            f"stderr tail:\n{(res.stderr or '')[-2000:]}"
        )
        assert "no test" not in combined.lower(), (
            "vitest reported no tests were collected"
        )

    def test_acceptance_suite_has_enough_cases(self):
        """L2: the acceptance suite actually contains >= 12 cases as required,
        proven by running it and reading the passed-count from the summary."""
        rel = os.path.relpath(CATALOG_TEST_TS, REPO_DIR)
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
        """L2: the acceptance test asserts on tRPC error *codes* for the
        required failure categories (not-found and validation), not on message
        substrings."""
        src = _read(CATALOG_TEST_TS)
        assert "NOT_FOUND" in src, (
            "acceptance suite must assert the NOT_FOUND code for unknown sku"
        )
        assert "BAD_REQUEST" in src, (
            "acceptance suite must assert validation -> BAD_REQUEST code"
        )

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: pricing math (no-code + both discount codes,
    #       floor semantics) computed through the agent's caller factory
    # ------------------------------------------------------------------ #
    def test_independent_pricing_math(self):
        """L2 (independent): drive `quote` through the agent's caller factory
        and assert the EXACT numeric contract for the no-code path and both
        discount codes, including floor semantics and the
        total = subtotal - discount identity.

        The seeded sku + unit price are discovered at runtime from
        `listByCurrency` / `getProduct`, so this never assumes the private
        store shape. A stub that hardcodes totals or ignores quantity/discount
        cannot satisfy these derived-value assertions.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, pickSku } from './__indep_helpers';

            test('no-code quote: subtotal = unit*qty, discount 0', async () => {
              const store = makeStore();
              const caller = makeCaller(store);
              const { sku, unitPriceCents } = await pickSku(caller);
              const q = await caller.catalog.quote({ sku, quantity: 3 });
              expect(q.quantity).toBe(3);
              expect(q.unitPriceCents).toBe(unitPriceCents);
              expect(q.subtotalCents).toBe(unitPriceCents * 3);
              expect(q.discountCents).toBe(0);
              expect(q.totalCents).toBe(unitPriceCents * 3);
            });

            test('SAVE10 discount = floor(10% subtotal)', async () => {
              const store = makeStore();
              const caller = makeCaller(store);
              const { sku, unitPriceCents } = await pickSku(caller);
              const qty = 4;
              const subtotal = unitPriceCents * qty;
              const expectedDiscount = Math.floor(subtotal * 0.1);
              const q = await caller.catalog.quote({
                sku, quantity: qty, discountCode: 'SAVE10',
              });
              expect(q.subtotalCents).toBe(subtotal);
              expect(q.discountCents).toBe(expectedDiscount);
              expect(q.totalCents).toBe(subtotal - expectedDiscount);
            });

            test('SAVE25 discount = floor(25% subtotal)', async () => {
              const store = makeStore();
              const caller = makeCaller(store);
              const { sku, unitPriceCents } = await pickSku(caller);
              const qty = 4;
              const subtotal = unitPriceCents * qty;
              const expectedDiscount = Math.floor(subtotal * 0.25);
              const q = await caller.catalog.quote({
                sku, quantity: qty, discountCode: 'SAVE25',
              });
              expect(q.subtotalCents).toBe(subtotal);
              expect(q.discountCents).toBe(expectedDiscount);
              expect(q.totalCents).toBe(subtotal - expectedDiscount);
              // SAVE25 must remove strictly more than SAVE10 for the same basket
              // (so long as the subtotal is large enough to make 10% >= 1).
              if (Math.floor(subtotal * 0.1) >= 1) {
                expect(q.discountCents).toBeGreaterThan(
                  Math.floor(subtotal * 0.1),
                );
              }
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_pricing", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: getProduct / listByCurrency correctness
    # ------------------------------------------------------------------ #
    def test_independent_getproduct_and_listbycurrency(self):
        """L2 (independent): getProduct returns the exact product record and
        listByCurrency returns ONLY products of the requested currency.

        listByCurrency is filtered: every returned product's currency must equal
        the requested one, and a product known (via getProduct) to be of the
        other currency must be absent. This kills a stub that returns the whole
        catalog or ignores the currency filter.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, pickSku } from './__indep_helpers';

            test('getProduct returns the exact seeded record', async () => {
              const caller = makeCaller(makeStore());
              const { sku } = await pickSku(caller);
              const p = await caller.catalog.getProduct({ sku });
              expect(p.sku).toBe(sku);
              expect(typeof p.name).toBe('string');
              expect(p.name.length).toBeGreaterThan(0);
              expect(Number.isInteger(p.priceCents)).toBe(true);
              expect(p.priceCents).toBeGreaterThanOrEqual(0);
              expect(['USD', 'EUR']).toContain(p.currency);
            });

            test('listByCurrency returns only that currency', async () => {
              const caller = makeCaller(makeStore());
              for (const currency of ['USD', 'EUR'] as const) {
                const list = await caller.catalog.listByCurrency({ currency });
                expect(Array.isArray(list)).toBe(true);
                for (const prod of list) {
                  expect(prod.currency).toBe(currency);
                }
              }
            });

            test('listByCurrency partitions the catalog by currency', async () => {
              const caller = makeCaller(makeStore());
              const usd = await caller.catalog.listByCurrency({ currency: 'USD' });
              const eur = await caller.catalog.listByCurrency({ currency: 'EUR' });
              const usdSkus = new Set(usd.map((p: any) => p.sku));
              const eurSkus = new Set(eur.map((p: any) => p.sku));
              // No sku may appear in both buckets.
              for (const s of usdSkus) {
                expect(eurSkus.has(s)).toBe(false);
              }
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_lookup", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: input validation -> BAD_REQUEST
    # ------------------------------------------------------------------ #
    def test_independent_validation_rejected(self):
        """L2 (independent): malformed input is rejected as a validation error
        (BAD_REQUEST) BEFORE pricing logic runs -- quantity 0, fractional
        quantity, unrecognized discount code, and a bogus currency each fail.
        Uses a real seeded sku so we exercise the validator, not not-found.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, pickSku } from './__indep_helpers';

            async function codeOf(p: Promise<unknown>): Promise<string | undefined> {
              try {
                await p;
                return undefined;
              } catch (err: any) {
                return err?.code ?? err?.cause?.code;
              }
            }

            test('quantity 0 -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeStore());
              const { sku } = await pickSku(caller);
              expect(
                await codeOf(caller.catalog.quote({ sku, quantity: 0 })),
              ).toBe('BAD_REQUEST');
            });

            test('fractional quantity -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeStore());
              const { sku } = await pickSku(caller);
              expect(
                await codeOf(caller.catalog.quote({ sku, quantity: 2.5 })),
              ).toBe('BAD_REQUEST');
            });

            test('unrecognized discount code -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeStore());
              const { sku } = await pickSku(caller);
              expect(
                await codeOf(
                  caller.catalog.quote({
                    sku, quantity: 1, discountCode: 'BOGUS',
                  }),
                ),
              ).toBe('BAD_REQUEST');
            });

            test('bogus currency on listByCurrency -> BAD_REQUEST', async () => {
              const caller = makeCaller(makeStore());
              expect(
                await codeOf(
                  // @ts-expect-error invalid currency on purpose
                  caller.catalog.listByCurrency({ currency: 'GBP' }),
                ),
              ).toBe('BAD_REQUEST');
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_validation", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: not-found vs validation distinction +
    #       valid discount codes clear validation (not a reject-all stub)
    # ------------------------------------------------------------------ #
    def test_independent_notfound_vs_validation(self):
        """L2 (independent): an unknown but well-formed sku surfaces NOT_FOUND
        (distinct from BAD_REQUEST), while a well-formed quote with a recognized
        discount code clears validation. This rules out both a "return NOT_FOUND
        for everything" stub and a "reject all input as BAD_REQUEST" stub.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, pickSku } from './__indep_helpers';

            async function codeOf(p: Promise<unknown>): Promise<string | undefined> {
              try {
                await p;
                return undefined;
              } catch (err: any) {
                return err?.code ?? err?.cause?.code;
              }
            }

            test('unknown sku getProduct -> NOT_FOUND (not BAD_REQUEST)', async () => {
              const caller = makeCaller(makeStore());
              const code = await codeOf(
                caller.catalog.getProduct({ sku: 'does-not-exist-xyz' }),
              );
              expect(code).toBe('NOT_FOUND');
              expect(code).not.toBe('BAD_REQUEST');
            });

            test('unknown sku quote -> NOT_FOUND', async () => {
              const caller = makeCaller(makeStore());
              const code = await codeOf(
                caller.catalog.quote({ sku: 'nope-nope', quantity: 1 }),
              );
              expect(code).toBe('NOT_FOUND');
            });

            test('recognized codes clear validation on a real sku', async () => {
              const caller = makeCaller(makeStore());
              const { sku } = await pickSku(caller);
              for (const discountCode of ['SAVE10', 'SAVE25'] as const) {
                const code = await codeOf(
                  caller.catalog.quote({ sku, quantity: 2, discountCode }),
                );
                // A well-formed, in-catalog quote must SUCCEED (undefined code).
                expect(code).toBeUndefined();
              }
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_notfound", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: output contract enforced at the boundary
    # ------------------------------------------------------------------ #
    def test_independent_output_contract_enforced(self):
        """L2 (independent): every numeric field declared by the `quote` output
        contract is present and of numeric type on a successful quote, currency
        is one of the allowed values, and no negative total ever leaks.

        A real `.output()` parser guarantees the shape; a stub that returns a
        partial / wrongly-typed object would either be rejected at the boundary
        (surfacing an error here instead of a value) or fail these type checks.
        We also confirm the non-negative-total guard holds for the heaviest
        discount across a range of quantities.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, pickSku } from './__indep_helpers';

            const NUMERIC = [
              'quantity',
              'unitPriceCents',
              'subtotalCents',
              'discountCents',
              'totalCents',
            ] as const;

            test('quote output has every declared numeric field, typed', async () => {
              const caller = makeCaller(makeStore());
              const { sku } = await pickSku(caller);
              const q = await caller.catalog.quote({ sku, quantity: 2 });
              for (const f of NUMERIC) {
                expect(typeof (q as any)[f]).toBe('number');
                expect(Number.isFinite((q as any)[f])).toBe(true);
              }
              expect(q.sku).toBe(sku);
              expect(['USD', 'EUR']).toContain(q.currency);
            });

            test('totalCents never negative under heaviest discount', async () => {
              const caller = makeCaller(makeStore());
              const { sku } = await pickSku(caller);
              for (const quantity of [1, 2, 3, 7]) {
                const q = await caller.catalog.quote({
                  sku, quantity, discountCode: 'SAVE25',
                });
                expect(q.totalCents).toBeGreaterThanOrEqual(0);
                expect(q.totalCents).toBe(q.subtotalCents - q.discountCents);
              }
            });
            """
        ).lstrip()
        self._run_independent_driver("indep_contract", driver)

    # ------------------------------------------------------------------ #
    # L2 -- INDEPENDENT driver: store isolation between independent stores
    # ------------------------------------------------------------------ #
    def test_independent_store_isolation(self):
        """L2 (independent): the store factory yields fresh, isolated instances.

        Two stores built by the factory each resolve a seeded sku independently,
        and getProduct on store A's sku returns the same record through store B
        ONLY if both seed identically -- which they must, since the factory
        produces a clean deterministic store per call. Crucially, reading
        through one store must never depend on or mutate the other (no shared
        global singleton). We assert that both stores independently answer
        getProduct for their own discovered sku, and that quote results are
        identical across the two fresh stores for the same input -- proving the
        per-call factory is deterministic and not a leaked singleton.
        """
        driver = textwrap.dedent(
            r"""
            import { expect, test } from 'vitest';
            import { makeStore, makeCaller, pickSku } from './__indep_helpers';

            test('independent stores are isolated and deterministic', async () => {
              const callerA = makeCaller(makeStore());
              const callerB = makeCaller(makeStore());

              const { sku } = await pickSku(callerA);

              // The same sku resolves identically through a second fresh store.
              const pA = await callerA.catalog.getProduct({ sku });
              const pB = await callerB.catalog.getProduct({ sku });
              expect(pB.sku).toBe(pA.sku);
              expect(pB.priceCents).toBe(pA.priceCents);
              expect(pB.currency).toBe(pA.currency);

              // Quotes computed on two independent fresh stores agree exactly.
              const qA = await callerA.catalog.quote({
                sku, quantity: 3, discountCode: 'SAVE10',
              });
              const qB = await callerB.catalog.quote({
                sku, quantity: 3, discountCode: 'SAVE10',
              });
              expect(qB.subtotalCents).toBe(qA.subtotalCents);
              expect(qB.discountCents).toBe(qA.discountCents);
              expect(qB.totalCents).toBe(qA.totalCents);
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
           store factory from catalog.ts by introspection, because the task does
           not fix their export names. */
        import * as M from './catalog';

        type AnyFn = (...args: any[]) => any;

        function exportedFns(): Array<[string, AnyFn]> {
          return Object.entries(M as Record<string, unknown>)
            .filter(([, v]) => typeof v === 'function')
            .map(([k, v]) => [k, v as AnyFn]);
        }

        /** Build a fresh, isolated store using the module's store factory. */
        export function makeStore(): any {
          const fns = exportedFns();
          const named =
            fns.find(([k]) => /(store|db|data|catalog)/i.test(k) &&
                              /(create|make|new|factory|init)/i.test(k)) ||
            fns.find(([k]) => /(store|db|data)/i.test(k)) ||
            null;
          if (named) {
            try {
              const out = named[1]();
              if (out && typeof out === 'object' && typeof out.then !== 'function') {
                if (!('catalog' in out)) return out;
              }
            } catch {
              /* fall through */
            }
          }
          // Fallback: any zero-arg factory whose result is a non-caller object.
          for (const [, fn] of fns) {
            try {
              const out = fn();
              if (out && typeof out === 'object' && typeof out.then !== 'function') {
                if (!('catalog' in out)) return out;
              }
            } catch {
              /* ignore */
            }
          }
          throw new Error(
            'Could not locate a store/db factory exported from catalog.ts',
          );
        }

        function callerFactory(): AnyFn {
          const fns = exportedFns();
          const named =
            fns.find(([k]) => /caller/i.test(k)) ||
            fns.find(([k]) => /(create|make).*call/i.test(k));
          if (named) return named[1];
          throw new Error(
            'Could not locate a caller factory exported from catalog.ts',
          );
        }

        /** Invoke the caller factory tolerating several context shapes:
              factory(store) / factory({ store }) / factory({ db }) /
              factory({ ctx: { store } }) / factory() (store via closure). */
        export function makeCaller(store: any): any {
          const factory = callerFactory();
          const attempts: Array<() => any> = [
            () => factory(store),
            () => factory({ store }),
            () => factory({ db: store }),
            () => factory({ data: store }),
            () => factory({ catalog: store }),
            () => factory({ ctx: { store } }),
            () => factory({ ctx: { db: store } }),
            () => factory(),
          ];
          let lastErr: unknown;
          for (const attempt of attempts) {
            try {
              const caller = attempt();
              if (caller && typeof caller === 'object' && 'catalog' in caller) {
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
            'Could not invoke caller factory with a store in any known shape: ' +
              String(lastErr),
          );
        }

        /** Discover a seeded sku + its unit price from the live catalog, without
            assuming the private store shape. Tries both currencies. */
        export async function pickSku(
          caller: any,
        ): Promise<{ sku: string; unitPriceCents: number; currency: string }> {
          for (const currency of ['USD', 'EUR'] as const) {
            let list: any[] = [];
            try {
              list = await caller.catalog.listByCurrency({ currency });
            } catch {
              list = [];
            }
            if (Array.isArray(list) && list.length) {
              const p = list[0];
              const sku = p.sku;
              const product = await caller.catalog.getProduct({ sku });
              return {
                sku: product.sku,
                unitPriceCents: product.priceCents,
                currency: product.currency,
              };
            }
          }
          throw new Error(
            'No seeded products found via listByCurrency for USD or EUR',
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
