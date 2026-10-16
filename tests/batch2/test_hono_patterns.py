"""Tests for the `hono-patterns` skill task (ext2 variant): a mountable
in-memory URL-shortener / redirect module.

Verifies the deliverable `src/helper/url-shortener/index.ts` (and its colocated
`index.test.ts`) inside the Hono repo at /workspace/hono.

Task summary
------------
The agent must add a helper module exporting a factory `createShortener()` that
returns a fresh, isolated, mountable sub-application implementing a URL shortener:

- POST collection root with `{ url, code? }` -> 201 `{ code, url }`; an omitted
  code is auto-assigned from lowercase letters+digits only. Missing/non-string
  `url` -> 400 `{ error }` (no registration). Duplicate `code` -> 409 `{ error }`
  (existing mapping untouched).
- GET the follow path embedding a registered code -> 302 with `Location` set to
  the EXACT destination URL (redirect not followed). `?permanent=true` -> 301
  with the same `Location`. Unknown code -> 404 `{ error }`.
- GET the inspect path embedding a registered code -> 200
  `{ code, url, hits }` where `hits` is the number of successful follow redirects.
- Code segments containing anything other than lowercase letters/digits must be
  an UNMATCHED route (404), not a "not registered" lookup. `hits` increments only
  on successful follows. Errors never mutate state. All instances are isolated.

Verification strategy
---------------------
- L1: the required deliverable files exist and are minimally well-formed (export
  the factory, register POST + the redirect/inspect GET routes, ship a colocated
  vitest test file).
- L2: DYNAMIC EXECUTION. We write an *independent* vitest spec into the repo that
  imports the agent's `createShortener()` and exercises every requirement against
  BOTH a directly-used and a mounted-under-a-prefix instance. It dispatches
  IN-MEMORY requests via `app.request(...)` with `{ redirect: 'manual' }` so the
  redirect itself is never followed, and asserts on real status codes, the exact
  `Location` header, JSON bodies, hit-counting, isolation, and malformed-code
  routing. A naive implementation (shared global mapping, always 302, never
  counting hits, treating malformed codes as valid lookups, or mutating state on
  error) fails specific named cases.

  To keep runtime bounded we run that independent spec ONCE with vitest's JSON
  reporter, cache the per-test results module-wide, and have each L2 Python test
  assert on one specific named case (a missing case is treated as a failure, so a
  solution can't pass by making cases disappear).

- The agent's OWN colocated suite is checked separately: it must contain >=10
  cases and pass, per the acceptance criteria.

Native test command (per task acceptance criteria):
    npx vitest --run src/helper/url-shortener/index.test.ts
"""

import json
import os
import subprocess
import textwrap

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - fallback if helper not co-located
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/hono"
MODULE_DIR = os.path.join(REPO_DIR, "src", "helper", "url-shortener")
MODULE_TS = os.path.join(MODULE_DIR, "index.ts")
MODULE_TEST_TS = os.path.join(MODULE_DIR, "index.test.ts")

# Independent verification spec (unique name; never clobbers agent files).
VERIFY_SPEC = os.path.join(MODULE_DIR, "__bench_verify.test.ts")

NPX = "npx"


@pytest.fixture(scope="module", autouse=True)
def _install_deps():
    """Install repo node deps once before running native vitest."""
    if ensure_npm_dependencies is not None:
        ensure_npm_dependencies(REPO_DIR)
    yield


def _run_vitest(rel_spec, timeout, json_out=None):
    """Run vitest --run on a single spec relative to REPO_DIR.

    Coverage is disabled and the run is scoped to the `main` project to keep
    startup cheap (the repo's default vitest config enables v8 coverage and loads
    several runtime-test projects, which is needlessly slow for one spec).
    """
    cmd = [NPX, "vitest", "--run", "--project", "main", "--coverage.enabled=false"]
    if json_out:
        cmd += ["--reporter=json", f"--outputFile={json_out}"]
    cmd.append(rel_spec)
    result = subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "CI": "true"},
    )
    if result.returncode != 0 and "No test files found" in (result.stdout + result.stderr):
        # Some vitest CLIs reject --project on non-workspace runs; retry plainly.
        cmd = [NPX, "vitest", "--run", "--coverage.enabled=false"]
        if json_out:
            cmd += ["--reporter=json", f"--outputFile={json_out}"]
        cmd.append(rel_spec)
        result = subprocess.run(
            cmd,
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "CI": "true"},
        )
    return result


