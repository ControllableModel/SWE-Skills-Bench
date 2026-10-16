"""Benchmark tests for the `zustand-state-management` skill (variant ext4).

Verifies the agent's implementation of a self-contained AUTHENTICATION SESSION
store module built on top of zustand's public vanilla `createStore` API.

Source of truth: tasks/ext4/zustand-state-management.md. The task asks the agent
to create:
  - examples/auth-store/authStore.ts  (factory `createAuthStore` + types)
  - tests/authStore.test.ts           (the agent's own Vitest suite)

This is a DIFFERENT task from ext1 (shopping cart). Here the domain is an async
login flow with explicit status/error states, a derived `isAuthenticated`
boolean, logout, and optional session persistence with rehydration.

L1 checks: the deliverable files exist and are minimally well-formed, and the
agent's own suite passes via `pnpm vitest run tests/authStore.test.ts`.

L2 checks: discriminative DYNAMIC EXECUTION. We DO NOT trust the agent's own
test file. Instead we write INDEPENDENT Vitest driver files into REPO_DIR/tests/
that import the agent's `createAuthStore` factory directly and exercise the real
runtime behavior:
  - login success sets user/token/status='authenticated'/isAuthenticated=true
  - login rejection captures error WITHOUT throwing, keeps prior session
  - synchronous throw inside authenticate is also captured
  - invalid-input guard (non-function) -> error state, no async work
  - logout clears session and flips isAuthenticated to false
  - isAuthenticated derived consistency never drifts across actions
  - persistence: successful login writes session to in-memory storage
  - logout removes the persisted session
  - rehydration: a fresh store given the same populated storage restores auth
  - no-storage mode works with no side effects

Each driver runs via the repo's native `pnpm vitest run` and we assert on
returncode. A naive / hardcoded / "looks related" implementation (e.g. one that
ignores the rejection, throws on failure, hardcodes isAuthenticated, or skips
storage) fails these driver tests.
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
AUTH_STORE = os.path.join(REPO_DIR, "examples", "auth-store", "authStore.ts")
AGENT_TEST = os.path.join(REPO_DIR, "tests", "authStore.test.ts")

# Driver files we create under tests/ so vitest (dir: 'tests') picks them up.
# Each is removed in teardown. Use a unique tag to avoid clobbering anything.
_TAG = uuid.uuid4().hex[:8]
_DRIVER_BASENAME = f"_bench_auth_driver_{_TAG}.test.ts"
DRIVER_PATH = os.path.join(REPO_DIR, "tests", _DRIVER_BASENAME)

VITEST_TIMEOUT = 600


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
    """Write an independent vitest driver file under tests/ and return basename."""
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


# Relative import path from a file living in tests/ to the auth store module.
_IMPORT = "../examples/auth-store/authStore"


def _run_driver(body):
    """Helper: write a driver, run it, clean up, return CompletedProcess."""
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


# Shared TS helper injected into drivers: an in-memory key/value storage that
# satisfies the minimal contract (getItem/setItem/removeItem) with no window.
_STORAGE_HELPER = """
function makeStorage(seed?: Record<string, string>) {{
  const map = new Map<string, string>()
  if (seed) {{ for (const k of Object.keys(seed)) map.set(k, seed[k]) }}
  return {{
    getItem: (name: string) => (map.has(name) ? map.get(name)! : null),
    setItem: (name: string, value: string) => {{ map.set(name, value) }},
    removeItem: (name: string) => {{ map.delete(name) }},
    _map: map,
  }}
}}
"""


class TestZustandStateManagement:
    REPO_DIR = REPO_DIR

    # ------------------------------------------------------------------ L1
    def test_auth_store_module_exists(self):
        """L1: examples/auth-store/authStore.ts exists and is non-trivial."""
        assert os.path.isfile(AUTH_STORE), f"missing {AUTH_STORE}"
        size = os.path.getsize(AUTH_STORE)
        assert size > 200, f"authStore.ts suspiciously small ({size} bytes)"

    def test_module_exports_factory(self):
        """L1: module declares an exported `createAuthStore`."""
        with open(AUTH_STORE) as fh:
            src = fh.read()
        assert re.search(r"export\b.*\bcreateAuthStore\b", src) or re.search(
            r"\bcreateAuthStore\b", src
        ), "createAuthStore not found in authStore.ts"

    def test_agent_test_suite_exists(self):
        """L1: the agent's own Vitest suite file exists and is non-trivial."""
        assert os.path.isfile(AGENT_TEST), f"missing {AGENT_TEST}"
        assert os.path.getsize(AGENT_TEST) > 200

    def test_agent_suite_passes(self):
        """L1/L2: the agent's own `tests/authStore.test.ts` suite passes (>=10)."""
        proc = _run_vitest("tests/authStore.test.ts")
        _assert_passed(proc, "agent authStore.test.ts suite")
        combined = (proc.stdout or "") + (proc.stderr or "")
        m = re.search(r"Tests\s+(\d+)\s+passed", combined)
        if m:
            assert int(m.group(1)) >= 10, (
                f"expected >=10 passing tests, parsed {m.group(1)}\n"
                f"{combined[-2000:]}"
            )

    # ------------------------------------------------------------------ L2
    def test_initial_state_unauthenticated(self):
        """L2: a fresh store starts idle, null user/token, isAuthenticated=false."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createAuthStore }} from '{_IMPORT}'

describe('bench-init', () => {{
  it('starts in a clean unauthenticated state', () => {{
    const store = createAuthStore()
    const s = store.getState()
    expect(s.user).toBeNull()
    expect(s.token).toBeNull()
    expect(s.status).toBe('idle')
    expect(s.errorMessage).toBeNull()
    expect(s.isAuthenticated).toBe(false)
    // standard vanilla handles must be present
    expect(typeof store.getState).toBe('function')
    expect(typeof store.setState).toBe('function')
    expect(typeof store.subscribe).toBe('function')
  }})
}})
"""
        _assert_passed(_run_driver(body), "initial unauthenticated state")

    def test_login_success_path(self):
        """L2: login success sets user/token/status='authenticated' and isAuthenticated."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createAuthStore }} from '{_IMPORT}'

describe('bench-login-success', () => {{
  it('login success populates session and flips isAuthenticated', async () => {{
    const store = createAuthStore()
    const authenticate = async () => ({{
      user: {{ id: 'u1', email: 'a@b.com' }},
      token: 'tok-123',
    }})
    const ret = await store.getState().login(authenticate)
    // login must resolve (not reject)
    const s = store.getState()
    expect(s.status).toBe('authenticated')
    expect(s.errorMessage).toBeNull()
    expect(s.user).not.toBeNull()
    expect((s.user as any).id).toBe('u1')
    expect((s.user as any).email).toBe('a@b.com')
    expect(s.token).toBe('tok-123')
    expect(s.isAuthenticated).toBe(true)
  }})
}})
"""
        _assert_passed(_run_driver(body), "login success")

    def test_login_sets_loading_before_await(self):
        """L2: status becomes 'loading' and errorMessage clears before awaiting."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createAuthStore }} from '{_IMPORT}'

describe('bench-loading', () => {{
  it('enters loading state synchronously before the auth promise resolves', async () => {{
    const store = createAuthStore()
    // seed a stale error so we can prove it is cleared before awaiting
    store.setState({{ status: 'error', errorMessage: 'stale' }} as any)
    let statusDuringAwait: string | undefined
    let errDuringAwait: any = 'sentinel'
    const authenticate = () => new Promise<{{ user: any; token: string }}>((resolve) => {{
      // observe the store state while the auth call is in-flight
      statusDuringAwait = store.getState().status
      errDuringAwait = store.getState().errorMessage
      resolve({{ user: {{ id: 'u2', email: 'c@d.com' }}, token: 'tk' }})
    }})
    await store.getState().login(authenticate)
    expect(statusDuringAwait).toBe('loading')
    expect(errDuringAwait).toBeNull()
    // and it resolves into authenticated
    expect(store.getState().status).toBe('authenticated')
    expect(store.getState().isAuthenticated).toBe(true)
  }})
}})
"""
        _assert_passed(_run_driver(body), "loading before await")

    def test_login_rejection_captured_not_thrown(self):
        """L2: a rejecting authenticate sets error state, keeps session, never throws."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createAuthStore }} from '{_IMPORT}'

describe('bench-login-reject', () => {{
  it('captures async rejection into error state without throwing', async () => {{
    const store = createAuthStore()
    let threw = false
    try {{
      await store.getState().login(async () => {{ throw new Error('bad creds') }})
    }} catch (e) {{
      threw = true
    }}
    expect(threw).toBe(false)
    const s = store.getState()
    expect(s.status).toBe('error')
    expect(typeof s.errorMessage).toBe('string')
    expect((s.errorMessage as string).length).toBeGreaterThan(0)
    // session left unchanged (still logged out)
    expect(s.user).toBeNull()
    expect(s.token).toBeNull()
    expect(s.isAuthenticated).toBe(false)
  }})

  it('rejection leaves a PRIOR authenticated session unchanged', async () => {{
    const store = createAuthStore()
    await store.getState().login(async () => ({{
      user: {{ id: 'u9', email: 'keep@x.com' }}, token: 'keep-tok',
    }}))
    expect(store.getState().isAuthenticated).toBe(true)
    let threw = false
    try {{
      await store.getState().login(async () => {{ throw new Error('second fail') }})
    }} catch (e) {{ threw = true }}
    expect(threw).toBe(false)
    const s = store.getState()
    expect(s.status).toBe('error')
    // unchanged user/token from the first successful login
    expect((s.user as any).id).toBe('u9')
    expect(s.token).toBe('keep-tok')
  }})
}})
"""
        _assert_passed(_run_driver(body), "login rejection captured")

    def test_login_synchronous_throw_captured(self):
        """L2: a synchronous throw inside authenticate is also captured, not propagated."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createAuthStore }} from '{_IMPORT}'

describe('bench-sync-throw', () => {{
  it('synchronous throw is captured into error state', async () => {{
    const store = createAuthStore()
    let threw = false
    try {{
      await store.getState().login(() => {{ throw new Error('sync boom') }})
    }} catch (e) {{
      threw = true
    }}
    expect(threw).toBe(false)
    const s = store.getState()
    expect(s.status).toBe('error')
    expect((s.errorMessage as string).length).toBeGreaterThan(0)
    expect(s.isAuthenticated).toBe(false)
  }})
}})
"""
        _assert_passed(_run_driver(body), "synchronous throw captured")

    def test_invalid_input_guard(self):
        """L2: non-function authenticate -> error state with message, no async work."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createAuthStore }} from '{_IMPORT}'

describe('bench-guard', () => {{
  it('guards a non-function authenticate into error state', async () => {{
    const store = createAuthStore()
    let threw = false
    try {{
      // @ts-expect-error intentionally invalid
      await store.getState().login(42)
    }} catch (e) {{
      threw = true
    }}
    expect(threw).toBe(false)
    const s = store.getState()
    expect(s.status).toBe('error')
    expect(typeof s.errorMessage).toBe('string')
    expect((s.errorMessage as string).length).toBeGreaterThan(0)
    expect(s.user).toBeNull()
    expect(s.token).toBeNull()
    expect(s.isAuthenticated).toBe(false)
  }})
}})
"""
        _assert_passed(_run_driver(body), "invalid input guard")

    def test_logout_clears_session(self):
        """L2: logout resets user/token/status='idle' and isAuthenticated=false."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createAuthStore }} from '{_IMPORT}'

describe('bench-logout', () => {{
  it('logout clears an authenticated session', async () => {{
    const store = createAuthStore()
    await store.getState().login(async () => ({{
      user: {{ id: 'u3', email: 'e@f.com' }}, token: 'zzz',
    }}))
    expect(store.getState().isAuthenticated).toBe(true)
    store.getState().logout()
    const s = store.getState()
    expect(s.user).toBeNull()
    expect(s.token).toBeNull()
    expect(s.status).toBe('idle')
    expect(s.errorMessage).toBeNull()
    expect(s.isAuthenticated).toBe(false)
  }})
}})
"""
        _assert_passed(_run_driver(body), "logout clears session")

    def test_is_authenticated_never_drifts(self):
        """L2: isAuthenticated always equals (user!=null && token!=null) after every action."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createAuthStore }} from '{_IMPORT}'

function check(s: any) {{
  expect(s.isAuthenticated).toBe(s.user !== null && s.token !== null)
}}

describe('bench-derived', () => {{
  it('derived flag matches user/token presence after each action', async () => {{
    const store = createAuthStore()
    check(store.getState())
    // failed login
    await store.getState().login(async () => {{ throw new Error('x') }})
    check(store.getState())
    // successful login
    await store.getState().login(async () => ({{
      user: {{ id: 'u4', email: 'g@h.com' }}, token: 't4',
    }}))
    check(store.getState())
    expect(store.getState().isAuthenticated).toBe(true)
    // logout
    store.getState().logout()
    check(store.getState())
    expect(store.getState().isAuthenticated).toBe(false)
    // login again
    await store.getState().login(async () => ({{
      user: {{ id: 'u5', email: 'i@j.com' }}, token: 't5',
    }}))
    check(store.getState())
  }})
}})
"""
        _assert_passed(_run_driver(body), "isAuthenticated no-drift")

    def test_storage_persist_on_login_and_clear_on_logout(self):
        """L2: successful login writes session to storage; logout removes it."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createAuthStore }} from '{_IMPORT}'
{_STORAGE_HELPER}

describe('bench-persist', () => {{
  it('persists on login and clears on logout', async () => {{
    const storage = makeStorage()
    const store = createAuthStore({{ storage }})
    expect(storage._map.size).toBe(0)
    await store.getState().login(async () => ({{
      user: {{ id: 'u6', email: 'k@l.com' }}, token: 'persist-tok',
    }}))
    // something must have been written
    expect(storage._map.size).toBeGreaterThan(0)
    // the persisted blob must actually contain the user id and token
    const blob = Array.from(storage._map.values()).join('|')
    expect(blob).toContain('u6')
    expect(blob).toContain('persist-tok')
    // logout removes the persisted session
    store.getState().logout()
    expect(storage._map.size).toBe(0)
  }})

  it('does NOT persist a failed login', async () => {{
    const storage = makeStorage()
    const store = createAuthStore({{ storage }})
    await store.getState().login(async () => {{ throw new Error('nope') }})
    expect(storage._map.size).toBe(0)
  }})
}})
"""
        _assert_passed(_run_driver(body), "persist on login / clear on logout")

    def test_rehydrate_from_populated_storage(self):
        """L2: a fresh store given the same populated storage rehydrates the session."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createAuthStore }} from '{_IMPORT}'
{_STORAGE_HELPER}

describe('bench-rehydrate', () => {{
  it('rehydrates an authenticated session from shared storage', async () => {{
    const storage = makeStorage()
    const s1 = createAuthStore({{ storage }})
    await s1.getState().login(async () => ({{
      user: {{ id: 'u7', email: 'm@n.com' }}, token: 'rehy-tok',
    }}))
    expect(storage._map.size).toBeGreaterThan(0)
    // a brand new store with the SAME populated storage restores the session
    const s2 = createAuthStore({{ storage }})
    const st = s2.getState()
    expect(st.user).not.toBeNull()
    expect((st.user as any).id).toBe('u7')
    expect((st.user as any).email).toBe('m@n.com')
    expect(st.token).toBe('rehy-tok')
    expect(st.status).toBe('authenticated')
    expect(st.isAuthenticated).toBe(true)
  }})
}})
"""
        _assert_passed(_run_driver(body), "rehydrate from storage")

    def test_no_storage_mode_no_side_effects(self):
        """L2: without storage the store works normally and login/logout don't throw."""
        body = f"""
import {{ describe, it, expect }} from 'vitest'
import {{ createAuthStore }} from '{_IMPORT}'

describe('bench-nostorage', () => {{
  it('works with no storage option', async () => {{
    const store = createAuthStore()
    let threw = false
    try {{
      await store.getState().login(async () => ({{
        user: {{ id: 'u8', email: 'o@p.com' }}, token: 'nt',
      }}))
      store.getState().logout()
    }} catch (e) {{
      threw = true
    }}
    expect(threw).toBe(false)
    expect(store.getState().status).toBe('idle')
    expect(store.getState().isAuthenticated).toBe(false)
  }})
}})
"""
        _assert_passed(_run_driver(body), "no-storage mode")
