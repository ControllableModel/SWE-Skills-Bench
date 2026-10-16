"""Benchmark tests for the `graphql-schema-design` skill.

Skill task: build a self-contained "library catalog" GraphQL feature module inside
the `@apollo/server` package (`packages/server/src/examples/libraryCatalog.ts`) that
exports `typeDefs` (SDL string), `resolvers`, and an in-memory data-store factory,
plus a Jest test suite at
`packages/server/src/__tests__/examples/libraryCatalog.test.ts`.

What this file verifies
-----------------------
L1 (existence / minimal well-formedness):
  - the two deliverable files exist,
  - the module exports `typeDefs` / `resolvers` / a store factory,
  - the agent's own Jest suite declares >= 10 `it`/`test` cases,
  - the agent's own Jest suite passes (acceptance command).

L2 (dynamic execution -- the discriminative core):
  Instead of trusting the agent's own test file, we synthesize an INDEPENDENT
  TypeScript Jest harness, drop it next to the module, and run it through the
  repo's native `jest` toolchain.  The harness builds an `ApolloServer` directly
  from the module's `typeDefs`/`resolvers`, introspects the schema to discover
  the real field / enum / argument names (so we do not hard-code the agent's
  naming choices), and then exercises every Acceptance-Criterion scenario:
  single fetch hit/miss for both entities, nested author<->books resolution,
  full forward-pagination traversal with no dup/omission, status filtering, the
  introspectable fixed status value set, invalid-status validation failure that
  fires *before* resolvers run, default-status creation, created-id uniqueness,
  and the author-not-found mutation outcome distinguished from success without
  the top-level `errors` array.

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
    MODULE_REL = "src/examples/libraryCatalog.ts"
    SUITE_REL = "src/__tests__/examples/libraryCatalog.test.ts"
    MODULE_PATH = os.path.join(SERVER_DIR, "src", "examples", "libraryCatalog.ts")
    SUITE_PATH = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "libraryCatalog.test.ts"
    )

    # Directory where we drop our own independent harness suite.
    HARNESS_DIR = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "__bench__"
    )
    HARNESS_NAME = "benchLibraryCatalog.test.ts"
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
        #   - module under test -> ../../../examples/libraryCatalog.js
        return r"""// @ts-nocheck
import { describe, it, expect } from '@jest/globals';
import { ApolloServer } from '../../../index.js';
import * as mod from '../../../examples/libraryCatalog.js';

// ---- locate exports without hard-coding the factory's name -----------------
const typeDefs: any = (mod as any).typeDefs;
const resolvers: any = (mod as any).resolvers;

