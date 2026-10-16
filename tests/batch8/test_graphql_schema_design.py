"""Benchmark tests for the `graphql-schema-design` skill (variant ext8).

Skill task (ext8): build a self-contained "contacts" GraphQL feature module
inside the `@apollo/server` package
(`packages/server/src/examples/contactsModule.ts`) that exports `typeDefs`
(SDL string), `resolvers`, and an in-memory data-store factory, plus a Jest
suite at `packages/server/src/__tests__/examples/contactsModule.test.ts`.

The defining requirement of THIS variant (distinct from ext1's library-catalog
enum/pagination task) is **domain-specific custom scalars**: a contact's
email, optional website URL, and created-at timestamp are each their OWN
scalar type -- distinct from `String` and from each other -- so that malformed
input is rejected *before resolvers run* (a scalar parse error), and a valid
value round-trips unchanged. A well-formed-but-conflicting case (duplicate
email of a seeded contact) is NOT a scalar failure; it is reported through the
mutation payload while the top-level `errors` array stays empty.

What this file verifies
-----------------------
L1 (existence / minimal well-formedness):
  - the two deliverable files exist,
  - the module exports `typeDefs` / `resolvers` / a store factory,
  - the module is self-contained (no sibling example imports),
  - the agent's own Jest suite declares >= 10 `it`/`test` cases,
  - the agent's own Jest suite passes (acceptance command).

L2 (dynamic execution -- the discriminative core):
  Instead of trusting the agent's own test file, we synthesize an INDEPENDENT
  TypeScript Jest harness, drop it next to the module, and run it through the
  repo's native `jest` toolchain. The harness builds an `ApolloServer`
  directly from the module's `typeDefs`/`resolvers`, introspects the schema to
  discover the real custom-scalar type names and field/argument names (so we do
  not hard-code the agent's naming choices), and then exercises every
  Acceptance-Criterion scenario:
    * email / URL / created-at are three DISTINCT custom scalar types, each !=
      `String` and != each other, used on the Contact object;
    * valid create + round-trip returns the exact scalar values supplied;
    * malformed email / malformed URL / malformed timestamp each fail
      VALIDATION (scalar parse) *before* resolvers run -> errors populated, no
      data for the field;
    * omitting the optional website succeeds and reads back as absent (null);
    * single contact fetch hit/miss (miss -> null, no error);
    * the contacts list is never null and never contains null entries;
    * a duplicate-email create is reported via the payload while top-level
      `errors` stays empty (recoverable, distinct from a scalar failure).

We run jest with `--json` and assert on individual named test outcomes, so a
stub / partial / "looks related" / plain-`String`-instead-of-scalar solution
fails.
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
    MODULE_REL = "src/examples/contactsModule.ts"
    SUITE_REL = "src/__tests__/examples/contactsModule.test.ts"
    MODULE_PATH = os.path.join(SERVER_DIR, "src", "examples", "contactsModule.ts")
    SUITE_PATH = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "contactsModule.test.ts"
    )

    # Directory where we drop our own independent harness suite.
    HARNESS_DIR = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "__bench__"
    )
    HARNESS_NAME = "benchContactsModule.test.ts"
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
        node_modules/.bin. Resolving it by absolute path avoids `npx` trying to
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
        #   - module under test -> ../../../examples/contactsModule.js
        return r"""// @ts-nocheck
import { describe, it, expect } from '@jest/globals';
import { ApolloServer } from '../../../index.js';
import * as mod from '../../../examples/contactsModule.js';

const typeDefs: any = (mod as any).typeDefs;
const resolvers: any = (mod as any).resolvers;

function findFactory(): (() => any) | null {
  const preferred = [
    'createStore', 'makeStore', 'createContactsStore', 'makeContactsStore',
    'createContacts', 'makeContacts', 'createDataStore', 'createInMemoryStore',
    'storeFactory', 'seedStore', 'createContactStore',
  ];
  for (const k of preferred) {
    if (typeof (mod as any)[k] === 'function') return (mod as any)[k];
  }
  for (const [k, v] of Object.entries(mod as any)) {
    if (k === 'typeDefs' || k === 'resolvers') continue;
    if (typeof v === 'function') {
      try {
        const r = (v as any)();
        if (r && typeof r === 'object') return v as any;
      } catch (_e) { /* ignore */ }
    }
  }
  return null;
}

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

