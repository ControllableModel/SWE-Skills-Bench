"""
Test for the 'kysely-query-builder' skill (variant ext10) —
Add a ``concatWs`` helper for PostgreSQL.

The variant task asks the agent to add and export a new ``concatWs`` function
to ``src/helpers/postgres.ts`` that compiles to PostgreSQL's
``concat_ws(<separator>, <value0>, <value1>, ...)`` function, where:

  * ``concatWs(separator: string, values: Expression<unknown>[])`` is the API,
  * the ``separator`` is emitted as the FIRST argument and is ALWAYS a bound
    parameter (``$1`` placeholder collected into the parameter list) — it must
    NOT be inlined as a literal,
  * each value expression is compiled normally AFTER the separator: column
    refs are double-quoted, ``eb.val(...)`` values become subsequent bound
    parameters (``$2``, ``$3``, ... in input order), and raw ``sql`` fragments
    are emitted verbatim,
  * exactly one pair of parentheses; arguments joined by ``, `` with no
    trailing separator.

The agent must also create ``test/node/src/concat-ws-postgres.test.ts``.

Strategy / discriminative power
-------------------------------
L1 checks confirm the deliverable files exist, that ``concatWs`` is exported
from ``src/helpers/postgres.ts``, and that the existing exported helpers
(``jsonArrayFrom``, ``jsonObjectFrom``, ``jsonBuildObject``, ``mergeAction``)
are still present (no regression of the public surface).

L2 checks do NOT trust the agent's own test file. Instead this harness:
  1. builds the kysely library (``pnpm build``) once,
  2. writes its OWN independent TypeScript driver into ``test/node/src/`` that
     imports the freshly-built ``concatWs`` helper, builds a ``Kysely``
     instance with the PostgreSQL adapter/compiler + ``DummyDriver`` (no DB /
     network), calls ``.compile()`` and ``console.log``s the produced ``sql``
     + ``parameters`` as JSON,
  3. compiles the node test sources (``pnpm test:node:build`` — this also
     type-checks the agent's ``concatWs`` signature, since the driver invokes
     it), and runs the driver under ``mocha``,
  4. parses the emitted JSON and asserts on exact SQL strings, exact parameter
     arrays, argument ordering, separator-is-first-bound-parameter, and
     verbatim raw fragments.

A naive solution fails these tests because the real Kysely compiler is
exercised end-to-end:
  * inlining the separator as a literal (e.g. ``concat_ws(' ', ...)``) instead
    of a ``$1`` bound parameter -> separator-binding assertions fail,
  * placing the separator anywhere but first -> ordering assertions fail,
  * using the wrong SQL function name -> function-name assertions fail,
  * inlining ``eb.val(...)`` values, wrong parameter ordering, missing the
    helper, or a non-compiling type signature -> the relevant L2 fails or the
    probe never type-checks/runs.
"""

import json
import os
import re
import subprocess

import pytest


REPO_DIR = "/workspace/kysely"

PG_HELPER = os.path.join(REPO_DIR, "src", "helpers", "postgres.ts")
NEW_TEST_TS = os.path.join(
    REPO_DIR, "test", "node", "src", "concat-ws-postgres.test.ts"
)

# Where this harness drops its own independent driver (NOT the agent's file).
DRIVER_NAME = "zzz-concat-ws-probe"
DRIVER_TS = os.path.join(REPO_DIR, "test", "node", "src", DRIVER_NAME + ".ts")
DRIVER_JS = os.path.join(REPO_DIR, "test", "node", "dist", DRIVER_NAME + ".js")

# Markers used to extract our JSON payloads from the mocha stdout stream.
BEGIN = "@@PROBE_BEGIN@@"
END = "@@PROBE_END@@"


