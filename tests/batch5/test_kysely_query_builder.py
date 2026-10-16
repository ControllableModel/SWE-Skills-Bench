"""
Test for the 'kysely-query-builder' skill (variant ext5) — add a
``jsonbBuildObject`` PostgreSQL helper (the binary-JSON ``jsonb`` variant of
the existing ``jsonBuildObject``).

The variant task requires the agent to:

  * add and export ``jsonbBuildObject`` from ``src/helpers/postgres.ts``,
    accepting the SAME argument shape as ``jsonBuildObject`` — a record
    mapping string keys to ``Expression<unknown>`` values — and returning a
    ``RawBuilder`` aliasable with ``.as(...)`` inside a ``select(...)``;
  * compile to PostgreSQL's ``jsonb_build_object(<k0>, <v0>, <k1>, <v1>, ...)``
    where:
      - each property KEY is emitted as a single-quoted string literal
        inlined into the SQL text (``'first'``) — keys are NOT bound params;
      - each property VALUE is compiled through normal expression compilation:
        column refs are double-quoted, ``eb.val(...)`` becomes ``$1``/``$2``
        placeholders collected (in order) into the parameters list, raw
        ``sql`` fragments are emitted verbatim;
      - keys and values alternate in the object's key (insertion) order,
        separated by ``, ``, with exactly one pair of call parentheses;
  * leave every existing exported helper unchanged — in particular
    ``jsonBuildObject`` must still emit ``json_build_object`` (the ``json``
    variant), NOT ``jsonb_build_object``;
  * add a new node test file
    ``test/node/src/jsonb-build-object-postgres.test.ts``.

Strategy / discriminative power
-------------------------------
L1 checks confirm the deliverable files exist, declare/export the new symbol,
and do not regress the existing helper's function name.

L2 checks do NOT trust the agent's own test file. Instead this harness:
  1. builds the kysely library (``pnpm build``) once,
  2. writes its OWN TypeScript driver into ``test/node/src/`` that imports the
     freshly-built ``jsonbBuildObject`` (and ``jsonBuildObject``), builds a
     ``Kysely`` instance with the PostgreSQL adapter/compiler + ``DummyDriver``
     (no DB / network), calls ``.compile()`` and ``console.log``s the produced
     ``sql`` + ``parameters`` as JSON,
  3. compiles the node test sources (``pnpm test:node:build`` — this also
     type-checks the agent's new signature, since our driver invokes it),
  4. runs the driver under mocha and asserts on exact SQL strings, exact
     parameter arrays, key/value ordering, inline-key literals, bound-param
     values, verbatim raw fragments, and a single call-paren pair.

A naive solution fails: wrong function name (``json_build_object`` instead of
``jsonb_build_object``, or vice-versa for the untouched helper), keys turned
into bound parameters, values inlined instead of parameterised, dropped/wrong
key order, or a non-compiling type signature all break the end-to-end compile.
"""

import json
import os
import re
import subprocess

import pytest


REPO_DIR = "/workspace/kysely"

PG_HELPER = os.path.join(REPO_DIR, "src", "helpers", "postgres.ts")
NEW_TEST_TS = os.path.join(
    REPO_DIR, "test", "node", "src", "jsonb-build-object-postgres.test.ts"
)

# Where this harness drops its own independent driver (NOT the agent's file).
DRIVER_NAME = "zzz-jsonb-build-object-probe"
DRIVER_TS = os.path.join(REPO_DIR, "test", "node", "src", DRIVER_NAME + ".ts")
DRIVER_JS = os.path.join(REPO_DIR, "test", "node", "dist", DRIVER_NAME + ".js")

# Markers used to extract our JSON payloads from the mocha stdout stream.
BEGIN = "@@PROBE_BEGIN@@"
END = "@@PROBE_END@@"


# ---------------------------------------------------------------------------
# Driver test (TypeScript) written into the repo by this harness.
# Uses the PostgreSQL adapter/compiler + DummyDriver pattern from kysely.
# Imports BOTH the new jsonbBuildObject and the existing jsonBuildObject so we
# can also prove the existing helper was left untouched.
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
import {
  jsonbBuildObject,
  jsonBuildObject,
} from '../../../dist/helpers/postgres.js'

interface DB {
  person: {
    id: number
    first_name: string | null
    last_name: string | null
  }
}

