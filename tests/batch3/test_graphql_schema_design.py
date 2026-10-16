"""Benchmark tests for the `graphql-schema-design` skill (variant: ext3).

Skill task (ext3): build a self-contained "warehouse inventory" GraphQL feature
module inside the `@apollo/server` package
(`packages/server/src/examples/inventoryService.ts`) that exports `typeDefs`
(SDL string), `resolvers`, and an in-memory data-store factory, plus a Jest
suite at `packages/server/src/__tests__/examples/inventoryService.test.ts`.

The domain models **stock items**. Each item has a stable server-assigned id, a
name, a unit price expressed as a *domain-specific money scalar* (not a bare
Int/Float/String), an availability state drawn from a closed set of exactly four
values (in stock / low stock / out of stock / discontinued), and a non-negative
quantity on hand.  The root query fetches a single item by id (miss -> null, no
error) and lists items optionally filtered by availability.  A mutation adjusts
an existing item's quantity by a signed delta via a SINGLE structured input
argument, recomputing availability from the resulting quantity (0 -> out of
stock; otherwise in stock unless already discontinued), and reports
item-not-found / would-go-negative outcomes through the returned PAYLOAD (not the
top-level `errors` array).

What this file verifies
-----------------------
L1 (existence / minimal well-formedness):
  - the two deliverable files exist,
  - the module exports `typeDefs` / `resolvers` / a store factory,
  - the module is self-contained (no sibling-example imports),
  - the public package `index.ts` was not modified to re-export the module,
  - the agent's own Jest suite declares >= 10 `it`/`test` cases,
  - the agent's own Jest suite passes (acceptance command).

L2 (dynamic execution -- the discriminative core):
  Instead of trusting the agent's own test file, we synthesize an INDEPENDENT
  TypeScript Jest harness, drop it next to the module, and run it through the
  repo's native `jest` toolchain.  The harness builds an `ApolloServer` directly
  from the module's `typeDefs`/`resolvers`, introspects the schema to discover
  the real field / enum / scalar / argument names (so we do not hard-code the
  agent's naming choices), and then exercises every Acceptance-Criterion
  scenario:
    * schema builds; an Item object has a non-null stable id distinct from name,
      a non-null quantity (Int), a non-null availability enum, and a price field
      whose named type is a custom scalar (NOT Int/Float/String/Boolean/ID);
    * the availability enum is introspectable and holds EXACTLY four values
      covering in-stock / low-stock / out-of-stock / discontinued;
    * single-item fetch HIT returns matching seed fields; MISS -> null, no error;
    * list filtered by OUT_OF_STOCK returns only out-of-stock items and the
      filter is meaningful (more items overall);
    * an availability value outside the fixed set fails VALIDATION before
      resolvers run (populated errors, no data for the field);
    * a malformed money literal on input fails before resolvers run;
    * two seeded items priced identically read back equal price scalars;
    * adjust-quantity takes a SINGLE structured input-object argument;
    * adjusting an item's quantity to zero flips availability to out-of-stock in
      the returned payload, and the change persists on refetch;
    * adjusting a NON-EXISTENT item, and driving quantity NEGATIVE, are both
      reported through the payload while the top-level `errors` array stays empty.

We run jest with `--json` and assert on individual named test outcomes, so a
stub / partial / "looks related" solution fails.
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
    MODULE_REL = "src/examples/inventoryService.ts"
    SUITE_REL = "src/__tests__/examples/inventoryService.test.ts"
    MODULE_PATH = os.path.join(SERVER_DIR, "src", "examples", "inventoryService.ts")
    SUITE_PATH = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "inventoryService.test.ts"
    )
    INDEX_PATH = os.path.join(SERVER_DIR, "src", "index.ts")

    # Directory where we drop our own independent harness suite.
    HARNESS_DIR = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "__bench__"
    )
    HARNESS_NAME = "benchInventoryService.test.ts"
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
        #   - module under test -> ../../../examples/inventoryService.js
        return r"""// @ts-nocheck
import { describe, it, expect } from '@jest/globals';
import { ApolloServer } from '../../../index.js';
import * as mod from '../../../examples/inventoryService.js';

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