function findFactory(): (() => any) | null {
  // Prefer common names, else first zero-or-defaulted-arg function export that
  // is not typeDefs/resolvers.
  const preferred = [
    'createStore', 'makeStore', 'createCatalog', 'makeCatalog',
    'createDataStore', 'createInMemoryStore', 'storeFactory', 'createCatalogStore',
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

// Introspection helpers to discover real schema shape ------------------------
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

describe('library catalog (independent harness)', () => {

  it('schema builds and exposes book/author entities with id distinct from name/title', async () => {
    const server = await mkServer();
    const intro = await run(server, INTRO);
    expect(intro.errors).toBeFalsy();
    const types: any[] = intro.data.__schema.types;
    const byName: Record<string, any> = {};
    for (const t of types) byName[t.name] = t;

    const bookT = types.find(
      (t) => t.kind === 'OBJECT' && t.fields &&
        t.fields.some((f: any) => f.name === 'title') &&
        t.fields.some((f: any) => /year/i.test(f.name)),
    );
    const authorT = types.find(
      (t) => t.kind === 'OBJECT' && t.fields &&
        t.fields.some((f: any) => f.name === 'name') &&
        t.fields.some((f: any) => unwrap(f.type).list && byName),
    );
    expect(bookT).toBeTruthy();
    expect(authorT).toBeTruthy();

    // id field present and never null on both
    for (const t of [bookT, authorT]) {
      const idf = t.fields.find((f: any) => /^id$/i.test(f.name) || /id$/i.test(f.name));
      expect(idf).toBeTruthy();
      expect(unwrap(idf.type).nonNull).toBe(true);
    }
    // title/year/status non-null; summary nullable
    const title = bookT.fields.find((f: any) => f.name === 'title');
    const year = bookT.fields.find((f: any) => /year/i.test(f.name));
    expect(unwrap(title.type).nonNull).toBe(true);
    expect(unwrap(year.type).nonNull).toBe(true);
    const summary = bookT.fields.find((f: any) => /summary/i.test(f.name));
    if (summary) expect(unwrap(summary.type).nonNull).toBe(false);
    await server.stop();
  });

  it('reading-status enum is introspectable and has exactly 3 values', async () => {
    const server = await mkServer();
    const intro = await run(server, INTRO);
    const enums = intro.data.__schema.types.filter(
      (t: any) => t.kind === 'ENUM' && Array.isArray(t.enumValues) &&
        t.enumValues.some((v: any) => /finish/i.test(v.name)),
    );
    expect(enums.length).toBeGreaterThanOrEqual(1);
    const statusEnum = enums[0];
    const names = statusEnum.enumValues.map((v: any) => v.name);
    expect(names.length).toBe(3);
    expect(names.some((n: string) => /finish/i.test(n))).toBe(true);
    expect(names.some((n: string) => /progress/i.test(n))).toBe(true);
    expect(names.some((n: string) => /(not.?started|unread|todo)/i.test(n))).toBe(true);
    (global as any).__statusEnum = names;
    await server.stop();
  });

  // ---- behavioral discovery: build queries from a seeded server -------------
  async function discover(server: any) {
    const intro = await run(server, INTRO);
    const sch = intro.data.__schema;
    const qName = sch.queryType.name;
    const mName = sch.mutationType ? sch.mutationType.name : null;
    const types: any[] = sch.types;
    const qType = types.find((t) => t.name === qName);
    const mType = mName ? types.find((t) => t.name === mName) : null;

    const bookObj = types.find(
      (t) => t.kind === 'OBJECT' && t.fields &&
        t.fields.some((f: any) => f.name === 'title'),
    );
    const authorObj = types.find(
      (t) => t.kind === 'OBJECT' && t.fields && t.fields.some((f: any) => f.name === 'name') &&
        t.name !== bookObj.name,
    );
    const idField = (obj: any) =>
      (obj.fields.find((f: any) => /^id$/i.test(f.name)) ||
        obj.fields.find((f: any) => /id$/i.test(f.name))).name;

    // single-book query: returns bookObj, takes one id-ish arg
    const bookQ = qType.fields.find((f: any) => {
      const u = unwrap(f.type);
      return u.name === bookObj.name && !u.list && f.args.length >= 1;
    });
    const authorQ = qType.fields.find((f: any) => {
      const u = unwrap(f.type);
      return u.name === authorObj.name && !u.list && f.args.length >= 1;
    });
    // list/pagination query: a root field returning a *connection* object that
    // has a list field whose elements are Books (directly) or edges whose node is
    // a Book.  Must NOT match the single `author` query (which returns an Author
    // that merely happens to own a `books` list) -- so the connection object itself
    // must not be the Author or Book type, and the page must carry Books.
    const isBookList = (ct: any) => {
      for (const cf of ct.fields) {
        const cu = unwrap(cf.type);
        if (!cu.list) continue;
        if (cu.name === bookObj.name) return cf; // list of Book
        // list of edges -> node: Book
        const elem = types.find((t: any) => t.name === cu.name);
        if (elem && elem.fields && elem.fields.some((ef: any) => unwrap(ef.type).name === bookObj.name)) {
          return cf;
        }
      }
      return null;
    };
    let listQ: any = null;
    let connObj: any = null;
    let itemsField: any = null;
    // prefer candidates that take an Int (page size) argument
    const candidates = qType.fields.filter((f: any) => {
      const u = unwrap(f.type);
      if (u.kind !== 'OBJECT' || !u.name) return false;
      if (u.name === bookObj.name || u.name === authorObj.name) return false;
      const ct = types.find((t: any) => t.name === u.name);
      return ct && ct.fields && isBookList(ct);
    });
    candidates.sort((a: any, b: any) => {
      const ai = a.args.some((x: any) => unwrap(x.type).name === 'Int') ? 0 : 1;
      const bi = b.args.some((x: any) => unwrap(x.type).name === 'Int') ? 0 : 1;
      return ai - bi;
    });
    if (candidates.length) {
      listQ = candidates[0];
      connObj = types.find((t: any) => t.name === unwrap(listQ.type).name);
      itemsField = isBookList(connObj);
    }

    return {
      qName, mName, qType, mType, types,
      bookObj, authorObj,
      bookId: idField(bookObj), authorId: idField(authorObj),
      bookQ, authorQ, listQ, connObj, itemsField,
      yearField: bookObj.fields.find((f: any) => /year/i.test(f.name)).name,
      statusField: (bookObj.fields.find((f: any) => /status/i.test(f.name)) || {}).name,
      booksOnAuthor: (authorObj.fields.find((f: any) => unwrap(f.type).list) || {}).name,
      authorOnBook: (bookObj.fields.find((f: any) => unwrap(f.type).name === authorObj.name) || {}).name,
    };
  }

  it('single book fetch HIT returns correct fields and nested author name', async () => {
    const server = await mkServer();
    const d = await discover(server);
    // get a known id by listing
    const listSel = buildListSelection(d, 5);
    const page = await run(server, `query{ ${d.listQ.name}${listArgs(d, 5)} { ${listSel} } }`);
    expect(page.errors).toBeFalsy();
    const ids = extractBookIds(page.data[d.listQ.name], d);
    expect(ids.length).toBeGreaterThan(0);
    const known = ids[0];

    const argName = d.bookQ.args[0].name;
    const q = `query($id: ${argTypeStr(d.bookQ.args[0])}){ ${d.bookQ.name}(${argName}: $id){ ${d.bookId} title ${d.yearField} ${d.statusField} ${d.authorOnBook} { name } } }`;
    const res = await run(server, q, { id: known });
    expect(res.errors).toBeFalsy();
    const b = res.data[d.bookQ.name];
    expect(b).toBeTruthy();
    expect(typeof b.title).toBe('string');
    expect(b.title.length).toBeGreaterThan(0);
    expect(typeof b[d.yearField]).toBe('number');
    expect(b[d.authorOnBook]).toBeTruthy();
    expect(typeof b[d.authorOnBook].name).toBe('string');
    expect(b[d.authorOnBook].name.length).toBeGreaterThan(0);
    await server.stop();
  });

  it('single book fetch MISS yields null book and no execution error', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const argName = d.bookQ.args[0].name;
    const q = `query($id: ${argTypeStr(d.bookQ.args[0])}){ ${d.bookQ.name}(${argName}: $id){ ${d.bookId} } }`;
    const res = await run(server, q, { id: 'definitely-not-a-real-id-zzz' });
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    expect(res.data[d.bookQ.name]).toBeNull();
    await server.stop();
  });

  it('single author fetch MISS yields null author and no execution error', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const argName = d.authorQ.args[0].name;
    const q = `query($id: ${argTypeStr(d.authorQ.args[0])}){ ${d.authorQ.name}(${argName}: $id){ ${d.authorId} } }`;
    const res = await run(server, q, { id: 'no-such-author-zzz' });
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    expect(res.data[d.authorQ.name]).toBeNull();
    await server.stop();
  });

  it('nested author->books and book->author resolve as objects/lists', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const listSel = buildListSelection(d, 5);
    const page = await run(server, `query{ ${d.listQ.name}${listArgs(d, 5)} { ${listSel} } }`);
    const ids = extractBookIds(page.data[d.listQ.name], d);
    const known = ids[0];
    const argName = d.bookQ.args[0].name;
    const q = `query($id: ${argTypeStr(d.bookQ.args[0])}){ ${d.bookQ.name}(${argName}: $id){ ${d.authorOnBook} { ${d.authorId} name ${d.booksOnAuthor} { ${d.bookId} } } } }`;
    const res = await run(server, q, { id: known });
    expect(res.errors).toBeFalsy();
    const author = res.data[d.bookQ.name][d.authorOnBook];
    expect(Array.isArray(author[d.booksOnAuthor])).toBe(true);
    expect(author[d.booksOnAuthor].length).toBeGreaterThan(0);
    // the original book must appear among the author's books
    const childIds = author[d.booksOnAuthor].map((x: any) => x[d.bookId]);
    expect(childIds).toContain(known);
    await server.stop();
  });

  it('forward pagination in pages of 2 visits every book exactly once, last page reports no more', async () => {
    const server = await mkServer();
    const d = await discover(server);

    // total set of ids via a big page
    const bigSel = buildListSelection(d, 1000);
    const big = await run(server, `query{ ${d.listQ.name}${listArgs(d, 1000)} { ${bigSel} } }`);
    const allIds = extractBookIds(big.data[d.listQ.name], d);
    const totalSet = new Set(allIds);
    expect(totalSet.size).toBeGreaterThanOrEqual(3);

    const { cursorArg, sizeArg } = pageArgs(d);
    expect(cursorArg).toBeTruthy();
    expect(sizeArg).toBeTruthy();

    const seen: string[] = [];
    let after: string | null = null;
    let lastHasMore: any = null;
    for (let i = 0; i < 50; i++) {
      const args: string[] = [`${sizeArg}: 2`];
      if (after != null) args.push(`${cursorArg}: ${JSON.stringify(after)}`);
      const sel = buildPageSelection(d);
      const r = await run(server, `query{ ${d.listQ.name}(${args.join(', ')}) { ${sel} } }`);
      expect(r.errors).toBeFalsy();
      const conn = r.data[d.listQ.name];
      const pageIds = extractBookIds(conn, d);
      expect(pageIds.length).toBeLessThanOrEqual(2);
      for (const id of pageIds) seen.push(id);
      const pi = extractPageInfo(conn, d);
      lastHasMore = pi.hasMore;
      if (!pi.hasMore) break;
      // cursor to resume from: prefer pageInfo.endCursor, else the last edge cursor
      const resume = pi.endCursor != null ? pi.endCursor : extractLastCursor(conn, d);
      expect(resume).toBeTruthy();
      after = resume;
    }
    // no duplicates, no omissions
    expect(new Set(seen).size).toBe(seen.length);
    expect(new Set(seen)).toEqual(totalSet);
    // final page reports no more
    expect(!!lastHasMore).toBe(false);
    await server.stop();
  });

  it('status filter FINISHED returns only finished books', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const intro = await run(server, INTRO);
    const statusEnum = intro.data.__schema.types.find(
      (t: any) => t.kind === 'ENUM' && t.enumValues &&
        t.enumValues.some((v: any) => /finish/i.test(v.name)),
    );
    const finished = statusEnum.enumValues.map((v: any) => v.name).find((n: string) => /finish/i.test(n));

    // find a status-typed arg on the list query
    const statusArg = d.listQ.args.find((a: any) => unwrap(a.type).name === statusEnum.name);
    expect(statusArg).toBeTruthy();
    const { sizeArg } = pageArgs(d);
    const sel = buildListSelection(d, 1000, /*withStatus*/ true);
    const r = await run(
      server,
      `query{ ${d.listQ.name}(${sizeArg}: 1000, ${statusArg.name}: ${finished}) { ${sel} } }`,
    );
    expect(r.errors).toBeFalsy();
    const items = extractBookObjects(r.data[d.listQ.name], d);
    expect(items.length).toBeGreaterThan(0);
    for (const it of items) {
      expect(it[d.statusField]).toBe(finished);
    }
    // and there exists at least one non-finished book overall (filter is meaningful)
    const allSel = buildListSelection(d, 1000, true);
    const all = await run(server, `query{ ${d.listQ.name}(${sizeArg}: 1000) { ${allSel} } }`);
    const allItems = extractBookObjects(all.data[d.listQ.name], d);
    expect(allItems.length).toBeGreaterThan(items.length);
    await server.stop();
  });

  it('invalid reading-status string fails VALIDATION before resolvers (errors, no data for field)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const intro = await run(server, INTRO);
    const statusEnum = intro.data.__schema.types.find(
      (t: any) => t.kind === 'ENUM' && t.enumValues &&
        t.enumValues.some((v: any) => /finish/i.test(v.name)),
    );
    const statusArg = d.listQ.args.find((a: any) => unwrap(a.type).name === statusEnum.name);
    const { sizeArg } = pageArgs(d);
    // Inline an invalid enum literal -> must be a validation (parse/validate) error.
    const r = await run(
      server,
      `query{ ${d.listQ.name}(${sizeArg}: 5, ${statusArg.name}: NOT_A_REAL_STATUS) { ${buildListSelection(d, 5)} } }`,
    );
    expect(Array.isArray(r.errors)).toBe(true);
    expect(r.errors!.length).toBeGreaterThan(0);
    // validation errors -> no data at all
    expect(r.data == null || r.data[d.listQ.name] === undefined).toBe(true);
    await server.stop();
  });

  // ---- mutation discovery & tests ------------------------------------------
  async function mutationInfo(server: any, d: any) {
    expect(d.mType).toBeTruthy();
    const addM = d.mType.fields.find((f: any) =>
      /add|create/i.test(f.name) && unwrap(f.type).kind === 'OBJECT',
    );
    expect(addM).toBeTruthy();
    // single structured (INPUT_OBJECT) argument
    const inputArg = addM.args.find((a: any) => unwrap(a.type).kind === 'INPUT_OBJECT');
    expect(inputArg).toBeTruthy();
    const payloadType = d.types.find((t: any) => t.name === unwrap(addM.type).name);
    return { addM, inputArg, payloadType };
  }

  it('mutation accepts a single structured (input object) argument', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const { addM, inputArg } = await mutationInfo(server, d);
    // exactly one structured arg drives the mutation (other args, if any, are not scalar spam)
    const structured = addM.args.filter((a: any) => unwrap(a.type).kind === 'INPUT_OBJECT');
    expect(structured.length).toBe(1);
    expect(inputArg).toBeTruthy();
    await server.stop();
  });

  it('add book with existing author, no status -> defaults to NOT_STARTED, new unique id, refetchable', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const { addM, inputArg, payloadType } = await mutationInfo(server, d);

    // existing author id
    const authorsPage = await run(server, `query{ ${d.listQ.name}${listArgs(d, 1)} { ${buildListSelection(d, 1)} } }`);
    const someBookIds = extractBookIds(authorsPage.data[d.listQ.name], d);
    // get an author id via a known book's author
    const bookArg = d.bookQ.args[0].name;
    const bk = await run(server, `query($id:${argTypeStr(d.bookQ.args[0])}){ ${d.bookQ.name}(${bookArg}:$id){ ${d.authorOnBook}{ ${d.authorId} } } }`, { id: someBookIds[0] });
    const existingAuthorId = bk.data[d.bookQ.name][d.authorOnBook][d.authorId];
    expect(existingAuthorId).toBeTruthy();

    // collect existing ids before mutation
    const before = await run(server, `query{ ${d.listQ.name}${listArgs(d, 1000)} { ${buildListSelection(d, 1000)} } }`);
    const existingIds = new Set(extractBookIds(before.data[d.listQ.name], d));

    // build the input object from its fields
    const inputObjType = d.types.find((t: any) => t.name === unwrap(inputArg.type).name);
    const inputVar = buildAddInput(inputObjType, existingAuthorId, /*omitStatus*/ true);
    // build selection: dig for nested book + its id/status
    const sel = buildPayloadBookSelection(payloadType, d);
    const m = `mutation($in: ${unwrap(inputArg.type).name}!){ ${addM.name}(${inputArg.name}: $in){ ${sel} } }`;
    const res = await run(server, m, { in: inputVar });
    expect(res.errors == null || res.errors.length === 0).toBe(true);

    const created = digCreatedBook(res.data[addM.name], d);
    expect(created).toBeTruthy();
    expect(created[d.bookId]).toBeTruthy();
    expect(existingIds.has(created[d.bookId])).toBe(false); // unique
    // default status NOT_STARTED
    const ns = (global as any).__nsStatus || pickNotStarted(d, server);
    expect(/(not.?started|unread|todo)/i.test(String(created[d.statusField]))).toBe(true);

    // refetch returns the same book
    const re = await run(server, `query($id:${argTypeStr(d.bookQ.args[0])}){ ${d.bookQ.name}(${d.bookQ.args[0].name}:$id){ ${d.bookId} title ${d.statusField} } }`, { id: created[d.bookId] });
    expect(re.data[d.bookQ.name]).toBeTruthy();
    expect(re.data[d.bookQ.name][d.bookId]).toBe(created[d.bookId]);
    await server.stop();
  });

  it('created book ids are unique across multiple additions', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const { addM, inputArg, payloadType } = await mutationInfo(server, d);
    const page = await run(server, `query{ ${d.listQ.name}${listArgs(d, 1)} { ${buildListSelection(d, 1)} } }`);
    const aBook = extractBookIds(page.data[d.listQ.name], d)[0];
    const bk = await run(server, `query($id:${argTypeStr(d.bookQ.args[0])}){ ${d.bookQ.name}(${d.bookQ.args[0].name}:$id){ ${d.authorOnBook}{ ${d.authorId} } } }`, { id: aBook });
    const authorId = bk.data[d.bookQ.name][d.authorOnBook][d.authorId];

    const inputObjType = d.types.find((t: any) => t.name === unwrap(inputArg.type).name);
    const sel = buildPayloadBookSelection(payloadType, d);
    const made: string[] = [];
    for (let i = 0; i < 3; i++) {
      const inputVar = buildAddInput(inputObjType, authorId, true, i);
      const res = await run(server, `mutation($in: ${unwrap(inputArg.type).name}!){ ${addM.name}(${inputArg.name}: $in){ ${sel} } }`, { in: inputVar });
      const created = digCreatedBook(res.data[addM.name], d);
      expect(created).toBeTruthy();
      made.push(created[d.bookId]);
    }
    expect(new Set(made).size).toBe(made.length);
    await server.stop();
  });

  it('add book for MISSING author -> result payload signals not-found, top-level errors empty', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const { addM, inputArg, payloadType } = await mutationInfo(server, d);
    const inputObjType = d.types.find((t: any) => t.name === unwrap(inputArg.type).name);
    const inputVar = buildAddInput(inputObjType, 'no-such-author-zzz', true);

    // request a selection that also surfaces non-book payload fields so a client
    // can distinguish the failure (e.g. a boolean/message/error code/union).
    const sel = buildFullPayloadSelection(payloadType, d);
    const res = await run(server, `mutation($in: ${unwrap(inputArg.type).name}!){ ${addM.name}(${inputArg.name}: $in){ ${sel} } }`, { in: inputVar });

    // top-level errors must be empty (recoverable outcome)
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    const payload = res.data[addM.name];
    expect(payload).toBeTruthy();
    const created = digCreatedBook(payload, d);
    // no book was created
    expect(created == null || created[d.bookId] == null).toBe(true);
    // and there is some discriminating signal in the payload distinct from success
    expect(payloadSignalsFailure(payload, d)).toBe(true);
    await server.stop();
  });
});

