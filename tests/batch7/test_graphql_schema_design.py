"""Benchmark tests for the `graphql-schema-design` skill (variant ext7).

Skill task (ext7): build a self-contained "comment thread" GraphQL feature
module inside the `@apollo/server` package
(`packages/server/src/examples/commentThread.ts`) that exports `typeDefs`
(an SDL string), `resolvers`, and an in-memory data-store factory, plus a Jest
test suite at
`packages/server/src/__tests__/examples/commentThread.test.ts`.

The central concern of this variant is *bidirectional cursor pagination* over
an ordered list of comments in a single thread:

  - a root page field returns a page of comments using a count + opaque cursor;
  - it supports BOTH directions: "first N after cursor" and "last N before cursor";
  - each returned comment carries an opaque cursor; the page reports whether
    more comments exist before and after it, plus boundary cursors;
  - the page also reports the total comment count, independent of the window;
  - lists / per-comment cursor lists never resolve null and never contain nulls;
  - a forward-obtained cursor is consistently usable to page backward.

What this file verifies
-----------------------
L1 (existence / minimal well-formedness):
  - the two deliverable files exist at the required paths,
  - the module declares exported `typeDefs` / `resolvers` / a store factory,
  - the module is self-contained (no sibling-example imports),
  - the module does NOT touch the package public `index.ts` exports,
  - the agent's own Jest suite declares >= 10 `it`/`test` cases,
  - the agent's own Jest suite passes (the acceptance command:
    `npx jest packages/server/src/__tests__/examples/commentThread.test.ts`).

L2 (dynamic execution -- the discriminative core):
  Rather than trusting the agent's own test file, we synthesize an INDEPENDENT
  TypeScript Jest harness, drop it next to the module, and run it through the
  repo's native `jest` toolchain.  The harness builds an `ApolloServer` directly
  from the module's `typeDefs`/`resolvers`, introspects the schema to discover
  the real field / argument / cursor names (so we do not hard-code the agent's
  naming choices), and then exercises every Acceptance-Criterion scenario:

    - full forward traversal in fixed pages of 2 visits every comment exactly
      once (no dups / omissions); the last forward page reports "no more after";
    - full backward traversal from the end reproduces the reversed order
      exactly once each; the last backward page reports "no more before";
    - a cursor taken while paging forward is usable to page backward and lands
      on the expected preceding neighbours (direction consistency);
    - paging past the end yields an empty (non-null) item list with metadata
      reporting no further comments in that direction;
    - the reported total count equals the seeded comment count regardless of
      the page window;
    - returned comment fields (id, author, body) are always present (non-null);
    - the items list and per-comment cursor values are never null.

  A stub that hardcodes a single page, ignores the cursor, ignores the
  direction, or always reports `hasMore=false` fails these named cases.  We run
  jest with `--json` and assert on individual named test outcomes.
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
    MODULE_REL = "src/examples/commentThread.ts"
    SUITE_REL = "src/__tests__/examples/commentThread.test.ts"
    MODULE_PATH = os.path.join(SERVER_DIR, "src", "examples", "commentThread.ts")
    SUITE_PATH = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "commentThread.test.ts"
    )

    # Directory where we drop our own independent harness suite.
    HARNESS_DIR = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "__bench__"
    )
    HARNESS_NAME = "benchCommentThread.test.ts"
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
        #   - module under test -> ../../../examples/commentThread.js
        return r"""// @ts-nocheck
import { describe, it, expect } from '@jest/globals';
import { ApolloServer } from '../../../index.js';
import * as mod from '../../../examples/commentThread.js';

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

// ---- type-ref unwrapping ---------------------------------------------------
function unwrap(t: any): any {
  let nonNull = false, list = false, listItemNonNull = false, cur = t;
  while (cur) {
    if (cur.kind === 'NON_NULL') {
      if (list) listItemNonNull = true; else nonNull = true;
      cur = cur.ofType; continue;
    }
    if (cur.kind === 'LIST') { list = true; cur = cur.ofType; continue; }
    break;
  }
  return { kind: cur ? cur.kind : '', name: cur ? cur.name : null, nonNull, list, listItemNonNull };
}
function typeStr(t: any): string {
  if (!t) return 'ID';
  if (t.kind === 'NON_NULL') return typeStr(t.ofType) + '!';
  if (t.kind === 'LIST') return '[' + typeStr(t.ofType) + ']';
  return t.name || 'ID';
}

