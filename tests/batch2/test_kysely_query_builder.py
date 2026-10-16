"""
Test for the 'kysely-query-builder' skill (variant ext2) —
Add ``jsonBuildArray`` positional helpers for the MySQL and MSSQL dialects.

This variant is DISTINCT from ext1 (which targeted PostgreSQL + SQLite).
Here the agent must add a new ``jsonBuildArray`` helper to BOTH the
MySQL (``src/helpers/mysql.ts``) and MS SQL Server (``src/helpers/mssql.ts``)
helper modules, such that BOTH dialects compile a positional list of
expressions to the native ``json_array(...)`` function, with:

  * column refs quoted with the dialect's identifier quoting
    (backticks for MySQL, double quotes for MSSQL),
  * ``eb.val(...)`` arguments emitted as the dialect's bound-parameter
    placeholder (``?`` for MySQL; ``@1``, ``@2``, ... for MSSQL) and
    collected into the compiled query's ``parameters`` array — NEVER inlined
    as literals,
  * raw ``sql`` fragments emitted verbatim,
  * arguments joined in input order with ``, `` and exactly one call-paren
    pair (no trailing separator).

Strategy / discriminative power
-------------------------------
L1 checks confirm the deliverable files exist and export the new symbol from
each of the MySQL and MSSQL modules, and that the agent created the required
new node test file.

L2 checks do NOT trust the agent's own test file. Instead this harness:
  1. builds the kysely library (``pnpm build``) once,
  2. writes its OWN TypeScript driver test into ``test/node/src/`` that
     imports the freshly-built MySQL/MSSQL helpers, builds a ``Kysely``
     instance per dialect with that dialect's adapter + query compiler and
     ``DummyDriver`` (no DB / network), calls ``.compile()`` and
     ``console.log``s the produced ``sql`` + ``parameters`` as JSON,
  3. compiles the node test sources (``pnpm test:node:build`` — this also
     type-checks the agent's new ``jsonBuildArray`` signature because our
     driver invokes it), and runs the driver under mocha,
  4. parses the emitted JSON and asserts on exact SQL strings, exact
     parameter arrays, argument ordering and verbatim raw fragments.

A naive solution (wrong SQL function name, ``json_object``/``json_build_array``
instead of ``json_array``, inlined values instead of bound parameters, wrong
argument ordering, only one of the two dialects implemented, or a
non-compiling type signature) fails these tests because the real Kysely
compiler for each dialect is exercised end-to-end.

Native acceptance command driven by L2:
    npx mocha --timeout 15000 test/node/dist/<probe>.js
(equivalent to the doc's ``npx mocha --timeout 15000
test/node/dist/json-build-array-mysql-mssql.test.js`` but using this harness's
own independent probe instead of the agent-authored test).
"""

import json
import os
import re
import subprocess

import pytest


REPO_DIR = "/workspace/kysely"

MYSQL_HELPER = os.path.join(REPO_DIR, "src", "helpers", "mysql.ts")
MSSQL_HELPER = os.path.join(REPO_DIR, "src", "helpers", "mssql.ts")
NEW_TEST_TS = os.path.join(
    REPO_DIR, "test", "node", "src", "json-build-array-mysql-mssql.test.ts"
)

# Where this harness drops its own independent driver (NOT the agent's file).
DRIVER_NAME = "zzz-json-build-array-mysql-mssql-probe"
DRIVER_TS = os.path.join(REPO_DIR, "test", "node", "src", DRIVER_NAME + ".ts")
DRIVER_JS = os.path.join(REPO_DIR, "test", "node", "dist", DRIVER_NAME + ".js")

# Markers used to extract our JSON payloads from the mocha stdout stream.
BEGIN = "@@PROBE_BEGIN@@"
END = "@@PROBE_END@@"


