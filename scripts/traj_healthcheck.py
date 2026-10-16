#!/usr/bin/env python3
"""Trajectory health check — scan the most recent trajectories for OBVIOUS errors.

Red flags it looks for, per cell (newest N per mode):
  - UNKNOWN-CMD : "Unknown command: /skill" in the first user msg -> /skill-id failed to register
  - 0-TURN-DONE : trajectory finished (has eval report) but 0 assistant turns -> agent died at start
  - NO-TOOLS    : >0 turns but never called a tool -> likely chatter / no real work
  - API-ERROR   : api_error / overloaded / 5xx / "Connection error" in the output log
  - EMPTY-RESP  : assistant turns but every one had empty content -> gateway dropped content (CCR bug)

Prints a compact PASS/SUSPECT verdict so a 30-min poll can tell healthy from garbage at a glance.
"""
import glob, json, os, re, sys, subprocess
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT = os.environ.get("AGENT", "claude")
MODEL = os.environ.get("MODEL_NAME", "claude-haiku-4-5")
N = int(os.environ.get("HC_N", "12"))  # newest N trajectories per mode
PB = f"{ROOT}/outputs/claude_process/{AGENT}/{MODEL}"
RB = f"{ROOT}/outputs/reports/{AGENT}/{MODEL}"
EDIT = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
ERR_PAT = re.compile(r"(api_error|overloaded_error|Connection error|rate.?limit|50[023] |Internal Server Error|ECONNREFUSED)", re.I)


def scan(tf):
    turns = 0; tools = Counter(); reg = None; unknown = False; nonempty_assist = 0; builtin_collision = False
    try:
        for l in open(tf, errors="ignore"):
            try: e = json.loads(l)
            except: continue
            t = e.get("type")
            if t == "user" and reg is None:
                cont = e.get("message", {}).get("content")
                # only inspect the command-injection text, NOT tool_result blobs (a bash
                # "Unknown command: bin" inside a tool_result is not a slash-cmd failure)
                if isinstance(cont, str):
                    c = cont
                elif isinstance(cont, list):
                    c = " ".join(x.get("text", "") for x in cont
                                 if isinstance(x, dict) and x.get("type") == "text")
                else:
                    c = ""
                if "<command-name>/" in c: reg = True
                if "Unknown command: /" in c: unknown = True; reg = False
            if t == "user" and "!`git diff origin/HEAD" in json.dumps(e.get("message", {}).get("content")):
                builtin_collision = True
            if t == "assistant":
                turns += 1
                got = False
                for x in (e.get("message", {}).get("content") or []):
                    if isinstance(x, dict):
                        if x.get("type") == "tool_use": tools[x["name"]] += 1; got = True
                        elif x.get("type") == "text" and x.get("text", "").strip(): got = True
                if got: nonempty_assist += 1
    except FileNotFoundError:
        pass
    return turns, tools, reg, unknown, nonempty_assist, builtin_collision


def main():
    print(f"### traj healthcheck  {AGENT}/{MODEL}  (newest {N}/mode)")
    # liveness
    try:
        code = subprocess.run(["curl", "-s", "-m", "5", "-o", "/dev/null", "-w", "%{http_code}",
                               os.environ.get("ANTHROPIC_BASE_URL", "http://127.0.0.1:3456") + "/"],
                              capture_output=True, text=True, timeout=8).stdout.strip()
        print(f"CCR gateway: http {code}  {'OK' if code=='200' else 'CHECK'}")
    except Exception as e:
        print(f"CCR gateway: ERROR {e}")
    total_flags = Counter()
    for mode, suf in (("none", "use-skill-false"), ("one", "use-skill-one")):
        tjs = sorted(glob.glob(f"{PB}/batch*/claude_thinking/*{suf}*.jsonl"), key=os.path.getmtime)[-N:]
        if not tjs:
            print(f"\n[{mode}] no trajectories yet"); continue
        rows = []
        for tf in tjs:
            skill = re.search(r"claude_(.+?)_use-agent", os.path.basename(tf)).group(1)
            batch = re.search(r"/(batch\d+)/", tf).group(1)
            turns, tools, reg, unknown, ne, collision = scan(tf)
            # does an eval report exist for this cell (i.e. it's 'done')?
            done = bool(glob.glob(f"{RB}/{batch}/eval/eval_report_{glob.escape(skill)}_*{suf}*.json"))
            # output log error scan
            logs = glob.glob(f"{PB}/{batch}/claude_output/claude_log_{glob.escape(skill)}_*{suf}*.log")
            api_err = False
            if logs:
                lg = max(logs, key=os.path.getmtime)
                try: api_err = bool(ERR_PAT.search(open(lg, errors="ignore").read()))
                except: pass
            flags = []
            if unknown: flags.append("UNKNOWN-CMD")
            if collision and turns == 0: flags.append("BUILTIN-COLLISION")
            elif done and turns == 0: flags.append("0-TURN-DONE")
            if turns > 0 and not tools: flags.append("NO-TOOLS")
            if turns > 0 and ne == 0: flags.append("EMPTY-RESP")
            if api_err: flags.append("API-ERROR")
            for f in flags: total_flags[f] += 1
            rows.append((batch, skill, turns, sum(tools.values()), any(t in EDIT for t in tools), done, flags))
        nflag = sum(1 for r in rows if r[6])
        print(f"\n[{mode}] {len(rows)} recent cells, {nflag} flagged")
        for b, s, tn, tc, ed, dn, fl in rows:
            mark = ("⚠ " + ",".join(fl)) if fl else ("ok" if (tn > 0 or not dn) else "ok")
            st = "done" if dn else "live"
            print(f"   [{b:8}] {s[:34]:34} turns={tn:3} tools={tc:3} edit={'Y' if ed else '-'} {st:4} {mark}")

    print()
    if total_flags:
        print(f"VERDICT: SUSPECT — flags: {dict(total_flags)}")
    else:
        print("VERDICT: PASS — no obvious errors in recent trajectories")


if __name__ == "__main__":
    main()
