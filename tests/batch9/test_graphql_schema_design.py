"""Benchmark tests for the `graphql-schema-design` skill (variant ext9).

Skill task (ext9): build a self-contained "task-board" GraphQL feature module
inside the `@apollo/server` package
(`packages/server/src/examples/taskBoard.ts`) that exports `typeDefs` (an SDL
string), `resolvers`, and an in-memory data-store factory for a boards ->
columns -> cards domain, plus a Jest suite at
`packages/server/src/__tests__/examples/taskBoard.test.ts`.

The *central concern* of this variant is INTENTIONAL NULLABILITY and LIST
CONTRACTS, all of which must be discoverable through GraphQL introspection:

  - Always present (non-null): every identifier, a board name, a column title,
    a card title.
  - Optional (nullable): a card's description, a card's assignee handle.
  - List contracts: a board's columns, a column's cards, and a card's labels
    are each a NON-NULL LIST of NON-NULL items.  A column seeded with zero
    cards yields an EMPTY LIST (never null); a card with no labels yields an
    EMPTY LIST (never null).
  - A board fetched by an unknown id resolves to `null` with no execution error.
  - A card with no description / no assignee reads those scalars as `null`
    (never empty-string substitutes).

What this file verifies
-----------------------
L1 (existence / minimal well-formedness):
  - the two deliverable files exist,
  - the module exports `typeDefs` / `resolvers` / a store factory,
  - the module is self-contained (no imports from sibling example files),
  - the module does not touch the package's public `index.ts` exports,
  - the agent's own Jest suite declares >= 10 `it`/`test` cases,
  - the agent's own Jest suite passes (acceptance command).

L2 (dynamic execution -- the discriminative core):
  Instead of trusting the agent's own tests, we synthesize an INDEPENDENT
  TypeScript Jest harness, drop it under
  `src/__tests__/examples/__bench__/`, and run it through the repo's native
  `jest` toolchain.  The harness builds an `ApolloServer` directly from the
  module's `typeDefs`/`resolvers`, introspects the schema to discover the real
  board/column/card type and field names (so we do not hard-code the agent's
  naming choices), and then exercises every Acceptance-Criterion scenario:

    * nested board -> columns -> cards resolution in seeded order,
    * a column seeded with zero cards yields an empty list (not null),
    * a card with no labels yields an empty list (not null),
    * a card with no description reads as null (not ""),
    * a card with no assignee reads as null (not ""),
    * introspection: card description & assignee are NULLABLE,
    * introspection: card title & every id are NON-NULL,
    * introspection: card labels is a NON-NULL LIST of NON-NULL items,
    * introspection: board columns is a NON-NULL LIST of NON-NULL items,
    * introspection: column cards is a NON-NULL LIST of NON-NULL items,
    * board list query returns a non-null list of non-null boards,
    * board fetch MISS returns null with no execution error.

  A stub that hardcodes non-empty cards, emits null instead of [] for empty
  lists, returns "" instead of null for absent scalars, or marks optional
  scalars NON_NULL (or required scalars nullable) FAILS the corresponding
  harness case.  We run jest with `--json` and assert on individual named test
  outcomes.

The native acceptance command this L2 drives:
    npx jest packages/server/src/__tests__/examples/taskBoard.test.ts --verbose
(executed via the workspace-hoisted jest binary, with --json/--runInBand).
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
    MODULE_REL = "src/examples/taskBoard.ts"
    SUITE_REL = "src/__tests__/examples/taskBoard.test.ts"
    MODULE_PATH = os.path.join(SERVER_DIR, "src", "examples", "taskBoard.ts")
    SUITE_PATH = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "taskBoard.test.ts"
    )

    # Directory where we drop our own independent harness suite.
    HARNESS_DIR = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "__bench__"
    )
    HARNESS_NAME = "benchTaskBoard.test.ts"
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
        #   - ApolloServer    -> ../../../index.js
        #   - module under test -> ../../../examples/taskBoard.js
        return r"""// @ts-nocheck
import { describe, it, expect } from '@jest/globals';
import { ApolloServer } from '../../../index.js';
import * as mod from '../../../examples/taskBoard.js';

