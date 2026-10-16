"""
Test for 'tanstack-query-patterns' skill — Query-Key Relationship Utility.

Verifies the agent added a pure `relateKeys(a, b): KeyRelation` utility to
`@tanstack/query-core` (packages/query-core/src/keyRelation.ts), re-exported it
from the package entry point, and that the relation semantics match the
requirement doc exactly (exact / ancestor / descendant / disjoint), including
structural plain-object partial matching, property-order-independent
equivalence, empty-key edge cases, the ancestor<->descendant inverse property,
and argument-purity.

Strategy: rather than trusting the agent's own test file, this suite writes its
own vitest probe spec into packages/query-core/src/__tests__/ and runs it with
the repo's native vitest (the SAME command family the Acceptance Criteria
specifies). The probe imports `relateKeys` / `KeyRelation` from the package
index (`..`) and asserts concrete behavior, so a stub / hardcoded / mislabeled
implementation fails. It also cross-checks consistency with the package's own
`partialMatchKey` / `hashKey` primitives.
"""

import json
import os
import subprocess

import pytest


REPO_DIR = "/workspace/query"
CORE_DIR = os.path.join(REPO_DIR, "packages", "query-core")
SRC_DIR = os.path.join(CORE_DIR, "src")
TESTS_SUBDIR = os.path.join(SRC_DIR, "__tests__")

# Probe specs we inject live under src/__tests__ so the package's vitest
# config (test.dir === './src') picks them up. Distinct name to avoid clobber.
PROBE_BASENAME = "zzKeyRelationProbe.gen.test.tsx"
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


def _run_vitest_on_probe(probe_source, marker):
    """Write `probe_source` into src/__tests__, run native vitest on just that
    file, and return the CompletedProcess. The probe MUST print `marker` on its
    own (after a passing run) so we can distinguish a clean pass from a vitest
    crash / no-tests-collected situation."""
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