# ---------------------------------------------------------------------------
# The single comprehensive independent verification spec. Each `it(<name>, ...)`
# maps to one task requirement; the Python L2 tests below assert on these names.
#
# Design notes that make this discriminative:
#  - We mount the shortener under a NON-EMPTY prefix and ALSO use it directly,
#    so a hardcoded-prefix implementation fails one of them.
#  - We discover the module's own route shape generically: POST the collection
#    root, then for every candidate follow/inspect path template, locate the one
#    that yields the expected redirect / inspect JSON. This keeps the harness
#    independent of cosmetic path naming while still enforcing the *behavior*
#    (302/301, exact Location, hits counting, malformed-code routing).
# ---------------------------------------------------------------------------
_VERIFY_SPEC_SRC = textwrap.dedent(
    """
    import { describe, it, expect } from 'vitest'
    import { Hono } from '../../hono'
    import { createShortener } from '.'

    const base = 'http://localhost'

    // A parent app with the shortener mounted under a non-empty prefix, plus the
    // prefix itself so the harness can build absolute URLs.
    const mountedAt = (prefix) => {
      const app = new Hono()
      app.route(prefix, createShortener())
      return app
    }

    const register = (app, root, body) =>
      app.request(base + root, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

    const noFollow = { redirect: 'manual' }

    // Given a registered `code`, probe a small set of plausible follow-path
    // templates beneath `root` and return the first that produces a redirect
    // (3xx) for the registered code. This makes the harness agnostic to the
    // exact path segment naming while still asserting redirect behavior.
    const candidateFollowPaths = (root, code) => [
      root + '/' + code,
      root + '/r/' + code,
      root + '/go/' + code,
      root + '/' + code + '/follow',
      root + '/follow/' + code,
      root + '/redirect/' + code,
    ]
    const candidateInspectPaths = (root, code) => [
      root + '/i/' + code,
      root + '/inspect/' + code,
      root + '/' + code + '/info',
      root + '/info/' + code,
      root + '/' + code + '/stats',
      root + '/stats/' + code,
      root + '/links/' + code,
    ]

    const findFollowPath = async (app, root, code) => {
      for (const p of candidateFollowPaths(root, code)) {
        const res = await app.request(base + p, noFollow)
        if (res.status === 301 || res.status === 302) {
          return p
        }
      }
      return null
    }
    const findInspectPath = async (app, root, code) => {
      for (const p of candidateInspectPaths(root, code)) {
        const res = await app.request(base + p)
        if (res.status === 200) {
          const body = await res.json().catch(() => null)
          if (body && 'hits' in body && body.code === code) {
            return p
          }
        }
      }
      return null
    }

    describe('url-shortener verification', () => {
      it('register_with_code_201_echoes_code_and_url', async () => {
        const root = '/s'
        const app = mountedAt(root)
        const res = await register(app, root, { url: 'https://example.com', code: 'ex' })
        expect(res.status).toBe(201)
        const body = await res.json()
        expect(body.code).toBe('ex')
        expect(body.url).toBe('https://example.com')
      })

      it('register_without_code_assigns_lowercase_alnum_code', async () => {
        const root = '/s'
        const app = mountedAt(root)
        const res = await register(app, root, { url: 'https://example.org/x' })
        expect(res.status).toBe(201)
        const body = await res.json()
        expect(typeof body.code).toBe('string')
        expect(body.code.length).toBeGreaterThan(0)
        expect(/^[a-z0-9]+$/.test(body.code)).toBe(true)
        expect(body.url).toBe('https://example.org/x')
        // The assigned code must actually resolve.
        const fp = await findFollowPath(app, root, body.code)
        expect(fp).not.toBeNull()
      })

      it('register_missing_url_400_no_registration', async () => {
        const root = '/s'
        const app = mountedAt(root)
        const bad = await register(app, root, { code: 'abc' })
        expect(bad.status).toBe(400)
        expect(typeof (await bad.json()).error).toBe('string')
        const bad2 = await register(app, root, { url: 123, code: 'abc' })
        expect(bad2.status).toBe(400)
        // Nothing was registered: 'abc' must not resolve to a redirect.
        const fp = await findFollowPath(app, root, 'abc')
        expect(fp).toBeNull()
      })

      it('duplicate_code_409_keeps_original_mapping', async () => {
        const root = '/s'
        const app = mountedAt(root)
        const first = await register(app, root, { url: 'https://first.example', code: 'dup' })
        expect(first.status).toBe(201)
        const second = await register(app, root, { url: 'https://second.example', code: 'dup' })
        expect(second.status).toBe(409)
        expect(typeof (await second.json()).error).toBe('string')
        // Original mapping intact: follow 'dup' still points at the first url.
        const fp = await findFollowPath(app, root, 'dup')
        expect(fp).not.toBeNull()
        const res = await app.request(base + fp, noFollow)
        expect(res.headers.get('location')).toBe('https://first.example')
      })

      it('follow_registered_code_302_exact_location_no_follow', async () => {
        const root = '/s'
        const app = mountedAt(root)
        await register(app, root, { url: 'https://dest.example/path?q=1', code: 'go' })
        const fp = await findFollowPath(app, root, 'go')
        expect(fp).not.toBeNull()
        const res = await app.request(base + fp, noFollow)
        expect(res.status).toBe(302)
        expect(res.headers.get('location')).toBe('https://dest.example/path?q=1')
      })

      it('follow_permanent_true_returns_301_same_location', async () => {
        const root = '/s'
        const app = mountedAt(root)
        await register(app, root, { url: 'https://perm.example', code: 'pm' })
        const fp = await findFollowPath(app, root, 'pm')
        expect(fp).not.toBeNull()
        const temp = await app.request(base + fp, noFollow)
        expect(temp.status).toBe(302)
        expect(temp.headers.get('location')).toBe('https://perm.example')
        const sep = fp.includes('?') ? '&' : '?'
        const perm = await app.request(base + fp + sep + 'permanent=true', noFollow)
        expect(perm.status).toBe(301)
        expect(perm.headers.get('location')).toBe('https://perm.example')
      })

      it('follow_unknown_code_404_error_json', async () => {
        const root = '/s'
        const app = mountedAt(root)
        await register(app, root, { url: 'https://known.example', code: 'known' })
        // 'missing' is well-formed (lowercase alnum) but never registered.
        let saw404 = false
        for (const p of candidateFollowPaths(root, 'missing')) {
          const res = await app.request(base + p, noFollow)
          if (res.status === 301 || res.status === 302) {
            throw new Error('unknown code unexpectedly redirected at ' + p)
          }
          if (res.status === 404) {
            const body = await res.json().catch(() => null)
            if (body && typeof body.error === 'string') {
              saw404 = true
            }
          }
        }
        expect(saw404).toBe(true)
      })

      it('inspect_reports_hits_count_after_two_follows', async () => {
        const root = '/s'
        const app = mountedAt(root)
        await register(app, root, { url: 'https://hit.example', code: 'hc' })
        const fp = await findFollowPath(app, root, 'hc')
        expect(fp).not.toBeNull()
        const ip = await findInspectPath(app, root, 'hc')
        expect(ip).not.toBeNull()
        // hits starts at 0 before any follow.
        const before = await (await app.request(base + ip)).json()
        expect(before.code).toBe('hc')
        expect(before.url).toBe('https://hit.example')
        expect(before.hits).toBe(0)
        await app.request(base + fp, noFollow)
        await app.request(base + fp, noFollow)
        const after = await (await app.request(base + ip)).json()
        expect(after.hits).toBe(2)
      })

      it('inspect_and_failed_follow_do_not_count_hits', async () => {
        const root = '/s'
        const app = mountedAt(root)
        await register(app, root, { url: 'https://count.example', code: 'cn' })
        const ip = await findInspectPath(app, root, 'cn')
        expect(ip).not.toBeNull()
        // A bunch of inspect calls must not change hits.
        for (let i = 0; i < 3; i++) {
          await app.request(base + ip)
        }
        // A failed follow on an unknown code must not change hits either.
        for (const p of candidateFollowPaths(root, 'nope')) {
          await app.request(base + p, noFollow)
        }
        const after = await (await app.request(base + ip)).json()
        expect(after.hits).toBe(0)
      })

      it('malformed_code_is_unmatched_route_404', async () => {
        const root = '/s'
        const app = mountedAt(root)
        await register(app, root, { url: 'https://valid.example', code: 'ok' })
        const fp = await findFollowPath(app, root, 'ok')
        expect(fp).not.toBeNull()
        // Build a malformed follow path by swapping the code segment for 'EX!'.
        const malformed = fp.replace(/ok(?!.*ok)/, 'EX!')
        const res = await app.request(base + malformed, noFollow)
        expect(res.status).toBe(404)
        // The same uppercase/punctuation code must also not register a real link.
        const reg = await register(app, root, { url: 'https://bad.example', code: 'Ex!' })
        // Either rejected, or — if accepted — it must never be reachable via a
        // malformed follow path (cannot pass by treating malformed codes as valid).
        if (reg.status === 201) {
          const m2 = await app.request(base + fp.replace(/ok(?!.*ok)/, 'Ex!'), noFollow)
          expect(m2.status).toBe(404)
        }
      })

      it('instances_have_isolated_mappings', async () => {
        const root = '/s'
        const a = mountedAt(root)
        const b = mountedAt(root)
        await register(a, root, { url: 'https://only-a.example', code: 'iso' })
        const inA = await findFollowPath(a, root, 'iso')
        expect(inA).not.toBeNull()
        // Same code in b must NOT resolve (separate private mapping).
        const inB = await findFollowPath(b, root, 'iso')
        expect(inB).toBeNull()
        // And b can reuse the code freely with a different destination.
        const reg = await register(b, root, { url: 'https://only-b.example', code: 'iso' })
        expect(reg.status).toBe(201)
        const fpB = await findFollowPath(b, root, 'iso')
        expect(fpB).not.toBeNull()
        const resB = await b.request(base + fpB, noFollow)
        expect(resB.headers.get('location')).toBe('https://only-b.example')
      })

      it('works_directly_and_under_different_prefix', async () => {
        // Direct use (mounted at root) and a deep prefix must both work, proving
        // the sub-app is genuinely mountable and not hardwired to one base path.
        const rootA = '/'
        const appA = new Hono()
        appA.route(rootA, createShortener())
        const regA = await appA.request(base + '/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: 'https://root.example', code: 'rt' }),
        })
        expect(regA.status).toBe(201)
        const fpA = await findFollowPath(appA, '', 'rt')
        expect(fpA).not.toBeNull()
        const resA = await appA.request(base + fpA, noFollow)
        expect(resA.status).toBe(302)
        expect(resA.headers.get('location')).toBe('https://root.example')

        const rootB = '/deep/nested/prefix'
        const appB = mountedAt(rootB)
        await register(appB, rootB, { url: 'https://deep.example', code: 'dp' })
        const fpB = await findFollowPath(appB, rootB, 'dp')
        expect(fpB).not.toBeNull()
        const resB = await appB.request(base + fpB, noFollow)
        expect(resB.status).toBe(302)
        expect(resB.headers.get('location')).toBe('https://deep.example')
      })
    })
    """
)