// ============================ tiny query builders ===========================
function argTypeStr(arg: any): string {
  const u = unwrapTopName(arg.type);
  return u;
}
function unwrapTopName(t: any): string {
  // produce a SDL-ish type string for a variable definition
  if (!t) return 'ID';
  if (t.kind === 'NON_NULL') return unwrapTopName(t.ofType) + '!';
  if (t.kind === 'LIST') return '[' + unwrapTopName(t.ofType) + ']';
  return t.name || 'ID';
}
function unwrap(t: any): any {
  let nonNull = false, list = false, cur = t;
  while (cur) {
    if (cur.kind === 'NON_NULL') { nonNull = true; cur = cur.ofType; continue; }
    if (cur.kind === 'LIST') { list = true; cur = cur.ofType; continue; }
    break;
  }
  return { kind: cur ? cur.kind : '', name: cur ? cur.name : null, nonNull, list };
}

// page-size / cursor argument discovery on the list query
function pageArgs(d: any) {
  let sizeArg: string | null = null, cursorArg: string | null = null;
  for (const a of d.listQ.args) {
    const u = unwrap(a.type);
    if ((u.name === 'Int') && /(first|size|limit|count|page)/i.test(a.name)) sizeArg = a.name;
    if ((u.name === 'String' || u.name === 'ID') && /(after|cursor|from|page.?token)/i.test(a.name)) cursorArg = a.name;
  }
  if (!sizeArg) {
    const a = d.listQ.args.find((x: any) => unwrap(x.type).name === 'Int');
    if (a) sizeArg = a.name;
  }
  if (!cursorArg) {
    // any String/ID arg that is not the enum status filter
    const a = d.listQ.args.find(
      (x: any) => ['String', 'ID'].includes(unwrap(x.type).name) && unwrap(x.type).kind !== 'ENUM',
    );
    if (a) cursorArg = a.name;
  }
  return { sizeArg, cursorArg };
}
function listArgs(d: any, size: number) {
  const { sizeArg } = pageArgs(d);
  return sizeArg ? `(${sizeArg}: ${size})` : '';
}

