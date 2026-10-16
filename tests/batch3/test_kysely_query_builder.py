"""
Test for the 'kysely-query-builder' skill (variant ext3) — add a PostgreSQL
``toJson`` single-expression scalar helper.

Variant task
------------
The agent must add and export a new ``toJson`` function to
``src/helpers/postgres.ts`` that wraps a *single* ``Expression<unknown>``
argument in PostgreSQL's scalar ``to_json(<arg>)`` function, and create a new
deterministic compilation test file ``test/node/src/to-json-postgres.test.ts``.

Required compiled behavior (PostgreSQL dialect):
  * ``toJson(eb.ref('data'))``  -> ``to_json("data")``  (quoted ident, no params)
  * ``toJson(eb.val(42))``      -> ``to_json($1)``       (bound parameter, 42 NOT inlined)
  * ``toJson(sql`now()`)``      -> ``to_json(now())``    (raw fragment verbatim, no params)
  * exactly ONE pair of parentheses and exactly ONE argument (no comma).
  * existing helpers (jsonArrayFrom / jsonObjectFrom / jsonBuildObject /
    mergeAction) are unchanged.

Verification strategy / discriminative power
--------------------------------------------
L1 checks confirm the deliverable files exist, that ``postgres.ts`` exports a
``toJson`` function, and that the existing helpers are still present and
exported (so the agent cannot break them).

L2 checks do NOT trust the agent's own test file. This harness:
  1. builds the kysely library (``pnpm build``) once,
  2. writes its OWN independent TypeScript driver into ``test/node/src/`` that
     imports the freshly-built ``toJson`` from ``dist/helpers/postgres.js``,
     constructs a ``Kysely`` instance with the PostgreSQL adapter/compiler +
     ``DummyDriver`` (no DB / network), calls ``.compile()`` for each scenario
     and ``console.log``s the produced ``sql`` + ``parameters`` as JSON,
  3. compiles the node test sources (``pnpm test:node:build``) — this also
     type-checks the agent's new ``toJson`` signature, since the driver calls
     it (a non-compiling / ``any``-typed signature fails here),
  4. runs the driver under mocha and asserts exact SQL strings, exact
     parameter arrays, single-argument / single-paren-pair structure, and that
     ``eb.val`` values are bound (never inlined).

A naive solution (wrong function name, multiple args / comma, inlined value,
hardcoded SQL ignoring the input expression, or a broken type signature) fails
because the real Kysely compiler is exercised end-to-end.
"""

import json
import os
import re
import subprocess

import pytest


REPO_DIR = "/workspace/kysely"

PG_HELPER = os.path.join(REPO_DIR, "src", "helpers", "postgres.ts")
NEW_TEST_TS = os.path.join(REPO_DIR, "test", "node", "src", "to-json-postgres.test.ts")

# Where this harness drops its own independent driver (NOT the agent's file).
DRIVER_NAME = "zzz-to-json-postgres-probe"
DRIVER_TS = os.path.join(REPO_DIR, "test", "node", "src", DRIVER_NAME + ".ts")
DRIVER_JS = os.path.join(REPO_DIR, "test", "node", "dist", DRIVER_NAME + ".js")

# Markers used to extract our JSON payloads from the mocha stdout stream.
BEGIN = "@@PROBE_BEGIN@@"
END = "@@PROBE_END@@"


# ---------------------------------------------------------------------------
# Driver test (TypeScript) written into the repo by this harness.
# Uses the PostgreSQL dialect adapter/compiler + DummyDriver pattern.
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
import { toJson } from '../../../dist/helpers/postgres.js'

interface DB {
  person: {
    id: number
    first_name: string | null
    last_name: string | null
    data: unknown
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

describe('to-json-postgres probe', () => {
  it('emits compiled output for every scenario', () => {
    // --- column ref argument -> to_json("data"), no params ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) => toJson(eb.ref('data')).as('doc'))
        .compile()
      emit('pg_ref', c.sql, c.parameters)
    }

    // --- eb.val(42) argument -> to_json($1), 42 bound as a parameter ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) => toJson(eb.val(42)).as('n'))
        .compile()
      emit('pg_val', c.sql, c.parameters)
    }

    // --- raw sql fragment argument -> to_json(now()), verbatim, no params ---
    {
      const c = pgDb
        .selectFrom('person')
        .select(() => toJson(sql`now()`).as('ts'))
        .compile()
      emit('pg_raw', c.sql, c.parameters)
    }

    // --- composes alongside other selected columns without altering them ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) => [
          'id',
          'first_name',
          toJson(eb.ref('data')).as('doc'),
        ])
        .compile()
      emit('pg_compose', c.sql, c.parameters)
    }

