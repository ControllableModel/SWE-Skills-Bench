"""
Test for the 'kysely-query-builder' skill (variant ext8) —
Add an ``arrayToString`` helper for PostgreSQL.

Verifies that the agent added a new ``arrayToString`` two-argument helper to the
PostgreSQL helper module (``src/helpers/postgres.ts``) such that:

  * it takes ``(array: Expression<unknown>, delimiter: string)`` and returns a
    ``RawBuilder<string>`` aliasable with ``.as(...)`` inside ``select(...)``;
  * it compiles to PostgreSQL's ``array_to_string(<array>, <delimiter>)``;
  * the ``array`` argument flows through Kysely's normal expression compilation:
      - a column reference is double-quoted (``"tags"``),
      - an ``eb.val(...)`` array value becomes a bound ``$N`` placeholder
        collected into the parameters list (NOT inlined),
      - a raw ``sql`` fragment is emitted verbatim;
  * the ``delimiter`` argument is ALWAYS emitted as a single bound parameter
    (placeholder collected into the parameters list) and is NEVER inlined into
    the SQL text as a string literal;
  * exactly one pair of parentheses with the two args separated by ``, ``.

Strategy / discriminative power
-------------------------------
L1 checks confirm the deliverable files exist and export the symbol, and that
the existing helpers are still exported (no regressions to the public API).

L2 checks do NOT trust the agent's own test file. Instead this harness:
  1. builds the kysely library (``pnpm build``) once,
  2. writes its OWN TypeScript driver test into ``test/node/src/`` that imports
     the freshly-built ``arrayToString`` helper, builds a ``Kysely`` instance
     using the PostgreSQL adapter + query compiler with ``DummyDriver``
     (no DB / network), calls ``.compile()`` and ``console.log``s the produced
     ``sql`` + ``parameters`` as JSON,
  3. compiles the node test sources (``pnpm test:node:build``) — this also
     type-checks the agent's ``arrayToString`` signature, since our driver
     invokes it and aliases its result,
  4. runs the driver under mocha and parses the emitted JSON,
  5. asserts on exact SQL strings, exact parameter arrays, argument ordering,
     verbatim raw fragments, and that the delimiter is bound rather than inlined.

A naive solution fails these tests because the real Kysely compiler is exercised
end-to-end. In particular, an implementation that:
  * inlines the delimiter as a literal (``'-'`` in the SQL text instead of ``$N``),
  * uses the wrong function name (e.g. ``string_to_array`` / ``array_agg``),
  * fails to bind an ``eb.val(...)`` array as a parameter,
  * drops or reorders an argument, or
  * does not type-check as ``RawBuilder<string>``
will be caught.
"""

import json
import os
import re
import subprocess

import pytest


REPO_DIR = "/workspace/kysely"

PG_HELPER = os.path.join(REPO_DIR, "src", "helpers", "postgres.ts")
NEW_TEST_TS = os.path.join(
    REPO_DIR, "test", "node", "src", "array-to-string-postgres.test.ts"
)

# Where this harness drops its own independent driver (NOT the agent's file).
DRIVER_NAME = "zzz-array-to-string-probe"
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
import { arrayToString } from '../../../dist/helpers/postgres.js'

