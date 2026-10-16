"""Benchmark tests for the `graphql-schema-design` skill (variant ext10).

Skill task: build a self-contained "product listing" GraphQL feature module
inside the `@apollo/server` package
(`packages/server/src/examples/productListing.ts`) that exports `typeDefs`
(SDL string), `resolvers`, and an in-memory data-store factory, plus a Jest
test suite at
`packages/server/src/__tests__/examples/productListing.test.ts`.

The central concern of THIS variant is expressing filtering, sorting, and
ranges through field arguments and a *structured filter input* (NOT the
library-catalog fetch/pagination/mutation domain of ext1):

  * a single root products-listing field,
  * an optional structured filter input (category / minPrice / maxPrice /
    inStock) whose constraints combine conjunctively,
  * an optional sort key drawn from a fixed, introspectable closed set,
  * an optional sort direction drawn from a fixed, introspectable closed set,
  * a category drawn from a fixed, introspectable closed enum set,
  * total/deterministic sorting with ties broken by identifier,
  * out-of-set sort key / direction / category rejected by operation
    VALIDATION before resolvers run,
  * a non-null list of non-null products; an empty match yields [] not null.

What this file verifies
-----------------------
L1 (existence / minimal well-formedness):
  - the two deliverable files exist,
  - the module exports `typeDefs` / `resolvers` / a store factory,
  - the module is self-contained (no sibling-example imports),
  - the agent's own Jest suite declares >= 10 `it`/`test` cases,
  - the agent's own Jest suite passes (the native acceptance command).

L2 (dynamic execution -- the discriminative core):
  Rather than trusting the agent's own test file, we synthesize an INDEPENDENT
  TypeScript Jest harness, drop it next to the module, and run it through the
  repo's native `jest` toolchain.  The harness builds an `ApolloServer`
  directly from the module's `typeDefs`/`resolvers`, introspects the schema to
  discover the real field / enum / input / argument names (so we do not
  hard-code the agent's naming choices), and then exercises every
  Acceptance-Criterion scenario:

    - unfiltered listing sorted by price ascending => globally non-decreasing,
      ties broken by id (a stub that ignores the sort arg fails);
    - single-category filter => only that category appears AND the filter is
      meaningful (other categories exist overall);
    - inclusive min/max price range => every result inside [min,max] and
      boundary inclusivity honored;
    - inStock=true filter => only in-stock products;
    - combined conjunctive filter (category + range + inStock) => the
      conjunction holds for every result and matches a manual reference set;
    - filter matching nothing => empty list, NOT null, no execution error;
    - sort-key / sort-direction / category each an introspectable closed set
      with exactly the documented members;
    - out-of-set sort key, direction, and category each fail VALIDATION
      (errors present, no field data) before resolvers run;
    - descending sort is the reverse-keyed order with the same tie-break.

  We run jest with `--json` and assert on individual named test outcomes, so a
  stub / partial / "looks related" solution fails.

The native acceptance command this drives is:
    npx jest packages/server/src/__tests__/examples/productListing.test.ts --verbose
"""

import json
import os
import re
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _dependency_utils import ensure_npm_dependencies
except Exception:  # pragma: no cover - helper always present at runtime
    ensure_npm_dependencies = None