const db = new Kysely<DB>({
  dialect: {
    createAdapter: () => new PostgresAdapter(),
    createDriver: () => new DummyDriver(),
    createIntrospector: (d) => new PostgresIntrospector(d),
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

describe('jsonb-build-object probe', () => {
  it('emits compiled output for every scenario', () => {
    // --- two column refs: keys inline, values double-quoted, no params ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) =>
          jsonbBuildObject({
            first: eb.ref('first_name'),
            last: eb.ref('last_name'),
          }).as('name'),
        )
        .compile()
      emit('refs', c.sql, c.parameters)
    }

    // --- eb.val value becomes a bound parameter; keys stay inline ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) =>
          jsonbBuildObject({
            greeting: eb.val('hi'),
            id: eb.ref('id'),
          }).as('name'),
        )
        .compile()
      emit('val', c.sql, c.parameters)
    }

    // --- raw sql fragment value emitted verbatim ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) =>
          jsonbBuildObject({
            full: sql<string>`first_name || ' ' || last_name`,
          }).as('name'),
        )
        .compile()
      emit('raw', c.sql, c.parameters)
    }

    // --- multiple eb.val values: parameter ordering ($1,$2,$3) ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) =>
          jsonbBuildObject({
            a: eb.val('A'),
            b: eb.val('B'),
            c: eb.val('C'),
          }).as('vals'),
        )
        .compile()
      emit('multi_val', c.sql, c.parameters)
    }

    // --- key ORDER preservation with three properties ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) =>
          jsonbBuildObject({
            zebra: eb.ref('first_name'),
            alpha: eb.ref('last_name'),
            mid: eb.ref('id'),
          }).as('triple'),
        )
        .compile()
      emit('order', c.sql, c.parameters)
    }

    // --- the EXISTING jsonBuildObject must still emit json_build_object ---
    {
      const c = db
        .selectFrom('person')
        .select((eb) =>
          jsonBuildObject({
            first: eb.ref('first_name'),
            last: eb.ref('last_name'),
          }).as('name'),
        )
        .compile()
      emit('legacy_json', c.sql, c.parameters)
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

    # 1. install deps only if missing (benchmark container already has them).
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
        # 4. compile the node test sources (also type-checks the new signature).
        tsb = _run("pnpm test:node:build", timeout=600)
        assert tsb.returncode == 0, (
            "pnpm test:node:build (tsc) failed — the jsonbBuildObject helper "
            "does not type-check or is not exported:\nSTDOUT:\n"
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
    """jsonbBuildObject helper for the PostgreSQL dialect (ext5 variant)."""

    REPO_DIR = "/workspace/kysely"

    # ------------------------------------------------------------------
    # L1 — deliverables exist / minimally well-formed
    # ------------------------------------------------------------------

    def test_postgres_helper_file_exists(self):
        """src/helpers/postgres.ts must exist."""
        assert os.path.isfile(PG_HELPER), f"missing {PG_HELPER}"

    def test_postgres_exports_jsonb_build_object(self):
        """postgres.ts must declare an exported `jsonbBuildObject` function."""
        with open(PG_HELPER) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+jsonbBuildObject\b", src
        ), "no `export function jsonbBuildObject` in src/helpers/postgres.ts"

    def test_existing_json_build_object_still_present(self):
        """The pre-existing `jsonBuildObject` export must remain (not removed/renamed)."""
        with open(PG_HELPER) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+jsonBuildObject\b", src
        ), "existing `export function jsonBuildObject` was removed/renamed"

    def test_new_node_test_file_exists(self):
        """The required new node test file must be created by the agent."""
        assert os.path.isfile(
            NEW_TEST_TS
        ), "test/node/src/jsonb-build-object-postgres.test.ts was not created"

    # ------------------------------------------------------------------
    # L2 — dynamic compilation behavior (via the harness's own driver)
    # ------------------------------------------------------------------

    def test_column_refs_sql(self, probe):
        """Two column refs: inline keys, double-quoted value idents, no params."""
        r = probe["refs"]
        assert (
            r["sql"]
            == 'select jsonb_build_object(\'first\', "first_name", \'last\', "last_name") as "name" from "person"'
        ), f"unexpected refs sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_uses_jsonb_function_name(self, probe):
        """Must compile to jsonb_build_object(...) — not the json_build_object variant."""
        s = probe["refs"]["sql"]
        assert "jsonb_build_object(" in s, f"missing jsonb_build_object(): {s!r}"
        # The json (non-binary) call must not leak into the jsonb helper output.
        # Strip the 'jsonb_' occurrences, then ensure no bare 'json_build_object('.
        without_jsonb = s.replace("jsonb_build_object(", "")
        assert (
            "json_build_object(" not in without_jsonb
        ), f"jsonb helper wrongly emitted json_build_object(): {s!r}"

    def test_keys_are_inline_literals_not_parameters(self, probe):
        """Object keys must be single-quoted literals inlined, never bound params."""
        r = probe["refs"]
        s = r["sql"]
        assert "'first'" in s, f"key 'first' not inlined as a literal: {s!r}"
        assert "'last'" in s, f"key 'last' not inlined as a literal: {s!r}"
        # keys must not have leaked into the parameter list
        assert "first" not in [str(p) for p in r["parameters"]]
        assert "last" not in [str(p) for p in r["parameters"]]
        assert r["parameters"] == [], f"keys leaked into params: {r['parameters']!r}"

    def test_key_value_alternation_and_order(self, probe):
        """Compiled args must alternate key,value,key,value in object key order."""
        r = probe["refs"]
        inner = re.search(r"jsonb_build_object\((.*?)\) as", r["sql"]).group(1)
        assert (
            inner == "'first', \"first_name\", 'last', \"last_name\""
        ), f"bad key/value arg list/order: {inner!r}"

    def test_val_value_is_bound_parameter_keys_inline(self, probe):
        """eb.val('hi') value -> $1 placeholder collected as param; keys stay inline."""
        r = probe["val"]
        assert (
            r["sql"]
            == 'select jsonb_build_object(\'greeting\', $1, \'id\', "id") as "name" from "person"'
        ), f"unexpected val sql: {r['sql']!r}"
        assert r["parameters"] == ["hi"], f"expected ['hi'] params, got {r['parameters']!r}"
        # the value must NOT be inlined as a literal, but the keys must be.
        assert "'hi'" not in r["sql"], f"value was inlined: {r['sql']!r}"
        assert "'greeting'" in r["sql"], f"key 'greeting' not inlined: {r['sql']!r}"
        assert "'id'" in r["sql"], f"key 'id' not inlined: {r['sql']!r}"

    def test_raw_fragment_emitted_verbatim(self, probe):
        """A raw sql`...` fragment value must be emitted verbatim, no params."""
        r = probe["raw"]
        assert (
            r["sql"]
            == 'select jsonb_build_object(\'full\', first_name || \' \' || last_name) as "name" from "person"'
        ), f"unexpected raw sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_multi_val_parameter_ordering(self, probe):
        """Multiple eb.val values -> $1,$2,$3 in order; params collected in order."""
        r = probe["multi_val"]
        assert (
            r["sql"]
            == 'select jsonb_build_object(\'a\', $1, \'b\', $2, \'c\', $3) as "vals" from "person"'
        ), f"unexpected multi-val sql: {r['sql']!r}"
        assert r["parameters"] == ["A", "B", "C"], f"bad params: {r['parameters']!r}"

    def test_key_order_preserved_non_alphabetical(self, probe):
        """Insertion (object key) order must be preserved, not sorted alphabetically."""
        r = probe["order"]
        inner = re.search(r"jsonb_build_object\((.*?)\) as", r["sql"]).group(1)
        assert (
            inner
            == "'zebra', \"first_name\", 'alpha', \"last_name\", 'mid', \"id\""
        ), f"key order not preserved (or sorted): {inner!r}"
        # confirm it is NOT alphabetically sorted (alpha would precede zebra).
        assert inner.index("'zebra'") < inner.index(
            "'alpha'"
        ), f"keys appear sorted, order lost: {inner!r}"

    def test_single_call_paren_pair_and_no_trailing_separator(self, probe):
        """Exactly one jsonb_build_object( call, balanced parens, no trailing `, `."""
        for label in ("refs", "order", "multi_val"):
            s = probe[label]["sql"]
            assert (
                s.count("jsonb_build_object(") == 1
            ), f"expected exactly one call in {label}: {s!r}"
            assert ", )" not in s, f"trailing separator in {label}: {s!r}"
            assert s.count("(") == s.count(")"), f"unbalanced parens in {label}: {s!r}"

    def test_existing_helper_unchanged(self, probe):
        """The untouched jsonBuildObject must still emit json_build_object (json variant)."""
        r = probe["legacy_json"]
        assert (
            r["sql"]
            == 'select json_build_object(\'first\', "first_name", \'last\', "last_name") as "name" from "person"'
        ), f"existing jsonBuildObject changed: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"
        # crucially: the existing helper must NOT have been switched to jsonb.
        assert (
            "jsonb_build_object(" not in r["sql"]
        ), f"jsonBuildObject wrongly emits jsonb_build_object: {r['sql']!r}"
