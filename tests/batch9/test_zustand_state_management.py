"""Benchmark tests for the `zustand-state-management` skill (variant ext9).

Variant task (tasks/ext9/zustand-state-management.md): the agent must build a
self-contained *versioned preferences* domain module on top of zustand's public
vanilla `createStore` API. Deliverables:
  - examples/preferences-store/preferencesStore.ts  (factory `createPreferencesStore` + types)
  - tests/preferencesStore.test.ts                  (the agent's own Vitest suite)

The preferences store exposes the vanilla handles (`getState`, `setState`,
`subscribe`) and a state shape:
  - theme: 'light' | 'dark' | 'system'   (default 'system')
  - fontScale: number                    (default 1, clamped to [0.5, 2])
  - language: string                     (default 'en')
  - isDefault: boolean                   (derived; true iff all three are default)
Actions: setTheme / setFontScale / setLanguage / resetToDefaults.
Persistence: optional `options.storage` (getItem/setItem/removeItem). On every
mutation the prefs are serialized under a stable key with numeric schema
`version` (current = 2). A fresh store rehydrates a populated storage; a
`version: 1` payload using a boolean `darkMode` is migrated to `theme` and
written back; missing/malformed/unknown-version payloads fall back to defaults
without throwing.

Verification strategy
---------------------
L1: deliverable files exist, are minimally well-formed, export the factory, and
    the agent's own suite passes (`pnpm vitest run tests/preferencesStore.test.ts`)
    with >= 10 cases.

L2: DISCRIMINATIVE dynamic execution. We DO NOT trust the agent's own tests.
    We inject our OWN independent Vitest drivers under tests/ that import the
    agent's `createPreferencesStore` directly and assert exact runtime behavior:
    defaults, theme validation, fontScale clamping + non-finite rejection,
    language trimming/blank rejection, isDefault derived consistency,
    resetToDefaults, persistence-after-mutation with current version=2,
    rehydration of a current-version payload, migration of a version=1
    darkMode payload (with write-back), and robust fallback to defaults on
    missing/malformed/future-version payloads.

A naive / hardcoded / "looks related" implementation (ignores validation,
skips clamping, drops the version, never migrates, throws on bad JSON, or
hardcodes isDefault) fails these drivers.
"""

import os
import re
import shutil
import subprocess
import uuid

import pytest

try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - helper is present at runtime
    ensure_npm_dependencies = None


REPO_DIR = "/workspace/zustand"
PREFS_STORE = os.path.join(
    REPO_DIR, "examples", "preferences-store", "preferencesStore.ts"
)
AGENT_TEST = os.path.join(REPO_DIR, "tests", "preferencesStore.test.ts")

# Independent driver files we create under tests/ so vitest (dir: 'tests')
# picks them up. Each is removed in teardown; a unique tag avoids clobbering.
_TAG = uuid.uuid4().hex[:8]
_DRIVER_BASENAME = f"_bench_prefs_driver_{_TAG}.test.ts"
DRIVER_PATH = os.path.join(REPO_DIR, "tests", _DRIVER_BASENAME)

VITEST_TIMEOUT = 600

# Relative import path from a file living in tests/ to the prefs store module.
_IMPORT = "../examples/preferences-store/preferencesStore"

# Reusable in-memory storage helper injected into each driver.
_STORAGE_HELPER = """
function makeStorage(initial?: Record<string, string>) {
  const map = new Map<string, string>()
  if (initial) for (const k of Object.keys(initial)) map.set(k, initial[k])
  return {
    getItem: (name: string) => (map.has(name) ? map.get(name)! : null),
    setItem: (name: string, value: string) => { map.set(name, value) },
    removeItem: (name: string) => { map.delete(name) },
    _map: map,
    entries: () => Array.from(map.entries()),
  }
}
"""


def _pnpm_available():
    return shutil.which("pnpm") is not None


@pytest.fixture(scope="module", autouse=True)
def _prepare_deps():
    """Best-effort install of node deps before running native vitest."""
    if ensure_npm_dependencies is not None:
        try:
            ensure_npm_dependencies(REPO_DIR)
        except Exception:
            if _pnpm_available():
                subprocess.run(
                    ["pnpm", "install", "--frozen-lockfile=false"],
                    cwd=REPO_DIR,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )
    yield