// The connection object has either edges{node{...}} or nodes/items list of books.
function buildPageSelection(d: any): string {
  const conn = d.connObj;
  const listF = d.itemsField;
  const u = unwrap(listF.type);
  const listElemType = d.types.find((t: any) => t.name === u.name);
  let bookSel: string;
  if (listElemType && listElemType.name === d.bookObj.name) {
    bookSel = `${listF.name} { ${d.bookId} ${d.statusField} }`;
  } else {
    // edges -> node (+ per-edge opaque cursor if present)
    const nodeField = listElemType.fields.find((f: any) => unwrap(f.type).name === d.bookObj.name);
    const edgeCursor = listElemType.fields.find(
      (f: any) => /cursor/i.test(f.name) && ['String', 'ID'].includes(unwrap(f.type).name),
    );
    const cursorSel = edgeCursor ? ` ${edgeCursor.name}` : '';
    bookSel = `${listF.name} { ${nodeField.name} { ${d.bookId} ${d.statusField} }${cursorSel} }`;
  }
  const pageInfo = pageInfoSelection(d);
  return `${bookSel} ${pageInfo}`;
}
function buildListSelection(d: any, size: number, withStatus = false): string {
  return buildPageSelection(d);
}
function pageInfoSelection(d: any): string {
  // find a field on conn that is an object holding hasMore/endCursor, OR scalar fields directly
  const conn = d.connObj;
  // direct scalar booleans on the connection?
  const directBool = conn.fields.find((f: any) => /(hasNext|hasMore|moreFollow)/i.test(f.name) && unwrap(f.type).name === 'Boolean');
  const directCursor = conn.fields.find((f: any) => /(endCursor|nextCursor|cursor)/i.test(f.name) && ['String', 'ID'].includes(unwrap(f.type).name));
  if (directBool || directCursor) {
    let s = '';
    if (directBool) s += ` ${directBool.name}`;
    if (directCursor) s += ` ${directCursor.name}`;
    return s;
  }
  // nested pageInfo object
  const piField = conn.fields.find((f: any) => {
    const u = unwrap(f.type);
    if (u.kind !== 'OBJECT') return false;
    const t = d.types.find((x: any) => x.name === u.name);
    return t && t.fields && t.fields.some((cf: any) => /(hasNext|hasMore)/i.test(cf.name));
  });
  if (piField) {
    const t = d.types.find((x: any) => x.name === unwrap(piField.type).name);
    const b = t.fields.find((cf: any) => /(hasNext|hasMore|moreFollow)/i.test(cf.name));
    const c = t.fields.find((cf: any) => /(endCursor|nextCursor)/i.test(cf.name));
    return `${piField.name} { ${b ? b.name : ''} ${c ? c.name : ''} }`;
  }
  return '';
}
function extractBookObjects(conn: any, d: any): any[] {
  if (conn == null) return [];
  const listF = d.itemsField.name;
  const arr = conn[listF];
  if (!Array.isArray(arr)) return [];
  // could be books directly or edges with node
  return arr.map((x: any) => (x && x[d.bookId] !== undefined ? x : (x ? x[firstObjKey(x)] : x))).filter(Boolean);
}
function firstObjKey(o: any): string {
  for (const k of Object.keys(o)) if (o[k] && typeof o[k] === 'object') return k;
  return Object.keys(o)[0];
}
function extractBookIds(conn: any, d: any): string[] {
  return extractBookObjects(conn, d).map((b: any) => b[d.bookId]).filter((x: any) => x != null);
}
function extractPageInfo(conn: any, d: any): { hasMore: any; endCursor: any } {
  // search recursively for boolean-ish hasMore and cursor strings
  let hasMore: any = undefined, endCursor: any = undefined;
  const visit = (o: any) => {
    if (!o || typeof o !== 'object') return;
    for (const [k, v] of Object.entries(o)) {
      if (/(hasNext|hasMore|moreFollow)/i.test(k) && typeof v === 'boolean') hasMore = v;
      else if (/(endCursor|nextCursor)/i.test(k) && (typeof v === 'string' || v === null)) endCursor = v;
      else if (v && typeof v === 'object' && !Array.isArray(v)) visit(v);
    }
  };
  visit(conn);
  return { hasMore, endCursor };
}
function extractLastCursor(conn: any, d: any): any {
  // pull the cursor from the last edge/item of the connection's list field
  if (!conn) return null;
  const arr = conn[d.itemsField.name];
  if (!Array.isArray(arr) || arr.length === 0) return null;
  const last = arr[arr.length - 1];
  if (last && typeof last === 'object') {
    for (const [k, v] of Object.entries(last)) {
      if (/cursor/i.test(k) && (typeof v === 'string')) return v;
    }
  }
  return null;
}

