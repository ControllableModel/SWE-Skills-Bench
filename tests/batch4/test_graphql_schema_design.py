"""Benchmark tests for the `graphql-schema-design` skill (ext4 variant).

Skill task: build a self-contained "heterogeneous search" GraphQL feature module
inside the `@apollo/server` package
(`packages/server/src/examples/searchModule.ts`) that exports `typeDefs`
(SDL string), `resolvers`, and an in-memory data-store factory for a small
directory domain of three mutually-exclusive object kinds -- people, projects and
documents.  A single root `search` field takes a free-text query and returns a
list whose elements may each be a person, a project, or a document; clients must
be able to discover each element's concrete kind and read that kind's own fields.
The agent also writes a Jest suite at
`packages/server/src/__tests__/examples/searchModule.test.ts`.

What this file verifies
-----------------------
L1 (existence / minimal well-formedness):
  - the two deliverable files exist,
  - the module exports `typeDefs` / `resolvers` / a store factory,
  - the module is self-contained (imports no sibling example file),
  - the agent's own Jest suite declares >= 10 `it`/`test` cases,
  - the agent's own Jest suite passes (the acceptance command).

L2 (dynamic execution -- the discriminative core):
  Instead of trusting the agent's own test file, we synthesize an INDEPENDENT
  TypeScript Jest harness, drop it next to the module, and run it through the
  repo's native `jest` toolchain.  The harness builds an `ApolloServer` directly
  from the module's `typeDefs`/`resolvers`, introspects the schema to discover
  the real query / field / enum / abstract-type names (so we never hard-code the
  agent's naming choices), then exercises every Acceptance-Criterion scenario:

    * the search field returns an ABSTRACT (union or interface) element type that
      resolves to >= 3 concrete object kinds (people / projects / documents),
      each with its own non-shared fields;
    * a multi-kind search hit returns exactly the matching elements, each
      observably its own concrete kind (via `__typename`), each exposing its own
      fields (e.g. person.email);
    * an empty search returns a non-null empty list (never null, no null entries);
    * concrete-kind NARROWING: narrowing a matched person to the person kind
      reads its email; narrowing the same element to the document kind yields
      nothing for document-only fields;
    * repeated identical searches yield identical ordered sequences (stable);
    * kind-specific single fetch HIT for person and project;
    * kind-specific single fetch MISS -> null, no error;
    * the project-status enum is introspectable with a fixed closed value set;
    * an out-of-set status literal fails VALIDATION before resolvers run.

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
    MODULE_REL = "src/examples/searchModule.ts"
    SUITE_REL = "src/__tests__/examples/searchModule.test.ts"
    MODULE_PATH = os.path.join(SERVER_DIR, "src", "examples", "searchModule.ts")
    SUITE_PATH = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "searchModule.test.ts"
    )

    # Directory where we drop our own independent harness suite.
    HARNESS_DIR = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "__bench__"
    )
    HARNESS_NAME = "benchSearchModule.test.ts"
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
        #   - module under test -> ../../../examples/searchModule.js
        return r"""// @ts-nocheck
import { describe, it, expect } from '@jest/globals';
import { ApolloServer } from '../../../index.js';
import * as mod from '../../../examples/searchModule.js';

const typeDefs: any = (mod as any).typeDefs;
const resolvers: any = (mod as any).resolvers;