const TYPEREF = `kind name ofType { kind name ofType { kind name ofType { kind name } } }`;
const INTRO = `
{
  __schema {
    queryType { name }
    mutationType { name }
    types {
      kind name
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

// ---- schema discovery: contact object, custom scalars, queries, mutation ----
async function discover(server: any) {
  const intro = await run(server, INTRO);
  expect(intro.errors).toBeFalsy();
  const sch = intro.data.__schema;
  const types: any[] = sch.types;
  const byName: Record<string, any> = {};
  for (const t of types) byName[t.name] = t;

  const qType = types.find((t) => t.name === sch.queryType.name);
  const mType = sch.mutationType ? types.find((t) => t.name === sch.mutationType.name) : null;

  // Built-in scalars we must NOT treat as the domain scalars.
  const BUILTIN = new Set(['String', 'Int', 'Float', 'Boolean', 'ID']);
  const customScalars = types
    .filter((t) => t.kind === 'SCALAR' && !BUILTIN.has(t.name))
    .map((t) => t.name);

  // Contact object: an OBJECT (not the query/mutation root, not an input/payload)
  // that carries an id-ish field, a name field, and uses custom scalar fields.
  const contactObj = types.find((t) => {
    if (t.kind !== 'OBJECT' || !t.fields) return false;
    if (t.name === sch.queryType.name) return false;
    if (mType && t.name === mType.name) return false;
    if (/^__/.test(t.name)) return false;
    const hasName = t.fields.some((f: any) => /name/i.test(f.name));
    const usesScalar = t.fields.some((f: any) => customScalars.includes(unwrap(f.type).name));
    return hasName && usesScalar;
  });
  expect(contactObj).toBeTruthy();

  const idField = (contactObj.fields.find((f: any) => /^id$/i.test(f.name)) ||
    contactObj.fields.find((f: any) => /id$/i.test(f.name)));
  expect(idField).toBeTruthy();

  // classify the custom-scalar-typed fields on contact by name hint
  const fieldByScalarRole: Record<string, any> = {};
  const scalarTypeByRole: Record<string, string> = {};
  for (const f of contactObj.fields) {
    const u = unwrap(f.type);
    if (!customScalars.includes(u.name)) continue;
    if (/e?mail/i.test(f.name) && !fieldByScalarRole.email) {
      fieldByScalarRole.email = f; scalarTypeByRole.email = u.name;
    } else if (/(url|site|web|link|homepage)/i.test(f.name) && !fieldByScalarRole.url) {
      fieldByScalarRole.url = f; scalarTypeByRole.url = u.name;
    } else if (/(created|date|time|at|when|stamp)/i.test(f.name) && !fieldByScalarRole.ts) {
      fieldByScalarRole.ts = f; scalarTypeByRole.ts = u.name;
    }
  }

  // single-contact query: returns the contact object, takes one id-ish arg
  const contactQ = qType.fields.find((f: any) => {
    const u = unwrap(f.type);
    return u.name === contactObj.name && !u.list && f.args.length >= 1;
  });
  // list query: returns a list of contacts
  const listQ = qType.fields.find((f: any) => {
    const u = unwrap(f.type);
    return u.name === contactObj.name && u.list;
  });

  // create mutation: returns OBJECT, takes a single structured INPUT_OBJECT arg
  let addM: any = null, inputArg: any = null, payloadType: any = null, inputObjType: any = null;
  if (mType) {
    addM = mType.fields.find((f: any) =>
      /add|create|new/i.test(f.name) && unwrap(f.type).kind === 'OBJECT');
    if (addM) {
      inputArg = addM.args.find((a: any) => unwrap(a.type).kind === 'INPUT_OBJECT');
      payloadType = byName[unwrap(addM.type).name];
      if (inputArg) inputObjType = byName[unwrap(inputArg.type).name];
    }
  }

  return {
    types, byName, qType, mType, customScalars,
    contactObj, idField,
    fieldByScalarRole, scalarTypeByRole,
    contactQ, listQ,
    addM, inputArg, payloadType, inputObjType,
  };
}

// classify input-object fields by role and capture their custom-scalar types
function classifyInputFields(d: any) {
  const roles: Record<string, any> = {};
  for (const f of (d.inputObjType.inputFields || [])) {
    const u = unwrap(f.type);
    if (/e?mail/i.test(f.name)) roles.email = { f, type: u };
    else if (/(url|site|web|link|homepage)/i.test(f.name)) roles.url = { f, type: u };
    else if (/(created|date|time|at|when|stamp)/i.test(f.name)) roles.ts = { f, type: u };
    else if (/name/i.test(f.name)) roles.name = { f, type: u };
  }
  return roles;
}

// produce a literal GraphQL value for a contact-input field of a given role
const VALID = {
  email: 'bench.user@example.com',
  url: 'https://bench.example.com/path',
  ts: '2021-03-04T05:06:07.000Z',
  name: 'Bench Person',
};
const INVALID = {
  email: 'not-an-email-at-all',
  url: 'definitely not a url ::::',
  ts: 'not-a-real-timestamp',
};

function gqlLiteral(v: any): string {
  return JSON.stringify(v); // strings -> quoted; works for scalar serialise-from-string inputs
}

// build the create-mutation input variable object using valid values, with
// optional overrides; omit roles listed in `omit`.
function buildInput(roles: any, overrides: Record<string, any> = {}, omit: string[] = []): any {
  const obj: any = {};
  if (roles.name) obj[roles.name.f.name] = overrides.name ?? VALID.name;
  if (roles.email && !omit.includes('email')) obj[roles.email.f.name] = overrides.email ?? VALID.email;
  if (roles.url && !omit.includes('url')) obj[roles.url.f.name] = overrides.url ?? VALID.url;
  if (roles.ts && !omit.includes('ts')) obj[roles.ts.f.name] = overrides.ts ?? VALID.ts;
  // fill any other NON_NULL string-ish fields so the mutation is well-formed
  for (const f of (roles && roles.__all ? roles.__all : [])) { /* noop */ }
  return obj;
}

// selection of the created contact's scalar fields from the mutation payload
function digContact(payload: any, d: any): any {
  if (payload == null) return null;
  if (payload[d.idField.name] !== undefined) return payload;
  for (const [k, v] of Object.entries(payload)) {
    if (v && typeof v === 'object' && (v as any)[d.idField.name] !== undefined) return v;
  }
  return null;
}
function contactSelection(d: any): string {
  const parts: string[] = [d.idField.name];
  const nameF = d.contactObj.fields.find((f: any) => /name/i.test(f.name));
  if (nameF) parts.push(nameF.name);
  if (d.fieldByScalarRole.email) parts.push(d.fieldByScalarRole.email.name);
  if (d.fieldByScalarRole.url) parts.push(d.fieldByScalarRole.url.name);
  if (d.fieldByScalarRole.ts) parts.push(d.fieldByScalarRole.ts.name);
  return parts.join(' ');
}
function payloadContactSelection(d: any): string {
  if (d.payloadType.name === d.contactObj.name) return contactSelection(d);
  const cf = (d.payloadType.fields || []).find(
    (f: any) => unwrap(f.type).name === d.contactObj.name);
  if (cf) return `${cf.name} { ${contactSelection(d)} }`;
  return `... on ${d.contactObj.name} { ${contactSelection(d)} }`;
}
function fullPayloadSelection(d: any): string {
  if (d.payloadType.kind === 'UNION') {
    return `__typename ... on ${d.contactObj.name} { ${d.idField.name} }`;
  }
  const parts: string[] = ['__typename'];
  for (const f of (d.payloadType.fields || [])) {
    const u = unwrap(f.type);
    if (u.name === d.contactObj.name && !u.list) parts.push(`${f.name} { ${d.idField.name} ${(d.fieldByScalarRole.email||{}).name||''} }`);
    else if (u.kind === 'SCALAR' || u.kind === 'ENUM') parts.push(f.name);
  }
  return parts.join(' ');
}
function payloadSignalsConflict(payload: any, d: any): boolean {
  if (payload.__typename && !new RegExp(d.contactObj.name, 'i').test(payload.__typename)
      && !/success/i.test(payload.__typename)) return true;
  for (const [k, v] of Object.entries(payload)) {
    if (/success|ok|created/i.test(k) && v === false) return true;
    if (/(message|reason|code|error|conflict|duplicate|exist)/i.test(k) && v != null && v !== '') return true;
  }
  const created = digContact(payload, d);
  return created == null || created[d.idField.name] == null;
}

async function createContact(server: any, d: any, roles: any, overrides: any, omit: string[] = []) {
  const inputVar = buildInput(roles, overrides, omit);
  const sel = payloadContactSelection(d);
  const m = `mutation($in: ${unwrapTopName(d.inputArg.type)}){ ${d.addM.name}(${d.inputArg.name}: $in){ ${sel} } }`;
  return run(server, m, { in: inputVar });
}

describe('contacts module (independent harness)', () => {

  it('schema builds and exposes a Contact object with three distinct custom scalars', async () => {
    const server = await mkServer();
    const d = await discover(server);
    // id never null
    expect(unwrap(d.idField.type).nonNull).toBe(true);

    // three custom scalar roles must be present, each a custom (non-builtin) scalar
    expect(d.fieldByScalarRole.email).toBeTruthy();
    expect(d.fieldByScalarRole.url).toBeTruthy();
    expect(d.fieldByScalarRole.ts).toBeTruthy();

    const e = d.scalarTypeByRole.email;
    const u = d.scalarTypeByRole.url;
    const t = d.scalarTypeByRole.ts;
    for (const n of [e, u, t]) {
      expect(d.customScalars).toContain(n);     // custom, not String/ID/etc.
      expect(['String', 'ID', 'Int', 'Float', 'Boolean']).not.toContain(n);
    }
    // distinct from one another
    expect(new Set([e, u, t]).size).toBe(3);

    // email + created-at non-null, website nullable
    expect(unwrap(d.fieldByScalarRole.email.type).nonNull).toBe(true);
    expect(unwrap(d.fieldByScalarRole.ts.type).nonNull).toBe(true);
    expect(unwrap(d.fieldByScalarRole.url.type).nonNull).toBe(false);
    await server.stop();
  });

  it('contacts list is non-null and contains no null entries', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.listQ).toBeTruthy();
    // list type itself NON_NULL and elements NON_NULL ([Contact!]!)
    const top = d.listQ.type;
    expect(top.kind).toBe('NON_NULL');
    const r = await run(server, `query{ ${d.listQ.name} { ${d.idField.name} } }`);
    expect(r.errors).toBeFalsy();
    const arr = r.data[d.listQ.name];
    expect(Array.isArray(arr)).toBe(true);
    expect(arr.length).toBeGreaterThanOrEqual(1);
    for (const c of arr) {
      expect(c).not.toBeNull();
      expect(c[d.idField.name]).toBeTruthy();
    }
    await server.stop();
  });

  it('single contact fetch HIT returns the seeded scalar values', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.contactQ).toBeTruthy();
    const list = await run(server, `query{ ${d.listQ.name} { ${d.idField.name} } }`);
    const knownId = list.data[d.listQ.name][0][d.idField.name];
    const arg = d.contactQ.args[0];
    const sel = contactSelection(d);
    const r = await run(server,
      `query($id: ${unwrapTopName(arg.type)}){ ${d.contactQ.name}(${arg.name}: $id){ ${sel} } }`,
      { id: knownId });
    expect(r.errors).toBeFalsy();
    const c = r.data[d.contactQ.name];
    expect(c).toBeTruthy();
    expect(c[d.idField.name]).toBe(knownId);
    // email + created-at present and string-serialised
    expect(typeof c[d.fieldByScalarRole.email.name]).toBe('string');
    expect(c[d.fieldByScalarRole.email.name].length).toBeGreaterThan(0);
    expect(typeof c[d.fieldByScalarRole.ts.name]).toBe('string');
    await server.stop();
  });

  it('single contact fetch MISS yields null and no execution error', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const arg = d.contactQ.args[0];
    const r = await run(server,
      `query($id: ${unwrapTopName(arg.type)}){ ${d.contactQ.name}(${arg.name}: $id){ ${d.idField.name} } }`,
      { id: 'definitely-not-a-real-contact-zzz' });
    expect(r.errors == null || r.errors.length === 0).toBe(true);
    expect(r.data[d.contactQ.name]).toBeNull();
    await server.stop();
  });

  it('valid create round-trips: created scalars equal supplied scalars when refetched', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.addM).toBeTruthy();
    expect(d.inputArg).toBeTruthy();
    const roles = classifyInputFields(d);
    // structured-input requirement: exactly one INPUT_OBJECT arg
    const structured = d.addM.args.filter((a: any) => unwrap(a.type).kind === 'INPUT_OBJECT');
    expect(structured.length).toBe(1);

    const res = await createContact(server, d, roles, {});
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    const created = digContact(res.data[d.addM.name], d);
    expect(created).toBeTruthy();
    const newId = created[d.idField.name];
    expect(newId).toBeTruthy();
    // values round-trip on the payload
    expect(created[d.fieldByScalarRole.email.name]).toBe(VALID.email);

    // refetch returns the same scalar values
    const arg = d.contactQ.args[0];
    const re = await run(server,
      `query($id: ${unwrapTopName(arg.type)}){ ${d.contactQ.name}(${arg.name}: $id){ ${contactSelection(d)} } }`,
      { id: newId });
    expect(re.errors).toBeFalsy();
    const back = re.data[d.contactQ.name];
    expect(back).toBeTruthy();
    expect(back[d.fieldByScalarRole.email.name]).toBe(VALID.email);
    expect(back[d.fieldByScalarRole.url.name]).toBe(VALID.url);
    // timestamp round-trips to an equivalent instant
    expect(new Date(back[d.fieldByScalarRole.ts.name]).getTime())
      .toBe(new Date(VALID.ts).getTime());
    await server.stop();
  });

  it('malformed EMAIL is rejected by scalar VALIDATION before resolvers run', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const roles = classifyInputFields(d);
    const res = await createContact(server, d, roles, { email: INVALID.email });
    expect(Array.isArray(res.errors)).toBe(true);
    expect(res.errors.length).toBeGreaterThan(0);
    // scalar parse failure -> no data for the mutation field
    expect(res.data == null || res.data[d.addM.name] == null).toBe(true);
    await server.stop();
  });

  it('malformed WEBSITE URL is rejected by scalar VALIDATION before resolvers run', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const roles = classifyInputFields(d);
    const res = await createContact(server, d, roles, { url: INVALID.url });
    expect(Array.isArray(res.errors)).toBe(true);
    expect(res.errors.length).toBeGreaterThan(0);
    expect(res.data == null || res.data[d.addM.name] == null).toBe(true);
    await server.stop();
  });

  it('malformed TIMESTAMP is rejected by scalar VALIDATION before resolvers run', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const roles = classifyInputFields(d);
    const res = await createContact(server, d, roles, { ts: INVALID.ts });
    expect(Array.isArray(res.errors)).toBe(true);
    expect(res.errors.length).toBeGreaterThan(0);
    expect(res.data == null || res.data[d.addM.name] == null).toBe(true);
    await server.stop();
  });

  it('the three malformed-input cases discriminate the scalar (a valid create with the same other fields succeeds)', async () => {
    // guards against a stub that always errors regardless of input.
    const server = await mkServer();
    const d = await discover(server);
    const roles = classifyInputFields(d);
    const ok = await createContact(server, d, roles, {});
    expect(ok.errors == null || ok.errors.length === 0).toBe(true);
    expect(digContact(ok.data[d.addM.name], d)).toBeTruthy();
    // and each malformed variant individually fails
    for (const bad of [{ email: INVALID.email }, { url: INVALID.url }, { ts: INVALID.ts }]) {
      const r = await createContact(server, d, roles, bad);
      expect(Array.isArray(r.errors) && r.errors.length > 0).toBe(true);
    }
    await server.stop();
  });

  it('omitting the optional website succeeds and reads back as absent (null)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const roles = classifyInputFields(d);
    const res = await createContact(server, d, roles, { email: 'no.site.user@example.org' }, ['url']);
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    const created = digContact(res.data[d.addM.name], d);
    expect(created).toBeTruthy();
    expect(created[d.fieldByScalarRole.url.name] == null).toBe(true);
    // refetch confirms absence
    const arg = d.contactQ.args[0];
    const re = await run(server,
      `query($id: ${unwrapTopName(arg.type)}){ ${d.contactQ.name}(${arg.name}: $id){ ${contactSelection(d)} } }`,
      { id: created[d.idField.name] });
    expect(re.data[d.contactQ.name][d.fieldByScalarRole.url.name] == null).toBe(true);
    await server.stop();
  });

  it('duplicate-email create is reported via the payload while top-level errors stay empty', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const roles = classifyInputFields(d);

    // discover a seeded contact's existing email by reading the list
    const sel = contactSelection(d);
    const list = await run(server, `query{ ${d.listQ.name} { ${sel} } }`);
    expect(list.errors).toBeFalsy();
    const seeded = list.data[d.listQ.name].find(
      (c: any) => c[d.fieldByScalarRole.email.name]);
    expect(seeded).toBeTruthy();
    const dupEmail = seeded[d.fieldByScalarRole.email.name];

    // attempt to create another contact with that exact (valid) email
    const fullSel = fullPayloadSelection(d);
    const inputVar = buildInput(roles, { email: dupEmail });
    const m = `mutation($in: ${unwrapTopName(d.inputArg.type)}){ ${d.addM.name}(${d.inputArg.name}: $in){ ${fullSel} } }`;
    const res = await run(server, m, { in: inputVar });

    // recoverable -> NOT a scalar/validation failure: top-level errors empty
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    const payload = res.data[d.addM.name];
    expect(payload).toBeTruthy();
    // and the payload itself signals the conflict (no new contact, or an explicit flag/message)
    expect(payloadSignalsConflict(payload, d)).toBe(true);

    // the duplicate must NOT have grown the contact list
    const after = await run(server, `query{ ${d.listQ.name} { ${d.idField.name} ${d.fieldByScalarRole.email.name} } }`);
    const dupCount = after.data[d.listQ.name].filter(
      (c: any) => c[d.fieldByScalarRole.email.name] === dupEmail).length;
    expect(dupCount).toBe(1);
    await server.stop();
  });

  it('created contact ids are unique across multiple additions', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const roles = classifyInputFields(d);
    const made: string[] = [];
    for (let i = 0; i < 3; i++) {
      const res = await createContact(server, d, roles, {
        email: `unique.user.${i}@example.net`,
        name: `Bench Person ${i}`,
      });
      expect(res.errors == null || res.errors.length === 0).toBe(true);
      const created = digContact(res.data[d.addM.name], d);
      expect(created).toBeTruthy();
      made.push(created[d.idField.name]);
    }
    expect(new Set(made).size).toBe(made.length);
    await server.stop();
  });
});
"""

    @classmethod
    def _ensure_workspace_built(cls):
        """ts-jest type-checks server src, which imports sibling workspace packages
        (e.g. @apollo/server-gateway-interface) by their built `dist` types. If
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
        """L1: the contacts module file exists at the required path."""
        assert os.path.isfile(self.MODULE_PATH), f"missing {self.MODULE_REL}"

    def test_suite_file_exists(self):
        """L1: the agent's Jest suite file exists at the required path."""
        assert os.path.isfile(self.SUITE_PATH), f"missing {self.SUITE_REL}"

    def test_module_exports_typedefs_resolvers_and_factory(self):
        """L1: module declares exported typeDefs, resolvers, and a store factory."""
        src = self._read(self.MODULE_PATH)
        assert re.search(r"\btypeDefs\b", src), "no typeDefs export"
        assert re.search(r"\bresolvers\b", src), "no resolvers export"
        assert re.search(
            r"export\s+(const|function)\s+\w*(create|make|store|contact|seed)\w*",
            src,
            re.IGNORECASE,
        ), "no store-factory export found"

    def test_module_declares_custom_scalars(self):
        """L1: the SDL declares >= 3 custom scalar types (email/url/timestamp),
        i.e. the domain values are NOT plain String."""
        src = self._read(self.MODULE_PATH)
        scalars = set(re.findall(r"\bscalar\s+([A-Za-z_][A-Za-z0-9_]*)", src))
        assert len(scalars) >= 3, (
            f"expected >= 3 custom scalar declarations, found {sorted(scalars)}"
        )

    def test_module_has_no_other_example_imports(self):
        """L1: module is self-contained (does not import from sibling example files)."""
        src = self._read(self.MODULE_PATH)
        for m in re.finditer(r"""import[^;]*?from\s*['"]([^'"]+)['"]""", src):
            spec = m.group(1)
            if "examples/" in spec and "contactsModule" not in spec:
                pytest.fail(f"module imports another example file: {spec}")

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

    def test_harness_schema_and_custom_scalars(self, harness_report):
        """L2: schema builds; Contact carries three DISTINCT custom scalar types
        (email/url/timestamp), each != String and != each other; correct nullability."""
        self._passed(harness_report, r"three distinct custom scalars")

    def test_harness_list_non_null(self, harness_report):
        """L2: contacts list is non-null and contains no null entries ([Contact!]!)."""
        self._passed(harness_report, r"contacts list is non-null")

    def test_harness_single_fetch_hit(self, harness_report):
        """L2: single contact fetch hit returns seeded scalar values."""
        self._passed(harness_report, r"single contact fetch HIT")

    def test_harness_single_fetch_miss(self, harness_report):
        """L2: unknown contact id resolves to null with no execution error."""
        self._passed(harness_report, r"single contact fetch MISS")

    def test_harness_valid_create_roundtrip(self, harness_report):
        """L2: valid create round-trips email/url/timestamp scalar values unchanged."""
        self._passed(harness_report, r"valid create round-trips")

    def test_harness_malformed_email_rejected(self, harness_report):
        """L2: malformed email fails scalar validation before resolvers run."""
        self._passed(harness_report, r"malformed EMAIL is rejected")

    def test_harness_malformed_url_rejected(self, harness_report):
        """L2: malformed website URL fails scalar validation before resolvers run."""
        self._passed(harness_report, r"malformed WEBSITE URL is rejected")

    def test_harness_malformed_timestamp_rejected(self, harness_report):
        """L2: malformed timestamp fails scalar validation before resolvers run."""
        self._passed(harness_report, r"malformed TIMESTAMP is rejected")

    def test_harness_malformed_cases_discriminate(self, harness_report):
        """L2: a same-shape valid create succeeds while each malformed variant fails
        (guards against an always-error stub)."""
        self._passed(harness_report, r"three malformed-input cases discriminate")

    def test_harness_optional_website_omission(self, harness_report):
        """L2: omitting the optional website succeeds and reads back as absent."""
        self._passed(harness_report, r"omitting the optional website")

    def test_harness_duplicate_email_payload(self, harness_report):
        """L2: duplicate-email create is reported via the payload while top-level
        errors stay empty, and the list does not grow."""
        self._passed(harness_report, r"duplicate-email create is reported")

    def test_harness_created_id_uniqueness(self, harness_report):
        """L2: multiple created contacts get unique, non-colliding ids."""
        self._passed(harness_report, r"created contact ids are unique")