// mutation input construction -------------------------------------------------
function buildAddInput(inputType: any, authorId: string, omitStatus: boolean, salt = 0): any {
  const obj: any = {};
  for (const f of inputType.inputFields || inputType.fields || []) {
    const u = unwrap(f.type);
    if (/title/i.test(f.name)) obj[f.name] = 'Bench Title ' + salt;
    else if (/year/i.test(f.name)) obj[f.name] = 1999 + salt;
    else if (/summary/i.test(f.name)) { /* optional, omit */ }
    else if (/status/i.test(f.name)) { if (!omitStatus) {/*skip*/} }
    else if (/author/i.test(f.name) || u.name === 'ID') obj[f.name] = authorId;
    else if (u.nonNull) {
      if (u.name === 'Int') obj[f.name] = 1;
      else if (u.name === 'String' || u.name === 'ID') obj[f.name] = authorId;
      else if (u.name === 'Boolean') obj[f.name] = false;
    }
  }
  return obj;
}

// Note: jest introspection returns args of input objects under `args`? No.
// We re-introspect input object fields via a dedicated query at call sites.

function buildPayloadBookSelection(payloadType: any, d: any): string {
  // payload may BE the book, or contain a book field
  if (payloadType.name === d.bookObj.name) {
    return `${d.bookId} title ${d.statusField}`;
  }
  const bookField = payloadType.fields.find((f: any) => unwrap(f.type).name === d.bookObj.name);
  if (bookField) {
    return `${bookField.name} { ${d.bookId} title ${d.statusField} }`;
  }
  // union? select inline on Book type
  return `... on ${d.bookObj.name} { ${d.bookId} title ${d.statusField} }`;
}
function buildFullPayloadSelection(payloadType: any, d: any): string {
  if (payloadType.kind === 'UNION') {
    // select id on book branch + typename
    return `__typename ... on ${d.bookObj.name} { ${d.bookId} }`;
  }
  const parts: string[] = ['__typename'];
  for (const f of payloadType.fields || []) {
    const u = unwrap(f.type);
    if (u.name === d.bookObj.name && !u.list) parts.push(`${f.name} { ${d.bookId} }`);
    else if (u.kind === 'SCALAR' || u.kind === 'ENUM') parts.push(f.name);
  }
  return parts.join(' ');
}
function digCreatedBook(payload: any, d: any): any {
  if (payload == null) return null;
  if (payload[d.bookId] !== undefined) return payload;
  for (const [k, v] of Object.entries(payload)) {
    if (v && typeof v === 'object' && (v as any)[d.bookId] !== undefined) return v;
  }
  return null;
}
function payloadSignalsFailure(payload: any, d: any): boolean {
  // some field distinguishes failure: a boolean false success, a non-null message/code,
  // a __typename that is not the success/book type, or simply a null book with a sibling signal.
  if (payload.__typename && !new RegExp(d.bookObj.name, 'i').test(payload.__typename) &&
      !/success/i.test(payload.__typename)) return true;
  for (const [k, v] of Object.entries(payload)) {
    if (/success|ok|created/i.test(k) && v === false) return true;
    if (/(message|reason|code|error|notfound|not_found)/i.test(k) && v != null && v !== '') return true;
  }
  // null book while errors empty also discriminates from the success payload shape
  const created = digCreatedBook(payload, d);
  return created == null;
}
function pickNotStarted(d: any, server: any): any { return null; }
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
        """L1: the catalog module file exists at the required path."""
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
        # an exported factory function (create*/make*/*Store/*Catalog)
        assert re.search(
            r"export\s+(const|function)\s+\w*(create|make|store|catalog|seed)\w*",
            src,
            re.IGNORECASE,
        ), "no store-factory export found"

    def test_module_has_no_other_example_imports(self):
        """L1: module is self-contained (does not import from sibling example files)."""
        src = self._read(self.MODULE_PATH)
        for m in re.finditer(r"""import[^;]*?from\s*['"]([^'"]+)['"]""", src):
            spec = m.group(1)
            if "examples/" in spec and "libraryCatalog" not in spec:
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

    def test_harness_schema_and_entities(self, harness_report):
        """L2: schema builds; book/author entities exist with non-null stable ids
        distinct from title/name; intentional nullability (summary optional)."""
        self._passed(harness_report, r"schema builds and exposes book/author")

    def test_harness_status_enum_three_values(self, harness_report):
        """L2: reading-status enum is introspectable with exactly three values."""
        self._passed(harness_report, r"reading-status enum is introspectable")

    def test_harness_single_fetch_hit(self, harness_report):
        """L2: single book fetch hit returns correct fields + nested author name."""
        self._passed(harness_report, r"single book fetch HIT")

    def test_harness_book_miss_null(self, harness_report):
        """L2: unknown book id resolves to null with no execution error."""
        self._passed(harness_report, r"single book fetch MISS")

    def test_harness_author_miss_null(self, harness_report):
        """L2: unknown author id resolves to null with no execution error."""
        self._passed(harness_report, r"single author fetch MISS")

    def test_harness_nested_resolution(self, harness_report):
        """L2: book->author object and author->books list resolve (round-trip)."""
        self._passed(harness_report, r"nested author->books and book->author")

    def test_harness_full_pagination_traversal(self, harness_report):
        """L2: forward pagination in pages of 2 visits each book once, last page no-more."""
        self._passed(harness_report, r"forward pagination in pages of 2")

    def test_harness_status_filter(self, harness_report):
        """L2: FINISHED filter returns only finished books (and is meaningful)."""
        self._passed(harness_report, r"status filter FINISHED")

    def test_harness_invalid_status_validation(self, harness_report):
        """L2: invalid status literal fails validation before resolvers (errors, no data)."""
        self._passed(harness_report, r"invalid reading-status string fails VALIDATION")

    def test_harness_mutation_single_input(self, harness_report):
        """L2: add-book mutation takes a single structured input-object argument."""
        self._passed(harness_report, r"single structured \(input object\) argument")

    def test_harness_default_status_creation(self, harness_report):
        """L2: add with existing author + no status -> NOT_STARTED, unique id, refetchable."""
        self._passed(harness_report, r"defaults to NOT_STARTED")

    def test_harness_created_id_uniqueness(self, harness_report):
        """L2: multiple created books get unique, non-colliding ids."""
        self._passed(harness_report, r"created book ids are unique")

    def test_harness_author_not_found_outcome(self, harness_report):
        """L2: missing-author add signals not-found via payload; top-level errors empty."""
        self._passed(harness_report, r"add book for MISSING author")
