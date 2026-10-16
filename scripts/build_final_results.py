#!/usr/bin/env python3
"""
Assemble the FINAL canonical dataset (latest eval report per cell, so the 2026-07-23
re-runs override the old infra-fake-0 scores) and emit one big HTML table per
harness x model combo under results/final_results/, at the finest granularity:
one row per (skill, requirement=batch) with none / one / delta.
Also writes a tidy CSV per combo + a combined CSV.
"""
import glob, json, os, re, csv, html, sys
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from src.utils.infra_errors import classify_report, classify_log_head  # noqa: E402

CONFIGS = [  # (label, [report base_dirs], [trajectory base_dirs], agent)
    ("codex__gpt-5.4-mini", ["codex/gpt-5.4-mini"],
     ["outputs/codex_process/codex/gpt-5.4-mini"], "codex"),
    ("codex__Kimi-K2.6",    ["codex/Kimi-K2.6"],
     ["outputs/codex_process/codex/Kimi-K2.6"], "codex"),
    ("claude__Kimi-K2.6",   ["claude/Kimi-K2.6"],
     ["outputs/claude_process/claude/Kimi-K2.6", "outputs/claude_process/Kimi-K2.6"], "claude"),
    # haiku reports exist under two directory layouts (one-level and
    # agent/model). Search both; the latest report per cell wins.
    ("claude__haiku-4-5",   ["claude-haiku-4-5", "claude/claude-haiku-4-5"],
     ["outputs/claude_process/claude-haiku-4-5", "outputs/claude_process/claude/claude-haiku-4-5"], "claude"),
]

TRAJ_RE = {
    "claude": re.compile(r"^claude_log_(?P<skill>.+?)_use-agent-\w+_use-skill-(?P<mode>false|one)_(?P<ts>\d{8}_\d{6})\.log$"),
    "codex":  re.compile(r"^codex_log_(?P<skill>.+?)_use-agent-\w+_use-skill-(?P<mode>false|one)_(?P<ts>\d{8}_\d{6})\.log$"),
}
TRAJ_SUBDIR = {"claude": "claude_output", "codex": "codex_output"}

def index_traj_logs(traj_dirs, agent):
    """{(skill, idx, mode): sorted [(ts, logpath)]} over every interaction log."""
    cells = {}
    fre = TRAJ_RE[agent]
    for base in traj_dirs:
        for p in glob.glob(f"{base}/*/{TRAJ_SUBDIR[agent]}/*.log"):
            sub = p.split(f"/{TRAJ_SUBDIR[agent]}/")[0].rsplit("/", 1)[-1]
            m = re.match(r"(?:batch|ext)(\d+)$", sub)
            if not m:
                continue
            fm = fre.match(os.path.basename(p))
            if not fm:
                continue
            mode = "none" if fm.group("mode") == "false" else "one"
            cells.setdefault((fm.group("skill"), m.group(1), mode), []).append((fm.group("ts"), p))
    for v in cells.values():
        v.sort()
    return cells

def scored_run_log_class(traj_index, skill, idx, mode, report_ts):
    """Infra class of the interaction log BOUND to a report (last log ts <= report ts).
    None = clean or no log found (unverifiable -> accept)."""
    logs = traj_index.get((skill, idx, mode)) or []
    prior = [lp for ts, lp in logs if ts <= report_ts]
    if not prior:
        return None
    try:
        with open(prior[-1], errors="replace") as f:
            return classify_log_head(f.read(300))
    except Exception:
        return None

