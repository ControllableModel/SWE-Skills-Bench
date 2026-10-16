"""Benchmark tests for the `graphql-schema-design` skill (variant: ext2).

Skill task: build a self-contained "content graph" GraphQL feature module inside
the `@apollo/server` package at `packages/server/src/examples/contentGraph.ts`.
The module exports `typeDefs` (SDL string), `resolvers`, and an in-memory
data-store factory for a small content domain of **articles, videos, and tags**.
Its central concern is a single, uniform refetch entry point: all three kinds
share one abstract contract (a GraphQL *interface*) carrying a stable, globally
unique identifier, and the root query exposes ONE field that accepts a single
identifier and returns the matching object regardless of kind (Relay "node"
style). The agent also writes a Jest suite at
`packages/server/src/__tests__/examples/contentGraph.test.ts`.

What this file verifies
-----------------------
L1 (existence / minimal well-formedness):
  - both deliverable files exist,
  - the module exports `typeDefs` / `resolvers` / a store factory,
  - the module is self-contained (imports no sibling example file, does not touch
    the package's public index exports),
  - the agent's own Jest suite declares >= 10 `it`/`test` cases.

L2 (dynamic execution -- the discriminative core):
  Rather than trusting the agent's own tests, we synthesize an INDEPENDENT
  TypeScript Jest harness, drop it next to the module, and run it through the
  repo's native `jest` toolchain.  The harness builds an `ApolloServer` directly
  from the module's `typeDefs`/`resolvers`, introspects the schema to discover
  the real interface / object / field names (so we never hard-code the agent's
  naming choices), and exercises every Acceptance-Criterion scenario:
    * an INTERFACE type carrying a non-null shared id is implemented by >= 3
      object kinds (article / video / tag),
    * a single root field returns that interface and takes one id-ish argument,
    * refetch HIT for an article -> __typename is the article kind + title,
    * refetch HIT for a video -> __typename is the video kind,
    * refetch HIT for a tag -> __typename is the tag kind + label,
    * refetch MISS -> null, no execution error,
    * the shared id is requestable through the single entry point WITHOUT a
      narrowing inline fragment,
    * type-specific list queries for articles and videos never null / no null
      entries, and every seeded item appears,
    * an article's tags resolve to nested tag OBJECTS (label + id), not strings,
    * ids are globally unique across all three kinds (no collision),
    * a tag shared by two parents refetches to identical content from the node
      entry point.

  We run jest with `--json` and assert on individual named test outcomes, so a
  stub / partial / "looks related" solution fails.  A naive implementation that
  hard-codes a single kind, returns bare tag id strings, lets ids collide across
  kinds, errors on an unknown id, or skips the interface contract cannot pass.

The native acceptance command this drives:
    npx jest packages/server/src/__tests__/examples/contentGraph.test.ts --verbose
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
    MODULE_REL = "src/examples/contentGraph.ts"
    SUITE_REL = "src/__tests__/examples/contentGraph.test.ts"
    MODULE_PATH = os.path.join(SERVER_DIR, "src", "examples", "contentGraph.ts")
    SUITE_PATH = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "contentGraph.test.ts"
    )

    # Directory where we drop our own independent harness suite.
    HARNESS_DIR = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "__bench__"
    )
    HARNESS_NAME = "benchContentGraph.test.ts"
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
        #   - module under test -> ../../../examples/contentGraph.js
        return r"""// @ts-nocheck
import { describe, it, expect } from '@jest/globals';
import { ApolloServer } from '../../../index.js';
import * as mod from '../../../examples/contentGraph.js';

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