    // --- string value argument is bound, not inlined ---
    {
      const c = pgDb
        .selectFrom('person')
        .select((eb) => toJson(eb.val('hello')).as('greeting'))
        .compile()
      emit('pg_val_str', c.sql, c.parameters)
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

    # 1. install deps only if missing. In the benchmark container the repo
    #    toolchain is already installed; if so we skip the (network-bound)
    #    install entirely. The build step below is the real gate.
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
        # 4. compile the node test sources (also type-checks the agent's new
        #    toJson signature, since our driver invokes it).
        tsb = _run("pnpm test:node:build", timeout=600)
        assert tsb.returncode == 0, (
            "pnpm test:node:build (tsc) failed — the toJson helper does not "
            "type-check:\nSTDOUT:\n"
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
    """toJson single-expression scalar helper for the PostgreSQL dialect."""

    REPO_DIR = "/workspace/kysely"

    # ------------------------------------------------------------------
    # L1 — deliverable files exist / export the symbol / leave others intact
    # ------------------------------------------------------------------

    def test_postgres_helper_file_exists(self):
        """src/helpers/postgres.ts must exist."""
        assert os.path.isfile(PG_HELPER), f"missing {PG_HELPER}"

    def test_postgres_exports_to_json(self):
        """postgres.ts must declare an exported `toJson` function."""
        with open(PG_HELPER) as f:
            src = f.read()
        assert re.search(
            r"export\s+function\s+toJson\b", src
        ), "no `export function toJson` in src/helpers/postgres.ts"

    def test_new_node_test_file_exists(self):
        """The required new node test file must be created by the agent."""
        assert os.path.isfile(
            NEW_TEST_TS
        ), "test/node/src/to-json-postgres.test.ts was not created"

    def test_existing_helpers_still_exported(self):
        """Existing helpers must remain exported (agent must not remove them)."""
        with open(PG_HELPER) as f:
            src = f.read()
        for name in ("jsonArrayFrom", "jsonObjectFrom", "jsonBuildObject", "mergeAction"):
            assert re.search(
                r"export\s+function\s+" + name + r"\b", src
            ), f"existing helper `{name}` is no longer exported from postgres.ts"

    def test_to_json_signature_not_any_typed(self):
        """toJson must take a typed Expression argument, not be `any`-typed."""
        with open(PG_HELPER) as f:
            src = f.read()
        m = re.search(r"export\s+function\s+toJson\s*<[^>]*>?\s*\(([^)]*)\)", src)
        if m is None:
            m = re.search(r"export\s+function\s+toJson\s*\(([^)]*)\)", src)
        assert m is not None, "could not locate toJson(...) parameter list"
        params = m.group(1)
        # Must reference Expression in the single parameter's type, and must
        # not be typed as bare `any`.
        assert "Expression" in params, (
            f"toJson parameter should be an Expression<...>, got: {params!r}"
        )
        assert not re.search(r":\s*any\b", params), (
            f"toJson parameter must not be `any`-typed: {params!r}"
        )

    # ------------------------------------------------------------------
    # L2 — dynamic compilation behavior (via the harness's own driver)
    # ------------------------------------------------------------------

    def test_column_ref_compiles_to_to_json(self, probe):
        """Column ref arg -> select to_json("data") as "doc" from "person", no params."""
        r = probe["pg_ref"]
        assert (
            r["sql"] == 'select to_json("data") as "doc" from "person"'
        ), f"unexpected ref sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_uses_correct_function_name(self, probe):
        """Must use the scalar to_json( (not json_build_object / json_agg / to_jsonb)."""
        s = probe["pg_ref"]["sql"]
        assert "to_json(" in s, f"missing to_json(): {s!r}"
        assert "to_jsonb(" not in s, f"must use to_json, not to_jsonb: {s!r}"
        assert "json_build_object(" not in s, f"must not use json_build_object: {s!r}"
        assert "json_agg(" not in s, f"must not use json_agg: {s!r}"

    def test_val_argument_is_bound_parameter(self, probe):
        """eb.val(42) -> to_json($1) with 42 collected as a parameter, never inlined."""
        r = probe["pg_val"]
        assert (
            r["sql"] == 'select to_json($1) as "n" from "person"'
        ), f"unexpected val sql: {r['sql']!r}"
        assert r["parameters"] == [42], f"expected [42] params, got {r['parameters']!r}"
        # 42 must NOT be inlined as a literal in the SQL text.
        assert "42" not in r["sql"], f"value was inlined: {r['sql']!r}"

    def test_string_val_argument_is_bound(self, probe):
        """eb.val('hello') -> to_json($1) with 'hello' bound, not inlined as a literal."""
        r = probe["pg_val_str"]
        assert (
            r["sql"] == 'select to_json($1) as "greeting" from "person"'
        ), f"unexpected string-val sql: {r['sql']!r}"
        assert r["parameters"] == ["hello"], f"bad params: {r['parameters']!r}"
        assert "'hello'" not in r["sql"], f"string value was inlined: {r['sql']!r}"

    def test_raw_fragment_emitted_verbatim(self, probe):
        """A raw sql`now()` fragment must be emitted verbatim, with no parameters."""
        r = probe["pg_raw"]
        assert (
            r["sql"] == 'select to_json(now()) as "ts" from "person"'
        ), f"unexpected raw sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"

    def test_exactly_one_argument_no_comma(self, probe):
        """to_json must take exactly one argument: no comma separator inside its parens."""
        for label in ("pg_ref", "pg_val", "pg_raw", "pg_val_str"):
            s = probe[label]["sql"]
            inner = re.search(r"to_json\((.*?)\)\s+as", s)
            assert inner is not None, f"could not parse to_json(...) in {label}: {s!r}"
            arg = inner.group(1)
            assert "," not in arg, (
                f"to_json must have a single argument (no comma) in {label}: {arg!r}"
            )
            assert arg.strip() != "", f"to_json argument empty in {label}: {s!r}"

    def test_single_paren_pair_and_balanced(self, probe):
        """Exactly one `to_json(` call and balanced parentheses for every scenario."""
        for label in ("pg_ref", "pg_val", "pg_raw", "pg_val_str"):
            s = probe[label]["sql"]
            assert s.count("to_json(") == 1, f"expected one to_json( in {label}: {s!r}"
            assert s.count("(") == s.count(")"), f"unbalanced parens in {label}: {s!r}"

    def test_does_not_ignore_input_expression(self, probe):
        """The compiled arg must reflect the actual input (not a hardcoded constant)."""
        # ref('data') -> "data"; ref-based and raw-based outputs must differ from
        # the val-based output, proving the helper consumes its argument.
        ref_arg = re.search(r"to_json\((.*?)\)", probe["pg_ref"]["sql"]).group(1)
        raw_arg = re.search(r"to_json\((.*?)\)", probe["pg_raw"]["sql"]).group(1)
        val_arg = re.search(r"to_json\((.*?)\)", probe["pg_val"]["sql"]).group(1)
        assert ref_arg == '"data"', f"ref arg not rendered from input: {ref_arg!r}"
        assert raw_arg == "now()", f"raw arg not rendered from input: {raw_arg!r}"
        assert val_arg == "$1", f"val arg not rendered as placeholder: {val_arg!r}"
        assert len({ref_arg, raw_arg, val_arg}) == 3, (
            "to_json appears to ignore its input (all args identical): "
            f"{ref_arg!r}, {raw_arg!r}, {val_arg!r}"
        )

    def test_composes_with_other_columns(self, probe):
        """toJson must compose inside a multi-column select without altering them."""
        r = probe["pg_compose"]
        assert (
            r["sql"]
            == 'select "id", "first_name", to_json("data") as "doc" from "person"'
        ), f"unexpected composed sql: {r['sql']!r}"
        assert r["parameters"] == [], f"expected no params, got {r['parameters']!r}"