interface DB {
  person: {
    id: number
    tags: string[]
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

describe('array-to-string probe', () => {
  it('emits compiled output for every scenario', () => {
    // --- column-ref array + string delimiter ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) => arrayToString(eb.ref('tags'), ', ').as('csv'))
        .compile()
      emit('ref', c.sql, c.parameters)
    }

    // --- eb.val(array) + string delimiter (both bound, in order) ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) => arrayToString(eb.val(['a', 'b']), '-').as('joined'))
        .compile()
      emit('val', c.sql, c.parameters)
    }

    // --- raw sql fragment array + string delimiter ---
    {
      const c = pgDb
        .selectFrom('person')
        .select(() => arrayToString(sql`array['a','b']`, ', ').as('raw'))
        .compile()
      emit('raw', c.sql, c.parameters)
    }

    // --- column-ref array with a different delimiter (delimiter is bound, not inlined) ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) => arrayToString(eb.ref('tags'), '|').as('piped'))
        .compile()
      emit('pipe', c.sql, c.parameters)
    }

    // --- result type must be string: assignable to a string-typed select alias ---
    // (compilation of this block is itself the type assertion; if arrayToString
    //  were `any` or non-string this still compiles, so we additionally use the
    //  value in a string-only context below.)
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) => arrayToString(eb.ref('tags'), ',').as('s'))
        .compile()
      emit('type', c.sql, c.parameters)
    }
  })
})
"""


# ---------------------------------------------------------------------------
# Module-scoped fixture: build lib + node tests once, run the probe, capture.
# ---------------------------------------------------------------------------
_PROBE_CACHE = {}


def _run(cmd, timeout, cwd=REPO_DIR):
    env = dict(os.environ)
    env.setdefault("CI", "true")
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=True,
        env=env,
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
        #    new arrayToString signature, since our driver invokes it).
        tsb = _run("pnpm test:node:build", timeout=600)
        assert tsb.returncode == 0, (
            "pnpm test:node:build (tsc) failed — the arrayToString helper does "
            "not type-check (wrong signature / not exported / not RawBuilder<string>):"
            "\nSTDOUT:\n"
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
    """arrayToString helper for the PostgreSQL dialect."""

    REPO_DIR = "/workspace/kysely"

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and export the symbol
    # ------------------------------------------------------------------

    def test_postgres_helper_file_exists(self):
        """src/helpers/postgres.ts must exist."""
        assert os.path.isfile(PG_HELPER), f"missing {PG_HELPER}"

    def test_postgres_exports_array_to_string(self):
        """postgres.ts must declare an exported `arrayToString` function."""
        with open(PG_HELPER) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+arrayToString\b", src
        ), "no `export function arrayToString` in src/helpers/postgres.ts"

    def test_array_to_string_takes_two_args(self):
        """The exported arrayToString must declare two parameters (array, delimiter)."""
        with open(PG_HELPER) as f:
            src = f.read()
        m = re.search(
            r"export\s+function\s+arrayToString\s*(<[^>]*>)?\s*\((.*?)\)\s*:",
            src,
            re.S,
        )
        assert m, "could not parse arrayToString parameter list"
        params = m.group(2)
        # two comma-separated params (ignore commas inside generic <...> which we
        # already excluded from the param-list capture).
        assert params.count(",") >= 1, f"arrayToString must take 2 args, got: {params!r}"
        # the second argument must be a plain string delimiter, not an expression.
        assert "string" in params, (
            "the delimiter argument must be typed `string`: " + repr(params)
        )

    def test_existing_helpers_still_exported(self):
        """No regression: the pre-existing helpers must remain exported."""
        with open(PG_HELPER) as f:
            src = f.read()
        for name in (
            "jsonArrayFrom",
            "jsonObjectFrom",
            "jsonBuildObject",
            "mergeAction",
        ):
            assert re.search(
                r"export\s+function\s+" + name + r"\b", src
            ), f"existing helper `{name}` is no longer exported"

    def test_new_node_test_file_exists(self):
        """The required new node test file must be created by the agent."""
        assert os.path.isfile(
            NEW_TEST_TS
        ), "test/node/src/array-to-string-postgres.test.ts was not created"

    # ------------------------------------------------------------------
    # L2 — dynamic compilation behavior (via the harness's own driver)
    # ------------------------------------------------------------------

    def test_column_ref_array_with_string_delimiter(self, probe):
        """A column-ref array + ', ' delimiter compiles to array_to_string("tags", $1)
        with the delimiter bound as the single parameter [', ']."""
        r = probe["ref"]
        assert (
            r["sql"]
            == 'select array_to_string("tags", $1) as "csv" from "person"'
        ), f"unexpected ref sql: {r['sql']!r}"
        assert r["parameters"] == [", "], f"expected [', '] params, got {r['parameters']!r}"

    def test_uses_correct_function_name(self, probe):
        """Must use array_to_string( — not string_to_array / array_agg / array_join."""
        s = probe["ref"]["sql"]
        assert "array_to_string(" in s, f"missing array_to_string(): {s!r}"
        assert "string_to_array(" not in s, f"must not use string_to_array(): {s!r}"
        assert "array_agg(" not in s, f"must not use array_agg(): {s!r}"

    def test_delimiter_is_bound_not_inlined_ref(self, probe):
        """The delimiter for the column-ref case must be a placeholder, never an inlined literal."""
        r = probe["ref"]
        assert "$1" in r["sql"], f"delimiter not bound as placeholder: {r['sql']!r}"
        assert "', '" not in r["sql"], f"delimiter was inlined: {r['sql']!r}"
        assert "', '" not in r["sql"].replace('","', ""), "delimiter inlined"
        assert r["parameters"] == [", "]

    def test_val_array_and_delimiter_both_bound_in_order(self, probe):
        """eb.val(['a','b']) + '-' : both the array value and the delimiter are bound,
        in argument order, and neither is inlined in the SQL text."""
        r = probe["val"]
        assert (
            r["sql"]
            == 'select array_to_string($1, $2) as "joined" from "person"'
        ), f"unexpected val sql: {r['sql']!r}"
        # array value first ($1), delimiter second ($2), in argument order.
        assert r["parameters"] == [["a", "b"], "-"], (
            f"expected [['a','b'], '-'] params in order, got {r['parameters']!r}"
        )
        # neither argument inlined in the SQL text.
        assert "'-'" not in r["sql"], f"delimiter inlined: {r['sql']!r}"
        assert "array[" not in r["sql"].lower(), f"array value inlined: {r['sql']!r}"

    def test_raw_sql_fragment_emitted_verbatim(self, probe):
        """A raw sql`array['a','b']` fragment is emitted verbatim as arg 1; the
        delimiter is bound as the single parameter [', ']."""
        r = probe["raw"]
        assert (
            r["sql"]
            == "select array_to_string(array['a','b'], $1) as \"raw\" from \"person\""
        ), f"unexpected raw sql: {r['sql']!r}"
        assert r["parameters"] == [", "], (
            f"expected only the bound delimiter [', '], got {r['parameters']!r}"
        )

    def test_different_delimiter_value_flows_through(self, probe):
        """A different delimiter ('|') must appear (only) in the parameter list,
        proving the delimiter is not hardcoded and is bound rather than inlined."""
        r = probe["pipe"]
        assert (
            r["sql"]
            == 'select array_to_string("tags", $1) as "piped" from "person"'
        ), f"unexpected pipe sql: {r['sql']!r}"
        assert r["parameters"] == ["|"], f"expected ['|'] params, got {r['parameters']!r}"
        assert "'|'" not in r["sql"], f"delimiter inlined: {r['sql']!r}"

    def test_exactly_two_args_single_paren_pair(self, probe):
        """array_to_string must wrap exactly two args in one pair of parentheses,
        separated by ', ' — no trailing separator, balanced parens."""
        s = probe["ref"]["sql"]
        assert s.count("array_to_string(") == 1, f"expected one call: {s!r}"
        inner = re.search(r"array_to_string\((.*?)\) as", s).group(1)
        # exactly two arguments: the quoted column ref and the placeholder.
        assert inner == '"tags", $1', f"bad arg list: {inner!r}"
        assert ", )" not in s, f"trailing separator: {s!r}"
        assert s.count("(") == s.count(")"), f"unbalanced parens: {s!r}"

    def test_does_not_collapse_to_single_arg(self, probe):
        """Discriminative: a stub that ignores the delimiter (single-arg call) must fail.
        The compiled SQL must contain a comma-separated two-argument call."""
        s = probe["ref"]["sql"]
        inner = re.search(r"array_to_string\((.*?)\) as", s).group(1)
        assert "," in inner, (
            "array_to_string call must have two comma-separated args (delimiter "
            f"must not be dropped): {inner!r}"
        )
        # the delimiter must be present as a bound parameter, not absent.
        assert probe["ref"]["parameters"], "delimiter parameter was dropped"

    def test_type_scenario_compiles_and_runs(self, probe):
        """The string-typed alias scenario must compile (type-checked at tsc time)
        and produce a well-formed two-arg array_to_string call at runtime."""
        r = probe["type"]
        assert (
            r["sql"]
            == 'select array_to_string("tags", $1) as "s" from "person"'
        ), f"unexpected type-scenario sql: {r['sql']!r}"
        assert r["parameters"] == [","], f"unexpected params: {r['parameters']!r}"