# ---------------------------------------------------------------------------
# Driver test (TypeScript) written into the repo by this harness.
# Uses the PostgreSQL adapter/compiler + DummyDriver pattern from the repo.
# ---------------------------------------------------------------------------
DRIVER_SOURCE = r"""
import {
  DummyDriver,
  Kysely,
  PostgresAdapter,
  PostgresIntrospector,
  PostgresQueryCompiler,
  sql,
} from '../../../dist/index.js'
import { concatWs } from '../../../dist/helpers/postgres.js'

interface DB {
  person: {
    id: number
    first_name: string | null
    last_name: string | null
  }
}

const pgDb = new Kysely<DB>({
  dialect: {
    createAdapter: () => new PostgresAdapter(),
    createDriver: () => new DummyDriver(),
    createIntrospector: (db) => new PostgresIntrospector(db),
    createQueryCompiler: () => new PostgresQueryCompiler(),
  },
})

function emit(label: string, sqlText: string, parameters: readonly unknown[]) {
  console.log('@@PROBE_BEGIN@@' + JSON.stringify({
    label,
    sql: sqlText,
    parameters,
  }) + '@@PROBE_END@@')
}

describe('concat-ws probe', () => {
  it('emits compiled output for every scenario', () => {
    // --- two column refs, separator ' ' ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) =>
          concatWs(' ', [eb.ref('first_name'), eb.ref('last_name')]).as('full'),
        )
        .compile()
      emit('two_refs', c.sql, c.parameters)
    }

    // --- column ref + eb.val, separator '-' ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) => concatWs('-', [eb.ref('a'), eb.val('x')]).as('out'))
        .compile()
      emit('ref_val', c.sql, c.parameters)
    }

    // --- raw sql fragment first + column ref, separator ', ' ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) =>
          concatWs(', ', [sql`upper(first_name)`, eb.ref('last_name')]).as('out'),
        )
        .compile()
      emit('raw_ref', c.sql, c.parameters)
    }

    // --- three column refs (ordering), separator '/' ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) =>
          concatWs('/', [
            eb.ref('first_name'),
            eb.ref('last_name'),
            eb.ref('id'),
          ]).as('triple'),
        )
        .compile()
      emit('three_refs', c.sql, c.parameters)
    }

    // --- multiple eb.val values, parameter ordering, separator '|' ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) =>
          concatWs('|', [eb.val('a'), eb.val('b'), eb.val('c')]).as('vals'),
        )
        .compile()
      emit('multi_val', c.sql, c.parameters)
    }

    // --- single value (still a separator + one arg) ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) => concatWs('X', [eb.ref('first_name')]).as('one'))
        .compile()
      emit('single', c.sql, c.parameters)
    }
  })
})
"""


# ---------------------------------------------------------------------------
# Module-scoped fixture: build lib + node tests once, run the probe, capture.
# ---------------------------------------------------------------------------
_PROBE_CACHE = {}


def _run(cmd, timeout, cwd=REPO_DIR):
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=True,
    )


@pytest.fixture(scope="module")
def probe():
    """Build the lib, compile + run the harness's own driver, return parsed results."""
    if _PROBE_CACHE:
        return _PROBE_CACHE

    assert os.path.isdir(REPO_DIR), f"repo dir missing: {REPO_DIR}"

    # 1. install deps only if they are missing. In the benchmark container the
    #    repo toolchain is already installed; if so we skip the (network-bound)
    #    install entirely. We never hard-fail on install output — the build step
    #    below is the real gate.
    if not os.path.isdir(os.path.join(REPO_DIR, "node_modules", ".bin")):
        try:
            _run("pnpm install --prefer-offline", timeout=600)
        except subprocess.TimeoutExpired:
            pass

    # 2. build the library (produces dist/, dist/helpers/*.js)
    build = _run("pnpm build", timeout=600)
    assert build.returncode == 0, (
        "pnpm build failed:\nSTDOUT:\n"
        + build.stdout[-4000:]
        + "\nSTDERR:\n"
        + build.stderr[-4000:]
    )
    assert os.path.isfile(
        os.path.join(REPO_DIR, "dist", "helpers", "postgres.js")
    ), "dist/helpers/postgres.js not produced by build"

    # 3. drop our independent driver into the node test sources.
    with open(DRIVER_TS, "w") as f:
        f.write(DRIVER_SOURCE)

    try:
        # 4. compile the node test sources (this also type-checks the agent's
        #    new concatWs signature, since our driver invokes it).
        tsb = _run("pnpm test:node:build", timeout=600)
        assert tsb.returncode == 0, (
            "pnpm test:node:build (tsc) failed — the concatWs helper does "
            "not type-check:\nSTDOUT:\n"
            + tsb.stdout[-4000:]
            + "\nSTDERR:\n"
            + tsb.stderr[-4000:]
        )
        assert os.path.isfile(DRIVER_JS), "compiled probe driver missing"

        # 5. run only our driver under mocha.
        run = _run(
            "npx mocha --timeout 15000 " + DRIVER_JS,
            timeout=300,
        )
        out = run.stdout + "\n" + run.stderr
        assert run.returncode == 0, (
            "probe driver failed under mocha:\n" + out[-6000:]
        )
    finally:
        # tidy up our injected files so we don't pollute the repo.
        for p in (DRIVER_TS, DRIVER_JS):
            try:
                os.remove(p)
            except OSError:
                pass

    results = {}
    for m in re.finditer(re.escape(BEGIN) + r"(.*?)" + re.escape(END), out, re.S):
        payload = json.loads(m.group(1))
        results[payload["label"]] = payload

    assert results, "no probe output captured from mocha run:\n" + out[-4000:]
    _PROBE_CACHE.update(results)
    return _PROBE_CACHE