const typeDefs: any = (mod as any).typeDefs;
const resolvers: any = (mod as any).resolvers;

// ---- locate the store factory without hard-coding its name ----------------
function findFactory(): (() => any) | null {
  const preferred = [
    'createStore', 'makeStore', 'createTaskBoard', 'makeTaskBoard',
    'createDataStore', 'createInMemoryStore', 'storeFactory',
    'createBoardStore', 'createTaskBoardStore', 'seedStore', 'createSeed',
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

// ---- type-ref unwrapping ----------------------------------------------------
function unwrap(t: any): any {
  let nonNull = false, list = false, listItemNonNull = false, cur = t;
  // peel an outer NON_NULL
  if (cur && cur.kind === 'NON_NULL') { nonNull = true; cur = cur.ofType; }
  if (cur && cur.kind === 'LIST') {
    list = true;
    cur = cur.ofType;
    if (cur && cur.kind === 'NON_NULL') { listItemNonNull = true; cur = cur.ofType; }
  }
  // peel any remaining wrappers down to the named type
  while (cur && (cur.kind === 'NON_NULL' || cur.kind === 'LIST')) cur = cur.ofType;
  return {
    kind: cur ? cur.kind : '',
    name: cur ? cur.name : null,
    nonNull, list, listItemNonNull,
  };
}

const TYPEREF = `kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name } } } }`;
const INTRO = `
{
  __schema {
    queryType { name }
    types {
      kind name
      fields {
        name
        args { name type { ${TYPEREF} } }
        type { ${TYPEREF} }
      }
    }
  }
}`;

// ---- discover board/column/card object types and their field names ---------
async function discover(server: any) {
  const intro = await run(server, INTRO);
  if (intro.errors) throw new Error('introspection errors: ' + JSON.stringify(intro.errors));
  const sch = intro.data.__schema;
  const types: any[] = sch.types.filter((t: any) => t.kind === 'OBJECT' && !/^__/.test(t.name));
  const qType = sch.types.find((t: any) => t.name === sch.queryType.name);

  const hasField = (t: any, rx: RegExp) =>
    t.fields && t.fields.some((f: any) => rx.test(f.name));
  const listFieldTo = (t: any, targetName: string) =>
    t.fields && t.fields.find((f: any) => {
      const u = unwrap(f.type);
      return u.list && u.name === targetName;
    });

  // card: an OBJECT with a title plus optional description/assignee plus a labels list
  const cardT = types.find((t: any) =>
    hasField(t, /^title$/i) &&
    hasField(t, /(description|desc)/i) &&
    hasField(t, /(assignee|assigned|handle|owner)/i) &&
    t.fields.some((f: any) => unwrap(f.type).list && unwrap(f.type).name === 'String'),
  );
  if (!cardT) throw new Error('could not identify card type');

  // column: an OBJECT with a title that holds a list of cards
  const columnT = types.find((t: any) =>
    t.name !== cardT.name &&
    hasField(t, /(title|name)/i) &&
    !!listFieldTo(t, cardT.name),
  );
  if (!columnT) throw new Error('could not identify column type');

  // board: an OBJECT with a name that holds a list of columns
  const boardT = types.find((t: any) =>
    t.name !== cardT.name && t.name !== columnT.name &&
    hasField(t, /name/i) &&
    !!listFieldTo(t, columnT.name),
  );
  if (!boardT) throw new Error('could not identify board type');

  const fieldName = (t: any, rx: RegExp) => {
    const f = t.fields.find((x: any) => rx.test(x.name));
    return f ? f.name : null;
  };
  const idField = (t: any) =>
    fieldName(t, /^id$/i) || fieldName(t, /id$/i);

  const columnsOnBoard = listFieldTo(boardT, columnT.name).name;
  const cardsOnColumn = listFieldTo(columnT, cardT.name).name;
  const labelsOnCard = cardT.fields.find(
    (f: any) => unwrap(f.type).list && unwrap(f.type).name === 'String',
  ).name;

  // root queries: single board (returns board, takes >=1 arg) and list-of-boards
  const boardSingleQ = qType.fields.find((f: any) => {
    const u = unwrap(f.type);
    return u.name === boardT.name && !u.list && (f.args || []).length >= 1;
  });
  const boardListQ = qType.fields.find((f: any) => {
    const u = unwrap(f.type);
    return u.name === boardT.name && u.list;
  });

  return {
    types, boardT, columnT, cardT,
    boardId: idField(boardT), columnId: idField(columnT), cardId: idField(cardT),
    boardName: fieldName(boardT, /name/i),
    columnTitle: fieldName(columnT, /(title|name)/i),
    cardTitle: fieldName(cardT, /^title$/i),
    cardDescription: fieldName(cardT, /(description|desc)/i),
    cardAssignee: fieldName(cardT, /(assignee|assigned|handle|owner)/i),
    columnsOnBoard, cardsOnColumn, labelsOnCard,
    boardSingleQ, boardListQ,
  };
}

function fullBoardQuery(d: any): string {
  return `
  {
    ${d.boardListQ.name} {
      ${d.boardId}
      ${d.boardName}
      ${d.columnsOnBoard} {
        ${d.columnId}
        ${d.columnTitle}
        ${d.cardsOnColumn} {
          ${d.cardId}
          ${d.cardTitle}
          ${d.cardDescription}
          ${d.cardAssignee}
          ${d.labelsOnCard}
        }
      }
    }
  }`;
}

function allCards(boards: any[], d: any): any[] {
  const out: any[] = [];
  for (const b of boards) {
    for (const c of (b[d.columnsOnBoard] || [])) {
      for (const card of (c[d.cardsOnColumn] || [])) out.push(card);
    }
  }
  return out;
}
function allColumns(boards: any[], d: any): any[] {
  const out: any[] = [];
  for (const b of boards) for (const c of (b[d.columnsOnBoard] || [])) out.push(c);
  return out;
}

describe('task board schema (independent harness)', () => {

  it('schema builds and exposes board/column/card object types', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.boardT).toBeTruthy();
    expect(d.columnT).toBeTruthy();
    expect(d.cardT).toBeTruthy();
    expect(d.boardId && d.columnId && d.cardId).toBeTruthy();
    expect(d.boardListQ).toBeTruthy();
    expect(d.boardSingleQ).toBeTruthy();
    await server.stop();
  });

  it('board list query returns a NON-NULL list of NON-NULL boards (introspection)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const u = unwrap(d.boardListQ.type);
    expect(u.list).toBe(true);
    expect(u.nonNull).toBe(true);          // outer list non-null
    expect(u.listItemNonNull).toBe(true);  // items non-null
    expect(u.name).toBe(d.boardT.name);
    await server.stop();
  });

  it('introspection: identifiers, board name, column title, card title are NON-NULL', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const nn = (t: any, name: string) => {
      const f = t.fields.find((x: any) => x.name === name);
      expect(f).toBeTruthy();
      return unwrap(f.type).nonNull;
    };
    expect(nn(d.boardT, d.boardId)).toBe(true);
    expect(nn(d.columnT, d.columnId)).toBe(true);
    expect(nn(d.cardT, d.cardId)).toBe(true);
    expect(nn(d.boardT, d.boardName)).toBe(true);
    expect(nn(d.columnT, d.columnTitle)).toBe(true);
    expect(nn(d.cardT, d.cardTitle)).toBe(true);
    await server.stop();
  });

  it('introspection: card description and assignee are NULLABLE (optional)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const fld = (name: string) => d.cardT.fields.find((x: any) => x.name === name);
    const desc = fld(d.cardDescription);
    const asg = fld(d.cardAssignee);
    expect(desc).toBeTruthy();
    expect(asg).toBeTruthy();
    expect(unwrap(desc.type).nonNull).toBe(false);
    expect(unwrap(asg.type).nonNull).toBe(false);
    // and they are plain scalars (not lists)
    expect(unwrap(desc.type).list).toBe(false);
    expect(unwrap(asg.type).list).toBe(false);
    await server.stop();
  });

  it('introspection: card labels is a NON-NULL LIST of NON-NULL String', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const f = d.cardT.fields.find((x: any) => x.name === d.labelsOnCard);
    const u = unwrap(f.type);
    expect(u.list).toBe(true);
    expect(u.nonNull).toBe(true);
    expect(u.listItemNonNull).toBe(true);
    expect(u.name).toBe('String');
    await server.stop();
  });

  it('introspection: board columns is a NON-NULL LIST of NON-NULL items', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const f = d.boardT.fields.find((x: any) => x.name === d.columnsOnBoard);
    const u = unwrap(f.type);
    expect(u.list).toBe(true);
    expect(u.nonNull).toBe(true);
    expect(u.listItemNonNull).toBe(true);
    expect(u.name).toBe(d.columnT.name);
    await server.stop();
  });

  it('introspection: column cards is a NON-NULL LIST of NON-NULL items', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const f = d.columnT.fields.find((x: any) => x.name === d.cardsOnColumn);
    const u = unwrap(f.type);
    expect(u.list).toBe(true);
    expect(u.nonNull).toBe(true);
    expect(u.listItemNonNull).toBe(true);
    expect(u.name).toBe(d.cardT.name);
    await server.stop();
  });

  it('nested board -> columns -> cards resolve in seeded order with stable ids', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const res = await run(server, fullBoardQuery(d));
    expect(res.errors).toBeFalsy();
    const boards = res.data[d.boardListQ.name];
    expect(Array.isArray(boards)).toBe(true);
    expect(boards.length).toBeGreaterThan(0);

    // at least one board has at least one column with at least one card
    const cards = allCards(boards, d);
    expect(cards.length).toBeGreaterThan(0);

    // every reachable card/column/board has a non-null id and required title/name
    for (const b of boards) {
      expect(b[d.boardId]).toBeTruthy();
      expect(typeof b[d.boardName]).toBe('string');
      expect(b[d.boardName].length).toBeGreaterThan(0);
      expect(Array.isArray(b[d.columnsOnBoard])).toBe(true);
      for (const col of b[d.columnsOnBoard]) {
        expect(col[d.columnId]).toBeTruthy();
        expect(typeof col[d.columnTitle]).toBe('string');
        expect(col[d.columnTitle].length).toBeGreaterThan(0);
        expect(Array.isArray(col[d.cardsOnColumn])).toBe(true);
        for (const card of col[d.cardsOnColumn]) {
          expect(card[d.cardId]).toBeTruthy();
          expect(typeof card[d.cardTitle]).toBe('string');
          expect(card[d.cardTitle].length).toBeGreaterThan(0);
          expect(Array.isArray(card[d.labelsOnCard])).toBe(true);
        }
      }
    }

    // ids are unique within each scope (no hardcoded duplication)
    const cardIds = cards.map((c: any) => c[d.cardId]);
    expect(new Set(cardIds).size).toBe(cardIds.length);
    await server.stop();
  });

  it('a column seeded with zero cards yields an EMPTY LIST, never null', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const res = await run(server, fullBoardQuery(d));
    expect(res.errors).toBeFalsy();
    const boards = res.data[d.boardListQ.name];
    const columns = allColumns(boards, d);
    // every column's cards must be an array (never null) -- the contract
    for (const col of columns) {
      expect(col[d.cardsOnColumn]).not.toBeNull();
      expect(Array.isArray(col[d.cardsOnColumn])).toBe(true);
    }
    // and at least one seeded column has exactly zero cards (the empty case)
    const emptyCols = columns.filter((c: any) => c[d.cardsOnColumn].length === 0);
    expect(emptyCols.length).toBeGreaterThan(0);
    await server.stop();
  });

  it('a card with no labels yields an EMPTY LIST, never null', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const res = await run(server, fullBoardQuery(d));
    expect(res.errors).toBeFalsy();
    const cards = allCards(res.data[d.boardListQ.name], d);
    for (const card of cards) {
      expect(card[d.labelsOnCard]).not.toBeNull();
      expect(Array.isArray(card[d.labelsOnCard])).toBe(true);
      for (const lbl of card[d.labelsOnCard]) {
        expect(typeof lbl).toBe('string');  // non-null string items
      }
    }
    // at least one seeded card has zero labels (the empty case exists)
    const noLabel = cards.filter((c: any) => c[d.labelsOnCard].length === 0);
    expect(noLabel.length).toBeGreaterThan(0);
    await server.stop();
  });

  it('a card with no description / no assignee reads as null, never empty-string', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const res = await run(server, fullBoardQuery(d));
    expect(res.errors).toBeFalsy();
    const cards = allCards(res.data[d.boardListQ.name], d);

    // absent optionals must be exactly null (a stub that emits "" fails here)
    for (const card of cards) {
      const desc = card[d.cardDescription];
      const asg = card[d.cardAssignee];
      expect(desc === null || (typeof desc === 'string' && desc.length > 0)).toBe(true);
      expect(asg === null || (typeof asg === 'string' && asg.length > 0)).toBe(true);
    }
    // the seed must actually exercise the null cases
    const nullDesc = cards.filter((c: any) => c[d.cardDescription] === null);
    const nullAsg = cards.filter((c: any) => c[d.cardAssignee] === null);
    expect(nullDesc.length).toBeGreaterThan(0);
    expect(nullAsg.length).toBeGreaterThan(0);
    await server.stop();
  });

  it('single board fetch HIT returns its name and ordered columns/cards', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const list = await run(server, fullBoardQuery(d));
    const boards = list.data[d.boardListQ.name];
    // pick a board that actually has columns + cards
    const target = boards.find((b: any) =>
      (b[d.columnsOnBoard] || []).some((c: any) => (c[d.cardsOnColumn] || []).length > 0),
    ) || boards[0];
    const knownId = target[d.boardId];

    const argName = d.boardSingleQ.args[0].name;
    const argT = unwrapTopName(d.boardSingleQ.args[0].type);
    const q = `query($id: ${argT}){ ${d.boardSingleQ.name}(${argName}: $id){
      ${d.boardId} ${d.boardName}
      ${d.columnsOnBoard} { ${d.columnId} ${d.columnTitle} ${d.cardsOnColumn} { ${d.cardId} ${d.cardTitle} } }
    } }`;
    const res = await run(server, q, { id: knownId });
    expect(res.errors).toBeFalsy();
    const b = res.data[d.boardSingleQ.name];
    expect(b).toBeTruthy();
    expect(b[d.boardId]).toBe(knownId);
    expect(typeof b[d.boardName]).toBe('string');
    expect(b[d.boardName].length).toBeGreaterThan(0);

    // column order matches the list-query ordering for the same board
    const expectedColIds = (target[d.columnsOnBoard] || []).map((c: any) => c[d.columnId]);
    const gotColIds = (b[d.columnsOnBoard] || []).map((c: any) => c[d.columnId]);
    expect(gotColIds).toEqual(expectedColIds);
    await server.stop();
  });

  it('single board fetch MISS yields null board and no execution error', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const argName = d.boardSingleQ.args[0].name;
    const argT = unwrapTopName(d.boardSingleQ.args[0].type);
    const q = `query($id: ${argT}){ ${d.boardSingleQ.name}(${argName}: $id){ ${d.boardId} } }`;
    const res = await run(server, q, { id: 'definitely-not-a-real-board-zzz' });
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    expect(res.data[d.boardSingleQ.name]).toBeNull();
    await server.stop();
  });

  it('store factory returns a FRESH, independent store on each call', async () => {
    const factory = findFactory();
    expect(factory).toBeTruthy();
    const a = (factory as any)();
    const b = (factory as any)();
    expect(a).toBeTruthy();
    expect(b).toBeTruthy();
    expect(a).not.toBe(b);  // distinct instances, not a shared singleton
    await Promise.resolve();
  });
});

