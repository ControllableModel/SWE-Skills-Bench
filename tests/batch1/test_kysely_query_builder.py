"""
Test for the 'kysely-query-builder' skill — Add jsonBuildArray dialect helpers.

Verifies that the agent added a new ``jsonBuildArray`` helper to BOTH the
PostgreSQL (``src/helpers/postgres.ts``) and SQLite (``src/helpers/sqlite.ts``)
helper modules, such that:

  * PostgreSQL compiles to ``json_build_array(<arg0>, <arg1>, ...)``
  * SQLite   compiles to ``json_array(<arg0>, <arg1>, ...)``
  * column refs are quoted, ``eb.val(...)`` becomes a bound parameter
    (``$1`` / ``?``, collected into the parameters list, NOT inlined),
    and raw ``sql`` fragments are emitted verbatim, in input order.

Strategy / discriminative power
-------------------------------
L1 checks confirm the deliverable files exist and export the symbol.

L2 checks do NOT trust the agent's own test file. Instead this harness:
  1. builds the kysely library (``pnpm build``) once,
  2. writes its OWN TypeScript driver test into ``test/node/src/`` that
     imports the freshly-built helpers, builds a ``Kysely`` instance per
     dialect with ``DummyDriver`` (no DB / network), calls ``.compile()``
     and ``console.log``s the produced ``sql`` + ``parameters`` as JSON,
  3. compiles the node test sources (``pnpm test:node:build``) and runs the
     driver under mocha,
  4. parses the emitted JSON and asserts on exact SQL strings, exact
     parameter arrays, argument ordering and verbatim raw fragments.

A naive solution (wrong SQL function name, inlined values, wrong ordering,
missing dialect, or a non-compiling type signature) fails these tests because
the real Kysely compiler is exercised end-to-end.
"""

import json
import os
import re
import subprocess

import pytest


REPO_DIR = "/workspace/kysely"

PG_HELPER = os.path.join(REPO_DIR, "src", "helpers", "postgres.ts")
SQLITE_HELPER = os.path.join(REPO_DIR, "src", "helpers", "sqlite.ts")
NEW_TEST_TS = os.path.join(REPO_DIR, "test", "node", "src", "json-build-array.test.ts")

# Where this harness drops its own independent driver (NOT the agent's file).
DRIVER_NAME = "zzz-json-build-array-probe"
DRIVER_TS = os.path.join(REPO_DIR, "test", "node", "src", DRIVER_NAME + ".ts")
DRIVER_JS = os.path.join(REPO_DIR, "test", "node", "dist", DRIVER_NAME + ".js")

# Markers used to extract our JSON payloads from the mocha stdout stream.
BEGIN = "@@PROBE_BEGIN@@"
END = "@@PROBE_END@@"


