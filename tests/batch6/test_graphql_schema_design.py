"""Benchmark tests for the `graphql-schema-design` skill (variant ext6).

Skill task (ext6): build a self-contained "event seat-reservation" GraphQL
feature module inside the `@apollo/server` package at
`packages/server/src/examples/seatReservation.ts` that exports `typeDefs`
(SDL string), `resolvers`, and an in-memory data-store factory, plus a Jest
test suite at
`packages/server/src/__tests__/examples/seatReservation.test.ts`.

The module models **events**, each owning a fixed set of **seats** (free or
held by a named holder).  Two mutations communicate *expected, recoverable*
failures through their RETURN SHAPE (a discriminated payload) instead of the
top-level GraphQL `errors` array:

  reserve(input)  -> success | seat-already-taken (names current holder)
                     | seat-not-found
  release(input)  -> success | seat-already-free | seat-not-found

A successful reserve/release must actually MUTATE the store (a follow-up query
reflects the change).  An explicitly empty holder name supplied to reserve is a
*true* validation/illegal-input failure that must be rejected BEFORE resolvers
run (top-level errors, not a payload outcome).  A single-event query returns
absent (null, no error) on an unknown id; the seats list is non-null with no
null entries.

What this file verifies
-----------------------
L1 (existence / minimal well-formedness):
  - the two deliverable files exist,
  - the module exports `typeDefs` / `resolvers` / a store factory,
  - the module imports no sibling example file,
  - the module is not wired into the package's public `index.ts`,
  - the agent's own Jest suite declares >= 10 `it`/`test` cases,
  - the agent's own Jest suite passes (acceptance command).

L2 (dynamic execution -- the discriminative core):
  Instead of trusting the agent's own tests, we synthesize an INDEPENDENT
  TypeScript Jest harness, drop it next to the module, and run it through the
  repo's native `jest` toolchain.  The harness builds an `ApolloServer`
  directly from the module's `typeDefs`/`resolvers`, introspects the schema to
  discover the real type/field/enum/mutation/input names (so we do not hard-code
  the agent's naming choices), and then exercises every Acceptance scenario:

    * event fetch HIT (seats list non-null, no null entries) and MISS (null, no
      execution error),
    * reserve a free seat -> success outcome + a follow-up query proves the seat
      is now held by that holder (real store mutation),
    * reserve an already-held seat -> already-taken outcome that names the
      current holder; top-level errors empty; store unchanged,
    * reserve a non-existent seat -> seat-not-found outcome; top-level errors
      empty,
    * reserve takes a SINGLE structured (input-object) argument,
    * reserve with an explicitly empty holder name -> VALIDATION failure before
      resolvers run (top-level errors, no payload), and the store is NOT mutated,
    * release a held seat -> success + follow-up query shows it free again
      (real store mutation),
    * release an already-free seat -> already-free outcome; errors empty,
    * release a non-existent seat -> seat-not-found outcome; errors empty,
    * the three reserve outcomes are *mutually distinguishable* from the
      returned data alone (distinct __typename / discriminator).

  jest runs with `--json`; we assert on individual named test outcomes, so a
  stub / partial / "looks related" solution fails (e.g. a reserve that throws on
  already-taken instead of returning a payload, that doesn't persist, that
  funnels empty-holder through the payload, or that returns the same shape for
  all outcomes).
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
    MODULE_REL = "src/examples/seatReservation.ts"
    SUITE_REL = "src/__tests__/examples/seatReservation.test.ts"
    MODULE_PATH = os.path.join(SERVER_DIR, "src", "examples", "seatReservation.ts")
    SUITE_PATH = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "seatReservation.test.ts"
    )
    INDEX_PATH = os.path.join(SERVER_DIR, "src", "index.ts")

    # Directory where we drop our own independent harness suite.
    HARNESS_DIR = os.path.join(
        SERVER_DIR, "src", "__tests__", "examples", "__bench__"
    )
    HARNESS_NAME = "benchSeatReservation.test.ts"
    HARNESS_PATH = os.path.join(HARNESS_DIR, HARNESS_NAME)
    HARNESS_REL = "src/__tests__/examples/__bench__/" + HARNESS_NAME

    # ----------------------------------------------------------------- helpers
    @classmethod
    def _read(cls, path):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()

    @classmethod
    def _jest_bin(cls):
        """Locate the workspace-hoisted jest binary (walk up from packages/server)."""
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
        #   - module under test -> ../../../examples/seatReservation.js
        return r"""// @ts-nocheck
