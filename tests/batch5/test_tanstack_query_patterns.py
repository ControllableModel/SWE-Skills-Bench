"""
Test for 'tanstack-query-patterns' skill (variant ext5) — Infinite-Query Page
Accumulator.

Verifies the agent added a pure `appendPage(input): { next, nextPageParam,
hasNextPage }` utility to `@tanstack/query-core`
(packages/query-core/src/pageAccumulator.ts), re-exported it (and the
`AccumulatedPages` type) from the package entry point
(packages/query-core/src/index.ts), and that the accumulation semantics match
the requirement doc exactly:

  * `next.pages` / `next.pageParams` are `current.*` with `page` / `param`
    appended at the end, kept index-aligned;
  * `nextPageParam` is `getNextPageParam(lastPage=page, allPages=next.pages,
    lastPageParam=param, allPageParams=next.pageParams)`;
  * a `null` or `undefined` result from `getNextPageParam` is normalized to
    `undefined`, with `hasNextPage === false`; any other value yields
    `hasNextPage === true`;
  * appending the first page to an empty accumulator still computes a param;
  * `current` and its arrays are never mutated (referential change is required
    so the caller can detect updates);
  * `getNextPageParam` is invoked exactly once per call.

Strategy: rather than trusting the agent's own test file, this suite writes its
own vitest probe specs into packages/query-core/src/__tests__/ and runs them
with the repo's native vitest — the SAME command family the Acceptance Criteria
specifies (`pnpm --filter @tanstack/query-core exec vitest run ...`). The probes
import `appendPage` from the package index (`..`) and assert concrete return
values, mutation/identity behavior, and call-count, so a stub / hardcoded /
mutating / mislabeled implementation fails.
"""

import os
import subprocess

import pytest


REPO_DIR = "/workspace/query"
CORE_DIR = os.path.join(REPO_DIR, "packages", "query-core")
SRC_DIR = os.path.join(CORE_DIR, "src")
TESTS_SUBDIR = os.path.join(SRC_DIR, "__tests__")

# Probe specs we inject live under src/__tests__ so the package's vitest
# config (test.dir === './src') picks them up. Distinct name to avoid clobber.
PROBE_BASENAME = "zzPageAccumulatorProbe.gen.test.tsx"
PROBE_PATH = os.path.join(TESTS_SUBDIR, PROBE_BASENAME)

INSTALL_TIMEOUT = 1800
VITEST_TIMEOUT = 600


def _pnpm_env():
    env = dict(os.environ)
    # Keep installs/output deterministic and offline-friendly where possible.
    env.setdefault("CI", "")
    env.setdefault("npm_config_yes", "true")
    return env


@pytest.fixture(scope="module", autouse=True)
def _ensure_repo_dependencies():
    """Install workspace deps once so native vitest can run."""
    assert os.path.isdir(REPO_DIR), f"repo not found: {REPO_DIR}"
    assert os.path.isdir(CORE_DIR), f"query-core package not found: {CORE_DIR}"
    node_modules = os.path.join(REPO_DIR, "node_modules")
    if not os.path.isdir(node_modules):
        result = subprocess.run(
            ["pnpm", "install", "--frozen-lockfile", "--prefer-offline"],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT,
            env=_pnpm_env(),
        )
        if result.returncode != 0:
            # Fall back to a non-frozen install (lockfile drift tolerant).
            result = subprocess.run(
                ["pnpm", "install", "--prefer-offline"],
                cwd=REPO_DIR,
                capture_output=True,
                text=True,
                timeout=INSTALL_TIMEOUT,
                env=_pnpm_env(),
            )
        assert result.returncode == 0, (
            "pnpm install failed:\n"
            f"stdout={result.stdout[-3000:]}\nstderr={result.stderr[-3000:]}"
        )
    yield
    # Clean up the injected probe so we don't pollute the repo.
    try:
        if os.path.isfile(PROBE_PATH):
            os.remove(PROBE_PATH)
    except OSError:
        pass


def _run_vitest_on_probe(probe_source):
    """Write `probe_source` into src/__tests__, run native vitest on just that
    file, and return (CompletedProcess, combined_output)."""
    os.makedirs(TESTS_SUBDIR, exist_ok=True)
    with open(PROBE_PATH, "w", encoding="utf-8") as fh:
        fh.write(probe_source)
    try:
        result = subprocess.run(
            [
                "pnpm",
                "--filter",
                "@tanstack/query-core",
                "exec",
                "vitest",
                "run",
                f"src/__tests__/{PROBE_BASENAME}",
            ],
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=VITEST_TIMEOUT,
            env=_pnpm_env(),
        )
    finally:
        try:
            os.remove(PROBE_PATH)
        except OSError:
            pass
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    return result, combined