class TestTanstackQueryPatterns:
    """Verify the relateKeys query-key relationship utility."""

    REPO_DIR = "/workspace/query"

    # ------------------------------------------------------------------
    # L1: deliverable files exist and are minimally well-formed.
    # ------------------------------------------------------------------

    def test_keyrelation_source_file_exists(self):
        """packages/query-core/src/keyRelation.ts must exist and be non-trivial."""
        path = os.path.join(SRC_DIR, "keyRelation.ts")
        assert os.path.isfile(path), "keyRelation.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "relateKeys" in content, "relateKeys not defined in keyRelation.ts"
        assert len(content.strip()) > 80, "keyRelation.ts looks empty/stub"

    def test_index_reexports_relatekeys(self):
        """index.ts must re-export relateKeys and the KeyRelation type."""
        path = os.path.join(SRC_DIR, "index.ts")
        assert os.path.isfile(path), "index.ts not found"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "relateKeys" in content, "index.ts does not re-export relateKeys"
        assert "KeyRelation" in content, "index.ts does not re-export KeyRelation"

    def test_agent_test_suite_exists(self):
        """The required vitest suite file must exist."""
        path = os.path.join(TESTS_SUBDIR, "keyRelation.test.tsx")
        assert os.path.isfile(path), "keyRelation.test.tsx not found"

    # ------------------------------------------------------------------
    # L2: dynamic execution via the repo's native vitest toolchain.
    # Each method injects its own focused probe importing relateKeys from
    # the package index, so the agent's own test file is not trusted.
    # ------------------------------------------------------------------

    def test_basic_relation_scenarios(self):
        """All eleven documented Expected-Functionality scenarios resolve to the
        exact relation string the requirement specifies."""
        cases = [
            (["todos"], ["todos"], "exact"),
            (["todos"], ["todos", 5], "ancestor"),
            (["todos", 5], ["todos"], "descendant"),
            (["todos", 5], ["users", 5], "disjoint"),
            (["todos", 5], ["todos", 6], "disjoint"),
            ([], ["anything"], "ancestor"),
            ([], [], "exact"),
        ]
        body = "\n".join(
            f"  expect(relateKeys({json.dumps(a)}, {json.dumps(b)})).toBe({json.dumps(rel)})"
            for a, b, rel in cases
        )
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { relateKeys } from '..'\n"
            "describe('relateKeys basic', () => {\n"
            "  it('matches documented scenarios', () => {\n"
            f"{body}\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe, "basic")
        _assert_vitest_passed(result, combined)

    def test_structural_plain_object_partial_match(self):
        """Plain-object elements are compared structurally: a filter object whose
        every property matches a superset candidate object is an ancestor."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { relateKeys } from '..'\n"
            "describe('relateKeys structural', () => {\n"
            "  it('partial-matches object elements', () => {\n"
            "    expect(relateKeys(['todos', { status: 'done' }], ['todos', { status: 'done', page: 2 }])).toBe('ancestor')\n"
            "    expect(relateKeys(['todos', { status: 'done', page: 2 }], ['todos', { status: 'done' }])).toBe('descendant')\n"
            "    expect(relateKeys(['todos', { status: 'done' }], ['todos', { status: 'open' }])).toBe('disjoint')\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe, "structural")
        _assert_vitest_passed(result, combined)

    def test_property_order_independent_equivalence(self):
        """Object property ordering MUST NOT affect equivalence -> 'exact'."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { relateKeys } from '..'\n"
            "describe('relateKeys order', () => {\n"
            "  it('is property-order independent', () => {\n"
            "    expect(relateKeys(['t', { a: 1, b: 2 }], ['t', { b: 2, a: 1 }])).toBe('exact')\n"
            "    expect(relateKeys(['t', { b: 2, a: 1 }], ['t', { a: 1, b: 2 }])).toBe('exact')\n"
            "    // nested objects too\n"
            "    expect(relateKeys(['t', { x: { p: 1, q: 2 } }], ['t', { x: { q: 2, p: 1 } }])).toBe('exact')\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe, "order")
        _assert_vitest_passed(result, combined)

    def test_nested_array_elements(self):
        """Array nesting is supported the same partial-match way."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { relateKeys } from '..'\n"
            "describe('relateKeys nested arrays', () => {\n"
            "  it('compares array elements element-wise', () => {\n"
            "    // exact: identical nested array element\n"
            "    expect(relateKeys(['t', [1, 2]], ['t', [1, 2]])).toBe('exact')\n"
            "    // differing nested array element of same length -> disjoint\n"
            "    expect(relateKeys(['t', [1, 2]], ['t', [1, 3]])).toBe('disjoint')\n"
            "    // longer key with same prefix -> ancestor\n"
            "    expect(relateKeys(['t', [1, 2]], ['t', [1, 2], 'x'])).toBe('ancestor')\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe, "nested")
        _assert_vitest_passed(result, combined)

    def test_equal_length_nonequivalent_is_disjoint(self):
        """Two equal-length keys that are not equivalent are 'disjoint' (a strict
        prefix relationship is impossible at equal length), and a shared-length
        element difference is disjoint even with a matching leading element."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { relateKeys } from '..'\n"
            "describe('relateKeys equal-length', () => {\n"
            "  it('equal length non-equivalent is disjoint', () => {\n"
            "    expect(relateKeys(['a', 1], ['a', 2])).toBe('disjoint')\n"
            "    expect(relateKeys(['a', 1], ['b', 1])).toBe('disjoint')\n"
            "    expect(relateKeys(['x'], ['y'])).toBe('disjoint')\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe, "equal-length")
        _assert_vitest_passed(result, combined)

    def test_exact_never_misclassified_as_ancestor_or_descendant(self):
        """Equivalent keys MUST return 'exact', never 'ancestor'/'descendant',
        even for multi-element keys and the empty-key pair."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { relateKeys } from '..'\n"
            "describe('relateKeys exact precedence', () => {\n"
            "  it('prefers exact for equivalent keys', () => {\n"
            "    for (const k of [[], ['todos'], ['todos', 5, 'comments'], ['t', { a: 1 }]]) {\n"
            "      expect(relateKeys(k, k)).toBe('exact')\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe, "exact-precedence")
        _assert_vitest_passed(result, combined)

    def test_ancestor_descendant_inverse_property(self):
        """For randomized/representative key pairs, relateKeys(a,b)==='ancestor'
        iff relateKeys(b,a)==='descendant', and exact/disjoint are symmetric."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { relateKeys } from '..'\n"
            "const keys = [\n"
            "  [], ['todos'], ['todos', 5], ['todos', 5, 'comments'],\n"
            "  ['users', 5], ['todos', 6], ['t', { a: 1, b: 2 }],\n"
            "  ['t', { a: 1 }], ['t', { a: 1, b: 2, c: 3 }], ['a', 1], ['a', 2],\n"
            "]\n"
            "describe('relateKeys inverse', () => {\n"
            "  it('ancestor <-> descendant; exact/disjoint symmetric', () => {\n"
            "    for (const a of keys) {\n"
            "      for (const b of keys) {\n"
            "        const ab = relateKeys(a, b)\n"
            "        const ba = relateKeys(b, a)\n"
            "        if (ab === 'ancestor') expect(ba).toBe('descendant')\n"
            "        else if (ab === 'descendant') expect(ba).toBe('ancestor')\n"
            "        else expect(ba).toBe(ab)\n"
            "      }\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe, "inverse")
        _assert_vitest_passed(result, combined)

    def test_empty_key_is_ancestor_of_every_nonempty(self):
        """[] is an ancestor of every non-empty key, and the reverse is a
        descendant; relateKeys([], []) is exact."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { relateKeys } from '..'\n"
            "const nonEmpty = [['a'], ['a', 1], ['todos', { x: 1 }], [0], [false]]\n"
            "describe('relateKeys empty', () => {\n"
            "  it('empty key relations', () => {\n"
            "    expect(relateKeys([], [])).toBe('exact')\n"
            "    for (const k of nonEmpty) {\n"
            "      expect(relateKeys([], k)).toBe('ancestor')\n"
            "      expect(relateKeys(k, [])).toBe('descendant')\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe, "empty")
        _assert_vitest_passed(result, combined)

    def test_purity_no_mutation(self):
        """relateKeys MUST NOT mutate either argument (deep snapshot via stable
        stringify before/after)."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { relateKeys } from '..'\n"
            "describe('relateKeys purity', () => {\n"
            "  it('does not mutate arguments', () => {\n"
            "    const a = ['todos', { status: 'done', meta: { p: 1 } }]\n"
            "    const b = ['todos', { status: 'done', meta: { p: 1 }, page: 2 }]\n"
            "    const sa = JSON.stringify(a)\n"
            "    const sb = JSON.stringify(b)\n"
            "    relateKeys(a, b)\n"
            "    relateKeys(b, a)\n"
            "    expect(JSON.stringify(a)).toBe(sa)\n"
            "    expect(JSON.stringify(b)).toBe(sb)\n"
            "    expect(a.length).toBe(2)\n"
            "    expect(b.length).toBe(2)\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe, "purity")
        _assert_vitest_passed(result, combined)

    def test_consistency_with_package_primitives(self):
        """relateKeys MUST reuse the package's existing comparison semantics:
        its verdicts must agree with hashKey (for 'exact') and partialMatchKey
        (for containment direction) across a representative key grid, rather than
        a divergent comparison."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { relateKeys } from '..'\n"
            "import { hashKey, partialMatchKey } from '../utils'\n"
            "const keys = [\n"
            "  [], ['todos'], ['todos', 5], ['todos', 5, 'comments'],\n"
            "  ['users', 5], ['todos', 6],\n"
            "  ['todos', { status: 'done' }], ['todos', { status: 'done', page: 2 }],\n"
            "  ['todos', { status: 'open' }], ['t', { a: 1, b: 2 }], ['t', { b: 2, a: 1 }],\n"
            "  ['a', 1], ['a', 2],\n"
            "]\n"
            "describe('relateKeys consistency', () => {\n"
            "  it('agrees with hashKey and partialMatchKey', () => {\n"
            "    for (const a of keys) {\n"
            "      for (const b of keys) {\n"
            "        const rel = relateKeys(a, b)\n"
            "        const eq = hashKey(a) === hashKey(b)\n"
            "        // a contains b (a is broader filter): partialMatchKey(candidate=b, filter=a)\n"
            "        const aContainsB = partialMatchKey(b, a)\n"
            "        const bContainsA = partialMatchKey(a, b)\n"
            "        if (eq) {\n"
            "          expect(rel).toBe('exact')\n"
            "        } else if (aContainsB) {\n"
            "          expect(rel).toBe('ancestor')\n"
            "        } else if (bContainsA) {\n"
            "          expect(rel).toBe('descendant')\n"
            "        } else {\n"
            "          expect(rel).toBe('disjoint')\n"
            "        }\n"
            "      }\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe, "consistency")
        _assert_vitest_passed(result, combined)

    def test_return_value_is_one_of_four_literals(self):
        """Over a broad key grid the function only ever returns one of the four
        documented literal relation strings."""
        probe = (
            "import { describe, expect, it } from 'vitest'\n"
            "import { relateKeys } from '..'\n"
            "const allowed = new Set(['exact', 'ancestor', 'descendant', 'disjoint'])\n"
            "const keys = [\n"
            "  [], ['x'], ['x', 1], ['x', 1, 2], ['y'], [{ a: 1 }], [{ a: 1, b: 2 }],\n"
            "  ['x', { a: 1 }], ['x', [1, 2]], [null], [undefined], [0],\n"
            "]\n"
            "describe('relateKeys domain', () => {\n"
            "  it('only returns the four literals', () => {\n"
            "    for (const a of keys) {\n"
            "      for (const b of keys) {\n"
            "        expect(allowed.has(relateKeys(a, b))).toBe(true)\n"
            "      }\n"
            "    }\n"
            "  })\n"
            "})\n"
        )
        result, combined = _run_vitest_on_probe(probe, "domain")
        _assert_vitest_passed(result, combined)