import { describe, it, expect } from '@jest/globals';
import { ApolloServer } from '../../../index.js';
import * as mod from '../../../examples/seatReservation.js';

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

// ---- type-ref unwrap --------------------------------------------------------
function unwrap(t: any): any {
  let nonNull = false, list = false, listItemNonNull = false, cur = t;
  let sawList = false;
  while (cur) {
    if (cur.kind === 'NON_NULL') {
      if (sawList) listItemNonNull = true; else nonNull = true;
      cur = cur.ofType; continue;
    }
    if (cur.kind === 'LIST') { list = true; sawList = true; cur = cur.ofType; continue; }
    break;
  }
  return {
    kind: cur ? cur.kind : '',
    name: cur ? cur.name : null,
    nonNull, list, listItemNonNull,
  };
}
function sdl(t: any): string {
  if (!t) return 'ID';
  if (t.kind === 'NON_NULL') return sdl(t.ofType) + '!';
  if (t.kind === 'LIST') return '[' + sdl(t.ofType) + ']';
  return t.name || 'ID';
}

const TYPEREF = `kind name ofType { kind name ofType { kind name ofType { kind name ofType { kind name } } } }`;
const INTRO = `
{
  __schema {
    queryType { name }
    mutationType { name }
    types {
      kind name
      possibleTypes { kind name }
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

// -------- schema discovery: locate the event / seat / mutation shapes --------
async function discover(server: any) {
  const intro = await run(server, INTRO);
  expect(intro.errors).toBeFalsy();
  const sch = intro.data.__schema;
  const types: any[] = sch.types;
  const byName: Record<string, any> = {};
  for (const t of types) byName[t.name] = t;
  const qType = types.find((t) => t.name === sch.queryType.name);
  const mType = sch.mutationType ? types.find((t) => t.name === sch.mutationType.name) : null;

  // Seat object: OBJECT with a label/name-ish field AND a holder-ish field.
  const seatObj = types.find(
    (t) => t.kind === 'OBJECT' && t.fields &&
      t.fields.some((f: any) => /^id$/i.test(f.name) || /id$/i.test(f.name)) &&
      t.fields.some((f: any) => /(label|name|number|row)/i.test(f.name)) &&
      t.fields.some((f: any) => /(holder|holdBy|heldBy|reservedBy|occupant|owner)/i.test(f.name)),
  );
  // Event object: OBJECT with a name and a LIST field whose element is the seat.
  const eventObj = types.find(
    (t) => t.kind === 'OBJECT' && t.fields && seatObj &&
      t.name !== seatObj.name &&
      t.fields.some((f: any) => /(name|title)/i.test(f.name)) &&
      t.fields.some((f: any) => unwrap(f.type).name === seatObj.name && unwrap(f.type).list),
  );

  const idField = (obj: any) =>
    (obj.fields.find((f: any) => /^id$/i.test(f.name)) ||
     obj.fields.find((f: any) => /id$/i.test(f.name))).name;

  // single-event query: returns eventObj (not list), takes an id-ish arg.
  const eventQ = qType.fields.find((f: any) => {
    const u = unwrap(f.type);
    return u.name === (eventObj && eventObj.name) && !u.list && f.args.length >= 1;
  });

  // seats list field on the event + its holder field on a seat.
  const seatsField = eventObj
    ? eventObj.fields.find((f: any) => unwrap(f.type).name === seatObj.name && unwrap(f.type).list)
    : null;
  const seatLabel = seatObj
    ? (seatObj.fields.find((f: any) => /(label|number|row)/i.test(f.name)) ||
       seatObj.fields.find((f: any) => /name/i.test(f.name))).name
    : null;
  const seatHolder = seatObj
    ? seatObj.fields.find((f: any) => /(holder|holdBy|heldBy|reservedBy|occupant|owner)/i.test(f.name)).name
    : null;

  // mutations: reserve & release, each returning an OBJECT or UNION payload and
  // taking a single structured (input object) argument.
  const reserveM = mType && mType.fields.find((f: any) =>
    /reserv|book|hold|claim/i.test(f.name));
  const releaseM = mType && mType.fields.find((f: any) =>
    /releas|cancel|free|unreserv|unbook/i.test(f.name));

  return {
    types, byName, qType, mType,
    eventObj, seatObj,
    eventId: eventObj ? idField(eventObj) : null,
    seatId: seatObj ? idField(seatObj) : null,
    eventQ, seatsField, seatLabel, seatHolder,
    reserveM, releaseM,
  };
}

function structuredArg(m: any, d: any): any {
  return m.args.find((a: any) => unwrap(a.type).kind === 'INPUT_OBJECT');
}
function inputObjType(arg: any, d: any): any {
  return d.types.find((t: any) => t.name === unwrap(arg.type).name);
}

// Fill an input object for reserve/release: map event id, seat id, holder name.
function buildOpInput(inType: any, eventId: any, seatId: any, holder: any): any {
  const obj: any = {};
  for (const f of (inType.inputFields || [])) {
    const u = unwrap(f.type);
    if (/event/i.test(f.name)) obj[f.name] = eventId;
    else if (/seat/i.test(f.name)) obj[f.name] = seatId;
    else if (/(holder|name|who|by)/i.test(f.name) && (u.name === 'String' || u.name === 'ID')) {
      if (holder !== undefined) obj[f.name] = holder;
    } else if (u.nonNull) {
      // best-effort fill for any other required scalar
      if (u.name === 'String' || u.name === 'ID') obj[f.name] = eventId;
      else if (u.name === 'Int') obj[f.name] = 1;
      else if (u.name === 'Boolean') obj[f.name] = false;
    }
  }
  return obj;
}
// find the holder field name on the input object (for the empty-holder test)
function holderInputField(inType: any): any {
  return (inType.inputFields || []).find((f: any) => {
    const u = unwrap(f.type);
    return /(holder|name|who|by)/i.test(f.name) && (u.name === 'String' || u.name === 'ID');
  });
}

// Selection for a mutation payload: __typename + all scalar/enum fields + a
// nested seat (with id/label/holder) if present + any nested holder/string field.
function payloadSelection(payloadType: any, d: any): string {
  if (payloadType.kind === 'UNION') {
    const parts: string[] = ['__typename'];
    for (const pt of (payloadType.possibleTypes || [])) {
      const t = d.byName[pt.name];
      if (!t || !t.fields) continue;
      parts.push(`... on ${pt.name} { ${objBranchSelection(t, d)} }`);
    }
    return parts.join(' ');
  }
  return '__typename ' + objBranchSelection(payloadType, d);
}
function objBranchSelection(t: any, d: any): string {
  const parts: string[] = [];
  for (const f of (t.fields || [])) {
    const u = unwrap(f.type);
    if (u.name === (d.seatObj && d.seatObj.name) && !u.list) {
      parts.push(`${f.name} { ${d.seatId} ${d.seatLabel} ${d.seatHolder} }`);
    } else if (u.kind === 'SCALAR' || u.kind === 'ENUM') {
      parts.push(f.name);
    }
  }
  return parts.length ? parts.join(' ') : '__typename';
}

// dig a seat object out of a returned payload (nested or branch).
function digSeat(payload: any, d: any): any {
  if (payload == null || typeof payload !== 'object') return null;
  if (payload[d.seatId] !== undefined && payload[d.seatHolder] !== undefined) return payload;
  for (const v of Object.values(payload)) {
    if (v && typeof v === 'object' && !Array.isArray(v) &&
        (v as any)[d.seatId] !== undefined) return v;
  }
  return null;
}
// collect any holder-ish string value anywhere in the payload (for already-taken).
function collectHolderStrings(payload: any): string[] {
  const out: string[] = [];
  const visit = (o: any) => {
    if (!o || typeof o !== 'object') return;
    for (const [k, v] of Object.entries(o)) {
      if (typeof v === 'string' && /(holder|by|who|occupant|owner|name|message|reason)/i.test(k)) {
        out.push(v as string);
      } else if (v && typeof v === 'object') visit(v);
    }
  };
  visit(payload);
  return out;
}

// Fetch the first event's id and the ids of a free seat + a held seat, by
// probing the seeded store via queries.  We classify free vs held by holder.
async function probeEvent(server: any, d: any) {
  // We need a known event id.  Try reflecting from a list query if present,
  // else brute the eventQ with candidate seed ids is unreliable; instead read
  // every event-returning root field that yields a list of events.
  const listEventsQ = d.qType.fields.find((f: any) => {
    const u = unwrap(f.type);
    return u.name === (d.eventObj && d.eventObj.name) && u.list;
  });
  let eventId: any = null;
  if (listEventsQ) {
    const r = await run(server, `query{ ${listEventsQ.name} { ${d.eventId} } }`);
    expect(r.errors).toBeFalsy();
    const arr = r.data[listEventsQ.name];
    expect(Array.isArray(arr)).toBe(true);
    expect(arr.length).toBeGreaterThan(0);
    eventId = arr[0][d.eventId];
  }
  expect(eventId).toBeTruthy();

  const ev = await run(
    server,
    `query($id: ${sdl(d.eventQ.args[0].type)}){ ${d.eventQ.name}(${d.eventQ.args[0].name}: $id){ ${d.eventId} ${d.seatsField.name} { ${d.seatId} ${d.seatLabel} ${d.seatHolder} } } }`,
    { id: eventId },
  );
  expect(ev.errors).toBeFalsy();
  const event = ev.data[d.eventQ.name];
  expect(event).toBeTruthy();
  const seats = event[d.seatsField.name];
  expect(Array.isArray(seats)).toBe(true);
  expect(seats.every((s: any) => s != null)).toBe(true);

  const freeSeat = seats.find((s: any) => s[d.seatHolder] == null);
  const heldSeat = seats.find((s: any) => s[d.seatHolder] != null);
  return { eventId, seats, freeSeat, heldSeat };
}

async function reserve(server: any, d: any, eventId: any, seatId: any, holder: any) {
  const arg = structuredArg(d.reserveM, d);
  const inType = inputObjType(arg, d);
  const inVar = buildOpInput(inType, eventId, seatId, holder);
  const payloadType = d.byName[unwrap(d.reserveM.type).name];
  const sel = payloadSelection(payloadType, d);
  return run(
    server,
    `mutation($in: ${sdl(arg.type)}){ ${d.reserveM.name}(${arg.name}: $in){ ${sel} } }`,
    { in: inVar },
  );
}
async function release(server: any, d: any, eventId: any, seatId: any) {
  const arg = structuredArg(d.releaseM, d);
  const inType = inputObjType(arg, d);
  const inVar = buildOpInput(inType, eventId, seatId, undefined);
  const payloadType = d.byName[unwrap(d.releaseM.type).name];
  const sel = payloadSelection(payloadType, d);
  return run(
    server,
    `mutation($in: ${sdl(arg.type)}){ ${d.releaseM.name}(${arg.name}: $in){ ${sel} } }`,
    { in: inVar },
  );
}
async function refetchSeat(server: any, d: any, eventId: any, seatId: any) {
  const r = await run(
    server,
    `query($id: ${sdl(d.eventQ.args[0].type)}){ ${d.eventQ.name}(${d.eventQ.args[0].name}: $id){ ${d.seatsField.name} { ${d.seatId} ${d.seatHolder} } } }`,
    { id: eventId },
  );
  const seats = r.data[d.eventQ.name][d.seatsField.name];
  return seats.find((s: any) => String(s[d.seatId]) === String(seatId));
}
function typenameOf(payload: any): string | null {
  if (payload && typeof payload === 'object' && payload.__typename) return payload.__typename;
  return null;
}

describe('seat reservation (independent harness)', () => {

  it('schema exposes event/seat with non-null stable ids and a holder field', async () => {
    const server = await mkServer();
    const d = await discover(server);
    expect(d.eventObj).toBeTruthy();
    expect(d.seatObj).toBeTruthy();
    expect(d.reserveM).toBeTruthy();
    expect(d.releaseM).toBeTruthy();

    const evId = d.eventObj.fields.find((f: any) => f.name === d.eventId);
    const stId = d.seatObj.fields.find((f: any) => f.name === d.seatId);
    expect(unwrap(evId.type).nonNull).toBe(true);
    expect(unwrap(stId.type).nonNull).toBe(true);

    // seats list field on event is non-null with non-null element entries.
    const seatsF = d.eventObj.fields.find((f: any) => f.name === d.seatsField.name);
    const su = unwrap(seatsF.type);
    expect(su.list).toBe(true);
    expect(su.nonNull).toBe(true);
    expect(su.listItemNonNull).toBe(true);

    // a free seat's holder is nullable (absent when free).
    const holderF = d.seatObj.fields.find((f: any) => f.name === d.seatHolder);
    expect(unwrap(holderF.type).nonNull).toBe(false);
    await server.stop();
  });

  it('event fetch HIT returns seats list with no null entries; MISS returns null and no error', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const { eventId, seats } = await probeEvent(server, d);
    expect(seats.length).toBeGreaterThan(0);
    expect(seats.every((s: any) => s != null && s[d.seatId] != null)).toBe(true);

    const miss = await run(
      server,
      `query($id: ${sdl(d.eventQ.args[0].type)}){ ${d.eventQ.name}(${d.eventQ.args[0].name}: $id){ ${d.eventId} } }`,
      { id: 'no-such-event-zzz' },
    );
    expect(miss.errors == null || miss.errors.length === 0).toBe(true);
    expect(miss.data[d.eventQ.name]).toBeNull();
    await server.stop();
  });

  it('reserve takes a single structured (input object) argument', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const structured = d.reserveM.args.filter((a: any) => unwrap(a.type).kind === 'INPUT_OBJECT');
    expect(structured.length).toBe(1);
    // the input object actually carries event/seat/holder-ish fields
    const inType = inputObjType(structured[0], d);
    const names = (inType.inputFields || []).map((f: any) => f.name.toLowerCase()).join(',');
    expect(/event/.test(names)).toBe(true);
    expect(/seat/.test(names)).toBe(true);
    expect(/holder|name|who|by/.test(names)).toBe(true);
    await server.stop();
  });

  it('reserve a FREE seat -> success outcome; payload shows it held by the holder; follow-up query confirms persistence', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const { eventId, freeSeat } = await probeEvent(server, d);
    expect(freeSeat).toBeTruthy();
    const holder = 'Alice Bench';
    const res = await reserve(server, d, eventId, freeSeat[d.seatId], holder);
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    const payload = res.data[d.reserveM.name];
    expect(payload).toBeTruthy();
    const seat = digSeat(payload, d);
    expect(seat).toBeTruthy();
    expect(seat[d.seatHolder]).toBe(holder);

    // store actually mutated: refetch shows the seat held by that holder.
    const after = await refetchSeat(server, d, eventId, freeSeat[d.seatId]);
    expect(after).toBeTruthy();
    expect(after[d.seatHolder]).toBe(holder);
    await server.stop();
  });

  it('reserve an ALREADY-HELD seat -> already-taken outcome naming the current holder; errors empty; store unchanged', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const { eventId, freeSeat } = await probeEvent(server, d);
    // first reserve to create a held seat with a known holder
    const firstHolder = 'Original Holder';
    const first = await reserve(server, d, eventId, freeSeat[d.seatId], firstHolder);
    expect(first.errors == null || first.errors.length === 0).toBe(true);

    // second reserve of the same seat by a different holder
    const res = await reserve(server, d, eventId, freeSeat[d.seatId], 'Second Person');
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    const payload = res.data[d.reserveM.name];
    expect(payload).toBeTruthy();
    // outcome must be DISTINCT from the success branch
    const tn = typenameOf(payload);
    const holderStrings = collectHolderStrings(payload);
    // the current holder must be surfaced somewhere in the payload
    expect(holderStrings).toContain(firstHolder);
    // and the new holder must NOT have been applied
    expect(holderStrings).not.toContain('Second Person');

    // store unchanged: still held by original holder
    const after = await refetchSeat(server, d, eventId, freeSeat[d.seatId]);
    expect(after[d.seatHolder]).toBe(firstHolder);
    await server.stop();
  });

  it('reserve a NON-EXISTENT seat -> seat-not-found outcome; top-level errors empty', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const { eventId } = await probeEvent(server, d);
    const res = await reserve(server, d, eventId, 'no-such-seat-zzz', 'Nobody');
    expect(res.errors == null || res.errors.length === 0).toBe(true);
    const payload = res.data[d.reserveM.name];
    expect(payload).toBeTruthy();
    // no seat object produced for a not-found
    const seat = digSeat(payload, d);
    expect(seat == null || seat[d.seatHolder] == null).toBe(true);
    // and there is a discriminating signal (typename / message / code)
    const tn = typenameOf(payload);
    const signal =
      (tn && /(notfound|not_found|missing|unknown|invalid)/i.test(tn)) ||
      collectHolderStrings(payload).some((s) => /not.?found|missing|unknown|no\s|invalid/i.test(s)) ||
      Object.entries(payload).some(([k, v]) =>
        /(notfound|not_found|code|reason|message|kind|status)/i.test(k) && v != null && v !== '');
    expect(signal).toBe(true);
    await server.stop();
  });

  it('the three reserve outcomes are mutually distinguishable from returned data alone', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const { eventId, freeSeat } = await probeEvent(server, d);

    const success = await reserve(server, d, eventId, freeSeat[d.seatId], 'Disc Holder');
    const taken = await reserve(server, d, eventId, freeSeat[d.seatId], 'Other');
    const notfound = await reserve(server, d, eventId, 'no-such-seat-zzz', 'Other2');
    for (const r of [success, taken, notfound]) {
      expect(r.errors == null || r.errors.length === 0).toBe(true);
    }
    const ps = success.data[d.reserveM.name];
    const pt = taken.data[d.reserveM.name];
    const pn = notfound.data[d.reserveM.name];

    // Discriminate either by __typename (union/interface) or by a discriminator
    // field present-and-distinct.  We require all three to differ.
    const sig = (p: any): string => {
      const tn = typenameOf(p);
      if (tn) return 'TN:' + tn;
      // fallback: a discriminator scalar/enum field
      for (const [k, v] of Object.entries(p)) {
        if (/(kind|status|code|outcome|result|type)/i.test(k) && (typeof v === 'string')) {
          return k + '=' + v;
        }
      }
      // last resort: success has a non-null seat; failures don't / differ
      const seat = digSeat(p, d);
      return 'SEAT:' + (seat ? 'present' : 'absent');
    };
    const a = sig(ps), b = sig(pt), c = sig(pn);
    expect(a).not.toBe(b);
    expect(a).not.toBe(c);
    expect(b).not.toBe(c);
    await server.stop();
  });

  it('reserve with an explicitly EMPTY holder name fails VALIDATION before resolvers; store not mutated', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const { eventId, freeSeat } = await probeEvent(server, d);
    const before = await refetchSeat(server, d, eventId, freeSeat[d.seatId]);
    expect(before[d.seatHolder]).toBeNull();

    const res = await reserve(server, d, eventId, freeSeat[d.seatId], '');
    // a true validation/illegal-input failure -> top-level errors present.
    expect(Array.isArray(res.errors)).toBe(true);
    expect(res.errors.length).toBeGreaterThan(0);

    // store must NOT have been mutated by the rejected reserve.
    const after = await refetchSeat(server, d, eventId, freeSeat[d.seatId]);
    expect(after[d.seatHolder]).toBeNull();
    await server.stop();
  });

  it('release a HELD seat -> success; follow-up query shows the seat free again (persistence)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const { eventId, freeSeat } = await probeEvent(server, d);
    // first hold it
    const r1 = await reserve(server, d, eventId, freeSeat[d.seatId], 'To Release');
    expect(r1.errors == null || r1.errors.length === 0).toBe(true);
    const held = await refetchSeat(server, d, eventId, freeSeat[d.seatId]);
    expect(held[d.seatHolder]).toBe('To Release');

    const rel = await release(server, d, eventId, freeSeat[d.seatId]);
    expect(rel.errors == null || rel.errors.length === 0).toBe(true);
    const payload = rel.data[d.releaseM.name];
    expect(payload).toBeTruthy();
    // success branch: seat now free (holder null) OR a clearly-success typename
    const after = await refetchSeat(server, d, eventId, freeSeat[d.seatId]);
    expect(after[d.seatHolder]).toBeNull();
    await server.stop();
  });

  it('release an ALREADY-FREE seat -> already-free outcome; errors empty', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const { eventId, freeSeat } = await probeEvent(server, d);
    // seat is free at seed; release it directly
    const rel = await release(server, d, eventId, freeSeat[d.seatId]);
    expect(rel.errors == null || rel.errors.length === 0).toBe(true);
    const payload = rel.data[d.releaseM.name];
    expect(payload).toBeTruthy();
    const tn = typenameOf(payload);
    const signal =
      (tn && /(free|already|notheld|not_held|nothing)/i.test(tn)) ||
      collectHolderStrings(payload).some((s) => /free|already|not held|nothing/i.test(s)) ||
      Object.entries(payload).some(([k, v]) =>
        /(free|already|kind|status|code|reason|message|outcome)/i.test(k) && v != null && v !== '');
    expect(signal).toBe(true);
    await server.stop();
  });

  it('release a NON-EXISTENT seat -> seat-not-found outcome; errors empty', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const { eventId } = await probeEvent(server, d);
    const rel = await release(server, d, eventId, 'no-such-seat-zzz');
    expect(rel.errors == null || rel.errors.length === 0).toBe(true);
    const payload = rel.data[d.releaseM.name];
    expect(payload).toBeTruthy();
    const tn = typenameOf(payload);
    const signal =
      (tn && /(notfound|not_found|missing|unknown|invalid)/i.test(tn)) ||
      collectHolderStrings(payload).some((s) => /not.?found|missing|unknown|no\s|invalid/i.test(s)) ||
      Object.entries(payload).some(([k, v]) =>
        /(notfound|not_found|code|reason|message|kind|status)/i.test(k) && v != null && v !== '');
    expect(signal).toBe(true);
    await server.stop();
  });

  it('release outcomes (success vs already-free vs not-found) are mutually distinguishable', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const { eventId, freeSeat } = await probeEvent(server, d);
    // build success: hold then release
    await reserve(server, d, eventId, freeSeat[d.seatId], 'X');
    const okRes = await release(server, d, eventId, freeSeat[d.seatId]);
    const freeRes = await release(server, d, eventId, freeSeat[d.seatId]); // now already-free
    const nfRes = await release(server, d, eventId, 'no-such-seat-zzz');
    for (const r of [okRes, freeRes, nfRes]) {
      expect(r.errors == null || r.errors.length === 0).toBe(true);
    }
    const sig = (p: any): string => {
      const tn = typenameOf(p);
      if (tn) return 'TN:' + tn;
      for (const [k, v] of Object.entries(p)) {
        if (/(kind|status|code|outcome|result|type)/i.test(k) && typeof v === 'string') return k + '=' + v;
      }
      return JSON.stringify(p);
    };
    const a = sig(okRes.data[d.releaseM.name]);
    const b = sig(freeRes.data[d.releaseM.name]);
    const c = sig(nfRes.data[d.releaseM.name]);
    expect(a).not.toBe(b);
    expect(a).not.toBe(c);
    expect(b).not.toBe(c);
    await server.stop();
  });

  it('store factory yields a FRESH, isolated store (mutations on one server do not leak into another)', async () => {
    const server = await mkServer();
    const d = await discover(server);
    const { eventId, freeSeat } = await probeEvent(server, d);
    await reserve(server, d, eventId, freeSeat[d.seatId], 'Leaker');
    const held = await refetchSeat(server, d, eventId, freeSeat[d.seatId]);
    expect(held[d.seatHolder]).toBe('Leaker');
    await server.stop();

    // a brand-new server (new resolvers/store) must start from the seed again.
    const server2 = await mkServer();
    const d2 = await discover(server2);
    const probe2 = await probeEvent(server2, d2);
    const sameSeat = probe2.seats.find((s: any) => String(s[d2.seatId]) === String(freeSeat[d.seatId]));
    // The seeded state is deterministic; the seat must be free again in a fresh
    // server (proving the store is not module-global shared mutable state).
    expect(sameSeat).toBeTruthy();
    expect(sameSeat[d2.seatHolder]).toBeNull();
    await server2.stop();
  });
});
"""

    @classmethod
    def _ensure_workspace_built(cls):
        """ts-jest type-checks server src, which imports sibling workspace packages
        by their built `dist` types.  If those dist outputs are missing, run the
        repo's `compile` build once so the sibling packages resolve."""
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
        """L1: the seat-reservation module file exists at the required path."""
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
        assert re.search(
            r"export\s+(const|function)\s+\w*(create|make|store|seed|reservation|seat|event)\w*",
            src,
            re.IGNORECASE,
        ), "no store-factory export found"

    def test_module_has_no_other_example_imports(self):
        """L1: module is self-contained (does not import from sibling example files)."""
        src = self._read(self.MODULE_PATH)
        for m in re.finditer(r"""import[^;]*?from\s*['"]([^'"]+)['"]""", src):
            spec = m.group(1)
            if "examples/" in spec and "seatReservation" not in spec:
                pytest.fail(f"module imports another example file: {spec}")

    def test_public_index_not_modified_to_export_module(self):
        """L1: the package's public index.ts must not be wired to this example."""
        if not os.path.isfile(self.INDEX_PATH):
            pytest.skip("index.ts not present")
        src = self._read(self.INDEX_PATH)
        assert "seatReservation" not in src, (
            "index.ts must not export the seatReservation example"
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

    def test_harness_schema_event_seat_shape(self, harness_report):
        """L2: schema exposes event/seat with non-null ids, non-null seats list
        with non-null entries, and a nullable holder on a free seat."""
        self._passed(harness_report, r"schema exposes event/seat")

    def test_harness_event_hit_and_miss(self, harness_report):
        """L2: event fetch hit returns a clean seats list; miss returns null, no error."""
        self._passed(harness_report, r"event fetch HIT")

    def test_harness_reserve_single_input(self, harness_report):
        """L2: reserve takes a single structured input-object argument."""
        self._passed(harness_report, r"reserve takes a single structured")

    def test_harness_reserve_success_persists(self, harness_report):
        """L2: reserving a free seat succeeds and persists (follow-up query confirms)."""
        self._passed(harness_report, r"reserve a FREE seat")

    def test_harness_reserve_already_taken(self, harness_report):
        """L2: reserving a held seat yields already-taken naming the holder; store unchanged."""
        self._passed(harness_report, r"reserve an ALREADY-HELD seat")

    def test_harness_reserve_seat_not_found(self, harness_report):
        """L2: reserving a non-existent seat yields seat-not-found; errors empty."""
        self._passed(harness_report, r"reserve a NON-EXISTENT seat")

    def test_harness_reserve_outcomes_distinct(self, harness_report):
        """L2: the three reserve outcomes are mutually distinguishable from data alone."""
        self._passed(harness_report, r"three reserve outcomes are mutually distinguishable")

    def test_harness_empty_holder_validation(self, harness_report):
        """L2: empty holder name fails validation before resolvers; store not mutated."""
        self._passed(harness_report, r"explicitly EMPTY holder name fails VALIDATION")

    def test_harness_release_success_persists(self, harness_report):
        """L2: releasing a held seat succeeds and the seat becomes free again."""
        self._passed(harness_report, r"release a HELD seat")

    def test_harness_release_already_free(self, harness_report):
        """L2: releasing a free seat yields already-free outcome; errors empty."""
        self._passed(harness_report, r"release an ALREADY-FREE seat")

    def test_harness_release_seat_not_found(self, harness_report):
        """L2: releasing a non-existent seat yields seat-not-found; errors empty."""
        self._passed(harness_report, r"release a NON-EXISTENT seat")

    def test_harness_release_outcomes_distinct(self, harness_report):
        """L2: release outcomes (success/already-free/not-found) are mutually distinguishable."""
        self._passed(harness_report, r"release outcomes .* are mutually distinguishable")

    def test_harness_store_factory_fresh(self, harness_report):
        """L2: the store factory yields a fresh, isolated store per server (no global leak)."""
        self._passed(harness_report, r"store factory yields a FRESH")
