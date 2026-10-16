"""
Benchmark test for the `valibot-validation` skill (variant batch: ext2).

Skill task: implement a self-contained Environment Configuration Loader
(`library/src/envConfig/`) built on Valibot's own public API. The module
exports `loadConfig(env: unknown)` plus the underlying schema. The raw env map
is string-only (the shape of `process.env`); the loader must COERCE values to
their proper runtime types, apply defaults, strip unknown keys, and THROW for
malformed configuration. Unlike ext1, `loadConfig` returns the normalized,
fully-typed config object DIRECTLY (no `{ok, ...}` wrapper) and throws on error.

Field contract (from the variant requirement doc):
  * NODE_ENV   (optional) picklist development|production|test, default "development"
  * PORT       (required) string -> number, whole, inclusive 1..65535
  * DATABASE_URL (required) valid URL string, stored unchanged
  * LOG_LEVEL  (optional) picklist error|warn|info|debug, default "info"
  * ENABLE_CACHE (optional) "true"/"false" (case-sensitive) -> boolean, default false
  * MAX_CONNECTIONS (optional) string -> number, whole, >= 1, default 10

What this test verifies:
  * L1 - the deliverable files exist and are minimally well-formed (the module,
    its barrel re-export, and a test suite with >= 10 cases).
  * L2 - DYNAMIC EXECUTION: we drop our OWN vitest drivers into the repo that
    import the agent's `loadConfig` from `library/src/envConfig/index.ts` and
    exercise every field rule (coercion, defaulting, range/picklist/URL
    rejection, unknown-key stripping, and throw-on-invalid), deep-validating
    concrete returned values and types. The agent's own test file is NOT
    trusted for behavior; we exercise the real exported function instead. A
    final L2 case also runs the agent's authored suite under the native command.

A naive implementation that returns a fixed object, skips coercion (leaving
PORT/MAX_CONNECTIONS as strings or ENABLE_CACHE as a string), ignores defaults,
fails to strip unknown keys, or never throws on invalid input MUST fail here.

Run by the harness with:
    python -m pytest /tmp/benchmark_tests/test_valibot_validation.py -v --tb=short

Native acceptance command (driven by L2), from the library/ directory:
    npx vitest run src/envConfig/envConfig.test.ts
"""

import os
import subprocess
import textwrap

import pytest

REPO_DIR = "/workspace/valibot"
LIB_DIR = os.path.join(REPO_DIR, "library")
SRC_DIR = os.path.join(LIB_DIR, "src")
MODULE_DIR = os.path.join(SRC_DIR, "envConfig")
# Temp dir for our own driver vitest files (kept inside src so vite resolves it).
DRIVER_DIR = os.path.join(SRC_DIR, "__benchmark_envconfig__")

NPX = "npx"
VITEST_TIMEOUT = 600


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module", autouse=True)
def ensure_deps_and_cleanup():
    """Make sure vitest is runnable and clean up our driver dir afterwards."""
    try:
        from _dependency_utils import ensure_npm_dependencies  # type: ignore

        try:
            ensure_npm_dependencies(LIB_DIR)
        except Exception:
            # Container is expected to already have deps installed; ignore.
            pass
    except Exception:
        pass
    os.makedirs(DRIVER_DIR, exist_ok=True)
    yield
    # Best-effort cleanup of anything we wrote.
    try:
        import shutil

        shutil.rmtree(DRIVER_DIR, ignore_errors=True)
    except Exception:
        pass


def _run_vitest(test_filename):
    """Run a single vitest file (relative to library/) and return CompletedProcess."""
    rel = os.path.relpath(os.path.join(DRIVER_DIR, test_filename), LIB_DIR)
    return subprocess.run(
        [NPX, "vitest", "run", "--no-coverage", rel],
        cwd=LIB_DIR,
        capture_output=True,
        text=True,
        timeout=VITEST_TIMEOUT,
    )


def _write_driver(test_filename, body):
    """Write a vitest driver that imports the agent's module and asserts `body`.

    `body` is TypeScript placed inside a single `test(...)` block. The driver
    imports `loadConfig` from the agent's barrel file via a relative path. A
    `BASE` helper holds the minimal valid env map so individual cases override
    only the field under test.
    """
    path = os.path.join(DRIVER_DIR, test_filename)
    content = textwrap.dedent(
        """
        import {{ describe, expect, test }} from 'vitest';
        import {{ loadConfig }} from '../envConfig/index.ts';

        // Minimal valid raw env map (string-only, the shape of process.env).
        const BASE = {{
          PORT: '8080',
          DATABASE_URL: 'https://db.example.com',
        }};

        describe('envConfig benchmark driver', () => {{
          test('case', () => {{
        {body}
          }});
        }});
        """
    ).format(body=textwrap.indent(textwrap.dedent(body), "    "))
    with open(path, "w") as fh:
        fh.write(content)
    return path