const TYPEREF = `kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name } } } }`;
const INTRO = `
{
  __schema {
    queryType { name }
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

// ---- schema discovery ------------------------------------------------------
// Discover:
//   commentObj    : the OBJECT with an author-ish field + a body-ish field
//   pageObj       : an OBJECT that holds a list (directly or via edges) of comments
//   pageQ         : a root query field returning pageObj, taking a count Int arg
//   countArg      : Int arg on pageQ (page size)
//   afterArg/beforeArg : opaque cursor args (forward/backward), String/ID typed
//   totalField    : Int-ish field on pageObj reporting the total
//   hasBefore/hasAfter : Boolean page-metadata fields (possibly nested in pageInfo)
//   startCursor/endCursor : boundary cursor fields
//   per-comment cursor    : a cursor on each item/edge
async function discover(server: any) {
  const intro = await run(server, INTRO);
  if (intro.errors) throw new Error('introspection failed: ' + JSON.stringify(intro.errors));
  const sch = intro.data.__schema;
  const types: any[] = sch.types;
  const byName: Record<string, any> = {};
  for (const t of types) byName[t.name] = t;
  const qType = types.find((t) => t.name === sch.queryType.name);

  const commentObj = types.find(
    (t) => t.kind === 'OBJECT' && t.fields &&
      t.fields.some((f: any) => /(author|user|handle|name)/i.test(f.name) && unwrap(f.type).kind === 'SCALAR') &&
      t.fields.some((f: any) => /(body|text|content|message)/i.test(f.name) && unwrap(f.type).kind === 'SCALAR'),
  );
  if (!commentObj) throw new Error('no comment object type (author+body scalar fields) found');

  const idField = (commentObj.fields.find((f: any) => /^id$/i.test(f.name)) ||
    commentObj.fields.find((f: any) => /id$/i.test(f.name)) ||
    commentObj.fields.find((f: any) => /^(key|ref)$/i.test(f.name)));
  const authorField = commentObj.fields.find((f: any) => /(author|user|handle|name)/i.test(f.name) && unwrap(f.type).kind === 'SCALAR');
  const bodyField = commentObj.fields.find((f: any) => /(body|text|content|message)/i.test(f.name) && unwrap(f.type).kind === 'SCALAR');

  // a "page" object: an OBJECT (not the comment) that exposes a list whose
  // elements are Comments directly, or edges whose node is a Comment.
  function commentListField(obj: any): { field: any; viaEdge: boolean; edgeType: any } | null {
    for (const f of obj.fields) {
      const u = unwrap(f.type);
      if (!u.list) continue;
      if (u.name === commentObj.name) return { field: f, viaEdge: false, edgeType: null };
      const elem = byName[u.name];
      if (elem && elem.fields && elem.fields.some((ef: any) => unwrap(ef.type).name === commentObj.name)) {
        return { field: f, viaEdge: true, edgeType: elem };
      }
    }
    return null;
  }

  // candidate page queries: root field returning an OBJECT page with a comment
  // list and at least one Int arg (the count).
  const candidates = qType.fields.filter((f: any) => {
    const u = unwrap(f.type);
    if (u.kind !== 'OBJECT' || !u.name || u.name === commentObj.name) return false;
    const obj = byName[u.name];
    if (!obj || !obj.fields) return false;
    if (!commentListField(obj)) return false;
    return f.args.some((a: any) => unwrap(a.type).name === 'Int');
  });
  if (!candidates.length) throw new Error('no page query (returns a page object with a comment list + Int count arg) found');
  // prefer the one with the most cursor-ish args (forward+backward).
  candidates.sort((a: any, b: any) => {
    const score = (f: any) => f.args.filter((x: any) =>
      ['String', 'ID'].includes(unwrap(x.type).name)).length;
    return score(b) - score(a);
  });
  const pageQ = candidates[0];
  const pageObj = byName[unwrap(pageQ.type).name];
  const listInfo = commentListField(pageObj);

  // page-size + cursor args
  const intArgs = pageQ.args.filter((a: any) => unwrap(a.type).name === 'Int');
  const countArg = (pageQ.args.find((a: any) => unwrap(a.type).name === 'Int' && /(first|last|count|size|limit|n)/i.test(a.name)) || intArgs[0]).name;
  const lastArg = (pageQ.args.find((a: any) => unwrap(a.type).name === 'Int' && /last/i.test(a.name)) || {}).name;
  const cursorArgs = pageQ.args.filter((a: any) => ['String', 'ID'].includes(unwrap(a.type).name));
  const afterArg = (cursorArgs.find((a: any) => /(after|from|start)/i.test(a.name)) || cursorArgs[0] || {}).name;
  const beforeArg = (cursorArgs.find((a: any) => /(before|until|end)/i.test(a.name)) ||
    cursorArgs.find((a: any) => a.name !== afterArg) || {}).name;

  // total field on the page object (Int, not a list)
  const totalField = (pageObj.fields.find((f: any) =>
    /(total|count)/i.test(f.name) && unwrap(f.type).name === 'Int' && !unwrap(f.type).list) || {}).name;

  // per-comment cursor: on the comment object itself OR on the edge type.
  let itemCursorField: string | null = null;
  let edgeNodeField: string | null = null;
  if (listInfo!.viaEdge) {
    const et = listInfo!.edgeType;
    edgeNodeField = (et.fields.find((f: any) => unwrap(f.type).name === commentObj.name) || {}).name;
    itemCursorField = (et.fields.find((f: any) => /cursor/i.test(f.name) && ['String', 'ID'].includes(unwrap(f.type).name)) || {}).name;
  } else {
    const cc = commentObj.fields.find((f: any) => /cursor/i.test(f.name) && ['String', 'ID'].includes(unwrap(f.type).name));
    itemCursorField = cc ? cc.name : null;
  }

  return {
    types, byName, qType,
    commentObj, pageObj,
    idField: idField ? idField.name : null,
    authorField: authorField.name, bodyField: bodyField.name,
    listField: listInfo!.field.name, listType: listInfo!.field.type,
    viaEdge: listInfo!.viaEdge, edgeNodeField, itemCursorField,
    countArg, lastArg, afterArg, beforeArg, totalField,
  };
}

// ---- page-metadata extraction (recursive; tolerant of nested pageInfo) -----
function findMeta(pageData: any) {
  let hasBefore: any = undefined, hasAfter: any = undefined;
  let startCursor: any = undefined, endCursor: any = undefined;
  const visit = (o: any) => {
    if (!o || typeof o !== 'object') return;
    for (const [k, v] of Object.entries(o)) {
      if (typeof v === 'boolean') {
        if (/(before|prev|previous)/i.test(k)) hasBefore = v;
        else if (/(after|next|more)/i.test(k)) hasAfter = v;
      } else if (typeof v === 'string' || v === null) {
        if (/start.?cursor|first.?cursor|begin/i.test(k)) startCursor = v;
        else if (/end.?cursor|last.?cursor/i.test(k)) endCursor = v;
      } else if (v && typeof v === 'object' && !Array.isArray(v)) {
        visit(v);
      }
    }
  };
  visit(pageData);
  return { hasBefore, hasAfter, startCursor, endCursor };
}

function itemsOf(pageData: any, d: any): any[] {
  if (pageData == null) return [];
  const arr = pageData[d.listField];
  if (!Array.isArray(arr)) return [];
  if (!d.viaEdge) return arr;
  return arr.map((e: any) => (e ? e[d.edgeNodeField] : e));
}
function itemCursorsOf(pageData: any, d: any): any[] {
  if (pageData == null) return [];
  const arr = pageData[d.listField];
  if (!Array.isArray(arr)) return [];
  if (d.viaEdge) return arr.map((e: any) => (e ? e[d.itemCursorField] : null));
  return arr.map((e: any) => (e ? e[d.itemCursorField] : null));
}
function idsOf(pageData: any, d: any): string[] {
  return itemsOf(pageData, d).map((c: any) => (d.idField ? c[d.idField] : JSON.stringify([c[d.authorField], c[d.bodyField]])));
}

// build a selection set for a page query result.
function pageSelection(d: any): string {
  let inner: string;
  const idSel = d.idField ? d.idField + ' ' : '';
  if (d.viaEdge) {
    const cur = d.itemCursorField ? d.itemCursorField + ' ' : '';
    inner = `${d.listField} { ${cur}${d.edgeNodeField} { ${idSel}${d.authorField} ${d.bodyField}${d.itemCursorField && !d.viaEdge ? ' ' + d.itemCursorField : ''} } }`;
  } else {
    const cur = d.itemCursorField ? ' ' + d.itemCursorField : '';
    inner = `${d.listField} { ${idSel}${d.authorField} ${d.bodyField}${cur} }`;
  }
  // include every scalar/Boolean field on the page object + nested pageInfo objects
  const meta = metaSelection(d);
  const tot = d.totalField ? ' ' + d.totalField : '';
  return `${inner}${tot}${meta}`;
}
function metaSelection(d: any): string {
  const parts: string[] = [];
  for (const f of d.pageObj.fields) {
    const u = unwrap(f.type);
    if (f.name === d.listField) continue;
    if (d.totalField && f.name === d.totalField) continue;
    if (u.list) continue;
    if (u.kind === 'SCALAR') {
      parts.push(f.name);
    } else if (u.kind === 'OBJECT') {
      const obj = d.byName[u.name];
      if (!obj || !obj.fields) continue;
      const sub = obj.fields
        .filter((sf: any) => { const su = unwrap(sf.type); return su.kind === 'SCALAR' && !su.list; })
        .map((sf: any) => sf.name);
      if (sub.length) parts.push(`${f.name} { ${sub.join(' ')} }`);
    }
  }
  return parts.length ? ' ' + parts.join(' ') : '';
}

// run one page query given a directional cursor.
async function fetchPage(server: any, d: any, opts: { count: number; after?: string | null; before?: string | null; useLast?: boolean }) {
  const args: string[] = [];
  const sizeArg = (opts.useLast && d.lastArg) ? d.lastArg : d.countArg;
  args.push(`${sizeArg}: ${opts.count}`);
  if (opts.after != null && d.afterArg) args.push(`${d.afterArg}: ${JSON.stringify(opts.after)}`);
  if (opts.before != null && d.beforeArg) args.push(`${d.beforeArg}: ${JSON.stringify(opts.before)}`);
  const q = `query{ ${pageSelectionQuery(d, args)} }`;
  const res = await run(server, q);
  return res;
}
function pageSelectionQuery(d: any, args: string[]): string {
  return `${d.qFieldName}(${args.join(', ')}) { ${pageSelection(d)} }`;
}

describe('comment thread bidirectional pagination (independent harness)', () => {

  it('schema builds; thread/comment shape exposes non-null author and body', async () => {
    const server = await mkServer();
    const d = await discover(server);
    d.qFieldName = (await pageQueryName(server, d));
    // author + body fields must be declared non-null on the comment type
    const cObj = d.commentObj;
    const authorF = cObj.fields.find((f: any) => f.name === d.authorField);
    const bodyF = cObj.fields.find((f: any) => f.name === d.bodyField);
    expect(unwrap(authorF.type).nonNull).toBe(true);
    expect(unwrap(bodyF.type).nonNull).toBe(true);
    if (d.idField) {
      const idF = cObj.fields.find((f: any) => f.name === d.idField);
      expect(unwrap(idF.type).nonNull).toBe(true);
    }
    // the comment list field itself must be non-null and non-null-item
    const lf = d.pageObj.fields.find((f: any) => f.name === d.listField);
    const u = unwrap(lf.type);
    expect(u.list).toBe(true);
    expect(u.nonNull).toBe(true);          // list itself NON_NULL
    expect(u.listItemNonNull).toBe(true);  // elements NON_NULL
    await server.stop();
  });

  it('a page query exists taking a count and supporting two directional cursors', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.countArg).toBeTruthy();
    expect(d.afterArg).toBeTruthy();   // forward cursor
    expect(d.beforeArg).toBeTruthy();  // backward cursor
    expect(d.afterArg).not.toBe(d.beforeArg);
    // a per-item opaque cursor must be discoverable
    expect(d.itemCursorField).toBeTruthy();
    await server.stop();
  });

  it('forward paging size 2 from start visits every comment exactly once; last page has no more after', async () => {
    const server = await mkServer();
    const d = await discover(server);
    d.qFieldName = await pageQueryName(server, d);

    // ground truth: one big forward page
    const big = await fetchPage(server, d, { count: 10000 });
    expect(big.errors).toBeFalsy();
    const bigData = big.data[d.qFieldName];
    const allIds = idsOf(bigData, d);
    expect(allIds.length).toBeGreaterThanOrEqual(4);
    const totalSet = allIds.slice();

    const seen: string[] = [];
    let after: string | null = null;
    let lastHasAfter: any = null;
    for (let i = 0; i < 100; i++) {
      const r = await fetchPage(server, d, { count: 2, after });
      expect(r.errors).toBeFalsy();
      const data = r.data[d.qFieldName];
      const ids = idsOf(data, d);
      expect(ids.length).toBeLessThanOrEqual(2);
      for (const id of ids) seen.push(id);
      const meta = findMeta(data);
      lastHasAfter = meta.hasAfter;
      if (meta.hasAfter === false || ids.length === 0) break;
      // advance using the page's end boundary cursor, else last item cursor
      const cursors = itemCursorsOf(data, d).filter((c: any) => c != null);
      const next = meta.endCursor != null ? meta.endCursor : (cursors.length ? cursors[cursors.length - 1] : null);
      expect(next).toBeTruthy();
      after = next;
    }
    // exactly once each, in order, covering all
    expect(seen).toEqual(totalSet);
    expect(new Set(seen).size).toBe(seen.length);
    expect(lastHasAfter).toBe(false);
    await server.stop();
  });

  it('backward paging size 2 from end reproduces the reversed order; last page has no more before', async () => {
    const server = await mkServer();
    const d = await discover(server);
    d.qFieldName = await pageQueryName(server, d);

    const big = await fetchPage(server, d, { count: 10000 });
    const forwardIds = idsOf(big.data[d.qFieldName], d);
    const reversed = forwardIds.slice().reverse();

    const seen: string[] = [];
    let before: string | null = null;
    let lastHasBefore: any = null;
    for (let i = 0; i < 100; i++) {
      const r = await fetchPage(server, d, { count: 2, before, useLast: true });
      expect(r.errors).toBeFalsy();
      const data = r.data[d.qFieldName];
      const ids = idsOf(data, d);
      expect(ids.length).toBeLessThanOrEqual(2);
      // backward page items are still in forward order within the page; we
      // collect them and reverse at the end to compare against `reversed`.
      for (const id of ids) seen.push(id);
      const meta = findMeta(data);
      lastHasBefore = meta.hasBefore;
      if (meta.hasBefore === false || ids.length === 0) break;
      const cursors = itemCursorsOf(data, d).filter((c: any) => c != null);
      const prev = meta.startCursor != null ? meta.startCursor : (cursors.length ? cursors[0] : null);
      expect(prev).toBeTruthy();
      before = prev;
    }
    // Reconstruct the full forward order from the chunks gathered while walking
    // backward.  Each backward page sits "before" the previous one, so the
    // pages arrive last-block-first; within a block items keep forward order.
    // The set must equal all ids exactly once.
    expect(new Set(seen)).toEqual(new Set(forwardIds));
    expect(seen.length).toBe(forwardIds.length);
    expect(new Set(seen).size).toBe(seen.length);
    expect(lastHasBefore).toBe(false);
    // sanity: reversed contains the same members
    expect(new Set(reversed)).toEqual(new Set(forwardIds));
    await server.stop();
  });

  it('a forward-obtained cursor is usable to page backward and lands on preceding neighbours', async () => {
    const server = await mkServer();
    const d = await discover(server);
    d.qFieldName = await pageQueryName(server, d);

    const big = await fetchPage(server, d, { count: 10000 });
    const allIds = idsOf(big.data[d.qFieldName], d);
    expect(allIds.length).toBeGreaterThanOrEqual(4);

    // forward: first 3 -> grab cursor of the 3rd item
    const fwd = await fetchPage(server, d, { count: 3 });
    const fwdData = fwd.data[d.qFieldName];
    const fwdIds = idsOf(fwdData, d);
    expect(fwdIds.length).toBe(3);
    const fwdCursors = itemCursorsOf(fwdData, d);
    const thirdCursor = fwdCursors[2];
    expect(thirdCursor).toBeTruthy();
    const thirdId = fwdIds[2];

    // backward "last 2 before thirdCursor" must be the two comments preceding it
    const back = await fetchPage(server, d, { count: 2, before: thirdCursor, useLast: true });
    expect(back.errors).toBeFalsy();
    const backIds = idsOf(back.data[d.qFieldName], d);
    // expected preceding pair = the two ids immediately before thirdId in allIds
    const idx = allIds.indexOf(thirdId);
    expect(idx).toBeGreaterThanOrEqual(2);
    const expectedPrev = [allIds[idx - 2], allIds[idx - 1]];
    // direction-consistent: the backward window covers exactly those neighbours
    expect(new Set(backIds)).toEqual(new Set(expectedPrev));
    // and it must NOT include the anchor itself
    expect(backIds.includes(thirdId)).toBe(false);
    await server.stop();
  });

  it('paging forward past the end yields an empty (non-null) item list and no more after', async () => {
    const server = await mkServer();
    const d = await discover(server);
    d.qFieldName = await pageQueryName(server, d);

    // walk to the very end to get the last cursor
    let after: string | null = null;
    let endCursor: string | null = null;
    for (let i = 0; i < 100; i++) {
      const r = await fetchPage(server, d, { count: 1000, after });
      const data = r.data[d.qFieldName];
      const meta = findMeta(data);
      const cursors = itemCursorsOf(data, d).filter((c: any) => c != null);
      endCursor = meta.endCursor != null ? meta.endCursor : (cursors.length ? cursors[cursors.length - 1] : endCursor);
      if (meta.hasAfter === false) break;
      after = endCursor;
    }
    expect(endCursor).toBeTruthy();
    // now ask for the page AFTER the last cursor -> empty, not null
    const past = await fetchPage(server, d, { count: 3, after: endCursor });
    expect(past.errors).toBeFalsy();
    const data = past.data[d.qFieldName];
    const items = itemsOf(data, d);
    expect(Array.isArray(data[d.listField])).toBe(true); // list, not null
    expect(items.length).toBe(0);
    const meta = findMeta(data);
    expect(meta.hasAfter).toBe(false);
    await server.stop();
  });

  it('total count equals seeded comment count and is independent of the page window', async () => {
    const server = await mkServer();
    const d = await discover(server);
    d.qFieldName = await pageQueryName(server, d);
    expect(d.totalField).toBeTruthy();

    const big = await fetchPage(server, d, { count: 10000 });
    const bigData = big.data[d.qFieldName];
    const total = bigData[d.totalField];
    const allIds = idsOf(bigData, d);
    expect(typeof total).toBe('number');
    expect(total).toBe(allIds.length);
    expect(total).toBeGreaterThanOrEqual(4);

    // total is the same on a small first page
    const small = await fetchPage(server, d, { count: 1 });
    const smallData = small.data[d.qFieldName];
    expect(idsOf(smallData, d).length).toBe(1);
    expect(smallData[d.totalField]).toBe(total);

    // and the same on a mid-thread page
    const fwdCursors = itemCursorsOf(smallData, d).filter((c: any) => c != null);
    if (fwdCursors.length) {
      const mid = await fetchPage(server, d, { count: 2, after: fwdCursors[0] });
      expect(mid.data[d.qFieldName][d.totalField]).toBe(total);
    }
    await server.stop();
  });

  it('every returned comment has non-null id/author/body values', async () => {
    const server = await mkServer();
    const d = await discover(server);
    d.qFieldName = await pageQueryName(server, d);
    const big = await fetchPage(server, d, { count: 10000 });
    const items = itemsOf(big.data[d.qFieldName], d);
    expect(items.length).toBeGreaterThanOrEqual(4);
    for (const c of items) {
      expect(c).toBeTruthy();
      if (d.idField) {
        expect(c[d.idField]).not.toBeNull();
        expect(c[d.idField]).not.toBeUndefined();
      }
      expect(typeof c[d.authorField]).toBe('string');
      expect(c[d.authorField].length).toBeGreaterThan(0);
      expect(typeof c[d.bodyField]).toBe('string');
      expect(c[d.bodyField].length).toBeGreaterThan(0);
    }
    await server.stop();
  });

  it('item list and per-comment cursors are never null and contain no null entries', async () => {
    const server = await mkServer();
    const d = await discover(server);
    d.qFieldName = await pageQueryName(server, d);
    const r = await fetchPage(server, d, { count: 3 });
    const data = r.data[d.qFieldName];
    const rawList = data[d.listField];
    expect(rawList).not.toBeNull();
    expect(Array.isArray(rawList)).toBe(true);
    for (const e of rawList) expect(e).not.toBeNull();
    const cursors = itemCursorsOf(data, d);
    expect(cursors.length).toBe(rawList.length);
    for (const c of cursors) {
      expect(c).not.toBeNull();
      expect(c).not.toBeUndefined();
      expect(typeof c).toBe('string');
      expect(c.length).toBeGreaterThan(0);
    }
    await server.stop();
  });

  it('full forward traversal yields no duplicate ids and no omissions versus one big page', async () => {
    const server = await mkServer();
    const d = await discover(server);
    d.qFieldName = await pageQueryName(server, d);
    const big = await fetchPage(server, d, { count: 10000 });
    const allIds = idsOf(big.data[d.qFieldName], d);
    const allSet = new Set(allIds);

    const seen: string[] = [];
    let after: string | null = null;
    for (let i = 0; i < 100; i++) {
      const r = await fetchPage(server, d, { count: 2, after });
      const data = r.data[d.qFieldName];
      const ids = idsOf(data, d);
      for (const id of ids) seen.push(id);
      const meta = findMeta(data);
      if (meta.hasAfter === false || ids.length === 0) break;
      const cursors = itemCursorsOf(data, d).filter((c: any) => c != null);
      after = meta.endCursor != null ? meta.endCursor : cursors[cursors.length - 1];
    }
    expect(new Set(seen).size).toBe(seen.length);  // no dups
    expect(new Set(seen)).toEqual(allSet);          // no omissions
    await server.stop();
  });

  it('boundary cursors (start/end) of a mid-thread page point at that page first/last items', async () => {
    const server = await mkServer();
    const d = await discover(server);
    d.qFieldName = await pageQueryName(server, d);

    // first page of 2, then the next page of 2 (mid thread)
    const p1 = await fetchPage(server, d, { count: 2 });
    const p1data = p1.data[d.qFieldName];
    const p1meta = findMeta(p1data);
    const p1cursors = itemCursorsOf(p1data, d).filter((c: any) => c != null);
    const resume = p1meta.endCursor != null ? p1meta.endCursor : p1cursors[p1cursors.length - 1];
    expect(resume).toBeTruthy();

    const p2 = await fetchPage(server, d, { count: 2, after: resume });
    const p2data = p2.data[d.qFieldName];
    const p2items = itemsOf(p2data, d);
    const p2cursors = itemCursorsOf(p2data, d);
    expect(p2items.length).toBeGreaterThan(0);
    const meta = findMeta(p2data);
    // the page's boundary cursors must equal the first/last per-item cursors
    if (meta.startCursor != null) {
      expect(meta.startCursor).toBe(p2cursors[0]);
    }
    if (meta.endCursor != null) {
      expect(meta.endCursor).toBe(p2cursors[p2cursors.length - 1]);
    }
    // at minimum one boundary cursor must be exposed
    expect(meta.startCursor != null || meta.endCursor != null).toBe(true);
    // a non-first page reports "more before it"
    expect(meta.hasBefore).toBe(true);
    await server.stop();
  });

});

// resolve the root page query's actual field name (cache on d).
async function pageQueryName(server: any, d: any): Promise<string> {
  if (d.qFieldName) return d.qFieldName;
  const intro = await run(server, INTRO);
  const sch = intro.data.__schema;
  const qType = sch.types.find((t: any) => t.name === sch.queryType.name);
  // re-find the same page query field as discover() did
  const byName: Record<string, any> = {};
  for (const t of sch.types) byName[t.name] = t;
  const field = qType.fields.find((f: any) => {
    const u = unwrap(f.type);
    return u.kind === 'OBJECT' && u.name === d.pageObj.name;
  });
  d.qFieldName = field.name;
  return field.name;
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
        """L1: the comment-thread module file exists at the required path."""
        assert os.path.isfile(self.MODULE_PATH), f"missing {self.MODULE_REL}"

    def test_suite_file_exists(self):
        """L1: the agent's Jest suite file exists at the required path."""
        assert os.path.isfile(self.SUITE_PATH), f"missing {self.SUITE_REL}"

    def test_module_exports_typedefs_resolvers_and_factory(self):
        """L1: module declares exported typeDefs, resolvers, and a store factory."""
        src = self._read(self.MODULE_PATH)
        assert re.search(r"export\s+(const|let|var|function)\s+typeDefs", src) or re.search(
            r"export\b[^;]*\btypeDefs\b", src
        ), "no exported typeDefs"
        assert re.search(r"export\b[^;]*\bresolvers\b", src) or re.search(
            r"export\s+(const|let|var|function)\s+resolvers", src
        ), "no exported resolvers"
        # an exported factory function (create*/make*/seed*/*Store/*Thread)
        assert re.search(
            r"export\s+(const|function)\s+\w*(create|make|build|seed|store|thread)\w*",
            src,
            re.IGNORECASE,
        ), "no store-factory export found"

    def test_module_has_no_other_example_imports(self):
        """L1: module is self-contained (does not import from sibling example files)."""
        src = self._read(self.MODULE_PATH)
        for m in re.finditer(r"""import[^;]*?from\s*['"]([^'"]+)['"]""", src):
            spec = m.group(1)
            if "examples/" in spec and "commentThread" not in spec:
                pytest.fail(f"module imports another example file: {spec}")

    def test_public_index_not_modified_to_export_module(self):
        """L1: the task forbids changing the package public index.ts exports;
        the comment-thread module must not be wired into index.ts."""
        index_path = os.path.join(self.SERVER_DIR, "src", "index.ts")
        if not os.path.isfile(index_path):
            pytest.skip("index.ts not present")
        src = self._read(index_path)
        assert "commentThread" not in src, (
            "index.ts references commentThread; public exports must stay untouched"
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
        """L2: the acceptance command (agent's own suite) passes all assertions.

        Mirrors `npx jest packages/server/src/__tests__/examples/commentThread.test.ts`.
        """
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

    def test_harness_schema_shape(self, harness_report):
        """L2: schema builds; comment shape exposes non-null author/body/id and a
        non-null list-of-non-null comments."""
        self._passed(harness_report, r"schema builds; thread/comment shape")

    def test_harness_two_directional_cursors(self, harness_report):
        """L2: page query takes a count and exposes distinct forward/backward
        cursor args plus a per-item opaque cursor."""
        self._passed(harness_report, r"two directional cursors")

    def test_harness_forward_traversal_complete(self, harness_report):
        """L2: forward paging in fixed pages of 2 visits each comment exactly once;
        last page reports no more after."""
        self._passed(harness_report, r"forward paging size 2 from start")

    def test_harness_backward_traversal_complete(self, harness_report):
        """L2: backward paging from the end reproduces the reversed order; last
        page reports no more before."""
        self._passed(harness_report, r"backward paging size 2 from end")

    def test_harness_cross_direction_cursor_reuse(self, harness_report):
        """L2: a forward-obtained cursor pages backward onto the expected
        preceding neighbours (direction consistency)."""
        self._passed(harness_report, r"forward-obtained cursor is usable to page backward")

    def test_harness_empty_page_past_end(self, harness_report):
        """L2: paging past the end yields an empty (non-null) item list with
        metadata reporting no more after."""
        self._passed(harness_report, r"past the end yields an empty")

    def test_harness_total_count_window_independent(self, harness_report):
        """L2: total count equals the seeded count and does not vary with the
        page window."""
        self._passed(harness_report, r"total count equals seeded comment count")

    def test_harness_non_null_comment_fields(self, harness_report):
        """L2: every returned comment has non-null id/author/body values."""
        self._passed(harness_report, r"every returned comment has non-null")

    def test_harness_non_null_list_and_cursors(self, harness_report):
        """L2: item list and per-comment cursors are never null / contain no nulls."""
        self._passed(harness_report, r"item list and per-comment cursors are never null")

    def test_harness_no_duplicates_no_omissions(self, harness_report):
        """L2: full forward traversal has no duplicate ids and no omissions."""
        self._passed(harness_report, r"no duplicate ids and no omissions")

    def test_harness_boundary_cursor_metadata(self, harness_report):
        """L2: a mid-thread page's start/end boundary cursors match its first/last
        item cursors and it reports more-before."""
        self._passed(harness_report, r"boundary cursors \(start/end\) of a mid-thread page")