class TestKyselyQueryBuilder:
    """concatWs helper for the PostgreSQL dialect (variant ext10)."""

    REPO_DIR = "/workspace/kysely"

    # ------------------------------------------------------------------
    # L1 — deliverable files exist, symbol exported, no public regression
    # ------------------------------------------------------------------

    def test_postgres_helper_file_exists(self):
        """src/helpers/postgres.ts must exist."""
        assert os.path.isfile(PG_HELPER), f"missing {PG_HELPER}"

    def test_postgres_exports_concat_ws(self):
        """postgres.ts must declare an exported `concatWs` function."""
        with open(PG_HELPER) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+concatWs\b", src
        ), "no `export function concatWs` in src/helpers/postgres.ts"

    def test_existing_helpers_not_removed(self):
        """The pre-existing exported helpers must still be present (no regression)."""
        with open(PG_HELPER) as f:
            src = f.read()
        for name in (
            "jsonArrayFrom",
            "jsonObjectFrom",
            "jsonBuildObject",
            "mergeAction",
        ):
            assert re.search(
                r"export\s+function\s+" + re.escape(name) + r"\b", src
            ), f"existing exported helper `{name}` was removed/altered"

    def test_new_node_test_file_exists(self):
        """The required new node test file must be created by the agent."""
        assert os.path.isfile(
            NEW_TEST_TS
        ), "test/node/src/concat-ws-postgres.test.ts was not created"

    # ------------------------------------------------------------------
    # L2 — dynamic compilation behavior (via the harness's own driver)
    # ------------------------------------------------------------------

    def test_two_column_refs_sql(self, probe):
        """Two column refs compile to concat_ws with separator as $1, idents quoted."""
        r = probe["two_refs"]
        assert (
            r["sql"]
            == 'select concat_ws($1, "first_name", "last_name") as "full" from "person"'
        ), f"unexpected sql: {r['sql']!r}"
        assert r["parameters"] == [" "], f"expected [' '] params, got {r['parameters']!r}"

    def test_separator_is_first_bound_parameter(self, probe):
        """The separator must ALWAYS be the first bound parameter, never inlined."""
        r = probe["two_refs"]
        # $1 must immediately follow the opening paren (separator is first arg).
        assert re.search(
            r"concat_ws\(\s*\$1\s*,", r["sql"]
        ), f"separator is not the first bound arg ($1): {r['sql']!r}"
        # separator value collected as a parameter, in first position.
        assert r["parameters"][:1] == [" "], f"separator not bound first: {r['parameters']!r}"
        # the literal separator must NOT be inlined into the SQL text.
        assert "' '" not in r["sql"], f"separator was inlined as a literal: {r['sql']!r}"

    def test_uses_correct_function_name(self, probe):
        """Must use concat_ws (not concat / json_build_array / concat_ws spelled wrong)."""
        s = probe["two_refs"]["sql"]
        assert "concat_ws(" in s, f"missing concat_ws(): {s!r}"
        # `concat(` must not appear other than as part of `concat_ws(`.
        assert (
            re.search(r"(?<![_a-z])concat\(", s) is None
        ), f"must use concat_ws, not plain concat(): {s!r}"
        assert s.count("concat_ws(") == 1, f"expected exactly one call: {s!r}"

    def test_ref_plus_val_parameter_ordering(self, probe):
        """ref + eb.val('x'): separator is $1, the value is $2, ref stays quoted."""
        r = probe["ref_val"]
        assert (
            r["sql"]
            == 'select concat_ws($1, "a", $2) as "out" from "person"'
        ), f"unexpected sql: {r['sql']!r}"
        # separator '-' first, value 'x' second, in that exact order.
        assert r["parameters"] == ["-", "x"], f"bad params: {r['parameters']!r}"
        # neither value inlined as literal.
        assert "'-'" not in r["sql"] and "'x'" not in r["sql"], (
            f"a value was inlined: {r['sql']!r}"
        )

    def test_raw_fragment_verbatim(self, probe):
        """A raw sql`upper(first_name)` fragment is emitted verbatim as the first value."""
        r = probe["raw_ref"]
        assert (
            r["sql"]
            == 'select concat_ws($1, upper(first_name), "last_name") as "out" from "person"'
        ), f"unexpected sql: {r['sql']!r}"
        # only the separator is a bound parameter; the raw fragment is not.
        assert r["parameters"] == [", "], f"expected [', '] params, got {r['parameters']!r}"
        assert "upper(first_name)" in r["sql"], "raw fragment not emitted verbatim"

    def test_three_refs_order_and_separators(self, probe):
        """3 value refs joined in input order after the separator, single paren pair."""
        r = probe["three_refs"]
        assert (
            r["sql"]
            == 'select concat_ws($1, "first_name", "last_name", "id") as "triple" from "person"'
        ), f"unexpected sql: {r['sql']!r}"
        inner = re.search(r"concat_ws\((.*?)\) as", r["sql"]).group(1)
        assert inner == '$1, "first_name", "last_name", "id"', f"bad arg list: {inner!r}"
        assert r["parameters"] == ["/"], f"expected ['/'] params, got {r['parameters']!r}"

    def test_multi_val_parameter_ordering(self, probe):
        """Multiple eb.val values: separator $1 then $2,$3,$4 with params in order."""
        r = probe["multi_val"]
        assert (
            r["sql"]
            == 'select concat_ws($1, $2, $3, $4) as "vals" from "person"'
        ), f"unexpected sql: {r['sql']!r}"
        # separator first, then a, b, c in input order.
        assert r["parameters"] == ["|", "a", "b", "c"], f"bad params: {r['parameters']!r}"

    def test_single_value_still_has_separator_first(self, probe):
        """A single value: still concat_ws(<sep $1>, <value>) — separator stays first."""
        r = probe["single"]
        assert (
            r["sql"]
            == 'select concat_ws($1, "first_name") as "one" from "person"'
        ), f"unexpected sql: {r['sql']!r}"
        assert r["parameters"] == ["X"], f"expected ['X'] params, got {r['parameters']!r}"

    def test_no_trailing_separator_and_balanced_parens(self, probe):
        """No trailing `, ` and a balanced paren count across scenarios."""
        for label in ("two_refs", "ref_val", "raw_ref", "three_refs", "multi_val"):
            s = probe[label]["sql"]
            assert ", )" not in s, f"trailing separator in {label}: {s!r}"
            assert s.count("(") == s.count(")"), f"unbalanced parens in {label}: {s!r}"

    def test_separator_never_inlined_across_scenarios(self, probe):
        """For every scenario the string separator must be bound, never inlined."""
        expected_sep = {
            "two_refs": " ",
            "ref_val": "-",
            "raw_ref": ", ",
            "three_refs": "/",
            "multi_val": "|",
            "single": "X",
        }
        for label, sep in expected_sep.items():
            r = probe[label]
            # separator is the first collected parameter.
            assert r["parameters"][0] == sep, (
                f"{label}: separator {sep!r} not first param, got {r['parameters']!r}"
            )
            # the SQL begins the call with the $1 placeholder, not a literal sep.
            assert re.search(r"concat_ws\(\s*\$1\s*,", r["sql"]), (
                f"{label}: separator not bound as $1: {r['sql']!r}"
            )