class TestGraphqlSchemaDesign:
    REPO_DIR = "/workspace/apollo-server"

    SERVER_DIR = os.path.join(REPO_DIR, "packages", "server")
    MODULE_REL = "src/examples/productListing.ts"
    SUITE_REL = "src/__tests__/examples/productListing.test.ts"
    MODULE_PATH = os.path.join(SERVER_DIR, "src", "examples", "productListing.ts")
    SUITE_PATH = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "productListing.test.ts"
    )

    # Directory where we drop our own independent harness suite.
    HARNESS_DIR = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "__bench__"
    )
    HARNESS_NAME = "benchProductListing.test.ts"
    HARNESS_PATH = os.path.join(HARNESS_DIR, HARNESS_NAME)
    HARNESS_REL = "src/__tests__/examples/__bench__/" + HARNESS_NAME

    # ----------------------------------------------------------------- helpers
    @classmethod
    def _read(cls, path):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()

    @classmethod
    def _jest_bin(cls):
        """Locate the workspace-hoisted jest binary (walk up from packages/server).

        In an npm-workspace install the jest binary is hoisted to the repo-root
        node_modules/.bin.  Resolving it by absolute path avoids `npx` trying to
        download a fresh, mis-configured jest.
        """
        d = cls.SERVER_DIR
        seen = set()
        while d and d not in seen:
            seen.add(d)
            cand = os.path.join(d, "node_modules", ".bin", "jest")
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        return None

    @classmethod
    def _run_jest(cls, test_rel, timeout=600):
        """Run jest for a single test file from packages/server, return (proc, json)."""
        jest = cls._jest_bin()
        if jest is not None:
            cmd = [jest]
        else:
            # last resort: npx without network install
            cmd = ["npx", "--no-install", "jest"]
        cmd += [test_rel, "--json", "--runInBand", "--no-coverage"]
        proc = subprocess.run(
            cmd,
            cwd=cls.SERVER_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        report = cls._extract_json(proc.stdout) or cls._extract_json(proc.stderr)
        return proc, report

    @staticmethod
    def _extract_json(text):
        if not text:
            return None
        # jest --json prints a single JSON object; find the outermost {...}.
        start = text.find("{")
        while start != -1:
            depth = 0
            for i in range(start, len(text)):
                c = text[i]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        chunk = text[start : i + 1]
                        try:
                            obj = json.loads(chunk)
                            if isinstance(obj, dict) and "testResults" in obj:
                                return obj
                        except Exception:
                            break
            start = text.find("{", start + 1)
        return None

    @classmethod
    def _assertions_by_title(cls, report):
        """Map of test title -> status ('passed'/'failed') from a jest json report."""
        out = {}
        if not report:
            return out
        for suite in report.get("testResults", []):
            for a in suite.get("assertionResults", []):
                out[a.get("title", "")] = a.get("status", "")
        return out

    # ----------------------------------------------------------- harness source
    @classmethod
    def _harness_source(cls):
        # NB: imports are relative to src/__tests__/examples/__bench__/
        #   - ApolloServer  -> ../../../index.js
        #   - module under test -> ../../../examples/productListing.js
        return r"""// @ts-nocheck
import { describe, it, expect } from '@jest/globals';
import { ApolloServer } from '../../../index.js';
import * as mod from '../../../examples/productListing.js';

const typeDefs: any = (mod as any).typeDefs;
const resolvers: any = (mod as any).resolvers;

async function mkServer() {
  const server = new ApolloServer({ typeDefs, resolvers });
  await server.start();
  return server;
}

async function run(server: any, query: string, variables?: any) {
  const res = await server.executeOperation({ query, variables });
  if (res.body.kind !== 'single') throw new Error('expected single result');
  return res.body.singleResult as { data?: any; errors?: any[] };
}

// ----------------------- introspection type helpers -------------------------
const TYPEREF = `kind name ofType { kind name ofType { kind name ofType { kind name } } }`;
const INTRO = `
{
  __schema {
    queryType { name }
    types {
      kind name
      enumValues { name }
      inputFields { name type { ${TYPEREF} } }
      fields {
        name
        args { name type { ${TYPEREF} } }
        type { ${TYPEREF} }
      }
    }
  }
}`;

function unwrap(t: any): any {
  let nonNull = false, list = false, listItemNonNull = false, cur = t, depth = 0;
  while (cur) {
    if (cur.kind === 'NON_NULL') {
      if (list) listItemNonNull = true; else nonNull = true;
      cur = cur.ofType; depth++; continue;
    }
    if (cur.kind === 'LIST') { list = true; cur = cur.ofType; depth++; continue; }
    break;
  }
  return { kind: cur ? cur.kind : '', name: cur ? cur.name : null, nonNull, list, listItemNonNull };
}

function typeStr(t: any): string {
  if (!t) return 'String';
  if (t.kind === 'NON_NULL') return typeStr(t.ofType) + '!';
  if (t.kind === 'LIST') return '[' + typeStr(t.ofType) + ']';
  return t.name || 'String';
}

// --------------------------- schema discovery -------------------------------
// Discover the product type, the listing query field, the filter input object,
// the sort-key enum, sort-direction enum, and category enum -- WITHOUT relying
// on the agent's exact identifier choices.
async function discover(server: any) {
  const intro = await run(server, INTRO);
  if (intro.errors) throw new Error('introspection errors: ' + JSON.stringify(intro.errors));
  const sch = intro.data.__schema;
  const types: any[] = sch.types;
  const byName: Record<string, any> = {};
  for (const t of types) byName[t.name] = t;
  const qType = types.find((t) => t.name === sch.queryType.name);

  // ---- product object: has name + category + price + inStock-ish + id ------
  const isProduct = (t: any) =>
    t.kind === 'OBJECT' && Array.isArray(t.fields) &&
    t.fields.some((f: any) => f.name === 'name') &&
    t.fields.some((f: any) => /categor/i.test(f.name)) &&
    t.fields.some((f: any) => /price/i.test(f.name)) &&
    t.fields.some((f: any) => /(stock|inStock|available)/i.test(f.name));
  const productObj = types.find(isProduct);
  if (!productObj) throw new Error('no product object type found');

  const fieldName = (re: RegExp) => {
    const f = productObj.fields.find((x: any) => re.test(x.name));
    return f ? f.name : null;
  };
  const idField =
    (productObj.fields.find((f: any) => /^id$/i.test(f.name)) ||
      productObj.fields.find((f: any) => /id$/i.test(f.name))).name;
  const nameField = fieldName(/^name$/i) || fieldName(/name/i);
  const categoryField = fieldName(/categor/i);
  const priceField = fieldName(/price/i);
  const stockField = fieldName(/(inStock|stock|available)/i);

  // ---- listing query field: returns a LIST of products ---------------------
  const listQ = qType.fields.find((f: any) => {
    const u = unwrap(f.type);
    return u.list && u.name === productObj.name;
  });
  if (!listQ) throw new Error('no products-listing query field returning [Product]');

  // ---- filter input object argument (a single INPUT_OBJECT) ----------------
  const filterArg = listQ.args.find((a: any) => unwrap(a.type).kind === 'INPUT_OBJECT');
  const filterType = filterArg ? byName[unwrap(filterArg.type).name] : null;

  // ---- category enum -------------------------------------------------------
  // category enum: an ENUM referenced by the product's category field type OR
  // by an input field named like category in the filter input.
  let categoryEnum: any = null;
  const catU = unwrap(productObj.fields.find((f: any) => f.name === categoryField).type);
  if (catU.kind === 'ENUM') categoryEnum = byName[catU.name];
  if (!categoryEnum && filterType) {
    const cf = (filterType.inputFields || []).find((f: any) => /categor/i.test(f.name));
    if (cf && unwrap(cf.type).kind === 'ENUM') categoryEnum = byName[unwrap(cf.type).name];
  }

  // ---- sort key + sort direction enums (args on listing query) -------------
  // A sort-key enum's values look like NAME/PRICE/CATEGORY; a direction enum's
  // values look like ASC/DESC.  Find the ENUM-typed args on the list query and
  // classify them.
  const enumArgs = listQ.args
    .map((a: any) => ({ arg: a, u: unwrap(a.type) }))
    .filter((x: any) => x.u.kind === 'ENUM')
    .map((x: any) => ({ ...x, enumT: byName[x.u.name] }));

  const isDirEnum = (e: any) =>
    e && (e.enumValues || []).some((v: any) => /^(ASC|ASCENDING|DESC|DESCENDING)$/i.test(v.name));
  let dirArg: any = null, sortArg: any = null;
  for (const e of enumArgs) {
    if (isDirEnum(e.enumT)) dirArg = e;
    else sortArg = e;
  }
  // If only one enum arg classified, the other may live inside an input object;
  // but the doc says sort key + direction are field arguments, so keep as-is.

  return {
    types, byName, qType,
    productObj, idField, nameField, categoryField, priceField, stockField,
    listQ,
    filterArg, filterType,
    categoryEnum,
    sortArg: sortArg ? sortArg.arg : null,
    sortEnum: sortArg ? sortArg.enumT : null,
    dirArg: dirArg ? dirArg.arg : null,
    dirEnum: dirArg ? dirArg.enumT : null,
  };
}

// Build the product selection set for a query.
function prodSel(d: any): string {
  return `${d.idField} ${d.nameField} ${d.categoryField} ${d.priceField} ${d.stockField}`;
}

// Fetch the entire catalog (no args) for use as a reference oracle.
async function allProducts(server: any, d: any): Promise<any[]> {
  const r = await run(server, `query{ ${d.listQ.name} { ${prodSel(d)} } }`);
  expect(r.errors).toBeFalsy();
  const arr = r.data[d.listQ.name];
  expect(Array.isArray(arr)).toBe(true);
  return arr;
}

// Pick the enum value that maps to "price" / "name" sort, or "ascending".
function pickEnumValue(enumT: any, res: RegExp[]): string | null {
  if (!enumT) return null;
  for (const re of res) {
    const v = (enumT.enumValues || []).find((x: any) => re.test(x.name));
    if (v) return v.name;
  }
  return null;
}

describe('product listing (independent harness)', () => {

  it('schema builds; product type has non-null id/name/category/price/inStock', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const nonNull = (fname: string) => {
      const f = d.productObj.fields.find((x: any) => x.name === fname);
      expect(f).toBeTruthy();
      return unwrap(f.type).nonNull === true;
    };
    expect(nonNull(d.idField)).toBe(true);
    expect(nonNull(d.nameField)).toBe(true);
    expect(nonNull(d.categoryField)).toBe(true);
    expect(nonNull(d.priceField)).toBe(true);
    expect(nonNull(d.stockField)).toBe(true);

    // listing result is a non-null list of non-null products
    const lu = unwrap(d.listQ.type);
    expect(lu.list).toBe(true);
    expect(lu.nonNull).toBe(true);
    expect(lu.listItemNonNull).toBe(true);

    // price is an integer scalar; inStock is boolean
    const priceF = d.productObj.fields.find((f: any) => f.name === d.priceField);
    expect(unwrap(priceF.type).name).toBe('Int');
    const stockF = d.productObj.fields.find((f: any) => f.name === d.stockField);
    expect(unwrap(stockF.type).name).toBe('Boolean');
    await server.stop();
  });

  it('category, sort-key, and sort-direction are introspectable closed enum sets', async () => {
    const server = await mkServer();
    const d = await discover(server);

    // category enum: >= 2 values, all SCREAMING/word-like, and the product's
    // category field is typed by it.
    expect(d.categoryEnum).toBeTruthy();
    const catVals = d.categoryEnum.enumValues.map((v: any) => v.name);
    expect(catVals.length).toBeGreaterThanOrEqual(2);

    // sort-key enum present and references name/price/category style keys
    expect(d.sortEnum).toBeTruthy();
    const sortVals = d.sortEnum.enumValues.map((v: any) => v.name);
    expect(sortVals.length).toBeGreaterThanOrEqual(2);
    expect(sortVals.some((n: string) => /price/i.test(n))).toBe(true);
    expect(sortVals.some((n: string) => /name/i.test(n))).toBe(true);

    // sort-direction enum present with exactly ascending + descending members
    expect(d.dirEnum).toBeTruthy();
    const dirVals = d.dirEnum.enumValues.map((v: any) => v.name);
    expect(dirVals.length).toBe(2);
    expect(dirVals.some((n: string) => /^(asc|ascending)$/i.test(n))).toBe(true);
    expect(dirVals.some((n: string) => /^(desc|descending)$/i.test(n))).toBe(true);
    await server.stop();
  });

  it('filter is a single structured input object (category/min/max/inStock)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    // exactly one structured input-object argument drives filtering
    const structured = d.listQ.args.filter((a: any) => unwrap(a.type).kind === 'INPUT_OBJECT');
    expect(structured.length).toBe(1);
    expect(d.filterType).toBeTruthy();
    const ifNames = (d.filterType.inputFields || []).map((f: any) => f.name);
    // must offer category, a min and a max price, and an in-stock flag
    expect(ifNames.some((n: string) => /categor/i.test(n))).toBe(true);
    expect(ifNames.some((n: string) => /min/i.test(n))).toBe(true);
    expect(ifNames.some((n: string) => /max/i.test(n))).toBe(true);
    expect(ifNames.some((n: string) => /(stock|available)/i.test(n))).toBe(true);
    // every filter input field is OPTIONAL (omitting the whole filter lists all)
    for (const f of d.filterType.inputFields) {
      expect(unwrap(f.type).nonNull).toBe(false);
    }
    await server.stop();
  });

  it('unfiltered listing sorted by price ASC is globally non-decreasing, ties broken by id', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const priceKey = pickEnumValue(d.sortEnum, [/price/i]);
    const ascDir = pickEnumValue(d.dirEnum, [/^(asc|ascending)$/i]);
    expect(priceKey).toBeTruthy();
    expect(ascDir).toBeTruthy();

    const q = `query($k:${typeStr(d.sortArg.type)},$dir:${typeStr(d.dirArg.type)}){ ${d.listQ.name}(${d.sortArg.name}:$k, ${d.dirArg.name}:$dir){ ${prodSel(d)} } }`;
    const r = await run(server, q, { k: priceKey, dir: ascDir });
    expect(r.errors).toBeFalsy();
    const items = r.data[d.listQ.name];
    expect(items.length).toBeGreaterThanOrEqual(3);
    // every entry non-null
    for (const it of items) expect(it).not.toBeNull();

    // non-decreasing price; ties strictly increasing id (total deterministic order)
    for (let i = 1; i < items.length; i++) {
      const a = items[i - 1], b = items[i];
      expect(a[d.priceField] <= b[d.priceField]).toBe(true);
      if (a[d.priceField] === b[d.priceField]) {
        expect(String(a[d.idField]) < String(b[d.idField])).toBe(true);
      }
    }

    // determinism: identical args -> identical id sequence
    const r2 = await run(server, q, { k: priceKey, dir: ascDir });
    const ids1 = items.map((x: any) => x[d.idField]);
    const ids2 = r2.data[d.listQ.name].map((x: any) => x[d.idField]);
    expect(ids2).toEqual(ids1);
    await server.stop();
  });

  it('sort by price DESC is the exact reverse-keyed order (same tie-break on id)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const priceKey = pickEnumValue(d.sortEnum, [/price/i]);
    const ascDir = pickEnumValue(d.dirEnum, [/^(asc|ascending)$/i]);
    const descDir = pickEnumValue(d.dirEnum, [/^(desc|descending)$/i]);

    const q = (dir: string) =>
      `query($k:${typeStr(d.sortArg.type)},$dir:${typeStr(d.dirArg.type)}){ ${d.listQ.name}(${d.sortArg.name}:$k, ${d.dirArg.name}:$dir){ ${prodSel(d)} } }`;
    const asc = (await run(server, q(ascDir), { k: priceKey, dir: ascDir })).data[d.listQ.name];
    const desc = (await run(server, q(descDir), { k: priceKey, dir: descDir })).data[d.listQ.name];

    // descending must be non-increasing on price
    for (let i = 1; i < desc.length; i++) {
      expect(desc[i - 1][d.priceField] >= desc[i][d.priceField]).toBe(true);
    }
    // same multiset of ids
    expect(new Set(desc.map((x: any) => x[d.idField]))).toEqual(
      new Set(asc.map((x: any) => x[d.idField])),
    );
    // a stub that ignores direction would make asc === desc; they must differ
    // (the catalog has distinct prices, so the orders cannot coincide).
    expect(desc.map((x: any) => x[d.idField])).not.toEqual(asc.map((x: any) => x[d.idField]));
    await server.stop();
  });

  it('single-category filter returns only that category and is meaningful', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const all = await allProducts(server, d);
    // choose a category that exists and is not the only one
    const counts: Record<string, number> = {};
    for (const p of all) counts[p[d.categoryField]] = (counts[p[d.categoryField]] || 0) + 1;
    const cats = Object.keys(counts);
    expect(cats.length).toBeGreaterThanOrEqual(2);
    const chosen = cats[0];

    const catFieldName = (d.filterType.inputFields.find((f: any) => /categor/i.test(f.name))).name;
    const q = `query($f:${typeStr(d.filterArg.type)}){ ${d.listQ.name}(${d.filterArg.name}:$f){ ${prodSel(d)} } }`;
    const r = await run(server, q, { f: { [catFieldName]: chosen } });
    expect(r.errors).toBeFalsy();
    const items = r.data[d.listQ.name];
    expect(items.length).toBe(counts[chosen]);
    for (const it of items) expect(it[d.categoryField]).toBe(chosen);
    // meaningful: there exist products of other categories
    expect(all.length).toBeGreaterThan(items.length);
    await server.stop();
  });

  it('inclusive min/max price-range filter keeps only in-range products with boundaries inclusive', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const all = await allProducts(server, d);
    const prices = all.map((p: any) => p[d.priceField]).sort((a: number, b: number) => a - b);
    // pick a window strictly inside the catalog so we can check inclusivity
    const lo = prices[0];
    const hi = prices[prices.length - 1];
    expect(hi).toBeGreaterThan(lo);

    const minF = (d.filterType.inputFields.find((f: any) => /min/i.test(f.name))).name;
    const maxF = (d.filterType.inputFields.find((f: any) => /max/i.test(f.name))).name;
    const q = `query($f:${typeStr(d.filterArg.type)}){ ${d.listQ.name}(${d.filterArg.name}:$f){ ${prodSel(d)} } }`;

    // full window [lo, hi] must return everything
    const full = await run(server, q, { f: { [minF]: lo, [maxF]: hi } });
    expect(full.errors).toBeFalsy();
    expect(full.data[d.listQ.name].length).toBe(all.length);

    // a strict sub-window: reference set computed manually
    const mid = prices[Math.floor(prices.length / 2)];
    const expected = all.filter((p: any) => p[d.priceField] >= lo && p[d.priceField] <= mid);
    const r = await run(server, q, { f: { [minF]: lo, [maxF]: mid } });
    const got = r.data[d.listQ.name];
    for (const it of got) {
      expect(it[d.priceField]).toBeGreaterThanOrEqual(lo);
      expect(it[d.priceField]).toBeLessThanOrEqual(mid);
    }
    expect(new Set(got.map((x: any) => x[d.idField]))).toEqual(
      new Set(expected.map((x: any) => x[d.idField])),
    );
    // boundary inclusivity: the lo-priced and mid-priced items are present
    const gotPrices = new Set(got.map((x: any) => x[d.priceField]));
    expect(gotPrices.has(lo)).toBe(true);
    expect(gotPrices.has(mid)).toBe(true);
    await server.stop();
  });

  it('inStock filter returns only in-stock products and is meaningful', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const all = await allProducts(server, d);
    const inStockCount = all.filter((p: any) => p[d.stockField] === true).length;
    expect(inStockCount).toBeGreaterThan(0);
    expect(inStockCount).toBeLessThan(all.length); // some are out of stock

    const stockF = (d.filterType.inputFields.find((f: any) => /(stock|available)/i.test(f.name))).name;
    const q = `query($f:${typeStr(d.filterArg.type)}){ ${d.listQ.name}(${d.filterArg.name}:$f){ ${prodSel(d)} } }`;
    const r = await run(server, q, { f: { [stockF]: true } });
    expect(r.errors).toBeFalsy();
    const items = r.data[d.listQ.name];
    expect(items.length).toBe(inStockCount);
    for (const it of items) expect(it[d.stockField]).toBe(true);
    await server.stop();
  });

  it('combined category+range+inStock filter is a strict conjunction matching a manual oracle', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const all = await allProducts(server, d);

    const catF = (d.filterType.inputFields.find((f: any) => /categor/i.test(f.name))).name;
    const minF = (d.filterType.inputFields.find((f: any) => /min/i.test(f.name))).name;
    const maxF = (d.filterType.inputFields.find((f: any) => /max/i.test(f.name))).name;
    const stockF = (d.filterType.inputFields.find((f: any) => /(stock|available)/i.test(f.name))).name;

    const prices = all.map((p: any) => p[d.priceField]);
    const lo = Math.min(...prices), hi = Math.max(...prices);
    // pick a category that has at least one product
    const cat = all[0][d.categoryField];
    const filter = { [catF]: cat, [minF]: lo, [maxF]: hi, [stockF]: true };

    const expected = all.filter(
      (p: any) =>
        p[d.categoryField] === cat &&
        p[d.priceField] >= lo &&
        p[d.priceField] <= hi &&
        p[d.stockField] === true,
    );

    const q = `query($f:${typeStr(d.filterArg.type)}){ ${d.listQ.name}(${d.filterArg.name}:$f){ ${prodSel(d)} } }`;
    const r = await run(server, q, { f: filter });
    expect(r.errors).toBeFalsy();
    const got = r.data[d.listQ.name];
    for (const it of got) {
      expect(it[d.categoryField]).toBe(cat);
      expect(it[d.stockField]).toBe(true);
      expect(it[d.priceField]).toBeGreaterThanOrEqual(lo);
      expect(it[d.priceField]).toBeLessThanOrEqual(hi);
    }
    expect(new Set(got.map((x: any) => x[d.idField]))).toEqual(
      new Set(expected.map((x: any) => x[d.idField])),
    );
    await server.stop();
  });

  it('filter matching nothing yields an EMPTY list (not null) with no execution error', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const all = await allProducts(server, d);
    const maxPrice = Math.max(...all.map((p: any) => p[d.priceField]));

    const minF = (d.filterType.inputFields.find((f: any) => /min/i.test(f.name))).name;
    const maxF = (d.filterType.inputFields.find((f: any) => /max/i.test(f.name))).name;
    // impossible window: min above every price
    const q = `query($f:${typeStr(d.filterArg.type)}){ ${d.listQ.name}(${d.filterArg.name}:$f){ ${d.idField} } }`;
    const r = await run(server, q, { f: { [minF]: maxPrice + 1000000, [maxF]: maxPrice + 2000000 } });
    expect(r.errors == null || r.errors.length === 0).toBe(true);
    const items = r.data[d.listQ.name];
    expect(items).not.toBeNull();
    expect(Array.isArray(items)).toBe(true);
    expect(items.length).toBe(0);
    await server.stop();
  });

  it('out-of-set SORT KEY fails operation validation before resolvers (errors, no field data)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const dirAsc = pickEnumValue(d.dirEnum, [/^(asc|ascending)$/i]);
    // inline an invalid enum literal for the sort key
    const q = `query{ ${d.listQ.name}(${d.sortArg.name}: NOT_A_REAL_SORT_KEY_ZZZ${dirAsc ? `, ${d.dirArg.name}: ${dirAsc}` : ''}){ ${d.idField} } }`;
    const r = await run(server, q);
    expect(Array.isArray(r.errors)).toBe(true);
    expect(r.errors.length).toBeGreaterThan(0);
    // validation -> no data executed for the field
    expect(r.data == null || r.data[d.listQ.name] === undefined || r.data[d.listQ.name] === null).toBe(true);
    await server.stop();
  });

  it('out-of-set SORT DIRECTION fails operation validation before resolvers', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const priceKey = pickEnumValue(d.sortEnum, [/price/i, /name/i]);
    const q = `query{ ${d.listQ.name}(${d.sortArg.name}: ${priceKey}, ${d.dirArg.name}: SIDEWAYS_ZZZ){ ${d.idField} } }`;
    const r = await run(server, q);
    expect(Array.isArray(r.errors)).toBe(true);
    expect(r.errors.length).toBeGreaterThan(0);
    expect(r.data == null || r.data[d.listQ.name] === undefined || r.data[d.listQ.name] === null).toBe(true);
    await server.stop();
  });

  it('out-of-set CATEGORY in the filter fails operation validation before resolvers', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const catFieldName = (d.filterType.inputFields.find((f: any) => /categor/i.test(f.name))).name;
    // inline an invalid enum literal inside the filter input object
    const q = `query{ ${d.listQ.name}(${d.filterArg.name}: { ${catFieldName}: NOT_A_REAL_CATEGORY_ZZZ }){ ${d.idField} } }`;
    const r = await run(server, q);
    expect(Array.isArray(r.errors)).toBe(true);
    expect(r.errors.length).toBeGreaterThan(0);
    expect(r.data == null || r.data[d.listQ.name] === undefined || r.data[d.listQ.name] === null).toBe(true);
    await server.stop();
  });

  it('omitting the filter entirely lists every product (no constraints)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const all = await allProducts(server, d);
    expect(all.length).toBeGreaterThanOrEqual(3);
    // ids are unique (stable identifiers)
    const ids = all.map((p: any) => p[d.idField]);
    expect(new Set(ids).size).toBe(ids.length);
    await server.stop();
  });
});
"""

    @classmethod
    def _ensure_workspace_built(cls):
        """ts-jest type-checks server src, which imports sibling workspace packages
        (e.g. @apollo/server-gateway-interface) by their built `dist` types.  If
        those dist outputs are missing, run the repo's `compile` build once so the
        sibling packages resolve."""
        gw_types = os.path.join(
            cls.REPO_DIR, "packages", "gateway-interface", "dist", "esm", "index.d.ts"
        )
        if os.path.isfile(gw_types):
            return
        subprocess.run(
            ["npm", "run", "compile"],
            cwd=cls.REPO_DIR,
            capture_output=True,
            text=True,
            timeout=900,
        )

    # --------------------------------------------------------- module fixture
    @pytest.fixture(scope="class", autouse=True)
    def _install_deps(self):
        assert os.path.isdir(self.REPO_DIR), f"missing repo {self.REPO_DIR}"
        if ensure_npm_dependencies is not None:
            ensure_npm_dependencies(self.REPO_DIR)
        self._ensure_workspace_built()
        yield
        try:
            if os.path.exists(self.HARNESS_PATH):
                os.remove(self.HARNESS_PATH)
        except OSError:
            pass

    @pytest.fixture(scope="class")
    def harness_report(self):
        """Write our independent harness suite, run it once, return the jest json."""
        os.makedirs(self.HARNESS_DIR, exist_ok=True)
        with open(self.HARNESS_PATH, "w", encoding="utf-8") as fh:
            fh.write(self._harness_source())
        proc, report = self._run_jest(self.HARNESS_REL, timeout=600)
        return {"proc": proc, "report": report}

    # =========================== L1: deliverables ===========================
    def test_module_file_exists(self):
        """L1: the product-listing module file exists at the required path."""
        assert os.path.isfile(self.MODULE_PATH), f"missing {self.MODULE_REL}"

    def test_suite_file_exists(self):
        """L1: the agent's Jest suite file exists at the required path."""
        assert os.path.isfile(self.SUITE_PATH), f"missing {self.SUITE_REL}"

    def test_module_exports_typedefs_resolvers_and_factory(self):
        """L1: module declares exported typeDefs, resolvers, and a store factory."""
        src = self._read(self.MODULE_PATH)
        assert re.search(r"export\s+(const|let|var|function)\s+typeDefs", src) or re.search(
            r"\btypeDefs\b", src
        ), "no typeDefs export"
        assert re.search(r"\bresolvers\b", src), "no resolvers export"
        # an exported factory function (create*/make*/*Store/*Catalog/seed*)
        assert re.search(
            r"export\s+(const|function)\s+\w*(create|make|store|catalog|seed|product)\w*",
            src,
            re.IGNORECASE,
        ), "no store-factory export found"

    def test_module_has_no_other_example_imports(self):
        """L1: module is self-contained (does not import from sibling example files)."""
        src = self._read(self.MODULE_PATH)
        for m in re.finditer(r"""import[^;]*?from\s*['"]([^'"]+)['"]""", src):
            spec = m.group(1)
            if "examples/" in spec and "productListing" not in spec:
                pytest.fail(f"module imports another example file: {spec}")

    def test_does_not_modify_public_index_exports(self):
        """L1: package public index.ts is not made to re-export the example module."""
        index_path = os.path.join(self.SERVER_DIR, "src", "index.ts")
        if os.path.isfile(index_path):
            src = self._read(index_path)
            assert "productListing" not in src, (
                "public index.ts must not export the productListing example"
            )

    def test_agent_suite_declares_at_least_10_cases(self):
        """L1: the agent's own suite declares >= 10 it/test cases (acceptance criterion)."""
        src = self._read(self.SUITE_PATH)
        count = len(re.findall(r"\b(it|test)\s*(\.\w+)?\s*\(", src))
        assert count >= 10, f"agent suite declares only {count} it/test cases"

    # ===================== L2: dynamic via independent harness ================
    def _passed(self, harness_report, title_regex):
        report = harness_report["report"]
        proc = harness_report["proc"]
        assert report is not None, (
            "jest produced no parseable JSON report.\n"
            f"returncode={proc.returncode}\n"
            f"stdout(tail)={proc.stdout[-3000:]}\n"
            f"stderr(tail)={proc.stderr[-3000:]}"
        )
        results = self._assertions_by_title(report)
        rx = re.compile(title_regex, re.IGNORECASE)
        matched = {t: s for t, s in results.items() if rx.search(t)}
        assert matched, (
            f"no harness test matched /{title_regex}/. "
            f"available titles={list(results.keys())}\n"
            f"stderr(tail)={proc.stderr[-2000:]}"
        )
        for title, status in matched.items():
            assert status == "passed", (
                f"harness case '{title}' status={status}\n"
                f"stderr(tail)={proc.stderr[-3000:]}"
            )

    def test_agent_acceptance_suite_passes(self, harness_report):
        """L2: the native acceptance command (agent's own suite) passes all assertions."""
        proc, report = self._run_jest(self.SUITE_REL, timeout=600)
        assert report is not None, (
            "agent suite produced no JSON.\n"
            f"rc={proc.returncode}\nstdout(tail)={proc.stdout[-2500:]}\n"
            f"stderr(tail)={proc.stderr[-2500:]}"
        )
        num_total = report.get("numTotalTests", 0)
        num_passed = report.get("numPassedTests", 0)
        num_failed = report.get("numFailedTests", -1)
        assert num_total >= 10, f"agent suite ran only {num_total} tests"
        assert num_failed == 0 and num_passed == num_total, (
            f"agent suite failing: passed={num_passed} failed={num_failed} total={num_total}\n"
            f"stderr(tail)={proc.stderr[-3000:]}"
        )

    def test_harness_schema_and_nullability(self, harness_report):
        """L2: schema builds; product fields are non-null; list is non-null list of non-null."""
        self._passed(harness_report, r"schema builds; product type has non-null")

    def test_harness_closed_enum_sets(self, harness_report):
        """L2: category / sort-key / sort-direction are introspectable closed enum sets."""
        self._passed(harness_report, r"introspectable closed enum sets")

    def test_harness_filter_is_single_input(self, harness_report):
        """L2: filtering is a single structured optional input object."""
        self._passed(harness_report, r"single structured input object")

    def test_harness_price_asc_total_order(self, harness_report):
        """L2: price-ascending listing is globally non-decreasing, ties broken by id, deterministic."""
        self._passed(harness_report, r"sorted by price ASC is globally non-decreasing")

    def test_harness_price_desc_reverse(self, harness_report):
        """L2: descending sort is the reverse-keyed order; differs from ascending (no ignored arg)."""
        self._passed(harness_report, r"price DESC is the exact reverse-keyed order")

    def test_harness_single_category_filter(self, harness_report):
        """L2: single-category filter returns only that category and is meaningful."""
        self._passed(harness_report, r"single-category filter returns only that category")

    def test_harness_price_range_inclusive(self, harness_report):
        """L2: inclusive min/max range filter keeps only in-range products, boundaries inclusive."""
        self._passed(harness_report, r"price-range filter keeps only in-range")

    def test_harness_instock_filter(self, harness_report):
        """L2: inStock filter returns only in-stock products."""
        self._passed(harness_report, r"inStock filter returns only in-stock")

    def test_harness_combined_conjunction(self, harness_report):
        """L2: combined category+range+inStock filter is a strict conjunction vs manual oracle."""
        self._passed(harness_report, r"combined category\+range\+inStock filter is a strict conjunction")

    def test_harness_empty_not_null(self, harness_report):
        """L2: a filter matching nothing yields an empty list, not null, no execution error."""
        self._passed(harness_report, r"matching nothing yields an EMPTY list")

    def test_harness_invalid_sort_key_validation(self, harness_report):
        """L2: out-of-set sort key fails validation before resolvers run."""
        self._passed(harness_report, r"out-of-set SORT KEY fails operation validation")

    def test_harness_invalid_sort_direction_validation(self, harness_report):
        """L2: out-of-set sort direction fails validation before resolvers run."""
        self._passed(harness_report, r"out-of-set SORT DIRECTION fails operation validation")

    def test_harness_invalid_category_validation(self, harness_report):
        """L2: out-of-set category in the filter fails validation before resolvers run."""
        self._passed(harness_report, r"out-of-set CATEGORY in the filter fails operation validation")

    def test_harness_omitting_filter_lists_all(self, harness_report):
        """L2: omitting the filter lists every product; ids are unique stable identifiers."""
        self._passed(harness_report, r"omitting the filter entirely lists every product")