def _run_vitest(rel_file):
    """Run `pnpm vitest run <rel_file>` (or npx fallback) from REPO_DIR."""
    if _pnpm_available():
        cmd = ["pnpm", "vitest", "run", rel_file, "--reporter=verbose"]
    else:
        cmd = ["npx", "vitest", "run", rel_file, "--reporter=verbose"]
    return subprocess.run(
        cmd,
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
        timeout=VITEST_TIMEOUT,
    )


def _write_driver(body):
    os.makedirs(os.path.dirname(DRIVER_PATH), exist_ok=True)
    with open(DRIVER_PATH, "w") as fh:
        fh.write(body)
    return _DRIVER_BASENAME


def _cleanup_driver():
    try:
        if os.path.exists(DRIVER_PATH):
            os.remove(DRIVER_PATH)
    except OSError:
        pass


def _run_driver(body):
    """Write a driver, run it via native vitest, clean up, return result."""
    rel = _write_driver(body)
    try:
        return _run_vitest(rel)
    finally:
        _cleanup_driver()


def _assert_passed(proc, scenario):
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, (
        f"vitest driver for '{scenario}' failed (rc={proc.returncode}).\n"
        f"{combined[-4000:]}"
    )


class TestZustandStateManagement:
    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------ L1
    def test_prefs_store_module_exists(self):
        """L1: examples/preferences-store/preferencesStore.ts exists, non-trivial."""
        assert os.path.isfile(PREFS_STORE), f"missing {PREFS_STORE}"
        size = os.path.getsize(PREFS_STORE)
        assert size > 200, f"preferencesStore.ts suspiciously small ({size} bytes)"

    def test_module_exports_factory(self):
        """L1: module declares an exported `createPreferencesStore`."""
        with open(PREFS_STORE) as fh:
            src = fh.read()
        assert re.search(r"export\b[\s\S]*\bcreatePreferencesStore\b", src) or re.search(
            r"\bcreatePreferencesStore\b", src
        ), "createPreferencesStore not found in preferencesStore.ts"

    def test_agent_test_suite_exists(self):
        """L1: the agent's own Vitest suite file exists and is non-trivial."""
        assert os.path.isfile(AGENT_TEST), f"missing {AGENT_TEST}"
        assert os.path.getsize(AGENT_TEST) > 200

    def test_agent_suite_passes(self):
        """L1/L2: the agent's own tests/preferencesStore.test.ts suite passes."""
        proc = _run_vitest("tests/preferencesStore.test.ts")
        _assert_passed(proc, "agent preferencesStore.test.ts suite")
        # The task requires at least 10 cases; verify vitest actually ran a
        # healthy number of tests rather than a single rubber-stamp.
        combined = (proc.stdout or "") + (proc.stderr or "")
        m = re.search(r"Tests\s+(\d+)\s+passed", combined)
        if m:
            assert int(m.group(1)) >= 10, (
                f"expected >=10 passing tests, parsed {m.group(1)}\n"
                f"{combined[-2000:]}"
            )

    # ------------------------------------------------------------------ L2
    def test_defaults_and_is_default(self):
        """L2: a fresh store has the documented defaults and isDefault === true."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createPreferencesStore }} from '{_IMPORT}'

describe('bench-defaults', () => {{
  it('exposes vanilla handles and default preferences', () => {{
    const store = createPreferencesStore()
    expect(typeof store.getState).toBe('function')
    expect(typeof store.setState).toBe('function')
    expect(typeof store.subscribe).toBe('function')
    const s = store.getState()
    expect(s.theme).toBe('system')
    expect(s.fontScale).toBe(1)
    expect(s.language).toBe('en')
    expect(s.isDefault).toBe(true)
  }})
}})
"""
        _assert_passed(_run_driver(body), "defaults + isDefault")

    def test_set_theme_valid_and_invalid(self):
        """L2: setTheme accepts allowed values, rejects invalid (no state change)."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createPreferencesStore }} from '{_IMPORT}'

describe('bench-set-theme', () => {{
  it('accepts light/dark/system and rejects anything else', () => {{
    const store = createPreferencesStore()
    store.getState().setTheme('dark')
    expect(store.getState().theme).toBe('dark')
    expect(store.getState().isDefault).toBe(false)
    store.getState().setTheme('light')
    expect(store.getState().theme).toBe('light')
    store.getState().setTheme('system')
    expect(store.getState().theme).toBe('system')
    expect(store.getState().isDefault).toBe(true)
    // invalid value -> rejected, no change
    store.getState().setTheme('dark')
    expect(() => store.getState().setTheme('blue' as any)).not.toThrow()
    expect(store.getState().theme).toBe('dark')
    expect(() => store.getState().setTheme('' as any)).not.toThrow()
    expect(store.getState().theme).toBe('dark')
  }})
}})
"""
        _assert_passed(_run_driver(body), "setTheme valid/invalid")

    def test_set_font_scale_clamping_and_non_finite(self):
        """L2: setFontScale clamps to [0.5,2]; non-finite rejected (no change)."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createPreferencesStore }} from '{_IMPORT}'

describe('bench-fontscale', () => {{
  it('clamps into [0.5, 2] and rejects non-finite', () => {{
    const store = createPreferencesStore()
    store.getState().setFontScale(1.25)
    expect(store.getState().fontScale).toBeCloseTo(1.25, 6)
    // clamp high
    store.getState().setFontScale(5)
    expect(store.getState().fontScale).toBe(2)
    // clamp low
    store.getState().setFontScale(0.1)
    expect(store.getState().fontScale).toBe(0.5)
    // boundaries kept exactly
    store.getState().setFontScale(0.5)
    expect(store.getState().fontScale).toBe(0.5)
    store.getState().setFontScale(2)
    expect(store.getState().fontScale).toBe(2)
    // non-finite rejected (keeps last valid value of 2)
    expect(() => store.getState().setFontScale(NaN)).not.toThrow()
    expect(store.getState().fontScale).toBe(2)
    expect(() => store.getState().setFontScale(Infinity)).not.toThrow()
    expect(store.getState().fontScale).toBe(2)
    expect(() => store.getState().setFontScale(-Infinity)).not.toThrow()
    expect(store.getState().fontScale).toBe(2)
  }})
}})
"""
        _assert_passed(_run_driver(body), "setFontScale clamp + non-finite")

    def test_set_language_trim_and_blank(self):
        """L2: setLanguage trims and rejects blank/whitespace-only input."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createPreferencesStore }} from '{_IMPORT}'

describe('bench-language', () => {{
  it('accepts trimmed non-empty strings, rejects blank', () => {{
    const store = createPreferencesStore()
    store.getState().setLanguage('  fr  ')
    expect(store.getState().language).toBe('fr')
    expect(store.getState().isDefault).toBe(false)
    // blank / whitespace-only rejected, value retained
    expect(() => store.getState().setLanguage('')).not.toThrow()
    expect(store.getState().language).toBe('fr')
    expect(() => store.getState().setLanguage('   ')).not.toThrow()
    expect(store.getState().language).toBe('fr')
  }})
}})
"""
        _assert_passed(_run_driver(body), "setLanguage trim/blank")

    def test_reset_to_defaults_and_derived_consistency(self):
        """L2: resetToDefaults restores defaults; isDefault never drifts."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createPreferencesStore }} from '{_IMPORT}'

function expectedIsDefault(s: any) {{
  return s.theme === 'system' && s.fontScale === 1 && s.language === 'en'
}}

describe('bench-reset-derived', () => {{
  it('isDefault equals an independent recompute after every action', () => {{
    const store = createPreferencesStore()
    const ops: Array<() => void> = [
      () => store.getState().setTheme('dark'),
      () => store.getState().setFontScale(1.5),
      () => store.getState().setLanguage('de'),
      () => store.getState().setTheme('system'),
      () => store.getState().setFontScale(1),
      () => store.getState().setLanguage('en'),   // back to all defaults
      () => store.getState().setFontScale(0.75),
    ]
    for (const op of ops) {{
      op()
      const s = store.getState()
      expect(s.isDefault).toBe(expectedIsDefault(s))
    }}
    // resetToDefaults makes everything default and isDefault true
    store.getState().setTheme('light')
    store.getState().setFontScale(2)
    store.getState().setLanguage('jp')
    expect(store.getState().isDefault).toBe(false)
    store.getState().resetToDefaults()
    const s = store.getState()
    expect(s.theme).toBe('system')
    expect(s.fontScale).toBe(1)
    expect(s.language).toBe('en')
    expect(s.isDefault).toBe(true)
  }})
}})
"""
        _assert_passed(_run_driver(body), "resetToDefaults + derived consistency")

    def test_persist_current_version_after_mutation(self):
        """L2: mutations serialize prefs under a stable key with version === 2."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createPreferencesStore }} from '{_IMPORT}'
{_STORAGE_HELPER}
describe('bench-persist', () => {{
  it('writes current-version payload after a mutation', () => {{
    const storage = makeStorage()
    const store = createPreferencesStore({{ storage }})
    store.getState().setTheme('dark')
    store.getState().setFontScale(1.5)
    store.getState().setLanguage('es')
    expect(storage._map.size).toBeGreaterThan(0)
    // find the persisted payload, parse it, assert shape + version
    const raw = storage.entries().map((e: any) => e[1])
    let parsed: any = null
    for (const v of raw) {{
      try {{ const p = JSON.parse(v); if (p && typeof p === 'object') parsed = p }} catch {{}}
    }}
    expect(parsed).not.toBeNull()
    expect(parsed.version).toBe(2)
    // the serialized preferences must reflect the mutations (allow either a
    // nested `state`/`preferences` object or a flat payload)
    const flat = JSON.stringify(parsed)
    expect(flat).toContain('dark')
    expect(flat).toContain('es')
  }})
}})
"""
        _assert_passed(_run_driver(body), "persist current version")

    def test_rehydrate_current_version_payload(self):
        """L2: a fresh store rehydrates a populated storage and recomputes isDefault."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createPreferencesStore }} from '{_IMPORT}'
{_STORAGE_HELPER}
describe('bench-rehydrate', () => {{
  it('rehydrates saved preferences into a new store', () => {{
    // First store persists non-default prefs.
    const storage = makeStorage()
    const s1 = createPreferencesStore({{ storage }})
    s1.getState().setTheme('dark')
    s1.getState().setFontScale(1.75)
    s1.getState().setLanguage('fr')
    // A brand-new store over the same storage must rehydrate them.
    const s2 = createPreferencesStore({{ storage }})
    const s = s2.getState()
    expect(s.theme).toBe('dark')
    expect(s.fontScale).toBeCloseTo(1.75, 6)
    expect(s.language).toBe('fr')
    expect(s.isDefault).toBe(false)
  }})

  it('rehydrating all-default prefs yields isDefault === true', () => {{
    const storage = makeStorage()
    const s1 = createPreferencesStore({{ storage }})
    // mutate then reset so storage holds a default-equivalent payload
    s1.getState().setTheme('dark')
    s1.getState().resetToDefaults()
    const s2 = createPreferencesStore({{ storage }})
    const s = s2.getState()
    expect(s.theme).toBe('system')
    expect(s.fontScale).toBe(1)
    expect(s.language).toBe('en')
    expect(s.isDefault).toBe(true)
  }})
}})
"""
        _assert_passed(_run_driver(body), "rehydrate current version")

    def test_migrate_version1_darkmode_payload(self):
        """L2: a version:1 darkMode payload migrates to theme and is written back."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createPreferencesStore }} from '{_IMPORT}'
{_STORAGE_HELPER}
// Discover the stable storage key by letting a current-version store write
// once, then reuse that exact key to seed a legacy v1 payload.
function discoverKey(): string {{
  const probe = makeStorage()
  const s = createPreferencesStore({{ storage: probe }})
  s.getState().setTheme('dark')
  const keys = probe.entries().map((e: any) => e[0])
  if (keys.length === 0) throw new Error('store wrote no storage key')
  return keys[0]
}}

describe('bench-migrate', () => {{
  it('migrates darkMode:true -> theme:dark and writes current version back', () => {{
    const key = discoverKey()
    const legacy = JSON.stringify({{ version: 1, darkMode: true }})
    const storage = makeStorage({{ [key]: legacy }})
    const store = createPreferencesStore({{ storage }})
    const s = store.getState()
    expect(s.theme).toBe('dark')
    // other fields keep defaults after migration
    expect(s.fontScale).toBe(1)
    expect(s.language).toBe('en')
    // the migrated payload was written back at the current version
    const after = storage.getItem(key)
    expect(after).not.toBeNull()
    const parsed = JSON.parse(after as string)
    expect(parsed.version).toBe(2)
    expect(JSON.stringify(parsed)).not.toContain('darkMode')
  }})

  it('migrates darkMode:false -> theme:light', () => {{
    const key = discoverKey()
    const legacy = JSON.stringify({{ version: 1, darkMode: false }})
    const storage = makeStorage({{ [key]: legacy }})
    const store = createPreferencesStore({{ storage }})
    const s = store.getState()
    expect(s.theme).toBe('light')
    expect(s.fontScale).toBe(1)
    expect(s.language).toBe('en')
    const parsed = JSON.parse(storage.getItem(key) as string)
    expect(parsed.version).toBe(2)
  }})
}})
"""
        _assert_passed(_run_driver(body), "migrate v1 darkMode")

    def test_fallback_on_bad_payloads(self):
        """L2: missing/malformed/unknown-version payloads fall back to defaults."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createPreferencesStore }} from '{_IMPORT}'
{_STORAGE_HELPER}
function discoverKey(): string {{
  const probe = makeStorage()
  const s = createPreferencesStore({{ storage: probe }})
  s.getState().setLanguage('zz')
  const keys = probe.entries().map((e: any) => e[0])
  if (keys.length === 0) throw new Error('store wrote no storage key')
  return keys[0]
}}

function expectDefaults(store: any) {{
  const s = store.getState()
  expect(s.theme).toBe('system')
  expect(s.fontScale).toBe(1)
  expect(s.language).toBe('en')
  expect(s.isDefault).toBe(true)
}}

describe('bench-fallback', () => {{
  it('missing payload -> defaults, no throw', () => {{
    const storage = makeStorage()  // empty
    let store: any
    expect(() => {{ store = createPreferencesStore({{ storage }}) }}).not.toThrow()
    expectDefaults(store)
  }})

  it('malformed JSON -> defaults, no throw', () => {{
    const key = discoverKey()
    const storage = makeStorage({{ [key]: '{{not valid json' }})
    let store: any
    expect(() => {{ store = createPreferencesStore({{ storage }}) }}).not.toThrow()
    expectDefaults(store)
  }})

  it('unrecognized future version -> defaults, no throw', () => {{
    const key = discoverKey()
    const payload = JSON.stringify({{ version: 999, theme: 'dark', fontScale: 2, language: 'fr' }})
    const storage = makeStorage({{ [key]: payload }})
    let store: any
    expect(() => {{ store = createPreferencesStore({{ storage }}) }}).not.toThrow()
    expectDefaults(store)
  }})
}})
"""
        _assert_passed(_run_driver(body), "fallback on bad payloads")

    def test_no_storage_has_no_side_effects(self):
        """L2: omitting options.storage works normally with no persistence."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createPreferencesStore }} from '{_IMPORT}'

describe('bench-no-storage', () => {{
  it('mutations work and never throw without a storage backend', () => {{
    const store = createPreferencesStore()
    expect(() => {{
      store.getState().setTheme('dark')
      store.getState().setFontScale(1.5)
      store.getState().setLanguage('it')
      store.getState().resetToDefaults()
    }}).not.toThrow()
    const s = store.getState()
    expect(s.theme).toBe('system')
    expect(s.fontScale).toBe(1)
    expect(s.language).toBe('en')
    expect(s.isDefault).toBe(true)
  }})
}})
"""
        _assert_passed(_run_driver(body), "no storage / no side effects")