def _assert_vitest_passed(result, combined):
    assert result.returncode == 0, (
        "native vitest run did not pass:\n"
        f"stdout={result.stdout[-4000:]}\nstderr={result.stderr[-4000:]}"
    )
    # Vitest reports passing files; guard against "No test files found".
    lowered = combined.lower()
    assert "no test files found" not in lowered, (
        "vitest collected no tests:\n" + combined[-3000:]
    )


# Shared probe preamble: import appendPage from the package index.
_IMPORT = (
    "import { describe, expect, it, vi } from 'vitest'\n"
    "import { appendPage } from '..'\n"
)


class TestTanstackQueryPatterns:
    """Verify the appendPage infinite-query page accumulator utility."""

    REPO_DIR = "/workspace/query"

    # ------------------------------------------------------------------
    # L1: deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_pageaccumulator_source_file_exists(self):
        """packages/query-core/src/pageAccumulator.ts must exist and define
        appendPage (non-trivially)."""
        path = os.path.join(SRC_DIR, "pageAccumulator.ts")
        assert os.path.isfile(path), "pageAccumulator.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "appendPage" in content, "appendPage not defined in pageAccumulator.ts"
        assert "getNextPageParam" in content, (
            "pageAccumulator.ts never references getNextPageParam"
        )
        assert len(content.strip()) > 120, "pageAccumulator.ts looks empty/stub"

    def test_index_reexports_appendpage(self):
        """index.ts must re-export appendPage and the AccumulatedPages type."""
        path = os.path.join(SRC_DIR, "index.ts")
        assert os.path.isfile(path), "index.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "appendPage" in content, "index.ts does not re-export appendPage"
        assert "AccumulatedPages" in content, (
            "index.ts does not re-export AccumulatedPages"
        )

    def test_agent_test_suite_exists(self):
        """The required vitest suite file must exist."""
        path = os.path.join(TESTS_SUBDIR, "pageAccumulator.test.tsx")
        assert os.path.isfile(path), "pageAccumulator.test.tsx not found"

    def test_appendpage_importable_from_index(self):
        """appendPage must be a runtime-importable function value from the
        package entry point (not just a type)."""
        probe = (
            _IMPORT
            + "describe('appendPage importable', () => {\n"
            "  it('is a function exported from the index', () => {\n"
            "    expect(typeof appendPage).toBe('function')\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    # ------------------------------------------------------------------
    # L2: dynamic execution via the repo's native vitest toolchain.
    # Each method injects its own focused probe importing appendPage from
    # the package index, so the agent's own test file is not trusted.
    # ------------------------------------------------------------------

    def test_documented_happy_path(self):
        """The exact Expected-Functionality scenario: append page
        {items:['a'],cursor:2} with param 1 to an empty accumulator, where
        getNextPageParam returns lastPage.cursor -> pages/pageParams appended,
        nextPageParam 2, hasNextPage true."""
        probe = (
            _IMPORT
            + "describe('appendPage happy path', () => {\n"
            "  it('matches the documented scenario', () => {\n"
            "    const r = appendPage({\n"
            "      current: { pages: [], pageParams: [] },\n"
            "      page: { items: ['a'], cursor: 2 },\n"
            "      param: 1,\n"
            "      getNextPageParam: (lastPage: any) => lastPage.cursor,\n"
            "    })\n"
            "    expect(r.next.pages).toEqual([{ items: ['a'], cursor: 2 }])\n"
            "    expect(r.next.pageParams).toEqual([1])\n"
            "    expect(r.nextPageParam).toBe(2)\n"
            "    expect(r.hasNextPage).toBe(true)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_appends_and_index_aligns_to_nonempty(self):
        """Appending to a non-empty accumulator preserves prior entries, adds
        the new page/param at the END, keeps them index-aligned, and a stub
        that ignores `current` (returns only the new page) must fail."""
        probe = (
            _IMPORT
            + "describe('appendPage accumulation', () => {\n"
            "  it('appends at the end and stays index-aligned', () => {\n"
            "    const current = {\n"
            "      pages: [{ id: 10 }, { id: 20 }],\n"
            "      pageParams: [0, 1],\n"
            "    }\n"
            "    const r = appendPage({\n"
            "      current,\n"
            "      page: { id: 30 },\n"
            "      param: 2,\n"
            "      getNextPageParam: () => 99,\n"
            "    })\n"
            "    expect(r.next.pages).toEqual([{ id: 10 }, { id: 20 }, { id: 30 }])\n"
            "    expect(r.next.pageParams).toEqual([0, 1, 2])\n"
            "    expect(r.next.pages.length).toBe(3)\n"
            "    expect(r.next.pageParams.length).toBe(3)\n"
            "    // index alignment: last page corresponds to last param\n"
            "    expect(r.next.pages[2]).toEqual({ id: 30 })\n"
            "    expect(r.next.pageParams[2]).toBe(2)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_getnextpageparam_invoked_with_correct_arguments(self):
        """getNextPageParam MUST receive (lastPage=page, allPages=next.pages,
        lastPageParam=param, allPageParams=next.pageParams) — i.e. the FULL
        appended arrays, with the new page/param last. A stub that passes the
        old arrays, or the wrong positions, fails."""
        probe = (
            _IMPORT
            + "describe('appendPage callback args', () => {\n"
            "  it('passes lastPage, full allPages, lastPageParam, full allPageParams', () => {\n"
            "    const spy = vi.fn(() => undefined)\n"
            "    appendPage({\n"
            "      current: { pages: [{ id: 1 }], pageParams: [5] },\n"
            "      page: { id: 2 },\n"
            "      param: 6,\n"
            "      getNextPageParam: spy as any,\n"
            "    })\n"
            "    expect(spy).toHaveBeenCalledTimes(1)\n"
            "    const [lastPage, allPages, lastPageParam, allPageParams] = spy.mock.calls[0]\n"
            "    expect(lastPage).toEqual({ id: 2 })\n"
            "    expect(allPages).toEqual([{ id: 1 }, { id: 2 }])\n"
            "    expect(lastPageParam).toBe(6)\n"
            "    expect(allPageParams).toEqual([5, 6])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_getnextpageparam_invoked_exactly_once(self):
        """getNextPageParam MUST be invoked exactly once per appendPage call."""
        probe = (
            _IMPORT
            + "describe('appendPage call count', () => {\n"
            "  it('invokes getNextPageParam exactly once', () => {\n"
            "    const spy = vi.fn(() => 7)\n"
            "    const r = appendPage({\n"
            "      current: { pages: [], pageParams: [] },\n"
            "      page: { v: 1 },\n"
            "      param: 0,\n"
            "      getNextPageParam: spy as any,\n"
            "    })\n"
            "    expect(spy).toHaveBeenCalledTimes(1)\n"
            "    expect(r.nextPageParam).toBe(7)\n"
            "    expect(r.hasNextPage).toBe(true)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_undefined_param_means_no_next_page(self):
        """When getNextPageParam returns undefined -> hasNextPage false and
        nextPageParam undefined."""
        probe = (
            _IMPORT
            + "describe('appendPage undefined', () => {\n"
            "  it('undefined -> no next page', () => {\n"
            "    const r = appendPage({\n"
            "      current: { pages: [{ a: 1 }], pageParams: [0] },\n"
            "      page: { a: 2 },\n"
            "      param: 1,\n"
            "      getNextPageParam: () => undefined,\n"
            "    })\n"
            "    expect(r.hasNextPage).toBe(false)\n"
            "    expect(r.nextPageParam).toBeUndefined()\n"
            "    // page is still accumulated even when there is no next page\n"
            "    expect(r.next.pages).toEqual([{ a: 1 }, { a: 2 }])\n"
            "    expect(r.next.pageParams).toEqual([0, 1])\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_null_param_normalized_to_undefined(self):
        """When getNextPageParam returns null -> nextPageParam MUST be
        normalized to undefined (strict, not null) and hasNextPage false."""
        probe = (
            _IMPORT
            + "describe('appendPage null normalize', () => {\n"
            "  it('null -> undefined, no next page', () => {\n"
            "    const r = appendPage({\n"
            "      current: { pages: [], pageParams: [] },\n"
            "      page: { a: 1 },\n"
            "      param: 0,\n"
            "      getNextPageParam: () => null,\n"
            "    })\n"
            "    expect(r.hasNextPage).toBe(false)\n"
            "    // strict: must be undefined, NOT null\n"
            "    expect(r.nextPageParam).toBeUndefined()\n"
            "    expect(r.nextPageParam === null).toBe(false)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_falsy_but_defined_params_keep_next_page(self):
        """hasNextPage keys ONLY on null/undefined: defined falsy params such as
        0, '' and false MUST still yield hasNextPage true and preserve the exact
        value (a truthiness-based stub fails here)."""
        probe = (
            _IMPORT
            + "describe('appendPage falsy params', () => {\n"
            "  it('0 / empty-string / false are valid next params', () => {\n"
            "    const mk = (val: any) => appendPage({\n"
            "      current: { pages: [], pageParams: [] },\n"
            "      page: { a: 1 },\n"
            "      param: 1,\n"
            "      getNextPageParam: () => val,\n"
            "    })\n"
            "    const r0 = mk(0)\n"
            "    expect(r0.hasNextPage).toBe(true)\n"
            "    expect(r0.nextPageParam).toBe(0)\n"
            "    const rEmpty = mk('')\n"
            "    expect(rEmpty.hasNextPage).toBe(true)\n"
            "    expect(rEmpty.nextPageParam).toBe('')\n"
            "    const rFalse = mk(false)\n"
            "    expect(rFalse.hasNextPage).toBe(true)\n"
            "    expect(rFalse.nextPageParam).toBe(false)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_purity_no_mutation_and_new_arrays(self):
        """appendPage MUST NOT mutate `current` or its arrays, and MUST return
        NEW array instances (referential change). A stub that pushes into the
        existing arrays fails both the length check on `current` and the
        identity check."""
        probe = (
            _IMPORT
            + "describe('appendPage purity', () => {\n"
            "  it('does not mutate current; returns fresh arrays', () => {\n"
            "    const pages = [{ id: 1 }]\n"
            "    const pageParams = [0]\n"
            "    const current = { pages, pageParams }\n"
            "    const r = appendPage({\n"
            "      current,\n"
            "      page: { id: 2 },\n"
            "      param: 1,\n"
            "      getNextPageParam: () => 5,\n"
            "    })\n"
            "    // original arrays untouched\n"
            "    expect(current.pages).toBe(pages)\n"
            "    expect(current.pageParams).toBe(pageParams)\n"
            "    expect(pages.length).toBe(1)\n"
            "    expect(pageParams.length).toBe(1)\n"
            "    expect(pages).toEqual([{ id: 1 }])\n"
            "    expect(pageParams).toEqual([0])\n"
            "    // returned arrays are NEW instances\n"
            "    expect(r.next.pages).not.toBe(pages)\n"
            "    expect(r.next.pageParams).not.toBe(pageParams)\n"
            "    expect(r.next.pages.length).toBe(2)\n"
            "    expect(r.next.pageParams.length).toBe(2)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_first_page_empty_accumulator_computes_param(self):
        """Appending the FIRST page to an empty accumulator yields a one-page
        result and still computes nextPageParam from that page (getNextPageParam
        receives a single-element allPages)."""
        probe = (
            _IMPORT
            + "describe('appendPage first page', () => {\n"
            "  it('empty accumulator -> one page, param computed', () => {\n"
            "    let seenAllPages: any = null\n"
            "    const r = appendPage({\n"
            "      current: { pages: [], pageParams: [] },\n"
            "      page: { cursor: 42 },\n"
            "      param: null,\n"
            "      getNextPageParam: (lastPage: any, allPages: any) => {\n"
            "        seenAllPages = allPages\n"
            "        return lastPage.cursor\n"
            "      },\n"
            "    })\n"
            "    expect(r.next.pages).toEqual([{ cursor: 42 }])\n"
            "    expect(r.next.pageParams).toEqual([null])\n"
            "    expect(seenAllPages).toEqual([{ cursor: 42 }])\n"
            "    expect(r.nextPageParam).toBe(42)\n"
            "    expect(r.hasNextPage).toBe(true)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)

    def test_repeated_accumulation_drives_a_paginated_walk(self):
        """End-to-end: repeatedly feeding appendPage's output back as `current`
        walks a cursor-based pagination correctly, terminating when
        getNextPageParam returns undefined — exercising index alignment,
        nextPageParam threading, and hasNextPage termination together."""
        probe = (
            _IMPORT
            + "describe('appendPage iterative walk', () => {\n"
            "  it('threads nextPageParam across pages and terminates', () => {\n"
            "    // simulated source: cursor n returns items and next cursor n+1,\n"
            "    // until cursor 3 which signals the end (null).\n"
            "    const fetchPage = (cursor: number) => ({\n"
            "      items: ['item' + cursor],\n"
            "      next: cursor >= 3 ? null : cursor + 1,\n"
            "    })\n"
            "    const getNextPageParam = (lastPage: any) => lastPage.next\n"
            "    let acc: any = { pages: [], pageParams: [] }\n"
            "    let param: any = 1\n"
            "    let hasNext = true\n"
            "    let guard = 0\n"
            "    while (hasNext && guard++ < 50) {\n"
            "      const page = fetchPage(param)\n"
            "      const r = appendPage({ current: acc, page, param, getNextPageParam })\n"
            "      acc = r.next\n"
            "      hasNext = r.hasNextPage\n"
            "      if (hasNext) param = r.nextPageParam\n"
            "    }\n"
            "    expect(acc.pageParams).toEqual([1, 2, 3])\n"
            "    expect(acc.pages.map((p: any) => p.items[0])).toEqual(['item1', 'item2', 'item3'])\n"
            "    expect(hasNext).toBe(false)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe)
        _assert_vitest_passed(result, combined)