def skills():
    c = yaml.safe_load(open("config/benchmark_config.yaml"))
    def fs(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "skills" and isinstance(v, list) and len(v) > 40: return v
                r = fs(v)
                if r: return r
        elif isinstance(o, list):
            for v in o:
                r = fs(v)
                if r: return r
    return sorted((s["id"] if isinstance(s, dict) else s) for s in fs(c))

SKILLS = skills()
BATCHES = [f"batch{i}" for i in range(1, 11)]

FN_RE = re.compile(
    r"^eval_report_(?P<skill>.+?)_use-agent-\w+_use-skill-(?P<mode>false|one)_(?P<ts>\d{8}_\d{6})\.json$")

INFRA_LOG = []  # (combo, skill, batch, mode, ts, infra_class) for every skipped report

def index_config(base_dirs):
    """One pass over every eval report -> {(skill, batch_idx, 'none'|'one'): [(ts, path)...]}
    ALL reports per cell, ts-sorted. batch{i} and legacy dir names collapse to idx i."""
    cells = {}
    for base in base_dirs:
        for p in glob.glob(f"outputs/reports/{base}/*/eval/eval_report_*.json"):
            sub = p.split("/eval/")[0].rsplit("/", 1)[-1]  # batch7 or ext7
            m = re.match(r"(?:batch|ext)(\d+)$", sub)
            if not m:
                continue
            idx = m.group(1)
            fm = FN_RE.match(os.path.basename(p))
            if not fm:
                continue
            mode = "none" if fm.group("mode") == "false" else "one"
            key = (fm.group("skill"), idx, mode)
            cells.setdefault(key, []).append((fm.group("ts"), p))
    for v in cells.values():
        v.sort(reverse=True)  # newest first
    return cells

def canonical(index, traj_index, skill, batch, mode, combo=""):
    """Newest INFRA-CLEAN report for a cell -> (score|None, is_na).

    Walks reports newest->oldest and refuses any that (a) classifies as an
    infra error from the report itself (workspace lost, missing tool, setup
    failure), or (b) whose BOUND interaction log — the last log written before
    the report — starts with a 0-turn marker (Unknown command / API dead).
    (b) is essential: a 0-turn run's eval report looks like a legitimate 0
    against the initial repo; only the trajectory head reveals it (2026-07-26
    audit: 63 such cells). Timeout reports are policy-counted as 0.
    A cell with only infra reports is N/A — it must be re-run, not scored."""
    hits = index.get((skill, batch[5:], mode)) or []
    for ts, path in hits:
        try:
            d = json.load(open(path))
        except Exception:
            continue
        cls = classify_report(d)
        if cls is None and d.get("stage") != "timeout":
            cls = scored_run_log_class(traj_index, skill, batch[5:], mode, ts)
        if cls:
            INFRA_LOG.append((combo, skill, batch, mode, ts, cls))
            continue
        s = d.get("evaluation_scores", {}).get("overall_score")
        if s is None:
            INFRA_LOG.append((combo, skill, batch, mode, ts, "container_lost"))
            continue
        return (float(s), False)
    return (None, True)  # no infra-clean report -> N/A (needs re-run)

def cell_html(v, na):
    if na:
        return '<td class="na">N/A</td>'
    pct = v * 100
    # green scale for high, red for low
    r = int(220 - min(pct, 100) * 1.5)
    g = int(70 + min(pct, 100) * 1.5)
    return f'<td style="background:rgb({max(r,70)},{min(g,220)},80);color:#111">{pct:.0f}</td>'

def delta_html(n, o, na_n, na_o):
    if na_n or na_o:
        return '<td class="na">–</td>'
    d = (o - n) * 100
    col = "#1a7a1a" if d > 0.5 else ("#b02020" if d < -0.5 else "#666")
    sign = "+" if d > 0 else ""
    return f'<td style="color:{col};font-weight:600">{sign}{d:.0f}</td>'

def build():
    os.makedirs("results/final_results", exist_ok=True)
    combined = [["harness_model", "skill", "requirement_batch", "none_pass_rate", "one_pass_rate", "delta_pp"]]
    for label, base_dirs, traj_dirs, agent in CONFIGS:
        rows_csv = [["skill", "requirement_batch", "none_pass_rate", "one_pass_rate", "delta_pp"]]
        body = []
        # per-config aggregate accumulators
        alln = []; allo = []
        idx_map = index_config(base_dirs)
        traj_map = index_traj_logs(traj_dirs, agent)
        for skill in SKILLS:
            sk_n = []; sk_o = []
            for b in BATCHES:
                n, na_n = canonical(idx_map, traj_map, skill, b, "none", label)
                o, na_o = canonical(idx_map, traj_map, skill, b, "one", label)
                body.append(
                    f'<tr><td class="sk">{html.escape(skill)}</td><td class="bt">{b[5:]}</td>'
                    f'{cell_html(n, na_n)}{cell_html(o, na_o)}{delta_html(n, o, na_n, na_o)}</tr>'
                )
                rows_csv.append([skill, b,
                                 "" if na_n else f"{n*100:.2f}",
                                 "" if na_o else f"{o*100:.2f}",
                                 "" if (na_n or na_o) else f"{(o-n)*100:.2f}"])
                combined.append([label, skill, b,
                                 "" if na_n else f"{n*100:.2f}",
                                 "" if na_o else f"{o*100:.2f}",
                                 "" if (na_n or na_o) else f"{(o-n)*100:.2f}"])
                if not na_n: sk_n.append(n); alln.append(n)
                if not na_o: sk_o.append(o); allo.append(o)
        gm_n = sum(alln) / len(alln) * 100 if alln else 0
        gm_o = sum(allo) / len(allo) * 100 if allo else 0
        gm_d = gm_o - gm_n
        # write CSV
        with open(f"results/final_results/{label}_cells.csv", "w", newline="") as f:
            csv.writer(f).writerows(rows_csv)
        # write HTML
        page = f"""<!doctype html><html><head><meta charset=utf-8><title>{label} — final</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1115;color:#e6e6e6}}
.wrap{{max-width:1100px;margin:0 auto;padding:24px}}
h1{{font-size:20px;margin:0 0 4px}} .sub{{color:#9aa;font-size:13px;margin-bottom:16px}}
.gm{{display:inline-block;background:#1b2130;border:1px solid #2a3345;border-radius:8px;padding:10px 16px;margin:0 8px 16px 0;font-size:14px}}
.gm b{{font-size:18px}}
table{{border-collapse:collapse;width:100%;font-size:12px}}
th,td{{padding:3px 8px;text-align:center;border-bottom:1px solid #222}}
th{{position:sticky;top:0;background:#1b2130;z-index:1}}
td.sk{{text-align:left;color:#cdd;max-width:230px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
td.bt{{color:#889}} td.na{{color:#556}}
tr:hover td{{outline:1px solid #38455f}}
</style></head><body><div class=wrap>
<h1>{label.replace('__',' × ')} — final per-requirement pass rates</h1>
<div class=sub>7 env-fixed skills re-run 2026-07-23 (override old infra-fake-0); rest = finalized runs. Cell = pass_rate (0-100). Δ = one − none (pp).</div>
<div class=gm>none <b>{gm_n:.1f}%</b></div><div class=gm>one <b>{gm_o:.1f}%</b></div>
<div class=gm>Δ (one−none) <b style="color:{'#4caf50' if gm_d>0 else '#e57373'}">{'+' if gm_d>0 else ''}{gm_d:.1f}pp</b></div>
<table><thead><tr><th>skill</th><th>req</th><th>none</th><th>one</th><th>Δ</th></tr></thead>
<tbody>{''.join(body)}</tbody></table>
</div></body></html>"""
        open(f"results/final_results/{label}.html", "w").write(page)
        print(f"  {label}: none={gm_n:.1f}% one={gm_o:.1f}% Δ={gm_d:+.1f}pp -> {label}.html + _cells.csv")
    with open("results/final_results/ALL_combined_cells.csv", "w", newline="") as f:
        csv.writer(f).writerows(combined)
    print("wrote results/final_results/ (4 html + 4 csv + ALL_combined_cells.csv)")

    # ---- PROACTIVE INFRA REPORT ------------------------------------------
    # Every report that was REFUSED for an infra error, and every cell that is
    # N/A because no infra-clean report exists (=> must be re-run). The run is
    # only final when the N/A count is ZERO.
    with open("results/final_results/infra_refused_reports.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["combo", "skill", "batch", "mode", "report_ts", "infra_class"])
        w.writerows(sorted(INFRA_LOG))
    from collections import Counter
    by_class = Counter(x[5] for x in INFRA_LOG)
    rows = list(csv.reader(open("results/final_results/ALL_combined_cells.csv")))[1:]
    na = [(r[0], r[1], r[2], m) for r in rows for m, i in (("none", 3), ("one", 4)) if r[i] == ""]
    print("\n=== INFRA REPORT (proactive) ===")
    print(f"refused reports: {len(INFRA_LOG)}  by class: {dict(by_class)}")
    print(f"cells with NO infra-clean report (N/A -> MUST RE-RUN): {len(na)}")
    for combo, skill, batch, mode in na[:60]:
        print(f"  RERUN {combo:22} {skill:36} {batch:8} {mode}")
    if len(na) > 60:
        print(f"  ... and {len(na)-60} more")
    print("full refusal list: results/final_results/infra_refused_reports.csv")
    if not na:
        print("*** INFRA-CLEAN: every scored cell passed the gate ***")

if __name__ == "__main__":
    build()