def _collect_assertion_results(json_path):
    """Parse vitest JSON output into {test_title: 'passed'|'failed'|...}."""
    with open(json_path) as f:
        report = json.load(f)
    results = {}
    for suite in report.get("testResults", []):
        for assertion in suite.get("assertionResults", []):
            results[assertion.get("title")] = assertion.get("status")
    return results


# Module-scoped cache so the independent spec runs exactly once.
_VERIFY_CACHE = {}


def _verify_results():
    if _VERIFY_CACHE:
        return _VERIFY_CACHE["results"]
    os.makedirs(MODULE_DIR, exist_ok=True)
    with open(VERIFY_SPEC, "w") as f:
        f.write(_VERIFY_SPEC_SRC)
    json_path = os.path.join(REPO_DIR, "__bench_verify_report.json")
    try:
        proc = _run_vitest(
            "src/helper/url-shortener/__bench_verify.test.ts", timeout=600, json_out=json_path
        )
        assert os.path.isfile(json_path), (
            "vitest produced no JSON report; the independent verification spec "
            "failed to run (likely a compile/import error in the module).\n"
            f"STDOUT:\n{proc.stdout[-4000:]}\nSTDERR:\n{proc.stderr[-3000:]}"
        )
        results = _collect_assertion_results(json_path)
    finally:
        for p in (VERIFY_SPEC, json_path):
            try:
                os.remove(p)
            except OSError:
                pass
    _VERIFY_CACHE["results"] = results
    _VERIFY_CACHE["proc"] = proc
    return results