def _assert_vitest_pass(proc, label):
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, (
        f"[{label}] vitest run failed (rc={proc.returncode}).\n"
        f"----- stdout/stderr -----\n{combined[-4000:]}"
    )
    # Guard against "0 passed" / no-tests-found situations.
    assert "passed" in combined, (
        f"[{label}] vitest produced no passing tests.\n{combined[-2000:]}"
    )


# --------------------------------------------------------------------------- #
class TestValibotValidation:
    REPO_DIR = REPO_DIR

    # ----------------------------------------------------------------------- #
    # L1 - deliverable files exist and are minimally well-formed
    # ----------------------------------------------------------------------- #
    def test_module_file_exists(self):
        """L1: envConfig.ts exists and is non-trivially sized."""
        path = os.path.join(MODULE_DIR, "envConfig.ts")
        assert os.path.isfile(path), f"missing module: {path}"
        assert os.path.getsize(path) > 100, "envConfig.ts is suspiciously small"

    def test_module_uses_public_api_and_exports_loadConfig(self):
        """L1: module imports valibot's public API and exports loadConfig."""
        path = os.path.join(MODULE_DIR, "envConfig.ts")
        with open(path) as fh:
            text = fh.read()
        # Built on the library's own public API (per the doc), not a 3rd-party dep.
        assert "../index.ts" in text, (
            "envConfig.ts should build on the library's public API "
            "(import from '../index.ts')"
        )
        assert "loadConfig" in text, "envConfig.ts does not define loadConfig"

    def test_barrel_index_exists(self):
        """L1: index.ts barrel exists and re-exports from the envConfig module."""
        path = os.path.join(MODULE_DIR, "index.ts")
        assert os.path.isfile(path), f"missing barrel: {path}"
        with open(path) as fh:
            text = fh.read()
        assert "envConfig" in text, "index.ts does not re-export the envConfig module"

    def test_agent_test_suite_exists(self):
        """L1: the agent authored a test suite with at least 10 test cases."""
        path = os.path.join(MODULE_DIR, "envConfig.test.ts")
        assert os.path.isfile(path), f"missing test file: {path}"
        with open(path) as fh:
            text = fh.read()
        # Count `test(`/`it(` occurrences as a coarse lower bound.
        n = text.count("test(") + text.count("it(")
        assert n >= 10, f"expected >= 10 test cases in suite, found ~{n}"

    # ----------------------------------------------------------------------- #
    # L2 - dynamic execution against the real exported function
    # ----------------------------------------------------------------------- #
    def test_full_payload_normalization(self):
        """L2: the doc's example payload -> fully typed & coerced config object."""
        _write_driver(
            "full.test.ts",
            """
            const cfg = loadConfig({
              NODE_ENV: 'production',
              PORT: '8080',
              DATABASE_URL: 'https://db.example.com',
              LOG_LEVEL: 'debug',
              ENABLE_CACHE: 'true',
              MAX_CONNECTIONS: '25',
            }) as any;
            // Returns the normalized object DIRECTLY (no result wrapper).
            expect(cfg.NODE_ENV).toBe('production');
            expect(cfg.PORT).toBe(8080);
            expect(typeof cfg.PORT).toBe('number');
            expect(cfg.DATABASE_URL).toBe('https://db.example.com');
            expect(cfg.LOG_LEVEL).toBe('debug');
            expect(cfg.ENABLE_CACHE).toBe(true);
            expect(typeof cfg.ENABLE_CACHE).toBe('boolean');
            expect(cfg.MAX_CONNECTIONS).toBe(25);
            expect(typeof cfg.MAX_CONNECTIONS).toBe('number');
            // It must NOT be wrapped in {ok, data}.
            expect('ok' in cfg).toBe(false);
            expect('data' in cfg).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("full.test.ts"), "full")

    def test_all_defaults_applied(self):
        """L2: a minimal payload applies every documented default with correct types."""
        _write_driver(
            "defaults.test.ts",
            """
            const cfg = loadConfig({
              PORT: '3000',
              DATABASE_URL: 'http://localhost',
            }) as any;
            expect(cfg.NODE_ENV).toBe('development');
            expect(cfg.LOG_LEVEL).toBe('info');
            expect(cfg.ENABLE_CACHE).toBe(false);
            expect(typeof cfg.ENABLE_CACHE).toBe('boolean');
            expect(cfg.MAX_CONNECTIONS).toBe(10);
            expect(typeof cfg.MAX_CONNECTIONS).toBe('number');
            expect(cfg.PORT).toBe(3000);
            expect(typeof cfg.PORT).toBe('number');
            expect(cfg.DATABASE_URL).toBe('http://localhost');
            """,
        )
        _assert_vitest_pass(_run_vitest("defaults.test.ts"), "defaults")

    def test_port_coercion_and_range(self):
        """L2: PORT string->number with inclusive 1..65535 bounds enforced."""
        _write_driver(
            "port.test.ts",
            """
            // valid mid value coerces to a number
            const ok = loadConfig({ ...BASE, PORT: '443' }) as any;
            expect(ok.PORT).toBe(443);
            expect(typeof ok.PORT).toBe('number');

            // boundary values accepted
            const low = loadConfig({ ...BASE, PORT: '1' }) as any;
            expect(low.PORT).toBe(1);
            const high = loadConfig({ ...BASE, PORT: '65535' }) as any;
            expect(high.PORT).toBe(65535);

            // out-of-range rejected
            expect(() => loadConfig({ ...BASE, PORT: '70000' })).toThrow();
            expect(() => loadConfig({ ...BASE, PORT: '0' })).toThrow();
            expect(() => loadConfig({ ...BASE, PORT: '-5' })).toThrow();

            // non-numeric rejected
            expect(() => loadConfig({ ...BASE, PORT: 'abc' })).toThrow();

            // fractional rejected (must be a whole number)
            expect(() => loadConfig({ ...BASE, PORT: '80.5' })).toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("port.test.ts"), "port")

    def test_port_required(self):
        """L2: PORT is required - omitting it must throw (not silently default)."""
        _write_driver(
            "port_required.test.ts",
            """
            expect(() => loadConfig({ DATABASE_URL: 'http://x' })).toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("port_required.test.ts"), "port_required")

    def test_database_url_validation(self):
        """L2: DATABASE_URL must be a valid URL, stored unchanged; invalid rejected."""
        _write_driver(
            "url.test.ts",
            """
            // valid URL stored unchanged
            const cfg = loadConfig({ ...BASE, DATABASE_URL: 'https://db.example.com/path?x=1' }) as any;
            expect(cfg.DATABASE_URL).toBe('https://db.example.com/path?x=1');

            // invalid URL strings rejected
            expect(() => loadConfig({ ...BASE, DATABASE_URL: 'not a url' })).toThrow();
            expect(() => loadConfig({ ...BASE, DATABASE_URL: '' })).toThrow();

            // missing required DATABASE_URL rejected
            expect(() => loadConfig({ PORT: '80' })).toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("url.test.ts"), "url")

    def test_node_env_picklist(self):
        """L2: NODE_ENV accepts only dev/prod/test; default development; else throws."""
        _write_driver(
            "node_env.test.ts",
            """
            for (const e of ['development', 'production', 'test']) {
              const cfg = loadConfig({ ...BASE, NODE_ENV: e }) as any;
              expect(cfg.NODE_ENV).toBe(e);
            }
            // default when absent
            const def = loadConfig({ ...BASE }) as any;
            expect(def.NODE_ENV).toBe('development');
            // invalid picklist member rejected
            expect(() => loadConfig({ ...BASE, NODE_ENV: 'staging' })).toThrow();
            expect(() => loadConfig({ ...BASE, NODE_ENV: 'PRODUCTION' })).toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("node_env.test.ts"), "node_env")

    def test_log_level_picklist(self):
        """L2: LOG_LEVEL accepts only error/warn/info/debug; default info; else throws."""
        _write_driver(
            "log_level.test.ts",
            """
            for (const lvl of ['error', 'warn', 'info', 'debug']) {
              const cfg = loadConfig({ ...BASE, LOG_LEVEL: lvl }) as any;
              expect(cfg.LOG_LEVEL).toBe(lvl);
            }
            // default when absent
            const def = loadConfig({ ...BASE }) as any;
            expect(def.LOG_LEVEL).toBe('info');
            // invalid value rejected
            expect(() => loadConfig({ ...BASE, LOG_LEVEL: 'verbose' })).toThrow();
            expect(() => loadConfig({ ...BASE, LOG_LEVEL: 'INFO' })).toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("log_level.test.ts"), "log_level")

    def test_enable_cache_boolean_coercion(self):
        """L2: ENABLE_CACHE 'true'/'false' (case-sensitive) -> boolean; default false."""
        _write_driver(
            "enable_cache.test.ts",
            """
            const t = loadConfig({ ...BASE, ENABLE_CACHE: 'true' }) as any;
            expect(t.ENABLE_CACHE).toBe(true);
            expect(typeof t.ENABLE_CACHE).toBe('boolean');

            const f = loadConfig({ ...BASE, ENABLE_CACHE: 'false' }) as any;
            expect(f.ENABLE_CACHE).toBe(false);
            expect(typeof f.ENABLE_CACHE).toBe('boolean');

            // default when absent
            const def = loadConfig({ ...BASE }) as any;
            expect(def.ENABLE_CACHE).toBe(false);

            // anything else (incl. case variants / truthy strings) rejected
            expect(() => loadConfig({ ...BASE, ENABLE_CACHE: 'yes' })).toThrow();
            expect(() => loadConfig({ ...BASE, ENABLE_CACHE: 'True' })).toThrow();
            expect(() => loadConfig({ ...BASE, ENABLE_CACHE: '1' })).toThrow();
            expect(() => loadConfig({ ...BASE, ENABLE_CACHE: '' })).toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("enable_cache.test.ts"), "enable_cache")

    def test_max_connections_coercion_and_min(self):
        """L2: MAX_CONNECTIONS string->number, whole, >=1; default 10; else throws."""
        _write_driver(
            "max_conn.test.ts",
            """
            const cfg = loadConfig({ ...BASE, MAX_CONNECTIONS: '25' }) as any;
            expect(cfg.MAX_CONNECTIONS).toBe(25);
            expect(typeof cfg.MAX_CONNECTIONS).toBe('number');

            // boundary 1 accepted
            const one = loadConfig({ ...BASE, MAX_CONNECTIONS: '1' }) as any;
            expect(one.MAX_CONNECTIONS).toBe(1);

            // default when absent
            const def = loadConfig({ ...BASE }) as any;
            expect(def.MAX_CONNECTIONS).toBe(10);

            // below minimum / non-whole / non-numeric rejected
            expect(() => loadConfig({ ...BASE, MAX_CONNECTIONS: '0' })).toThrow();
            expect(() => loadConfig({ ...BASE, MAX_CONNECTIONS: '-3' })).toThrow();
            expect(() => loadConfig({ ...BASE, MAX_CONNECTIONS: '2.5' })).toThrow();
            expect(() => loadConfig({ ...BASE, MAX_CONNECTIONS: 'lots' })).toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("max_conn.test.ts"), "max_conn")

    def test_unknown_keys_stripped(self):
        """L2: unknown extra keys in the raw env map must not appear in the output."""
        _write_driver(
            "strip.test.ts",
            """
            const cfg = loadConfig({
              PORT: '8080',
              DATABASE_URL: 'https://db.example.com',
              HOME: '/root',
              PATH: '/usr/bin',
              SECRET_TOKEN: 'abc',
            }) as any;
            const keys = Object.keys(cfg).sort();
            expect(keys).toEqual(
              ['DATABASE_URL','ENABLE_CACHE','LOG_LEVEL','MAX_CONNECTIONS','NODE_ENV','PORT'].sort()
            );
            expect('HOME' in cfg).toBe(false);
            expect('PATH' in cfg).toBe(false);
            expect('SECRET_TOKEN' in cfg).toBe(false);
            """,
        )
        _assert_vitest_pass(_run_vitest("strip.test.ts"), "strip")

    def test_throws_and_does_not_return_malformed(self):
        """L2: invalid configs throw rather than silently returning a malformed object."""
        _write_driver(
            "invalid.test.ts",
            """
            // Every doc-listed invalid case must throw.
            expect(() => loadConfig({ PORT: '70000', DATABASE_URL: 'http://x' })).toThrow();
            expect(() => loadConfig({ PORT: 'abc', DATABASE_URL: 'http://x' })).toThrow();
            expect(() => loadConfig({ PORT: '80', DATABASE_URL: 'not a url' })).toThrow();
            expect(() => loadConfig({ PORT: '80', DATABASE_URL: 'http://x', ENABLE_CACHE: 'yes' })).toThrow();
            expect(() => loadConfig({ PORT: '80', DATABASE_URL: 'http://x', NODE_ENV: 'staging' })).toThrow();

            // Non-object / nullish inputs must also throw (unknown input).
            expect(() => loadConfig(null as unknown)).toThrow();
            expect(() => loadConfig(42 as unknown)).toThrow();
            expect(() => loadConfig('nope' as unknown)).toThrow();
            expect(() => loadConfig(undefined as unknown)).toThrow();
            """,
        )
        _assert_vitest_pass(_run_vitest("invalid.test.ts"), "invalid")

    def test_agent_own_suite_passes(self):
        """L2: the agent's authored suite passes under the native command."""
        proc = subprocess.run(
            [NPX, "vitest", "run", "--no-coverage", "src/envConfig/envConfig.test.ts"],
            cwd=LIB_DIR,
            capture_output=True,
            text=True,
            timeout=VITEST_TIMEOUT,
        )
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        assert proc.returncode == 0, (
            "agent's own envConfig.test.ts suite did not pass.\n"
            f"{combined[-4000:]}"
        )