# ---------------------------------------------------------------------------
# Driver test (TypeScript) written into the repo by this harness.
# Uses the dialect adapter/compiler + DummyDriver pattern from the kysely repo,
# but for the MySQL and MSSQL dialects (this variant's targets).
# ---------------------------------------------------------------------------
DRIVER_SOURCE = r"""
import {
  DummyDriver,
  Kysely,
  MysqlAdapter,
  MysqlIntrospector,
  MysqlQueryCompiler,
  MssqlAdapter,
  MssqlIntrospector,
  MssqlQueryCompiler,
  sql,
} from '../../../dist/index.js'
import { jsonBuildArray as mysql_jsonBuildArray } from '../../../dist/helpers/mysql.js'
import { jsonBuildArray as mssql_jsonBuildArray } from '../../../dist/helpers/mssql.js'

interface DB {
  person: {
    id: number
    first_name: string | null
    last_name: string | null
  }
}

const mysqlDb = new Kysely<DB>({
  dialect: {
    createAdapter: () => new MysqlAdapter(),
    createDriver: () => new DummyDriver(),
    createIntrospector: (db) => new MysqlIntrospector(db),
    createQueryCompiler: () => new MysqlQueryCompiler(),
  },
})

const mssqlDb = new Kysely<DB>({
  dialect: {
    createAdapter: () => new MssqlAdapter(),
    createDriver: () => new DummyDriver(),
    createIntrospector: (db) => new MssqlIntrospector(db),
    createQueryCompiler: () => new MssqlQueryCompiler(),
  },
})

function emit(label: string, sqlText: string, parameters: readonly unknown[]) {
  console.log('@@PROBE_BEGIN@@' + JSON.stringify({
    label,
    sql: sqlText,
    parameters,
  }) + '@@PROBE_END@@')
}

describe('json-build-array mysql/mssql probe', () => {
  it('emits compiled output for every scenario', () => {
    // --- MySQL: two column refs ---
    {
      const c = mysqlDb
        .selectFrom('person')
        .select((eb) =>
          mysql_jsonBuildArray([eb.ref('first_name'), eb.ref('last_name')]).as('name'),
        )
        .compile()
      emit('mysql_refs', c.sql, c.parameters)
    }

    // --- MSSQL: two column refs ---
    {
      const c = mssqlDb
        .selectFrom('person')
        .select((eb) =>
          mssql_jsonBuildArray([eb.ref('first_name'), eb.ref('last_name')]).as('name'),
        )
        .compile()
      emit('mssql_refs', c.sql, c.parameters)
    }

    // --- MySQL: ref + eb.val (bound parameter) ---
    {
      const c = mysqlDb
        .selectFrom('person')
        .select((eb) =>
          mysql_jsonBuildArray([eb.ref('first_name'), eb.val('!')]).as('name'),
        )
        .compile()
      emit('mysql_val', c.sql, c.parameters)
    }

    // --- MSSQL: ref + eb.val (bound parameter) ---
    {
      const c = mssqlDb
        .selectFrom('person')
        .select((eb) =>
          mssql_jsonBuildArray([eb.ref('first_name'), eb.val('!')]).as('name'),
        )
        .compile()
      emit('mssql_val', c.sql, c.parameters)
    }

    // --- MySQL: raw sql fragment + ref ---
    {
      const c = mysqlDb
        .selectFrom('person')
        .select((eb) =>
          mysql_jsonBuildArray([sql<number>`1 + 1`, eb.ref('id')]).as('calc'),
        )
        .compile()
      emit('mysql_raw', c.sql, c.parameters)
    }

    // --- MSSQL: raw sql fragment + ref ---
    {
      const c = mssqlDb
        .selectFrom('person')
        .select((eb) =>
          mssql_jsonBuildArray([sql<number>`1 + 1`, eb.ref('id')]).as('calc'),
        )
        .compile()
      emit('mssql_raw', c.sql, c.parameters)
    }

    // --- MySQL: three column refs (ordering) ---
    {
      const c = mysqlDb
        .selectFrom('person')
        .select((eb) =>
          mysql_jsonBuildArray([
            eb.ref('first_name'),
            eb.ref('last_name'),
            eb.ref('id'),
          ]).as('triple'),
        )
        .compile()
      emit('mysql_three', c.sql, c.parameters)
    }

    // --- MSSQL: three column refs (ordering) ---
    {
      const c = mssqlDb
        .selectFrom('person')
        .select((eb) =>
          mssql_jsonBuildArray([
            eb.ref('first_name'),
            eb.ref('last_name'),
            eb.ref('id'),
          ]).as('triple'),
        )
        .compile()
      emit('mssql_three', c.sql, c.parameters)
    }

    // --- MySQL: multiple eb.val args, parameter ordering ---
    {
      const c = mysqlDb
        .selectFrom('person')
        .select((eb) =>
          mysql_jsonBuildArray([eb.val('a'), eb.val('b'), eb.val('c')]).as('vals'),
        )
        .compile()
      emit('mysql_multi_val', c.sql, c.parameters)
    }

    // --- MSSQL: multiple eb.val args, parameter ordering ---
    {
      const c = mssqlDb
        .selectFrom('person')
        .select((eb) =>
          mssql_jsonBuildArray([eb.val('a'), eb.val('b'), eb.val('c')]).as('vals'),
        )
        .compile()
      emit('mssql_multi_val', c.sql, c.parameters)
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
        os.path.join(REPO_DIR, "dist", "helpers", "mysql.js")
    ), "dist/helpers/mysql.js not produced by build"
    assert os.path.isfile(
        os.path.join(REPO_DIR, "dist", "helpers", "mssql.js")
    ), "dist/helpers/mssql.js not produced by build"

    # 3. drop our independent driver into the node test sources.
    with open(DRIVER_TS, "w") as f:
        f.write(DRIVER_SOURCE)

    try:
        # 4. compile the node test sources (this also type-checks the agent's
        #    new jsonBuildArray signature, since our driver invokes it).
        tsb = _run("pnpm test:node:build", timeout=600)
        assert tsb.returncode == 0, (
            "pnpm test:node:build (tsc) failed — the jsonBuildArray helper does "
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
    """jsonBuildArray helpers for the MySQL and MSSQL dialects."""

    REPO_DIR = "/workspace/kysely"

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and export the symbol
    # ------------------------------------------------------------------

    def test_mysql_helper_file_exists(self):
        """src/helpers/mysql.ts must exist."""
        assert os.path.isfile(MYSQL_HELPER), f"missing {MYSQL_HELPER}"

    def test_mssql_helper_file_exists(self):
        """src/helpers/mssql.ts must exist."""
        assert os.path.isfile(MSSQL_HELPER), f"missing {MSSQL_HELPER}"

    def test_mysql_exports_json_build_array(self):
        """mysql.ts must declare an exported `jsonBuildArray` function."""
        with open(MYSQL_HELPER) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+jsonBuildArray\b", src
        ), "no `export function jsonBuildArray` in src/helpers/mysql.ts"

    def test_mssql_exports_json_build_array(self):
        """mssql.ts must declare an exported `jsonBuildArray` function."""
        with open(MSSQL_HELPER) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+jsonBuildArray\b", src
        ), "no `export function jsonBuildArray` in src/helpers/mssql.ts"

    def test_existing_helpers_preserved(self):
        """Existing exported helpers in both modules must be left intact."""
        with open(MYSQL_HELPER) as f:
            mysql_src = f.read()
        with open(MSSQL_HELPER) as f:
            mssql_src = f.read()
        for sym in ("jsonArrayFrom", "jsonObjectFrom", "jsonBuildObject"):
            assert re.search(
                r"export\s+function\s+" + sym + r"\b", mysql_src
            ), f"mysql.ts lost existing export {sym}"
            assert re.search(
                r"export\s+function\s+" + sym + r"\b", mssql_src
            ), f"mssql.ts lost existing export {sym}"

    def test_new_node_test_file_exists(self):
        """The required new node test file must be created by the agent."""
        assert os.path.isfile(
            NEW_TEST_TS
        ), "test/node/src/json-build-array-mysql-mssql.test.ts was not created"

    # ------------------------------------------------------------------
    # L2 — dynamic compilation behavior (via the harness's own driver)
    # ------------------------------------------------------------------

    def test_mysql_column_refs_sql(self, probe):
        """MySQL: two column refs -> json_array with backtick-quoted idents, no params."""
        r = probe["mysql_refs"]
        assert (
            r["sql"]
            == "select json_array(`first_name`, `last_name`) as `name` from `person`"
        ), f"unexpected MySQL sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_mssql_column_refs_sql(self, probe):
        """MSSQL: two column refs -> json_array with double-quoted idents, no params."""
        r = probe["mssql_refs"]
        assert (
            r["sql"]
            == 'select json_array("first_name", "last_name") as "name" from "person"'
        ), f"unexpected MSSQL sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_mysql_uses_correct_function_name(self, probe):
        """MySQL must use json_array (not json_build_array / json_object)."""
        s = probe["mysql_refs"]["sql"]
        assert "json_array(" in s, f"MySQL missing json_array(): {s!r}"
        assert (
            "json_build_array(" not in s
        ), f"MySQL must not use json_build_array(): {s!r}"
        assert "json_object(" not in s, f"MySQL must not use json_object(): {s!r}"

    def test_mssql_uses_correct_function_name(self, probe):
        """MSSQL must use json_array (not json_build_array / json_query)."""
        s = probe["mssql_refs"]["sql"]
        assert "json_array(" in s, f"MSSQL missing json_array(): {s!r}"
        assert (
            "json_build_array(" not in s
        ), f"MSSQL must not use json_build_array(): {s!r}"
        assert "json_query(" not in s, f"MSSQL must not use json_query(): {s!r}"

    def test_mysql_val_is_bound_parameter(self, probe):
        """MySQL: eb.val('!') must become a ? placeholder and be collected as a param."""
        r = probe["mysql_val"]
        assert (
            r["sql"]
            == "select json_array(`first_name`, ?) as `name` from `person`"
        ), f"unexpected MySQL val sql: {r['sql']!r}"
        assert r["parameters"] == ["!"], f"expected ['!'] params, got {r['parameters']!r}"
        # value must NOT be inlined as a literal in the SQL text.
        assert "'!'" not in r["sql"], f"value was inlined: {r['sql']!r}"

    def test_mssql_val_is_bound_parameter(self, probe):
        """MSSQL: eb.val('!') must become an @1 placeholder and be collected as a param."""
        r = probe["mssql_val"]
        assert (
            r["sql"]
            == 'select json_array("first_name", @1) as "name" from "person"'
        ), f"unexpected MSSQL val sql: {r['sql']!r}"
        assert r["parameters"] == ["!"], f"expected ['!'] params, got {r['parameters']!r}"
        assert "'!'" not in r["sql"], f"value was inlined: {r['sql']!r}"

    def test_mysql_raw_fragment_verbatim(self, probe):
        """MySQL: a raw sql`1 + 1` fragment must be emitted verbatim as the first arg."""
        r = probe["mysql_raw"]
        assert (
            r["sql"] == "select json_array(1 + 1, `id`) as `calc` from `person`"
        ), f"unexpected MySQL raw sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_mssql_raw_fragment_verbatim(self, probe):
        """MSSQL: a raw sql`1 + 1` fragment must be emitted verbatim as the first arg."""
        r = probe["mssql_raw"]
        assert (
            r["sql"] == 'select json_array(1 + 1, "id") as "calc" from "person"'
        ), f"unexpected MSSQL raw sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_mysql_three_args_order_and_separators(self, probe):
        """MySQL: 3+ args joined in input order with `, ` and a single paren pair."""
        r = probe["mysql_three"]
        assert (
            r["sql"]
            == "select json_array(`first_name`, `last_name`, `id`) as `triple` from `person`"
        ), f"unexpected MySQL three-arg sql: {r['sql']!r}"
        inner = re.search(r"json_array\((.*?)\) as", r["sql"]).group(1)
        assert inner == "`first_name`, `last_name`, `id`", f"bad arg list: {inner!r}"
        assert r["sql"].count("json_array(") == 1

    def test_mssql_three_args_order_and_separators(self, probe):
        """MSSQL: 3+ args joined in input order with `, ` and a single paren pair."""
        r = probe["mssql_three"]
        assert (
            r["sql"]
            == 'select json_array("first_name", "last_name", "id") as "triple" from "person"'
        ), f"unexpected MSSQL three-arg sql: {r['sql']!r}"
        inner = re.search(r"json_array\((.*?)\) as", r["sql"]).group(1)
        assert inner == '"first_name", "last_name", "id"', f"bad arg list: {inner!r}"
        assert r["sql"].count("json_array(") == 1

    def test_mysql_multi_val_parameter_ordering(self, probe):
        """MySQL: multiple eb.val args -> ?,?,? with params collected in order."""
        r = probe["mysql_multi_val"]
        assert (
            r["sql"] == "select json_array(?, ?, ?) as `vals` from `person`"
        ), f"unexpected MySQL multi-val sql: {r['sql']!r}"
        assert r["parameters"] == ["a", "b", "c"], f"bad params: {r['parameters']!r}"

    def test_mssql_multi_val_parameter_ordering(self, probe):
        """MSSQL: multiple eb.val args -> @1,@2,@3 with params collected in order."""
        r = probe["mssql_multi_val"]
        assert (
            r["sql"] == 'select json_array(@1, @2, @3) as "vals" from "person"'
        ), f"unexpected MSSQL multi-val sql: {r['sql']!r}"
        assert r["parameters"] == ["a", "b", "c"], f"bad params: {r['parameters']!r}"

    def test_no_trailing_separator_and_single_paren(self, probe):
        """Both dialects: no trailing `, ` and balanced parens for the call form."""
        for label in ("mysql_three", "mssql_three"):
            s = probe[label]["sql"]
            assert ", )" not in s, f"trailing separator in {label}: {s!r}"
            assert s.count("(") == s.count(")"), f"unbalanced parens in {label}: {s!r}"