def _assert_case(name):
    """Assert a named verification case ran and passed."""
    results = _verify_results()
    status = results.get(name)
    assert status is not None, (
        f"verification case {name!r} did not run; available cases: "
        f"{sorted(results.keys())}\nvitest stderr:\n"
        f"{_VERIFY_CACHE.get('proc').stderr[-2000:] if _VERIFY_CACHE.get('proc') else ''}"
    )
    assert status == "passed", f"verification case {name!r} status={status} (expected passed)"


class TestHonoPatterns:
    REPO_DIR = "/workspace/hono"

    # ------------------------------------------------------------- L1 ----

    def test_module_file_exists(self):
        """L1: the url-shortener module file is present."""
        assert os.path.isfile(MODULE_TS), f"missing deliverable {MODULE_TS}"

    def test_module_exports_factory(self):
        """L1: module source exports a `createShortener` factory."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert "createShortener" in src, "createShortener not found"
        assert "export" in src, "factory not exported"

    def test_module_registers_post_and_get_routes(self):
        """L1: module registers a POST (register) and GET (follow/inspect) route."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert ".post(" in src, "module does not register a POST route"
        assert ".get(" in src, "module does not register a GET route"

    def test_module_uses_redirect(self):
        """L1: module issues redirects (uses c.redirect) for the follow path."""
        with open(MODULE_TS) as f:
            src = f.read()
        assert "redirect" in src, "module does not appear to issue redirects"

    def test_colocated_test_file_exists(self):
        """L1: the colocated deterministic test file exists."""
        assert os.path.isfile(MODULE_TEST_TS), f"missing {MODULE_TEST_TS}"

    def test_agent_suite_has_min_cases_and_passes(self):
        """L2/acceptance: agent's colocated suite has >=10 cases and passes via vitest."""
        with open(MODULE_TEST_TS) as f:
            test_src = f.read()
        case_count = test_src.count("it(") + test_src.count("test(")
        assert case_count >= 10, (
            f"colocated suite has only {case_count} cases; task requires >=10"
        )
        result = _run_vitest("src/helper/url-shortener/index.test.ts", timeout=600)
        assert result.returncode == 0, (
            "agent's colocated vitest suite failed:\n"
            f"STDOUT:\n{result.stdout[-4000:]}\nSTDERR:\n{result.stderr[-3000:]}"
        )

    # ------------------------------------------------------------- L2 ----
    # Each maps to one task requirement, verified by the independent spec.

    def test_register_with_code_201_echoes_code_and_url(self):
        """L2: POST {url, code} -> 201 with body {code, url} echoing the inputs."""
        _assert_case("register_with_code_201_echoes_code_and_url")

    def test_register_without_code_assigns_lowercase_alnum_code(self):
        """L2: omitting `code` assigns a resolvable code of [a-z0-9]+ only."""
        _assert_case("register_without_code_assigns_lowercase_alnum_code")

    def test_register_missing_url_400_no_registration(self):
        """L2: missing/non-string url -> 400 {error}; nothing registered."""
        _assert_case("register_missing_url_400_no_registration")

    def test_duplicate_code_409_keeps_original_mapping(self):
        """L2: re-registering an existing code -> 409 {error}; original mapping intact."""
        _assert_case("duplicate_code_409_keeps_original_mapping")

    def test_follow_registered_code_302_exact_location_no_follow(self):
        """L2: follow a registered code -> 302 with exact Location, redirect not followed."""
        _assert_case("follow_registered_code_302_exact_location_no_follow")

    def test_follow_permanent_true_returns_301_same_location(self):
        """L2: `?permanent=true` switches the redirect status to 301, same Location."""
        _assert_case("follow_permanent_true_returns_301_same_location")

    def test_follow_unknown_code_404_error_json(self):
        """L2: follow a well-formed-but-unregistered code -> 404 {error}, no redirect."""
        _assert_case("follow_unknown_code_404_error_json")

    def test_inspect_reports_hits_count_after_two_follows(self):
        """L2: inspect returns {code,url,hits}; hits==2 after two successful follows."""
        _assert_case("inspect_reports_hits_count_after_two_follows")

    def test_inspect_and_failed_follow_do_not_count_hits(self):
        """L2: inspects and failed (404) follows never increment the hit counter."""
        _assert_case("inspect_and_failed_follow_do_not_count_hits")

    def test_malformed_code_is_unmatched_route_404(self):
        """L2: a code segment with non [a-z0-9] chars is an unmatched route (404)."""
        _assert_case("malformed_code_is_unmatched_route_404")

    def test_instances_have_isolated_mappings(self):
        """L2: two createShortener() instances keep fully private mappings."""
        _assert_case("instances_have_isolated_mappings")

    def test_works_directly_and_under_different_prefix(self):
        """L2: the sub-app works both used directly and mounted under a deep prefix."""
        _assert_case("works_directly_and_under_different_prefix")