function unwrapTopName(t: any): string {
  if (!t) return 'ID';
  if (t.kind === 'NON_NULL') return unwrapTopName(t.ofType) + '!';
  if (t.kind === 'LIST') return '[' + unwrapTopName(t.ofType) + ']';
  return t.name || 'ID';
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
        """L1: the task-board module file exists at the required path."""
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
        # an exported factory function (create*/make*/*Store/*Board/seed*)
        assert re.search(
            r"export\s+(const|function)\s+\w*(create|make|store|board|seed)\w*",
            src,
            re.IGNORECASE,
        ), "no store-factory export found"

    def test_module_has_no_other_example_imports(self):
        """L1: module is self-contained (does not import from sibling example files)."""
        src = self._read(self.MODULE_PATH)
        for m in re.finditer(r"""import[^;]*?from\s*['"]([^'"]+)['"]""", src):
            spec = m.group(1)
            if "examples/" in spec and "taskBoard" not in spec:
                pytest.fail(f"module imports another example file: {spec}")

    def test_public_index_not_modified_for_taskboard(self):
        """L1: the package's public index.ts is NOT made to export the task board
        (the task forbids modifying public index exports)."""
        index_path = os.path.join(self.SERVER_DIR, "src", "index.ts")
        if not os.path.isfile(index_path):
            pytest.skip("index.ts not present")
        src = self._read(index_path)
        assert not re.search(
            r"taskBoard", src, re.IGNORECASE
        ), "public index.ts must not reference taskBoard"

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

        Drives: npx jest packages/server/src/__tests__/examples/taskBoard.test.ts
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

    def test_harness_schema_and_entities(self, harness_report):
        """L2: schema builds; board/column/card object types + queries exist."""
        self._passed(harness_report, r"schema builds and exposes board/column/card")

    def test_harness_board_list_nonnull_wrapping(self, harness_report):
        """L2: board list query is a non-null list of non-null boards (introspection)."""
        self._passed(harness_report, r"board list query returns a NON-NULL list")

    def test_harness_required_scalars_nonnull(self, harness_report):
        """L2: ids, board name, column title, card title are NON-NULL (introspection)."""
        self._passed(harness_report, r"identifiers, board name, column title, card title are NON-NULL")

    def test_harness_optional_scalars_nullable(self, harness_report):
        """L2: card description & assignee are NULLABLE (introspection)."""
        self._passed(harness_report, r"card description and assignee are NULLABLE")

    def test_harness_labels_nonnull_list_of_nonnull(self, harness_report):
        """L2: card labels is a non-null list of non-null String (introspection)."""
        self._passed(harness_report, r"card labels is a NON-NULL LIST of NON-NULL String")

    def test_harness_columns_nonnull_list_of_nonnull(self, harness_report):
        """L2: board columns is a non-null list of non-null items (introspection)."""
        self._passed(harness_report, r"board columns is a NON-NULL LIST")

    def test_harness_cards_nonnull_list_of_nonnull(self, harness_report):
        """L2: column cards is a non-null list of non-null items (introspection)."""
        self._passed(harness_report, r"column cards is a NON-NULL LIST")

    def test_harness_nested_resolution_in_order(self, harness_report):
        """L2: nested board->columns->cards resolve in seeded order with stable ids."""
        self._passed(harness_report, r"nested board -> columns -> cards resolve in seeded order")

    def test_harness_empty_cards_list_not_null(self, harness_report):
        """L2: a column with zero cards yields an empty list, never null."""
        self._passed(harness_report, r"column seeded with zero cards yields an EMPTY LIST")

    def test_harness_empty_labels_list_not_null(self, harness_report):
        """L2: a card with no labels yields an empty list, never null."""
        self._passed(harness_report, r"card with no labels yields an EMPTY LIST")

    def test_harness_absent_scalars_are_null(self, harness_report):
        """L2: absent description/assignee read as null, never empty-string."""
        self._passed(harness_report, r"no description / no assignee reads as null")

    def test_harness_single_board_hit(self, harness_report):
        """L2: single board fetch hit returns name + ordered columns/cards."""
        self._passed(harness_report, r"single board fetch HIT")

    def test_harness_single_board_miss_null(self, harness_report):
        """L2: unknown board id resolves to null with no execution error."""
        self._passed(harness_report, r"single board fetch MISS")

    def test_harness_fresh_store_factory(self, harness_report):
        """L2: store factory yields a fresh, independent store on each call."""
        self._passed(harness_report, r"store factory returns a FRESH, independent store")