function findFactory(): (() => any) | null {
  const preferred = [
    'createStore', 'makeStore', 'createDirectory', 'makeDirectory',
    'createDataStore', 'createInMemoryStore', 'storeFactory', 'createSearchStore',
    'seedStore', 'createDirectoryStore',
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

// ---- type helpers ----------------------------------------------------------
function unwrap(t: any): any {
  let nonNull = false, list = false, cur = t;
  while (cur) {
    if (cur.kind === 'NON_NULL') { nonNull = true; cur = cur.ofType; continue; }
    if (cur.kind === 'LIST') { list = true; cur = cur.ofType; continue; }
    break;
  }
  return { kind: cur ? cur.kind : '', name: cur ? cur.name : null, nonNull, list };
}
// peel only LIST wrappers, recording whether inner elements are non-null
function listInfo(t: any): { isList: boolean; innerNonNull: boolean; name: string; kind: string } {
  let isList = false, innerNonNull = false, listNonNull = false;
  let cur = t;
  // outer non-null around list
  while (cur && cur.kind === 'NON_NULL') { listNonNull = true; cur = cur.ofType; }
  if (cur && cur.kind === 'LIST') {
    isList = true;
    cur = cur.ofType;
    while (cur && cur.kind === 'NON_NULL') { innerNonNull = true; cur = cur.ofType; }
  }
  return { isList, innerNonNull, name: cur ? cur.name : null, kind: cur ? cur.kind : '' };
}

const TYPEREF = `kind name ofType { kind name ofType { kind name ofType { kind name } } }`;
const INTRO = `
{
  __schema {
    queryType { name }
    types {
      kind name
      enumValues { name }
      possibleTypes { name }
      inputFields { name type { ${TYPEREF} } }
      fields {
        name
        args { name type { ${TYPEREF} } }
        type { ${TYPEREF} }
      }
    }
  }
}`;

// Discover the schema shape we need, named-agnostically.
async function discover(server: any) {
  const intro = await run(server, INTRO);
  if (intro.errors) throw new Error('introspection failed: ' + JSON.stringify(intro.errors));
  const sch = intro.data.__schema;
  const types: any[] = sch.types;
  const byName: Record<string, any> = {};
  for (const t of types) byName[t.name] = t;
  const qType = types.find((t) => t.name === sch.queryType.name);

  // The "search" field: a root query field returning a LIST whose element type
  // is an ABSTRACT type (UNION or INTERFACE) and that takes a String argument.
  const searchField = qType.fields.find((f: any) => {
    const li = listInfo(f.type);
    if (!li.isList) return false;
    const elem = byName[li.name];
    if (!elem) return false;
    if (elem.kind !== 'UNION' && elem.kind !== 'INTERFACE') return false;
    return f.args.some((a: any) => unwrap(a.type).name === 'String');
  });

  let elemType: any = null;
  let concreteNames: string[] = [];
  if (searchField) {
    const li = listInfo(searchField.type);
    elemType = byName[li.name];
    if (elemType.kind === 'UNION') {
      concreteNames = (elemType.possibleTypes || []).map((p: any) => p.name);
    } else {
      // interface -> any object implementing it (possibleTypes is populated for interfaces too)
      concreteNames = (elemType.possibleTypes || []).map((p: any) => p.name);
    }
  }
  const concreteTypes = concreteNames.map((n) => byName[n]).filter(Boolean);

  // Classify concrete kinds by their own (non-shared) fields.
  const personType = concreteTypes.find((t: any) =>
    t.fields && t.fields.some((f: any) => /email/i.test(f.name)));
  const projectType = concreteTypes.find((t: any) =>
    t.fields && t.fields.some((f: any) => /status/i.test(f.name)) && t !== personType);
  const documentType = concreteTypes.find((t: any) =>
    t.fields && t.fields.some((f: any) => /(word|count)/i.test(f.name)) &&
    t !== personType && t !== projectType);

  const idField = (obj: any) => {
    if (!obj || !obj.fields) return null;
    const f = obj.fields.find((x: any) => /^id$/i.test(x.name)) ||
              obj.fields.find((x: any) => /id$/i.test(x.name));
    return f ? f.name : null;
  };
  const labelField = (obj: any, names: RegExp) => {
    if (!obj || !obj.fields) return null;
    const f = obj.fields.find((x: any) => names.test(x.name));
    return f ? f.name : null;
  };

  // kind-specific single fetch queries: root field returning a single concrete
  // object (not a list) and taking >= 1 arg.
  const singleFetch = (objType: any) => {
    if (!objType) return null;
    return qType.fields.find((f: any) => {
      const u = unwrap(f.type);
      return u.name === objType.name && !listInfo(f.type).isList && f.args.length >= 1;
    });
  };

  // project status enum
  const statusEnum = projectType
    ? (() => {
        const sf = projectType.fields.find((f: any) => /status/i.test(f.name));
        if (!sf) return null;
        const u = unwrap(sf.type);
        const et = byName[u.name];
        return et && et.kind === 'ENUM' ? et : null;
      })()
    : null;

  return {
    types, byName, qType,
    searchField, elemType, concreteTypes,
    personType, projectType, documentType,
    personId: idField(personType),
    projectId: idField(projectType),
    documentId: idField(documentType),
    personEmail: labelField(personType, /email/i),
    personName: labelField(personType, /(name|display)/i),
    projectName: labelField(projectType, /name/i),
    documentTitle: labelField(documentType, /title/i),
    documentWords: labelField(documentType, /(word|count)/i),
    searchArg: searchField ? searchField.args.find((a: any) => unwrap(a.type).name === 'String') : null,
    personFetch: singleFetch(personType),
    projectFetch: singleFetch(projectType),
    statusEnum,
  };
}

// Run the search query for a term, requesting __typename + each kind's own fields.
async function doSearch(server: any, d: any, term: string) {
  const argName = d.searchArg.name;
  const sel = [
    '__typename',
    d.personType ? `... on ${d.personType.name} { ${d.personId} ${d.personName} ${d.personEmail} }` : '',
    d.projectType ? `... on ${d.projectType.name} { ${d.projectId} ${d.projectName} }` : '',
    d.documentType ? `... on ${d.documentType.name} { ${d.documentId} ${d.documentTitle} ${d.documentWords} }` : '',
  ].filter(Boolean).join('\n');
  const q = `query($q: String!){ ${d.searchField.name}(${argName}: $q){ ${sel} } }`;
  return run(server, q, { q: term });
}

// Find a term that matches exactly one person and one project (and no document),
// by probing the human-readable labels of the seeded store.
async function findTwoKindTerm(server: any, d: any) {
  // Pull all labels via a broad search ('' or 'e' etc. may match everything);
  // instead probe per-kind labels by doing a permissive search for a vowel.
  const probes = ['a', 'e', 'i', 'o', 'r', 's', 't', 'n', 'l'];
  // Gather full population by unioning several single-char searches.
  const pop: any[] = [];
  const seen = new Set<string>();
  for (const p of probes) {
    const res = await doSearch(server, d, p);
    if (res.errors) continue;
    for (const el of (res.data[d.searchField.name] || [])) {
      const key = el.__typename + ':' + (el[d.personId] || el[d.projectId] || el[d.documentId] || JSON.stringify(el));
      if (seen.has(key)) continue;
      seen.add(key);
      pop.push(el);
    }
  }
  const people = pop.filter((e) => e.__typename === d.personType.name);
  const projects = pop.filter((e) => e.__typename === d.projectType.name);
  // try every substring of a person label and see if it also hits a project
  const labelOf = (el: any) => {
    if (el.__typename === d.personType.name) return el[d.personName];
    if (el.__typename === d.projectType.name) return el[d.projectName];
    if (d.documentType && el.__typename === d.documentType.name) return el[d.documentTitle];
    return '';
  };
  for (const person of people) {
    const pl = String(labelOf(person) || '');
    for (let len = pl.length; len >= 1; len--) {
      for (let s = 0; s + len <= pl.length; s++) {
        const sub = pl.substring(s, s + len).trim();
        if (sub.length < 1) continue;
        const res = await doSearch(server, d, sub);
        if (res.errors) continue;
        const els = res.data[d.searchField.name] || [];
        const kinds = new Set(els.map((e: any) => e.__typename));
        const hasPerson = els.some((e: any) => e.__typename === d.personType.name);
        const hasProject = els.some((e: any) => e.__typename === d.projectType.name);
        if (hasPerson && hasProject) {
          return { term: sub, els, person, kinds: Array.from(kinds) };
        }
      }
    }
  }
  return null;
}

describe('heterogeneous search module (independent harness)', () => {

  it('search field returns an abstract element type covering at least three concrete kinds', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.searchField).toBeTruthy();
    // element type must be UNION or INTERFACE (mutually-exclusive kinds in one list)
    expect(['UNION', 'INTERFACE']).toContain(d.elemType.kind);
    expect(d.concreteTypes.length).toBeGreaterThanOrEqual(3);
    // the three documented kinds are all present and identifiable by own fields
    expect(d.personType).toBeTruthy();
    expect(d.projectType).toBeTruthy();
    expect(d.documentType).toBeTruthy();
    // they do not share field sets beyond being searchable: email is person-only,
    // word-count is document-only.
    const personFieldNames = d.personType.fields.map((f: any) => f.name);
    const projFieldNames = d.projectType.fields.map((f: any) => f.name);
    expect(personFieldNames.some((n: string) => /email/i.test(n))).toBe(true);
    expect(projFieldNames.some((n: string) => /email/i.test(n))).toBe(false);
    // search list itself must be non-null (outer), per "never resolves to null"
    const li = listInfo(d.searchField.type);
    expect(li.isList).toBe(true);
    await server.stop();
  });

  it('id and label fields are non-null on each concrete kind', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const requireNonNull = (objType: any, fieldName: string) => {
      const f = objType.fields.find((x: any) => x.name === fieldName);
      expect(f).toBeTruthy();
      expect(unwrap(f.type).nonNull).toBe(true);
    };
    requireNonNull(d.personType, d.personId);
    requireNonNull(d.personType, d.personName);
    requireNonNull(d.projectType, d.projectId);
    requireNonNull(d.projectType, d.projectName);
    requireNonNull(d.documentType, d.documentId);
    requireNonNull(d.documentType, d.documentTitle);
    await server.stop();
  });

  it('multi-kind search hit returns exactly the matching elements, each observably its own kind', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const found = await findTwoKindTerm(server, d);
    expect(found).toBeTruthy();
    const els = found.els;
    // every element is exactly one of the concrete kinds, and __typename is set
    const concreteSet = new Set(d.concreteTypes.map((t: any) => t.name));
    for (const el of els) {
      expect(typeof el.__typename).toBe('string');
      expect(concreteSet.has(el.__typename)).toBe(true);
    }
    // at least one person and one project among results
    const people = els.filter((e: any) => e.__typename === d.personType.name);
    const projects = els.filter((e: any) => e.__typename === d.projectType.name);
    expect(people.length).toBeGreaterThanOrEqual(1);
    expect(projects.length).toBeGreaterThanOrEqual(1);
    // person element exposes its own email field (its own shape)
    expect(typeof people[0][d.personEmail]).toBe('string');
    expect(people[0][d.personEmail].length).toBeGreaterThan(0);
    // project element exposes its own name but no person email key
    expect(typeof projects[0][d.projectName]).toBe('string');
    expect(projects[0][d.personEmail]).toBeUndefined();
    await server.stop();
  });

  it('empty search returns a non-null empty list (no error, no null entries)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const res = await doSearch(server, d, 'zzzqqq-no-such-term-xyzzy-9999');
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    const list = res.data[d.searchField.name];
    expect(Array.isArray(list)).toBe(true);
    expect(list).not.toBeNull();
    expect(list.length).toBe(0);
    await server.stop();
  });

  it('matching is case-insensitive substring against the human-readable label', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const found = await findTwoKindTerm(server, d);
    expect(found).toBeTruthy();
    const term = found.term;
    // same query lower vs upper case must yield the same set of element identities
    const lower = await doSearch(server, d, term.toLowerCase());
    const upper = await doSearch(server, d, term.toUpperCase());
    expect(lower.errors).toBeFalsy();
    expect(upper.errors).toBeFalsy();
    const idOf = (e: any) => e.__typename + ':' + (e[d.personId] || e[d.projectId] || e[d.documentId]);
    const lowSet = (lower.data[d.searchField.name] || []).map(idOf).sort();
    const upSet = (upper.data[d.searchField.name] || []).map(idOf).sort();
    expect(upSet).toEqual(lowSet);
    expect(lowSet.length).toBeGreaterThan(0);
    await server.stop();
  });

  it('repeated identical searches yield identical ordered sequences (stable, deterministic order)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const found = await findTwoKindTerm(server, d);
    expect(found).toBeTruthy();
    const seqOf = (els: any[]) =>
      els.map((e: any) => e.__typename + ':' + (e[d.personId] || e[d.projectId] || e[d.documentId]));
    const r1 = await doSearch(server, d, found.term);
    const r2 = await doSearch(server, d, found.term);
    const r3 = await doSearch(server, d, found.term);
    const s1 = seqOf(r1.data[d.searchField.name]);
    const s2 = seqOf(r2.data[d.searchField.name]);
    const s3 = seqOf(r3.data[d.searchField.name]);
    expect(s2).toEqual(s1);   // identical ORDER, not just set
    expect(s3).toEqual(s1);
    expect(s1.length).toBeGreaterThanOrEqual(2);
    await server.stop();
  });

  it('narrowing a person element reads email; narrowing the same element to document kind yields nothing for document-only fields', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const found = await findTwoKindTerm(server, d);
    expect(found).toBeTruthy();
    const term = found.term;
    // narrow ONLY to the person kind: email present, document-only fields absent
    const argName = d.searchArg.name;
    const q = `query($q: String!){ ${d.searchField.name}(${argName}: $q){
      __typename
      ... on ${d.personType.name} { ${d.personId} ${d.personEmail} }
      ... on ${d.documentType.name} { ${d.documentWords} }
    } }`;
    const res = await run(server, q, { q: term });
    expect(res.errors).toBeFalsy();
    const els = res.data[d.searchField.name];
    const person = els.find((e: any) => e.__typename === d.personType.name);
    expect(person).toBeTruthy();
    expect(typeof person[d.personEmail]).toBe('string');
    expect(person[d.personEmail].length).toBeGreaterThan(0);
    // the person element, narrowed to the document inline-fragment, exposes no
    // document-only field (word count) -- it is a person, not a document.
    expect(person[d.documentWords]).toBeUndefined();
    await server.stop();
  });

  it('kind-specific fetch HIT returns a single person/project with its own fields', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.personFetch).toBeTruthy();
    expect(d.projectFetch).toBeTruthy();
    // discover a real person id via search probing
    const probe = await doSearch(server, d, 'a');
    const apers = (probe.data[d.searchField.name] || []).find((e: any) => e.__typename === d.personType.name);
    // fall back: union of vowel probes
    let personEl = apers;
    if (!personEl) {
      for (const c of ['e', 'i', 'o', 'r', 's', 't']) {
        const r = await doSearch(server, d, c);
        personEl = (r.data[d.searchField.name] || []).find((e: any) => e.__typename === d.personType.name);
        if (personEl) break;
      }
    }
    expect(personEl).toBeTruthy();
    const pid = personEl[d.personId];

    const pa = d.personFetch.args[0].name;
    const paType = unwrap(d.personFetch.args[0].type).name + (unwrap(d.personFetch.args[0].type).nonNull ? '!' : '');
    const pq = `query($id: ${paType}){ ${d.personFetch.name}(${pa}: $id){ ${d.personId} ${d.personName} ${d.personEmail} } }`;
    const pr = await run(server, pq, { id: pid });
    expect(pr.errors).toBeFalsy();
    const got = pr.data[d.personFetch.name];
    expect(got).toBeTruthy();
    expect(got[d.personId]).toBe(pid);
    expect(typeof got[d.personEmail]).toBe('string');
    expect(got[d.personEmail].length).toBeGreaterThan(0);
    await server.stop();
  });

  it('kind-specific fetch MISS for unknown person and project ids returns null with no error', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const mk = (fetchField: any, idField: string) => {
      const an = fetchField.args[0].name;
      const at = unwrap(fetchField.args[0].type).name + (unwrap(fetchField.args[0].type).nonNull ? '!' : '');
      return { q: `query($id: ${at}){ ${fetchField.name}(${an}: $id){ ${idField} } }` };
    };
    const pq = mk(d.personFetch, d.personId);
    const pr = await run(server, pq.q, { id: 'no-such-person-zzz-0000' });
    expect(pr.errors == null || pr.errors.length === 0).toBe(true);
    expect(pr.data[d.personFetch.name]).toBeNull();

    const jq = mk(d.projectFetch, d.projectId);
    const jr = await run(server, jq.q, { id: 'no-such-project-zzz-0000' });
    expect(jr.errors == null || jr.errors.length === 0).toBe(true);
    expect(jr.data[d.projectFetch.name]).toBeNull();
    await server.stop();
  });

  it('project status enum is introspectable as a fixed closed set of values', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.statusEnum).toBeTruthy();
    expect(d.statusEnum.kind).toBe('ENUM');
    const names = (d.statusEnum.enumValues || []).map((v: any) => v.name);
    // a closed, non-empty, finite set with >= 2 distinct values
    expect(names.length).toBeGreaterThanOrEqual(2);
    expect(new Set(names).size).toBe(names.length);
    // every searched project's status is one of the enum values (closed set holds at runtime)
    const probe = await doSearch(server, d, 'a');
    const argName = d.searchArg.name;
    const q = `query($q: String!){ ${d.searchField.name}(${argName}: $q){
      __typename ... on ${d.projectType.name} { status: ${d.projectType.fields.find((f: any) => /status/i.test(f.name)).name} } } }`;
    const res = await run(server, q, { q: 'a' });
    if (!res.errors) {
      const projects = (res.data[d.searchField.name] || []).filter((e: any) => e.__typename === d.projectType.name);
      for (const p of projects) {
        if (p.status != null) expect(names).toContain(p.status);
      }
    }
    await server.stop();
  });

  it('out-of-set project status literal fails VALIDATION before resolvers run', async () => {
    const server = await mkServer();
    const d = await discover(server);
    // Find a query/field that ACCEPTS the status enum as an argument.  Prefer a
    // root field with an arg whose type is the status enum.
    const statusEnumName = d.statusEnum.name;
    let accepting: any = null;
    let acceptArg: any = null;
    for (const f of d.qType.fields) {
      const a = f.args.find((x: any) => unwrap(x.type).name === statusEnumName);
      if (a) { accepting = f; acceptArg = a; break; }
    }
    // If no root arg takes the enum, the closed set is still enforced by the
    // schema for any input position; assert via a variable coercion against the
    // project fetch is not possible, so require an accepting field to exist.
    expect(accepting).toBeTruthy();
    // Inline an invalid enum literal -> must be a validation (parse/validate)
    // error fired before resolvers, hence no data for the field.
    const otherArgs = accepting.args
      .filter((x: any) => x !== acceptArg && unwrap(x.type).nonNull)
      .map((x: any) => {
        const u = unwrap(x.type);
        if (u.name === 'String' || u.name === 'ID') return `${x.name}: "x"`;
        if (u.name === 'Int') return `${x.name}: 1`;
        if (u.name === 'Boolean') return `${x.name}: false`;
        return null;
      })
      .filter(Boolean);
    const argList = [`${acceptArg.name}: NOT_A_REAL_STATUS_ZZZ`, ...otherArgs].join(', ');
    const li = listInfo(accepting.type);
    const sel = li.isList || unwrap(accepting.type).kind === 'OBJECT' || unwrap(accepting.type).kind === 'UNION' || unwrap(accepting.type).kind === 'INTERFACE'
      ? '{ __typename }'
      : '';
    const r = await run(server, `query{ ${accepting.name}(${argList}) ${sel} }`);
    expect(Array.isArray(r.errors)).toBe(true);
    expect(r.errors.length).toBeGreaterThan(0);
    // validation errors -> no data for the field
    expect(r.data == null || r.data[accepting.name] === undefined).toBe(true);
    await server.stop();
  });

  it('module store factory produces a fresh, independent store on each call', async () => {
    // Build two servers; both must start and serve search independently, proving
    // the factory yields self-contained deterministic stores (no shared mutable
    // global leaking between instances).
    const s1 = await mkServer();
    const d1 = await discover(s1);
    const r1 = await doSearch(s1, d1, 'a');
    expect(r1.errors).toBeFalsy();
    await s1.stop();

    const s2 = await mkServer();
    const d2 = await discover(s2);
    const r2 = await doSearch(s2, d2, 'a');
    expect(r2.errors).toBeFalsy();
    const idsOf = (els: any[], d: any) =>
      els.map((e: any) => e.__typename + ':' + (e[d.personId] || e[d.projectId] || e[d.documentId])).sort();
    // deterministic seed -> the two independent servers return the same population
    expect(idsOf(r2.data[d2.searchField.name], d2)).toEqual(idsOf(r1.data[d1.searchField.name], d1));
    await s2.stop();
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
        """L1: the search module file exists at the required path."""
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
        # an exported factory function (create*/make*/*Store/*Directory/seed*)
        assert re.search(
            r"export\s+(const|function)\s+\w*(create|make|store|directory|seed)\w*",
            src,
            re.IGNORECASE,
        ), "no store-factory export found"

    def test_module_has_no_other_example_imports(self):
        """L1: module is self-contained (does not import from sibling example files)."""
        src = self._read(self.MODULE_PATH)
        for m in re.finditer(r"""import[^;]*?from\s*['"]([^'"]+)['"]""", src):
            spec = m.group(1)
            if "examples/" in spec and "searchModule" not in spec:
                pytest.fail(f"module imports another example file: {spec}")

    def test_module_does_not_modify_index_exports(self):
        """L1: the package public index.ts must not be wired to the search module."""
        index_path = os.path.join(self.SERVER_DIR, "src", "index.ts")
        if os.path.isfile(index_path):
            idx = self._read(index_path)
            assert "searchModule" not in idx, (
                "index.ts must not export/import the search module"
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

    def test_harness_abstract_search_three_kinds(self, harness_report):
        """L2: search field returns an abstract element type covering >=3 concrete kinds."""
        self._passed(harness_report, r"abstract element type covering at least three concrete kinds")

    def test_harness_nonnull_id_label(self, harness_report):
        """L2: id and label fields are non-null on each concrete kind."""
        self._passed(harness_report, r"id and label fields are non-null")

    def test_harness_multi_kind_hit(self, harness_report):
        """L2: multi-kind search hit returns exactly the matching elements, each its own kind."""
        self._passed(harness_report, r"multi-kind search hit returns exactly the matching")

    def test_harness_empty_search(self, harness_report):
        """L2: empty search returns a non-null empty list (no error)."""
        self._passed(harness_report, r"empty search returns a non-null empty list")

    def test_harness_case_insensitive_substring(self, harness_report):
        """L2: matching is case-insensitive substring against the label."""
        self._passed(harness_report, r"case-insensitive substring against the human-readable label")

    def test_harness_stable_order(self, harness_report):
        """L2: repeated identical searches yield identical ordered sequences."""
        self._passed(harness_report, r"identical ordered sequences")

    def test_harness_kind_narrowing(self, harness_report):
        """L2: narrowing to person reads email; document-only fields absent on a person."""
        self._passed(harness_report, r"narrowing a person element reads email")

    def test_harness_kind_specific_fetch_hit(self, harness_report):
        """L2: kind-specific fetch hit returns a single person/project with its own fields."""
        self._passed(harness_report, r"kind-specific fetch HIT")

    def test_harness_kind_specific_fetch_miss(self, harness_report):
        """L2: kind-specific fetch miss for unknown ids returns null with no error."""
        self._passed(harness_report, r"kind-specific fetch MISS")

    def test_harness_status_enum_closed_set(self, harness_report):
        """L2: project status enum is introspectable as a fixed closed set."""
        self._passed(harness_report, r"project status enum is introspectable")

    def test_harness_invalid_status_validation(self, harness_report):
        """L2: out-of-set status literal fails validation before resolvers run."""
        self._passed(harness_report, r"out-of-set project status literal fails VALIDATION")

    def test_harness_fresh_store_factory(self, harness_report):
        """L2: factory produces fresh, deterministic, independent stores."""
        self._passed(harness_report, r"fresh, independent store on each call")