// ---- introspection helpers -------------------------------------------------
const TYPEREF = `kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name } } } }`;
const INTRO = `
{
  __schema {
    queryType { name }
    types {
      kind name
      interfaces { name }
      possibleTypes { name }
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
function sdlType(t: any): string {
  if (!t) return 'ID';
  if (t.kind === 'NON_NULL') return sdlType(t.ofType) + '!';
  if (t.kind === 'LIST') return '[' + sdlType(t.ofType) + ']';
  return t.name || 'ID';
}

// Discover the central content-graph shape from a live, introspected schema.
async function discover(server: any) {
  const intro = await run(server, INTRO);
  if (intro.errors) throw new Error('introspection failed: ' + JSON.stringify(intro.errors));
  const sch = intro.data.__schema;
  const types: any[] = sch.types;
  const byName: Record<string, any> = {};
  for (const t of types) byName[t.name] = t;
  const qType = types.find((t) => t.name === sch.queryType.name);

  // The shared abstract contract is a GraphQL INTERFACE that carries an id-ish,
  // non-null scalar field and is implemented by at least three object kinds.
  const interfaces = types.filter((t) => t.kind === 'INTERFACE');
  let iface: any = null;
  for (const itf of interfaces) {
    const idf = (itf.fields || []).find((f: any) => /^id$/i.test(f.name) || /id$/i.test(f.name));
    if (!idf) continue;
    const impls = (itf.possibleTypes || []).map((p: any) => p.name);
    if (impls.length >= 3) { iface = itf; break; }
    if (!iface && impls.length >= 2) iface = itf; // fall back, keep scanning
  }
  if (!iface) throw new Error('no shared interface with >=2 implementors found');

  const idField = (iface.fields.find((f: any) => /^id$/i.test(f.name)) ||
    iface.fields.find((f: any) => /id$/i.test(f.name))).name;

  const implNames: string[] = (iface.possibleTypes || []).map((p: any) => p.name);
  const impls = implNames.map((n) => byName[n]).filter(Boolean);

  // classify the three kinds by their distinctive fields
  const articleT = impls.find((t: any) =>
    t.fields.some((f: any) => /title/i.test(f.name)) &&
    t.fields.some((f: any) => { const u = unwrap(f.type); return u.list; }));
  const videoT = impls.find((t: any) =>
    t !== articleT && t.fields.some((f: any) => /title/i.test(f.name)));
  const tagT = impls.find((t: any) =>
    t !== articleT && t !== videoT &&
    t.fields.some((f: any) => /label/i.test(f.name)));

  // single refetch (node) entry point: a root field returning the INTERFACE
  // (nullable), taking exactly one id-ish argument.
  const nodeQ = qType.fields.find((f: any) => {
    const u = unwrap(f.type);
    return u.kind === 'INTERFACE' && u.name === iface.name && !u.list && f.args.length >= 1;
  });

  // type-specific list queries returning [Article] / [Video]
  const listFor = (objT: any) => objT && qType.fields.find((f: any) => {
    const u = unwrap(f.type);
    return u.list && u.name === objT.name;
  });
  const articlesQ = listFor(articleT);
  const videosQ = listFor(videoT);

  // tags field on an article/video that is a LIST of the tag object type
  const tagsFieldOn = (objT: any) => objT && objT.fields.find((f: any) => {
    const u = unwrap(f.type);
    return u.list && tagT && u.name === tagT.name;
  });

  // a label field on the tag type
  const labelField = tagT && (tagT.fields.find((f: any) => /label/i.test(f.name)) || {}).name;
  const titleFieldOn = (objT: any) => objT && (objT.fields.find((f: any) => /title/i.test(f.name)) || {}).name;

  return {
    qType, types, byName,
    iface, idField, impls, implNames,
    articleT, videoT, tagT,
    nodeQ, articlesQ, videosQ,
    tagsOnArticle: tagsFieldOn(articleT),
    tagsOnVideo: tagsFieldOn(videoT),
    labelField,
    articleTitle: titleFieldOn(articleT),
    videoTitle: titleFieldOn(videoT),
  };
}

function nodeArg(d: any) { return d.nodeQ.args[0]; }

async function fetchNode(server: any, d: any, id: string, sel: string) {
  const a = nodeArg(d);
  const q = `query($id: ${sdlType(a.type)}){ ${d.nodeQ.name}(${a.name}: $id){ ${sel} } }`;
  return run(server, q, { id });
}

describe('content graph (independent harness)', () => {

  it('shared interface carries a non-null id and is implemented by article, video, and tag kinds', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.iface).toBeTruthy();
    // id field on the interface is non-null
    const idf = d.iface.fields.find((f: any) => f.name === d.idField);
    expect(unwrap(idf.type).nonNull).toBe(true);
    // at least three concrete implementors
    expect(d.implNames.length).toBeGreaterThanOrEqual(3);
    expect(d.articleT).toBeTruthy();
    expect(d.videoT).toBeTruthy();
    expect(d.tagT).toBeTruthy();
    // each implementor lists the interface in its `interfaces`
    for (const t of [d.articleT, d.videoT, d.tagT]) {
      const names = (t.interfaces || []).map((i: any) => i.name);
      expect(names).toContain(d.iface.name);
      // each implementor's id is non-null too
      const tid = t.fields.find((f: any) => f.name === d.idField);
      expect(tid).toBeTruthy();
      expect(unwrap(tid.type).nonNull).toBe(true);
    }
    await server.stop();
  });

  it('single refetch entry point returns the shared interface and takes one id argument', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.nodeQ).toBeTruthy();
    const u = unwrap(d.nodeQ.type);
    expect(u.kind).toBe('INTERFACE');
    expect(u.name).toBe(d.iface.name);
    // nullable (a miss must resolve to null, not error)
    expect(u.nonNull).toBe(false);
    expect(d.nodeQ.args.length).toBe(1);
    await server.stop();
  });

  it('refetch HIT for an article: __typename is the article kind and title is present', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const arts = await run(server, `query{ ${d.articlesQ.name}{ ${d.idField} } }`);
    expect(arts.errors).toBeFalsy();
    const list = arts.data[d.articlesQ.name];
    expect(Array.isArray(list)).toBe(true);
    expect(list.length).toBeGreaterThan(0);
    const id = list[0][d.idField];
    const res = await fetchNode(server, d, id,
      `__typename ${d.idField} ... on ${d.articleT.name} { ${d.articleTitle} }`);
    expect(res.errors).toBeFalsy();
    const node = res.data[d.nodeQ.name];
    expect(node).toBeTruthy();
    expect(node.__typename).toBe(d.articleT.name);
    expect(node[d.idField]).toBe(id);
    expect(typeof node[d.articleTitle]).toBe('string');
    expect(node[d.articleTitle].length).toBeGreaterThan(0);
    await server.stop();
  });

  it('refetch HIT for a video: __typename is the video kind', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const vids = await run(server, `query{ ${d.videosQ.name}{ ${d.idField} } }`);
    expect(vids.errors).toBeFalsy();
    const list = vids.data[d.videosQ.name];
    expect(Array.isArray(list)).toBe(true);
    expect(list.length).toBeGreaterThan(0);
    const id = list[0][d.idField];
    const res = await fetchNode(server, d, id, `__typename ${d.idField}`);
    expect(res.errors).toBeFalsy();
    const node = res.data[d.nodeQ.name];
    expect(node).toBeTruthy();
    expect(node.__typename).toBe(d.videoT.name);
    expect(node[d.idField]).toBe(id);
    await server.stop();
  });

  it('refetch HIT for a tag: __typename is the tag kind and label is present', async () => {
    const server = await mkServer();
    const d = await discover(server);
    // discover a real tag id by walking an article's nested tags
    const arts = await run(server, `query{ ${d.articlesQ.name}{ ${d.tagsOnArticle.name} { ${d.idField} ${d.labelField} } } }`);
    expect(arts.errors).toBeFalsy();
    let tagId: any = null;
    for (const a of arts.data[d.articlesQ.name]) {
      const tags = a[d.tagsOnArticle.name];
      if (Array.isArray(tags) && tags.length) { tagId = tags[0][d.idField]; break; }
    }
    expect(tagId).toBeTruthy();
    const res = await fetchNode(server, d, tagId,
      `__typename ${d.idField} ... on ${d.tagT.name} { ${d.labelField} }`);
    expect(res.errors).toBeFalsy();
    const node = res.data[d.nodeQ.name];
    expect(node).toBeTruthy();
    expect(node.__typename).toBe(d.tagT.name);
    expect(typeof node[d.labelField]).toBe('string');
    expect(node[d.labelField].length).toBeGreaterThan(0);
    await server.stop();
  });

  it('refetch MISS resolves to null with no execution error', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const res = await fetchNode(server, d, 'definitely-not-a-real-id-zzz', `__typename ${d.idField}`);
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    expect(res.data[d.nodeQ.name]).toBeNull();
    await server.stop();
  });

  it('shared id is requestable through the entry point WITHOUT a narrowing fragment', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const vids = await run(server, `query{ ${d.videosQ.name}{ ${d.idField} } }`);
    const id = vids.data[d.videosQ.name][0][d.idField];
    // select ONLY the interface id -- no inline fragment at all
    const res = await fetchNode(server, d, id, `${d.idField}`);
    expect(res.errors).toBeFalsy();
    const node = res.data[d.nodeQ.name];
    expect(node).toBeTruthy();
    expect(node[d.idField]).toBe(id);
    await server.stop();
  });

  it('article and video list queries never null and contain no null entries; every seeded item refetchable', async () => {
    const server = await mkServer();
    const d = await discover(server);
    for (const [q, kind] of [[d.articlesQ, d.articleT], [d.videosQ, d.videoT]] as any[]) {
      const r = await run(server, `query{ ${q.name}{ ${d.idField} } }`);
      expect(r.errors).toBeFalsy();
      const arr = r.data[q.name];
      expect(Array.isArray(arr)).toBe(true);
      expect(arr.length).toBeGreaterThan(0);
      for (const item of arr) {
        expect(item).not.toBeNull();
        expect(typeof item[d.idField]).toBe('string');
        // each listed item is refetchable via the single entry point as its kind
        const got = await fetchNode(server, d, item[d.idField], `__typename ${d.idField}`);
        expect(got.errors).toBeFalsy();
        expect(got.data[d.nodeQ.name]).toBeTruthy();
        expect(got.data[d.nodeQ.name].__typename).toBe(kind.name);
        expect(got.data[d.nodeQ.name][d.idField]).toBe(item[d.idField]);
      }
    }
    await server.stop();
  });

  it("an article's tags resolve to nested tag OBJECTS (label + id), not bare id strings", async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.tagsOnArticle).toBeTruthy();
    // the schema type of the tags field must be a LIST of the tag object type
    const u = unwrap(d.tagsOnArticle.type);
    expect(u.list).toBe(true);
    expect(u.name).toBe(d.tagT.name);
    const r = await run(server,
      `query{ ${d.articlesQ.name}{ ${d.idField} ${d.tagsOnArticle.name} { ${d.idField} ${d.labelField} } } }`);
    expect(r.errors).toBeFalsy();
    let sawTags = false;
    for (const a of r.data[d.articlesQ.name]) {
      const tags = a[d.tagsOnArticle.name];
      expect(Array.isArray(tags)).toBe(true); // never null
      for (const t of tags) {
        expect(t).not.toBeNull();           // no null entries
        expect(typeof t).toBe('object');     // objects, not strings
        expect(typeof t[d.idField]).toBe('string');
        expect(typeof t[d.labelField]).toBe('string');
        expect(t[d.labelField].length).toBeGreaterThan(0);
        sawTags = true;
      }
    }
    expect(sawTags).toBe(true);
    await server.stop();
  });

  it('identifiers are globally unique across articles, videos, and tags (no cross-kind collision)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const arts = await run(server,
      `query{ ${d.articlesQ.name}{ ${d.idField} ${d.tagsOnArticle.name} { ${d.idField} } } }`);
    const vids = await run(server,
      `query{ ${d.videosQ.name}{ ${d.idField} ${d.tagsOnVideo.name} { ${d.idField} } } }`);
    expect(arts.errors).toBeFalsy();
    expect(vids.errors).toBeFalsy();
    const ids: string[] = [];
    const tagIds = new Set<string>();
    for (const a of arts.data[d.articlesQ.name]) {
      ids.push(a[d.idField]);
      for (const t of a[d.tagsOnArticle.name] || []) tagIds.add(t[d.idField]);
    }
    for (const v of vids.data[d.videosQ.name]) {
      ids.push(v[d.idField]);
      for (const t of (v[d.tagsOnVideo.name] || [])) tagIds.add(t[d.idField]);
    }
    for (const tid of tagIds) ids.push(tid);
    // total ids span all three kinds and are all distinct
    expect(ids.length).toBeGreaterThanOrEqual(3);
    expect(new Set(ids).size).toBe(ids.length);
    await server.stop();
  });

  it('a tag shared by two parents refetches identically through the single entry point', async () => {
    const server = await mkServer();
    const d = await discover(server);
    // gather (parentId -> set of tagIds) across articles and videos
    const arts = await run(server,
      `query{ ${d.articlesQ.name}{ ${d.idField} ${d.tagsOnArticle.name} { ${d.idField} ${d.labelField} } } }`);
    const vids = await run(server,
      `query{ ${d.videosQ.name}{ ${d.idField} ${d.tagsOnVideo.name} { ${d.idField} ${d.labelField} } } }`);
    const parents: any[] = [
      ...arts.data[d.articlesQ.name].map((a: any) => ({ id: a[d.idField], tags: a[d.tagsOnArticle.name] || [] })),
      ...vids.data[d.videosQ.name].map((v: any) => ({ id: v[d.idField], tags: v[d.tagsOnVideo.name] || [] })),
    ];
    // find a tag id that appears under two distinct parents
    const tagToParents: Record<string, Set<string>> = {};
    const tagLabel: Record<string, string> = {};
    for (const p of parents) {
      for (const t of p.tags) {
        (tagToParents[t[d.idField]] = tagToParents[t[d.idField]] || new Set()).add(p.id);
        tagLabel[t[d.idField]] = t[d.labelField];
      }
    }
    const sharedTagId = Object.keys(tagToParents).find((k) => tagToParents[k].size >= 2);
    expect(sharedTagId).toBeTruthy();

    // refetch that tag through the single node entry point -> identical content
    const res = await fetchNode(server, d, sharedTagId!,
      `__typename ${d.idField} ... on ${d.tagT.name} { ${d.labelField} }`);
    expect(res.errors).toBeFalsy();
    const node = res.data[d.nodeQ.name];
    expect(node.__typename).toBe(d.tagT.name);
    expect(node[d.idField]).toBe(sharedTagId);
    expect(node[d.labelField]).toBe(tagLabel[sharedTagId!]);

    // and the same tag content observed from BOTH parents is identical
    const observed = parents
      .filter((p) => tagToParents[sharedTagId!].has(p.id))
      .map((p) => p.tags.find((t: any) => t[d.idField] === sharedTagId));
    expect(observed.length).toBeGreaterThanOrEqual(2);
    for (const o of observed) expect(o[d.labelField]).toBe(node[d.labelField]);
    await server.stop();
  });

  it('store factory is deterministic: two fresh servers expose the same id set', async () => {
    const s1 = await mkServer();
    const d1 = await discover(s1);
    const a1 = await run(s1, `query{ ${d1.articlesQ.name}{ ${d1.idField} } }`);
    const ids1 = a1.data[d1.articlesQ.name].map((x: any) => x[d1.idField]).sort();
    await s1.stop();

    const s2 = await mkServer();
    const d2 = await discover(s2);
    const a2 = await run(s2, `query{ ${d2.articlesQ.name}{ ${d2.idField} } }`);
    const ids2 = a2.data[d2.articlesQ.name].map((x: any) => x[d2.idField]).sort();
    await s2.stop();

    expect(ids1.length).toBeGreaterThan(0);
    expect(ids1).toEqual(ids2);
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
        """L1: the content-graph module file exists at the required path."""
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
        # an exported factory function (create*/make*/*Store/*Graph/seed*)
        assert re.search(
            r"export\s+(const|function)\s+\w*(create|make|store|graph|catalog|content|seed)\w*",
            src,
            re.IGNORECASE,
        ), "no store-factory export found"

    def test_module_has_no_other_example_imports(self):
        """L1: module is self-contained (does not import from sibling example files)."""
        src = self._read(self.MODULE_PATH)
        for m in re.finditer(r"""import[^;]*?from\s*['"]([^'"]+)['"]""", src):
            spec = m.group(1)
            if "examples/" in spec and "contentGraph" not in spec:
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

    def test_harness_interface_three_implementors(self, harness_report):
        """L2: a shared interface with non-null id is implemented by article/video/tag kinds."""
        self._passed(harness_report, r"shared interface carries a non-null id")

    def test_harness_node_field_returns_interface(self, harness_report):
        """L2: a single root field returns the interface (nullable) with one id argument."""
        self._passed(harness_report, r"single refetch entry point returns the shared interface")

    def test_harness_refetch_article(self, harness_report):
        """L2: refetch hit for an article -> __typename article kind + title."""
        self._passed(harness_report, r"refetch HIT for an article")

    def test_harness_refetch_video(self, harness_report):
        """L2: refetch hit for a video -> __typename video kind."""
        self._passed(harness_report, r"refetch HIT for a video")

    def test_harness_refetch_tag(self, harness_report):
        """L2: refetch hit for a tag -> __typename tag kind + label."""
        self._passed(harness_report, r"refetch HIT for a tag")

    def test_harness_refetch_miss_null(self, harness_report):
        """L2: unknown id resolves to null through the entry point, no execution error."""
        self._passed(harness_report, r"refetch MISS resolves to null")

    def test_harness_unnarrowed_id(self, harness_report):
        """L2: the shared id is requestable without a narrowing inline fragment."""
        self._passed(harness_report, r"requestable through the entry point WITHOUT a narrowing")

    def test_harness_list_queries_nonnull(self, harness_report):
        """L2: article/video lists never null, no null entries, every item refetchable."""
        self._passed(harness_report, r"list queries never null")

    def test_harness_nested_tag_objects(self, harness_report):
        """L2: tags resolve to nested tag objects (label + id), not id strings."""
        self._passed(harness_report, r"tags resolve to nested tag OBJECTS")

    def test_harness_global_id_uniqueness(self, harness_report):
        """L2: ids are globally unique across all three kinds (no cross-kind collision)."""
        self._passed(harness_report, r"globally unique across articles, videos, and tags")

    def test_harness_shared_tag_identical(self, harness_report):
        """L2: a tag shared by two parents refetches identically through the entry point."""
        self._passed(harness_report, r"shared by two parents refetches identically")

    def test_harness_deterministic_store(self, harness_report):
        """L2: the store factory is deterministic across two fresh servers."""
        self._passed(harness_report, r"deterministic: two fresh servers")