// ---------- type unwrapping / introspection helpers -------------------------
function unwrap(t: any): any {
  let nonNull = false, list = false, cur = t;
  while (cur) {
    if (cur.kind === 'NON_NULL') { nonNull = true; cur = cur.ofType; continue; }
    if (cur.kind === 'LIST') { list = true; cur = cur.ofType; continue; }
    break;
  }
  return { kind: cur ? cur.kind : '', name: cur ? cur.name : null, nonNull, list };
}
function unwrapTopName(t: any): string {
  if (!t) return 'ID';
  if (t.kind === 'NON_NULL') return unwrapTopName(t.ofType) + '!';
  if (t.kind === 'LIST') return '[' + unwrapTopName(t.ofType) + ']';
  return t.name || 'ID';
}

const TYPEREF = `kind name ofType { kind name ofType { kind name ofType { kind name } } }`;
const INTRO = `
{
  __schema {
    queryType { name }
    mutationType { name }
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

const SCALAR_BUILTINS = new Set(['Int', 'Float', 'String', 'Boolean', 'ID']);

async function introspect(server: any) {
  const intro = await run(server, INTRO);
  expect(intro.errors).toBeFalsy();
  return intro.data.__schema;
}

// Discover the availability ENUM: an enum whose value names cover the four
// closed states (in stock / low stock / out of stock / discontinued).
function findAvailabilityEnum(types: any[]): any {
  const reDisc = /(discontinu)/i;
  const reOut = /(out.?of.?stock|out_of_stock|outofstock|sold.?out)/i;
  const reLow = /(low.?stock|low_stock|lowstock|low)/i;
  const reIn = /(in.?stock|in_stock|instock|available)/i;
  for (const t of types) {
    if (t.kind !== 'ENUM' || !Array.isArray(t.enumValues)) continue;
    const names = t.enumValues.map((v: any) => v.name);
    const joined = names.join(' ');
    if (reDisc.test(joined) && reOut.test(joined) && reLow.test(joined) && reIn.test(joined)) {
      return { type: t, names };
    }
  }
  return null;
}
function availValue(names: string[], re: RegExp): string | null {
  return names.find((n) => re.test(n)) || null;
}

// Discover the Item OBJECT: an object that has a name field, a quantity-ish
// Int field, an availability-enum field, and a price field typed as a custom
// scalar.
function findItemObject(types: any[], availEnumName: string): any {
  for (const t of types) {
    if (t.kind !== 'OBJECT' || !Array.isArray(t.fields)) continue;
    if (t.name.startsWith('__')) continue;
    const hasName = t.fields.some((f: any) => /^name$/i.test(f.name));
    const availF = t.fields.find((f: any) => unwrap(f.type).name === availEnumName);
    const qtyF = t.fields.find(
      (f: any) => /(quantity|qty|onHand|stock|count)/i.test(f.name) && unwrap(f.type).name === 'Int',
    );
    const priceF = t.fields.find((f: any) => {
      const u = unwrap(f.type);
      return u.kind === 'SCALAR' && u.name && !SCALAR_BUILTINS.has(u.name) &&
        /(price|cost|amount|money)/i.test(f.name);
    });
    if (hasName && availF && qtyF && priceF) {
      return { type: t, availF, qtyF, priceF, nameF: t.fields.find((f: any) => /^name$/i.test(f.name)) };
    }
  }
  return null;
}
function idFieldOf(obj: any): any {
  return (
    obj.fields.find((f: any) => /^id$/i.test(f.name)) ||
    obj.fields.find((f: any) => /id$/i.test(f.name))
  );
}

// Discover the single-item query (returns Item, takes an id arg) and the list
// query (returns a list of Item).
function findItemQuery(qType: any, itemName: string): any {
  return qType.fields.find((f: any) => {
    const u = unwrap(f.type);
    return u.name === itemName && !u.list && f.args.length >= 1;
  });
}
function findListQuery(qType: any, itemName: string): any {
  return qType.fields.find((f: any) => {
    const u = unwrap(f.type);
    return u.name === itemName && u.list;
  });
}

// Build a full selection over the Item to read back its core fields.
function itemSelection(item: any): string {
  const idF = idFieldOf(item.type).name;
  return `${idF} ${item.nameF.name} ${item.qtyF.name} ${item.availF.name} ${item.priceF.name}`;
}

async function discover(server: any) {
  const sch = await introspect(server);
  const types: any[] = sch.types;
  const qType = types.find((t) => t.name === sch.queryType.name);
  const mType = sch.mutationType ? types.find((t) => t.name === sch.mutationType.name) : null;

  const av = findAvailabilityEnum(types);
  expect(av).toBeTruthy();
  const item = findItemObject(types, av.type.name);
  expect(item).toBeTruthy();

  const itemQ = findItemQuery(qType, item.type.name);
  const listQ = findListQuery(qType, item.type.name);
  expect(itemQ).toBeTruthy();
  expect(listQ).toBeTruthy();

  return {
    types, qType, mType,
    availEnum: av.type, availNames: av.names,
    item, itemId: idFieldOf(item.type).name,
    itemQ, listQ,
  };
}

function extractItems(arr: any): any[] {
  return Array.isArray(arr) ? arr.filter((x: any) => x != null) : [];
}

// Discover the adjust mutation: a mutation returning an OBJECT payload, taking a
// single structured (INPUT_OBJECT) argument.
function findAdjustMutation(mType: any) {
  const m = mType.fields.find((f: any) =>
    /(adjust|update|change|set|modify)/i.test(f.name) &&
    unwrap(f.type).kind === 'OBJECT' &&
    f.args.some((a: any) => unwrap(a.type).kind === 'INPUT_OBJECT'),
  );
  return m || mType.fields.find((f: any) =>
    unwrap(f.type).kind === 'OBJECT' &&
    f.args.some((a: any) => unwrap(a.type).kind === 'INPUT_OBJECT'),
  );
}

// =========================================================================
describe('inventory service (independent harness)', () => {

  it('schema builds and exposes an Item with non-null id/name/quantity/availability and a money SCALAR price', async () => {
    const server = await mkServer();
    const sch = await introspect(server);
    const types: any[] = sch.types;
    const av = findAvailabilityEnum(types);
    expect(av).toBeTruthy();
    const item = findItemObject(types, av.type.name);
    expect(item).toBeTruthy();

    const idF = idFieldOf(item.type);
    expect(idF).toBeTruthy();
    // id distinct from name
    expect(/^name$/i.test(idF.name)).toBe(false);
    // stable id, name, quantity, availability all non-null
    expect(unwrap(idF.type).nonNull).toBe(true);
    expect(unwrap(item.nameF.type).nonNull).toBe(true);
    expect(unwrap(item.qtyF.type).nonNull).toBe(true);
    expect(unwrap(item.availF.type).nonNull).toBe(true);
    // price is a *custom* scalar (not Int/Float/String/Boolean/ID)
    const pu = unwrap(item.priceF.type);
    expect(pu.kind).toBe('SCALAR');
    expect(SCALAR_BUILTINS.has(pu.name)).toBe(false);
    expect(unwrap(item.priceF.type).nonNull).toBe(true);
    await server.stop();
  });

  it('availability enum is introspectable with EXACTLY four closed-set values', async () => {
    const server = await mkServer();
    const sch = await introspect(server);
    const av = findAvailabilityEnum(sch.types);
    expect(av).toBeTruthy();
    expect(av.names.length).toBe(4);
    expect(availValue(av.names, /(in.?stock|in_stock|instock|available)/i)).toBeTruthy();
    expect(availValue(av.names, /(low.?stock|low_stock|lowstock|low)/i)).toBeTruthy();
    expect(availValue(av.names, /(out.?of.?stock|out_of_stock|outofstock|sold.?out)/i)).toBeTruthy();
    expect(availValue(av.names, /(discontinu)/i)).toBeTruthy();
    await server.stop();
  });

  it('single-item fetch HIT returns matching seeded name/quantity/availability/price', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const sel = itemSelection(d.item);
    const list = await run(server, `query{ ${d.listQ.name} { ${sel} } }`);
    expect(list.errors).toBeFalsy();
    const items = extractItems(list.data[d.listQ.name]);
    expect(items.length).toBeGreaterThan(0);
    const known = items[0];

    const arg = d.itemQ.args[0];
    const q = `query($id: ${unwrapTopName(arg.type)}){ ${d.itemQ.name}(${arg.name}: $id){ ${sel} } }`;
    const res = await run(server, q, { id: known[d.itemId] });
    expect(res.errors).toBeFalsy();
    const got = res.data[d.itemQ.name];
    expect(got).toBeTruthy();
    expect(got[d.itemId]).toBe(known[d.itemId]);
    expect(got[d.item.nameF.name]).toBe(known[d.item.nameF.name]);
    expect(typeof got[d.item.nameF.name]).toBe('string');
    expect(got[d.item.nameF.name].length).toBeGreaterThan(0);
    expect(got[d.item.qtyF.name]).toBe(known[d.item.qtyF.name]);
    expect(typeof got[d.item.qtyF.name]).toBe('number');
    expect(got[d.item.availF.name]).toBe(known[d.item.availF.name]);
    // price scalar round-trips equal to the value seen in the list
    expect(got[d.item.priceF.name]).toEqual(known[d.item.priceF.name]);
    await server.stop();
  });

  it('single-item fetch MISS yields null item and NO execution error', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const arg = d.itemQ.args[0];
    const q = `query($id: ${unwrapTopName(arg.type)}){ ${d.itemQ.name}(${arg.name}: $id){ ${d.itemId} } }`;
    const res = await run(server, q, { id: 'definitely-not-a-real-item-zzz' });
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    expect(res.data[d.itemQ.name]).toBeNull();
    await server.stop();
  });

  it('list filtered by OUT_OF_STOCK returns only out-of-stock items, filter is meaningful', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const outVal = availValue(d.availNames, /(out.?of.?stock|out_of_stock|outofstock|sold.?out)/i);
    expect(outVal).toBeTruthy();
    const availArg = d.listQ.args.find((a: any) => unwrap(a.type).name === d.availEnum.name);
    expect(availArg).toBeTruthy();

    const sel = itemSelection(d.item);
    const filtered = await run(
      server,
      `query{ ${d.listQ.name}(${availArg.name}: ${outVal}) { ${sel} } }`,
    );
    expect(filtered.errors).toBeFalsy();
    const fItems = extractItems(filtered.data[d.listQ.name]);
    expect(fItems.length).toBeGreaterThan(0);
    for (const it of fItems) {
      expect(it[d.item.availF.name]).toBe(outVal);
    }
    // unfiltered list returns strictly more (the filter excludes some items)
    const all = await run(server, `query{ ${d.listQ.name} { ${sel} } }`);
    const allItems = extractItems(all.data[d.listQ.name]);
    expect(allItems.length).toBeGreaterThan(fItems.length);
    // and the list never contains null entries
    expect(allItems.every((x: any) => x != null && x[d.itemId] != null)).toBe(true);
    await server.stop();
  });

  it('availability value OUTSIDE the fixed set fails VALIDATION before resolvers (errors, no data for field)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const availArg = d.listQ.args.find((a: any) => unwrap(a.type).name === d.availEnum.name);
    expect(availArg).toBeTruthy();
    const sel = `${d.itemId}`;
    const r = await run(
      server,
      `query{ ${d.listQ.name}(${availArg.name}: NOT_A_REAL_AVAILABILITY) { ${sel} } }`,
    );
    expect(Array.isArray(r.errors)).toBe(true);
    expect(r.errors!.length).toBeGreaterThan(0);
    // validation -> no data for the field
    expect(r.data == null || r.data[d.listQ.name] === undefined || r.data[d.listQ.name] === null).toBe(true);
    await server.stop();
  });

  it('two seeded items priced identically read back EQUAL money scalars', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const sel = `${d.itemId} ${d.item.priceF.name}`;
    const list = await run(server, `query{ ${d.listQ.name} { ${sel} } }`);
    expect(list.errors).toBeFalsy();
    const items = extractItems(list.data[d.listQ.name]);
    // group by JSON-serialized price scalar; require at least one duplicated price
    const byPrice: Record<string, any[]> = {};
    for (const it of items) {
      const key = JSON.stringify(it[d.item.priceF.name]);
      (byPrice[key] = byPrice[key] || []).push(it);
    }
    const dupGroup = Object.values(byPrice).find((g) => g.length >= 2);
    expect(dupGroup).toBeTruthy();
    // structural equality of the two scalar values
    expect(dupGroup![0][d.item.priceF.name]).toEqual(dupGroup![1][d.item.priceF.name]);
    await server.stop();
  });

  it('adjust mutation accepts a SINGLE structured (input object) argument', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.mType).toBeTruthy();
    const m = findAdjustMutation(d.mType);
    expect(m).toBeTruthy();
    const structured = m.args.filter((a: any) => unwrap(a.type).kind === 'INPUT_OBJECT');
    expect(structured.length).toBe(1);
    await server.stop();
  });

  it('adjusting quantity to ZERO flips availability to OUT_OF_STOCK in the payload and persists', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const m = findAdjustMutation(d.mType);
    expect(m).toBeTruthy();
    const inputArg = m.args.find((a: any) => unwrap(a.type).kind === 'INPUT_OBJECT');
    const inputType = d.types.find((t: any) => t.name === unwrap(inputArg.type).name);
    expect(inputType).toBeTruthy();

    const outVal = availValue(d.availNames, /(out.?of.?stock|out_of_stock|outofstock|sold.?out)/i);
    const discVal = availValue(d.availNames, /(discontinu)/i);

    // find a seeded item that is NOT discontinued and has quantity > 0
    const sel = itemSelection(d.item);
    const list = await run(server, `query{ ${d.listQ.name} { ${sel} } }`);
    const target = extractItems(list.data[d.listQ.name]).find(
      (it: any) => it[d.item.availF.name] !== discVal && it[d.item.qtyF.name] > 0,
    );
    expect(target).toBeTruthy();

    // build the structured input: id field + signed delta field = -quantity
    const idField = (inputType.inputFields || []).find(
      (f: any) => /id/i.test(f.name) && ['ID', 'String', 'Int'].includes(unwrap(f.type).name),
    );
    const deltaField = (inputType.inputFields || []).find(
      (f: any) => /(delta|amount|change|by|adjust|qty|quantity|count)/i.test(f.name) &&
        unwrap(f.type).name === 'Int',
    );
    expect(idField).toBeTruthy();
    expect(deltaField).toBeTruthy();
    const input: any = {};
    input[idField.name] = target[d.itemId];
    input[deltaField.name] = -target[d.item.qtyF.name]; // drive to exactly zero

    const payloadType = d.types.find((t: any) => t.name === unwrap(m.type).name);
    const paySel = payloadItemSelection(payloadType, d);
    const res = await run(
      server,
      `mutation($in: ${unwrapTopName(inputArg.type)}){ ${m.name}(${inputArg.name}: $in){ ${paySel} } }`,
      { in: input },
    );
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    const item = digItem(res.data[m.name], d);
    expect(item).toBeTruthy();
    expect(item[d.item.qtyF.name]).toBe(0);
    expect(item[d.item.availF.name]).toBe(outVal);

    // persisted: refetch shows quantity 0 + out-of-stock
    const arg = d.itemQ.args[0];
    const re = await run(
      server,
      `query($id: ${unwrapTopName(arg.type)}){ ${d.itemQ.name}(${arg.name}: $id){ ${d.item.qtyF.name} ${d.item.availF.name} } }`,
      { id: target[d.itemId] },
    );
    expect(re.data[d.itemQ.name][d.item.qtyF.name]).toBe(0);
    expect(re.data[d.itemQ.name][d.item.availF.name]).toBe(outVal);
    await server.stop();
  });

  it('positive adjustment from zero recomputes availability to IN_STOCK (state derived from quantity)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const m = findAdjustMutation(d.mType);
    const inputArg = m.args.find((a: any) => unwrap(a.type).kind === 'INPUT_OBJECT');
    const inputType = d.types.find((t: any) => t.name === unwrap(inputArg.type).name);
    const inVal = availValue(d.availNames, /(in.?stock|in_stock|instock|available)/i);
    const discVal = availValue(d.availNames, /(discontinu)/i);

    const sel = itemSelection(d.item);
    const list = await run(server, `query{ ${d.listQ.name} { ${sel} } }`);
    // pick a non-discontinued item with quantity > 0, zero it, then add back.
    const target = extractItems(list.data[d.listQ.name]).find(
      (it: any) => it[d.item.availF.name] !== discVal && it[d.item.qtyF.name] > 0,
    );
    expect(target).toBeTruthy();

    const idField = (inputType.inputFields || []).find(
      (f: any) => /id/i.test(f.name) && ['ID', 'String', 'Int'].includes(unwrap(f.type).name),
    );
    const deltaField = (inputType.inputFields || []).find(
      (f: any) => /(delta|amount|change|by|adjust|qty|quantity|count)/i.test(f.name) &&
        unwrap(f.type).name === 'Int',
    );
    const payloadType = d.types.find((t: any) => t.name === unwrap(m.type).name);
    const paySel = payloadItemSelection(payloadType, d);
    const mut = (delta: number) => {
      const input: any = {};
      input[idField.name] = target[d.itemId];
      input[deltaField.name] = delta;
      return run(
        server,
        `mutation($in: ${unwrapTopName(inputArg.type)}){ ${m.name}(${inputArg.name}: $in){ ${paySel} } }`,
        { in: input },
      );
    };
    // drive to zero
    await mut(-target[d.item.qtyF.name]);
    // add back a positive amount
    const res = await mut(5);
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    const item = digItem(res.data[m.name], d);
    expect(item).toBeTruthy();
    expect(item[d.item.qtyF.name]).toBe(5);
    expect(item[d.item.availF.name]).toBe(inVal);
    await server.stop();
  });

  it('adjusting a NON-EXISTENT item reports via the payload; top-level errors EMPTY', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const m = findAdjustMutation(d.mType);
    const inputArg = m.args.find((a: any) => unwrap(a.type).kind === 'INPUT_OBJECT');
    const inputType = d.types.find((t: any) => t.name === unwrap(inputArg.type).name);
    const idField = (inputType.inputFields || []).find(
      (f: any) => /id/i.test(f.name) && ['ID', 'String', 'Int'].includes(unwrap(f.type).name),
    );
    const deltaField = (inputType.inputFields || []).find(
      (f: any) => /(delta|amount|change|by|adjust|qty|quantity|count)/i.test(f.name) &&
        unwrap(f.type).name === 'Int',
    );
    const input: any = {};
    input[idField.name] = 'no-such-item-zzz';
    input[deltaField.name] = 1;

    const payloadType = d.types.find((t: any) => t.name === unwrap(m.type).name);
    const paySel = fullPayloadSelection(payloadType, d);
    const res = await run(
      server,
      `mutation($in: ${unwrapTopName(inputArg.type)}){ ${m.name}(${inputArg.name}: $in){ ${paySel} } }`,
      { in: input },
    );
    // recoverable: no top-level errors
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    const payload = res.data[m.name];
    expect(payload).toBeTruthy();
    // no item produced
    const item = digItem(payload, d);
    expect(item == null || item[d.itemId] == null).toBe(true);
    // a discriminating signal exists
    expect(payloadSignalsFailure(payload, d)).toBe(true);
    await server.stop();
  });

  it('driving quantity NEGATIVE is reported via the payload, not thrown; top-level errors EMPTY', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const m = findAdjustMutation(d.mType);
    const inputArg = m.args.find((a: any) => unwrap(a.type).kind === 'INPUT_OBJECT');
    const inputType = d.types.find((t: any) => t.name === unwrap(inputArg.type).name);
    const discVal = availValue(d.availNames, /(discontinu)/i);

    const sel = itemSelection(d.item);
    const list = await run(server, `query{ ${d.listQ.name} { ${sel} } }`);
    const target = extractItems(list.data[d.listQ.name]).find(
      (it: any) => it[d.item.availF.name] !== discVal,
    );
    expect(target).toBeTruthy();

    const idField = (inputType.inputFields || []).find(
      (f: any) => /id/i.test(f.name) && ['ID', 'String', 'Int'].includes(unwrap(f.type).name),
    );
    const deltaField = (inputType.inputFields || []).find(
      (f: any) => /(delta|amount|change|by|adjust|qty|quantity|count)/i.test(f.name) &&
        unwrap(f.type).name === 'Int',
    );
    const input: any = {};
    input[idField.name] = target[d.itemId];
    input[deltaField.name] = -(target[d.item.qtyF.name] + 1000); // would go negative

    const payloadType = d.types.find((t: any) => t.name === unwrap(m.type).name);
    const paySel = fullPayloadSelection(payloadType, d);
    const res = await run(
      server,
      `mutation($in: ${unwrapTopName(inputArg.type)}){ ${m.name}(${inputArg.name}: $in){ ${paySel} } }`,
      { in: input },
    );
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    expect(payloadSignalsFailure(res.data[m.name], d)).toBe(true);
    // and the item's stored quantity did not go negative
    const arg = d.itemQ.args[0];
    const re = await run(
      server,
      `query($id: ${unwrapTopName(arg.type)}){ ${d.itemQ.name}(${arg.name}: $id){ ${d.item.qtyF.name} } }`,
      { id: target[d.itemId] },
    );
    if (re.data[d.itemQ.name]) {
      expect(re.data[d.itemQ.name][d.item.qtyF.name]).toBeGreaterThanOrEqual(0);
    }
    await server.stop();
  });

  it('malformed money value on input is rejected before resolvers run', async () => {
    const server = await mkServer();
    const d = await discover(server);
    // Find any mutation whose structured input has a price/money scalar field,
    // OR any input object across the schema carrying the money scalar.
    const priceScalarName = unwrap(d.item.priceF.type).name;
    let target: any = null; // { mutationName, argName, inputTypeName, priceFieldName, otherFields }
    if (d.mType) {
      for (const f of d.mType.fields) {
        const inArg = f.args.find((a: any) => unwrap(a.type).kind === 'INPUT_OBJECT');
        if (!inArg) continue;
        const it = d.types.find((t: any) => t.name === unwrap(inArg.type).name);
        if (!it) continue;
        const pf = (it.inputFields || []).find((x: any) => unwrap(x.type).name === priceScalarName);
        if (pf) { target = { f, inArg, it, pf }; break; }
      }
    }
    if (!target) {
      // No money-typed input field exposed; assert the price scalar at least
      // parses a malformed *literal* as an error via a direct coercion probe is
      // not possible without an input path -> treat as not-applicable PASS only
      // if the scalar is genuinely custom (already checked elsewhere).
      expect(priceScalarName).toBeTruthy();
      await server.stop();
      return;
    }
    // Build an input with a clearly malformed money value. Custom money scalars
    // reject negative amounts / non-money strings during input coercion, which
    // happens before resolvers run -> populated errors.
    const inputType = target.it;
    const input: any = {};
    for (const fld of inputType.inputFields || []) {
      const u = unwrap(fld.type);
      if (fld.name === target.pf.name) {
        input[fld.name] = '-not-a-valid-money-$$$';
        continue;
      }
      if (!u.nonNull) continue;
      if (/id/i.test(fld.name) || u.name === 'ID') input[fld.name] = 'x';
      else if (u.name === 'Int') input[fld.name] = 1;
      else if (u.name === 'String') input[fld.name] = 'x';
      else if (u.name === 'Boolean') input[fld.name] = false;
      else if (u.kind === 'ENUM') {
        const et = d.types.find((t: any) => t.name === u.name);
        input[fld.name] = et.enumValues[0].name;
      }
    }
    const res = await run(
      server,
      `mutation($in: ${unwrapTopName(target.inArg ? target.inArg.type : target.f.type)}){ ${target.f.name}(${target.inArg.name}: $in){ __typename } }`,
      { in: input },
    );
    expect(Array.isArray(res.errors)).toBe(true);
    expect(res.errors!.length).toBeGreaterThan(0);
    await server.stop();
  });
});

// ============================ payload helpers ===============================
function payloadItemSelection(payloadType: any, d: any): string {
  const idF = d.itemId;
  const qty = d.item.qtyF.name;
  const avail = d.item.availF.name;
  if (payloadType.name === d.item.type.name) {
    return `${idF} ${qty} ${avail}`;
  }
  const itemField = (payloadType.fields || []).find(
    (f: any) => unwrap(f.type).name === d.item.type.name,
  );
  if (itemField) {
    return `${itemField.name} { ${idF} ${qty} ${avail} }`;
  }
  return `... on ${d.item.type.name} { ${idF} ${qty} ${avail} }`;
}
function fullPayloadSelection(payloadType: any, d: any): string {
  if (payloadType.kind === 'UNION') {
    return `__typename ... on ${d.item.type.name} { ${d.itemId} }`;
  }
  const parts: string[] = ['__typename'];
  for (const f of payloadType.fields || []) {
    const u = unwrap(f.type);
    if (u.name === d.item.type.name && !u.list) {
      parts.push(`${f.name} { ${d.itemId} ${d.item.qtyF.name} }`);
    } else if (u.kind === 'SCALAR' || u.kind === 'ENUM') {
      parts.push(f.name);
    }
  }
  return parts.join(' ');
}
function digItem(payload: any, d: any): any {
  if (payload == null) return null;
  if (payload[d.itemId] !== undefined && payload[d.itemId] !== null) return payload;
  for (const [, v] of Object.entries(payload)) {
    if (v && typeof v === 'object' && (v as any)[d.itemId] !== undefined && (v as any)[d.itemId] !== null) {
      return v;
    }
  }
  return null;
}
function payloadSignalsFailure(payload: any, d: any): boolean {
  if (payload == null) return true;
  if (payload.__typename && !new RegExp(d.item.type.name, 'i').test(payload.__typename) &&
      !/success/i.test(payload.__typename)) return true;
  for (const [k, v] of Object.entries(payload)) {
    if (/success|ok|adjusted|updated/i.test(k) && v === false) return true;
    if (/(message|reason|code|error|notfound|not_found|found)/i.test(k) && v != null && v !== '' && v !== true) return true;
  }
  // a null item with empty top-level errors also discriminates from success
  const item = digItem(payload, d);
  return item == null || item[d.itemId] == null;
}
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
        """L1: the inventory module file exists at the required path."""
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
        # an exported factory function (create*/make*/*Store/*Inventory/seed*)
        assert re.search(
            r"export\s+(const|function)\s+\w*(create|make|store|inventory|seed|build)\w*",
            src,
            re.IGNORECASE,
        ), "no store-factory export found"

    def test_module_has_no_other_example_imports(self):
        """L1: module is self-contained (does not import from sibling example files)."""
        src = self._read(self.MODULE_PATH)
        for m in re.finditer(r"""import[^;]*?from\s*['"]([^'"]+)['"]""", src):
            spec = m.group(1)
            if "examples/" in spec and "inventoryService" not in spec:
                pytest.fail(f"module imports another example file: {spec}")

    def test_public_index_not_modified_to_export_module(self):
        """L1: the package's public index.ts does not re-export the new module
        (the task forbids modifying the public index exports)."""
        if not os.path.isfile(self.INDEX_PATH):
            return
        src = self._read(self.INDEX_PATH)
        assert "inventoryService" not in src, (
            "public index.ts must not be modified to export inventoryService"
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
        """L2: the acceptance command (agent's own suite) passes all assertions."""
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

    def test_harness_schema_and_item_shape(self, harness_report):
        """L2: schema builds; Item has non-null id/name/quantity/availability and a
        custom money SCALAR price (not Int/Float/String)."""
        self._passed(harness_report, r"exposes an Item with non-null")

    def test_harness_availability_enum_four_values(self, harness_report):
        """L2: availability enum is introspectable with exactly the four closed values."""
        self._passed(harness_report, r"availability enum is introspectable with EXACTLY four")

    def test_harness_single_fetch_hit(self, harness_report):
        """L2: single-item fetch hit returns matching seeded fields + price scalar."""
        self._passed(harness_report, r"single-item fetch HIT")

    def test_harness_item_miss_null(self, harness_report):
        """L2: unknown item id resolves to null with no execution error."""
        self._passed(harness_report, r"single-item fetch MISS")

    def test_harness_availability_filter(self, harness_report):
        """L2: OUT_OF_STOCK filter returns only out-of-stock items (and is meaningful)."""
        self._passed(harness_report, r"filtered by OUT_OF_STOCK")

    def test_harness_invalid_availability_validation(self, harness_report):
        """L2: an availability value outside the fixed set fails validation pre-resolver."""
        self._passed(harness_report, r"OUTSIDE the fixed set fails VALIDATION")

    def test_harness_price_equality_roundtrip(self, harness_report):
        """L2: two identically priced seeded items read back equal money scalars."""
        self._passed(harness_report, r"priced identically read back EQUAL")

    def test_harness_mutation_single_input(self, harness_report):
        """L2: adjust mutation takes a single structured input-object argument."""
        self._passed(harness_report, r"SINGLE structured \(input object\) argument")

    def test_harness_adjust_to_zero_out_of_stock(self, harness_report):
        """L2: adjusting quantity to zero flips availability to out-of-stock and persists."""
        self._passed(harness_report, r"quantity to ZERO flips availability to OUT_OF_STOCK")

    def test_harness_positive_recompute_in_stock(self, harness_report):
        """L2: positive adjustment from zero recomputes availability to in-stock."""
        self._passed(harness_report, r"positive adjustment from zero recomputes")

    def test_harness_missing_item_outcome(self, harness_report):
        """L2: adjusting a missing item reports via payload; top-level errors empty."""
        self._passed(harness_report, r"NON-EXISTENT item reports via the payload")

    def test_harness_negative_quantity_outcome(self, harness_report):
        """L2: driving quantity negative is reported via payload, not thrown."""
        self._passed(harness_report, r"driving quantity NEGATIVE is reported")

    def test_harness_malformed_money_rejected(self, harness_report):
        """L2: a malformed money value on input is rejected before resolvers run."""
        self._passed(harness_report, r"malformed money value on input is rejected")