# ---------------------------------------------------------------------------
# Driver test (TypeScript) written into the repo by this harness.
# Uses the dialect adapter/compiler + DummyDriver pattern from the kysely repo.
# ---------------------------------------------------------------------------
DRIVER_SOURCE = r"""
import {
  DummyDriver,
  Kysely,
  PostgresAdapter,
  PostgresIntrospector,
  PostgresQueryCompiler,
  SqliteAdapter,
  SqliteIntrospector,
  SqliteQueryCompiler,
  sql,
} from '../../../dist/index.js'
import { jsonBuildArray as pg_jsonBuildArray } from '../../../dist/helpers/postgres.js'
import { jsonBuildArray as sqlite_jsonBuildArray } from '../../../dist/helpers/sqlite.js'

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

const sqliteDb = new Kysely<DB>({
  dialect: {
    createAdapter: () => new SqliteAdapter(),
    createDriver: () => new DummyDriver(),
    createIntrospector: (db) => new SqliteIntrospector(db),
    createQueryCompiler: () => new SqliteQueryCompiler(),
  },
})

function emit(label: string, sqlText: string, parameters: readonly unknown[]) {
  console.log('@@PROBE_BEGIN@@' + JSON.stringify({
    label,
    sql: sqlText,
    parameters,
  }) + '@@PROBE_END@@')
}

describe('json-build-array probe', () => {
  it('emits compiled output for every scenario', () => {
    // --- PostgreSQL: two column refs ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) =>
          pg_jsonBuildArray([eb.ref('first_name'), eb.ref('last_name')]).as('name'),
        )
        .compile()
      emit('pg_refs', c.sql, c.parameters)
    }

    // --- SQLite: two column refs ---
    {
      const c = sqliteDb
        .selectFrom('person')
        .select((eb) =>
          sqlite_jsonBuildArray([eb.ref('first_name'), eb.ref('last_name')]).as('name'),
        )
        .compile()
      emit('sqlite_refs', c.sql, c.parameters)
    }

    // --- PostgreSQL: ref + eb.val (bound parameter) ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) =>
          pg_jsonBuildArray([eb.ref('first_name'), eb.val('!')]).as('name'),
        )
        .compile()
      emit('pg_val', c.sql, c.parameters)
    }

    // --- SQLite: ref + eb.val (bound parameter) ---
    {
      const c = sqliteDb
        .selectFrom('person')
        .select((eb) =>
          sqlite_jsonBuildArray([eb.ref('first_name'), eb.val('!')]).as('name'),
        )
        .compile()
      emit('sqlite_val', c.sql, c.parameters)
    }

    // --- PostgreSQL: raw sql fragment + ref ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) =>
          pg_jsonBuildArray([sql<number>`1 + 1`, eb.ref('id')]).as('calc'),
        )
        .compile()
      emit('pg_raw', c.sql, c.parameters)
    }

    // --- SQLite: raw sql fragment + ref ---
    {
      const c = sqliteDb
        .selectFrom('person')
        .select((eb) =>
          sqlite_jsonBuildArray([sql<number>`1 + 1`, eb.ref('id')]).as('calc'),
        )
        .compile()
      emit('sqlite_raw', c.sql, c.parameters)
    }

    // --- PostgreSQL: three column refs (ordering) ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) =>
          pg_jsonBuildArray([
            eb.ref('first_name'),
            eb.ref('last_name'),
            eb.ref('id'),
          ]).as('triple'),
        )
        .compile()
      emit('pg_three', c.sql, c.parameters)
    }

    // --- SQLite: three column refs (ordering) ---
    {
      const c = sqliteDb
        .selectFrom('person')
        .select((eb) =>
          sqlite_jsonBuildArray([
            eb.ref('first_name'),
            eb.ref('last_name'),
            eb.ref('id'),
          ]).as('triple'),
        )
        .compile()
      emit('sqlite_three', c.sql, c.parameters)
    }

    // --- PostgreSQL: multiple eb.val args, parameter ordering ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) =>
          pg_jsonBuildArray([eb.val('a'), eb.val('b'), eb.val('c')]).as('vals'),
        )
        .compile()
      emit('pg_multi_val', c.sql, c.parameters)
    }

    // --- SQLite: multiple eb.val args, parameter ordering ---
    {
      const c = sqliteDb
        .selectFrom('person')
        .select((eb) =>
          sqlite_jsonBuildArray([eb.val('a'), eb.val('b'), eb.val('c')]).as('vals'),
        )
        .compile()
      emit('sqlite_multi_val', c.sql, c.parameters)
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
    """jsonBuildArray helpers for the PostgreSQL and SQLite dialects."""

    REPO_DIR = "/workspace/kysely"

    # ------------------------------------------------------------------
    # L1 — deliverable files exist and export the symbol
    # ------------------------------------------------------------------

    def test_postgres_helper_file_exists(self):
        """src/helpers/postgres.ts must exist."""
        assert os.path.isfile(PG_HELPER), f"missing {PG_HELPER}"

    def test_sqlite_helper_file_exists(self):
        """src/helpers/sqlite.ts must exist."""
        assert os.path.isfile(SQLITE_HELPER), f"missing {SQLITE_HELPER}"

    def test_postgres_exports_json_build_array(self):
        """postgres.ts must declare an exported `jsonBuildArray` function."""
        with open(PG_HELPER) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+jsonBuildArray\b", src
        ), "no `export function jsonBuildArray` in src/helpers/postgres.ts"

    def test_sqlite_exports_json_build_array(self):
        """sqlite.ts must declare an exported `jsonBuildArray` function."""
        with open(SQLITE_HELPER) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+jsonBuildArray\b", src
        ), "no `export function jsonBuildArray` in src/helpers/sqlite.ts"

    def test_new_node_test_file_exists(self):
        """The required new node test file must be created by the agent."""
        assert os.path.isfile(
            NEW_TEST_TS
        ), "test/node/src/json-build-array.test.ts was not created"

    # ------------------------------------------------------------------
    # L2 — dynamic compilation behavior (via the harness's own driver)
    # ------------------------------------------------------------------

    def test_postgres_column_refs_sql(self, probe):
        """PG: two column refs compile to json_build_array with quoted idents, no params."""
        r = probe["pg_refs"]
        assert (
            r["sql"]
            == 'select json_build_array("first_name", "last_name") as "name" from "person"'
        ), f"unexpected PG sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_sqlite_column_refs_sql(self, probe):
        """SQLite: two column refs compile to json_array with quoted idents, no params."""
        r = probe["sqlite_refs"]
        assert (
            r["sql"]
            == 'select json_array("first_name", "last_name") as "name" from "person"'
        ), f"unexpected SQLite sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_postgres_uses_correct_function_name(self, probe):
        """PG must use json_build_array (not json_array / json_build_object)."""
        s = probe["pg_refs"]["sql"]
        assert "json_build_array(" in s, f"PG missing json_build_array(): {s!r}"
        assert "json_array(" not in s, f"PG must not use json_array(): {s!r}"
        assert (
            "json_build_object(" not in s
        ), f"PG must not use json_build_object(): {s!r}"

    def test_sqlite_uses_correct_function_name(self, probe):
        """SQLite must use json_array (not json_build_array / json_object)."""
        s = probe["sqlite_refs"]["sql"]
        assert "json_array(" in s, f"SQLite missing json_array(): {s!r}"
        assert (
            "json_build_array(" not in s
        ), f"SQLite must not use json_build_array(): {s!r}"
        assert "json_object(" not in s, f"SQLite must not use json_object(): {s!r}"

    def test_postgres_val_is_bound_parameter(self, probe):
        """PG: eb.val('!') must become $1 placeholder and be collected as a param."""
        r = probe["pg_val"]
        assert (
            r["sql"]
            == 'select json_build_array("first_name", $1) as "name" from "person"'
        ), f"unexpected PG val sql: {r['sql']!r}"
        assert r["parameters"] == ["!"], f"expected ['!'] params, got {r['parameters']!r}"
        # value must NOT be inlined as a literal in the SQL text.
        assert "'!'" not in r["sql"], f"value was inlined: {r['sql']!r}"

    def test_sqlite_val_is_bound_parameter(self, probe):
        """SQLite: eb.val('!') must become a ? placeholder and be collected as a param."""
        r = probe["sqlite_val"]
        assert (
            r["sql"] == 'select json_array("first_name", ?) as "name" from "person"'
        ), f"unexpected SQLite val sql: {r['sql']!r}"
        assert r["parameters"] == ["!"], f"expected ['!'] params, got {r['parameters']!r}"
        assert "'!'" not in r["sql"], f"value was inlined: {r['sql']!r}"

    def test_postgres_raw_fragment_verbatim(self, probe):
        """PG: a raw sql`1 + 1` fragment must be emitted verbatim as the first arg."""
        r = probe["pg_raw"]
        assert (
            r["sql"]
            == 'select json_build_array(1 + 1, "id") as "calc" from "person"'
        ), f"unexpected PG raw sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_sqlite_raw_fragment_verbatim(self, probe):
        """SQLite: a raw sql`1 + 1` fragment must be emitted verbatim as the first arg."""
        r = probe["sqlite_raw"]
        assert (
            r["sql"] == 'select json_array(1 + 1, "id") as "calc" from "person"'
        ), f"unexpected SQLite raw sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_postgres_three_args_order_and_separators(self, probe):
        """PG: 3+ args joined in input order with `, ` and a single paren pair."""
        r = probe["pg_three"]
        assert (
            r["sql"]
            == 'select json_build_array("first_name", "last_name", "id") as "triple" from "person"'
        ), f"unexpected PG three-arg sql: {r['sql']!r}"
        inner = re.search(r"json_build_array\((.*?)\) as", r["sql"]).group(1)
        assert inner == '"first_name", "last_name", "id"', f"bad arg list: {inner!r}"
        # exactly one '(' belonging to the function call form `json_build_array(`
        assert r["sql"].count("json_build_array(") == 1

    def test_sqlite_three_args_order_and_separators(self, probe):
        """SQLite: 3+ args joined in input order with `, ` and a single paren pair."""
        r = probe["sqlite_three"]
        assert (
            r["sql"]
            == 'select json_array("first_name", "last_name", "id") as "triple" from "person"'
        ), f"unexpected SQLite three-arg sql: {r['sql']!r}"
        inner = re.search(r"json_array\((.*?)\) as", r["sql"]).group(1)
        assert inner == '"first_name", "last_name", "id"', f"bad arg list: {inner!r}"
        assert r["sql"].count("json_array(") == 1

    def test_postgres_multi_val_parameter_ordering(self, probe):
        """PG: multiple eb.val args produce $1,$2,$3 in order with params in order."""
        r = probe["pg_multi_val"]
        assert (
            r["sql"]
            == 'select json_build_array($1, $2, $3) as "vals" from "person"'
        ), f"unexpected PG multi-val sql: {r['sql']!r}"
        assert r["parameters"] == ["a", "b", "c"], f"bad params: {r['parameters']!r}"

    def test_sqlite_multi_val_parameter_ordering(self, probe):
        """SQLite: multiple eb.val args produce ?,?,? with params collected in order."""
        r = probe["sqlite_multi_val"]
        assert (
            r["sql"] == 'select json_array(?, ?, ?) as "vals" from "person"'
        ), f"unexpected SQLite multi-val sql: {r['sql']!r}"
        assert r["parameters"] == ["a", "b", "c"], f"bad params: {r['parameters']!r}"

    def test_no_trailing_separator_and_single_paren(self, probe):
        """Both dialects: no trailing `, ` and a balanced single call-paren pair."""
        for label in ("pg_three", "sqlite_three"):
            s = probe[label]["sql"]
            assert ", )" not in s, f"trailing separator in {label}: {s!r}"
            assert s.count("(") == s.count(")"), f"unbalanced parens in {label}: {s!r}"
